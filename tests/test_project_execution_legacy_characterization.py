#!/usr/bin/env python3
"""Characterization tests for legacy Project Execution progression.

These tests intentionally describe the pre-stage-pipeline contract. They should
be updated or removed only when the stage orchestration implementation replaces
the legacy single/free/manual progression authorities.
"""

import copy
import os
import sys
import threading
from contextlib import contextmanager


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services import execution_lifecycle, project_schedule
from services.project_execution_ordering import first_incomplete_task
from services.project_repository import ProjectRepository


def _project(**overrides):
    project = {
        "id": "p1",
        "title": "Legacy execution project",
        "projectExecutionEnabled": True,
        "projectExecutionStartMode": "continuous",
        "projectExecutionFlowActive": False,
        "projectExecutionFlowStopReason": None,
        "workflowActive": False,
        "workflowPhase": "idle",
        "activeTaskId": None,
        "activeAgent": None,
        "workspacePath": "/workspace",
        "columns": [{"id": "done", "title": "Done"}],
        "tasks": [
            {
                "id": "t1",
                "title": "First",
                "order": 0,
                "executionOrder": 1,
                "executionState": "backlog",
                "attempts": [],
                "executorAgentId": "executor",
                "reviewerAgentId": "reviewer",
                "requiresUserAcceptance": False,
            },
            {
                "id": "t2",
                "title": "Second",
                "order": 1,
                "executionOrder": 2,
                "executionState": "backlog",
                "attempts": [],
                "executorAgentId": "executor",
                "reviewerAgentId": "reviewer",
                "requiresUserAcceptance": False,
            },
        ],
    }
    project.update(overrides)
    return project


def _repository(project=None):
    state = {"projects": [copy.deepcopy(project or _project())], "templates": []}
    lock = threading.Lock()

    def load():
        with lock:
            return copy.deepcopy(state)

    def save(value):
        with lock:
            state.clear()
            state.update(copy.deepcopy(value))

    return state, ProjectRepository(load_projects=load, save_projects=save)


def _active_task(project):
    return next(
        (
            task for task in project.get("tasks", [])
            if task.get("executionState") in {
                "validating",
                "executing",
                "retrying",
                "reviewing",
                "reworking",
                "execution_complete",
                "awaiting_user_acceptance",
            }
        ),
        None,
    )


def _ports(launched):
    def transition(project, task, state, actor, reason, attempt_id):
        task["executionState"] = state
        task.setdefault("stateHistory", []).append(
            {"attemptId": attempt_id, "to": state, "actor": actor, "reason": reason}
        )

    ids = iter(["attempt-1", "attempt-2", "attempt-3"])
    return execution_lifecycle.StartPorts(
        validate_workspace=lambda path: {"ok": True, "path": path, "kind": "git"},
        git_snapshot=lambda path: {"kind": "git", "dirty": False, "fingerprint": "", "files": []},
        resolve_roles=lambda project, task, allow_skip: {
            "ok": True,
            "executor": {"id": task.get("executorAgentId") or "executor", "providerKind": "test"},
            "reviewer": {"id": task.get("reviewerAgentId") or "reviewer", "providerKind": "test"},
        },
        active_task=_active_task,
        start_mode=lambda project, body: str(body.get("mode") or project.get("projectExecutionStartMode") or "continuous"),
        requires_acceptance=lambda task: task.get("requiresUserAcceptance") is True,
        reopen_completed_task=lambda project, task, actor: False,
        clear_restart_bindings=lambda *args: None,
        seed_checklist=lambda task, actor: False,
        has_pending_meeting_actions=lambda task: False,
        transition=transition,
        now=lambda: "now",
        new_id=lambda: next(ids),
        launcher=lambda callback: launched.append(callback),
        runner=lambda *args: None,
        notify_intervention=lambda *args, **kwargs: None,
    )


def _start_task(repository, launched, task_id, body=None):
    return execution_lifecycle.start_task(
        "p1",
        task_id,
        body or {},
        repository=repository,
        cancel_registry=execution_lifecycle.CancelRegistry(),
        ports=_ports(launched),
    )


def test_manual_task_start_is_single_mode_and_sets_singular_active_task():
    _, repository = _repository()
    launched = []

    result = _start_task(repository, launched, "t1")

    assert result["ok"] is True
    assert result["startMode"] == "single"
    current = repository.get("p1")
    first = current["tasks"][0]
    assert current["workflowActive"] is True
    assert current["workflowPhase"] == "executing"
    assert current["activeTaskId"] == "t1"
    assert current["activeAgent"] == "executor"
    assert current["projectExecutionStartMode"] == "continuous"
    assert current["projectExecutionFlowActive"] is False
    assert first["activeAttemptId"] == "attempt-1"
    assert first["attempts"][0]["startMode"] == "single"
    assert first["attempts"][0]["projectFlow"] is False
    assert len(launched) == 1


def test_project_start_continuous_selects_one_execution_order_task_and_blocks_parallel_start():
    _, repository = _repository()
    launched = []

    result = execution_lifecycle.start_project(
        "p1",
        {"mode": "continuous", "by": "user"},
        repository=repository,
        active_task=_active_task,
        all_tasks_repeatable=lambda project: True,
        reset_tasks=lambda project, actor: {"ok": True, "resetTaskCount": 0},
        next_task=first_incomplete_task,
        start_mode=lambda project, body: str(body.get("mode") or project.get("projectExecutionStartMode") or "continuous"),
        start_task_command=lambda project_id, task_id, body: _start_task(repository, launched, task_id, body),
        notify_complete=lambda project, message: None,
        now=lambda: "now",
    )

    assert result["ok"] is True
    assert result["selectedTask"] == {"id": "t1", "title": "First"}
    assert result["startMode"] == "continuous"
    current = repository.get("p1")
    assert current["activeTaskId"] == "t1"
    assert current["projectExecutionStartMode"] == "continuous"
    assert current["projectExecutionFlowActive"] is True
    assert current["tasks"][0]["attempts"][0]["projectFlow"] is True

    parallel = _start_task(repository, launched, "t2")
    assert parallel["_status"] == 409
    assert parallel["activeTaskId"] == "t1"
    assert len(current["tasks"][0]["attempts"]) == 1


