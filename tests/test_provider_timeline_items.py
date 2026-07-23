from __future__ import annotations

import io
import json

import pytest

from app.provider_sse_transport import ProviderSSETransport
from app.services.conversation_timeline import ConversationTimelineService
from app.services.conversation_timeline_events import ProviderTimelineItemProjector
from app.services.provider_events import ProviderEventJournal
from app.services.provider_registry import ProviderRunRepository


@pytest.mark.parametrize("provider", ["codex", "claude-code", "hermes", "openclaw"])
def test_all_supported_providers_receive_same_bounded_timeline_contract(provider):
    projector = ProviderTimelineItemProjector(ConversationTimelineService())
    item = projector.project(
        "message.delta",
        {"runId": "run", "messageId": "message", "text": "visible", "status": "running", "eventId": 1},
        provider,
        "agent",
        "conversation",
        1,
    )
    assert item is not None
    assert item["providerKind"] == provider
    assert item["conversationId"] == "conversation"
    assert item["itemKind"] == "message"
    assert item["text"] == "visible"
    assert item["status"] == "running"
    assert item["fromAgentId"] == "agent"
    assert set(item) == {
        "id", "version", "providerKind", "conversationId", "providerRunId", "itemKind", "role", "text",
        "thinking", "status", "epochMs", "sequence", "source", "from", "fromAgentId", "to", "toAgentId",
        "media", "attachments", "tools", "reasoningTokens", "approval", "idempotencyKey",
    }


def test_reasoning_replay_boundary_replace_and_terminal_share_one_item():
    projector = ProviderTimelineItemProjector(ConversationTimelineService())
    values = [
        ("reasoning.delta", {"eventId": 1, "runId": "run", "operationId": "turn", "itemId": "reason", "text": "first", "status": "running"}),
        ("reasoning.delta", {"eventId": 2, "runId": "run", "operationId": "turn", "itemId": "reason", "boundary": True}),
        ("reasoning.delta", {"eventId": 3, "runId": "run", "operationId": "turn", "itemId": "reason", "text": "second"}),
        ("reasoning.delta", {"eventId": 3, "runId": "run", "operationId": "turn", "itemId": "reason", "text": "duplicate"}),
        ("reasoning.available", {"eventId": 4, "runId": "run", "operationId": "turn", "itemId": "reason", "replace": True, "text": "final", "status": "completed"}),
    ]
    items = [
        projector.project(name, payload, "codex", "agent", "conversation", payload["eventId"])
        for name, payload in values
    ]
    assert len({item["id"] for item in items if item}) == 1
    assert items[2]["thinking"] == "first\n\nsecond"
    assert items[3]["thinking"] == items[2]["thinking"]
    assert items[-1]["thinking"] == "final"
    assert items[-1]["status"] == "done"


def test_tool_and_run_lifecycle_keep_stable_scoped_identity():
    projector = ProviderTimelineItemProjector(ConversationTimelineService())
    tool_start = projector.project("tool.started", {"runId": "run", "toolCallId": "tool", "name": "read"}, "hermes", "agent", "conversation", 1)
    tool_done = projector.project("tool.completed", {"runId": "run", "toolCallId": "tool", "name": "read", "result": "ok"}, "hermes", "agent", "conversation", 2)
    run_start = projector.project("run.started", {"runId": "run"}, "hermes", "agent", "conversation", 3)
    run_done = projector.project("run.completed", {"runId": "run", "ok": True}, "hermes", "agent", "conversation", 4)
    assert tool_start["id"] == tool_done["id"]
    assert tool_start["status"] == "running" and tool_done["status"] == "done"
    assert tool_start["tools"][0]["status"] == "running" and tool_done["tools"][0]["status"] == "done"
    assert run_start["id"] == run_done["id"]
    assert run_start["status"] == "running" and run_done["status"] == "done"


class _StopWriter(io.BytesIO):
    def write(self, value):
        result = super().write(value)
        if b"event: run.completed" in self.getvalue():
            raise BrokenPipeError
        return result


class _Handler:
    headers = {"Last-Event-ID": "0"}
    close_connection = False

    def __init__(self):
        self.wfile = _StopWriter()

    def send_response(self, _status):
        pass

    def send_header(self, _name, _value):
        pass

    def end_headers(self):
        pass


def test_sse_adds_timeline_item_without_changing_event_name_or_legacy_fields():
    repository = ProviderRunRepository()
    journal = ProviderEventJournal()
    repository.reserve_start(provider_kind="codex", agent_id="agent", conversation_id="conversation", run_id="run")
    journal.publish("codex", "agent", "conversation", "run.completed", {"ok": True, "reply": "done"}, "run")
    transport = ProviderSSETransport(
        repository,
        journal,
        provider_kind_of=lambda meta, _run_id: meta.get("providerKind") or "",
        timeline_item_projector=ProviderTimelineItemProjector(ConversationTimelineService()).project,
    )
    handler = _Handler()
    transport.stream_run(handler, "run")
    body = handler.wfile.getvalue().decode()
    assert "event: run.completed" in body
    data = json.loads(body.split("data: ", 1)[1].split("\n", 1)[0])
    assert data["ok"] is True and data["reply"] == "done"
    assert data["timelineItem"]["itemKind"] == "run"
    assert data["timelineItem"]["status"] == "done"
    assert data["timelineItem"]["text"] == "done"


def test_projection_failure_does_not_change_legacy_sse_delivery():
    transport = ProviderSSETransport(
        ProviderRunRepository(),
        ProviderEventJournal(),
        provider_kind_of=lambda *_args: "codex",
        timeline_item_projector=lambda *_args: (_ for _ in ()).throw(ValueError("malformed")),
    )
    assert transport._payload("message.delta", {"text": "legacy"}, "codex", "agent", "conversation") == {"text": "legacy"}
