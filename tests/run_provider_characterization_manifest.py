#!/usr/bin/env python3
"""Run and record the checked-in Provider characterization manifest."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "openspec" / "changes" / "extract-provider-services-and-finish-modularization" / "evidence" / "baseline"
MANIFEST = BASELINE / "provider-characterization-manifest.json"
RESULT = BASELINE / "provider-characterization-result.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-result", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    results = []
    for item in manifest["commands"]:
        started = time.perf_counter()
        completed = subprocess.run(
            item["command"], cwd=ROOT, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=300,
        )
        output = completed.stdout or ""
        results.append({
            "id": item["id"], "command": item["command"], "exitCode": completed.returncode,
            "durationMs": round((time.perf_counter() - started) * 1000, 3),
            "outputTail": output[-4000:],
        })
        print(f"[{'PASS' if completed.returncode == 0 else 'FAIL'}] {item['id']}")
        if completed.returncode:
            print(output[-4000:])
    payload = {
        "schema": 1,
        "manifest": MANIFEST.relative_to(ROOT).as_posix(),
        "passed": all(item["exitCode"] == 0 for item in results),
        "commandCount": len(results),
        "results": results,
    }
    if args.write_result:
        RESULT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
