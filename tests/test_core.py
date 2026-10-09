import pytest
from scan_yasno_20251216 import extract_today, consolidate_periods, format_time, calculate_sum, process_day, process_alarms, load_state_log, save_state_log


def test_extract_today_simple():
    data = {'a': {'dailySchedule': {'today': 1}}}
    assert extract_today(data, 'dailySchedule') == {'today': 1}


def test_consolidate_periods():
    items = [{'start': 1.0, 'end': 2.0}, {'start': 1.5, 'end': 3.0}, {'start': 4.0, 'end': 5.0}]
    res = consolidate_periods(items)
    assert res == [{'start': 1.0, 'end': 3.0}, {'start': 4.0, 'end': 5.0}]


def test_format_time():
    assert format_time('1.5') == '01:30'
    assert format_time('0') == '00:00'
    assert format_time('23.75') == '23:45'


def test_calculate_sum_and_process_day(tmp_path):
    state_file = tmp_path / "states.json"
    # ensure a clean state file
    save_state_log({}, state_file=str(state_file))
    day_data = {'title': '2025-10-23 на чомусь', 'groups': {'2': [{'start': '1.0', 'end': '2.0'}]}}
    s = calculate_sum(day_data, '2')
    assert s != ''
    msg = process_day(day_data, '2')
    assert 'Оновлення для' in msg


def test_process_alarms_no_periods(tmp_path):
    state_file = tmp_path / "states.json"
    save_state_log({}, state_file=str(state_file))
    day_data = {'title': '2025-10-23 на чомусь', 'groups': {'2': []}}
    res = process_alarms(day_data, '2')
    assert res is None
