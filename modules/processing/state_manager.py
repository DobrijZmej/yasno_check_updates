"""
Модуль для управління станами та відстеження змін у розкладі.
"""

import json
import logging
import os
import hashlib

logger = logging.getLogger(__name__)


OUTAGE_TYPES = ("Definite", "Possible")


def normalize_schedule_slots(slots):
    """Return a canonical representation of outage intervals.

    Providers can describe the same outage either as one long slot or as a
    sequence of adjacent hourly slots.  Sorting and merging by outage type
    makes those representations equivalent for change detection.
    """
    intervals_by_type = {slot_type: [] for slot_type in OUTAGE_TYPES}

    for slot in slots or []:
        if not isinstance(slot, dict):
            continue

        slot_type = slot.get("type")
        if slot_type not in intervals_by_type:
            continue

        try:
            start = int(slot["start"])
            end = int(slot["end"])
        except (KeyError, TypeError, ValueError):
            continue

        if not 0 <= start < end <= 1440:
            continue

        intervals_by_type[slot_type].append((start, end))

    normalized = []
    for slot_type, intervals in intervals_by_type.items():
        merged = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))

        normalized.extend(
            {"start": start, "end": end, "type": slot_type}
            for start, end in merged
        )

    return sorted(
        normalized,
        key=lambda slot: (slot["start"], slot["end"], slot["type"]),
    )


def calculate_outage_duration(slots):
    """Return total outage minutes without double-counting overlaps."""
    intervals = sorted(
        (slot["start"], slot["end"])
        for slot in normalize_schedule_slots(slots)
    )
    merged = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return sum(end - start for start, end in merged)


def get_stored_schedule_slots(state, group, date_str):
    """Read canonical intervals saved for an earlier version of a schedule."""
    value = state.get(f"{group}_{date_str}_periods")
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return None
    if not isinstance(value, list):
        return None
    return normalize_schedule_slots(value)


def _schedule_date(day_data):
    """Normalize provider-specific ISO timestamps to a calendar date."""
    value = day_data.get("date", "")
    return value[:10] if isinstance(value, str) else str(value)


def _calculate_legacy_schedule_hash(day_data):
    """Calculate the pre-normalization hash for a seamless state migration."""
    hash_str = ""
    for slot in day_data.get("slots", []):
        if slot.get("type") == "Definite":
            hash_str += f"{slot['start']}-{slot['end']}"
        elif slot.get("type") == "Possible":
            hash_str += f"P{slot['start']}-{slot['end']}"

    if "date" in day_data:
        hash_str += day_data["date"]

    return hashlib.md5(hash_str.encode()).hexdigest() if hash_str else ""


