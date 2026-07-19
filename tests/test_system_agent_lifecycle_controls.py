"""Pause, resume, projection, and degraded-read lifecycle coverage."""

import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.system_agent_lifecycle import LifecycleStatus, SystemAgentLifecycleState
from services.system_agent_roles import HR_ROLE
from system_agent_fakes import TemporarySystemAgentWorkspace
from test_system_agent_lifecycle_reconcile import build_service, existing_hr, operations


def test_pause_reconciles_then_persists_pause_and_presence():
    with TemporarySystemAgentWorkspace() as workspace:
        service, provider, _profiles, repository = build_service(
            workspace, agents=(existing_hr(workspace),),
        )
        state = service.pause(HR_ROLE)
        assert state.status is LifecycleStatus.PAUSED
        assert state.paused is True
        assert state.last_action == "pause"
        assert service._ports.presence.calls == [
            ("hr", "break", "System Agent paused by human control"),
        ]
        assert repository.value is state
        assert len(operations(provider, "create")) == 0


def test_pause_presence_failure_keeps_pause_and_exposes_error():
    with TemporarySystemAgentWorkspace() as workspace:
        service, _provider, _profiles, repository = build_service(
            workspace, agents=(existing_hr(workspace),),
        )

        def fail_presence(*_args, **_kwargs):
            raise RuntimeError("presence unavailable")

        service._ports.presence.set_presence = fail_presence
        state = service.pause(HR_ROLE)
        assert state.status is LifecycleStatus.PAUSED
        assert state.paused is True
        assert state.last_action == "presence"
        assert state.last_error == "presence unavailable"
        assert repository.value is state


def test_pausing_degraded_agent_preserves_provider_error():
    with TemporarySystemAgentWorkspace() as workspace:
        service, provider, _profiles, _repository = build_service(workspace)
        provider.fail_next("discover", TimeoutError("provider down"))
        provider.fail_next("discover", TimeoutError("provider still down"))
        state = service.pause(HR_ROLE)
        assert state.paused is True
        assert state.status is LifecycleStatus.PAUSED
        assert state.last_error == "provider still down"


def test_resume_clears_pause_only_after_successful_reconciliation():
    with TemporarySystemAgentWorkspace() as workspace:
        paused = SystemAgentLifecycleState.from_mapping(
            HR_ROLE,
            {"agentId": "hr", "status": "paused", "paused": True, "lastError": "old"},
            now="before",
        )
        service, provider, _profiles, repository = build_service(
            workspace, agents=(existing_hr(workspace),), state=paused,
        )
        state = service.resume(HR_ROLE)
        assert state.status is LifecycleStatus.IDLE
        assert state.paused is False
        assert state.last_error == ""
        assert state.last_action == "resume"
        assert service._ports.presence.calls == [("hr", "idle", "")]
        assert [item.action for item in state.recent_activity][-3:] == ["resume", "profile_update", "resume"]
        assert repository.value is state
        assert len(operations(provider, "create")) == 0


def test_failed_resume_stays_unpaused_but_degraded_and_does_not_set_idle_presence():
    with TemporarySystemAgentWorkspace() as workspace:
        paused = SystemAgentLifecycleState.from_mapping(
            HR_ROLE, {"status": "paused", "paused": True}, now="before",
        )
        service, provider, _profiles, _repository = build_service(workspace, state=paused)
        provider.fail_next("discover", TimeoutError("one"))
        provider.fail_next("discover", TimeoutError("two"))
        state = service.resume(HR_ROLE)
        assert state.status is LifecycleStatus.ERROR
        assert state.paused is False
        assert state.last_error == "two"
        assert service._ports.presence.calls == []


def test_automatic_work_policy_allows_owned_ready_category_only():
    ready = dataclasses.replace(
        SystemAgentLifecycleState.initial(HR_ROLE, "now"),
        status=LifecycleStatus.IDLE,
    )
    allowed = service_decision(ready, "daily_reporting")
    unsupported = service_decision(ready, "archive_maintenance")
    unavailable = service_decision(dataclasses.replace(ready, status=LifecycleStatus.ERROR), "daily_reporting")
    assert allowed.allowed is True
    assert unsupported.code == "unsupported_work_category"
    assert unavailable.code == "system_agent_unavailable"


