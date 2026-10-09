"""
Модуль для обробки попереджень про відключення/відновлення електроенергії.
Надсилає сповіщення за 30 хвилин до відключення та за 60 хвилин до відновлення.
"""

import logging
from datetime import datetime
from state_manager import load_state_log, save_state_log
from notifiers import extract_definite_slots, format_time
from data_processor import consolidate_periods

logger = logging.getLogger(__name__)


def is_cross_day_continuation(today_data, tomorrow_data):
    """
    Перевіряємо чи є періоди, що продовжуються з сьогодні на завтра.
    Наприклад: сьогодні 23:00-24:00 → завтра 00:00-XX:XX
    
    Args:
        today_data: дані сьогоднішнього дня
        tomorrow_data: дані завтрашнього дня (може бути None)
    
    Returns:
        bool: True якщо є кросс-день період
    """
    if not today_data or not tomorrow_data:
        return False
    
    # Отримуємо слоти для сьогодні
    today_definite = extract_definite_slots(today_data)
    if not today_definite:
        return False
    
    # Отримуємо слоти для завтра
    tomorrow_definite = extract_definite_slots(tomorrow_data)
    if not tomorrow_definite:
        return False
    
    # Консолідуємо періоди
    today_periods = consolidate_periods(today_definite)
    tomorrow_periods = consolidate_periods(tomorrow_definite)
    
    # Перевіряємо чи останній період сьогодні закінчується о 24:00
    # І чи перший період завтра починається о 00:00
    if today_periods and tomorrow_periods:
        last_today = today_periods[-1]
        first_tomorrow = tomorrow_periods[0]
        
        if last_today['end'] == 1440 and first_tomorrow['start'] == 0:
            logger.debug("🌉 Виявлено кросс-день період (сьогодні до 24:00 → завтра з 00:00)")
            return True
    
    return False


