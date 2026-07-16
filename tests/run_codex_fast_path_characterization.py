#!/usr/bin/env python3
"""Execute the checked-in Codex fast-path characterization manifest."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "openspec" / "changes" / "optimize-codex-chat-fast-path" / "evidence" / "baseline"
MANIFEST = EVIDENCE / "codex-fast-path-characterization-manifest.json"
RESULT = EVIDENCE / "codex-fast-path-characterization-result.json"


def resolve_command(raw: list[str]) -> list[str]:
    node = os.environ.get("VO_NODE_BIN") or shutil.which("node") or "node"
    return [sys.executable if value == "{python}" else node if value == "{node}" else value for value in raw]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-result", action="store_true")
    parser.add_argument("--check-result")
    args = parser.parse_args()
    if args.check_result:
        payload = json.loads(Path(args.check_result).read_text(encoding="utf-8"))
        assert payload.get("passed") is True
        assert payload.get("commandCount") == len(payload.get("results") or [])
        assert all(item.get("passed") is True for item in payload["results"])
        print("Codex fast-path characterization result verified")
        return 0

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    results = []
    for item in manifest["commands"]:
        command = resolve_command(item["command"])
        started = time.perf_counter()
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
            env={**os.environ, "VO_STATUS_DIR": os.environ.get("VO_STATUS_DIR", "/tmp/vo-codex-fast-path-characterization")},
        )
        output = completed.stdout or ""
        expected_exit_codes = item.get("expectedExitCodes") or [0]
        result = {
            "id": item["id"],
            "command": command,
            "exitCode": completed.returncode,
            "expectedExitCodes": expected_exit_codes,
            "passed": completed.returncode in expected_exit_codes,
            "durationMs": round((time.perf_counter() - started) * 1000, 3),
            "outputTail": output[-4000:],
        }
        if item.get("baselineExpectation"):
            result["baselineExpectation"] = item["baselineExpectation"]
        results.append(result)
        print(f"[{'PASS' if result['passed'] else 'FAIL'}] {item['id']} (exit={completed.returncode}, expected={expected_exit_codes})")
        if not result["passed"]:
            print(output[-4000:])
    payload = {
        "schema": 1,
        "manifest": MANIFEST.relative_to(ROOT).as_posix(),
        "passed": all(item["passed"] for item in results),
        "commandCount": len(results),
        "scenarioCount": len(manifest.get("scenarios") or []),
        "results": results,
    }
    if args.write_result:
        RESULT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
