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
