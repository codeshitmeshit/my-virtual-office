"""Agent-facing HR application queries, disclosure, and audit ordering."""

import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_agent_api import HRAgentAPI, HRAgentAPIValidationError, HRAgentAuditError
from services.hr_agent_auth import AuthenticatedHRAgent
from services.hr_directory import HRDirectoryQuery
from services.hr_repository import HRRepository, HRRepositoryError


NOW = datetime(2026, 7, 19, 10, tzinfo=timezone.utc)


def identity(ai_id):
    return AuthenticatedHRAgent(
        ai_id=ai_id,
        name=ai_id.title(),
        provider_kind="openclaw",
    )


@pytest.fixture
def setup(tmp_path):
    repository = HRRepository(tmp_path / "status", clock=lambda: NOW)
    repository.initialize()
    for ai_id, availability in (
        ("agent-1", "available"),
        ("agent-2", "busy"),
        ("agent-3", "available"),
    ):
        repository.upsert_agent(
            ai_id=ai_id,
            name=ai_id.title(),
            agent_kind="project",
            provider_kind="openclaw",
            status="active",
            availability=availability,
            source="test",
        )
        repository.save_introduction(
            ai_id=ai_id,
            state="published",
            raw_response=f"private introduction from {ai_id}",
            introduction=f"Public introduction for {ai_id}",
            source="hr-summary",
            actor_id="hr",
            expected_version=0,
        )
    repository.save_daily_report(
        report_id="report-2",
        cycle_id=None,
        ai_id="agent-2",
        local_date="2026-07-19",
        submission_state="normalized",
        raw_response="PRIVATE RAW REPORT",
        normalized={"completedWork": ["Delivered public API"], "blockers": ["PRIVATE"]},
        normalizer_id="hr",
        expected_revision=0,
    )
    repository.save_assessment(
        assessment_id="assessment-2",
        ai_id="agent-2",
        local_date="2026-07-19",
        status="succeeded",
        workload="high",
        principal_contributions=["Delivered public API"],
        rationale="PRIVATE HR RATIONALE",
        blockers=["PRIVATE BLOCKER"],
        strengths=["Reliable"],
        improvements=["PRIVATE IMPROVEMENT"],
        runtime_diagnosis="healthy",
        information_sufficiency="sufficient",
        evidence_version="evidence-v1",
        hr_id="hr",
        evidence=[],
        expected_version=0,
    )
    return repository, HRAgentAPI(
        repository,
        HRDirectoryQuery(repository),
        clock=lambda: NOW,
    )


def test_directory_is_safe_paginated_and_never_creates_access_log(setup):
    repository, api = setup
    result = api.directory(identity("agent-1"), query="agent", limit=2)
    assert result.status == 200
    assert len(result.payload["items"]) == 2
    assert result.payload["nextCursor"]
    assert set(result.payload["items"][0]) == {
        "name",
        "introduction",
        "aiId",
        "availability",
        "readiness",
    }
    assert repository.list_access_log().items == ()
    assert "private introduction" not in str(result.payload)


def test_cross_agent_detail_returns_exact_public_projection_after_one_audit(setup):
    repository, api = setup
    result = api.agent_detail(
        identity("agent-1"),
        "agent-2",
        occurrence_key="request-public-1",
    )
    assert result.status == 200
    assert result.payload["agent"] == {
        "aiId": "agent-2",
        "name": "Agent-2",
        "introduction": "Public introduction for agent-2",
        "availability": "busy",
        "publicWorkSummary": ["Delivered public API"],
        "workload": "high",
        "scope": "public",
    }
    encoded = str(result.payload)
    assert "PRIVATE RAW REPORT" not in encoded
    assert "PRIVATE HR RATIONALE" not in encoded
    assert "PRIVATE IMPROVEMENT" not in encoded
    logs = repository.list_access_log().items
    assert len(logs) == 1
    assert logs[0].viewer_ai_id == "agent-1"
    assert logs[0].target_ai_id == "agent-2"
    assert logs[0].scope == "public_work_summary"