def service_decision(state, category):
    from services.system_agent_lifecycle import SystemAgentLifecycleService
    return SystemAgentLifecycleService.automatic_work_decision(HR_ROLE, state, category)


def test_skipped_automatic_work_is_bounded_and_preserves_last_error():
    with TemporarySystemAgentWorkspace() as workspace:
        degraded = SystemAgentLifecycleState.from_mapping(
            HR_ROLE,
            {"status": "error", "lastError": "provider unavailable"},
            now="before",
        )
        service, _provider, _profiles, repository = build_service(workspace, state=degraded)
        for _index in range(20):
            decision = service.check_automatic_work(HR_ROLE, "daily_reporting")
            assert decision.allowed is False
        assert repository.value.last_error == "provider unavailable"
        assert len(repository.value.recent_activity) == 12
        assert all(item.action == "automatic_work_skipped" for item in repository.value.recent_activity)


def test_skip_check_can_be_read_only():
    with TemporarySystemAgentWorkspace() as workspace:
        paused = SystemAgentLifecycleState.from_mapping(
            HR_ROLE, {"status": "paused", "paused": True}, now="before",
        )
        service, _provider, _profiles, repository = build_service(workspace, state=paused)
        decision = service.check_automatic_work(
            HR_ROLE, "daily_reporting", record_skip=False,
        )
        assert decision.code == "system_agent_paused"
        assert repository.saved == []


def test_public_state_is_allowlisted_and_degraded_read_does_not_touch_provider():
    with TemporarySystemAgentWorkspace() as workspace:
        state = SystemAgentLifecycleState.from_mapping(
            HR_ROLE,
            {
                "agentId": "provider-hr-8",
                "status": "error",
                "workspace": "/secret/workspace",
                "profileFiles": ["IDENTITY.md"],
                "lastError": "provider offline",
            },
            now="before",
        )
        service, provider, _profiles, _repository = build_service(workspace, state=state)
        public = service.public_state(HR_ROLE)
        assert public["agentId"] == "provider-hr-8"
        assert public["status"] == "error"
        assert public["lastError"] == "provider offline"
        assert "workspace" not in public
        assert "profileFiles" not in public
        assert provider.calls == []


def test_public_state_ensure_reports_provider_failure_with_existing_data():
    with TemporarySystemAgentWorkspace() as workspace:
        previous = SystemAgentLifecycleState.from_mapping(
            HR_ROLE,
            {"agentId": "provider-hr-8", "status": "idle", "profileVersion": "v0"},
            now="before",
        )
        service, provider, _profiles, _repository = build_service(workspace, state=previous)
        provider.fail_next("discover", TimeoutError("one"))
        provider.fail_next("discover", TimeoutError("two"))
        public = service.public_state(HR_ROLE, ensure=True)
        assert public["agentId"] == "provider-hr-8"
        assert public["profileVersion"] == "v0"
        assert public["status"] == "error"
        assert public["lastError"] == "two"


def test_metadata_matches_stable_and_persisted_identity_without_leaking_state():
    with TemporarySystemAgentWorkspace() as workspace:
        state = SystemAgentLifecycleState.from_mapping(
            HR_ROLE,
            {"agentId": "provider-hr-8", "name": "HR", "status": "idle"},
            now="before",
        )
        service, _provider, _profiles, _repository = build_service(workspace, state=state)
        expected = {
            "systemRole": "hr",
            "systemAgent": True,
            "assignable": False,
            "deletable": False,
            "meetingEligible": True,
            "lifecycleStatus": "idle",
            "paused": False,
        }
        assert service.metadata(HR_ROLE, "hr") == expected
        assert service.metadata(HR_ROLE, {"statusKey": "provider-hr-8"}) == expected
        assert service.metadata(HR_ROLE, {"systemRole": "hr", "id": "renamed"}) == expected
        assert service.metadata(HR_ROLE, "ordinary-agent") == {}
