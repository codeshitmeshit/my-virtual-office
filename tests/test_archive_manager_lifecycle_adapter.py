"""Compatibility tests for the Archive Manager shared-lifecycle adapter."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.archive_manager_lifecycle import (
    ARCHIVE_MANAGER_ACTIVITY_LIMIT,
    ArchiveManagerLifecycleAdapter,
    ArchiveManagerProfilePort,
    ArchiveManagerProviderPort,
    ArchiveManagerStateRepository,
    archive_manager_label,
)
from services.system_agent_lifecycle import (
    ActivityStatus,
    LifecycleStatus,
    ProviderAgent,
    SystemAgentLifecycleState,
    record_lifecycle_activity,
)
from services.system_agent_roles import ARCHIVE_MANAGER_ROLE
from system_agent_fakes import FakeClock, SequenceIdProvider


def repository(tmp_path):
    return ArchiveManagerStateRepository(
        tmp_path,
        clock=FakeClock(datetime(2026, 7, 19, 10, tzinfo=timezone.utc)),
    )


def test_missing_repository_uses_exact_legacy_archive_identity(tmp_path):
    state = repository(tmp_path).load()
    assert state.agent_id == "archive-manager"
    assert state.name == "档案管理员"
    assert state.emoji == "🗄️"
    assert state.provider_kind == "openclaw"
    assert state.status is LifecycleStatus.MISSING
    assert archive_manager_label(state) == "未接入"


def test_error_labels_distinguish_initial_creation_from_existing_repair(tmp_path):
    base = repository(tmp_path).load()
    initial_profile_failure = dataclass_replace(
        base,
        status=LifecycleStatus.ERROR,
        auto_created=True,
        last_action="profile_sync",
    )
    assert archive_manager_label(initial_profile_failure) == "档案管理员创建失败"
    existing_profile_failure = dataclass_replace(
        initial_profile_failure,
        profile_version="v0",
    )
    assert archive_manager_label(existing_profile_failure) == "档案管理员配置失败"
    initial_skill_failure = dataclass_replace(
        base,
        status=LifecycleStatus.ERROR,
        auto_created=True,
        last_action="skill_sync",
    )
    assert archive_manager_label(initial_skill_failure) == "档案管理员创建后通信技能未就绪"
    existing_skill_failure = dataclass_replace(
        initial_skill_failure,
        communication_skill={"ready": True},
    )
    assert archive_manager_label(existing_skill_failure) == "档案管理员通信技能未就绪"


def test_legacy_manager_json_round_trips_fields_and_flattens_activity_context(tmp_path):
    repo = repository(tmp_path)
    repo.archive_room_dir.mkdir(parents=True)
    legacy = {
        "agentId": "provider-archive-7",
        "name": "档案管理员",
        "emoji": "🗄️",
        "providerKind": "openclaw",
        "status": "idle",
        "label": "已接入",
        "phase": "phase-4",
        "paused": False,
        "autoCreated": False,
        "createdAt": "created",
        "updatedAt": "updated",
        "workspace": "/workspace",
        "profileFiles": ["IDENTITY.md"],
        "profileVersion": "v1",
        "profileUpdatedAt": "profile-updated",
        "communicationSkill": {"ready": True},
        "lastAction": "manual_maintain",
        "lastError": "",
        "recentActivity": [{
            "id": "event-1",
            "action": "manual_maintain",
            "status": "ok",
            "message": "done",
            "projectId": "project-1",
            "error": "",
            "at": "at",
        }],
    }
    repo.path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
    state = repo.load()
    assert state.agent_id == "provider-archive-7"
    assert state.recent_activity[0].context["projectId"] == "project-1"
    repo.save(ARCHIVE_MANAGER_ROLE, state)

    saved = json.loads(repo.path.read_text(encoding="utf-8"))
    assert saved["label"] == "已接入"
    assert saved["phase"] == "phase-4"
    assert saved["recentActivity"][0]["projectId"] == "project-1"
    assert "context" not in saved["recentActivity"][0]
    assert saved["profileVersion"] == "v1"
    assert saved["communicationSkill"] == {"ready": True}


def test_repository_bounds_activity_and_writes_atomically(tmp_path):
    repo = repository(tmp_path)
    state = repo.load()
    ids = SequenceIdProvider("activity")
    clock = FakeClock(datetime(2026, 7, 19, 10, tzinfo=timezone.utc))
    for index in range(20):
        state, _item = record_lifecycle_activity(
            state,
            action="test",
            status=ActivityStatus.OK,
            context={"index": index},
            clock=clock,
            new_id=ids,
            activity_limit=ARCHIVE_MANAGER_ACTIVITY_LIMIT,
        )
    repo.save(ARCHIVE_MANAGER_ROLE, state)
    payload = json.loads(repo.path.read_text(encoding="utf-8"))
    assert len(payload["recentActivity"]) == ARCHIVE_MANAGER_ACTIVITY_LIMIT
    assert payload["recentActivity"][-1]["index"] == 19
    assert not list(repo.archive_room_dir.glob(".manager.*.tmp"))


def test_repository_recovers_from_invalid_json_and_rejects_symlink_target(tmp_path):
    repo = repository(tmp_path)
    repo.archive_room_dir.mkdir(parents=True)
    repo.path.write_text("not-json", encoding="utf-8")
    assert repo.load().status is LifecycleStatus.MISSING

    repo.path.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text("outside", encoding="utf-8")
    repo.path.symlink_to(outside)
    with pytest.raises(ValueError, match="symbolic link"):
        repo.save(ARCHIVE_MANAGER_ROLE, repo.load())
    assert outside.read_text(encoding="utf-8") == "outside"


def test_profile_port_renders_exact_legacy_version_and_six_files(tmp_path):
    port = ArchiveManagerProfilePort(
        APP_DIR / "archive-manager-profile.md",
        tmp_path / "openclaw",
    )
    profile = port.render()
    assert profile.version == "2026-06-20.2"
    assert tuple(profile.files) == ARCHIVE_MANAGER_ROLE.required_files
    assert "档案管理员" in profile.files["IDENTITY.md"]
    assert "🗄️" in profile.files["IDENTITY.md"]
    assert "vo-archive-manager" in profile.files["AGENTS.md"]
    assert "不承担普通执行任务" in profile.files["agent.md"]


def test_profile_port_sync_is_idempotent_and_repairs_stale_file(tmp_path):
    port = ArchiveManagerProfilePort(
        APP_DIR / "archive-manager-profile.md",
        tmp_path / "openclaw",
    )
    workspace = port.workspace_for("archive-manager")
    agent = ProviderAgent(
        id="archive-manager",
        name="档案管理员",
        provider_kind="openclaw",
        workspace=str(workspace),
    )
    first = port.synchronize(ARCHIVE_MANAGER_ROLE, agent, workspace)
    assert first.updated is True
    assert first.written_files == ARCHIVE_MANAGER_ROLE.required_files
    second = port.synchronize(ARCHIVE_MANAGER_ROLE, agent, workspace)
    assert second.updated is False

    (workspace / "AGENTS.md").write_text("stale", encoding="utf-8")
    repaired = port.synchronize(ARCHIVE_MANAGER_ROLE, agent, workspace)
    assert repaired.written_files == ("AGENTS.md",)
    assert "vo-archive-manager" in (workspace / "AGENTS.md").read_text(encoding="utf-8")


def test_provider_port_preserves_openclaw_create_parameters_and_forced_discovery(tmp_path):
    profile = ArchiveManagerProfilePort(
        APP_DIR / "archive-manager-profile.md",
        tmp_path / "openclaw",
    )
    calls = []
    roster = [
        {"id": "main", "name": "Main", "providerKind": "openclaw"},
        {"id": "archive-manager", "name": "archive-manager", "providerKind": "openclaw"},
    ]

    def list_agents(force_refresh):
        calls.append(("list", force_refresh))
        return roster

    def create_agent(params, timeout):
        calls.append(("create", dict(params), timeout))
        return {"ok": True, "agentId": "archive-manager"}

    skill_payloads = []
    provider = ArchiveManagerProviderPort(
        list_agents=list_agents,
        create_agent=create_agent,
        profile_port=profile,
        sync_managed_skills=lambda payload: skill_payloads.append(payload) or {"ready": True},
        default_model=lambda: "test-model",
    )
    discovered = provider.discover(ARCHIVE_MANAGER_ROLE, force_refresh=True)
    assert [agent.id for agent in discovered] == ["archive-manager"]
    created = provider.create(ARCHIVE_MANAGER_ROLE)
    assert calls[-1] == (
        "create",
        {
            "name": "archive-manager",
            "workspace": str(tmp_path / "openclaw" / "workspace-archive-manager"),
            "emoji": "🗄️",
            "model": "test-model",
        },
        30,
    )
    assert provider.resolve_workspace(created) == tmp_path / "openclaw" / "workspace-archive-manager"
    assert provider.sync_managed_skills(created) == {"ready": True}
    assert skill_payloads[0]["statusKey"] == "archive-manager"


class StubLifecycle:
    def __init__(self, state):
        self.state = state
        self.calls = []

    def reconcile(self, role):
        self.calls.append(("reconcile", role.role_key))
        return self.state

    def pause(self, role):
        self.calls.append(("pause", role.role_key))
        self.state = dataclass_replace(self.state, paused=True, status=LifecycleStatus.PAUSED)
        return self.state

    def resume(self, role):
        self.calls.append(("resume", role.role_key))
        self.state = dataclass_replace(self.state, paused=False, status=LifecycleStatus.IDLE)
        return self.state


def dataclass_replace(state, **changes):
    from dataclasses import replace
    return replace(state, **changes)


def test_adapter_public_fields_labels_and_legacy_delegates(tmp_path):
    repo = repository(tmp_path)
    ready = dataclass_replace(
        repo.load(),
        status=LifecycleStatus.IDLE,
        auto_created=True,
        profile_version="v1",
    )
    repo.save(ARCHIVE_MANAGER_ROLE, ready)
    lifecycle = StubLifecycle(ready)
    adapter = ArchiveManagerLifecycleAdapter(lifecycle, repo)

    public = adapter.public_state(ensure=False)
    assert set(public) == {
        "agentId", "name", "emoji", "providerKind", "status", "label", "phase",
        "paused", "autoCreated", "createdAt", "updatedAt", "profileVersion",
        "profileUpdatedAt", "communicationSkill", "lastAction", "lastError",
        "recentActivity",
    }
    assert public["label"] == "已自动创建"
    assert adapter.create_if_missing() is ready
    assert adapter.profile_check_on_startup() is ready
    assert adapter.update("pause").paused is True
    assert adapter.update("resume").paused is False
    with pytest.raises(ValueError, match="pause or resume"):
        adapter.update("delete")


def test_adapter_identity_and_metadata_preserve_archive_specific_fields(tmp_path):
    repo = repository(tmp_path)
    state = dataclass_replace(
        repo.load(), agent_id="provider-archive-8", status=LifecycleStatus.IDLE,
    )
    repo.save(ARCHIVE_MANAGER_ROLE, state)
    adapter = ArchiveManagerLifecycleAdapter(StubLifecycle(state), repo)
    assert adapter.is_archive_manager("archive-manager") is True
    assert adapter.is_archive_manager("档案管理员") is True
    assert adapter.is_archive_manager({"statusKey": "provider-archive-8"}) is True
    assert adapter.is_archive_manager("ordinary-agent") is False
    assert adapter.agent_meta("provider-archive-8") == {
        "systemRole": "archive_manager",
        "assignable": False,
        "archiveManager": True,
        "archiveManagerStatus": "idle",
        "archiveManagerPaused": False,
        "archiveManagerLabel": "已接入",
    }
    assert adapter.agent_meta("ordinary-agent") == {}
