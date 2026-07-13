#!/usr/bin/env python3
"""Exact Provider repository/journal/transport compatibility fixtures."""

from __future__ import annotations

import io
import os
import sys
import tempfile
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-provider-characterization-"))
os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")

import server
from services.provider_events import ProviderEventJournal, TERMINAL_EVENTS, canonical_event_name
from services.provider_registry import ProviderRunRepository


class ProviderFixture:
    def __init__(self):
        self.repository = ProviderRunRepository(retention_ms=10 * 60 * 1000)
        self.journal = ProviderEventJournal(max_events=4000)
        self._event_log = self.journal.compatibility_event_log

    @property
    def _runs(self):
        return self.repository.snapshots()

    @property
    def _next_event_id(self):
        return self.journal.next_event_id

    def remember(self, meta):
        return self.repository.reserve_start(
            provider_kind=meta.get("providerKind") or "",
            agent_id=meta.get("agentId") or "",
            conversation_id=meta.get("conversationId") or "",
            run_id=meta.get("runId") or "",
            meta=meta,
        ).snapshot

    def update(self, run_id, **updates):
        return self.repository.update(run_id, **updates).snapshot

    def publish(self, provider_kind, agent_id, conversation_id, event_name, payload=None, run_id=""):
        return self.journal.publish(provider_kind, agent_id, conversation_id, event_name, payload, run_id)

    def emit(self, run_id, event_name, payload=None):
        meta = self.repository.get(run_id)
        if not meta:
            return False
        name = canonical_event_name(event_name)
        data = dict(payload or {})
        if name in TERMINAL_EVENTS and not self.repository.claim_terminal_event(run_id, name, data).applied:
            return True
        self.journal.publish(meta.get("providerKind") or "", meta.get("agentId") or "", meta.get("conversationId") or "", name, data, run_id)
        return True


class StopWriter(io.BytesIO):
    def __init__(self, stop_after: bytes | None = None):
        super().__init__()
        self.stop_after = stop_after

    def write(self, data):
        result = super().write(data)
        if self.stop_after and self.stop_after in self.getvalue():
            raise BrokenPipeError("fixture stream complete")
        return result


class FakeSseHandler:
    def __init__(self, request_headers=None, stop_after: bytes | None = None):
        self.headers = dict(request_headers or {})
        self.response_headers = []
        self.status = None
        self.wfile = StopWriter(stop_after)

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.response_headers.append((name, value))

    def end_headers(self):
        pass


def test_missing_run_sse_has_exact_404_event_contract():
    bridge = ProviderFixture()
    handler = FakeSseHandler()
    server._provider_sse_transport_for(bridge.repository, bridge.journal).stream_run(handler, "missing-run", "Codex")
    body = handler.wfile.getvalue().decode("utf-8")
    assert handler.status == 404
    assert ("Content-Type", "text/event-stream") in handler.response_headers
    assert body == 'event: run.failed\ndata: {"error": "Codex run not found"}\n\n'


def test_provider_sse_replays_only_after_max_query_and_last_event_id():
    bridge = ProviderFixture()
    bridge.publish("codex", "agent-a", "conv-a", "run.started", {"value": 1}, "run-a")
    bridge.publish("codex", "agent-a", "conv-a", "message.delta", {"value": 2}, "run-a")
    handler = FakeSseHandler({"Last-Event-ID": "1"}, b"event: message.delta")
    server._provider_sse_transport_for(bridge.repository, bridge.journal).stream_conversation(handler, "codex", "agent-a", "conv-a", after=0)
    body = handler.wfile.getvalue().decode("utf-8")
    assert handler.status == 200
    assert "event: provider.snapshot" in body
    assert "event: run.started" not in body
    assert "id: 2\nevent: message.delta" in body
    assert '"value": 2' in body


