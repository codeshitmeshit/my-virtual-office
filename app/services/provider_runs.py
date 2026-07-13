"""Shared Provider run orchestration over repository, journal, and adapter ports."""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .provider_events import ProviderEventJournal, sanitize_payload
from .provider_ports import AdapterEvent, AdapterResult, ProviderAdapterRegistry, RunCommand, ThreadTaskLauncher
from .provider_registry import ProviderRunRepository, Reservation


@dataclass(frozen=True)
class StartOutcome:
    accepted: bool
    duplicate: bool
    run_id: str
    snapshot: dict[str, Any]


@dataclass(frozen=True)
class CancelOutcome:
    handled: bool
    result: dict[str, Any]
    snapshot: dict[str, Any] | None


@dataclass
class _RuntimeHandle:
    command: RunCommand
    adapter: Any
    generation: str
    cancel_event: threading.Event
    cancel_lock: threading.Lock
    cancel_called: bool = False


def _bounded_diagnostic(exc: BaseException) -> dict[str, str]:
    category = type(exc).__name__[:80]
    message = str(exc or category)
    cleaned = sanitize_payload({"error": message}) or {}
    safe = str(cleaned.get("error") or category)[:512]
    return {"error": safe, "errorCategory": category}


def _terminal_name(result: Mapping[str, Any], requested: str = "") -> str:
    requested = str(requested or "").lower()
    if requested in {"run.completed", "run.failed", "run.cancelled", "run.canceled"}:
        return "run.cancelled" if requested == "run.canceled" else requested
    status = str(result.get("status") or "").lower()
    if status in {"cancelled", "canceled", "cancelling", "canceling"}:
        return "run.cancelled"
    return "run.completed" if result.get("ok") else "run.failed"


