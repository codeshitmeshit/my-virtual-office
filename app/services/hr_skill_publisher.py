"""Canonical HR Agent-directory skill publication and readiness projection."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from services.managed_skills import ManagedSkillDefinition, sync_managed_skill_to_workspace


DIRECTORY_SKILL_NAME = "vo-agent-directory"


class HRSkillPublisherValidationError(ValueError):
    code = "hr_skill_publisher_validation_failed"


@dataclass(frozen=True, slots=True)
class HRSkillReadiness:
    ai_id: str
    ready: bool
    state: str
    updated: bool
    sha256: str
    error_code: str


class HRSkillPublisher:
    """Publishes the repository-owned directory skill to supported Agent workspaces."""

    def __init__(
        self,
        *,
        workspace_base: str | os.PathLike[str],
        canonical_skill_path: str | os.PathLike[str],
        supported_provider_kinds: frozenset[str] = frozenset({"openclaw"}),
    ):
        supported_provider_kinds = frozenset(
            str(value).strip() for value in supported_provider_kinds if str(value).strip()
        )
        if not supported_provider_kinds:
            raise HRSkillPublisherValidationError("supported_provider_kinds must not be empty")
        self._workspace_base = Path(workspace_base)
        self._canonical_skill_path = Path(canonical_skill_path)
        self._definition = ManagedSkillDefinition(
            name=DIRECTORY_SKILL_NAME,
            content_loader=self._load_canonical,
            provider_kinds=supported_provider_kinds,
        )

    def _load_canonical(self) -> str:
        if self._canonical_skill_path.is_symlink() or not self._canonical_skill_path.is_file():
            raise HRSkillPublisherValidationError("canonical directory skill is missing or unsafe")
        content = self._canonical_skill_path.read_text(encoding="utf-8")
        if re.search(r"Bearer\s+[A-Za-z0-9_-]{24,}", content):
            raise HRSkillPublisherValidationError("canonical directory skill embeds a bearer grant")
        return content

    def publish(self, agent: Mapping[str, object]) -> HRSkillReadiness:
        if not isinstance(agent, Mapping):
            return HRSkillReadiness(
                ai_id="",
                ready=False,
                state="invalid_agent",
                updated=False,
                sha256="",
                error_code="hr_skill_agent_invalid",
            )
        ai_id = str(agent.get("id") or agent.get("statusKey") or "").strip()
        if not ai_id:
            return HRSkillReadiness(
                ai_id="",
                ready=False,
                state="invalid_agent",
                updated=False,
                sha256="",
                error_code="hr_skill_agent_invalid",
            )
        try:
            result = sync_managed_skill_to_workspace(
                self._definition,
                agent,
                workspace_base=self._workspace_base,
            )
        except (OSError, ValueError) as exc:
            return HRSkillReadiness(
                ai_id=ai_id,
                ready=False,
                state="canonical_invalid",
                updated=False,
                sha256="",
                error_code=getattr(exc, "code", "hr_skill_canonical_invalid"),
            )
        state = str(result.get("status") or "failed")
        if state == "not_applicable":
            state = "unsupported_provider"
        return HRSkillReadiness(
            ai_id=ai_id,
            ready=bool(result.get("ready")),
            state=state,
            updated=bool(result.get("updated")),
            sha256=str(result.get("sha256") or ""),
            error_code="" if result.get("ready") else f"hr_skill_{state}",
        )


def repository_directory_skill_path(repository_root: str | os.PathLike[str]) -> Path:
    root = Path(repository_root).resolve(strict=False)
    path = root / "skills" / DIRECTORY_SKILL_NAME / "SKILL.md"
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise HRSkillPublisherValidationError("canonical directory skill escapes repository") from exc
    return path
