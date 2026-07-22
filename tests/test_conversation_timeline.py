from __future__ import annotations

import sys
from pathlib import Path

import pytest


APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.conversation_timeline import (
    ConversationTimelineService,
    ReasoningAccumulator,
    TimelineItem,
    TimelinePage,
    TimelineQuery,
    TimelineScope,
    canonical_provider_kind,
    decode_timeline_cursor,
    encode_timeline_cursor,
    normalize_lifecycle,
    visible_reasoning,
)


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [
        ("codex", "codex"),
        ("Claude", "claude-code"),
        ("claude_code", "claude-code"),
        ("claudecode", "claude-code"),
        ("claude-code", "claude-code"),
        ("hermes", "hermes"),
        ("gateway", "openclaw"),
        ("open-claw", "openclaw"),
        ("openclaw", "openclaw"),
    ],
)
def test_provider_aliases_are_canonical(alias, canonical):
    assert canonical_provider_kind(alias) == canonical


def test_scope_and_query_are_bounded_and_require_identity():
    scope = TimelineScope.create("gateway", "agent", "", "", "session")
    assert scope.provider_kind == "openclaw"
    assert scope.conversation_ref == "session"
    assert TimelineQuery(limit=50, candidate_limit=1000).include_live is True
    with pytest.raises(ValueError):
        TimelineScope.create("unknown", "agent", "", "conversation")
    with pytest.raises(ValueError):
        TimelineScope.create("codex", "", "", "conversation")
    with pytest.raises(ValueError):
        TimelineScope.create("codex", "a" * 161, "", "conversation")
    with pytest.raises(ValueError):
        TimelineQuery(limit=51)
    with pytest.raises(ValueError):
        TimelineQuery(before=(0, ""))
    assert TimelineQuery(limit="2", candidate_limit="3").limit == 2
    with pytest.raises(ValueError):
        TimelineQuery(include_live="false")


def test_canonical_item_and_page_contracts_reject_invalid_values():
    item = TimelineItem(
        id="item",
        version="version",
        provider_kind="gateway",
        conversation_id="conversation",
        item_kind="reasoning",
        thinking="detail",
        status="completed",
    )
    assert item.provider_kind == "openclaw"
    assert item.status == "done"
    assert TimelinePage((item,)).items == (item,)
    with pytest.raises(ValueError):
        TimelineItem("", "version", "codex", "conversation", "message")
    with pytest.raises(ValueError):
        TimelineItem("item", "version", "codex", "conversation", "unknown")
    with pytest.raises(ValueError):
        TimelinePage(tuple(item for _ in range(51)))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("pending", "queued"),
        ("streaming", "running"),
        ("completed", "done"),
        ("execution_failed", "failed"),
        ("canceled", "cancelled"),
        ("unknown", "done"),
    ],
)
def test_lifecycle_aliases(raw, expected):
    assert normalize_lifecycle(raw) == expected


@pytest.mark.parametrize(
    ("provider", "record"),
    [
        ("codex", {"thinking": "running", "status": "running"}),
        ("codex", {"thinking": "Codex run 正在执行"}),
        ("claude-code", {"thinking": "Claude Code completed."}),
        ("hermes", {"thinking": "done"}),
        ("openclaw", {"thinking": ""}),
    ],
)
def test_status_placeholders_are_not_presented_as_reasoning(provider, record):
    assert visible_reasoning(provider, record) == ""


def test_provider_supplied_reasoning_is_preserved_without_fabrication():
    assert visible_reasoning("hermes", {"thinking": "Checked the dependency."}) == "Checked the dependency."
    assert visible_reasoning("openclaw", {}) == ""


def test_reasoning_delta_boundary_replace_replay_and_terminal_state():
    accumulator = ReasoningAccumulator()
    assert accumulator.apply("codex", {"id": "empty", "boundary": True, "text": ""}) is None
    first = accumulator.apply("codex", {"id": "1", "text": "first", "ts": 1, "status": "running"})
    assert first and first.text == "first" and first.status == "running"
    accumulator.apply("codex", {"id": "boundary", "boundary": True})
    second = accumulator.apply("codex", {"id": "2", "output": "second", "ts": 2})
    assert second and second.text == "first\n\nsecond"
    replay = accumulator.apply("codex", {"id": "2", "output": "duplicate"})
    assert replay and replay.text == second.text
    replaced = accumulator.apply("codex", {"id": "3", "replace": True, "text": "final", "status": "completed"})
    assert replaced and replaced.text == "final" and replaced.status == "done"


