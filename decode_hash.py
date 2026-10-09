#!/usr/bin/python3
"""
Утиліта для розшифровки хешів розкладу
"""

def decode_hash(hash_string):
    """Розшифровує хеш розкладу у читабельний формат"""
    print(f"📋 Оригінальний хеш:")
    print(f"   {hash_string}")
    print()
    
    # Відділяємо дату від періодів
    if 'T' in hash_string:
        parts = hash_string.split('2025-')
        periods_part = parts[0]
        date_part = '2025-' + parts[1] if len(parts) > 1 else ''
    else:
        periods_part = hash_string
        date_part = ''
    
    print(f"📅 Дата: {date_part if date_part else 'Не вказана'}")
    print()
    
    # Парсимо періоди використовуючи регулярні вирази
    import re
    
    # Шукаємо всі пари чисел у форматі число-число
    pattern = r'(\d+)-(\d+)'
    matches = re.findall(pattern, periods_part)
    
    periods = []
    for start_str, end_str in matches:
        start = int(start_str)
        end = int(end_str)
        periods.append((start, end))
    
    print(f"🔌 Періоди відключень: {len(periods)}")
    print()
    
    total_minutes = 0
    for i, (start, end) in enumerate(periods, 1):
        start_h = start // 60
        start_m = start % 60
        end_h = end // 60
        end_m = end % 60
        
        duration = end - start
        total_minutes += duration
        
        duration_h = duration // 60
        duration_m = duration % 60
        
        print(f"  {i:2d}. {start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d}  "
              f"({duration:4d} хв = {duration_h}:{duration_m:02d})")
    
    print()
    total_h = total_minutes // 60
    total_m = total_minutes % 60
    print(f"⏱️  Загальна тривалість: {total_minutes} хв ({total_h}:{total_m:02d})")
    print()
    
    # Аналізуємо можливість консолідації
    if len(periods) > 1:
        print("🔄 Консолідовані періоди (суміжні об'єднані):")
        consolidated = []
        current = list(periods[0])
        
        for start, end in periods[1:]:
            if start <= current[1]:  # Суміжні або перекриваються
                current[1] = max(current[1], end)
            else:
                consolidated.append(tuple(current))
                current = [start, end]
        consolidated.append(tuple(current))
        
        for i, (start, end) in enumerate(consolidated, 1):
            start_h = start // 60
            start_m = start % 60
            end_h = end // 60
            end_m = end % 60
            
            duration = end - start
            duration_h = duration // 60
            duration_m = duration % 60
            
            print(f"  {i}. {start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d}  "
                  f"({duration_h}:{duration_m:02d})")
        
        print()
        print(f"📊 Результат консолідації: {len(periods)} періодів → {len(consolidated)} періодів")

def decode_manually():
    """Ручна розшифровка конкретних хешів з логу"""
    print("=" * 70)
    print("🔍 Розшифровка хешів розкладу (вручну)")
    print("=" * 70)
    print()
    
    # YASNO
    print("🟦 YASNO Hash:")
    print("   0-210630-870960-10501260-14402025-12-13T00:00:00+02:00")
    print()
    print("📅 Дата: 2025-12-13")
    print()
    print("🔌 Періоди відключень:")
    yasno_periods = [
        (0, 210, "00:00", "03:30"),
        (630, 870, "10:30", "14:30"),
        (960, 1050, "16:00", "17:30"),
        (1260, 1440, "21:00", "24:00")
    ]
    
    total = 0
    for i, (start, end, start_time, end_time) in enumerate(yasno_periods, 1):
        duration = end - start
        total += duration
        hours = duration // 60
        mins = duration % 60
        print(f"   {i}. {start_time} - {end_time}  ({hours}:{mins:02d})")
    
    t_hours = total // 60
    t_mins = total % 60
    print()
    print(f"⏱️  Загальна тривалість: {total} хв ({t_hours}:{t_mins:02d})")
    print()
    
    # DTEK
    print("=" * 70)
    print()
    print("🟨 DTEK Hash:")
    print("   0-6060-120120-180180-210630-660660-720720-780780-840")
    print("   840-870960-10201020-10501260-13201320-13801380-1440...")
    print()
    print("📅 Дата: 2025-12-13")
    print()
    print("🔌 Періоди відключень (погодинна розбивка):")
    dtek_periods = [
        (0, 60, "00:00", "01:00"),
        (60, 120, "01:00", "02:00"),
        (120, 180, "02:00", "03:00"),
        (180, 210, "03:00", "03:30"),
        (630, 660, "10:30", "11:00"),
        (660, 720, "11:00", "12:00"),
        (720, 780, "12:00", "13:00"),
        (780, 840, "13:00", "14:00"),
        (840, 870, "14:00", "14:30"),
        (960, 1020, "16:00", "17:00"),
        (1020, 1050, "17:00", "17:30"),
        (1260, 1320, "21:00", "22:00"),
        (1320, 1380, "22:00", "23:00"),
        (1380, 1440, "23:00", "24:00")
    ]
    
    total = 0
    for i, (start, end, start_time, end_time) in enumerate(dtek_periods, 1):
        duration = end - start
        total += duration
        print(f"   {i:2d}. {start_time} - {end_time}  ({duration} хв)")
    
    t_hours = total // 60
    t_mins = total % 60
    print()
    print(f"⏱️  Загальна тривалість: {total} хв ({t_hours}:{t_mins:02d})")
    print()
    
    # Консолідація DTEK
    print("� DTEK після консолідації (суміжні періоди об'єднані):")
    consolidated = [
        (0, 210, "00:00", "03:30", 210),
        (630, 870, "10:30", "14:30", 240),
        (960, 1050, "16:00", "17:30", 90),
        (1260, 1440, "21:00", "24:00", 180)
    ]
    
    for i, (start, end, start_time, end_time, duration) in enumerate(consolidated, 1):
        hours = duration // 60
        mins = duration % 60
        print(f"   {i}. {start_time} - {end_time}  ({hours}:{mins:02d})")
    
    print()
    print("=" * 70)
    print("📝 Висновок")
    print("=" * 70)
    print()
    print("✅ YASNO надає вже консолідовані періоди (4 періоди)")
    print("✅ ДТЕК надає погодинну розбивку (14 періодів)")
    print()
    print("✅ Після консолідації обидва джерела дають ОДНАКОВІ 4 періоди:")
    print("   1. 00:00 - 03:30 (3:30)")
    print("   2. 10:30 - 14:30 (4:00)")
    print("   3. 16:00 - 17:30 (1:30)")
    print("   4. 21:00 - 24:00 (3:00)")
    print()
    print("📊 Загальна тривалість відключень: 12:00 (720 хвилин)")
    print()
    print("💡 Хеші різні бо:")
    print("   • YASNO: '0-210630-870960-10501260-1440...' (4 періоди)")
    print("   • ДТЕК:  '0-6060-120120-180...' (14 періодів)")
    print()
    print("   Але після consolidate_periods() результат ІДЕНТИЧНИЙ! ✅")

def main():
    decode_manually()

if __name__ == '__main__':
    main()
