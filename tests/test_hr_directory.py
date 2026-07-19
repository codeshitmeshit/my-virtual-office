"""Multi-source HR roster reconciliation and eligibility tests."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_directory import (
    HRDirectoryService,
    HRDirectoryValidationError,
    RosterObservation,
    RosterSourceSnapshot,
)
from services.hr_repository import HRRepository


@pytest.fixture
def repository(tmp_path):
    result = HRRepository(
        tmp_path / "status",
        clock=lambda: datetime(2026, 7, 19, 9, tzinfo=timezone.utc),
    )
    result.initialize()
    return result


def observation(ai_id, name=None, **overrides):
    values = {
        "ai_id": ai_id,
        "name": name or ai_id,
        "agent_kind": "project",
        "provider_kind": "codex",
        "status": "active",
        "availability": "available",
    }
    values.update(overrides)
    return RosterObservation(**values)


def snapshot(source, *agents, available=True, error=""):
    return RosterSourceSnapshot(source, tuple(agents), available, error)


def states_by_id(result):
    return {item.agent.ai_id: item for item in result.agents}


def test_reconcile_covers_system_project_external_and_synthetic_agents(repository):
    result = HRDirectoryService(repository).reconcile(
        (
            snapshot("system", observation("hr", "HR", agent_kind="system")),
            snapshot("projects", observation("project-1", agent_kind="project")),
            snapshot("external", observation("external-1", agent_kind="external")),
            snapshot("synthetic", observation("synthetic-1", agent_kind="synthetic")),
        )
    )
    assert set(result.created) == {"hr", "project-1", "external-1", "synthetic-1"}
    assert {state.agent.agent_kind for state in result.agents} == {
        "system",
        "project",
        "external",
        "synthetic",
    }
    states = states_by_id(result)
    assert states["hr"].report_eligible is False
    assert states["hr"].assessment_eligible is False
    assert states["project-1"].report_eligible is True


def test_duplicate_sources_merge_one_stable_agent_with_deterministic_precedence(repository):
    result = HRDirectoryService(repository).reconcile(
        (
            snapshot(
                "provider",
                observation("agent-1", "Provider Name", priority=10, availability="busy"),
            ),
            snapshot(
                "workspace",
                observation(
                    "agent-1",
                    "Workspace Name",
                    priority=1,
                    agent_kind="external",
                    provider_kind="",
                ),
            ),
        )
    )
    agent = states_by_id(result)["agent-1"].agent
    assert agent.name == "Provider Name"
    assert agent.agent_kind == "project"
    assert agent.provider_kind == "codex"
    assert agent.discovery_source == "provider+workspace"
    assert len(repository.list_agents().items) == 1
    assert len(repository.list_identity_history("agent-1").items) == 1


def test_changed_name_updates_same_record_and_retains_history(repository):
    service = HRDirectoryService(repository)
    first = service.reconcile((snapshot("provider", observation("agent-1", "Old Name")),))
    second = service.reconcile((snapshot("provider", observation("agent-1", "New Name")),))
    assert first.created == ("agent-1",)
    assert second.updated == ("agent-1",)
    assert states_by_id(second)["agent-1"].agent.name == "New Name"
    assert [item.name for item in repository.list_identity_history("agent-1").items] == [
        "New Name",
        "Old Name",
    ]


def test_complete_source_absence_marks_agent_unreachable(repository):
    service = HRDirectoryService(repository)
    service.reconcile((snapshot("provider", observation("agent-1")),))
    result = service.reconcile((snapshot("provider"),))
    state = states_by_id(result)["agent-1"]
    assert result.authoritative_absence is True
    assert result.inactivated == ("agent-1",)
    assert state.agent.status == "unreachable"
    assert state.agent.availability == "unavailable"
    assert state.report_eligible is False


def test_unavailable_source_does_not_infer_absence_or_block_other_sources(repository):
    service = HRDirectoryService(repository)
    service.reconcile((snapshot("provider", observation("agent-1")),))
    result = service.reconcile(
        (
            snapshot("provider", available=False, error="provider timeout"),
            snapshot("workspace", observation("agent-2")),
        )
    )
    states = states_by_id(result)
    assert result.authoritative_absence is False
    assert result.source_errors == ("provider",)
    assert result.source_failures[0].error == "provider timeout"
    assert states["agent-1"].agent.status == "active"
    assert states["agent-2"].agent.status == "active"
    assert result.inactivated == ()


def test_absence_is_only_authoritative_for_agent_prior_sources(repository):
    service = HRDirectoryService(repository)
    service.reconcile((snapshot("provider", observation("agent-1")),))
    result = service.reconcile((snapshot("workspace"),))
    assert states_by_id(result)["agent-1"].agent.status == "active"
    assert result.inactivated == ()


def test_inactive_agent_reactivates_without_losing_identity(repository):
    service = HRDirectoryService(repository)
    service.reconcile((snapshot("provider", observation("agent-1")),))
    inactive = service.reconcile((snapshot("provider"),))
    inactive_revision = states_by_id(inactive)["agent-1"].agent.revision
    restored = service.reconcile((snapshot("provider", observation("agent-1")),))
    agent = states_by_id(restored)["agent-1"].agent
    assert restored.reactivated == ("agent-1",)
    assert agent.status == "active"
    assert agent.revision == inactive_revision + 1
    assert len(repository.list_agents().items) == 1


def test_availability_change_updates_workflow_eligibility_classification(repository):
    service = HRDirectoryService(repository)
    service.reconcile((snapshot("provider", observation("agent-1")),))
    inactive = service.reconcile(
        (snapshot("provider", observation("agent-1", availability="unavailable")),)
    )
    assert inactive.inactivated == ("agent-1",)
    restored = service.reconcile((snapshot("provider", observation("agent-1")),))
    assert restored.reactivated == ("agent-1",)


def test_active_source_identity_wins_over_higher_priority_inactive_source(repository):
    result = HRDirectoryService(repository).reconcile(
        (
            snapshot(
                "stale-provider",
                observation(
                    "agent-1",
                    "Stale Name",
                    status="offline",
                    availability="offline",
                    priority=100,
                ),
            ),
            snapshot("live-workspace", observation("agent-1", "Live Name", priority=1)),
        )
    )
    agent = states_by_id(result)["agent-1"].agent
    assert agent.status == "active"
    assert agent.name == "Live Name"


@pytest.mark.parametrize(
    "availability",
    ("unavailable", "offline", "disabled", "deleted", "unreachable"),
)
def test_unavailable_states_are_not_report_or_assessment_eligible(repository, availability):
    result = HRDirectoryService(repository).reconcile(
        (
            snapshot(
                "provider",
                observation(
                    "agent-1",
                    status="offline" if availability == "offline" else "active",
                    availability=availability,
                ),
            ),
        )
    )
    state = states_by_id(result)["agent-1"]
    assert state.report_eligible is False
    assert state.assessment_eligible is False


def test_one_invalid_agent_update_does_not_block_other_agents(repository):
    result = HRDirectoryService(repository).reconcile(
        (
            snapshot(
                "provider",
                observation("bad", status="invented"),
                observation("good"),
            ),
        )
    )
    assert result.created == ("good",)
    assert len(result.failures) == 1
    assert result.failures[0].ai_id == "bad"
    assert repository.get_agent("good") is not None
    assert repository.get_agent("bad") is None


def test_reconcile_reads_all_repository_pages(repository):
    agents = tuple(observation(f"agent-{index:03d}") for index in range(105))
    result = HRDirectoryService(repository).reconcile((snapshot("provider", *agents),))
    assert len(result.agents) == 105
    repeated = HRDirectoryService(repository).reconcile((snapshot("provider", *agents),))
    assert len(repeated.unchanged) == 105
    assert len(repeated.agents) == 105


def test_source_and_snapshot_validation_fail_before_mutation(repository):
    service = HRDirectoryService(repository)
    with pytest.raises(HRDirectoryValidationError, match="at least one"):
        service.reconcile(())
    with pytest.raises(HRDirectoryValidationError, match="source names"):
        service.reconcile((snapshot("same"), snapshot("same")))
    with pytest.raises(HRDirectoryValidationError, match="duplicate AI ID"):
        service.reconcile(
            (snapshot("provider", observation("agent-1"), observation("agent-1")),)
        )
    assert repository.list_agents().items == ()


def test_directory_module_has_no_server_or_transport_dependency():
    source = (APP_DIR / "services" / "hr_directory.py").read_text(encoding="utf-8")
    assert "import server" not in source
    assert "OfficeHandler" not in source
    assert "http.server" not in source
