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
from services.project_orchestration import EXECUTION_MODEL_STAGE_PIPELINE_V1, default_orchestration_state
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


def test_runner_plans_checklist_before_executing_empty_checklist_attempt():
    state, repository = _repository()
    project = state["projects"][0]
    project.update({"columns": [{"id": "done", "order": 1}], "workflowActive": True, "activeTaskId": "t1"})
    task = project["tasks"][0]
    task.update({
        "executionState": "executing",
        "activeAttemptId": "attempt-1",
        "checklist": [],
        "attempts": [{
            "id": "attempt-1",
            "status": "executing",
            "workspacePath": "/workspace",
            "executor": {"id": "executor", "providerKind": "test"},
            "skipReview": True,
            "requiresUserAcceptance": False,
            "autoReviewAfterExecution": False,
            "projectFlow": False,
        }],
    })
    saved = copy.deepcopy(state)
    repository = ProjectRepository(load_projects=lambda: copy.deepcopy(saved), save_projects=lambda value: saved.update(copy.deepcopy(value)))
    calls = []

    def provider(executor, prompt, workspace, attempt_id, **ids):
        calls.append(prompt)
        if len(calls) == 1:
            return {
                "ok": True,
                "reply": '```json\n{"checklistUpdates":[{"id":"deliverable","text":"Produce the final report","done":false,"evidence":"planned"}]}\n```',
                "status": "completed",
            }
        return {
            "ok": True,
            "reply": '```json\n{"checklistUpdates":[{"id":"deliverable","text":"Produce the final report","done":true,"evidence":"verified"}]}\n```',
            "status": "completed",
        }

    def apply_checklist_updates(task, result):
        reply = str(result.get("reply") or "")
        if '"done":false' in reply:
            task["checklist"] = [{
                "id": "deliverable",
                "text": "Produce the final report",
                "done": False,
                "source": "project_execution_acceptance",
                "generatedBy": "project_execution_checklist_planner",
            }]
            return True
        if '"done":true' in reply:
            task["checklist"][0]["done"] = True
            return True
        return False

    def find(project_id, task_id):
        project = repository.get(project_id)
        task = next(item for item in project["tasks"] if item["id"] == task_id)
        return {"projects": [project]}, project, task

    ports = type("Ports", (), {
        "repository": repository,
        "build_prompt": staticmethod(lambda project, task, attempt, workspace: "EXECUTE\nCHECKLIST:\n" + "\n".join(item["text"] for item in task["checklist"])),
        "provider": staticmethod(provider),
        "git_snapshot": staticmethod(lambda path: {"files": [], "dirty": False}),
        "find": staticmethod(find),
        "find_attempt": staticmethod(lambda task, attempt_id: next(item for item in task["attempts"] if item["id"] == attempt_id)),
        "apply_checklist_updates": staticmethod(apply_checklist_updates),
        "apply_meeting_discussion_points": staticmethod(lambda task, result: False),
        "redact": staticmethod(lambda value: str(value or "")),
        "now": staticmethod(lambda: "now"),
        "acceptance_checklist": staticmethod(lambda task: task.get("checklist") or []),
        "test_evidence": staticmethod(lambda result: []),
        "transition": staticmethod(lambda project, task, state, actor, reason, attempt_id: task.update({"executionState": state})),
        "notify_intervention": staticmethod(lambda *args, **kwargs: None),
        "mark_meeting_actions_completed": staticmethod(lambda *args, **kwargs: None),
        "move_task_to_column": staticmethod(lambda *args, **kwargs: None),
        "backlog_column": staticmethod(lambda project: {"id": "backlog"}),
        "commit_projects": staticmethod(lambda *args, **kwargs: True),
        "cancel_registry": execution_lifecycle.CancelRegistry(flags={"attempt-1": threading.Event()}),
        "has_pending_meeting_actions": staticmethod(lambda task: False),
        "launcher": staticmethod(lambda callback: callback()),
        "start_task": staticmethod(lambda *args, **kwargs: {"ok": True}),
        "attempt_requires_acceptance": staticmethod(lambda task, attempt: False),
        "stage_acceptance": staticmethod(lambda *args, **kwargs: ""),
        "deliver_notification": staticmethod(lambda *args, **kwargs: None),
        "mark_done": staticmethod(lambda project, task, actor, reason, attempt_id: {"ok": True}),
        "continue_incomplete_checklist": staticmethod(lambda *args, **kwargs: {"continued": False}),
        "schedule_continue": staticmethod(lambda *args, **kwargs: None),
        "transient_failure_reason": staticmethod(lambda result: None),
        "schedule_transient_retry": staticmethod(lambda *args, **kwargs: False),
        "start_review": staticmethod(lambda *args, **kwargs: None),
        "finalize_cancel": staticmethod(lambda *args, **kwargs: False),
        "is_stage_pipeline": staticmethod(lambda project: False),
        "reconcile_terminal": staticmethod(lambda *args, **kwargs: None),
    })()

    execution_lifecycle.run_attempt("p1", "t1", "attempt-1", threading.Event(), ports=ports)

    assert len(calls) == 2
    assert "Do not execute the task yet" in calls[0]
    assert "Produce the final report" in calls[1]


