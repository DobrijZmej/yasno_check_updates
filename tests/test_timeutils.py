from datetime import datetime, timezone

from modules.timeutils import from_timestamp_kyiv, to_kyiv


def test_dtek_midnight_timestamp_maps_to_kyiv_date():
    # DTEK віддає timestamp київської півночі; у UTC це ще попередня доба
    timestamp = int(datetime(2026, 10, 9, 21, 0, tzinfo=timezone.utc).timestamp())

    assert from_timestamp_kyiv(timestamp).strftime('%Y-%m-%d') == '2026-10-10'


def test_utc_time_after_kyiv_midnight_has_kyiv_date():
    utc_time = datetime(2026, 1, 15, 23, 30, tzinfo=timezone.utc)

    kyiv_time = to_kyiv(utc_time)

    assert kyiv_time.date().isoformat() == '2026-01-16'
    assert kyiv_time.hour == 1
