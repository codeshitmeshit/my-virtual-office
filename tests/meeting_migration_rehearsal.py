#!/usr/bin/env python3
"""Run small/medium/large offline Meeting migration rehearsals on copied fixtures."""

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "migrate_meeting_store.py"


def fixture(status: Path, size: int):
    meetings = {}; events = {}; occupancy = {}; requests = {}
    for index in range(size):
        meeting_id = f"m-{index:04d}"; request_id = f"r-{index:04d}"; agents = [f"a-{index * 2}", f"a-{index * 2 + 1}"]
        meetings[meeting_id] = {"id": meeting_id, "stage": "active_discussion", "participants": agents}
        events[meeting_id] = [{"id": f"e-{index}", "meetingId": meeting_id, "sequence": 1, "type": "participant_turn"}]
        occupancy.update({agent: meeting_id for agent in agents})
        requests[request_id] = {"id": request_id, "status": "confirmed", "source": {"projectId": f"p-{index}", "taskId": f"t-{index}"}, "conversion": {"meetingId": meeting_id}}
    executable = {"meetings": meetings, "events": events, "occupancy": occupancy, "idempotency": {"seed": size}, "updatedAt": "2026-07-13T00:00:00Z"}
    request_store = {"requests": requests, "idempotency": {"seed": size}, "updatedAt": "2026-07-13T00:00:01Z"}
    (status / "executable-meetings.json").write_text(json.dumps(executable, sort_keys=True), encoding="utf-8")
    (status / "meeting-requests.json").write_text(json.dumps(request_store, sort_keys=True), encoding="utf-8")


def run(status: Path, apply=False):
    command = [sys.executable, str(SCRIPT), "--status-dir", str(status)] + (["--apply"] if apply else [])
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    return completed.returncode, json.loads(completed.stdout)


def sha(path: Path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    result = {"schema": 1, "fixtures": {}}
    for label, size in (("small", 1), ("medium", 20), ("large", 100)):
        with tempfile.TemporaryDirectory(prefix=f"meeting-migration-{label}-") as directory:
            status = Path(directory); fixture(status, size)
            source_digests = {name: sha(status / name) for name in ("executable-meetings.json", "meeting-requests.json")}
            dry_code, dry = run(status); apply_code, applied = run(status, True)
            unified_digest = sha(status / "meeting-domain.json")
            repeat_code, repeated = run(status, True)
            backups = sorted(path.name for path in status.glob("*.backup-*"))
            result["fixtures"][label] = {
                "size": size, "dryRunExit": dry_code, "dryRunStatus": dry.get("status"),
                "applyExit": apply_code, "applyStatus": applied.get("status"),
                "repeatExit": repeat_code, "repeatStatus": repeated.get("status"),
                "counts": applied.get("counts"), "relationshipChecks": applied.get("relationshipChecks"),
                "sourceDigest": applied.get("sourceDigest"), "sourceFileDigests": source_digests,
                "unifiedDigest": unified_digest, "repeatUnifiedDigest": sha(status / "meeting-domain.json"),
                "backups": backups, "backupCount": len(backups),
            }
    assert all(item["dryRunStatus"] == "validated" and item["applyStatus"] == "migrated" and item["repeatStatus"] == "already_migrated" for item in result["fixtures"].values())
    assert all(item["unifiedDigest"] == item["repeatUnifiedDigest"] and item["backupCount"] == 2 for item in result["fixtures"].values())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__": main()
