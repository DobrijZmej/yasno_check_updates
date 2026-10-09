# Рефакторинг структури проекту

## Нова модульна архітектура

Проект було повністю рефакторено для полегшення супроводження та розширення.

### Структура проекту

```
yasno_check_updates_2025/
├── main.py                    # Головний файл запуску
├── modules/                   # Модулі додатку
│   ├── data_sources/         # Джерела даних
│   │   ├── yasno_loader.py           # YASNO API
│   │   ├── dtek_schedule_loader.py   # DTEK Schedule API
│   │   ├── dtek_fact_loader.py       # DTEK Fact (з аварій)
│   │   ├── standard_loader.py        # Стандартний графік
│   │   ├── group_detector.py         # Визначення групи
│   │   └── alarms_loader.py          # Аварії DTEK
│   ├── processing/           # Обробка даних
│   │   ├── data_merger.py            # Об'єднання з пріоритетами
│   │   └── state_manager.py          # Hash-based зміни
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

#### 1. Отримання даних з джерел
- **YASNO API** - офіційний графік YASNO
- **DTEK Schedule API** - плановий графік ДTEK
- **DTEK Fact** - графік з аварій (з DTEK Alarms API)
- **Standard Schedule** - резервний графік з файлу
- **Group Detector** - автоматичне визначення групи на основі аварій

#### 2. Об'єднання даних з пріоритетами
Модуль `data_merger.py` об'єднує дані за пріоритетами:
1. **DTEK Fact** (найвищий) - найточніший, оновлюється під час аварій
2. **DTEK Schedule** - плановий графік від DTEK
3. **YASNO** - офіційний графік YASNO
4. **Standard Schedule** (резервний) - використовується якщо всі інші недоступні

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
GROUP=12.1
YASNO_API_URL=https://...
DTEK_API_URL=https://...
DTEK_ALARMS_API_URL=https://...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
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
# Тест YASNO loader
from modules.data_sources.yasno_loader import load_yasno_data
data = load_yasno_data('https://...', '12.1')

# Тест data merger
from modules.processing.data_merger import merge_data_sources
merged, info = merge_data_sources(yasno_data, dtek_data, standard_data, dtek_fact_data)
```

---

**Рефакторинг виконано 29.01.2026**
