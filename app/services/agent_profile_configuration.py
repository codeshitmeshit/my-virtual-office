"""Audience policy and one-field commands for Agent profile configuration."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from services.agent_profile_store import AgentProfile, AgentProfileStore


LOW_RISK_FIELDS = frozenset(
    {"name", "introduction", "responsibilities", "specialties"}
)
DIRECTORY_RECONCILIATION_FIELDS = LOW_RISK_FIELDS

APPEARANCE_ENUMS: dict[str, frozenset[object]] = {
    "gender": frozenset({"M", "F"}),
    "hairStyle": frozenset(
        {
            "bald",
            "buzz",
            "short",
            "medium",
            "long",
            "curly",
            "wavy",
            "spiky",
            "bun",
            "ponytail",
            "mohawk",
        }
    ),
    "eyebrowStyle": frozenset({"thin", "thick", "angular", "arched"}),
    "facialHair": frozenset(
        {None, "none", "stubble", "beard", "goatee", "mustache"}
    ),
    "costume": frozenset({None, "none", "lobster", "chicken"}),
    "headwear": frozenset(
        {
            None,
            "none",
            "hardhat",
            "cap",
            "crown",
            "tiara",
            "headband",
            "goggles",
            "headset",
            "beanie",
        }
    ),
    "glasses": frozenset({None, "none", "round", "square", "sunglasses"}),
    "heldItem": frozenset(
        {
            None,
            "none",
            "tablet",
            "wrench",
            "coffee",
            "clipboard",
            "pen",
            "hammer",
            "testTube",
            "book",
        }
    ),
    "deskItem": frozenset(
        {
            None,
            "none",
            "anvil",
            "trophy",
            "calendar",
            "envelope",
            "money",
            "ruler",
            "marker",
            "chart",
            "plans",
            "checklist",
            "microscope",
            "shield",
            "phone",
            "files",
        }
    ),
}
APPEARANCE_COLORS = frozenset(
    {
        "color",
        "skinTone",
        "hairColor",
        "hairHighlight",
        "eyeColor",
        "facialHairColor",
        "headwearColor",
        "glassesColor",
    }
)
APPEARANCE_TEXT = frozenset({"emoji"})
APPEARANCE_FIELDS = (
    frozenset(APPEARANCE_ENUMS) | APPEARANCE_COLORS | APPEARANCE_TEXT
)
COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")


class AgentProfileConfigurationError(RuntimeError):
    code = "agent_profile_configuration_failed"


class AgentProfileAuthorizationError(AgentProfileConfigurationError, PermissionError):
    code = "agent_profile_mutation_denied"


class AgentProfileCommandError(AgentProfileConfigurationError, ValueError):
    code = "agent_profile_command_invalid"


class ActorKind(str, Enum):
    HUMAN = "human"
    AGENT = "agent"


@dataclass(frozen=True, slots=True)
class ConfigurationActor:
    kind: ActorKind
    ai_id: str | None = None

    @classmethod
    def human(cls) -> "ConfigurationActor":
        return cls(ActorKind.HUMAN)

    @classmethod
    def agent(cls, ai_id: str) -> "ConfigurationActor":
        value = str(ai_id or "").strip()
        if not value:
            raise AgentProfileCommandError("Agent actor requires a stable AI ID")
        return cls(ActorKind.AGENT, value)


@dataclass(frozen=True, slots=True)
class ProfileMutationCommand:
    target_ai_id: str
    field: str
    value: object
    expected_revision: int

    def __post_init__(self) -> None:
        if not str(self.target_ai_id or "").strip():
            raise AgentProfileCommandError("target_ai_id is required")
        if not str(self.field or "").strip():
            raise AgentProfileCommandError("field is required")
        if (
            isinstance(self.expected_revision, bool)
            or not isinstance(self.expected_revision, int)
            or self.expected_revision < 0
        ):
            raise AgentProfileCommandError(
                "expected_revision must be a non-negative integer"
            )


@dataclass(frozen=True, slots=True)
class ProfileMutationResult:
    profile: AgentProfile
    field: str
    reconciliation_pending: bool = False
    warning_code: str | None = None


class AgentDirectoryReconciliationPort(Protocol):
    def profile_changed(
        self,
        *,
        ai_id: str,
        field: str,
        value: object,
        revision: int,
    ) -> None: ...


class _NoopDirectoryPort:
    def profile_changed(
        self,
        *,
        ai_id: str,
        field: str,
        value: object,
        revision: int,
    ) -> None:
        return None


class AgentProfileConfigurationService:
    """Apply allowlisted low-risk changes under an explicit actor policy."""

    def __init__(
        self,
        store: AgentProfileStore,
        *,
        directory: AgentDirectoryReconciliationPort | None = None,
    ):
        if not isinstance(store, AgentProfileStore):
            raise TypeError("store must be an AgentProfileStore")
        self._store = store
        self._directory = directory or _NoopDirectoryPort()

    @staticmethod
    def _authorize(actor: ConfigurationActor, target_ai_id: str) -> None:
        if not isinstance(actor, ConfigurationActor):
            raise AgentProfileAuthorizationError("configuration actor is invalid")
        if actor.kind is ActorKind.HUMAN:
            return
        if actor.kind is ActorKind.AGENT and actor.ai_id == target_ai_id:
            return
        raise AgentProfileAuthorizationError(
            "an ordinary Agent may modify only its own low-risk profile"
        )

    @staticmethod
    def _appearance_value(field: str, value: object) -> object:
        if field in APPEARANCE_ENUMS:
            if value not in APPEARANCE_ENUMS[field]:
                raise AgentProfileCommandError(
                    f"appearance field {field} has an unsupported value"
                )
            return None if value == "none" else value
        if field in APPEARANCE_COLORS:
            if value is None and field in {"hairHighlight", "facialHairColor"}:
                return None
            if not isinstance(value, str) or COLOR_PATTERN.fullmatch(value) is None:
                raise AgentProfileCommandError(
                    f"appearance field {field} requires a hex color"
                )
            return value.lower()
        if field in APPEARANCE_TEXT:
            if not isinstance(value, str):
                raise AgentProfileCommandError(
                    f"appearance field {field} requires text"
                )
            normalized = value.strip()
            if not normalized or len(normalized) > 16:
                raise AgentProfileCommandError(
                    f"appearance field {field} is invalid"
                )
            return normalized
        raise AgentProfileCommandError(
            f"appearance field {field} is not self-service configurable"
        )

    def mutate(
        self,
        actor: ConfigurationActor,
        command: ProfileMutationCommand,
    ) -> ProfileMutationResult:
        if not isinstance(command, ProfileMutationCommand):
            raise AgentProfileCommandError("profile mutation command is invalid")
        target = command.target_ai_id.strip()
        field = command.field.strip()
        self._authorize(actor, target)

        if field in LOW_RISK_FIELDS:
            patch = {field: copy.deepcopy(command.value)}
        elif field.startswith("appearance."):
            appearance_field = field.removeprefix("appearance.")
            value = self._appearance_value(appearance_field, command.value)
            current = self._store.get(target)
            appearance = copy.deepcopy(current.appearance if current else {})
            if value is None:
                appearance.pop(appearance_field, None)
            else:
                appearance[appearance_field] = value
            patch = {"appearance": appearance}
        else:
            raise AgentProfileAuthorizationError(
                f"field {field} is not a low-risk profile field"
            )

        profile = self._store.update(
            target,
            patch,
            expected_revision=command.expected_revision,
        )
        if field not in DIRECTORY_RECONCILIATION_FIELDS:
            return ProfileMutationResult(profile=profile, field=field)
        try:
            self._directory.profile_changed(
                ai_id=target,
                field=field,
                value=copy.deepcopy(command.value),
                revision=profile.revision,
            )
        except Exception:
            # The profile store is authoritative for these edits. A directory
            # projection failure is reported for reconciliation and must not
            # make a client retry the already committed revision.
            return ProfileMutationResult(
                profile=profile,
                field=field,
                reconciliation_pending=True,
                warning_code="agent_directory_reconciliation_pending",
            )
        return ProfileMutationResult(profile=profile, field=field)

    @staticmethod
    def recommendation_terms(profile: AgentProfile) -> tuple[str, ...]:
        """Return descriptive terms only; callers may rank but never deny."""

        terms: list[str] = []
        seen: set[str] = set()
        for value in (*profile.responsibilities, *profile.specialties):
            normalized = value.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            terms.append(value)
        return tuple(terms)

    @staticmethod
    def assignment_allowed(
        _profile: AgentProfile,
        _task_categories: tuple[str, ...] = (),
    ) -> bool:
        """Responsibility/specialty mismatch is never a permission gate."""

        return True
