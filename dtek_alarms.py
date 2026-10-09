"""
Модуль для моніторингу аварійних відключень DTEK.
Відстежує зміни в аварійних відключеннях по будинках та відправляє повідомлення.
"""

import json
import logging
import os
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

DTEK_ALARMS_STATE_FILE = './dtek_alarms_state.json'


def format_timestamp(timestamp_str):
    """
    Форматує timestamp у зручний для читання формат.
    
    Args:
        timestamp_str: ISO timestamp рядок
    
    Returns:
        str: Відформатований час
    """
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt.strftime('%d.%m.%Y %H:%M')
    except:
        return timestamp_str


def find_most_affected_group(alarms_groups):
    """
    Знаходить групу з найбільшою кількістю будинків, що мають аварії.
    
    Args:
        alarms_groups: Словник з групами аварій
    
    Returns:
        str: Номер групи (наприклад "6.2") або None якщо аварій немає
    """
    if not alarms_groups:
        logger.info("📊 Аварій немає - використовуємо групу з .env")
        return None
    
    # Підраховуємо будинки по групах
    group_counts = {}
    
    for alarm_info in alarms_groups.values():
        houses = alarm_info.get('houses', [])
        
        for house in houses:
            # Отримуємо інформацію про групу
            if isinstance(house, dict):
                group_name = house.get('group', '')
            else:
                # Старий формат - немає інформації про групу
                continue
            
            if group_name:
                # Витягуємо номер групи з назви (наприклад "GPV6.2" -> "6.2")
                group_number = extract_group_number(group_name)
                if group_number:
                    if group_number not in group_counts:
                        group_counts[group_number] = set()
                    # Додаємо номер будинку до множини (щоб не враховувати дублікати)
                    group_counts[group_number].add(house.get('number', ''))
    
    if not group_counts:
        logger.info("📊 Не знайдено інформації про групи в аваріях - використовуємо групу з .env")
        return None
    
    # Знаходимо групу з найбільшою кількістю будинків
    most_affected_group = max(group_counts.items(), key=lambda x: len(x[1]))
    group_number = most_affected_group[0]
    houses_count = len(most_affected_group[1])
    
    logger.info(f"🎯 Найбільш уражена група: {group_number} ({houses_count} будинків)")
    logger.info(f"📊 Статистика груп: {', '.join(f'{g}: {len(h)} буд.' for g, h in sorted(group_counts.items()))}")
    
    return group_number


def extract_group_number(group_name):
    """
    Витягує номер групи з назви.
    
    Args:
        group_name: Назва групи (наприклад "GPV6.2")
    
    Returns:
        str: Номер групи ("6.2") або None
    """
    import re
    
    # Шукаємо патерн: GPV + число (може бути з крапкою)
    match = re.search(r'GPV(\d+(?:\.\d+)?)', group_name)
    if match:
        return match.group(1)
    
    # Якщо патерн не знайдено, але є число в кінці
    match = re.search(r'(\d+(?:\.\d+)?)$', group_name)
    if match:
        return match.group(1)
    
    logger.warning(f"⚠️ Не вдалося витягти номер з групи '{group_name}'")
    return None


def format_timestamp(timestamp_str):
    """
    Форматує timestamp в український формат дати/часу.
    
    Args:
        timestamp_str: Timestamp в ISO форматі або рядок
    
    Returns:
        str: Відформатований час у форматі "ДД.ММ.РРРР ГГ:ХХ"
    """
    try:
        if not timestamp_str or 'T' not in timestamp_str:
            return timestamp_str
        
        # Очищаємо timestamp від мікросекунд та timezone
        # Формати: 2026-01-17T19:44:29.571502, 2026-01-17T19:44:29571502, 2026-01-17T19:44:29+02:00
        
        # Розділяємо по 'T'
        date_part, time_part = timestamp_str.split('T', 1)
        
        # Видаляємо timezone якщо є (все після + або Z)
        if '+' in time_part:
            time_part = time_part.split('+')[0]
        elif 'Z' in time_part:
            time_part = time_part.split('Z')[0]
        
        # Обробляємо мікросекунди
        if '.' in time_part:
            # Формат з крапкою: 19:44:29.571502
            time_part = time_part.split('.')[0]
        else:
            # Формат без крапки але з мікросекундами: 19:44:29571502
            # Відрізаємо останні 6 цифр якщо час довший за ГГ:ХХ:СС (8 символів з двокрапками)
            if len(time_part) > 8:
                time_part = time_part[:8]
        
        # Парсимо очищений timestamp
        clean_timestamp = f"{date_part}T{time_part}"
        dt = datetime.fromisoformat(clean_timestamp)
        
        # Форматуємо в український формат: ДД.ММ.РРРР ГГ:ХХ
        return dt.strftime('%d.%m.%Y %H:%M')
    except Exception as e:
        logger.debug(f"Помилка форматування timestamp '{timestamp_str}': {e}")
        # Якщо не вдалося розпарсити, повертаємо оригінальний рядок
        return timestamp_str


