"""
Home Assistant Integration для Akadem Svitlo
=============================================

Цей скрипт читає дані з Home Assistant сенсора та відправляє їх до Laravel API.

Налаштування:
1. Встановіть необхідні пакети: pip install requests python-dotenv
2. Створіть .env файл з такими параметрами:
   - HA_URL=http://homeassistant.local:8123
   - HA_TOKEN=your_long_lived_access_token
   - HA_SENSOR_ENTITY_ID=sensor.energy_monitor_001
   - LARAVEL_API_URL=https://your-site.com/api
   - API_TOKEN=your_laravel_api_token

Як отримати Long-Lived Access Token в Home Assistant:
1. Відкрийте Home Assistant
2. Натисніть на свій профіль (ліворуч внизу)
3. Прокрутіть до "Long-Lived Access Tokens"
4. Натисніть "Create Token"
5. Дайте йому назву (наприклад, "Akadem Svitlo Integration")
6. Скопіюйте токен і додайте в .env файл

Як знайти Entity ID сенсора:
1. Відкрийте Home Assistant
2. Перейдіть до Developer Tools > States
3. Знайдіть свій сенсор (наприклад, sensor.energy_monitor_001)
4. Скопіюйте Entity ID

Запуск:
- Одноразово: python home_assistant_integration.py
- В циклі (кожні 60 секунд): python home_assistant_integration.py --loop
- Вказати інтервал: python home_assistant_integration.py --loop --interval 30
"""

import os
import sys
import time
import argparse
import requests
import urllib3
from datetime import datetime
from dotenv import load_dotenv

# Завантажуємо змінні з .env
load_dotenv()

# Конфігурація Home Assistant
HA_URL = os.getenv('HA_URL', 'http://homeassistant.local:8123')
HA_TOKEN = os.getenv('HA_TOKEN')
HA_VOLTAGE_SENSOR = os.getenv('HA_VOLTAGE_SENSOR', 'sensor.0xb43522fffec16319_voltage')
HA_FREQUENCY_SENSOR = os.getenv('HA_FREQUENCY_SENSOR', 'sensor.0xb43522fffec16319_ac_frequency')
HA_POWER_SENSOR = os.getenv('HA_POWER_SENSOR', 'binary_sensor.is_electicity_exists')
HA_MODE_SENSOR = os.getenv('HA_MODE_SENSOR', 'input_text.yasno_last_state')
HA_VERIFY_SSL = os.getenv('HA_VERIFY_SSL', 'true').lower() in ('true', '1', 'yes')

# Конфігурація Laravel API
LARAVEL_API_URL = os.getenv('LARAVEL_API_URL', 'http://localhost')
API_TOKEN = os.getenv('API_TOKEN')

# Вимкнути попередження про SSL якщо потрібно
if not HA_VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_sensor_data_from_ha():
    """
    Отримати дані з Home Assistant сенсорів (напруга, частота, наявність електрики, режим)
    
    Returns:
        dict: Дані сенсорів або None у випадку помилки
    """
    if not HA_TOKEN:
        print("❌ Помилка: HA_TOKEN не вказано в .env файлі")
        return None
    
    headers = {
        'Authorization': f'Bearer {HA_TOKEN}',
        'Content-Type': 'application/json',
    }
    
    try:
        # Отримуємо напругу
        voltage_url = f"{HA_URL}/api/states/{HA_VOLTAGE_SENSOR}"
        voltage_response = requests.get(voltage_url, headers=headers, timeout=30, verify=HA_VERIFY_SSL)
        voltage_response.raise_for_status()
        voltage_data = voltage_response.json()
        
        # Отримуємо частоту
        frequency_url = f"{HA_URL}/api/states/{HA_FREQUENCY_SENSOR}"
        frequency_response = requests.get(frequency_url, headers=headers, timeout=30, verify=HA_VERIFY_SSL)
        frequency_response.raise_for_status()
        frequency_data = frequency_response.json()
        
        # Отримуємо статус електрики (binary sensor)
        power_url = f"{HA_URL}/api/states/{HA_POWER_SENSOR}"
        power_response = requests.get(power_url, headers=headers, timeout=30, verify=HA_VERIFY_SSL)
        power_response.raise_for_status()
        power_data = power_response.json()
        
        # Отримуємо режим відключень (NORMAL/STABLE/EMERGENCY)
        mode_url = f"{HA_URL}/api/states/{HA_MODE_SENSOR}"
        mode_response = requests.get(mode_url, headers=headers, timeout=30, verify=HA_VERIFY_SSL)
        mode_response.raise_for_status()
        mode_data = mode_response.json()
        
        # Парсимо напругу
        voltage_state = voltage_data.get('state')
        voltage = None
        if voltage_state not in ['unavailable', 'unknown', None]:
            try:
                voltage = float(voltage_state)
            except (ValueError, TypeError):
                voltage = None
        
        # Парсимо частоту
        frequency_state = frequency_data.get('state')
        frequency = None
        if frequency_state not in ['unavailable', 'unknown', None]:
            try:
                frequency = float(frequency_state)
            except (ValueError, TypeError):
                frequency = None
        
        # Визначаємо чи є електрика (з binary sensor)
        power_state = power_data.get('state', '').lower()
        has_power = power_state == 'on'
        
        # Парсимо режим відключень
        mode_state = mode_data.get('state', '').upper()
        # Конвертуємо режим з HA у формат Laravel
        # NORMAL -> normal, STABLE -> blackout, EMERGENCY -> emergency
        mode_map = {
            'NORMAL': 'normal',
            'STABLE': 'blackout',
            'EMERGENCY': 'emergency'
        }
        mode = mode_map.get(mode_state, None)
        
        result = {
            'voltage': voltage,
            'frequency': frequency,
            'has_power': has_power,
            'mode': mode,
            'mode_raw': mode_state,
            'voltage_sensor': HA_VOLTAGE_SENSOR,
            'frequency_sensor': HA_FREQUENCY_SENSOR,
            'power_sensor': HA_POWER_SENSOR,
            'mode_sensor': HA_MODE_SENSOR,
            'power_state': power_state,
            'timestamp': datetime.now().isoformat()
        }
        
        return result
        
    except requests.exceptions.SSLError as e:
        print(f"❌ Помилка SSL з'єднання з Home Assistant: {e}")
        print(f"💡 Порада: Додайте HA_VERIFY_SSL=false в .env файл для вимкнення перевірки SSL")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Помилка при отриманні даних з Home Assistant: {e}")
        return None


