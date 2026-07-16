#!/usr/bin/env python3
"""Codex coalescing integration at the Provider journal boundary."""

import io
import threading
import time

from app.provider_sse_transport import ProviderSSETransport
from app.services.codex_fast_path import CodexTransientCoalescer
from app.services.provider_events import ProviderEventJournal
from app.services.provider_ports import AdapterCapabilities, AdapterEvent, AdapterResult, RunCommand
from app.services.provider_registry import ProviderRunRepository
from app.services.provider_runs import ProviderRunCoordinator


class BurstAdapter:
    provider_kind = "codex"
    provider_path = "fixture"
    capabilities = AdapterCapabilities(background_run=True, streaming_events=True)

    def run(self, command, emit, cancel_event):
        emit(AdapterEvent("message.delta", {"delta": "A", "text": "A"}))
        emit(AdapterEvent("message.delta", {"delta": "B", "text": "B"}))
        emit(AdapterEvent("message.delta", {"delta": "C", "text": "C"}))
        emit(AdapterEvent("approval.request", {"approvalId": "approval-1"}))
        emit(AdapterEvent("reasoning.available", {"text": "D"}))
        emit(AdapterEvent("tool.started", {"toolCallId": "tool-1"}))
        emit(AdapterEvent("message.delta", {"delta": "E", "text": "E"}))
        return AdapterResult(
            {"ok": True, "status": "completed", "reply": "ABCDE"},
            {"ok": True, "status": "completed", "reply": "ABCDE"},
            "run.completed",
        )


class Handler:
    def __init__(self, last_event_id=""):
        self.headers = {"Last-Event-ID": str(last_event_id)} if last_event_id != "" else {}
        self.status = None
        self.close_connection = False
        self.wfile = io.BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, *_args):
        return None

    def end_headers(self):
        return None


def _wait_terminal(repository, run_id):
    deadline = time.time() + 2
    while time.time() < deadline:
        snapshot = repository.get(run_id)
        if snapshot and snapshot.get("terminal"):
            return snapshot
        time.sleep(0.005)
    raise AssertionError("run did not complete")


def test_coalescing_precedes_journal_and_barriers_preserve_replay_order():
    repository = ProviderRunRepository()
    journal = ProviderEventJournal()
    coalescer = CodexTransientCoalescer(min_ms=33, max_ms=100)
    coordinator = ProviderRunCoordinator(repository, journal, event_pipeline=coalescer)
    command = RunCommand(
        provider_kind="codex",
        provider_path="fixture",
        agent_id="agent",
        conversation_id="conversation",
        idempotency_key="coalesced-run",
    )
    try:
        outcome = coordinator.start(command, adapter=BurstAdapter())
        _wait_terminal(repository, outcome.run_id)
        events = journal.run_events_after(outcome.run_id)
        assert [event["event"] for event in events] == [
            "run.started",
            "message.delta",
            "message.delta",
            "approval.request",
            "reasoning.available",
            "tool.started",
            "message.delta",
            "run.completed",
        ]
        assert [
            event["data"].get("delta")
            for event in events
            if event["event"] == "message.delta"
        ] == ["A", "BC", "E"]
        assert events[2]["data"]["text"] == "BC"
        assert len([event for event in events if event["event"] == "run.completed"]) == 1
        assert coalescer.drain_due() == 0

        cursor = events[1]["id"]
        replay = journal.run_events_after(outcome.run_id, cursor)
        assert [event["id"] for event in replay] == list(range(cursor + 1, events[-1]["id"] + 1))
        assert "".join(
            event["data"].get("delta") or ""
            for event in events
            if event["event"] == "message.delta"
        ) == "ABCE"

        transport = ProviderSSETransport(repository, journal, provider_kind_of=lambda meta, _run_id: meta.get("providerKind") or "codex")
        handler = Handler(cursor)
        transport.stream_run(handler, outcome.run_id)
        body = handler.wfile.getvalue().decode()
        assert handler.status == 200
        assert f"id: {cursor}\n" not in body
        assert "event: approval.request" in body
        assert body.count("event: run.completed") == 1
        assert handler.close_connection is True
    finally:
        coalescer.close()


def test_coalescer_never_crosses_conversation_scope_and_non_codex_bypasses_pipeline():
    journal = ProviderEventJournal()
    coalescer = CodexTransientCoalescer(min_ms=33, max_ms=100, start_dispatcher=False)

    def publish(agent, conversation, run, name, payload):
        return coalescer.publish_event(
            "codex",
            agent,
            conversation,
            name,
            payload,
            run,
            lambda event_name, data: journal.publish("codex", agent, conversation, event_name, data, run),
        )

    publish("agent", "conv-1", "run-1", "message.delta", {"delta": "A1"})
    publish("agent", "conv-1", "run-1", "message.delta", {"delta": "B1"})
    publish("agent", "conv-2", "run-2", "message.delta", {"delta": "A2"})
    publish("agent", "conv-2", "run-2", "message.delta", {"delta": "B2"})
    publish("agent", "conv-1", "run-1", "approval.request", {"approvalId": "one"})
    assert [event["data"].get("delta") for event in journal.run_events_after("run-1") if event["event"] == "message.delta"] == ["A1", "B1"]
    assert [event["data"].get("delta") for event in journal.run_events_after("run-2") if event["event"] == "message.delta"] == ["A2"]
    publish("agent", "conv-2", "run-2", "run.cancelled", {"status": "cancelled"})
    assert [event["data"].get("delta") for event in journal.run_events_after("run-2") if event["event"] == "message.delta"] == ["A2", "B2"]

    class FailIfUsed:
        def publish_event(self, *_args, **_kwargs):
            raise AssertionError("non-Codex event entered Codex pipeline")

    repository = ProviderRunRepository()
    coordinator = ProviderRunCoordinator(repository, journal, event_pipeline=FailIfUsed())
    direct = coordinator._publish("hermes", "agent", "conv", "message.delta", {"delta": "hermes"}, "hermes-run")
    assert direct["data"]["delta"] == "hermes"
    coalescer.close()
