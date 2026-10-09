"""
Модуль для обробки графіка відключень з поля 'fact' DTEK API.
Конвертує формат DTEK fact у формат сумісний з рештою додатку.
"""

import logging
from datetime import datetime
import json

logger = logging.getLogger(__name__)


def parse_dtek_fact_schedule(dtek_alarms_data, group):
    """
    Витягує та конвертує графік з поля 'fact' у форматі DTEK API.
    
    Args:
        dtek_alarms_data: Дані з DTEK API (з полем response.fact)
        group: Номер групи (наприклад "8.1")
    
    Returns:
        dict: Дані у форматі {date: {...}} або None
    """
    if not dtek_alarms_data:
        logger.debug("❌ DTEK Fact: Немає даних")
        return None
    
    try:
        # Перевіряємо структуру
        if 'response' not in dtek_alarms_data:
            logger.debug("❌ DTEK Fact: Немає поля 'response'")
            return None
        
        response = dtek_alarms_data['response']
        
        if 'fact' not in response:
            logger.debug("❌ DTEK Fact: Немає поля 'fact'")
            return None
        
        fact = response['fact']
        
        if 'data' not in fact:
            logger.debug("❌ DTEK Fact: Немає поля 'data' в 'fact'")
            return None
        
        fact_data = fact['data']
        
        if not fact_data:
            logger.debug("❌ DTEK Fact: Поле 'data' порожнє")
            return None
        
        # Отримуємо update time
        update_time = fact.get('updateFact', '')
        logger.debug(f"📅 DTEK Fact update time: {update_time}")
        
        result = {}
        group_key = f"GPV{group}"  # Конвертуємо "8.1" -> "GPV8.1"
        
        logger.debug(f"🔍 DTEK Fact: Шукаємо групу {group_key}")
        
        # Обробляємо кожну дату (timestamp)
        for timestamp_str, groups_data in fact_data.items():
            try:
                # Конвертуємо timestamp у дату
                timestamp = int(timestamp_str)
                date_obj = datetime.fromtimestamp(timestamp)
                date_str = date_obj.strftime('%Y-%m-%d')
                
                logger.debug(f"📅 DTEK Fact: Обробка дати {date_str} (timestamp {timestamp_str})")
                
                # Перевіряємо чи є наша група в цих даних
                if group_key not in groups_data:
                    logger.debug(f"⚠️ DTEK Fact: Група {group_key} не знайдена для {date_str}")
                    logger.debug(f"   Доступні групи: {', '.join(groups_data.keys())}")
                    continue
                
                group_schedule = groups_data[group_key]
                logger.debug(f"✅ DTEK Fact: Знайдено графік для групи {group_key} на {date_str}")
                
                # Конвертуємо годинний графік у формат schedules
                schedules = convert_hourly_to_schedules(group_schedule)
                
                if schedules:
                    result[date_str] = {
                        'slots': schedules,
                        'update_time': update_time,
                        'date': f"{date_str}T00:00:00"
                    }
                    logger.info(f"✅ DTEK Fact: Створено графік для {date_str} ({len(schedules)} періодів)")
                else:
                    logger.debug(f"⚠️ DTEK Fact: Не вдалося створити графік для {date_str}")
                    
            except (ValueError, TypeError) as e:
                logger.warning(f"⚠️ DTEK Fact: Помилка обробки timestamp {timestamp_str}: {e}")
                continue
        
        if result:
            logger.info(f"✅ DTEK Fact: Завантажено дані для {len(result)} дат")
            return result
        else:
            logger.warning(f"⚠️ DTEK Fact: Група {group_key} не знайдена в даних")
            return None
            
    except Exception as e:
        logger.error(f"❌ DTEK Fact: Помилка парсингу: {e}", exc_info=True)
        return None


def convert_hourly_to_schedules(hourly_data):
    """
    Конвертує годинний графік DTEK у список періодів відключень.
    
    Формат вхідних даних:
        {"1": "yes", "2": "no", "3": "first", "4": "second", ...}
    
    Значення:
        - "yes" = є світло (не відключено)
        - "no" = немає світла (відключено весь час)
        - "first" = перша половина години відключена
        - "second" = друга половина години відключена
    
    Args:
        hourly_data: Словник {hour: state}
    
    Returns:
        list: Список періодів у форматі [{'start': '14:00', 'end': '15:00', 'state': 'Definite'}, ...]
    """
    schedules = []
    current_outage = None
    
    for hour in range(1, 25):  # 1-24
        hour_str = str(hour)
        state = hourly_data.get(hour_str, "yes")
        
        # Визначаємо час початку та кінця години
        # Година 1 = 00:00-01:00, година 2 = 01:00-02:00, і т.д.
        hour_start = hour - 1
        hour_end = hour if hour < 24 else 0
        
        # Обробляємо різні стани
        if state == "no":
            # Вся година без світла
            if current_outage is None:
                # Початок нового відключення
                current_outage = {
                    'start': f"{hour_start:02d}:00",
                    'end': f"{hour_end:02d}:00",
                    'state': 'Definite'
                }
            else:
                # Продовження відключення
                current_outage['end'] = f"{hour_end:02d}:00"
                
        elif state == "first":
            # Перша половина години без світла (00-30)
            # Закриваємо попереднє відключення якщо є
            if current_outage:
                schedules.append(current_outage)
                current_outage = None
            
            # Додаємо відключення на першу половину
            schedules.append({
                'start': f"{hour_start:02d}:00",
                'end': f"{hour_start:02d}:30",
                'state': 'Definite'
            })
            
        elif state == "second":
            # Друга половина години без світла (30-60)
            # Закриваємо попереднє відключення якщо є
            if current_outage:
                schedules.append(current_outage)
                current_outage = None
            
            # Додаємо відключення на другу половину
            schedules.append({
                'start': f"{hour_start:02d}:30",
                'end': f"{hour_end:02d}:00",
                'state': 'Definite'
            })
            
        else:  # "yes" або інше
            # Є світло - закриваємо поточне відключення якщо є
            if current_outage:
                schedules.append(current_outage)
                current_outage = None
    
    # Закриваємо останнє відключення якщо залишилось відкритим
    if current_outage:
        schedules.append(current_outage)
    
    logger.debug(f"📊 DTEK Fact: Конвертовано {len(schedules)} періодів відключень")
    
    return schedules


def load_dtek_fact_data(dtek_alarms_url, group):
    """
    Завантажує та обробляє графік з DTEK fact API.
    
    Args:
        dtek_alarms_url: URL до DTEK API з аваріями та графіком
        group: Номер групи (наприклад "8.1")
    
    Returns:
        dict: Дані у форматі {date: {...}} або None
    """
    try:
        import requests
        
        logger.debug(f"📡 DTEK Fact: Запит до {dtek_alarms_url}")
        response = requests.get(dtek_alarms_url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        logger.debug("✅ DTEK Fact: Отримано відповідь")
        
        return parse_dtek_fact_schedule(data, group)
        
    except requests.exceptions.Timeout:
        logger.error("❌ DTEK Fact: Таймаут запиту")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ DTEK Fact: Помилка запиту: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"❌ DTEK Fact: Помилка парсингу JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ DTEK Fact: Несподівана помилка: {e}", exc_info=True)
        return None
