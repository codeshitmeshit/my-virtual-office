#!/usr/bin/env python3
"""Server adapter tests for marked project stage starts."""

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

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-stage-start-server-import-"))

import server
from services.project_orchestration import (
    EXECUTION_MODEL_STAGE_PIPELINE_V1,
    default_orchestration_state,
    default_skip_state,
)
from services.project_repository import ProjectRepository
from services.project_stage_dispatch import BoundedProjectExecutionDispatcher
from services.project_stage_dispatch import QUEUE_FULL_CODE


class _MemoryStore:
    def __init__(self, project):
        self.data = {"projects": [copy.deepcopy(project)], "templates": []}

    def load(self):
        return copy.deepcopy(self.data)

    def save(self, value):
        self.data = copy.deepcopy(value)


class _PreflightPorts:
    def __init__(self):
        self.run_ids = ["run-1"]

    def validate_workspace(self, path):
        return {"ok": True, "path": path, "kind": "local", "virtual": True}

    def git_snapshot(self, path):
        return {"ok": True, "dirty": False, "files": [], "fingerprint": ""}

    def resolve_roles(self, project, task, allow_skip):
        return {"ok": True, "executor": {"id": f"exec-{task['id']}"}, "reviewer": {"id": "reviewer"}}

    def authorize(self, project, actor):
        return {"ok": True}

    def now(self):
        return "now"

    def new_run_id(self):
        return self.run_ids.pop(0)


class _AttemptPorts:
    def __init__(self):
        self.attempt_ids = ["attempt-a", "attempt-b"]

    def now(self):
        return "now"

    def new_attempt_id(self):
        return self.attempt_ids.pop(0)

    def requires_acceptance(self, task):
        return False

    def seed_checklist(self, task, actor):
        return True

    def has_pending_meeting_actions(self, task):
        return False

    def transition(self, project, task, next_state, actor, reason, attempt_id):
        task["executionState"] = next_state


