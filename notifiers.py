"""
Модуль для формування та відправки повідомлень.
Підтримує Telegram Bot API та зовнішній API.
"""

import json
import logging
import requests
from data_processor import consolidate_periods

logger = logging.getLogger(__name__)


def format_time(minutes_value, minutes_adjustment=0):
    """Конвертуємо хвилини від початку дня у формат HH:MM"""
    try:
        total_minutes = int(minutes_value) + int(minutes_adjustment)
        
        if total_minutes < 0:
            return None
        
        # Обробляємо 24:00 як кінець дня
        if total_minutes >= 1440:  # 1440 = 24*60
            if total_minutes == 1440:
                return "24:00"  # Кінець дня
            else:
                return None  # Більше 24:00 - некоректно

        hours = total_minutes // 60
        minutes = total_minutes % 60
        
        return f"{hours:02d}:{minutes:02d}"
    except (ValueError, TypeError):
        return None


def format_duration(minutes):
    """Форматуємо тривалість у форматі 'H:MM' або '0:MM'"""
    try:
        total_minutes = int(minutes)
        if total_minutes <= 0:
            return "0:00"
        
        hours = total_minutes // 60
        mins = total_minutes % 60
        
        return f"{hours}:{mins:02d}"
    except (ValueError, TypeError):
        return "??"


def extract_definite_slots(day_data):
    """Витягуємо тільки слоти з типом 'Definite' (планові відключення)"""
    logger.debug("🔍 extract_definite_slots")
    
    if not day_data or "slots" not in day_data:
        logger.debug("❌ Немає слотів")
        return []
    
    slots = day_data["slots"]
    logger.debug(f"📋 Загальна кількість слотів: {len(slots)}")
    
    definite_slots = []
    for i, slot in enumerate(slots):
        slot_type = slot.get("type", "Unknown")
        start = slot.get("start", "N/A")
        end = slot.get("end", "N/A")
        logger.debug(f"  Слот {i+1}: тип='{slot_type}', {start}-{end}")
        
        if slot_type == "Definite":
            definite_slots.append({
                "start": slot["start"],
                "end": slot["end"]
            })
            logger.debug(f"  ✅ Додано Definite слот: {start}-{end}")
        else:
            logger.debug(f"  ⏩ Пропущено слот типу '{slot_type}'")
    
    logger.debug(f"📊 Знайдено {len(definite_slots)} Definite слотів")
    return definite_slots


def calculate_total_outage_minutes(periods):
    """Обчислюємо загальну тривалість відключень у хвилинах"""
    if not periods:
        return 0
    
    consolidated = consolidate_periods(periods)
    total = sum(p['end'] - p['start'] for p in consolidated)
    return total


def compare_schedules(old_periods, new_periods):
    """
    Порівнюємо старий та новий розклади.
    Показуємо різницю в тривалості відключень.
    
    Args:
        old_periods: старі періоди (список [{start: int, end: int}, ...]) або None
        new_periods: нові періоди (список [{start: int, end: int}, ...])
    
    Returns:
        str: опис змін або None
    """
    if not old_periods or not new_periods:
        return None
    
    old_minutes = calculate_total_outage_minutes(old_periods)
    new_minutes = calculate_total_outage_minutes(new_periods)
    
    diff_minutes = new_minutes - old_minutes
    
    if diff_minutes == 0:
        return None
    
    # Форматуємо різницю
    diff_hours = abs(diff_minutes) // 60
    diff_mins = abs(diff_minutes) % 60
    
    if diff_hours > 0 and diff_mins > 0:
        diff_str = f"{diff_hours} год {diff_mins} хв"
    elif diff_hours > 0:
        diff_str = f"{diff_hours} год"
    else:
        diff_str = f"{diff_mins} хв"
    
    if diff_minutes > 0:
        return f"\n📊 Відключення тепер довші на {diff_str}"
    else:
        return f"\n📊 Відключень тепер менше на {diff_str}"


