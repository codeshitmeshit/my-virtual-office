#!/usr/bin/env python3
"""Tests for orchestration skip request and decision commands."""

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

os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-orchestration-skip-test-"))

from services.project_orchestration import EXECUTION_MODEL_STAGE_PIPELINE_V1, default_orchestration_state, default_skip_state
from services.project_orchestration_skip import SkipPorts, decide_task_skip, request_task_skip
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


class _Ports:
    def __init__(self, *, authorized=True):
        self.run_ids = ["run-2"]
        self.authorized = authorized
        self.auth_calls = []
        self.on_project_completed = None

    def now(self):
        return "now"

    def management_authorize(self, project, actor):
        self.auth_calls.append((project.get("id"), dict(actor)))
        if not self.authorized:
            return {"ok": False, "code": "management_token_required", "error": "manager required"}
        return {"ok": True}

    def new_run_id(self):
        return self.run_ids.pop(0)


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
        "executorAgentId": "owner-a",
        "reviewerAgentId": "reviewer",
    }
    task.update(overrides)
    return task


def _project(**overrides):
    project = {
        "id": "project-1",
        "title": "Project",
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": default_orchestration_state(),
        "projectExecutionEnabled": True,
        "tasks": [_task("a", 1), _task("b", 1), _task("c", 2)],
    }
    project.update(overrides)
    return project


def _repo(project):
    store = _MemoryStore(project)
    return store, ProjectRepository(load_projects=store.load, save_projects=store.save)


