"""Allowlisted Agent directory projection and disclosure-negative tests."""

import hashlib
import sys
from dataclasses import asdict, fields
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_directory import (
    HRDirectoryQuery,
    HRDirectoryValidationError,
    SafeDirectoryEntry,
)
from services.hr_repository import HRRepository


NOW = datetime(2026, 7, 19, 9, tzinfo=timezone.utc)


@pytest.fixture
def repository(tmp_path):
    result = HRRepository(tmp_path / "status", clock=lambda: NOW)
    result.initialize()
    for ai_id, name, availability in (
        ("agent-1", "Researcher", "available"),
        ("agent-2", "Builder", "busy"),
        ("agent-3", "Reviewer", "unavailable"),
    ):
        result.upsert_agent(
            ai_id=ai_id,
            name=name,
            agent_kind="project",
            status="active",
            availability=availability,
            source="test",
        )
    result.save_introduction(
        ai_id="agent-1",
        state="published",
        raw_response="RAW_PRIVATE_SELF_DESCRIPTION",
        introduction="Investigates reliability incidents.",
        source="hr-summary",
        actor_id="hr",
        expected_version=0,
    )
    current = result.get_agent("agent-1")
    result.update_agent_enablement(
        ai_id="agent-1",
        skill_readiness="ready",
        grant_readiness="ready",
        expected_revision=current.revision,
    )
    result.save_introduction(
        ai_id="agent-2",
        state="response_received",
        raw_response="BUILDER_PRIVATE_RESPONSE",
        introduction="",
        source="agent-response",
        actor_id="hr",
        expected_version=0,
    )
    return result


def add_sensitive_records(repository):
    repository.save_daily_report(
        report_id="report-1",
        cycle_id=None,
        ai_id="agent-1",
        local_date="2026-07-19",
        submission_state="normalized",
        raw_response="RAW_PRIVATE_REPORT",
        normalized={"blockers": ["PRIVATE_BLOCKER"]},
        normalizer_id="hr",
        expected_revision=0,
    )
    repository.save_assessment(
        assessment_id="assessment-1",
        ai_id="agent-1",
        local_date="2026-07-19",
        status="succeeded",
        workload="appropriate",
        principal_contributions=["contribution"],
        rationale="PRIVATE_HR_RATIONALE",
        blockers=["PRIVATE_ASSESSMENT_BLOCKER"],
        strengths=["strength"],
        improvements=["PRIVATE_IMPROVEMENT"],
        runtime_diagnosis="PRIVATE_RUNTIME_DIAGNOSIS",
        information_sufficiency="sufficient",
        evidence_version="evidence-v1",
        hr_id="hr",
        evidence=[
            {
                "evidence_type": "report",
                "reference_id": "report-1",
                "summary": "PRIVATE_EVIDENCE",
            }
        ],
        expected_version=0,
    )
    repository.rotate_access_grant(
        ai_id="agent-1",
        key_id="PRIVATE_KEY_ID",
        secret_digest=hashlib.sha256(b"PRIVATE_RAW_GRANT").hexdigest(),
        issued_at="2026-07-19T01:00:00Z",
    )


def test_safe_entry_type_has_exactly_five_allowlisted_fields():
    assert [field.name for field in fields(SafeDirectoryEntry)] == [
        "name",
        "introduction",
        "ai_id",
        "availability",
        "readiness",
    ]


def test_directory_list_contains_only_safe_fields_despite_sensitive_authority(repository):
    add_sensitive_records(repository)
    page = HRDirectoryQuery(repository).list()
    assert len(page.items) == 3
    serialized = [asdict(item) for item in page.items]
    assert all(
        set(item) == {"name", "introduction", "ai_id", "availability", "readiness"}
        for item in serialized
    )
    text = repr(serialized)
    for secret in (
        "RAW_PRIVATE_SELF_DESCRIPTION",
        "BUILDER_PRIVATE_RESPONSE",
        "RAW_PRIVATE_REPORT",
        "PRIVATE_BLOCKER",
        "PRIVATE_HR_RATIONALE",
        "PRIVATE_ASSESSMENT_BLOCKER",
        "PRIVATE_IMPROVEMENT",
        "PRIVATE_RUNTIME_DIAGNOSIS",
        "PRIVATE_EVIDENCE",
        "PRIVATE_KEY_ID",
        "PRIVATE_RAW_GRANT",
        "evidence-v1",
    ):
        assert secret not in text


