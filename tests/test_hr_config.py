"""Strict HR defaults, switch behavior, and configuration boundaries."""

import sys
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_config import HRConfig, HRConfigError


def test_defaults_enable_hr_lifecycle_but_keep_scheduler_disabled():
    config = HRConfig.from_env({})
    assert config.enabled is True
    assert config.scheduler_enabled is False
    assert config.scheduler_active is False
    assert config.timezone_name == "UTC"
    assert config.daily_time == time(18, 0)
    assert config.submission_window_minutes == 120
    assert config.max_workers == 2
    assert config.agent_timeout_seconds == 30.0
    assert config.retry_limit == 3


def test_all_supported_values_and_timezone_fallbacks():
    config = HRConfig.from_env(
        {
            "VO_HR_ENABLED": "yes",
            "VO_HR_SCHEDULER_ENABLED": "ON",
            "VO_TIMEZONE": "Asia/Shanghai",
            "VO_HR_DAILY_TIME": "07:05",
            "VO_HR_SUBMISSION_WINDOW_MINUTES": "90",
            "VO_HR_MAX_WORKERS": "4",
            "VO_HR_AGENT_TIMEOUT_SECONDS": "12.5",
            "VO_HR_RETRY_LIMIT": "5",
        }
    )
    assert config.scheduler_active is True
    assert config.timezone_name == "Asia/Shanghai"
    assert config.timezone == ZoneInfo("Asia/Shanghai")
    assert config.daily_time == time(7, 5)
    assert config.submission_window_minutes == 90
    assert config.max_workers == 4
    assert config.agent_timeout_seconds == 12.5
    assert config.retry_limit == 5


def test_hr_timezone_overrides_vo_and_process_timezone():
    config = HRConfig.from_env(
        {
            "VO_HR_TIMEZONE": "America/New_York",
            "VO_TIMEZONE": "Asia/Shanghai",
            "TZ": "UTC",
        }
    )
    assert config.timezone_name == "America/New_York"


def test_scheduler_switch_alone_never_bypasses_master_switch():
    config = HRConfig.from_env(
        {"VO_HR_ENABLED": "0", "VO_HR_SCHEDULER_ENABLED": "1"}
    )
    assert config.scheduler_enabled is True
    assert config.scheduler_active is False


@pytest.mark.parametrize(
    "value, expected",
    (("1", True), ("true", True), ("on", True), ("0", False), ("false", False), ("off", False)),
)
def test_boolean_spellings(value, expected):
    assert HRConfig.from_env({"VO_HR_ENABLED": value}).enabled is expected


@pytest.mark.parametrize(
    "environment, message",
    (
        ({"VO_HR_ENABLED": "maybe"}, "boolean"),
        ({"VO_HR_SCHEDULER_ENABLED": "2"}, "boolean"),
        ({"VO_HR_TIMEZONE": "Mars/Olympus"}, "IANA"),
        ({"VO_HR_DAILY_TIME": "7:00"}, "HH:MM"),
        ({"VO_HR_DAILY_TIME": "24:00"}, "HH:MM"),
        ({"VO_HR_SUBMISSION_WINDOW_MINUTES": "none"}, "integer"),
        ({"VO_HR_MAX_WORKERS": "1.5"}, "integer"),
        ({"VO_HR_AGENT_TIMEOUT_SECONDS": "fast"}, "numeric"),
        ({"VO_HR_RETRY_LIMIT": "-1"}, "between"),
    ),
)
def test_invalid_values_fail_closed_with_named_errors(environment, message):
    with pytest.raises(HRConfigError, match=message):
        HRConfig.from_env(environment)


@pytest.mark.parametrize(
    "name, low, high",
    (
        ("VO_HR_SUBMISSION_WINDOW_MINUTES", "1", "1440"),
        ("VO_HR_MAX_WORKERS", "1", "8"),
        ("VO_HR_AGENT_TIMEOUT_SECONDS", "0.1", "300"),
        ("VO_HR_RETRY_LIMIT", "0", "10"),
    ),
)
def test_numeric_boundaries_are_inclusive(name, low, high):
    HRConfig.from_env({name: low})
    HRConfig.from_env({name: high})


@pytest.mark.parametrize(
    "name, value",
    (
        ("VO_HR_SUBMISSION_WINDOW_MINUTES", "0"),
        ("VO_HR_SUBMISSION_WINDOW_MINUTES", "1441"),
        ("VO_HR_MAX_WORKERS", "0"),
        ("VO_HR_MAX_WORKERS", "9"),
        ("VO_HR_AGENT_TIMEOUT_SECONDS", "0.09"),
        ("VO_HR_AGENT_TIMEOUT_SECONDS", "301"),
        ("VO_HR_RETRY_LIMIT", "11"),
    ),
)
def test_numeric_values_outside_bounds_are_rejected(name, value):
    with pytest.raises(HRConfigError, match="between"):
        HRConfig.from_env({name: value})


def test_blank_values_use_defaults_but_do_not_hide_invalid_nonblank_values():
    assert HRConfig.from_env({"VO_HR_ENABLED": " "}).enabled is True
    assert HRConfig.from_env({"VO_HR_DAILY_TIME": "  "}).daily_time == time(18, 0)
    assert HRConfig.from_env({"VO_HR_MAX_WORKERS": " "}).max_workers == 2


def test_direct_construction_cannot_bypass_validation():
    with pytest.raises(HRConfigError, match="out of bounds"):
        HRConfig(
            enabled=True,
            scheduler_enabled=True,
            timezone_name="UTC",
            daily_time=time(18, 0),
            submission_window_minutes=120,
            max_workers=99,
            agent_timeout_seconds=30,
            retry_limit=3,
        )
