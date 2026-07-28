#!/usr/bin/env python3
"""HTTP contract tests for project orchestration auto-save."""

from __future__ import annotations

import copy
import io
import json
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
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-orchestration-http-import-"))

import server
from project_store import MarkdownProjectStore
from services.project_orchestration import (
    EXECUTION_MODEL_STAGE_PIPELINE_V1,
    default_orchestration_state,
    default_skip_state,
)
from services.project_repository import ProjectRepository


class _Connection:
    def settimeout(self, timeout):
        self.timeout = timeout


class _MemoryStore:
    def __init__(self, project, *, fail_save=False):
        self.data = {"projects": [copy.deepcopy(project)], "templates": []}
        self.fail_save = fail_save
        self.save_calls = 0

    def load(self):
        return copy.deepcopy(self.data)

    def save(self, value):
        if self.fail_save:
            raise OSError("simulated save failure")
        self.save_calls += 1
        self.data = copy.deepcopy(value)


def _task(task_id, stage, **overrides):
    task = {
        "id": task_id,
        "title": task_id,
        "executionStage": stage,
        "stageRunId": None,
        "orchestrationSkip": default_skip_state(),
        "executionState": "backlog",
    }
    task.update(overrides)
    return task


def _project(*, revision=0):
    return {
        "id": "project-1",
        "title": "Project",
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": {
            **default_orchestration_state(),
            "revision": revision,
        },
        "tasks": [_task("a", 1), _task("b", 2)],
    }


def _handler(body, *, authorized=True):
    payload = json.dumps(body).encode("utf-8")
    handler = object.__new__(server.OfficeHandler)
    handler.path = "/api/projects/project-1/orchestration"
    handler.headers = {"Content-Length": str(len(payload))}
    if authorized:
        handler.headers["X-VO-Management-Token"] = server._MANAGEMENT_TOKEN
    handler.rfile = io.BytesIO(payload)
    handler.wfile = io.BytesIO()
    handler.connection = _Connection()
    handler.client_address = ("127.0.0.1", 12345)
    handler.responses = []
    handler.response_headers = []
    handler.send_response = lambda status, *args, **kwargs: handler.responses.append(status)
    handler.send_header = lambda name, value: handler.response_headers.append((name, value))
    handler.end_headers = lambda: None
    return handler


def _post_handler(path, body, *, management=False, agent_id=None, origin="", remote="127.0.0.1"):
    payload = json.dumps(body).encode("utf-8")
    handler = object.__new__(server.OfficeHandler)
    handler.path = path
    handler.headers = {"Content-Length": str(len(payload))}
    if management:
        handler.headers["X-VO-Management-Token"] = server._MANAGEMENT_TOKEN
    if agent_id is not None:
        handler.headers["X-VO-Agent-Action"] = "project-execution"
        handler.headers["X-VO-Agent-Id"] = agent_id
    if origin:
        handler.headers["Origin"] = origin
    handler.rfile = io.BytesIO(payload)
    handler.wfile = io.BytesIO()
    handler.connection = _Connection()
    handler.client_address = (remote, 12345)
    handler.responses = []
    handler.response_headers = []
    handler.send_response = lambda status, *args, **kwargs: handler.responses.append(status)
    handler.send_header = lambda name, value: handler.response_headers.append((name, value))
    handler.end_headers = lambda: None
    return handler


def _get_handler(path):
    handler = object.__new__(server.OfficeHandler)
    handler.path = path
    handler.headers = {}
    handler.rfile = io.BytesIO()
    handler.wfile = io.BytesIO()
    handler.connection = _Connection()
    handler.client_address = ("127.0.0.1", 12345)
    handler.responses = []
    handler.response_headers = []
    handler.send_response = lambda status, *args, **kwargs: handler.responses.append(status)
    handler.send_header = lambda name, value: handler.response_headers.append((name, value))
    handler.end_headers = lambda: None
    return handler


def _call(handler):
    handler.do_PUT()
    raw = handler.wfile.getvalue()
    return handler.responses[-1], json.loads(raw) if raw else {}


def _call_post(handler):
    handler.do_POST()
    raw = handler.wfile.getvalue()
    return handler.responses[-1], json.loads(raw) if raw else {}