def load_dtek_alarms_data(url):
    """
    Завантажуємо дані про аварії DTEK з API.
    
    Args:
        url: URL API DTEK
    
    Returns:
        dict: Дані про аварії або None якщо помилка
    """
    try:
        logger.debug(f"Запит до DTEK Alarms API: {url}")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        logger.info("✅ Отримано відповідь від DTEK Alarms API")
        logger.info(f"📊 Розмір відповіді: {len(str(data))} символів")
        logger.info(f"📊 Тип даних: {type(data)}")
        
        # Виводимо структуру даних верхнього рівня
        logger.info(f"📋 Ключі верхнього рівня: {list(data.keys()) if isinstance(data, dict) else 'НЕ СЛОВНИК!'}")
        
        # Якщо дані занадто великі, виводимо скорочену версію
        data_str = json.dumps(data, ensure_ascii=False, indent=2)
        if len(data_str) > 1000:
            logger.info(f"📄 Початок даних (перші 1000 символів):\n{data_str[:1000]}...")
        else:
            logger.info(f"📄 Повні дані:\n{data_str}")
        
        # Перевіряємо структуру даних
        if 'response' in data:
            logger.debug("✅ Є поле 'response'")
            response_data = data.get('response', {})
            logger.debug(f"📋 Ключі в 'response': {list(response_data.keys())}")
            
            if 'data' in response_data:
                houses_data = response_data['data']
                houses_count = len(houses_data)
                logger.debug(f"✅ Є поле 'data' з {houses_count} будинками")
                
                # Виводимо приклад структури першого будинку
                if houses_data:
                    first_house_key = list(houses_data.keys())[0]
                    first_house_data = houses_data[first_house_key]
                    logger.debug(f"📊 Приклад структури будинку '{first_house_key}':")
                    logger.debug(f"   Ключі: {list(first_house_data.keys())}")
                    logger.debug(f"   Значення: {json.dumps(first_house_data, ensure_ascii=False, indent=2)}")
                    
                    # Виводимо кілька прикладів будинків для розуміння
                    sample_count = min(3, houses_count)
                    logger.debug(f"📋 Перші {sample_count} будинки:")
                    for idx, (house_key, house_data) in enumerate(list(houses_data.items())[:sample_count]):
                        logger.debug(f"   {idx+1}. {house_key}: sub_type='{house_data.get('sub_type', '')}', "
                                   f"start='{house_data.get('start_date', '')}', "
                                   f"end='{house_data.get('end_date', '')}', "
                                   f"type='{house_data.get('type', '')}'")
            else:
                logger.warning("⚠️ Немає поля 'data' в 'response'")
                logger.debug(f"   Наявні ключі: {list(response_data.keys())}")
        else:
            logger.warning("⚠️ Немає поля 'response' в даних")
        
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
        
        start_date = house_info.get('start_date', '').strip()
        end_date = house_info.get('end_date', '').strip()
        alarm_type = house_info.get('type', '').strip()
        
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
    
    # Сортуємо будинки в кожній групі (тепер це словники з 'number' та 'group')
    for group_info in alarms_groups.values():
        group_info['houses'].sort(key=lambda x: (not x['number'][0].isdigit(), x['number']))
    
    return alarms_groups


def format_dtek_alarms_message(alarms_groups, timestamp):
    """
    Форматуємо повідомлення про аварії DTEK.
    
    Args:
        alarms_groups: Згруповані аварії
        timestamp: Час отримання даних
    
    Returns:
        str: Відформатоване повідомлення
    """
    if not alarms_groups:
        return None
    
    message_parts = [
        "🚨 <b>Аварійні відключення DTEK</b>",
        f"📅 Станом на: {format_timestamp(timestamp)}\n"
    ]
    
    total_groups = len(alarms_groups)
    
    for idx, (group_key, group_info) in enumerate(alarms_groups.items(), 1):
        # Форматуємо будинки з групами: "4 (GPV6.2), 6 (GPV6.2)"
        houses_with_groups = []
        for house in group_info['houses']:
            if house['group']:
                houses_with_groups.append(f"{house['number']} ({house['group']})")
            else:
                houses_with_groups.append(house['number'])
        houses_str = ', '.join(houses_with_groups)
        
        # Показуємо номер групи тільки якщо груп більше однієї
        if total_groups > 1:
            message_parts.append(f"<b>Група {idx}:</b>")
        
        message_parts.append(f"  📋 Тип: {group_info['sub_type']}")
        
        if group_info['start_date']:
            message_parts.append(f"  🕐 Початок: {group_info['start_date']}")
        
        if group_info['end_date']:
            message_parts.append(f"  🕐 Очікуване відновлення: {group_info['end_date']}")
        
        message_parts.append(f"  🏠 Будинки: {houses_str}")
        message_parts.append("")  # Порожній рядок між групами
    
    return "\n".join(message_parts)


