#!/usr/bin/env python3
"""Focused contracts for the extracted execution lifecycle service."""

import copy
import os
import sys
import threading
import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services import execution_lifecycle
from services.project_repository import ProjectRepository


def _repository():
    state = {
        "projects": [{
            "id": "p1", "title": "Project", "projectExecutionEnabled": True,
            "workspacePath": "/workspace", "projectExecutionStartMode": "continuous",
            "columns": [], "activity": [], "tasks": [{
                "id": "t1", "title": "Task", "executionState": "backlog",
                "attempts": [], "requiresUserAcceptance": False,
                "executorAgentId": "executor", "reviewerAgentId": "reviewer",
            }],
        }],
        "templates": [],
    }
    lock = threading.Lock()

    def load():
        with lock:
            return copy.deepcopy(state)

    def save(value):
        with lock:
            state.clear()
            state.update(copy.deepcopy(value))

    return state, ProjectRepository(load_projects=load, save_projects=save)


def _ports(launcher, *, git_snapshot=None):
    def transition(project, task, state, actor, reason, attempt_id):
        task["executionState"] = state
        task["stateHistory"] = [{"attemptId": attempt_id, "to": state}]

    return execution_lifecycle.StartPorts(
        validate_workspace=lambda path: {"ok": True, "path": path, "kind": "git"},
        git_snapshot=git_snapshot or (lambda path: {"kind": "git", "dirty": False, "fingerprint": "", "files": []}),
        resolve_roles=lambda project, task, allow_skip: {
            "ok": True,
            "executor": {"id": "executor", "providerKind": "test"},
            "reviewer": {"id": "reviewer", "providerKind": "test"},
        },
        active_task=lambda project: next((task for task in project["tasks"] if task.get("executionState") in {"executing", "reviewing"}), None),
        start_mode=lambda project, body: body.get("mode") or "continuous",
        requires_acceptance=lambda task: task.get("requiresUserAcceptance") is True,
        reopen_completed_task=lambda project, task, actor: False,
        clear_restart_bindings=lambda *args: None,
        seed_checklist=lambda task, actor: bool(task.setdefault("checklist", [{"id": "seeded", "text": "Complete task", "done": False}])),
        has_pending_meeting_actions=lambda task: False,
        transition=transition,
        now=lambda: "now",
        new_id=lambda: "attempt-1",
        launcher=launcher,
        runner=lambda *args: None,
        notify_intervention=lambda *args, **kwargs: None,
    )


def test_start_persists_attempt_before_launcher_runs():
    _, repository = _repository()
    observed = []

    def launcher(callback):
        observed.append(repository.get("p1"))

    result = execution_lifecycle.start_task(
        "p1", "t1", {}, repository=repository,
        cancel_registry=execution_lifecycle.CancelRegistry(), ports=_ports(launcher),
    )

    assert result == {
        "ok": True, "status": "started", "taskId": "t1", "attemptId": "attempt-1",
        "startMode": "single", "requiresUserAcceptance": False, "reopenedCompletedTask": False,
    }
    assert observed[0]["activeTaskId"] == "t1"
    assert observed[0]["tasks"][0]["activeAttemptId"] == "attempt-1"


def test_concurrent_start_creates_only_one_active_attempt():
    _, repository = _repository()
    barrier = threading.Barrier(2)
    results = []

    def snapshot(path):
        barrier.wait(timeout=2)
        return {"kind": "git", "dirty": False, "fingerprint": "", "files": []}

    def run():
        results.append(execution_lifecycle.start_task(
            "p1", "t1", {}, repository=repository,
            cancel_registry=execution_lifecycle.CancelRegistry(),
            ports=_ports(lambda callback: None, git_snapshot=snapshot),
        ))

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    assert sum(result.get("ok") is True for result in results) == 1
    assert sum(result.get("_status") == 409 for result in results) == 1
    assert len(repository.get("p1")["tasks"][0]["attempts"]) == 1


def test_git_snapshot_error_fails_closed_before_launcher():
    _, repository = _repository()
    launched = []
    result = execution_lifecycle.start_task(
        "p1", "t1", {}, repository=repository,
        cancel_registry=execution_lifecycle.CancelRegistry(),
        ports=_ports(
            lambda callback: launched.append(callback),
            git_snapshot=lambda path: {"kind": "git", "error": "timed out", "dirty": False, "files": []},
        ),
    )

    assert result["_status"] == 409
    assert result["code"] == "workspace_git_snapshot_failed"
    assert launched == []
    assert repository.get("p1")["tasks"][0]["attempts"] == []


