#!/usr/bin/env python3
"""Tests for phase-one project orchestration pause commands."""

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
from services.project_orchestration_pause import (
    PauseCancellationPorts,
    PausePorts,
    complete_phase_two_pause,
    request_phase_one_pause,
)
from services.project_repository import ProjectRepository


class _MemoryStore:
    def __init__(self, project):
        self.data = {"projects": [copy.deepcopy(project)], "templates": []}
        self.save_calls = 0

    def load(self):
        return copy.deepcopy(self.data)

    def save(self, value):
        self.save_calls += 1
        self.data = copy.deepcopy(value)


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


def _project(*, state="running", revision=3, tasks=None, marked=True):
    project = {
        "id": "project-1",
        "title": "Project",
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": {
            **default_orchestration_state(),
            "state": state,
            "currentStage": 1,
            "currentRunId": "run-1",
            "revision": revision,
        },
        "tasks": tasks if tasks is not None else [
            _task(
                "a",
                1,
                stageRunId="run-1",
                executionState="executing",
                activeAttemptId="attempt-a",
                attempts=[{"id": "attempt-a", "status": "executing", "stageRunId": "run-1"}],
            ),
            _task(
                "b",
                1,
                stageRunId="run-1",
                executionState="reviewing",
                activeAttemptId="attempt-b",
                attempts=[{"id": "attempt-b", "status": "reviewing", "stageRunId": "run-1"}],
            ),
            _task("c", 2),
        ],
    }
    if not marked:
        project.pop("executionModel", None)
    return project


def _repo(project):
    store = _MemoryStore(project)
    return store, ProjectRepository(load_projects=store.load, save_projects=store.save)


def _ports(*, authorized=True):
    return PausePorts(
        now=lambda: "paused-at",
        authorize=lambda project, actor: (
            {"ok": True}
            if authorized
            else {"ok": False, "code": "management_token_required", "error": "manager required"}
        ),
    )


def _cancellation_ports(cancelled=None, *, fail_attempts=None):
    cancelled = cancelled if cancelled is not None else []
    fail_attempts = set(fail_attempts or ())

    def cancel_attempt(payload):
        cancelled.append(dict(payload))
        if payload["attemptId"] in fail_attempts:
            return {"ok": False, "status": "provider_cancel_failed", "error": "provider refused"}
        return {"ok": True, "status": "cancelled", "provider": "fake"}

    def transition(project, task, next_state, actor, reason, attempt_id):
        task["executionState"] = next_state
        task.setdefault("stateHistory", []).append({
            "state": next_state,
            "actor": actor,
            "reason": reason,
            "attemptId": attempt_id,
        })

    return PauseCancellationPorts(
        now=lambda: "converged-at",
        cancel_attempt=cancel_attempt,
        transition=transition,
    )


def _pausing_project():
    project = _project(state="pausing", revision=4)
    project["orchestration"]["pauseReason"] = "rebalance stages"
    project["orchestration"]["pauseSnapshot"] = {
        "requestedAt": "paused-at",
        "requestedBy": {"type": "management", "id": "manager"},
        "reason": "rebalance stages",
        "currentStage": 1,
        "currentRunId": "run-1",
        "activeAttemptIds": ["attempt-a", "attempt-b"],
        "activeAttempts": [
            {"taskId": "a", "attemptId": "attempt-a", "executionStage": 1, "stageRunId": "run-1"},
            {"taskId": "b", "attemptId": "attempt-b", "executionStage": 1, "stageRunId": "run-1"},
        ],
    }
    return project


def test_phase_one_pause_requires_explicit_confirmation():
    store, repo = _repo(_project())

    outcome = request_phase_one_pause(
        "project-1",
        {"actor": {"type": "management", "id": "manager"}},
        repository=repo,
        ports=_ports(),
    )

    assert outcome.result.status == 400
    assert outcome.result.payload["code"] == "pause_confirmation_required"
    assert store.save_calls == 0


