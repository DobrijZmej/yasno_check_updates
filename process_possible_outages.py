"""
Скрипт для обробки possible_outage інтервалів у стандартному розкладі.
Розбиває годинні інтервали з possible_outage на два по 30 хвилин,
враховуючи попередній стан.
"""

import json
from datetime import datetime, timedelta


def time_to_minutes(time_str):
    """Конвертує час HH:MM в хвилини від початку дня"""
    h, m = map(int, time_str.split(':'))
    return h * 60 + m


def minutes_to_time(minutes):
    """Конвертує хвилини від початку дня в HH:MM"""
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def process_day_intervals(intervals):
    """
    Обробляє інтервали одного дня, розбиваючи possible_outage на два інтервали.
    
    Args:
        intervals: список інтервалів дня
    
    Returns:
        список оброблених інтервалів
    """
    result = []
    
    for i, interval in enumerate(intervals):
        state = interval['state']
        
        if state == 'possible_outage':
            # Визначаємо попередній стан
            if i > 0:
                previous_state = intervals[i - 1]['state']
            else:
                # Якщо це перший інтервал, дивимося на останній інтервал попереднього дня
                # Для простоти припускаємо no_power
                previous_state = 'no_power'
            
            # Обчислюємо середину інтервалу
            start_min = time_to_minutes(interval['from'])
            end_min = time_to_minutes(interval['to'])
            middle_min = start_min + (end_min - start_min) // 2
            middle_time = minutes_to_time(middle_min)
            
            # Визначаємо стани для двох половин
            if previous_state == 'no_power':
                # Якщо до цього не було світла: спочатку не буде, потім буде
                first_state = 'no_power'
                second_state = 'power_on'
            else:  # previous_state == 'power_on'
                # Якщо до цього було світло: спочатку буде, потім не буде
                first_state = 'power_on'
                second_state = 'no_power'
            
            # Додаємо два інтервали
            result.append({
                'from': interval['from'],
                'to': middle_time,
                'state': first_state
            })
            result.append({
                'from': middle_time,
                'to': interval['to'],
                'state': second_state
            })
            
            print(f"  {interval['from']}-{interval['to']} possible_outage → "
                  f"{interval['from']}-{middle_time} {first_state} + "
                  f"{middle_time}-{interval['to']} {second_state}")
        else:
            # Залишаємо інтервал без змін
            result.append(interval)
    
    return result


def process_schedule(input_file, output_file):
    """
    Обробляє файл розкладу, замінюючи possible_outage інтервали.
    
    Args:
        input_file: шлях до вхідного файлу
        output_file: шлях до вихідного файлу
    """
    print(f"📖 Читання файлу: {input_file}")
    
    with open(input_file, 'r', encoding='utf-8') as f:
        schedule = json.load(f)
    
    print(f"✅ Завантажено розклад для {schedule['provider']} черги {schedule['queue']}")
    print(f"📍 Адреса: {schedule['address']}\n")
    
    # Обробляємо кожен день тижня
    days_order = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    days_names = {
        'monday': 'Понеділок',
        'tuesday': 'Вівторок',
        'wednesday': 'Середа',
        'thursday': 'Четвер',
        'friday': 'П\'ятниця',
        'saturday': 'Субота',
        'sunday': 'Неділя'
    }
    
    for day in days_order:
        if day in schedule['week']:
            print(f"🔄 Обробка: {days_names[day]}")
            intervals = schedule['week'][day]['intervals']
            
            # Підраховуємо possible_outage до обробки
            possible_count = sum(1 for interval in intervals if interval['state'] == 'possible_outage')
            
            if possible_count > 0:
                print(f"  Знайдено {possible_count} інтервал(ів) possible_outage")
                schedule['week'][day]['intervals'] = process_day_intervals(intervals)
            else:
                print(f"  Інтервалів possible_outage не знайдено")
            
            print()
    
    # Зберігаємо оброблений розклад
    print(f"💾 Збереження обробленого розкладу: {output_file}")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)
    
    print("✅ Обробка завершена!")


if __name__ == '__main__':
    input_file = 'standart_schedule.json'
    output_file = 'standart_schedule_processed.json'
    
    process_schedule(input_file, output_file)
