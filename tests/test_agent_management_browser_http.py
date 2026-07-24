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
    tempfile.mkdtemp(prefix="vo-agent-management-browser-http-import-"),
)

import server
from services.agent_management_browser import (
    BOOTSTRAP_PATH,
    LOGOUT_PATH,
    PROFILE_MUTATION_PATH,
    AgentManagementBrowserRoutes,
)
from services.agent_management_runtime import build_agent_management_runtime
from services.agent_management_sessions import AgentManagementSessionService
from services.hr_repository import HRRepository


def _routes(tmp_path):
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
    sessions = AgentManagementSessionService()
    session = sessions.exchange_launch_code(
        sessions.issue_launch_code("codex-local").code
    )
    profiles = build_agent_management_runtime(status_dir=tmp_path / "status")
    routes = AgentManagementBrowserRoutes(
        repository=repository,
        sessions=sessions,
        profiles=profiles.profiles,
        mutations=profiles.mutations,
    )
    return session, routes


def _handler(path, payload=b"", *, cookie=None, management=False):
    class _Connection:
        def settimeout(self, timeout):
            self.timeout = timeout

    handler = object.__new__(server.OfficeHandler)
    handler.path = path
    handler.headers = {"Content-Length": str(len(payload))}
    if cookie is not None:
        handler.headers["Cookie"] = (
            f"vo_agent_management_session={cookie}"
        )
    if management:
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


def test_browser_bootstrap_requires_cookie_not_management_token(
    monkeypatch,
    tmp_path,
):
    session, routes = _routes(tmp_path)
    monkeypatch.setattr(
        server, "_get_agent_management_browser_routes", lambda: routes
    )
    human_only = _handler(BOOTSTRAP_PATH, management=True)
    human_only.do_GET()
    agent = _handler(
        BOOTSTRAP_PATH,
        cookie=session.token,
        management=True,
    )
    agent.do_GET()

    assert human_only.responses == [401]
    assert (
        _payload(human_only)["code"]
        == "agent_management_browser_session_expired"
    )
    assert agent.responses == [200]
    assert _payload(agent)["audience"] == {
        "kind": "agent",
        "aiId": "codex-local",
    }


def test_agent_cookie_cannot_authorize_human_confirmation_route(
    monkeypatch,
    tmp_path,
):
    session, routes = _routes(tmp_path)
    monkeypatch.setattr(
        server, "_get_agent_management_browser_routes", lambda: routes
    )
    handler = _handler(
        "/api/agent-management/confirmations",
        b'{"confirmed":true}',
        cookie=session.token,
    )
    handler.do_POST()
    assert handler.responses == [403]
    assert _payload(handler)["code"] == "management_token_required"


def test_agent_cookie_cannot_authorize_human_resources_management(
    tmp_path,
):
    session, _routes_instance = _routes(tmp_path)
    handler = _handler(
        "/api/human-resources/overview",
        cookie=session.token,
    )
    handler.do_GET()
    assert handler.responses == [403]
    assert _payload(handler)["code"] == "management_token_required"


def test_browser_profile_post_uses_cookie_identity_even_with_management_token(
    monkeypatch,
    tmp_path,
):
    session, routes = _routes(tmp_path)
    monkeypatch.setattr(
        server, "_get_agent_management_browser_routes", lambda: routes
    )
    body = json.dumps(
        {
            "targetAiId": "codex-local",
            "field": "name",
            "value": "Codex",
            "expectedRevision": 0,
        }
    ).encode()
    handler = _handler(
        PROFILE_MUTATION_PATH,
        body,
        cookie=session.token,
        management=True,
    )
    handler.do_POST()
    assert handler.responses == [200]
    assert _payload(handler)["profile"]["name"] == "Codex"


def test_browser_api_responses_are_no_store_and_no_referrer(
    monkeypatch,
    tmp_path,
):
    session, routes = _routes(tmp_path)
    monkeypatch.setattr(
        server, "_get_agent_management_browser_routes", lambda: routes
    )
    handler = _handler(BOOTSTRAP_PATH, cookie=session.token)

    def end_headers():
        server.OfficeHandler.end_headers(handler)

    handler.end_headers = end_headers
    handler._headers_buffer = []
    handler.request_version = "HTTP/1.1"
    handler.do_GET()
    headers = dict(handler.response_headers)
    assert headers["Cache-Control"] == "no-store"
    assert headers["Referrer-Policy"] == "no-referrer"


def test_logout_clears_cookie_and_invalidates_server_session(
    monkeypatch,
    tmp_path,
):
    session, routes = _routes(tmp_path)
    monkeypatch.setattr(
        server, "_get_agent_management_browser_routes", lambda: routes
    )
    handler = _handler(LOGOUT_PATH, b"{}", cookie=session.token)
    handler.do_POST()
    headers = dict(handler.response_headers)
    assert handler.responses == [200]
    assert "Max-Age=0" in headers["Set-Cookie"]
    after = _handler(BOOTSTRAP_PATH, cookie=session.token)
    after.do_GET()
    assert after.responses == [401]