def calculate_schedule_hash(day_data):
    """
    Обчислюємо хеш для відстеження змін у розкладі.
    
    Args:
        day_data: dict з полями 'slots' та 'date'
    
    Returns:
        str: хеш розкладу
    """
    if not day_data or "slots" not in day_data:
        return ""

    canonical_schedule = {
        "date": _schedule_date(day_data),
        "slots": normalize_schedule_slots(day_data["slots"]),
    }
    hash_str = json.dumps(
        canonical_schedule,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.md5(hash_str.encode()).hexdigest()


def load_state(state_file="states.json"):
    """
    Завантажуємо збережений стан з файлу.
    
    Args:
        state_file: шлях до файлу зі станами
    
    Returns:
        dict: словник станів {group_date: hash, ...}
    """
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                logger.debug(f"📂 Завантажено стан з {state_file}: {len(state)} записів")
                return state
        except Exception as e:
            logger.error(f"❌ Помилка читання {state_file}: {e}")
            return {}
    else:
        logger.debug(f"📂 Файл {state_file} не знайдено, створюємо новий стан")
        return {}


def save_state(state, state_file="states.json"):
    """
    Зберігаємо стан у файл.
    
    Args:
        state: словник станів
        state_file: шлях до файлу для збереження
    """
    try:
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        logger.debug(f"💾 Збережено стан у {state_file}: {len(state)} записів")
    except Exception as e:
        logger.error(f"❌ Помилка запису {state_file}: {e}")


def is_changed(group, date_str, day_data, state, source=''):
    """
    Перевіряємо чи змінився розклад для конкретної дати.
    
    Args:
        group: група (наприклад "6.2")
        date_str: дата у форматі YYYY-MM-DD
        day_data: дані дня з полями 'slots' та 'date'
        state: поточний стан
        source: джерело даних ('yasno', 'dtek', 'dtek_fact', 'standard')
    
    Returns:
        tuple: (bool, str, str) - (чи змінилося, старий хеш, новий хеш)
    """
    # Формуємо ключ стану: група_дата
    state_key = f"{group}_{date_str}"
    
    # Обчислюємо новий хеш
    new_hash = calculate_schedule_hash(day_data)
    
    # Додаємо джерело до хешу для логування
    new_hash_with_source = new_hash + (f" (source: {source})" if source else "")
    
    # Отримуємо старий хеш
    old_hash = state.get(state_key, "")

    # Existing installations store hashes of raw provider slots.  If the old
    # value matches the current raw representation, migrate it without
    # reporting a schedule change on the first run after this update.
    legacy_hash = _calculate_legacy_schedule_hash(day_data)
    if old_hash and old_hash != new_hash and old_hash == legacy_hash:
        logger.info(f"🔄 Стандартизовано збережений хеш для {state_key}")
        state[state_key] = new_hash
        old_hash = new_hash
    
    # Якщо хеш змінився - є зміна
    changed = (old_hash != new_hash) and new_hash != ""
    
    if changed:
        logger.info(f"🔄 Виявлено зміну розкладу для групи {group} на {date_str}")
        logger.info(f"   Старий хеш: {old_hash}")
        logger.info(f"   Новий хеш: {new_hash_with_source}")
    else:
        if new_hash == "":
            logger.warning(f"⚠️ Немає даних для {state_key}")
        else:
            logger.info(f"✅ Розклад не змінився для {state_key}")
            logger.info(f"   Старий хеш: {old_hash}")
            logger.info(f"   Новий хеш: {new_hash_with_source}")
    
    return changed, old_hash, new_hash


def update_state(group, date_str, new_hash, state, periods=None):
    """
    Оновлюємо стан для конкретної групи та дати.
    
    Args:
        group: група (наприклад "6.2")
        date_str: дата у форматі YYYY-MM-DD
        new_hash: новий хеш розкладу
        state: поточний стан (буде змінено)
        periods: опціонально - список періодів [{start: int, end: int}, ...] для аналізу змін
    
    Returns:
        dict: оновлений стан
    """
    state_key = f"{group}_{date_str}"
    state[state_key] = new_hash
    
    # Зберігаємо періоди в окремому ключі для порівняння (якщо передані)
    if periods is not None:
        periods_key = f"{group}_{date_str}_periods"
        normalized_periods = normalize_schedule_slots(periods)
        state[periods_key] = json.dumps(normalized_periods)
        logger.debug(f"💾 Збережено {len(normalized_periods)} періодів для {state_key}")
    
    logger.debug(f"🔄 Оновлено стан для {state_key}")
    return state


def cleanup_old_states(state, days_to_keep=7):
    """
    Видаляємо старі записи зі стану (старші N днів).
    
    Args:
        state: поточний стан
        days_to_keep: скільки днів зберігати
    
    Returns:
        dict: очищений стан
    """
    from datetime import datetime, timedelta
    
    cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).strftime('%Y-%m-%d')
    
    keys_to_remove = []
    for key in state.keys():
        # Пропускаємо service ключі (last_*, etc)
        if key.startswith('last_'):
            continue
        
        # Ключ має формат "група_YYYY-MM-DD" або "група_YYYY-MM-DD_periods"
        parts = key.split('_')
        if len(parts) >= 2:
            # Шукаємо частину з датою (YYYY-MM-DD формат)
            for part in parts:
                if len(part) == 10 and part.count('-') == 2:
                    if part < cutoff_date:
                        keys_to_remove.append(key)
                    break
    
    if keys_to_remove:
        logger.info(f"🧹 Видаляємо {len(keys_to_remove)} старих записів зі стану")
        for key in keys_to_remove:
            del state[key]
            logger.debug(f"   Видалено: {key}")
    
    return state


def clear_hash_for_date(group, date_str, state):
    """
    Очищає хеш та періоди для конкретної дати (для примусового оновлення).
    
    Args:
        group: група (наприклад "6.2")
        date_str: дата у форматі YYYY-MM-DD
        state: поточний стан
    
    Returns:
        dict: оновлений стан
    """
    state_key = f"{group}_{date_str}"
    periods_key = f"{group}_{date_str}_periods"
    
    if state_key in state:
        del state[state_key]
        logger.info(f"🗑️ Видалено хеш {state_key}")
    
    if periods_key in state:
        del state[periods_key]
        logger.info(f"🗑️ Видалено періоди {periods_key}")
    
    return state


class StateManager:
    """Клас для керування станом сповіщень та розкладів"""
    
    def __init__(self, state_file="states.json"):
        """
        Ініціалізація менеджера станів
        
        Args:
            state_file: Шлях до файлу зі станами
        """
        self.state_file = state_file
        self.state = load_state(state_file)
    
    def save(self):
        """Зберігає поточний стан у файл"""
        save_state(self.state, self.state_file)
    
    def get_notification_sent(self, notification_key):
        """
        Перевіряє чи було відправлено сповіщення з даним ключем
        
        Args:
            notification_key: Ключ сповіщення (наприклад "hourly_notification_12.1_2025-02-01_14")
        
        Returns:
            bool: True якщо сповіщення вже було відправлено
        """
        return notification_key in self.state
    
    def mark_notification_sent(self, notification_key, timestamp):
        """
        Відмічає що сповіщення було відправлено
        
        Args:
            notification_key: Ключ сповіщення
            timestamp: Час відправки у форматі ISO
        """
        self.state[notification_key] = timestamp
        self.save()
        logger.debug(f"✅ Відмічено сповіщення як відправлене: {notification_key}")
