#!/usr/bin/python3

from datetime import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import time
import requests
from dotenv import load_dotenv

# Завантажуємо змінні з .env файлу
load_dotenv()

# Налаштування логування з ротацією
def setup_logging():
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_file = os.getenv('LOG_FILE', 'yasno_bot.log')
    log_max_size = int(os.getenv('LOG_MAX_SIZE', '10')) * 1024 * 1024  # В байтах
    log_backup_count = int(os.getenv('LOG_BACKUP_COUNT', '5'))
    
    # Створюємо formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Налаштовуємо root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level))
    
    # Очищуємо існуючі handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler з ротацією
    file_handler = RotatingFileHandler(
        log_file, 
        maxBytes=log_max_size, 
        backupCount=log_backup_count,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    return logging.getLogger(__name__)

logger = setup_logging()

STATES_FILE = './states.json'

def load_config():
    """Завантажуємо конфігурацію зі змінних оточення"""
    config = {
        'yasno_url': os.getenv('YASNO_URL', 'https://api.yasno.com.ua/api/v1/pages/home/schedule-turn-off-electricity'),
        'dtek_url': os.getenv('DTEK_URL', 'https://kit.uca.co.ua/dtek_parsed.json'),
        'bot_token': os.getenv('BOT_TOKEN'),
        'chat_id': os.getenv('CHAT_ID'),
        'additional_chat_ids': os.getenv('ADDITIONAL_CHAT_IDS', ''),
        'city': os.getenv('CITY', 'kiev'),
        'group': os.getenv('GROUP', '2'),
        'check_interval': int(os.getenv('CHECK_INTERVAL', '58')),
        'external_api_url': os.getenv('EXTERNAL_API_URL', ''),
        'external_api_token': os.getenv('EXTERNAL_API_TOKEN', '')
    }
    
    # Підготовуємо список всіх чатів
    all_chat_ids = [config['chat_id']]
    if config['additional_chat_ids']:
        # Розділяємо додаткові чати по комах та очищаємо від пробілів
        additional_ids = [chat_id.strip() for chat_id in config['additional_chat_ids'].split(',') if chat_id.strip()]
        all_chat_ids.extend(additional_ids)
    
    config['all_chat_ids'] = all_chat_ids
    
    # Перевіряємо обов'язкові параметри
    if not config['bot_token'] or not config['chat_id']:
        raise ValueError("BOT_TOKEN та CHAT_ID повинні бути встановлені в .env файлі")
    
    logger.info(f"Конфігурація завантажена: місто={config['city']}, група={config['group']}")
    logger.info(f"Чати для відправки: {len(config['all_chat_ids'])} ({', '.join(config['all_chat_ids'])})")
    
    if config['external_api_url']:
        logger.info(f"Зовнішній API увімкнено: {config['external_api_url']}")
    
    return config

def load_state_log(state_file=STATES_FILE):
    if os.path.exists(state_file):
        with open(state_file, "r") as f:
            return json.load(f)
    return {}

def save_state_log(state, state_file=STATES_FILE):
    with open(state_file, "w") as f:
        json.dump(state, f, indent=4)


def load_data(yasno_url, group):
    """Завантажуємо дані з нового API YASNO з обробкою помилок"""
    try:
        logger.debug(f"Запит до API: {yasno_url}")
        response = requests.get(yasno_url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        logger.debug("Отримано відповідь від API")
        logger.debug(f"📋 Розмір відповіді: {len(response.text)} символів")
        logger.debug(f"📊 Структура API відповіді: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}")
        
        # Логуємо частину відповіді для діагностики (обмежуємо розмір)
        response_preview = str(data)
        logger.debug(f"🔍 Відповідь API: {response_preview}")
        
        # Новий API повертає дані безпосередньо з групами як ключами
        if group in data:
            group_data = data[group]
            logger.debug(f"Знайдено дані для групи {group}")
            return group_data
        else:
            logger.warning(f"Дані для групи {group} не знайдено")
            available_groups = list(data.keys())
            logger.info(f"Доступні групи: {available_groups}")
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Помилка при запиті до API: {e}")
        return None
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        logger.error(f"Помилка при обробці відповіді API: {e}")
        return None

def load_dtek_data(dtek_url, group):
    """Завантажуємо дані з ДТЕК API з обробкою помилок"""
    try:
        logger.debug(f"Запит до DTEK API: {dtek_url}")
        response = requests.get(dtek_url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        logger.debug("Отримано відповідь від DTEK API")
        
        # Перевіряємо чи API працює коректно
        if not data.get('ok', False):
            logger.warning("DTEK API повернув ok=false")
            return None
        
        # Витягуємо js_variables.fact
        js_variables = data.get('js_variables', {})
        fact = js_variables.get('fact', {})
        fact_data = fact.get('data', {})
        update_time = fact.get('update', '')
        
        logger.debug(f"DTEK update time: {update_time}")
        logger.debug(f"Доступні дати в DTEK: {list(fact_data.keys())}")
        
        # Конвертуємо групу у формат ДТЕК
        # Якщо group="6.2", то dtek_group="GPV6.2"
        # Якщо group="2", то dtek_group="GPV6.2" (за замовчуванням підгрупа 2)
        if '.' in group:
            # Вже є формат "6.2"
            dtek_group = f"GPV{group}"
        else:
            # Старий формат "2", додаємо 6. перед ним
            dtek_group = f"GPV6.{group}"
        
        logger.debug(f"Шукаємо групу DTEK: {dtek_group}")
        
        result = {
            'data': fact_data,
            'update_time': update_time,
            'group': dtek_group,
            'today_timestamp': fact.get('today', None)
        }
        
        return result
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Помилка при запиті до DTEK API: {e}")
        return None
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        logger.error(f"Помилка при обробці відповіді DTEK API: {e}")
        return None

def convert_dtek_to_yasno_format(dtek_day_data, date_str, dtek_update_time):
    """
    Конвертуємо формат ДТЕК (yes/no/first/second) у формат YASNO.
    Автоматично консолідує суміжні періоди для сумісності з YASNO.
    """
    logger.debug(f"Конвертація DTEK даних для {date_str}")
    
    slots = []
    
    # dtek_day_data - це словник з ключами "1"-"24" та значеннями yes/no/first/second
    for hour_str, status in sorted(dtek_day_data.items(), key=lambda x: int(x[0])):
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
            # Електроенергія є, не додаємо слоти
            logger.debug(f"  Година {hour}: електроенергія є")
            pass
    
    logger.debug(f"📊 ДТЕК: отримано {len(slots)} окремих слотів")
    
    # КОНСОЛІДУЄМО суміжні періоди як це робить YASNO
    # Це важливо для коректного порівняння хешів
    if slots:
        consolidated_slots = consolidate_periods(slots)
        logger.debug(f"📊 ДТЕК: після консолідації {len(consolidated_slots)} періодів")
    else:
        consolidated_slots = []
    
    # Формуємо результат у форматі YASNO
    result = {
        "date": f"{date_str}T00:00:00+02:00",
        "status": "ScheduleApplies",
        "slots": consolidated_slots,  # Використовуємо консолідовані слоти
        "source": "dtek",
        "source_update_time": dtek_update_time
    }
    
    logger.debug(f"✅ Конвертовано ДТЕК → YASNO формат: {len(consolidated_slots)} консолідованих періодів")
    return result

def merge_sources_data(yasno_data, dtek_data, group):
    """
    Об'єднуємо дані з YASNO та DTEK, вибираючи найсвіжіші дані.
    Повертає об'єднану структуру даних та інформацію про джерела оновлень.
    """
    logger.info("🔄 Початок об'єднання даних з YASNO та DTEK")
    
    merged = {}
    source_info = {}  # Для відстеження джерел оновлень
    
    # Якщо ДТЕК недоступний, використовуємо тільки YASNO
    if not dtek_data:
        logger.info("📡 DTEK недоступний, використовуємо тільки YASNO")
        if yasno_data:
            source_info['today'] = {'source': 'yasno', 'update_time': None}
            source_info['tomorrow'] = {'source': 'yasno', 'update_time': None}
        return yasno_data, source_info
    
    # Якщо YASNO недоступний, конвертуємо дані DTEK
    if not yasno_data:
        logger.info("📡 YASNO недоступний, використовуємо тільки DTEK")
        return convert_dtek_to_merged_format(dtek_data, group)
    
    # Обидва джерела доступні - порівнюємо і вибираємо найсвіжіше
    from datetime import datetime
    
    # Отримуємо timestamp з DTEK для сьогодні
    today_timestamp = dtek_data.get('today_timestamp')
    dtek_group = dtek_data.get('group')
    dtek_fact_data = dtek_data.get('data', {})
    dtek_update_time = dtek_data.get('update_time', '')
    
    logger.debug(f"📅 DTEK today_timestamp: {today_timestamp}")
    logger.debug(f"📅 Доступні дати в DTEK: {list(dtek_fact_data.keys())}")
    
    # Перевіряємо чи YASNO має актуальну дату для today
    yasno_today_date = yasno_data.get('today', {}).get('date', '')
    if yasno_today_date:
        yasno_date_only = yasno_today_date.split('T')[0]  # Беремо тільки дату, без часу
        today_actual_date = datetime.now().strftime('%Y-%m-%d')
        
        logger.debug(f"📅 YASNO today date: {yasno_date_only}")
        logger.debug(f"📅 Поточна дата: {today_actual_date}")
        
        if yasno_date_only != today_actual_date:
            logger.warning(f"⚠️ YASNO показує неактуальну дату ({yasno_date_only} != {today_actual_date})")
            logger.info(f"📡 Використовуємо тільки DTEK для today (YASNO застарів)")
            
            # Використовуємо тільки DTEK для today
            if today_timestamp and str(today_timestamp) in dtek_fact_data:
                dtek_today = dtek_fact_data[str(today_timestamp)].get(dtek_group, {})
                if dtek_today:
                    dtek_converted = convert_dtek_to_yasno_format(dtek_today, today_actual_date, dtek_update_time)
                    merged['today'] = dtek_converted
                    source_info['today'] = {'source': 'dtek', 'update_time': dtek_update_time}
                else:
                    logger.warning("⚠️ DTEK немає даних для today")
                    merged['today'] = {}
                    source_info['today'] = {'source': 'none', 'update_time': None}
            else:
                logger.warning("⚠️ DTEK недоступний для today")
                merged['today'] = {}
                source_info['today'] = {'source': 'none', 'update_time': None}
                
            # Tomorrow залишаємо від YASNO (навіть якщо воно застаріле, tomorrow може бути актуальним)
            merged['tomorrow'] = yasno_data.get('tomorrow', {})
            source_info['tomorrow'] = {'source': 'yasno', 'update_time': None}
            
            logger.info(f"✅ Об'єднання завершено: today={source_info['today']['source']}, tomorrow={source_info['tomorrow']['source']}")
            return merged, source_info
    
    # Обробляємо today (якщо YASNO має актуальну дату)
    merged['today'] = yasno_data.get('today', {})
    source_info['today'] = {'source': 'yasno', 'update_time': None}
    
    if today_timestamp and str(today_timestamp) in dtek_fact_data:
        dtek_today = dtek_fact_data[str(today_timestamp)].get(dtek_group, {})
        if dtek_today:
            # Конвертуємо дані DTEK
            today_date = yasno_data.get('today', {}).get('date', '').split('T')[0]
            dtek_converted = convert_dtek_to_yasno_format(dtek_today, today_date, dtek_update_time)
            
            # Порівнюємо хеші розкладів
            yasno_hash = calculate_sum({'today': yasno_data.get('today', {})}, 'today')
            dtek_hash = calculate_sum({'today': dtek_converted}, 'today')
            
            logger.debug(f"🔍 YASNO today hash: {yasno_hash}")
            logger.debug(f"🔍 DTEK today hash: {dtek_hash}")
            
            # Якщо розклади різні, використовуємо DTEK (він оновлюється швидше)
            if yasno_hash != dtek_hash:
                logger.info(f"⚡ DTEK має інший розклад для today - використовуємо його")
                merged['today'] = dtek_converted
                source_info['today'] = {'source': 'dtek', 'update_time': dtek_update_time}
    
    # Обробляємо tomorrow - ЗАВЖДИ використовуємо тільки YASNO (ДТЕК тільки для сьогодні)
    merged['tomorrow'] = yasno_data.get('tomorrow', {})
    source_info['tomorrow'] = {'source': 'yasno', 'update_time': None}
    logger.debug(f"� Tomorrow: завжди використовуємо YASNO (ДТЕК тільки для today)")
    
    logger.info(f"✅ Об'єднання завершено: today={source_info['today']['source']}, tomorrow={source_info['tomorrow']['source']}")
    return merged, source_info

def convert_dtek_to_merged_format(dtek_data, group):
    """
    Конвертуємо дані DTEK у формат YASNO для випадку коли YASNO недоступний.
    ДТЕК використовується ТІЛЬКИ для today, для tomorrow даних не буде.
    """
    merged = {}
    source_info = {}
    
    today_timestamp = dtek_data.get('today_timestamp')
    dtek_group = dtek_data.get('group')
    dtek_fact_data = dtek_data.get('data', {})
    dtek_update_time = dtek_data.get('update_time', '')
    
    from datetime import datetime
    
    # Конвертуємо today з ДТЕК
    if today_timestamp and str(today_timestamp) in dtek_fact_data:
        dtek_today = dtek_fact_data[str(today_timestamp)].get(dtek_group, {})
        if dtek_today:
            today_date = datetime.fromtimestamp(today_timestamp).strftime('%Y-%m-%d')
            merged['today'] = convert_dtek_to_yasno_format(dtek_today, today_date, dtek_update_time)
            source_info['today'] = {'source': 'dtek', 'update_time': dtek_update_time}
    
    # НЕ конвертуємо tomorrow з ДТЕК - ДТЕК тільки для сьогодні
    # Tomorrow буде порожнім або буде взято з YASNO якщо він доступний
    logger.debug("⏩ Tomorrow не конвертується з ДТЕК (ДТЕК тільки для today)")
    
    return merged, source_info

def calculate_sum(day_data, day_key="today"):
    """Обчислюємо хеш для відстеження змін у розкладі для вказаного дня"""
    total_sum = ""
    if day_key not in day_data or "slots" not in day_data[day_key]:
        return ""
    
    # Враховуємо тільки слоти типу "Definite" (планові відключення)
    for slot in day_data[day_key]["slots"]:
        if slot.get("type") == "Definite":
            total_sum += f"{slot['start']}-{slot['end']}"
    
    # Додаємо дату для унікальності
    if "date" in day_data[day_key]:
        total_sum += day_data[day_key]["date"]
    
    return total_sum

def is_changed(day_data, group, day_key="today", source_info=None):
    """Перевіряємо чи змінився розклад відключень для вказаного дня"""
    logger.debug(f"🔍 Перевіряємо зміни для групи {group}, день {day_key}")
    
    states = load_state_log()
    
    # Використовуємо дату як ключ
    if day_key not in day_data or "date" not in day_data[day_key]:
        logger.warning(f"❌ Некоректна структура даних - відсутня інформація про {day_key}/date")
        logger.debug(f"📊 Рішення: повертаємо False (некоректні дані)")
        return False
        
    date_key = day_data[day_key]["date"].split("T")[0]  # Витягуємо тільки дату
    state_key = f"{group}_{date_key}"  # Виключаємо day_key з ключа
    logger.debug(f"🔑 Ключ стану: {state_key}")
    
    current_schedule = calculate_sum(day_data, day_key)
    logger.debug(f"📋 Поточний хеш розкладу: {current_schedule}")
    
    # Зберігаємо джерело оновлення
    source = 'unknown'
    update_time = None
    if source_info and day_key in source_info:
        source = source_info[day_key].get('source', 'unknown')
        update_time = source_info[day_key].get('update_time')
    
    if state_key not in states:
        logger.info(f"🆕 Перший запуск для групи {group} на {date_key}")
        logger.debug(f"💾 Зберігаємо початковий стан: {current_schedule}")
        states[state_key] = current_schedule
        states[f"{state_key}_source"] = source
        if update_time:
            states[f"{state_key}_update_time"] = update_time
        save_state_log(states)
        logger.debug(f"✅ Рішення: повертаємо True (новий розклад)")
        return True
        
    stored_schedule = states[state_key]
    logger.debug(f"🗃️ Збережений хеш розкладу: {stored_schedule}")
    
    if stored_schedule != current_schedule:
        old_source = states.get(f"{state_key}_source", 'unknown')
        logger.info(f"🔄 Виявлено зміну розкладу для групи {group} на {date_key}")
        logger.info(f"📊 Старий хеш: {stored_schedule} (джерело: {old_source})")
        logger.info(f"📊 Новий хеш: {current_schedule} (джерело: {source})")
        logger.debug(f"💾 Оновлюємо збережений стан")
        states[state_key] = current_schedule
        states[f"{state_key}_source"] = source
        if update_time:
            states[f"{state_key}_update_time"] = update_time
        save_state_log(states)
        logger.debug(f"✅ Рішення: повертаємо True (розклад змінився)")
        return True
    
    logger.debug(f"⚪ Розклад не змінився для групи {group} на {date_key}")
    logger.debug(f"❌ Рішення: повертаємо False (без змін)")
    return False

def consolidate_periods(items):
    """Консолідуємо періоди відключень, об'єднуючи суміжні"""
    logger.debug(f"🔧 consolidate_periods: вхідних періодів {len(items)}")
    
    if not items:
        logger.debug("📭 Немає періодів для консолідації")
        return []
    
    # Логуємо вхідні дані
    for i, item in enumerate(items):
        start_time = format_time(item["start"]) if item.get("start") else "N/A"
        end_time = format_time(item["end"]) if item.get("end") else "N/A"
        logger.debug(f"  Вхідний період {i+1}: {start_time} - {end_time} ({item.get('start')}-{item.get('end')})")
        
    # Сортуємо по часу початку
    items.sort(key=lambda x: x["start"])
    logger.debug(f"📊 Періоди відсортовано за часом початку")
    
    consolidated = []
    current_period = items[0].copy()
    logger.debug(f"🚀 Початковий період: {format_time(current_period['start'])} - {format_time(current_period['end'])}")

    for i, item in enumerate(items[1:], 1):
        item_start_time = format_time(item["start"])
        item_end_time = format_time(item["end"])
        current_end_time = format_time(current_period["end"])
        
        logger.debug(f"🔍 Перевіряємо період {i+1}: {item_start_time} - {item_end_time}")
        logger.debug(f"    Поточний кінець: {current_end_time} ({current_period['end']})")
        logger.debug(f"    Новий початок: {item_start_time} ({item['start']})")
        
        if item["start"] <= current_period["end"]:  # Перевіряємо суміжність
            logger.debug(f"    ✅ Об'єднуємо: {item['start']} <= {current_period['end']}")
            # Розширюємо поточний період
            old_end = current_period["end"]
            current_period["end"] = max(current_period["end"], item["end"])
            new_end_time = format_time(current_period["end"])
            logger.debug(f"    📈 Розширено період до: {format_time(current_period['start'])} - {new_end_time}")
        else:
            logger.debug(f"    ➡️ Зберігаємо період та починаємо новий")
            # Зберігаємо завершений період та починаємо новий
            consolidated.append(current_period)
            logger.debug(f"    💾 Збережено: {format_time(current_period['start'])} - {format_time(current_period['end'])}")
            current_period = item.copy()
            logger.debug(f"    🆕 Новий період: {item_start_time} - {item_end_time}")

    # Додаємо останній період
    consolidated.append(current_period)
    logger.debug(f"💾 Збережено останній період: {format_time(current_period['start'])} - {format_time(current_period['end'])}")

    logger.debug(f"✅ Консолідація завершена: {len(items)} → {len(consolidated)} періодів")
    for i, period in enumerate(consolidated):
        start_time = format_time(period["start"])
        end_time = format_time(period["end"])
        logger.debug(f"  Фінальний період {i+1}: {start_time} - {end_time}")

    return consolidated

def extract_definite_slots(day_data, day_key="today"):
    """Витягуємо тільки слоти з типом 'Definite' (планові відключення) для вказаного дня"""
    logger.debug(f"🔍 extract_definite_slots для {day_key}")
    
    if day_key not in day_data or "slots" not in day_data[day_key]:
        logger.debug(f"❌ Немає слотів для {day_key}")
        return []
    
    slots = day_data[day_key]["slots"]
    logger.debug(f"📋 Загальна кількість слотів для {day_key}: {len(slots)}")
    
    definite_slots = []
    for i, slot in enumerate(slots):
        slot_type = slot.get("type", "Unknown")
        start = slot.get("start", "N/A")
        end = slot.get("end", "N/A")
        logger.debug(f"  Слот {i+1}: тип='{slot_type}', {start}-{end}")
        
        if slot_type == "Definite":
            definite_slots.append({
                "start": slot["start"],
                "end": slot["end"]
            })
            logger.debug(f"  ✅ Додано Definite слот: {start}-{end}")
        else:
            logger.debug(f"  ⏩ Пропущено слот типу '{slot_type}'")
    
    logger.debug(f"📊 Знайдено {len(definite_slots)} Definite слотів")
    return definite_slots

def process_day(day_data, group, day_key="today", source_info=None):
    """Формуємо повідомлення про зміни в розкладі відключень для вказаного дня"""
    if day_key not in day_data or "date" not in day_data[day_key]:
        return "Помилка: некоректна структура даних"
        
    date_str = day_data[day_key]["date"].split("T")[0]
    day_label = "сьогодні" if day_key == "today" else "завтра" if day_key == "tomorrow" else day_key
    
    # Визначаємо джерело оновлення
    source = 'невідоме джерело'
    if source_info and day_key in source_info:
        source_name = source_info[day_key].get('source', 'unknown')
        update_time = source_info[day_key].get('update_time')
        
        if source_name == 'yasno':
            source = 'YASNO'
        elif source_name == 'dtek':
            source = f"ДТЕК"
            if update_time:
                source += f" (оновлено {update_time})"
    
    result = f"Оновлення розкладу для групи {group} на {date_str} ({day_label})\nДжерело: {source}"
    
    logger.info(f"Обробка розкладу для групи {group} ({day_key}), джерело: {source}")
    
    # Витягуємо тільки планові відключення
    definite_slots = extract_definite_slots(day_data, day_key)
    
    if not definite_slots:
        result += "\n• Планових відключень немає 🟢"
    else:
        periods = consolidate_periods(definite_slots)
        result += f"\n• Планові відключення ({len(periods)} період{'и' if len(periods) > 1 else ''}):"
        
        for period in periods:
            start_time = format_time(period['start'])
            end_time = format_time(period['end'])
            duration_minutes = period['end'] - period['start']
            duration_str = format_duration(duration_minutes)
            
            if start_time and end_time:
                result += f"\n  ⚡ {start_time} - {end_time} ({duration_str})"
                logger.info(f"Період відключення ({day_key}): {start_time} - {end_time} ({duration_str})")
    
    # Додаємо статус розкладу
    #status = day_data[day_key].get("status", "Unknown")
    #if status == "ScheduleApplies":
    #    result += "\n📋 Статус: розклад діє"
    #elif status == "WaitingForSchedule":
    #    result += "\n⏳ Статус: очікування розкладу"
    #else:
    #    result += f"\n❓ Статус: {status}"
    
    logger.info(f"Сформовано повідомлення ({day_key}): {len(result)} символів")
    return result



def send_to_telegram(message, config):
    """Відправляємо повідомлення в усі налаштовані Telegram чати з обробкою помилок"""
    logger.info(f"Відправка повідомлення у {len(config['all_chat_ids'])} чатів: {message}")
    
    success_count = 0
    total_chats = len(config['all_chat_ids'])
    
    for chat_id in config['all_chat_ids']:
        try:
            logger.debug(f"Відправка в чат {chat_id}")
            url = f"https://api.telegram.org/bot{config['bot_token']}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            response = requests.post(url, data=payload, timeout=30)
            response.raise_for_status()
            success_count += 1
            logger.debug(f"✅ Повідомлення успішно відправлено в чат {chat_id}")
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Помилка при відправці в чат {chat_id}: {e}")
        except Exception as e:
            logger.error(f"❌ Неочікувана помилка при відправці в чат {chat_id}: {e}")
    
    logger.info(f"📊 Результат відправки: {success_count}/{total_chats} чатів отримали повідомлення")
    return success_count > 0  # Повертаємо True якщо хоча б один чат отримав повідомлення

def send_to_external_api(day_data, group, day_key, config):
    """Відправляємо дані на зовнішній API"""
    if not config.get('external_api_url') or not config.get('external_api_token'):
        logger.debug("Зовнішній API не налаштований, пропускаємо відправку")
        return False
    
    if day_key not in day_data:
        logger.warning(f"День {day_key} відсутній в даних для відправки на зовнішній API")
        return False
    
    try:
        # Формуємо дані для відправки відповідно до API
        api_data = {
            "date": day_data[day_key].get("date", ""),
            "group": group,
            "slots": [],
            "status": day_data[day_key].get("status", "Unknown")
        }
        
        # Копіюємо слоти напряму - API вже використовує правильну структуру
        for slot in day_data[day_key].get("slots", []):
            api_data["slots"].append({
                "start": slot.get("start", 0),
                "end": slot.get("end", 0),
                "type": slot.get("type", "NotPlanned")
            })
        
        # Відправляємо запит
        headers = {
            "Authorization": f"Bearer {config['external_api_token']}",
            "Content-Type": "application/json"
        }
        
        logger.debug(f"📤 Відправка даних на зовнішній API для {day_key} ({api_data['date']})")
        logger.debug(f"📊 Дані: {json.dumps(api_data, ensure_ascii=False)}")
        
        response = requests.post(
            config['external_api_url'],
            json=api_data,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        logger.info(f"✅ Дані успішно відправлено на зовнішній API для {day_key} ({api_data['date']})")
        logger.debug(f"📨 Відповідь API: {response.status_code} - {response.text[:200]}")
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Помилка при відправці на зовнішній API для {day_key}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Неочікувана помилка при відправці на зовнішній API для {day_key}: {e}")
        return False

def format_time(minutes_value, minutes_adjustment=0):
    """Конвертуємо хвилини від початку дня у формат HH:MM"""
    try:
        total_minutes = int(minutes_value) + int(minutes_adjustment)
        
        if total_minutes < 0:
            return None
        
        # Обробляємо 24:00 як кінець дня
        if total_minutes >= 1440:  # 1440 = 24*60
            if total_minutes == 1440:
                return "24:00"  # Кінець дня
            else:
                return None  # Більше 24:00 - некоректно

        hours = total_minutes // 60
        minutes = total_minutes % 60
        
        return f"{hours:02d}:{minutes:02d}"
    except (ValueError, TypeError):
        return None  # Handle invalid input

def format_duration(minutes):
    """Форматуємо тривалість у форматі 'Xг Yхв' або 'Yхв'"""
    try:
        total_minutes = int(minutes)
        if total_minutes <= 0:
            return "0хв"
        
        hours = total_minutes // 60
        mins = total_minutes % 60
        
        if hours > 0 and mins > 0:
            return f"{hours}:{mins}"
        elif hours > 0:
            return f"{hours}:00"
        else:
            return f"00:{mins}"
    except (ValueError, TypeError):
        return "??"

def process_alarms(day_data, group):
    """Обробляємо попередження про відключення/відновлення електроенергії"""
    logger.debug(f"🚨 Початок process_alarms для групи {group}")
    
    states = load_state_log()
    current_time = datetime.now()
    current_time_min = current_time.hour * 60 + current_time.minute
    
    logger.debug(f"⏰ Поточний час: {current_time.strftime('%H:%M')} ({current_time_min} хвилин від початку доби)")
    
    # Скидаємо лічильник сповіщень о півночі
    if current_time_min == 0:
        logger.debug("🌙 Північ - скидаємо лічильники сповіщень")
        states["last_send_alarm"] = None
        save_state_log(states)
        return None
    
    # Перевіряємо чи не надсилали сповіщення цієї години цього дня
    current_date = current_time.strftime('%Y-%m-%d')
    alarm_key = f"last_alarm_{group}_{current_date}_{current_time.hour}"
    logger.debug(f"🔑 Ключ сповіщення: {alarm_key}")
    
    if alarm_key in states:
        logger.debug(f"🔕 Сповіщення вже надсилалось {current_date} о {current_time.hour}:XX")
        logger.debug(f"📋 Збережено: {states[alarm_key]}")
        return None
    
    # Витягуємо планові відключення
    definite_slots = extract_definite_slots(day_data)
    logger.debug(f"📋 Знайдено слотів відключення: {len(definite_slots) if definite_slots else 0}")
    
    if not definite_slots:
        logger.debug("❌ Немає планових відключень для обробки")
        return None
    
    periods = consolidate_periods(definite_slots)
    logger.debug(f"📊 Консолідовано періодів: {len(periods)}")
    
    # Перевіряємо чи є кросс-день період (сьогодні до 24:00 → завтра з 00:00)
    has_cross_day = is_cross_day_continuation(day_data)
    
    for i, period in enumerate(periods):
        start_minutes = period['start']
        end_minutes = period['end']
        
        # ПРОПУСКАЄМО період, що починається о 00:00, якщо він є продовженням вчорашнього
        if start_minutes == 0 and has_cross_day:
            logger.debug(f"⏭️ Пропускаємо період {i+1} (00:00-{format_time(end_minutes)}) - продовження кросс-день періоду")
            continue
        
        logger.debug(f"🔍 Період {i+1}: {format_time(start_minutes)} - {format_time(end_minutes)} ({start_minutes}-{end_minutes} хв)")
        
        # Попередження за 30 хвилин до відключення
        start_warning_time = start_minutes - 30
        logger.debug(f"⚠️ Попередження про відключення: {format_time(start_warning_time)} - {format_time(start_warning_time + 30)} ({start_warning_time}-{start_warning_time + 30} хв)")
        logger.debug(f"🔢 Перевірка: {start_warning_time} <= {current_time_min} < {start_warning_time + 30} = {start_warning_time <= current_time_min < start_warning_time + 30}")
        
        if (start_warning_time <= current_time_min < start_warning_time + 30):
            logger.info(f"🔴 ТРИГЕР: Попередження про відключення!")
            states[alarm_key] = current_time.isoformat()
            save_state_log(states)
            start_time = format_time(start_minutes)
            
            # Якщо період закінчується о 24:00 і продовжується завтра, показуємо реальний час відновлення
            if end_minutes == 1440 and has_cross_day and "tomorrow" in day_data:
                tomorrow_definite = [s for s in day_data["tomorrow"]["slots"] if s.get("type") == "Definite"]
                if tomorrow_definite:
                    tomorrow_periods = consolidate_periods(tomorrow_definite)
                    if tomorrow_periods and tomorrow_periods[0]['start'] == 0:
                        real_end = tomorrow_periods[0]['end']
                        end_time = f"завтра о {format_time(real_end - 30)}"
                        logger.debug(f"🌉 Кросс-день: відновлення завтра о {format_time(real_end)}")
                    else:
                        end_time = format_time(end_minutes, -30)
                else:
                    end_time = format_time(end_minutes, -30)
            else:
                end_time = format_time(end_minutes, -30)
            
            return f"🔴 Попередження: відключення о {start_time}\nОчікуване відновлення: {end_time}"
        
        # Повідомлення про ймовірне відновлення за 1 годину до кінця
        # Для періодів, що закінчуються о 24:00 і продовжуються завтра, НЕ надсилаємо попередження
        if end_minutes == 1440 and has_cross_day:
            logger.debug(f"⏭️ Пропускаємо попередження про відновлення для кросс-день періоду (24:00)")
            continue
        
        end_warning_time = end_minutes - 60
        logger.debug(f"⚡ Попередження про відновлення: {format_time(end_warning_time)} - {format_time(end_warning_time + 30)} ({end_warning_time}-{end_warning_time + 30} хв)")
        logger.debug(f"🔢 Перевірка: {end_warning_time} <= {current_time_min} < {end_warning_time + 30} = {end_warning_time <= current_time_min < end_warning_time + 30}")
        
        if (end_warning_time <= current_time_min < end_warning_time + 30):
            logger.info(f"🟢 ТРИГЕР: Попередження про відновлення!")
            states[alarm_key] = current_time.isoformat()
            save_state_log(states)
            end_time_start = format_time(end_minutes, -30)
            end_time_end   = format_time(end_minutes,   0)
            return f"🟢 Очікується відновлення електроенергії з {end_time_start} по {end_time_end}"

    logger.debug("✅ process_alarms завершено - жодних попереджень не потрібно")
    return None

def is_cross_day_continuation(day_data):
    """Перевіряємо чи є періоди, що продовжуються з сьогодні на завтра (23:00-24:00 → 00:00-XX:XX)"""
    # Перевіряємо чи є сьогодні період, що закінчується о 24:00
    if "today" not in day_data or "tomorrow" not in day_data:
        return False
    
    # Отримуємо слоти для сьогодні
    today_definite = []
    if "slots" in day_data["today"]:
        today_definite = [s for s in day_data["today"]["slots"] if s.get("type") == "Definite"]
    
    # Отримуємо слоти для завтра
    tomorrow_definite = []
    if "slots" in day_data["tomorrow"]:
        tomorrow_definite = [s for s in day_data["tomorrow"]["slots"] if s.get("type") == "Definite"]
    
    if not today_definite or not tomorrow_definite:
        return False
    
    # Перевіряємо останній період сьогодні
    today_periods = consolidate_periods(today_definite)
    if not today_periods:
        return False
    
    last_today = today_periods[-1]
    
    # Перевіряємо перший період завтра
    tomorrow_periods = consolidate_periods(tomorrow_definite)
    if not tomorrow_periods:
        return False
    
    first_tomorrow = tomorrow_periods[0]
    
    # Якщо останній період сьогодні закінчується о 24:00 (1440)
    # і перший період завтра починається о 00:00 (0)
    # то це кросс-день період
    is_cross_day = (last_today['end'] == 1440 and first_tomorrow['start'] == 0)
    
    if is_cross_day:
        logger.debug(f"🌉 Виявлено кросс-день період: сьогодні до 24:00, завтра з 00:00")
    
    return is_cross_day

def should_process_day(data, day_key):
    """Перевіряємо чи потрібно обробляти день (тільки якщо статус 'ScheduleApplies')"""
    logger.debug(f"🔍 Перевіряємо чи обробляти день {day_key}")
    
    if day_key not in data:
        logger.debug(f"❌ День {day_key} відсутній в даних")
        logger.debug(f"📊 Рішення: НЕ обробляти (дані відсутні)")
        return False
    
    status = data[day_key].get("status", "Unknown")
    logger.debug(f"📋 Статус дня {day_key}: '{status}'")
    
    if status == "ScheduleApplies":
        logger.debug(f"✅ Розклад діє для {day_key}")
        logger.debug(f"📊 Рішення: ОБРОБЛЯТИ день {day_key}")
        return True
    elif status == "WaitingForSchedule":
        logger.debug(f"⏳ Очікування розкладу для {day_key}")
        logger.debug(f"📊 Рішення: НЕ обробляти {day_key} (статус 'WaitingForSchedule')")
        return False
    else:
        logger.warning(f"❓ Невідомий статус для {day_key}: '{status}'")
        logger.debug(f"📊 Рішення: НЕ обробляти {day_key} (невідомий статус)")
        return False

def process_yasno(config):
    """Основна функція обробки даних від YASNO та ДТЕК"""
    logger.info("=" * 60)
    logger.info("🔄 Початок перевірки оновлень")
    
    # Завантажуємо дані з обох джерел
    yasno_data = load_data(config["yasno_url"], config["group"])
    dtek_data = load_dtek_data(config["dtek_url"], config["group"])
    
    if not yasno_data and not dtek_data:
        logger.warning("❌ Не вдалося отримати дані від жодного API")
        return None
    
    # Об'єднуємо дані з обох джерел
    data, source_info = merge_sources_data(yasno_data, dtek_data, config["group"])
    
    if not data:
        logger.warning("❌ Після об'єднання даних немає")
        return None
    
    logger.debug(f"✅ Отримано об'єднані дані для групи {config['group']}")
    logger.debug(f"📊 Джерела: today={source_info.get('today', {}).get('source', 'N/A')}, tomorrow={source_info.get('tomorrow', {}).get('source', 'N/A')}")
    
    # Перевіряємо зміни в розкладі для сьогодні (тільки якщо розклад діє)
    if should_process_day(data, "today") and is_changed(data, config["group"], "today", source_info):
        message = process_day(data, config["group"], "today", source_info)
        send_to_telegram(message, config)
        send_to_external_api(data, config["group"], "today", config)
        logger.info("✅ Відправлено повідомлення про зміни в розкладі (today)")
    
    # Перевіряємо зміни в розкладі для завтра (тільки якщо розклад діє)
    if should_process_day(data, "tomorrow") and is_changed(data, config["group"], "tomorrow", source_info):
        message = process_day(data, config["group"], "tomorrow", source_info)
        send_to_telegram(message, config)
        send_to_external_api(data, config["group"], "tomorrow", config)
        logger.info("✅ Відправлено повідомлення про зміни в розкладі (tomorrow)")
    
    # Перевіряємо попередження про відключення (тільки для сьогодні і тільки якщо розклад діє)
    if should_process_day(data, "today"):
        logger.debug("🚨 Викликаємо process_alarms для today")
        alarm_message = process_alarms(data, config["group"])
        if alarm_message:
            logger.info(f"📱 Отримано повідомлення попередження: {alarm_message}")
            send_to_telegram(alarm_message, config)
            logger.info("✅ Відправлено попередження про відключення")
        else:
            logger.debug("🔕 process_alarms повернув None - попереджень немає")
    else:
        logger.debug("⏩ Пропускаємо process_alarms - today не потребує обробки")
    
    logger.info("✅ Перевірка завершена")
    logger.info("=" * 60)

def main():
    try:
        config = load_config()
        logger.info("Запуск yasno_check_updates бота...")
        
        #while True:
        process_yasno(config)
        #    time.sleep(config['check_interval'])
    except KeyboardInterrupt:
        logger.info("Зупинка роботи за запитом користувача...")
    except Exception as e:
        logger.error(f"Критична помилка: {e}", exc_info=True)
        raise

if __name__ == '__main__':
    main()
