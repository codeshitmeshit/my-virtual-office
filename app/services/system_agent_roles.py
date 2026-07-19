"""Immutable role definitions and policy lookup for VO system Agents.

This module is intentionally independent from provider, persistence, HTTP, and
domain entry points.  Domains register data; shared callers ask the registry for
identity and eligibility decisions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePath
from types import MappingProxyType
from typing import Any, Iterable, Mapping


_ROLE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_STABLE_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_PROVIDER_KIND_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


class SystemAgentRoleError(ValueError):
    """Raised when role configuration is invalid or ambiguous."""


def _clean_identity(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _validate_safe_relative_file(value: str, *, field: str) -> None:
    path = PurePath(value)
    if (
        not value
        or path.is_absolute()
        or len(path.parts) != 1
        or path.name in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\x00" in value
    ):
        raise SystemAgentRoleError(f"{field} must be one safe relative filename")


@dataclass(frozen=True, slots=True)
class SystemAgentRole:
    """Configuration and cross-domain policy for one globally unique role."""

    role_key: str
    stable_id: str
    display_name: str
    emoji: str
    provider_kind: str
    profile_template: str
    version_marker: str
    required_files: tuple[str, ...]
    assignable: bool
    deletable: bool
    meeting_eligible: bool
    automatic_work_categories: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _ROLE_KEY_RE.fullmatch(self.role_key):
            raise SystemAgentRoleError(
                "role_key must start with a letter and contain lowercase letters, digits, or underscores"
            )
        if not _STABLE_ID_RE.fullmatch(self.stable_id):
            raise SystemAgentRoleError(
                "stable_id must be a lowercase provider-safe identifier of at most 64 characters"
            )
        if not self.display_name.strip():
            raise SystemAgentRoleError("display_name must not be empty")
        if self.display_name != self.display_name.strip():
            raise SystemAgentRoleError("display_name must not have surrounding whitespace")
        if not self.emoji.strip():
            raise SystemAgentRoleError("emoji must not be empty")
        if not _PROVIDER_KIND_RE.fullmatch(self.provider_kind):
            raise SystemAgentRoleError("provider_kind must be a lowercase identifier")
        _validate_safe_relative_file(self.profile_template, field="profile_template")
        if not self.version_marker.strip() or self.version_marker != self.version_marker.strip():
            raise SystemAgentRoleError("version_marker must be a non-empty trimmed string")
        if not self.required_files:
            raise SystemAgentRoleError("required_files must not be empty")
        for filename in self.required_files:
            _validate_safe_relative_file(filename, field="required_files entry")
        if len(set(self.required_files)) != len(self.required_files):
            raise SystemAgentRoleError("required_files must not contain duplicates")
        if any(not _ROLE_KEY_RE.fullmatch(item) for item in self.automatic_work_categories):
            raise SystemAgentRoleError("automatic_work_categories must contain role-key identifiers")
        if len(set(self.automatic_work_categories)) != len(self.automatic_work_categories):
            raise SystemAgentRoleError("automatic_work_categories must not contain duplicates")

        identities = [self.stable_id, self.display_name, *self.aliases]
        if any(not _clean_identity(item) or item != _clean_identity(item) for item in identities):
            raise SystemAgentRoleError("role identities must be non-empty and trimmed")
        if len(set(identities)) != len(identities):
            raise SystemAgentRoleError("stable_id, display_name, and aliases must be unique")

    @property
    def identity_keys(self) -> frozenset[str]:
        return frozenset((self.stable_id, self.display_name, *self.aliases))

    def matches_identity(self, candidate: Any, *persisted_identities: Any) -> bool:
        needle = _clean_identity(candidate)
        if not needle:
            return False
        known = set(self.identity_keys)
        known.update(
            cleaned
            for value in persisted_identities
            if (cleaned := _clean_identity(value))
        )
        return needle in known


class SystemAgentRoleRegistry:
    """Validated role registry with exact, conflict-free identity matching."""

    def __init__(self, roles: Iterable[SystemAgentRole]):
        by_key: dict[str, SystemAgentRole] = {}
        by_identity: dict[str, SystemAgentRole] = {}
        for role in roles:
            if not isinstance(role, SystemAgentRole):
                raise SystemAgentRoleError("registry entries must be SystemAgentRole values")
            if role.role_key in by_key:
                raise SystemAgentRoleError(f"duplicate system-Agent role_key: {role.role_key}")
            by_key[role.role_key] = role
            for identity in role.identity_keys:
                conflict = by_identity.get(identity)
                if conflict is not None:
                    raise SystemAgentRoleError(
                        f"system-Agent identity {identity!r} conflicts between "
                        f"{conflict.role_key!r} and {role.role_key!r}"
                    )
                by_identity[identity] = role
        self._by_key = MappingProxyType(by_key)
        self._by_identity = MappingProxyType(by_identity)

    @property
    def roles(self) -> tuple[SystemAgentRole, ...]:
        return tuple(self._by_key.values())

    def get(self, role_key: str) -> SystemAgentRole | None:
        return self._by_key.get(_clean_identity(role_key))

    def require(self, role_key: str) -> SystemAgentRole:
        role = self.get(role_key)
        if role is None:
            raise KeyError(f"unknown system-Agent role: {role_key}")
        return role

    def resolve(
        self,
        candidate: Any,
        *,
        persisted_identities: Mapping[str, Iterable[Any]] | None = None,
    ) -> SystemAgentRole | None:
        candidates: list[str] = []
        if isinstance(candidate, Mapping):
            for key in ("systemRole", "system_role"):
                role_key = _clean_identity(candidate.get(key))
                if role_key and (role := self.get(role_key)) is not None:
                    return role
            for key in ("id", "agentId", "agent_id", "statusKey", "name"):
                if value := _clean_identity(candidate.get(key)):
                    candidates.append(value)
        elif value := _clean_identity(candidate):
            candidates.append(value)

        for value in candidates:
            if role := self._by_identity.get(value):
                return role

        if persisted_identities:
            matches: list[SystemAgentRole] = []
            candidate_set = set(candidates)
            for role_key, values in persisted_identities.items():
                role = self.get(role_key)
                if role is None:
                    continue
                persisted = {_clean_identity(value) for value in values}
                if candidate_set.intersection(persisted - {""}):
                    matches.append(role)
            if len(matches) > 1:
                raise SystemAgentRoleError("persisted identities resolve to conflicting system-Agent roles")
            if matches:
                return matches[0]
        return None

    def is_assignable(self, candidate: Any, **kwargs: Any) -> bool:
        role = self.resolve(candidate, **kwargs)
        return True if role is None else role.assignable

    def is_deletable(self, candidate: Any, **kwargs: Any) -> bool:
        role = self.resolve(candidate, **kwargs)
        return True if role is None else role.deletable

    def is_meeting_eligible(self, candidate: Any, **kwargs: Any) -> bool:
        role = self.resolve(candidate, **kwargs)
        return True if role is None else role.meeting_eligible


_STANDARD_PROFILE_FILES = (
    "IDENTITY.md",
    "SOUL.md",
    "AGENTS.md",
    "agent.md",
    "MEMORY.md",
    "HEARTBEAT.md",
)

ARCHIVE_MANAGER_ROLE = SystemAgentRole(
    role_key="archive_manager",
    stable_id="archive-manager",
    display_name="档案管理员",
    emoji="🗄️",
    provider_kind="openclaw",
    profile_template="archive-manager-profile.md",
    version_marker="archive-manager-profile-version",
    required_files=_STANDARD_PROFILE_FILES,
    assignable=False,
    deletable=False,
    meeting_eligible=False,
    automatic_work_categories=("archive_maintenance",),
)

HR_ROLE = SystemAgentRole(
    role_key="hr",
    stable_id="hr",
    display_name="HR",
    emoji="🧑‍💼",
    provider_kind="openclaw",
    profile_template="hr-profile.md",
    version_marker="hr-profile-version",
    required_files=_STANDARD_PROFILE_FILES,
    assignable=False,
    deletable=False,
    meeting_eligible=True,
    automatic_work_categories=("directory_coordination", "daily_reporting", "performance_assessment"),
)

DEFAULT_SYSTEM_AGENT_ROLES = SystemAgentRoleRegistry((ARCHIVE_MANAGER_ROLE, HR_ROLE))


def resolve_system_agent_role(
    candidate: Any,
    *,
    persisted_identities: Mapping[str, Iterable[Any]] | None = None,
) -> SystemAgentRole | None:
    return DEFAULT_SYSTEM_AGENT_ROLES.resolve(
        candidate,
        persisted_identities=persisted_identities,
    )
