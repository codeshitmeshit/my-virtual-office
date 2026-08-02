#!/usr/bin/env python3
"""Behavior contracts for project completion-report occurrence state."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.project_completion_reporting import (
    CompletionReportStateError,
    begin_completion_report_delivery,
    claim_due_completion_report,
    fail_completion_report_attempt,
    finish_completion_report_delivery,
    finish_completion_report_generation,
    request_manual_resend,
    stage_completion_report_occurrence,
)


COMPLETED_AT = "2026-08-03T01:30:00+08:00"


def _project(*, enabled: bool = True) -> dict:
    return {
        "id": "project-1",
        "status": "completed",
        "feishuCompletionReportEnabled": enabled,
        "orchestration": {"completedAt": COMPLETED_AT},
    }


def test_successful_completion_stages_one_pending_report_occurrence():
    project = _project()

    result = stage_completion_report_occurrence(
        project,
        run_id="run-1",
        completed_at=COMPLETED_AT,
    )

    assert result["created"] is True
    assert result["occurrence"] == {
        "schemaVersion": 1,
        "occurrenceId": "stage-run:run-1",
        "version": 1,
        "runId": "run-1",
        "completedAt": COMPLETED_AT,
        "state": "pending",
        "visibleStatus": "pending",
        "reportingAgentId": "",
        "reportMarkdownPath": "",
        "reportDigest": "",
        "attemptCount": 0,
        "nextAttemptAt": None,
        "lastError": None,
        "messageId": None,
        "claim": None,
        "attempts": [],
    }
    assert project["orchestration"]["completionReports"] == [result["occurrence"]]


def test_repeated_completion_signal_for_same_run_is_idempotent():
    project = _project()
    first = stage_completion_report_occurrence(project, run_id="run-1", completed_at=COMPLETED_AT)

    repeated = stage_completion_report_occurrence(
        project,
        run_id="run-1",
        completed_at="2026-08-03T01:31:00+08:00",
    )

    assert repeated["created"] is False
    assert repeated["occurrence"] is first["occurrence"]
    assert len(project["orchestration"]["completionReports"]) == 1


def test_new_successful_run_gets_next_user_visible_version():
    project = _project()
    stage_completion_report_occurrence(project, run_id="run-1", completed_at=COMPLETED_AT)

    second = stage_completion_report_occurrence(
        project,
        run_id="run-2",
        completed_at="2026-08-04T01:30:00+08:00",
    )

    assert second["created"] is True
    assert second["occurrence"]["occurrenceId"] == "stage-run:run-2"
    assert second["occurrence"]["version"] == 2


def test_disabled_project_locks_first_completion_without_staging_report():
    project = {
        "id": "project-1",
        "status": "completed",
        "feishuCompletionReportEnabled": False,
        "orchestration": {"completedAt": None},
    }

    result = stage_completion_report_occurrence(
        project,
        run_id="run-1",
        completed_at=COMPLETED_AT,
    )

    assert result == {"created": False, "status": "skipped_disabled", "occurrence": None}
    assert project["orchestration"]["completedAt"] == COMPLETED_AT
    assert project["orchestration"]["completionReports"] == []


@pytest.mark.parametrize("run_id", ["", "  ", None])
def test_completion_occurrence_rejects_missing_run_id(run_id):
    with pytest.raises(ValueError, match="run_id is required"):
        stage_completion_report_occurrence(
            _project(),
            run_id=run_id,
            completed_at=COMPLETED_AT,
        )


def _staged_project() -> tuple[dict, str]:
    project = _project()
    staged = stage_completion_report_occurrence(project, run_id="run-1", completed_at=COMPLETED_AT)
    return project, staged["occurrence"]["occurrenceId"]


def test_claim_is_atomic_by_token_and_tracks_one_bounded_attempt():
    project, occurrence_id = _staged_project()

    claimed = claim_due_completion_report(
        project,
        occurrence_id=occurrence_id,
        now="2026-08-03T02:00:00+00:00",
        token="claim-1",
    )
    competing = claim_due_completion_report(
        project,
        occurrence_id=occurrence_id,
        now="2026-08-03T02:00:01+00:00",
        token="claim-2",
    )

    assert claimed["claimed"] is True
    assert competing == {"claimed": False, "status": "in_progress", "occurrence": None}
    occurrence = project["orchestration"]["completionReports"][0]
    assert occurrence["state"] == "generating"
    assert occurrence["attemptCount"] == 1
    assert occurrence["claim"]["token"] == "claim-1"
    assert occurrence["attempts"][-1]["mode"] == "automatic"


def test_generation_and_delivery_finish_only_for_claim_owner():
    project, occurrence_id = _staged_project()
    claim_due_completion_report(
        project, occurrence_id=occurrence_id, now="2026-08-03T02:00:00+00:00", token="claim-1"
    )

    with pytest.raises(CompletionReportStateError) as wrong_owner:
        finish_completion_report_generation(
            project,
            occurrence_id=occurrence_id,
            token="wrong",
            now="2026-08-03T02:00:02+00:00",
            reporting_agent_id="agent",
            markdown_path="report.md",
            digest="digest",
            report={"goal": "Goal"},
        )
    assert wrong_owner.value.code == "completion_report_claim_lost"

    finish_completion_report_generation(
        project,
        occurrence_id=occurrence_id,
        token="claim-1",
        now="2026-08-03T02:00:02+00:00",
        reporting_agent_id="agent",
        markdown_path="report.md",
        digest="digest",
        report={"goal": "Goal"},
    )
    begin_completion_report_delivery(
        project, occurrence_id=occurrence_id, token="claim-1", now="2026-08-03T02:00:03+00:00"
    )
    finish_completion_report_delivery(
        project,
        occurrence_id=occurrence_id,
        token="claim-1",
        now="2026-08-03T02:00:04+00:00",
        message_id="message-1",
    )

    occurrence = project["orchestration"]["completionReports"][0]
    assert occurrence["state"] == "delivered"
    assert occurrence["visibleStatus"] == "delivered"
    assert occurrence["messageId"] == "message-1"
    assert occurrence["claim"] is None


def test_recoverable_failures_use_30_and_120_second_backoff_then_exhaust():
    project, occurrence_id = _staged_project()
    expected_next = ["2026-08-03T02:00:30+00:00", "2026-08-03T02:02:30+00:00"]
    times = ["2026-08-03T02:00:00+00:00", "2026-08-03T02:00:30+00:00", "2026-08-03T02:02:30+00:00"]
    for index, now in enumerate(times):
        token = f"claim-{index}"
        assert claim_due_completion_report(
            project, occurrence_id=occurrence_id, now=now, token=token
        )["claimed"] is True
        result = fail_completion_report_attempt(
            project,
            occurrence_id=occurrence_id,
            token=token,
            now=now,
            code="reporting_agent_busy",
            error="busy",
            recoverable=True,
        )
        if index < 2:
            assert result["state"] == "retry"
            assert result["nextAttemptAt"] == expected_next[index]
        else:
            assert result["state"] == "failed"
            assert result["visibleStatus"] == "failed"
            assert result["nextAttemptAt"] is None


def test_unknown_delivery_outcome_is_terminal_without_automatic_retry():
    project, occurrence_id = _staged_project()
    claim_due_completion_report(
        project, occurrence_id=occurrence_id, now="2026-08-03T02:00:00+00:00", token="claim"
    )

    failed = fail_completion_report_attempt(
        project,
        occurrence_id=occurrence_id,
        token="claim",
        now="2026-08-03T02:00:01+00:00",
        code="delivery_outcome_unknown",
        error="Delivery may have succeeded",
        recoverable=True,
        outcome_unknown=True,
    )

    assert failed["state"] == "failed"
    assert failed["nextAttemptAt"] is None
    assert failed["lastError"]["code"] == "delivery_outcome_unknown"


def test_manual_resend_keeps_occurrence_version_and_requires_owner_authorization():
    project, occurrence_id = _staged_project()
    occurrence = project["orchestration"]["completionReports"][0]
    occurrence.update({"state": "failed", "visibleStatus": "failed", "attemptCount": 3})

    with pytest.raises(CompletionReportStateError) as unauthorized:
        request_manual_resend(
            project,
            occurrence_id=occurrence_id,
            now="2026-08-03T03:00:00+00:00",
            owner_authorized=False,
        )
    assert unauthorized.value.code == "completion_report_resend_forbidden"

    resent = request_manual_resend(
        project,
        occurrence_id=occurrence_id,
        now="2026-08-03T03:00:00+00:00",
        owner_authorized=True,
    )

    assert resent["occurrenceId"] == occurrence_id
    assert resent["version"] == 1
    assert resent["state"] == "pending"
    assert resent["visibleStatus"] == "pending"
    assert resent["attemptCount"] == 0
    assert resent["attempts"][-1]["mode"] == "manual_resend_requested"


def test_attempt_audit_keeps_only_the_most_recent_twenty_entries():
    project, occurrence_id = _staged_project()
    occurrence = project["orchestration"]["completionReports"][0]

    for index in range(25):
        occurrence.update({"state": "failed", "visibleStatus": "failed"})
        request_manual_resend(
            project,
            occurrence_id=occurrence_id,
            now=f"2026-08-03T03:{index:02d}:00+00:00",
            owner_authorized=True,
        )

    assert len(occurrence["attempts"]) == 20
    assert occurrence["attempts"][0]["requestedAt"] == "2026-08-03T03:05:00+00:00"
