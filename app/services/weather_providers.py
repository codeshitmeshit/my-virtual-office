"""Provider adapters and shared caching for Virtual Office weather."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping


DEFAULT_PROVIDER = "qweather"
SUPPORTED_PROVIDERS = frozenset({"qweather", "wttr"})
DEFAULT_CACHE_TTL_SECONDS = 900


class WeatherProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _optional_float(value: object, minimum: float, maximum: float) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise WeatherProviderError("invalid_location", "Weather coordinates are invalid") from exc
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise WeatherProviderError("invalid_location", "Weather coordinates are out of range")
    return number


@dataclass(frozen=True, slots=True)
class WeatherSettings:
    provider: str
    location: str
    latitude: float | None
    longitude: float | None
    qweather_api_host: str
    qweather_api_key: str
    fallback_enabled: bool

    @classmethod
    def from_mapping(
        cls,
        config: Mapping[str, Any] | None,
        environ: Mapping[str, str] | None = None,
    ) -> "WeatherSettings":
        config = config if isinstance(config, Mapping) else {}
        environ = environ if isinstance(environ, Mapping) else {}
        qweather = config.get("qweather") if isinstance(config.get("qweather"), Mapping) else {}
        provider = str(environ.get("VO_WEATHER_PROVIDER") or config.get("provider") or DEFAULT_PROVIDER).strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise WeatherProviderError("unsupported_provider", "Weather provider is not supported")
        return cls(
            provider=provider,
            location=str(environ.get("VO_WEATHER_LOCATION") or config.get("location") or "").strip(),
            latitude=_optional_float(environ.get("VO_WEATHER_LATITUDE", config.get("latitude")), -90, 90),
            longitude=_optional_float(environ.get("VO_WEATHER_LONGITUDE", config.get("longitude")), -180, 180),
            qweather_api_host=str(environ.get("VO_QWEATHER_API_HOST") or qweather.get("apiHost") or "").strip(),
            qweather_api_key=str(environ.get("VO_QWEATHER_API_KEY") or qweather.get("apiKey") or "").strip(),
            fallback_enabled=bool(config.get("fallbackEnabled", True)),
        )

    def safe_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "location": self.location,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "fallbackEnabled": self.fallback_enabled,
            "qweather": {
                "apiHost": self.qweather_api_host,
                "apiKeyConfigured": bool(self.qweather_api_key),
                "maskedApiKey": "••••••••••••" if self.qweather_api_key else "",
            },
        }


def _condition(text: object, icon: object = "") -> str:
    value = str(text or "").strip().lower()
    icon_value = str(icon or "").strip()
    if any(token in value for token in ("雷", "thunder")):
        return "thunderstorm"
    if any(token in value for token in ("暴雪", "blizzard")):
        return "snow_storm"
    if any(token in value for token in ("雪", "snow")):
        return "light_snow" if any(token in value for token in ("小", "light")) else "snow"
    if any(token in value for token in ("冻雨", "雨夹雪", "sleet", "ice")):
        return "sleet"
    if any(token in value for token in ("暴雨", "大雨", "heavy rain", "torrential")):
        return "heavy_rain"
    if any(token in value for token in ("小雨", "阵雨", "light rain", "shower")):
        return "light_rain"
    if any(token in value for token in ("毛毛雨", "drizzle")):
        return "drizzle"
    if any(token in value for token in ("雨", "rain")):
        return "rain"
    if any(token in value for token in ("雾", "霾", "fog", "mist", "haze")):
        return "foggy"
    if any(token in value for token in ("阴", "overcast")):
        return "overcast"
    if any(token in value for token in ("多云", "partly cloudy")):
        return "partly_cloudy"
    if any(token in value for token in ("云", "cloud")):
        return "cloudy"
    if any(token in value for token in ("晴", "sunny", "clear")):
        return "sunny"
    if icon_value == "100":
        return "sunny"
    if icon_value in {"101", "102", "103"}:
        return "partly_cloudy"
    if icon_value == "104":
        return "overcast"
    return "cloudy"


def _number(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _validate_qweather_host(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        raise WeatherProviderError("qweather_not_configured", "QWeather API Host is not configured")
    parsed = urllib.parse.urlsplit(raw if "://" in raw else f"https://{raw}")
    hostname = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or not hostname.endswith(".qweatherapi.com")
    ):
        raise WeatherProviderError("invalid_qweather_host", "QWeather API Host is invalid")
    return hostname


class QWeatherProvider:
    name = "qweather"

    def __init__(self, opener: Callable[..., Any] = urllib.request.urlopen):
        self._opener = opener

    def fetch(self, settings: WeatherSettings, fetched_at_ms: int) -> dict[str, Any]:
        host = _validate_qweather_host(settings.qweather_api_host)
        if not settings.qweather_api_key:
            raise WeatherProviderError("qweather_not_configured", "QWeather API Key is not configured")
        if settings.latitude is None or settings.longitude is None:
            raise WeatherProviderError("qweather_location_required", "QWeather requires latitude and longitude")
        location = f"{settings.longitude:.6f},{settings.latitude:.6f}"
        query = urllib.parse.urlencode({"location": location, "lang": "zh"})
        request = urllib.request.Request(
            f"https://{host}/v7/weather/now?{query}",
            headers={"X-QW-Api-Key": settings.qweather_api_key, "User-Agent": "VirtualOffice/1.0"},
        )
        try:
            with self._opener(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or exc.code >= 500
            code = "qweather_auth_failed" if exc.code in {401, 403} else "qweather_unavailable"
            raise WeatherProviderError(code, "QWeather request failed", retryable=retryable) from exc
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise WeatherProviderError("qweather_unavailable", "QWeather is temporarily unavailable", retryable=True) from exc
        if str(payload.get("code") or "") != "200" or not isinstance(payload.get("now"), Mapping):
            code = str(payload.get("code") or "")
            auth_failed = code in {"401", "402", "403"}
            raise WeatherProviderError(
                "qweather_auth_failed" if auth_failed else "qweather_unavailable",
                "QWeather returned an invalid response",
                retryable=not auth_failed,
            )
        now = payload["now"]
        temp_c = _number(now.get("temp"))
        return {
            "ok": True,
            "provider": self.name,
            "location": {
                "name": settings.location,
                "latitude": settings.latitude,
                "longitude": settings.longitude,
            },
            "current": {
                "condition": _condition(now.get("text"), now.get("icon")),
                "description": str(now.get("text") or ""),
                "code": str(now.get("icon") or ""),
                "temperatureC": temp_c,
                "temperatureF": round(temp_c * 9 / 5 + 32),
                "feelsLikeC": _number(now.get("feelsLike")),
                "windKph": _number(now.get("windSpeed")),
                "humidity": _number(now.get("humidity")),
                "visibilityKm": _number(now.get("vis")),
                "precipMm": _number(now.get("precip")),
                "cloudCover": _number(now.get("cloud")),
            },
            "observedAt": now.get("obsTime"),
            "fetchedAt": fetched_at_ms,
            "attributionUrl": payload.get("fxLink") or "https://www.qweather.com/",
            "stale": False,
        }


class WttrProvider:
    name = "wttr"

    def __init__(self, opener: Callable[..., Any] = urllib.request.urlopen):
        self._opener = opener

    def fetch(self, settings: WeatherSettings, fetched_at_ms: int) -> dict[str, Any]:
        if not settings.location:
            raise WeatherProviderError("weather_location_required", "Weather location is not configured")
        encoded = urllib.parse.quote(settings.location, safe="")
        request = urllib.request.Request(
            f"https://wttr.in/{encoded}?format=j1",
            headers={"User-Agent": "VirtualOffice/1.0"},
        )
        try:
            with self._opener(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError, urllib.error.HTTPError) as exc:
            raise WeatherProviderError("wttr_unavailable", "wttr.in is temporarily unavailable", retryable=True) from exc
        current = (payload.get("current_condition") or [{}])[0]
        if not isinstance(current, Mapping) or not current:
            raise WeatherProviderError("wttr_unavailable", "wttr.in returned an invalid response", retryable=True)
        description = ((current.get("weatherDesc") or [{}])[0] or {}).get("value") or ""
        temp_c = _number(current.get("temp_C"))
        nearest = (payload.get("nearest_area") or [{}])[0]
        area = ((nearest.get("areaName") or [{}])[0] or {}).get("value") if isinstance(nearest, Mapping) else ""
        return {
            "ok": True,
            "provider": self.name,
            "location": {
                "name": area or settings.location,
                "latitude": settings.latitude,
                "longitude": settings.longitude,
            },
            "current": {
                "condition": _condition(description, current.get("weatherCode")),
                "description": description,
                "code": str(current.get("weatherCode") or ""),
                "temperatureC": temp_c,
                "temperatureF": _number(current.get("temp_F"), round(temp_c * 9 / 5 + 32)),
                "feelsLikeC": _number(current.get("FeelsLikeC")),
                "windKph": _number(current.get("windspeedKmph")),
                "humidity": _number(current.get("humidity")),
                "visibilityKm": _number(current.get("visibility")),
                "precipMm": _number(current.get("precipMM")),
                "cloudCover": _number(current.get("cloudcover")),
            },
            "observedAt": None,
            "fetchedAt": fetched_at_ms,
            "attributionUrl": "https://wttr.in/",
            "stale": False,
        }


class WeatherService:
    def __init__(
        self,
        *,
        qweather: QWeatherProvider | None = None,
        wttr: WttrProvider | None = None,
        clock: Callable[[], float] = time.time,
        ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
    ):
        self._providers = {
            "qweather": qweather or QWeatherProvider(),
            "wttr": wttr or WttrProvider(),
        }
        self._clock = clock
        self._ttl_seconds = max(1, int(ttl_seconds))
        self._cache: dict[tuple[object, ...], tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _cache_key(settings: WeatherSettings) -> tuple[object, ...]:
        return (
            settings.provider,
            settings.location,
            settings.latitude,
            settings.longitude,
            settings.qweather_api_host,
            hashlib.sha256(settings.qweather_api_key.encode("utf-8")).digest()
            if settings.qweather_api_key
            else b"",
            settings.fallback_enabled,
        )

    def current(self, settings: WeatherSettings, *, force: bool = False) -> dict[str, Any]:
        now = self._clock()
        key = self._cache_key(settings)
        with self._lock:
            cached = self._cache.get(key)
            if cached and not force and now - cached[0] < self._ttl_seconds:
                result = copy.deepcopy(cached[1])
                result["cached"] = True
                return result
        fetched_at_ms = int(now * 1000)
        try:
            result = self._providers[settings.provider].fetch(settings, fetched_at_ms)
        except WeatherProviderError as exc:
            can_fallback = (
                settings.provider != "wttr"
                and settings.fallback_enabled
                and (exc.retryable or exc.code in {"qweather_not_configured", "qweather_location_required"})
            )
            if can_fallback:
                result = self._providers["wttr"].fetch(settings, fetched_at_ms)
                result["fallbackFrom"] = settings.provider
                result["fallbackReason"] = exc.code
            elif cached:
                result = copy.deepcopy(cached[1])
                result.update({"stale": True, "cached": True, "refreshError": exc.code})
                return result
            else:
                raise
        result["cached"] = False
        with self._lock:
            self._cache[key] = (now, copy.deepcopy(result))
        return result


DEFAULT_WEATHER_SERVICE = WeatherService()
