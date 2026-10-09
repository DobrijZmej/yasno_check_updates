#!/usr/bin/python3
"""
Головний файл бота для моніторингу планових відключень електроенергії.
Використовує модульну архітектуру з датами замість today/tomorrow.
"""

from datetime import datetime, timedelta
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import time
from dotenv import load_dotenv

# Імпортуємо наші модулі
from api_clients import load_yasno_data, load_dtek_data
from data_processor import merge_sources_data
from state_manager import load_state_log, save_state_log, is_changed, update_state, cleanup_old_states, get_old_periods
from notifiers import send_to_telegram, send_to_external_api, process_day, extract_definite_slots, consolidate_periods, send_dtek_alarms_to_telegram
from alarms import process_alarms
from dtek_alarms import process_dtek_alarms_monitoring
from standart_schedule_loader import load_standard_schedule_data
from dtek_fact_loader import load_dtek_fact_data

# Завантажуємо змінні з .env файлу
load_dotenv()


def setup_logging():
    """Налаштування логування з ротацією"""
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
        'dtek_pryladnyj_url': os.getenv('DTEK_PRYLADNYJ_URL', 'https://kit.uca.co.ua/dtek_pryladnyj.json'),
        'bot_token': os.getenv('BOT_TOKEN'),
        'chat_id': os.getenv('CHAT_ID'),
        'additional_chat_ids': os.getenv('ADDITIONAL_CHAT_IDS', ''),
        'dtek_alarms_chat_id': os.getenv('DTEK_ALARMS_CHAT_ID', ''),
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
    
    if config['dtek_alarms_chat_id']:
        logger.info(f"Окремий чат для аварій DTEK: {config['dtek_alarms_chat_id']}")
    
    if config['external_api_url']:
        logger.info(f"Зовнішній API увімкнено: {config['external_api_url']}")
    
    return config


