"""Resolve which Virtual Office agents currently have a library skill installed."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from services import provider_skill_sync


def _agent_id(agent: Mapping[str, Any]) -> str:
    return str(agent.get("id") or agent.get("statusKey") or "").strip()


def _installed_for_agent(
    skill_name: str,
    agent: Mapping[str, Any],
    resolve_context: Callable[[str], Mapping[str, Any] | None],
) -> bool:
    agent_id = _agent_id(agent)
    if not agent_id:
        return False
    context = resolve_context(agent_id) or agent
    try:
        root = provider_skill_sync.skill_root_for_agent(context)
        normalized = provider_skill_sync.normalize_skill_name(skill_name)
    except provider_skill_sync.SkillSyncError:
        return False
    skill_file = Path(root) / normalized / "SKILL.md"
    return skill_file.is_file() and not skill_file.is_symlink()


def loaded_agents_for_skill(
    skill_name: str,
    agents: Iterable[Mapping[str, Any]],
    resolve_context: Callable[[str], Mapping[str, Any] | None],
) -> list[dict[str, str]]:
    """Return display-safe agent summaries for agents with the skill installed."""
    loaded = []
    for agent in agents:
        if not _installed_for_agent(skill_name, agent, resolve_context):
            continue
        agent_id = _agent_id(agent)
        loaded.append(
            {
                "id": agent_id,
                "statusKey": str(agent.get("statusKey") or agent_id),
                "name": str(agent.get("name") or agent_id),
                "emoji": str(agent.get("emoji") or "🤖"),
                "branch": str(agent.get("branch") or ""),
                "providerKind": str(agent.get("providerKind") or "openclaw"),
            }
        )
    return loaded


def enrich_library_response(
    response: Mapping[str, Any],
    agents: Iterable[Mapping[str, Any]],
    resolve_context: Callable[[str], Mapping[str, Any] | None],
) -> dict[str, Any]:
    """Add installed-agent summaries to every skill without adding lifecycle state."""
    enriched = dict(response)
    enriched_skills = []
    agent_list = list(agents)
    context_cache: dict[str, Mapping[str, Any] | None] = {}

    def cached_context(agent_id: str) -> Mapping[str, Any] | None:
        if agent_id not in context_cache:
            context_cache[agent_id] = resolve_context(agent_id)
        return context_cache[agent_id]

    for skill in response.get("skills", []):
        item = dict(skill)
        loaded = loaded_agents_for_skill(
            str(item.get("name") or ""),
            agent_list,
            cached_context,
        )
        item["loadedAgents"] = loaded
        item["loadedAgentIds"] = [agent["id"] for agent in loaded]
        enriched_skills.append(item)
    enriched["skills"] = enriched_skills
    return enriched
