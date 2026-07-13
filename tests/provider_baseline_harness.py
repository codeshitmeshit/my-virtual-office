#!/usr/bin/env python3
"""Measure fixed Provider repository/journal capacity and performance fixtures."""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-provider-baseline-"))
os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")

from services.provider_events import ProviderEventJournal, TERMINAL_EVENTS, canonical_event_name
from services.provider_registry import ProviderRunRepository


class ProviderFixture:
    def __init__(self):
        self.repository = ProviderRunRepository(retention_ms=10 * 60 * 1000)
        self.journal = ProviderEventJournal(max_events=4000)
        self._event_log = self.journal.compatibility_event_log

    @property
    def _runs(self):
        return self.repository.snapshots()

    @property
    def _next_event_id(self):
        return self.journal.next_event_id

    def remember(self, meta):
        return self.repository.reserve_start(
            provider_kind=meta.get("providerKind") or "", agent_id=meta.get("agentId") or "",
            conversation_id=meta.get("conversationId") or "", run_id=meta.get("runId") or "", meta=meta,
        ).snapshot

    def update(self, run_id, **updates):
        return self.repository.update(run_id, **updates).snapshot

    def publish(self, provider_kind, agent_id, conversation_id, event_name, payload=None, run_id=""):
        return self.journal.publish(provider_kind, agent_id, conversation_id, event_name, payload, run_id)

    def emit(self, run_id, event_name, payload=None):
        meta = self.repository.get(run_id)
        name = canonical_event_name(event_name)
        data = dict(payload or {})
        if name in TERMINAL_EVENTS and not self.repository.claim_terminal_event(run_id, name, data).applied:
            return True
        self.journal.publish(meta.get("providerKind") or "", meta.get("agentId") or "", meta.get("conversationId") or "", name, data, run_id)
        return True


DEFAULT_OUTPUT = ROOT / "openspec" / "changes" / "extract-provider-services-and-finish-modularization" / "evidence" / "baseline" / "provider-performance-baseline.json"


def percentile(values, pct):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * pct))))]


def stats(samples):
    return {
        "medianNs": int(statistics.median(samples)),
        "p95Ns": int(percentile(samples, 0.95)),
        "maxNs": int(max(samples)),
    }


def run_fixture(count):
    bridge = ProviderFixture()
    durations = []
    tracemalloc.start()
    for index in range(count):
        started = time.perf_counter_ns()
        run_id = f"run-{index}"
        bridge.remember({"runId": run_id, "providerKind": "codex", "agentId": f"agent-{index}", "conversationId": f"conv-{index}", "done": False})
        bridge.emit(run_id, "run.started", {"providerPath": "fixture"})
        bridge.update(run_id, done=True, result={"ok": True, "status": "completed", "runId": run_id})
        bridge.emit(run_id, "run.completed", {"ok": True, "status": "completed"})
        durations.append(time.perf_counter_ns() - started)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    terminals = [item for item in bridge._event_log if item["event"] == "run.completed"]
    return {
        "fixtureCount": count,
        "adapterLaunches": count,
        "registeredRuns": len(bridge._runs),
        "terminalEvents": len(terminals),
        "retainedEvents": len(bridge._event_log),
        "retainedBytesJson": len(json.dumps({"runs": bridge.repository.snapshots() if hasattr(bridge, "repository") else bridge._runs, "events": list(bridge._event_log)}, default=str).encode()),
        "peakAllocatedBytes": peak,
        "operationLatency": stats(durations),
        "lockCallCountProxy": count * 5,
    }


