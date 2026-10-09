from datetime import datetime

from modules.data_sources.svitlo_monitor_loader import parse_svitlo_monitor_data
from modules.processing.data_merger import merge_data_sources
from modules.notification.rules import should_send_schedule
from modules.notification.notifier import format_schedule_message
import pytest


def test_parse_unified_schedules_and_statuses():
    payload = {
        "schema_version": 4,
        "schedules": {
            "yasno": {
                "stale": False,
                "groups": {
                    "8.1": {
                        "source_updated_at": "2026-10-09T00:43:15+00:00",
                        "today": {
                            "date": "2026-10-09T00:00:00+03:00",
                            "status": "ScheduleApplies",
                            "slots": [
                                {"start": "00:00", "end": "12:00", "status": "NotPlanned"},
                                {"start": "12:00", "end": "15:30", "status": "Definite"},
                            ],
                        },
                    }
                },
            },
            "dtek": {
                "group": "GPV8.1",
                "stale": False,
                "today": {
                    "date": "2026-10-09",
                    "applies": True,
                    "slots": [
                        {"start": "00:00", "end": "01:00", "status": "yes"},
                        {"start": "01:00", "end": "02:00", "status": "no"},
                        {"start": "02:00", "end": "03:00", "status": "first"},
                        {"start": "03:00", "end": "04:00", "status": "second"},
                        {"start": "04:00", "end": "05:00", "status": "mfirst"},
                    ],
                },
            },
        },
        "current_mode": {"dtek": {"current": {"status": "scheduled"}, "history": []}},
    }

    result = parse_svitlo_monitor_data(payload, "8.1")

    assert result["yasno_data"]["2026-10-09"]["slots"] == [
        {"start": 0, "end": 720, "type": "NotPlanned"},
        {"start": 720, "end": 930, "type": "Definite"},
    ]
    dtek_slots = result["dtek_schedule_data"]["dates"]["2026-10-09"]["slots"]
    assert dtek_slots == [
        {"start": 0, "end": 60, "type": "NotPlanned"},
        {"start": 60, "end": 120, "type": "Definite"},
        {"start": 120, "end": 150, "type": "Definite"},
        {"start": 150, "end": 180, "type": "NotPlanned"},
        {"start": 180, "end": 210, "type": "NotPlanned"},
        {"start": 210, "end": 240, "type": "Definite"},
        {"start": 240, "end": 270, "type": "Possible"},
        {"start": 270, "end": 300, "type": "NotPlanned"},
    ]


def test_parse_ignores_stale_schedules_and_dtek_group_mismatch():
    payload = {
        "schedules": {
            "yasno": {"stale": True, "groups": {"8.1": {"today": {}}}},
            "dtek": {
                "group": "GPV9.1",
                "stale": False,
                "today": {"date": "2026-10-09", "slots": []},
            },
        }
    }

    result = parse_svitlo_monitor_data(payload, "8.1")

    assert result["yasno_data"] is None
    assert result["dtek_schedule_data"] is None


def test_merger_accepts_normalized_dtek_slots():
    today = datetime.now().strftime("%Y-%m-%d")
    dtek_data = {
        "dates": {
            today: {
                "date": f"{today}T00:00:00+03:00",
                "status": "ScheduleApplies",
                "slots": [{"start": 480, "end": 600, "type": "Definite"}],
                "update_time": "2026-10-09T07:00:00+03:00",
            }
        },
        "update_time": "2026-10-09T07:00:00+03:00",
    }

    merged, sources = merge_data_sources(None, dtek_data, None)

    assert merged[today]["slots"] == dtek_data["dates"][today]["slots"]
    assert sources[today]["source"] == "dtek"


def test_possible_outages_survive_merger_and_are_sendable():
    today = datetime.now().strftime("%Y-%m-%d")
    dtek_data = {
        "dates": {
            today: {
                "date": f"{today}T00:00:00+03:00",
                "status": "ScheduleApplies",
                "slots": [{"start": 480, "end": 540, "type": "Possible"}],
            }
        }
    }

    merged, _ = merge_data_sources(None, dtek_data, None)

    assert should_send_schedule("8.1", today, True, {}, merged[today])
    message = format_schedule_message(today, merged[today], "8.1", "сьогодні")
    assert "Можливі відключення" in message
    assert "08:00 - 09:00" in message


def test_dtek_schedule_without_apply_flag_is_not_used():
    payload = {
        "schedules": {
            "dtek": {
                "group": "GPV8.1",
                "stale": False,
                "today": {
                    "date": "2026-10-09",
                    "applies": False,
                    "slots": [{"start": "00:00", "end": "24:00", "status": "unknown"}],
                },
            }
        }
    }

    result = parse_svitlo_monitor_data(payload, "8.1")

    assert result["dtek_schedule_data"] is None


def test_unsupported_schema_version_is_rejected():
    with pytest.raises(ValueError, match="Unsupported svitlo monitor schema version"):
        parse_svitlo_monitor_data({"schema_version": 5, "schedules": {}}, "8.1")
