from __future__ import annotations

import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services import agent_legacy_mutation_policy as policy


def test_every_retained_legacy_agent_write_requires_management():
    routes = (
        ("POST", "/api/office-config"),
        ("POST", "/api/agent-workspace/codex-local"),
        ("POST", "/api/agent/codex-local/skills"),
        ("POST", "/api/skills-library"),
        ("POST", "/api/skills-library/apply"),
        ("DELETE", "/api/agent/codex-local/skills/reviewer"),
        ("DELETE", "/api/skills-library/reviewer"),
    )
    assert all(policy.requires_management(method, path) for method, path in routes)
    assert not policy.requires_management("GET", "/api/agent-workspace/codex-local")
    assert not policy.requires_management("POST", "/api/presence/codex-local")


def test_old_high_risk_routes_are_removed_instead_of_accepting_boolean_confirmation():
    for method, path in (
        ("POST", "/api/agent/create"),
        ("DELETE", "/api/agent/delete"),
        ("POST", "/set-model"),
    ):
        assert policy.requires_management(method, path)
        decision = policy.retired_route(method, path)
        assert decision.allowed is False
        assert decision.status == 410
        assert decision.response()["code"] == "agent_management_route_migrated"


def test_office_config_allows_layout_only_and_rejects_agent_or_branch_changes():
    current = {
        "agents": [{"id": "codex-local", "role": "Backend"}],
        "branches": [{"id": "hq", "name": "总部"}],
        "layout": {"zoom": 1},
    }
    assert policy.office_config_update(
        current,
        {**current, "layout": {"zoom": 2}},
    ).allowed

    agent_change = policy.office_config_update(
        current,
        {**current, "agents": [{"id": "codex-local", "role": "HR"}]},
    )
    assert agent_change.allowed is False
    assert agent_change.status == 410

    omitted_owned_state = policy.office_config_update(
        current,
        {"layout": {"zoom": 2}},
    )
    assert omitted_owned_state.allowed is False


def test_workspace_settings_cannot_mutate_profile_or_branch():
    for field in ("name", "displayName", "role", "branch", "emoji", "color"):
        decision = policy.workspace_update(
            {"action": "updateSettings", field: "replacement"}
        )
        assert decision.allowed is False
        assert decision.status == 410

    assert policy.workspace_update(
        {"action": "updateSettings", "heartbeatMinutes": 15}
    ).allowed
    assert policy.workspace_update(
        {"action": "saveAgentSkill", "name": "review"}
    ).allowed
