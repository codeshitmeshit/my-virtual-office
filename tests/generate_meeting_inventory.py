#!/usr/bin/env python3
"""Emit a deterministic Meeting-domain definition and call-edge inventory."""

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT / "app" / "server.py").read_text(encoding="utf-8"))
functions = {
    node.name: node for node in ast.walk(tree)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
meeting_names = {name for name in functions if "meeting" in name.lower()}
edges = set()
for caller, node in functions.items():
    for call in ast.walk(node):
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
            callee = call.func.id
            if caller in meeting_names or callee in meeting_names:
                edges.add((caller, callee))

print(json.dumps({
    "schema": 1,
    "definitions": sorted(meeting_names),
    "edges": [{"caller": caller, "callee": callee} for caller, callee in sorted(edges)],
}, indent=2, sort_keys=True))
