from datetime import datetime

from modules.processing.mode_history import advance_mode_history, format_mode_transition


def test_initial_mode_history_seeds_cursor_without_old_notifications():
    mode_data = {
        "dtek": {
            "current": {"status": "scheduled", "stale": False},
            "history": [
                {"status": "emergency", "changed_at": "2026-10-09T06:00:00+03:00"},
                {"status": "scheduled", "changed_at": "2026-10-09T10:00:00+03:00"},
            ],
        }
    }

    state, transitions = advance_mode_history(mode_data)

    assert transitions == []
    assert state["dtek"]["current_status"] == "scheduled"
    assert state["dtek"]["durations_seconds"]["emergency"] == 4 * 60 * 60


def test_new_mode_transition_reports_episode_and_accumulated_duration():
    previous_state = {
        "dtek": {
            "last_event_key": "2026-10-09T10:00:00+03:00|scheduled",
            "current_status": "scheduled",
            "current_since": "2026-10-09T10:00:00+03:00",
            "durations_seconds": {"scheduled": 600},
        }
    }
    mode_data = {
        "dtek": {
            "current": {"status": "no_outages", "stale": False},
            "history": [
                {"status": "emergency", "changed_at": "2026-10-09T06:00:00+03:00"},
                {"status": "scheduled", "changed_at": "2026-10-09T10:00:00+03:00"},
                {
                    "status": "no_outages",
                    "changed_at": "2026-10-09T11:30:00+03:00",
                    "message": "Графік завершено <терміново> & світло повернуто.",
                },
            ],
        }
    }

    state, transitions = advance_mode_history(
        mode_data,
        previous_state,
        now=datetime.fromisoformat("2026-10-09T11:37:30+03:00"),
    )

    assert len(transitions) == 1
    assert transitions[0]["previous_status"] == "scheduled"
    assert transitions[0]["status"] == "no_outages"
    assert transitions[0]["duration_seconds"] == 90 * 60
    assert transitions[0]["total_seconds"] == 100 * 60
    assert transitions[0]["elapsed_since_change_seconds"] == 7 * 60 + 30
    message = format_mode_transition(transitions[0])
    assert "Минула зміна була 1 год 30 хв тому" in message
    assert "Час зміни" not in message
    assert "сумарно" not in message
    assert "+0300" not in message
    assert "💬 <b>Коментар ДТЕК:</b>" in message
    assert "&lt;терміново&gt; &amp;" in message
    assert state["dtek"]["durations_seconds"]["scheduled"] == 100 * 60


def test_latest_dtek_current_comment_is_used_when_history_has_none():
    previous_state = {
        "dtek": {
            "last_event_key": "2026-10-09T10:00:00+03:00|scheduled",
            "current_status": "scheduled",
            "current_since": "2026-10-09T10:00:00+03:00",
            "durations_seconds": {},
        }
    }
    mode_data = {
        "dtek": {
            "current": {
                "status": "emergency",
                "stale": False,
                "raw_status": "Застосовані аварійні відключення.",
            },
            "history": [
                {"status": "scheduled", "changed_at": "2026-10-09T10:00:00+03:00"},
                {"status": "emergency", "changed_at": "2026-10-09T12:00:00+03:00"},
            ],
        }
    }

    _, transitions = advance_mode_history(
        mode_data,
        previous_state,
        now=datetime.fromisoformat("2026-10-09T12:03:00+03:00"),
    )

    assert transitions[0]["comment"] == "Застосовані аварійні відключення."
    message = format_mode_transition(transitions[0])
    assert "🚨 <b>ДТЕК</b>: У Києві екстрені відключення. Графіки не діють" in message
    assert "Минула зміна була 2 год тому" in message


def test_yasno_scheduled_transition_uses_success_emoji_and_short_text():
    transition = {
        "provider": "yasno",
        "previous_status": "emergency",
        "status": "scheduled",
        "changed_at": datetime.fromisoformat("2026-10-09T11:13:00+03:00"),
        "duration_seconds": 2 * 60 * 60 + 47 * 60,
    }

    assert format_mode_transition(transition) == (
        "✅ <b>YASNO</b>: режим змінився: аварійний → плановий.\n"
        "Минула зміна була 2 год 47 хв тому"
    )


def test_dtek_emergency_cancellation_has_dedicated_headline():
    transition = {
        "provider": "dtek",
        "previous_status": "emergency",
        "status": "scheduled",
        "changed_at": datetime.fromisoformat("2026-10-09T13:00:00+03:00"),
        "duration_seconds": 45 * 60,
    }

    message = format_mode_transition(transition)

    assert message.startswith("✅ <b>ДТЕК</b>: Екстрені відключення скасовано")


def test_stale_provider_does_not_advance_mode_cursor():
    previous_state = {"dtek": {"last_event_key": "old-cursor"}}
    mode_data = {
        "dtek": {
            "current": {"status": "scheduled", "stale": True},
            "history": [
                {"status": "scheduled", "changed_at": "2026-10-09T10:00:00+03:00"},
            ],
        }
    }

    state, transitions = advance_mode_history(mode_data, previous_state)

    assert transitions == []
    assert state == previous_state


