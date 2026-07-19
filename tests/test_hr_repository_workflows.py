"""Daily workflow and assessment persistence invariants."""

import sqlite3
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_repository import (
    HRRepository,
    HRRepositoryConflictError,
    HRRepositoryValidationError,
)


class TickClock:
    def __init__(self):
        self.value = datetime(2026, 7, 19, 9, tzinfo=timezone.utc)
        self.lock = threading.Lock()

    def __call__(self):
        with self.lock:
            result = self.value
            self.value += timedelta(microseconds=1)
            return result


@pytest.fixture
def repository(tmp_path):
    result = HRRepository(tmp_path / "status", clock=TickClock())
    result.initialize()
    for ai_id in ("agent-1", "agent-2"):
        result.upsert_agent(
            ai_id=ai_id,
            name=ai_id,
            agent_kind="project",
            status="active",
            availability="available",
            source="test",
        )
    return result


def cycle(repository, *, cycle_id="cycle-19", local_date="2026-07-19", occurrence="daily:2026-07-19"):
    return repository.ensure_daily_cycle(
        cycle_id=cycle_id,
        local_date=local_date,
        timezone_name="Asia/Shanghai",
        scheduled_at=f"{local_date}T10:00:00+08:00",
        window_opens_at=f"{local_date}T09:55:00+08:00",
        window_closes_at=f"{local_date}T18:00:00+08:00",
        status="open",
        roster_snapshot=("agent-1", "agent-2"),
        occurrence_key=occurrence,
    )


def request(repository, ai_id="agent-1"):
    return repository.ensure_report_request(
        request_id=f"request-{ai_id}",
        cycle_id="cycle-19",
        ai_id=ai_id,
        occurrence_key=f"cycle-19:{ai_id}",
        conversation_key=f"hr-report:2026-07-19:{ai_id}",
    )


def assessment(repository, *, assessment_id="assessment-1", evidence_version="evidence-v1", expected=0):
    return repository.save_assessment(
        assessment_id=assessment_id,
        ai_id="agent-1",
        local_date="2026-07-19",
        status="succeeded",
        workload="appropriate",
        principal_contributions=["Delivered repository"],
        rationale="Evidence supports an appropriate workload.",
        blockers=[],
        strengths=["Atomic changes"],
        improvements=["Add operational metrics"],
        runtime_diagnosis="Runtime was available.",
        information_sufficiency="Report and execution evidence were available.",
        evidence_version=evidence_version,
        hr_id="hr",
        revision_reason="" if expected == 0 else "Late evidence arrived.",
        expected_version=expected,
        evidence=[
            {
                "evidence_type": "daily_report",
                "reference_id": "report-1",
                "summary": "Completed the planned repository work.",
                "evidence_date": "2026-07-19",
                "metadata": {"revision": expected + 1},
            }
        ],
    )


def test_daily_cycle_is_date_unique_idempotent_and_restart_visible(repository):
    first = cycle(repository)
    assert first.roster_snapshot == ("agent-1", "agent-2")
    assert cycle(repository) == first

    restarted = HRRepository(repository.status_dir, clock=TickClock())
    restarted.initialize()
    assert restarted.get_daily_cycle("cycle-19") == first
    assert cycle(restarted) == first

    with pytest.raises(HRRepositoryConflictError):
        cycle(repository, cycle_id="other", occurrence="other-occurrence")


def test_concurrent_cycle_creation_converges_on_one_row(repository):
    barrier = threading.Barrier(3)
    results = []

    def create():
        barrier.wait()
        results.append(cycle(repository))

    threads = [threading.Thread(target=create) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)
    assert len(results) == 2
    assert results[0].id == results[1].id
    with sqlite3.connect(repository.path) as connection:
        assert connection.execute("SELECT count(*) FROM daily_cycles").fetchone()[0] == 1


def test_report_request_uniqueness_and_restart_visibility(repository):
    cycle(repository)
    first = request(repository)
    assert request(repository) == first
    restarted = HRRepository(repository.status_dir, clock=TickClock())
    restarted.initialize()
    assert restarted.get_report_request(first.id) == first
    with pytest.raises(HRRepositoryConflictError):
        restarted.ensure_report_request(
            request_id="different",
            cycle_id="cycle-19",
            ai_id="agent-1",
            occurrence_key="different",
            conversation_key="different",
        )


