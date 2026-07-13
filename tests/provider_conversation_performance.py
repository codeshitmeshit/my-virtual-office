#!/usr/bin/env python3
"""Deterministic conversation-service scale and call-count evidence."""

import argparse
import json
from pathlib import Path
import statistics
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.provider_conversations import CallableConversationStatePort, CallableQueuedConversationPort, ConversationKey, ProviderConversationService  # noqa: E402


def fixture(scope_count):
    service = ProviderConversationService()
    stores = {index: {"messages": []} for index in range(scope_count)}
    durations = []

    def worker(index):
        key = ConversationKey("openclaw", f"agent-{index}", "default", f"conversation-{index}")
        port = CallableConversationStatePort(lambda _key: stores[index], lambda _key, value: stores.__setitem__(index, dict(value)))
        started = time.perf_counter_ns()
        service.overwrite(key, port, messages=[{"text": "x" * 128}] * 600, native_id=f"native-{index}")
        service.read(key, port)
        durations.append((time.perf_counter_ns() - started) / 1_000)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(scope_count)]
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    elapsed_ms = (time.perf_counter() - started) * 1_000
    return {
        "scopes": scope_count,
        "elapsedMs": round(elapsed_ms, 3),
        "medianOperationUs": round(statistics.median(durations), 3),
        "p95OperationUs": round(sorted(durations)[max(0, int(len(durations) * 0.95) - 1)], 3),
        "retainedScopes": service.diagnostics()["scopedConversations"],
        "maxRetainedMessages": max(len(store["messages"]) for store in stores.values()),
    }


def queued_delivery_counts():
    service = ProviderConversationService()
    calls = []
    port = CallableQueuedConversationPort(
        lambda key, native_id, message, attachments: calls.append((native_id, message)) or "ok",
        lambda key, native_id, action: {"ok": True},
    )
    for index in range(100):
        key = ConversationKey("openclaw", "agent", "default", f"conversation-{index}")
        service.deliver_queued(key, f"agent:agent:conversation-{index}", "hello", port)
    return {"requests": 100, "adapterCalls": len(calls), "syntheticRunRecords": service.diagnostics()["scopedConversations"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    result = {
        "schemaVersion": 1,
        "fixtures": [fixture(count) for count in (1, 20, 100)],
        "queuedDelivery": queued_delivery_counts(),
        "gates": {
            "boundedMessages": 500,
            "oneAdapterCallPerDelivery": True,
            "noSyntheticRunState": True,
        },
    }
    assert all(row["retainedScopes"] == row["scopes"] and row["maxRetainedMessages"] == 500 for row in result["fixtures"])
    assert result["queuedDelivery"] == {"requests": 100, "adapterCalls": 100, "syntheticRunRecords": 0}
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