def test_empty_replace_does_not_erase_reasoning_and_malformed_events_are_ignored():
    accumulator = ReasoningAccumulator()
    accumulator.apply("claude-code", {"id": "1", "thinking": "kept"})
    snapshot = accumulator.apply("claude-code", {"id": "2", "replace": True, "thinking": ""})
    assert snapshot and snapshot.text == "kept"
    assert accumulator.apply("claude-code", "malformed") is None
    assert accumulator.apply("unsupported", {"text": "ignored"}) is None


def test_service_accumulates_each_provider_with_one_policy():
    service = ConversationTimelineService()
    for provider in ("codex", "claude-code", "hermes", "openclaw"):
        snapshots = service.accumulate_reasoning(provider, [{"id": provider, "thinking": f"{provider} detail"}])
        assert [item.text for item in snapshots] == [f"{provider} detail"]


def test_reasoning_state_and_event_identity_are_bounded():
    accumulator = ReasoningAccumulator(max_states=2, max_event_ids=2)
    accumulator.apply("codex", {"id": "a", "turnId": "one", "text": "1"})
    accumulator.apply("codex", {"id": "b", "turnId": "two", "text": "2"})
    accumulator.apply("codex", {"id": "c", "turnId": "three", "text": "3"})
    assert [item.key for item in accumulator.snapshots()] == ["two:reasoning", "three:reasoning"]
    with pytest.raises(ValueError):
        ReasoningAccumulator(max_states="bad")
    bounded = ReasoningAccumulator()
    snapshot = bounded.apply("codex", {"turnId": "x" * 300, "itemId": "y" * 300, "text": "bounded"})
    assert snapshot and len(snapshot.key) == 513


def test_stable_native_identity_and_version_are_scoped_and_render_sensitive():
    service = ConversationTimelineService()
    scope = TimelineScope.create("codex", "agent", "profile", "conversation")
    record = {"id": "native", "text": "hello", "epochMs": 10}
    first = service.item_from_record(scope, record, source="codex")
    repeated = service.item_from_record(scope, record, source="durable-copy")
    changed = service.item_from_record(scope, {**record, "text": "updated"}, source="codex")
    other_scope = TimelineScope.create("codex", "agent", "profile", "other")
    other = service.item_from_record(other_scope, {**record, "conversationId": "other"}, source="codex")
    assert first.id == repeated.id
    assert first.identity_key == repeated.identity_key
    assert first.version != changed.version
    assert first.id != other.id


def test_fallback_identity_keeps_duplicate_text_and_is_deterministic():
    service = ConversationTimelineService()
    scope = TimelineScope.create("hermes", "agent", "profile", "conversation")
    record = {"role": "assistant", "text": "same", "epochMs": 20}
    first = service.item_from_record(scope, record, source="hermes", ordinal=0)
    repeated = service.item_from_record(scope, record, source="hermes", ordinal=0)
    duplicate = service.item_from_record(scope, record, source="hermes", ordinal=1)
    assert first.id == repeated.id
    assert first.id != duplicate.id
    assert len(service.merge_items(scope, ((first, duplicate),))) == 2


def test_provider_sequence_precedes_equal_or_missing_timestamps():
    service = ConversationTimelineService()
    scope = TimelineScope.create("openclaw", "agent", "", "conversation")
    records = [
        {"id": "second", "text": "second", "sequence": 2, "epochMs": 0},
        {"id": "first", "text": "first", "sequence": 1, "epochMs": 99},
        {"id": "third", "text": "third", "sequence": 3, "epochMs": 99},
    ]
    items = service.normalize_records(scope, records, source="openclaw")
    ordered = service.merge_items(scope, (items,))
    assert [item.text for item in ordered] == ["first", "second", "third"]
    missing_sequence = service.item_from_record(scope, {"id": "unsequenced", "text": "unsequenced", "epochMs": 1}, source="openclaw")
    mixed = service.merge_items(scope, (items, (missing_sequence,)))
    assert [item.text for item in mixed] == ["first", "second", "third", "unsequenced"]


