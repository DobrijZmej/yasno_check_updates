import json

import pytest

import main
from modules.notification.rules import is_schedule_unavailable


TODAY = "2026-10-30"
TOMORROW = "2026-10-31"

WAITING = {
    "date": f"{TOMORROW}T00:00:00+02:00",
    "status": "WaitingForSchedule",
    "slots": [],
}
PUBLISHED = {
    "date": f"{TOMORROW}T00:00:00+02:00",
    "status": "ScheduleApplies",
    "slots": [
        {"start": 510, "end": 720, "type": "Definite"},
        {"start": 930, "end": 1140, "type": "Definite"},
    ],
}
REVISED = {
    **PUBLISHED,
    "slots": [
        {"start": 510, "end": 720, "type": "Definite"},
        {"start": 930, "end": 1170, "type": "Definite"},
    ],
}
NO_OUTAGES = {**WAITING, "status": "NoOutages"}
EMERGENCY = {**WAITING, "status": "EmergencyShutdowns"}
NOT_PLANNED_ALL_DAY = {
    **PUBLISHED,
    "slots": [{"start": 0, "end": 1440, "type": "NotPlanned"}],
}


@pytest.fixture
def run_bot(monkeypatch, tmp_path):
    """Run one bot pass for tomorrow's schedule and return the sent messages."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "setup_logging", lambda: None)
    monkeypatch.setattr(main, "today_str", lambda offset=0: TOMORROW if offset else TODAY)
    monkeypatch.setattr(main, "load_config", lambda: {
        "group": "12.1",
        "schedule_source": "unified",
        "use_dynamic_group": False,
        "enable_hourly_notifications": False,
        "enable_alarm_notifications": False,
        "enable_mode_notifications": False,
        "telegram_bot_token": "token",
        "telegram_chat_id": "1",
        "additional_chat_ids": "",
        "dtek_alarms_chat_id": "",
        "dtek_alarms_url": "",
        "external_api_url": "",
        "external_api_token": "",
    })
    monkeypatch.setattr(main, "load_dtek_alarms", lambda url: None)
    monkeypatch.setattr(main, "load_schedule_sources", lambda config, group: (None, None, None, {}))

    def run(day_data):
        sent = []
        monkeypatch.setattr(main, "merge_data_sources", lambda *args: (
            {TOMORROW: day_data},
            {TOMORROW: {"source": "yasno"}},
        ))
        monkeypatch.setattr(
            main,
            "send_to_multiple_chats",
            lambda token, chats, message: sent.append(message) or 1,
        )
        main.main()
        return sent

    return run


def test_pending_day_is_not_treated_as_a_stored_schedule(run_bot, tmp_path):
    assert run_bot(WAITING) == []

    state = json.loads((tmp_path / "states.json").read_text(encoding="utf-8"))
    assert f"12.1_{TOMORROW}" not in state
    assert f"12.1_{TOMORROW}_periods" not in state


def test_first_publication_after_waiting_has_no_delta(run_bot):
    run_bot(WAITING)

    sent = run_bot(PUBLISHED)

    assert len(sent) == 1
    assert sent[0].endswith("Час без світла: 7:00 (29%)")


def test_revision_of_published_schedule_shows_delta(run_bot):
    run_bot(WAITING)
    run_bot(PUBLISHED)

    sent = run_bot(REVISED)

    assert len(sent) == 1
    assert sent[0].endswith("Час без світла: 7:30 (31%), зміна: +0:30")


def test_withdrawn_schedule_keeps_previous_version_for_delta(run_bot):
    run_bot(PUBLISHED)
    run_bot(WAITING)

    sent = run_bot(REVISED)

    assert sent[0].endswith("Час без світла: 7:30 (31%), зміна: +0:30")


def test_confirmed_absence_of_outages_is_still_a_real_baseline(run_bot):
    run_bot(NO_OUTAGES)

    sent = run_bot(PUBLISHED)

    assert sent[0].endswith("Час без світла: 7:00 (29%), зміна: +7:00")


def test_first_publication_after_emergency_has_no_delta(run_bot):
    run_bot(EMERGENCY)

    sent = run_bot(PUBLISHED)

    assert len(sent) == 1
    assert sent[0].endswith("Час без світла: 7:00 (29%)")


def test_unchanged_schedule_is_not_resent_after_emergency(run_bot):
    run_bot(PUBLISHED)
    run_bot(EMERGENCY)

    assert run_bot(PUBLISHED) == []


def test_changed_schedule_after_emergency_shows_delta_from_last_schedule(run_bot):
    run_bot(PUBLISHED)
    run_bot(EMERGENCY)

    sent = run_bot(REVISED)

    assert sent[0].endswith("Час без світла: 7:30 (31%), зміна: +0:30")


def test_published_day_without_outages_is_a_real_baseline(run_bot):
    run_bot(NOT_PLANNED_ALL_DAY)

    sent = run_bot(PUBLISHED)

    assert sent[0].endswith("Час без світла: 7:00 (29%), зміна: +7:00")


@pytest.mark.parametrize("status", ["WaitingForSchedule", "EmergencyShutdowns", "Unknown"])
def test_empty_day_without_confirmed_status_is_unavailable(status):
    assert is_schedule_unavailable({"status": status, "slots": []})
    assert is_schedule_unavailable(
        {"status": status, "slots": [{"start": 0, "end": 1440, "type": "NotPlanned"}]}
    )


def test_outages_or_confirmed_status_make_schedule_available():
    assert not is_schedule_unavailable({**PUBLISHED, "status": "WaitingForSchedule"})
    assert not is_schedule_unavailable({**PUBLISHED, "status": "EmergencyShutdowns"})
    assert not is_schedule_unavailable(NO_OUTAGES)
    assert not is_schedule_unavailable(NOT_PLANNED_ALL_DAY)
    assert not is_schedule_unavailable({"slots": []})
