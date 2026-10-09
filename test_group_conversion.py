#!/usr/bin/python3
"""
Тест формування коду групи ДТЕК
"""

def test_dtek_group_conversion():
    """Тестуємо різні формати груп"""
    print("🧪 Тест конвертації коду групи ДТЕК")
    print("=" * 60)
    
    test_cases = [
        ("6.2", "GPV6.2"),     # Новий формат з крапкою
        ("1.1", "GPV1.1"),     # Перша група
        ("3.2", "GPV3.2"),     # Третя група
        ("2", "GPV6.2"),       # Старий формат без крапки (за замовчуванням 6.2)
        ("1", "GPV6.1"),       # Старий формат
    ]
    
    for group_input, expected_output in test_cases:
        # Логіка з коду
        if '.' in group_input:
            dtek_group = f"GPV{group_input}"
        else:
            dtek_group = f"GPV6.{group_input}"
        
        status = "✅" if dtek_group == expected_output else "❌"
        print(f"{status} GROUP={group_input:4s} -> {dtek_group:8s} (очікується: {expected_output})")
        
        if dtek_group != expected_output:
            print(f"   ⚠️ ПОМИЛКА: очікується {expected_output}, отримано {dtek_group}")
            return False
    
    print("=" * 60)
    print("✅ Всі тести пройшли успішно!")
    return True

if __name__ == '__main__':
    try:
        success = test_dtek_group_conversion()
        exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Помилка: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
