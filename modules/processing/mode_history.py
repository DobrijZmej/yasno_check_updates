"""Track provider mode transitions and the duration of completed modes."""

from copy import deepcopy
from datetime import datetime
from html import escape
import logging

logger = logging.getLogger(__name__)


MODE_LABELS = {
    "emergency": "аварійний",
    "scheduled": "плановий",
    "no_outages": "відключень немає",
    "waiting_for_schedule": "очікування графіка",
    "unknown": "невідомий",
}

PROVIDER_LABELS = {
    "dtek": "DTEK",
    "yasno": "YASNO",
    "ukrenergo": "Укренерго",
}


def _parse_timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _event_key(status, changed_at):
    return f"{changed_at.isoformat()}|{status}"


def _read_comment(item):
    for field in ("message", "raw_status"):
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _read_provider_history(provider_data):
    current = provider_data.get("current")
    if (
        not isinstance(current, dict)
        or provider_data.get("stale")
        or current.get("stale")
        or provider_data.get("error")
        or current.get("error")
    ):
        return []

    events = []
    seen = set()
    for item in provider_data.get("history", []):
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        changed_at = _parse_timestamp(item.get("changed_at"))
        if status not in MODE_LABELS or changed_at is None:
            continue
        key = _event_key(status, changed_at)
        if key in seen:
            continue
        seen.add(key)
        events.append({
            "status": status,
            "changed_at": changed_at,
            "key": key,
            "comment": _read_comment(item),
        })

    events.sort(key=lambda event: event["changed_at"])
    if (
        events
        and events[-1]["status"] == current.get("status")
        and not events[-1]["comment"]
    ):
        events[-1]["comment"] = _read_comment(current)
    return events


def _add_duration(provider_state, status, seconds):
    if seconds <= 0:
        return
    durations = provider_state.setdefault("durations_seconds", {})
    durations[status] = durations.get(status, 0) + int(seconds)


def advance_mode_history(mode_data, previous_state=None, now=None):
    """Return new tracker state and transitions newer than the stored cursors.

    The first observation seeds the cursor from the feed history without sending
    old notifications. Completed durations visible in that initial history are
    included in the local totals.
    """
    next_state = deepcopy(previous_state or {})
    transitions = []

    for provider, provider_data in mode_data.items():
        if provider not in PROVIDER_LABELS or not isinstance(provider_data, dict):
            continue
        events = _read_provider_history(provider_data)
        if not events:
            continue

        provider_state = next_state.setdefault(provider, {"durations_seconds": {}})
        cursor = provider_state.get("last_event_key")

        if not cursor:
            for previous, current in zip(events, events[1:]):
                _add_duration(
                    provider_state,
                    previous["status"],
                    (current["changed_at"] - previous["changed_at"]).total_seconds(),
                )
            latest = events[-1]
            provider_state["last_event_key"] = latest["key"]
            provider_state["current_status"] = latest["status"]
            provider_state["current_since"] = latest["changed_at"].isoformat()
            continue

        cursor_index = next(
            (index for index, event in enumerate(events) if event["key"] == cursor),
            None,
        )
        if cursor_index is None:
            logger.warning("Mode history cursor for %s expired; resyncing without replay", provider)
            latest = events[-1]
            provider_state["last_event_key"] = latest["key"]
            provider_state["current_status"] = latest["status"]
            provider_state["current_since"] = latest["changed_at"].isoformat()
            continue

        for index in range(cursor_index + 1, len(events)):
            previous = events[index - 1]
            current = events[index]
            duration_seconds = int(
                (current["changed_at"] - previous["changed_at"]).total_seconds()
            )
            _add_duration(provider_state, previous["status"], duration_seconds)
            if previous["status"] != current["status"]:
                observed_at = now or datetime.now(tz=current["changed_at"].tzinfo)
                transitions.append({
                    "provider": provider,
                    "previous_status": previous["status"],
                    "status": current["status"],
                    "changed_at": current["changed_at"],
                    "duration_seconds": max(duration_seconds, 0),
                    "total_seconds": provider_state["durations_seconds"].get(previous["status"], 0),
                    "elapsed_since_change_seconds": max(
                        int((observed_at - current["changed_at"]).total_seconds()),
                        0,
                    ),
                    "comment": current.get("comment"),
                })

        latest = events[-1]
        provider_state["last_event_key"] = latest["key"]
        provider_state["current_status"] = latest["status"]
        provider_state["current_since"] = latest["changed_at"].isoformat()

    transitions.sort(key=lambda event: event["changed_at"])
    return next_state, transitions


def _format_duration(seconds):
    minutes = max(seconds, 0) // 60
    days, minutes = divmod(minutes, 24 * 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if days:
        parts.append(f"{days} д")
    if hours:
        parts.append(f"{hours} год")
    if minutes or not parts:
        parts.append(f"{minutes} хв")
    return " ".join(parts)


def format_mode_transition(transition):
    provider = PROVIDER_LABELS[transition["provider"]]
    previous = MODE_LABELS[transition["previous_status"]]
    current = MODE_LABELS[transition["status"]]
    changed_at = transition["changed_at"].strftime("%d.%m %H:%M")
    duration = _format_duration(transition["duration_seconds"])
    total_duration = _format_duration(transition.get("total_seconds", 0))
    elapsed = _format_duration(transition.get("elapsed_since_change_seconds", 0))
    result = (
        f"🔄 <b>{provider}</b>: режим змінився: {previous} → {current}.\n"
        f"Попередній режим тривав {duration}; сумарно за доступною історією: {total_duration}.\n"
        f"Час зміни: {changed_at}. Після перемикання минуло {elapsed}."
    )
    comment = transition.get("comment")
    if transition["provider"] == "dtek" and comment:
        result += f"\n\n<b>Коментар DTEK:</b>\n{escape(comment, quote=False)}"
    return result
