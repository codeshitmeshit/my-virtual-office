"""Persistent page-managed HR daily schedule settings."""

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_repository import HRRepository
from services.hr_schedule_settings import (
    HRScheduleSettingsService,
    HRScheduleSettingsValidationError,
)


def service(tmp_path):
    repository = HRRepository(tmp_path / "status")
    repository.initialize()
    return repository, HRScheduleSettingsService(repository)


def test_default_is_enabled_at_1800_without_environment_configuration(tmp_path):
    _repository, settings = service(tmp_path)
    current = settings.load()
    assert current.enabled is True
    assert current.daily_time_text == "18:00"


def test_page_update_persists_across_service_restart(tmp_path):
    repository, settings = service(tmp_path)
    updated = settings.update({"enabled": False, "dailyTime": "07:35"})
    restarted = HRScheduleSettingsService(repository).load()
    assert updated == restarted
    assert restarted.enabled is False
    assert restarted.daily_time_text == "07:35"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"enabled": True},
        {"enabled": 1, "dailyTime": "18:00"},
        {"enabled": True, "dailyTime": "24:00"},
        {"enabled": True, "dailyTime": "18:00", "timezone": "UTC"},
    ],
)
def test_invalid_schedule_payload_does_not_replace_last_good_value(tmp_path, payload):
    _repository, settings = service(tmp_path)
    settings.update({"enabled": True, "dailyTime": "19:10"})
    with pytest.raises(HRScheduleSettingsValidationError):
        settings.update(payload)
    assert settings.load().daily_time_text == "19:10"
