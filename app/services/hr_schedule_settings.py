"""Persistent UI-managed schedule settings for automatic HR daily reporting."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import time
from typing import Mapping

from services.hr_repository import HRRepository


SETTINGS_KEY = "hr_daily_schedule"
DEFAULT_DAILY_TIME = "18:00"


class HRScheduleSettingsValidationError(ValueError):
    code = "hr_schedule_settings_validation_failed"


@dataclass(frozen=True, slots=True)
class HRScheduleSettings:
    enabled: bool = True
    daily_time: time = time(18, 0)

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
        if not isinstance(payload, dict) or set(payload) != {
            "schemaVersion",
            "enabled",
            "dailyTime",
        }:
            raise HRScheduleSettingsValidationError(
                "stored HR schedule has unsupported fields"
            )
        if payload["schemaVersion"] != 1 or not isinstance(payload["enabled"], bool):
            raise HRScheduleSettingsValidationError(
                "stored HR schedule is invalid"
            )
        return HRScheduleSettings(
            enabled=payload["enabled"],
            daily_time=self._parse_time(payload["dailyTime"]),
        )

    def update(self, payload: Mapping[str, object]) -> HRScheduleSettings:
        if not isinstance(payload, Mapping) or set(payload) != {
            "enabled",
            "dailyTime",
        }:
            raise HRScheduleSettingsValidationError(
                "schedule requires only enabled and dailyTime"
            )
        enabled = payload.get("enabled")
        if not isinstance(enabled, bool):
            raise HRScheduleSettingsValidationError("enabled must be boolean")
        settings = HRScheduleSettings(
            enabled=enabled,
            daily_time=self._parse_time(payload.get("dailyTime")),
        )
        self._repository.set_metadata_value(
            SETTINGS_KEY,
            json.dumps(
                {
                    "schemaVersion": 1,
                    "enabled": settings.enabled,
                    "dailyTime": settings.daily_time_text,
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
        return settings