def test_non_git_workspace_without_snapshot_remains_startable():
    _, repository = _repository()
    result = execution_lifecycle.start_task(
        "p1", "t1", {}, repository=repository,
        cancel_registry=execution_lifecycle.CancelRegistry(),
        ports=_ports(
            lambda callback: None,
            git_snapshot=lambda path: {"kind": "directory", "dirty": False, "fingerprint": "", "files": []},
        ),
    )
    assert result["ok"] is True


def test_provider_invocation_reads_persisted_attempt_and_rejects_stale_attempt():
    _, repository = _repository()
    launched = []
    execution_lifecycle.start_task(
        "p1", "t1", {}, repository=repository,
        cancel_registry=execution_lifecycle.CancelRegistry(),
        ports=_ports(lambda callback: launched.append(callback)),
    )
    calls = []
    invocation = execution_lifecycle.invoke_provider(
        "p1", "t1", "attempt-1", repository=repository, monotonic=lambda: 12.5,
        build_prompt=lambda project, task, attempt, workspace: "prompt",
        provider=lambda executor, prompt, workspace, attempt_id, **ids: calls.append(
            (executor["id"], prompt, workspace, attempt_id, ids)
        ) or {"ok": True},
    )
    assert invocation is not None
    assert invocation.started_at == 12.5
    assert calls == [("executor", "prompt", "/workspace", "attempt-1", {"project_id": "p1", "task_id": "t1"})]

    repository.update("p1", lambda project: project["tasks"][0].update({"activeAttemptId": "replacement"}))
    assert execution_lifecycle.invoke_provider(
        "p1", "t1", "attempt-1", repository=repository, monotonic=lambda: 0,
        build_prompt=lambda *args: "unused", provider=lambda *args, **kwargs: calls.append("unexpected"),
    ) is None
    assert "unexpected" not in calls


def test_attempt_compare_token_allows_only_the_active_attempt():
    task = {"activeAttemptId": "a1", "attempts": [{"id": "a1", "status": "executing"}]}
    assert execution_lifecycle.attempt_is_committable(task, "a1") is True
    task["activeAttemptId"] = None
    assert execution_lifecycle.attempt_is_committable(task, "a1") is False
    task["attempts"][0]["status"] = "cancelling"
    assert execution_lifecycle.attempt_is_committable(task, "a1") is False


def test_runner_discards_cancel_flag_when_provider_raises():
    _, repository = _repository()
    registry = execution_lifecycle.CancelRegistry()
    execution_lifecycle.start_task(
        "p1", "t1", {}, repository=repository, cancel_registry=registry,
        ports=_ports(lambda callback: None),
    )
    flag = registry.get("attempt-1")
    ports = type("Ports", (), {
        "repository": repository,
        "build_prompt": staticmethod(lambda *args: "prompt"),
        "provider": staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider failed"))),
        "cancel_registry": registry,
    })()
    with pytest.raises(RuntimeError, match="provider failed"):
        execution_lifecycle.run_attempt("p1", "t1", "attempt-1", flag, ports=ports)
    assert registry.get("attempt-1") is None


def test_lifecycle_module_has_no_server_or_http_dependency():
    path = os.path.join(APP_DIR, "services", "execution_lifecycle.py")
    source = open(path, encoding="utf-8").read()
    assert "import server" not in source
    assert "OfficeHandler" not in source
    assert "http.server" not in source


def test_server_lifecycle_entrypoints_are_thin_service_delegates():
    import ast

    source = open(os.path.join(APP_DIR, "server.py"), encoding="utf-8").read()
    tree = ast.parse(source)
    functions = {
        node.name: ast.get_source_segment(source, node)
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }
    assert "execution_lifecycle_service.start_task(" in functions["_handle_project_execution_start"]
    assert "execution_lifecycle_service.start_project(" in functions["_handle_project_execution_project_start"]
    assert "execution_lifecycle_service.status(" in functions["_handle_project_execution_status"]
    assert "execution_lifecycle_service.cancel(" in functions["_handle_project_execution_cancel"]
    assert "execution_lifecycle_service.run_attempt(" in functions["_project_execution_run_attempt"]
