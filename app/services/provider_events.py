"""Bounded Provider event normalization, indexing, replay, and waiting."""

from __future__ import annotations

import copy
import re
import threading
import time
from collections import OrderedDict, defaultdict, deque
from typing import Any, Callable


DEFAULT_MAX_EVENTS = 4000
MAX_STRING = 8192
MAX_LIST = 200
MAX_FIELDS = 100
MAX_DEPTH = 6
TERMINAL_EVENTS = {"run.completed", "run.failed", "run.cancelled"}
CANONICAL_EVENTS = {
    "run.started", "run.completed", "run.failed", "run.cancelled",
    "run.native.started", "run.queued", "run.running", "run.stop_requested",
    "message.complete", "message.completed", "message.delta", "message.delta.text", "message.error",
    "reasoning.available", "reasoning.delta",
    "tool.started", "tool.completed", "tool.failed", "session.metrics",
    "tool.call", "tool.call.start", "tool.complete", "tool.end", "tool.ended", "tool.error",
    "tool.generating", "tool.progress", "tool.result", "tool.start", "tool.update", "tool.updated",
    "approval.required", "approval.request", "approval.resolved", "approval.responded",
    "provider.snapshot", "provider.heartbeat", "provider.activity",
    "history.recovered", "turn.stream", "clarify.request", "secret.request", "sudo.request",
    "session.active_list", "session.create", "session.message", "session.resume", "session.tool",
}
SAFE_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")
SENSITIVE_KEY = re.compile(r"(?:authorization|cookie|credential|password|secret|token|api.?key|raw.?request|raw.?response|transcript|prompt)$", re.I)
SECRET_VALUE = re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9._-]{12,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)", re.I)
ABSOLUTE_PATH = re.compile(r"(?:^|[\s'\"])(?:/Users/|/home/|/root/|/private/|[A-Za-z]:\\)")


def canonical_event_name(value: Any) -> str:
    name = str(value or "provider.activity").strip().lower()
    if name == "run.canceled":
        return "run.cancelled"
    return name if name in CANONICAL_EVENTS else "provider.activity"


def _sanitize_string(value: str) -> str:
    value = str(value)
    if SECRET_VALUE.search(value):
        return "[redacted]"
    if ABSOLUTE_PATH.search(value):
        return "[redacted-path]"
    if len(value) > MAX_STRING:
        return value[: MAX_STRING - 1] + "…"
    return value


def sanitize_payload(value: Any, *, depth: int = 0, key: str = "") -> Any:
    if depth > MAX_DEPTH:
        return "[truncated]"
    if key and (not SAFE_KEY.fullmatch(key) or SENSITIVE_KEY.search(key)):
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _sanitize_string(value)
    if isinstance(value, dict):
        result = {}
        for raw_key, item in list(value.items())[:MAX_FIELDS]:
            normalized_key = str(raw_key)
            cleaned = sanitize_payload(item, depth=depth + 1, key=normalized_key)
            if cleaned is not None:
                result[normalized_key] = cleaned
        return result
    if isinstance(value, (list, tuple, deque)):
        return [sanitize_payload(item, depth=depth + 1) for item in list(value)[:MAX_LIST]]
    return _sanitize_string(str(value))


