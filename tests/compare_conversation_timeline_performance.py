#!/usr/bin/env python3
"""Compare content-free timeline performance fixtures against bounded gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def indexed(payload: dict, group: str, key: str) -> dict[int, dict]:
    return {int(item[key]): item for item in payload[group]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()
    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))
    gates = []

    before_history = indexed(before, "historyFixtures", "sourceRecords")
    for count, current in indexed(after, "historyFixtures", "sourceRecords").items():
        prior = before_history[count]
        p95_bound = max(prior["latency"]["p95Ns"] * 2, 25_000_000)
        gates.extend([
            {"fixture": f"history-{count}", "gate": "candidateBound", "passed": current["candidates"] <= 1_000},
            {"fixture": f"history-{count}", "gate": "p95Bound", "passed": current["latency"]["p95Ns"] <= p95_bound},
            {"fixture": f"history-{count}", "gate": "responseBytes", "passed": current["responseBytes"] == prior["responseBytes"]},
        ])

    before_live = indexed(before, "liveFixtures", "liveEvents")
    for count, current in indexed(after, "liveFixtures", "liveEvents").items():
        prior = before_live[count]
        p95_bound = max(prior["latency"]["p95Ns"] * 4, 10_000_000)
        gates.extend([
            {"fixture": f"live-{count}", "gate": "eventBound", "passed": current["candidates"] <= 4_000},
            {"fixture": f"live-{count}", "gate": "p95Bound", "passed": current["latency"]["p95Ns"] <= p95_bound},
        ])

    gates.extend([
        {"fixture": "after", "gate": "providerCalls", "passed": after["providerCalls"] == before["providerCalls"] == 0},
        {"fixture": "after", "gate": "historyWrites", "passed": after["historyWrites"] == before["historyWrites"] == 0},
        {"fixture": "after", "gate": "cacheHitMiss", "passed": after["cache"]["hits"] == after["cache"]["misses"] == 1},
        {"fixture": "after", "gate": "cacheEntryBound", "passed": after["cache"]["entries"] <= after["cache"]["entryBound"]},
        {"fixture": "after", "gate": "cacheByteBound", "passed": after["cache"]["bytes"] <= after["cache"]["byteBound"]},
        {"fixture": "after", "gate": "lockHeldWork", "passed": after["lockHeldWork"] == "cache-lookup-and-update-only"},
    ])
    result = {
        "schemaVersion": 1,
        "contentFree": True,
        "passed": all(item["passed"] for item in gates),
        "gates": gates,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
