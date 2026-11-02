import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
import requests


SCRIPT = Path(__file__).resolve().parent.parent / "check_HA" / "main.py"
SENSOR = "sensor.test_radiator"
ELECTRICITY_STATES = {
    "voltage": "223.0",
    "frequency": "49.94",
    "is_electicity_exists": "on",
    "yasno_last_state": "NORMAL",
}


class FakeResponse:
    def __init__(self, body, status_code=200):
        self.body = body
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} Error")

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


class FakeHttp:
    """Підміняє HA та портал і запам'ятовує всі запити."""

    def __init__(self):
        self.heating_get = FakeResponse({"state": "42.5"})
        self.heating_post = FakeResponse({"success": True, "data": {}})
        self.ha_available = True
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if SENSOR in url:
            if isinstance(self.heating_get, Exception):
                raise self.heating_get
            return self.heating_get
        if not self.ha_available:
            raise requests.exceptions.ConnectionError("HA down")
        for key, state in ELECTRICITY_STATES.items():
            if key in url:
                return FakeResponse({"state": state})
        raise requests.exceptions.ConnectionError(url)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if url.endswith("/api/update/heating"):
            if isinstance(self.heating_post, Exception):
                raise self.heating_post
            return self.heating_post
        return FakeResponse({"success": True})

    def posts(self, suffix):
        return [c for c in self.calls if c[0] == "POST" and c[1].endswith(suffix)]


@pytest.fixture
def script(monkeypatch):
    # Файл .env не повинен потрапляти в тести
    with patch("dotenv.load_dotenv"):
        spec = importlib.util.spec_from_file_location("check_ha_main", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

    http = FakeHttp()
    monkeypatch.setattr(module.requests, "get", http.get)
    monkeypatch.setattr(module.requests, "post", http.post)
    monkeypatch.setattr(module, "HA_URL", "http://ha.test")
    monkeypatch.setattr(module, "HA_TOKEN", "ha-secret")
    monkeypatch.setattr(module, "HA_VOLTAGE_SENSOR", "sensor.voltage")
    monkeypatch.setattr(module, "HA_FREQUENCY_SENSOR", "sensor.frequency")
    monkeypatch.setattr(module, "LARAVEL_API_URL", "http://portal.test")
    monkeypatch.setattr(module, "API_TOKEN", "portal-secret")
    monkeypatch.setattr(module, "HA_VERIFY_SSL", False)
    monkeypatch.setattr(module, "HA_HEATING_SENSOR", SENSOR)
    module.http = http
    return module


def test_without_setting_no_heating_requests(script, monkeypatch):
    monkeypatch.setattr(script, "HA_HEATING_SENSOR", None)

    assert script.sync_once() is True

    assert script.http.posts("/api/update/heating") == []
    assert not any("None" in call[1] for call in script.http.calls)
    assert len(script.http.posts("/api/update/sensor")) == 1


def test_temperature_sent_separately_with_same_headers(script, capsys):
    assert script.sync_once() is True

    _, url, kwargs = script.http.posts("/api/update/heating")[0]
    _, _, sensor_kwargs = script.http.posts("/api/update/sensor")[0]
    assert url == "http://portal.test/api/update/heating"
    assert kwargs["json"] == {"temperature": 42.5}
    assert kwargs["headers"] == sensor_kwargs["headers"]
    assert kwargs["timeout"] == 30
    assert kwargs["verify"] is False
    assert "temperature" not in sensor_kwargs["json"]
    assert "42.5 °C" in capsys.readouterr().out


def test_low_value_is_sent_as_is(script):
    script.http.heating_get = FakeResponse({"state": "-3.2"})

    script.sync_once()

    assert script.http.posts("/api/update/heating")[0][2]["json"] == {"temperature": -3.2}


@pytest.mark.parametrize("state", ["unavailable", "unknown", "", None, "warm", "nan", "inf"])
def test_bad_state_warns_and_sends_nothing(script, capsys, state):
    script.http.heating_get = FakeResponse({"state": state})

    assert script.sync_once() is True

    assert script.http.posts("/api/update/heating") == []
    assert len(script.http.posts("/api/update/sensor")) == 1
    assert "⚠️ Температура батареї недоступна" in capsys.readouterr().out


def test_missing_entity_warns_and_electricity_continues(script, capsys):
    script.http.heating_get = FakeResponse({"message": "Entity not found."}, status_code=404)

    assert script.sync_once() is True

    assert len(script.http.posts("/api/update/sensor")) == 1
    assert "⚠️" in capsys.readouterr().out


@pytest.mark.parametrize(
    "failure",
    [
        requests.exceptions.Timeout("timed out"),
        requests.exceptions.ConnectionError("portal down"),
        FakeResponse({"message": "Unauthenticated."}, status_code=401),
        FakeResponse({"message": "invalid"}, status_code=422),
        FakeResponse({"message": "down"}, status_code=503),
        FakeResponse(ValueError("not json")),
        FakeResponse(["unexpected"]),
    ],
)
def test_portal_failure_does_not_change_result(script, capsys, failure):
    script.http.heating_post = failure

    assert script.sync_once() is True

    assert len(script.http.posts("/api/update/sensor")) == 1
    assert "⚠️" in capsys.readouterr().out


def test_ha_read_timeout_does_not_change_result(script):
    script.http.heating_get = requests.exceptions.Timeout("timed out")

    assert script.sync_once() is True


def test_ignored_is_not_an_error(script, capsys):
    script.http.heating_post = FakeResponse({"success": True, "ignored": True})

    assert script.sync_once() is True

    out = capsys.readouterr().out
    assert "пропущено" in out
    assert "⚠️" not in out


def test_failed_electricity_result_is_kept_and_temperature_still_read(script):
    script.http.ha_available = False

    assert script.sync_once() is False

    assert len(script.http.posts("/api/update/heating")) == 1
    assert script.http.posts("/api/update/sensor") == []


def test_cron_exit_code_stays_zero_when_heating_fails(script, monkeypatch):
    script.http.heating_post = requests.exceptions.Timeout("timed out")
    monkeypatch.setattr(script.time, "sleep", lambda _: None)

    with pytest.raises(SystemExit) as exit_info:
        script.sync_cron(iterations=2, interval=0)

    assert exit_info.value.code == 0
    assert len(script.http.posts("/api/update/sensor")) == 2


def test_tokens_are_not_logged(script, capsys):
    script.sync_once()
    script.http.heating_post = requests.exceptions.ConnectionError("portal down")
    script.sync_once()

    out = capsys.readouterr().out
    assert "ha-secret" not in out
    assert "portal-secret" not in out
