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
    assert "1 год 30 хв" in message
    assert "Після перемикання минуло 7 хв" in message
    assert "Час зміни: 09.10 11:30." in message
    assert "+0300" not in message
    assert "<b>Коментар DTEK:</b>" in message
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
    assert "Після перемикання минуло 3 хв" in format_mode_transition(transitions[0])


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
