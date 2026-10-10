"""
Модуль для завантаження стандартного розкладу.
"""

import json
import logging
from datetime import datetime
from modules.timeutils import today_str

logger = logging.getLogger(__name__)


def time_to_minutes(time_str):
    """Конвертує час HH:MM в хвилини від початку дня"""
    h, m = map(int, time_str.split(':'))
    return h * 60 + m


def get_day_name_from_date(date_str):
    """Отримує назву дня тижня з дати YYYY-MM-DD"""
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    days_map = {
        0: 'monday',
        1: 'tuesday',
        2: 'wednesday',
        3: 'thursday',
        4: 'friday',
        5: 'saturday',
        6: 'sunday'
    }
    return days_map[date_obj.weekday()]


def convert_intervals_to_slots(intervals):
    """
    Конвертує інтервали з no_power у слоти формату YASNO.
    
    Args:
        intervals: список інтервалів {'from': 'HH:MM', 'to': 'HH:MM', 'state': '...'}
    
    Returns:
        список слотів [{'start': int, 'end': int, 'type': 'Definite'}, ...]
    """
    slots = []
    
    for interval in intervals:
        if interval['state'] == 'no_power':
            start_min = time_to_minutes(interval['from'])
            end_min = time_to_minutes(interval['to'])
            
            slots.append({
                'start': start_min,
                'end': end_min,
                'type': 'Definite'
            })
    
    return slots


def load_standard_schedule(schedule_file='standart_schedule.json'):
    """
    Завантажує стандартний розклад з файлу.
    
    Args:
        schedule_file: шлях до файлу розкладу
    
    Returns:
        dict: розклад по днях тижня або None
    """
    try:
        with open(schedule_file, 'r', encoding='utf-8') as f:
            schedule = json.load(f)
        
        logger.debug(f"📂 Завантажено стандартний розклад: {schedule['provider']} черга {schedule['queue']}")
        logger.debug(f"📍 Адреса: {schedule['address']}")
        
        return schedule
    except FileNotFoundError:
        logger.warning(f"⚠️ Файл стандартного розкладу не знайдено: {schedule_file}")
        return None
    except Exception as e:
        logger.error(f"❌ Помилка читання стандартного розкладу: {e}")
        return None


def get_standard_schedule_for_dates(dates, schedule_file='standart_schedule.json'):
    """
    Отримує стандартний розклад для конкретних дат у форматі YASNO.
    
    Args:
        dates: список дат у форматі ['YYYY-MM-DD', ...]
        schedule_file: шлях до файлу розкладу
    
    Returns:
        dict: {
            'YYYY-MM-DD': {
                'date': 'YYYY-MM-DDTHH:MM:SS',
                'slots': [{'start': int, 'end': int, 'type': 'Definite'}, ...]
            },
            ...
        }
    """
    schedule = load_standard_schedule(schedule_file)
    if not schedule:
        return None
    
    result = {}
    
    for date_str in dates:
        day_name = get_day_name_from_date(date_str)
        
        if day_name not in schedule['week']:
            logger.warning(f"⚠️ День {day_name} не знайдено у розкладі")
            continue
        
        intervals = schedule['week'][day_name]['intervals']
        slots = convert_intervals_to_slots(intervals)
        
        result[date_str] = {
            'date': f"{date_str}T00:00:00",
            'slots': slots
        }
        
        logger.debug(f"📅 Стандартний розклад для {date_str} ({day_name}): {len(slots)} слотів")
    
    return result


def load_standard_schedule_data(dates=None):
    """
    Завантажує стандартний розклад для сьогодні та завтра (або інших дат).
    
    Args:
        dates: список дат ['YYYY-MM-DD', ...] або None (використає сьогодні/завтра)
    
    Returns:
        dict: дані у форматі YASNO або None
    """
    if dates is None:
        # За замовчуванням беремо сьогодні та завтра
        today = today_str()
        tomorrow = today_str(1)
        dates = [today, tomorrow]
    
    logger.debug(f"📡 Завантаження стандартного розкладу для дат: {dates}")
    
    result = get_standard_schedule_for_dates(dates)
    
    if result:
        logger.info(f"✅ Завантажено стандартний розклад для {len(result)} дат")
    else:
        logger.warning("❌ Не вдалося завантажити стандартний розклад")
    
    return result
