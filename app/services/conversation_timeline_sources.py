"""Injected, bounded, read-only sources for canonical conversation timelines."""

from __future__ import annotations

import copy
from collections import deque
from dataclasses import dataclass, field
from itertools import islice
from typing import Any, Iterable, Mapping, Protocol

from .conversation_timeline import (
    ConversationTimelineService,
    TimelineItem,
    TimelineQuery,
    TimelineScope,
)


MAX_CONTENT_BLOCKS = 100
MAX_BLOCK_TEXT = 128 * 1024
PUBLIC_SESSION_FIELDS = frozenset({"sessionId", "contextUsed", "contextWindow", "tokenUsage"})


class HistoryReader(Protocol):
    def __call__(self, scope: TimelineScope, limit: int) -> Iterable[Mapping[str, Any]]: ...


class ScopeReader(Protocol):
    def __call__(self, scope: TimelineScope) -> Any: ...


@dataclass(frozen=True)
class TimelineSourcePorts:
    provider_history: HistoryReader | None = None
    office_history: HistoryReader | None = None
    live_activity: HistoryReader | None = None
    session_metrics: ScopeReader | None = None
    active_state: ScopeReader | None = None


@dataclass(frozen=True)
class SourceFailure:
    source: str
    error_type: str


@dataclass(frozen=True)
class TimelineSourceSnapshot:
    groups: tuple[tuple[TimelineItem, ...], ...]
    session: Mapping[str, Any] = field(default_factory=dict)
    active: bool = False
    failures: tuple[SourceFailure, ...] = field(default_factory=tuple)
    candidates: int = 0


def _bounded_text(value: Any) -> str:
    return str(value or "")[:MAX_BLOCK_TEXT]


def _tool_result_value(block: Mapping[str, Any]) -> Any:
    for key in ("result", "output", "content", "text", "error"):
        if key in block:
            return copy.deepcopy(block[key])
    return ""


def parse_openclaw_content(content: Any) -> dict[str, Any]:
    """Parse supported OpenClaw blocks once without resolving files or sessions."""

    if isinstance(content, str):
        return {"text": _bounded_text(content), "thinking": "", "media": [], "tools": []}
    if not isinstance(content, (list, tuple)):
        return {"text": "", "thinking": "", "media": [], "tools": []}

    text_parts: list[str] = []
    thinking_parts: list[str] = []
    media: list[dict[str, Any]] = []
    tools: list[dict[str, Any]] = []
    indexed_tools: dict[str, dict[str, Any]] = {}
    for raw_block in content[:MAX_CONTENT_BLOCKS]:
        if not isinstance(raw_block, Mapping):
            continue
        block = dict(raw_block)
        block_type = str(block.get("type") or "").strip().lower().replace("_", "")
        if block_type in {"text", "outputtext"}:
            text_parts.append(_bounded_text(block.get("text") or block.get("content")))
        elif block_type in {"thinking", "reasoning"}:
            thinking_parts.append(_bounded_text(block.get("thinking") or block.get("text") or block.get("content")))
        elif block_type in {"image", "audio", "video", "file", "media"}:
            media.append(
                {
                    key: copy.deepcopy(block[key])
                    for key in ("type", "url", "path", "mimeType", "name", "alt")
                    if key in block
                }
            )
        elif block_type in {"toolcall", "tooluse"}:
            tool_id = str(block.get("id") or block.get("toolCallId") or "")
            tool = {
                "id": tool_id,
                "name": str(block.get("name") or block.get("toolName") or "tool"),
                "arguments": copy.deepcopy(block.get("arguments", block.get("input", {}))),
                "status": str(block.get("status") or "running"),
            }
            tools.append(tool)
            if tool_id:
                indexed_tools[tool_id] = tool
        elif block_type in {"toolresult", "toolresponse"}:
            tool_id = str(block.get("toolCallId") or block.get("id") or "")
            tool = indexed_tools.get(tool_id)
            if tool is None:
                tool = {"id": tool_id, "name": str(block.get("name") or "tool result"), "arguments": {}}
                tools.append(tool)
                if tool_id:
                    indexed_tools[tool_id] = tool
            error = copy.deepcopy(block.get("error") or "")
            tool["result"] = _tool_result_value(block)
            tool["error"] = error
            tool["status"] = "error" if error else "done"

    return {
        "text": "".join(text_parts),
        "thinking": "\n\n".join(part for part in thinking_parts if part),
        "media": media,
        "tools": tools,
    }


