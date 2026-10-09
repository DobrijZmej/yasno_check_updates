"""
Модуль для перевірки поточного стану електрики через Home Assistant
"""
import os
import logging
import requests
import urllib3

logger = logging.getLogger(__name__)


def get_power_status_from_ha():
    """
    Перевіряє чи є зараз електрика через Home Assistant
    
    Returns:
        bool or None: True - електрика є, False - електрики немає, None - помилка або вимкнено
    """
    # Перевіряємо чи увімкнена інтеграція з HA
    ha_enabled = os.getenv('HA_ENABLED', 'false').lower() in ('true', '1', 'yes')
    
    if not ha_enabled:
        logger.debug("🏠 Home Assistant інтеграція вимкнена (HA_ENABLED=false)")
        return None
    
    # Конфігурація
    ha_url = os.getenv('HA_URL', 'http://homeassistant.local:8123')
    ha_token = os.getenv('HA_TOKEN')
    ha_power_sensor = os.getenv('HA_POWER_SENSOR', 'binary_sensor.is_electicity_exists')
    ha_verify_ssl = os.getenv('HA_VERIFY_SSL', 'true').lower() in ('true', '1', 'yes')
    
    if not ha_token:
        logger.warning("⚠️ HA_TOKEN не вказано в .env файлі")
        return None
    
    # Вимкнути попередження про SSL якщо потрібно
    if not ha_verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    headers = {
        'Authorization': f'Bearer {ha_token}',
        'Content-Type': 'application/json',
    }
    
    try:
        power_url = f"{ha_url}/api/states/{ha_power_sensor}"
        response = requests.get(power_url, headers=headers, timeout=10, verify=ha_verify_ssl)
        response.raise_for_status()
        power_data = response.json()
        
        # Визначаємо чи є електрика
        power_state = power_data.get('state', '').lower()
        has_power = power_state == 'on'
        
        logger.info(f"🏠 Home Assistant: Електрика {'Є ✅' if has_power else 'НЕМАЄ ❌'} (sensor: {ha_power_sensor}, state: {power_state})")
        
        return has_power
        
    except requests.exceptions.SSLError as e:
        logger.warning(f"⚠️ Помилка SSL з'єднання з Home Assistant: {e}")
        logger.info(f"💡 Порада: Додайте HA_VERIFY_SSL=false в .env файл")
        return None
    except requests.exceptions.Timeout:
        logger.warning("⚠️ Час очікування відповіді від Home Assistant вичерпано")
        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"⚠️ Помилка при отриманні даних з Home Assistant: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Несподівана помилка при роботі з Home Assistant: {e}")
        return None
