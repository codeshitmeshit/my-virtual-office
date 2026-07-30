"""Shared guard for slash-like chat messages before provider dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

try:
    from services.chat_commands import ChatCommand
except ModuleNotFoundError:  # pragma: no cover - package import fallback
    from .chat_commands import ChatCommand


SUPPORTED_COMMANDS = frozenset(command.value for command in ChatCommand)


@dataclass(frozen=True)
class SlashGuardResult:
    kind: str
    text: str = ""
    command: str = ""

    @property
    def is_ordinary(self) -> bool:
        return self.kind == "ordinary"

    @property
    def is_command(self) -> bool:
        return self.kind == "command"

    @property
    def is_blocked(self) -> bool:
        return self.kind == "blocked"


def classify_slash_message(
    text: Any,
    attachments: Sequence[Mapping[str, Any]] | None = None,
) -> SlashGuardResult:
    """Classify attachment-free slash-prefixed text before normal dispatch."""

    value = str(text or "").strip()
    if not value or attachments or not value.startswith("/"):
        return SlashGuardResult("ordinary", text=value)
    if value in SUPPORTED_COMMANDS:
        return SlashGuardResult("command", text=value, command=value)
    return SlashGuardResult("blocked", text=value)


def blocked_command_name(text: Any) -> str:
    value = str(text or "").strip()
    return (value.split(maxsplit=1)[0] if value else "/")[:80]


def provider_block_response(text: Any) -> dict[str, Any]:
    command = blocked_command_name(text)
    return {
        "ok": False,
        "status": "slash_command_blocked",
        "error": f"Slash-like message '{command}' was not sent to the Agent.",
        "reply": f"Slash-like message '{command}' was not sent to the Agent.",
        "_status": 400,
    }


def feishu_block_reply(text: Any, *, disabled: bool = False) -> str:
    command = blocked_command_name(text)
    if disabled:
        return f"slash 命令 {command} 当前未启用，未发送给 Agent。"
    return f"未知 slash 命令 {command}，未发送给 Agent。"
