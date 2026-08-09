"""Regression coverage for the extracted weather route implementation."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = (ROOT / "app" / "server.py").read_text(encoding="utf-8")
CONFIG_ROUTE = (ROOT / "app" / "server_routes" / "config.py").read_text(
    encoding="utf-8"
)
CONFIG_RUNTIME = (
    ROOT / "app" / "server_services" / "config_runtime.py"
).read_text(encoding="utf-8")
WEATHER_PROVIDERS = (
    ROOT / "app" / "services" / "weather_providers.py"
).read_text(encoding="utf-8")


def _do_get_block() -> str:
    start = SERVER.index("    def do_GET(self):")
    end = SERVER.index("    def do_PUT(self):", start)
    return SERVER[start:end]


def test_weather_get_routes_delegate_to_the_extracted_config_route():
    do_get = _do_get_block()

    assert 'request_path in {"/weather-proxy", "/api/weather/test"}' in do_get
    assert "server_routes.config.handle_get(self, parsed_url)" in do_get
    assert 'elif self.path == "/weather-proxy"' not in do_get
    assert 'urllib.parse.urlparse(self.path).path == "/api/weather/test"' not in do_get


def test_extracted_weather_route_delegates_to_the_provider_service():
    assert 'path == "/weather-proxy"' in CONFIG_ROUTE
    assert 'path == "/api/weather/test"' in CONFIG_ROUTE
    assert "service._handle_weather_proxy()" in CONFIG_ROUTE
    assert "service._handle_weather_test(" in CONFIG_ROUTE

    assert "DEFAULT_WEATHER_SERVICE.current" in CONFIG_RUNTIME
    assert 'f"https://{host}/v7/weather/now?' in WEATHER_PROVIDERS
    assert 'f"https://wttr.in/{encoded}?format=j1"' in WEATHER_PROVIDERS
    assert "qweatherapi.com" not in SERVER
    assert "wttr.in/" not in SERVER


def test_legacy_safe_config_path_masks_qweather_credentials():
    assert '"weather": VO_CONFIG["weather"]' not in SERVER
    assert "WeatherSettings.from_mapping" in SERVER


def test_weather_post_test_route_is_management_guarded():
    start = SERVER.index("    def do_POST(self):")
    end = SERVER.index("    def do_GET", start) if "    def do_GET" in SERVER[start:] else len(SERVER)
    block = SERVER[start:end]

    route = block.index('request_path == "/api/weather/test"')
    guard = block.index("self._reject_untrusted_management_request()", route)
    delegate = block.index("server_routes.config.handle_post(self, parsed_url)", route)
    assert route < guard < delegate
