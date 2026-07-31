"""Render Hermes profile bootstrap documents through the common business bridge."""

from __future__ import annotations

from typing import Any

from services import business_prompt_bridge


def hermes_profile_template_files(
    *,
    name: str,
    role: str,
    emoji: str,
    profile: str,
) -> dict[str, str]:
    return {
        "IDENTITY.md": _identity_document(name=name, role=role, emoji=emoji, profile=profile),
        "SOUL.md": _soul_document(name=name, role=role, emoji=emoji, profile=profile),
        "AGENTS.md": _instructions_document(name=name, role=role, emoji=emoji, profile=profile),
        "MEMORY.md": _single_note_document("hermes_profile_memory", name, "No memories yet."),
        "TOOLS.md": _single_note_document("hermes_profile_tools", name, "Add tool-specific notes here."),
    }


def _identity_document(*, name: str, role: str, emoji: str, profile: str) -> str:
    return _render_profile_document(
        "hermes_profile_identity",
        "identity",
        [
            {"name": "name", "value": name},
            {"name": "profile", "value": profile},
            {"name": "role", "value": role},
            {"name": "vibe", "value": "Helpful, direct, ready to work", "trusted": True},
            {"name": "emoji", "value": emoji},
        ],
    )


def _soul_document(*, name: str, role: str, emoji: str, profile: str) -> str:
    return _render_profile_document(
        "hermes_profile_soul",
        "soul",
        [
            {"name": "name", "value": name},
            {"name": "emoji", "value": emoji},
            {"name": "role", "value": role},
            {
                "name": "style",
                "children": [
                    {"name": "rule", "value": "Be helpful and direct.", "trusted": True},
                    {"name": "rule", "value": "Keep work visible through Virtual Office when possible.", "trusted": True},
                    {"name": "rule", "value": f"Use your Hermes profile `{profile}` for isolated context."},
                ],
            },
        ],
    )


def _instructions_document(*, name: str, role: str, emoji: str, profile: str) -> str:
    return _render_profile_document(
        "hermes_profile_instructions",
        "instructions",
        [
            {"name": "identity", "value": "", "attrs": {"name": name, "emoji": emoji, "role": role, "profile": profile}},
            {"name": "role", "value": role},
            {
                "name": "core_rules",
                "children": [
                    {"name": "rule", "value": "Follow instructions carefully.", "trusted": True},
                    {"name": "rule", "value": "Keep replies concise and useful.", "trusted": True},
                    {"name": "rule", "value": "Do not expose secrets from your Hermes profile.", "trusted": True},
                ],
            },
            {"name": "memory", "value": "Use Hermes profile memory and sessions normally.", "trusted": True},
        ],
    )


def _single_note_document(root: str, name: str, note: str) -> str:
    return _render_profile_document(
        root,
        "note",
        [{"name": "note", "value": note, "trusted": True}],
        attrs={"name": name},
    )


def _render_profile_document(
    root: str,
    operation: str,
    sections: list[dict[str, Any]],
    *,
    attrs: dict[str, Any] | None = None,
) -> str:
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "hermes.profile_document",
            "operation": operation,
            "locale": "en-US",
            "root": root,
            "attrs": attrs or {},
            "sections": sections,
        }
    ) + "\n"


__all__ = ["hermes_profile_template_files"]
