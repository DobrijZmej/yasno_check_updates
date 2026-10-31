import json
from datetime import timedelta

from modules.notification.external_api import consolidate_periods as api_consolidate
from modules.notification.hourly_notifications import consolidate_periods as hourly_consolidate
from modules.notification.notifier import consolidate_periods as notifier_consolidate
from modules.notification.rules import should_send_alarm
from modules.processing import state_manager
from modules.processing.data_merger import convert_dtek_hours_to_slots
from modules.processing.state_manager import (
    cleanup_old_states,
    consolidate_periods,
    load_state,
    mark_alarm_seen,
    save_state,
)
from modules.timeutils import now_kyiv


ALARM_KEY = ("Аварія", "10:00 31.10.2026", "18:00 31.10.2026")


def test_failed_save_keeps_previous_state_and_leaves_no_temp_file(tmp_path):
    state_file = tmp_path / "states.json"
    save_state({"key": "old"}, state_file=str(state_file))

    save_state({"key": object()}, state_file=str(state_file))

    assert load_state(state_file=str(state_file)) == {"key": "old"}
    assert [path.name for path in tmp_path.iterdir()] == ["states.json"]


def test_save_replaces_state_atomically(tmp_path, monkeypatch):
    state_file = tmp_path / "states.json"
    save_state({"key": "old"}, state_file=str(state_file))
    seen_before_replace = []
    real_replace = state_manager.os.replace

    def checking_replace(source, target):
        seen_before_replace.append(json.loads(state_file.read_text(encoding="utf-8")))
        real_replace(source, target)

    monkeypatch.setattr(state_manager.os, "replace", checking_replace)

    save_state({"key": "new"}, state_file=str(state_file))

    assert seen_before_replace == [{"key": "old"}]
    assert load_state(state_file=str(state_file)) == {"key": "new"}


def test_recent_alarm_survives_cleanup_and_is_not_resent():
    state = {}
    mark_alarm_seen(ALARM_KEY, state)

    cleanup_old_states(state, days_to_keep=7)

    assert not should_send_alarm(str(ALARM_KEY), state)


def test_alarm_not_seen_for_longer_than_retention_is_removed():
    key = f"last_alarm_{ALARM_KEY}"
    state = {
        key: (now_kyiv() - timedelta(days=8)).isoformat(),
        "last_monitoring_group": "8.1",
    }

    cleanup_old_states(state, days_to_keep=7)

    assert state == {"last_monitoring_group": "8.1"}


def test_legacy_alarm_value_gets_retention_timestamp_instead_of_being_lost():
    key = f"last_alarm_{ALARM_KEY}"
    state = {key: str(ALARM_KEY)}

    cleanup_old_states(state, days_to_keep=7)

    assert key in state
    assert now_kyiv() - timedelta(minutes=1) < now_kyiv().fromisoformat(state[key])


def test_all_notification_modules_share_one_consolidation():
    assert notifier_consolidate is consolidate_periods
    assert hourly_consolidate is consolidate_periods
    assert api_consolidate is consolidate_periods


def test_legacy_dtek_outage_ends_at_midnight():
    hours = {str(hour): "yes" for hour in range(1, 25)}
    hours.update({"23": "no", "24": "no"})

    assert convert_dtek_hours_to_slots(hours) == [
        {"start": 1320, "end": 1440, "type": "Definite"},
    ]


def test_legacy_dtek_second_half_of_last_hour_ends_at_midnight():
    hours = {str(hour): "yes" for hour in range(1, 25)}
    hours["24"] = "second"

    assert convert_dtek_hours_to_slots(hours) == [
        {"start": 1410, "end": 1440, "type": "Definite"},
    ]
