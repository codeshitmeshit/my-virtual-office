"""Register a VO MCP server in a provider client and record agent assignment."""

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
    assign_registry: Callable[[str, dict[str, Any]], dict[str, Any]],
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

    assignment = assign_registry(server_name, {"agentId": agent_id, "mode": "add"})
    if not assignment.get("ok"):
        return {
            **assignment,
            "ok": False,
            "stage": "assign-agent",
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
        "assignment": assignment,
        "assignedAgentIds": assignment.get("assignedAgentIds", []),
    }


def assign_to_agents(
    server_name: str,
    body: dict[str, Any],
    *,
    list_agents: Callable[[], dict[str, Any]],
    register_client: Callable[[str, str, dict[str, Any]], dict[str, Any]],
    assign_registry: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    requested_ids = body.get("agentIds")
    agent_ids = [str(item or "").strip() for item in requested_ids] if isinstance(requested_ids, list) else []
    agent_ids = list(dict.fromkeys(item for item in agent_ids if item))
    if not agent_ids:
        return {"ok": False, "error": "agentIds is required", "_status": 400, "stage": "resolve-agent"}

    agent_payload = list_agents()
    agents = agent_payload.get("agents") if isinstance(agent_payload, dict) else None
    available = agents if isinstance(agents, list) else []
    resolved: list[tuple[str, dict[str, Any], str]] = []
    for agent_id in agent_ids:
        agent = find_agent(available, agent_id)
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
        resolved.append((agent_id, agent, client))

    registrations: dict[str, dict[str, Any]] = {}
    for client in dict.fromkeys(item[2] for item in resolved):
        representative_id = next(item[0] for item in resolved if item[2] == client)
        registration = register_client(server_name, client, {**body, "agentId": representative_id})
        if not registration.get("ok"):
            return {
                **registration,
                "ok": False,
                "stage": "register-client",
                "agentId": representative_id,
                "client": client,
                "registrations": registrations,
            }
        registrations[client] = registration

    assignment = assign_registry(server_name, {"agentIds": agent_ids, "mode": "add"})
    if not assignment.get("ok"):
        return {
            **assignment,
            "ok": False,
            "stage": "assign-agent",
            "registrations": registrations,
        }
    return {
        "ok": True,
        "agentIds": agent_ids,
        "clients": list(registrations),
        "registrations": registrations,
        "assignment": assignment,
        "assignedAgentIds": assignment.get("assignedAgentIds", []),
    }
