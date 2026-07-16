"""Guarded configuration and runtime primitives for the Codex chat fast path."""

from __future__ import annotations

from collections import OrderedDict
import copy
from dataclasses import dataclass
import threading
import time
from typing import Any, Callable, Mapping

from .provider_events import sanitize_payload


TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}
FALSE_VALUES = {"0", "false", "no", "off", "disabled"}
TERMINAL_STATUSES = {"completed", "done", "success", "failed", "error", "cancelled", "canceled"}
MAX_LIVE_SCOPES = 4_096


@dataclass(frozen=True)
class CodexFastPathSettings:
    requested_enabled: bool = False
    enabled: bool = False
    valid: bool = True
    max_concurrent_turns: int = 1
    coalesce_min_ms: int = 33
    coalesce_max_ms: int = 100
    issues: tuple[str, ...] = ()

    def diagnostics(self) -> dict[str, Any]:
        return {
            "requestedEnabled": self.requested_enabled,
            "enabled": self.enabled,
            "valid": self.valid,
            "startupOnly": True,
            "maxConcurrentTurns": self.max_concurrent_turns,
            "streamCoalesceMinMs": self.coalesce_min_ms,
            "streamCoalesceMaxMs": self.coalesce_max_ms,
            "issues": list(self.issues),
        }


@dataclass
class _LiveScope:
    sequence: int = 0
    active: int = 0
    last_used_ns: int = 0
    last_event: dict[str, Any] | None = None


def classify_codex_event(event: Mapping[str, Any] | None) -> str:
    event = event if isinstance(event, Mapping) else {}
    event_type = str(event.get("type") or "").strip().lower()
    status = str(event.get("status") or "").strip().lower()
    if event_type in {"turn", "run"} and status in TERMINAL_STATUSES:
        return "terminal"
    if event_type in {"interaction", "approval"}:
        return "durable_key"
    if event_type in {"message", "assistant_message", "assistant", "text", "output"} and status in TERMINAL_STATUSES:
        return "durable_key"
    if event_type in {"reasoning", "thinking", "message", "assistant_message", "assistant", "text", "output", "activity", "tool", "command"}:
        return "transient"
    return "durable_key"


class CodexEventFastPath:
    """Bounded Codex event normalization without owning run or SSE state."""

    def __init__(
        self,
        settings: CodexFastPathSettings,
        *,
        max_scopes: int = MAX_LIVE_SCOPES,
        clock_ns: Callable[[], int] | None = None,
        sanitizer: Callable[[Any], Any] | None = None,
    ) -> None:
        self.settings = settings
        self.max_scopes = max(1, int(max_scopes))
        self._clock_ns = clock_ns or time.monotonic_ns
        self._sanitize = sanitizer or sanitize_payload
        self._lock = threading.Lock()
        self._scopes: OrderedDict[tuple[str, str, str], _LiveScope] = OrderedDict()
        self._conversation_sequences: OrderedDict[tuple[str, str], int] = OrderedDict()
        self._counters = {
            "disabledPassThrough": 0,
            "normalized": 0,
            "transient": 0,
            "durableKey": 0,
            "terminal": 0,
            "scopeEvictions": 0,
            "capacityBypass": 0,
        }

    @staticmethod
    def scope_key(agent_id: str, conversation_id: str, run_id: str) -> tuple[str, str, str]:
        return (
            str(agent_id or "")[:160],
            str(conversation_id or "")[:240],
            str(run_id or "")[:200],
        )

    def begin(self, agent_id: str, conversation_id: str, run_id: str, *, initial_sequence: int = 0) -> bool:
        if not self.settings.enabled:
            return False
        key = self.scope_key(agent_id, conversation_id, run_id)
        with self._lock:
            scope = self._get_or_create_locked(key)
            if scope is None:
                self._counters["capacityBypass"] += 1
                return False
            scope.active += 1
            scope.last_used_ns = self._clock_ns()
            sequence_key = key[:2]
            self._conversation_sequences[sequence_key] = max(
                self._conversation_sequences.get(sequence_key, 0),
                max(0, int(initial_sequence or 0)),
            )
            self._conversation_sequences.move_to_end(sequence_key)
            self._prune_sequences_locked()
            return True

    def end(self, agent_id: str, conversation_id: str, run_id: str) -> None:
        key = self.scope_key(agent_id, conversation_id, run_id)
        with self._lock:
            scope = self._scopes.get(key)
            if not scope:
                return
            scope.active = max(0, scope.active - 1)
            scope.last_used_ns = self._clock_ns()
            self._scopes.move_to_end(key)
            self._prune_locked()

    def process_event(
        self,
        agent_id: str,
        conversation_id: str,
        run_id: str,
        event: dict[str, Any],
        *,
        legacy_callback: Callable[[dict[str, Any]], Any] | None = None,
    ) -> Any:
        if not self.settings.enabled:
            with self._lock:
                self._counters["disabledPassThrough"] += 1
            return legacy_callback(event) if legacy_callback else event

        event_class = classify_codex_event(event)
        cleaned = self._sanitize(event)
        cleaned = copy.deepcopy(cleaned) if isinstance(cleaned, dict) else {}
        key = self.scope_key(agent_id, conversation_id, run_id)
        with self._lock:
            scope = self._get_or_create_locked(key)
            if scope is None:
                self._counters["capacityBypass"] += 1
                return legacy_callback(event) if legacy_callback else event
            sequence_key = key[:2]
            sequence = self._conversation_sequences.get(sequence_key, 0) + 1
            self._conversation_sequences[sequence_key] = sequence
            self._conversation_sequences.move_to_end(sequence_key)
            self._prune_sequences_locked()
            scope.sequence = sequence
            scope.last_used_ns = self._clock_ns()
            cleaned.setdefault("providerSequence", int(event.get("sequence") or 0))
            cleaned["sequence"] = sequence
            cleaned["agentId"] = key[0]
            cleaned["conversationId"] = key[1]
            if key[2]:
                cleaned.setdefault("runId", key[2])
            cleaned["eventClass"] = event_class
            scope.last_event = copy.deepcopy(cleaned)
            self._scopes.move_to_end(key)
            self._counters["normalized"] += 1
            counter = "transient" if event_class == "transient" else "terminal" if event_class == "terminal" else "durableKey"
            self._counters[counter] += 1
        return cleaned

    def live_snapshot(self, agent_id: str, conversation_id: str, run_id: str) -> dict[str, Any] | None:
        key = self.scope_key(agent_id, conversation_id, run_id)
        with self._lock:
            scope = self._scopes.get(key)
            return copy.deepcopy(scope.last_event) if scope and scope.last_event else None

    def live_events(self, agent_id: str, conversation_id: str, *, after: int = 0) -> list[dict[str, Any]]:
        prefix = self.scope_key(agent_id, conversation_id, "")[:2]
        with self._lock:
            events = [
                copy.deepcopy(scope.last_event)
                for key, scope in self._scopes.items()
                if key[:2] == prefix and scope.last_event and int(scope.last_event.get("sequence") or 0) > int(after or 0)
            ]
        return sorted(events, key=lambda item: int(item.get("sequence") or 0))

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            active = sum(scope.active for scope in self._scopes.values())
            return {
                **self.settings.diagnostics(),
                **self._counters,
                "liveScopes": len(self._scopes),
                "activeScopes": active,
                "maxLiveScopes": self.max_scopes,
            }

    def _get_or_create_locked(self, key: tuple[str, str, str]) -> _LiveScope | None:
        scope = self._scopes.get(key)
        if scope is not None:
            self._scopes.move_to_end(key)
            return scope
        self._prune_locked(required=1)
        if len(self._scopes) >= self.max_scopes:
            return None
        scope = _LiveScope(last_used_ns=self._clock_ns())
        self._scopes[key] = scope
        return scope

    def _prune_locked(self, required: int = 0) -> None:
        target = max(0, self.max_scopes - max(0, int(required)))
        for key, scope in list(self._scopes.items()):
            if len(self._scopes) <= target:
                break
            if scope.active == 0:
                self._scopes.pop(key, None)
                self._counters["scopeEvictions"] += 1

    def _prune_sequences_locked(self) -> None:
        while len(self._conversation_sequences) > self.max_scopes:
            self._conversation_sequences.popitem(last=False)


