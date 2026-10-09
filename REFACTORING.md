# Рефакторинг структури проекту

## Нова модульна архітектура

Проект було повністю рефакторено для полегшення супроводження та розширення.

### Структура проекту

```
yasno_check_updates_2025/
├── main.py                    # Головний файл запуску
├── modules/                   # Модулі додатку
│   ├── data_sources/         # Джерела даних
│   │   ├── svitlo_monitor_loader.py  # Агреговані графіки й режими
│   │   ├── standard_loader.py        # Стандартний графік
│   │   ├── group_detector.py         # Визначення групи
│   │   └── alarms_loader.py          # Аварії DTEK
│   ├── processing/           # Обробка даних
│   │   ├── data_merger.py            # Об'єднання з пріоритетами
│   │   ├── state_manager.py          # Hash-based зміни
│   │   └── mode_history.py           # Переходи й тривалість режимів
│   └── notification/         # Нотифікації
│       ├── rules.py                  # Правила відправки
│       └── notifier.py               # Telegram відправка
├── config.json
├── states.json
├── standart_schedule.json
└── requirements.txt
```

### Архітектура

Додаток працює в 4 кроки:

#### 1. Отримання даних
- **Уніфікований endpoint** - графіки YASNO для груп, адресний графік DTEK і режими DTEK/YASNO/Укренерго
- **DTEK Alarms API** - окремий потік аварій та визначення групи; ця інтеграція його не змінює

#### 2. Об'єднання даних з пріоритетами
Модуль `data_merger.py` об'єднує нормалізовані графіки: адресний DTEK має пріоритет за наявності підтверджених відключень, інакше використовується YASNO для вибраної групи.

#### 3. Формування правил відправки
Модуль `rules.py` визначає:
- Чи потрібно відправляти розклад (на основі змін)
- Чи потрібно відправляти аварії (нові vs відправлені)
- Форматування міток (сьогодні/завтра)

#### 4. Відправка повідомлень
Модуль `notifier.py`:
- Форматує повідомлення про розклади
- Форматує повідомлення про аварії
- Відправляє в Telegram

### Переваги нової структури

✅ **Модульність** - кожен модуль має чітку відповідальність
✅ **Легке тестування** - модулі можна тестувати окремо
✅ **Легке розширення** - легко додати нові джерела даних
✅ **Чіткий потік даних** - зрозуміла послідовність обробки
✅ **Менше дублювання коду** - функції винесені в окремі модулі

### Міграція зі старої структури

Старі файли залишаються для порівняння:
- `scan_yasno.py` - старий головний файл (застарілий)
- `api_clients.py` - застарілий (замінено на data_sources/)
- `data_processor.py` - застарілий (замінено на processing/)
- `notifiers.py` - застарілий (замінено на notification/)
- `state_manager.py` - застарілий (замінено на processing/state_manager.py)

**Використовуйте `main.py` замість `scan_yasno.py`!**

### Запуск

```bash
# Встановити залежності
pip install -r requirements.txt

# Налаштувати .env файл
cp .env.example .env
# Відредагувати .env

# Запустити
python main.py
```

### Конфігурація (.env)

```env
GROUP=8.1
SCHEDULE_SOURCE=unified
SVITLO_MONITOR_URL=https://kit.uca.co.ua/svitlo_monitor_response.json
ENABLE_MODE_NOTIFICATIONS=true
BOT_TOKEN=...
CHAT_ID=...
```

### Логування

Всі модулі використовують Python logging:
- **INFO** - основний потік виконання
- **WARNING** - попередження (відсутні дані, тощо)
- **ERROR** - помилки (API недоступні, тощо)
- **DEBUG** - детальна інформація

Логи зберігаються у `yasno_bot.log` (ротація по 10MB, 5 backup файлів).

### Розробка

Для додавання нового джерела даних:
1. Створити loader у `modules/data_sources/`
2. Додати виклик у `main.py` (крок 1)
3. Оновити `data_merger.py` для підтримки нового джерела
4. Додати пріоритет у логіку об'єднання

### Тестування

Кожен модуль можна тестувати окремо:

```python
# Тест уніфікованого loader
from modules.data_sources.svitlo_monitor_loader import load_svitlo_monitor_data
data = load_svitlo_monitor_data('https://kit.uca.co.ua/svitlo_monitor_response.json', '8.1')

# Тест data merger
from modules.processing.data_merger import merge_data_sources
merged, info = merge_data_sources(yasno_data, dtek_data, standard_data, dtek_fact_data)
```

---

**Рефакторинг виконано 29.01.2026**
