from modules.processing.state_manager import (
    _calculate_legacy_schedule_hash,
    calculate_outage_duration,
    calculate_schedule_hash,
    get_stored_schedule_slots,
    is_changed,
    normalize_schedule_slots,
    update_state,
)


def test_equivalent_yasno_and_fragmented_dtek_schedules_have_same_hash():
    yasno = {
        "date": "2026-10-09T00:00:00+03:00",
        "slots": [
            {"start": 0, "end": 720, "type": "NotPlanned"},
            {"start": 720, "end": 930, "type": "Definite"},
            {"start": 930, "end": 1260, "type": "NotPlanned"},
            {"start": 1260, "end": 1440, "type": "Definite"},
        ],
    }
    dtek = {
        "date": "2026-10-09T00:00:00",
        "slots": [
            {"start": 1260, "end": 1320, "type": "Definite"},
            {"start": 720, "end": 780, "type": "Definite"},
            {"start": 900, "end": 930, "type": "Definite"},
            {"start": 1320, "end": 1380, "type": "Definite"},
            {"start": 780, "end": 840, "type": "Definite"},
            {"start": 1380, "end": 1440, "type": "Definite"},
            {"start": 840, "end": 900, "type": "Definite"},
        ],
    }

    assert calculate_schedule_hash(yasno) == calculate_schedule_hash(dtek)
    assert normalize_schedule_slots(dtek["slots"]) == [
        {"start": 720, "end": 930, "type": "Definite"},
        {"start": 1260, "end": 1440, "type": "Definite"},
    ]


def test_real_schedule_change_still_changes_hash():
    original = {
        "date": "2026-10-09T00:00:00+03:00",
        "slots": [{"start": 720, "end": 930, "type": "Definite"}],
    }
    changed = {
        "date": "2026-10-09",
        "slots": [{"start": 720, "end": 960, "type": "Definite"}],
    }

    assert calculate_schedule_hash(original) != calculate_schedule_hash(changed)


def test_legacy_hash_is_migrated_without_false_change():
    day_data = {
        "date": "2026-10-09T00:00:00+03:00",
        "slots": [
            {"start": 720, "end": 780, "type": "Definite"},
            {"start": 780, "end": 930, "type": "Definite"},
        ],
    }
    state = {"8.1_2026-10-09": _calculate_legacy_schedule_hash(day_data)}

    changed, _, new_hash = is_changed(
        "8.1", "2026-10-09", day_data, state, source="dtek"
    )

    assert changed is False
    assert state["8.1_2026-10-09"] == new_hash


def test_periods_are_stored_canonically_and_duration_does_not_double_count():
    periods = [
        {"start": 720, "end": 780, "type": "Definite"},
        {"start": 780, "end": 930, "type": "Definite"},
        {"start": 900, "end": 960, "type": "Possible"},
    ]
    state = {}

    update_state("8.1", "2026-10-09", "hash", state, periods=periods)
    stored = get_stored_schedule_slots(state, "8.1", "2026-10-09")

    assert stored == [
        {"start": 720, "end": 930, "type": "Definite"},
        {"start": 900, "end": 960, "type": "Possible"},
    ]
    assert calculate_outage_duration(stored) == 240
