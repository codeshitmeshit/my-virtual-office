"""Weather location configuration defaults and precedence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


DEFAULT_WEATHER_LOCATION = "北京市,海淀区"


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
