"""HR adapter coverage against deterministic fake OpenClaw boundaries."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_lifecycle import (
    HR_ACTIVITY_LIMIT,
    HRLifecycleAdapter,
    HRProfilePort,
    HRProviderPort,
    HRStateRepository,
    hr_label,
)
from services.system_agent_lifecycle import (
    ActivityStatus,
    LifecycleStatus,
    ProviderAgent,
    SystemAgentLifecycleService,
    SystemAgentPorts,
    record_lifecycle_activity,
)
from services.system_agent_roles import HR_ROLE
from system_agent_fakes import FakeClock, SequenceIdProvider


class FakePresence:
    def __init__(self):
        self.calls = []

    def set_presence(self, agent_id, state, reason=""):
        self.calls.append((agent_id, state, reason))


def repository(tmp_path, clock=None):
    return HRStateRepository(
        tmp_path / "status",
        clock=clock or FakeClock(datetime(2026, 7, 19, 10, tzinfo=timezone.utc)),
    )


def build_adapter(
    tmp_path,
    *,
    roster=None,
    create_result=None,
    skill_result=None,
    profile_path=None,
    list_agents=None,
):
    clock = FakeClock(datetime(2026, 7, 19, 10, tzinfo=timezone.utc))
    roster = [] if roster is None else roster
    calls = []
    openclaw_home = tmp_path / "openclaw"
    profile = HRProfilePort(profile_path or APP_DIR / "hr-profile.md", openclaw_home)

    def default_list(force_refresh):
        calls.append(("list", force_refresh))
        return list(roster)

    def create(params, timeout):
        calls.append(("create", dict(params), timeout))
        result = create_result if create_result is not None else {"ok": True, "agentId": "hr"}
        if result.get("ok"):
            roster.append({
                "id": result.get("agentId") or "hr",
                "name": params["name"],
                "providerKind": "openclaw",
                "workspace": params["workspace"],
            })
        return result

    def sync_skill(payload):
        calls.append(("skill", dict(payload)))
        return skill_result if skill_result is not None else {"ready": True, "status": "ready"}

    provider = HRProviderPort(
        list_agents=list_agents or default_list,
        create_agent=create,
        profile_port=profile,
        sync_managed_skills=sync_skill,
        default_model=lambda: "test-model",
    )
    repo = repository(tmp_path, clock)
    presence = FakePresence()
    lifecycle = SystemAgentLifecycleService(
        SystemAgentPorts(
            provider=provider,
            profiles=profile,
            state=repo,
            presence=presence,
            clock=clock,
            new_id=SequenceIdProvider("hr-event"),
        ),
        provider_retry_limit=0,
        activity_limit=HR_ACTIVITY_LIMIT,
    )
    return HRLifecycleAdapter(lifecycle, repo), calls, roster, presence


def test_repository_defaults_to_missing_hr_without_creating_storage(tmp_path):
    repo = repository(tmp_path)
    state = repo.load()
    assert repo.path == tmp_path / "status" / "human-resources" / "hr.json"
    assert repo.path.exists() is False
    assert state.agent_id == "hr"
    assert state.name == "HR"
    assert state.status is LifecycleStatus.MISSING
    assert hr_label(state) == "未接入"


def test_repository_round_trip_bounds_activity_and_writes_atomically(tmp_path):
    clock = FakeClock(datetime(2026, 7, 19, 10, tzinfo=timezone.utc))
    repo = repository(tmp_path, clock)
    state = repo.load()
    ids = SequenceIdProvider("activity")
    for index in range(HR_ACTIVITY_LIMIT + 5):
        state, _ = record_lifecycle_activity(
            state,
            action="directory_sync",
            status=ActivityStatus.OK,
            context={"index": index},
            clock=clock,
            new_id=ids,
            activity_limit=HR_ACTIVITY_LIMIT,
        )
    repo.save(HR_ROLE, state)
    saved = json.loads(repo.path.read_text(encoding="utf-8"))
    assert saved["roleKey"] == "hr"
    assert saved["label"] == "未接入"
    assert len(saved["recentActivity"]) == HR_ACTIVITY_LIMIT
    assert saved["recentActivity"][-1]["context"]["index"] == HR_ACTIVITY_LIMIT + 4
    assert len(repo.public_state()["recentActivity"]) == 12
    assert not list(repo.hr_dir.glob(".hr.*.tmp"))


def test_repository_recovers_invalid_json_and_rejects_symlink_target(tmp_path):
    repo = repository(tmp_path)
    repo.hr_dir.mkdir(parents=True)
    repo.path.write_text("not-json", encoding="utf-8")
    assert repo.load().status is LifecycleStatus.MISSING

    state = repo.load()
    repo.path.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text("outside", encoding="utf-8")
    repo.path.symlink_to(outside)
    with pytest.raises(ValueError, match="symbolic link"):
        repo.save(HR_ROLE, state)
    assert outside.read_text(encoding="utf-8") == "outside"


def test_profile_port_renders_syncs_idempotently_and_repairs_stale_files(tmp_path):
    profile = HRProfilePort(APP_DIR / "hr-profile.md", tmp_path / "openclaw")
    rendered = profile.render()
    assert rendered.version == "2026-07-19.1"
    assert tuple(rendered.files) == HR_ROLE.required_files
    workspace = profile.workspace_for("hr")
    agent = ProviderAgent("hr", "HR", "openclaw", str(workspace))

    first = profile.synchronize(HR_ROLE, agent, workspace)
    assert first.updated is True
    assert first.written_files == HR_ROLE.required_files
    assert profile.synchronize(HR_ROLE, agent, workspace).updated is False
    (workspace / "AGENTS.md").write_text("stale", encoding="utf-8")
    repaired = profile.synchronize(HR_ROLE, agent, workspace)
    assert repaired.written_files == ("AGENTS.md",)
    assert "vo.hr.assessment.v1" in (workspace / "AGENTS.md").read_text(encoding="utf-8")


def test_provider_uses_stable_openclaw_identity_and_managed_skill_payload(tmp_path):
    adapter, calls, roster, _presence = build_adapter(tmp_path)
    state = adapter.reconcile()
    assert state.status is LifecycleStatus.IDLE
    assert state.auto_created is True
    assert state.agent_id == "hr"
    create = next(call for call in calls if call[0] == "create")
    assert create == (
        "create",
        {
            "name": "HR",
            "workspace": str(tmp_path / "openclaw" / "workspace-hr"),
            "emoji": "🧑‍💼",
            "model": "test-model",
        },
        30,
    )
    skill = next(call for call in calls if call[0] == "skill")
    assert skill[1]["statusKey"] == "hr"
    assert roster[0]["id"] == "hr"


def test_public_state_canonicalizes_legacy_mixed_case_hr_name(tmp_path):
    repo = repository(tmp_path)
    repo.hr_dir.mkdir(parents=True)
    repo.path.write_text(
        json.dumps({"roleKey": "hr", "agentId": "hr", "name": "Hr", "status": "idle"}),
        encoding="utf-8",
    )
    assert repo.public_state()["name"] == "HR"


def test_repeated_and_restarted_reconcile_rediscovers_one_hr_and_repairs_profile(tmp_path):
    adapter, calls, roster, _presence = build_adapter(tmp_path)
    first = adapter.reconcile()
    assert first.profile_version == "2026-07-19.1"
    (tmp_path / "openclaw" / "workspace-hr" / "SOUL.md").write_text("stale", encoding="utf-8")
    second = adapter.reconcile()
    assert second.status is LifecycleStatus.IDLE
    assert "single global Human Resources Agent" in (
        tmp_path / "openclaw" / "workspace-hr" / "SOUL.md"
    ).read_text(encoding="utf-8")
    restarted, restarted_calls, _same_roster, _presence = build_adapter(tmp_path, roster=roster)
    third = restarted.reconcile()
    assert third.agent_id == "hr"
    assert third.auto_created is True
    assert len([call for call in calls + restarted_calls if call[0] == "create"]) == 1


def test_pause_resume_and_public_state_use_shared_lifecycle(tmp_path):
    adapter, _calls, _roster, presence = build_adapter(tmp_path)
    adapter.reconcile()
    paused = adapter.update("pause")
    assert paused.status is LifecycleStatus.PAUSED
    assert adapter.public_state(ensure=False)["label"] == "已暂停"
    assert presence.calls[-1][1] == "break"

    resumed = adapter.update("resume")
    assert resumed.status is LifecycleStatus.IDLE
    assert adapter.public_state(ensure=False)["label"] == "已自动创建"
    assert presence.calls[-1][1] == "idle"
    with pytest.raises(ValueError, match="pause or resume"):
        adapter.update("delete")


def test_adapter_recognizes_stable_display_explicit_and_persisted_hr_identities(tmp_path):
    adapter, _calls, _roster, _presence = build_adapter(
        tmp_path,
        roster=[{
            "id": "provider-hr-7",
            "name": "HR",
            "providerKind": "openclaw",
            "workspace": str(tmp_path / "openclaw" / "workspace-provider-hr-7"),
        }],
    )
    state = adapter.reconcile()
    assert state.agent_id == "provider-hr-7"
    assert adapter.is_hr("hr") is True
    assert adapter.is_hr("HR") is True
    assert adapter.is_hr({"systemRole": "hr", "id": "renamed"}) is True
    assert adapter.is_hr("provider-hr-7") is True
    assert adapter.is_hr("ordinary-agent") is False


def test_legacy_mixed_case_provider_name_is_reused_without_duplicate_creation(tmp_path):
    adapter, calls, _roster, _presence = build_adapter(
        tmp_path,
        roster=[{
            "id": "provider-hr-legacy",
            "name": "Hr",
            "providerKind": "openclaw",
            "workspace": str(tmp_path / "openclaw" / "workspace-provider-hr-legacy"),
        }],
    )
    state = adapter.reconcile()
    assert state.agent_id == "provider-hr-legacy"
    assert state.name == "HR"
    assert not [call for call in calls if call[0] == "create"]


@pytest.mark.parametrize(
    ("failure", "expected_action", "expected_label"),
    [
        ("discover", "discover", "HR 接入失败"),
        ("create", "create", "HR 接入失败"),
        ("profile", "profile_sync", "HR Profile 配置失败"),
        ("skill", "skill_sync", "HR 通信技能未就绪"),
    ],
)
def test_provider_profile_and_skill_failures_degrade_to_persisted_error(
    tmp_path, failure, expected_action, expected_label,
):
    kwargs = {}
    if failure == "discover":
        kwargs["list_agents"] = lambda _force: (_ for _ in ()).throw(RuntimeError("offline"))
    elif failure == "create":
        kwargs["create_result"] = {"ok": False, "error": "denied"}
    elif failure == "profile":
        kwargs["profile_path"] = tmp_path / "missing-profile.md"
        kwargs["roster"] = [{"id": "hr", "name": "HR", "providerKind": "openclaw"}]
    elif failure == "skill":
        kwargs["skill_result"] = {"ready": False, "status": "grant unavailable"}
    adapter, _calls, _roster, _presence = build_adapter(tmp_path, **kwargs)
    state = adapter.reconcile()
    assert state.status is LifecycleStatus.ERROR
    assert state.last_action == expected_action
    assert hr_label(state) == expected_label
    persisted = json.loads(adapter.repository.path.read_text(encoding="utf-8"))
    assert persisted["status"] == "error"
    assert persisted["lastError"]


def test_duplicate_hr_candidates_fail_closed_without_creating_another(tmp_path):
    roster = [
        {"id": "hr", "name": "HR", "providerKind": "openclaw"},
        {"id": "provider-hr-2", "name": "HR", "providerKind": "openclaw"},
    ]
    adapter, calls, _roster, _presence = build_adapter(tmp_path, roster=roster)
    state = adapter.reconcile()
    assert state.status is LifecycleStatus.ERROR
    assert state.last_action == "duplicate_detected"
    assert hr_label(state) == "HR 身份冲突"
    assert not [call for call in calls if call[0] == "create"]
