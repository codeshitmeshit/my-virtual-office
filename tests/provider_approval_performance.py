#!/usr/bin/env python3
"""Fixed capacity/count evidence for ProviderApprovalService."""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.provider_approvals import ProviderApprovalService, TrustedApprovalContext


def percentile(values, fraction):
    values = sorted(values)
    return values[min(len(values) - 1, round((len(values) - 1) * fraction))]


def measure():
    service = ProviderApprovalService(max_pending=1000, max_per_scope=100)
    latencies = []
    started = time.perf_counter_ns()
    for index in range(1000):
        context = TrustedApprovalContext("hermes", f"agent-{index // 100}", "default", f"session-{index // 100}", f"run-{index}")
        one = time.perf_counter_ns()
        service.register(context, {"id": f"approval-{index}", "command": "safe fixture", "choices": ["once", "session", "always", "deny"]})
        latencies.append(time.perf_counter_ns() - one)
    total_ns = time.perf_counter_ns() - started
    before = service.stats()
    resolved = 0
    provider_calls = 0
    for index in range(100):
        context = TrustedApprovalContext("hermes", "agent-0", "default", "session-0", f"run-{index}")

        def continuation(record, choice):
            nonlocal provider_calls
            provider_calls += 1
            return {"ok": True, "choice": choice}

        outcome = service.resolve(context, f"approval-{index}", "once", continuation)
        resolved += int(bool(outcome.claimed and (outcome.outcome or {}).get("ok")))
        replay = service.resolve(context, f"approval-{index}", "once", continuation)
        assert replay.replay
    return {
        "schema": 1,
        "registered": 1000,
        "pendingBeforeResolution": before["pending"],
        "scopeCount": before["scopes"],
        "resolved": resolved,
        "providerCalls": provider_calls,
        "pendingAfterResolution": service.stats()["pending"],
        "totalRegistrationNs": total_ns,
        "registrationLatency": {
            "medianNs": int(statistics.median(latencies)),
            "p95Ns": int(percentile(latencies, 0.95)),
            "maxNs": max(latencies),
        },
    }


def validate(data):
    assert data["registered"] == data["pendingBeforeResolution"] == 1000
    assert data["scopeCount"] == 10
    assert data["resolved"] == data["providerCalls"] == 100
    assert data["pendingAfterResolution"] == 900
    assert data["totalRegistrationNs"] < 5_000_000_000


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
    print("provider approval performance verified")


if __name__ == "__main__":
    main()