def _call_get(handler):
    handler.do_GET()
    raw = handler.wfile.getvalue()
    return handler.responses[-1], json.loads(raw) if raw else {}


def _install_repo(monkeypatch, project, *, fail_save=False):
    store = _MemoryStore(project, fail_save=fail_save)
    repo = ProjectRepository(load_projects=store.load, save_projects=store.save)
    monkeypatch.setattr(server, "_PROJECT_REPOSITORY", repo)
    monkeypatch.setattr(server, "_proj_now", lambda: "saved")
    return store


def _install_markdown_repo(monkeypatch, tmp_path, project):
    store = MarkdownProjectStore(str(tmp_path))
    store.save_all({"projects": [project], "templates": []})
    reloaded_store = MarkdownProjectStore(str(tmp_path))
    repo = ProjectRepository(load_projects=reloaded_store.load_all, save_projects=reloaded_store.save_all)
    monkeypatch.setattr(server, "_PROJECT_REPOSITORY", repo)
    return reloaded_store


def _legacy_polluted_marked_project():
    project = _project()
    project.update({
        "status": "active",
        "orchestration": {
            **project["orchestration"],
            "state": "running",
            "currentStage": 1,
            "currentRunId": "run-1",
            "pauseReason": None,
        },
        "projectExecutionStartMode": "single",
        "projectExecutionFlowActive": True,
        "projectExecutionFlowStopReason": "legacy_stop",
        "executionPolicy": {"maxActiveTasks": 1},
        "workflowActive": True,
        "workflowPhase": "executing",
        "activeTaskId": "a",
        "activeAgent": "legacy-agent",
        "autoMode": True,
    })
    project["tasks"][0].update({
        "executionOrder": 1,
        "stageRunId": "run-1",
        "executionState": "executing",
        "activeAttemptId": "attempt-a",
        "attempts": [{"id": "attempt-a", "stageRunId": "run-1", "state": "executing"}],
    })
    project["tasks"][1].update({
        "executionOrder": 2,
        "stageRunId": "run-1",
        "executionState": "reviewing",
        "activeAttemptId": "attempt-b",
        "attempts": [{"id": "attempt-b", "stageRunId": "run-1", "state": "reviewing"}],
    })
    return project


def _assert_marked_project_contract(project):
    assert project["executionModel"] == EXECUTION_MODEL_STAGE_PIPELINE_V1
    assert project["activeTaskIds"] == ["a", "b"]
    assert project["activeTaskCount"] == 2
    assert project["currentStage"] == 1
    assert project["orchestrationState"] == "running"
    for legacy in (
        "projectExecutionStartMode",
        "projectExecutionFlowActive",
        "projectExecutionFlowStopReason",
        "executionPolicy",
        "workflowActive",
        "workflowPhase",
        "activeTaskId",
        "activeAgent",
        "autoMode",
    ):
        assert legacy not in project


def test_marked_project_routes_survive_markdown_reload_without_legacy_authorities(monkeypatch, tmp_path):
    _install_markdown_repo(monkeypatch, tmp_path, _legacy_polluted_marked_project())

    detail_status, detail_payload = _call_get(_get_handler("/api/projects/project-1"))

    assert detail_status == 200
    assert detail_payload["ok"] is True
    detail_project = detail_payload["project"]
    _assert_marked_project_contract(detail_project)
    tasks_by_id = {task["id"]: task for task in detail_project["tasks"]}
    assert tasks_by_id["a"]["executionStage"] == 1
    assert tasks_by_id["b"]["executionStage"] == 2
    assert "executionOrder" not in tasks_by_id["a"]
    assert "executionOrder" not in tasks_by_id["b"]

    list_status, list_payload = _call_get(_get_handler("/api/projects?status=active"))

    assert list_status == 200
    assert list_payload["ok"] is True
    summary = list_payload["projects"][0]
    assert summary["id"] == "project-1"
    assert summary["activeTaskIds"] == ["a", "b"]
    assert summary["activeTaskCount"] == 2
    assert summary["currentStage"] == 1
    assert summary["orchestrationState"] == "running"
    assert summary["projectExecutionActive"] is True
    for legacy in (
        "projectExecutionStartMode",
        "projectExecutionFlowActive",
        "projectExecutionFlowStopReason",
        "executionPolicy",
        "workflowActive",
        "workflowPhase",
        "activeTaskId",
        "activeAgent",
        "autoMode",
    ):
        assert legacy not in summary


