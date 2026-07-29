import io
import json
import urllib.parse

from server_routes import mcp_registry as routes
from server_services import mcp_registry


class _Handler:
    def __init__(self):
        self.headers = {"Content-Length": "0"}
        self.rfile = io.BytesIO()
        self.wfile = io.BytesIO()
        self.status = None

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        pass

    def end_headers(self):
        pass


def _post(path):
    handler = _Handler()
    handled = routes.handle_post(handler, urllib.parse.urlparse(path))
    return handled, handler.status, json.loads(handler.wfile.getvalue())


def test_codex_and_claude_registration_routes(monkeypatch):
    calls = []
    monkeypatch.setattr(
        mcp_registry,
        "_handle_mcp_registry_register_codex",
        lambda name, body=None: calls.append(("codex", name, body)) or {"ok": True},
    )
    monkeypatch.setattr(
        mcp_registry,
        "_handle_mcp_registry_register_claude",
        lambda name, body=None: calls.append(("claude", name, body)) or {"ok": True},
    )

    assert _post("/api/mcp-registry/echo/codex")[:2] == (True, 200)
    assert _post("/api/mcp-registry/echo/claude")[:2] == (True, 200)
    assert calls == [("codex", "echo", {}), ("claude", "echo", {})]