def process_alarms(merged_data, group, config, states, source_info=None):
    """
    Обробляємо попередження про відключення/відновлення електроенергії.
    
    Args:
        merged_data: dict {date: day_data} - об'єднані дані по датах
        group: група (наприклад "6.2")
        config: конфігурація з параметрами bot_token, all_chat_ids
        states: поточний стан (буде оновлено)
        source_info: інформація про джерела даних {date: {'source': str, ...}}
    
    Returns:
        dict: оновлений стан
    """
    logger.debug(f"🚨 Початок process_alarms для групи {group}")
    current_time = datetime.now()
    current_time_min = current_time.hour * 60 + current_time.minute
    current_date = current_time.strftime('%Y-%m-%d')
    
    logger.debug(f"⏰ Поточний час: {current_time.strftime('%H:%M')} ({current_time_min} хвилин від початку доби)")
    
    # Скидаємо лічильник сповіщень о півночі
    if current_time_min == 0:
        logger.debug("🌙 Північ - скидаємо лічильники сповіщень")
        # Видаляємо всі ключі alarm для попередніх днів
        alarm_keys_to_remove = [k for k in states.keys() if k.startswith('last_alarm_') and current_date not in k]
        for key in alarm_keys_to_remove:
            del states[key]
        return states
    
    # Перевіряємо чи не надсилали сповіщення цієї години цього дня
    alarm_key = f"last_alarm_{group}_{current_date}_{current_time.hour}"
    logger.debug(f"🔑 Ключ сповіщення: {alarm_key}")
    
    if alarm_key in states:
        logger.debug(f"🔕 Сповіщення вже надсилалось {current_date} о {current_time.hour}:XX")
        return states
    
    # Отримуємо дані сьогодні
    if current_date not in merged_data:
        logger.debug(f"❌ Немає даних для {current_date}")
        return states
    
    today_data = merged_data[current_date]
    
    # Отримуємо дані завтра (якщо є)
    tomorrow_date = datetime.now().strftime('%Y-%m-%d')
    from datetime import timedelta
    tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    tomorrow_data = merged_data.get(tomorrow_date)
    
    # Витягуємо планові відключення
    definite_slots = extract_definite_slots(today_data)
    logger.debug(f"📋 Знайдено слотів відключення: {len(definite_slots) if definite_slots else 0}")
    
    if not definite_slots:
        logger.debug("❌ Немає планових відключень для обробки")
        return states
    
    periods = consolidate_periods(definite_slots)
    logger.debug(f"📊 Консолідовано періодів: {len(periods)}")
    
    # Перевіряємо чи є кросс-день період
    has_cross_day = is_cross_day_continuation(today_data, tomorrow_data)
    
    # Перевіряємо чи використовується стандартний розклад
    is_standard = False
    if source_info and current_date in source_info:
        is_standard = source_info[current_date].get('source') == 'standard'
    
    # Додаємо префікс для стандартного розкладу
    standard_prefix = "⚠️ (Стандартний графік) " if is_standard else ""
    
    for i, period in enumerate(periods, 1):
        start_minutes = period['start']
        end_minutes = period['end']
        
        # ПРОПУСКАЄМО період, що починається о 00:00, якщо він є продовженням вчорашнього
        if start_minutes == 0 and has_cross_day:
            logger.debug(f"⏭️ Пропускаємо період {i} (00:00-{format_time(end_minutes)}) - продовження кросс-день періоду")
            continue
        
        logger.debug(f"🔍 Період {i}: {format_time(start_minutes)} - {format_time(end_minutes)} ({start_minutes}-{end_minutes} хв)")
        
        # ========== ПОПЕРЕДЖЕННЯ ЗА 30 ХВИЛИН ДО ВІДКЛЮЧЕННЯ ==========
        start_warning_time = start_minutes - 30
        logger.debug(f"⚠️ Попередження про відключення: {format_time(start_warning_time)} - {format_time(start_warning_time + 30)}")
        
        if start_warning_time <= current_time_min < start_warning_time + 30:
            logger.info(f"🔴 ТРИГЕР: Попередження про відключення!")
            
            start_time = format_time(start_minutes)
            
            # Якщо період закінчується о 24:00 і продовжується завтра
            if end_minutes == 1440 and has_cross_day and tomorrow_data:
                tomorrow_definite = extract_definite_slots(tomorrow_data)
                if tomorrow_definite:
                    tomorrow_periods = consolidate_periods(tomorrow_definite)
                    if tomorrow_periods and tomorrow_periods[0]['start'] == 0:
                        real_end = tomorrow_periods[0]['end']
                        end_time = f"завтра о {format_time(real_end)}"
                        logger.debug(f"🌉 Кросс-день: відновлення завтра о {format_time(real_end)}")
                    else:
                        end_time = format_time(end_minutes)
                else:
                    end_time = format_time(end_minutes)
            else:
                end_time = format_time(end_minutes)
            
            message = f"{standard_prefix}🔴 Попередження: відключення о {start_time}\nОчікуване відновлення: {end_time}"
            
            # Відправляємо сповіщення
            send_alarm_to_telegram(message, config)
            
            # Зберігаємо що надіслали
            states[alarm_key] = current_time.isoformat()
            logger.debug(f"💾 Збережено alarm_key для відключення: {alarm_key}")
            return states
        
        # ========== ПОПЕРЕДЖЕННЯ ЗА 60 ХВИЛИН ДО ВІДНОВЛЕННЯ ==========
        # Для періодів, що закінчуються о 24:00 і продовжуються завтра, НЕ надсилаємо
        if end_minutes == 1440 and has_cross_day:
            logger.debug(f"⏭️ Пропускаємо попередження про відновлення для кросс-день періоду (24:00)")
            continue
        
        end_warning_time = end_minutes - 60
        logger.debug(f"⚡ Попередження про відновлення: {format_time(end_warning_time)} - {format_time(end_warning_time + 30)}")
        
        if end_warning_time <= current_time_min < end_warning_time + 30:
            logger.info(f"🟢 ТРИГЕР: Попередження про відновлення!")
            
            end_time_start = format_time(end_minutes - 30)
            end_time_end = format_time(end_minutes)
            
            message = f"{standard_prefix}🟢 Очікується відновлення електроенергії з {end_time_start} по {end_time_end}"
            
            # Відправляємо сповіщення
            send_alarm_to_telegram(message, config)
            
            # Зберігаємо що надіслали
            states[alarm_key] = current_time.isoformat()
            logger.debug(f"💾 Збережено alarm_key для відновлення: {alarm_key}")
            return states
    
    logger.debug("✅ process_alarms завершено - жодних попереджень не потрібно")
    return states


def send_alarm_to_telegram(message, config):
    """Відправляємо попередження в Telegram"""
    import requests
    
    logger.info(f"📢 Відправка попередження: {message}")
    
    success_count = 0
    total_chats = len(config['all_chat_ids'])
    
    for chat_id in config['all_chat_ids']:
        try:
            url = f"https://api.telegram.org/bot{config['bot_token']}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            response = requests.post(url, data=payload, timeout=30)
            response.raise_for_status()
            success_count += 1
            logger.debug(f"✅ Попередження відправлено в чат {chat_id}")
        except Exception as e:
            logger.error(f"❌ Помилка відправки попередження в чат {chat_id}: {e}")
    
    logger.info(f"📊 Попередження відправлено в {success_count}/{total_chats} чатів")
