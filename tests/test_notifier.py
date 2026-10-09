from modules.notification.notifier import (
    TELEGRAM_FOOTER,
    append_telegram_footer,
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
