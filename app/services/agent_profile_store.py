"""Atomic revisioned storage for editable Virtual Office Agent profiles.

This module owns only low-risk profile and appearance data. Provider bindings,
branches, workspaces, project assignments, skills, runtime settings, and Human
Resources history remain in their domain owners.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping


SCHEMA_VERSION = 1
MAX_NAME_LENGTH = 160
MAX_INTRODUCTION_LENGTH = 5_000
MAX_TAG_COUNT = 12
MAX_TAG_LENGTH = 80
MAX_APPEARANCE_BYTES = 16_384
MAX_APPEARANCE_FIELDS = 64

PROFILE_FIELDS = frozenset(
    {"name", "introduction", "responsibilities", "specialties", "appearance"}
)
LEGACY_APPEARANCE_FIELDS = ("emoji", "color", "gender")


class AgentProfileStoreError(RuntimeError):
    """Base error for profile persistence failures."""


class AgentProfileValidationError(AgentProfileStoreError, ValueError):
    code = "agent_profile_invalid"


class AgentProfileConflictError(AgentProfileStoreError):
    code = "agent_profile_revision_conflict"


@dataclass(frozen=True, slots=True)
class AgentProfile:
    ai_id: str
    revision: int
    name: str
    introduction: str
    responsibilities: tuple[str, ...]
    specialties: tuple[str, ...]
    appearance: dict[str, object]
    updated_at: str | None
    source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "aiId": self.ai_id,
            "revision": self.revision,
            "name": self.name,
            "introduction": self.introduction,
            "responsibilities": list(self.responsibilities),
            "specialties": list(self.specialties),
            "appearance": copy.deepcopy(self.appearance),
            "updatedAt": self.updated_at,
            "source": self.source,
        }


def _normalize_ai_id(value: object) -> str:
    ai_id = str(value or "").strip()
    if (
        not ai_id
        or len(ai_id) > 256
        or "/" in ai_id
        or "\\" in ai_id
        or any(ord(character) < 32 for character in ai_id)
    ):
        raise AgentProfileValidationError("ai_id is invalid")
    return ai_id


def _normalize_text(value: object, *, field: str, maximum: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise AgentProfileValidationError(f"{field} must be a string")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise AgentProfileValidationError(f"{field} exceeds {maximum} characters")
    return normalized


def _normalize_tags(value: object, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise AgentProfileValidationError(f"{field} must be a list")
    if len(value) > MAX_TAG_COUNT:
        raise AgentProfileValidationError(f"{field} has too many values")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _normalize_text(item, field=field, maximum=MAX_TAG_LENGTH)
        if not text:
            continue
        folded = text.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        normalized.append(text)
    return tuple(normalized)


def _normalize_appearance(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise AgentProfileValidationError("appearance must be an object")
    if len(value) > MAX_APPEARANCE_FIELDS:
        raise AgentProfileValidationError("appearance has too many fields")
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise AgentProfileValidationError("appearance must contain JSON values") from exc
    if len(encoded.encode("utf-8")) > MAX_APPEARANCE_BYTES:
        raise AgentProfileValidationError("appearance is too large")
    parsed = json.loads(encoded)
    if not isinstance(parsed, dict):
        raise AgentProfileValidationError("appearance must be an object")
    for key in parsed:
        if (
            not isinstance(key, str)
            or not key
            or len(key) > 80
            or any(ord(character) < 32 for character in key)
        ):
            raise AgentProfileValidationError("appearance field name is invalid")
    return parsed


def _normalize_fields(raw: Mapping[str, object]) -> dict[str, object]:
    unknown = set(raw) - PROFILE_FIELDS
    if unknown:
        raise AgentProfileValidationError(
            f"unsupported profile fields: {', '.join(sorted(unknown))}"
        )
    return {
        "name": _normalize_text(
            raw.get("name"), field="name", maximum=MAX_NAME_LENGTH
        ),
        "introduction": _normalize_text(
            raw.get("introduction"),
            field="introduction",
            maximum=MAX_INTRODUCTION_LENGTH,
        ),
        "responsibilities": list(
            _normalize_tags(raw.get("responsibilities"), field="responsibilities")
        ),
        "specialties": list(
            _normalize_tags(raw.get("specialties"), field="specialties")
        ),
        "appearance": _normalize_appearance(raw.get("appearance")),
    }


class AgentProfileStore:
    """Own profile records with optimistic revision checks and atomic writes."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        legacy_office_config_path: str | os.PathLike[str] | None = None,
        now: Callable[[], datetime] | None = None,
        replace: Callable[[str, str], None] | None = None,
    ):
        self.path = Path(path)
        self.legacy_office_config_path = (
            Path(legacy_office_config_path)
            if legacy_office_config_path is not None
            else None
        )
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._replace = replace or os.replace
        self._lock = threading.RLock()

    @staticmethod
    def _empty_root() -> dict[str, object]:
        return {"schemaVersion": SCHEMA_VERSION, "profiles": {}}

    def _load_root(self) -> dict[str, object]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return self._empty_root()
        except OSError as exc:
            raise AgentProfileStoreError("profile store could not be read") from exc
        try:
            root = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AgentProfileStoreError("profile store is invalid JSON") from exc
        if (
            not isinstance(root, dict)
            or root.get("schemaVersion") != SCHEMA_VERSION
            or not isinstance(root.get("profiles"), dict)
        ):
            raise AgentProfileStoreError("profile store schema is invalid")
        return root

    def _load_legacy_fields(self, ai_id: str) -> dict[str, object] | None:
        path = self.legacy_office_config_path
        if path is None:
            return None
        try:
            root = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise AgentProfileStoreError("legacy office config could not be read") from exc
        if not isinstance(root, dict) or not isinstance(root.get("agents", []), list):
            raise AgentProfileStoreError("legacy office config schema is invalid")
        item = next(
            (
                candidate
                for candidate in root.get("agents", [])
                if isinstance(candidate, dict)
                and ai_id in (candidate.get("id"), candidate.get("statusKey"))
            ),
            None,
        )
        if item is None:
            return None
        appearance = copy.deepcopy(item.get("appearance") or {})
        if not isinstance(appearance, dict):
            appearance = {}
        for field in LEGACY_APPEARANCE_FIELDS:
            if field in item and item.get(field) is not None:
                appearance[field] = item.get(field)
        responsibilities = item.get("responsibilities")
        if responsibilities is None:
            legacy_role = str(item.get("role") or "").strip()
            responsibilities = [legacy_role] if legacy_role else []
        return _normalize_fields(
            {
                "name": item.get("name") or item.get("displayName") or "",
                "introduction": item.get("introduction") or "",
                "responsibilities": responsibilities,
                "specialties": item.get("specialties") or [],
                "appearance": appearance,
            }
        )

    @staticmethod
    def _record(ai_id: str, payload: Mapping[str, object], *, source: str) -> AgentProfile:
        fields = _normalize_fields(
            {field: payload.get(field) for field in PROFILE_FIELDS}
        )
        revision = payload.get("revision", 0)
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise AgentProfileStoreError("profile revision is invalid")
        updated_at = payload.get("updatedAt")
        if updated_at is not None and not isinstance(updated_at, str):
            raise AgentProfileStoreError("profile updatedAt is invalid")
        return AgentProfile(
            ai_id=ai_id,
            revision=revision,
            name=str(fields["name"]),
            introduction=str(fields["introduction"]),
            responsibilities=tuple(fields["responsibilities"]),
            specialties=tuple(fields["specialties"]),
            appearance=copy.deepcopy(fields["appearance"]),
            updated_at=updated_at,
            source=source,
        )

    def get(self, ai_id: object) -> AgentProfile | None:
        key = _normalize_ai_id(ai_id)
        with self._lock:
            root = self._load_root()
            payload = root["profiles"].get(key)
            if payload is not None:
                if not isinstance(payload, dict):
                    raise AgentProfileStoreError("profile record is invalid")
                return self._record(key, payload, source="profile-store")
            legacy = self._load_legacy_fields(key)
            if legacy is None:
                return None
            return self._record(key, legacy, source="legacy-office-config")

    def list(self) -> tuple[AgentProfile, ...]:
        with self._lock:
            root = self._load_root()
            records: list[AgentProfile] = []
            for ai_id, payload in root["profiles"].items():
                key = _normalize_ai_id(ai_id)
                if not isinstance(payload, dict):
                    raise AgentProfileStoreError("profile record is invalid")
                records.append(self._record(key, payload, source="profile-store"))
            return tuple(sorted(records, key=lambda record: record.ai_id))

    def update(
        self,
        ai_id: object,
        patch: Mapping[str, object],
        *,
        expected_revision: int,
    ) -> AgentProfile:
        key = _normalize_ai_id(ai_id)
        if not isinstance(patch, Mapping) or not patch:
            raise AgentProfileValidationError("profile patch must not be empty")
        if set(patch) - PROFILE_FIELDS:
            raise AgentProfileValidationError("profile patch contains unsupported fields")
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 0
        ):
            raise AgentProfileValidationError(
                "expected_revision must be a non-negative integer"
            )
        with self._lock:
            root = self._load_root()
            stored = root["profiles"].get(key)
            if stored is not None:
                if not isinstance(stored, dict):
                    raise AgentProfileStoreError("profile record is invalid")
                current = self._record(key, stored, source="profile-store")
            else:
                legacy = self._load_legacy_fields(key)
                current = (
                    self._record(key, legacy, source="legacy-office-config")
                    if legacy is not None
                    else AgentProfile(key, 0, "", "", (), (), {}, None, "new")
                )
            if current.revision != expected_revision:
                raise AgentProfileConflictError(
                    f"Agent {key} revision is {current.revision}, "
                    f"expected {expected_revision}"
                )
            combined: dict[str, object] = {
                "name": current.name,
                "introduction": current.introduction,
                "responsibilities": list(current.responsibilities),
                "specialties": list(current.specialties),
                "appearance": copy.deepcopy(current.appearance),
            }
            combined.update(copy.deepcopy(dict(patch)))
            normalized = _normalize_fields(combined)
            updated_at = self._now().astimezone(timezone.utc).isoformat()
            payload = {
                **normalized,
                "revision": current.revision + 1,
                "updatedAt": updated_at,
            }
            root["profiles"][key] = payload
            self._atomic_write(root)
            return self._record(key, payload, source="profile-store")

    def _atomic_write(self, root: Mapping[str, object]) -> None:
        directory = self.path.parent
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=directory
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(root, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            self._replace(temporary, str(self.path))
        except Exception as exc:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            if isinstance(exc, AgentProfileStoreError):
                raise
            raise AgentProfileStoreError("profile store write failed") from exc