def format_houses_list(houses):
    """
    Форматує список будинків з групами.
    
    Args:
        houses: Список словників {'number': '4', 'group': 'GPV6.2'} або список рядків (старий формат)
    
    Returns:
        str: Відформатований список будинків
    """
    result = []
    for house in houses:
        if isinstance(house, dict):
            # Новий формат - словник з number та group
            if house.get('group'):
                result.append(f"{house['number']} ({house['group']})")
            else:
                result.append(house['number'])
        else:
            # Старий формат - просто рядок
            result.append(house)
    return ', '.join(result)


def compare_dtek_alarms(old_alarms, new_alarms, timestamp):
    """
    Порівнюємо стан аварій та формуємо повідомлення про зміни.
    
    Args:
        old_alarms: Попередній стан аварій
        new_alarms: Новий стан аварій
        timestamp: Час отримання даних
    
    Returns:
        str: Повідомлення про зміни або None
    """
    messages = []
    
    old_keys = set(old_alarms.keys())
    new_keys = set(new_alarms.keys())
    
    # Створюємо мапу для швидкого пошуку аварій за типом та будинками (без врахування дат)
    def get_alarm_signature(alarm_info):
        """Повертає унікальну сигнатуру аварії (тип + відсортовані будинки)"""
        # Отримуємо номери будинків (враховуємо старий та новий формат)
        house_numbers = []
        for house in alarm_info['houses']:
            if isinstance(house, dict):
                house_numbers.append(house['number'])
            else:
                house_numbers.append(house)
        houses_tuple = tuple(sorted(house_numbers))
        return (alarm_info['sub_type'], houses_tuple)
    
    # Створюємо мапи старих і нових аварій за сигнатурами
    old_by_signature = {}
    for key, info in old_alarms.items():
        sig = get_alarm_signature(info)
        old_by_signature[sig] = (key, info)
    
    new_by_signature = {}
    for key, info in new_alarms.items():
        sig = get_alarm_signature(info)
        new_by_signature[sig] = (key, info)
    
    # Відстежуємо які ключі вже оброблені як зміни часу
    processed_as_time_change = set()
    
    # Перевіряємо зміни часу (той самий тип і будинки, але різні дати)
    time_changes = []
    for sig in old_by_signature:
        if sig in new_by_signature:
            old_key, old_info = old_by_signature[sig]
            new_key, new_info = new_by_signature[sig]
            
            # Якщо ключі різні (різні дати), але сигнатура та сама - це зміна часу
            if old_key != new_key:
                processed_as_time_change.add(old_key)
                processed_as_time_change.add(new_key)
                time_changes.append((old_info, new_info))
    
    if time_changes:
        messages.append("🕐 <b>Зміна часу аварій:</b>")
        for old_info, new_info in time_changes:
            houses_str = format_houses_list(new_info['houses'])
            messages.append(f"  📋 {new_info['sub_type']}")
            messages.append(f"  🏠 Будинки: {houses_str}")
            
            # Показуємо зміни часу
            if old_info['start_date'] != new_info['start_date']:
                messages.append(f"  🕐 Початок: {old_info['start_date']} → {new_info['start_date']}")
            
            if old_info['end_date'] != new_info['end_date']:
                messages.append(f"  🕐 Очікуване відновлення: {old_info['end_date']} → {new_info['end_date']}")
            
            messages.append("")
    
    # Нові аварії (виключаючи ті, що вже оброблені як зміни часу)
    added_keys = new_keys - old_keys - processed_as_time_change
    if added_keys:
        messages.append("🆕 <b>Нові аварії:</b>")
        for key in added_keys:
            group_info = new_alarms[key]
            houses_str = format_houses_list(group_info['houses'])
            messages.append(f"  📋 {group_info['sub_type']}")
            if group_info['start_date']:
                messages.append(f"  🕐 Початок: {group_info['start_date']}")
            if group_info['end_date']:
                messages.append(f"  🕐 До: {group_info['end_date']}")
            messages.append(f"  🏠 Будинки: {houses_str}")
            messages.append("")
    
    # Усунені аварії (виключаючи ті, що вже оброблені як зміни часу)
    removed_keys = old_keys - new_keys - processed_as_time_change
    if removed_keys:
        messages.append("✅ <b>Усунені аварії:</b>")
        for key in removed_keys:
            group_info = old_alarms[key]
            houses_str = format_houses_list(group_info['houses'])
            messages.append(f"  📋 {group_info['sub_type']}")
            messages.append(f"  🏠 Будинки: {houses_str}")
            messages.append("")
    
    # Зміни в існуючих аваріях (зміна списку будинків при тих самих датах)
    common_keys = old_keys & new_keys
    for key in common_keys:
        # Перетворюємо словники будинків у множини номерів для порівняння
        def get_house_number(house):
            return house['number'] if isinstance(house, dict) else house
        
        old_house_numbers = {get_house_number(h) for h in old_alarms[key]['houses']}
        new_house_numbers = {get_house_number(h) for h in new_alarms[key]['houses']}
        
        if old_house_numbers != new_house_numbers:
            messages.append(f"🔄 <b>Зміни в аварії:</b> {new_alarms[key]['sub_type']}")
            
            added_houses = new_house_numbers - old_house_numbers
            if added_houses:
                # Знаходимо повну інформацію про додані будинки
                added_with_groups = [h for h in new_alarms[key]['houses'] if get_house_number(h) in added_houses]
                added_str = format_houses_list(sorted(added_with_groups, key=lambda x: (not get_house_number(x)[0].isdigit(), get_house_number(x))))
                messages.append(f"  ➕ Додано: {added_str}")
            
            removed_houses = old_house_numbers - new_house_numbers
            if removed_houses:
                # Знаходимо повну інформацію про видалені будинки
                removed_with_groups = [h for h in old_alarms[key]['houses'] if get_house_number(h) in removed_houses]
                removed_str = format_houses_list(sorted(removed_with_groups, key=lambda x: (not get_house_number(x)[0].isdigit(), get_house_number(x))))
                messages.append(f"  ➖ Видалено: {removed_str}")
            
            messages.append("")
    
    if not messages:
        return None
    
    header = [
        "🚨 <b>Зміни в аварійних відключеннях DTEK</b>",
        f"📅 {format_timestamp(timestamp)}\n"
    ]
    
    return "\n".join(header + messages)


