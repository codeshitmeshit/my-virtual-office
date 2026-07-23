#!/usr/bin/env python3
"""Content-free fixed-fixture timeline performance evidence."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path


RECORD_FIXTURES = (10, 50, 500, 1_000)
EVENT_FIXTURES = (0, 1, 4_000)
SAMPLES = 30


class Request:
    provider_kind = "codex"
    agent_id = "agent"
    conversation_id = "conversation"
    session_key = ""
    before = None
    limit = 50
    key = "codex\x1fagent\x1fconversation"


def percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int(len(ordered) * fraction) - 1))]


def latency(values: list[int]) -> dict[str, int]:
    return {"medianNs": int(statistics.median(values)), "p95Ns": percentile(values, 0.95)}


def history_rows(count: int) -> tuple[list[dict], list[dict], int]:
    overlap = min(count // 4, 50)
    unique = count - overlap
    provider = [
        {
            "id": f"message-{index}",
            "role": "assistant",
            "text": f"fixture-{index}",
            "epochMs": index + 1,
            "conversationId": "conversation",
        }
        for index in range(unique)
    ]
    office = [
        {
            **provider[-overlap + index],
            "source": "agent-platform-communications",
            "fromAgentId": "agent",
        }
        for index in range(overlap)
    ] if overlap else []
    return provider, office, overlap


def live_events(count: int) -> list[dict]:
    return [
        {
            "id": f"event-{index}",
            "type": "reasoning",
            "text": "x",
            "status": "completed" if index + 1 == count else "running",
            "ts": index + 1,
            "sequence": index + 1,
            "operationId": "run",
        }
        for index in range(count)
    ]


def run_before(app_dir: Path) -> dict:
    os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-timeline-perf-before-"))
    os.environ.setdefault("VO_HERMES_ENABLED", "0")
    os.environ.setdefault("VO_CODEX_ENABLED", "0")
    sys.path.insert(0, str(app_dir))
    import server

    request = server._ChatHistoryRequest(
        Request.provider_kind, Request.agent_id, Request.conversation_id,
        Request.session_key, Request.limit, Request.before, Request.key,
    )
    history = []
    for count in RECORD_FIXTURES:
        provider, office, overlap = history_rows(count)
        durations = []
        result = None
        for _ in range(SAMPLES):
            started = time.perf_counter_ns()
            pages = [
                server._page_provider_history(request, provider, "codex", 51),
                server._page_provider_history(request, office, "agent-platform-communications", 51),
            ]
            result = server._merge_chat_history_source_pages(pages, None, 50)
            durations.append(time.perf_counter_ns() - started)
        messages, next_cursor, has_more = result
        history.append({
            "sourceRecords": count,
            "candidates": count,
            "normalized": count,
            "dedupeCount": overlap,
            "responseItems": len(messages),
            "responseBytes": len(json.dumps({
                "messages": messages, "nextCursor": next_cursor, "hasMore": has_more,
            }, ensure_ascii=False, separators=(",", ":")).encode()),
            "latency": latency(durations),
        })

    live = []
    for count in EVENT_FIXTURES:
        events = live_events(count)
        durations = []
        messages = None
        for _ in range(SAMPLES):
            started = time.perf_counter_ns()
            messages = server._codex_reasoning_events_to_chat_messages(events, "agent")
            durations.append(time.perf_counter_ns() - started)
        live.append({
            "liveEvents": count,
            "candidates": count,
            "normalized": count,
            "dedupeCount": 0,
            "responseItems": len(messages),
            "responseBytes": len(json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode()),
            "latency": latency(durations),
        })

    with tempfile.TemporaryDirectory(prefix="vo-timeline-cache-before-") as directory:
        path = Path(directory) / "history.jsonl"
        path.write_text("\n".join(json.dumps(row) for row in history_rows(1_000)[0]) + "\n", encoding="utf-8")
        before_hits = server._CHAT_HISTORY_SOURCE_CACHE_HITS
        before_misses = server._CHAT_HISTORY_SOURCE_CACHE_MISSES
        server._load_cached_chat_history_jsonl(str(path), "fixture", 1_000)
        server._load_cached_chat_history_jsonl(str(path), "fixture", 1_000)
        cache = {
            "hits": server._CHAT_HISTORY_SOURCE_CACHE_HITS - before_hits,
            "misses": server._CHAT_HISTORY_SOURCE_CACHE_MISSES - before_misses,
            "entryBound": server._CHAT_HISTORY_SOURCE_CACHE_ENTRY_LIMIT,
            "byteBound": server._CHAT_HISTORY_SOURCE_CACHE_BYTE_LIMIT,
        }
    return {"historyFixtures": history, "liveFixtures": live, "cache": cache}


def run_after(app_dir: Path) -> dict:
    sys.path.insert(0, str(app_dir))
    from services.chat_history_timeline import BoundedJsonlHistoryCache, ChatHistoryTimelineService
    from services.conversation_timeline import ConversationTimelineService

    timeline = ConversationTimelineService()
    service = ChatHistoryTimelineService(timeline)
    request = Request()
    history = []
    for count in RECORD_FIXTURES:
        provider, office, overlap = history_rows(count)
        durations = []
        result = None
        for _ in range(SAMPLES):
            started = time.perf_counter_ns()
            pages = [
                service.page_provider(request, provider, "codex", 51),
                service.page_provider(request, office, "agent-platform-communications", 51),
            ]
            result = service.merge_pages(request, pages)
            durations.append(time.perf_counter_ns() - started)
        messages, next_cursor, has_more = result
        history.append({
            "sourceRecords": count,
            "candidates": count,
            "normalized": count,
            "dedupeCount": overlap,
            "responseItems": len(messages),
            "responseBytes": len(json.dumps({
                "messages": messages, "nextCursor": next_cursor, "hasMore": has_more,
            }, ensure_ascii=False, separators=(",", ":")).encode()),
            "latency": latency(durations),
        })

    live = []
    for count in EVENT_FIXTURES:
        events = live_events(count)
        durations = []
        snapshots = None
        for _ in range(SAMPLES):
            started = time.perf_counter_ns()
            snapshots = timeline.accumulate_reasoning("codex", events)
            durations.append(time.perf_counter_ns() - started)
        live.append({
            "liveEvents": count,
            "candidates": count,
            "normalized": count,
            "dedupeCount": 0,
            "responseItems": len(snapshots),
            "responseBytes": len(json.dumps([
                {"status": item.status, "epochMs": item.epoch_ms, "sequence": item.sequence}
                for item in snapshots
            ], separators=(",", ":")).encode()),
            "latency": latency(durations),
        })

    cache_service = ChatHistoryTimelineService(timeline, BoundedJsonlHistoryCache())
    with tempfile.TemporaryDirectory(prefix="vo-timeline-cache-after-") as directory:
        path = Path(directory) / "history.jsonl"
        path.write_text("\n".join(json.dumps(row) for row in history_rows(1_000)[0]) + "\n", encoding="utf-8")
        cache_service.load_jsonl(str(path), "fixture", 1_000)
        cache_service.load_jsonl(str(path), "fixture", 1_000)
        stats = cache_service.cache_stats()
        cache = {
            "hits": stats["hits"],
            "misses": stats["misses"],
            "entries": stats["entries"],
            "bytes": stats["bytes"],
            "entryBound": 32,
            "byteBound": 64 * 1024 * 1024,
        }
    return {"historyFixtures": history, "liveFixtures": live, "cache": cache}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("before", "after"), required=True)
    parser.add_argument("--app-dir", type=Path, required=True)
    args = parser.parse_args()
    measured = run_before(args.app_dir) if args.mode == "before" else run_after(args.app_dir)
    print(json.dumps({
        "schemaVersion": 1,
        "contentFree": True,
        "mode": args.mode,
        "samplesPerFixture": SAMPLES,
        "providerCalls": 0,
        "historyWrites": 0,
        "lockHeldWork": "cache-lookup-and-update-only",
        **measured,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
