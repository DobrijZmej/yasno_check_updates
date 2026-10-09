"""
Модуль для управління станами та відстеження змін у розкладі.
Працює з конкретними датами замість today/tomorrow.
"""

import json
import logging
import os
from data_processor import calculate_schedule_hash

logger = logging.getLogger(__name__)


def load_state_log(state_file="states.json"):
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


def save_state_log(state, state_file="states.json"):
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
        source: джерело даних ('yasno', 'dtek', 'none')
    
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
        import json
        periods_key = f"{group}_{date_str}_periods"
        state[periods_key] = json.dumps(periods)
        logger.debug(f"💾 Збережено {len(periods)} періодів для {state_key}")
    
    logger.debug(f"🔄 Оновлено стан для {state_key}")
    return state


def get_old_periods(group, date_str, state):
    """
    Отримуємо збережені періоди для порівняння.
    
    Args:
        group: група (наприклад "6.2")
        date_str: дата у форматі YYYY-MM-DD
        state: поточний стан
    
    Returns:
        list: список періодів [{start: int, end: int}, ...] або None якщо немає
    """
    periods_key = f"{group}_{date_str}_periods"
    periods_json = state.get(periods_key)
    
    if not periods_json:
        return None
    
    try:
        import json
        periods = json.loads(periods_json)
        logger.debug(f"📂 Завантажено {len(periods)} старих періодів для {group}_{date_str}")
        return periods
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"⚠️ Помилка парсингу періодів для {periods_key}")
        return None


def cleanup_old_states(state, days_to_keep=7):
    """
    Видаляємо старі записи зі стану (старші N днів).
    НЕ чіпаємо ключі alarm (last_alarm_*) - вони мають власну логіку очищення.
    
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
        # Пропускаємо alarm ключі - вони мають власну логіку
        if key.startswith('last_alarm_'):
            continue
        
        # Ключ має формат "група_YYYY-MM-DD"
        parts = key.split('_')
        if len(parts) >= 2:
            date_part = parts[-1]  # Остання частина - дата
            if date_part < cutoff_date:
                keys_to_remove.append(key)
    
    if keys_to_remove:
        logger.info(f"🧹 Видаляємо {len(keys_to_remove)} старих записів зі стану")
        for key in keys_to_remove:
            del state[key]
            logger.debug(f"   Видалено: {key}")
    
    return state