def test_marked_project_start_route_rejects_legacy_payload_contract(monkeypatch):
    _install_repo(monkeypatch, _project())

    status, payload = _call_post(_post_handler(
        "/api/projects/project-1/project-execution/start",
        {"mode": "single", "startMode": "continuous", "restartPipeline": True},
        management=True,
    ))

    assert status == 400
    assert payload["code"] == "marked_project_legacy_start_payload_forbidden"
    assert payload["fields"] == ["mode", "startMode", "restartPipeline"]


def test_orchestration_put_requires_management_token_before_dispatch(monkeypatch):
    store = _install_repo(monkeypatch, _project())

    status, payload = _call(_handler({"revision": 0, "assignments": []}, authorized=False))

    assert status == 403
    assert payload["code"] == "management_token_required"
    assert store.data["projects"][0]["orchestration"]["revision"] == 0
    assert store.save_calls == 0


def test_orchestration_put_persists_assignment_and_returns_stable_success(monkeypatch):
    store = _install_repo(monkeypatch, _project())

    status, payload = _call(_handler({
        "revision": 0,
        "assignments": [
            {"taskId": "a", "executionStage": 2},
            {"taskId": "b", "executionStage": 1},
        ],
    }))

    assert status == 200
    assert payload["ok"] is True
    assert payload["orchestration"]["revision"] == 1
    assert payload["assignments"] == [
        {"taskId": "a", "executionStage": 2},
        {"taskId": "b", "executionStage": 1},
    ]
    assert store.save_calls == 1
    assert [(task["id"], task["executionStage"]) for task in store.data["projects"][0]["tasks"]] == [
        ("a", 2),
        ("b", 1),
    ]


def test_orchestration_put_returns_validation_errors_without_persisting(monkeypatch):
    project = _project()
    store = _install_repo(monkeypatch, project)

    status, payload = _call(_handler({
        "revision": 0,
        "assignments": [{"taskId": "a", "executionStage": 1}],
    }))

    assert status == 400
    assert payload["code"] == "incomplete_orchestration_assignment"
    assert store.data["projects"][0] == project
    assert store.save_calls == 0


def test_orchestration_put_returns_stale_revision_conflict_with_authoritative_state(monkeypatch):
    project = _project(revision=3)
    store = _install_repo(monkeypatch, project)

    status, payload = _call(_handler({
        "revision": 2,
        "assignments": [
            {"taskId": "a", "executionStage": 1},
            {"taskId": "b", "executionStage": 1},
        ],
    }))

    assert status == 409
    assert payload["code"] == "orchestration_revision_conflict"
    assert payload["currentRevision"] == 3
    assert payload["assignments"] == [
        {"taskId": "a", "executionStage": 1},
        {"taskId": "b", "executionStage": 2},
    ]
    assert store.data["projects"][0] == project
    assert store.save_calls == 0


def test_orchestration_put_maps_persistence_failure(monkeypatch):
    project = _project()
    store = _install_repo(monkeypatch, project, fail_save=True)

    status, payload = _call(_handler({
        "revision": 0,
        "assignments": [
            {"taskId": "a", "executionStage": 1},
            {"taskId": "b", "executionStage": 1},
        ],
    }))

    assert status == 500
    assert payload["code"] == "orchestration_persistence_failed"
    assert store.data["projects"][0] == project
    assert store.save_calls == 0


