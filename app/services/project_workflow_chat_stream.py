"""Project-scoped workflow chat Server-Sent Event helpers."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .project_workflow_chat import ProjectWorkflowChatService, ProjectWorkflowScope
from .provider_events import sanitize_payload


JsonDict = dict[str, Any]

TERMINAL_EVENTS = frozenset({"run.completed", "run.failed", "run.cancelled", "run.canceled"})


@dataclass(frozen=True)
class ProjectWorkflowChatStreamPorts:
    workflow_chat: ProjectWorkflowChatService
    journal: Any
    timeline_item_projector: Callable[[str, Mapping[str, Any], str, str, str, Any], JsonDict | None]
    clock: Callable[[], float] = time.time


def scope_version(scope: ProjectWorkflowScope) -> str:
    payload = {
        "projectId": scope.project_id,
        "taskId": scope.task_id,
        "sessionTaskId": scope.session_task_id,
        "agentId": scope.agent_id,
        "providerKind": scope.provider_kind,
        "profile": scope.profile,
        "conversationId": scope.conversation_id,
        "attemptId": scope.attempt_id,
        "reviewId": scope.review_id,
        "phase": scope.phase,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()


class ProjectWorkflowChatStreamService:
    """Resolve project scope server-side and expose safe provider events."""

    def __init__(self, ports: ProjectWorkflowChatStreamPorts):
        self._ports = ports

    def resolve_scope(self, project_id: str, *, task_scope: str | None = None) -> ProjectWorkflowScope | None:
        return self._ports.workflow_chat.resolve_scope(project_id, task_scope=task_scope).scope

    @staticmethod
    def cursor(headers: Mapping[str, Any] | None = None, after: Any = 0) -> int:
        header_value = ""
        try:
            header_value = str((headers or {}).get("Last-Event-ID") or "")
        except AttributeError:
            header_value = ""
        values = []
        for raw in (header_value, after):
            try:
                values.append(int(raw or 0))
            except (TypeError, ValueError):
                values.append(0)
        return max(0, *values)

    def snapshot(self, project_id: str, *, task_scope: str | None = None, after: Any = 0) -> JsonDict:
        resolution = self._ports.workflow_chat.resolve_scope(project_id, task_scope=task_scope)
        if resolution.scope is None:
            payload = dict(resolution.empty_payload or {"ok": True})
            payload.update({
                "stream": "inactive",
                "events": [],
                "scopeVersion": "",
                "eventId": self.cursor(after=after),
                "ts": int(self._ports.clock() * 1000),
            })
            return payload
        scope = resolution.scope
        cursor = self.cursor(after=after)
        return {
            "ok": True,
            "stream": "active",
            "projectId": scope.project_id,
            "taskId": scope.task_id,
            "attemptId": scope.attempt_id,
            "reviewId": scope.review_id,
            "agentId": scope.agent_id,
            "providerKind": scope.provider_kind,
            "conversationId": scope.conversation_id,
            "scopeVersion": scope_version(scope),
            "eventId": cursor,
            "ts": int(self._ports.clock() * 1000),
        }

    def project_event(self, scope: ProjectWorkflowScope, event: Mapping[str, Any]) -> JsonDict | None:
        provider_kind = str(event.get("providerKind") or "").strip().lower()
        agent_id = str(event.get("agentId") or "").strip()
        conversation_id = str(event.get("conversationId") or "").strip()
        if provider_kind != scope.provider_kind or agent_id != scope.agent_id:
            return None
        if scope.conversation_id and conversation_id and conversation_id != scope.conversation_id:
            return None
        event_name = str(event.get("event") or "provider.activity")
        event_id = event.get("id")
        data = dict(event.get("data")) if isinstance(event.get("data"), Mapping) else {}
        item = None
        try:
            item = self._ports.timeline_item_projector(
                event_name,
                data,
                scope.provider_kind,
                scope.agent_id,
                scope.conversation_id,
                event_id,
            )
        except Exception:
            item = None
        payload = {
            "ok": True,
            "projectId": scope.project_id,
            "taskId": scope.task_id,
            "attemptId": scope.attempt_id,
            "reviewId": scope.review_id,
            "agentId": scope.agent_id,
            "providerKind": scope.provider_kind,
            "conversationId": scope.conversation_id,
            "scopeVersion": scope_version(scope),
            "eventId": event_id,
            "eventName": event_name,
            "terminal": event_name in TERMINAL_EVENTS,
        }
        if isinstance(item, Mapping):
            payload["timelineItem"] = dict(item)
        return sanitize_payload(payload)

    def wait_events(self, scope: ProjectWorkflowScope, after: int, *, timeout: float = 1.0) -> list[JsonDict]:
        raw_events = self._ports.journal.wait_for_conversation_events(
            scope.provider_kind,
            scope.agent_id,
            scope.conversation_id,
            after,
            timeout=timeout,
        )
        events = [self.project_event(scope, event) for event in raw_events]
        return [event for event in events if isinstance(event, dict)]
