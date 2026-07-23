"""HTTP Server-Sent Events transport over provider repositories and journals."""

from __future__ import annotations

import json
import time
from typing import Any, Callable

try:
    from services.provider_events import sanitize_payload
except ModuleNotFoundError:  # Package import in isolated unit tests.
    from app.services.provider_events import sanitize_payload


class ProviderSSETransport:
    """Frame repository snapshots and indexed journal replay as SSE.

    This adapter owns HTTP headers, cursor parsing, framing, heartbeat cadence,
    and disconnect handling. It never starts provider work or mutates run state.
    """

    def __init__(
        self,
        repository,
        journal,
        *,
        provider_kind_of: Callable[[dict[str, Any], str], str],
        pending_lookup: Callable[[str, str, str], dict[str, Any] | None] | None = None,
        recovery_lookup: Callable[[str, str, str], dict[str, Any] | None] | None = None,
        clock: Callable[[], float] | None = None,
        telemetry=None,
        timeline_item_projector: Callable[..., dict[str, Any] | None] | None = None,
    ) -> None:
        self.repository = repository
        self.journal = journal
        self.provider_kind_of = provider_kind_of
        self.pending_lookup = pending_lookup or (lambda *_args: None)
        self.recovery_lookup = recovery_lookup or (lambda *_args: None)
        self.clock = clock or time.time
        self.telemetry = telemetry
        self.timeline_item_projector = timeline_item_projector

    def _payload(self, event_name, payload, provider_kind, agent_id, conversation_id, event_id=None):
        compatible = dict(payload) if isinstance(payload, dict) else {}
        if self.timeline_item_projector is None:
            return compatible
        try:
            item = self.timeline_item_projector(
                event_name,
                compatible,
                provider_kind,
                agent_id,
                conversation_id,
                event_id,
            )
        except Exception:
            item = None
        if isinstance(item, dict):
            compatible.setdefault("timelineItem", item)
        return compatible

    @staticmethod
    def _cursor(handler, after=0) -> int:
        try:
            header_cursor = int(handler.headers.get("Last-Event-ID") or 0)
        except (AttributeError, TypeError, ValueError):
            header_cursor = 0
        try:
            query_cursor = int(after or 0)
        except (TypeError, ValueError):
            query_cursor = 0
        return max(0, header_cursor, query_cursor)

    @staticmethod
    def write_event(handler, event_name, payload, event_id=None) -> None:
        cleaned = sanitize_payload(payload if isinstance(payload, dict) else {})
        encoded = json.dumps(cleaned if isinstance(cleaned, dict) else {}, ensure_ascii=False, default=str)
        prefix = f"id: {int(event_id)}\n" if event_id else ""
        handler.wfile.write(f"{prefix}event: {event_name}\ndata: {encoded}\n\n".encode("utf-8"))
        handler.wfile.flush()

    @staticmethod
    def _sse_headers(handler, status=200, *, no_transform=False) -> None:
        handler.send_response(status)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache, no-transform" if no_transform else "no-cache")
        if status == 200:
            handler.send_header("Connection", "keep-alive")
        handler.send_header("Access-Control-Allow-Origin", "*")
        if no_transform:
            handler.send_header("X-Accel-Buffering", "no")
        handler.end_headers()

    def stream_run(self, handler, run_id, missing_provider_label="Provider", after=0) -> None:
        run_id = str(run_id or "")
        meta = self.repository.get(run_id)
        if not meta:
            self._sse_headers(handler, 404)
            payload = json.dumps({"error": f"{missing_provider_label} run not found"}, ensure_ascii=False)
            handler.wfile.write(f"event: run.failed\ndata: {payload}\n\n".encode("utf-8"))
            return
        telemetry_enabled = str(self.provider_kind_of(meta, run_id) or "").strip().lower() == "codex"
        provider_kind = str(self.provider_kind_of(meta, run_id) or "").strip().lower()
        agent_id = str(meta.get("agentId") or "")
        conversation_id = str(meta.get("conversationId") or "")

        self._sse_headers(handler, 200)
        cursor = self._cursor(handler, after)
        last_keepalive = self.clock()
        try:
            while True:
                items = self.journal.wait_for_run_events(run_id, cursor, timeout=0.5)
                if not items:
                    meta = self.repository.get(run_id) or meta
                    if meta.get("done") or meta.get("terminal"):
                        result = meta.get("result") if isinstance(meta.get("result"), dict) else {}
                        status = str(result.get("status") or "").lower()
                        event_name = "run.completed" if result.get("ok") else ("run.cancelled" if status in {"cancelled", "canceled"} else "run.failed")
                        payload = dict(result)
                        payload.setdefault("runId", run_id)
                        payload.setdefault("agentId", meta.get("agentId") or "")
                        payload.setdefault("profile", meta.get("profile") or "")
                        self.write_event(handler, event_name, self._payload(event_name, payload, provider_kind, agent_id, conversation_id))
                        if self.telemetry is not None and telemetry_enabled:
                            self.telemetry.mark(run_id, "sse_written")
                            self.telemetry.mark(run_id, "terminal_sse_written")
                        handler.close_connection = True
                        break
                    if self.clock() - last_keepalive >= 10:
                        handler.wfile.write(b": keepalive\n\n")
                        handler.wfile.flush()
                        last_keepalive = self.clock()
                    continue
                for item in items:
                    cursor = max(cursor, int(item.get("id") or 0))
                    event_name = str(item.get("event") or "message")
                    self.write_event(handler, event_name, self._payload(
                        event_name,
                        item.get("data") or {},
                        item.get("providerKind") or provider_kind,
                        item.get("agentId") or agent_id,
                        item.get("conversationId") or conversation_id,
                        item.get("id"),
                    ), item.get("id"))
                    if self.telemetry is not None and telemetry_enabled:
                        self.telemetry.mark(run_id, "sse_written")
                        if event_name in {"run.completed", "run.failed", "run.cancelled", "run.canceled"}:
                            self.telemetry.mark(run_id, "terminal_sse_written")
                    if event_name in {"run.completed", "run.failed", "run.cancelled", "run.canceled"}:
                        handler.close_connection = True
                        return
        except (BrokenPipeError, ConnectionError, OSError):
            handler.close_connection = True
            return

    def stream_conversation(self, handler, provider_kind, agent_id, conversation_id, after=0) -> None:
        provider_kind = str(provider_kind or "").strip().lower()
        agent_id = str(agent_id or "").strip()
        conversation_id = str(conversation_id or "").strip()
        if provider_kind not in {"codex", "hermes", "claude-code"} or not agent_id or not conversation_id:
            handler.send_response(400)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Access-Control-Allow-Origin", "*")
            handler.end_headers()
            handler.wfile.write(json.dumps({"ok": False, "error": "provider, agentId and conversationId are required"}).encode("utf-8"))
            return
        telemetry_enabled = provider_kind == "codex"

        cursor = self._cursor(handler, after)
        current_cursor = self.journal.next_event_id
        active_runs = [
            {
                "runId": meta.get("runId") or run_id,
                "startedAt": meta.get("startedAt") or 0,
                "status": "running",
            }
            for run_id, meta in self.repository.snapshots().items()
            if isinstance(meta, dict)
            and not meta.get("done")
            and not meta.get("terminal")
            and self.provider_kind_of(meta, run_id) == provider_kind
            and str(meta.get("agentId") or "") == agent_id
            and str(meta.get("conversationId") or "") == conversation_id
        ]
        if cursor <= 0:
            cursor = current_cursor

        self._sse_headers(handler, 200, no_transform=True)
        snapshot = {
            "ok": True,
            "providerKind": provider_kind,
            "agentId": agent_id,
            "conversationId": conversation_id,
            "activeRuns": active_runs,
            "eventId": cursor,
            "ts": int(self.clock() * 1000),
        }
        last_keepalive = self.clock()
        try:
            self.write_event(handler, "provider.snapshot", self._payload(
                "provider.snapshot", snapshot, provider_kind, agent_id, conversation_id, cursor
            ), cursor if cursor > 0 else None)
            try:
                pending = self.pending_lookup(provider_kind, agent_id, conversation_id)
            except Exception:
                pending = None
            if isinstance(pending, dict):
                approval_payload = {
                    "providerKind": provider_kind,
                    "agentId": agent_id,
                    "conversationId": conversation_id,
                    "approval": pending,
                    "pending_count": 1,
                }
                self.write_event(handler, "approval.request", self._payload(
                    "approval.request", approval_payload, provider_kind, agent_id, conversation_id
                ))
            try:
                progress = self.recovery_lookup(provider_kind, agent_id, conversation_id)
            except Exception:
                progress = None
            if isinstance(progress, dict):
                recovery_payload = {
                    "providerKind": provider_kind,
                    "agentId": agent_id,
                    "conversationId": conversation_id,
                    "progress": progress,
                    "eventId": cursor,
                }
                self.write_event(handler, "history.recovered", self._payload(
                    "history.recovered", recovery_payload, provider_kind, agent_id, conversation_id, cursor
                ))

            while True:
                items = self.journal.wait_for_conversation_events(provider_kind, agent_id, conversation_id, cursor, timeout=1.0)
                if items:
                    for item in items:
                        cursor = max(cursor, int(item.get("id") or 0))
                        event_name = item.get("event") or "message"
                        self.write_event(handler, event_name, self._payload(
                            event_name,
                            item.get("data") or {},
                            item.get("providerKind") or provider_kind,
                            item.get("agentId") or agent_id,
                            item.get("conversationId") or conversation_id,
                            item.get("id"),
                        ), item.get("id"))
                        if self.telemetry is not None and telemetry_enabled and item.get("runId"):
                            self.telemetry.mark(item.get("runId"), "sse_written")
                            if item.get("event") in {"run.completed", "run.failed", "run.cancelled", "run.canceled"}:
                                self.telemetry.mark(item.get("runId"), "terminal_sse_written")
                    continue
                if self.clock() - last_keepalive >= 10:
                    heartbeat_payload = {
                        "providerKind": provider_kind,
                        "agentId": agent_id,
                        "conversationId": conversation_id,
                        "eventId": cursor,
                        "ts": int(self.clock() * 1000),
                    }
                    self.write_event(handler, "provider.heartbeat", self._payload(
                        "provider.heartbeat", heartbeat_payload, provider_kind, agent_id, conversation_id, cursor
                    ))
                    last_keepalive = self.clock()
        except (BrokenPipeError, ConnectionError, OSError):
            handler.close_connection = True
            return
