#!/usr/bin/python3
"""
Тест реальних API endpoints (YASNO та ДТЕК)
"""

import requests
import json

def test_yasno_api():
    """Тест YASNO API"""
    print("🧪 Тест YASNO API")
    print("=" * 60)
    
    url = "https://app.yasno.ua/api/blackout-service/public/shutdowns/regions/25/dsos/902/planned-outages"
    
    try:
        print(f"📡 Запит до: {url}")
        response = requests.get(url, timeout=10)
        print(f"✅ Статус: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            # Перевіряємо доступні групи
            if isinstance(data, dict):
                groups = list(data.keys())
                print(f"📊 Доступні групи: {groups[:5]}..." if len(groups) > 5 else f"📊 Доступні групи: {groups}")
                
                # Перевіряємо структуру для групи 6.2
                if '6.2' in data:
                    group_data = data['6.2']
                    print(f"✅ Дані для групи 6.2: {list(group_data.keys())}")
                    
                    if 'today' in group_data:
                        today = group_data['today']
                        print(f"   Today: date={today.get('date', 'N/A')}, status={today.get('status', 'N/A')}")
                        print(f"   Slots: {len(today.get('slots', []))}")
                else:
                    print("⚠️ Група 6.2 не знайдена")
            
            print("✅ YASNO API працює коректно!")
            return True
        else:
            print(f"❌ YASNO API повернув код {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Помилка при запиті до YASNO API: {e}")
        return False
    finally:
        print("=" * 60)
        print()

def test_dtek_api():
    """Тест ДТЕК API"""
    print("🧪 Тест ДТЕК API")
    print("=" * 60)
    
    url = "https://kit.uca.co.ua/dtek_parsed.json"
    
    try:
        print(f"📡 Запит до: {url}")
        response = requests.get(url, timeout=10)
        print(f"✅ Статус: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            # Перевіряємо структуру
            print(f"📊 Структура: {list(data.keys())}")
            print(f"✅ ok={data.get('ok', False)}")
            print(f"📅 ts={data.get('ts', 'N/A')}")
            
            # Перевіряємо js_variables
            js_vars = data.get('js_variables', {})
            fact = js_vars.get('fact', {})
            fact_data = fact.get('data', {})
            
            print(f"📊 Доступні дати: {list(fact_data.keys())}")
            print(f"⏰ Останнє оновлення: {fact.get('update', 'N/A')}")
            
            # Перевіряємо групу GPV6.2
            today_ts = fact.get('today')
            if today_ts and str(today_ts) in fact_data:
                day_data = fact_data[str(today_ts)]
                groups = list(day_data.keys())
                print(f"📊 Доступні групи для сьогодні: {groups}")
                
                if 'GPV6.2' in day_data:
                    gpv62 = day_data['GPV6.2']
                    print(f"✅ Дані для GPV6.2: {len(gpv62)} годин")
                    
                    # Підраховуємо відключення
                    no_count = sum(1 for v in gpv62.values() if v == 'no')
                    first_count = sum(1 for v in gpv62.values() if v == 'first')
                    second_count = sum(1 for v in gpv62.values() if v == 'second')
                    
                    print(f"   Повні відключення (no): {no_count} годин")
                    print(f"   Перша половина (first): {first_count} годин")
                    print(f"   Друга половина (second): {second_count} годин")
                else:
                    print("⚠️ Група GPV6.2 не знайдена")
            
            print("✅ ДТЕК API працює коректно!")
            return True
        else:
            print(f"❌ ДТЕК API повернув код {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Помилка при запиті до ДТЕК API: {e}")
        return False
    finally:
        print("=" * 60)
        print()

def main():
    print("🔬 Тестування реальних API endpoints")
    print("=" * 60)
    print()
    
    yasno_ok = test_yasno_api()
    dtek_ok = test_dtek_api()
    
    print("📊 Підсумок")
    print("=" * 60)
    print(f"YASNO API: {'✅ Працює' if yasno_ok else '❌ Не працює'}")
    print(f"ДТЕК API:  {'✅ Працює' if dtek_ok else '❌ Не працює'}")
    print("=" * 60)
    
    if yasno_ok and dtek_ok:
        print("\n🎉 Обидва API доступні! Бот може працювати в повному режимі.")
    elif yasno_ok or dtek_ok:
        print("\n⚠️ Один з API недоступний, але бот може працювати в обмеженому режимі.")
    else:
        print("\n❌ Жоден API недоступний. Перевірте інтернет з'єднання.")

if __name__ == '__main__':
    main()
