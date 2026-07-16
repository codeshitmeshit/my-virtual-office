import io

from app.provider_sse_transport import ProviderSSETransport
from app.services.provider_events import ProviderEventJournal
from app.services.provider_registry import ProviderRunRepository


class StopWriter(io.BytesIO):
    def __init__(self, stop_after=b""):
        super().__init__()
        self.stop_after = stop_after

    def write(self, value):
        written = super().write(value)
        if self.stop_after and self.stop_after in self.getvalue():
            raise BrokenPipeError("client disconnected")
        return written


class Handler:
    def __init__(self, headers=None, stop_after=b""):
        self.headers = headers or {}
        self.status = None
        self.close_connection = False
        self.response_headers = []
        self.wfile = StopWriter(stop_after)

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.response_headers.append((name, value))

    def end_headers(self):
        return None


def transport(repository=None, journal=None, **values):
    return ProviderSSETransport(
        repository or ProviderRunRepository(),
        journal or ProviderEventJournal(),
        provider_kind_of=lambda meta, run_id: meta.get("providerKind") or "codex",
        **values,
    )


def test_run_transport_replays_after_max_cursor_with_exact_frames():
    repository = ProviderRunRepository()
    journal = ProviderEventJournal()
    repository.reserve_start(provider_kind="codex", agent_id="agent", conversation_id="conv", run_id="run")
    journal.publish("codex", "agent", "conv", "run.started", {"value": 1}, "run")
    journal.publish("codex", "agent", "conv", "message.delta", {"value": 2}, "run")
    journal.publish("codex", "agent", "conv", "run.completed", {"ok": True}, "run")
    handler = Handler({"Last-Event-ID": "1"})
    transport(repository, journal).stream_run(handler, "run", after=2)
    body = handler.wfile.getvalue().decode()
    assert handler.status == 200
    assert "event: run.started" not in body and "event: message.delta" not in body
    assert "id: 3\nevent: run.completed\ndata:" in body
    assert handler.close_connection is True


def test_missing_run_and_invalid_scope_keep_compatibility_contracts():
    missing = Handler()
    transport().stream_run(missing, "absent", "Codex")
    assert missing.status == 404
    assert missing.wfile.getvalue() == b'event: run.failed\ndata: {"error": "Codex run not found"}\n\n'
    invalid = Handler()
    transport().stream_conversation(invalid, "unknown", "agent", "conv")
    assert invalid.status == 400
    assert invalid.wfile.getvalue() == b'{"ok": false, "error": "provider, agentId and conversationId are required"}'


def test_snapshot_pending_recovery_and_sensitive_canaries_are_transport_sanitized():
    ticks = iter((1, 1, 1))
    handler = Handler(stop_after=b"event: history.recovered")
    adapter = transport(
        pending_lookup=lambda *_args: {"id": "approval", "authorization": "Bearer abcdefghijklmnop"},
        recovery_lookup=lambda *_args: {"text": "sk-abcdefghijklmnop", "path": "/Users/private/file"},
        clock=lambda: next(ticks, 1),
    )
    adapter.stream_conversation(handler, "codex", "agent", "conv")
    body = handler.wfile.getvalue().decode()
    assert "event: provider.snapshot" in body
    assert "event: approval.request" in body
    assert "event: history.recovered" in body
    assert "Bearer abcdefghijklmnop" not in body
    assert "sk-abcdefghijklmnop" not in body
    assert "/Users/private/file" not in body


def test_disconnect_does_not_mutate_or_remove_active_run():
    repository = ProviderRunRepository()
    journal = ProviderEventJournal()
    reservation = repository.reserve_start(provider_kind="codex", agent_id="agent", conversation_id="conv", run_id="run")
    journal.publish("codex", "agent", "conv", "message.delta", {"text": "partial"}, "run")
    handler = Handler(stop_after=b"message.delta")
    transport(repository, journal).stream_run(handler, "run")
    snapshot = repository.get("run")
    assert snapshot is not None
    assert snapshot["generation"] == reservation.token.generation
    assert snapshot.get("done") is not True
    assert handler.close_connection is True


