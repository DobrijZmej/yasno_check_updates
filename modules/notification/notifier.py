"""
Модуль для відправки повідомлень в Telegram.
"""

import logging
import requests

logger = logging.getLogger(__name__)


def format_time(minutes):
    """Конвертує хвилини від початку дня у формат HH:MM"""
    try:
        total_minutes = int(minutes)
        
        if total_minutes < 0:
            return None
        
        if total_minutes >= 1440:
            if total_minutes == 1440:
                return "24:00"
            else:
                return None
        
        hours = total_minutes // 60
        mins = total_minutes % 60
        
        return f"{hours:02d}:{mins:02d}"
    except (ValueError, TypeError):
        return None


def format_duration(minutes):
    """Форматує тривалість у форматі 'H:MM'"""
    try:
        total_minutes = int(minutes)
        if total_minutes <= 0:
            return "0:00"
        
        hours = total_minutes // 60
        mins = total_minutes % 60
        
        return f"{hours}:{mins:02d}"
    except (ValueError, TypeError):
        return "??"


def consolidate_periods(periods):
    """Об'єднує сусідні періоди відключень"""
    if not periods:
        return []
    
    # Сортуємо за початком
    sorted_periods = sorted(periods, key=lambda x: x['start'])
    
    consolidated = []
    current = sorted_periods[0].copy()
    
    for period in sorted_periods[1:]:
        if period['start'] <= current['end']:
            # Об'єднуємо
            current['end'] = max(current['end'], period['end'])
        else:
            # Новий період
            consolidated.append(current)
            current = period.copy()
    
    consolidated.append(current)
    return consolidated


def format_schedule_message(date_str, day_data, group, day_label, source_info=None, group_change_info=None):
    """
    Формує повідомлення про розклад.
    
    Args:
        date_str: дата YYYY-MM-DD
        day_data: дані з 'slots'
        group: номер групи
        day_label: "сьогодні" або "завтра"
        source_info: {'source': str, 'update_time': str}
        group_change_info: {'previous': str, 'current': str} якщо група змінилась
    
    Returns:
        str: форматоване повідомлення
    """
    # Визначаємо джерело
    source = 'невідоме джерело'
    is_standard = False
    
    if source_info:
        source_name = source_info.get('source', 'unknown')
        update_time = source_info.get('update_time', '')
        
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
    
    # Додаємо інформацію про зміну групи якщо є
    if group_change_info:
        previous = group_change_info.get('previous')
        current = group_change_info.get('current')
        result += f"\n\n🔄 <b>Змінилася група відключень!</b>\n"
        result += f"   Попередня: {previous}\n"
        result += f"   Поточна: {current}"
    
    if is_standard:
        result += "\n⚠️ <b>УВАГА:</b> Офіційний графік не опублікований. Використовується стандартний графік білих зон."
    
    # Витягуємо підтверджені та можливі відключення
    outage_slots = {"Definite": [], "Possible": []}
    if day_data and "slots" in day_data:
        for slot in day_data["slots"]:
            slot_type = slot.get("type") or slot.get("state")
            if slot_type in outage_slots:
                start = slot["start"]
                end = slot["end"]
                if isinstance(start, str):
                    h, m = map(int, start.split(':'))
                    start = h * 60 + m
                if isinstance(end, str):
                    h, m = map(int, end.split(':'))
                    end = h * 60 + m
                
                outage_slots[slot_type].append({
                    "start": start,
                    "end": end
                })

    if not outage_slots["Definite"] and not outage_slots["Possible"]:
        result += "\n• Підтверджених планових відключень немає"
    for slot_type, heading in (("Definite", "Планові відключення"), ("Possible", "Можливі відключення")):
        if not outage_slots[slot_type]:
            continue
        periods = consolidate_periods(outage_slots[slot_type])
        result += f"\n• {heading} ({len(periods)} період{'и' if len(periods) > 1 else ''}):"

        for period in periods:
            start_time = format_time(period['start'])
            end_time = format_time(period['end'])
            duration_minutes = period['end'] - period['start']
            duration_str = format_duration(duration_minutes)
            
            if start_time and end_time:
                marker = "⚡" if slot_type == "Definite" else "◦"
                result += f"\n  {marker} {start_time} - {end_time} ({duration_str})"
    
    return result


def format_alarm_message(alarm_info, houses_count):
    """
    Формує повідомлення про аварію.
    
    Args:
        alarm_info: dict з інформацією про аварію
        houses_count: кількість будинків
    
    Returns:
        str: форматоване повідомлення
    """
    sub_type = alarm_info.get('sub_type', 'Невідомий тип')
    start_date = alarm_info.get('start_date', '')
    end_date = alarm_info.get('end_date', '')
    houses = alarm_info.get('houses', [])
    
    # Форматуємо список будинків з групами
    houses_list = []
    for house in houses[:10]:  # Перші 10
        if isinstance(house, dict):
            number = house.get('number', '?')
            group = house.get('group', '')
            if group:
                houses_list.append(f"{number} ({group})")
            else:
                houses_list.append(number)
        else:
            houses_list.append(str(house))
    
    houses_str = ', '.join(houses_list)
    if len(houses) > 10:
        houses_str += f" та ще {len(houses) - 10}"
    
    result = f"🚨 Аварія ДТЕК\n"
    result += f"Тип: {sub_type}\n"
    result += f"Період: {start_date} - {end_date}\n"
    result += f"Будинки ({houses_count}): {houses_str}"
    
    return result


def send_telegram_message(bot_token, chat_id, message):
    """
    Відправляє повідомлення в Telegram.
    
    Args:
        bot_token: токен бота
        chat_id: ID чату
        message: текст повідомлення
    
    Returns:
        bool: успішно/неуспішно
    """
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        
        logger.info("✅ Повідомлення відправлено в Telegram")
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Помилка відправки в Telegram: {e}")
        return False


def send_to_multiple_chats(bot_token, chat_ids, message):
    """
    Відправляє повідомлення в кілька чатів.
    
    Args:
        bot_token: токен бота
        chat_ids: список ID чатів
        message: текст повідомлення
    
    Returns:
        int: кількість успішних відправок
    """
    if not chat_ids:
        return 0
    
    success_count = 0
    for chat_id in chat_ids:
        if send_telegram_message(bot_token, chat_id, message):
            success_count += 1
    
    return success_count
