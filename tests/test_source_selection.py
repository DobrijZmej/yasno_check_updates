import pytest

import main


def _config(source):
    return {
        "schedule_source": source,
        "svitlo_monitor_url": "https://unified.invalid/data.json",
        "yasno_url": "https://yasno.invalid/data.json",
        "dtek_url": "https://dtek.invalid/data.json",
        "dtek_alarms_url": "https://alarms.invalid/data.json",
    }


def test_unified_source_does_not_call_legacy_loaders(monkeypatch):
    unified = {
        "yasno_data": {"2026-10-09": {"slots": []}},
        "dtek_schedule_data": {"dates": {}},
        "mode_data": {"dtek": {}},
    }
    monkeypatch.setattr(main, "load_svitlo_monitor_data", lambda url, group: unified)

    def unexpected_call(*args, **kwargs):
        raise AssertionError("legacy loader must not be called in unified mode")

    monkeypatch.setattr(main, "load_yasno_data", unexpected_call)
    monkeypatch.setattr(main, "load_dtek_schedule_data", unexpected_call)
    monkeypatch.setattr(main, "load_dtek_fact_data", unexpected_call)

    result = main.load_schedule_sources(_config("unified"), "8.1")

    assert result == (
        unified["yasno_data"],
        unified["dtek_schedule_data"],
        None,
        unified["mode_data"],
    )


def test_legacy_source_is_only_selected_explicitly(monkeypatch):
    monkeypatch.setattr(
        main,
        "load_svitlo_monitor_data",
        lambda *args: (_ for _ in ()).throw(
            AssertionError("unified loader must not be called in legacy mode")
        ),
    )
    monkeypatch.setattr(main, "load_yasno_data", lambda url, group: {"yasno": group})
    monkeypatch.setattr(main, "load_dtek_schedule_data", lambda url, group: {"dtek": group})
    monkeypatch.setattr(main, "load_dtek_fact_data", lambda url, group: {"fact": group})

    result = main.load_schedule_sources(_config("legacy"), "8.1")

    assert result == (
        {"yasno": "8.1"},
        {"dtek": "8.1"},
        {"fact": "8.1"},
        {},
    )


def test_unknown_source_is_rejected():
    with pytest.raises(ValueError, match="Unsupported SCHEDULE_SOURCE"):
        main.load_schedule_sources(_config("automatic"), "8.1")
