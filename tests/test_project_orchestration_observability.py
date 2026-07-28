#!/usr/bin/env python3
"""Structured observability coverage for project task orchestration."""

from __future__ import annotations

import copy
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-orchestration-observability-test-"))

from services.project_orchestration import EXECUTION_MODEL_STAGE_PIPELINE_V1, default_orchestration_state, default_skip_state
from services.project_orchestration_commands import autosave_orchestration
from services.project_orchestration_observability import (
    autosave_conflict_diagnostics,
    duplicate_suppression_diagnostics,
    pause_diagnostics,
    recovery_diagnostics,
    reservation_diagnostics,
    skip_decision_diagnostics,
    stage_advancement_diagnostics,
    stuck_state_diagnostics,
    submission_diagnostics,
)
from services.project_orchestration_recovery import RecoveryPorts, recover_marked_projects
from services.project_repository import ProjectRepository
from services.project_stage_dispatch import BoundedProjectExecutionDispatcher, QUEUE_FULL_CODE, reconcile_stage, reserve_stage_run


class _MemoryStore:
    def __init__(self, project):
        self.data = {"projects": [copy.deepcopy(project)], "templates": []}
        self.save_calls = 0

    def load(self):
        return copy.deepcopy(self.data)

    def save(self, value):
        self.save_calls += 1
        self.data = copy.deepcopy(value)


class _PreflightPorts:
    def validate_workspace(self, path):
        return {"ok": True, "path": path, "kind": "local"}

    def git_snapshot(self, path):
        return {"ok": True, "dirty": False, "files": [], "fingerprint": "", "truncated": False}

    def resolve_roles(self, project, task, allow_skip_reviewer):
        return {"ok": True, "executor": {"id": "executor"}, "reviewer": {"id": "reviewer"}}

    def authorize(self, project, actor):
        return {"ok": True}

    def now(self):
        return "now"

    def new_run_id(self):
        return "run-1"


def _task(task_id, stage, **overrides):
    task = {
        "id": task_id,
        "title": task_id,
        "executionStage": stage,
        "stageRunId": None,
        "orchestrationSkip": default_skip_state(),
        "executionState": "pending",
        "attempts": [],
        "activeAttemptId": None,
        "executorAgentId": "executor",
        "reviewerAgentId": "reviewer",
    }
    task.update(overrides)
    return task


def _project(*, state="draft", revision=0, tasks=None):
    return {
        "id": "project-1",
        "title": "Project",
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": {
            **default_orchestration_state(),
            "state": state,
            "currentStage": 1 if state in {"starting", "running"} else None,
            "currentRunId": "run-1" if state in {"starting", "running"} else None,
            "revision": revision,
        },
        "projectExecutionEnabled": True,
        "workspacePath": "/work/project",
        "tasks": tasks if tasks is not None else [_task("a", 1), _task("b", 1), _task("c", 2)],
    }


def _repo(project):
    store = _MemoryStore(project)
    return store, ProjectRepository(load_projects=store.load, save_projects=store.save)


def test_observability_helpers_emit_stable_counters_timings_and_audit_context():
    diagnostics = [
        reservation_diagnostics(status="reserved", project_id="p", stage=1, run_id="r", revision=2, task_ids=["t"], duration_ms=4),
        submission_diagnostics(status="rejected", project_id="p", task_id="t", stage=1, run_id="r", attempt_id="a", revision=2, queued=1, in_flight=0, worker_count=8, queue_capacity=1, code=QUEUE_FULL_CODE),
        duplicate_suppression_diagnostics(project_id="p", stage=1, run_id="r", revision=2, status="stage_waiting", pending_task_ids=["t"]),
        stage_advancement_diagnostics(project_id="p", stage=1, run_id="r", revision=3, status="stage_advanced", next_stage=2, next_run_id="r2", duration_ms=5),
        pause_diagnostics(project_id="p", stage=1, run_id="r", revision=4, status="pausing", attempt_ids=["a"], duration_ms=6),
        skip_decision_diagnostics(project_id="p", task_id="t", stage=1, run_id="r", attempt_id="a", revision=4, status="approved", approved=True),
        recovery_diagnostics(project_id="p", stage=1, run_id="r", revision=5, status="blocked", preserved_attempt_ids=["a"], prepared_attempt_ids=["b"], blocked_task_ids=["t"], duration_ms=7),
        autosave_conflict_diagnostics(project_id="p", revision=4, current_revision=5),
        stuck_state_diagnostics(project_id="p", stage=1, run_id="r", revision=5, status="blocked", blocked_task_ids=["t"], code="not_resumable"),
    ]

    for item in diagnostics:
        assert set(item) == {"operation", "status", "counters", "timings", "audit"}
        assert item["audit"]["projectId"] == "p"
        assert item["counters"]
    assert diagnostics[1]["counters"]["queueRejections"] == 1
    assert diagnostics[1]["audit"]["attemptId"] == "a"
    assert diagnostics[7]["audit"]["currentRevision"] == 5
    assert diagnostics[8]["counters"]["stuckStates"] == 1