def send_sensor_data_to_laravel(sensor_data):
    """
    Відправити дані сенсора до Laravel API
    
    Args:
        sensor_data (dict): Дані сенсора
        
    Returns:
        bool: True якщо успішно, False якщо помилка
    """
    if not API_TOKEN:
        print("❌ Помилка: API_TOKEN не вказано в .env файлі")
        return False
    
    if not sensor_data:
        print("❌ Немає даних для відправки")
        return False
    
    headers = {
        'Authorization': f'Bearer {API_TOKEN}',
        'Content-Type': 'application/json',
    }
    
    url = f"{LARAVEL_API_URL}/api/update/sensor"
    
    payload = {
        'voltage': sensor_data['voltage'],
        'frequency': sensor_data['frequency'],
        'has_power': sensor_data['has_power'],
        'mode': sensor_data.get('mode')  # Додаємо режим
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30, verify=HA_VERIFY_SSL)
        response.raise_for_status()
        
        try:
            result = response.json()
        except ValueError as e:
            print(f"❌ Помилка парсингу відповіді від Laravel: {e}")
            print(f"   Response status: {response.status_code}")
            print(f"   Response text: {response.text[:200]}")
            return False
        
        if result.get('success'):
            print(f"✅ Дані успішно відправлено:")
            print(f"   📊 Напруга: {sensor_data['voltage']} В")
            print(f"   📊 Частота: {sensor_data['frequency']} Гц")
            print(f"   ⚡ Електрика: {'✓ Є' if sensor_data['has_power'] else '✗ Немає'}")
            if sensor_data.get('mode'):
                mode_text = {'normal': '🟢 Звичайний', 'blackout': '🟡 Стабілізація', 'emergency': '🔴 Аварійний'}
                print(f"   🔄 Режим: {mode_text.get(sensor_data['mode'], sensor_data['mode'])}")
            return True
        else:
            print(f"❌ Помилка від API: {result}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Помилка при відправці до Laravel: {e}")
        if hasattr(e.response, 'text'):
            print(f"   Response: {e.response.text[:200]}")
        return False


def sync_once():
    """
    Одноразова синхронізація даних
    """
    print(f"\n🔄 Синхронізація даних ({datetime.now().strftime('%H:%M:%S')})")
    print(f"   Home Assistant: {HA_URL}")
    print(f"   Сенсор напруги: {HA_VOLTAGE_SENSOR}")
    print(f"   Сенсор частоти: {HA_FREQUENCY_SENSOR}")
    print(f"   Сенсор електрики: {HA_POWER_SENSOR}")
    print(f"   Сенсор режиму: {HA_MODE_SENSOR}")
    print(f"   SSL Verification: {'✓ Увімкнено' if HA_VERIFY_SSL else '✗ Вимкнено'}")
    print(f"   Laravel API: {LARAVEL_API_URL}")
    print()
    
    # Отримуємо дані з HA
    sensor_data = get_sensor_data_from_ha()
    
    if not sensor_data:
        print("❌ Не вдалося отримати дані з Home Assistant")
        return False
    
    print(f"📥 Отримано дані з Home Assistant:")
    print(f"   Напруга: {sensor_data['voltage']} В")
    print(f"   Частота: {sensor_data['frequency']} Гц")
    print(f"   Електрика: {'✓ Є' if sensor_data['has_power'] else '✗ Немає'}")
    if sensor_data.get('mode'):
        mode_names = {'normal': 'Звичайний', 'blackout': 'Стабілізація', 'emergency': 'Аварійний'}
        print(f"   Режим: {sensor_data['mode_raw']} → {mode_names.get(sensor_data['mode'], sensor_data['mode'])}")
    print()
    print(f"   Частота: {sensor_data['frequency']} Гц")
    print(f"   Електрика: {'✓ Є' if sensor_data['has_power'] else '✗ Немає'}")
    print()
    
    # Відправляємо до Laravel
    success = send_sensor_data_to_laravel(sensor_data)
    
    return success


