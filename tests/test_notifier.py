from modules.notification.notifier import (
    TELEGRAM_FOOTER,
    append_telegram_footer,
    format_schedule_message,
    send_telegram_message,
)


class _SuccessfulResponse:
    def raise_for_status(self):
        return None


def test_append_telegram_footer_adds_clickable_links_once():
    message = append_telegram_footer("Тестове сповіщення")

    assert message.endswith(TELEGRAM_FOOTER)
    assert '<a href="https://t.me/+ZQZvzzIFH3c2Yzgy">Цей бот</a>' in message
    assert '<a href="https://akadem-svitlo.kiev.ua/">Сайт ЖК</a>' in message
    assert append_telegram_footer(message).count(TELEGRAM_FOOTER) == 1


def test_send_telegram_message_includes_footer(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured.update(url=url, payload=json, timeout=timeout)
        return _SuccessfulResponse()

    monkeypatch.setattr("modules.notification.notifier.requests.post", fake_post)

    assert send_telegram_message("token", "chat", "Повідомлення")
    assert captured["payload"]["text"] == f"Повідомлення\n\n{TELEGRAM_FOOTER}"
    assert captured["payload"]["parse_mode"] == "HTML"
    assert captured["payload"]["link_preview_options"] == {"is_disabled": True}


def test_schedule_message_shows_total_share_and_increase_after_intervals():
    message = format_schedule_message(
        "2026-10-09",
        {
            "slots": [
                {"start": 720, "end": 930, "type": "Definite"},
                {"start": 1260, "end": 1440, "type": "Definite"},
            ]
        },
        "8.1",
        "сьогодні (09.10)",
        duration_delta_minutes=232,
    )

    assert message.endswith("Час без світла: 6:30 (27%), зміна: +3:52")
    assert message.index("21:00 - 24:00") < message.index("Час без світла")


def test_first_schedule_for_day_shows_total_without_delta():
    message = format_schedule_message(
        "2026-10-09",
        {"slots": [
            {"start": 150, "end": 570, "type": "Definite"},
            {"start": 750, "end": 1200, "type": "Definite"},
            {"start": 1320, "end": 1440, "type": "Definite"},
            {"start": 1200, "end": 1230, "type": "Possible"},
        ]},
        "8.1",
        "сьогодні (09.10)",
    )

    assert message.endswith("Час без світла: 17:00 (71%)")


def test_overlapping_definite_and_possible_are_not_counted_twice():
    message = format_schedule_message(
        "2026-10-09",
        {"slots": [
            {"start": 720, "end": 840, "type": "Definite"},
            {"start": 780, "end": 900, "type": "Possible"},
        ]},
        "8.1",
        "сьогодні (09.10)",
    )

    assert message.endswith("Час без світла: 3:00 (13%)")


def test_schedule_message_reports_decreased_or_unchanged_duration():
    day_data = {"slots": [{"start": 720, "end": 930, "type": "Definite"}]}

    decreased = format_schedule_message(
        "2026-10-09",
        day_data,
        "8.1",
        "сьогодні (09.10)",
        duration_delta_minutes=-151,
    )
    unchanged = format_schedule_message(
        "2026-10-09",
        day_data,
        "8.1",
        "сьогодні (09.10)",
        duration_delta_minutes=0,
    )

    assert decreased.endswith("Час без світла: 3:30 (15%), зміна: -2:31")
    assert unchanged.endswith("Час без світла: 3:30 (15%), без змін")
