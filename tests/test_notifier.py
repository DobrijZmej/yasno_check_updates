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


def test_schedule_message_reports_increased_outage_duration_after_intervals():
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

    assert message.endswith("час відключень збільшився на 3:52")
    assert message.index("21:00 - 24:00") < message.index("час відключень")


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

    assert decreased.endswith("час відключень зменшився на 2:31")
    assert unchanged.endswith("час відключень не змінився")
