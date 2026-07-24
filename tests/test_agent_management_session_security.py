from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.agent_management_browser import (
    AGENT_PREFIX,
    BOOTSTRAP_PATH,
    PROFILE_MUTATION_PATH,
    AgentManagementBrowserRoutes,
)
from services.agent_management_runtime import build_agent_management_runtime
from services.agent_management_session_exchange import SESSION_COOKIE_PATH
from services.agent_management_sessions import AgentManagementSessionService
from services.hr_repository import HRRepository, HRRepositoryError


class Clock:
    def __init__(self):
        self.value = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)

    def now(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


def _environment(tmp_path, *, clock=None):
    repository = HRRepository(tmp_path / "status")
    repository.initialize()
    for ai_id in ("codex-local", "hermes-default"):
        repository.upsert_agent(
            ai_id=ai_id,
            name=ai_id,
            agent_kind="project",
            provider_kind=ai_id.split("-", 1)[0],
            status="active",
            availability="available",
            source="test",
        )
    kwargs = {}
    if clock is not None:
        kwargs = {
            "now": clock.now,
            "idle_ttl_seconds": 30,
            "absolute_ttl_seconds": 90,
        }
    sessions = AgentManagementSessionService(**kwargs)
    profiles = build_agent_management_runtime(status_dir=tmp_path / "status")
    routes = AgentManagementBrowserRoutes(
        repository=repository,
        sessions=sessions,
        profiles=profiles.profiles,
        mutations=profiles.mutations,
    )
    return repository, sessions, routes


def _session(sessions, ai_id):
    return sessions.exchange_launch_code(
        sessions.issue_launch_code(ai_id).code
    )


def test_simultaneous_agent_sessions_cannot_switch_or_mutate_each_other(
    tmp_path,
):
    _, sessions, routes = _environment(tmp_path)
    codex = _session(sessions, "codex-local")
    hermes = _session(sessions, "hermes-default")

    codex_bootstrap = routes.get(
        BOOTSTRAP_PATH,
        {"aiId": ["hermes-default"]},
        session_token=codex.token,
        occurrence_key="codex-bootstrap",
    )
    hermes_bootstrap = routes.get(
        BOOTSTRAP_PATH,
        {"aiId": ["codex-local"]},
        session_token=hermes.token,
        occurrence_key="hermes-bootstrap",
    )
    spoof = routes.post(
        PROFILE_MUTATION_PATH,
        {
            "targetAiId": "hermes-default",
            "field": "name",
            "value": "Taken over",
            "expectedRevision": 0,
        },
        session_token=codex.token,
    )

    assert codex_bootstrap.payload["audience"]["aiId"] == "codex-local"
    assert hermes_bootstrap.payload["audience"]["aiId"] == "hermes-default"
    assert spoof.status == 403


def test_expired_session_can_reenter_only_with_a_new_launch_exchange(tmp_path):
    clock = Clock()
    _, sessions, routes = _environment(tmp_path, clock=clock)
    first = _session(sessions, "codex-local")
    clock.advance(31)
    expired = routes.get(
        BOOTSTRAP_PATH,
        {},
        session_token=first.token,
        occurrence_key="expired",
    )
    assert expired.status == 401

    second = _session(sessions, "codex-local")
    restored = routes.get(
        BOOTSTRAP_PATH,
        {},
        session_token=second.token,
        occurrence_key="reentered",
    )
    assert second.token != first.token
    assert restored.status == 200


def test_cross_agent_audit_failure_prevents_disclosure(
    monkeypatch,
    tmp_path,
):
    repository, sessions, routes = _environment(tmp_path)
    codex = _session(sessions, "codex-local")

    def fail_audit(**_kwargs):
        raise HRRepositoryError("audit unavailable")

    monkeypatch.setattr(repository, "record_successful_access", fail_audit)
    response = routes.get(
        f"{AGENT_PREFIX}hermes-default",
        {},
        session_token=codex.token,
        occurrence_key="audit-failure",
    )
    assert response.status == 503
    assert response.payload == {"ok": False, "code": "hr_audit_unavailable"}
    assert "hr" not in response.payload
    assert "profile" not in response.payload


def test_cookie_scope_is_limited_to_browser_agent_management_api():
    assert SESSION_COOKIE_PATH == "/api/agent-management/browser"
    assert not "/api/human-resources".startswith(SESSION_COOKIE_PATH)
    assert not "/api/agent-management/confirmations".startswith(
        SESSION_COOKIE_PATH
    )


def test_browser_assets_skills_and_workspace_templates_do_not_persist_secrets():
    browser_sources = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for pattern in ("*.js", "*.html")
        for path in APP_DIR.glob(pattern)
    )
    assert "vo_agent_management_session" not in browser_sources
    assert "localStorage.setItem('agent_management_launch" not in browser_sources
    assert 'localStorage.setItem("agent_management_launch' not in browser_sources

    inspected = []
    for root_name in ("skills", "templates"):
        root = ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.stat().st_size <= 1_000_000:
                inspected.append(
                    path.read_text(encoding="utf-8", errors="replace")
                )
    combined = "\n".join(inspected)
    assert "vo_agent_management_session" not in combined
    assert "agent_management_launch_code" not in combined