def test_new_transport_instance_has_non_durable_run_and_event_state():
    old_repository = ProviderRunRepository()
    old_journal = ProviderEventJournal()
    old_repository.reserve_start(provider_kind="codex", agent_id="agent", conversation_id="conv", run_id="run")
    old_journal.publish("codex", "agent", "conv", "run.started", {}, "run")
    restarted = transport(ProviderRunRepository(), ProviderEventJournal())
    handler = Handler()
    restarted.stream_run(handler, "run", "Codex")
    assert handler.status == 404
    assert old_repository.get("run") is not None


def test_late_callback_cannot_recreate_cleared_or_reused_run():
    repository = ProviderRunRepository()
    first = repository.reserve_start(provider_kind="codex", agent_id="old", run_id="shared")
    assert repository.clear("shared", generation=first.token.generation)
    second = repository.reserve_start(provider_kind="hermes", agent_id="new", run_id="shared")
    late = repository.complete("shared", {"ok": True, "status": "completed", "reply": "old"}, generation=first.token.generation)
    assert late.stale is True and late.applied is False
    assert repository.get("shared")["agentId"] == "new"
    assert repository.get("shared")["generation"] == second.token.generation


def test_pending_or_history_recovery_failure_does_not_close_event_replay():
    journal = ProviderEventJournal()
    journal.publish("codex", "agent", "conv", "run.started", {}, "run")
    journal.publish("codex", "agent", "conv", "message.delta", {"text": "healthy"}, "run")
    handler = Handler({"Last-Event-ID": "1"}, stop_after=b"event: message.delta")

    def unavailable(*_args):
        raise OSError("history unavailable")

    adapter = transport(journal=journal, pending_lookup=unavailable, recovery_lookup=unavailable)
    adapter.stream_conversation(handler, "codex", "agent", "conv")
    body = handler.wfile.getvalue().decode()
    assert "event: provider.snapshot" in body
    assert "id: 2\nevent: message.delta" in body
    assert "history unavailable" not in body
    assert handler.close_connection is True


def test_codex_telemetry_ignores_non_codex_run_and_conversation_streams():
    class Telemetry:
        def __init__(self):
            self.marks = []

        def mark(self, run_id, stage):
            self.marks.append((run_id, stage))

    repository = ProviderRunRepository()
    journal = ProviderEventJournal()
    telemetry = Telemetry()
    adapter = ProviderSSETransport(
        repository,
        journal,
        provider_kind_of=lambda meta, _run_id: meta.get("providerKind") or "",
        telemetry=telemetry,
    )

    repository.reserve_start(provider_kind="hermes", agent_id="agent", conversation_id="conv", run_id="hermes-run")
    journal.publish("hermes", "agent", "conv", "run.completed", {"ok": True}, "hermes-run")
    adapter.stream_run(Handler(), "hermes-run")
    assert telemetry.marks == []

    class ConversationJournal:
        next_event_id = 0

        def wait_for_conversation_events(self, *_args, **_kwargs):
            return [{"id": 1, "event": "run.completed", "runId": "hermes-run", "data": {"ok": True}}]

    conversation_adapter = ProviderSSETransport(
        repository,
        ConversationJournal(),
        provider_kind_of=lambda meta, _run_id: meta.get("providerKind") or "",
        telemetry=telemetry,
    )
    conversation = Handler(stop_after=b"event: run.completed")
    conversation_adapter.stream_conversation(conversation, "hermes", "agent", "conv")
    assert telemetry.marks == []

    repository.reserve_start(provider_kind="codex", agent_id="agent", conversation_id="codex-conv", run_id="codex-run")
    journal.publish("codex", "agent", "codex-conv", "run.completed", {"ok": True}, "codex-run")
    adapter.stream_run(Handler(), "codex-run")
    assert ("codex-run", "sse_written") in telemetry.marks
    assert ("codex-run", "terminal_sse_written") in telemetry.marks
