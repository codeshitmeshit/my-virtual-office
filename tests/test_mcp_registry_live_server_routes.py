import io
import json
import os
import tempfile

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-mcp-live-routes-"))

import server
from server_services import mcp_registry


def _handler(path, body=None, *, management_token=None):
    handler = object.__new__(server.OfficeHandler)
    raw = json.dumps(body).encode("utf-8") if body is not None else b""
    handler.path = path
    handler.headers = {"Content-Length": str(len(raw))}
    if management_token:
        handler.headers["X-VO-Management-Token"] = management_token
    handler.rfile = io.BytesIO(raw)
    handler.wfile = io.BytesIO()
    handler.status = None
    handler.response_headers = []
    handler.send_response = lambda status, *args, **kwargs: setattr(handler, "status", status)
    handler.send_header = lambda key, value: handler.response_headers.append((key, value))
    handler.end_headers = lambda: None
    return handler


def _payload(handler):
    return json.loads(handler.wfile.getvalue().decode("utf-8") or "{}")


def test_live_server_dispatches_mcp_registry_get(monkeypatch):
    monkeypatch.setattr(
        mcp_registry,
        "_handle_mcp_registry_list",
        lambda: {"ok": True, "servers": [{"name": "browser-smoke"}]},
    )
    handler = _handler("/api/mcp-registry")

    server.OfficeHandler.do_GET(handler)

    assert handler.status == 200
    assert _payload(handler)["servers"] == [{"name": "browser-smoke"}]


def test_live_server_protects_and_dispatches_mcp_registry_post(monkeypatch):
    calls = []
    monkeypatch.setattr(
        mcp_registry,
        "_handle_mcp_registry_save",
        lambda body: calls.append(body) or {"ok": True, "server": body},
    )
    denied = _handler("/api/mcp-registry", {"name": "browser-smoke"})

    server.OfficeHandler.do_POST(denied)

    assert denied.status == 403
    assert _payload(denied)["code"] == "management_token_required"
    allowed = _handler(
        "/api/mcp-registry",
        {"name": "browser-smoke"},
        management_token=server._MANAGEMENT_TOKEN,
    )

    server.OfficeHandler.do_POST(allowed)

    assert allowed.status == 200
    assert calls == [{"name": "browser-smoke"}]
