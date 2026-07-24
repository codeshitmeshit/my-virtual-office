from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.agent_management_session_exchange import (
    AgentManagementExchangeRequest,
    AgentManagementSessionExchangeService,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_PATH,
)
from services.agent_management_sessions import AgentManagementSessionService


class Clock:
    def __init__(self):
        self.value = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)

    def now(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


class Secrets:
    def __init__(self):
        self.index = 0

    def __call__(self):
        self.index += 1
        return f"exchange-secret-{self.index:04d}-" + "x" * 40


def _services():
    clock = Clock()
    sessions = AgentManagementSessionService(
        now=clock.now,
        secret_factory=Secrets(),
        launch_ttl_seconds=10,
        idle_ttl_seconds=30,
        absolute_ttl_seconds=90,
    )
    exchange = AgentManagementSessionExchangeService(
        sessions,
        now=clock.now,
    )
    return clock, sessions, exchange


def _request(code, **overrides):
    values = {
        "code": code,
        "host": "office.test:3000",
        "origin": None,
        "referer": None,
        "fetch_site": "none",
        "secure": False,
    }
    values.update(overrides)
    return AgentManagementExchangeRequest(**values)


def test_exchange_sets_scoped_opaque_cookie_and_redirects_without_code():
    _, sessions, exchange = _services()
    launch = sessions.issue_launch_code("codex-local")

    response = exchange.exchange(_request(launch.code))

    assert response.status == 303
    assert response.body() == b""
    assert response.headers["Location"] == "/#agent-management"
    assert launch.code not in response.headers["Location"]
    cookie = response.headers["Set-Cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE_NAME}=")
    assert f"Path={SESSION_COOKIE_PATH}" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Strict" in cookie
    assert "Max-Age=90" in cookie
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_secure_exchange_adds_secure_cookie_attribute():
    _, sessions, exchange = _services()
    launch = sessions.issue_launch_code("codex-local")
    response = exchange.exchange(_request(launch.code, secure=True))
    assert response.headers["Set-Cookie"].endswith("; Secure")


def test_replay_and_restarted_process_codes_are_unavailable():
    _, sessions, exchange = _services()
    launch = sessions.issue_launch_code("codex-local")
    assert exchange.exchange(_request(launch.code)).status == 303
    replay = exchange.exchange(_request(launch.code))
    assert replay.status == 410
    assert replay.payload["code"] == "agent_management_launch_code_unavailable"

    _, _, fresh_exchange = _services()
    restarted = fresh_exchange.exchange(_request(launch.code))
    assert restarted.status == 410
    assert restarted.payload["code"] == "agent_management_launch_code_unavailable"


def test_expired_and_malformed_codes_are_rejected():
    clock, sessions, exchange = _services()
    launch = sessions.issue_launch_code("codex-local")
    clock.advance(11)
    expired = exchange.exchange(_request(launch.code))
    malformed = exchange.exchange(_request("short"))
    assert expired.status == 410
    assert expired.payload["code"] == "agent_management_launch_code_expired"
    assert malformed.status == 400
    assert malformed.payload["code"] == "agent_management_launch_code_invalid"


def test_cross_origin_csrf_signals_are_rejected_before_code_consumption():
    _, sessions, exchange = _services()
    launch = sessions.issue_launch_code("codex-local")
    attempts = (
        _request(
            launch.code,
            origin="https://evil.test",
            fetch_site="cross-site",
        ),
        _request(launch.code, referer="https://evil.test/from"),
        _request(launch.code, host=""),
        _request(launch.code, origin="null"),
        _request(launch.code, fetch_site="same-site"),
    )
    for request in attempts:
        response = exchange.exchange(request)
        assert response.status == 403
        assert (
            response.payload["code"]
            == "agent_management_exchange_origin_forbidden"
        )

    accepted = exchange.exchange(
        _request(
            launch.code,
            origin="http://office.test:3000",
            referer="http://office.test:3000/",
            fetch_site="same-origin",
        )
    )
    assert accepted.status == 303
