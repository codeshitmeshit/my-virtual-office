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

from services.project_completion_reporting import stage_completion_report_occurrence


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
