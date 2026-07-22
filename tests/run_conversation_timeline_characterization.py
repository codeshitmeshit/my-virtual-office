#!/usr/bin/env python3
"""Validate and run the content-free conversation timeline baseline manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE = (
    ROOT
    / "openspec"
    / "changes"
    / "unify-conversation-timeline-projections"
    / "evidence"
    / "baseline"
)
MANIFEST = BASELINE / "conversation-timeline-characterization-manifest.json"
RESULT = BASELINE / "conversation-timeline-characterization-result.json"
PROVIDERS = {"codex", "claude-code", "hermes", "openclaw"}
FORBIDDEN_KEYS = {
    "message",
    "messageText",
    "reasoning",
    "reasoningText",
    "thinking",
    "thinkingText",
    "toolArguments",
    "toolResult",
    "prompt",
    "transcript",
}


def _walk_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def validate_manifest(manifest: dict) -> None:
    assert manifest.get("schema") == 1
    assert manifest.get("contentPolicy") == "content-free"
    assert set(manifest.get("providers") or {}) == PROVIDERS
    assert not (set(_walk_keys(manifest)) & FORBIDDEN_KEYS)

    routes = manifest.get("routeContracts") or {}
    assert routes["standardChatHistory"]["path"] == "/api/chat/history"
    assert routes["projectWorkflowChat"]["path"] == "/api/projects/{projectId}/workflow/chat"
    assert routes["providerEvents"]["path"] == "/api/provider/events"
    assert routes["standardChatHistory"]["maxPageSize"] == 50

    bounds = manifest.get("capacityBounds") or {}
    assert bounds == {
        "chatHistoryMaxPageSize": 50,
        "chatHistorySourceCandidateLimit": 1000,
        "historySourceCacheEntries": 32,
        "historySourceCacheBytes": 67108864,
        "mountedHistoricalRoots": 160,
        "providerEventRetention": 4000,
        "workflowMessageLimit": 50,
    }

    required_fields = {"id", "version", "providerKind", "conversationId", "role", "text", "epochMs", "tools", "thinking", "status", "source"}
    assert required_fields.issubset(set(manifest.get("canonicalHistoryFields") or []))
    assert manifest.get("scopeIsolation", {}).get("standardChat") == ["providerKind", "agentId", "conversationIdOrSessionKey"]
    assert manifest.get("scopeIsolation", {}).get("projectExecution") == ["projectId", "taskId", "attemptOrReviewId", "providerKind", "agentId"]

    command_ids = [item["id"] for item in manifest.get("commands") or []]
    assert command_ids
    assert len(command_ids) == len(set(command_ids))
    for item in manifest["commands"]:
        command = item.get("command")
        assert isinstance(command, list) and command
        assert all(isinstance(part, str) and part for part in command)


def run_manifest(manifest: dict) -> dict:
    results = []
    for item in manifest["commands"]:
        started = time.perf_counter()
        completed = subprocess.run(
            item["command"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=int(item.get("timeoutSec") or 300),
        )
        output = completed.stdout or ""
        result = {
            "id": item["id"],
            "exitCode": completed.returncode,
            "durationMs": round((time.perf_counter() - started) * 1000, 3),
            "outputBytes": len(output.encode("utf-8")),
            "outputLines": len(output.splitlines()),
            "outputSha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
        }
        results.append(result)
        print(f"[{'PASS' if completed.returncode == 0 else 'FAIL'}] {item['id']}")

    git_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    ).stdout.strip()
    return {
        "schema": 1,
        "manifest": MANIFEST.relative_to(ROOT).as_posix(),
        "contentPolicy": "content-free",
        "gitHead": git_head,
        "passed": all(item["exitCode"] == 0 for item in results),
        "commandCount": len(results),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-result", action="store_true")
    parser.add_argument("--check-result", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    if args.check_result:
        result = json.loads(RESULT.read_text(encoding="utf-8"))
        assert result.get("schema") == 1
        assert result.get("contentPolicy") == "content-free"
        assert result.get("passed") is True
        assert result.get("commandCount") == len(manifest["commands"])
        assert [item["id"] for item in result.get("results") or []] == [item["id"] for item in manifest["commands"]]
        assert all(item.get("exitCode") == 0 for item in result["results"])
        print("conversation timeline characterization result verified")
        return 0

    result = run_manifest(manifest)
    if args.write_result:
        RESULT.parent.mkdir(parents=True, exist_ok=True)
        RESULT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
