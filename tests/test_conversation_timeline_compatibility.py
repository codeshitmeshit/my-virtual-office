from __future__ import annotations

import json

import pytest

from conversation_timeline_compatibility import DEFAULT_POLICY, assess


POLICY = json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))


def _snapshot(*observations):
    return {"schema": 1, "contentPolicy": "content-free", "observations": list(observations)}


def _observation(observation_id, provider, surface, dimension, **values):
    return {
        "id": observation_id,
        "provider": provider,
        "surface": surface,
        "dimension": dimension,
        "values": values,
    }


def test_exact_compatibility_passes_without_differences():
    snapshot = _snapshot(_observation("ordinary", "codex", "standard-chat", "dto", status=200, fields=["ok"]))
    assert assess(snapshot, snapshot, POLICY) == {"ok": True, "allowed": [], "rejected": []}


def test_unexplained_contract_and_visual_differences_fail():
    before = _snapshot(_observation("ordinary", "codex", "standard-chat", "dto", status=200, visualDigest="a"))
    after = _snapshot(_observation("ordinary", "codex", "standard-chat", "dto", status=201, visualDigest="b"))
    result = assess(before, after, POLICY)
    assert result["ok"] is False
    assert {item["path"] for item in result["rejected"]} == {"/status", "/visualDigest"}


def test_only_exact_claude_workflow_fixture_can_change_history_selection():
    before = _snapshot(_observation("claude-code-project-history-selection", "claude-code", "project-execution", "history", historySource="openclaw", canonicalDigest="old"))
    after = _snapshot(_observation("claude-code-project-history-selection", "claude-code", "project-execution", "history", historySource="claude-code", canonicalDigest="new"))
    assert assess(before, after, POLICY)["ok"] is True

    wrong_surface = _snapshot(_observation("claude-code-project-history-selection", "claude-code", "standard-chat", "history", historySource="claude-code", canonicalDigest="new"))
    assert assess(before, wrong_surface, POLICY)["ok"] is False


@pytest.mark.parametrize(
    ("observation_id", "provider", "surface", "dimension", "before_values", "after_values"),
    [
        ("hermes-completed-reasoning-state", "hermes", "project-execution", "status", {"reasoningStatus": "live"}, {"reasoningStatus": "done"}),
        ("openclaw-structured-block-consistency", "openclaw", "cross-surface", "history", {"canonicalDigest": "old"}, {"canonicalDigest": "new"}),
        ("codex-single-reasoning-owner", "codex", "cross-surface", "history", {"reasoningOwner": "server-and-client"}, {"reasoningOwner": "timeline"}),
    ],
)
def test_each_other_named_correction_allows_only_its_exact_fixture(
    observation_id, provider, surface, dimension, before_values, after_values
):
    before = _snapshot(_observation(observation_id, provider, surface, dimension, **before_values))
    after = _snapshot(_observation(observation_id, provider, surface, dimension, **after_values))
    assert assess(before, after, POLICY)["ok"] is True

    foreign = _snapshot(_observation(observation_id, "claude-code", surface, dimension, **after_values))
    assert assess(before, foreign, POLICY)["ok"] is False


def test_four_named_corrections_are_narrow_and_no_wildcard_rule_exists():
    rules = POLICY["allowedCorrections"]
    assert {item["id"] for item in rules} == {
        "claude-code-workflow-history-selection",
        "hermes-completed-reasoning-state",
        "openclaw-structured-block-consistency",
        "codex-single-reasoning-owner",
    }
    assert all(item.get("selectors", {}).get("observation_id") for item in rules)
    assert all("*" not in item.get("paths", []) for item in rules)


def test_added_or_removed_observation_fails_by_default():
    before = _snapshot(_observation("ordinary", "hermes", "standard-chat", "events", eventDigest="a"))
    result = assess(before, _snapshot(), POLICY)
    assert result["ok"] is False
    assert result["rejected"]


def test_observation_scope_metadata_drift_fails_even_when_values_match():
    before = _snapshot(_observation("ordinary", "codex", "standard-chat", "events", eventDigest="a"))
    after = _snapshot(_observation("ordinary", "codex", "project-execution", "events", eventDigest="a"))
    result = assess(before, after, POLICY)
    assert result["ok"] is False
    assert {item["path"] for item in result["rejected"]} == {"/__meta__/surface"}


def test_content_bearing_observation_is_rejected_before_comparison():
    unsafe = _snapshot(_observation("ordinary", "codex", "standard-chat", "history", text="private"))
    with pytest.raises(AssertionError):
        assess(unsafe, unsafe, POLICY)