def test_future_only_announcement_keeps_previous_active_mode():
    previous_state = {
        "dtek": {
            "last_event_key": "2026-10-09T10:00:00+03:00|scheduled",
            "current_status": "scheduled",
            "current_since": "2026-10-09T10:00:00+03:00",
            "durations_seconds": {"scheduled": 3600},
        }
    }
    future_message = (
        "Шановні клієнти! За наказом НЕК Укренерго 10.10 діють "
        "стабілізаційні відключення електроенергії."
    )
    mode_data = {
        "dtek": {
            "current": {
                "status": "no_outages",
                "observed_at": "2026-10-09T20:29:02+03:00",
                "raw_status": future_message,
                "classification": {
                    "temporal_schema": 1,
                    "active_from": None,
                    "active_until": None,
                    "status_during_window": None,
                    "status_outside_window": None,
                },
            },
            "history": [
                {
                    "status": "scheduled",
                    "changed_at": "2026-10-09T10:00:00+03:00",
                },
                {
                    "status": "no_outages",
                    "changed_at": "2026-10-09T20:29:02+03:00",
                    "raw_status": future_message,
                },
            ],
        }
    }

    state, transitions = advance_mode_history(mode_data, previous_state)

    assert transitions == []
    ignored_key = "2026-10-09T20:29:02+03:00|no_outages"
    assert state["dtek"]["current_status"] == "scheduled"
    assert state["dtek"]["last_event_key"] == previous_state["dtek"]["last_event_key"]
    assert state["dtek"]["ignored_event_keys"] == [ignored_key]

    # A refreshed observation on the announced day must not activate the
    # status that was classified for the previous day.
    mode_data["dtek"]["current"]["observed_at"] = "2026-10-10T00:05:00+03:00"
    refreshed_state, refreshed_transitions = advance_mode_history(
        mode_data,
        state,
    )
    assert refreshed_transitions == []
    assert refreshed_state["dtek"]["current_status"] == "scheduled"
    assert refreshed_state["dtek"]["ignored_event_keys"] == [ignored_key]


def test_ignored_future_event_stays_filtered_after_corrective_event_is_appended():
    ignored_key = "2026-10-09T20:29:02+03:00|no_outages"
    previous_state = {
        "dtek": {
            "last_event_key": "2026-10-09T10:00:00+03:00|scheduled",
            "current_status": "scheduled",
            "current_since": "2026-10-09T10:00:00+03:00",
            "durations_seconds": {"scheduled": 3600},
        }
    }
    mode_data = {
        "dtek": {
            "current": {
                "status": "scheduled",
                "observed_at": "2026-10-09T20:30:02+03:00",
                "message": "Поточний режим залишається плановим.",
            },
            "history": [
                {
                    "status": "scheduled",
                    "changed_at": "2026-10-09T10:00:00+03:00",
                },
                {
                    "status": "no_outages",
                    "changed_at": "2026-10-09T20:29:02+03:00",
                    "observed_at": "2026-10-09T20:29:02+03:00",
                    "message": "10.10 діють стабілізаційні відключення.",
                    "classification": {
                        "temporal_schema": 1,
                        "active_from": None,
                        "active_until": None,
                        "status_during_window": None,
                        "status_outside_window": None,
                    },
                },
                {
                    "status": "scheduled",
                    "changed_at": "2026-10-09T20:30:02+03:00",
                },
            ],
        }
    }

    state, transitions = advance_mode_history(mode_data, previous_state)

    assert transitions == []
    assert state["dtek"]["current_status"] == "scheduled"
    assert state["dtek"]["last_event_key"] == (
        "2026-10-09T20:30:02+03:00|scheduled"
    )
    assert state["dtek"]["ignored_event_keys"] == [ignored_key]


def test_announcement_for_observation_date_can_change_active_mode():
    previous_state = {
        "dtek": {
            "last_event_key": "2026-10-09T10:00:00+03:00|scheduled",
            "current_status": "scheduled",
            "current_since": "2026-10-09T10:00:00+03:00",
            "durations_seconds": {},
        }
    }
    current_message = "09.10 стабілізаційні відключення завершено."
    mode_data = {
        "dtek": {
            "current": {
                "status": "no_outages",
                "observed_at": "2026-10-09T20:29:02+03:00",
                "message": current_message,
                "classification": {
                    "temporal_schema": 1,
                    "active_from": None,
                    "active_until": None,
                    "status_during_window": None,
                    "status_outside_window": None,
                },
            },
            "history": [
                {
                    "status": "scheduled",
                    "changed_at": "2026-10-09T10:00:00+03:00",
                },
                {
                    "status": "no_outages",
                    "changed_at": "2026-10-09T20:29:02+03:00",
                    "message": current_message,
                },
            ],
        }
    }

    state, transitions = advance_mode_history(mode_data, previous_state)

    assert len(transitions) == 1
    assert transitions[0]["status"] == "no_outages"
    assert state["dtek"]["current_status"] == "no_outages"