def test_overlapping_live_and_durable_sources_settle_one_item_conservatively():
    service = ConversationTimelineService()
    scope = TimelineScope.create("claude-code", "agent", "profile", "conversation")
    live = service.item_from_record(
        scope,
        {"eventId": "shared", "text": "answer", "status": "running", "sequence": 1},
        source="provider-events",
        durable=False,
    )
    durable = service.item_from_record(
        scope,
        {"messageId": "shared", "text": "answer", "status": "completed", "epochMs": 30},
        source="claude-code",
        durable=True,
    )
    merged = service.merge_items(scope, ((live,), (durable,)))
    assert len(merged) == 1
    assert merged[0].status == "done"
    assert merged[0].durable is True
    assert service.merge_items(scope, ((durable,), (durable,)))[0].version == durable.version


def test_source_priority_can_preserve_communication_attribution_without_text_matching():
    service = ConversationTimelineService()
    scope = TimelineScope.create("codex", "agent", "profile", "conversation")
    provider = service.item_from_record(scope, {"id": "shared", "text": "provider"}, source="codex")
    communication = service.item_from_record(
        scope,
        {"id": "shared", "text": "communication", "fromAgentId": "agent", "sourcePriority": 10},
        source="agent-platform-communications",
    )
    merged = service.merge_items(scope, ((provider,), (communication,)))
    assert len(merged) == 1
    assert merged[0].text == "communication"
    assert merged[0].from_agent_id == "agent"


def test_cursor_paging_is_stable_and_public_results_are_copied():
    service = ConversationTimelineService()
    scope = TimelineScope.create("codex", "agent", "profile", "conversation")
    items = service.normalize_records(
        scope,
        ({"id": f"m-{index}", "text": str(index), "epochMs": index} for index in range(1, 6)),
        source="codex",
    )
    latest = service.read(scope, TimelineQuery(limit=2), (items,), session={"tokenUsage": {"total": 1}})
    assert [item.text for item in latest.items] == ["4", "5"]
    assert latest.has_more and decode_timeline_cursor(latest.next_cursor) == (latest.items[0].epoch_ms, latest.items[0].id)
    older = service.read(scope, TimelineQuery(limit=2, before=decode_timeline_cursor(latest.next_cursor)), (items,))
    assert [item.text for item in older.items] == ["2", "3"]

    public = latest.to_public_dict()
    public["messages"][0]["text"] = "mutated"
    public["session"]["tokenUsage"]["total"] = 2
    assert latest.items[0].text == "4"
    assert latest.session["tokenUsage"]["total"] == 1
    assert encode_timeline_cursor(1, "item")
    with pytest.raises(ValueError):
        decode_timeline_cursor("bad")


def test_cross_conversation_provider_and_agent_records_are_rejected():
    service = ConversationTimelineService()
    scope = TimelineScope.create("codex", "agent", "profile", "conversation")
    for record in (
        {"providerKind": "hermes", "text": "foreign"},
        {"conversationId": "other", "text": "foreign"},
        {"agentId": "other", "text": "foreign"},
    ):
        with pytest.raises(ValueError):
            service.item_from_record(scope, record, source="source")
    foreign_scope = TimelineScope.create("codex", "agent", "profile", "other")
    foreign = service.item_from_record(foreign_scope, {"id": "foreign"}, source="codex")
    with pytest.raises(ValueError):
        service.merge_items(scope, ((foreign,),))


def test_input_and_output_nested_values_do_not_share_mutable_state():
    service = ConversationTimelineService()
    scope = TimelineScope.create("openclaw", "agent", "", "conversation")
    tool = {"id": "tool", "arguments": {"path": "a"}}
    item = service.item_from_record(scope, {"id": "message", "text": "answer", "tools": [tool]}, source="openclaw")
    assert item.item_kind == "message"
    tool["arguments"]["path"] = "changed"
    public = item.to_public_dict()
    public["tools"][0]["arguments"]["path"] = "public-change"
    assert item.tools[0]["arguments"]["path"] == "a"
    with pytest.raises(ValueError):
        service.normalize_records(scope, (), source="openclaw", candidate_limit="bad")


def test_compatibility_merge_deduplicates_legacy_id_even_if_item_kind_changes():
    service = ConversationTimelineService()
    scope = TimelineScope.create("codex", "agent", "", "conversation")
    records = service.merge_compatibility_records(
        scope,
        (
            ({"id": "shared", "providerKind": "codex", "conversationId": "conversation", "text": "message", "source": "codex"},),
            ({"id": "shared", "providerKind": "codex", "conversationId": "conversation", "approval": {"status": "pending"}, "source": "agent-platform-communications", "sourcePriority": 10},),
        ),
    )
    assert len(records) == 1
    assert records[0]["approval"] == {"status": "pending"}
