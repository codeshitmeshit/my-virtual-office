"""VO-managed MCP server registry and client registration orchestration."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
REGISTRY_FILENAME = "mcp-registry.json"
_SAFE_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9_.-]{0,62}[a-z0-9])?$")
_SAFE_AGENT_ID_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.:-]{0,126}[A-Za-z0-9])?$")


def _server_module():
    return sys.modules.get("server") or sys.modules.get("__main__")


def _status_dir() -> str:
    server = _server_module()
    value = getattr(server, "STATUS_DIR", None) if server is not None else None
    return str(value or os.environ.get("VO_STATUS_DIR") or Path(__file__).resolve().parents[2] / "status")


def _registry_path() -> Path:
    root = Path(_status_dir())
    root.mkdir(parents=True, exist_ok=True)
    return root / REGISTRY_FILENAME


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_registry() -> dict[str, Any]:
    return {"schemaVersion": SCHEMA_VERSION, "servers": {}}


def _load_registry() -> dict[str, Any]:
    path = _registry_path()
    if not path.is_file():
        return _empty_registry()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_registry()
    if not isinstance(data, dict):
        return _empty_registry()
    servers = data.get("servers")
    if not isinstance(servers, dict):
        data["servers"] = {}
    data["schemaVersion"] = SCHEMA_VERSION
    return data


def _save_registry(data: dict[str, Any]) -> None:
    path = _registry_path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _safe_name(value: Any) -> str:
    name = str(value or "").strip().lower()
    if not _SAFE_NAME_RE.fullmatch(name):
        raise ValueError("name must be 1-64 chars: lowercase letters, digits, dot, dash, underscore")
    return name


def _string_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if not isinstance(value, list):
        raise ValueError("list field must be a list of strings")
    result = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def _env_map(value: Any) -> dict[str, str]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValueError("env must be an object")
    result: dict[str, str] = {}
    for key, raw in value.items():
        name = str(key or "").strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"invalid env name: {name}")
        result[name] = str(raw)
    return result


def _agent_ids(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    raw_items = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in raw_items:
        agent_id = str(item or "").strip()
        if not agent_id:
            continue
        if not _SAFE_AGENT_ID_RE.fullmatch(agent_id):
            raise ValueError(f"invalid agent id: {agent_id}")
        if agent_id not in result:
            result.append(agent_id)
    return result


def _normalize_server(body: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    existing = dict(existing or {})
    name = _safe_name(body.get("name") or existing.get("name"))
    transport = str(body.get("transport") or existing.get("transport") or "stdio").strip().lower()
    if transport not in {"stdio", "streamable-http", "sse"}:
        raise ValueError("transport must be stdio, streamable-http, or sse")

    command = str(body.get("command") if "command" in body else existing.get("command") or "").strip()
    url = str(body.get("url") if "url" in body else existing.get("url") or "").strip()
    if transport == "stdio" and not command:
        raise ValueError("command is required for stdio MCP servers")
    if transport != "stdio" and not url:
        raise ValueError("url is required for HTTP MCP servers")

    created_at = existing.get("createdAt") or _now()
    server = {
        "name": name,
        "description": str(body.get("description") if "description" in body else existing.get("description") or "").strip(),
        "transport": transport,
        "command": command,
        "args": _string_list(body.get("args") if "args" in body else existing.get("args")),
        "cwd": str(body.get("cwd") if "cwd" in body else existing.get("cwd") or "").strip(),
        "url": url,
        "env": _env_map(body.get("env") if "env" in body else existing.get("env")),
        "include": _string_list(body.get("include") if "include" in body else existing.get("include")),
        "exclude": _string_list(body.get("exclude") if "exclude" in body else existing.get("exclude")),
        "timeout": body.get("timeout") if "timeout" in body else existing.get("timeout"),
        "connectTimeout": body.get("connectTimeout") if "connectTimeout" in body else existing.get("connectTimeout"),
        "disabled": bool(body.get("disabled") if "disabled" in body else existing.get("disabled", False)),
        "parallel": bool(body.get("parallel") if "parallel" in body else existing.get("parallel", False)),
        "assignedAgentIds": _agent_ids(body.get("assignedAgentIds") if "assignedAgentIds" in body else existing.get("assignedAgentIds")),
        "createdAt": created_at,
        "updatedAt": _now(),
        "openclaw": dict(existing.get("openclaw") or {}),
        "codex": dict(existing.get("codex") or {}),
        "claude": dict(existing.get("claude") or {}),
    }
    return {key: value for key, value in server.items() if value not in ("", None, [], {})}


def _public_server(server: dict[str, Any]) -> dict[str, Any]:
    item = dict(server)
    if isinstance(item.get("env"), dict):
        item["envKeys"] = sorted(item["env"].keys())
        item.pop("env", None)
    return item


def _openclaw_config(server: dict[str, Any]) -> dict[str, Any]:
    config: dict[str, Any] = {"disabled": bool(server.get("disabled", False))}
    if server.get("transport") == "stdio":
        config["command"] = server.get("command")
        if server.get("args"):
            config["args"] = server.get("args")
        if server.get("cwd"):
            config["cwd"] = server.get("cwd")
        if server.get("env"):
            config["env"] = server.get("env")
    else:
        config["url"] = server.get("url")
        config["transport"] = server.get("transport")
    for source, target in (("include", "include"), ("exclude", "exclude"), ("timeout", "timeout"), ("connectTimeout", "connectTimeout")):
        if source in server:
            config[target] = server[source]
    if server.get("parallel"):
        config["parallel"] = True
    return config


def _run_openclaw(args: list[str], timeout: int = 30) -> dict[str, Any]:
    binary = shutil.which("openclaw")
    if not binary:
        return {"ok": False, "error": "openclaw CLI not found", "_status": 500}
    try:
        result = subprocess.run([binary, *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "openclaw command timed out", "_status": 504}
    except OSError as exc:
        return {"ok": False, "error": str(exc), "_status": 500}
    payload: Any = None
    text = (result.stdout or "").strip()
    if text:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
    if result.returncode != 0:
        return {
            "ok": False,
            "error": (result.stderr or result.stdout or "openclaw command failed").strip()[:2000],
            "code": result.returncode,
            "_status": 500,
        }
    return {"ok": True, "stdout": result.stdout, "stderr": result.stderr, "data": payload}


def _skill_content(server: dict[str, Any]) -> str:
    config = json.dumps(_openclaw_config(server), ensure_ascii=False, indent=2)
    description = server.get("description") or f"Use the {server['name']} MCP server registered by Virtual Office."
    return f"""---
