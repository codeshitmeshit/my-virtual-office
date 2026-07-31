"""Render default Agent workspace documents through the common business bridge."""

from __future__ import annotations

from typing import Any, Literal

from services import business_prompt_bridge


CommunicationProfile = Literal["service", "legacy"]


def agent_template_files(
    name: str,
    role: str,
    emoji: str,
    agent_kind: str = "OpenClaw",
    *,
    communication_profile: CommunicationProfile = "service",
) -> dict[str, str]:
    """Return non-secret bootstrap files for a newly-created Agent workspace."""

    return {
        "IDENTITY.md": _identity_document(name, role, emoji, agent_kind),
        "SOUL.md": _soul_document(name, role, emoji),
        "USER.md": _user_profile_document(),
        "AGENTS.md": _agents_instructions_document(
            name,
            role,
            emoji,
            communication_profile=communication_profile,
        ),
        "HEARTBEAT.md": _heartbeat_document(),
        "MEMORY.md": _single_note_document("agent_memory", name, "No memories yet."),
        "TOOLS.md": _single_note_document("agent_tools", name, "Add tool-specific notes here."),
    }


def _identity_document(name: str, role: str, emoji: str, agent_kind: str) -> str:
    return _render_workspace_document(
        "agent_identity",
        "identity",
        [
            {"name": "name", "value": name},
            {"name": "kind", "value": agent_kind},
            {"name": "role", "value": role},
            {"name": "vibe", "value": "Helpful, efficient, ready to work", "trusted": True},
            {"name": "emoji", "value": emoji},
        ],
    )


def _soul_document(name: str, role: str, emoji: str) -> str:
    return _render_workspace_document(
        "agent_soul",
        "soul",
        [
            {"name": "name", "value": name},
            {"name": "emoji", "value": emoji},
            {"name": "role", "value": role},
            {
                "name": "style",
                "children": [
                    {"name": "rule", "value": "Be helpful and direct.", "trusted": True},
                    {"name": "rule", "value": "Follow your AGENTS.md workflow strictly.", "trusted": True},
                    {"name": "rule", "value": "Keep work visible through Virtual Office when possible.", "trusted": True},
                ],
            },
        ],
    )


def _user_profile_document() -> str:
    return _render_workspace_document(
        "agent_user_profile",
        "user_profile",
        [
            {"name": "name", "value": "(set by your owner)", "trusted": True},
            {"name": "timezone", "value": "(set by your owner)", "trusted": True},
            {"name": "notes", "value": "Prefers direct, clear communication.", "trusted": True},
        ],
    )


def _agents_instructions_document(
    name: str,
    role: str,
    emoji: str,
    *,
    communication_profile: CommunicationProfile,
) -> str:
    communication_rules = [
        "Use Virtual Office communication tools when talking to other office agents.",
        "Your text reply IS your response - write it directly.",
    ]
    if communication_profile == "legacy":
        communication_rules = [
            "Use the installed `vo-agent-communication` skill whenever you ask, delegate to, notify, or hand off to another office agent.",
            "Resolve current agent identities through Virtual Office and send through `/api/agent-platform-communications/send`.",
            "Never fall back to `sessions_list`, `sessions_send`, `openclaw agents`, a provider-private CLI, or a local subagent for office-agent communication.",
            "If Virtual Office routing is unavailable, report the real failure and stop.",
            "Your text reply IS your response - write it directly.",
        ]
    return _render_workspace_document(
        "agent_instructions",
        "instructions",
        [
            {"name": "identity", "value": "", "attrs": {"name": name, "emoji": emoji, "role": role}},
            {"name": "role", "value": role},
            {
                "name": "core_rules",
                "children": [
                    {"name": "rule", "value": "Follow instructions carefully.", "trusted": True},
                    {"name": "rule", "value": "Log your work in memory/YYYY-MM-DD.md when useful.", "trusted": True},
                    {"name": "rule", "value": "Complete the full loop: working -> work -> report -> idle.", "trusted": True},
                ],
            },
            {
                "name": "communication",
                "children": [
                    {"name": "rule", "value": rule, "trusted": True}
                    for rule in communication_rules
                ],
            },
            {
                "name": "memory",
                "value": {
                    "daily": "memory/YYYY-MM-DD.md",
                    "long_term": "MEMORY.md",
                },
                "trusted": True,
            },
        ],
    )


def _heartbeat_document() -> str:
    return _render_workspace_document(
        "agent_heartbeat",
        "heartbeat",
        [
            {
                "name": "instruction",
                "value": "Add periodic tasks below. If nothing needs attention, reply HEARTBEAT_OK.",
                "trusted": True,
            },
        ],
    )


def _single_note_document(root: str, name: str, note: str) -> str:
    return _render_workspace_document(
        root,
        "note",
        [{"name": "note", "value": note, "trusted": True}],
        attrs={"name": name},
    )


def _render_workspace_document(
    root: str,
    operation: str,
    sections: list[dict[str, Any]],
    *,
    attrs: dict[str, Any] | None = None,
) -> str:
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "agent.workspace_document",
            "operation": operation,
            "locale": "en-US",
            "root": root,
            "attrs": attrs or {},
            "sections": sections,
        }
    ) + "\n"


__all__ = ["agent_template_files"]
