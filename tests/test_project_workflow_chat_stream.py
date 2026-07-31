from __future__ import annotations

import sys
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.project_workflow_chat import ProjectWorkflowChatPorts, ProjectWorkflowChatService
from services.project_workflow_chat_stream import (
    ProjectWorkflowChatStreamPorts,
    ProjectWorkflowChatStreamService,
)
from services.provider_events import ProviderEventJournal


def workflow_chat(projects, provider_kind="codex"):
    return ProjectWorkflowChatService(
        ProjectWorkflowChatPorts(
            workflow_state=lambda _project_id: {},
            persisted_state=lambda _project_id: {},
            load_projects=lambda: {"projects": projects},
            project_execution_enabled=lambda project: bool(project.get("projectExecutionEnabled")),
            task_agent_id=lambda _project, task: task.get("executorAgentId") or "",
            agent_descriptor=lambda agent_id: {"providerKind": provider_kind, "profile": "local"} if agent_id == "agent" else {"providerKind": "openclaw"},
            read_messages=lambda *_args: [],
            session_active=lambda *_args: False,
        )
    )


def stream_service(projects, journal=None, provider_kind="codex"):
    def projector(event_name, payload, provider_kind, agent_id, conversation_id, event_id):
        return {
            "id": f"{provider_kind}:{agent_id}:{conversation_id}:{event_id}",
            "itemKind": "message",
            "status": "done",
            "text": payload.get("text") or event_name,
            "version": str(event_id or ""),
        }

    return ProjectWorkflowChatStreamService(
        ProjectWorkflowChatStreamPorts(
            workflow_chat=workflow_chat(projects, provider_kind=provider_kind),
            journal=journal or ProviderEventJournal(),
            timeline_item_projector=projector,
            clock=lambda: 1.25,
        )
    )


def active_project(*, project_id="project", task_id="task", attempt_id="attempt", agent_id="agent"):
    return {
        "id": project_id,
        "projectExecutionEnabled": True,
        "workflowActive": True,
        "workflowPhase": "executing",
        "activeTaskId": task_id,
        "activeAgent": agent_id,
        "tasks": [{
            "id": task_id,
            "activeAttemptId": attempt_id,
            "executionState": "executing",
            "executorAgentId": agent_id,
        }],
        "columns": [],
    }


def test_inactive_project_returns_compatible_empty_stream_snapshot():
    service = stream_service([{"id": "project", "tasks": [], "columns": []}])

    snapshot = service.snapshot("project", after="bad-cursor")

    assert snapshot["ok"] is True
    assert snapshot["stream"] == "inactive"
    assert snapshot["events"] == []
    assert snapshot["scopeVersion"] == ""
    assert snapshot["eventId"] == 0


def test_active_snapshot_uses_server_resolved_scope_and_cursor():
    service = stream_service([active_project()])

    snapshot = service.snapshot("project", after=17)

    assert snapshot["stream"] == "active"
    assert snapshot["projectId"] == "project"
    assert snapshot["taskId"] == "task"
    assert snapshot["attemptId"] == "attempt"
    assert snapshot["agentId"] == "agent"
    assert snapshot["providerKind"] == "codex"
    assert snapshot["conversationId"] == "attempt"
    assert snapshot["eventId"] == 17
    assert len(snapshot["scopeVersion"]) == 40


def test_wait_events_filters_other_scope_and_projects_canonical_items():
    journal = ProviderEventJournal()
    journal.publish("codex", "agent", "attempt", "message.delta", {"text": "visible"}, "run-1")
    journal.publish("codex", "other-agent", "attempt", "message.delta", {"text": "hidden"}, "run-2")
    journal.publish("hermes", "agent", "attempt", "message.delta", {"text": "hidden"}, "run-3")
    service = stream_service([active_project()], journal)
    scope = workflow_chat([active_project()]).resolve_scope("project").scope

    events = service.wait_events(scope, 0, timeout=0)

    assert len(events) == 1
    assert events[0]["timelineItem"]["text"] == "visible"
    assert events[0]["projectId"] == "project"
    assert events[0]["scopeVersion"]


def test_all_provider_families_use_the_canonical_timeline_projector():
    for provider_kind in ("codex", "hermes", "claude-code", "openclaw"):
        journal = ProviderEventJournal()
        journal.publish(provider_kind, "agent", "attempt", "message.complete", {"text": provider_kind}, f"run-{provider_kind}")
        service = stream_service([active_project()], journal, provider_kind=provider_kind)
        scope = workflow_chat([active_project()], provider_kind=provider_kind).resolve_scope("project").scope

        events = service.wait_events(scope, 0, timeout=0)

        assert len(events) == 1
        assert events[0]["providerKind"] == provider_kind
        assert events[0]["timelineItem"]["text"] == provider_kind


def test_terminal_events_are_marked_for_snapshot_settlement():
    journal = ProviderEventJournal()
    published = journal.publish("codex", "agent", "attempt", "run.completed", {"ok": True}, "run-1")
    service = stream_service([active_project()], journal)
    scope = workflow_chat([active_project()]).resolve_scope("project").scope

    payload = service.project_event(scope, published)

    assert payload["terminal"] is True
    assert payload["eventName"] == "run.completed"