def test_agent_skip_request_uses_header_actor_and_url_task_not_forged_body(monkeypatch):
    project = _project()
    project["tasks"][0].update({"executorAgentId": "owner-a", "responsibleActor": {"type": "agent", "id": "owner-a"}})
    project["tasks"][1].update({"executorAgentId": "owner-b", "responsibleActor": {"type": "agent", "id": "owner-b"}})
    store = _install_repo(monkeypatch, project)
    monkeypatch.setattr(server, "_office_agent_lookup", lambda agent_id: {"id": agent_id} if agent_id == "owner-a" else None)

    status, payload = _call_post(_post_handler(
        "/api/agent/projects/project-1/tasks/a/orchestration/skip-request",
        {
            "projectId": "other-project",
            "taskId": "b",
            "actor": {"type": "management", "id": "forged"},
            "reason": "blocked on external dependency",
        },
        agent_id="owner-a",
    ))

    assert status == 200
    assert payload["status"] == "skip_requested"
    saved = store.data["projects"][0]
    assert saved["tasks"][0]["orchestrationSkip"]["requestedBy"] == {"type": "agent", "id": "owner-a"}
    assert saved["tasks"][0]["orchestrationSkip"]["reason"] == "blocked on external dependency"
    assert saved["tasks"][1]["orchestrationSkip"]["status"] == "none"


def test_agent_skip_request_rejects_cross_task_owner_forgery(monkeypatch):
    project = _project()
    project["tasks"][0].update({"executorAgentId": "owner-a", "responsibleActor": {"type": "agent", "id": "owner-a"}})
    project["tasks"][1].update({"executorAgentId": "owner-b", "responsibleActor": {"type": "agent", "id": "owner-b"}})
    store = _install_repo(monkeypatch, project)
    monkeypatch.setattr(server, "_office_agent_lookup", lambda agent_id: {"id": agent_id} if agent_id == "owner-a" else None)

    status, payload = _call_post(_post_handler(
        "/api/agent/projects/project-1/tasks/b/orchestration/skip-request",
        {"reason": "try to skip another task"},
        agent_id="owner-a",
    ))

    assert status == 403
    assert payload["code"] == "skip_request_forbidden"
    assert store.save_calls == 0


def test_skip_decision_requires_management_token_before_mutation(monkeypatch):
    project = _project()
    project["tasks"][0]["orchestrationSkip"] = {
        **default_skip_state(),
        "status": "requested",
        "requestedBy": {"type": "agent", "id": "owner-a"},
        "requestedAt": "earlier",
        "reason": "blocked",
    }
    store = _install_repo(monkeypatch, project)

    status, payload = _call_post(_post_handler(
        "/api/projects/project-1/tasks/a/orchestration/skip-decision",
        {"decision": "approve"},
    ))

    assert status == 403
    assert payload["code"] == "management_token_required"
    assert store.save_calls == 0


def test_management_skip_approval_overrides_forged_actor_and_reconciles_completion_race(monkeypatch):
    project = _project()
    project["orchestration"].update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    project["tasks"][0].update({
        "stageRunId": "run-1",
        "executionState": "done",
        "completedAt": "done-at",
        "orchestrationSkip": {
            **default_skip_state(),
            "status": "requested",
            "requestedBy": {"type": "agent", "id": "owner-a"},
            "requestedAt": "earlier",
            "reason": "blocked",
        },
    })
    project["tasks"][1].update({"stageRunId": "run-1", "executionState": "done", "completedAt": "done-at"})
    store = _install_repo(monkeypatch, project)
    monkeypatch.setattr(server, "_proj_uuid", lambda: "run-2")

    status, payload = _call_post(_post_handler(
        "/api/projects/project-1/tasks/a/orchestration/skip-decision",
        {"decision": "approve", "actor": {"type": "agent", "id": "forged"}, "by": "manager", "reason": "race resolved"},
        management=True,
    ))

    assert status == 200
    assert payload["status"] == "skip_approved"
    assert payload["reconciliation"]["status"] == "stage_advanced"
    saved = store.data["projects"][0]
    assert saved["tasks"][0]["orchestrationSkip"]["decidedBy"] == {"type": "management", "id": "manager"}
    assert saved["orchestration"]["currentStage"] == 2
    assert saved["orchestration"]["currentRunId"] == "run-2"


