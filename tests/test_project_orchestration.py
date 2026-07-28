#!/usr/bin/env python3
"""Table-driven tests for pure Project task orchestration helpers."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services import project_orchestration as orchestration


def _project(tasks, **overrides):
    project = {
        "id": "p1",
        "executionModel": orchestration.EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": orchestration.default_orchestration_state(),
        "tasks": tasks,
    }
    project.update(overrides)
    return project


def _task(task_id, stage, state="backlog", **overrides):
    task = {
        "id": task_id,
        "title": task_id,
        "executionStage": stage,
        "executionState": state,
        "orchestrationSkip": orchestration.default_skip_state(),
        "attempts": [],
    }
    task.update(overrides)
    return task


@pytest.mark.parametrize(
    ("assignments", "expected"),
    [
        ([{"taskId": "a", "executionStage": 1}, {"taskId": "b", "executionStage": 1}], (("a", 1), ("b", 1))),
        ([{"taskId": "a", "executionStage": 2}, {"taskId": "b", "executionStage": 5}], (("a", 1), ("b", 2))),
        ([{"taskId": "a", "executionStage": "3"}, {"taskId": "b", "executionStage": "3"}], (("a", 1), ("b", 1))),
    ],
)
def test_normalize_assignments_compacts_positive_stages(assignments, expected):
    result = orchestration.normalize_assignments(assignments)
    assert result.ok is True
    assert result.assignments == expected


@pytest.mark.parametrize(
    ("assignments", "codes"),
    [
        ([{"taskId": "", "executionStage": 1}], {"missing_task_id"}),
        ([{"taskId": "a", "executionStage": 0}], {"invalid_execution_stage"}),
        ([{"taskId": "a", "executionStage": 1}, {"taskId": "a", "executionStage": 2}], {"duplicate_task_id"}),
    ],
)
def test_normalize_assignments_reports_invalid_inputs(assignments, codes):
    result = orchestration.normalize_assignments(assignments)
    assert result.ok is False
    assert {issue.code for issue in result.issues} == codes


@pytest.mark.parametrize(
    ("project", "codes"),
    [
        (_project([_task("a", 1), _task("b", 1), _task("c", 2)]), set()),
        (_project([_task("a", 2)]), {"non_contiguous_stages"}),
        (_project([_task("a", None)]), {"invalid_execution_stage"}),
        (_project([_task("a", 1)], executionModel=None), {"missing_execution_model"}),
        (_project([_task("a", 1)], orchestration={"schemaVersion": 99, "state": "draft"}), {"invalid_orchestration_schema"}),
        (_project([_task("a", 1)], orchestration={"schemaVersion": 1, "state": "weird"}), {"invalid_orchestration_state"}),
    ],
)
def test_validate_stage_invariants(project, codes):
    result = orchestration.validate_stage_invariants(project)
    assert {issue.code for issue in result.issues} == codes
    assert result.ok is (not codes)


@pytest.mark.parametrize(
    ("task", "accepted"),
    [
        (_task("done", 1, state="done"), True),
        (_task("completed-at", 1, completedAt="now"), True),
        (_task("skip", 1, orchestrationSkip={"status": "approved"}), True),
        (_task("review-skipped", 1, reviewResult={"status": "skipped"}), False),
        (_task("awaiting", 1, state="awaiting_user_acceptance"), False),
    ],
)
def test_task_accepted_terminal_does_not_reuse_review_skipped(task, accepted):
    assert orchestration.task_is_accepted_terminal(task) is accepted


def test_stage_helpers_detect_completed_blocked_and_next_unfinished_stage():
    project = _project([
        _task("a", 1, state="done"),
        _task("b", 1, orchestrationSkip={"status": "approved"}),
        _task("c", 2, state="blocked", blockedReason="failed"),
        _task("d", 3),
    ])
    assert orchestration.last_completed_stage(project) == 1
    assert orchestration.next_unfinished_stage(project) == 2
    assert orchestration.stage_has_accepted_terminal_outcomes(project, 1) is True
    assert orchestration.stage_has_failed_or_blocked_task(project, 2) is True


def test_completed_stage_locks_reject_reassigning_completed_history():
    project = _project([
        _task("a", 1, state="done"),
        _task("b", 2),
        _task("c", 3),
    ])
    issues = orchestration.validate_completed_stage_locks(
        project,
        [
            {"taskId": "a", "executionStage": 2},
            {"taskId": "b", "executionStage": 2},
            {"taskId": "c", "executionStage": 3},
        ],
    )
    assert [issue.code for issue in issues] == ["completed_stage_locked"]
    assert issues[0].task_id == "a"


def test_compact_stages_after_removal_closes_empty_stage_gaps():
    project = _project([
        _task("a", 1),
        _task("b", 2),
        _task("c", 3),
        _task("d", 3),
    ])

    assert orchestration.compact_stages_after_removal(project, "b") == (
        ("a", 1),
        ("c", 2),
        ("d", 2),
    )
    assert orchestration.compact_stages_after_removal(project, "c") == (
        ("a", 1),
        ("b", 2),
        ("d", 3),
    )


def test_active_task_projection_is_derived_from_task_attempts_and_states():
    project = _project(
        [
            _task("a", 1, activeAttemptId="attempt-a"),
            _task("b", 1, state="reviewing"),
            _task("c", 2, attempts=[{"id": "attempt-c", "status": "executing"}]),
            _task("d", 2, state="backlog"),
        ],
        orchestration={
            **orchestration.default_orchestration_state(),
            "state": "running",
            "currentStage": 1,
            "pauseReason": None,
        },
    )

    assert orchestration.active_task_ids(project) == ("a", "b", "c")
    assert orchestration.active_task_count(project) == 3
    assert orchestration.project_projection(project) == {
        "executionModel": "stage_pipeline_v1",
        "orchestrationState": "running",
        "currentStage": 1,
        "pauseReason": None,
        "activeTaskIds": ["a", "b", "c"],
        "activeTaskCount": 3,
    }


def test_current_stage_tasks_groups_parallel_tasks():
    project = _project(
        [_task("a", 1), _task("b", 2), _task("c", 2)],
        orchestration={**orchestration.default_orchestration_state(), "state": "running", "currentStage": 2},
    )
    assert [task["id"] for task in orchestration.current_stage_tasks(project)] == ["b", "c"]


def test_project_orchestration_module_has_no_transport_or_repository_dependency():
    source = (APP / "services" / "project_orchestration.py").read_text(encoding="utf-8")
    forbidden = ["import server", "ProjectRepository", "http.server", "requests", "subprocess"]
    for token in forbidden:
        assert token not in source
