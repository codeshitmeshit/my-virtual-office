"""Project/task execution scope resolution for workflow chat reads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .project_orchestration import active_task_ids, is_marked_project, orchestration_state, task_is_active


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


def _find_task(project: Mapping[str, Any], task_id: str) -> Mapping[str, Any] | None:
    return next(
        (
            item
            for item in project.get("tasks", [])
            if isinstance(item, Mapping) and str(item.get("id") or "") == task_id
        ),
        None,
    )


def _most_recent_task(tasks: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    if not tasks:
        return None
    return sorted(tasks, key=lambda item: str(item.get("updatedAt") or ""), reverse=True)[0]


def _marked_scope_payload(project: Mapping[str, Any], phase: str, *, code: str = "task_scope_required") -> dict[str, Any]:
    ids = list(active_task_ids(project))
    display_task = _most_recent_task([
        task for task in project.get("tasks", [])
        if isinstance(task, Mapping) and str(task.get("id") or "") in set(ids)
    ])
    return {
        "ok": True,
        "messages": [],
        "agent": None,
        "phase": phase,
        "taskId": None,
        "displayTaskId": str((display_task or {}).get("id") or "") or None,
        "activeTaskIds": ids,
        "activeTaskCount": len(ids),
        "requiresTaskScope": len(ids) > 1,
        "code": code,
    }


class ProjectWorkflowChatService:
    def __init__(self, ports: ProjectWorkflowChatPorts) -> None:
        self._ports = ports

    def resolve_scope(self, project_id: str, *, task_scope: str | None = None) -> ScopeResolution:
        explicit_task_id = str(task_scope or "").strip()
        workflow = dict(self._ports.workflow_state(project_id) or {})
        persisted = dict(self._ports.persisted_state(project_id) or {})
        current_task_id = workflow.get("currentTaskId") or persisted.get("currentTaskId")
        phase = workflow.get("phase") or persisted.get("phase", "idle")
        data = self._ports.load_projects() or {}
        project = next((item for item in data.get("projects", []) if item.get("id") == project_id), None)
        if not project:
            return ScopeResolution(None, {"ok": True, "messages": [], "agent": None})

        execution_enabled = bool(self._ports.project_execution_enabled(project))
        if execution_enabled and is_marked_project(project):
            orchestration_phase = str(orchestration_state(project).get("state") or "")
            if orchestration_phase and phase in {"", "idle", "stopped"}:
                phase = orchestration_phase
            ids = list(active_task_ids(project))
            if explicit_task_id:
                if explicit_task_id not in ids:
                    payload = _marked_scope_payload(project, phase, code="invalid_task_scope")
                    return ScopeResolution(None, {**payload, "ok": False, "_status": 409})
                current_task_id = explicit_task_id
            elif len(ids) > 1:
                return ScopeResolution(None, _marked_scope_payload(project, phase))
            elif len(ids) == 1:
                current_task_id = ids[0]

        project_execution_active = execution_enabled and project.get("workflowActive") and project.get("activeTaskId")
        agent_id = project.get("activeAgent") if project_execution_active else None
        task_id = project.get("activeTaskId") if project_execution_active else current_task_id
        conversation_id = ""
        task = None

        if task_id:
            task = _find_task(project, str(task_id))
            if task:
                task_execution_active = (
                    execution_enabled
                    and task.get("activeAttemptId")
                    and task_is_active(task)
                )
                if project_execution_active or task_execution_active:
                    phase = project.get("workflowPhase") or phase
                    conversation_id = str(task.get("activeAttemptId") or "")
                    agent_id = agent_id or self._ports.task_agent_id(project, task)
                    if task_execution_active and (explicit_task_id or phase in {"", "idle", "stopped", "running", "starting"}):
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
                if item.get("activeAttemptId") and task_is_active(item)
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

    def read(self, project_id: str, *, task_scope: str | None = None) -> dict[str, Any]:
        resolution = self.resolve_scope(project_id, task_scope=task_scope)
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
