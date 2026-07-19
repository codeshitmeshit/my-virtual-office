"""Contract tests for provider-neutral system-Agent lifecycle state."""

import ast
import dataclasses
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.system_agent_lifecycle import (
    ActivityStatus,
    LifecycleActivity,
    LifecycleStatus,
    ProviderAgent,
    SystemAgentLifecycleState,
    SystemAgentPorts,
    normalize_lifecycle_status,
    record_lifecycle_activity,
    validate_activity_limit,
)
from services.system_agent_roles import HR_ROLE


def test_status_normalization_is_closed_and_pause_wins():
    assert normalize_lifecycle_status("ready") is LifecycleStatus.IDLE
    assert normalize_lifecycle_status("working") is LifecycleStatus.WORKING
    assert normalize_lifecycle_status("degraded") is LifecycleStatus.ERROR
    assert normalize_lifecycle_status("unknown-provider-state") is LifecycleStatus.MISSING
    assert normalize_lifecycle_status("error", paused=True) is LifecycleStatus.PAUSED


def test_initial_state_is_role_owned_and_timezone_aware():
    now = datetime(2026, 7, 19, 10, tzinfo=timezone(timedelta(hours=8)))
    state = SystemAgentLifecycleState.initial(HR_ROLE, now)
    assert state.role_key == "hr"
    assert state.agent_id == "hr"
    assert state.status is LifecycleStatus.MISSING
    assert state.updated_at == now.isoformat()
    with pytest.raises(ValueError, match="timezone-aware"):
        SystemAgentLifecycleState.initial(HR_ROLE, datetime(2026, 7, 19, 10))


def test_legacy_mapping_is_normalized_without_accepting_role_spoofing():
    state = SystemAgentLifecycleState.from_mapping(
        HR_ROLE,
        {
            "roleKey": "archive_manager",
            "agentId": "provider-hr-1",
            "providerKind": "openclaw",
            "status": "ready",
            "autoCreated": True,
            "profileFiles": ["IDENTITY.md", "AGENTS.md"],
            "communicationSkill": {"ready": True},
        },
        now="2026-07-19T10:00:00+08:00",
    )
    assert state.role_key == "hr"
    assert state.agent_id == "provider-hr-1"
    assert state.status is LifecycleStatus.IDLE
    assert state.auto_created is True
    assert state.to_mapping()["communicationSkill"] == {"ready": True}


def test_pause_flag_forces_paused_state_during_load_and_construction():
    loaded = SystemAgentLifecycleState.from_mapping(
        HR_ROLE, {"status": "idle", "paused": True}, now="now",
    )
    assert loaded.status is LifecycleStatus.PAUSED
    assert loaded.paused is True
    direct = dataclasses.replace(loaded, status=LifecycleStatus.ERROR)
    assert direct.status is LifecycleStatus.PAUSED


def test_invalid_activity_records_are_skipped_and_history_is_bounded():
    activity = [
        {"id": f"id-{index}", "action": "reconcile", "status": "ok", "at": f"t-{index}"}
        for index in range(15)
    ]
    activity.insert(2, {"not": "an activity"})
    activity.insert(5, "bad")
    state = SystemAgentLifecycleState.from_mapping(
        HR_ROLE, {"recentActivity": activity}, now="now", activity_limit=4,
    )
    assert [item.id for item in state.recent_activity] == ["id-11", "id-12", "id-13", "id-14"]


def test_record_activity_is_immutable_bounded_and_clears_prior_error():
    moments = iter(
        datetime(2026, 7, 19, 10, minute=index, tzinfo=timezone.utc)
        for index in range(5)
    )
    identifiers = iter(f"event-{index}" for index in range(5))
    original = dataclasses.replace(
        SystemAgentLifecycleState.initial(HR_ROLE, "start"), last_error="old error",
    )
    current = original
    for index in range(5):
        current, item = record_lifecycle_activity(
            current,
            action=f"action-{index}",
            status=ActivityStatus.OK,
            context={"index": index},
            clock=lambda: next(moments),
            new_id=lambda: next(identifiers),
            activity_limit=3,
        )
    assert original.recent_activity == ()
    assert [item.id for item in current.recent_activity] == ["event-2", "event-3", "event-4"]
    assert current.last_action == "action-4"
    assert current.last_error == ""
    with pytest.raises(TypeError):
        item.context["index"] = 99


@pytest.mark.parametrize("limit", (True, 0, -1, 101, 1.5, "12"))
def test_activity_limit_validation_rejects_invalid_bounds(limit):
    with pytest.raises(ValueError, match="activity limit"):
        validate_activity_limit(limit)


def test_provider_agent_and_nested_state_are_defensively_immutable():
    raw = {"id": "hr", "nested": {"value": 1}}
    agent = ProviderAgent.from_mapping(raw, default_provider_kind="openclaw")
    raw["id"] = "changed"
    raw["nested"]["value"] = 2
    assert agent.id == "hr"
    assert agent.raw["nested"]["value"] == 1
    with pytest.raises(TypeError):
        agent.raw["new"] = True
    with pytest.raises(TypeError):
        agent.raw["nested"]["value"] = 3

    skill = {"ready": True, "details": {"version": 1}}
    state = dataclasses.replace(SystemAgentLifecycleState.initial(HR_ROLE, "now"), communication_skill=skill)
    skill["ready"] = False
    skill["details"]["version"] = 2
    assert state.communication_skill["ready"] is True
    assert state.communication_skill["details"]["version"] == 1
    assert state.to_mapping()["communicationSkill"]["details"] == {"version": 1}
    copied = dataclasses.replace(state, last_action="copied")
    assert copied.communication_skill["details"]["version"] == 1


def test_ports_bundle_is_immutable_and_requires_explicit_collaborators():
    marker = object()
    ports = SystemAgentPorts(
        provider=marker,
        profiles=marker,
        state=marker,
        presence=marker,
        clock=lambda: datetime.now(timezone.utc),
        new_id=lambda: "id",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        ports.provider = object()


def test_lifecycle_module_has_no_legacy_entrypoint_or_transport_imports():
    path = APP_DIR / "services" / "system_agent_lifecycle.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(name == "server" or name.endswith(".server") for name in imported)
    assert not any(name in {"http", "urllib", "flask", "fastapi"} for name in imported)