def normalize_source_record(provider_kind: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten a trusted Provider record into the raw canonical boundary."""

    envelope = dict(raw) if isinstance(raw, Mapping) else {}
    message = envelope.get("message") if isinstance(envelope.get("message"), Mapping) else {}
    record = {**envelope, **message}
    content = record.get("content")
    if isinstance(content, (str, list, tuple)):
        projected = parse_openclaw_content(content)
        record["text"] = record.get("text") or projected["text"]
        record["thinking"] = record.get("thinking") or projected["thinking"]
        record["media"] = list(record.get("media") or []) + projected["media"]
        record["tools"] = list(record.get("tools") or []) + projected["tools"]
    record["providerKind"] = record.get("providerKind") or provider_kind
    return record


def project_workflow_history(
    timeline: ConversationTimelineService,
    scope: TimelineScope,
    records: Iterable[Mapping[str, Any]],
    *,
    source: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Project durable Provider rows through canonical semantics and a legacy envelope."""

    projected: list[dict[str, Any]] = []
    normalized_limit = max(1, min(int(limit or 50), 50))
    bounded = tuple(deque(islice(records or (), 1_000), maxlen=normalized_limit))
    for ordinal, raw in enumerate(bounded):
        if not isinstance(raw, Mapping):
            continue
        normalized = normalize_source_record(scope.provider_kind, raw)
        compatible_source = str(raw.get("source") or source)
        item = timeline.item_from_record(scope, normalized, source=compatible_source, ordinal=ordinal, durable=True)
        message = copy.deepcopy(dict(raw))
        if "text" in raw or normalized.get("content") is not None:
            message["text"] = item.text
        if "thinking" in raw or normalized.get("content") is not None:
            message["thinking"] = item.thinking
        if "tools" in raw or normalized.get("content") is not None:
            message["tools"] = copy.deepcopy(list(item.tools))
        if "media" in raw or normalized.get("content") is not None:
            message["media"] = copy.deepcopy(list(item.media))
        if item.thinking or raw.get("reasoningStatus") is not None:
            message["reasoningStatus"] = item.status
        projected.append(message)
    return projected


class ConversationTimelineSourceReader:
    def __init__(self, timeline: ConversationTimelineService, ports: TimelineSourcePorts) -> None:
        self._timeline = timeline
        self._ports = ports

    def read(self, scope: TimelineScope, query: TimelineQuery) -> TimelineSourceSnapshot:
        failures: list[SourceFailure] = []
        groups: list[tuple[TimelineItem, ...]] = []
        candidates = 0
        source_specs = [
            ("provider-history", self._ports.provider_history, True, 0),
            ("office-history", self._ports.office_history, True, 10),
        ]
        if query.include_live:
            source_specs.append(("live-activity", self._ports.live_activity, False, 0))

        for source_name, reader, durable, priority in source_specs:
            if reader is None or candidates >= query.candidate_limit:
                continue
            remaining = query.candidate_limit - candidates
            try:
                raw_records = reader(scope, remaining)
                normalized = []
                inspected = 0
                for raw in islice(raw_records or (), remaining):
                    inspected += 1
                    if not isinstance(raw, Mapping):
                        continue
                    record = normalize_source_record(scope.provider_kind, raw)
                    if priority:
                        record["sourcePriority"] = max(priority, int(record.get("sourcePriority") or 0))
                    normalized.append(record)
                items = self._timeline.normalize_records(
                    scope,
                    normalized,
                    source=source_name,
                    durable=durable,
                    candidate_limit=remaining,
                )
                candidates += inspected
                groups.append(items)
            except Exception as exc:
                failures.append(SourceFailure(source_name, type(exc).__name__))

        session = self._read_session(scope, failures)
        active = self._read_active(scope, failures) if query.include_live else False
        return TimelineSourceSnapshot(tuple(groups), session, active, tuple(failures), candidates)

    def _read_session(self, scope: TimelineScope, failures: list[SourceFailure]) -> dict[str, Any]:
        if self._ports.session_metrics is None:
            return {}
        try:
            value = self._ports.session_metrics(scope)
            if not isinstance(value, Mapping):
                return {}
            return copy.deepcopy({key: value[key] for key in PUBLIC_SESSION_FIELDS if key in value})
        except Exception as exc:
            failures.append(SourceFailure("session-metrics", type(exc).__name__))
            return {}

    def _read_active(self, scope: TimelineScope, failures: list[SourceFailure]) -> bool:
        if self._ports.active_state is None:
            return False
        try:
            value = self._ports.active_state(scope)
            if isinstance(value, Mapping):
                return bool(value.get("active") or value.get("running") or value.get("sessionActive"))
            return bool(value)
        except Exception as exc:
            failures.append(SourceFailure("active-state", type(exc).__name__))
            return False
