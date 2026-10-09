"""
Модуль для об'єднання даних з різних джерел за пріоритетами.

Пріоритет джерел (від найвищого):
1. DTEK Fact (графік з аварій)
2. DTEK Schedule (плановий графік)
3. YASNO

Якщо немає жодних даних - нічого не відправляємо.
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def convert_dtek_hours_to_slots(hours_data):
    """
    Конвертує годинні дані DTEK у формат слотів YASNO.
    
    Args:
        hours_data: dict {hour: status}  (1: 'yes', 2: 'no', ...)
    
    Returns:
        list: Список слотів [{'start': int, 'end': int, 'type': 'Definite'}, ...]
    """
    slots = []
    current_outage = None
    
    for hour in range(1, 25):
        hour_str = str(hour)
        status = hours_data.get(hour_str, 'yes')
        
        hour_start_minutes = (hour - 1) * 60
        hour_end_minutes = hour * 60 if hour < 24 else 0
        
        if status == 'no':
            # Немає світла
            if current_outage is None:
                current_outage = {
                    'start': hour_start_minutes,
                    'end': hour_end_minutes,
                    'type': 'Definite'
                }
            else:
                current_outage['end'] = hour_end_minutes
        elif status == 'first':
            # Перша половина години без світла
            if current_outage:
                slots.append(current_outage)
                current_outage = None
            
            slots.append({
                'start': hour_start_minutes,
                'end': hour_start_minutes + 30,
                'type': 'Definite'
            })
        elif status == 'second':
            # Друга половина години без світла
            if current_outage:
                slots.append(current_outage)
                current_outage = None
            
            slots.append({
                'start': hour_start_minutes + 30,
                'end': hour_end_minutes,
                'type': 'Definite'
            })
        else:
            # Є світло
            if current_outage:
                slots.append(current_outage)
                current_outage = None
    
    if current_outage:
        slots.append(current_outage)
    
    return slots


def convert_dtek_to_yasno_format(hours_data, date_str, update_time):
    """
    Конвертує дані DTEK у формат YASNO.
    
    Args:
        hours_data: dict з годинними даними
        date_str: дата у форматі YYYY-MM-DD
        update_time: час оновлення
    
    Returns:
        dict: дані у форматі YASNO
    """
    slots = convert_dtek_hours_to_slots(hours_data)
    
    return {
        'date': f"{date_str}T00:00:00",
        'slots': slots,
        'update_time': update_time
    }


def has_outages(day_data):
    """
    Перевіряє чи є планові відключення в даних.
    
    Args:
        day_data: дані дня з полем 'slots'
    
    Returns:
        bool: True якщо є хоч один Definite слот
    """
    if not day_data or 'slots' not in day_data:
        return False
    
    for slot in day_data['slots']:
        if slot.get('type') == 'Definite':
            return True
    
    return False


def merge_data_sources(yasno_data, dtek_schedule_data, dtek_fact_data):
    """
    Об'єднує дані з різних джерел за пріоритетами.
    
    Пріоритет (від найвищого):
    1. DTEK Fact - графік з аварій (найточніший)
    2. DTEK Schedule - плановий графік від DTEK
    3. YASNO - офіційний графік YASNO
    
    Якщо немає жодних реальних даних - повертаємо порожній результат.
    
    Args:
        yasno_data: дані з YASNO {date: {...}}
        dtek_schedule_data: дані з DTEK Schedule {'dates': {date: {...}}, 'update_time': str}
        dtek_fact_data: графік з аварій DTEK {date: {...}}
    
    Returns:
        tuple: (merged_data, source_info)
            - merged_data: {date: {...}}
            - source_info: {date: {'source': str, 'update_time': str}}
    """
    today_date = datetime.now().strftime('%Y-%m-%d')
    tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    
    logger.debug(f"📅 Потрібні дати: {today_date}, {tomorrow_date}")
    
    merged = {}
    source_info = {}
    
    # Якщо всі джерела недоступні
    if not yasno_data and not dtek_schedule_data and not dtek_fact_data:
        logger.warning("❌ Всі джерела даних недоступні")
        return {}, {}
    
    # Підготовка даних з усіх джерел
    yasno_dates = yasno_data if yasno_data else {}
    dtek_fact_dates = dtek_fact_data if dtek_fact_data else {}
    dtek_dates = {}
    
    if dtek_schedule_data and 'dates' in dtek_schedule_data:
        # Конвертуємо дані DTEK у формат YASNO
        for date_str, date_data in dtek_schedule_data['dates'].items():
            dtek_converted = convert_dtek_to_yasno_format(
                date_data['hours'],
                date_str,
                date_data['update_time']
            )
            dtek_dates[date_str] = dtek_converted
            logger.debug(f"✅ Конвертовано DTEK дані для {date_str}")
    
    # Обробляємо кожну потрібну дату
    for target_date in [today_date, tomorrow_date]:
        yasno_has_date = target_date in yasno_dates
        dtek_has_date = target_date in dtek_dates
        dtek_fact_has_date = target_date in dtek_fact_dates
        
        # Пріоритет 1: DTEK Fact (якщо є)
        if dtek_fact_has_date:
            logger.info(f"🎯 {target_date}: Використовуємо DTEK Fact (найвищий пріоритет)")
            merged[target_date] = dtek_fact_dates[target_date]
            source_info[target_date] = {
                'source': 'dtek_fact',
                'update_time': dtek_fact_dates[target_date].get('update_time', '')
            }
            continue
        
        # Пріоритет 2: DTEK Schedule > YASNO (якщо є відключення)
        if dtek_has_date and has_outages(dtek_dates[target_date]):
            logger.info(f"🎯 {target_date}: Використовуємо DTEK Schedule (пріоритет над YASNO)")
            merged[target_date] = dtek_dates[target_date]
            source_info[target_date] = {
                'source': 'dtek',
                'update_time': dtek_schedule_data.get('update_time', '')
            }
            continue
        
        # Пріоритет 3: YASNO (якщо є відключення)
        if yasno_has_date and has_outages(yasno_dates[target_date]):
            logger.info(f"🎯 {target_date}: Використовуємо YASNO")
            merged[target_date] = yasno_dates[target_date]
            source_info[target_date] = {
                'source': 'yasno',
                'update_time': yasno_dates[target_date].get('update_time', '')
            }
            continue
        
        # DTEK/YASNO навіть якщо порожні (показуємо що відключень немає)
        if dtek_has_date:
            logger.info(f"🎯 {target_date}: Використовуємо DTEK Schedule (відключень немає)")
            merged[target_date] = dtek_dates[target_date]
            source_info[target_date] = {
                'source': 'dtek',
                'update_time': dtek_schedule_data.get('update_time', '')
            }
            continue
        
        if yasno_has_date:
            logger.info(f"🎯 {target_date}: Використовуємо YASNO (відключень немає)")
            merged[target_date] = yasno_dates[target_date]
            source_info[target_date] = {
                'source': 'yasno',
                'update_time': yasno_dates[target_date].get('update_time', '')
            }
            continue
        
        # Немає даних з жодного джерела - пропускаємо цю дату
        logger.warning(f"⚠️ {target_date}: Немає даних з жодного джерела")
    
    logger.info(f"✅ Об'єднано дані для {len(merged)} дат")
    return merged, source_info
