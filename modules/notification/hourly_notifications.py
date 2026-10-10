"""
Модуль для перевірки майбутніх подій відключення/відновлення
та відправки попереджень за певний час до них
"""
import logging
from modules.timeutils import now_kyiv
from modules.processing.state_manager import StateManager
from modules.data_sources.ha_power_checker import get_power_status_from_ha

logger = logging.getLogger(__name__)


def format_time(minutes, offset=0):
    """
    Конвертує хвилини від початку доби в формат HH:MM з можливим зсувом
    
    Args:
        minutes: Хвилини від початку доби (0-1440)
        offset: Зсув у хвилинах (може бути від'ємним)
    
    Returns:
        Час у форматі HH:MM або None якщо некоректні дані
    """
    try:
        total_minutes = minutes + offset
        
        if total_minutes < 0 or total_minutes >= 1440:
            return None
        
        hours = int(total_minutes // 60)
        mins = int(total_minutes % 60)
        
        return f"{hours:02}:{mins:02}"
    except (ValueError, TypeError):
        return None


def extract_definite_slots(schedule_data):
    """
    Витягує всі слоти типу Definite (планові відключення) з даних графіка
    
    Args:
        schedule_data: Дані графіка з ключами date, slots, status
    
    Returns:
        Список слотів відключення або None якщо їх немає
    """
    if not schedule_data or not isinstance(schedule_data, dict):
        return None
    
    slots = schedule_data.get('slots', [])
    if not slots:
        return None
    
    definite_slots = [slot for slot in slots if slot.get('type') == 'Definite']
    
    return definite_slots if definite_slots else None


def consolidate_periods(slots):
    """
    Об'єднує суміжні періоди відключень у єдині блоки
    
    Args:
        slots: Список слотів з полями start, end, type
    
    Returns:
        Список консолідованих періодів
    """
    if not slots or len(slots) == 0:
        return []
    
    # Сортуємо за початком
    sorted_slots = sorted(slots, key=lambda x: x['start'])
    
    consolidated = []
    current = dict(sorted_slots[0])  # Копіюємо перший період
    
    for slot in sorted_slots[1:]:
        # Якщо наступний період починається до або одразу після закінчення поточного
        if slot['start'] <= current['end']:
            # Розширюємо поточний період
            current['end'] = max(current['end'], slot['end'])
        else:
            # Зберігаємо завершений період і починаємо новий
            consolidated.append(current)
            current = dict(slot)
    
    # Додаємо останній період
    consolidated.append(current)
    
    return consolidated


def is_cross_day_continuation(schedule_data):
    """
    Перевіряє чи є кросс-день період (відключення триває до завтра)
    
    Args:
        schedule_data: Дані графіка з today та tomorrow
    
    Returns:
        True якщо today закінчується о 24:00 і tomorrow починається з 00:00
    """
    if not schedule_data or not isinstance(schedule_data, dict):
        return False
    
    today_data = schedule_data.get('today')
    tomorrow_data = schedule_data.get('tomorrow')
    
    if not today_data or not tomorrow_data:
        return False
    
    # Перевіряємо чи є Definite слоти
    today_slots = extract_definite_slots(today_data)
    tomorrow_slots = extract_definite_slots(tomorrow_data)
    
    if not today_slots or not tomorrow_slots:
        return False
    
    # Консолідуємо періоди
    today_periods = consolidate_periods(today_slots)
    tomorrow_periods = consolidate_periods(tomorrow_slots)
    
    # Перевіряємо чи останній період сьогодні закінчується о 24:00
    # та перший завтра починається о 00:00
    if today_periods and tomorrow_periods:
        last_today = today_periods[-1]
        first_tomorrow = tomorrow_periods[0]
        
        if last_today['end'] == 1440 and first_tomorrow['start'] == 0:
            return True
    
    return False


def check_upcoming_events(merged_data, group, state_manager):
    """
    Перевіряє чи наближається відключення або відновлення електроенергії
    та повертає відповідне попередження
    
    Args:
        merged_data: Об'єднані дані з усіх джерел (today, tomorrow)
        group: Номер групи відключень
        state_manager: Менеджер стану для збереження відправлених сповіщень
    
    Returns:
        Текст попередження або None якщо попередження не потрібне
    """
    logger.debug(f"🚨 Перевірка майбутніх подій для групи {group}")
    
    if not merged_data:
        logger.info("❌ Причина: Немає даних для перевірки")
        return None
    
    # Отримуємо дані для сьогодні
    today_data = merged_data.get('today')
    if not today_data:
        logger.info("❌ Причина: Немає даних для сьогодні")
        return None
    
    # Поточний час
    current_time = now_kyiv()
    current_time_min = current_time.hour * 60 + current_time.minute
    current_date = current_time.strftime('%Y-%m-%d')
    
    logger.info(f"⏰ Поточний час: {current_time.strftime('%H:%M')} ({current_time_min} хвилин від початку доби)")
    
    # Скидаємо лічильник о півночі
    if current_time_min == 0:
        logger.info("🌙 Причина: Північ - скидаємо лічильники попереджень")
        return None
    
    # Витягуємо планові відключення
    definite_slots = extract_definite_slots(today_data)
    
    if not definite_slots:
        logger.info("❌ Причина: Немає планових відключень на сьогодні")
        return None
    
    # Консолідуємо періоди
    periods = consolidate_periods(definite_slots)
    logger.info(f"📊 Знайдено відключень: {len(periods)} період(ів)")
    
    # Перевіряємо кросс-день
    has_cross_day = is_cross_day_continuation(merged_data)
    if has_cross_day:
        logger.info("🌉 Виявлено кросс-день період (відключення продовжується після півночі)")
    
    # Перевіряємо кожен період
    for i, period in enumerate(periods):
        start_minutes = period['start']
        end_minutes = period['end']
        
        logger.info(f"🔍 Перевірка періоду {i+1}: {format_time(start_minutes)} - {format_time(end_minutes)}")
        
        # ПРОПУСКАЄМО період що починається о 00:00 якщо це продовження
        if start_minutes == 0 and has_cross_day:
            logger.info(f"⏭️ Причина: Період {i+1} пропущено - це продовження вчорашнього відключення")
            continue
        
        # === ПОПЕРЕДЖЕННЯ ЗА 30 ХВИЛИН (ПІВ ГОДИНИ) ДО ВІДКЛЮЧЕННЯ ===
        start_warning_time = start_minutes - 30
        start_warning_end = start_warning_time + 30
        logger.debug(f"⚠️ Вікно попередження про відключення: {format_time(start_warning_time)} - {format_time(start_warning_end)}")
        
        if start_warning_time <= current_time_min < start_warning_end:
            # Перевіряємо чи не відправляли вже попередження для цього періоду
            alarm_key = f"hourly_outage_{group}_{current_date}_{start_minutes}"
            
            if state_manager.get_notification_sent(alarm_key):
                logger.info(f"🔕 Попередження про відключення о {format_time(start_minutes)} вже було відправлено")
                continue
            
            # Перевіряємо реальний стан електрики через Home Assistant
            has_power = get_power_status_from_ha()
            if has_power is False:
                logger.info(f"⏭️ Пропускаємо попередження про відключення - електрики вже немає (HA)")
                # Відмічаємо як відправлене, щоб не перевіряти знову
                state_manager.mark_notification_sent(alarm_key, current_time.isoformat())
                continue
            
            logger.info(f"✅ ВІДПРАВКА: Попередження про відключення (поточний час {current_time.strftime('%H:%M')} у вікні {format_time(start_warning_time)}-{format_time(start_warning_end)})")
            
            # Зберігаємо що відправили попередження
            state_manager.mark_notification_sent(alarm_key, current_time.isoformat())
            
            start_time = format_time(start_minutes)
            
            # Якщо період закінчується о 24:00 і продовжується завтра
            if end_minutes == 1440 and has_cross_day:
                tomorrow_data = merged_data.get('tomorrow')
                if tomorrow_data:
                    tomorrow_definite = extract_definite_slots(tomorrow_data)
                    if tomorrow_definite:
                        tomorrow_periods = consolidate_periods(tomorrow_definite)
                        if tomorrow_periods and tomorrow_periods[0]['start'] == 0:
                            real_end = tomorrow_periods[0]['end']
                            end_time = f"завтра о {format_time(real_end, -30)}"
                            logger.debug(f"🌉 Кросс-день: відновлення завтра о {format_time(real_end)}")
                        else:
                            end_time = format_time(end_minutes, -30)
                    else:
                        end_time = format_time(end_minutes, -30)
                else:
                    end_time = format_time(end_minutes, -30)
            else:
                end_time = format_time(end_minutes, -30)
            
            return f"🔴 Попередження: відключення о {start_time}\nОчікуване відновлення: {end_time}"
        
        # === ПОПЕРЕДЖЕННЯ ЗА 60 ХВИЛИН (1 ГОД) ДО ВІДНОВЛЕННЯ ===
        # Для кросс-день періодів що закінчуються о 24:00 НЕ надсилаємо
        if end_minutes == 1440 and has_cross_day:
            logger.info(f"⏭️ Причина: Попередження про відновлення пропущено - кросс-день період (відновлення буде завтра)")
            continue
        
        end_warning_time = end_minutes - 60
        end_warning_end = end_warning_time + 30
        logger.debug(f"⚡ Вікно попередження про відновлення: {format_time(end_warning_time)} - {format_time(end_warning_end)}")
        
        if end_warning_time <= current_time_min < end_warning_end:
            # Перевіряємо чи не відправляли вже попередження для цього періоду
            alarm_key = f"hourly_restore_{group}_{current_date}_{end_minutes}"
            
            if state_manager.get_notification_sent(alarm_key):
                logger.info(f"🔕 Попередження про відновлення о {format_time(end_minutes)} вже було відправлено")
                continue
            
            # Перевіряємо реальний стан електрики через Home Assistant
            has_power = get_power_status_from_ha()
            if has_power is True:
                logger.info(f"⏭️ Пропускаємо попередження про відновлення - електрика вже є (HA)")
                # Відмічаємо як відправлене, щоб не перевіряти знову
                state_manager.mark_notification_sent(alarm_key, current_time.isoformat())
                continue
            
            logger.info(f"✅ ВІДПРАВКА: Попередження про відновлення (поточний час {current_time.strftime('%H:%M')} у вікні {format_time(end_warning_time)}-{format_time(end_warning_end)})")
            
            # Зберігаємо що відправили попередження
            state_manager.mark_notification_sent(alarm_key, current_time.isoformat())
            
            end_time_start = format_time(end_minutes, -30)
            end_time_end = format_time(end_minutes, 0)
            
            return f"🟢 Очікується відновлення електроенергії з {end_time_start} по {end_time_end}"
    
    logger.info("❌ Причина: Поточний час не потрапляє у вікна попереджень (за 60 хв до подій)")
    return None
