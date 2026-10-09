"""
Модуль для обробки та об'єднання даних з різних джерел.
Конвертує дані DTEK у формат YASNO, консолідує періоди, об'єднує джерела.
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def consolidate_periods(periods):
    """
    Об'єднуємо суміжні періоди відключень у більші блоки.
    Наприклад: [270-300, 300-360, 360-420] → [270-420]
    
    Args:
        periods: список словників {'start': int, 'end': int, 'type': str}
    
    Returns:
        list: консолідовані періоди
    """
    if not periods:
        return []
    
    logger.debug(f"🔧 consolidate_periods: вхідних періодів {len(periods)}")
    
    # Логуємо вхідні періоди
    for i, p in enumerate(periods, 1):
        start_time = format_minutes_to_time(p['start'])
        end_time = format_minutes_to_time(p['end'])
        logger.debug(f"  Вхідний період {i}: {start_time} - {end_time} ({p['start']}-{p['end']})")
    
    # Сортуємо по часу початку
    sorted_periods = sorted(periods, key=lambda x: x['start'])
    logger.debug("📊 Періоди відсортовано за часом початку")
    
    # Об'єднуємо суміжні періоди
    consolidated = []
    current = sorted_periods[0].copy()
    
    start_time = format_minutes_to_time(current['start'])
    end_time = format_minutes_to_time(current['end'])
    logger.debug(f"🚀 Початковий період: {start_time} - {end_time}")
    
    for period in sorted_periods[1:]:
        start_time = format_minutes_to_time(period['start'])
        end_time = format_minutes_to_time(period['end'])
        logger.debug(f"🔍 Перевіряємо період {len(consolidated) + 2}: {start_time} - {end_time}")
        
        current_end_time = format_minutes_to_time(current['end'])
        logger.debug(f"    Поточний кінець: {current_end_time} ({current['end']})")
        logger.debug(f"    Новий початок: {start_time} ({period['start']})")
        
        # Якщо новий період починається там де закінчився попередній (або раніше)
        if period['start'] <= current['end']:
            # Розширюємо поточний період
            logger.debug(f"    ✅ Об'єднуємо: {period['start']} <= {current['end']}")
            current['end'] = max(current['end'], period['end'])
            new_end_time = format_minutes_to_time(current['end'])
            start_current = format_minutes_to_time(current['start'])
            logger.debug(f"    📈 Розширено період до: {start_current} - {new_end_time}")
        else:
            # Зберігаємо попередній і починаємо новий
            logger.debug(f"    ➡️ Зберігаємо період та починаємо новий")
            save_start = format_minutes_to_time(current['start'])
            save_end = format_minutes_to_time(current['end'])
            logger.debug(f"    💾 Збережено: {save_start} - {save_end}")
            
            consolidated.append(current)
            current = period.copy()
            
            new_start = format_minutes_to_time(current['start'])
            new_end = format_minutes_to_time(current['end'])
            logger.debug(f"    🆕 Новий період: {new_start} - {new_end}")
    
    # Додаємо останній період
    consolidated.append(current)
    last_start = format_minutes_to_time(current['start'])
    last_end = format_minutes_to_time(current['end'])
    logger.debug(f"💾 Збережено останній період: {last_start} - {last_end}")
    
    logger.debug(f"✅ Консолідація завершена: {len(periods)} → {len(consolidated)} періодів")
    for i, p in enumerate(consolidated, 1):
        start_time = format_minutes_to_time(p['start'])
        end_time = format_minutes_to_time(p['end'])
        logger.debug(f"  Фінальний період {i}: {start_time} - {end_time}")
    
    return consolidated


def format_minutes_to_time(minutes):
    """Конвертуємо хвилини від початку дня у формат HH:MM"""
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def convert_dtek_to_yasno_format(dtek_hours, date_str, update_time):
    """
    Конвертуємо формат DTEK (yes/no/first/second) у формат YASNO.
    
    Args:
        dtek_hours: dict {1: 'yes', 2: 'no', ...} - години та їх статуси
        date_str: str - дата у форматі YYYY-MM-DD
        update_time: str - час оновлення даних DTEK
    
    Returns:
        dict: дані у форматі YASNO з консолідованими слотами
    """
    logger.debug(f"Конвертація DTEK даних для {date_str}")
    
    slots = []
    
    # dtek_hours - це словник з ключами "1"-"24" та значеннями yes/no/first/second
    for hour_str, status in sorted(dtek_hours.items(), key=lambda x: int(x[0])):
        hour = int(hour_str)
        start_minutes = (hour - 1) * 60  # Година 1 = 0-60 хвилин
        end_minutes = hour * 60
        
        if status == "no":
            # Повне відключення на годину
            slots.append({
                "start": start_minutes,
                "end": end_minutes,
                "type": "Definite"
            })
            logger.debug(f"  Година {hour}: відключення {start_minutes}-{end_minutes}")
        elif status == "first":
            # Відключення перші 30 хвилин
            slots.append({
                "start": start_minutes,
                "end": start_minutes + 30,
                "type": "Definite"
            })
            logger.debug(f"  Година {hour}: відключення першої половини {start_minutes}-{start_minutes + 30}")
        elif status == "second":
            # Відключення другі 30 хвилин
            slots.append({
                "start": start_minutes + 30,
                "end": end_minutes,
                "type": "Definite"
            })
            logger.debug(f"  Година {hour}: відключення другої половини {start_minutes + 30}-{end_minutes}")
        elif status == "yes":
            # Електроенергія є
            logger.debug(f"  Година {hour}: електроенергія є")
            pass
    
    logger.debug(f"📊 ДТЕК: отримано {len(slots)} окремих слотів")
    
    # Консолідуємо суміжні періоди
    if slots:
        consolidated_slots = consolidate_periods(slots)
    else:
        consolidated_slots = []
    
    # Створюємо слоти NotPlanned для заповнення проміжків
    all_slots = []
    if consolidated_slots:
        # Якщо є відключення, додаємо NotPlanned між ними
        last_end = 0
        for slot in consolidated_slots:
            if slot['start'] > last_end:
                all_slots.append({
                    "start": last_end,
                    "end": slot['start'],
                    "type": "NotPlanned"
                })
            all_slots.append(slot)
            last_end = slot['end']
        
        # Якщо останнє відключення не до кінця дня
        if last_end < 1440:
            all_slots.append({
                "start": last_end,
                "end": 1440,
                "type": "NotPlanned"
            })
    else:
        # Якщо немає відключень, весь день NotPlanned
        all_slots = [{
            "start": 0,
            "end": 1440,
            "type": "NotPlanned"
        }]
    
    # Формуємо результат у форматі YASNO
    result = {
        "date": f"{date_str}T00:00:00+02:00",
        "status": "ScheduleApplies",
        "slots": all_slots
    }
    
    logger.debug(f"✅ Конвертовано ДТЕК → YASNO: {len(consolidated_slots)} періодів відключень")
    return result


def calculate_schedule_hash(day_data):
    """
    Обчислюємо хеш для відстеження змін у розкладі.
    
    Args:
        day_data: dict з полями 'slots' та 'date'
    
    Returns:
        str: хеш розкладу
    """
    hash_str = ""
    
    if not day_data or "slots" not in day_data:
        return ""
    
    # Враховуємо тільки слоти типу "Definite" (планові відключення)
    for slot in day_data["slots"]:
        if slot.get("type") == "Definite":
            hash_str += f"{slot['start']}-{slot['end']}"
    
    # Додаємо дату для унікальності
    if "date" in day_data:
        hash_str += day_data["date"]
    
    return hash_str


def merge_sources_data(yasno_data, dtek_data, standard_data=None, dtek_fact_data=None):
    """
    Об'єднуємо дані з усіх джерел з урахуванням пріоритетів.
    
    Пріоритет джерел (від найвищого до найнижчого):
    1. DTEK Fact (графік з аварій) - найактуальніший
    2. DTEK Schedule (загальний графік)
    3. YASNO (офіційний графік)
    4. Standard Schedule (резервний статичний графік)
    
    Args:
        yasno_data: dict {date: {...}, date: {...}} або None
        dtek_data: dict {'dates': {date: {...}}, 'update_time': str} або None
        standard_data: dict {date: {...}, date: {...}} або None (стандартний розклад)
        dtek_fact_data: dict {date: {...}, date: {...}} або None (графік з DTEK fact)
    
    Returns:
        tuple: (merged_data, source_info)
            merged_data: dict {date: {...}}
            source_info: dict {date: {'source': str, 'update_time': str}}
    """
    logger.info("🔄 Початок об'єднання даних з усіх джерел")
    
    # Визначаємо які дати нам потрібні
    today_date = datetime.now().strftime('%Y-%m-%d')
    tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    
    logger.debug(f"📅 Потрібні дати: {today_date}, {tomorrow_date}")
    
    merged = {}
    source_info = {}
    
    # Якщо всі джерела недоступні
    if not yasno_data and not dtek_data and not standard_data and not dtek_fact_data:
        logger.warning("❌ Всі джерела даних недоступні")
        return {}, {}
    
    # Підготовка даних з усіх джерел
    standard_dates = standard_data if standard_data else {}
    yasno_dates = yasno_data if yasno_data else {}
    dtek_fact_dates = dtek_fact_data if dtek_fact_data else {}
    dtek_dates = {}
    
    if dtek_data and 'dates' in dtek_data:
        # Конвертуємо дані DTEK у формат YASNO
        for date_str, date_data in dtek_data['dates'].items():
            dtek_converted = convert_dtek_to_yasno_format(
                date_data['hours'],
                date_str,
                date_data['update_time']
            )
            dtek_dates[date_str] = dtek_converted
            logger.debug(f"✅ Конвертовано DTEK дані для {date_str}")
    
    # Обробляємо кожну потрібну дату
    for target_date in [today_date, tomorrow_date]:
        yasno_has_date = target_date in yasno_dates
        dtek_has_date = target_date in dtek_dates
        dtek_fact_has_date = target_date in dtek_fact_dates
        
        # Пріоритет 1: DTEK Fact (якщо є)
        if dtek_fact_has_date:
            logger.info(f"🎯 {target_date}: Використовуємо DTEK Fact (найвищий пріоритет)")
            merged[target_date] = dtek_fact_dates[target_date]
            source_info[target_date] = {
                'source': 'dtek_fact',
                'update_time': dtek_fact_dates[target_date].get('update_time', '')
            }
            continue
        
        if yasno_has_date and dtek_has_date:
            # Обидва джерела мають дані
            # Перевіряємо статус YASNO
            yasno_status = yasno_dates[target_date].get('status', '')
            if yasno_status in ('WaitingForSchedule', 'EmergencyShutdowns'):
                # YASNO ще не має розкладу або аварійний режим
                if target_date == today_date:
                    # Для сьогодні використовуємо DTEK
                    logger.info(f"⏳ {target_date}: YASNO {'очікує розклад' if yasno_status == 'WaitingForSchedule' else 'аварійний режим'} - використовуємо DTEK")
                    merged[target_date] = dtek_dates[target_date]
                    source_info[target_date] = {
                        'source': 'dtek',
                        'update_time': dtek_data.get('update_time', '')
                    }
                else:
                    # Для завтра перевіряємо чи DTEK має відключення
                    dtek_day = dtek_dates[target_date]
                    has_outages = any(slot.get('type') == 'Definite' for slot in dtek_day.get('slots', []))
                    
                    if has_outages:
                        # DTEK має відключення - використовуємо його розклад
                        status_text = 'очікує' if yasno_status == 'WaitingForSchedule' else 'аварійний'
                        logger.info(f"✅ {target_date}: YASNO {status_text}, але DTEK має відключення - використовуємо DTEK")
                        merged[target_date] = dtek_dates[target_date]
                        source_info[target_date] = {
                            'source': 'dtek',
                            'update_time': dtek_data.get('update_time', '')
                        }
                    else:
                        # DTEK без відключень - перевіряємо стандартний розклад
                        if target_date in standard_dates:
                            status_text = 'очікує розклад' if yasno_status == 'WaitingForSchedule' else 'аварійний режим'
                            logger.info(f"📋 {target_date}: YASNO {status_text}, DTEK без відключень - використовуємо стандартний розклад")
                            merged[target_date] = standard_dates[target_date]
                            source_info[target_date] = {
                                'source': 'standard',
                                'update_time': None
                            }
                        else:
                            # Немає жодного джерела
                            status_text = 'очікує розклад' if yasno_status == 'WaitingForSchedule' else 'аварійний режим'
                            logger.info(f"⏳ {target_date}: YASNO {status_text}, DTEK без відключень, немає стандартного розкладу - пропускаємо")
                            continue
            else:
                # Обидва джерела мають дані - порівнюємо хеші
                yasno_hash = calculate_schedule_hash(yasno_dates[target_date])
                dtek_hash = calculate_schedule_hash(dtek_dates[target_date])
                
                logger.debug(f"📊 {target_date}: YASNO hash={yasno_hash[:50]}..., DTEK hash={dtek_hash[:50]}...")
                
                # DTEK має пріоритет для всіх дат (швидші та точніші оновлення)
                if yasno_hash != dtek_hash:
                    logger.info(f"⚡ {target_date}: DTEK має інший розклад - використовуємо його (пріоритет)")
                    merged[target_date] = dtek_dates[target_date]
                    source_info[target_date] = {
                        'source': 'dtek',
                        'update_time': dtek_data.get('update_time', '')
                    }
                else:
                    # Якщо розклади однакові - використовуємо YASNO
                    merged[target_date] = yasno_dates[target_date]
                    source_info[target_date] = {
                        'source': 'yasno',
                        'update_time': None
                    }
                
        elif yasno_has_date:
            # Тільки YASNO має дані
            # Перевіряємо чи розклад опублікований
            yasno_status = yasno_dates[target_date].get('status', '')
            if yasno_status in ('WaitingForSchedule', 'EmergencyShutdowns'):
                # YASNO не має розкладу - використовуємо стандартний
                if target_date in standard_dates:
                    status_text = 'очікує розклад' if yasno_status == 'WaitingForSchedule' else 'аварійний режим'
                    logger.info(f"📋 {target_date}: YASNO {status_text}, DTEK недоступний - використовуємо стандартний розклад")
                    merged[target_date] = standard_dates[target_date]
                    source_info[target_date] = {
                        'source': 'standard',
                        'update_time': None
                    }
                else:
                    status_text = 'очікує розклад' if yasno_status == 'WaitingForSchedule' else 'аварійний режим'
                    logger.info(f"⏳ {target_date}: YASNO {status_text}, немає альтернативних джерел - пропускаємо")
                    continue
            else:
                # YASNO має опублікований розклад
                merged[target_date] = yasno_dates[target_date]
                source_info[target_date] = {
                    'source': 'yasno',
                    'update_time': None
                }
                logger.debug(f"📡 {target_date}: тільки YASNO")
            
        elif dtek_has_date:
            # Тільки DTEK має дані
            if target_date == today_date:
                # Для сьогодні завжди використовуємо DTEK
                merged[target_date] = dtek_dates[target_date]
                source_info[target_date] = {
                    'source': 'dtek',
                    'update_time': dtek_data.get('update_time', '')
                }
                logger.debug(f"📡 {target_date}: тільки DTEK (сьогодні)")
            else:
                # Для завтра перевіряємо чи є відключення
                dtek_day = dtek_dates[target_date]
                has_outages = any(slot.get('type') == 'Definite' for slot in dtek_day.get('slots', []))
                
                if has_outages:
                    # Є відключення - рахуємо це справжнім розкладом
                    merged[target_date] = dtek_dates[target_date]
                    source_info[target_date] = {
                        'source': 'dtek',
                        'update_time': dtek_data.get('update_time', '')
                    }
                    logger.info(f"✅ {target_date}: DTEK має відключення на завтра - використовуємо")
                else:
                    # Немає відключень - хибна інформація, чекаємо YASNO
                    logger.info(f"⏭️ {target_date}: DTEK без відключень на завтра - пропускаємо, чекаємо YASNO")
                    continue
        else:
            # Жодного джерела (YASNO/DTEK) немає - перевіряємо стандартний розклад
            if target_date in standard_dates:
                logger.info(f"📋 {target_date}: Використовуємо стандартний розклад (YASNO/DTEK недоступні)")
                merged[target_date] = standard_dates[target_date]
                source_info[target_date] = {
                    'source': 'standard',
                    'update_time': None
                }
            else:
                logger.warning(f"⚠️ Немає даних для {target_date} (включно зі стандартним розкладом)")
                # Не додаємо порожні дані в merged
                # Жодного джерела немає
            logger.warning(f"⚠️ Немає даних для {target_date}")
            # Не додаємо порожні дані в merged
            continue
    
    logger.info(f"✅ Об'єднання завершено:")
    for date_key in sorted(merged.keys()):
        source = source_info.get(date_key, {}).get('source', 'N/A')
        logger.info(f"   {date_key}: {source}")
    
    return merged, source_info
