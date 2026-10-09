#!/usr/bin/python3
"""
Тестовий скрипт для перевірки інтеграції ДТЕК API
"""

import json
from datetime import datetime

# Симулюємо дані ДТЕК
dtek_sample = {
    "1": "yes",
    "2": "yes",
    "3": "yes",
    "4": "second",
    "5": "no",
    "6": "first",
    "7": "yes",
    "8": "yes",
    "9": "yes",
    "10": "yes",
    "11": "yes",
    "12": "yes",
    "13": "yes",
    "14": "yes",
    "15": "no",
    "16": "no",
    "17": "no",
    "18": "no",
    "19": "yes",
    "20": "yes",
    "21": "yes",
    "22": "yes",
    "23": "yes",
    "24": "yes"
}

def test_convert_dtek_format():
    """Тест конвертації формату ДТЕК у формат YASNO"""
    print("🧪 Тест конвертації формату ДТЕК")
    print("=" * 60)
    
    # Імпортуємо функцію з основного модуля
    import sys
    sys.path.insert(0, '.')
    from scan_yasno_20251216 import convert_dtek_to_yasno_format
    
    # Тестові дані
    date_str = "2025-12-13"
    update_time = "13.12.2025 15:45"
    
    # Конвертуємо
    result = convert_dtek_to_yasno_format(dtek_sample, date_str, update_time)
    
    # Виводимо результат
    print(f"📅 Дата: {date_str}")
    print(f"⏰ Час оновлення: {update_time}")
    print(f"📊 Статус: {result['status']}")
    print(f"🔌 Кількість слотів відключення: {len(result['slots'])}")
    print("\n📋 Слоти відключення:")
    
    for i, slot in enumerate(result['slots'], 1):
        start_hour = slot['start'] // 60
        start_min = slot['start'] % 60
        end_hour = slot['end'] // 60
        end_min = slot['end'] % 60
        duration = slot['end'] - slot['start']
        
        print(f"  {i}. {start_hour:02d}:{start_min:02d} - {end_hour:02d}:{end_min:02d} "
              f"({duration} хв) - {slot['type']}")
    
    print("\n" + "=" * 60)
    print("✅ Тест успішно завершено!")
    
    return result

def test_merge_logic():
    """Тест логіки об'єднання даних"""
    print("\n🧪 Тест логіки об'єднання даних")
    print("=" * 60)
    
    # Створюємо тестові дані YASNO
    yasno_data = {
        'today': {
            'date': '2025-12-13T00:00:00+02:00',
            'status': 'ScheduleApplies',
            'slots': [
                {'start': 0, 'end': 180, 'type': 'Definite'},
                {'start': 840, 'end': 1080, 'type': 'Definite'}
            ]
        },
        'tomorrow': {
            'date': '2025-12-14T00:00:00+02:00',
            'status': 'ScheduleApplies',
            'slots': []
        }
    }
    
    # Створюємо тестові дані ДТЕК
    dtek_data = {
        'data': {
            '1765576800': {  # 13.12.2025
                'GPV6.2': dtek_sample
            },
            '1765663200': {  # 14.12.2025
                'GPV6.2': {str(h): 'yes' for h in range(1, 25)}
            }
        },
        'update_time': '13.12.2025 15:45',
        'group': 'GPV6.2',
        'today_timestamp': 1765576800
    }
    
    print("📡 YASNO data: сьогодні 2 періоди відключень, завтра немає")
    print("📡 DTEK data: сьогодні інший розклад")
    print("⚠️  ДТЕК використовується ТІЛЬКИ для today (не для tomorrow)")
    print("\n🔄 Перевіряємо чи система виявить різницю...")
    
    # Імпортуємо функції
    import sys
    sys.path.insert(0, '.')
    from scan_yasno_20251216 import merge_sources_data
    
    merged, source_info = merge_sources_data(yasno_data, dtek_data, '2')
    
    print(f"\n📊 Результат об'єднання:")
    print(f"  Today джерело: {source_info['today']['source']}")
    print(f"  Tomorrow джерело: {source_info['tomorrow']['source']}")
    
    # Перевіряємо що tomorrow завжди від YASNO
    if source_info['tomorrow']['source'] != 'yasno':
        print(f"\n❌ ПОМИЛКА: Tomorrow має бути від YASNO, а не від {source_info['tomorrow']['source']}")
        return False
    
    print(f"\n✅ Правильно: Tomorrow завжди від YASNO")
    print(f"✅ Today може бути від YASNO або ДТЕК (залежно від актуальності)")
    
    print("\n" + "=" * 60)
    print("✅ Тест логіки об'єднання завершено!")
    return True

if __name__ == '__main__':
    try:
        # Тест 1: Конвертація формату
        result = test_convert_dtek_format()
        
        # Тест 2: Логіка об'єднання
        merge_ok = test_merge_logic()
        
        if merge_ok:
            print("\n" + "=" * 60)
            print("🎉 Всі тести пройдено успішно!")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("❌ Деякі тести не пройшли!")
            print("=" * 60)
            exit(1)
        
    except Exception as e:
        print(f"\n❌ Помилка: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
