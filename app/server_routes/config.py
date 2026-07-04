import urllib.parse

from .http import JsonBodyError, read_json, send_json


def _config_service():
    from server_services import config_runtime
    config_runtime._hydrate()
    return config_runtime


def _body(handler):
    try:
        return read_json(handler), None
    except JsonBodyError as e:
        return {}, {"ok": False, "error": str(e), "_status": 400}


def handle_get(handler, parsed_url):
    service = _config_service()
    path = parsed_url.path
    if path == "/health":
        return send_json(handler, service._handle_health(), status=200)
    if path == "/e2e-health":
        return send_json(handler, service._handle_e2e_health(), status=200)
    if path == "/status":
        return send_json(handler, service._handle_status(), status=200)
    if path == "/api/office-config":
        return send_json(handler, service._handle_office_config_get())
    if path == "/api/license":
        return send_json(handler, service._handle_license_status(), status=200)
    if path == "/vo-config":
        return send_json(handler, service._handle_vo_config(), status=200)
    if path == "/api/gateway/test":
        return send_json(handler, handler._test_gateway_connection(), status=200)
    if path == "/weather-proxy":
        return send_json(handler, service._handle_weather_proxy())
    if path == "/api/weather/test":
        return send_json(handler, service._handle_weather_test(urllib.parse.parse_qs(parsed_url.query or "")))
    return False


def handle_post(handler, parsed_url):
    service = _config_service()
    path = parsed_url.path
    if path == "/setup/save":
        body, error = _body(handler)
        return send_json(handler, error or service._persist_setup_payload(body), status=200 if not error else None)
    if path == "/api/office-config":
        raw = handler.rfile.read(int(handler.headers.get("Content-Length", 0) or 0))
        return send_json(handler, service._handle_office_config_save(raw))
    if path == "/api/license/activate":
        body, error = _body(handler)
        return send_json(handler, error or service._handle_license_activate(body), status=200 if not error else None)
    if path == "/api/license/deactivate":
        return send_json(handler, service._handle_license_deactivate(), status=200)
    return False


def handle_put(handler, parsed_url):
    return False


def handle_delete(handler, parsed_url):
    return False