def test_claim_fencing_rejects_busy_and_stale_workers(repository):
    cycle(repository)
    pending = request(repository)
    first = repository.claim_report_request(
        request_id=pending.id,
        claimed_by="worker-a",
        claim_token="token-a",
        now="2026-07-19T01:00:00+00:00",
        claim_expires_at="2026-07-19T01:05:00+00:00",
    )
    assert first.attempt_count == 1
    assert repository.claim_report_request(
        request_id=pending.id,
        claimed_by="worker-b",
        claim_token="token-b",
        now="2026-07-19T01:04:00+00:00",
        claim_expires_at="2026-07-19T01:09:00+00:00",
    ) is None
    second = repository.claim_report_request(
        request_id=pending.id,
        claimed_by="worker-b",
        claim_token="token-b",
        now="2026-07-19T01:05:00+00:00",
        claim_expires_at="2026-07-19T01:10:00+00:00",
    )
    assert second.attempt_count == 2
    with pytest.raises(HRRepositoryConflictError, match="stale"):
        repository.finish_report_request(
            request_id=pending.id,
            claim_token="token-a",
            status="submitted",
            finished_at="2026-07-19T01:06:00+00:00",
        )
    finished = repository.finish_report_request(
        request_id=pending.id,
        claim_token="token-b",
        status="submitted",
        finished_at="2026-07-19T01:06:00+00:00",
    )
    assert finished.status == "submitted"
    assert finished.claim_token == ""


def test_concurrent_claim_has_one_winner(repository):
    cycle(repository)
    pending = request(repository)
    barrier = threading.Barrier(3)
    results = []

    def claim(label):
        barrier.wait()
        results.append(
            repository.claim_report_request(
                request_id=pending.id,
                claimed_by=f"worker-{label}",
                claim_token=f"token-{label}",
                now="2026-07-19T01:00:00+00:00",
                claim_expires_at="2026-07-19T01:05:00+00:00",
            )
        )

    threads = [threading.Thread(target=claim, args=(label,)) for label in ("a", "b")]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)
    assert sum(item is not None for item in results) == 1


def test_daily_report_is_unique_versioned_and_json_validated(repository):
    cycle(repository)
    first = repository.save_daily_report(
        report_id="report-1",
        cycle_id="cycle-19",
        ai_id="agent-1",
        local_date="2026-07-19",
        submission_state="submitted",
        raw_response="  raw answer  ",
        normalized={"completed": ["Task 5.3"]},
        submitted_at="2026-07-19T02:00:00Z",
        expected_revision=0,
    )
    assert first.raw_response == "  raw answer  "
    assert first.normalized == {"completed": ["Task 5.3"]}
    assert repository.save_daily_report(
        report_id="report-1",
        cycle_id="cycle-19",
        ai_id="agent-1",
        local_date="2026-07-19",
        submission_state="submitted",
        raw_response=first.raw_response,
        normalized=first.normalized,
        submitted_at="2026-07-19T02:00:00+00:00",
        expected_revision=1,
    ) == first
    revised = repository.save_daily_report(
        report_id="report-1",
        cycle_id="cycle-19",
        ai_id="agent-1",
        local_date="2026-07-19",
        submission_state="normalized",
        raw_response=first.raw_response,
        normalized={"completed": ["Task 5.3"], "blockers": []},
        normalizer_id="hr",
        submitted_at="2026-07-19T02:00:00Z",
        normalized_at="2026-07-19T02:01:00Z",
        expected_revision=1,
    )
    assert revised.revision == 2
    assert repository.get_daily_report("agent-1", "2026-07-19") == revised

    with pytest.raises(HRRepositoryConflictError, match="immutable"):
        repository.save_daily_report(
            report_id="report-1",
            cycle_id="cycle-19",
            ai_id="agent-1",
            local_date="2026-07-19",
            submission_state="normalized",
            raw_response="rewritten claim",
            normalized=revised.normalized,
            expected_revision=2,
        )

    with pytest.raises(HRRepositoryValidationError, match="valid JSON"):
        repository.save_daily_report(
            report_id="report-1",
            cycle_id="cycle-19",
            ai_id="agent-1",
            local_date="2026-07-19",
            submission_state="normalized",
            raw_response="answer",
            normalized="{broken",
            expected_revision=2,
        )
    assert repository.get_daily_report("agent-1", "2026-07-19") == revised