def test_provider_sse_snapshot_and_history_recovery_shape():
    bridge = ProviderFixture()
    bridge.remember({
        "runId": "run-recover", "providerKind": "claude-code", "agentId": "agent-r",
        "conversationId": "conv-r", "startedAt": 123, "done": False,
    })
    old = server._provider_recovery_progress_snapshot
    server._provider_recovery_progress_snapshot = lambda *args: {"status": "running", "text": "partial"}
    try:
        handler = FakeSseHandler(stop_after=b"event: history.recovered")
        server._provider_sse_transport_for(bridge.repository, bridge.journal).stream_conversation(handler, "claude-code", "agent-r", "conv-r", after=0)
    finally:
        server._provider_recovery_progress_snapshot = old
    body = handler.wfile.getvalue().decode("utf-8")
    assert '"activeRuns": [{"runId": "run-recover", "startedAt": 123, "status": "running"}]' in body
    assert "event: history.recovered" in body
    assert '"progress": {"status": "running", "text": "partial"}' in body


def test_provider_sse_emits_ten_second_heartbeat_contract():
    bridge = ProviderFixture()
    old_recovery = server._provider_recovery_progress_snapshot
    old_time = server.time.time
    ticks = iter((0, 1, 11, 12, 22, 23))
    server._provider_recovery_progress_snapshot = lambda *args: None
    server.time.time = lambda: next(ticks, 30)
    try:
        handler = FakeSseHandler(stop_after=b"event: provider.heartbeat")
        server._provider_sse_transport_for(bridge.repository, bridge.journal).stream_conversation(handler, "codex", "agent-h", "conv-h", after=0)
    finally:
        server._provider_recovery_progress_snapshot = old_recovery
        server.time.time = old_time
    body = handler.wfile.getvalue().decode("utf-8")
    assert "event: provider.snapshot" in body
    assert "event: provider.heartbeat" in body


def test_event_cursor_is_monotonic_and_retention_is_exactly_4000():
    bridge = ProviderFixture()
    for index in range(4001):
        bridge.publish("codex", "agent", "conv", "provider.activity", {"index": index}, "run")
    assert bridge._next_event_id == 4001
    assert len(bridge._event_log) == 4000
    assert bridge._event_log[0]["id"] == 2
    assert bridge._event_log[-1]["id"] == 4001


def test_concurrent_provider_scopes_keep_event_identity_and_payload_isolated():
    bridge = ProviderFixture()
    threads = []
    for index in range(100):
        thread = threading.Thread(
            target=bridge.publish,
            args=("codex" if index % 2 == 0 else "hermes", f"agent-{index}", f"conv-{index}", "run.started", {"scope": index}, f"run-{index}"),
        )
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()
    assert bridge._next_event_id == 100
    assert len({item["id"] for item in bridge._event_log}) == 100
    assert {(item["agentId"], item["conversationId"], item["data"]["scope"]) for item in bridge._event_log} == {
        (f"agent-{index}", f"conv-{index}", index) for index in range(100)
    }


def test_cancel_vs_complete_has_one_fenced_terminal_winner():
    """The Section 1 failing-before race now proves one terminal event wins."""
    bridge = ProviderFixture()
    run_id = "race-run"
    bridge.remember({"runId": run_id, "providerKind": "codex", "agentId": "agent", "conversationId": "conv", "done": False})
    barrier = threading.Barrier(3)

    def finish(event_name, result):
        barrier.wait()
        bridge.update(run_id, done=True, result=result)
        bridge.emit(run_id, event_name, result)

    threads = [
        threading.Thread(target=finish, args=("run.completed", {"ok": True, "status": "completed"})),
        threading.Thread(target=finish, args=("run.cancelled", {"ok": False, "status": "cancelled"})),
    ]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()
    terminals = [item["event"] for item in bridge._event_log if item["event"] in {"run.cancelled", "run.completed", "run.failed"}]
    assert len(terminals) == 1
    assert terminals[0] in {"run.cancelled", "run.completed"}


def test_invalid_provider_stream_scope_has_exact_400_json_contract():
    bridge = ProviderFixture()
    handler = FakeSseHandler()
    server._provider_sse_transport_for(bridge.repository, bridge.journal).stream_conversation(handler, "unknown", "agent", "conv")
    assert handler.status == 400
    assert ("Content-Type", "application/json") in handler.response_headers
    assert handler.wfile.getvalue().decode("utf-8") == '{"ok": false, "error": "provider, agentId and conversationId are required"}'


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"test_provider_characterization.py passed ({len(tests)} tests)")
