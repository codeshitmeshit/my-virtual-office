from __future__ import annotations

import inspect
import sys
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.project_orchestration import EXECUTION_MODEL_STAGE_PIPELINE_V1, default_orchestration_state
from services.project_workflow_chat import ProjectWorkflowChatPorts, ProjectWorkflowChatService


def service(projects, *, workflow=None, persisted=None, descriptors=None, calls=None):
    calls = calls if calls is not None else []
    return ProjectWorkflowChatService(
        ProjectWorkflowChatPorts(
            workflow_state=lambda project_id: workflow or {},
            persisted_state=lambda project_id: persisted or {},
            load_projects=lambda: {"projects": projects},
            project_execution_enabled=lambda project: bool(project.get("projectExecutionEnabled")),
            task_agent_id=lambda project, task: task.get("executorAgentId") or task.get("assignee") or "",
            agent_descriptor=lambda agent_id: (descriptors or {}).get(agent_id, {"providerKind": "openclaw"}),
            read_messages=lambda agent, project, task, conversation: calls.append(("messages", agent, project, task, conversation)) or [{"text": "message"}],
            session_active=lambda agent, project, task: calls.append(("active", agent, project, task)) or True,
        )
    )


def test_missing_project_and_empty_project_keep_compatible_envelopes():
    assert service([]).read("missing") == {"ok": True, "messages": [], "agent": None}
    project = {"id": "project", "tasks": [], "columns": []}
    assert service([project], persisted={"phase": "idle"}).read("project") == {
        "ok": True, "messages": [], "agent": None, "phase": "idle"
    }


def test_tracked_codex_attempt_preserves_task_session_and_envelope():
    calls = []
    project = {
        "id": "project", "projectExecutionEnabled": True, "workflowActive": True,
        "workflowPhase": "executing", "activeTaskId": "task", "activeAgent": "codex-agent",
        "tasks": [{"id": "task", "activeAttemptId": "attempt", "executionState": "executing"}], "columns": [],
    }
    result = service([project], descriptors={"codex-agent": {"providerKind": "codex", "profile": "main"}}, calls=calls).read("project")
    assert result == {
        "ok": True, "messages": [{"text": "message"}], "agent": "codex-agent",
        "taskId": "task", "phase": "executing", "sessionActive": True,
    }
    assert calls[0] == ("messages", "codex-agent", "project", "task", "attempt")


def test_claude_attempts_use_attempt_scoped_session_id():
    calls = []
    project = {
        "id": "project", "projectExecutionEnabled": True, "workflowActive": False, "workflowPhase": "idle",
        "tasks": [{
            "id": "task", "activeAttemptId": "attempt", "executionState": "reviewing",
            "executorAgentId": "agent", "activeReviewId": "review", "updatedAt": "2",
        }],
        "columns": [],
    }
    resolved = service([project], descriptors={"agent": {"providerKind": "claude-code"}}, calls=calls).resolve_scope("project").scope
    assert resolved and resolved.session_task_id == "attempt"
    assert resolved.session_fallback_ids == ()
    assert resolved.attempt_id == "attempt" and resolved.review_id == "review"
    assert resolved.phase == "reviewing"


def test_openclaw_attempt_keeps_task_session_with_attempt_fallback():
    calls = []
    project = {
        "id": "project", "projectExecutionEnabled": True, "workflowActive": False, "workflowPhase": "idle",
        "tasks": [{
            "id": "task", "activeAttemptId": "attempt", "executionState": "reviewing",
            "executorAgentId": "agent", "activeReviewId": "review", "updatedAt": "2",
        }],
        "columns": [],
    }
    resolved = service([project], descriptors={"agent": {"providerKind": "openclaw"}}, calls=calls).resolve_scope("project").scope
    assert resolved and resolved.session_task_id == "task"
    assert resolved.session_fallback_ids == ("attempt",)
    assert resolved.attempt_id == "attempt" and resolved.review_id == "review"
    assert resolved.phase == "reviewing"


def test_openclaw_read_falls_back_to_attempt_session_when_task_session_is_empty():
    calls = []
    project = {
        "id": "project", "projectExecutionEnabled": True,
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": {"state": "running"},
        "tasks": [active_stage_task("task", "agent", updated_at="2")],
        "columns": [],
    }

    def read_messages(agent, project_id, task_id, conversation):
        calls.append(("messages", agent, project_id, task_id, conversation))
        return [{"text": "attempt message"}] if task_id == "attempt-task" else []

    svc = ProjectWorkflowChatService(
        ProjectWorkflowChatPorts(
            workflow_state=lambda project_id: {},
            persisted_state=lambda project_id: {},
            load_projects=lambda: {"projects": [project]},
            project_execution_enabled=lambda project: True,
            task_agent_id=lambda project, task: task.get("executorAgentId") or "",
            agent_descriptor=lambda agent_id: {"providerKind": "openclaw"},
            read_messages=read_messages,
            session_active=lambda agent, project_id, task_id: False,
        )
    )

    result = svc.read("project")

    assert result["messages"] == [{"text": "attempt message"}]
    assert calls == [
        ("messages", "agent", "project", "task", "attempt-task"),
        ("messages", "agent", "project", "attempt-task", "attempt-task"),
    ]


