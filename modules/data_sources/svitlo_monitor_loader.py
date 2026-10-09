"""Load and normalize schedules and mode history from the unified feed."""

import logging

import requests

logger = logging.getLogger(__name__)

SUPPORTED_SCHEMA_VERSIONS = {4}


def _time_to_minutes(value):
    if not isinstance(value, str):
        raise ValueError(f"Invalid time value: {value!r}")

    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time value: {value!r}")

    hour, minute = (int(part) for part in parts)
    total = hour * 60 + minute
    if minute not in range(60) or total not in range(1441):
        raise ValueError(f"Invalid time value: {value!r}")
    return total


def _day_date(day):
    value = day.get("date")
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError("Schedule day is missing a valid date")
    return value[:10]


def _normalize_yasno_day(day, update_time=None):
    if not isinstance(day, dict):
        return None

    slots = []
    source_slots = day.get("slots", [])
    if not isinstance(source_slots, list):
        raise ValueError("YASNO schedule slots must be a list")
    for slot in source_slots:
        if not isinstance(slot, dict):
            raise ValueError("YASNO schedule slot must be an object")
        status = slot.get("status")
        start = _time_to_minutes(slot["start"])
        end = _time_to_minutes(slot["end"])
        if start >= end:
            raise ValueError("YASNO schedule slot has an invalid interval")
        slots.append({
            "start": start,
            "end": end,
            "type": status if status in {"Definite", "Possible", "NotPlanned"} else "Unknown",
        })

    normalized = {
        "date": day["date"],
        "status": day.get("status", "Unknown"),
        "slots": slots,
    }
    if update_time:
        normalized["update_time"] = update_time
    return normalized


def _normalize_dtek_slots(day):
    normalized = []
    source_slots = day.get("slots", [])
    if not isinstance(source_slots, list):
        raise ValueError("DTEK schedule slots must be a list")
    for slot in source_slots:
        if not isinstance(slot, dict):
            raise ValueError("DTEK schedule slot must be an object")
        start = _time_to_minutes(slot["start"])
        end = _time_to_minutes(slot["end"])
        if start >= end:
            raise ValueError("DTEK schedule slot has an invalid interval")
        status = slot.get("status")

        if status == "yes":
            slot_types = [(start, end, "NotPlanned")]
        elif status == "no":
            slot_types = [(start, end, "Definite")]
        elif status == "first":
            midpoint = (start + end) // 2
            slot_types = [(start, midpoint, "Definite"), (midpoint, end, "NotPlanned")]
        elif status == "second":
            midpoint = (start + end) // 2
            slot_types = [(start, midpoint, "NotPlanned"), (midpoint, end, "Definite")]
        elif status == "maybe":
            slot_types = [(start, end, "Possible")]
        elif status == "mfirst":
            midpoint = (start + end) // 2
            slot_types = [(start, midpoint, "Possible"), (midpoint, end, "NotPlanned")]
        elif status == "msecond":
            midpoint = (start + end) // 2
            slot_types = [(start, midpoint, "NotPlanned"), (midpoint, end, "Possible")]
        else:
            slot_types = [(start, end, "Unknown")]

        normalized.extend(
            {"start": start_time, "end": end_time, "type": slot_type}
            for start_time, end_time, slot_type in slot_types
            if start_time < end_time
        )

    return normalized


def parse_svitlo_monitor_data(payload, group):
    """Return the unified response as inputs accepted by the existing merger."""
    if not isinstance(payload, dict) or not isinstance(payload.get("schedules"), dict):
        raise ValueError("Unexpected svitlo monitor response structure")

    schema_version = payload.get("schema_version")
    if schema_version is not None and schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"Unsupported svitlo monitor schema version: {schema_version!r}")
    if payload.get("schema_version") not in (None, 4):
        raise ValueError(f"Unsupported svitlo monitor schema: {payload['schema_version']}")

    schedules = payload["schedules"]
    yasno_data = {}
    yasno = schedules.get("yasno", {})
    if isinstance(yasno, dict) and not yasno.get("stale") and not yasno.get("error"):
        groups = yasno.get("groups", {})
        group_data = groups.get(group) if isinstance(groups, dict) else None
        if group_data is None and yasno.get("group") == group:
            group_data = yasno
        if group_data is None:
            logger.warning("YASNO group %s is absent from the unified feed", group)
        if isinstance(group_data, dict):
            update_time = group_data.get("source_updated_at") or yasno.get("source_updated_at")
            for day_key in ("today", "tomorrow"):
                day = group_data.get(day_key)
                if day:
                    normalized = _normalize_yasno_day(day, update_time)
                    yasno_data[_day_date(normalized)] = normalized

    dtek_schedule_data = None
    dtek = schedules.get("dtek", {})
    expected_dtek_group = f"GPV{group}" if "." in group else f"GPV6.{group}"
    if (
        isinstance(dtek, dict)
        and dtek.get("group") == expected_dtek_group
        and not dtek.get("stale")
        and not dtek.get("error")
    ):
        day = dtek.get("today")
        if isinstance(day, dict) and day.get("applies", True):
            date_str = _day_date(day)
            dtek_schedule_data = {
                "dates": {
                    date_str: {
                        "date": day["date"],
                        "status": "ScheduleApplies",
                        "slots": _normalize_dtek_slots(day),
                        "update_time": dtek.get("source_updated_at") or dtek.get("fetched_at", ""),
                    }
                },
                "update_time": dtek.get("source_updated_at") or dtek.get("fetched_at", ""),
            }

    mode_data = payload.get("current_mode", {})
    if not isinstance(mode_data, dict):
        mode_data = {}

    return {
        "yasno_data": yasno_data or None,
        "dtek_schedule_data": dtek_schedule_data,
        "mode_data": mode_data,
        "schema_version": payload.get("schema_version"),
        "updated_at": payload.get("updated_at"),
    }


def load_svitlo_monitor_data(url, group):
    """Fetch and parse the unified outage and mode feed."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return parse_svitlo_monitor_data(response.json(), group)
    except requests.exceptions.RequestException as exc:
        logger.error("Unified outage feed request failed: %s", exc)
    except (ValueError, KeyError, TypeError) as exc:
        logger.error("Unified outage feed parsing failed: %s", exc)
    return None