def test_task_responsible_actor_can_request_skip_with_audit_history():
    store, repo = _repo(_project())

    outcome = request_task_skip(
        "project-1",
        "a",
        {"actor": {"type": "agent", "id": "owner-a"}, "reason": "provider unavailable"},
        repository=repo,
        ports=_Ports(),
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["status"] == "skip_requested"
    saved = store.data["projects"][0]["tasks"][0]
    assert saved["orchestrationSkip"]["status"] == "requested"
    assert saved["orchestrationSkip"]["reason"] == "provider unavailable"
    assert saved["orchestrationSkip"]["requestedBy"] == {"type": "agent", "id": "owner-a"}
    assert saved["orchestrationSkipHistory"][-1]["action"] == "requested"
    assert saved.get("reviewResult") is None


def test_skip_request_rejects_non_responsible_actor_and_review_skipped_is_not_terminal_skip():
    project = _project()
    project["tasks"][0]["reviewResult"] = {"status": "skipped"}
    store, repo = _repo(project)

    outcome = request_task_skip(
        "project-1",
        "a",
        {"actor": {"type": "agent", "id": "other"}, "reason": "please skip"},
        repository=repo,
        ports=_Ports(),
    )

    assert outcome.result.status == 403
    assert outcome.result.payload["code"] == "skip_request_forbidden"
    assert store.save_calls == 0
    assert store.data["projects"][0]["tasks"][0]["orchestrationSkip"]["status"] == "none"
    assert store.data["projects"][0]["tasks"][0]["reviewResult"]["status"] == "skipped"


def test_management_approval_marks_skip_accepted_terminal_and_reconciles_current_run():
    project = _project()
    project["orchestration"].update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    project["tasks"][0].update({
        "stageRunId": "run-1",
        "orchestrationSkip": {
            **default_skip_state(),
            "status": "requested",
            "requestedBy": {"type": "agent", "id": "owner-a"},
            "requestedAt": "earlier",
            "reason": "blocked",
        },
    })
    project["tasks"][1].update({"stageRunId": "run-1", "executionState": "done", "completedAt": "done-at"})
    store, repo = _repo(project)

    outcome = decide_task_skip(
        "project-1",
        "a",
        {"decision": "approve", "actor": {"type": "management", "id": "manager"}, "reason": "acceptable"},
        repository=repo,
        ports=_Ports(),
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["status"] == "skip_approved"
    assert outcome.result.payload["reconciliation"]["status"] == "stage_advanced"
    saved = store.data["projects"][0]
    assert saved["tasks"][0]["orchestrationSkip"]["status"] == "approved"
    assert saved["tasks"][0]["orchestrationSkip"]["decisionReason"] == "acceptable"
    assert saved["tasks"][0]["finalResult"]["status"] == "skipped"
    assert saved["tasks"][0]["finalResult"]["skipReason"] == "acceptable"
    assert saved["orchestration"]["stageHandoffs"]["1"]["tasks"][0]["status"] == "skipped"
    assert saved["orchestration"]["currentStage"] == 2
    assert saved["orchestration"]["currentRunId"] == "run-2"
    assert saved["tasks"][2]["stageRunId"] == "run-2"


def test_skip_rejection_is_audited_and_does_not_reconcile():
    project = _project()
    project["orchestration"].update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    project["tasks"][0]["orchestrationSkip"] = {
        **default_skip_state(),
        "status": "requested",
        "requestedBy": {"type": "agent", "id": "owner-a"},
        "requestedAt": "earlier",
        "reason": "blocked",
    }
    store, repo = _repo(project)

    outcome = decide_task_skip(
        "project-1",
        "a",
        {"decision": "reject", "actor": {"type": "management", "id": "manager"}, "reason": "must finish"},
        repository=repo,
        ports=_Ports(),
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["status"] == "skip_rejected"
    assert outcome.result.payload["reconciliation"] is None
    saved = store.data["projects"][0]["tasks"][0]
    assert saved["orchestrationSkip"]["status"] == "rejected"
    assert saved["orchestrationSkipHistory"][-1]["action"] == "rejected"


def test_skip_decision_requires_management_authority_and_pending_request():
    project = _project()
    project["tasks"][0]["orchestrationSkip"] = {
        **default_skip_state(),
        "status": "requested",
        "requestedBy": {"type": "agent", "id": "owner-a"},
        "requestedAt": "earlier",
        "reason": "blocked",
    }
    store, repo = _repo(project)

    forbidden = decide_task_skip(
        "project-1",
        "a",
        {"decision": "approve", "actor": {"type": "agent", "id": "owner-a"}},
        repository=repo,
        ports=_Ports(authorized=False),
    )

    assert forbidden.result.status == 403
    assert forbidden.result.payload["code"] == "management_token_required"
    assert store.save_calls == 0

    project["tasks"][0]["orchestrationSkip"] = default_skip_state()
    store, repo = _repo(project)
    missing = decide_task_skip(
        "project-1",
        "a",
        {"decision": "approve", "actor": {"type": "management", "id": "manager"}},
        repository=repo,
        ports=_Ports(),
    )

    assert missing.result.status == 409
    assert missing.result.payload["code"] == "skip_request_not_pending"


def test_approved_skip_decision_is_idempotent_without_second_reconcile():
    project = _project()
    project["orchestration"].update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    project["tasks"][0].update({
        "stageRunId": "run-1",
        "orchestrationSkip": {
            **default_skip_state(),
            "status": "approved",
            "requestedBy": {"type": "agent", "id": "owner-a"},
            "requestedAt": "earlier",
            "reason": "blocked",
            "decidedBy": {"type": "management", "id": "manager"},
            "decidedAt": "already",
        },
    })
    store, repo = _repo(project)

    outcome = decide_task_skip(
        "project-1",
        "a",
        {"decision": "approve", "actor": {"type": "management", "id": "manager"}},
        repository=repo,
        ports=_Ports(),
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["idempotent"] is True
    assert outcome.result.payload["reconciliation"]["status"] == "stage_waiting"
    assert store.data["projects"][0]["tasks"][0]["orchestrationSkip"]["decidedAt"] == "already"


def test_skip_approval_final_stage_completes_project_and_notifies():
    project = _project(tasks=[
        _task("a", 1, stageRunId="run-1", orchestrationSkip={
            **default_skip_state(),
            "status": "requested",
            "requestedBy": {"type": "agent", "id": "owner-a"},
            "requestedAt": "earlier",
            "reason": "blocked",
        }),
        _task("b", 1, stageRunId="run-1", executionState="done", completedAt="done-at"),
    ])
    project["orchestration"].update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    store, repo = _repo(project)
    notifications = []

    ports = _Ports()

    def notify(completed_project, reason):
        notifications.append((completed_project["id"], completed_project["status"], reason))
        completed_project.setdefault("feishuNotifications", {})["complete"] = {"ok": True}
        return {"ok": True, "status": "sent"}

    ports.on_project_completed = notify

    outcome = decide_task_skip(
        "project-1",
        "a",
        {"decision": "approve", "actor": {"type": "management", "id": "manager"}},
        repository=repo,
        ports=ports,
    )

    assert outcome.result.status == 200
    assert outcome.result.payload["reconciliation"]["status"] == "project_completed"
    assert notifications == [(
        "project-1",
        "completed",
        "Project pipeline completed after the final stage reached accepted terminal outcomes.",
    )]
    saved = store.data["projects"][0]
    assert saved["status"] == "completed"
    assert saved["feishuNotifications"]["complete"]["ok"] is True
