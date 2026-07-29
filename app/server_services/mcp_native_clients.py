"""Native Codex and Claude MCP client registration."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

_CLIENTS = {"codex", "claude"}
_CODEX_APP_BINARY = Path("/Applications/ChatGPT.app/Contents/Resources/codex")


def _find_binary(client: str) -> str | None:
    binary = shutil.which(client)
    if binary:
        return binary
    if client == "codex" and _CODEX_APP_BINARY.is_file():
        return str(_CODEX_APP_BINARY)
    return None


def _run_client(client: str, args: list[str], timeout: int = 30) -> dict[str, Any]:
    binary = _find_binary(client)
    if not binary:
        return {"ok": False, "error": f"{client} CLI not found", "_status": 500}
    try:
        result = subprocess.run([binary, *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"{client} command timed out", "_status": 504}
    except OSError as exc:
        return {"ok": False, "error": str(exc), "_status": 500}
    if result.returncode != 0:
        return {
            "ok": False,
            "error": (result.stderr or result.stdout or f"{client} command failed").strip()[:2000],
            "code": result.returncode,
            "_status": 500,
        }
    return {"ok": True, "stdout": result.stdout, "stderr": result.stderr}


def _codex_args(server: dict[str, Any]) -> tuple[list[str], list[str]]:
    transport = server.get("transport")
    if transport == "sse":
        raise ValueError("Codex does not support registering legacy SSE MCP servers")
    if transport == "stdio":
        args = ["mcp", "add"]
        for key, value in (server.get("env") or {}).items():
            args.extend(["--env", f"{key}={value}"])
        args.extend([server["name"], "--", server["command"], *server.get("args", [])])
        warnings = ["Codex CLI does not persist the configured working directory"] if server.get("cwd") else []
        return args, warnings
    return ["mcp", "add", server["name"], "--url", server["url"]], []


def _claude_args(server: dict[str, Any], scope: str) -> tuple[list[str], list[str]]:
    if scope not in {"local", "project", "user"}:
        raise ValueError("Claude scope must be local, project, or user")
    transport = server.get("transport")
    if transport == "stdio":
        config: dict[str, Any] = {
            "type": "stdio",
            "command": server["command"],
            "args": server.get("args", []),
        }
        if server.get("env"):
            config["env"] = server["env"]
    else:
        config = {
            "type": "http" if transport == "streamable-http" else "sse",
            "url": server["url"],
        }
    warnings = ["Claude CLI does not persist the configured working directory"] if server.get("cwd") else []
    return [
        "mcp",
        "add-json",
        "--scope",
        scope,
        server["name"],
        json.dumps(config, ensure_ascii=False, separators=(",", ":")),
    ], warnings


def _redact_env_values(result: dict[str, Any], server: dict[str, Any]) -> dict[str, Any]:
    error = result.get("error")
    if not error:
        return result
    redacted = str(error)
    for value in (server.get("env") or {}).values():
        if value:
            redacted = redacted.replace(str(value), "***")
    result["error"] = redacted
    return result


def register_native_client(
    client: str,
    server: dict[str, Any],
    *,
    claude_scope: str = "user",
) -> dict[str, Any]:
    """Register a normalized VO MCP server in a supported native client."""
    normalized_client = str(client or "").strip().lower()
    if normalized_client not in _CLIENTS:
        return {"ok": False, "error": f"unsupported MCP client: {client}", "_status": 400}
    try:
        if normalized_client == "codex":
            args, warnings = _codex_args(server)
        else:
            args, warnings = _claude_args(server, claude_scope)
    except (KeyError, ValueError) as exc:
        return {"ok": False, "error": str(exc), "_status": 400}
    result = _redact_env_values(_run_client(normalized_client, args), server)
    if (
        normalized_client == "claude"
        and not result.get("ok")
        and "already exists" in str(result.get("error") or "").lower()
    ):
        remove_result = _run_client(
            "claude",
            ["mcp", "remove", server["name"], "--scope", claude_scope],
        )
        if not remove_result.get("ok"):
            return _redact_env_values(remove_result, server)
        result = _redact_env_values(_run_client("claude", args), server)
    if result.get("ok") and warnings:
        result["warnings"] = warnings
    return result
