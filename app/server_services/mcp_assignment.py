"""Assign a VO MCP server to an agent and register its native client."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_PROVIDER_CLIENTS = {
    "openclaw": "openclaw",
    "codex": "codex",
    "claude": "claude",
    "claude-code": "claude",
}


def client_for_provider(provider_kind: Any) -> str | None:
    return _PROVIDER_CLIENTS.get(str(provider_kind or "").strip().lower())


def find_agent(agents: list[dict[str, Any]], agent_id: str) -> dict[str, Any] | None:
    needle = str(agent_id or "").strip()
    for agent in agents:
        if needle in {
            str(agent.get("id") or ""),
            str(agent.get("statusKey") or ""),
            str(agent.get("providerAgentId") or ""),
        }:
            return agent
    return None


def assign_to_agent(
    server_name: str,
    body: dict[str, Any],
    *,
    list_agents: Callable[[], dict[str, Any]],
    register_client: Callable[[str, str, dict[str, Any]], dict[str, Any]],
    install_skill: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    agent_id = str(body.get("agentId") or "").strip()
    if not agent_id:
        return {"ok": False, "error": "agentId is required", "_status": 400, "stage": "resolve-agent"}

    agent_payload = list_agents()
    agents = agent_payload.get("agents") if isinstance(agent_payload, dict) else None
    agent = find_agent(agents if isinstance(agents, list) else [], agent_id)
    if not agent:
        return {
            "ok": False,
            "error": f"Agent '{agent_id}' not found",
            "_status": 404,
            "stage": "resolve-agent",
        }

    provider_kind = str(agent.get("providerKind") or "openclaw").strip().lower()
    client = client_for_provider(provider_kind)
    if not client:
        return {
            "ok": False,
            "error": f"Agent provider '{provider_kind}' does not support MCP auto-registration",
            "_status": 400,
            "stage": "resolve-client",
            "agentId": agent_id,
            "providerKind": provider_kind,
        }

    registration = register_client(server_name, client, body)
    if not registration.get("ok"):
        return {
            **registration,
            "ok": False,
            "stage": "register-client",
            "agentId": agent_id,
            "providerKind": provider_kind,
            "client": client,
        }

    installation = install_skill(server_name, body)
    if not installation.get("ok"):
        return {
            **installation,
            "ok": False,
            "stage": "install-skill",
            "agentId": agent_id,
            "providerKind": provider_kind,
            "client": client,
            "registration": registration,
        }

    return {
        "ok": True,
        "agentId": agent_id,
        "providerKind": provider_kind,
        "client": client,
        "registrationScope": "user" if client == "claude" else "client",
        "registration": registration,
        "skill": installation.get("skill"),
        "install": installation,
    }
