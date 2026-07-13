"""Provider-neutral in-process run and idempotency authority."""

from __future__ import annotations

import copy
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable


DEFAULT_RETENTION_MS = 10 * 60 * 1000
MAX_IDEMPOTENCY_KEY = 256


def _copy_value(value: Any) -> Any:
    """Copy public state returned by the repository."""
    try:
        return copy.deepcopy(value)
    except (TypeError, ValueError):
        if isinstance(value, dict):
            return {key: _copy_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [_copy_value(item) for item in value]
        return value


def _terminal_event_name(result: dict[str, Any] | None, requested: str = "") -> str:
    requested = str(requested or "").lower()
    if requested in {"run.cancelled", "run.canceled"}:
        return "run.cancelled"
    if requested in {"run.completed", "run.failed"}:
        return requested
    result = result if isinstance(result, dict) else {}
    status = str(result.get("status") or "").lower()
    if status in {"cancelled", "canceled", "cancelling", "canceling"}:
        return "run.cancelled"
    return "run.completed" if result.get("ok") else "run.failed"


@dataclass(frozen=True)
class RunToken:
    run_id: str
    generation: str
    version: int


@dataclass(frozen=True)
class Reservation:
    created: bool
    token: RunToken
    snapshot: dict[str, Any]
    idempotency_scope: tuple[str, str, str, str] | None


@dataclass(frozen=True)
class Transition:
    applied: bool
    stale: bool
    token: RunToken | None
    snapshot: dict[str, Any] | None


class ProviderRunRepository:
    """Owns active run state, idempotency reservations, fencing, and retention."""

    def __init__(
        self,
        *,
        retention_ms: int = DEFAULT_RETENTION_MS,
        clock_ms: Callable[[], int] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.retention_ms = max(1, int(retention_ms))
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self._id_factory = id_factory or (lambda: uuid.uuid4().hex)
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._runs: dict[str, dict[str, Any]] = {}
        self._idempotency: dict[tuple[str, str], dict[str, Any]] = {}
        self._generation = 0

    @property
    def lock(self):
        return self._lock

    @property
    def condition(self):
        return self._condition

    def _new_generation(self) -> str:
        self._generation += 1
        return f"g{self._generation}-{self._id_factory()[:12]}"

    @staticmethod
    def _token(meta: dict[str, Any]) -> RunToken:
        return RunToken(str(meta["runId"]), str(meta["generation"]), int(meta["version"]))

    @staticmethod
    def _scope(provider_kind: str, agent_id: str, conversation_id: str, key: str):
        key = str(key or "").strip()
        if not key:
            return None
        if len(key) > MAX_IDEMPOTENCY_KEY:
            raise ValueError("idempotency key exceeds 256 characters")
        return (str(provider_kind or "").strip().lower(), str(agent_id or "").strip(), str(conversation_id or "").strip(), key)

    def reserve_start(
        self,
        *,
        provider_kind: str,
        agent_id: str,
        conversation_id: str = "",
        idempotency_key: str = "",
        run_id: str = "",
        meta: dict[str, Any] | None = None,
    ) -> Reservation:
        now = self._clock_ms()
        scope = self._scope(provider_kind, agent_id, conversation_id, idempotency_key)
        with self._condition:
            self._prune_locked(now, 256)
            if scope:
                existing = self._idempotency.get(("run", "\x1f".join(scope)))
                if existing and now - int(existing.get("ts") or 0) <= self.retention_ms:
                    current = self._runs.get(str(existing.get("runId") or ""))
                    if current:
                        return Reservation(False, self._token(current), _copy_value(current), scope)
                    self._idempotency.pop(("run", "\x1f".join(scope)), None)
            actual_run_id = str(run_id or self._id_factory()).strip()
            if not actual_run_id:
                raise ValueError("run_id is required")
            if actual_run_id in self._runs:
                current = self._runs[actual_run_id]
                return Reservation(False, self._token(current), _copy_value(current), scope)
            generation = self._new_generation()
            stored = _copy_value(meta or {})
            stored.pop("events", None)
            initial_done = bool(stored.get("done", False))
            initial_result = stored.get("result") if isinstance(stored.get("result"), dict) else {}
            stored.update({
                "runId": actual_run_id,
                "providerKind": str(provider_kind or stored.get("providerKind") or "").strip().lower(),
                "agentId": str(agent_id or stored.get("agentId") or "").strip(),
                "conversationId": str(conversation_id or stored.get("conversationId") or "").strip(),
                "generation": generation,
                "version": 1,
                "terminal": initial_done,
                "terminalEventName": _terminal_event_name(initial_result) if initial_done else "",
                "terminalEventPublished": False,
                "cancelState": "none",
                "cancelToken": "",
                "createdAt": int(stored.get("createdAt") or stored.get("startedAt") or now),
                "updatedAt": now,
                "cleanupDeadline": now + self.retention_ms if initial_done else 0,
                "done": initial_done,
            })
            self._runs[actual_run_id] = stored
            if scope:
                self._idempotency[("run", "\x1f".join(scope))] = {
                    "runId": actual_run_id, "ts": now, "scope": scope, "result": None,
                }
            self._condition.notify_all()
            return Reservation(True, self._token(stored), _copy_value(stored), scope)

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            current = self._runs.get(str(run_id or ""))
            return _copy_value(current) if current else None

    def snapshots(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {run_id: _copy_value(meta) for run_id, meta in self._runs.items()}

    def find_active(self, provider_kind: str, *, agent_ids=(), profile: str = "") -> dict[str, Any] | None:
        normalized_provider = str(provider_kind or "").strip().lower()
        normalized_agents = {str(value) for value in agent_ids if str(value or "").strip()}
        normalized_profile = str(profile or "").strip()
        with self._lock:
            for meta in reversed(list(self._runs.values())):
                if str(meta.get("providerKind") or "").lower() != normalized_provider or meta.get("terminal"):
                    continue
                if normalized_agents and normalized_agents.intersection({str(meta.get("agentId") or ""), str(meta.get("agentKey") or "")}):
                    return _copy_value(meta)
                if normalized_profile and normalized_profile == str(meta.get("profile") or ""):
                    return _copy_value(meta)
        return None

    def update(self, run_id: str, *, generation: str = "", expected_version: int | None = None, **updates) -> Transition:
        if updates.get("done"):
            result = updates.get("result") if isinstance(updates.get("result"), dict) else {}
            transition = self.complete(run_id, result, generation=generation, expected_version=expected_version)
            remaining = {key: value for key, value in updates.items() if key not in {"done", "result"} and value is not None}
            if remaining and transition.snapshot:
                return self.update(run_id, generation=transition.token.generation if transition.token else generation, **remaining)
            return transition
        with self._condition:
            current = self._runs.get(str(run_id or ""))
            if not current:
                return Transition(False, True, None, None)
            if generation and current["generation"] != generation:
                return Transition(False, True, self._token(current), _copy_value(current))
            if expected_version is not None and current["version"] != expected_version:
                return Transition(False, True, self._token(current), _copy_value(current))
            if current.get("terminal"):
                return Transition(False, True, self._token(current), _copy_value(current))
            current.update({key: _copy_value(value) for key, value in updates.items() if value is not None})
            current["version"] += 1
            current["updatedAt"] = self._clock_ms()
            self._condition.notify_all()
            return Transition(True, False, self._token(current), _copy_value(current))

    def complete(
        self,
        run_id: str,
        result: dict[str, Any] | None,
        *,
        event_name: str = "",
        generation: str = "",
        expected_version: int | None = None,
    ) -> Transition:
        now = self._clock_ms()
        with self._condition:
            current = self._runs.get(str(run_id or ""))
            if not current:
                return Transition(False, True, None, None)
            if generation and current["generation"] != generation:
                return Transition(False, True, self._token(current), _copy_value(current))
            if expected_version is not None and current["version"] != expected_version:
                return Transition(False, True, self._token(current), _copy_value(current))
            if current.get("terminal"):
                return Transition(False, True, self._token(current), _copy_value(current))
            compatible_result = _copy_value(result or {})
            requested_terminal = _terminal_event_name(compatible_result, event_name)
            if current.get("terminalEventPublished") and current.get("terminalEventName") != requested_terminal:
                return Transition(False, True, self._token(current), _copy_value(current))
            current.update({
                "terminal": True,
                "done": True,
                "result": compatible_result,
                "terminalEventName": requested_terminal,
                "version": current["version"] + 1,
                "updatedAt": now,
                "cleanupDeadline": now + self.retention_ms,
                "cancelState": "completed" if current.get("cancelState") == "requested" else current.get("cancelState", "none"),
            })
            for entry in self._idempotency.values():
                if entry.get("runId") == current["runId"]:
                    entry["result"] = _copy_value(compatible_result)
                    entry["ts"] = now
            self._condition.notify_all()
            return Transition(True, False, self._token(current), _copy_value(current))

    def claim_terminal_event(self, run_id: str, event_name: str, payload: dict[str, Any] | None = None) -> Transition:
        with self._condition:
            current = self._runs.get(str(run_id or ""))
            if not current:
                return Transition(False, True, None, None)
            canonical = _terminal_event_name(payload, event_name)
            if current.get("terminalEventPublished"):
                return Transition(False, True, self._token(current), _copy_value(current))
            if current.get("terminal") and current.get("terminalEventName") and canonical != current.get("terminalEventName"):
                return Transition(False, True, self._token(current), _copy_value(current))
            if not current.get("terminal") or not current.get("terminalEventName"):
                current["terminalEventName"] = canonical
            current["terminalEventPublished"] = True
            current["version"] += 1
            current["updatedAt"] = self._clock_ms()
            self._condition.notify_all()
            return Transition(True, False, self._token(current), _copy_value(current))

    def claim_cancel(self, run_id: str, *, generation: str = "") -> tuple[Transition, str]:
        with self._condition:
            current = self._runs.get(str(run_id or ""))
            if not current:
                return Transition(False, True, None, None), ""
            if generation and current["generation"] != generation:
                return Transition(False, True, self._token(current), _copy_value(current)), ""
            if current.get("terminal") or current.get("cancelState") == "requested":
                return Transition(False, True, self._token(current), _copy_value(current)), str(current.get("cancelToken") or "")
            token = self._id_factory()
            current.update({"cancelState": "requested", "cancelToken": token, "version": current["version"] + 1, "updatedAt": self._clock_ms()})
            self._condition.notify_all()
            return Transition(True, False, self._token(current), _copy_value(current)), token

    def complete_cancel(self, run_id: str, cancel_token: str, result: dict[str, Any] | None = None) -> Transition:
        with self._lock:
            current = self._runs.get(str(run_id or ""))
            if not current or current.get("cancelToken") != cancel_token or current.get("cancelState") != "requested":
                return Transition(False, True, self._token(current) if current else None, _copy_value(current) if current else None)
            generation = current["generation"]
        compatible = {"ok": False, "status": "cancelled", **(result or {})}
        compatible.setdefault("status", "cancelled")
        return self.complete(run_id, compatible, event_name="run.cancelled", generation=generation)

    def clear(self, run_id: str, *, generation: str = "", require_expired: bool = False) -> bool:
        now = self._clock_ms()
        with self._condition:
            current = self._runs.get(str(run_id or ""))
            if not current or (generation and current["generation"] != generation):
                return False
            if require_expired and (not current.get("terminal") or int(current.get("cleanupDeadline") or 0) > now):
                return False
            self._runs.pop(str(run_id), None)
            self._condition.notify_all()
            return True

    def prune(self, *, max_items: int = 256) -> dict[str, int]:
        with self._condition:
            return self._prune_locked(self._clock_ms(), max(1, int(max_items)))

    def _prune_locked(self, now: int, max_items: int) -> dict[str, int]:
        removed_runs = 0
        removed_idempotency = 0
        for run_id, meta in list(self._runs.items()):
            if removed_runs >= max_items:
                break
            if meta.get("terminal") and int(meta.get("cleanupDeadline") or 0) <= now:
                self._runs.pop(run_id, None)
                removed_runs += 1
        for key, entry in list(self._idempotency.items()):
            if removed_idempotency >= max_items:
                break
            if now - int(entry.get("ts") or 0) > self.retention_ms or not self._runs.get(str(entry.get("runId") or "")):
                self._idempotency.pop(key, None)
                removed_idempotency += 1
        if removed_runs or removed_idempotency:
            self._condition.notify_all()
        return {"runs": removed_runs, "idempotency": removed_idempotency}

    def wait_for_change(self, timeout: float = 1.0) -> None:
        with self._condition:
            self._condition.wait(timeout=max(0.0, float(timeout)))
