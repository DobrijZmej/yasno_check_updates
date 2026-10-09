"""
Модуль для відправки даних на зовнішній API.
"""

import logging
import requests
import json

logger = logging.getLogger(__name__)


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


def send_to_external_api(date_str, day_data, group, api_url, api_token):
    """
    Відправляє дані на зовнішній API.
    
    Args:
        date_str: дата у форматі YYYY-MM-DD
        day_data: дані дня з полями 'slots', 'date', 'status'
        group: група (наприклад "6.2")
        api_url: URL зовнішнього API
        api_token: Bearer токен для авторизації
    
    Returns:
        bool: True якщо успішно відправлено
    """
    if not api_url or not api_token:
        logger.debug("Зовнішній API не налаштований, пропускаємо відправку")
        return False
    
    if not day_data:
        logger.warning(f"День {date_str} відсутній в даних для відправки на зовнішній API")
        return False
    
    try:
        # Формуємо дані для відправки
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
            "Authorization": f"Bearer {api_token}",
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
            api_url,
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
