from __future__ import annotations

import inspect
import sys
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

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


def test_claude_and_openclaw_attempts_use_attempt_scoped_session_id():
    for provider in ("claude-code", "openclaw"):
        calls = []
        project = {
            "id": "project", "projectExecutionEnabled": True, "workflowActive": False, "workflowPhase": "idle",
            "tasks": [{
                "id": "task", "activeAttemptId": "attempt", "executionState": "reviewing",
                "executorAgentId": "agent", "activeReviewId": "review", "updatedAt": "2",
            }],
            "columns": [],
        }
        resolved = service([project], descriptors={"agent": {"providerKind": provider}}, calls=calls).resolve_scope("project").scope
        assert resolved and resolved.session_task_id == "attempt"
        assert resolved.attempt_id == "attempt" and resolved.review_id == "review"
        assert resolved.phase == "reviewing"


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


def test_service_has_no_server_dependency():
    import services.project_workflow_chat as module

    source = inspect.getsource(module)
    assert "import server" not in source
    assert "from app import server" not in source
