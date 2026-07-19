"""Public/management report states, aggregate counts, and pagination."""

import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_reporting import (
    AgentReportManagementStatus,
    AgentReportPublicStatus,
    HRReportingProjection,
    HRReportingService,
)
from services.hr_repository import HRRepository


NOW = datetime(2026, 7, 19, 2, tzinfo=timezone.utc)
CLOSED = "2026-07-19T04:00:00+00:00"


def setup_projection(tmp_path):
    repository = HRRepository(tmp_path / "status", clock=lambda: NOW)
    repository.initialize()
    agent_ids = tuple(f"agent-{index}" for index in range(1, 8))
    for ai_id in ("hr", *agent_ids):
        repository.upsert_agent(
            ai_id=ai_id,
            name=ai_id,
            agent_kind="system" if ai_id == "hr" else "project",
            status="active",
            availability="available",
            source="test",
        )
    reporting = HRReportingService(
        repository,
        clock=lambda: NOW,
        claim_token_factory=lambda request_id: f"claim:{request_id}",
    )
    opened = reporting.open_cycle(
        local_date="2026-07-19",
        timezone_name="Asia/Shanghai",
        scheduled_at=NOW,
        window_opens_at=NOW,
        window_closes_at=datetime(2026, 7, 19, 4, tzinfo=timezone.utc),
        eligible_ai_ids=agent_ids,
    )

    def update(ai_id, state, *, raw=None, normalized=None, submitted=None, closed=None):
        current = repository.get_daily_report(ai_id, "2026-07-19")
        repository.save_daily_report(
            report_id=current.id,
            cycle_id=opened.cycle.id,
            ai_id=ai_id,
            local_date="2026-07-19",
            submission_state=state,
            raw_response=raw,
            normalized=normalized,
            normalizer_id="hr" if normalized else "",
            requested_at=NOW.isoformat(),
            window_closed_at=closed,
            submitted_at=submitted,
            normalized_at=NOW.isoformat() if normalized else None,
            expected_revision=current.revision,
        )

    update("agent-2", "submitted", raw="submitted", submitted=NOW.isoformat())
    update(
        "agent-3",
        "late_submitted",
        raw="late",
        submitted="2026-07-19T05:00:00+00:00",
        closed=CLOSED,
    )
    update("agent-4", "not_submitted", closed=CLOSED)
    update(
        "agent-5",
        "normalization_failed",
        raw="needs retry",
        submitted=NOW.isoformat(),
    )
    update("agent-6", "skipped")
    update(
        "agent-7",
        "normalized",
        raw="complete",
        submitted=NOW.isoformat(),
        normalized={"schemaVersion": 1, "completedWork": ["done"]},
    )
    return repository, reporting, opened, HRReportingProjection(repository)


def test_public_projection_exposes_all_required_states_without_report_content(tmp_path):
    _repository, _reporting, opened, projection = setup_projection(tmp_path)
    result = projection.project_cycle(opened.cycle.id)
    assert [item.status for item in result.items] == [
        "waiting",
        "submitted",
        "late",
        "not_submitted",
        "normalization_failed",
        "skipped",
        "complete",
    ]
    assert all(isinstance(item, AgentReportPublicStatus) for item in result.items)
    serialized = asdict(result)
    assert "raw_response" not in str(serialized)
    assert "normalized" not in str(serialized)
    assert result.counts == {
        "waiting": 1,
        "submitted": 1,
        "late": 1,
        "not_submitted": 1,
        "normalization_failed": 1,
        "skipped": 1,
        "complete": 1,
        "failed": 0,
    }
    assert result.total == 7
    assert result.status == "open"


def test_management_projection_contains_claims_and_hr_normalization(tmp_path):
    _repository, _reporting, opened, projection = setup_projection(tmp_path)
    result = projection.project_cycle(opened.cycle.id, management=True)
    assert all(isinstance(item, AgentReportManagementStatus) for item in result.items)
    submitted = result.items[1]
    complete = result.items[-1]
    assert submitted.public.status == "submitted"
    assert submitted.raw_response == "submitted"
    assert submitted.normalized is None
    assert complete.raw_response == "complete"
    assert complete.normalized["completedWork"] == ["done"]
    assert complete.normalizer_id == "hr"


def test_paginated_pages_keep_full_cycle_aggregate_counts(tmp_path):
    _repository, _reporting, opened, projection = setup_projection(tmp_path)
    first = projection.project_cycle(opened.cycle.id, limit=3)
    second = projection.project_cycle(
        opened.cycle.id,
        limit=3,
        cursor=first.next_cursor,
    )
    third = projection.project_cycle(
        opened.cycle.id,
        limit=3,
        cursor=second.next_cursor,
    )
    assert [item.ai_id for item in first.items] == ["agent-1", "agent-2", "agent-3"]
    assert [item.ai_id for item in second.items] == ["agent-4", "agent-5", "agent-6"]
    assert [item.ai_id for item in third.items] == ["agent-7"]
    assert first.counts == second.counts == third.counts
    assert first.total == second.total == third.total == 7
    assert third.next_cursor is None


def test_closed_cycle_is_not_complete_while_submissions_need_normalization(tmp_path):
    _repository, reporting, opened, projection = setup_projection(tmp_path)
    reporting.close_cycle(opened.cycle.id, closed_at=datetime.fromisoformat(CLOSED))
    result = projection.project_cycle(opened.cycle.id)
    assert result.status == "processing"
    assert result.counts["submitted"] == 1
    assert result.counts["late"] == 1
    assert result.counts["normalization_failed"] == 1


def test_closed_cycle_with_only_terminal_outcomes_is_complete(tmp_path):
    repository, reporting, opened, projection = setup_projection(tmp_path)
    for ai_id in ("agent-1", "agent-2", "agent-3", "agent-5"):
        current = repository.get_daily_report(ai_id, "2026-07-19")
        repository.save_daily_report(
            report_id=current.id,
            cycle_id=current.cycle_id,
            ai_id=ai_id,
            local_date=current.local_date,
            submission_state="normalized" if current.raw_response else "not_submitted",
            raw_response=current.raw_response,
            normalized={"schemaVersion": 1} if current.raw_response else None,
            normalizer_id="hr" if current.raw_response else "",
            requested_at=current.requested_at,
            window_closed_at=current.window_closed_at,
            submitted_at=current.submitted_at,
            normalized_at=NOW.isoformat() if current.raw_response else None,
            expected_revision=current.revision,
        )
    reporting.close_cycle(opened.cycle.id, closed_at=datetime.fromisoformat(CLOSED))
    result = projection.project_cycle(opened.cycle.id)
    assert result.status == "complete"
    assert result.total == (
        result.counts["complete"]
        + result.counts["not_submitted"]
        + result.counts["skipped"]
    )
