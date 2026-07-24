from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import urllib.parse
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
    tempfile.mkdtemp(prefix="vo-agent-management-exchange-http-import-"),
)

import server
from services.agent_management_session_exchange import (
    AgentManagementSessionExchangeService,
)
from services.agent_management_sessions import AgentManagementSessionService


@pytest.fixture
def exchange():
    sessions = AgentManagementSessionService()
    launch = sessions.issue_launch_code("codex-local")
    return launch, AgentManagementSessionExchangeService(sessions)


def _handler(code, *, origin=None, referer=None, fetch_site="none"):
    class _Connection:
        def settimeout(self, timeout):
            self.timeout = timeout

    handler = object.__new__(server.OfficeHandler)
    handler.path = (
        "/agent-management/exchange?code="
        + urllib.parse.quote(str(code), safe="")
    )
    handler.headers = {
        "Host": "office.test:3000",
        "Sec-Fetch-Site": fetch_site,
    }
    if origin is not None:
        handler.headers["Origin"] = origin
    if referer is not None:
        handler.headers["Referer"] = referer
    handler.rfile = io.BytesIO()
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


def test_http_exchange_sets_cookie_security_headers_and_code_free_redirect(
    monkeypatch,
    exchange,
):
    launch, service = exchange
    monkeypatch.setattr(
        server,
        "_get_agent_management_session_exchange",
        lambda: service,
    )
    handler = _handler(launch.code)

    handler.do_GET()

    headers = dict(handler.response_headers)
    assert handler.responses == [303]
    assert headers["Location"] == "/#agent-management"
    assert launch.code not in headers["Location"]
    assert "HttpOnly" in headers["Set-Cookie"]
    assert "SameSite=Strict" in headers["Set-Cookie"]
    assert "Path=/api/agent-management/browser" in headers["Set-Cookie"]
    assert headers["Cache-Control"] == "no-store"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert handler.wfile.getvalue() == b""


def test_http_exchange_rejects_cross_site_without_consuming_code(
    monkeypatch,
    exchange,
):
    launch, service = exchange
    monkeypatch.setattr(
        server,
        "_get_agent_management_session_exchange",
        lambda: service,
    )
    rejected = _handler(
        launch.code,
        origin="https://evil.test",
        fetch_site="cross-site",
    )
    rejected.do_GET()
    assert rejected.responses == [403]
    assert (
        json.loads(rejected.wfile.getvalue())["code"]
        == "agent_management_exchange_origin_forbidden"
    )

    accepted = _handler(
        launch.code,
        origin="http://office.test:3000",
        referer="http://office.test:3000/",
        fetch_site="same-origin",
    )
    accepted.do_GET()
    assert accepted.responses == [303]


def test_http_exchange_replay_is_gone(monkeypatch, exchange):
    launch, service = exchange
    monkeypatch.setattr(
        server,
        "_get_agent_management_session_exchange",
        lambda: service,
    )
    first = _handler(launch.code)
    first.do_GET()
    replay = _handler(launch.code)
    replay.do_GET()
    assert replay.responses == [410]
    assert (
        json.loads(replay.wfile.getvalue())["code"]
        == "agent_management_launch_code_unavailable"
    )


def test_exchange_request_logging_redacts_launch_code(capsys):
    secret = "secret-code-" + "x" * 40
    handler = _handler(secret)
    handler.requestline = f"GET {handler.path} HTTP/1.1"

    handler.log_message('"%s" %s %s', handler.requestline, "303", "-")

    logged = capsys.readouterr().err
    assert secret not in logged
    assert "code=[REDACTED]" in logged
