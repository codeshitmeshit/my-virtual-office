"""Codex durable and transient sources for Project Execution workflow chat."""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from itertools import islice
from typing import Any, Callable, Iterable, Mapping

from .conversation_timeline import ConversationTimelineService, TimelineScope
from .conversation_timeline_sources import project_workflow_history


MAX_DURABLE_CANDIDATES = 1_000
MAX_LIVE_EVENTS = 4_000


class CodexWorkflowTimelineSource:
    """Project Codex history with one canonical reasoning accumulator."""

    def __init__(
        self,
        timeline: ConversationTimelineService,
        read_communications: Callable[[str, int], Iterable[Mapping[str, Any]]],
        project_communication: Callable[[Mapping[str, Any], str], Mapping[str, Any] | None],
        read_activity: Callable[[str, str], Iterable[Mapping[str, Any]]],
    ) -> None:
        self._timeline = timeline
        self._read_communications = read_communications
        self._project_communication = project_communication
        self._read_activity = read_activity

    @staticmethod
    def _in_scope(record: Mapping[str, Any], scope: TimelineScope) -> bool:
        conversation = str(record.get("conversationId") or "")
        agent = str(record.get("agentId") or "")
        return (not conversation or conversation == scope.conversation_ref) and (not agent or agent == scope.agent_id)

    def read_messages(self, scope: TimelineScope, *, max_messages: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(max_messages or 50), 50))
        durable = []
        rows = self._read_communications(scope.conversation_ref, limit)
        for row in islice(rows or (), min(limit, MAX_DURABLE_CANDIDATES)):
            if not isinstance(row, Mapping) or not self._in_scope(row, scope):
                continue
            message = self._project_communication(row, scope.agent_id)
            if isinstance(message, Mapping):
                durable.append(dict(message))

        events = self._read_activity(scope.agent_id, scope.conversation_ref)
        if isinstance(events, Sequence):
            bounded_events = events[-MAX_LIVE_EVENTS:]
        else:
            bounded_events = deque(islice(events or (), MAX_LIVE_EVENTS), maxlen=MAX_LIVE_EVENTS)
        reasoning_events = [
            event
            for event in bounded_events
            if isinstance(event, Mapping)
            and str(event.get("type") or "").lower() == "reasoning"
            and self._in_scope(event, scope)
        ]
        transient = [
            {
                "role": "assistant",
                "text": "",
                "thinking": snapshot.text,
                "reasoningStatus": snapshot.status,
                "status": snapshot.status,
                "ts": snapshot.epoch_ms,
                "epochMs": snapshot.epoch_ms,
                "sequence": snapshot.sequence,
                "fromAgentId": scope.agent_id,
                "source": "codex-activity",
                "durable": False,
            }
            for snapshot in self._timeline.accumulate_reasoning("codex", reasoning_events)
        ]
        combined = [*durable, *transient]
        combined.sort(key=lambda message: (
            int(message.get("epochMs") or message.get("ts") or 0),
            int(message.get("sequence") or 0),
        ))
        messages = project_workflow_history(
            self._timeline,
            scope,
            combined,
            source="codex",
            limit=50,
        )
        for message in messages:
            if message.get("source") == "codex-activity":
                message.pop("status", None)
                message.pop("sequence", None)
                message.pop("durable", None)
        messages.sort(key=lambda message: (
            int(message.get("epochMs") or message.get("ts") or 0),
            int(message.get("sequence") or 0),
        ))
        return messages[-limit:]