def test_dispatcher_submission_diagnostics_identify_attempt_revision_and_queue_rejection():
    dispatcher = BoundedProjectExecutionDispatcher(lambda item: item.task_id, worker_count=1, queue_capacity=1, autostart=False)

    first = dispatcher.submit(project_id="project-1", task_id="a", run_id="run-1", payload={"attemptId": "attempt-a", "stage": 1, "revision": 4})
    second = dispatcher.submit(project_id="project-1", task_id="b", run_id="run-1", payload={"attemptId": "attempt-b", "stage": 1, "revision": 4})

    assert first.diagnostics["audit"]["attemptId"] == "attempt-a"
    assert first.diagnostics["audit"]["revision"] == 4
    assert second.accepted is False
    assert second.diagnostics["counters"]["queueRejections"] == 1
    assert second.diagnostics["audit"]["code"] == QUEUE_FULL_CODE


def test_reservation_reconciliation_and_autosave_conflict_expose_diagnostics():
    store, repo = _repo(_project())
    reserved = reserve_stage_run("project-1", {"revision": 0}, repository=repo, ports=_PreflightPorts())

    assert reserved.result.status == 200
    assert reserved.result.payload["diagnostics"]["operation"] == "reservation"
    assert reserved.result.payload["diagnostics"]["audit"]["taskCount"] == 2
    assert store.data["projects"][0]["orchestrationAudit"][-1]["operation"] == "reservation"

    stale = autosave_orchestration(
        "project-1",
        {"revision": 0, "assignments": [{"taskId": "a", "executionStage": 1}, {"taskId": "b", "executionStage": 1}, {"taskId": "c", "executionStage": 2}]},
        repository=repo,
        now=lambda: "saved",
    )

    assert stale.result.status == 409
    assert stale.result.payload["diagnostics"]["operation"] == "autoSaveConflict"
    assert stale.result.payload["diagnostics"]["audit"]["revision"] == 0
    assert stale.result.payload["diagnostics"]["audit"]["currentRevision"] == 1

    running = _project(
        state="running",
        revision=1,
        tasks=[
            _task("a", 1, stageRunId="run-1", executionState="done", completedAt="done"),
            _task("b", 1, stageRunId="run-1", executionState="done", completedAt="done"),
            _task("c", 2),
        ],
    )
    _advanced_store, advanced_repo = _repo(running)
    advanced = reconcile_stage("project-1", "run-1", repository=advanced_repo, now=lambda: "done", new_run_id=lambda: "run-2")

    assert advanced.result.status == 200
    assert advanced.result.payload["diagnostics"]["operation"] == "stageAdvancement"
    assert advanced.result.payload["diagnostics"]["counters"]["stageAdvancements"] == 1

    duplicate = reconcile_stage("project-1", "run-1", repository=advanced_repo, now=lambda: "later", new_run_id=lambda: "unused")

    assert duplicate.result.status == 200
    assert duplicate.result.payload["diagnostics"]["operation"] == "duplicateSuppression"
    assert duplicate.result.payload["diagnostics"]["counters"]["duplicateSuppressions"] == 1


def test_recovery_payload_includes_recovery_and_stuck_state_diagnostics():
    task = _task(
        "a",
        1,
        stageRunId="run-1",
        executionState="executing",
        activeAttemptId="attempt-a",
        attempts=[{"id": "attempt-a", "status": "executing", "stageRunId": "run-1"}],
    )
    _store, repo = _repo(_project(state="running", revision=4, tasks=[task]))

    ports = RecoveryPorts(
        now=lambda: "recovered",
        is_live_attempt=lambda attempt_id: False,
        prepare_reserved_task=lambda project_id, task_id, run_id: {"ok": True, "attemptId": "new"},
        submit_reserved_task=lambda project_id, task_id, run_id, attempt_id: {"ok": True, "accepted": True},
        reconcile_stage_run=lambda project_id, run_id: {"ok": True, "status": "stage_waiting"},
        complete_pausing_project=lambda project_id: {"ok": True, "status": "paused"},
        transition=lambda project, task, next_state, actor, reason, attempt_id: None,
    )

    report = recover_marked_projects(repository=repo, ports=ports)
    payload = report.result.payload["projects"][0]

    assert payload["status"] == "blocked"
    assert payload["diagnostics"]["counters"]["recoveries"] == 1
    assert payload["diagnostics"]["counters"]["stuckStates"] == 1
    assert [event["operation"] for event in payload["diagnostics"]["audit"]] == ["recovery", "stuckState"]
