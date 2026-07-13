#!/usr/bin/env python3
"""Generate deterministic Provider ownership and compatibility inventory artifacts."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHANGE = ROOT / "openspec" / "changes" / "extract-provider-services-and-finish-modularization"
EVIDENCE = CHANGE / "evidence" / "current"
KEYWORDS = ("provider", "openclaw", "codex", "claude", "hermes", "approval", "idempot", "sse")
EVENT_RE = re.compile(
    r"^(?:run|message|reasoning|tool|session|approval|provider|history|turn|clarify|sudo|secret)\.[a-zA-Z0-9_.-]+$"
)
STATE_NAMES = {
    "PROVIDER_RUN_REPOSITORY",
    "PROVIDER_EVENT_JOURNAL",
    "PROVIDER_RUN_COORDINATOR",
    "PROVIDER_CONVERSATION_SERVICE",
    "HERMES_APPROVAL_SERVICE",
    "_CODEX_ACTIVE",
    "_CODEX_ACTIVE_LOCK",
}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def source_files() -> list[Path]:
    candidates = sorted((ROOT / "app").rglob("*.py"))
    selected = []
    for path in candidates:
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if any(word in path.name.lower() or word in text.lower() for word in KEYWORDS):
            selected.append(path)
    return selected


def relevant(value: str) -> bool:
    lowered = value.lower()
    return any(word in lowered for word in KEYWORDS)


def relevant_route(value: str) -> bool:
    lowered = value.lower()
    return (
        any(word in lowered for word in KEYWORDS)
        or lowered.startswith("/api/chat")
        or "project-execution" in lowered
        or (lowered.startswith("/api/meetings/") and any(part in lowered for part in ("/run", "/transition", "/action-items")))
    )


class FunctionInventory(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.scope: list[str] = []
        self.definitions: list[dict] = []
        self.edges: set[tuple[str, str, int]] = set()
        self.state_access: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"readers": set(), "writers": set()})
        self.routes: set[tuple[str, int]] = set()
        self.events: set[tuple[str, int]] = set()

    @property
    def owner(self) -> str:
        return ".".join(self.scope) if self.scope else "<module>"

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.scope.append(node.name)
        if relevant(node.name):
            self.definitions.append({"name": self.owner, "file": rel(self.path), "line": node.lineno})
        self.generic_visit(node)
        self.scope.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        if relevant(node.name):
            self.definitions.append({"name": self.owner, "file": rel(self.path), "line": node.lineno})
        self.generic_visit(node)
        self.scope.pop()

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            callee = node.func.id
        elif isinstance(node.func, ast.Attribute):
            callee = node.func.attr
        else:
            callee = ""
        if callee and relevant(callee):
            self.edges.add((self.owner, callee, node.lineno))
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            state = node.func.value.id
            if state in STATE_NAMES and node.func.attr in {
                "append", "clear", "emit", "pop", "publish", "put", "remember", "remove",
                "setdefault", "stream_events", "stream_provider_events", "update",
            }:
                self.state_access[state]["writers"].add(self.owner)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in STATE_NAMES:
            mode = "writers" if isinstance(node.ctx, (ast.Store, ast.Del)) else "readers"
            self.state_access[node.id][mode].add(self.owner)

    def visit_Constant(self, node: ast.Constant) -> None:
        if not isinstance(node.value, str):
            return
        value = node.value.strip()
        if value.startswith("/api/") and relevant_route(value):
            self.routes.add((value, node.lineno))
        if EVENT_RE.fullmatch(value):
            self.events.add((value, node.lineno))


def build_inventory() -> dict:
    definitions: list[dict] = []
    edges: list[dict] = []
    routes: list[dict] = []
    events: dict[str, list[dict]] = defaultdict(list)
    state: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"readers": set(), "writers": set()})
    hashes = {}
    for path in source_files():
        raw = path.read_bytes()
        hashes[rel(path)] = hashlib.sha256(raw).hexdigest()
        visitor = FunctionInventory(path)
        visitor.visit(ast.parse(raw, filename=str(path)))
        definitions.extend(visitor.definitions)
        edges.extend(
            {"caller": caller, "callee": callee, "file": rel(path), "line": line}
            for caller, callee, line in visitor.edges
        )
        routes.extend({"path": route, "file": rel(path), "line": line} for route, line in visitor.routes)
        for event, line in visitor.events:
            events[event].append({"file": rel(path), "line": line})
        for name, access in visitor.state_access.items():
            state[name]["readers"].update(f"{rel(path)}::{owner}" for owner in access["readers"])
            state[name]["writers"].update(f"{rel(path)}::{owner}" for owner in access["writers"])
    return {
        "schema": 1,
        "sourceHashes": dict(sorted(hashes.items())),
        "definitions": sorted(definitions, key=lambda item: (item["file"], item["line"], item["name"])),
        "callEdges": sorted(edges, key=lambda item: (item["file"], item["line"], item["caller"], item["callee"])),
        "routes": sorted(routes, key=lambda item: (item["path"], item["file"], item["line"])),
        "stateAuthorities": {
            name: {"readers": sorted(access["readers"]), "writers": sorted(access["writers"])}
            for name, access in sorted(state.items())
        },
        "eventAliases": {name: sorted(locations, key=lambda item: (item["file"], item["line"])) for name, locations in sorted(events.items())},
    }


def capability_matrix() -> dict:
    return {
        "schema": 1,
        "paths": [
            {"providerKind": "openclaw", "providerPath": "gateway", "backgroundRun": False, "streamingEvents": False, "conversationContinuation": True, "attachments": True, "approvalContinuation": False, "cancel": False, "queuedDelivery": True, "owner": "app/server.py"},
            {"providerKind": "codex", "providerPath": "app-server/bridge", "backgroundRun": True, "streamingEvents": True, "conversationContinuation": True, "attachments": True, "approvalContinuation": True, "cancel": True, "queuedDelivery": False, "owner": "app/providers/codex.py"},
            {"providerKind": "claude-code", "providerPath": "claude-code-cli", "backgroundRun": True, "streamingEvents": True, "conversationContinuation": True, "attachments": True, "approvalContinuation": False, "cancel": True, "queuedDelivery": False, "owner": "app/providers/claude_code.py"},
            {"providerKind": "hermes", "providerPath": "api", "backgroundRun": True, "streamingEvents": True, "conversationContinuation": True, "attachments": True, "approvalContinuation": True, "cancel": True, "queuedDelivery": False, "owner": "app/providers/hermes.py"},
            {"providerKind": "hermes", "providerPath": "desktop", "backgroundRun": True, "streamingEvents": True, "conversationContinuation": True, "attachments": True, "approvalContinuation": False, "cancel": True, "queuedDelivery": False, "owner": "app/providers/hermes.py"},
            {"providerKind": "hermes", "providerPath": "gateway-platform", "backgroundRun": False, "streamingEvents": False, "conversationContinuation": True, "attachments": True, "approvalContinuation": False, "cancel": False, "queuedDelivery": True, "owner": "app/server.py"},
        ],
        "compatibilityRule": "Capabilities describe existing paths; unsupported behavior must not be synthesized.",
    }


def approval_bounds() -> dict:
    return {
        "schema": 1,
        "authorities": [
            {"name": "Hermes provider approval service", "state": "HERMES_APPROVAL_SERVICE", "file": "app/services/provider_approvals.py", "shape": "bounded records plus per-scope ordered queues", "bounded": True, "maxItems": 1000, "maxPerScope": 100, "cleanup": "fenced resolution plus resolved-retention pruning", "risk": "capacity eviction is explicit and tested"},
            {"name": "Codex app-server pending approvals", "state": "CodexAppServerProvider._pending_approvals", "file": "app/providers/codex_app_server.py", "shape": "dict[approvalId, approval]", "bounded": True, "maxItems": 100, "cleanup": "resolved/thread-close entries are removed; overflow is denied without registration", "risk": "bounded and fail-closed"},
            {"name": "Provider app-server request replies", "state": "ProviderAppServerClient._pending", "file": "app/provider_app_server.py", "shape": "dict[requestId, Queue(maxsize=1)]", "bounded": True, "maxItems": 1000, "cleanup": "finally/close removes requests; overflow is rejected before send", "risk": "bounded and fail-closed"},
        ],
        "requiredFinalState": "All Provider approval/request authorities have explicit aggregate bounds and deterministic overflow behavior",
    }


def transport_delegates() -> dict:
    return {
        "schema": 1,
        "candidates": [
            {"symbol": "OfficeHandler.do_GET", "allowed": "parse route/query/Last-Event-ID, authenticate, choose HTTP status and headers"},
            {"symbol": "OfficeHandler.do_POST", "allowed": "parse/validate request and assemble compatibility response"},
            {"symbol": "ProviderSSETransport.stream_run", "allowed": "HTTP headers, Last-Event-ID/after parsing, id/event/data framing, heartbeat, disconnect handling"},
            {"symbol": "ProviderSSETransport.stream_conversation", "allowed": "HTTP headers, Last-Event-ID/after parsing, snapshot/recovery framing, heartbeat, disconnect handling"},
            {"symbol": "_handle_codex_run_events", "allowed": "route adapter forwarding to transport stream"},
            {"symbol": "_handle_claude_code_run_events", "allowed": "route adapter forwarding to transport stream"},
            {"symbol": "_handle_hermes_run_events", "allowed": "route adapter forwarding to transport stream"},
        ],
        "mustMove": [],
    }


def outputs() -> dict[str, dict]:
    inventory = build_inventory()
    return {
        "provider-caller-writer-map.json": {key: value for key, value in inventory.items() if key != "eventAliases"},
        "provider-capability-matrix.json": capability_matrix(),
        "provider-event-alias-manifest.json": {"schema": 1, "aliases": inventory["eventAliases"]},
        "provider-approval-queue-bounds.json": approval_bounds(),
        "provider-transport-delegate-candidates.json": transport_delegates(),
    }


def encoded(value: dict) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    artifacts = outputs()
    if args.write:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        for name, value in artifacts.items():
            (EVIDENCE / name).write_text(encoded(value), encoding="utf-8")
        return 0
    failures = []
    for name, value in artifacts.items():
        path = EVIDENCE / name
        actual = path.read_text(encoding="utf-8") if path.exists() else ""
        if actual != encoded(value):
            failures.append(rel(path))
    if failures:
        print("provider inventory is stale: " + ", ".join(failures), file=sys.stderr)
        return 1
    print(f"provider inventory verified: {len(artifacts)} artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