def _task(task_id, stage):
    return {
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


def _project():
    return {
        "id": "project-1",
        "title": "Project",
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": default_orchestration_state(),
        "projectExecutionEnabled": True,
        "workspacePath": "/workspace/project",
        "tasks": [_task("a", 1), _task("b", 1), _task("c", 2)],
    }


def _install(monkeypatch, project):
    store = _MemoryStore(project)
    repo = ProjectRepository(load_projects=store.load, save_projects=store.save)
    monkeypatch.setattr(server, "_PROJECT_REPOSITORY", repo)
    return store


def test_marked_project_level_start_reserves_and_submits_stage(monkeypatch):
    store = _install(monkeypatch, _project())
    dispatched = []
    dispatcher = BoundedProjectExecutionDispatcher(
        lambda item: dispatched.append((item.task_id, item.payload["attemptId"])),
        worker_count=1,
        queue_capacity=4,
        autostart=False,
    )
    monkeypatch.setattr(server, "_PROJECT_STAGE_EXECUTION_DISPATCHER", dispatcher)
    monkeypatch.setattr(server, "_project_stage_preflight_ports", lambda: _PreflightPorts())
    monkeypatch.setattr(server, "_project_stage_attempt_ports", lambda: _AttemptPorts())

    result = server._handle_project_execution_project_start("project-1", {"by": "owner"})

    assert result["_status"] == 200
    assert result["status"] == "stage_started"
    assert result["taskIds"] == ["a", "b"]
    assert [attempt["attemptId"] for attempt in result["attempts"]] == ["attempt-a", "attempt-b"]
    saved = store.data["projects"][0]
    assert saved["orchestration"]["currentRunId"] == "run-1"
    assert saved["orchestration"]["currentStage"] == 1
    assert saved["orchestration"]["state"] == "running"
    assert saved["tasks"][0]["activeAttemptId"] == "attempt-a"
    assert saved["tasks"][1]["activeAttemptId"] == "attempt-b"
    assert saved["tasks"][2].get("stageRunId") is None
    assert saved.get("activeTaskId") is None
    assert saved.get("activeAgent") is None
    assert dispatcher.diagnostics()["queued"] == 2
    assert dispatcher.run_next_for_tests().ok is True
    assert dispatcher.run_next_for_tests().ok is True
    assert dispatched == [("a", "attempt-a"), ("b", "attempt-b")]


def test_marked_project_level_start_rejects_legacy_start_payload(monkeypatch):
    _install(monkeypatch, _project())

    result = server._handle_project_execution_project_start(
        "project-1",
        {"mode": "single", "startMode": "continuous", "restartPipeline": True},
    )

    assert result["_status"] == 400
    assert result["code"] == "marked_project_legacy_start_payload_forbidden"
    assert result["fields"] == ["mode", "startMode", "restartPipeline"]


def test_marked_project_level_start_restarts_completed_reusable_project(monkeypatch):
    project = _project()
    project.update({"projectType": "reusable", "status": "completed"})
    project["orchestration"].update({
        "state": "completed",
        "currentStage": 2,
        "currentRunId": None,
        "completedAt": "done-at",
        "revision": 5,
    })
    project["tasks"] = [
        {
            **_task("a", 1),
            "executionState": "done",
            "completedAt": "done-at",
            "stageRunId": "run-old",
            "activeAttemptId": "attempt-old",
            "reviewResult": {"status": "pass"},
            "meetingBlocker": {"requestId": "req-1"},
        },
        {
            **_task("later", 2),
            "executionState": "done",
            "completedAt": "done-at",
            "stageRunId": "run-later",
        },
    ]
    store = _install(monkeypatch, project)
    dispatcher = BoundedProjectExecutionDispatcher(
        lambda item: item.task_id,
        worker_count=1,
        queue_capacity=2,
        autostart=False,
    )
    preflight_ports = _PreflightPorts()
    preflight_ports.run_ids = ["run-fresh"]
    monkeypatch.setattr(server, "_PROJECT_STAGE_EXECUTION_DISPATCHER", dispatcher)
    monkeypatch.setattr(server, "_project_stage_preflight_ports", lambda: preflight_ports)
    monkeypatch.setattr(server, "_project_stage_attempt_ports", lambda: _AttemptPorts())

    result = server._handle_project_execution_project_start("project-1", {"by": "owner"})

    assert result["_status"] == 200
    assert result["currentRunId"] == "run-fresh"
    saved = store.data["projects"][0]
    task = saved["tasks"][0]
    assert saved["status"] == "active"
    assert saved["orchestration"]["state"] == "running"
    assert saved["orchestration"]["currentStage"] == 1
    assert saved["orchestration"]["completedAt"] is None
    assert task["stageRunId"] == "run-fresh"
    assert task["executionState"] == "executing"
    assert task["completedAt"] is None
    assert task["activeAttemptId"] == "attempt-a"
    assert task["reviewResult"] == {}
    assert task["meetingBlocker"] == {}
    assert task["meetingBlockerHistory"][0]["requestId"] == "req-1"
    assert saved["tasks"][1]["stageRunId"] is None
    assert saved["tasks"][1]["executionState"] == "backlog"
    assert dispatcher.diagnostics()["queued"] == 1


def test_marked_project_task_level_start_is_rejected(monkeypatch):
    _install(monkeypatch, _project())

    result = server._handle_project_execution_start("project-1", "a", {})

    assert result["_status"] == 409
    assert result["code"] == "marked_project_task_start_forbidden"


def test_marked_project_start_records_queue_rejection(monkeypatch):
    store = _install(monkeypatch, _project())
    dispatcher = BoundedProjectExecutionDispatcher(
        lambda item: None,
        worker_count=1,
        queue_capacity=1,
        autostart=False,
    )
    monkeypatch.setattr(server, "_PROJECT_STAGE_EXECUTION_DISPATCHER", dispatcher)
    monkeypatch.setattr(server, "_project_stage_preflight_ports", lambda: _PreflightPorts())
    monkeypatch.setattr(server, "_project_stage_attempt_ports", lambda: _AttemptPorts())

    result = server._handle_project_execution_project_start("project-1", {})

    assert result["_status"] == 409
    assert result["code"] == QUEUE_FULL_CODE
    assert result["submittedTaskIds"] == ["a"]
    saved = store.data["projects"][0]
    assert saved["orchestration"]["state"] == "blocked"
    assert saved["orchestration"]["pauseReason"] == QUEUE_FULL_CODE
    by_id = {task["id"]: task for task in saved["tasks"]}
    assert by_id["a"]["activeAttemptId"] == "attempt-a"
    assert by_id["a"]["executionState"] == "executing"
    assert by_id["b"]["activeAttemptId"] is None
    assert by_id["b"]["executionState"] == "blocked"
    assert by_id["b"]["blockedReason"] == QUEUE_FULL_CODE
    assert by_id["c"].get("stageRunId") is None


def test_marked_project_terminal_adapter_reconciles_attempt_stage_run(monkeypatch):
    project = _project()
    project["orchestration"].update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    project["tasks"][0].update({
        "stageRunId": "run-1",
        "executionState": "done",
        "completedAt": "done-at",
        "attempts": [{"id": "attempt-a", "stageRunId": "run-1"}],
    })
    project["tasks"][1].update({
        "stageRunId": "run-1",
        "executionState": "done",
        "completedAt": "done-at",
        "attempts": [{"id": "attempt-b", "stageRunId": "run-1"}],
    })
    store = _install(monkeypatch, project)
    run_ids = iter(["run-2", "run-duplicate"])
    monkeypatch.setattr(server, "_proj_uuid", lambda: next(run_ids))
    monkeypatch.setattr(server, "_proj_now", lambda: "now")

    advanced = server._project_stage_reconcile_terminal("project-1", "a", "attempt-a", "review_passed")
    duplicate = server._project_stage_reconcile_terminal("project-1", "b", "attempt-b", "review_passed")

    assert advanced["_status"] == 200
    assert advanced["status"] == "stage_advanced"
    assert advanced["reason"] == "review_passed"
    assert duplicate["_status"] == 200
    assert duplicate["status"] == "stale_run_ignored"
    saved = store.data["projects"][0]
    assert saved["orchestration"]["state"] == "starting"
    assert saved["orchestration"]["currentStage"] == 2
    assert saved["orchestration"]["currentRunId"] == "run-2"
    assert saved["tasks"][2]["stageRunId"] == "run-2"
