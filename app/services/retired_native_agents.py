"""Shared rules for native provider agents retired from VO management."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


RETIRED_NATIVE_MAIN_AGENT_IDS = frozenset({"codex-main", "claude-code-main"})


def is_retired_native_main_agent(agent: Mapping[str, Any]) -> bool:
    """Return whether an agent record is a retired built-in provider main entry."""
    agent_id = str(
        agent.get("ai_id")
        or agent.get("aiId")
        or agent.get("id")
        or agent.get("statusKey")
        or ""
    )
    source = str(agent.get("source") or "")
    return agent_id in RETIRED_NATIVE_MAIN_AGENT_IDS or source == "native-main"
