# Архітектура проекту

## Діаграма потоку даних

```
┌─────────────────────────────────────────────────────────────────┐
│                         MAIN.PY                                 │
│                   (Головна оркестрація)                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
      ┌───────────────────────────────────────────────────┐
      │         КРОК 1: Отримання даних                   │
      │         (modules/data_sources/)                   │
      └───────────────────────────────────────────────────┘
                              │
      ┌───────────────────────┼───────────────────────────┐
      │                       │                           │
      ▼                       ▼                           ▼
┌──────────────────────┐    ┌─────────────────────┐
│ Unified Feed Loader  │    │    Alarms Loader    │
│ YASNO + DTEK графіки │    │ (окремий API)       │
│ режими та історія    │    └─────────────────────┘
└──────────────────────┘              │
    │                │               ▼
    ▼                ▼        ┌───────────────┐
┌──────────┐   ┌────────────┐   │ Group Detector│
│ Schedule │   │ Mode       │   └───────────────┘
│ Merger   │   │ History    │
└──────────┘   └────────────┘
    │                │
    └────────┬───────┘
           ▼
      ┌──────────────────────────────────────────────┐
      │     КРОК 2: Об'єднання даних                 │
      │     (modules/processing/data_merger.py)      │
      │                                              │
    │  Пріоритет графіків:                         │
    │  1. DTEK адресний графік з definite слотами  │
    │  2. YASNO для вибраної групи                 │
      └──────────────────────────────────────────────┘
                     │
                     ▼
      ┌──────────────────────────────────────────────┐
      │     State Manager                            │
      │     (modules/processing/state_manager.py)    │
      │                                              │
      │  • Calculate hash                            │
      │  • Compare with previous                     │
      │  • Detect changes                            │
      └──────────────────────────────────────────────┘
                     │
                     ▼
      ┌──────────────────────────────────────────────┐
      │     КРОК 3: Правила відправки                │
      │     (modules/notification/rules.py)          │
      │                                              │
      │  • Should send schedule?                     │
      │  • Should send alarm?                        │
      │  • Format date labels                        │
      └──────────────────────────────────────────────┘
                     │
                     ▼
      ┌──────────────────────────────────────────────┐
      │     КРОК 4: Відправка                        │
      │     (modules/notification/notifier.py)       │
      │                                              │
      │  • Format messages                           │
      │  • Send to Telegram                          │
      └──────────────────────────────────────────────┘
                     │
                     ▼
              ┌─────────────┐
              │  Telegram   │
              │   Bot API   │
              └─────────────┘
```

## Модулі та їх відповідальність

### 📁 modules/data_sources/
Відповідальність: **Завантаження даних з зовнішніх джерел**

| Файл | Призначення |
|------|-------------|
| `svitlo_monitor_loader.py` | Єдиний endpoint: графіки YASNO/DTEK і режими |
| `group_detector.py` | Визначення групи на основі аварій |
| `alarms_loader.py` | Завантаження інформації про аварії |

### 📁 modules/processing/
Відповідальність: **Обробка та об'єднання даних**

| Файл | Призначення |
|------|-------------|
| `data_merger.py` | Об'єднання даних з пріоритетами |
| `state_manager.py` | Hash-based відстеження змін |
| `mode_history.py` | Дедуплікація переходів і тривалість режимів |

### 📁 modules/notification/
Відповідальність: **Формування та відправка повідомлень**

| Файл | Призначення |
|------|-------------|
| `rules.py` | Правила відправки (коли відправляти) |
| `notifier.py` | Форматування та Telegram відправка |

### 📄 main.py
Відповідальність: **Оркестрація всього процесу**

Завантажує агреговані графіки й історію режимів, окремо читає аварійні дані, об'єднує графіки та надсилає повідомлення.

## Переваги архітектури

### ✅ Separation of Concerns
Кожен модуль відповідає за одну річ:
- Data sources → завантаження
- Processing → обробка
- Notification → відправка

### ✅ Easy Testing
Модулі можна тестувати ізольовано:
```python
# Тест тільки merger
from modules.processing.data_merger import merge_data_sources
result = merge_data_sources(mock_yasno, mock_dtek, mock_standard, mock_fact)
```

### ✅ Easy Extension
Додати нове джерело даних:
1. Створити новий loader у `data_sources/`
2. Додати виклик у `main.py`
3. Оновити пріоритет у `data_merger.py`

### ✅ Clear Data Flow
Послідовний потік: Load → Merge → Check → Notify

### ✅ Single Responsibility
Кожна функція має одну відповідальність

## Приклад використання

### Запуск
```bash
python main.py
```

### Додавання нового джерела
```python
# 1. Створити modules/data_sources/new_source_loader.py
def load_new_source_data(url, group):
    """Завантажує дані з нового джерела"""
    response = requests.get(url)
    return parse_data(response.json())

# 2. Додати виклик у main.py (крок 1)
new_source_data = load_new_source_data(config['new_source_url'], monitoring_group)

# 3. Оновити data_merger.py
def merge_data_sources(yasno, dtek, standard, dtek_fact, new_source):
    # Додати логіку пріоритету
    if new_source_has_date:
        use_new_source()
```

---

**Рефакторинг: 29.01.2026**
