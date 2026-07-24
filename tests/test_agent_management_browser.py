from __future__ import annotations

import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.agent_management_browser import (
    ACCESS_LOG_PATH,
    AGENT_PREFIX,
    BOOTSTRAP_PATH,
    PROFILE_MUTATION_PATH,
    PROFILE_UNDO_PATH,
    AgentManagementBrowserRoutes,
)
from services.agent_management_runtime import build_agent_management_runtime
from services.agent_management_sessions import AgentManagementSessionService
from services.hr_repository import HRRepository


def _runtime(tmp_path):
    repository = HRRepository(tmp_path / "status")
    repository.initialize()
    for ai_id, provider in (
        ("codex-local", "codex"),
        ("hermes-default", "hermes"),
    ):
        repository.upsert_agent(
            ai_id=ai_id,
            name=ai_id,
            agent_kind="project",
            provider_kind=provider,
            status="active",
            availability="available",
            source="test",
        )
    sessions = AgentManagementSessionService()
    launch = sessions.issue_launch_code("codex-local")
    session = sessions.exchange_launch_code(launch.code)
    management = build_agent_management_runtime(status_dir=tmp_path / "status")
    routes = AgentManagementBrowserRoutes(
        repository=repository,
        sessions=sessions,
        profiles=management.profiles,
        mutations=management.mutations,
    )
    return repository, sessions, session, management, routes


def test_cookie_parser_accepts_only_the_scoped_opaque_cookie():
    token = "x" * 40
    assert (
        AgentManagementBrowserRoutes.session_token(
            f"other=1; vo_agent_management_session={token}"
        )
        == token
    )
    assert AgentManagementBrowserRoutes.session_token("other=1") is None
    assert (
        AgentManagementBrowserRoutes.session_token(
            "vo_agent_management_session=short"
        )
        is None
    )


def test_bootstrap_is_agent_audience_and_provider_neutral(tmp_path):
    _, _, session, _, routes = _runtime(tmp_path)
    response = routes.get(
        BOOTSTRAP_PATH,
        {},
        session_token=session.token,
        occurrence_key="bootstrap-1",
    )
    assert response.status == 200
    assert response.payload["audience"] == {
        "kind": "agent",
        "aiId": "codex-local",
    }
    assert {item["aiId"] for item in response.payload["items"]} == {
        "codex-local",
        "hermes-default",
    }
    assert "providerKind" not in response.payload["items"][0]


def test_self_low_risk_mutation_and_undo_use_session_identity(tmp_path):
    _, _, session, _, routes = _runtime(tmp_path)
    saved = routes.post(
        PROFILE_MUTATION_PATH,
        {
            "targetAiId": "codex-local",
            "field": "introduction",
            "value": "Builds backends",
            "expectedRevision": 0,
        },
        session_token=session.token,
    )
    denied_other = routes.post(
        PROFILE_MUTATION_PATH,
        {
            "targetAiId": "hermes-default",
            "field": "name",
            "value": "Spoofed",
            "expectedRevision": 0,
        },
        session_token=session.token,
    )
    denied_restricted = routes.post(
        PROFILE_MUTATION_PATH,
        {
            "targetAiId": "codex-local",
            "field": "branch",
            "value": "finance",
            "expectedRevision": saved.payload["revision"],
        },
        session_token=session.token,
    )
    undone = routes.post(
        PROFILE_UNDO_PATH,
        {
            "undoToken": saved.payload["undoToken"],
            "expectedRevision": saved.payload["revision"],
        },
        session_token=session.token,
    )

    assert saved.status == 200
    assert denied_other.status == 403
    assert denied_restricted.status == 403
    assert undone.status == 200


def test_self_and_public_detail_do_not_leak_restricted_hr_fields(tmp_path):
    repository, _, session, _, routes = _runtime(tmp_path)
    self_detail = routes.get(
        f"{AGENT_PREFIX}codex-local",
        {},
        session_token=session.token,
        occurrence_key="self-1",
    )
    public_detail = routes.get(
        f"{AGENT_PREFIX}hermes-default",
        {},
        session_token=session.token,
        occurrence_key="public-1",
    )

    assert self_detail.status == 200
    assert self_detail.payload["scope"] == "self"
    assert public_detail.status == 200
    assert public_detail.payload["scope"] == "public"
    assert "reports" not in public_detail.payload["hr"]
    assert "assessments" not in public_detail.payload["hr"]
    assert "accessHistory" not in public_detail.payload["hr"]
    logs = repository.list_access_log().items
    assert len(logs) == 1
    assert (logs[0].viewer_ai_id, logs[0].target_ai_id) == (
        "codex-local",
        "hermes-default",
    )


def test_access_history_is_always_for_session_target(tmp_path):
    repository, _, session, _, routes = _runtime(tmp_path)
    repository.record_successful_access(
        access_id="view-1",
        viewer_ai_id="hermes-default",
        target_ai_id="codex-local",
        viewed_at="2026-07-24T12:00:00+00:00",
        scope="public_work_summary",
        request_source="test",
        occurrence_key="view-1",
    )
    response = routes.get(
        ACCESS_LOG_PATH,
        {"targetAiId": ["hermes-default"]},
        session_token=session.token,
        occurrence_key="access-1",
    )
    assert response.status == 200
    assert {item["targetAiId"] for item in response.payload["items"]} == {
        "codex-local"
    }


def test_every_request_rechecks_active_directory_state_and_invalidates(
    tmp_path,
):
    repository, sessions, session, _, routes = _runtime(tmp_path)
    repository.upsert_agent(
        ai_id="codex-local",
        name="codex-local",
        agent_kind="project",
        provider_kind="codex",
        status="disabled",
        availability="unavailable",
        source="test",
    )
    response = routes.get(
        BOOTSTRAP_PATH,
        {},
        session_token=session.token,
        occurrence_key="disabled-1",
    )
    assert response.status == 403
    assert response.payload["code"] == "agent_management_agent_inactive"
    assert sessions.invalidate(session.token) is False


def test_browser_routes_never_claim_human_or_high_risk_paths():
    assert AgentManagementBrowserRoutes.handles("GET", BOOTSTRAP_PATH)
    assert AgentManagementBrowserRoutes.handles("POST", PROFILE_MUTATION_PATH)
    assert not AgentManagementBrowserRoutes.handles(
        "POST", "/api/agent-management/confirmations"
    )
    assert not AgentManagementBrowserRoutes.handles(
        "GET", "/api/human-resources/overview"
    )
