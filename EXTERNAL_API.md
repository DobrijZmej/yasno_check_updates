# Інтеграція із зовнішнім API

## Огляд

Бот автоматично відправляє дані про зміни в розкладі відключень на зовнішній API endpoint при виявленні будь-яких змін.

## Налаштування

### 1. Додайте параметри в .env

```env
EXTERNAL_API_URL=https://akadem-svitlo.kiev.ua/api/update/schedule
EXTERNAL_API_TOKEN=46134da9ef5868143a99ecd01c3e8583bb506cfe27a13ae166305b316b174d16
```

### 2. Формат запиту

**HTTP Method:** POST  
**Content-Type:** application/json  
**Authorization:** Bearer {EXTERNAL_API_TOKEN}

### 3. Структура даних

Для кожного дня (today/tomorrow) відправляється окремий POST запит:

```json
{
  "date": "2025-12-01T00:00:00+02:00",
  "group": "6.2",
  "slots": [
    {
      "start": 0,
      "end": 480,
      "type": "NotPlanned"
    },
    {
      "start": 480,
      "end": 600,
      "type": "Definite"
    },
    {
      "start": 600,
      "end": 930,
      "type": "NotPlanned"
    },
    {
      "start": 930,
      "end": 1170,
      "type": "Definite"
    },
    {
      "start": 1170,
      "end": 1440,
      "type": "NotPlanned"
    }
  ],
  "status": "ScheduleApplies"
}
```

## Параметри

### date (string)
Дата у форматі ISO 8601 з timezone  
Приклад: `"2025-12-01T00:00:00+02:00"`

### group (string)
Номер групи відключень  
Можливі значення: `"1.1"`, `"1.2"`, `"2.1"`, `"2.2"`, `"3.1"`, `"3.2"`, `"4.1"`, `"4.2"`, `"5.1"`, `"5.2"`, `"6.1"`, `"6.2"`

### slots (array)
Масив слотів з інформацією про час та тип періоду

#### Slot (object)
- **start** (integer) - початок періоду у хвилинах від початку дня (0-1440)
- **end** (integer) - кінець періоду у хвилинах від початку дня (0-1440)
- **type** (string) - тип періоду:
  - `"Definite"` - планове відключення електроенергії
  - `"NotPlanned"` - електроенергія наявна

**Приклад конвертації часу:**
- 00:00 → 0 хвилин
- 08:00 → 480 хвилин (8 * 60)
- 10:00 → 600 хвилин (10 * 60)
- 15:30 → 930 хвилин (15 * 60 + 30)
- 19:30 → 1170 хвилин (19 * 60 + 30)
- 24:00 → 1440 хвилин (24 * 60)

### status (string)
Статус розкладу  
Можливі значення:
- `"ScheduleApplies"` - розклад діє
- `"WaitingForSchedule"` - очікування розкладу
- `"NoOutages"` - відключень немає

## Приклади відповідей API

### Успішна відправка
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "success": true,
  "message": "Schedule updated successfully"
}
```

### Помилка аутентифікації
```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "success": false,
  "error": "Invalid token"
}
```

## Логування

Бот логує всі спроби відправки даних:

```
2025-12-01 09:10:52 - INFO - ✅ Дані успішно відправлено на зовнішній API для today (2025-12-01T00:00:00+02:00)
```

При помилках:
```
2025-12-01 09:10:52 - ERROR - ❌ Помилка при відправці на зовнішній API для today: Connection timeout
```

## Тестування

Для тестування без реальної відправки залиште `EXTERNAL_API_URL` порожнім або закоментуйте в .env:

```env
# EXTERNAL_API_URL=https://akadem-svitlo.kiev.ua/api/update/schedule
# EXTERNAL_API_TOKEN=your_token_here
```

Бот буде працювати в звичайному режимі без спроб відправки на зовнішній API.