def test_active_attempt_filters_old_task_session_messages():
    project = {
        "id": "project", "projectExecutionEnabled": True,
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": {"state": "running"},
        "tasks": [{
            "id": "task",
            "executionStage": 1,
            "executionState": "executing",
            "activeAttemptId": "attempt-new",
            "executorAgentId": "agent",
            "updatedAt": "2",
            "attempts": [
                {"id": "attempt-old", "startedAt": "2026-07-29T05:00:00+00:00"},
                {"id": "attempt-new", "startedAt": "2026-07-29T07:34:07+00:00"},
            ],
        }],
        "columns": [],
    }

    def read_messages(agent, project_id, task_id, conversation):
        return [
            {"text": "old attempt", "epochMs": 1785303000000},
            {"text": "new attempt", "epochMs": 1785310450000},
        ]

    svc = ProjectWorkflowChatService(
        ProjectWorkflowChatPorts(
            workflow_state=lambda project_id: {},
            persisted_state=lambda project_id: {},
            load_projects=lambda: {"projects": [project]},
            project_execution_enabled=lambda project: True,
            task_agent_id=lambda project, task: task.get("executorAgentId") or "",
            agent_descriptor=lambda agent_id: {"providerKind": "openclaw"},
            read_messages=read_messages,
            session_active=lambda agent, project_id, task_id: True,
        )
    )

    result = svc.read("project")

    assert result["messages"] == [{"text": "new attempt", "epochMs": 1785310450000}]


def test_most_recent_legacy_task_selection_is_unchanged():
    project = {
        "id": "project", "projectExecutionEnabled": False,
        "columns": [{"id": "doing", "title": "In Progress"}],
        "tasks": [
            {"id": "old", "columnId": "doing", "assignee": "old-agent", "updatedAt": "1"},
            {"id": "new", "columnId": "doing", "assignee": "new-agent", "updatedAt": "2"},
        ],
    }
    resolved = service([project]).resolve_scope("project").scope
    assert resolved and resolved.task_id == "new" and resolved.agent_id == "new-agent"


def marked_project(tasks):
    state = default_orchestration_state()
    state.update({"state": "running", "currentStage": 1, "currentRunId": "run-1"})
    return {
        "id": "project",
        "projectExecutionEnabled": True,
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": state,
        "tasks": tasks,
        "columns": [],
    }


def active_stage_task(task_id, agent_id, *, updated_at):
    return {
        "id": task_id,
        "executionStage": 1,
        "executionState": "executing",
        "activeAttemptId": f"attempt-{task_id}",
        "executorAgentId": agent_id,
        "updatedAt": updated_at,
    }


def test_marked_multi_active_requires_explicit_task_scope_without_reading_messages():
    calls = []
    project = marked_project([
        active_stage_task("old", "old-agent", updated_at="1"),
        active_stage_task("new", "new-agent", updated_at="2"),
    ])

    result = service([project], calls=calls).read("project")

    assert result == {
        "ok": True,
        "messages": [],
        "agent": None,
        "phase": "running",
        "taskId": None,
        "displayTaskId": "new",
        "activeTaskIds": ["old", "new"],
        "activeTaskCount": 2,
        "requiresTaskScope": True,
        "code": "task_scope_required",
    }
    assert calls == []


def test_marked_multi_active_explicit_task_scope_is_execution_authority():
    calls = []
    project = marked_project([
        active_stage_task("old", "old-agent", updated_at="1"),
        active_stage_task("new", "new-agent", updated_at="2"),
    ])

    result = service([project], calls=calls).read("project", task_scope="old")

    assert result["ok"] is True
    assert result["taskId"] == "old"
    assert result["agent"] == "old-agent"
    assert result["phase"] == "executing"
    assert result["messages"] == [{"text": "message"}]
    assert calls[0] == ("messages", "old-agent", "project", "old", "attempt-old")
    assert calls[1] == ("active", "old-agent", "project", "old")


def test_marked_multi_active_rejects_scope_outside_active_tasks_without_reading_messages():
    calls = []
    project = marked_project([
        active_stage_task("active", "agent", updated_at="2"),
        {
            "id": "inactive",
            "executionStage": 2,
            "executionState": "pending",
            "executorAgentId": "other-agent",
            "updatedAt": "3",
        },
    ])

    result = service([project], calls=calls).read("project", task_scope="inactive")

    assert result["ok"] is False
    assert result["_status"] == 409
    assert result["code"] == "invalid_task_scope"
    assert result["taskId"] is None
    assert result["activeTaskIds"] == ["active"]
    assert calls == []


def test_marked_single_active_task_can_resolve_without_explicit_scope():
    calls = []
    project = marked_project([active_stage_task("only", "agent", updated_at="1")])

    result = service([project], calls=calls).read("project")

    assert result["ok"] is True
    assert result["taskId"] == "only"
    assert result["agent"] == "agent"
    assert calls[0] == ("messages", "agent", "project", "only", "attempt-only")


def test_marked_explicit_scope_reads_non_working_active_attempt_states():
    calls = []
    task = active_stage_task("awaiting", "agent", updated_at="1")
    task["executionState"] = "awaiting_user_acceptance"
    project = marked_project([task])

    result = service([project], calls=calls).read("project", task_scope="awaiting")

    assert result["ok"] is True
    assert result["taskId"] == "awaiting"
    assert result["phase"] == "awaiting_user_acceptance"
    assert calls[0] == ("messages", "agent", "project", "awaiting", "attempt-awaiting")


def test_service_has_no_server_dependency():
    import services.project_workflow_chat as module

    source = inspect.getsource(module)
    assert "import server" not in source
    assert "from app import server" not in source