class ProviderEventJournal:
    """One global cursor with bounded, eviction-consistent scope indexes."""

    def __init__(self, *, max_events: int = DEFAULT_MAX_EVENTS, clock_ms: Callable[[], int] | None = None) -> None:
        self.max_events = max(1, int(max_events))
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._events: deque[dict[str, Any]] = deque()
        self._by_id: dict[int, dict[str, Any]] = {}
        self._run_index: dict[str, deque[int]] = defaultdict(deque)
        self._conversation_index: dict[tuple[str, str, str], deque[int]] = defaultdict(deque)
        self._next_event_id = 0
        self._terminal_by_run: OrderedDict[str, int] = OrderedDict()

    @property
    def lock(self):
        return self._lock

    @property
    def condition(self):
        return self._condition

    @property
    def next_event_id(self):
        with self._lock:
            return self._next_event_id

    @property
    def compatibility_event_log(self):
        return self._events

    def publish(
        self,
        provider_kind: str,
        agent_id: str,
        conversation_id: str,
        event_name: str,
        payload: dict[str, Any] | None = None,
        run_id: str = "",
    ) -> dict[str, Any] | None:
        provider_kind = str(provider_kind or "").strip().lower()[:80]
        agent_id = str(agent_id or "").strip()[:160]
        conversation_id = str(conversation_id or "").strip()[:200]
        run_id = str(run_id or "").strip()[:200]
        name = canonical_event_name(event_name)
        cleaned = sanitize_payload(payload if isinstance(payload, dict) else {})
        cleaned = cleaned if isinstance(cleaned, dict) else {}
        cleaned.setdefault("providerKind", provider_kind)
        cleaned.setdefault("agentId", agent_id)
        cleaned.setdefault("conversationId", conversation_id)
        if run_id:
            cleaned.setdefault("runId", run_id)
        with self._condition:
            if run_id and name in TERMINAL_EVENTS and run_id in self._terminal_by_run:
                existing = self._by_id.get(self._terminal_by_run[run_id])
                return copy.deepcopy(existing) if existing else None
            self._next_event_id += 1
            event_id = self._next_event_id
            cleaned["eventId"] = event_id
            item = {
                "id": event_id,
                "event": name,
                "providerKind": provider_kind,
                "agentId": agent_id,
                "conversationId": conversation_id,
                "runId": run_id,
                "data": cleaned,
                "ts": self._clock_ms(),
            }
            self._events.append(item)
            self._by_id[event_id] = item
            if run_id:
                self._run_index[run_id].append(event_id)
            self._conversation_index[(provider_kind, agent_id, conversation_id)].append(event_id)
            if run_id and name in TERMINAL_EVENTS:
                self._terminal_by_run[run_id] = event_id
                self._terminal_by_run.move_to_end(run_id)
                while len(self._terminal_by_run) > self.max_events:
                    self._terminal_by_run.popitem(last=False)
            while len(self._events) > self.max_events:
                self._evict_left()
            self._condition.notify_all()
            return copy.deepcopy(item)

    def _evict_left(self) -> None:
        item = self._events.popleft()
        event_id = int(item["id"])
        self._by_id.pop(event_id, None)
        run_id = str(item.get("runId") or "")
        if run_id:
            self._discard_index(self._run_index, run_id, event_id)
        scope = (str(item.get("providerKind") or ""), str(item.get("agentId") or ""), str(item.get("conversationId") or ""))
        self._discard_index(self._conversation_index, scope, event_id)

    @staticmethod
    def _discard_index(index, key, event_id) -> None:
        ids = index.get(key)
        if not ids:
            return
        if ids and ids[0] == event_id:
            ids.popleft()
        else:
            try:
                ids.remove(event_id)
            except ValueError:
                pass
        if not ids:
            index.pop(key, None)

    def _record_refs(self, ids, after: int) -> list[dict[str, Any]]:
        return [self._by_id[event_id] for event_id in ids if event_id > after and event_id in self._by_id]

    @staticmethod
    def _copy_records(items) -> list[dict[str, Any]]:
        return [copy.deepcopy(item) for item in items]

    def events_after(self, after: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            items = [item for item in self._events if int(item["id"]) > int(after or 0)]
        return self._copy_records(items)

    def run_events_after(self, run_id: str, after: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            items = self._record_refs(self._run_index.get(str(run_id or ""), ()), int(after or 0))
        return self._copy_records(items)

    def conversation_events_after(self, provider_kind: str, agent_id: str, conversation_id: str, after: int = 0) -> list[dict[str, Any]]:
        scope = (str(provider_kind or "").strip().lower(), str(agent_id or "").strip(), str(conversation_id or "").strip())
        with self._lock:
            direct = list(self._conversation_index.get(scope, ()))
            if conversation_id:
                direct.extend(self._conversation_index.get((scope[0], scope[1], ""), ()))
            items = self._record_refs(sorted(set(direct)), int(after or 0))
        return self._copy_records(items)

    def wait_for_run_events(self, run_id: str, after: int, timeout: float = 1.0):
        with self._condition:
            items = self._record_refs(self._run_index.get(str(run_id or ""), ()), int(after or 0))
            if items:
                selected = items
            else:
                self._condition.wait(timeout=max(0.0, float(timeout)))
                selected = self._record_refs(self._run_index.get(str(run_id or ""), ()), int(after or 0))
        return self._copy_records(selected)

    def wait_for_conversation_events(self, provider_kind: str, agent_id: str, conversation_id: str, after: int, timeout: float = 1.0):
        scope = (str(provider_kind or "").strip().lower(), str(agent_id or "").strip(), str(conversation_id or "").strip())
        with self._condition:
            ids = list(self._conversation_index.get(scope, ())) + list(self._conversation_index.get((scope[0], scope[1], ""), ()))
            items = self._record_refs(sorted(set(ids)), int(after or 0))
            if items:
                selected = items
            else:
                self._condition.wait(timeout=max(0.0, float(timeout)))
                ids = list(self._conversation_index.get(scope, ())) + list(self._conversation_index.get((scope[0], scope[1], ""), ()))
                selected = self._record_refs(sorted(set(ids)), int(after or 0))
        return self._copy_records(selected)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "retainedEvents": len(self._events),
                "nextEventId": self._next_event_id,
                "runIndexes": len(self._run_index),
                "conversationIndexes": len(self._conversation_index),
                "terminalRuns": len(self._terminal_by_run),
            }
