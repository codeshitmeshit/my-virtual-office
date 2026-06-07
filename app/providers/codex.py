"""Codex provider adapter for My Virtual Office.

This adapter exposes the current/local Codex collaborator as an office agent.
It intentionally starts as an opt-in harness: discovery, status, routing, and
office event visibility work without requiring OpenClaw or Hermes to be
installed. A real live Codex bridge can be added behind this adapter later.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any


def _env_bool(key: str, fallback: bool = False) -> bool:
    value = os.environ.get(key)
    if value is None or str(value).strip() == "":
        return fallback
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _safe_suffix(value: str) -> str:
    suffix = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value or "local").strip("-")
    return suffix[:80] or "local"


@dataclass
class CodexProvider:
    """Provider adapter for a local Codex collaborator harness."""

    enabled: bool = False
    workspace: str | None = None
    name: str | None = None
    agent_id: str | None = None
    model: str | None = None
    reply_text: str | None = None
    bridge_url: str | None = None

    provider_kind: str = "codex"
    provider_type: str = "harness"

    def __post_init__(self) -> None:
        self.enabled = bool(self.enabled)
        self.workspace = os.path.abspath(os.path.expanduser(
            self.workspace
            or os.environ.get("VO_CODEX_WORKSPACE")
            or os.getcwd()
        ))
        self.name = self.name or os.environ.get("VO_CODEX_AGENT_NAME") or "Codex"
        self.agent_id = _safe_suffix(self.agent_id or os.environ.get("VO_CODEX_AGENT_ID") or "local")
        self.model = self.model or os.environ.get("VO_CODEX_MODEL") or os.environ.get("OPENAI_MODEL") or ""
        self.reply_text = self.reply_text if self.reply_text is not None else os.environ.get("VO_CODEX_REPLY_TEXT")
        self.bridge_url = self.bridge_url or os.environ.get("VO_CODEX_BRIDGE_URL") or ""

    @classmethod
    def from_env(cls) -> "CodexProvider":
        return cls(
            enabled=_env_bool("VO_CODEX_ENABLED", False),
            workspace=os.environ.get("VO_CODEX_WORKSPACE"),
            name=os.environ.get("VO_CODEX_AGENT_NAME"),
            agent_id=os.environ.get("VO_CODEX_AGENT_ID"),
            model=os.environ.get("VO_CODEX_MODEL") or os.environ.get("OPENAI_MODEL"),
            reply_text=os.environ.get("VO_CODEX_REPLY_TEXT"),
            bridge_url=os.environ.get("VO_CODEX_BRIDGE_URL"),
        )

    def is_available(self) -> bool:
        return bool(self.enabled)

    def discover_agents(self) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        status_key = f"codex-{self.agent_id}"
        return [{
            "id": status_key,
            "statusKey": status_key,
            "providerKind": self.provider_kind,
            "providerType": self.provider_type,
            "providerAgentId": self.agent_id,
            "profile": self.agent_id,
            "name": self.name or "Codex",
            "emoji": os.environ.get("VO_CODEX_AGENT_EMOJI", "⚡"),
            "role": "Codex Collaborator",
            "model": self.model or "",
            "provider": "OpenAI Codex",
            "workspace": self.workspace,
            "home": self.workspace,
            "lastActiveAt": self._last_active(self.workspace),
            "capabilities": ["chat", "status", "collaboration", "event-stream"],
            "bridgeConfigured": bool(self.bridge_url or self.reply_text),
        }]

    def test(self) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "Codex harness is disabled. Set VO_CODEX_ENABLED=1 to expose it.", "agents": []}
        return {
            "ok": True,
            "workspace": self.workspace,
            "bridgeConfigured": bool(self.bridge_url or self.reply_text),
            "agents": self.discover_agents(),
        }

    def send_message(self, message: str, conversation_id: str = "", timeout_sec: int | None = None) -> dict[str, Any]:
        text = str(message or "").strip()
        if not self.enabled:
            return {"ok": False, "error": "Codex harness is disabled", "reply": ""}
        if not text:
            return {"ok": False, "error": "message is required", "reply": ""}
        if self.reply_text:
            return {
                "ok": True,
                "reply": self.reply_text,
                "conversationId": conversation_id,
                "mode": "replyText",
            }
        return {
            "ok": False,
            "error": "Codex harness is enabled but no live Codex bridge is configured",
            "reply": "Codex request recorded in Virtual Office. Configure VO_CODEX_REPLY_TEXT for demo replies or VO_CODEX_BRIDGE_URL when a live bridge is available.",
            "conversationId": conversation_id,
            "mode": "manual",
        }

    def _last_active(self, path: str | None) -> int:
        if not path or not os.path.isdir(path):
            return int(time.time())
        latest = 0.0
        try:
            for name in (".git", ".codex", ".agents"):
                candidate = os.path.join(path, name)
                if os.path.exists(candidate):
                    latest = max(latest, os.path.getmtime(candidate))
            latest = max(latest, os.path.getmtime(path))
        except OSError:
            pass
        return int(latest or time.time())
