from .http import send_json


def _browser_service():
    from server_services import browser_runtime
    browser_runtime._hydrate()
    return browser_runtime


def handle_get(handler, parsed_url):
    service = _browser_service()
    path = parsed_url.path
    if path == "/browser-controller":
        return send_json(handler, service._handle_browser_controller(), status=200)
    if path == "/browser-status":
        return send_json(handler, service._handle_browser_status(), status=200)
    if path == "/browser-viewer-status":
        return send_json(handler, service._handle_browser_viewer_status(), status=200)
    if path == "/browser-tabs":
        return send_json(handler, service._handle_browser_tabs(), status=200)
    return False


def handle_post(handler, parsed_url):
    return False


def handle_put(handler, parsed_url):
    return False


def handle_delete(handler, parsed_url):
    return False