def test_management_skip_rejection_is_idempotent_and_does_not_reconcile(monkeypatch):
    project = _project()
    project["tasks"][0]["orchestrationSkip"] = {
        **default_skip_state(),
        "status": "rejected",
        "requestedBy": {"type": "agent", "id": "owner-a"},
        "requestedAt": "earlier",
        "reason": "blocked",
        "decidedBy": {"type": "management", "id": "manager"},
        "decidedAt": "already",
    }
    store = _install_repo(monkeypatch, project)

    status, payload = _call_post(_post_handler(
        "/api/projects/project-1/tasks/a/orchestration/skip-decision",
        {"decision": "reject", "by": "manager"},
        management=True,
    ))

    assert status == 200
    assert payload["status"] == "skip_rejected"
    assert payload["idempotent"] is True
    assert payload["reconciliation"] is None
    assert store.data["projects"][0]["tasks"][0]["orchestrationSkip"]["decidedAt"] == "already"


def test_management_skip_approval_is_idempotent_at_api_boundary(monkeypatch):
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
    project["tasks"][1].update({"executionStage": 1, "stageRunId": "run-1", "executionState": "pending"})
    store = _install_repo(monkeypatch, project)

    status, payload = _call_post(_post_handler(
        "/api/projects/project-1/tasks/a/orchestration/skip-decision",
        {"decision": "approve", "by": "manager"},
        management=True,
    ))

    assert status == 200
    assert payload["status"] == "skip_approved"
    assert payload["idempotent"] is True
    assert payload["reconciliation"]["status"] == "stage_waiting"
    assert store.data["projects"][0]["tasks"][0]["orchestrationSkip"]["decidedAt"] == "already"


def test_pause_requires_management_token_before_mutation(monkeypatch):
    project = _project()
    project["orchestration"].update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    store = _install_repo(monkeypatch, project)

    status, payload = _call_post(_post_handler(
        "/api/projects/project-1/orchestration/pause",
        {"confirm": True},
    ))

    assert status == 403
    assert payload["code"] == "management_token_required"
    assert store.save_calls == 0
    assert store.data["projects"][0]["orchestration"]["state"] == "running"


def test_pause_route_cancels_active_attempts_and_enters_paused(monkeypatch):
    project = _project()
    project["orchestration"].update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    project["tasks"][0].update({
        "stageRunId": "run-1",
        "executionState": "executing",
        "activeAttemptId": "attempt-a",
        "attempts": [{"id": "attempt-a", "status": "executing", "stageRunId": "run-1", "executor": {"providerKind": "codex"}}],
    })
    store = _install_repo(monkeypatch, project)
    cancellations = []
    monkeypatch.setattr(server, "_project_execution_cancel_provider", lambda attempt, project_id, task_id, attempt_id: cancellations.append((project_id, task_id, attempt_id)))

    status, payload = _call_post(_post_handler(
        "/api/projects/project-1/orchestration/pause",
        {"confirm": True, "by": "manager", "reason": "rebalance"},
        management=True,
    ))

    assert status == 200
    assert payload["status"] == "paused"
    assert payload["idempotent"] is False
    assert cancellations == [("project-1", "a", "attempt-a")]
    saved = store.data["projects"][0]
    assert saved["orchestration"]["state"] == "paused"
    assert saved["orchestration"]["currentRunId"] is None
    assert saved["orchestration"]["pauseSnapshot"]["activeAttemptIds"] == ["attempt-a"]
    assert saved["tasks"][0]["executionState"] == "pending"
    assert saved["tasks"][0]["activeAttemptId"] is None
    assert saved["tasks"][0]["stageRunId"] is None
    assert saved["tasks"][0]["attempts"][0]["status"] == "cancelled"


def test_pause_route_failure_keeps_project_pausing_for_retry(monkeypatch):
    project = _project()
    project["orchestration"].update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    project["tasks"][0].update({
        "stageRunId": "run-1",
        "executionState": "executing",
        "activeAttemptId": "attempt-a",
        "attempts": [{"id": "attempt-a", "status": "executing", "stageRunId": "run-1"}],
    })
    store = _install_repo(monkeypatch, project)

    def fail_cancel(_attempt, _project_id, _task_id, _attempt_id):
        raise RuntimeError("provider refused")

    monkeypatch.setattr(server, "_project_execution_cancel_provider", fail_cancel)

    status, payload = _call_post(_post_handler(
        "/api/projects/project-1/orchestration/pause",
        {"confirm": True, "by": "manager", "reason": "rebalance"},
        management=True,
    ))

    assert status == 409
    assert payload["code"] == "pause_cancellation_failed"
    saved = store.data["projects"][0]
    assert saved["orchestration"]["state"] == "pausing"
    assert saved["tasks"][0]["activeAttemptId"] == "attempt-a"
    assert saved["tasks"][0]["attempts"][0]["status"] == "executing"