def test_runner_skips_checklist_planning_when_checklist_exists():
    state, repository = _repository()
    project = state["projects"][0]
    project.update({"columns": [{"id": "done", "order": 1}], "workflowActive": True, "activeTaskId": "t1"})
    task = project["tasks"][0]
    task.update({
        "executionState": "executing",
        "activeAttemptId": "attempt-1",
        "checklist": [{"id": "existing", "text": "Use existing acceptance criteria", "done": False}],
        "attempts": [{
            "id": "attempt-1",
            "status": "executing",
            "workspacePath": "/workspace",
            "executor": {"id": "executor", "providerKind": "test"},
            "skipReview": True,
            "requiresUserAcceptance": False,
            "autoReviewAfterExecution": False,
            "projectFlow": False,
        }],
    })
    saved = copy.deepcopy(state)
    repository = ProjectRepository(load_projects=lambda: copy.deepcopy(saved), save_projects=lambda value: saved.update(copy.deepcopy(value)))
    calls = []

    def provider(executor, prompt, workspace, attempt_id, **ids):
        calls.append(prompt)
        return {
            "ok": True,
            "reply": '```json\n{"checklistUpdates":[{"id":"existing","text":"Use existing acceptance criteria","done":true,"evidence":"verified"}]}\n```',
            "status": "completed",
        }

    def find(project_id, task_id):
        project = repository.get(project_id)
        task = next(item for item in project["tasks"] if item["id"] == task_id)
        return {"projects": [project]}, project, task

    ports = type("Ports", (), {
        "repository": repository,
        "build_prompt": staticmethod(lambda project, task, attempt, workspace: "EXECUTE\nCHECKLIST:\n" + "\n".join(item["text"] for item in task["checklist"])),
        "provider": staticmethod(provider),
        "git_snapshot": staticmethod(lambda path: {"files": [], "dirty": False}),
        "find": staticmethod(find),
        "find_attempt": staticmethod(lambda task, attempt_id: next(item for item in task["attempts"] if item["id"] == attempt_id)),
        "apply_checklist_updates": staticmethod(lambda task, result: task["checklist"][0].update({"done": True}) or True),
        "apply_meeting_discussion_points": staticmethod(lambda task, result: False),
        "redact": staticmethod(lambda value: str(value or "")),
        "now": staticmethod(lambda: "now"),
        "acceptance_checklist": staticmethod(lambda task: task.get("checklist") or []),
        "test_evidence": staticmethod(lambda result: []),
        "transition": staticmethod(lambda project, task, state, actor, reason, attempt_id: task.update({"executionState": state})),
        "notify_intervention": staticmethod(lambda *args, **kwargs: None),
        "mark_meeting_actions_completed": staticmethod(lambda *args, **kwargs: None),
        "move_task_to_column": staticmethod(lambda *args, **kwargs: None),
        "backlog_column": staticmethod(lambda project: {"id": "backlog"}),
        "commit_projects": staticmethod(lambda *args, **kwargs: True),
        "cancel_registry": execution_lifecycle.CancelRegistry(flags={"attempt-1": threading.Event()}),
        "has_pending_meeting_actions": staticmethod(lambda task: False),
        "launcher": staticmethod(lambda callback: callback()),
        "start_task": staticmethod(lambda *args, **kwargs: {"ok": True}),
        "attempt_requires_acceptance": staticmethod(lambda task, attempt: False),
        "stage_acceptance": staticmethod(lambda *args, **kwargs: ""),
        "deliver_notification": staticmethod(lambda *args, **kwargs: None),
        "mark_done": staticmethod(lambda project, task, actor, reason, attempt_id: {"ok": True}),
        "continue_incomplete_checklist": staticmethod(lambda *args, **kwargs: {"continued": False}),
        "schedule_continue": staticmethod(lambda *args, **kwargs: None),
        "transient_failure_reason": staticmethod(lambda result: None),
        "schedule_transient_retry": staticmethod(lambda *args, **kwargs: False),
        "start_review": staticmethod(lambda *args, **kwargs: None),
        "finalize_cancel": staticmethod(lambda *args, **kwargs: False),
        "is_stage_pipeline": staticmethod(lambda project: False),
        "reconcile_terminal": staticmethod(lambda *args, **kwargs: None),
    })()

    execution_lifecycle.run_attempt("p1", "t1", "attempt-1", threading.Event(), ports=ports)

    assert len(calls) == 1
    assert "Do not execute the task yet" not in calls[0]
    assert "Use existing acceptance criteria" in calls[0]


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


