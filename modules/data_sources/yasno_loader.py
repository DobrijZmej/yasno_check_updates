"""
Модуль для завантаження даних з API YASNO.
"""

import logging
import requests
import json

logger = logging.getLogger(__name__)


def load_yasno_data(yasno_url, group):
    """
    Завантажуємо дані з API YASNO.
    
    Args:
        yasno_url: URL API YASNO
        group: Номер групи (наприклад, "6.2")
    
    Returns:
        dict: Дані для групи у форматі {date: {...}, date: {...}}
              або None якщо помилка
    """
    try:
        logger.debug(f"Запит до YASNO API: {yasno_url}")
        response = requests.get(yasno_url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        logger.debug("Отримано відповідь від YASNO API")
        logger.debug(f"📋 Розмір відповіді: {len(response.text)} символів")
        logger.debug(f"📊 Доступні групи: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
        
        # API повертає дані з групами як ключами
        if group in data:
            group_data = data[group]
            logger.debug(f"✅ Знайдено дані для групи {group}")
            
            # Витягуємо дати з today/tomorrow і конвертуємо у нову структуру
            result = {}
            
            if 'today' in group_data and group_data['today']:
                today_date_full = group_data['today'].get('date', '')
                if today_date_full:
                    today_date = today_date_full.split('T')[0]  # YYYY-MM-DD
                    result[today_date] = group_data['today']
                    logger.debug(f"📅 YASNO today: {today_date}")
            
            if 'tomorrow' in group_data and group_data['tomorrow']:
                tomorrow_date_full = group_data['tomorrow'].get('date', '')
                if tomorrow_date_full:
                    tomorrow_date = tomorrow_date_full.split('T')[0]  # YYYY-MM-DD
                    result[tomorrow_date] = group_data['tomorrow']
                    logger.debug(f"📅 YASNO tomorrow: {tomorrow_date}")
            
            return result
        else:
            logger.warning(f"❌ Дані для групи {group} не знайдено")
            logger.info(f"Доступні групи: {list(data.keys())}")
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Помилка при запиті до YASNO API: {e}")
        return None
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        logger.error(f"❌ Помилка при обробці відповіді YASNO API: {e}")
        return None
