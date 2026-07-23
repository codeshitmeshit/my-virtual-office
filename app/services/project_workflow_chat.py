"""Project/task execution scope resolution for workflow chat reads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


WORKING_STATES = frozenset({"validating", "executing", "retrying", "reworking", "reviewing"})


@dataclass(frozen=True)
class ProjectWorkflowScope:
    project_id: str
    task_id: str
    session_task_id: str
    agent_id: str
    provider_kind: str
    profile: str
    conversation_id: str
    attempt_id: str
    review_id: str
    phase: str


@dataclass(frozen=True)
class ProjectWorkflowChatPorts:
    workflow_state: Callable[[str], Mapping[str, Any]]
    persisted_state: Callable[[str], Mapping[str, Any]]
    load_projects: Callable[[], Mapping[str, Any]]
    project_execution_enabled: Callable[[Mapping[str, Any]], bool]
    task_agent_id: Callable[[Mapping[str, Any], Mapping[str, Any]], str]
    agent_descriptor: Callable[[str], Mapping[str, Any]]
    read_messages: Callable[[str, str, str, str | None], list[dict[str, Any]]]
    session_active: Callable[[str, str, str], bool]


@dataclass(frozen=True)
class ScopeResolution:
    scope: ProjectWorkflowScope | None
    empty_payload: Mapping[str, Any] | None = None


class ProjectWorkflowChatService:
    def __init__(self, ports: ProjectWorkflowChatPorts) -> None:
        self._ports = ports

    def resolve_scope(self, project_id: str) -> ScopeResolution:
        workflow = dict(self._ports.workflow_state(project_id) or {})
        persisted = dict(self._ports.persisted_state(project_id) or {})
        current_task_id = workflow.get("currentTaskId") or persisted.get("currentTaskId")
        phase = workflow.get("phase") or persisted.get("phase", "idle")
        data = self._ports.load_projects() or {}
        project = next((item for item in data.get("projects", []) if item.get("id") == project_id), None)
        if not project:
            return ScopeResolution(None, {"ok": True, "messages": [], "agent": None})

        execution_enabled = bool(self._ports.project_execution_enabled(project))
        project_execution_active = execution_enabled and project.get("workflowActive") and project.get("activeTaskId")
        agent_id = project.get("activeAgent") if project_execution_active else None
        task_id = project.get("activeTaskId") if project_execution_active else current_task_id
        conversation_id = ""
        task = None

        if task_id:
            task = next((item for item in project.get("tasks", []) if item.get("id") == task_id), None)
            if task:
                task_execution_active = (
                    execution_enabled
                    and task.get("activeAttemptId")
                    and str(task.get("executionState") or "") in WORKING_STATES
                )
                if project_execution_active or task_execution_active:
                    phase = project.get("workflowPhase") or phase
                    conversation_id = str(task.get("activeAttemptId") or "")
                    agent_id = agent_id or self._ports.task_agent_id(project, task)
                    if task_execution_active and phase in {"", "idle", "stopped"}:
                        phase = str(task.get("executionState") or "executing")
                agent_id = agent_id or task.get("assignee")

        if not agent_id:
            column_ids = [
                column.get("id")
                for column in project.get("columns", [])
                if str(column.get("title") or "").lower() in {"in progress", "review", "to do"}
            ]
            execution_tasks = [
                item
                for item in project.get("tasks", [])
                if item.get("activeAttemptId") and str(item.get("executionState") or "") in WORKING_STATES
            ] if execution_enabled else []
            active_tasks = execution_tasks or [item for item in project.get("tasks", []) if item.get("columnId") in column_ids]
            if active_tasks:
                task = sorted(active_tasks, key=lambda item: item.get("updatedAt", ""), reverse=True)[0]
                task_id = task.get("id")
                if execution_tasks:
                    conversation_id = str(task.get("activeAttemptId") or "")
                    agent_id = self._ports.task_agent_id(project, task)
                    if phase in {"", "idle", "stopped"}:
                        phase = str(task.get("executionState") or "executing")
                else:
                    agent_id = task.get("assignee")

        if not agent_id or not task_id:
            return ScopeResolution(None, {"ok": True, "messages": [], "agent": None, "phase": phase})

        descriptor = dict(self._ports.agent_descriptor(str(agent_id)) or {})
        provider_kind = str(descriptor.get("providerKind") or "openclaw").strip().lower()
        profile = str(descriptor.get("profile") or descriptor.get("providerAgentId") or "")
        project_execution_session = execution_enabled and bool(conversation_id)
        session_task_id = conversation_id if project_execution_session and provider_kind not in {"hermes", "codex"} else str(task_id)
        return ScopeResolution(
            ProjectWorkflowScope(
                project_id=project_id,
                task_id=str(task_id),
                session_task_id=session_task_id,
                agent_id=str(agent_id),
                provider_kind=provider_kind,
                profile=profile,
                conversation_id=conversation_id,
                attempt_id=conversation_id,
                review_id=str((task or {}).get("activeReviewId") or ""),
                phase=str(phase or ""),
            )
        )

    def read(self, project_id: str) -> dict[str, Any]:
        resolution = self.resolve_scope(project_id)
        if resolution.scope is None:
            return dict(resolution.empty_payload or {"ok": True, "messages": [], "agent": None})
        scope = resolution.scope
        messages = self._ports.read_messages(
            scope.agent_id,
            scope.project_id,
            scope.session_task_id,
            scope.conversation_id or None,
        )
        active = self._ports.session_active(scope.agent_id, scope.project_id, scope.session_task_id)
        return {
            "ok": True,
            "messages": messages,
            "agent": scope.agent_id,
            "taskId": scope.task_id,
            "phase": scope.phase,
            "sessionActive": active,
        }