name: mcp-{server['name']}
description: "{description}"
---

# MCP Server: {server['name']}

This MCP server is managed by the Virtual Office MCP Registry.

## Usage

Use this server when the task matches its description:

{description}

## Client Registration

Virtual Office registers this MCP server in the native client that owns the assigned agent.
The normalized MCP config is:

```json
{config}
```

If tools are unavailable, ask the user or VO operator to assign this MCP server again from the Skills Library MCP Registry. Do not request or print secrets.
"""


def _get_server(name: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    safe = _safe_name(name)
    registry = _load_registry()
    server = registry.get("servers", {}).get(safe)
    return registry, server if isinstance(server, dict) else None


def _handle_mcp_registry_list() -> dict[str, Any]:
    registry = _load_registry()
    servers = [_public_server(item) for item in registry.get("servers", {}).values() if isinstance(item, dict)]
    servers.sort(key=lambda item: item.get("name", ""))
    return {"ok": True, "servers": servers}


def _handle_mcp_registry_get(name: str) -> dict[str, Any]:
    _, server = _get_server(name)
    if not server:
        return {"ok": False, "error": f"MCP server '{name}' not found", "_status": 404}
    return {"ok": True, "server": _public_server(server)}


def _handle_mcp_registry_save(body: dict[str, Any]) -> dict[str, Any]:
    try:
        name = _safe_name(body.get("name"))
        registry = _load_registry()
        existing = registry.get("servers", {}).get(name)
        server = _normalize_server(body, existing if isinstance(existing, dict) else None)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "_status": 400}
    registry.setdefault("servers", {})[server["name"]] = server
    _save_registry(registry)
    return {"ok": True, "server": _public_server(server)}


def _handle_mcp_registry_delete(name: str) -> dict[str, Any]:
    try:
        safe = _safe_name(name)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "_status": 400}
    registry = _load_registry()
    if safe not in registry.get("servers", {}):
        return {"ok": False, "error": f"MCP server '{safe}' not found", "_status": 404}
    registry["servers"].pop(safe, None)
    _save_registry(registry)
    return {"ok": True, "deleted": safe}


def _handle_mcp_registry_register_openclaw(name: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    registry, server = _get_server(name)
    if not server:
        return {"ok": False, "error": f"MCP server '{name}' not found", "_status": 404}
    config = _openclaw_config(server)
    result = _run_openclaw(["mcp", "set", server["name"], json.dumps(config, ensure_ascii=False)])
    if not result.get("ok"):
        return result
    reload_result = _run_openclaw(["mcp", "reload"], timeout=15)
    server["openclaw"] = {
        "registered": True,
        "registeredAt": _now(),
        "reloaded": bool(reload_result.get("ok")),
        "reloadError": reload_result.get("error", ""),
    }
    registry.setdefault("servers", {})[server["name"]] = server
    _save_registry(registry)
    return {"ok": True, "server": _public_server(server), "openclaw": server["openclaw"]}


def _handle_mcp_registry_register_native(name: str, client: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    registry, server = _get_server(name)
    if not server:
        return {"ok": False, "error": f"MCP server '{name}' not found", "_status": 404}
    from server_services import mcp_native_clients

    options = body or {}
    result = mcp_native_clients.register_native_client(
        client,
        server,
        claude_scope=str(options.get("scope") or "user"),
    )
    if not result.get("ok"):
        return result
    status = {
        "registered": True,
        "registeredAt": _now(),
    }
    if result.get("warnings"):
        status["warnings"] = result["warnings"]
    server[client] = status
    registry.setdefault("servers", {})[server["name"]] = server
    _save_registry(registry)
    return {"ok": True, "server": _public_server(server), client: status}


def _handle_mcp_registry_register_codex(name: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    return _handle_mcp_registry_register_native(name, "codex", body)


def _handle_mcp_registry_register_claude(name: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    return _handle_mcp_registry_register_native(name, "claude", body)


def _handle_mcp_registry_assign(name: str, body: dict[str, Any]) -> dict[str, Any]:
    registry, server = _get_server(name)
    if not server:
        return {"ok": False, "error": f"MCP server '{name}' not found", "_status": 404}
    try:
        requested = _agent_ids(body.get("agentIds") if "agentIds" in body else body.get("agentId"))
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "_status": 400}
    mode = str(body.get("mode") or "add").strip().lower()
    current = _agent_ids(server.get("assignedAgentIds"))
    if mode == "replace":
        assigned = requested
    elif mode == "remove":
        assigned = [agent_id for agent_id in current if agent_id not in requested]
    elif mode == "add":
        assigned = current[:]
        for agent_id in requested:
            if agent_id not in assigned:
                assigned.append(agent_id)
    else:
        return {"ok": False, "error": "mode must be add, remove, or replace", "_status": 400}
    server["assignedAgentIds"] = assigned
    server["updatedAt"] = _now()
    registry.setdefault("servers", {})[server["name"]] = server
    _save_registry(registry)
    return {"ok": True, "server": _public_server(server), "assignedAgentIds": assigned}


def _install_mcp_skill_only(name: str, body: dict[str, Any]) -> dict[str, Any]:
    _, server = _get_server(name)
    if not server:
        return {"ok": False, "error": f"MCP server '{name}' not found", "_status": 404}
    agent_id = str(body.get("agentId") or "").strip()
    if not agent_id:
        return {"ok": False, "error": "agentId is required", "_status": 400}
    skill_name = f"mcp-{server['name']}"
    content = _skill_content(server)
    from server_services import skills

    skills._hydrate()
    create = skills._handle_skills_library_create({"name": skill_name, "content": content})
    if not create.get("ok"):
        return create
    apply = skills._handle_skills_library_apply({"skill": create["skill"], "agentId": agent_id, "overwrite": bool(body.get("overwrite", True))})
    if not apply.get("ok"):
        return apply
    assignment = _handle_mcp_registry_assign(name, {"agentId": agent_id, "mode": "add"})
    if not assignment.get("ok"):
        return assignment
    return {
        "ok": True,
        "skill": create["skill"],
        "agentId": agent_id,
        "assignedAgentIds": assignment.get("assignedAgentIds", []),
        "library": create,
        "install": apply,
    }


def _register_mcp_for_client(name: str, client: str, body: dict[str, Any]) -> dict[str, Any]:
    if client == "openclaw":
        return _handle_mcp_registry_register_openclaw(name, body)
    return _handle_mcp_registry_register_native(name, client, body)


def _handle_mcp_registry_install_skill(name: str, body: dict[str, Any]) -> dict[str, Any]:
    from server_services import agents, mcp_assignment

    result = mcp_assignment.assign_to_agent(
        name,
        body,
        list_agents=agents._handle_agents_list,
        register_client=_register_mcp_for_client,
        install_skill=_install_mcp_skill_only,
    )
    install_result = result.get("install") if isinstance(result, dict) else None
    if result.get("ok") and isinstance(install_result, dict) and "assignedAgentIds" in install_result:
        result["assignedAgentIds"] = install_result["assignedAgentIds"]
    return result


def _handle_mcp_registry_vibe_template() -> dict[str, Any]:
    body = {
        "name": "vibe-trading",
        "description": "Finance research, market data, alpha exploration, and backtesting through Vibe-Trading. Research-only by default; do not enable live broker actions unless explicitly authorized.",
        "transport": "stdio",
        "command": "vibe-trading-mcp",
        "args": [],
        "include": ["*"],
        "disabled": False,
        "parallel": False,
    }
    return _handle_mcp_registry_save(body)
