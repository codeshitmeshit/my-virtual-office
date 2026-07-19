"""Submission-window closure, neutral absence, and late daily reports."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_reporting import HRReportingService, HRReportingValidationError
from services.hr_repository import (
    HRRepository,
    HRRepositoryConflictError,
    HRRepositoryValidationError,
)


NOW = datetime(2026, 7, 19, 2, tzinfo=timezone.utc)
CLOSED = datetime(2026, 7, 19, 4, tzinfo=timezone.utc)


@pytest.fixture
def setup(tmp_path):
    repository = HRRepository(tmp_path / "status", clock=lambda: NOW)
    repository.initialize()
    for ai_id in ("hr", "agent-1", "agent-2"):
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
        window_closes_at=CLOSED,
        eligible_ai_ids=("agent-1", "agent-2"),
    )
    return repository, reporting, opened


def test_close_marks_only_missing_reports_not_submitted_without_inference(setup):
    repository, reporting, opened = setup
    reporting.submit_response(
        ai_id="agent-1",
        local_date="2026-07-19",
        raw_response="完成了实现",
        submitted_at=datetime(2026, 7, 19, 3, tzinfo=timezone.utc),
    )
    closed = reporting.close_cycle(opened.cycle.id, closed_at=CLOSED)

    assert closed.cycle.status == "closed"
    reports = {item.ai_id: item for item in closed.reports}
    assert reports["agent-1"].submission_state == "submitted"
    missing = reports["agent-2"]
    assert missing.submission_state == "not_submitted"
    assert missing.raw_response is None
    assert missing.normalized is None
    assert missing.normalizer_id == ""
    assert missing.submitted_at is None
    assert missing.window_closed_at == CLOSED.isoformat()
    assert repository.get_report_request(opened.requests[1].id).status == "no_response"


def test_late_submission_updates_same_dated_record_and_preserves_close_time(setup):
    repository, reporting, opened = setup
    before = repository.get_daily_report("agent-2", "2026-07-19")
    reporting.close_cycle(opened.cycle.id, closed_at=CLOSED)
    late = reporting.submit_response(
        ai_id="agent-2",
        local_date="2026-07-19",
        raw_response="迟交：今天完成了测试",
        submitted_at=datetime(2026, 7, 19, 5, tzinfo=timezone.utc),
    )
    assert late.id == before.id
    assert late.submission_state == "late_submitted"
    assert late.window_closed_at == CLOSED.isoformat()
    assert late.submitted_at == "2026-07-19T05:00:00+00:00"
    assert late.raw_response == "迟交：今天完成了测试"
    assert repository.get_report_request(opened.requests[1].id).status == "submitted"


def test_duplicate_same_response_is_idempotent_but_conflict_cannot_replace_raw(setup):
    _repository, reporting, _opened = setup
    first = reporting.submit_response(
        ai_id="agent-1",
        local_date="2026-07-19",
        raw_response="唯一原文",
        submitted_at=NOW,
    )
    duplicate = reporting.submit_response(
        ai_id="agent-1",
        local_date="2026-07-19",
        raw_response="唯一原文",
        submitted_at=datetime(2026, 7, 19, 3, tzinfo=timezone.utc),
    )
    assert duplicate == first
    with pytest.raises(HRRepositoryConflictError, match="immutable"):
        reporting.submit_response(
            ai_id="agent-1",
            local_date="2026-07-19",
            raw_response="试图替换",
            submitted_at=datetime(2026, 7, 19, 3, tzinfo=timezone.utc),
        )


def test_duplicate_close_is_idempotent(setup):
    repository, reporting, opened = setup
    first = reporting.close_cycle(opened.cycle.id, closed_at=CLOSED)
    second = reporting.close_cycle(
        opened.cycle.id,
        closed_at=datetime(2026, 7, 19, 6, tzinfo=timezone.utc),
    )
    assert second == first
    assert repository.get_daily_report("agent-1", "2026-07-19").window_closed_at == (
        CLOSED.isoformat()
    )


def test_window_close_fences_an_inflight_claim(setup):
    repository, reporting, opened = setup
    claimed = reporting.claim_request(opened.requests[0].id, worker_id="slow-worker")
    reporting.close_cycle(opened.cycle.id, closed_at=CLOSED)
    with pytest.raises(HRRepositoryConflictError, match="stale"):
        repository.record_report_response(
            request_id=claimed.id,
            claim_token=claimed.claim_token,
            finished_at=datetime(2026, 7, 19, 3, tzinfo=timezone.utc).isoformat(),
            raw_response="late worker result",
        )
    assert repository.get_daily_report("agent-1", "2026-07-19").raw_response is None


def test_empty_or_naive_late_submission_is_rejected_without_mutation(setup):
    repository, reporting, _opened = setup
    with pytest.raises(HRRepositoryValidationError, match="raw_response"):
        reporting.submit_response(
            ai_id="agent-1",
            local_date="2026-07-19",
            raw_response="  ",
            submitted_at=NOW,
        )
    with pytest.raises(HRReportingValidationError, match="timezone-aware"):
        reporting.submit_response(
            ai_id="agent-1",
            local_date="2026-07-19",
            raw_response="valid",
            submitted_at=datetime(2026, 7, 19, 3),
        )
    assert repository.get_daily_report("agent-1", "2026-07-19").raw_response is None
