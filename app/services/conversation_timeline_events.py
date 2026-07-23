"""Additive canonical projection for existing Provider live-event payloads."""

from __future__ import annotations

import copy
import threading
from collections import OrderedDict
from typing import Any, Mapping

from .conversation_timeline import ConversationTimelineService, ReasoningAccumulator, TimelineScope


TERMINAL_EVENT_STATUS = {
    "run.completed": "done",
    "run.failed": "failed",
    "run.cancelled": "cancelled",
    "run.canceled": "cancelled",
}


def _text(value: Any) -> str:
    return str(value) if isinstance(value, (str, int, float)) else ""


def _event_record(event_name: str, payload: Mapping[str, Any], event_id: Any) -> dict[str, Any]:
    name = str(event_name or "provider.activity").strip().lower()
    nested_activity = payload.get("activity") if isinstance(payload.get("activity"), Mapping) else {}
    progress = payload.get("progress") if isinstance(payload.get("progress"), Mapping) else {}
    source = dict(progress or nested_activity or payload)
    record = copy.deepcopy(source)
    record.pop("eventId", None)
    record.update({
        "providerKind": payload.get("providerKind"),
        "agentId": payload.get("agentId"),
        "conversationId": payload.get("conversationId"),
        "providerRunId": payload.get("runId") or source.get("runId"),
        "epochMs": source.get("epochMs") or source.get("ts") or payload.get("ts"),
        "sequence": source.get("sequence") or payload.get("sequence") or payload.get("eventId") or event_id,
        "_eventIdentity": source.get("id") or source.get("eventId") or payload.get("eventId") or event_id,
    })
    record.setdefault("role", "assistant")
    if str(record.get("role") or "").lower() != "user":
        record.setdefault("fromAgentId", payload.get("agentId") or "")
    if name.startswith("message."):
        record["itemKind"] = "message"
        record["id"] = source.get("messageId") or source.get("id") or payload.get("runId") or f"message:{event_id or 0}"
        record["text"] = _text(source.get("text") or source.get("delta") or source.get("reply") or source.get("output"))
    elif name.startswith("reasoning."):
        record["itemKind"] = "reasoning"
        record["id"] = source.get("itemId") or payload.get("runId") or "reasoning"
        record["thinking"] = _text(source.get("thinking") or source.get("text") or source.get("delta") or source.get("output"))
    elif name.startswith("tool."):
        record["itemKind"] = "tool"
        record["toolCallId"] = source.get("toolCallId") or source.get("itemId") or source.get("id") or ""
        record["tools"] = [{
            key: copy.deepcopy(source[key])
            for key in ("id", "toolCallId", "name", "arguments", "args", "args_preview", "result", "error", "status")
            if source.get(key) is not None
        }]
    elif name.startswith("approval."):
        record["itemKind"] = "approval"
        approval = payload.get("approval") if isinstance(payload.get("approval"), Mapping) else source
        record["approvalId"] = approval.get("approval_id") or approval.get("approvalId") or approval.get("id") or ""
        record["approval"] = copy.deepcopy(payload.get("approval") or source)
    elif name == "history.recovered" and progress:
        record["text"] = _text(progress.get("text") or progress.get("reply"))
        record["thinking"] = _text(progress.get("thinking"))
        record["tools"] = copy.deepcopy(list(progress.get("tools") or ()))
        record["approval"] = copy.deepcopy(progress.get("approval")) if isinstance(progress.get("approval"), Mapping) else None
    else:
        record["itemKind"] = "run"
        record["id"] = payload.get("runId") or source.get("runId") or f"{name}:{event_id or 0}"
        record["text"] = _text(source.get("reply") or source.get("text") or source.get("error"))
        record["thinking"] = _text(source.get("thinking"))
        record["tools"] = copy.deepcopy(list(source.get("tools") or ()))
        record["approval"] = copy.deepcopy(source.get("approval")) if isinstance(source.get("approval"), Mapping) else None
    if name in TERMINAL_EVENT_STATUS:
        record["status"] = TERMINAL_EVENT_STATUS[name]
    elif name == "run.started":
        record["status"] = "running"
    elif name in {"tool.completed", "tool.complete", "tool.result", "tool.end", "tool.ended", "approval.resolved", "approval.responded", "message.complete", "message.completed"}:
        record["status"] = "done"
    elif name in {"tool.failed", "tool.error", "message.error"}:
        record["status"] = "failed"
    elif name in {"tool.started", "tool.start", "tool.call", "tool.call.start", "approval.request", "approval.required", "message.delta", "message.delta.text"}:
        record["status"] = "running"
    if record.get("itemKind") == "tool" and record.get("tools"):
        record["tools"][0]["status"] = record.get("status") or "running"
    return record


class ProviderTimelineItemProjector:
    def __init__(self, timeline: ConversationTimelineService) -> None:
        self._timeline = timeline
        self._reasoning: OrderedDict[tuple[str, ...], ReasoningAccumulator] = OrderedDict()
        self._lock = threading.Lock()

    def _reasoning_record(
        self,
        scope: TimelineScope,
        payload: Mapping[str, Any],
        record: dict[str, Any],
        event_id: Any,
    ) -> dict[str, Any] | None:
        key = scope.key()
        with self._lock:
            accumulator = self._reasoning.get(key)
            if accumulator is None:
                accumulator = ReasoningAccumulator()
                self._reasoning[key] = accumulator
            self._reasoning.move_to_end(key)
            while len(self._reasoning) > 256:
                self._reasoning.popitem(last=False)
            event = {
                **record,
                "id": record.get("_eventIdentity") or payload.get("eventId") or event_id or record.get("id"),
                "text": record.get("thinking") or record.get("text") or "",
            }
            snapshot = accumulator.apply(scope.provider_kind, event)
        if snapshot is None:
            return None
        record.update({
            "id": f"reasoning:{snapshot.key}",
            "thinking": snapshot.text,
            "status": snapshot.status,
            "epochMs": snapshot.epoch_ms,
            "sequence": snapshot.sequence,
        })
        return record

    def project(
        self,
        event_name: str,
        payload: Mapping[str, Any],
        provider_kind: str,
        agent_id: str,
        conversation_id: str,
        event_id: Any = None,
    ) -> dict[str, Any] | None:
        if not isinstance(payload, Mapping):
            return None
        try:
            scope = TimelineScope.create(provider_kind, agent_id, "", conversation_id)
            record = _event_record(event_name, payload, event_id)
            record["providerKind"] = scope.provider_kind
            record["agentId"] = scope.agent_id
            record["conversationId"] = scope.conversation_ref
            if str(record.get("role") or "").lower() != "user" and not record.get("fromAgentId"):
                record["fromAgentId"] = scope.agent_id
            if str(event_name or "").lower().startswith("reasoning."):
                record = self._reasoning_record(scope, payload, record, event_id)
                if record is None:
                    return None
            item = self._timeline.item_from_record(
                scope,
                record,
                source="provider-events",
                durable=False,
            )
            return item.to_public_dict()
        except (TypeError, ValueError):
            return None
