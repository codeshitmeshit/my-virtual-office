"""Shared provider-prompt guidance for escalating material VO decisions."""

from __future__ import annotations

from typing import Any


def human_decision_guidance(source_type: str) -> str:
    source = str(source_type or "task").strip().lower()
    if source not in {"chat", "meeting", "task"}:
        source = "task"
    return (
        "First investigate with available tools, evidence, existing rules, and prior user choices. "
        "Continue reversible, low-risk work that is already within the user's authorization. "
        "If two or more materially different reasonable choices remain and the choice affects outcome, risk, scope, cost, "
        "or an irreversible action, and you lack authority or sufficient confidence to choose for the user, do not silently pick one. "
        "Use the vo-human-decision skill and create a Human Decision Center request with "
        f"source.type={source}; pause only the affected branch while independent safe work continues. "
        "This is the sole exception to general instructions not to ask for user input. "
        "Do not escalate ordinary implementation uncertainty that further inspection, testing, or a single safe answer can resolve."
    )


def human_decision_section(
    source_type: str,
    *,
    agent_id: str = "",
    source_id: str = "",
    project_id: str = "",
) -> dict[str, Any]:
    source = str(source_type or "task").strip().lower()
    if source not in {"chat", "meeting", "task"}:
        source = "task"
    source_contract: dict[str, str] = {
        "type": source,
        "id": str(source_id or "").strip(),
    }
    if source == "task":
        source_contract["projectId"] = str(project_id or "").strip()
    return {
        "name": "human_decision_escalation",
        "children": [
            {
                "name": "threshold",
                "value": human_decision_guidance(source),
                "trusted": True,
            },
            {
                "name": "skill",
                "attrs": {"path": "/skills/vo-human-decision/SKILL.md"},
                "value": (
                    "Read this skill from the local VO service and follow its complete request contract. "
                    "Do not substitute a normal chat question."
                ),
                "trusted": True,
            },
            {
                "name": "create_request",
                "trusted": True,
                "children": [
                    {"name": "method", "value": "POST", "trusted": True},
                    {"name": "path", "value": "/api/agent/human-decisions", "trusted": True},
                    {
                        "name": "required_headers",
                        "format": "json",
                        "value": {
                            "Content-Type": "application/json",
                            "X-VO-Agent-Action": "human-decision",
                            "X-VO-Agent-Id": str(agent_id or "").strip(),
                        },
                    },
                    {"name": "required_source", "format": "json", "value": source_contract},
                ],
            },
            {
                "name": "after_create",
                "value": (
                    "End the affected turn after the request is created; do not return a normal completion result "
                    "and do not continue the blocked branch. The VO backend will resume this exact execution after resolution."
                ),
                "trusted": True,
            },
        ],
    }


__all__ = ["human_decision_guidance", "human_decision_section"]
