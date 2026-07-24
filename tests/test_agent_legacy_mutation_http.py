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
    tempfile.mkdtemp(prefix="vo-agent-legacy-http-import-"),
)

import server


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


def test_post_legacy_mutations_require_management_before_body_parsing():
    for path in (
        "/api/office-config",
        "/api/agent/create",
        "/api/agent-workspace/codex-local",
        "/api/agent/codex-local/skills",
        "/api/skills-library",
        "/api/skills-library/apply",
        "/set-model",
    ):
        handler = _handler(path, b"not-json")
        handler.do_POST()
        assert handler.responses == [403], path
        assert _payload(handler)["code"] == "management_token_required"


def test_delete_legacy_mutations_require_management_before_dispatch(monkeypatch):
    called = []
    monkeypatch.setattr(
        server,
        "_handle_skill_delete",
        lambda *args: called.append(args) or {"ok": True},
    )
    for path in (
        "/api/agent/delete",
        "/api/agent/codex-local/skills/reviewer",
        "/api/skills-library/reviewer",
    ):
        handler = _handler(path)
        handler.do_DELETE()
        assert handler.responses == [403], path
        assert _payload(handler)["code"] == "management_token_required"
    assert called == []


def test_authorized_old_high_risk_routes_are_still_removed():
    for method, path in (
        ("POST", "/api/agent/create"),
        ("POST", "/set-model"),
        ("DELETE", "/api/agent/delete"),
    ):
        handler = _handler(path, b"{}", authorized=True)
        getattr(handler, f"do_{method}")()
        assert handler.responses == [410], path
        assert _payload(handler)["code"] == "agent_management_route_migrated"


def test_workspace_profile_bypass_is_rejected_before_legacy_handler(monkeypatch):
    called = []
    monkeypatch.setattr(
        server,
        "_handle_agent_workspace_update",
        lambda *args: called.append(args) or {"ok": True},
    )
    handler = _handler(
        "/api/agent-workspace/codex-local",
        b'{"action":"updateSettings","branch":"finance"}',
        authorized=True,
    )

    handler.do_POST()

    assert handler.responses == [410]
    assert _payload(handler)["code"] == "agent_management_route_migrated"
    assert called == []


def test_retained_workspace_write_dispatches_after_management_authorization(
    monkeypatch,
):
    called = []
    monkeypatch.setattr(
        server,
        "_handle_agent_workspace_update",
        lambda *args: called.append(args) or {"ok": True},
    )
    handler = _handler(
        "/api/agent-workspace/codex-local",
        b'{"action":"updateSettings","heartbeatMinutes":15}',
        authorized=True,
    )

    handler.do_POST()

    assert handler.responses == [200]
    assert called == [
        (
            "codex-local",
            {"action": "updateSettings", "heartbeatMinutes": 15},
        )
    ]


def test_office_config_cannot_carry_agent_or_branch_changes(
    monkeypatch,
    tmp_path,
):
    current = {
        "agents": [{"id": "codex-local", "role": "Backend"}],
        "branches": [{"id": "hq", "name": "总部"}],
        "layout": {"zoom": 1},
    }
    (tmp_path / "office-config.json").write_text(
        json.dumps(current),
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "STATUS_DIR", str(tmp_path))
    proposed = {**current, "agents": [{"id": "codex-local", "role": "HR"}]}
    handler = _handler(
        "/api/office-config",
        json.dumps(proposed).encode(),
        authorized=True,
    )

    handler.do_POST()

    assert handler.responses == [410]
    assert _payload(handler)["code"] == "agent_management_route_migrated"
    assert json.loads((tmp_path / "office-config.json").read_text()) == current


def test_agent_delete_removes_office_config_override(monkeypatch, tmp_path):
    config = {
        "agents": [
            {"id": "keep-agent", "branch": "Keep"},
            {
                "id": "task18-disposable",
                "statusKey": "task18-disposable",
                "branch": "TASK18",
                "workspace": "/tmp/task18",
            },
        ],
    }
    (tmp_path / "office-config.json").write_text(
        json.dumps(config),
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "STATUS_DIR", str(tmp_path))
    monkeypatch.setattr(
        server,
        "_office_agent_lookup",
        lambda agent_id: {"id": agent_id, "providerKind": "openclaw"},
    )
    monkeypatch.setattr(
        server,
        "_gateway_rpc_call",
        lambda method, params, timeout=30: {"ok": True},
    )
    monkeypatch.setattr(server, "_remove_openclaw_agent_paths", lambda agent_id: None)
    monkeypatch.setattr(server, "refresh_agent_maps", lambda: None)

    result = server._handle_agent_delete({"id": "task18-disposable"})

    assert result["ok"] is True
    saved = json.loads((tmp_path / "office-config.json").read_text())
    assert saved["agents"] == [{"id": "keep-agent", "branch": "Keep"}]