def test_phase_one_pause_enters_pausing_and_snapshots_active_attempts():
    store, repo = _repo(_project())

    outcome = request_phase_one_pause(
        "project-1",
        {
            "confirm": True,
            "actor": {"type": "management", "id": "manager"},
            "reason": "rebalance stages",
        },
        repository=repo,
        ports=_ports(),
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["status"] == "pausing"
    assert outcome.result.payload["activeAttemptIds"] == ["attempt-a", "attempt-b"]
    assert outcome.result.payload["idempotent"] is False
    saved = store.data["projects"][0]
    state = saved["orchestration"]
    assert state["state"] == "pausing"
    assert state["revision"] == 4
    assert state["pauseReason"] == "rebalance stages"
    assert state["currentRunId"] == "run-1"
    assert state["currentStage"] == 1
    assert state["pauseSnapshot"]["activeAttemptIds"] == ["attempt-a", "attempt-b"]
    assert state["pauseSnapshot"]["activeAttempts"][0] == {
        "taskId": "a",
        "attemptId": "attempt-a",
        "executionStage": 1,
        "stageRunId": "run-1",
        "executionState": "executing",
        "attemptStatus": "executing",
    }
    assert state["pauseSnapshot"]["activeAttempts"][1]["attemptStatus"] == "reviewing"
    assert [task["activeAttemptId"] for task in saved["tasks"][:2]] == ["attempt-a", "attempt-b"]


def test_phase_one_pause_is_idempotent_while_already_pausing():
    project = _project(state="pausing")
    project["orchestration"]["pauseSnapshot"] = {"activeAttemptIds": ["attempt-a"], "activeAttempts": []}
    store, repo = _repo(project)

    outcome = request_phase_one_pause(
        "project-1",
        {"confirm": True, "actor": {"type": "management", "id": "manager"}},
        repository=repo,
        ports=_ports(),
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["idempotent"] is True
    assert outcome.result.payload["activeAttemptIds"] == ["attempt-a"]
    assert store.data["projects"][0]["orchestration"]["revision"] == 3
    assert store.save_calls == 1


def test_phase_one_pause_rejects_unauthorized_or_non_pausable_projects_without_mutation():
    store, repo = _repo(_project())
    forbidden = request_phase_one_pause(
        "project-1",
        {"confirm": True, "actor": {"type": "agent", "id": "worker"}},
        repository=repo,
        ports=_ports(authorized=False),
    )
    assert forbidden.result.status == 403
    assert forbidden.result.payload["code"] == "management_token_required"
    assert store.save_calls == 0

    completed_store, completed_repo = _repo(_project(state="completed"))
    completed = request_phase_one_pause(
        "project-1",
        {"confirm": True, "actor": {"type": "management", "id": "manager"}},
        repository=completed_repo,
        ports=_ports(),
    )
    assert completed.result.status == 409
    assert completed.result.payload["code"] == "orchestration_not_pausable"
    assert completed_store.save_calls == 0


def test_phase_two_pause_cancels_outside_lock_then_converges_to_paused():
    project = _pausing_project()
    store, repo = _repo(project)
    cancelled = []

    outcome = complete_phase_two_pause(
        "project-1",
        repository=repo,
        ports=_cancellation_ports(cancelled),
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["status"] == "paused"
    assert outcome.result.payload["idempotent"] is False
    assert cancelled == [
        {"taskId": "a", "attemptId": "attempt-a"},
        {"taskId": "b", "attemptId": "attempt-b"},
    ]
    saved = store.data["projects"][0]
    state = saved["orchestration"]
    assert state["state"] == "paused"
    assert state["currentRunId"] is None
    assert state["currentStage"] == 1
    assert state["revision"] == 5
    assert state["pauseSnapshot"]["convergedAt"] == "converged-at"
    assert [item["attemptId"] for item in state["pauseSnapshot"]["cancelledAttempts"]] == ["attempt-a", "attempt-b"]
    assert [item["ok"] for item in state["pauseSnapshot"]["cancelResults"]] == [True, True]
    task_a, task_b = saved["tasks"][:2]
    assert task_a["activeAttemptId"] is None
    assert task_a["stageRunId"] is None
    assert task_a["executionState"] == "pending"
    assert task_a["attempts"][0]["status"] == "cancelled"
    assert task_a["attempts"][0]["finishedAt"] == "converged-at"
    assert task_a["stateHistory"][-1]["state"] == "pending"
    assert task_b["activeAttemptId"] is None
    assert task_b["stageRunId"] is None


def test_phase_two_pause_keeps_completed_tasks_immutable_when_captured():
    project = _pausing_project()
    project["tasks"][0].update({"executionState": "done", "completedAt": "done-at"})
    store, repo = _repo(project)

    outcome = complete_phase_two_pause(
        "project-1",
        repository=repo,
        ports=_cancellation_ports(),
    )

    assert outcome.result.status == 200
    saved = store.data["projects"][0]
    completed_task = saved["tasks"][0]
    assert completed_task["executionState"] == "done"
    assert completed_task["completedAt"] == "done-at"
    assert completed_task["stageRunId"] == "run-1"
    assert completed_task["attempts"][0]["status"] == "cancelled"
    assert saved["tasks"][1]["executionState"] == "pending"


def test_phase_two_pause_failure_keeps_project_pausing_without_mutation():
    project = _pausing_project()
    before = copy.deepcopy(project)
    store, repo = _repo(project)
    cancelled = []

    outcome = complete_phase_two_pause(
        "project-1",
        repository=repo,
        ports=_cancellation_ports(cancelled, fail_attempts={"attempt-b"}),
    )

    assert outcome.result.status == 409
    assert outcome.result.payload["code"] == "pause_cancellation_failed"
    assert [item["ok"] for item in outcome.result.payload["cancelResults"]] == [True, False]
    assert cancelled == [
        {"taskId": "a", "attemptId": "attempt-a"},
        {"taskId": "b", "attemptId": "attempt-b"},
    ]
    assert store.data["projects"][0] == before
    assert store.save_calls == 0


def test_phase_two_pause_is_idempotent_after_project_is_paused():
    project = _pausing_project()
    project["orchestration"].update({
        "state": "paused",
        "currentRunId": None,
        "pauseSnapshot": {
            **project["orchestration"]["pauseSnapshot"],
            "cancelResults": [{"taskId": "a", "attemptId": "attempt-a", "ok": True}],
        },
    })
    store, repo = _repo(project)
    cancelled = []

    outcome = complete_phase_two_pause(
        "project-1",
        repository=repo,
        ports=_cancellation_ports(cancelled),
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["idempotent"] is True
    assert outcome.result.payload["cancelResults"] == [{"taskId": "a", "attemptId": "attempt-a", "ok": True}]
    assert cancelled == []
    assert store.save_calls == 0
