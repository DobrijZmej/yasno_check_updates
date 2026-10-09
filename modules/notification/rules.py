"""
Модуль для формування правил відправки повідомлень.
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def should_send_schedule(group, date_str, is_changed, state, day_data=None):
    """
    Визначає чи потрібно відправляти розклад для конкретної дати.
    
    Args:
        group: група (наприклад "6.2")
        date_str: дата у форматі YYYY-MM-DD
        is_changed: чи змінився розклад
        state: поточний стан
        day_data: дані дня для перевірки наявності відключень
    
    Returns:
        bool: чи потрібно відправляти
    """
    if not is_changed:
        logger.debug(f"⏭️ Розклад не змінився для {group} на {date_str} - пропускаємо")
        return False
    
    # Перевіряємо чи є планові відключення
    if day_data:
        has_outages = False
        if 'slots' in day_data:
            for slot in day_data['slots']:
                if slot.get('type') in {'Definite', 'Possible'}:
                    has_outages = True
                    break
        
        if not has_outages:
            logger.info(f"⏭️ Розклад змінився для {group} на {date_str}, але відключень немає - не відправляємо")
            return False
    
    logger.info(f"✅ Розклад змінився для {group} на {date_str} - відправляємо")
    return True


def should_send_alarm(alarm_key, state):
    """
    Визначає чи потрібно відправляти інформацію про аварію.
    
    Args:
        alarm_key: унікальний ключ аварії
        state: поточний стан
    
    Returns:
        bool: чи потрібно відправляти
    """
    state_key = f"last_alarm_{alarm_key}"
    
    if state_key in state:
        logger.debug(f"⏭️ Аварія {alarm_key} вже була відправлена - пропускаємо")
        return False
    
    logger.info(f"🆕 Нова аварія {alarm_key} - відправляємо")
    return True


def determine_day_label(date_str):
    """
    Визначає мітку дня (сьогодні/завтра).
    
    Args:
        date_str: дата у форматі YYYY-MM-DD
    
    Returns:
        str: 'today', 'tomorrow' або None
    """
    today = datetime.now().strftime('%Y-%m-%d')
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    
    if date_str == today:
        return 'today'
    elif date_str == tomorrow:
        return 'tomorrow'
    else:
        return None


def format_date_label(date_str):
    """
    Форматує дату для відображення (укр.).
    
    Args:
        date_str: дата у форматі YYYY-MM-DD
    
    Returns:
        str: "сьогодні (29.01)" або "завтра (30.01)" або "29.01.2026"
    """
    day_label = determine_day_label(date_str)
    
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    date_short = date_obj.strftime('%d.%m')
    
    if day_label == 'today':
        return f"сьогодні ({date_short})"
    elif day_label == 'tomorrow':
        return f"завтра ({date_short})"
    else:
        return date_obj.strftime('%d.%m.%Y')
