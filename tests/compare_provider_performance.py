#!/usr/bin/env python3
"""Compare Provider fixed-fixture primary gates and bounded timing evidence."""

import argparse
import json
from pathlib import Path


def indexed(data, key):
    return {item["fixtureCount"]: item for item in data[key]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    parser.add_argument("--write-result")
    args = parser.parse_args()
    baseline = json.loads(Path(args.baseline).read_text())
    candidate = json.loads(Path(args.candidate).read_text())
    checks = []
    for count, current in indexed(candidate, "runFixtures").items():
        prior = indexed(baseline, "runFixtures")[count]
        checks.extend([
            {"fixture": f"runs-{count}", "gate": "adapterLaunches", "passed": current["adapterLaunches"] == prior["adapterLaunches"]},
            {"fixture": f"runs-{count}", "gate": "terminalEvents", "passed": current["terminalEvents"] == prior["terminalEvents"]},
            {"fixture": f"runs-{count}", "gate": "registeredRuns", "passed": current["registeredRuns"] == count},
            {"fixture": f"runs-{count}", "gate": "p95Bound", "passed": current["operationLatency"]["p95Ns"] <= max(prior["operationLatency"]["p95Ns"] * 12, 1_000_000)},
        ])
    for count, current in indexed(candidate, "eventFixtures").items():
        prior = indexed(baseline, "eventFixtures")[count]
        checks.extend([
            {"fixture": f"events-{count}", "gate": "publishCount", "passed": current["publishedEvents"] == prior["publishedEvents"]},
            {"fixture": f"events-{count}", "gate": "retention", "passed": current["retainedEvents"] == min(count, 4000)},
            {"fixture": f"events-{count}", "gate": "replayCount", "passed": current["replayedEvents"] == count},
            {"fixture": f"events-{count}", "gate": "publishP95Bound", "passed": current["publishLatency"]["p95Ns"] <= max(prior["publishLatency"]["p95Ns"] * 12, 1_000_000)},
        ])
    result = {"schema": 1, "passed": all(item["passed"] for item in checks), "checks": checks}
    if args.write_result:
        Path(args.write_result).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
