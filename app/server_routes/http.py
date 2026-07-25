import json
import urllib.parse


class JsonBodyError(ValueError):
    pass


def read_json(handler, max_bytes=None):
    length = int(handler.headers.get("Content-Length", 0))
    if max_bytes is not None and length > max_bytes:
        raise JsonBodyError(f"Request body too large (max {max_bytes} bytes)")
    if not length:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise JsonBodyError(f"Invalid JSON: {e}") from e


def send_json(handler, data, status=None, headers=None):
    payload = dict(data or {}) if isinstance(data, dict) else data
    if status is None and isinstance(payload, dict):
        status = payload.get("_status", 200)
    if status is None:
        status = 200
    if isinstance(payload, dict):
        payload.pop("_status", None)
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    for key, value in (headers or {}).items():
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(json.dumps(payload).encode())
    return True


def send_error_json(handler, status, error, code=None):
    payload = {"ok": False, "error": error}
    if code:
        payload["code"] = code
    return send_json(handler, payload, status=status)


def require_origin(handler, allowed=None):
    origin = handler.headers.get("Origin", "")
    if not origin:
        return True
    if allowed is None:
        host = handler.headers.get("Host", "")
        allowed = {
            f"http://{host}",
            f"https://{host}",
            "http://127.0.0.1:8090",
            "http://localhost:8090",
        }
    return origin in set(allowed)


def query_dict(parsed_url):
    return urllib.parse.parse_qs(parsed_url.query or "")
