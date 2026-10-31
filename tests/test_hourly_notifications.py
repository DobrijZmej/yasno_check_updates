from datetime import datetime, timedelta, timezone

import pytest

import main
from modules.notification import hourly_notifications
from modules.notification.hourly_notifications import (
    check_upcoming_events,
    format_time,
)
from modules.processing.state_manager import StateManager
from modules.timeutils import KYIV_TZ, to_kyiv


def make_manager(tmp_path):
    return StateManager(state_file=str(tmp_path / "states.json"))


def day(*periods):
    return {
        "slots": [
            {"start": start, "end": end, "type": "Definite"}
            for start, end in periods
        ],
    }


def freeze_time(monkeypatch, moment):
    monkeypatch.setattr(hourly_notifications, "now_kyiv", lambda: moment)
    monkeypatch.setattr(hourly_notifications, "get_power_status_from_ha", lambda: None)


def test_format_time_supports_end_of_day():
    assert format_time(1440) == "24:00"
    assert format_time(1441) is None


def test_restore_warning_for_outage_until_midnight_has_end_time(monkeypatch, tmp_path):
    freeze_time(monkeypatch, datetime(2026, 10, 31, 23, 5, tzinfo=KYIV_TZ))

    warning = check_upcoming_events(
        {"today": day((1200, 1440)), "tomorrow": None},
        "8.1",
        make_manager(tmp_path),
    )

    assert warning["message"] == "🟢 Очікується відновлення електроенергії з 23:30 по 24:00"


def test_morning_restore_warning_survives_cross_day_evening_outage(monkeypatch, tmp_path):
    freeze_time(monkeypatch, datetime(2026, 10, 31, 3, 5, tzinfo=KYIV_TZ))

    warning = check_upcoming_events(
        {"today": day((0, 240), (1320, 1440)), "tomorrow": day((0, 120))},
        "8.1",
        make_manager(tmp_path),
    )

    assert warning["message"] == "🟢 Очікується відновлення електроенергії з 03:30 по 04:00"


def test_warning_is_not_marked_as_sent_until_delivery(monkeypatch, tmp_path):
    freeze_time(monkeypatch, datetime(2026, 10, 31, 11, 45, tzinfo=KYIV_TZ))
    manager = make_manager(tmp_path)
    data = {"today": day((720, 840)), "tomorrow": None}

    warning = check_upcoming_events(data, "8.1", manager)

    assert warning["key"] == "hourly_outage_8.1_2026-10-31_720"
    assert not manager.get_notification_sent(warning["key"])
    assert check_upcoming_events(data, "8.1", manager) == warning


@pytest.mark.parametrize(
    "utc_moment",
    [
        # Літо: UTC+3
        datetime(2026, 7, 1, 8, 45, tzinfo=timezone.utc),
        # Зима: UTC+2
        datetime(2026, 12, 1, 9, 45, tzinfo=timezone.utc),
    ],
)
def test_warning_window_uses_kyiv_time_on_utc_server(monkeypatch, tmp_path, utc_moment):
    freeze_time(monkeypatch, to_kyiv(utc_moment))

    warning = check_upcoming_events(
        {"today": day((720, 840)), "tomorrow": None},
        "8.1",
        make_manager(tmp_path),
    )

    assert warning["message"].startswith("🔴 Попередження: відключення о 12:00")


@pytest.mark.parametrize("sent_count, expected_sent", [(0, False), (1, True)])
def test_main_marks_warning_only_after_delivery(
    monkeypatch, tmp_path, sent_count, expected_sent
):
    monkeypatch.chdir(tmp_path)
    moment = datetime(2026, 10, 31, 11, 45, tzinfo=KYIV_TZ)
    freeze_time(monkeypatch, moment)
    today = moment.strftime("%Y-%m-%d")
    tomorrow = (moment + timedelta(days=1)).strftime("%Y-%m-%d")

    monkeypatch.setattr(main, "setup_logging", lambda: None)
    monkeypatch.setattr(main, "today_str", lambda offset=0: tomorrow if offset else today)
    monkeypatch.setattr(main, "load_config", lambda: {
        "group": "8.1",
        "schedule_source": "unified",
        "use_dynamic_group": False,
        "enable_hourly_notifications": True,
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
    monkeypatch.setattr(main, "merge_data_sources", lambda *args: (
        {today: {"date": today, **day((720, 840))}},
        {today: {"source": "yasno"}},
    ))
    monkeypatch.setattr(main, "send_to_multiple_chats", lambda *args: sent_count)

    main.main()

    key = f"hourly_outage_8.1_{today}_720"
    assert (key in main.load_state()) is expected_sent
