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


def human_decision_section(source_type: str) -> dict[str, Any]:
    return {
        "name": "human_decision_escalation",
        "value": human_decision_guidance(source_type),
        "trusted": True,
    }


__all__ = ["human_decision_guidance", "human_decision_section"]
