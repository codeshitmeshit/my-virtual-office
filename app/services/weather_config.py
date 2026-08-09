"""Weather location configuration defaults and precedence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


DEFAULT_WEATHER_LOCATION = "北京市,海淀区"
DEFAULT_WEATHER_LATITUDE = 39.96
DEFAULT_WEATHER_LONGITUDE = 116.30


def resolve_weather_location(
    environ: Mapping[str, str],
    weather_config: Mapping[str, Any] | None,
) -> str:
    """Resolve env override, persisted location, then the project default."""
    env_location = environ.get("VO_WEATHER_LOCATION")
    if env_location:
        return env_location

    configured_location = (weather_config or {}).get("location")
    if configured_location:
        return str(configured_location)

    return DEFAULT_WEATHER_LOCATION


def resolve_weather_config(
    environ: Mapping[str, str],
    weather_config: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Resolve provider, precise location and server-only QWeather credentials."""
    config = dict(weather_config or {})
    location = resolve_weather_location(environ, config)
    normalized_location = location.strip().lower().replace("+", "")
    is_default_area = normalized_location in {
        "beijing",
        "beijing,haidian",
        "北京",
        "北京市,海淀区",
    }
    qweather = config.get("qweather") if isinstance(config.get("qweather"), Mapping) else {}
    return {
        "provider": str(
            environ.get("VO_WEATHER_PROVIDER") or config.get("provider") or "qweather"
        ).strip().lower(),
        "location": location,
        "latitude": environ.get("VO_WEATHER_LATITUDE")
        or config.get("latitude")
        or (DEFAULT_WEATHER_LATITUDE if is_default_area else None),
        "longitude": environ.get("VO_WEATHER_LONGITUDE")
        or config.get("longitude")
        or (DEFAULT_WEATHER_LONGITUDE if is_default_area else None),
        "fallbackEnabled": config.get("fallbackEnabled", True) is not False,
        "qweather": {
            "apiHost": environ.get("VO_QWEATHER_API_HOST")
            or qweather.get("apiHost")
            or "",
            "apiKey": environ.get("VO_QWEATHER_API_KEY")
            or qweather.get("apiKey")
            or "",
        },
    }
