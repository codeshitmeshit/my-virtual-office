#!/usr/bin/env python3
"""Tests for marked project startup recovery."""

from __future__ import annotations

import copy
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.project_orchestration import (
    EXECUTION_MODEL_STAGE_PIPELINE_V1,
    default_orchestration_state,
    default_skip_state,
)
from services.project_orchestration_recovery import (
    NON_RESUMABLE_REASON,
    RecoveryPorts,
    recover_marked_projects,
)
from services.project_repository import ProjectRepository


class _MemoryStore:
    def __init__(self, projects):
        self.data = {"projects": copy.deepcopy(projects), "templates": []}
        self.save_calls = 0

    def load(self):
        return copy.deepcopy(self.data)

    def save(self, value):
        self.save_calls += 1
        self.data = copy.deepcopy(value)


class _Ports:
    def __init__(self, repository, *, live_attempts=None):
        self.repository = repository
        self.live_attempts = set(live_attempts or ())
        self.next_attempt = 1
        self.prepared = []
        self.submitted = []
        self.reconciled = []
        self.pausing = []
        self.transitions = []

    def now(self):
        return "recovered-at"

    def is_live_attempt(self, attempt_id):
        return attempt_id in self.live_attempts

    def prepare_reserved_task(self, project_id, task_id, run_id):
        attempt_id = f"recovered-attempt-{self.next_attempt}"
        self.next_attempt += 1

        def mutate(project):
            task = next(item for item in project["tasks"] if item["id"] == task_id)
            attempt = {
                "id": attempt_id,
                "status": "executing",
                "stageRunId": run_id,
                "startedAt": "recovered-at",
            }
            task.setdefault("attempts", []).append(attempt)
            task["activeAttemptId"] = attempt_id
            task["executionState"] = "executing"
            project["orchestration"]["state"] = "running"

        self.repository.update(project_id, mutate)
        self.prepared.append((project_id, task_id, run_id, attempt_id))
        return {"ok": True, "attemptId": attempt_id, "runId": run_id, "idempotent": False}

    def submit_reserved_task(self, project_id, task_id, run_id, attempt_id):
        self.live_attempts.add(attempt_id)
        self.submitted.append((project_id, task_id, run_id, attempt_id))
        return {"ok": True, "accepted": True, "code": "accepted"}

    def reconcile_stage_run(self, project_id, run_id):
        self.reconciled.append((project_id, run_id))
        return {"ok": True, "status": "stage_waiting", "runId": run_id}

    def complete_pausing_project(self, project_id):
        self.pausing.append(project_id)
        return {"ok": True, "status": "paused"}

    def transition(self, project, task, next_state, actor, reason, attempt_id):
        self.transitions.append((project["id"], task["id"], next_state, actor, reason, attempt_id))
        task["executionState"] = next_state

    def ports(self):
        return RecoveryPorts(
            now=self.now,
            is_live_attempt=self.is_live_attempt,
            prepare_reserved_task=self.prepare_reserved_task,
            submit_reserved_task=self.submit_reserved_task,
            reconcile_stage_run=self.reconcile_stage_run,
            complete_pausing_project=self.complete_pausing_project,
            transition=self.transition,
        )


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
    }
    task.update(overrides)
    return task


def _project(*, project_id="project-1", state="starting", tasks=None):
    return {
        "id": project_id,
        "title": project_id,
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": {
            **default_orchestration_state(),
            "state": state,
            "currentStage": 1,
            "currentRunId": "run-1",
            "revision": 4,
        },
        "workspacePath": "/work/project",
        "tasks": tasks if tasks is not None else [_task("a", 1, stageRunId="run-1")],
    }


def _repo(*projects):
    store = _MemoryStore(list(projects))
    return store, ProjectRepository(load_projects=store.load, save_projects=store.save)


