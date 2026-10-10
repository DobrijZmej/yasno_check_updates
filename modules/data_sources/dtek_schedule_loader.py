"""
Модуль для завантаження даних з API DTEK Schedule.
"""

import logging
import requests
import json
from modules.timeutils import from_timestamp_kyiv

logger = logging.getLogger(__name__)


def load_dtek_schedule_data(dtek_url, group):
    """
    Завантажуємо дані з API DTEK Schedule.
    
    Args:
        dtek_url: URL API DTEK
        group: Номер групи (наприклад, "6.2")
    
    Returns:
        dict: {
            'dates': {date: {hours, timestamp, update_time}},
            'update_time': str,
            'group': str (формат DTEK, наприклад "GPV6.2")
        }
        або None якщо помилка
    """
    try:
        logger.debug(f"Запит до DTEK API: {dtek_url}")
        response = requests.get(dtek_url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        logger.debug("Отримано відповідь від DTEK API")
        
        # Перевіряємо чи API працює коректно
        if not data.get('ok', False):
            logger.warning("❌ DTEK API повернув ok=false")
            return None
        
        # Витягуємо дані
        js_variables = data.get('js_variables', {})
        fact = js_variables.get('fact', {})
        fact_data = fact.get('data', {})
        update_time = fact.get('update', '')
        
        logger.debug(f"🕒 DTEK оновлено: {update_time}")
        logger.debug(f"📊 Тип fact_data: {type(fact_data)}")
        
        # Перевірка чи fact_data є словником
        if not isinstance(fact_data, dict):
            logger.warning(f"⚠️ DTEK API повернув дані у некоректному форматі: {type(fact_data)}")
            if isinstance(fact_data, list):
                logger.debug(f"fact_data є списком з {len(fact_data)} елементів")
            return None
        
        logger.debug(f"📅 Доступні timestamps: {list(fact_data.keys())}")
        
        # Конвертуємо групу у формат DTEK
        # "6.2" → "GPV6.2" або "2" → "GPV6.2"
        if '.' in group:
            dtek_group = f"GPV{group}"
        else:
            dtek_group = f"GPV6.{group}"
        
        logger.debug(f"🔍 Шукаємо групу DTEK: {dtek_group}")
        
        # Конвертуємо timestamps у дати та формуємо результат по датах
        result = {}
        for timestamp_str in fact_data.keys():
            timestamp = int(timestamp_str)
            date_obj = from_timestamp_kyiv(timestamp)
            date_str = date_obj.strftime('%Y-%m-%d')
            
            group_data = fact_data[timestamp_str].get(dtek_group, {})
            if group_data:
                result[date_str] = {
                    'hours': group_data,  # {1: 'yes', 2: 'no', ...}
                    'timestamp': timestamp,
                    'update_time': update_time
                }
                logger.debug(f"📅 DTEK: {date_str} (timestamp {timestamp})")
        
        if not result:
            logger.warning(f"⚠️ DTEK не має даних для групи {dtek_group}")
            return None
        
        return {
            'dates': result,  # {date: {hours, timestamp, update_time}}
            'update_time': update_time,
            'group': dtek_group
        }
            
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Помилка при запиті до DTEK API: {e}")
        return None
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        logger.error(f"❌ Помилка при обробці відповіді DTEK API: {e}")
        return None