def process_day(date_str, day_data, group, day_label="сьогодні", source_info=None, old_periods=None):
    """
    Формуємо повідомлення про зміни в розкладі відключень для вказаного дня.
    
    Args:
        date_str: дата у форматі YYYY-MM-DD
        day_data: дані дня з полями 'slots', 'date'
        group: група (наприклад "6.2")
        day_label: текстова мітка ("сьогодні", "завтра")
        source_info: інформація про джерело {'source': str, 'update_time': str}
    
    Returns:
        str: форматоване повідомлення
    """
    # Визначаємо джерело оновлення
    source = 'невідоме джерело'
    is_standard = False
    
    if source_info:
        source_name = source_info.get('source', 'unknown')
        update_time = source_info.get('update_time')
        
        if source_name == 'yasno':
            source = 'YASNO'
        elif source_name == 'dtek':
            source = f"ДТЕК"
            if update_time:
                source += f" (оновлено {update_time})"
        elif source_name == 'dtek_fact':
            source = f"ДТЕК (графік з аварій)"
            if update_time:
                source += f" (оновлено {update_time})"
        elif source_name == 'standard':
            source = 'Стандартний графік білих зон'
            is_standard = True
    
    result = f"Оновлення розкладу для групи {group} на {date_str} ({day_label})\nДжерело: {source}"
    
    # Якщо використовується стандартний розклад - додаємо попередження
    if is_standard:
        result += "\n⚠️ <b>УВАГА:</b> Офіційний графік не опублікований. Використовується стандартний графік білих зон."
    
    logger.info(f"Обробка розкладу для групи {group} на {date_str}, джерело: {source}")
    
    # Витягуємо тільки планові відключення
    definite_slots = extract_definite_slots(day_data)
    
    if not definite_slots:
        result += "\n• Розклад відключень не опублікований"
    else:
        periods = consolidate_periods(definite_slots)
        result += f"\n• Планові відключення ({len(periods)} період{'и' if len(periods) > 1 else ''}):"
        
        for period in periods:
            start_time = format_time(period['start'])
            end_time = format_time(period['end'])
            duration_minutes = period['end'] - period['start']
            duration_str = format_duration(duration_minutes)
            
            if start_time and end_time:
                result += f"\n  ⚡ {start_time} - {end_time} ({duration_str})"
                logger.info(f"Період відключення ({date_str}): {start_time} - {end_time} ({duration_str})")
        
        # Якщо є попередній розклад - додаємо порівняння
        if old_periods is not None:
            logger.info(f"Порівняння з попереднім розкладом ({date_str})")
            comparison = compare_schedules(old_periods, periods)
            if comparison:
                result += f"\n{comparison}"
                logger.info(f"Зміна тривалості відключень ({date_str}): {comparison}")
    
    logger.info(f"Сформовано повідомлення ({date_str}): {len(result)} символів")
    return result


def send_to_telegram(message, config):
    """Відправляємо повідомлення в усі налаштовані Telegram чати"""
    logger.info(f"Відправка повідомлення у {len(config['all_chat_ids'])} чатів")
    logger.debug(f"Повідомлення: {message}")
    
    success_count = 0
    total_chats = len(config['all_chat_ids'])
    
    for chat_id in config['all_chat_ids']:
        try:
            logger.debug(f"Відправка в чат {chat_id}")
            url = f"https://api.telegram.org/bot{config['bot_token']}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            response = requests.post(url, data=payload, timeout=30)
            response.raise_for_status()
            success_count += 1
            logger.debug(f"✅ Повідомлення успішно відправлено в чат {chat_id}")
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Помилка при відправці в чат {chat_id}: {e}")
        except Exception as e:
            logger.error(f"❌ Неочікувана помилка при відправці в чат {chat_id}: {e}")
    
    logger.info(f"📊 Результат відправки: {success_count}/{total_chats} чатів отримали повідомлення")
    return success_count > 0


