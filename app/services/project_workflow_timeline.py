"""Single Provider router for Project Execution timeline reads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from .codex_workflow_timeline_source import CodexWorkflowTimelineSource
from .conversation_timeline import ConversationTimelineService, TimelineScope, canonical_provider_kind
from .conversation_timeline_sources import project_workflow_history
from .openclaw_timeline_source import OpenClawWorkflowTimelineSource


@dataclass(frozen=True)
class ProjectWorkflowTimelinePorts:
    agent_descriptor: Callable[[str], Mapping[str, Any]]
    hermes_history: Callable[[str, str | None], Iterable[Mapping[str, Any]]]
    claude_history: Callable[[str, str | None], Iterable[Mapping[str, Any]]]
    communication_history: Callable[[str, int], Iterable[Mapping[str, Any]]]
    project_communication: Callable[[Mapping[str, Any], str], Mapping[str, Any] | None]
    codex_activity: Callable[[str, str], Iterable[Mapping[str, Any]]]
    openclaw_sessions_dir: Callable[[str], str]
    resolve_openclaw_session: Callable[[Mapping[str, Any], str, str], Mapping[str, Any] | None]
    task_session_key: Callable[[str, str, str], str]


class ProjectWorkflowTimelineRouter:
    def __init__(self, timeline: ConversationTimelineService, ports: ProjectWorkflowTimelinePorts) -> None:
        self._timeline = timeline
        self._ports = ports

    def _provider(self, agent_id: str) -> tuple[str, str]:
        descriptor = dict(self._ports.agent_descriptor(agent_id) or {})
        provider = canonical_provider_kind(descriptor.get("providerKind") or "openclaw")
        defaults = {"hermes": "default", "claude-code": "main", "openclaw": agent_id}
        profile = str(descriptor.get("profile") or descriptor.get("providerAgentId") or defaults.get(provider, ""))
        return provider, profile

    def read(
        self,
        agent_id: str,
        project_id: str,
        task_id: str,
        *,
        max_messages: int = 50,
        conversation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        provider, profile = self._provider(agent_id)
        conversation = str(conversation_id or task_id)
        scope = TimelineScope.create(provider, agent_id, profile, conversation)
        if provider == "hermes":
            return project_workflow_history(
                self._timeline,
                scope,
                self._ports.hermes_history(profile, conversation_id),
                source="hermes",
                limit=max_messages,
            )
        if provider == "claude-code":
            return project_workflow_history(
                self._timeline,
                scope,
                self._ports.claude_history(profile, conversation_id),
                source="claude-code",
                limit=max_messages,
            )
        if provider == "codex":
            source = CodexWorkflowTimelineSource(
                self._timeline,
                self._ports.communication_history,
                self._ports.project_communication,
                self._ports.codex_activity,
            )
            return source.read_messages(scope, max_messages=max_messages)
        session_key = self._ports.task_session_key(agent_id, project_id, task_id)
        source = OpenClawWorkflowTimelineSource(
            self._timeline,
            self._ports.openclaw_sessions_dir(agent_id),
            self._ports.resolve_openclaw_session,
        )
        return source.read_messages(scope, session_key, max_messages=max_messages)

    def is_active(self, agent_id: str, project_id: str, task_id: str) -> bool:
        provider, _profile = self._provider(agent_id)
        if provider != "openclaw":
            return False
        session_key = self._ports.task_session_key(agent_id, project_id, task_id)
        source = OpenClawWorkflowTimelineSource(
            self._timeline,
            self._ports.openclaw_sessions_dir(agent_id),
            self._ports.resolve_openclaw_session,
        )
        return source.is_active(agent_id, session_key)
