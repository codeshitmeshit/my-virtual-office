"""Canonical HR Agent-directory skill publication and readiness projection."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from services.hr_repository import HRRepository, HRRepositoryError
from services.managed_skills import (
    MANAGED_SKILL_MARKER,
    ManagedSkillDefinition,
    atomic_write_managed_text,
    managed_skill_path_is_safe,
    sync_managed_skill_to_workspace,
)


DIRECTORY_SKILL_NAME = "vo-agent-directory"
_GRANT_LOCK = threading.RLock()


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


@dataclass(frozen=True, slots=True)
class HRGrantReadiness:
    ai_id: str
    ready: bool
    state: str
    key_id: str
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


class HRGrantManager:
    """Issues digest-only repository grants and delivers raw values only to secure workspaces."""

    REFERENCE_NAME = ".vo-hr-grant-ref.json"
    SECRET_RELATIVE_PATH = Path(".vo") / "credentials" / "human-resources" / "grant"

    def __init__(
        self,
        repository: HRRepository,
        *,
        workspace_base: str | os.PathLike[str],
        secret_factory: Callable[[str], str],
        key_id_factory: Callable[[str], str],
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        supported_provider_kinds: frozenset[str] = frozenset({"openclaw"}),
    ):
        if not isinstance(repository, HRRepository):
            raise HRSkillPublisherValidationError("repository must be an HRRepository")
        if not callable(secret_factory) or not callable(key_id_factory):
            raise HRSkillPublisherValidationError("grant factories are required")
        self._repository = repository
        self._workspace_base = Path(os.path.realpath(os.path.abspath(workspace_base)))
        self._secret_factory = secret_factory
        self._key_id_factory = key_id_factory
        self._clock = clock
        self._supported_provider_kinds = frozenset(supported_provider_kinds)

    def _now(self) -> str:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise HRSkillPublisherValidationError("grant clock must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()

    def _workspace_paths(
        self,
        agent: Mapping[str, object],
        *,
        require_skill: bool,
    ) -> tuple[Path, Path] | None:
        workspace_value = str(agent.get("workspace") or "").strip()
        if not workspace_value:
            return None
        workspace = Path(os.path.realpath(os.path.abspath(workspace_value)))
        try:
            workspace.relative_to(self._workspace_base)
        except ValueError:
            return None
        if workspace == self._workspace_base or not workspace.is_dir():
            return None
        secret_path = workspace / self.SECRET_RELATIVE_PATH
        reference_path = workspace / "skills" / DIRECTORY_SKILL_NAME / self.REFERENCE_NAME
        checked = (
            secret_path.parent.parent.parent,
            secret_path.parent.parent,
            secret_path.parent,
            secret_path,
            reference_path.parent,
            reference_path,
        )
        if not all(managed_skill_path_is_safe(workspace, path) for path in checked):
            return None
        if require_skill and not (reference_path.parent / "SKILL.md").is_file():
            return None
        if require_skill:
            marker_path = reference_path.parent / MANAGED_SKILL_MARKER
            if marker_path.is_symlink() or not marker_path.is_file():
                return None
            try:
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
            if marker.get("managedBy") != "virtual-office" or marker.get("skill") != DIRECTORY_SKILL_NAME:
                return None
        return secret_path, reference_path

    @staticmethod
    def _remove_delivery(paths: tuple[Path, Path] | None) -> bool:
        if paths is None:
            return False
        removed = True
        for path in paths:
            try:
                if path.is_file() and not path.is_symlink():
                    path.unlink()
            except OSError:
                removed = False
        return removed

    @staticmethod
    def _delivery_matches(paths: tuple[Path, Path], *, key_id: str, digest: str) -> bool:
        secret_path, reference_path = paths
        if (
            secret_path.is_symlink()
            or reference_path.is_symlink()
            or not secret_path.is_file()
            or not reference_path.is_file()
        ):
            return False
        try:
            reference = json.loads(reference_path.read_text(encoding="utf-8"))
            secret = secret_path.read_text(encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            return False
        expected_reference = {
            "grantFile": HRGrantManager.SECRET_RELATIVE_PATH.as_posix(),
            "keyId": key_id,
            "schemaVersion": 1,
        }
        actual_digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        return (
            reference == expected_reference
            and hmac.compare_digest(actual_digest, digest)
            and (secret_path.stat().st_mode & 0o777) == 0o600
            and (reference_path.stat().st_mode & 0o777) == 0o600
        )

    def reconcile(
        self,
        agent: Mapping[str, object],
        *,
        eligible: bool,
        force_rotate: bool = False,
    ) -> HRGrantReadiness:
        with _GRANT_LOCK:
            return self._reconcile(agent, eligible=eligible, force_rotate=force_rotate)

    def _reconcile(
        self,
        agent: Mapping[str, object],
        *,
        eligible: bool,
        force_rotate: bool,
    ) -> HRGrantReadiness:
        if not isinstance(agent, Mapping):
            return HRGrantReadiness("", False, "invalid_agent", "", "hr_grant_agent_invalid")
        ai_id = str(agent.get("id") or agent.get("statusKey") or "").strip()
        if not ai_id:
            return HRGrantReadiness("", False, "invalid_agent", "", "hr_grant_agent_invalid")
        try:
            current = self._repository.get_access_grant(ai_id)
        except HRRepositoryError as exc:
            return HRGrantReadiness(ai_id, False, "repository_failed", "", exc.code)
        provider = str(agent.get("providerKind") or "").strip()
        supported = provider in self._supported_provider_kinds
        paths = self._workspace_paths(
            agent,
            require_skill=eligible and supported,
        )
        if not eligible or not supported:
            if current is not None and current.status == "active":
                try:
                    self._repository.revoke_access_grant(
                        ai_id=ai_id,
                        key_id=current.key_id,
                        revoked_at=self._now(),
                        reason="agent_ineligible" if not eligible else "unsupported_provider",
                    )
                except HRRepositoryError as exc:
                    return HRGrantReadiness(ai_id, False, "revoke_failed", "", exc.code)
            cleaned = self._remove_delivery(paths)
            state = "revoked" if not eligible else "unsupported_provider"
            if current is not None and paths is None:
                state = f"{state}_cleanup_unverified"
            elif not cleaned and paths is not None:
                state = f"{state}_cleanup_failed"
            return HRGrantReadiness(
                ai_id,
                False,
                state,
                "",
                "" if state == "revoked" else f"hr_grant_{state}",
            )
        if paths is None:
            return HRGrantReadiness(ai_id, False, "delivery_unsupported", "", "hr_grant_delivery_unsupported")
        if (
            current is not None
            and current.status == "active"
            and not force_rotate
            and self._delivery_matches(paths, key_id=current.key_id, digest=current.secret_digest)
        ):
            return HRGrantReadiness(ai_id, True, "ready", current.key_id, "")

        secret = self._secret_factory(ai_id)
        key_id = self._key_id_factory(ai_id)
        if (
            not isinstance(secret, str)
            or len(secret) < 32
            or any(character.isspace() for character in secret)
            or not isinstance(key_id, str)
            or not key_id
            or any(character.isspace() for character in key_id)
        ):
            return HRGrantReadiness(ai_id, False, "generation_failed", "", "hr_grant_generation_failed")
        digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        secret_path, reference_path = paths
        reference = {
            "grantFile": self.SECRET_RELATIVE_PATH.as_posix(),
            "keyId": key_id,
            "schemaVersion": 1,
        }
        try:
            atomic_write_managed_text(secret_path, secret, mode=0o600)
            atomic_write_managed_text(
                reference_path,
                json.dumps(reference, sort_keys=True, indent=2) + "\n",
                mode=0o600,
            )
            stored = self._repository.rotate_access_grant(
                ai_id=ai_id,
                key_id=key_id,
                secret_digest=digest,
                issued_at=self._now(),
                expected_key_id=current.key_id if current is not None else None,
            )
        except (OSError, HRRepositoryError, HRSkillPublisherValidationError) as exc:
            self._remove_delivery(paths)
            return HRGrantReadiness(
                ai_id,
                False,
                "delivery_failed",
                "",
                getattr(exc, "code", "hr_grant_delivery_failed"),
            )
        return HRGrantReadiness(ai_id, True, "rotated" if current else "issued", stored.key_id, "")
