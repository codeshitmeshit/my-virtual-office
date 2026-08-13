#!/usr/bin/env python3
"""Compare legacy JSON hot paths with the SQLite performance stores."""

from __future__ import annotations

import argparse
import copy
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.agent_event_repository import AgentEventRepository
from services.json_array_event_store import JsonArrayEventStore
from services.meeting_repository import MeetingDomainRepository, empty_store, normalize_store


def distribution(values: list[float]) -> dict:
    ordered = sorted(values)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))
    return {
        "runs": len(values),
        "medianMs": round(statistics.median(values), 4),
        "p95Ms": round(ordered[p95_index], 4),
        "minMs": round(ordered[0], 4),
        "maxMs": round(ordered[-1], 4),
    }


def measure(operation, *, warmups: int, runs: int) -> dict:
    for _ in range(warmups):
        operation()
    values = []
    for _ in range(runs):
        started = time.perf_counter_ns()
        operation()
        values.append((time.perf_counter_ns() - started) / 1_000_000)
    return distribution(values)


def comparison(legacy: dict, sqlite: dict) -> dict:
    legacy_median = float(legacy["medianMs"])
    sqlite_median = float(sqlite["medianMs"])
    speedup = legacy_median / sqlite_median if sqlite_median else 0.0
    reduction = (1.0 - sqlite_median / legacy_median) * 100 if legacy_median else 0.0
    return {
        "legacyJson": legacy,
        "sqlite": sqlite,
        "medianSpeedup": round(speedup, 2),
        "medianLatencyReductionPct": round(reduction, 1),
    }


def agent_event(sequence: int, *, scopes: int = 20) -> dict:
    scope = sequence % scopes
    return {
        "id": f"event-{sequence}", "agentId": f"agent-{scope % 4}",
        "conversationId": f"conversation-{scope}", "sequence": sequence // scopes + 1,
        "providerSequence": sequence, "type": "activity", "status": "running",
        "ts": 1_700_000_000_000 + sequence,
        "text": "x" * 160,
    }


def benchmark_agent(size: int, *, runs: int, warmups: int) -> dict:
    seed = [agent_event(index) for index in range(size)]
    with tempfile.TemporaryDirectory(prefix=f"agent-json-{size}-") as legacy_dir, tempfile.TemporaryDirectory(
        prefix=f"agent-sqlite-{size}-"
    ) as sqlite_dir:
        legacy_path = str(Path(legacy_dir) / "codex-activity.json")
        legacy = JsonArrayEventStore(max_events=5_000)
        legacy.save(legacy_path, seed)
        sqlite = AgentEventRepository(sqlite_dir, max_events=5_000)
        sqlite.save_compat(seed)
        next_legacy = size
        next_sqlite = size

        def append_legacy():
            nonlocal next_legacy
            events = legacy.load(legacy_path)
            events.append(agent_event(next_legacy))
            legacy.save(legacy_path, events)
            next_legacy += 1

        def append_sqlite():
            nonlocal next_sqlite
            events = sqlite.load_all()
            events.append(agent_event(next_sqlite))
            sqlite.save_compat(events)
            next_sqlite += 1

        def query_legacy():
            return [
                event for event in legacy.load(legacy_path)
                if event.get("agentId") == "agent-3" and event.get("conversationId") == "conversation-19"
                and int(event.get("sequence") or 0) > 0
            ]

        def query_sqlite():
            return sqlite.list_scope("agent-3", "conversation-19", after=0)

        append_json = measure(append_legacy, warmups=warmups, runs=runs)
        append_db = measure(append_sqlite, warmups=warmups, runs=runs)
        query_json = measure(query_legacy, warmups=warmups, runs=runs)
        query_db = measure(query_sqlite, warmups=warmups, runs=runs)
        return {
            "records": size,
            "append": comparison(append_json, append_db),
            "scopedQuery": comparison(query_json, query_db),
            "bytes": {
                "legacyJson": Path(legacy_path).stat().st_size,
                "sqlite": sqlite.path.stat().st_size,
                "sqliteWal": sqlite.path.with_name(sqlite.path.name + "-wal").stat().st_size
                if sqlite.path.with_name(sqlite.path.name + "-wal").exists() else 0,
            },
        }