def test_pause_route_is_idempotent_after_project_is_paused(monkeypatch):
    project = _project()
    project["orchestration"].update({
        "state": "paused",
        "currentStage": 1,
        "currentRunId": None,
        "pauseSnapshot": {"activeAttemptIds": [], "activeAttempts": [], "cancelResults": []},
    })
    store = _install_repo(monkeypatch, project)

    status, payload = _call_post(_post_handler(
        "/api/projects/project-1/orchestration/pause",
        {"confirm": True, "by": "manager"},
        management=True,
    ))

    assert status == 200
    assert payload["status"] == "paused"
    assert payload["idempotent"] is True
    assert store.save_calls == 0


def test_resume_route_requires_management_and_starts_paused_project(monkeypatch):
    project = _project()
    project["projectExecutionEnabled"] = True
    project["workspacePath"] = "/work/project"
    project["orchestration"].update({"state": "paused", "currentStage": 1, "currentRunId": None, "revision": 4})
    project["tasks"][0].update({"executionState": "done", "completedAt": "done-at", "stageRunId": "old-run"})
    project["tasks"][1].update({
        "executionState": "pending",
        "stageRunId": None,
        "attempts": [{"id": "old-attempt", "status": "cancelled", "stageRunId": "old-run"}],
    })
    store = _install_repo(monkeypatch, project)
    dispatcher = server.project_stage_dispatch_service.BoundedProjectExecutionDispatcher(lambda item: item.task_id, autostart=False)
    monkeypatch.setattr(server, "_PROJECT_STAGE_EXECUTION_DISPATCHER", dispatcher)
    ids = iter(["run-resume", "attempt-resume"])
    monkeypatch.setattr(server, "_proj_uuid", lambda: next(ids))
    monkeypatch.setattr(server, "_project_execution_validate_workspace", lambda path: {"ok": True, "path": path, "kind": "local"})
    monkeypatch.setattr(server, "_project_execution_git_snapshot", lambda path: {"ok": True, "dirty": False, "files": []})
    monkeypatch.setattr(server, "_project_execution_resolve_start_roles", lambda project, task, allow_skip_reviewer=False: {"ok": True, "executor": {"id": "executor"}, "reviewer": {"id": "reviewer"}})
    monkeypatch.setattr(server, "_project_execution_seed_acceptance_checklist", lambda task, actor: True)

    forbidden_status, forbidden_payload = _call_post(_post_handler(
        "/api/projects/project-1/orchestration/resume",
        {"revision": 4},
    ))
    assert forbidden_status == 403
    assert forbidden_payload["code"] == "management_token_required"

    status, payload = _call_post(_post_handler(
        "/api/projects/project-1/orchestration/resume",
        {"revision": 4, "stage": 99, "by": "manager"},
        management=True,
    ))

    assert status == 200
    assert payload["status"] == "stage_started"
    assert payload["currentStage"] == 2
    assert payload["currentRunId"] == "run-resume"
    assert payload["taskIds"] == ["b"]
    saved = store.data["projects"][0]
    assert saved["orchestration"]["state"] == "running"
    assert saved["orchestration"]["currentStage"] == 2
    assert saved["tasks"][0]["stageRunId"] == "old-run"
    assert saved["tasks"][1]["stageRunId"] == "run-resume"
    assert saved["tasks"][1]["activeAttemptId"] == "attempt-resume"
    assert [attempt["id"] for attempt in saved["tasks"][1]["attempts"]] == ["old-attempt", "attempt-resume"]


def test_resume_route_rejects_forbidden_transition_without_mutation(monkeypatch):
    project = _project()
    project["orchestration"].update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    store = _install_repo(monkeypatch, project)

    status, payload = _call_post(_post_handler(
        "/api/projects/project-1/orchestration/resume",
        {"revision": 0, "by": "manager"},
        management=True,
    ))

    assert status == 409
    assert payload["code"] == "orchestration_not_resumable"
    assert store.save_calls == 0
