from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")
os.environ.setdefault(
    "VO_STATUS_DIR",
    tempfile.mkdtemp(prefix="vo-agent-management-http-import-"),
)

import server


SERVER_SOURCE = (APP_DIR / "server.py").read_text(encoding="utf-8")


def _handler(path: str, payload: bytes = b"", *, authorized: bool = False):
    class _Connection:
        def settimeout(self, timeout):
            self.timeout = timeout

    handler = object.__new__(server.OfficeHandler)
    handler.path = path
    handler.headers = {"Content-Length": str(len(payload))}
    if authorized:
        handler.headers["X-VO-Management-Token"] = server._MANAGEMENT_TOKEN
    handler.rfile = io.BytesIO(payload)
    handler.wfile = io.BytesIO()
    handler.connection = _Connection()
    handler.client_address = ("127.0.0.1", 12345)
    handler.responses = []
    handler.response_headers = []
    handler.send_response = lambda status, *args, **kwargs: handler.responses.append(
        status
    )
    handler.send_header = (
        lambda name, value: handler.response_headers.append((name, value))
    )
    handler.end_headers = lambda: None
    return handler


def _payload(handler):
    return json.loads(handler.wfile.getvalue())


def test_management_get_and_post_reject_before_runtime_or_body(monkeypatch):
    calls = []
    monkeypatch.setattr(
        server,
        "_get_agent_management_runtime",
        lambda: calls.append(True),
    )

    get_handler = _handler("/api/agent-management/profiles/codex-local")
    get_handler.do_GET()
    post_handler = _handler(
        "/api/agent-management/profile/mutate",
        b"not-json",
    )
    post_handler.do_POST()

    assert get_handler.responses == [403]
    assert post_handler.responses == [403]
    assert _payload(get_handler)["code"] == "management_token_required"
    assert _payload(post_handler)["code"] == "management_token_required"
    assert calls == []


def test_authorized_http_round_trip_uses_constructed_runtime(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(server, "STATUS_DIR", str(tmp_path))
    monkeypatch.setattr(server, "_agent_management_runtime", None)
    mutation = {
        "targetAiId": "codex-local",
        "field": "name",
        "value": "Codex Local",
        "expectedRevision": 0,
    }
    post_handler = _handler(
        "/api/agent-management/profile/mutate",
        json.dumps(mutation).encode(),
        authorized=True,
    )
    post_handler.do_POST()

    get_handler = _handler(
        "/api/agent-management/profiles/codex-local",
        authorized=True,
    )
    get_handler.do_GET()

    assert post_handler.responses == [200]
    assert _payload(post_handler)["saveState"] == "saved"
    assert get_handler.responses == [200]
    assert _payload(get_handler)["profile"]["name"] == "Codex Local"


def test_authorized_confirmation_route_rejects_boolean_only_confirmation(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(server, "STATUS_DIR", str(tmp_path))
    monkeypatch.setattr(server, "_agent_management_runtime", None)
    handler = _handler(
        "/api/agent-management/confirmations",
        b'{"confirmed":true}',
        authorized=True,
    )

    handler.do_POST()

    assert handler.responses == [400]
    assert (
        _payload(handler)["code"]
        == "agent_management_confirmation_invalid"
    )


def test_server_is_only_runtime_construction_and_route_delegation():
    forbidden_imports = (
        "from services import agent_profile_store",
        "from services import agent_profile_configuration",
        "from services import agent_profile_mutations",
        "from services import agent_management_confirmations",
    )
    for forbidden in forbidden_imports:
        assert forbidden not in SERVER_SOURCE
    assert (
        "agent_management_runtime_service.build_agent_management_runtime("
        in SERVER_SOURCE
    )
    assert (
        'AgentManagementHTTPRoutes.handles(\n            "GET", request_path'
        in SERVER_SOURCE
    )
    assert (
        'AgentManagementHTTPRoutes.handles(\n            "POST", request_path'
        in SERVER_SOURCE
    )
