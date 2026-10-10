"""
Робота з часом за Києвом.

Сервер може працювати в UTC, тому всі розрахунки дат і часу мають
виконуватись у часовому поясі Europe/Kyiv, а не в системному.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    KYIV_TZ = ZoneInfo("Europe/Kyiv")
except ZoneInfoNotFoundError:
    # Старі бази tzdata знають тільки стару назву
    KYIV_TZ = ZoneInfo("Europe/Kiev")


def now_kyiv():
    """Поточний час за Києвом (timezone-aware)."""
    return datetime.now(KYIV_TZ)


def to_kyiv(dt):
    """Переводить aware datetime у київський час."""
    return dt.astimezone(KYIV_TZ)


def from_timestamp_kyiv(timestamp):
    """Unix timestamp → datetime за Києвом."""
    return datetime.fromtimestamp(timestamp, KYIV_TZ)


def today_str(offset_days=0):
    """Дата за Києвом у форматі YYYY-MM-DD (зі зсувом у днях)."""
    return (now_kyiv() + timedelta(days=offset_days)).strftime('%Y-%m-%d')


def kyiv_log_time_converter(timestamp):
    """Конвертер для logging.Formatter, щоб логи писались за Києвом."""
    return from_timestamp_kyiv(timestamp).timetuple()
