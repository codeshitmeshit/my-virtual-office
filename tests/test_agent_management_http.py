from __future__ import annotations

import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services import agent_management_http
from services.agent_management_runtime import build_agent_management_runtime


def test_runtime_builds_focused_routes_and_persists_profile(tmp_path):
    runtime = build_agent_management_runtime(status_dir=tmp_path)

    saved = runtime.routes.post(
        agent_management_http.PROFILE_MUTATION_PATH,
        {
            "targetAiId": "codex-local",
            "field": "name",
            "value": "Codex",
            "expectedRevision": 0,
        },
    )

    assert saved.status == 200
    assert saved.payload["saveState"] == "saved"
    assert (
        tmp_path / "agent-management" / "profiles.json"
    ).is_file()
    loaded = runtime.routes.get(
        f"{agent_management_http.PROFILE_PREFIX}codex-local"
    )
    assert loaded.status == 200
    assert loaded.payload["profile"]["name"] == "Codex"


def test_http_routes_delegate_mutation_undo_and_conflict(tmp_path):
    routes = build_agent_management_runtime(status_dir=tmp_path).routes
    first = routes.post(
        agent_management_http.PROFILE_MUTATION_PATH,
        {
            "targetAiId": "codex-local",
            "field": "introduction",
            "value": "Builds services",
            "expectedRevision": 0,
        },
    )
    conflict = routes.post(
        agent_management_http.PROFILE_MUTATION_PATH,
        {
            "targetAiId": "codex-local",
            "field": "introduction",
            "value": "Stale",
            "expectedRevision": 0,
        },
    )
    undone = routes.post(
        agent_management_http.PROFILE_UNDO_PATH,
        {
            "undoToken": first.payload["undoToken"],
            "expectedRevision": first.payload["revision"],
        },
    )

    assert first.status == 200
    assert conflict.status == 409
    assert conflict.payload["code"] == "agent_profile_revision_conflict"
    assert undone.status == 200
    assert undone.payload["saveState"] == "undone"


def test_http_routes_issue_payload_bound_confirmation(tmp_path):
    routes = build_agent_management_runtime(status_dir=tmp_path).routes
    response = routes.post(
        agent_management_http.CONFIRMATION_PATH,
        {
            "targetAiId": "codex-local",
            "action": "branch",
            "before": {"branch": "hq"},
            "after": {"branch": "finance"},
            "revision": 3,
        },
    )

    assert response.status == 201
    assert response.payload["confirmation"]["targetAiId"] == "codex-local"
    assert response.payload["confirmation"]["action"] == "branch"
    assert "challengeToken" in response.payload["confirmation"]


def test_http_route_shape_is_strict_and_does_not_claim_future_session_paths(
    tmp_path,
):
    routes = build_agent_management_runtime(status_dir=tmp_path).routes
    invalid = routes.post(
        agent_management_http.CONFIRMATION_PATH,
        {"confirmed": True},
    )

    assert invalid.status == 400
    assert not routes.handles("POST", "/api/agent-management/sessions")
    assert routes.handles("POST", agent_management_http.PROFILE_MUTATION_PATH)
    assert routes.handles("GET", "/api/agent-management/profiles/codex-local")
