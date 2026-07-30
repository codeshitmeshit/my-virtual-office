"""Bounded MCP tool-schema discovery for usage-guide generation."""

from __future__ import annotations

import json
import os
import select
import signal
import subprocess
import time
from typing import Any, Mapping


class McpIntrospectionError(RuntimeError):
    """Raised when an MCP server cannot be safely inspected."""


def _bounded_input_schema(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    try:
        encoded = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return {}
    if len(encoded.encode("utf-8")) <= 8 * 1024:
        return value
    properties = value.get("properties")
    property_names = (
        [str(name)[:160] for name in list(properties)[:80]]
        if isinstance(properties, dict)
        else []
    )
    return {
        "type": str(value.get("type") or "object")[:80],
        "required": [
            str(name)[:160] for name in (value.get("required") or [])[:80]
        ],
        "propertyNames": property_names,
        "_truncated": True,
    }


def _request(
    process: subprocess.Popen[str],
    request_id: int,
    method: str,
    params: Mapping[str, Any],
    *,
    deadline: float,
) -> dict[str, Any]:
    if process.stdin is None or process.stdout is None:
        raise McpIntrospectionError("MCP process pipes are unavailable")
    process.stdin.write(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": dict(params),
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    process.stdin.flush()
    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        ready, _, _ = select.select([process.stdout], [], [], remaining)
        if not ready:
            break
        line = process.stdout.readline()
        if not line:
            break
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message.get("id") != request_id:
            continue
        if message.get("error"):
            raise McpIntrospectionError(
                str(message["error"].get("message") or "MCP request failed")
            )
        result = message.get("result")
        return result if isinstance(result, dict) else {}
    raise McpIntrospectionError(f"MCP {method} request timed out")


def inspect_stdio_tools(
    server: Mapping[str, Any],
    *,
    timeout_seconds: int = 12,
    max_tools: int = 100,
) -> list[dict[str, Any]]:
    """Start one stdio MCP server and return bounded public tool definitions."""

    if str(server.get("transport") or "stdio") != "stdio":
        raise McpIntrospectionError(
            "Only stdio MCP tool introspection is currently supported"
        )
    command = str(server.get("command") or "").strip()
    if not command:
        raise McpIntrospectionError("MCP command is missing")
    args = [str(value) for value in (server.get("args") or [])]
    environment = os.environ.copy()
    environment.update(
        {
            str(key): str(value)
            for key, value in (server.get("env") or {}).items()
        }
    )
    deadline = time.monotonic() + max(1, min(int(timeout_seconds), 30))
    try:
        process = subprocess.Popen(
            [command, *args],
            cwd=str(server.get("cwd") or "") or None,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except OSError as exc:
        raise McpIntrospectionError(str(exc)) from exc

    try:
        initialized = _request(
            process,
            1,
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {
                    "name": "virtual-office-guide-organizer",
                    "version": "1.0",
                },
            },
            deadline=deadline,
        )
        if process.stdin is None:
            raise McpIntrospectionError("MCP process input is unavailable")
        process.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                }
            )
            + "\n"
        )
        process.stdin.flush()

        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        request_id = 2
        while len(tools) < max_tools:
            params = {"cursor": cursor} if cursor else {}
            page = _request(
                process,
                request_id,
                "tools/list",
                params,
                deadline=deadline,
            )
            for raw in page.get("tools") or []:
                if not isinstance(raw, dict):
                    continue
                tools.append(
                    {
                        "name": str(raw.get("name") or "")[:160],
                        "description": str(raw.get("description") or "")[:1200],
                        "inputSchema": _bounded_input_schema(
                            raw.get("inputSchema")
                        ),
                    }
                )
                if len(tools) >= max_tools:
                    break
            cursor = str(page.get("nextCursor") or "").strip() or None
            if not cursor:
                break
            request_id += 1
        _ = initialized
        return tools
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=2)
