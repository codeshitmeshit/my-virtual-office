#!/usr/bin/env python3
"""Fixed 1/20/100-run performance and count evidence for ProviderRunCoordinator."""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.provider_events import ProviderEventJournal
from app.services.provider_ports import AdapterCapabilities, AdapterResult, RunCommand
from app.services.provider_registry import ProviderRunRepository
from app.services.provider_runs import ProviderRunCoordinator


class ImmediateAdapter:
    provider_kind = "codex"
    provider_path = "fixture"
    capabilities = AdapterCapabilities(background_run=True, streaming_events=True, cancel=True)

    def __init__(self):
        self.launches = 0

    def run(self, command, emit, cancel_event):
        self.launches += 1
        return AdapterResult({"ok": True, "status": "completed", "reply": "ok"}, {"reply": "ok", "status": "completed"})

    def cancel(self, command, snapshot, payload):
        return {"ok": True, "status": "cancelled"}


def percentile(values, fraction):
    values = sorted(values)
    return values[min(len(values) - 1, round((len(values) - 1) * fraction))]


def fixture(count):
    repository = ProviderRunRepository()
    journal = ProviderEventJournal()
    coordinator = ProviderRunCoordinator(repository, journal)
    adapter = ImmediateAdapter()
    start_latencies = []
    outcomes = []
    overall = time.perf_counter_ns()
    for index in range(count):
        started = time.perf_counter_ns()
        outcomes.append(coordinator.start(RunCommand(
            provider_kind="codex", provider_path="fixture", agent_id=f"agent-{index}",
            conversation_id=f"conv-{index}", idempotency_key="fixed", timeout_sec=2,
        ), adapter=adapter))
        start_latencies.append(time.perf_counter_ns() - started)
    deadline = time.time() + 5
    while time.time() < deadline:
        snapshots = repository.snapshots()
        if len(snapshots) == count and all(item.get("terminal") for item in snapshots.values()):
            break
        time.sleep(0.001)
    total_ns = time.perf_counter_ns() - overall
    snapshots = repository.snapshots()
    terminals = [item for item in journal.events_after() if item["event"] in {"run.completed", "run.failed", "run.cancelled"}]
    return {
        "fixtureCount": count,
        "adapterLaunches": adapter.launches,
        "registeredRuns": len(snapshots),
        "terminalRuns": sum(bool(item.get("terminal")) for item in snapshots.values()),
        "terminalEvents": len(terminals),
        "totalNs": total_ns,
        "startLatency": {
            "medianNs": int(statistics.median(start_latencies)),
            "p95Ns": int(percentile(start_latencies, 0.95)),
            "maxNs": max(start_latencies),
        },
        "activeHandlesAfterCompletion": coordinator.diagnostics()["activeHandleCount"],
    }


def measure():
    return {"schema": 1, "fixtures": [fixture(count) for count in (1, 20, 100)]}


def validate(data):
    assert [item["fixtureCount"] for item in data["fixtures"]] == [1, 20, 100]
    for item in data["fixtures"]:
        count = item["fixtureCount"]
        assert item["adapterLaunches"] == item["registeredRuns"] == item["terminalRuns"] == item["terminalEvents"] == count
        assert item["activeHandlesAfterCompletion"] == 0
        assert item["totalNs"] < 5_000_000_000


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write")
    parser.add_argument("--check")
    args = parser.parse_args()
    if args.write:
        data = measure()
        validate(data)
        path = Path(args.write)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        print(path)
        return
    path = Path(args.check)
    validate(json.loads(path.read_text()))
    print("provider coordinator performance verified")


if __name__ == "__main__":
    main()
