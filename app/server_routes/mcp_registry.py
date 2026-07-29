import urllib.parse

from .http import JsonBodyError, read_json, send_json


def _service():
    from server_services import mcp_registry

    return mcp_registry


def _body(handler):
    try:
        return read_json(handler), None
    except JsonBodyError as exc:
        return {}, {"ok": False, "error": str(exc), "_status": 400}


def _server_name(path, suffix=""):
    rest = path.split("/api/mcp-registry/", 1)[1]
    if suffix and rest.endswith(suffix):
        rest = rest[: -len(suffix)]
    return urllib.parse.unquote(rest.strip("/"))


def handle_get(handler, parsed_url):
    service = _service()
    path = parsed_url.path
    if path == "/api/mcp-registry":
        return send_json(handler, service._handle_mcp_registry_list())
    if path.startswith("/api/mcp-registry/"):
        return send_json(handler, service._handle_mcp_registry_get(_server_name(path)))
    return False


def handle_post(handler, parsed_url):
    service = _service()
    path = parsed_url.path
    if path == "/api/mcp-registry":
        body, error = _body(handler)
        return send_json(handler, error or service._handle_mcp_registry_save(body))
    if path == "/api/mcp-registry/templates/vibe-trading":
        return send_json(handler, service._handle_mcp_registry_vibe_template())
    if path.startswith("/api/mcp-registry/") and path.endswith("/openclaw"):
        body, error = _body(handler)
        return send_json(handler, error or service._handle_mcp_registry_register_openclaw(_server_name(path, "/openclaw"), body))
    if path.startswith("/api/mcp-registry/") and path.endswith("/skill"):
        body, error = _body(handler)
        return send_json(handler, error or service._handle_mcp_registry_install_skill(_server_name(path, "/skill"), body))
    return False


def handle_put(handler, parsed_url):
    return False


def handle_delete(handler, parsed_url):
    service = _service()
    path = parsed_url.path
    if path.startswith("/api/mcp-registry/"):
        return send_json(handler, service._handle_mcp_registry_delete(_server_name(path)))
    return False
