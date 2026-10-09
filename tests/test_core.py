from modules.notification.notifier import consolidate_periods, format_time
from modules.processing.state_manager import load_state, save_state


def test_consolidate_periods():
    items = [{'start': 1.0, 'end': 2.0}, {'start': 1.5, 'end': 3.0}, {'start': 4.0, 'end': 5.0}]
    res = consolidate_periods(items)
    assert res == [{'start': 1.0, 'end': 3.0}, {'start': 4.0, 'end': 5.0}]


def test_format_time():
    assert format_time(90) == '01:30'
    assert format_time(0) == '00:00'
    assert format_time(1425) == '23:45'


def test_state_roundtrip(tmp_path):
    state_file = tmp_path / "states.json"
    state = {"8.1_2026-10-09": "hash"}

    save_state(state, state_file=str(state_file))

    assert load_state(state_file=str(state_file)) == state