def test_runner_stops_before_review_when_provider_created_human_decision():
    _, repository = _repository()
    repository.update("p1", lambda project: project["tasks"][0].update({
        "executionState": "executing",
        "activeAttemptId": "attempt-1",
        "checklist": [{"id": "deliverable", "text": "Deliver", "done": False}],
        "attempts": [{
            "id": "attempt-1",
            "status": "executing",
            "workspacePath": "/workspace",
            "executor": {"id": "executor", "providerKind": "test"},
        }],
    }))
    registry = execution_lifecycle.CancelRegistry(flags={"attempt-1": threading.Event()})
    forbidden = []

    def provider(*args, **kwargs):
        def wait(project):
            task = project["tasks"][0]
            task["attempts"][0].update({
                "status": "awaiting_user_decision",
                "humanDecisionId": "decision-1",
            })
            task["executionState"] = "awaiting_user_decision"
        repository.update("p1", wait)
        return {"ok": True, "reply": "waiting", "status": "completed"}

    ports = type("Ports", (), {
        "repository": repository,
        "build_prompt": staticmethod(lambda *args: "prompt"),
        "provider": staticmethod(provider),
        "acceptance_checklist": staticmethod(lambda task: task.get("checklist") or []),
        "find_attempt": staticmethod(lambda task, attempt_id: next(item for item in task["attempts"] if item["id"] == attempt_id)),
        "now": staticmethod(lambda: "now"),
        "cancel_registry": registry,
        "git_snapshot": staticmethod(lambda path: forbidden.append("git") or {}),
        "start_review": staticmethod(lambda *args: forbidden.append("review")),
        "reconcile_terminal": staticmethod(lambda *args: forbidden.append("reconcile")),
    })()

    execution_lifecycle.run_attempt("p1", "t1", "attempt-1", threading.Event(), ports=ports)

    saved = repository.get("p1")["tasks"][0]
    assert saved["activeAttemptId"] == "attempt-1"
    assert saved["attempts"][0]["status"] == "awaiting_user_decision"
    assert forbidden == []
    assert registry.get("attempt-1") is None


