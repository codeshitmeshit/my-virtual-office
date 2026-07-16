#!/usr/bin/env python3
"""Compare the fixed Codex warm-chat baseline with a fast-path candidate."""

import argparse
import json
from pathlib import Path


def _delta(candidate, baseline):
    return round(float(candidate) - float(baseline), 3)


def compare(baseline, candidate):
    base_fixture = baseline["fixture"]
    next_fixture = candidate["fixture"]
    base_stages = baseline["stages"]
    next_stages = candidate["stages"]
    base_counts = baseline["operationCounts"]
    next_counts = candidate["operationCounts"]
    measured = int(next_fixture["measuredTurns"])

    stage_comparison = {}
    for name, current in next_stages.items():
        prior = base_stages[name]
        stage_comparison[name] = {
            "samples": current["samples"],
            "baselineP95Ms": prior["p95Ms"],
            "candidateP95Ms": current["p95Ms"],
            "p95DeltaMs": _delta(current["p95Ms"], prior["p95Ms"]),
            "baselineMaxMs": prior["maxMs"],
            "candidateMaxMs": current["maxMs"],
        }

    count_comparison = {}
    for name, current in next_counts.items():
        prior = base_counts[name]
        count_comparison[name] = {
            "baselineTotal": prior["total"],
            "candidateTotal": current["total"],
            "totalDelta": int(current["total"] - prior["total"]),
            "baselinePerTurnMedian": prior["perTurnMedian"],
            "candidatePerTurnMedian": current["perTurnMedian"],
        }

    checks = [
        ("fixtureIdentity", base_fixture["kind"] == next_fixture["kind"] and base_fixture["warmups"] == next_fixture["warmups"] == 10 and base_fixture["measuredTurns"] == next_fixture["measuredTurns"] == 100),
        ("fastPathEnabled", next_fixture.get("fastPathEnabled") is True),
        ("noMeasuredFailures", candidate.get("failures") == []),
        ("allStageSamplesPresent", all(int(stage["samples"]) == measured for stage in next_stages.values())),
        ("workingFeedbackP95AtMost200Ms", next_stages["workingFeedbackMs"]["p95Ms"] <= 200),
        ("firstNativeEventP95AtMost1000Ms", next_stages["firstNativeEventMs"]["p95Ms"] <= 1000),
        ("firstFragmentNotDelayedBeyondCoalescingBound", next_stages["firstFragmentSseMs"]["p95Ms"] <= next_stages["firstNativeSseMs"]["p95Ms"] + 100),
        ("firstTextReportedSeparately", next_stages["firstTextSseMs"]["samples"] == measured),
        ("noFixedTerminal200MsFloor", next_stages["terminalTailMs"]["p50Ms"] < 100 and next_stages["terminalTailMs"]["p50Ms"] < base_stages["terminalTailMs"]["p50Ms"] - 100),
        ("readerCallbackP95Improved", next_stages["readerCallbackTotalMs"]["p95Ms"] < base_stages["readerCallbackTotalMs"]["p95Ms"]),
        ("activityWritesReduced", next_counts["activityJsonWrites"]["total"] < base_counts["activityJsonWrites"]["total"]),
        ("communicationProgressRewritesEliminated", next_counts["communicationProgressRewrites"]["total"] == 0),
        ("communicationHistoryLoadsReduced", next_counts["communicationHistoryLoads"]["total"] < base_counts["communicationHistoryLoads"]["total"]),
        # The candidate deliberately adds one idempotent terminal operation to
        # the accepted-user and final-reply appends already present per turn.
        ("durableCommunicationAppendsExpected", next_counts["communicationAppends"]["total"] == measured * 3),
    ]
    return {
        "schemaVersion": 1,
        "passed": all(passed for _name, passed in checks),
        "fixture": {
            "kind": next_fixture["kind"],
            "warmups": next_fixture["warmups"],
            "measuredTurns": measured,
            "externalModelOrCredentials": next_fixture["externalModelOrCredentials"],
        },
        "checks": [{"gate": name, "passed": passed} for name, passed in checks],
        "stageComparison": stage_comparison,
        "operationCountComparison": count_comparison,
        "operationCountNote": "Communication appends rise from 2 to 3 per turn because terminal outcome is now an idempotent durable record; transient activity writes and progress rewrites are the performance targets.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    result = compare(baseline, candidate)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
