"""Strict startup configuration for Human Resources and its durable scheduler."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import time
from typing import Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


Environment = Mapping[str, str]


class HRConfigError(ValueError):
    code = "hr_config_invalid"


def _raw(environ: Environment, name: str) -> str | None:
    value = environ.get(name)
    if value is None or not str(value).strip():
        return None
    return str(value).strip()


def _boolean(environ: Environment, name: str, default: bool) -> bool:
    value = _raw(environ, name)
    if value is None:
        return default
    normalized = value.lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise HRConfigError(f"{name} must be a boolean")


def _integer(
    environ: Environment,
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = _raw(environ, name)
    try:
        parsed = default if value is None else int(value)
    except ValueError as exc:
        raise HRConfigError(f"{name} must be an integer") from exc
    if isinstance(parsed, bool) or not minimum <= parsed <= maximum:
        raise HRConfigError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def _number(
    environ: Environment,
    name: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    value = _raw(environ, name)
    try:
        parsed = default if value is None else float(value)
    except ValueError as exc:
        raise HRConfigError(f"{name} must be numeric") from exc
    if not minimum <= parsed <= maximum:
        raise HRConfigError(f"{name} must be between {minimum:g} and {maximum:g}")
    return parsed


@dataclass(frozen=True, slots=True)
class HRConfig:
    enabled: bool
    scheduler_enabled: bool
    timezone_name: str
    daily_time: time
    submission_window_minutes: int
    max_workers: int
    agent_timeout_seconds: float
    retry_limit: int

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool) or not isinstance(self.scheduler_enabled, bool):
            raise HRConfigError("HR switches must be boolean")
        try:
            ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
            raise HRConfigError("timezone_name must name an IANA timezone") from exc
        if not isinstance(self.daily_time, time):
            raise HRConfigError("daily_time must be a datetime.time")
        integer_bounds = (
            (self.submission_window_minutes, 1, 1_440, "submission_window_minutes"),
            (self.max_workers, 1, 8, "max_workers"),
            (self.retry_limit, 0, 10, "retry_limit"),
        )
        for value, minimum, maximum, field in integer_bounds:
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                raise HRConfigError(f"{field} is out of bounds")
        if (
            isinstance(self.agent_timeout_seconds, bool)
            or not isinstance(self.agent_timeout_seconds, (int, float))
            or not 0.1 <= self.agent_timeout_seconds <= 300
        ):
            raise HRConfigError("agent_timeout_seconds is out of bounds")

    @property
    def scheduler_active(self) -> bool:
        return self.enabled and self.scheduler_enabled

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    @classmethod
    def from_env(cls, environ: Environment | None = None) -> "HRConfig":
        env = os.environ if environ is None else environ
        timezone_name = (
            _raw(env, "VO_HR_TIMEZONE")
            or _raw(env, "VO_TIMEZONE")
            or _raw(env, "TZ")
            or "UTC"
        )
        try:
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise HRConfigError("VO_HR_TIMEZONE must name an IANA timezone") from exc
        daily_text = _raw(env, "VO_HR_DAILY_TIME") or "18:00"
        if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", daily_text) is None:
            raise HRConfigError("VO_HR_DAILY_TIME must use 24-hour HH:MM")
        hour, minute = (int(part) for part in daily_text.split(":"))
        return cls(
            enabled=_boolean(env, "VO_HR_ENABLED", True),
            scheduler_enabled=_boolean(env, "VO_HR_SCHEDULER_ENABLED", False),
            timezone_name=timezone_name,
            daily_time=time(hour, minute),
            submission_window_minutes=_integer(
                env,
                "VO_HR_SUBMISSION_WINDOW_MINUTES",
                120,
                minimum=1,
                maximum=1_440,
            ),
            max_workers=_integer(
                env,
                "VO_HR_MAX_WORKERS",
                2,
                minimum=1,
                maximum=8,
            ),
            agent_timeout_seconds=_number(
                env,
                "VO_HR_AGENT_TIMEOUT_SECONDS",
                30.0,
                minimum=0.1,
                maximum=300.0,
            ),
            retry_limit=_integer(
                env,
                "VO_HR_RETRY_LIMIT",
                3,
                minimum=0,
                maximum=10,
            ),
        )
