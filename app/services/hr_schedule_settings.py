"""Persistent UI-managed settings for automatic HR daily reporting."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import time
from typing import Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.hr_repository import HRRepository


SETTINGS_KEY = "hr_daily_schedule"
DEFAULT_DAILY_TIME = "18:00"


class HRScheduleSettingsValidationError(ValueError):
    code = "hr_schedule_settings_validation_failed"


@dataclass(frozen=True, slots=True)
class HRScheduleSettings:
    enabled: bool = True
    daily_time: time = time(18, 0)
    submission_window_minutes: int = 120
    max_workers: int = 2
    agent_timeout_seconds: float = 30.0
    retry_limit: int = 3
    timezone_name: str = "UTC"

    @property
    def daily_time_text(self) -> str:
        return self.daily_time.strftime("%H:%M")


class HRScheduleSettingsService:
    """Own validation and durable storage for the page-managed HR schedule."""

    def __init__(self, repository: HRRepository):
        if not isinstance(repository, HRRepository):
            raise HRScheduleSettingsValidationError(
                "repository must be an HRRepository"
            )
        self._repository = repository

    @staticmethod
    def _parse_time(value: object) -> time:
        if not isinstance(value, str) or re.fullmatch(
            r"(?:[01]\d|2[0-3]):[0-5]\d", value
        ) is None:
            raise HRScheduleSettingsValidationError(
                "dailyTime must use 24-hour HH:MM"
            )
        hour, minute = (int(part) for part in value.split(":"))
        return time(hour, minute)

    @staticmethod
    def _parse_int(value: object, name: str, *, minimum: int, maximum: int) -> int:
        if isinstance(value, bool):
            raise HRScheduleSettingsValidationError(f"{name} must be an integer")
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise HRScheduleSettingsValidationError(f"{name} must be an integer") from exc
        if not minimum <= parsed <= maximum:
            raise HRScheduleSettingsValidationError(
                f"{name} must be between {minimum} and {maximum}"
            )
        return parsed

    @staticmethod
    def _parse_number(value: object, name: str, *, minimum: float, maximum: float) -> float:
        if isinstance(value, bool):
            raise HRScheduleSettingsValidationError(f"{name} must be numeric")
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise HRScheduleSettingsValidationError(f"{name} must be numeric") from exc
        if not minimum <= parsed <= maximum:
            raise HRScheduleSettingsValidationError(
                f"{name} must be between {minimum:g} and {maximum:g}"
            )
        return parsed

    @staticmethod
    def _parse_timezone(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise HRScheduleSettingsValidationError("timezoneName must name an IANA timezone")
        timezone_name = value.strip()
        try:
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
            raise HRScheduleSettingsValidationError(
                "timezoneName must name an IANA timezone"
            ) from exc
        return timezone_name

    @staticmethod
    def _serialize(settings: HRScheduleSettings) -> str:
        return json.dumps(
            {
                "schemaVersion": 3,
                "enabled": settings.enabled,
                "dailyTime": settings.daily_time_text,
                "timezoneName": settings.timezone_name,
                "submissionWindowMinutes": settings.submission_window_minutes,
                "maxWorkers": settings.max_workers,
                "agentTimeoutSeconds": settings.agent_timeout_seconds,
                "retryLimit": settings.retry_limit,
            },
            separators=(",", ":"),
            sort_keys=True,
        )

    def load(self) -> HRScheduleSettings:
        raw = self._repository.get_metadata_value(SETTINGS_KEY)
        if raw is None:
            return HRScheduleSettings()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HRScheduleSettingsValidationError(
                "stored HR schedule is invalid"
            ) from exc
        if not isinstance(payload, dict):
            raise HRScheduleSettingsValidationError(
                "stored HR schedule has unsupported fields"
            )
        schema_version = payload.get("schemaVersion")
        allowed = {
            "schemaVersion",
            "enabled",
            "dailyTime",
            "timezoneName",
            "submissionWindowMinutes",
            "maxWorkers",
            "agentTimeoutSeconds",
            "retryLimit",
        }
        if schema_version == 1:
            if set(payload) != {"schemaVersion", "enabled", "dailyTime"}:
                raise HRScheduleSettingsValidationError(
                    "stored HR schedule has unsupported fields"
                )
        elif schema_version == 2:
            if set(payload) != (allowed - {"timezoneName"}):
                raise HRScheduleSettingsValidationError(
                    "stored HR schedule has unsupported fields"
                )
        elif schema_version == 3:
            if set(payload) != allowed:
                raise HRScheduleSettingsValidationError(
                    "stored HR schedule has unsupported fields"
                )
        else:
            raise HRScheduleSettingsValidationError(
                "stored HR schedule is invalid"
            )
        if not isinstance(payload["enabled"], bool):
            raise HRScheduleSettingsValidationError("stored HR schedule is invalid")
        return HRScheduleSettings(
            enabled=payload["enabled"],
            daily_time=self._parse_time(payload["dailyTime"]),
            timezone_name=self._parse_timezone(payload.get("timezoneName", "UTC")),
            submission_window_minutes=self._parse_int(
                payload.get("submissionWindowMinutes", 120),
                "submissionWindowMinutes",
                minimum=1,
                maximum=1_440,
            ),
            max_workers=self._parse_int(
                payload.get("maxWorkers", 2),
                "maxWorkers",
                minimum=1,
                maximum=8,
            ),
            agent_timeout_seconds=self._parse_number(
                payload.get("agentTimeoutSeconds", 30.0),
                "agentTimeoutSeconds",
                minimum=0.1,
                maximum=300.0,
            ),
            retry_limit=self._parse_int(
                payload.get("retryLimit", 3),
                "retryLimit",
                minimum=0,
                maximum=10,
            ),
        )

    def update(self, payload: Mapping[str, object]) -> HRScheduleSettings:
        if not isinstance(payload, Mapping) or set(payload) != {
            "enabled",
            "dailyTime",
            "timezoneName",
            "submissionWindowMinutes",
            "maxWorkers",
            "agentTimeoutSeconds",
            "retryLimit",
        }:
            raise HRScheduleSettingsValidationError(
                "schedule requires only supported HR settings"
            )
        enabled = payload.get("enabled")
        if not isinstance(enabled, bool):
            raise HRScheduleSettingsValidationError("enabled must be boolean")
        settings = HRScheduleSettings(
            enabled=enabled,
            daily_time=self._parse_time(payload.get("dailyTime")),
            timezone_name=self._parse_timezone(payload.get("timezoneName")),
            submission_window_minutes=self._parse_int(
                payload.get("submissionWindowMinutes"),
                "submissionWindowMinutes",
                minimum=1,
                maximum=1_440,
            ),
            max_workers=self._parse_int(
                payload.get("maxWorkers"),
                "maxWorkers",
                minimum=1,
                maximum=8,
            ),
            agent_timeout_seconds=self._parse_number(
                payload.get("agentTimeoutSeconds"),
                "agentTimeoutSeconds",
                minimum=0.1,
                maximum=300.0,
            ),
            retry_limit=self._parse_int(
                payload.get("retryLimit"),
                "retryLimit",
                minimum=0,
                maximum=10,
            ),
        )
        self._repository.set_metadata_value(SETTINGS_KEY, self._serialize(settings))
        return settings