def process_yasno(config):
    """
    Головна функція обробки даних.
    Завантажує дані, порівнює зі збереженим станом, відправляє повідомлення.
    """
    logger.info("="*60)
    logger.info("🚀 Початок перевірки розкладу")
    logger.info(f"⏰ Поточний час: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    group = config['group']
    
    # 1. Завантажуємо дані з усіх джерел
    logger.info("📡 Завантаження даних з API...")
    yasno_data = load_yasno_data(config['yasno_url'], group)
    dtek_data = load_dtek_data(config['dtek_url'], group)
    
    # Завантажуємо стандартний розклад (як резервне джерело)
    logger.info("📋 Завантаження стандартного розкладу...")
    standard_data = load_standard_schedule_data()
    
    # Завантажуємо графік з DTEK Fact (найвищий пріоритет)
    logger.info("🔧 Завантаження графіка з DTEK Fact...")
    dtek_fact_data = load_dtek_fact_data(config['dtek_pryladnyj_url'], group)
    
    # 2. Об'єднуємо дані з усіх джерел
    merged_data, source_info = merge_sources_data(yasno_data, dtek_data, standard_data, dtek_fact_data)
    
    if not merged_data:
        logger.warning("❌ Не вдалося отримати дані з жодного джерела")
        return
    
    # 3. Визначаємо які дати нам потрібні
    today_date = datetime.now().strftime('%Y-%m-%d')
    tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    
    logger.info(f"📅 Обробка дат: {today_date} (сьогодні), {tomorrow_date} (завтра)")
    
    # 4. Завантажуємо поточний стан
    states = load_state_log(STATES_FILE)
    
    # 5. Обробляємо кожну дату
    dates_to_process = [
        (today_date, "сьогодні"),
        (tomorrow_date, "завтра")
    ]
    
    for date_str, day_label in dates_to_process:
        if date_str not in merged_data:
            logger.warning(f"⚠️ Немає даних для {date_str}")
            continue
        
        day_data = merged_data[date_str]
        day_source_info = source_info.get(date_str, {})
        
        # Перевіряємо статус розкладу
        schedule_status = day_data.get('status', '')
        if schedule_status == 'WaitingForSchedule':
            logger.info(f"⏳ Розклад для {date_str} ({day_label}) ще не опублікований - пропускаємо")
            continue
        if schedule_status == 'EmergencyShutdowns':
            logger.info(f"⏳ Розклад для {date_str} ({day_label}) аварійний - пропускаємо")
            continue
        
        # Перевіряємо чи змінився розклад
        source_name = day_source_info.get('source', '')
        changed, old_hash, new_hash = is_changed(group, date_str, day_data, states, source_name)
        
        if changed:
            logger.info(f"🔔 Розклад змінився для {date_str} ({day_label})")
            
            # Витягуємо та консолідуємо періоди відключень
            definite_slots = extract_definite_slots(day_data)
            consolidated_periods = consolidate_periods(definite_slots) if definite_slots else []
            
            # Отримуємо попередній розклад для порівняння
            old_periods = get_old_periods(group, date_str, states)
            
            # Формуємо та відправляємо повідомлення
            message = process_day(date_str, day_data, group, day_label, day_source_info, old_periods=old_periods)
            
            # Відправляємо в Telegram
            send_to_telegram(message, config)
            
            # Відправляємо на зовнішній API
            send_to_external_api(date_str, day_data, group, config)
            
            # Оновлюємо стан зі збереженням періодів
            update_state(group, date_str, new_hash, states, periods=consolidated_periods)
            
            # Зберігаємо update_time якщо є
            update_time = day_source_info.get('update_time')
            if update_time:
                update_time_key = f"{group}_{date_str}_update_time"
                states[update_time_key] = update_time
        else:
            logger.info(f"✅ Розклад не змінився для {date_str} ({day_label})")
    
    # 6. Обробляємо попередження про відключення/відновлення
    states = process_alarms(merged_data, group, config, states, source_info)
    
    # 7. Очищуємо старі записи зі стану (старші 7 днів)
    states = cleanup_old_states(states, days_to_keep=7)
    
    # 8. Зберігаємо оновлений стан
    save_state_log(states, STATES_FILE)
    
    logger.info("✅ Перевірка завершена")
    logger.info("="*60)


def main():
    """Головна функція програми"""
    try:
        # Завантажуємо конфігурацію
        config = load_config()
        
        logger.info("🤖 Бот запущено")
        logger.info(f"⏱️ Інтервал перевірки: {config['check_interval']} секунд")
        
        # Завантажуємо states для перевірки попередньої групи
        states = load_state_log(STATES_FILE)
        previous_monitoring_group = states.get('last_monitoring_group', None)
        
        # Головний цикл
        #while True:
        try:
            # 1. Спочатку аналізуємо аварії DTEK для визначення найбільш ураженої групи
            logger.info("=" * 60)
            logger.info("🔍 КРОК 1: Аналіз аварій DTEK")
            logger.info("=" * 60)
            
            dtek_result = process_dtek_alarms_monitoring(config, send_dtek_alarms_to_telegram)
            
            # 2. Визначаємо яку групу використовувати для моніторингу розкладу
            original_group = config['group']
            group_changed = False
            
            if dtek_result and dtek_result.get('most_affected_group'):
                monitoring_group = dtek_result['most_affected_group']
                logger.info(f"🎯 Використовуємо групу з найбільшою кількістю аварій: {monitoring_group} (замість {original_group} з .env)")
                
                # Перевіряємо чи змінилась група
                if previous_monitoring_group and previous_monitoring_group != monitoring_group:
                    logger.warning(f"⚠️ ЗМІНА ГРУПИ! Попередня: {previous_monitoring_group}, Поточна: {monitoring_group}")
                    group_changed = True
                
                # Оновлюємо конфігурацію
                config['group'] = monitoring_group
            else:
                monitoring_group = original_group
                logger.info(f"📌 Використовуємо групу з .env: {monitoring_group}")
                
                # Перевіряємо чи змінилась група
                if previous_monitoring_group and previous_monitoring_group != monitoring_group:
                    logger.warning(f"⚠️ ЗМІНА ГРУПИ! Попередня: {previous_monitoring_group}, Поточна: {monitoring_group} (повернення до .env)")
                    group_changed = True
            
            # 3. Якщо група змінилась - очищаємо хеші для обох груп щоб графіки відправились
            if group_changed:
                logger.info(f"🔄 Очищення збережених хешів через зміну групи")
                states = load_state_log(STATES_FILE)
                
                # Видаляємо хеші для обох груп (попередньої та нової)
                today_date = datetime.now().strftime('%Y-%m-%d')
                tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
                
                groups_to_clear = [monitoring_group]
                if previous_monitoring_group:
                    groups_to_clear.append(previous_monitoring_group)
                
                for group_to_clear in groups_to_clear:
                    logger.info(f"   Очищення хешів для групи {group_to_clear}")
                    for date_str in [today_date, tomorrow_date]:
                        hash_key = f"{group_to_clear}_{date_str}"
                        periods_key = f"{group_to_clear}_{date_str}_periods"
                        
                        if hash_key in states:
                            logger.info(f"      Видалено хеш {hash_key}")
                            del states[hash_key]
                        
                        if periods_key in states:
                            logger.info(f"      Видалено періоди {periods_key}")
                            del states[periods_key]
                
                # Зберігаємо оновлений стан
                save_state_log(states, STATES_FILE)
            
            # Зберігаємо поточну групу для наступної перевірки
            states = load_state_log(STATES_FILE)
            states['last_monitoring_group'] = monitoring_group
            save_state_log(states, STATES_FILE)
            
            # 4. Обробляємо розклад планових відключень для визначеної групи
            logger.info("=" * 60)
            logger.info(f"🔍 КРОК 2: Перевірка розкладу для групи {monitoring_group}")
            logger.info("=" * 60)
            
            process_yasno(config)
            
        except Exception as e:
            logger.error(f"❌ Помилка в циклі обробки: {e}", exc_info=True)
        
        # Чекаємо до наступної перевірки
        #logger.info(f"😴 Очікування {config['check_interval']} секунд до наступної перевірки...")
        #time.sleep(config['check_interval'])
            
    except KeyboardInterrupt:
        logger.info("⛔ Отримано сигнал зупинки (Ctrl+C)")
    except Exception as e:
        logger.error(f"💥 Критична помилка: {e}", exc_info=True)
    finally:
        logger.info("👋 Бот зупинено")


if __name__ == "__main__":
    main()