def _configured_value(environ: Mapping[str, Any], env_key: str, config: Mapping[str, Any], config_key: str, default: Any):
    raw = environ.get(env_key)
    if raw is not None and str(raw).strip() != "":
        return raw
    return config.get(config_key, default)


def _strict_bool(value: Any, default: bool, issue: str, issues: list[str]) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or str(value).strip() == "":
        return default
    normalized = str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    issues.append(issue)
    return default


def _bounded_int(value: Any, default: int, minimum: int, maximum: int, issue: str, issues: list[str]) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        issues.append(issue)
        return default
    if parsed < minimum or parsed > maximum:
        issues.append(issue)
        return default
    return parsed


def load_codex_fast_path_settings(environ: Mapping[str, Any], codex_config: Mapping[str, Any] | None = None) -> CodexFastPathSettings:
    codex_config = codex_config if isinstance(codex_config, Mapping) else {}
    nested = codex_config.get("fastPath")
    fast_config = nested if isinstance(nested, Mapping) else codex_config
    issues: list[str] = []
    requested_enabled = _strict_bool(
        _configured_value(environ, "VO_CODEX_CHAT_FAST_PATH_ENABLED", fast_config, "enabled", False),
        False,
        "invalid_enabled",
        issues,
    )
    max_turns = _bounded_int(
        _configured_value(environ, "VO_CODEX_MAX_CONCURRENT_TURNS", fast_config, "maxConcurrentTurns", 1),
        1,
        1,
        4,
        "invalid_max_concurrent_turns",
        issues,
    )
    minimum_ms = _bounded_int(
        _configured_value(environ, "VO_CODEX_STREAM_COALESCE_MIN_MS", fast_config, "streamCoalesceMinMs", 33),
        33,
        33,
        100,
        "invalid_coalesce_min_ms",
        issues,
    )
    maximum_ms = _bounded_int(
        _configured_value(environ, "VO_CODEX_STREAM_COALESCE_MAX_MS", fast_config, "streamCoalesceMaxMs", 100),
        100,
        33,
        100,
        "invalid_coalesce_max_ms",
        issues,
    )
    if maximum_ms < minimum_ms:
        issues.append("invalid_coalesce_window")
        minimum_ms, maximum_ms = 33, 100
    valid = not issues
    return CodexFastPathSettings(
        requested_enabled=requested_enabled,
        enabled=requested_enabled and valid,
        valid=valid,
        max_concurrent_turns=max_turns,
        coalesce_min_ms=minimum_ms,
        coalesce_max_ms=maximum_ms,
        issues=tuple(dict.fromkeys(issues)),
    )