def test_recovery_resubmits_reserved_tasks_without_attempts_and_preserves_live_attempts():
    project = _project(tasks=[
        _task("a", 1, stageRunId="run-1"),
        _task(
            "b",
            1,
            stageRunId="run-1",
            executionState="executing",
            activeAttemptId="attempt-b",
            attempts=[{"id": "attempt-b", "status": "executing", "stageRunId": "run-1"}],
        ),
    ])
    _store, repository = _repo(project)
    ports = _Ports(repository, live_attempts={"attempt-b"})

    report = recover_marked_projects(repository=repository, ports=ports.ports())

    assert report.result.status == 200
    result = report.projects[0]
    assert result.status == "resubmitted"
    assert result.preserved_attempt_ids == ("attempt-b",)
    assert ports.prepared == [("project-1", "a", "run-1", "recovered-attempt-1")]
    assert ports.submitted == [("project-1", "a", "run-1", "recovered-attempt-1")]
    saved = repository.get("project-1")
    assert saved["tasks"][0]["activeAttemptId"] == "recovered-attempt-1"
    assert saved["tasks"][1]["activeAttemptId"] == "attempt-b"

    second = recover_marked_projects(repository=repository, ports=ports.ports())

    assert second.projects[0].status == "preserved"
    assert ports.prepared == [("project-1", "a", "run-1", "recovered-attempt-1")]
    assert ports.submitted == [("project-1", "a", "run-1", "recovered-attempt-1")]


def test_recovery_blocks_non_resumable_active_attempt_without_duplicate_submission():
    project = _project(state="running", tasks=[
        _task(
            "a",
            1,
            stageRunId="run-1",
            executionState="executing",
            activeAttemptId="attempt-a",
            attempts=[{"id": "attempt-a", "status": "executing", "stageRunId": "run-1"}],
        ),
        _task("b", 1, stageRunId="run-1"),
    ])
    _store, repository = _repo(project)
    ports = _Ports(repository, live_attempts=set())

    report = recover_marked_projects(repository=repository, ports=ports.ports())

    result = report.projects[0]
    assert result.status == "blocked"
    assert result.blocked_task_ids == ("a",)
    assert ports.prepared == []
    assert ports.submitted == []
    saved = repository.get("project-1")
    assert saved["orchestration"]["state"] == "blocked"
    assert saved["orchestration"]["pauseReason"] == NON_RESUMABLE_REASON
    assert saved["tasks"][0]["activeAttemptId"] is None
    assert saved["tasks"][0]["attempts"][0]["status"] == "blocked"
    assert saved["tasks"][0]["blockedReason"] == NON_RESUMABLE_REASON


def test_recovery_restores_live_stage_attempt_missing_active_pointer():
    project = _project(state="running", tasks=[
        _task(
            "a",
            1,
            stageRunId="run-1",
            executionState="executing",
            attempts=[{"id": "attempt-a", "status": "executing", "stageRunId": "run-1"}],
        ),
    ])
    _store, repository = _repo(project)
    ports = _Ports(repository, live_attempts={"attempt-a"})

    report = recover_marked_projects(repository=repository, ports=ports.ports())

    assert report.projects[0].status == "preserved"
    assert report.projects[0].preserved_attempt_ids == ("attempt-a",)
    assert ports.prepared == []
    assert repository.get("project-1")["tasks"][0]["activeAttemptId"] == "attempt-a"


def test_recovery_repeats_pausing_convergence_without_dispatch():
    project = _project(state="pausing", tasks=[
        _task(
            "a",
            1,
            stageRunId="run-1",
            executionState="executing",
            activeAttemptId="attempt-a",
            attempts=[{"id": "attempt-a", "status": "cancelling", "stageRunId": "run-1"}],
        ),
    ])
    _store, repository = _repo(project)
    ports = _Ports(repository, live_attempts={"attempt-a"})

    report = recover_marked_projects(repository=repository, ports=ports.ports())

    assert report.projects[0].status == "paused"
    assert ports.pausing == ["project-1"]
    assert ports.prepared == []
    assert ports.submitted == []
    assert ports.reconciled == []
