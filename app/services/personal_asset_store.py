"""个人资产的单一、原子且可审计的持久化权威。"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import tempfile
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


JsonDict = dict[str, Any]
SCHEMA_VERSION = 1
SENSITIVITIES = frozenset({"standard", "sensitive"})
SUGGESTION_TERMINAL = frozenset({"accepted", "rejected"})
SUGGESTION_STATUSES = frozenset({"pending", *SUGGESTION_TERMINAL})
MAX_VALUE_BYTES = 16_384
MAX_VALUE_DEPTH = 5
MAX_ENTRIES = 500
MAX_SUGGESTIONS = 500
DEFAULT_USAGE_LIMIT = 1_000

_PATH_LOCKS: dict[str, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


class PersonalAssetStoreError(RuntimeError):
    code = "personal_asset_state_unavailable"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class PersonalAssetValidationError(PersonalAssetStoreError, ValueError):
    code = "personal_asset_invalid"


class PersonalAssetConflictError(PersonalAssetStoreError):
    code = "personal_asset_revision_conflict"


@dataclass(frozen=True, slots=True)
class PersonalAssetEntry:
    id: str
    category: str
    label: str
    value: Any
    sensitivity: str
    revision: int
    created_at: str
    updated_at: str

    def to_dict(self) -> JsonDict:
        return {
            "id": self.id,
            "category": self.category,
            "label": self.label,
            "value": copy.deepcopy(self.value),
            "sensitivity": self.sensitivity,
            "revision": self.revision,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class PersonalAssetSuggestion:
    id: str
    proposal: JsonDict
    source: JsonDict
    status: str
    created_at: str
    updated_at: str

    def to_dict(self) -> JsonDict:
        return {
            "id": self.id,
            "proposal": copy.deepcopy(self.proposal),
            "source": copy.deepcopy(self.source),
            "status": self.status,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class PersonalAssetAccessLink:
    request_id: str
    decision_id: str
    agent_id: str
    task_context: JsonDict
    entry_ids: tuple[str, ...]
    expires_at: str
    consumed_at: str = ""

    def to_dict(self) -> JsonDict:
        return {
            "requestId": self.request_id,
            "decisionId": self.decision_id,
            "agentId": self.agent_id,
            "taskContext": copy.deepcopy(self.task_context),
            "entryIds": list(self.entry_ids),
            "expiresAt": self.expires_at,
            "consumedAt": self.consumed_at,
        }


@dataclass(frozen=True, slots=True)
class PersonalAssetUsageRecord:
    request_id: str
    agent_id: str
    task_context: JsonDict
    entry_ids: tuple[str, ...]
    outcome: str
    created_at: str

    def to_dict(self) -> JsonDict:
        return {
            "requestId": self.request_id,
            "agentId": self.agent_id,
            "taskContext": copy.deepcopy(self.task_context),
            "entryIds": list(self.entry_ids),
            "outcome": self.outcome,
            "createdAt": self.created_at,
        }


def _lock_for(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


def _text(value: object, *, field: str, maximum: int, required: bool = True) -> str:
    if not isinstance(value, str):
        raise PersonalAssetValidationError(f"{field} must be a string")
    result = value.strip()
    if required and not result:
        raise PersonalAssetValidationError(f"{field} is required")
    if len(result) > maximum or any(ord(character) < 32 for character in result):
        raise PersonalAssetValidationError(f"{field} is invalid")
    return result


def _json_depth(value: Any, depth: int = 0) -> int:
    if depth > MAX_VALUE_DEPTH:
        return depth
    if isinstance(value, dict):
        return max((_json_depth(item, depth + 1) for item in value.values()), default=depth)
    if isinstance(value, list):
        return max((_json_depth(item, depth + 1) for item in value), default=depth)
    return depth


def _json_value(value: Any, *, field: str = "value") -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PersonalAssetValidationError(f"{field} must contain JSON values") from exc
    if len(encoded.encode("utf-8")) > MAX_VALUE_BYTES:
        raise PersonalAssetValidationError(f"{field} is too large")
    if _json_depth(value) > MAX_VALUE_DEPTH:
        raise PersonalAssetValidationError(f"{field} is too deep")
    return json.loads(encoded)


def _task_context(value: object) -> JsonDict:
    if not isinstance(value, Mapping):
        raise PersonalAssetValidationError("taskContext must be an object")
    result: JsonDict = {}
    for key in ("type", "id", "label", "projectId"):
        if value.get(key) is not None:
            result[key] = _text(value.get(key), field=f"taskContext.{key}", maximum=240)
    if not result.get("type") or not result.get("id"):
        raise PersonalAssetValidationError("taskContext.type and taskContext.id are required")
    return result


class PersonalAssetStore:
    """Owner profile authority; callers never mutate returned dictionaries in place."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        now: Callable[[], datetime] | None = None,
        replace: Callable[[str, str], None] | None = None,
        usage_limit: int = DEFAULT_USAGE_LIMIT,
    ):
        self.path = Path(path)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._replace = replace or os.replace
        self._usage_limit = max(1, min(10_000, int(usage_limit)))
        self._lock = _lock_for(self.path)

    @staticmethod
    def _empty() -> JsonDict:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "revision": 0,
            "entries": {},
            "suggestions": {},
            "accessLinks": {},
            "usageRecords": [],
            "idempotency": {},
        }

    def _iso_now(self) -> str:
        return self._now().astimezone(timezone.utc).isoformat()

    def _load(self) -> JsonDict:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return self._empty()
        except OSError as exc:
            raise PersonalAssetStoreError("personal asset state could not be read") from exc
        try:
            root = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PersonalAssetStoreError(
                "personal asset state is invalid JSON", code="personal_asset_state_invalid"
            ) from exc
        required = {
            "entries": dict,
            "suggestions": dict,
            "accessLinks": dict,
            "usageRecords": list,
            "idempotency": dict,
        }
        if not isinstance(root, dict) or root.get("schemaVersion") != SCHEMA_VERSION:
            raise PersonalAssetStoreError(
                "personal asset state schema is invalid", code="personal_asset_state_invalid"
            )
        if any(not isinstance(root.get(key), expected) for key, expected in required.items()):
            raise PersonalAssetStoreError(
                "personal asset state collections are invalid", code="personal_asset_state_invalid"
            )
        revision = root.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise PersonalAssetStoreError(
                "personal asset revision is invalid", code="personal_asset_state_invalid"
            )
        return root

    def _write(self, root: Mapping[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(root, stream, ensure_ascii=False, sort_keys=True, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            self._replace(temporary, str(self.path))
            os.chmod(self.path, 0o600)
        except Exception as exc:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise PersonalAssetStoreError("personal asset state could not be written") from exc

    @staticmethod
    def _expect_revision(root: Mapping[str, object], expected_revision: int) -> None:
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
            raise PersonalAssetValidationError("expectedRevision must be a non-negative integer")
        if root["revision"] != expected_revision:
            raise PersonalAssetConflictError(
                f"personal asset revision is {root['revision']}, expected {expected_revision}"
            )

    @staticmethod
    def _entry_payload(raw: Mapping[str, object], *, existing: Mapping[str, object] | None = None) -> JsonDict:
        if not isinstance(raw, Mapping):
            raise PersonalAssetValidationError("entry must be an object")
        allowed = {"category", "label", "value", "sensitivity"}
        if set(raw) - allowed:
            raise PersonalAssetValidationError("entry contains unsupported fields")
        combined = {
            "category": (existing or {}).get("category"),
            "label": (existing or {}).get("label"),
            "value": copy.deepcopy((existing or {}).get("value")),
            "sensitivity": (existing or {}).get("sensitivity", "standard"),
        }
        combined.update(copy.deepcopy(dict(raw)))
        sensitivity = _text(
            combined.get("sensitivity"), field="sensitivity", maximum=20
        ).lower()
        if sensitivity not in SENSITIVITIES:
            raise PersonalAssetValidationError("sensitivity must be standard or sensitive")
        return {
            "category": _text(combined.get("category"), field="category", maximum=80),
            "label": _text(combined.get("label"), field="label", maximum=160),
            "value": _json_value(combined.get("value")),
            "sensitivity": sensitivity,
        }

    def _public_snapshot(self, root: Mapping[str, object]) -> JsonDict:
        entries = [copy.deepcopy(item) for item in root["entries"].values()]
        suggestions = [copy.deepcopy(item) for item in root["suggestions"].values()]
        entries.sort(key=lambda item: (str(item.get("createdAt") or ""), str(item.get("id") or "")))
        suggestions.sort(key=lambda item: (str(item.get("createdAt") or ""), str(item.get("id") or "")))
        return {
            "revision": int(root["revision"]),
            "entries": entries,
            "suggestions": suggestions,
        }

    def snapshot(self) -> JsonDict:
        with self._lock:
            return self._public_snapshot(self._load())

    def internal_snapshot(self) -> JsonDict:
        with self._lock:
            return copy.deepcopy(self._load())

    def restore_profile_snapshot(
        self, profile: Mapping[str, object], *, expected_revision: int
    ) -> JsonDict:
        """Atomically replace public profile data after a validated remote restore."""

        if not isinstance(profile, Mapping):
            raise PersonalAssetValidationError("profile must be an object")
        remote_revision = profile.get("revision")
        if (
            isinstance(remote_revision, bool)
            or not isinstance(remote_revision, int)
            or remote_revision < 0
        ):
            raise PersonalAssetValidationError("profile revision is invalid")
        raw_entries = profile.get("entries")
        raw_suggestions = profile.get("suggestions")
        if not isinstance(raw_entries, list) or len(raw_entries) > MAX_ENTRIES:
            raise PersonalAssetValidationError("profile entries are invalid")
        if not isinstance(raw_suggestions, list) or len(raw_suggestions) > MAX_SUGGESTIONS:
            raise PersonalAssetValidationError("profile suggestions are invalid")

        entries: JsonDict = {}
        for raw in raw_entries:
            if not isinstance(raw, Mapping):
                raise PersonalAssetValidationError("profile entry is invalid")
            entry_id = _text(raw.get("id"), field="entry.id", maximum=160)
            if entry_id in entries:
                raise PersonalAssetValidationError("profile entry ids are duplicated")
            entry_revision = raw.get("revision")
            if (
                isinstance(entry_revision, bool)
                or not isinstance(entry_revision, int)
                or entry_revision < 1
            ):
                raise PersonalAssetValidationError("entry revision is invalid")
            entries[entry_id] = {
                "id": entry_id,
                **self._entry_payload(
                    {
                        key: raw.get(key)
                        for key in ("category", "label", "value", "sensitivity")
                    }
                ),
                "revision": entry_revision,
                "createdAt": _text(raw.get("createdAt"), field="entry.createdAt", maximum=80),
                "updatedAt": _text(raw.get("updatedAt"), field="entry.updatedAt", maximum=80),
            }

        suggestions: JsonDict = {}
        for raw in raw_suggestions:
            if not isinstance(raw, Mapping):
                raise PersonalAssetValidationError("profile suggestion is invalid")
            suggestion_id = _text(
                raw.get("id"), field="suggestion.id", maximum=160
            )
            if suggestion_id in suggestions:
                raise PersonalAssetValidationError("profile suggestion ids are duplicated")
            status = _text(
                raw.get("status"), field="suggestion.status", maximum=20
            ).lower()
            if status not in SUGGESTION_STATUSES:
                raise PersonalAssetValidationError("suggestion status is invalid")
            proposal = raw.get("proposal")
            if not isinstance(proposal, Mapping):
                raise PersonalAssetValidationError("suggestion proposal is invalid")
            source = _json_value(raw.get("source") or {}, field="suggestion.source")
            if not isinstance(source, dict):
                raise PersonalAssetValidationError("suggestion source is invalid")
            suggestions[suggestion_id] = {
                "id": suggestion_id,
                "proposal": self._entry_payload(proposal),
                "source": source,
                "status": status,
                "createdAt": _text(
                    raw.get("createdAt"), field="suggestion.createdAt", maximum=80
                ),
                "updatedAt": _text(
                    raw.get("updatedAt"), field="suggestion.updatedAt", maximum=80
                ),
            }

        with self._lock:
            root = self._load()
            self._expect_revision(root, expected_revision)
            working = copy.deepcopy(root)
            working["entries"] = entries
            working["suggestions"] = suggestions
            # Grants and idempotency receipts point at the replaced profile and must not survive it.
            working["accessLinks"] = {}
            working["idempotency"] = {}
            working["revision"] += 1
            self._write(working)
            return {
                "revision": working["revision"],
                "snapshot": self._public_snapshot(working),
            }

    def create_entry(self, payload: Mapping[str, object], *, expected_revision: int) -> JsonDict:
        normalized = self._entry_payload(payload)
        with self._lock:
            root = self._load()
            self._expect_revision(root, expected_revision)
            if len(root["entries"]) >= MAX_ENTRIES:
                raise PersonalAssetValidationError("personal asset entry limit reached")
            now = self._iso_now()
            entry = PersonalAssetEntry(
                id=f"asset-{uuid.uuid4().hex}",
                category=normalized["category"],
                label=normalized["label"],
                value=normalized["value"],
                sensitivity=normalized["sensitivity"],
                revision=1,
                created_at=now,
                updated_at=now,
            ).to_dict()
            root["entries"][entry["id"]] = entry
            root["revision"] += 1
            self._write(root)
            return {"entry": copy.deepcopy(entry), "revision": root["revision"], "snapshot": self._public_snapshot(root)}

    def update_entry(
        self, entry_id: object, patch: Mapping[str, object], *, expected_revision: int
    ) -> JsonDict:
        key = _text(entry_id, field="entryId", maximum=160)
        if not isinstance(patch, Mapping) or not patch:
            raise PersonalAssetValidationError("entry patch must not be empty")
        with self._lock:
            root = self._load()
            self._expect_revision(root, expected_revision)
            existing = root["entries"].get(key)
            if not isinstance(existing, dict):
                raise PersonalAssetValidationError("personal asset entry was not found")
            normalized = self._entry_payload(patch, existing=existing)
            updated = {
                **copy.deepcopy(existing),
                **normalized,
                "revision": int(existing.get("revision") or 0) + 1,
                "updatedAt": self._iso_now(),
            }
            root["entries"][key] = updated
            root["revision"] += 1
            self._write(root)
            return {"entry": copy.deepcopy(updated), "revision": root["revision"], "snapshot": self._public_snapshot(root)}

    def delete_entry(self, entry_id: object, *, expected_revision: int) -> JsonDict:
        key = _text(entry_id, field="entryId", maximum=160)
        with self._lock:
            root = self._load()
            self._expect_revision(root, expected_revision)
            deleted = root["entries"].pop(key, None)
            if not isinstance(deleted, dict):
                raise PersonalAssetValidationError("personal asset entry was not found")
            root["revision"] += 1
            self._write(root)
            return {"deleted": copy.deepcopy(deleted), "revision": root["revision"], "snapshot": self._public_snapshot(root)}

    def create_suggestion(
        self, payload: Mapping[str, object], *, idempotency_key: object
    ) -> JsonDict:
        if not isinstance(payload, Mapping):
            raise PersonalAssetValidationError("suggestion must be an object")
        key = _text(idempotency_key, field="idempotencyKey", maximum=240)
        proposal = self._entry_payload(payload.get("proposal") if isinstance(payload.get("proposal"), Mapping) else {})
        source = _json_value(payload.get("source") or {}, field="source")
        if not isinstance(source, dict):
            raise PersonalAssetValidationError("source must be an object")
        with self._lock:
            root = self._load()
            receipt_key = f"suggestion:{key}"
            existing_id = root["idempotency"].get(receipt_key)
            if existing_id:
                existing = root["suggestions"].get(existing_id)
                if not isinstance(existing, dict):
                    raise PersonalAssetStoreError("suggestion idempotency state is invalid", code="personal_asset_state_invalid")
                return {"created": False, "suggestion": copy.deepcopy(existing), "revision": root["revision"]}
            if len(root["suggestions"]) >= MAX_SUGGESTIONS:
                raise PersonalAssetValidationError("personal asset suggestion limit reached")
            now = self._iso_now()
            suggestion = PersonalAssetSuggestion(
                id=f"suggestion-{uuid.uuid4().hex}",
                proposal=proposal,
                source=source,
                status="pending",
                created_at=now,
                updated_at=now,
            ).to_dict()
            root["suggestions"][suggestion["id"]] = suggestion
            root["idempotency"][receipt_key] = suggestion["id"]
            root["revision"] += 1
            self._write(root)
            return {"created": True, "suggestion": copy.deepcopy(suggestion), "revision": root["revision"]}

    def resolve_suggestion(
        self,
        suggestion_id: object,
        *,
        action: object,
        expected_revision: int,
        edited_proposal: Mapping[str, object] | None = None,
    ) -> JsonDict:
        key = _text(suggestion_id, field="suggestionId", maximum=160)
        normalized_action = _text(action, field="action", maximum=20).lower()
        if normalized_action not in {"accept", "reject"}:
            raise PersonalAssetValidationError("action must be accept or reject")
        with self._lock:
            root = self._load()
            self._expect_revision(root, expected_revision)
            suggestion = root["suggestions"].get(key)
            if not isinstance(suggestion, dict):
                raise PersonalAssetValidationError("personal asset suggestion was not found")
            if suggestion.get("status") in SUGGESTION_TERMINAL:
                raise PersonalAssetConflictError("personal asset suggestion is already resolved")
            entry = None
            if normalized_action == "accept":
                proposal = edited_proposal or suggestion.get("proposal") or {}
                normalized = self._entry_payload(proposal)
                now = self._iso_now()
                entry = PersonalAssetEntry(
                    id=f"asset-{uuid.uuid4().hex}", revision=1, created_at=now, updated_at=now, **normalized
                ).to_dict()
                root["entries"][entry["id"]] = entry
            suggestion["status"] = "accepted" if normalized_action == "accept" else "rejected"
            suggestion["updatedAt"] = self._iso_now()
            root["revision"] += 1
            self._write(root)
            return {
                "suggestion": copy.deepcopy(suggestion),
                "entry": copy.deepcopy(entry),
                "revision": root["revision"],
                "snapshot": self._public_snapshot(root),
            }

    def apply_batch(
        self,
        changes: Sequence[Mapping[str, object]],
        *,
        expected_revision: int,
        idempotency_key: object,
        source: Mapping[str, object],
    ) -> JsonDict:
        if not isinstance(changes, Sequence) or isinstance(changes, (str, bytes)) or not changes:
            raise PersonalAssetValidationError("confirmedChanges must be a non-empty list")
        if len(changes) > 50:
            raise PersonalAssetValidationError("confirmedChanges has too many items")
        receipt_key = f"batch:{_text(idempotency_key, field='idempotencyKey', maximum=240)}"
        normalized_source = _json_value(source, field="source")
        if not isinstance(normalized_source, dict):
            raise PersonalAssetValidationError("source must be an object")
        normalized_changes = _json_value(list(changes), field="confirmedChanges")
        request_fingerprint = hashlib.sha256(
            json.dumps(
                {"changes": normalized_changes, "source": normalized_source},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        with self._lock:
            root = self._load()
            receipt = root["idempotency"].get(receipt_key)
            if isinstance(receipt, dict) and receipt.get("kind") == "batch":
                # 幂等键必须绑定同一变更集；旧回执缺少指纹时也 fail closed，避免误报新值已保存。
                if not hmac.compare_digest(
                    str(receipt.get("requestFingerprint") or ""), request_fingerprint
                ):
                    raise PersonalAssetConflictError(
                        "idempotency key is already bound to different confirmed changes"
                    )
                return {
                    "idempotent": True,
                    "revision": int(receipt.get("revision") or root["revision"]),
                    "changeScope": copy.deepcopy(receipt.get("changeScope") or []),
                    "snapshot": self._public_snapshot(root),
                }
            self._expect_revision(root, expected_revision)
            working = copy.deepcopy(root)
            changed_entries: list[JsonDict] = []
            changed_scope: list[JsonDict] = []
            now = self._iso_now()
            for raw_change in changes:
                if not isinstance(raw_change, Mapping):
                    raise PersonalAssetValidationError("each confirmed change must be an object")
                action = _text(raw_change.get("action"), field="action", maximum=20).lower()
                if action == "create":
                    if len(working["entries"]) >= MAX_ENTRIES:
                        raise PersonalAssetValidationError("personal asset entry limit reached")
                    normalized = self._entry_payload(
                        raw_change.get("entry") if isinstance(raw_change.get("entry"), Mapping) else {}
                    )
                    entry = PersonalAssetEntry(
                        id=f"asset-{uuid.uuid4().hex}",
                        revision=1,
                        created_at=now,
                        updated_at=now,
                        **normalized,
                    ).to_dict()
                    working["entries"][entry["id"]] = entry
                    changed_entries.append(copy.deepcopy(entry))
                    changed_scope.append({"action": "create", "entryId": entry["id"]})
                elif action == "update":
                    entry_id = _text(raw_change.get("entryId"), field="entryId", maximum=160)
                    existing = working["entries"].get(entry_id)
                    if not isinstance(existing, dict):
                        raise PersonalAssetValidationError("personal asset entry was not found")
                    patch = raw_change.get("patch")
                    if not isinstance(patch, Mapping) or not patch:
                        raise PersonalAssetValidationError("entry patch must not be empty")
                    normalized = self._entry_payload(patch, existing=existing)
                    updated = {
                        **copy.deepcopy(existing),
                        **normalized,
                        "revision": int(existing.get("revision") or 0) + 1,
                        "updatedAt": now,
                    }
                    working["entries"][entry_id] = updated
                    changed_entries.append(copy.deepcopy(updated))
                    changed_scope.append({"action": "update", "entryId": entry_id})
                elif action == "delete":
                    entry_id = _text(raw_change.get("entryId"), field="entryId", maximum=160)
                    if not isinstance(working["entries"].pop(entry_id, None), dict):
                        raise PersonalAssetValidationError("personal asset entry was not found")
                    changed_scope.append({"action": "delete", "entryId": entry_id})
                else:
                    raise PersonalAssetValidationError("action must be create, update, or delete")
            # 全部变更先在副本验证，只有整批有效时才发布，避免建档确认出现半份资料。
            working["revision"] += 1
            working["idempotency"][receipt_key] = {
                "kind": "batch",
                "revision": working["revision"],
                "source": normalized_source,
                "entryIds": [item["id"] for item in changed_entries],
                "changeScope": copy.deepcopy(changed_scope),
                "requestFingerprint": request_fingerprint,
            }
            self._write(working)
            return {
                "idempotent": False,
                "entries": changed_entries,
                "changeScope": changed_scope,
                "revision": working["revision"],
                "snapshot": self._public_snapshot(working),
            }

    def put_access_link(self, request_id: object, payload: Mapping[str, object]) -> JsonDict:
        key = _text(request_id, field="requestId", maximum=240)
        if not isinstance(payload, Mapping):
            raise PersonalAssetValidationError("access link must be an object")
        entry_ids = payload.get("entryIds")
        if not isinstance(entry_ids, Sequence) or isinstance(entry_ids, (str, bytes)) or not entry_ids:
            raise PersonalAssetValidationError("entryIds must be a non-empty list")
        normalized_ids = tuple(_text(item, field="entryId", maximum=160) for item in entry_ids)
        link = PersonalAssetAccessLink(
            request_id=key,
            decision_id=_text(payload.get("decisionId"), field="decisionId", maximum=160),
            agent_id=_text(payload.get("agentId"), field="agentId", maximum=256),
            task_context=_task_context(payload.get("taskContext")),
            entry_ids=normalized_ids,
            expires_at=_text(payload.get("expiresAt"), field="expiresAt", maximum=80),
            consumed_at="",
        ).to_dict()
        with self._lock:
            root = self._load()
            existing = root["accessLinks"].get(key)
            if existing is not None:
                if existing != link:
                    raise PersonalAssetConflictError("access request is already linked differently")
                return copy.deepcopy(existing)
            root["accessLinks"][key] = link
            root["revision"] += 1
            self._write(root)
            return copy.deepcopy(link)

    def get_access_link(self, request_id: object) -> JsonDict | None:
        key = _text(request_id, field="requestId", maximum=240)
        with self._lock:
            value = self._load()["accessLinks"].get(key)
            return copy.deepcopy(value) if isinstance(value, dict) else None

    def _usage_record(
        self,
        *,
        request_id: object,
        agent_id: object,
        task_context: object,
        entry_ids: Sequence[object],
        outcome: object,
    ) -> JsonDict:
        return PersonalAssetUsageRecord(
            request_id=_text(request_id, field="requestId", maximum=240),
            agent_id=_text(agent_id, field="agentId", maximum=256),
            task_context=_task_context(task_context),
            entry_ids=tuple(_text(item, field="entryId", maximum=160) for item in entry_ids),
            outcome=_text(outcome, field="outcome", maximum=40),
            created_at=self._iso_now(),
        ).to_dict()

    def record_usage(
        self,
        *,
        request_id: object,
        agent_id: object,
        task_context: object,
        entry_ids: Sequence[object],
        outcome: object,
    ) -> JsonDict:
        record = self._usage_record(
            request_id=request_id,
            agent_id=agent_id,
            task_context=task_context,
            entry_ids=entry_ids,
            outcome=outcome,
        )
        with self._lock:
            root = self._load()
            if any(item.get("requestId") == record["requestId"] for item in root["usageRecords"] if isinstance(item, dict)):
                return {"created": False, "record": copy.deepcopy(record), "revision": root["revision"]}
            root["usageRecords"].append(record)
            root["usageRecords"] = root["usageRecords"][-self._usage_limit :]
            root["revision"] += 1
            self._write(root)
            return {"created": True, "record": copy.deepcopy(record), "revision": root["revision"]}

    def consume_access_and_record_usage(
        self, request_id: object, *, once: bool, outcome: object
    ) -> JsonDict:
        key = _text(request_id, field="requestId", maximum=240)
        with self._lock:
            root = self._load()
            link = root["accessLinks"].get(key)
            if not isinstance(link, dict):
                raise PersonalAssetValidationError("access request was not found")
            if once and link.get("consumedAt"):
                return {"consumed": False, "link": copy.deepcopy(link), "revision": root["revision"]}
            record = self._usage_record(
                request_id=key,
                agent_id=link.get("agentId"),
                task_context=link.get("taskContext"),
                entry_ids=link.get("entryIds") or [],
                outcome=outcome,
            )
            # 一次性授权的消费标记与使用记录必须同一原子提交，避免并发重复披露。
            if once:
                link["consumedAt"] = record["createdAt"]
            if not any(item.get("requestId") == key for item in root["usageRecords"] if isinstance(item, dict)):
                root["usageRecords"].append(record)
                root["usageRecords"] = root["usageRecords"][-self._usage_limit :]
            root["revision"] += 1
            self._write(root)
            return {"consumed": True, "link": copy.deepcopy(link), "record": copy.deepcopy(record), "revision": root["revision"]}