def sync_loop(interval=60):
    """
    Безкінечний цикл синхронізації з заданим інтервалом
    
    Args:
        interval (int): Інтервал між синхронізаціями в секундах
    """
    print(f"\n🔁 Запуск циклічної синхронізації (інтервал: {interval} сек)")
    print("   Натисніть Ctrl+C для зупинки")
    print()
    
    try:
        while True:
            sync_once()
            print(f"\n⏳ Очікування {interval} секунд до наступної синхронізації...")
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n\n👋 Синхронізацію зупинено користувачем")
        sys.exit(0)


def sync_cron(iterations=6, interval=10):
    """
    Режим для cron: виконує N ітерацій з заданим інтервалом та завершується.
    За замовчуванням: 6 ітерацій по 10 секунд = 60 секунд (1 хвилина).
    
    Args:
        iterations (int): Кількість синхронізацій
        interval (int): Інтервал між синхронізаціями в секундах
    """
    total_time = iterations * interval
    print(f"\n🔁 Cron режим: {iterations} синхронізацій по {interval} сек (загалом {total_time} сек)")
    print()
    
    success_count = 0
    failed_count = 0
    
    for i in range(1, iterations + 1):
        print(f"═══ Ітерація {i}/{iterations} ═══")
        success = sync_once()
        
        if success:
            success_count += 1
        else:
            failed_count += 1
        
        # Чекаємо перед наступною ітерацією (крім останньої)
        if i < iterations:
            print(f"⏳ Очікування {interval} секунд...")
            print()
            time.sleep(interval)
    
    # Підсумок
    print(f"\n{'═' * 50}")
    print(f"📊 Підсумок:")
    print(f"   ✅ Успішно: {success_count}")
    print(f"   ❌ Помилок: {failed_count}")
    print(f"   📈 Успішність: {(success_count / iterations * 100):.1f}%")
    print(f"{'═' * 50}\n")
    
    sys.exit(0 if failed_count == 0 else 1)


def main():
    """
    Головна функція
    """
    parser = argparse.ArgumentParser(
        description='Home Assistant Integration для Akadem Svitlo',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Приклади використання:
  python home_assistant_integration.py                  # Одноразова синхронізація
  python home_assistant_integration.py --loop           # Циклічна синхронізація (60 сек)
  python home_assistant_integration.py --loop -i 30     # Циклічна синхронізація (30 сек)
  python home_assistant_integration.py --cron           # Cron режим: 6 разів по 10 сек
  python home_assistant_integration.py --cron -n 5 -i 10 # Cron: 5 разів по 10 сек
        """
    )
    
    parser.add_argument(
        '--loop',
        action='store_true',
        help='Запустити в нескінченному циклі з періодичною синхронізацією'
    )
    
    parser.add_argument(
        '--cron',
        action='store_true',
        help='Режим для cron: виконує N синхронізацій та завершується (за замовчуванням: 6 разів по 10 сек)'
    )
    
    parser.add_argument(
        '-n', '--iterations',
        type=int,
        default=6,
        help='Кількість ітерацій для --cron режиму (за замовчуванням: 6)'
    )
    
    parser.add_argument(
        '-i', '--interval',
        type=int,
        default=None,
        help='Інтервал між синхронізаціями в секундах (за замовчуванням: 10 для --cron, 60 для --loop)'
    )
    
    args = parser.parse_args()
    
    # Визначаємо дефолтний інтервал залежно від режиму
    if args.interval is None:
        if args.cron:
            args.interval = 10  # Для cron: 10 секунд
        else:
            args.interval = 60  # Для loop: 60 секунд
    
    # Перевірка конфігурації
    if not HA_TOKEN:
        print("❌ Помилка: HA_TOKEN не вказано в .env файлі")
        print("   Створіть Long-Lived Access Token в Home Assistant")
        sys.exit(1)
    
    if not API_TOKEN:
        print("❌ Помилка: API_TOKEN не вказано в .env файлі")
        sys.exit(1)
    
    # Перевірка що не вказано обидва режими одночасно
    if args.loop and args.cron:
        print("❌ Помилка: не можна використовувати --loop та --cron одночасно")
        sys.exit(1)
    
    # Запуск
    if args.cron:
        sync_cron(args.iterations, args.interval)
    elif args.loop:
        sync_loop(args.interval)
    else:
        success = sync_once()
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
