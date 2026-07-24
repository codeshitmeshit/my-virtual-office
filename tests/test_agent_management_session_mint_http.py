from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")
os.environ.setdefault(
    "VO_STATUS_DIR",
    tempfile.mkdtemp(prefix="vo-agent-management-mint-http-import-"),
)

import server
from services.agent_management_session_mint import (
    AgentManagementSessionMintService,
)
from services.agent_management_sessions import AgentManagementSessionService
from services.hr_repository import HRRepository


@pytest.fixture
def mint(tmp_path):
    repository = HRRepository(tmp_path / "status")
    repository.initialize()
    repository.upsert_agent(
        ai_id="codex-local",
        name="Codex Local",
        agent_kind="project",
        provider_kind="codex",
        status="active",
        availability="available",
        source="test",
    )
    return AgentManagementSessionMintService(
        repository,
        AgentManagementSessionService(),
    )


def _handler(*, remote_host="127.0.0.1", origin=None, action=None, ai_id=None):
    class _Connection:
        def settimeout(self, timeout):
            self.timeout = timeout

    handler = object.__new__(server.OfficeHandler)
    handler.path = "/api/agent-management/sessions"
    handler.headers = {"Content-Length": "0"}
    if origin is not None:
        handler.headers["Origin"] = origin
    if action is not None:
        handler.headers["X-VO-Agent-Action"] = action
    if ai_id is not None:
        handler.headers["X-VO-Agent-Id"] = ai_id
    handler.rfile = io.BytesIO()
    handler.wfile = io.BytesIO()
    handler.connection = _Connection()
    handler.client_address = (remote_host, 12345)
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


def test_originless_agent_can_mint_without_management_token(monkeypatch, mint):
    monkeypatch.setattr(
        server,
        "_get_agent_management_session_mint",
        lambda: mint,
    )
    handler = _handler(
        action="agent-management",
        ai_id="codex-local",
    )

    handler.do_POST()

    assert handler.responses == [201]
    payload = _payload(handler)
    assert payload["ok"] is True
    assert payload["aiId"] == "codex-local"
    assert payload["launchUrl"].startswith("/agent-management/exchange?code=")


@pytest.mark.parametrize(
    ("kwargs", "status", "code"),
    [
        (
            {
                "remote_host": "10.0.0.2",
                "action": "agent-management",
                "ai_id": "codex-local",
            },
            403,
            "agent_management_loopback_required",
        ),
        (
            {
                "origin": "https://office.example",
                "action": "agent-management",
                "ai_id": "codex-local",
            },
            403,
            "agent_management_browser_origin_forbidden",
        ),
        (
            {"ai_id": "codex-local"},
            400,
            "agent_management_action_required",
        ),
        (
            {"action": "agent-management", "ai_id": "unknown"},
            403,
            "agent_management_agent_unknown",
        ),
    ],
)
def test_http_mint_denials_are_stable(
    monkeypatch,
    mint,
    kwargs,
    status,
    code,
):
    monkeypatch.setattr(
        server,
        "_get_agent_management_session_mint",
        lambda: mint,
    )
    handler = _handler(**kwargs)

    handler.do_POST()

    assert handler.responses == [status]
    assert _payload(handler)["code"] == code
