from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.agent_management_sessions import (
    AgentManagementBrowserSessionExpiredError,
    AgentManagementLaunchCodeExpiredError,
    AgentManagementLaunchCodeUnavailableError,
    AgentManagementSessionCapacityError,
    AgentManagementSessionService,
    AgentManagementSessionValidationError,
)


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
        return f"secret-{self.index:04d}-" + "x" * 40


def _service(clock=None, secrets=None, **kwargs):
    clock = clock or Clock()
    secrets = secrets or Secrets()
    return AgentManagementSessionService(
        now=clock.now,
        secret_factory=secrets,
        launch_ttl_seconds=10,
        idle_ttl_seconds=30,
        absolute_ttl_seconds=90,
        **kwargs,
    )


def test_launch_exchange_stores_only_digests_and_is_single_use():
    service = _service()
    launch = service.issue_launch_code("codex-local")
    digest = hashlib.sha256(launch.code.encode()).hexdigest()

    assert launch.code not in service._launch_codes
    assert digest in service._launch_codes
    session = service.exchange_launch_code(launch.code)
    session_digest = hashlib.sha256(session.token.encode()).hexdigest()
    assert session.token not in service._sessions
    assert session_digest in service._sessions
    assert service.resolve(session.token).ai_id == "codex-local"

    with pytest.raises(AgentManagementLaunchCodeUnavailableError):
        service.exchange_launch_code(launch.code)


def test_launch_expiry_cleanup_and_restart_invalidation():
    clock = Clock()
    service = _service(clock)
    launch = service.issue_launch_code("codex-local")
    clock.advance(11)
    with pytest.raises(AgentManagementLaunchCodeExpiredError):
        service.exchange_launch_code(launch.code)

    fresh_process = _service(clock)
    with pytest.raises(AgentManagementLaunchCodeUnavailableError):
        fresh_process.exchange_launch_code(launch.code)


def test_session_idle_expiry_slides_but_never_exceeds_absolute_expiry():
    clock = Clock()
    service = _service(clock)
    launch = service.issue_launch_code("codex-local")
    session = service.exchange_launch_code(launch.code)
    absolute = session.absolute_expires_at

    clock.advance(20)
    refreshed = service.resolve(session.token)
    assert refreshed.idle_expires_at == clock.now() + timedelta(seconds=30)
    clock.advance(29)
    refreshed = service.resolve(session.token)
    assert refreshed.idle_expires_at < absolute
    clock.advance(29)
    refreshed = service.resolve(session.token)
    assert refreshed.idle_expires_at == absolute
    clock.advance(13)
    with pytest.raises(AgentManagementBrowserSessionExpiredError):
        service.resolve(session.token)


def test_idle_expiry_and_explicit_invalidation_fail_closed():
    clock = Clock()
    service = _service(clock)
    first = service.exchange_launch_code(
        service.issue_launch_code("codex-local").code
    )
    clock.advance(31)
    with pytest.raises(AgentManagementBrowserSessionExpiredError):
        service.resolve(first.token)

    second = service.exchange_launch_code(
        service.issue_launch_code("codex-local").code
    )
    assert service.invalidate(second.token) is True
    assert service.invalidate(second.token) is False
    with pytest.raises(AgentManagementBrowserSessionExpiredError):
        service.resolve(second.token)


def test_per_agent_and_global_launch_caps_are_enforced_then_cleanup_recovers():
    clock = Clock()
    service = _service(
        clock,
        max_launch_codes=2,
        max_launch_codes_per_agent=1,
    )
    service.issue_launch_code("codex-local")
    with pytest.raises(AgentManagementSessionCapacityError):
        service.issue_launch_code("codex-local")
    service.issue_launch_code("hermes-default")
    with pytest.raises(AgentManagementSessionCapacityError):
        service.issue_launch_code("claude-code-local")

    clock.advance(11)
    assert service.cleanup() == {
        "launchCodesRemoved": 2,
        "sessionsRemoved": 0,
    }
    assert service.issue_launch_code("codex-local").ai_id == "codex-local"


def test_per_agent_and_global_session_caps_are_enforced():
    service = _service(
        max_sessions=2,
        max_sessions_per_agent=1,
        max_launch_codes=5,
        max_launch_codes_per_agent=3,
    )
    service.exchange_launch_code(service.issue_launch_code("codex-local").code)
    second_launch = service.issue_launch_code("codex-local")
    with pytest.raises(AgentManagementSessionCapacityError):
        service.exchange_launch_code(second_launch.code)
    service.exchange_launch_code(service.issue_launch_code("hermes-default").code)
    third_launch = service.issue_launch_code("claude-code-local")
    with pytest.raises(AgentManagementSessionCapacityError):
        service.exchange_launch_code(third_launch.code)


def test_identity_and_constructor_bounds_are_validated():
    service = _service()
    for invalid in ("", "../main", "bad/id", "bad\x00id"):
        with pytest.raises(AgentManagementSessionValidationError):
            service.issue_launch_code(invalid)

    with pytest.raises(ValueError):
        AgentManagementSessionService(idle_ttl_seconds=10)
    with pytest.raises(ValueError):
        AgentManagementSessionService(
            idle_ttl_seconds=60,
            absolute_ttl_seconds=30,
        )
    with pytest.raises(ValueError):
        AgentManagementSessionService(
            max_sessions=1,
            max_sessions_per_agent=2,
        )
