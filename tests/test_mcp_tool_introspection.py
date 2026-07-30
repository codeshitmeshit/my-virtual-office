from __future__ import annotations

import os

from services.mcp_tool_introspection import inspect_stdio_tools


def test_stdio_introspection_reads_public_tool_schema(tmp_path):
    server = tmp_path / "fake-mcp"
    server.write_text(
        """#!/usr/bin/env python3
import json
import sys
for line in sys.stdin:
    message = json.loads(line)
    if message.get("method") == "initialize":
        print(json.dumps({"jsonrpc":"2.0","id":message["id"],"result":{"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"fake","version":"1"}}}), flush=True)
    elif message.get("method") == "tools/list":
        print(json.dumps({"jsonrpc":"2.0","id":message["id"],"result":{"tools":[{"name":"lookup","description":"Look up records","inputSchema":{"type":"object"}}]}}), flush=True)
""",
        encoding="utf-8",
    )
    os.chmod(server, 0o755)

    tools = inspect_stdio_tools(
        {
            "transport": "stdio",
            "command": str(server),
            "args": [],
        },
        timeout_seconds=3,
    )

    assert tools == [
        {
            "name": "lookup",
            "description": "Look up records",
            "inputSchema": {"type": "object"},
        }
    ]


def test_stdio_introspection_bounds_oversized_schemas(tmp_path):
    server = tmp_path / "large-schema-mcp"
    server.write_text(
        """#!/usr/bin/env python3
import json
import sys
for line in sys.stdin:
    message = json.loads(line)
    if message.get("method") == "initialize":
        print(json.dumps({"jsonrpc":"2.0","id":message["id"],"result":{}}), flush=True)
    elif message.get("method") == "tools/list":
        schema = {"type":"object","properties":{f"field_{i}":{"type":"string","description":"x"*500} for i in range(100)}}
        print(json.dumps({"jsonrpc":"2.0","id":message["id"],"result":{"tools":[{"name":"large","inputSchema":schema}]}}), flush=True)
""",
        encoding="utf-8",
    )
    os.chmod(server, 0o755)

    tools = inspect_stdio_tools(
        {"transport": "stdio", "command": str(server)},
        timeout_seconds=3,
    )

    assert tools[0]["inputSchema"]["_truncated"] is True
    assert len(tools[0]["inputSchema"]["propertyNames"]) == 80
