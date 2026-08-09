from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import urllib.error

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.weather_providers import (  # noqa: E402
    QWeatherProvider,
    WeatherProviderError,
    WeatherService,
    WeatherSettings,
    WttrProvider,
)


class Response:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def settings(**overrides):
    payload = {
        "provider": "qweather",
        "location": "北京市,海淀区",
        "latitude": 39.96,
        "longitude": 116.30,
        "fallbackEnabled": True,
        "qweather": {"apiHost": "demo.def.qweatherapi.com", "apiKey": "secret"},
    }
    payload.update(overrides)
    return WeatherSettings.from_mapping(payload)


def test_qweather_uses_dedicated_host_header_and_normalizes_response():
    calls = []

    def open_request(request, timeout):
        calls.append((request, timeout))
        return Response({
            "code": "200",
            "fxLink": "https://www.qweather.com/weather/beijing.html",
            "now": {
                "obsTime": "2026-08-10T10:20+08:00",
                "temp": "27",
                "feelsLike": "29",
                "icon": "305",
                "text": "小雨",
                "windSpeed": "12",
                "humidity": "80",
                "vis": "8",
                "precip": "0.6",
                "cloud": "92",
            },
        })

    result = QWeatherProvider(open_request).fetch(settings(), 123000)

    request, timeout = calls[0]
    assert timeout == 10
    assert request.full_url.startswith(
        "https://demo.def.qweatherapi.com/v7/weather/now?"
    )
    assert "location=116.300000%2C39.960000" in request.full_url
    assert request.get_header("X-qw-api-key") == "secret"
    assert result["provider"] == "qweather"
    assert result["current"]["condition"] == "light_rain"
    assert result["current"]["temperatureC"] == 27
    assert result["observedAt"] == "2026-08-10T10:20+08:00"


def test_qweather_rejects_non_qweather_api_hosts_before_network_access():
    provider = QWeatherProvider(lambda *_args, **_kwargs: pytest.fail("network called"))
    invalid = settings(qweather={"apiHost": "https://example.com/path", "apiKey": "secret"})

    with pytest.raises(WeatherProviderError) as error:
        provider.fetch(invalid, 1)

    assert error.value.code == "invalid_qweather_host"


def test_service_falls_back_to_wttr_when_qweather_is_not_configured():
    qweather = QWeatherProvider(lambda *_args, **_kwargs: pytest.fail("network called"))
    wttr = WttrProvider(lambda *_args, **_kwargs: Response({
        "current_condition": [{
            "weatherDesc": [{"value": "Clear"}],
            "weatherCode": "113",
            "temp_C": "25",
            "temp_F": "77",
            "FeelsLikeC": "26",
            "windspeedKmph": "7",
            "humidity": "40",
            "visibility": "10",
            "precipMM": "0",
            "cloudcover": "0",
        }],
        "nearest_area": [{"areaName": [{"value": "Haidian"}]}],
    }))
    service = WeatherService(qweather=qweather, wttr=wttr, clock=lambda: 100)
    unconfigured = settings(qweather={"apiHost": "", "apiKey": ""})

    result = service.current(unconfigured)

    assert result["provider"] == "wttr"
    assert result["fallbackFrom"] == "qweather"
    assert result["fallbackReason"] == "qweather_not_configured"


def test_service_does_not_hide_qweather_authentication_failures():
    def unauthorized(_request, timeout):
        raise urllib.error.HTTPError("https://demo.def.qweatherapi.com", 401, "", {}, io.BytesIO())

    service = WeatherService(
        qweather=QWeatherProvider(unauthorized),
        wttr=WttrProvider(lambda *_args, **_kwargs: pytest.fail("fallback called")),
    )

    with pytest.raises(WeatherProviderError) as error:
        service.current(settings())

    assert error.value.code == "qweather_auth_failed"


def test_shared_cache_avoids_duplicate_provider_requests():
    calls = []

    class Provider:
        def fetch(self, _settings, fetched_at):
            calls.append(fetched_at)
            return {"ok": True, "provider": "qweather", "current": {}, "fetchedAt": fetched_at}

    service = WeatherService(qweather=Provider(), clock=lambda: 100)
    first = service.current(settings())
    second = service.current(settings())

    assert first["cached"] is False
    assert second["cached"] is True
    assert calls == [100000]


def test_cache_is_invalidated_when_qweather_key_changes():
    calls = []

    class Provider:
        def fetch(self, provider_settings, fetched_at):
            calls.append(provider_settings.qweather_api_key)
            return {"ok": True, "provider": "qweather", "current": {}, "fetchedAt": fetched_at}

    service = WeatherService(qweather=Provider(), clock=lambda: 100)
    service.current(settings())
    service.current(settings(qweather={"apiHost": "demo.def.qweatherapi.com", "apiKey": "new-secret"}))

    assert calls == ["secret", "new-secret"]


def test_safe_settings_never_expose_qweather_key():
    safe = settings().safe_dict()

    assert "apiKey" not in safe["qweather"]
    assert safe["qweather"]["apiKeyConfigured"] is True
    assert safe["qweather"]["maskedApiKey"].startswith("••")