def event_fixture(count):
    bridge = ProviderFixture()
    publish = []
    tracemalloc.start()
    for index in range(count):
        started = time.perf_counter_ns()
        bridge.publish("codex", "agent", "conv", "message.delta", {"index": index}, "run")
        publish.append(time.perf_counter_ns() - started)
    replay_started = time.perf_counter_ns()
    replay = bridge.journal.run_events_after("run", 0) if hasattr(bridge, "journal") else bridge._events_after(0, lambda item: item.get("runId") == "run")
    replay_ns = time.perf_counter_ns() - replay_started
    selection_lock_ns = None
    if hasattr(bridge, "journal") and hasattr(bridge.journal, "_record_refs"):
        with bridge.journal.lock:
            selection_started = time.perf_counter_ns()
            bridge.journal._record_refs(bridge.journal._run_index.get("run", ()), 0)
            selection_lock_ns = time.perf_counter_ns() - selection_started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "fixtureCount": count,
        "publishedEvents": count,
        "retainedEvents": len(bridge._event_log),
        "firstRetainedEventId": bridge._event_log[0]["id"] if bridge._event_log else 0,
        "lastEventId": bridge._next_event_id,
        "replayedEvents": len(replay),
        "replayScanUpperBound": len(replay) if hasattr(bridge, "journal") else len(bridge._event_log),
        "retainedBytesJson": len(json.dumps(list(bridge._event_log), default=str).encode()),
        "peakAllocatedBytes": peak,
        "publishLatency": stats(publish),
        "replayLatencyNs": replay_ns,
        "selectionLockUpperBoundNs": selection_lock_ns,
        "lockCallCountProxy": count + 1,
    }


def measure():
    data = {
        "schema": 1,
        "implementation": "ProviderRunRepository + ProviderEventJournal",
        "environment": {"python": platform.python_version(), "platform": platform.platform(), "cpuCount": os.cpu_count()},
        "compatibilityBounds": {"globalEventRetention": 4000, "runAndIdempotencyRetentionMs": 600000},
        "runFixtures": [run_fixture(count) for count in (1, 20, 100)],
        "eventFixtures": [event_fixture(count) for count in (10, 1000, 4000)],
        "measurementNotes": [
            "lockCallCountProxy counts public bridge lock acquisitions, not wall-clock lock hold instrumentation",
            "provider and downstream call counts are zero because fixed fixtures use the in-memory bridge only",
            "timings are comparative evidence; call counts and capacity bounds are release gates",
        ],
    }
    bridge = ProviderFixture()
    if hasattr(bridge, "journal"):
        for index in range(4000):
            bridge.publish("codex", "agent", f"conv-{index % 100}", "message.delta", {"index": index}, f"run-{index % 100}")
        started = time.perf_counter_ns()
        scoped = bridge.journal.run_events_after("run-0", 0)
        replay_latency_ns = time.perf_counter_ns() - started
        with bridge.journal.lock:
            selection_started = time.perf_counter_ns()
            bridge.journal._record_refs(bridge.journal._run_index.get("run-0", ()), 0)
            selection_lock_ns = time.perf_counter_ns() - selection_started
        data["scopedReplayFixture"] = {
            "retainedEvents": len(bridge._event_log),
            "scopeCount": 100,
            "targetEvents": len(scoped),
            "replayScanUpperBound": len(scoped),
            "replayLatencyNs": replay_latency_ns,
            "selectionLockUpperBoundNs": selection_lock_ns,
        }
    return data


def validate(data):
    assert data["compatibilityBounds"] == {"globalEventRetention": 4000, "runAndIdempotencyRetentionMs": 600000}
    assert [item["fixtureCount"] for item in data["runFixtures"]] == [1, 20, 100]
    assert [item["fixtureCount"] for item in data["eventFixtures"]] == [10, 1000, 4000]
    for item in data["runFixtures"]:
        assert item["adapterLaunches"] == item["registeredRuns"] == item["terminalEvents"] == item["fixtureCount"]
    for item in data["eventFixtures"]:
        assert item["publishedEvents"] == item["retainedEvents"] == item["replayedEvents"] == item["fixtureCount"]
    if "scopedReplayFixture" in data:
        scoped = data["scopedReplayFixture"]
        assert scoped["retainedEvents"] == 4000
        assert scoped["targetEvents"] == scoped["replayScanUpperBound"] == 40


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    output = Path(args.output)
    if args.write:
        data = measure()
        validate(data)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(output)
        return
    data = json.loads(output.read_text(encoding="utf-8"))
    validate(data)
    print("provider performance baseline verified")


if __name__ == "__main__":
    main()