def send_dtek_alarms_to_telegram(message, config):
    """Відправляємо повідомлення про аварії DTEK в окремий чат"""
    # Використовуємо окремий чат для аварій DTEK, якщо налаштовано
    dtek_chat_id = config.get('dtek_alarms_chat_id')
    
    if not dtek_chat_id:
        # Якщо окремий чат не налаштовано, використовуємо основний
        logger.debug("Окремий чат для аварій DTEK не налаштовано, використовуємо основні чати")
        return send_to_telegram(message, config)
    
    logger.info(f"Відправка повідомлення про аварії DTEK в окремий чат {dtek_chat_id}")
    logger.debug(f"Повідомлення: {message}")
    
    try:
        url = f"https://api.telegram.org/bot{config['bot_token']}/sendMessage"
        payload = {
            'chat_id': dtek_chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, data=payload, timeout=30)
        response.raise_for_status()
        logger.info(f"✅ Повідомлення про аварії DTEK успішно відправлено в чат {dtek_chat_id}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Помилка при відправці аварій DTEK в чат {dtek_chat_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Неочікувана помилка при відправці аварій DTEK в чат {dtek_chat_id}: {e}")
        return False


def send_to_external_api(date_str, day_data, group, config):
    """
    Відправляємо дані на зовнішній API.
    
    Args:
        date_str: дата у форматі YYYY-MM-DD
        day_data: дані дня з полями 'slots', 'date', 'status'
        group: група (наприклад "6.2")
        config: конфігурація з параметрами external_api_url, external_api_token
    
    Returns:
        bool: True якщо успішно відправлено
    """
    if not config.get('external_api_url') or not config.get('external_api_token'):
        logger.debug("Зовнішній API не налаштований, пропускаємо відправку")
        return False
    
    if not day_data:
        logger.warning(f"День {date_str} відсутній в даних для відправки на зовнішній API")
        return False
    
    try:
        # Формуємо дані для відправки відповідно до API
        api_data = {
            "date": day_data.get("date", f"{date_str}T00:00:00+02:00"),
            "group": group,
            "slots": [],
            "status": day_data.get("status", "Unknown")
        }
        
        # Витягуємо тільки Definite слоти (планові відключення)
        definite_slots = [slot for slot in day_data.get("slots", []) if slot.get("type") == "Definite"]
        
        # Консолідуємо суміжні періоди відключень
        if definite_slots:
            consolidated = consolidate_periods(definite_slots)
            logger.debug(f"📊 Консолідовано слотів для API: {len(definite_slots)} → {len(consolidated)}")
            
            # Додаємо консолідовані слоти
            for slot in consolidated:
                api_data["slots"].append({
                    "start": slot.get("start", 0),
                    "end": slot.get("end", 0),
                    "type": slot.get("type", "Definite")
                })
        
        # Додаємо інші типи слотів без змін (якщо є)
        for slot in day_data.get("slots", []):
            if slot.get("type") != "Definite":
                api_data["slots"].append({
                    "start": slot.get("start", 0),
                    "end": slot.get("end", 0),
                    "type": slot.get("type", "NotPlanned")
                })
        
        # Відправляємо запит
        headers = {
            "Authorization": f"Bearer {config['external_api_token']}",
            "Content-Type": "application/json"
        }
        
        logger.debug(f"📤 Відправка даних на зовнішній API для {date_str}")
        logger.info(f"📊 Слотів для відправки на API: {len(api_data['slots'])}")
        
        # Логуємо слоти для перевірки
        for i, slot in enumerate(api_data['slots'], 1):
            start_h = slot['start'] // 60
            start_m = slot['start'] % 60
            end_h = slot['end'] // 60
            end_m = slot['end'] % 60
            logger.info(f"  Слот {i}: {start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d} ({slot['type']})")
        
        logger.debug(f"📊 Дані: {json.dumps(api_data, ensure_ascii=False)}")
        
        response = requests.post(
            config['external_api_url'],
            json=api_data,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        logger.info(f"✅ Дані успішно відправлено на зовнішній API для {date_str}")
        logger.debug(f"📨 Відповідь API: {response.status_code} - {response.text[:200]}")
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Помилка при відправці на зовнішній API для {date_str}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Неочікувана помилка при відправці на зовнішній API для {date_str}: {e}")
        return False