class ProviderRunCoordinator:
    def __init__(
        self,
        repository: ProviderRunRepository,
        journal: ProviderEventJournal,
        adapters: ProviderAdapterRegistry | None = None,
        *,
        launcher=None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.repository = repository
        self.journal = journal
        self.adapters = adapters or ProviderAdapterRegistry()
        self.launcher = launcher or ThreadTaskLauncher()
        self._clock = clock or time.monotonic
        self._handles: dict[str, _RuntimeHandle] = {}
        self._handles_lock = threading.Lock()

    def start(self, command: RunCommand, *, adapter=None, compatibility_meta: Mapping[str, Any] | None = None) -> StartOutcome:
        resolved = adapter or self.adapters.resolve(command.provider_kind, command.provider_path, ("background_run",))
        if str(resolved.provider_kind).lower() != str(command.provider_kind).lower() or str(resolved.provider_path).lower() != str(command.provider_path).lower():
            raise ValueError("resolved adapter does not match command provider kind/path")
        if not bool(getattr(resolved.capabilities, "background_run", False)):
            raise ValueError("provider adapter does not support background runs")
        meta = dict(compatibility_meta or {})
        meta.update({
            "providerKind": command.provider_kind,
            "providerPath": command.provider_path,
            "agentId": command.agent_id,
            "profile": command.profile,
            "conversationId": command.conversation_id,
            "idempotencyKey": command.idempotency_key,
            "startedAt": int(time.time() * 1000),
            "done": False,
            "result": None,
        })
        reservation = self.repository.reserve_start(
            provider_kind=command.provider_kind,
            agent_id=command.agent_id,
            conversation_id=command.conversation_id,
            idempotency_key=command.idempotency_key,
            run_id=command.run_id,
            meta=meta,
        )
        if not reservation.created:
            return StartOutcome(True, True, reservation.token.run_id, reservation.snapshot)
        handle = _RuntimeHandle(command, resolved, reservation.token.generation, threading.Event(), threading.Lock())
        with self._handles_lock:
            self._handles[reservation.token.run_id] = handle
        try:
            self.launcher.launch(
                lambda: self._worker(reservation, handle),
                name=f"provider-run-{command.provider_kind}-{reservation.token.run_id}",
            )
        except Exception as exc:
            self._remove_handle(reservation.token.run_id, handle)
            result = {"ok": False, "status": "launch_failed", **_bounded_diagnostic(exc), "_status": 500}
            self._commit_terminal(reservation, result, result, "run.failed")
            return StartOutcome(False, False, reservation.token.run_id, self.repository.get(reservation.token.run_id) or reservation.snapshot)
        return StartOutcome(True, False, reservation.token.run_id, reservation.snapshot)

    def _worker(self, reservation: Reservation, handle: _RuntimeHandle) -> None:
        run_id = reservation.token.run_id
        command = handle.command
        self._publish(command.provider_kind, command.agent_id, command.conversation_id, "run.started", dict(command.start_payload), run_id)
        holder: dict[str, Any] = {}
        finished = threading.Event()

        def emit(event: AdapterEvent) -> bool:
            snapshot = self.repository.get(run_id)
            if not snapshot or snapshot.get("terminal") or snapshot.get("generation") != handle.generation:
                return False
            updates = dict(event.state_updates or {})
            if updates:
                transition = self.repository.update(run_id, generation=handle.generation, **updates)
                if not transition.applied:
                    return False
            return bool(self._publish(command.provider_kind, command.agent_id, command.conversation_id, event.name, dict(event.payload or {}), run_id))

        def call_adapter():
            try:
                holder["result"] = handle.adapter.run(command, emit, handle.cancel_event)
            except BaseException as exc:  # adapter failures must become bounded run failures
                holder["exception"] = exc
            finally:
                finished.set()

        adapter_thread = threading.Thread(target=call_adapter, daemon=True, name=f"provider-adapter-{run_id}")
        adapter_thread.start()
        timeout = max(0.001, float(command.timeout_sec or 0.001))
        if not finished.wait(timeout=timeout):
            handle.cancel_event.set()
            result = {"ok": False, "status": "timeout", "error": "Provider run timed out", "_status": 504}
            self._commit_terminal(reservation, result, result, "run.failed")
            self._remove_handle(run_id, handle)
            # A provider-specific cancel hook may involve a slow subprocess or
            # remote transport.  The timeout fence must not wait for that hook,
            # otherwise callers can observe a run stuck beyond its deadline.
            threading.Thread(
                target=self._invoke_cancel,
                args=(handle, self.repository.get(run_id) or {}, {"reason": "timeout"}),
                daemon=True,
                name=f"provider-timeout-cancel-{run_id}",
            ).start()
            return
        if "exception" in holder:
            result = {"ok": False, "status": "execution_failed", **_bounded_diagnostic(holder["exception"]), "_status": 500}
            self._commit_terminal(reservation, result, result, "run.failed")
            self._remove_handle(run_id, handle)
            return
        adapter_result = holder.get("result")
        if isinstance(adapter_result, AdapterResult):
            result = dict(adapter_result.result)
            terminal_payload = dict(adapter_result.terminal_payload or result)
            terminal_event = _terminal_name(result, adapter_result.terminal_event)
        else:
            result = dict(adapter_result) if isinstance(adapter_result, Mapping) else {"ok": False, "status": "invalid_result", "error": "Provider adapter returned an invalid result", "_status": 500}
            terminal_payload = dict(result)
            terminal_event = _terminal_name(result)
        self._commit_terminal(reservation, result, terminal_payload, terminal_event)
        self._remove_handle(run_id, handle)

    def _commit_terminal(self, reservation: Reservation, result: dict[str, Any], payload: dict[str, Any], event_name: str):
        transition = self.repository.complete(
            reservation.token.run_id,
            result,
            event_name=event_name,
            generation=reservation.token.generation,
        )
        if not transition.applied:
            return transition
        claimed = self.repository.claim_terminal_event(reservation.token.run_id, event_name, payload)
        if claimed.applied:
            self._publish(
                str(transition.snapshot.get("providerKind") or ""),
                str(transition.snapshot.get("agentId") or ""),
                str(transition.snapshot.get("conversationId") or ""),
                event_name,
                payload,
                reservation.token.run_id,
            )
        timer = threading.Timer(
            self.repository.retention_ms / 1000.0,
            self.repository.clear,
            args=(reservation.token.run_id,),
            kwargs={"generation": reservation.token.generation, "require_expired": True},
        )
        timer.daemon = True
        timer.start()
        return transition

    def cancel(self, run_id: str, payload: Mapping[str, Any] | None = None) -> CancelOutcome:
        run_id = str(run_id or "")
        snapshot = self.repository.get(run_id)
        if not snapshot:
            return CancelOutcome(False, {"ok": False, "status": "not_found", "error": "Provider run not found", "_status": 404}, None)
        if snapshot.get("terminal"):
            result = dict(snapshot.get("result") or {})
            return CancelOutcome(True, result, snapshot)
        with self._handles_lock:
            handle = self._handles.get(run_id)
        if not handle:
            return CancelOutcome(False, {"ok": False, "status": "unmanaged", "error": "Provider run has no active coordinator handle", "_status": 409}, snapshot)
        claim, cancel_token = self.repository.claim_cancel(run_id, generation=handle.generation)
        if not claim.applied:
            latest = claim.snapshot or self.repository.get(run_id)
            return CancelOutcome(True, dict((latest or {}).get("result") or {"ok": True, "status": "cancelling"}), latest)
        handle.cancel_event.set()
        result = self._invoke_cancel(handle, claim.snapshot or snapshot, dict(payload or {}))
        compatible = dict(result) if isinstance(result, Mapping) else {"ok": True, "status": "cancelled"}
        compatible.setdefault("status", "cancelled")
        if compatible.get("ok"):
            transition = self.repository.complete_cancel(run_id, cancel_token, compatible)
            terminal_event = "run.cancelled"
        else:
            transition = self.repository.complete(run_id, compatible, event_name="run.failed", generation=handle.generation)
            terminal_event = "run.failed"
        if transition.applied:
            claimed = self.repository.claim_terminal_event(run_id, terminal_event, compatible)
            if claimed.applied:
                self._publish(handle.command.provider_kind, handle.command.agent_id, handle.command.conversation_id, terminal_event, compatible, run_id)
        self._remove_handle(run_id, handle)
        return CancelOutcome(True, compatible if transition.applied else dict((transition.snapshot or {}).get("result") or compatible), transition.snapshot)

    def _invoke_cancel(self, handle: _RuntimeHandle, snapshot: Mapping[str, Any], payload: Mapping[str, Any]):
        with handle.cancel_lock:
            if handle.cancel_called:
                return {"ok": True, "status": "cancelling"}
            handle.cancel_called = True
        try:
            return handle.adapter.cancel(handle.command, snapshot, payload)
        except BaseException as exc:
            return {"ok": False, "status": "cancel_failed", **_bounded_diagnostic(exc), "_status": 500}

    def _remove_handle(self, run_id: str, handle: _RuntimeHandle) -> None:
        with self._handles_lock:
            if self._handles.get(run_id) is handle:
                self._handles.pop(run_id, None)

    def _publish(self, provider_kind: str, agent_id: str, conversation_id: str, event_name: str, payload: Mapping[str, Any], run_id: str):
        return self.journal.publish(provider_kind, agent_id, conversation_id, event_name, dict(payload or {}), run_id)

    def diagnostics(self) -> dict[str, Any]:
        with self._handles_lock:
            active = list(self._handles)
        return {
            "activeHandleCount": len(active),
            "activeRunDigests": [hashlib.sha256(run_id.encode()).hexdigest()[:12] for run_id in active[:100]],
            "repositoryRuns": len(self.repository.snapshots()),
            **self.journal.stats(),
        }