def test_execution_order_blocks_later_manual_task_until_prior_task_is_complete():
    _, repository = _repository()
    launched = []

    blocked = _start_task(repository, launched, "t2")

    assert blocked["_status"] == 409
    assert blocked["code"] == "project_execution_order_blocked"
    assert blocked["priorTaskId"] == "t1"
    assert launched == []

    def complete_first(project):
        project["tasks"][0]["executionState"] = "done"
        project["tasks"][0]["completedAt"] = "now"

    repository.update("p1", complete_first)
    started = _start_task(repository, launched, "t2")
    assert started["ok"] is True
    assert repository.get("p1")["activeTaskId"] == "t2"


def test_project_start_after_completion_selects_next_single_task_by_execution_order():
    _, repository = _repository()
    launched = []

    def complete_first(project):
        project["tasks"][0]["executionState"] = "done"
        project["tasks"][0]["completedAt"] = "now"

    repository.update("p1", complete_first)
    result = execution_lifecycle.start_project(
        "p1",
        {"mode": "continuous", "by": "completion-callback"},
        repository=repository,
        active_task=_active_task,
        all_tasks_repeatable=lambda project: True,
        reset_tasks=lambda project, actor: {"ok": True, "resetTaskCount": 0},
        next_task=first_incomplete_task,
        start_mode=lambda project, body: str(body.get("mode") or project.get("projectExecutionStartMode") or "continuous"),
        start_task_command=lambda project_id, task_id, body: _start_task(repository, launched, task_id, body),
        notify_complete=lambda project, message: None,
        now=lambda: "now",
    )

    assert result["ok"] is True
    assert result["selectedTask"] == {"id": "t2", "title": "Second"}
    assert repository.get("p1")["activeTaskId"] == "t2"


def test_status_recovery_marks_non_live_singular_attempt_blocked():
    project = _project(
        workflowActive=True,
        workflowPhase="executing",
        activeTaskId="t1",
        activeAgent="executor",
        projectExecutionFlowActive=True,
    )
    project["tasks"][0].update({
        "executionState": "executing",
        "activeAttemptId": "attempt-lost",
        "attempts": [{"id": "attempt-lost", "status": "executing"}],
    })
    _, repository = _repository(project)

    result = execution_lifecycle.status(
        "p1",
        None,
        repository=repository,
        is_live=lambda attempt_id: False,
        transition_task=lambda project, task, state, actor, reason, attempt_id: task.update({"executionState": state}),
    )

    assert result["ok"] is True
    assert result["active"] is False
    assert result["phase"] == "blocked"
    assert result["currentTaskId"] is None
    assert result["flowActive"] is False
    assert result["flowStopReason"] == "previous_execution_not_resumable"
    recovered = repository.get("p1")
    assert recovered["tasks"][0]["executionState"] == "blocked"
    assert recovered["tasks"][0]["activeAttemptId"] is None
    assert recovered["tasks"][0]["blockedReason"] == "previous_execution_not_resumable"


@contextmanager
def _lock(_key):
    yield


def test_project_cron_dispatch_passes_legacy_start_mode_to_project_start():
    project = _project(projectExecutionStartMode="single")
    binding = {"id": "cron-1", "projectId": "p1", "targetType": "projectWorkflow"}
    calls = []
    histories = []

    ports = project_schedule.DispatchPorts(
        get_binding=lambda cron_id: binding,
        get_project=lambda project_id: copy.deepcopy(project),
        update_binding_status=lambda *args, **kwargs: None,
        append_history=lambda *args, **kwargs: histories.append((args, kwargs)),
        execution_enabled=lambda value: value.get("projectExecutionEnabled") is True,
        active_task=lambda value: None,
        done_column_ids=lambda value: {"done"},
        reopen_task=lambda project_id, task_id: {"ok": True, "reopened": False, "project": project},
        start_task=lambda project_id, task_id, body: {"ok": True, "taskId": task_id},
        start_project=lambda project_id, body: calls.append((project_id, body)) or {"ok": True, "startMode": body.get("mode")},
        start_legacy=lambda project_id, body: {"ok": True, "legacy": True},
        gateway=lambda method, params, timeout: {"ok": True},
        operation_lock=_lock,
        claim_dispatch=lambda cron_id, project_id, occurrence_id=None: {"status": "claimed", "token": "token"},
        renew_dispatch=lambda cron_id, token: True,
        owns_dispatch=lambda cron_id, token: True,
        release_dispatch=lambda cron_id, token, completed: None,
        sanitize_result=lambda result: dict(result or {}),
        monotonic=lambda: 10.0,
        lease_refresh_seconds=1.0,
    )

    result = project_schedule._dispatch_locked("p1", "cron-1", "cron", ports=ports)

    assert result["ok"] is True
    assert result["status"] == "started"
    assert calls == [("p1", {
        "mode": "single",
        "by": "project-cron",
        "source": "cron",
        "skipReviewConfirmed": True,
    })]
