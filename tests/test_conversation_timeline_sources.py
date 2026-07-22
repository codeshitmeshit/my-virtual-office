from __future__ import annotations

import inspect
import sys
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.conversation_timeline import ConversationTimelineService, TimelineQuery, TimelineScope
from services.conversation_timeline_sources import (
    ConversationTimelineSourceReader,
    TimelineSourcePorts,
    normalize_source_record,
    parse_openclaw_content,
)


def _scope(provider="codex"):
    return TimelineScope.create(provider, "agent", "profile", "conversation")


def test_injected_sources_are_bounded_read_only_and_copied():
    calls = []
    provider_record = {"id": "provider", "text": "answer", "tools": [{"id": "tool", "arguments": {"x": 1}}]}
    office_record = {"id": "office", "text": "request", "direction": "request"}
    metrics = {"sessionId": "session", "contextUsed": 1, "secret": "hidden", "tokenUsage": {"total": 2}}

    def history(name, records):
        def read(scope, limit):
            calls.append((name, scope.key(), limit))
            return records
        return read

    reader = ConversationTimelineSourceReader(
        ConversationTimelineService(),
        TimelineSourcePorts(
            provider_history=history("provider", [provider_record]),
            office_history=history("office", [office_record]),
            live_activity=history("live", [{"id": "live", "text": "delta"}]),
            session_metrics=lambda scope: metrics,
            active_state=lambda scope: {"running": True},
        ),
    )
    snapshot = reader.read(_scope(), TimelineQuery(candidate_limit=3))
    assert snapshot.candidates == 3
    assert [call[2] for call in calls] == [3, 2, 1]
    assert snapshot.active is True
    assert "secret" not in snapshot.session
    assert sum(len(group) for group in snapshot.groups) == 3
    provider_record["tools"][0]["arguments"]["x"] = 9
    metrics["tokenUsage"]["total"] = 9
    assert snapshot.groups[0][0].tools[0]["arguments"]["x"] == 1
    assert snapshot.session["tokenUsage"]["total"] == 2


def test_partial_source_failure_is_isolated_and_content_free():
    def failed(scope, limit):
        raise RuntimeError("private transcript content")

    reader = ConversationTimelineSourceReader(
        ConversationTimelineService(),
        TimelineSourcePorts(
            provider_history=failed,
            office_history=lambda scope, limit: [{"id": "safe", "text": "visible"}],
            session_metrics=lambda scope: (_ for _ in ()).throw(OSError("/private/path")),
            active_state=lambda scope: (_ for _ in ()).throw(ValueError("secret")),
        ),
    )
    snapshot = reader.read(_scope(), TimelineQuery())
    assert sum(len(group) for group in snapshot.groups) == 1
    assert [(failure.source, failure.error_type) for failure in snapshot.failures] == [
        ("provider-history", "RuntimeError"),
        ("session-metrics", "OSError"),
        ("active-state", "ValueError"),
    ]
    assert all(not hasattr(failure, "message") for failure in snapshot.failures)


def test_include_live_false_skips_live_and_active_readers():
    calls = []
    reader = ConversationTimelineSourceReader(
        ConversationTimelineService(),
        TimelineSourcePorts(
            live_activity=lambda scope, limit: calls.append("live") or [],
            active_state=lambda scope: calls.append("active") or True,
        ),
    )
    snapshot = reader.read(_scope(), TimelineQuery(include_live=False))
    assert calls == []
    assert snapshot.active is False


def test_malformed_source_records_still_consume_the_candidate_bound():
    inspected = []

    def malformed(scope, limit):
        for index in range(100):
            inspected.append(index)
            yield "not-a-record"

    calls = []
    reader = ConversationTimelineSourceReader(
        ConversationTimelineService(),
        TimelineSourcePorts(
            provider_history=malformed,
            office_history=lambda scope, limit: calls.append("office") or [],
        ),
    )
    snapshot = reader.read(_scope(), TimelineQuery(candidate_limit=3))
    assert inspected == [0, 1, 2]
    assert calls == []
    assert snapshot.candidates == 3


def test_openclaw_structured_blocks_cover_text_media_tools_errors_and_reasoning():
    projected = parse_openclaw_content(
        [
            {"type": "text", "text": "hello"},
            {"type": "reasoning", "text": "checked"},
            {"type": "image", "url": "image.png", "mimeType": "image/png"},
            {"type": "toolCall", "id": "call", "name": "read", "arguments": {"path": "a"}},
            {"type": "toolResult", "toolCallId": "call", "result": "done"},
            {"type": "tool_result", "id": "failed", "name": "write", "error": "denied"},
        ]
    )
    assert projected["text"] == "hello"
    assert projected["thinking"] == "checked"
    assert projected["media"] == [{"type": "image", "url": "image.png", "mimeType": "image/png"}]
    assert projected["tools"][0]["status"] == "done"
    assert projected["tools"][0]["result"] == "done"
    assert projected["tools"][1]["status"] == "error"


def test_malformed_blocks_and_nested_provider_messages_are_tolerated():
    assert parse_openclaw_content({"not": "content"}) == {"text": "", "thinking": "", "media": [], "tools": []}
    record = normalize_source_record(
        "openclaw",
        {"id": "entry", "message": {"role": "assistant", "content": [None, {"type": "text", "text": "ok"}]}},
    )
    assert record["id"] == "entry"
    assert record["role"] == "assistant"
    assert record["text"] == "ok"
    assert record["providerKind"] == "openclaw"


def test_source_module_has_no_server_or_mutation_authority():
    import services.conversation_timeline_sources as module

    source = inspect.getsource(module)
    assert "import server" not in source
    assert "from app import server" not in source
    assert "launch(" not in source
    assert "write(" not in source