def test_replayed_occurrence_returns_disclosure_with_exactly_one_access_record(setup):
    repository, api = setup
    first = api.agent_detail(
        identity("agent-1"), "agent-2", occurrence_key="request-replayed"
    )
    second = api.agent_detail(
        identity("agent-1"), "agent-2", occurrence_key="request-replayed"
    )
    assert first == second
    assert len(repository.list_access_log().items) == 1


def test_concurrent_duplicate_disclosure_commits_one_access_record(setup):
    repository, api = setup
    barrier = threading.Barrier(3)
    results = []

    def query():
        barrier.wait()
        results.append(
            api.agent_detail(
                identity("agent-1"), "agent-2", occurrence_key="request-concurrent"
            )
        )

    threads = [threading.Thread(target=query) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)
    assert len(results) == 2
    assert len(repository.list_access_log().items) == 1


def test_audit_failure_fails_closed_without_returning_public_detail(setup, monkeypatch):
    repository, api = setup

    def fail(**_kwargs):
        raise HRRepositoryError("injected audit outage")

    monkeypatch.setattr(repository, "record_successful_access", fail)
    with pytest.raises(HRAgentAuditError, match="audit could not be committed"):
        api.agent_detail(
            identity("agent-1"), "agent-2", occurrence_key="request-audit-failure"
        )
    error = api.safe_error(HRAgentAuditError("injected audit outage"))
    assert error.status == 503
    assert error.payload == {"ok": False, "code": "hr_audit_unavailable"}
    assert repository.list_access_log().items == ()


def test_self_detail_is_self_projection_and_does_not_create_view_log(setup):
    repository, api = setup
    result = api.agent_detail(identity("agent-2"), "agent-2", occurrence_key="")
    assert result.status == 200
    assert result.payload["agent"]["scope"] == "self"
    assert result.payload["agent"]["reports"][0]["rawResponse"] == "PRIVATE RAW REPORT"
    assert result.payload["agent"]["improvements"] == ["PRIVATE IMPROVEMENT"]
    assert repository.list_access_log().items == ()


def test_self_access_log_returns_only_records_where_caller_is_target(setup):
    repository, api = setup
    repository.record_successful_access(
        access_id="view-agent-2",
        viewer_ai_id="agent-1",
        target_ai_id="agent-2",
        viewed_at=NOW.isoformat(),
        scope="public_work_summary",
        request_source="test",
        occurrence_key="view-agent-2",
    )
    repository.record_successful_access(
        access_id="view-agent-3",
        viewer_ai_id="agent-2",
        target_ai_id="agent-3",
        viewed_at=NOW.isoformat(),
        scope="public_work_summary",
        request_source="test",
        occurrence_key="view-agent-3",
    )
    result = api.self_access_log(identity("agent-2"))
    assert result.status == 200
    assert len(result.payload["items"]) == 1
    assert result.payload["items"][0]["targetAiId"] == "agent-2"
    assert result.payload["items"][0]["viewerAiId"] == "agent-1"


def test_invalid_identity_occurrence_and_limits_fail_before_audit(setup):
    repository, api = setup
    with pytest.raises(HRAgentAPIValidationError, match="identity"):
        api.directory(object())
    with pytest.raises(HRAgentAPIValidationError, match="occurrence"):
        api.agent_detail(identity("agent-1"), "agent-2", occurrence_key="bad key")
    with pytest.raises(HRAgentAPIValidationError, match="between"):
        api.self_access_log(identity("agent-1"), limit=101)
    assert repository.list_access_log().items == ()


def test_missing_target_returns_not_found_without_access_log(setup):
    repository, api = setup
    result = api.agent_detail(
        identity("agent-1"), "missing", occurrence_key="request-missing"
    )
    assert result.status == 404
    assert result.payload["code"] == "hr_agent_not_found"
    assert repository.list_access_log().items == ()


def test_agent_api_has_no_transport_or_server_dependency():
    source = (APP_DIR / "services" / "hr_agent_api.py").read_text(encoding="utf-8")
    assert "import server" not in source
    assert "OfficeHandler" not in source
    assert "http.server" not in source
