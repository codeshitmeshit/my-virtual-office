"""Weather location default and override precedence."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.weather_config import DEFAULT_WEATHER_LOCATION, resolve_weather_location


def test_default_weather_location_is_beijing_haidian():
    assert DEFAULT_WEATHER_LOCATION == "北京市,海淀区"
    assert resolve_weather_location({}, {}) == DEFAULT_WEATHER_LOCATION
    assert resolve_weather_location({}, {"location": None}) == DEFAULT_WEATHER_LOCATION


def test_persisted_weather_location_overrides_default():
    assert resolve_weather_location({}, {"location": "上海市,浦东新区"}) == "上海市,浦东新区"


def test_environment_weather_location_has_highest_precedence():
    assert (
        resolve_weather_location(
            {"VO_WEATHER_LOCATION": "深圳市,南山区"},
            {"location": "上海市,浦东新区"},
        )
        == "深圳市,南山区"
    )
