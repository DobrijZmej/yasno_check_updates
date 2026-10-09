"""
Модуль для завантаження та обробки інформації про аварії DTEK.
"""

import logging
import requests
import json
import re

logger = logging.getLogger(__name__)


def load_dtek_alarms(dtek_alarms_url):
    """
    Завантажує дані про аварії з DTEK API.
    
    Args:
        dtek_alarms_url: URL до DTEK Alarms API
    
    Returns:
        dict: Дані про аварії або None при помилці
    """
    try:
        logger.debug(f"📡 Запит до DTEK Alarms API: {dtek_alarms_url}")
        response = requests.get(dtek_alarms_url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        logger.debug("✅ Отримано відповідь від DTEK Alarms API")
        
        return data
    except requests.exceptions.Timeout:
        logger.error("❌ Таймаут запиту до DTEK Alarms API")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Помилка запиту до DTEK Alarms API: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"❌ Помилка парсингу JSON від DTEK Alarms API: {e}")
        return None


def process_dtek_alarms(data):
    """
    Обробляємо дані про аварії DTEK та групуємо будинки за типом аварії.
    
    Args:
        data: Дані з API DTEK
    
    Returns:
        dict: Згруповані аварії {(sub_type, start_date, end_date): {...}}
    """
    if not data or 'response' not in data or 'data' not in data['response']:
        logger.warning("⚠️ Некоректна структура даних від DTEK API")
        return {}
    
    houses_data = data['response']['data']
    logger.debug(f"📊 Обробляємо {len(houses_data)} будинків")
    
    # Групуємо будинки за аваріями
    alarms_groups = {}
    houses_with_alarms = 0
    houses_without_alarms = 0
    
    for house_number, house_info in houses_data.items():
        sub_type = house_info.get('sub_type', '').strip()
        
        # Пропускаємо будинки без аварій
        if not sub_type:
            houses_without_alarms += 1
            continue
        
        houses_with_alarms += 1
        start_date = house_info.get('start_date', '').strip()
        end_date = house_info.get('end_date', '').strip()
        alarm_type = house_info.get('type', '').strip()
        
        # Отримуємо інформацію про групу
        sub_type_reason = house_info.get('sub_type_reason', [])
        group_name = sub_type_reason[0] if sub_type_reason else ''
        
        logger.debug(f"  🏠 {house_number}: {sub_type}, {start_date} - {end_date}, група: {group_name}")
        
        # Створюємо ключ групи: (sub_type, start_date, end_date)
        group_key = (sub_type, start_date, end_date)
        
        if group_key not in alarms_groups:
            alarms_groups[group_key] = {
                'houses': [],
                'sub_type': sub_type,
                'start_date': start_date,
                'end_date': end_date,
                'type': alarm_type
            }
        
        # Зберігаємо будинок разом з групою
        alarms_groups[group_key]['houses'].append({
            'number': house_number,
            'group': group_name
        })
    
    logger.info(f"📊 Оброблено будинків: {len(houses_data)} (з аваріями: {houses_with_alarms}, без аварій: {houses_without_alarms})")
    logger.info(f"🔢 Створено груп аварій: {len(alarms_groups)}")
    
    return alarms_groups


def find_priority_house_group(dtek_alarms_data, priority_houses={'10А', '10Б', '10В'}):
    """
    Шукає групу для пріоритетних будинків в API ДТЕК (незалежно від наявності аварій).
    
    Args:
        dtek_alarms_data: JSON дані з API
        priority_houses: Множина номерів пріоритетних будинків
    
    Returns:
        str: Номер групи (наприклад "8.1") або None
    """
    if not dtek_alarms_data:
        return None
    
    try:
        houses_data = dtek_alarms_data['response']['data']
    except (KeyError, TypeError):
        logger.error("❌ Не вдалося отримати дані про будинки")
        return None
    
    # Шукаємо пріоритетні будинки
    for house_number in priority_houses:
        if house_number in houses_data:
            house_info = houses_data[house_number]
            sub_type_reason = house_info.get('sub_type_reason', [])
            
            if sub_type_reason:
                group_name = sub_type_reason[0]
                # Витягуємо номер групи з "GPV8.1" -> "8.1"
                match = re.search(r'GPV(\d+(?:\.\d+)?)', group_name)
                if match:
                    group_number = match.group(1)
                    logger.info(f"🏠 Знайдено пріоритетний будинок {house_number} в API: група {group_number}")
                    return group_number
    
    return None
