#!/usr/bin/env python3
"""Compare current standard chat with the frozen pre-migration projection."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from conversation_timeline_compatibility import DEFAULT_POLICY, assess


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "openspec/changes/unify-conversation-timeline-projections/evidence/baseline/standard-chat-pre-migration.json"
SNAPSHOT = ROOT / "tests/standard_chat_compatibility_snapshot.py"
UI_COMMANDS = (
    ("store", ["node", "tests/check_chat_history_store.mjs"]),
    ("navigation", ["node", "tests/check_chat_history_navigation.mjs"]),
    ("live-sse", ["node", "tests/check_provider_chat_sse.mjs"]),
)


def main() -> int:
    completed = subprocess.run(
        [str(ROOT / ".venv/bin/python"), str(SNAPSHOT), "--app-dir", str(ROOT / "app")],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        print(completed.stderr)
        return completed.returncode
    current = json.loads(completed.stdout)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    policy = json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))
    comparison = assess(baseline, current, policy)
    if not comparison["ok"]:
        print(json.dumps(comparison, indent=2, sort_keys=True))
        return 1

    for name, command in UI_COMMANDS:
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        if result.returncode:
            print(f"[{name}] failed\n{result.stdout}")
            return result.returncode
        print(f"[{name}] passed")
    print("standard chat pre/post timeline comparison passed for four providers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
