"""Provider-neutral skill installation for VO agents."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Mapping

SYNC_MARKER = ".vo-synced-skill"
_SAFE_SKILL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


class SkillSyncError(ValueError):
    """Raised when a provider skill sync target is invalid or unsafe."""


def normalize_skill_name(name: object) -> str:
    value = str(name or "").strip()
    if not _SAFE_SKILL_NAME.fullmatch(value):
        raise SkillSyncError("Invalid skill name")
    return value


def _safe_root(path: object) -> Path:
    value = os.path.abspath(os.path.expanduser(str(path or "").strip()))
    if not value:
        raise SkillSyncError("Skill sync root is not configured")
    return Path(value)


def skill_root_for_agent(agent: Mapping[str, Any]) -> Path:
    explicit = str(agent.get("skillSyncRoot") or "").strip()
    if explicit:
        return _safe_root(explicit)

    provider = str(agent.get("providerKind") or "openclaw").lower()
    workspace = str(agent.get("workspace") or agent.get("home") or "").strip()
    if not workspace:
        raise SkillSyncError(f"Workspace is not configured for provider '{provider}'")
    base = _safe_root(workspace)

    if provider in {"openclaw", "hermes"}:
        return base / "skills"
    if provider == "codex":
        return base / ".codex" / "skills"
    if provider == "claude-code":
        return base / ".claude" / "skills"
    raise SkillSyncError(f"Unsupported provider for skill sync: {provider}")


def _skill_file(root: Path, skill_name: str) -> Path:
    name = normalize_skill_name(skill_name)
    target = root / name / "SKILL.md"
    resolved_root = root.resolve(strict=False)
    resolved_target = target.resolve(strict=False)
    if resolved_target != resolved_root and resolved_root not in resolved_target.parents:
        raise SkillSyncError("Skill target escapes provider skill root")
    return target


def install_skill_file(
    source_file: str | os.PathLike[str],
    skill_name: str,
    agent: Mapping[str, Any],
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    source = Path(source_file)
    if not source.is_file():
        raise SkillSyncError("Source skill file does not exist")
    root = skill_root_for_agent(agent)
    target = _skill_file(root, skill_name)
    existed = target.is_file()
    if existed and not overwrite:
        return {
            "ok": False,
            "exists": True,
            "warning": f"Agent already has skill '{skill_name}'. Set overwrite=true to replace.",
            "path": str(target),
            "providerKind": agent.get("providerKind") or "",
        }
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    (target.parent / SYNC_MARKER).write_text("1\n", encoding="utf-8")
    return {
        "ok": True,
        "skill": normalize_skill_name(skill_name),
        "agentId": agent.get("id") or agent.get("statusKey") or "",
        "providerKind": agent.get("providerKind") or "",
        "path": str(target),
        "overwritten": bool(existed and overwrite),
    }


def delete_skill(skill_name: str, agent: Mapping[str, Any]) -> dict[str, Any]:
    root = skill_root_for_agent(agent)
    target = _skill_file(root, skill_name)
    deleted = False
    if target.parent.is_dir():
        shutil.rmtree(target.parent)
        deleted = True
    return {
        "ok": True,
        "deleted": deleted,
        "skill": normalize_skill_name(skill_name),
        "agentId": agent.get("id") or agent.get("statusKey") or "",
        "providerKind": agent.get("providerKind") or "",
        "path": str(target),
    }
