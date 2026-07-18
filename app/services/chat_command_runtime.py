"""Bounded runtime collaborators for chat commands."""

from __future__ import annotations

import threading
from collections import Counter, OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from services.chat_commands import CommandRequest, CommandResult, CommandScope


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class CommandFeatureFlags:
    enabled: bool
    feishu_enabled: bool

    @classmethod
    def from_values(cls, global_value: Any, feishu_value: Any) -> "CommandFeatureFlags":
        enabled = _truthy(global_value)
        return cls(enabled, enabled and _truthy(feishu_value))

    def allows(self, surface: str) -> bool:
        return self.feishu_enabled if str(surface).startswith("feishu-") else self.enabled


class ScopedCommandReservations:
    def __init__(self, capacity: int = 4096) -> None:
        self._capacity = max(16, min(int(capacity), 16384))
        self._guard = threading.Lock()
        self._locks: OrderedDict[tuple[str, str, str, str], threading.Lock] = OrderedDict()

    def try_acquire(self, scope: CommandScope) -> bool:
        key = scope.key()
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            self._locks.move_to_end(key)
            self._prune(exclude=key)
        return lock.acquire(blocking=False)

    def release(self, scope: CommandScope) -> None:
        with self._guard:
            lock = self._locks.get(scope.key())
        if lock and lock.locked():
            lock.release()

    def _prune(self, exclude):
        while len(self._locks) > self._capacity:
            key, lock = next(iter(self._locks.items()))
            if key == exclude or lock.locked():
                self._locks.move_to_end(key)
                if all(candidate.locked() or item == exclude for item, candidate in self._locks.items()):
                    break
                continue
            self._locks.pop(key, None)

    def diagnostics(self) -> dict[str, int]:
        with self._guard:
            return {"scopes": len(self._locks), "locked": sum(lock.locked() for lock in self._locks.values())}


class CommandMetrics:
    ALLOWED_STATUSES = frozenset({"recognized", "success", "no_op", "busy", "unsupported", "failed", "stale", "indeterminate", "duplicate", "feedback_failed"})

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts = Counter()

    def increment(self, surface: str, provider: str, command: str, status: str) -> None:
        normalized_status = status if status in self.ALLOWED_STATUSES else "failed"
        normalized_surface = surface if surface in {"virtual-office", "feishu-dm", "feishu-group"} else "unknown"
        normalized_provider = provider if provider in {"codex", "hermes", "claude-code", "openclaw"} else "other"
        normalized_command = command if command in {"/new", "/compact"} else "other"
        with self._lock:
            self._counts[(normalized_surface, normalized_provider, normalized_command, normalized_status)] += 1

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = sorted(self._counts.items())
        return [{"surface": key[0], "provider": key[1], "command": key[2], "status": key[3], "count": value} for key, value in rows]


class CallbackCommandAuditPort:
    """Bind command orchestration to an existing authoritative journal/index."""

    def __init__(
        self,
        lookup: Callable[[CommandRequest], Mapping[str, Any] | CommandResult | None],
        append: Callable[[Mapping[str, Any]], Any],
        metrics: CommandMetrics | None = None,
    ) -> None:
        self._lookup = lookup
        self._append = append
        self._metrics = metrics

    def lookup(self, request: CommandRequest):
        result = self._lookup(request)
        if result is not None and self._metrics:
            self._metrics.increment(request.scope.surface, request.scope.provider_kind, request.command.value, "duplicate")
        return result

    def record_started(self, request: CommandRequest, operation_id: str, started_at_ms: int) -> None:
        self._append({
            "event": "command_started", "state": "started", "operationId": operation_id,
            "idempotencyKey": request.idempotency_key, "sourceMessageId": request.source_message_id,
            "providerKind": request.scope.provider_kind, "agentId": request.scope.agent_id,
            "profile": request.scope.profile, "conversationId": request.scope.conversation_id,
            "sourceSurface": request.scope.surface, "command": request.command.value, "startedAt": int(started_at_ms),
        })
        if self._metrics:
            self._metrics.increment(request.scope.surface, request.scope.provider_kind, request.command.value, "recognized")

    def record_terminal(self, request: CommandRequest, result: CommandResult) -> None:
        self._append({
            "event": "command_completed", "state": "terminal", "operationId": result.operation_id,
            "idempotencyKey": request.idempotency_key, "sourceMessageId": request.source_message_id,
            "providerKind": request.scope.provider_kind, "agentId": request.scope.agent_id,
            "profile": request.scope.profile, "conversationId": request.scope.conversation_id,
            "sourceSurface": request.scope.surface, "command": request.command.value,
            "ok": result.ok, "status": result.status, "changed": result.changed,
            "reply": result.reply[:2000], "durationMs": result.duration_ms,
            "nextConversationId": result.next_conversation_id,
            "nextSessionKey": result.next_session_key,
        })
        if self._metrics:
            self._metrics.increment(request.scope.surface, request.scope.provider_kind, request.command.value, result.status)