def test_directory_readiness_is_derived_without_exposing_workflow_state(repository):
    entries = {item.ai_id: item for item in HRDirectoryQuery(repository).list().items}
    assert entries["agent-1"].readiness == "ready"
    assert entries["agent-1"].introduction == "Investigates reliability incidents."
    assert entries["agent-2"].readiness == "awaiting_hr_summary"
    assert entries["agent-2"].introduction == ""
    assert entries["agent-3"].readiness == "pending"
    assert entries["agent-3"].availability == "unavailable"


def test_clarification_projects_previous_supported_introduction(repository):
    current = repository.get_current_introduction("agent-1")
    repository.save_introduction(
        ai_id="agent-1",
        state="clarification_pending",
        raw_response="A changed private response",
        introduction=current.introduction,
        source="hr-summary",
        actor_id="hr",
        clarification_question="Did your role change?",
        expected_version=current.version,
    )
    projected = HRDirectoryQuery(repository).get("agent-1")
    assert projected.readiness == "clarification_pending"
    assert projected.introduction == "Investigates reliability incidents."
    assert "changed private" not in repr(projected)


def test_directory_filters_by_availability_readiness_and_safe_text(repository):
    query = HRDirectoryQuery(repository)
    assert [item.ai_id for item in query.list(availability="busy").items] == ["agent-2"]
    assert [item.ai_id for item in query.list(readiness="ready").items] == ["agent-1"]
    assert [item.ai_id for item in query.list(query="reliability").items] == ["agent-1"]
    assert [item.ai_id for item in query.list(query="BUILDER_PRIVATE_RESPONSE").items] == []


def test_directory_pagination_is_stable_and_bounded(repository):
    query = HRDirectoryQuery(repository)
    first = query.list(limit=2)
    second = query.list(limit=2, cursor=first.next_cursor)
    assert [item.ai_id for item in first.items] == ["agent-1", "agent-2"]
    assert [item.ai_id for item in second.items] == ["agent-3"]
    assert first.next_cursor is not None
    assert second.next_cursor is None
    with pytest.raises(HRDirectoryValidationError):
        query.list(limit=101)
    with pytest.raises(HRDirectoryValidationError):
        query.list(cursor="invalid cursor")


def test_directory_get_returns_safe_entry_or_none(repository):
    query = HRDirectoryQuery(repository)
    assert query.get("agent-1") == SafeDirectoryEntry(
        name="Researcher",
        introduction="Investigates reliability incidents.",
        ai_id="agent-1",
        availability="available",
        readiness="ready",
    )
    assert query.get("missing") is None


def test_inactive_status_cannot_project_stale_available_value(repository):
    current = repository.get_agent("agent-1")
    repository.upsert_agent(
        ai_id="agent-1",
        name=current.name,
        agent_kind=current.agent_kind,
        status="deleted",
        availability="available",
        source="inconsistent-provider",
        expected_revision=current.revision,
    )
    assert HRDirectoryQuery(repository).get("agent-1").availability == "unavailable"


@pytest.mark.parametrize(
    "kwargs",
    (
        {"availability": ""},
        {"readiness": "internal_state"},
        {"query": ""},
        {"query": "x" * 201},
    ),
)
def test_invalid_filters_fail_closed(repository, kwargs):
    with pytest.raises(HRDirectoryValidationError):
        HRDirectoryQuery(repository).list(**kwargs)
