from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.chat_history_timeline import BoundedJsonlHistoryCache
from services.conversation_timeline import ConversationTimelineService, TimelineQuery, TimelineScope
from services.conversation_timeline_sources import ConversationTimelineSourceReader, TimelineSourcePorts


def scope() -> TimelineScope:
    return TimelineScope.create("codex", "agent", "local", "conversation")


def test_partial_provider_failure_keeps_durable_office_history_and_is_deterministic():
    calls = {"provider": 0, "office": 0}

    def unavailable(_scope, _limit):
        calls["provider"] += 1
        raise OSError("private provider path")

    def office(_scope, _limit):
        calls["office"] += 1
        return [{"id": "durable", "text": "visible", "status": "completed"}]

    reader = ConversationTimelineSourceReader(
        ConversationTimelineService(),
        TimelineSourcePorts(provider_history=unavailable, office_history=office),
    )
    first = reader.read(scope(), TimelineQuery())
    second = reader.read(scope(), TimelineQuery())
    assert [item.id for group in first.groups for item in group] == [
        item.id for group in second.groups for item in group
    ]
    assert [(failure.source, failure.error_type) for failure in first.failures] == [
        ("provider-history", "OSError"),
    ]
    assert calls == {"provider": 2, "office": 2}


def test_restart_recovers_durable_terminal_without_fabricating_transient_activity():
    durable = [{"id": "message", "text": "done", "status": "completed", "epochMs": 2}]
    transient = [{"id": "reasoning", "thinking": "live", "status": "running", "epochMs": 1}]

    before_reader = ConversationTimelineSourceReader(
        ConversationTimelineService(),
        TimelineSourcePorts(
            provider_history=lambda _scope, _limit: durable,
            live_activity=lambda _scope, _limit: transient,
        ),
    )
    before = before_reader.read(scope(), TimelineQuery(include_live=True))
    assert sum(len(group) for group in before.groups) == 2

    restarted_reader = ConversationTimelineSourceReader(
        ConversationTimelineService(),
        TimelineSourcePorts(provider_history=lambda _scope, _limit: durable),
    )
    restarted = restarted_reader.read(scope(), TimelineQuery(include_live=True))
    items = [item for group in restarted.groups for item in group]
    assert len(items) == 1
    assert items[0].status == "done"
    assert items[0].text == "done"
    assert items[0].thinking == ""


def test_concurrent_repeated_reads_are_copied_stable_and_scope_local():
    timeline = ConversationTimelineService()
    records = [
        timeline.item_from_record(
            scope(),
            {"id": f"message-{index}", "text": f"item-{index}", "epochMs": index},
            source="provider",
        )
        for index in range(50)
    ]

    def read_once():
        return timeline.read(scope(), TimelineQuery(limit=50), [records]).to_public_dict()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _index: read_once(), range(32)))
    signatures = [
        [(item["id"], item["version"], item["status"]) for item in result["messages"]]
        for result in results
    ]
    assert all(signature == signatures[0] for signature in signatures)
    results[0]["messages"][0]["text"] = "mutated"
    assert results[1]["messages"][0]["text"] != "mutated"


def test_source_cache_eviction_is_bounded_and_reloads_evicted_entry(tmp_path):
    cache = BoundedJsonlHistoryCache(entry_limit=2, byte_limit=1024 * 1024)
    paths = []
    for index in range(3):
        path = tmp_path / f"history-{index}.jsonl"
        path.write_text(json.dumps({"id": index}) + "\n", encoding="utf-8")
        paths.append(path)
        assert cache.load(str(path), f"key-{index}") == [{"id": index}]
    assert cache.stats()["entries"] == 2
    misses = cache.stats()["misses"]
    assert cache.load(str(paths[0]), "key-0") == [{"id": 0}]
    assert cache.stats()["misses"] == misses + 1
    assert cache.stats()["entries"] == 2
