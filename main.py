"""
Основний модуль для моніторингу розкладу електропостачання.

Архітектура:
1. Отримання графіків і режимів з вибраного вручну джерела; аварії обробляються окремо
2. Об'єднання даних з пріоритетами
3. Формування правил відправки
4. Відправка повідомлень

Графіки: DTEK для адреси має пріоритет над графіками груп YASNO.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Імпорти з модулів
from modules.data_sources.svitlo_monitor_loader import load_svitlo_monitor_data
from modules.data_sources.yasno_loader import load_yasno_data
from modules.data_sources.dtek_schedule_loader import load_dtek_schedule_data
from modules.data_sources.dtek_fact_loader import load_dtek_fact_data
from modules.data_sources.group_detector import find_most_affected_group
from modules.data_sources.alarms_loader import load_dtek_alarms, process_dtek_alarms, find_priority_house_group

from modules.processing.data_merger import merge_data_sources
from modules.processing.state_manager import (
    load_state, save_state, is_changed, update_state, 
    cleanup_old_states, clear_hash_for_date,
    calculate_outage_duration, get_stored_schedule_slots,
    normalize_schedule_slots,
)

from modules.notification.rules import (
    should_send_schedule, should_send_alarm, 
    format_date_label
)
from modules.notification.notifier import (
    format_schedule_message, format_alarm_message,
    send_telegram_message, send_to_multiple_chats
)
from modules.notification.external_api import send_to_external_api
from modules.notification.hourly_notifications import check_upcoming_events
from modules.processing.state_manager import StateManager as StateManagerClass
from modules.processing.mode_history import advance_mode_history, format_mode_transition

# Налаштування логування
logger = logging.getLogger(__name__)

SCHEDULE_SOURCES = {"unified", "legacy"}


def setup_logging():
    """Налаштовує логування"""
    log_handler = RotatingFileHandler(
        'yasno_bot.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    log_handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(log_handler)
    
    # Консольний вивід
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    root_logger.addHandler(console)


def load_config():
    """Завантажує конфігурацію з .env"""
    load_dotenv()
    
    config = {
        'group': os.getenv('GROUP', '8.1'),
        'schedule_source': os.getenv('SCHEDULE_SOURCE', 'unified').strip().lower(),
        'use_dynamic_group': os.getenv('USE_DYNAMIC_GROUP', 'false').lower() in ('true', '1', 'yes'),
        'enable_hourly_notifications': os.getenv('ENABLE_HOURLY_NOTIFICATIONS', 'true').lower() in ('true', '1', 'yes'),
        'enable_alarm_notifications': os.getenv('ENABLE_ALARM_NOTIFICATIONS', 'true').lower() in ('true', '1', 'yes'),
        'enable_mode_notifications': os.getenv('ENABLE_MODE_NOTIFICATIONS', 'true').lower() in ('true', '1', 'yes'),
        'svitlo_monitor_url': os.getenv('SVITLO_MONITOR_URL', 'https://kit.uca.co.ua/svitlo_monitor_response.json'),
        'yasno_url': os.getenv('YASNO_URL', 'https://app.yasno.ua/api/blackout-service/public/shutdowns/regions/25/dsos/902/planned-outages'),
        'dtek_url': os.getenv('DTEK_URL', 'https://kit.uca.co.ua/dtek_parsed.json'),
        'dtek_alarms_url': os.getenv('DTEK_PRYLADNYJ_URL', 'https://kit.uca.co.ua/dtek_pryladnyj.json'),
        'telegram_bot_token': os.getenv('BOT_TOKEN'),
        'telegram_chat_id': os.getenv('CHAT_ID'),
        'additional_chat_ids': os.getenv('ADDITIONAL_CHAT_IDS', ''),
        'dtek_alarms_chat_id': os.getenv('DTEK_ALARMS_CHAT_ID', ''),
        'external_api_url': os.getenv('EXTERNAL_API_URL', ''),
        'external_api_token': os.getenv('EXTERNAL_API_TOKEN', '')
    }
    
    return config


def load_schedule_sources(config, group):
    """Load schedules from the explicitly selected source.

    There is intentionally no automatic fallback: switching back to the old
    APIs requires setting SCHEDULE_SOURCE=legacy.
    """
    source = config['schedule_source']
    if source not in SCHEDULE_SOURCES:
        raise ValueError(
            f"Unsupported SCHEDULE_SOURCE={source!r}; expected unified or legacy"
        )

    if source == 'unified':
        unified_data = load_svitlo_monitor_data(config['svitlo_monitor_url'], group)
        if not unified_data:
            return None, None, None, {}
        return (
            unified_data['yasno_data'],
            unified_data['dtek_schedule_data'],
            None,
            unified_data['mode_data'],
        )

    logger.warning("⚠️ Увімкнено ручний legacy-режим джерел графіка")
    return (
        load_yasno_data(config['yasno_url'], group),
        load_dtek_schedule_data(config['dtek_url'], group),
        load_dtek_fact_data(config['dtek_alarms_url'], group),
        {},
    )


def main():
    """Головна функція"""
    setup_logging()
    logger.info("=" * 60)
    logger.info("🚀 Запуск моніторингу розкладу електропостачання")
    logger.info("=" * 60)
    
    # Завантаження конфігурації
    config = load_config()
    monitoring_group = config['group']
    use_dynamic_group = config['use_dynamic_group']

    if config['schedule_source'] not in SCHEDULE_SOURCES:
        logger.error(
            "❌ Невідоме SCHEDULE_SOURCE=%s; дозволено unified або legacy",
            config['schedule_source'],
        )
        return
    
    logger.info(f"⚙️ Група за замовчуванням: {monitoring_group}")
    logger.info(f"📡 Джерело графіків: {config['schedule_source'].upper()}")
    logger.info(f"🔄 Динамічне визначення групи: {'Увімкнено' if use_dynamic_group else 'Вимкнено'}")
    logger.info(f"⏰ Попередження за годину: {'Увімкнено' if config['enable_hourly_notifications'] else 'Вимкнено'}")
    logger.info(f"🚨 Сповіщення про аварії: {'Увімкнено' if config['enable_alarm_notifications'] else 'Вимкнено'}")
    logger.info(f"🔄 Сповіщення про режими: {'Увімкнено' if config['enable_mode_notifications'] else 'Вимкнено'}")
    
    # Підготовка списків чатів
    schedule_chat_ids = []
    if config.get('telegram_chat_id'):
        schedule_chat_ids.append(config['telegram_chat_id'])
    
    if config.get('additional_chat_ids'):
        additional_ids = [chat_id.strip() for chat_id in config['additional_chat_ids'].split(',') if chat_id.strip()]
        schedule_chat_ids.extend(additional_ids)
        logger.info(f"📱 Додаткові чати для розкладу: {len(additional_ids)}")
    
    alarm_chat_ids = []
    if config.get('dtek_alarms_chat_id'):
        alarm_chat_ids.append(config['dtek_alarms_chat_id'])
        logger.info(f"🚨 Окремий чат для аварій DTEK: {config['dtek_alarms_chat_id']}")
    
    # Визначаємо чи є налаштовані чати
    has_schedule_chats = len(schedule_chat_ids) > 0
    has_alarm_chats = len(alarm_chat_ids) > 0
    
    # Перевірка зовнішнього API
    external_api_enabled = bool(config.get('external_api_url') and config.get('external_api_token'))
    if external_api_enabled:
        logger.info(f"🌐 Зовнішній API увімкнено: {config['external_api_url']}")
    
    # Завантаження стану
    state = load_state()
    previous_monitoring_group = state.get('last_monitoring_group', monitoring_group)
    group_changed = False
    group_change_info = None
    
    # === КРОК 1: Отримання даних ===
    logger.info("")
    logger.info("=" * 60)
    logger.info("📡 КРОК 1: Завантаження даних з джерел")
    logger.info("=" * 60)
    
    # 1.1. Аварії DTEK та визначення групи
    logger.info("")
    logger.info("🚨 1.1. Завантаження аварій DTEK...")
    dtek_alarms_data = load_dtek_alarms(config['dtek_alarms_url'])
    alarms_groups = process_dtek_alarms(dtek_alarms_data) if dtek_alarms_data else {}
    
    # Динамічне визначення групи (якщо увімкнено)
    if use_dynamic_group:
        # Спочатку шукаємо пріоритетні будинки (незалежно від аварій)
        priority_group = find_priority_house_group(dtek_alarms_data) if dtek_alarms_data else None
        
        if priority_group:
            # Знайдено пріоритетний будинок - використовуємо його групу
            monitoring_group = priority_group
            logger.info(f"✅ Використовуємо групу пріоритетного будинку: {monitoring_group}")
        else:
            # Пріоритетних будинків немає, шукаємо групу з найбільшою кількістю будинків з аваріями
            detected_group = find_most_affected_group(alarms_groups)
            if detected_group:
                monitoring_group = detected_group
                logger.info(f"✅ Використовуємо групу з аварій: {monitoring_group}")
            else:
                logger.info(f"ℹ️ Аварій немає, використовуємо групу з .env: {monitoring_group}")
    else:
        logger.info(f"ℹ️ Динамічне визначення вимкнено, використовуємо групу з .env: {monitoring_group}")
    
    # Перевірка зміни групи
    if monitoring_group != previous_monitoring_group:
        logger.warning(f"⚠️ ЗМІНА ГРУПИ! Попередня: {previous_monitoring_group}, Поточна: {monitoring_group}")
        
        group_changed = True
        group_change_info = {
            'previous': previous_monitoring_group,
            'current': monitoring_group
        }
        
        today = datetime.now().strftime('%Y-%m-%d')
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Очищаємо хеші для ОБОХ груп
        for date_str in [today, tomorrow]:
            clear_hash_for_date(previous_monitoring_group, date_str, state)
            clear_hash_for_date(monitoring_group, date_str, state)
        
        state['last_monitoring_group'] = monitoring_group
        save_state(state)
    
    # 1.2. Вибране вручну джерело графіків і режимів
    logger.info("")
    logger.info("📊 1.2. Завантаження даних у режимі %s...", config['schedule_source'])
    yasno_data, dtek_schedule_data, dtek_fact_data, mode_data = load_schedule_sources(
        config,
        monitoring_group,
    )

    mode_state, mode_transitions = advance_mode_history(
        mode_data,
        state.get('mode_history')
    )
    if mode_transitions and config['enable_mode_notifications'] and has_schedule_chats:
        for transition in mode_transitions:
            logger.info(
                "🔄 Перехід режиму %s: %s → %s (подія: %s)",
                transition['provider'],
                transition['previous_status'],
                transition['status'],
                transition['changed_at'].isoformat(),
            )
        mode_message = "\n\n".join(
            format_mode_transition(transition) for transition in mode_transitions
        )
        logger.info("📨 Повідомлення про зміну режиму:\n%s", mode_message)
        sent_count = send_to_multiple_chats(
            config['telegram_bot_token'],
            schedule_chat_ids,
            mode_message
        )
        if sent_count:
            state['mode_history'] = mode_state
            logger.info(f"✅ Сповіщення про режими відправлено в {sent_count}/{len(schedule_chat_ids)} чат(ів)")
        else:
            logger.error("❌ Сповіщення про режими не відправлено; переходи буде повторено")
    else:
        state['mode_history'] = mode_state
        if mode_transitions and not config['enable_mode_notifications']:
            logger.info("⏭️ Сповіщення про режими вимкнені")
        elif mode_transitions and not has_schedule_chats:
            logger.warning("⚠️ Немає чатів для сповіщень про режими")
    
    # === КРОК 2: Об'єднання даних ===
    logger.info("")
    logger.info("=" * 60)
    logger.info("🔀 КРОК 2: Об'єднання даних з пріоритетами")
    logger.info("=" * 60)
    
    merged_data, source_info = merge_data_sources(
        yasno_data,
        dtek_schedule_data,
        dtek_fact_data
    )
    
    # === КРОК 2.5: Перевірка майбутніх подій (попередження) ===
    if config['enable_hourly_notifications'] and has_schedule_chats:
        logger.info("")
        logger.info("=" * 60)
        logger.info("⏰ КРОК 2.5: Перевірка майбутніх подій (попередження)")
        logger.info("=" * 60)
        
        # Показуємо які дані використовуємо
        today_date = datetime.now().strftime('%Y-%m-%d')
        tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        
        if today_date in merged_data:
            today_source = source_info.get(today_date, {}).get('source', 'невідомо')
            logger.info(f"📊 Перевірка попереджень для групи {monitoring_group}")
            logger.info(f"📅 Джерело даних для сьогодні ({today_date}): {today_source.upper()}")
        else:
            logger.warning(f"⚠️ Немає даних для сьогодні ({today_date}) - попередження неможливі")
        
        # Трансформуємо merged_data для функції check_upcoming_events
        # Вона очікує формат {'today': {...}, 'tomorrow': {...}}
        events_data = {
            'today': merged_data.get(today_date),
            'tomorrow': merged_data.get(tomorrow_date)
        }
        
        # Використовуємо основний state для відстеження відправлених попереджень
        # Створюємо StateManager з основним state
        notification_state_manager = StateManagerClass()
        notification_state_manager.state = state  # Використовуємо той самий state
        
        # Перевіряємо чи наближається відключення або відновлення
        warning_message = check_upcoming_events(
            events_data,
            monitoring_group,
            notification_state_manager
        )
        
        if warning_message:
            logger.info(f"")
            logger.info(f"⚠️ Попередження:")
            logger.info(warning_message)
            
            # Відправляємо у всі налаштовані чати для розкладу
            sent_count = send_to_multiple_chats(
                config['telegram_bot_token'],
                schedule_chat_ids,
                warning_message
            )
            
            if sent_count > 0:
                logger.info(f"✅ Попередження відправлено в {sent_count}/{len(schedule_chat_ids)} чат(ів)")
                # StateManager вже зберіг мітку про відправку всередині check_upcoming_events
        else:
            logger.info("ℹ️ Попереджень не потрібно (детальну інформацію див. вище)")
    elif not config['enable_hourly_notifications']:
        logger.debug("⏭️ Попередження вимкнені (ENABLE_HOURLY_NOTIFICATIONS=false)")
    elif not has_schedule_chats:
        logger.debug("⏭️ Пропускаємо попередження (немає налаштованих чатів)")
    
    # === КРОК 3: Перевірка змін та відправка ===
    logger.info("")
    logger.info("=" * 60)
    logger.info("📬 КРОК 3: Перевірка змін та відправка повідомлень")
    logger.info("=" * 60)
    
    # Перевірка чи є чати для відправки
    if not has_schedule_chats:
        logger.warning("⚠️ Немає налаштованих чатів для розкладу (CHAT_ID або ADDITIONAL_CHAT_IDS)")
    else:
        logger.info(f"📱 Відправка розкладу в {len(schedule_chat_ids)} чат(ів)")
    
    today = datetime.now().strftime('%Y-%m-%d')
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    
    for date_str in [today, tomorrow]:
        if date_str not in merged_data:
            logger.warning(f"⚠️ Немає даних для {date_str}")
            continue
        
        day_data = merged_data[date_str]
        source = source_info.get(date_str, {})
        day_label = format_date_label(date_str)
        
        # Перевірка змін
        changed, old_hash, new_hash = is_changed(
            monitoring_group, 
            date_str, 
            day_data, 
            state,
            source.get('source', '')
        )

        current_periods = normalize_schedule_slots(day_data.get('slots', []))
        previous_periods = get_stored_schedule_slots(
            state,
            monitoring_group,
            date_str,
        )
        duration_delta_minutes = None
        if previous_periods is not None:
            duration_delta_minutes = (
                calculate_outage_duration(current_periods)
                - calculate_outage_duration(previous_periods)
            )
        
        # Визначаємо чи відправляти
        send_schedule = should_send_schedule(
            monitoring_group,
            date_str,
            changed,
            state,
            day_data,
        )
        if send_schedule:
            # Формуємо повідомлення
            message = format_schedule_message(
                date_str,
                day_data,
                monitoring_group,
                day_label,
                source,
                group_change_info,
                duration_delta_minutes,
            )
            
            logger.info(f"")
            logger.info(f"📨 Повідомлення для {date_str}:")
            logger.info(message)
            
            # Відправляємо у всі налаштовані чати
            if has_schedule_chats:
                sent_count = send_to_multiple_chats(
                    config['telegram_bot_token'],
                    schedule_chat_ids,
                    message
                )
                success = sent_count > 0
                if sent_count > 0:
                    logger.info(f"✅ Відправлено в {sent_count}/{len(schedule_chat_ids)} чат(ів)")
            else:
                logger.info("⏭️ Пропускаємо відправку (немає налаштованих чатів)")
                success = True  # Вважаємо успішним для оновлення стану
            
            if success:
                # Оновлюємо стан
                update_state(
                    monitoring_group,
                    date_str,
                    new_hash,
                    state,
                    periods=current_periods,
                )
                save_state(state)
        elif (
            new_hash
            and (
                changed
                or previous_periods is None
                or state.get(f"{monitoring_group}_{date_str}") != new_hash
            )
        ):
            # Persist valid schedules even when there is nothing to notify
            # about. This also backfills intervals for duration deltas.
            update_state(
                monitoring_group,
                date_str,
                new_hash,
                state,
                periods=current_periods,
            )
            save_state(state)
        
        # Відправка на зовнішній API (незалежно від змін)
        if external_api_enabled:
            logger.info(f"")
            logger.info(f"🌐 Відправка на зовнішній API для {date_str}...")
            send_to_external_api(
                date_str,
                day_data,
                monitoring_group,
                config['external_api_url'],
                config['external_api_token']
            )
    
    # === КРОК 4: Обробка аварій ===
    if config['enable_alarm_notifications']:
        logger.info("")
        logger.info("=" * 60)
        logger.info("🚨 КРОК 4: Обробка аварій")
        logger.info("=" * 60)
        
        if alarms_groups:
            logger.info(f"📋 Знайдено {len(alarms_groups)} груп аварій")
            
            if not has_alarm_chats:
                logger.warning("⚠️ Немає налаштованого чату для аварій (DTEK_ALARMS_CHAT_ID)")
            
            for alarm_key, alarm_info in alarms_groups.items():
                houses_count = len(alarm_info['houses'])
                
                if should_send_alarm(str(alarm_key), state):
                    message = format_alarm_message(alarm_info, houses_count)
                    
                    logger.info(f"")
                    logger.info(f"📨 Аварія:")
                    logger.info(message)
                    
                    # Відправляємо у налаштовані чати для аварій
                    if has_alarm_chats:
                        sent_count = send_to_multiple_chats(
                            config['telegram_bot_token'],
                            alarm_chat_ids,
                            message
                        )
                        success = sent_count > 0
                        if sent_count > 0:
                            logger.info(f"✅ Відправлено аварію в {sent_count}/{len(alarm_chat_ids)} чат(ів)")
                    else:
                        logger.info("⏭️ Пропускаємо відправку аварії (немає налаштованих чатів)")
                        success = True  # Вважаємо успішним для оновлення стану
                    
                    if success:
                        state[f"last_alarm_{alarm_key}"] = str(alarm_key)
                        save_state(state)
        else:
            logger.info("✅ Аварій немає")
    else:
        logger.debug("⏭️ Сповіщення про аварії вимкнені (ENABLE_ALARM_NOTIFICATIONS=false)")
    
    # === Очищення старих записів ===
    logger.info("")
    logger.info("=" * 60)
    logger.info("🧹 Очищення старих записів")
    logger.info("=" * 60)
    
    state = cleanup_old_states(state, days_to_keep=7)
    save_state(state)
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("✅ Моніторинг завершено")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