def load_previous_state():
    """
    Завантажуємо попередній стан аварій з файлу.
    
    Returns:
        dict: Попередній стан аварій
    """
    previous_alarms = {}
    
    if os.path.exists(DTEK_ALARMS_STATE_FILE):
        try:
            with open(DTEK_ALARMS_STATE_FILE, 'r', encoding='utf-8') as f:
                previous_state = json.load(f)
            
            logger.debug(f"📂 Знайдено файл стану: {DTEK_ALARMS_STATE_FILE}")
            logger.debug(f"   Ключі в файлі: {list(previous_state.keys())}")
            
            # Конвертуємо ключі з попереднього стану (вони збережені як рядки)
            if 'alarms' in previous_state:
                alarm_count = len(previous_state['alarms'])
                logger.debug(f"   Знайдено {alarm_count} аварій у попередньому стані")
                
                for key_str, value in previous_state['alarms'].items():
                    try:
                        # Розпарсюємо ключ назад у tuple
                        key_tuple = eval(key_str)
                        previous_alarms[key_tuple] = value
                        logger.debug(f"   Завантажено аварію: {key_tuple[0][:50]}...")
                    except Exception as e:
                        logger.error(f"   Помилка парсингу ключа '{key_str}': {e}")
            else:
                logger.warning("   У файлі стану немає поля 'alarms'")
                    
        except Exception as e:
            logger.error(f"❌ Помилка читання {DTEK_ALARMS_STATE_FILE}: {e}")
    else:
        logger.debug(f"📂 Файл стану не знайдено: {DTEK_ALARMS_STATE_FILE}")
    
    return previous_alarms


