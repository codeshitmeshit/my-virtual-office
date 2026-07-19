"""Identity-bound Human Resources grants and secure workspace delivery."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping

from services.hr_repository import HRRepository, HRRepositoryError
from services.managed_skills import (
    MANAGED_SKILL_MARKER,
    atomic_write_managed_text,
    managed_skill_path_is_safe,
)


_GRANT_LOCK = threading.RLock()


class HRGrantValidationError(ValueError):
    code = "hr_grant_validation_failed"


@dataclass(frozen=True, slots=True)
class HRGrantReadiness:
    ai_id: str
    ready: bool
    state: str
    key_id: str
    error_code: str


class HRGrantManager:
    """Issue digest-only grants and deliver raw values outside the built-in skill."""

    SECRET_RELATIVE_PATH = Path(".vo") / "credentials" / "human-resources" / "grant"
    REFERENCE_RELATIVE_PATH = (
        Path(".vo") / "credentials" / "human-resources" / "grant-ref.json"
    )
    LEGACY_SKILL_RELATIVE_PATH = Path("skills") / "vo-agent-directory"
    LEGACY_REFERENCE_NAME = ".vo-hr-grant-ref.json"

    def __init__(
        self,
        repository: HRRepository,
        *,
        workspace_base: str | os.PathLike[str],
        secret_factory: Callable[[str], str],
        key_id_factory: Callable[[str], str],
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        grant_ttl_days: int = 30,
        supported_provider_kinds: frozenset[str] = frozenset({"openclaw"}),
    ):
        if not isinstance(repository, HRRepository):
            raise HRGrantValidationError("repository must be an HRRepository")
        if not callable(secret_factory) or not callable(key_id_factory):
            raise HRGrantValidationError("grant factories are required")
        self._repository = repository
        self._workspace_base = Path(os.path.realpath(os.path.abspath(workspace_base)))
        self._secret_factory = secret_factory
        self._key_id_factory = key_id_factory
        self._clock = clock
        if isinstance(grant_ttl_days, bool) or not isinstance(grant_ttl_days, int):
            raise HRGrantValidationError("grant_ttl_days must be an integer")
        if not 1 <= grant_ttl_days <= 365:
            raise HRGrantValidationError("grant_ttl_days must be between 1 and 365")
        self._grant_ttl = timedelta(days=grant_ttl_days)
        self._supported_provider_kinds = frozenset(supported_provider_kinds)
        if not self._supported_provider_kinds:
            raise HRGrantValidationError("supported_provider_kinds must not be empty")

    def _now_datetime(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise HRGrantValidationError("grant clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def _now(self) -> str:
        return self._now_datetime().isoformat()

    def _workspace_paths(self, agent: Mapping[str, object]) -> tuple[Path, Path] | None:
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
        self._remove_owned_legacy_skill(workspace)
        secret_path = workspace / self.SECRET_RELATIVE_PATH
        reference_path = workspace / self.REFERENCE_RELATIVE_PATH
        checked = (
            secret_path.parent.parent.parent,
            secret_path.parent.parent,
            secret_path.parent,
            secret_path,
            reference_path,
        )
        if not all(managed_skill_path_is_safe(workspace, path) for path in checked):
            return None
        return secret_path, reference_path

    @classmethod
    def _remove_owned_legacy_skill(cls, workspace: Path) -> bool:
        """Remove only the old VO-managed workspace copy; preserve unowned content."""
        directory = workspace / cls.LEGACY_SKILL_RELATIVE_PATH
        marker_path = directory / MANAGED_SKILL_MARKER
        skill_path = directory / "SKILL.md"
        reference_path = directory / cls.LEGACY_REFERENCE_NAME
        checked = (directory, marker_path, skill_path, reference_path)
        if not all(managed_skill_path_is_safe(workspace, path) for path in checked):
            return False
        if marker_path.is_symlink() or not marker_path.is_file():
            return False
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if marker.get("managedBy") != "virtual-office" or marker.get("skill") != "vo-agent-directory":
            return False
        declared_digest = str(marker.get("sha256") or "").lower()
        if len(declared_digest) != 64 or any(
            character not in "0123456789abcdef" for character in declared_digest
        ):
            return False
        try:
            actual_digest = hashlib.sha256(skill_path.read_bytes()).hexdigest()
        except OSError:
            return False
        if not hmac.compare_digest(actual_digest, declared_digest):
            return False
        removed = True
        for path in (reference_path, skill_path, marker_path):
            try:
                if path.is_file() and not path.is_symlink():
                    path.unlink()
            except OSError:
                removed = False
        try:
            directory.rmdir()
        except OSError:
            # Extra user files are preserved even after the VO-owned files leave.
            pass
        return removed

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
        paths = self._workspace_paths(agent)
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
            return HRGrantReadiness(
                ai_id,
                False,
                "delivery_unsupported",
                "",
                "hr_grant_delivery_unsupported",
            )
        if (
            current is not None
            and current.status == "active"
            and current.expires_at is not None
            and datetime.fromisoformat(current.expires_at) > self._now_datetime()
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
            return HRGrantReadiness(
                ai_id, False, "generation_failed", "", "hr_grant_generation_failed"
            )
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
            issued_at = self._now_datetime()
            stored = self._repository.rotate_access_grant(
                ai_id=ai_id,
                key_id=key_id,
                secret_digest=digest,
                issued_at=issued_at.isoformat(),
                expires_at=(issued_at + self._grant_ttl).isoformat(),
                expected_key_id=current.key_id if current is not None else None,
            )
        except (OSError, HRRepositoryError, HRGrantValidationError) as exc:
            self._remove_delivery(paths)
            return HRGrantReadiness(
                ai_id,
                False,
                "delivery_failed",
                "",
                getattr(exc, "code", "hr_grant_delivery_failed"),
            )
        return HRGrantReadiness(ai_id, True, "rotated" if current else "issued", stored.key_id, "")