def meeting_fixture(size: int) -> dict:
    data = empty_store()
    for index in range(size):
        meeting_id = f"m-{index:04d}"
        participants = [f"agent-{index * 2}", f"agent-{index * 2 + 1}"]
        data["meetings"][meeting_id] = {
            "id": meeting_id, "stage": "active_discussion", "version": 1,
            "participants": participants, "topic": "x" * 120,
        }
        data["events"][meeting_id] = [
            {"id": f"{meeting_id}-event-{event}", "sequence": event + 1, "type": "participant_turn", "payload": {"text": "y" * 180}}
            for event in range(20)
        ]
        data["occupancy"].update({participant: meeting_id for participant in participants})
        request_id = f"r-{index:04d}"
        data["requests"][request_id] = {
            "id": request_id, "status": "confirmed", "conversion": {"meetingId": meeting_id},
        }
    return normalize_store(data)


class LegacyMeetingJsonStore:
    """The former cached snapshot + whole-file atomic replacement behavior."""

    def __init__(self, directory: str, data: dict):
        self.path = Path(directory) / "meeting-domain.json"
        self.data = copy.deepcopy(data)
        self._write(self.data)

    def _write(self, data: dict) -> None:
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)
        directory = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def update(self, mutator) -> None:
        data = copy.deepcopy(self.data)
        mutator(data)
        data["updatedAt"] = "2026-08-13T00:00:00Z"
        validated = normalize_store(data, strict=True)
        self._write(validated)
        self.data = copy.deepcopy(validated)

    def snapshot(self) -> dict:
        return copy.deepcopy(self.data)


def benchmark_meeting(size: int, *, runs: int, warmups: int) -> dict:
    seed = meeting_fixture(size)
    target = "m-0000"
    with tempfile.TemporaryDirectory(prefix=f"meeting-json-{size}-") as legacy_dir, tempfile.TemporaryDirectory(
        prefix=f"meeting-sqlite-{size}-"
    ) as sqlite_dir:
        legacy = LegacyMeetingJsonStore(legacy_dir, seed)
        sqlite = MeetingDomainRepository(sqlite_dir)
        sqlite.import_store(copy.deepcopy(seed))
        legacy_sequence = 20
        sqlite_sequence = 20

        def append_legacy():
            nonlocal legacy_sequence
            legacy_sequence += 1
            event = {"id": f"legacy-{legacy_sequence}", "sequence": legacy_sequence, "type": "participant_turn", "payload": {"text": "z" * 180}}
            legacy.update(lambda data: data["events"][target].append(event))

        def append_sqlite():
            nonlocal sqlite_sequence
            sqlite_sequence += 1
            event = {"id": f"sqlite-{sqlite_sequence}", "sequence": sqlite_sequence, "type": "participant_turn", "payload": {"text": "z" * 180}}
            sqlite.mutate_meeting(target, lambda data: data["events"][target].append(event))

        append_json = measure(append_legacy, warmups=warmups, runs=runs)
        append_db = measure(append_sqlite, warmups=warmups, runs=runs)
        snapshot_json = measure(legacy.snapshot, warmups=warmups, runs=runs)
        snapshot_db = measure(lambda: (sqlite.get_meeting(target), sqlite.list_events(target)), warmups=warmups, runs=runs)
        return {
            "meetings": size, "initialEvents": size * 20,
            "eventAppend": comparison(append_json, append_db),
            "targetDetailRead": comparison(snapshot_json, snapshot_db),
            "bytes": {
                "legacyJson": legacy.path.stat().st_size,
                "sqlite": sqlite.path.stat().st_size,
                "sqliteWal": sqlite.path.with_name(sqlite.path.name + "-wal").stat().st_size
                if sqlite.path.with_name(sqlite.path.name + "-wal").exists() else 0,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--output")
    args = parser.parse_args()
    report = {
        "schema": 1,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": {
            "platform": platform.platform(), "python": platform.python_version(),
            "filesystem": "local temporary directories",
        },
        "method": {
            "runs": args.runs, "warmups": args.warmups,
            "agentLegacy": "cached JSON read plus bounded whole-file atomic rewrite",
            "meetingLegacy": "cached deep-copy snapshot plus whole-file atomic rewrite",
            "sqlite": "production repositories with WAL and row-level incremental commits",
            "interpretation": "Positive latency reduction and speedup above 1.0 favor SQLite; negative values are regressions.",
        },
        "agentEvents": {}, "meetings": {},
    }
    for size in (100, 1_000, 4_000):
        report["agentEvents"][str(size)] = benchmark_agent(size, runs=args.runs, warmups=args.warmups)
    for size in (1, 20, 100):
        report["meetings"][str(size)] = benchmark_meeting(size, runs=args.runs, warmups=args.warmups)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