def test_marked_project_terminal_attempt_reconciles_instead_of_scheduling_legacy_continue():
    project = {
        "id": "p1",
        "title": "Project",
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": {
            **default_orchestration_state(),
            "state": "running",
            "currentStage": 1,
            "currentRunId": "run-1",
        },
        "projectExecutionEnabled": True,
        "workspacePath": "/workspace",
        "tasks": [{
            "id": "t1",
            "title": "Task",
            "executionStage": 1,
            "stageRunId": "run-1",
            "executionState": "executing",
            "activeAttemptId": "attempt-1",
            "attempts": [{
                "id": "attempt-1",
                "status": "executing",
                "stageRunId": "run-1",
                "workspacePath": "/workspace",
                "executor": {"id": "executor", "providerKind": "test"},
                "skipReview": True,
                "requiresUserAcceptance": False,
                "autoReviewAfterExecution": False,
                "projectFlow": True,
            }],
            "checklist": [{"id": "done", "text": "Done", "done": True}],
        }],
    }
    scheduled = []
    reconciled = []

    def find(project_id, task_id):
        task = project["tasks"][0]
        return {"projects": [project]}, project, task

    ports = type("Ports", (), {
        "repository": type("Repo", (), {"get": staticmethod(lambda project_id: copy.deepcopy(project))})(),
        "build_prompt": staticmethod(lambda *args: "prompt"),
        "provider": staticmethod(lambda *args, **kwargs: {"ok": True, "reply": "done", "status": "completed"}),
        "git_snapshot": staticmethod(lambda path: {"files": [], "dirty": False}),
        "find": staticmethod(find),
        "find_attempt": staticmethod(lambda task, attempt_id: next(item for item in task["attempts"] if item["id"] == attempt_id)),
        "apply_checklist_updates": staticmethod(lambda task, result: False),
        "apply_meeting_discussion_points": staticmethod(lambda task, result: False),
        "redact": staticmethod(lambda value: str(value or "")),
        "now": staticmethod(lambda: "now"),
        "acceptance_checklist": staticmethod(lambda task: task.get("checklist") or []),
        "test_evidence": staticmethod(lambda result: []),
        "transition": staticmethod(lambda project, task, state, actor, reason, attempt_id: task.update({"executionState": state})),
        "notify_intervention": staticmethod(lambda *args, **kwargs: None),
        "mark_meeting_actions_completed": staticmethod(lambda *args, **kwargs: None),
        "move_task_to_column": staticmethod(lambda *args, **kwargs: None),
        "backlog_column": staticmethod(lambda project: {"id": "backlog"}),
        "commit_projects": staticmethod(lambda *args, **kwargs: True),
        "cancel_registry": execution_lifecycle.CancelRegistry(flags={"attempt-1": threading.Event()}),
        "has_pending_meeting_actions": staticmethod(lambda task: False),
        "launcher": staticmethod(lambda callback: callback()),
        "start_task": staticmethod(lambda *args, **kwargs: {"ok": True}),
        "attempt_requires_acceptance": staticmethod(lambda task, attempt: False),
        "stage_acceptance": staticmethod(lambda *args, **kwargs: ""),
        "deliver_notification": staticmethod(lambda *args, **kwargs: None),
        "mark_done": staticmethod(lambda project, task, actor, reason, attempt_id: task.update({"executionState": "done", "completedAt": "now"}) or {"ok": True}),
        "continue_incomplete_checklist": staticmethod(lambda *args, **kwargs: {"continued": False}),
        "schedule_continue": staticmethod(lambda project_id, reason: scheduled.append((project_id, reason))),
        "transient_failure_reason": staticmethod(lambda result: None),
        "schedule_transient_retry": staticmethod(lambda *args, **kwargs: False),
        "start_review": staticmethod(lambda *args, **kwargs: None),
        "finalize_cancel": staticmethod(lambda *args, **kwargs: False),
        "is_stage_pipeline": staticmethod(lambda project: True),
        "reconcile_terminal": staticmethod(lambda project_id, task_id, attempt_id, reason: reconciled.append((project_id, task_id, attempt_id, reason))),
    })()

    execution_lifecycle.run_attempt("p1", "t1", "attempt-1", threading.Event(), ports=ports)

    assert scheduled == []
    assert reconciled == [("p1", "t1", "attempt-1", "review_skipped")]
    assert project["tasks"][0]["executionState"] == "done"
    assert project.get("projectExecutionFlowActive") is None


def test_status_projects_stage_pipeline_orchestration_without_legacy_idle_reconcile():
    state, repository = _repository()
    project = state["projects"][0]
    project.update({
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": {
            **default_orchestration_state(),
            "state": "running",
            "currentStage": 1,
            "currentRunId": "run-1",
        },
        "workflowActive": False,
        "workflowPhase": "idle",
    })
    project["tasks"][0].update({
        "executionStage": 1,
        "stageRunId": "run-1",
        "executionState": "executing",
        "activeAttemptId": "attempt-1",
    })
    transitions = []

    result = execution_lifecycle.status(
        "p1",
        None,
        repository=repository,
        is_live=lambda attempt_id: False,
        transition_task=lambda *args: transitions.append(args),
    )

    assert result["ok"] is True
    assert result["active"] is True
    assert result["phase"] == "running"
    assert result["currentTaskId"] == "t1"
    assert result["activeTaskIds"] == ["t1"]
    assert result["currentStage"] == 1
    assert result["runId"] == "run-1"
    assert result["orchestrationState"] == "running"
    assert transitions == []
    stored_task = repository.get("p1")["tasks"][0]
    assert stored_task["executionState"] == "executing"
    assert stored_task["activeAttemptId"] == "attempt-1"


def test_status_projects_stage_pipeline_stale_running_without_active_task_is_idle():
    state, repository = _repository()
    project = state["projects"][0]
    project.update({
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": {
            **default_orchestration_state(),
            "state": "running",
            "currentStage": 1,
            "currentRunId": "run-1",
        },
        "workflowActive": False,
        "workflowPhase": "idle",
    })
    project["tasks"][0].update({
        "executionStage": 1,
        "stageRunId": "run-1",
        "executionState": "backlog",
        "activeAttemptId": None,
    })

    result = execution_lifecycle.status(
        "p1",
        None,
        repository=repository,
        is_live=lambda attempt_id: False,
        transition_task=lambda *args: None,
    )

    assert result["ok"] is True
    assert result["active"] is False
    assert result["phase"] == "idle"
    assert result["flowActive"] is False
    assert result["activeTaskIds"] == []
    assert result["orchestrationState"] == "running"


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