def test_daily_report_cursor_pagination(repository):
    for index, (ai_id, local_date) in enumerate(
        (("agent-1", "2026-07-19"), ("agent-2", "2026-07-19"), ("agent-1", "2026-07-18"))
    ):
        repository.save_daily_report(
            report_id=f"report-{index}",
            cycle_id=None,
            ai_id=ai_id,
            local_date=local_date,
            submission_state="not_submitted",
            raw_response=None,
            normalized=None,
            expected_revision=0,
        )
    first = repository.list_daily_reports(limit=2)
    second = repository.list_daily_reports(limit=2, cursor=first.next_cursor)
    assert len(first.items) == 2
    assert len(second.items) == 1
    assert len(repository.list_daily_reports(ai_id="agent-1").items) == 2


def test_late_report_retains_request_and_window_timestamps(repository):
    missing = repository.save_daily_report(
        report_id="report-late",
        cycle_id=None,
        ai_id="agent-1",
        local_date="2026-07-18",
        submission_state="not_submitted",
        raw_response=None,
        normalized=None,
        requested_at="2026-07-18T01:00:00Z",
        window_closed_at="2026-07-18T10:00:00Z",
        expected_revision=0,
    )
    late = repository.save_daily_report(
        report_id="report-late",
        cycle_id=None,
        ai_id="agent-1",
        local_date="2026-07-18",
        submission_state="late_submitted",
        raw_response="Late original response",
        normalized=None,
        submitted_at="2026-07-19T01:00:00Z",
        expected_revision=missing.revision,
    )
    assert late.requested_at == missing.requested_at
    assert late.window_closed_at == missing.window_closed_at
    assert late.raw_response == "Late original response"


def test_assessment_versions_current_invariant_and_evidence(repository):
    first = assessment(repository)
    assert first.version == 1
    assert first.is_current is True
    assert first.evidence[0].metadata == {"revision": 1}
    assert assessment(repository) == first

    second = assessment(
        repository,
        assessment_id="assessment-2",
        evidence_version="evidence-v2",
        expected=1,
    )
    assert second.version == 2
    assert repository.get_current_assessment("agent-1", "2026-07-19") == second
    history = repository.list_assessments(ai_id="agent-1").items
    assert [item.version for item in history] == [2, 1]
    assert [item.is_current for item in history] == [True, False]


def test_assessment_json_failure_is_atomic(repository):
    first = assessment(repository)
    with pytest.raises(HRRepositoryValidationError, match="contain strings"):
        repository.save_assessment(
            assessment_id="assessment-bad",
            ai_id="agent-1",
            local_date="2026-07-19",
            status="succeeded",
            workload="appropriate",
            principal_contributions=[{"not": "text"}],
            rationale="rationale",
            blockers=[],
            strengths=[],
            improvements=[],
            runtime_diagnosis="available",
            information_sufficiency="sufficient",
            evidence_version="evidence-v2",
            hr_id="hr",
            evidence=[],
            expected_version=1,
        )
    assert repository.get_current_assessment("agent-1", "2026-07-19") == first


def test_concurrent_assessment_revision_has_one_winner(repository):
    assessment(repository)
    barrier = threading.Barrier(3)
    successes = []
    failures = []

    def revise(label):
        barrier.wait()
        try:
            successes.append(
                assessment(
                    repository,
                    assessment_id=f"assessment-{label}",
                    evidence_version=f"evidence-{label}",
                    expected=1,
                )
            )
        except Exception as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    threads = [threading.Thread(target=revise, args=(label,)) for label in ("a", "b")]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)
    assert len(successes) == len(failures) == 1
    assert isinstance(failures[0], HRRepositoryConflictError)
    with sqlite3.connect(repository.path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM assessments WHERE is_current = 1"
        ).fetchone()[0] == 1


def test_assessment_pagination_includes_prior_versions(repository):
    assessment(repository)
    assessment(repository, assessment_id="assessment-2", evidence_version="ev-2", expected=1)
    repository.save_assessment(
        assessment_id="assessment-other",
        ai_id="agent-2",
        local_date="2026-07-18",
        status="insufficient_information",
        workload="insufficient_information",
        principal_contributions=[],
        rationale="Insufficient evidence.",
        blockers=[],
        strengths=[],
        improvements=["Submit a report."],
        runtime_diagnosis="Unknown.",
        information_sufficiency="No report was available.",
        evidence_version="ev-other",
        hr_id="hr",
        evidence=[],
        expected_version=0,
    )
    first = repository.list_assessments(limit=2)
    second = repository.list_assessments(limit=2, cursor=first.next_cursor)
    assert len(first.items) == 2
    assert len(second.items) == 1