def save_current_state(current_alarms, timestamp):
    """
    Зберігаємо поточний стан аварій у файл.
    
    Args:
        current_alarms: Поточний стан аварій
        timestamp: Час отримання даних
    """
    # Конвертуємо ключі в рядки для JSON
    alarms_for_save = {str(k): v for k, v in current_alarms.items()}
    
    new_state = {
        'timestamp': timestamp,
        'alarms': alarms_for_save
    }
    
    try:
        with open(DTEK_ALARMS_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(new_state, f, ensure_ascii=False, indent=2)
        logger.debug(f"💾 Збережено стан аварій DTEK")
    except Exception as e:
        logger.error(f"❌ Помилка запису {DTEK_ALARMS_STATE_FILE}: {e}")


def process_dtek_alarms_monitoring(config, send_message_callback):
    """
    Моніторинг аварій DTEK.
    Завантажує дані з кількох джерел, порівнює зі збереженим станом, відправляє повідомлення.
    
    Args:
        config: Конфігурація (словник з налаштуваннями)
        send_message_callback: Функція для відправки повідомлень (приймає message, config)
    
    Returns:
        dict: Інформація про аварії {'alarms_groups': dict, 'most_affected_group': str or None}
    """
    logger.info("🔧 Перевірка аварій DTEK")
    
    # Список URL для перевірки
    dtek_urls = [
        config.get('dtek_url', 'https://kit.uca.co.ua/dtek_parsed.json'),
        config.get('dtek_pryladnyj_url', 'https://kit.uca.co.ua/dtek_pryladnyj.json')
    ]
    
    logger.info(f"📡 Перевіряємо {len(dtek_urls)} джерел аварій")
    
    # Об'єднуємо дані з усіх джерел
    all_alarms = {}
    latest_timestamp = None
    
    for idx, url in enumerate(dtek_urls, 1):
        logger.info(f"📡 [{idx}/{len(dtek_urls)}] Завантаження з {url}")
        
        data = load_dtek_alarms_data(url)
        if not data:
            logger.warning(f"⚠️ [{idx}/{len(dtek_urls)}] Не вдалося отримати дані")
            continue
        
        # Отримуємо timestamp
        timestamp = data.get('timestamp', datetime.now().isoformat())
        if not latest_timestamp or timestamp > latest_timestamp:
            latest_timestamp = timestamp
        
        # Обробляємо дані
        logger.debug(f"🔄 [{idx}/{len(dtek_urls)}] Обробка даних...")
        source_alarms = process_dtek_alarms(data)
        logger.info(f"✅ [{idx}/{len(dtek_urls)}] Знайдено {len(source_alarms)} груп аварій")
        
        # Об'єднуємо з загальними результатами
        for key, value in source_alarms.items():
            if key in all_alarms:
                # Додаємо будинки до існуючої групи
                existing_houses = set(all_alarms[key]['houses'])
                new_houses = set(value['houses'])
                all_alarms[key]['houses'] = sorted(list(existing_houses | new_houses), key=lambda x: (not x[0].isdigit(), x))
            else:
                all_alarms[key] = value
    
    if not latest_timestamp:
        logger.warning("❌ Не вдалося отримати дані з жодного джерела")
        return {'alarms_groups': {}, 'most_affected_group': None}
    
    logger.info(f"📅 Timestamp даних: {latest_timestamp}")
    logger.info(f"📊 Всього знайдено {len(all_alarms)} груп аварій")
    
    current_alarms = all_alarms
    timestamp = latest_timestamp
    
    # Аналізуємо групи та знаходимо найбільш ураженну
    most_affected_group = find_most_affected_group(current_alarms)
    
    # Завантажуємо попередній стан
    logger.debug("📂 Завантаження попереднього стану...")
    previous_alarms = load_previous_state()
    logger.debug(f"📊 Попередній стан: {len(previous_alarms)} груп аварій")
    
    # Порівнюємо стани
    if previous_alarms:
        logger.debug("🔍 Порівнюємо стани аварій...")
        message = compare_dtek_alarms(previous_alarms, current_alarms, timestamp)
        if message:
            logger.info("🔔 Виявлено зміни в аваріях DTEK")
            logger.debug(f"📝 Довжина повідомлення: {len(message)} символів")
            send_message_callback(message, config)
        else:
            logger.info("✅ Зміни в аваріях DTEK не виявлено")
    else:
        logger.debug("🆕 Попереднього стану немає (перший запуск)")
        # Перший запуск - просто показуємо поточний стан якщо є аварії
        if current_alarms:
            logger.info(f"🆕 Перший запуск моніторингу аварій DTEK. Поточних аварій: {len(current_alarms)}")
            message = format_dtek_alarms_message(current_alarms, timestamp)
            if message:
                logger.debug(f"📝 Довжина повідомлення: {len(message)} символів")
                send_message_callback(message, config)
        else:
            logger.info("✅ Аварій немає (перший запуск)")
    
    # Зберігаємо поточний стан
    logger.debug(f"💾 Збереження поточного стану ({len(current_alarms)} груп)...")
    save_current_state(current_alarms, timestamp)
    
    return {'alarms_groups': current_alarms, 'most_affected_group': most_affected_group}
    
    logger.info("✅ Перевірка аварій DTEK завершена")
