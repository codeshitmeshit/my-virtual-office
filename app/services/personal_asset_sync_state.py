"""Atomic, non-secret state for best-effort Personal Assets OSS sync."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


SCHEMA_VERSION = 1
SYNC_STATUSES = frozenset(
    {"idle", "pending", "syncing", "restoring", "synced", "failed", "conflict"}
)
SYNC_OPERATIONS = frozenset({"", "upload", "restore"})
SYNC_RESOLUTIONS = frozenset({"", "local", "remote"})
_PATH_LOCKS: dict[str, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


class PersonalAssetSyncStateError(RuntimeError):
    code = "personal_asset_sync_state_unavailable"


class PersonalAssetSyncStateValidationError(PersonalAssetSyncStateError, ValueError):
    code = "personal_asset_sync_state_invalid"


def _lock_for(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


def _safe_text(value: object, *, field: str, maximum: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) > maximum or any(ord(character) < 32 for character in text):
        raise PersonalAssetSyncStateValidationError(f"{field} is invalid")
    return text


class PersonalAssetSyncStateStore:
    """Owns local synchronization metadata; profile values never enter this file."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        now: Callable[[], datetime] | None = None,
    ):
        self.path = Path(path)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._lock = _lock_for(self.path)

    def _iso_now(self) -> str:
        return self._now().astimezone(timezone.utc).isoformat()

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "enabled": True,
            "status": "idle",
            "operation": "",
            "pendingRevision": 0,
            "syncedRevision": 0,
            "syncedFingerprint": "",
            "baseEtag": "",
            "remoteEtag": "",
            "lastSyncedAt": "",
            "retryAt": "",
            "attempt": 0,
            "lastErrorCode": "",
            "originId": f"vo-{uuid.uuid4().hex}",
            "resolution": "",
        }

    @staticmethod
    def _validated(root: object) -> dict[str, Any]:
        if not isinstance(root, Mapping) or root.get("schemaVersion") != SCHEMA_VERSION:
            raise PersonalAssetSyncStateValidationError("sync state schema is invalid")
        enabled = root.get("enabled")
        if not isinstance(enabled, bool):
            raise PersonalAssetSyncStateValidationError("enabled must be a boolean")
        status = _safe_text(root.get("status"), field="status", maximum=24)
        operation = _safe_text(root.get("operation"), field="operation", maximum=24)
        resolution = _safe_text(root.get("resolution"), field="resolution", maximum=24)
        if status not in SYNC_STATUSES or operation not in SYNC_OPERATIONS:
            raise PersonalAssetSyncStateValidationError("sync state status is invalid")
        if resolution not in SYNC_RESOLUTIONS:
            raise PersonalAssetSyncStateValidationError("sync resolution is invalid")
        integers: dict[str, int] = {}
        for field in ("pendingRevision", "syncedRevision", "attempt"):
            value = root.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise PersonalAssetSyncStateValidationError(f"{field} is invalid")
            integers[field] = value
        return {
            "schemaVersion": SCHEMA_VERSION,
            "enabled": enabled,
            "status": status,
            "operation": operation,
            **integers,
            "syncedFingerprint": _safe_text(
                root.get("syncedFingerprint"), field="syncedFingerprint", maximum=64
            ),
            "baseEtag": _safe_text(root.get("baseEtag"), field="baseEtag"),
            "remoteEtag": _safe_text(root.get("remoteEtag"), field="remoteEtag"),
            "lastSyncedAt": _safe_text(
                root.get("lastSyncedAt"), field="lastSyncedAt"
            ),
            "retryAt": _safe_text(root.get("retryAt"), field="retryAt"),
            "lastErrorCode": _safe_text(
                root.get("lastErrorCode"), field="lastErrorCode", maximum=96
            ),
            "originId": _safe_text(root.get("originId"), field="originId", maximum=96),
            "resolution": resolution,
        }

    def _load(self) -> dict[str, Any]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            root = self._empty()
            self._write(root)
            return root
        except OSError as exc:
            raise PersonalAssetSyncStateError("sync state could not be read") from exc
        try:
            return self._validated(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise PersonalAssetSyncStateValidationError("sync state is invalid JSON") from exc

    def _write(self, root: Mapping[str, object]) -> None:
        value = self._validated(root)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        except Exception as exc:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise PersonalAssetSyncStateError("sync state could not be written") from exc

    def _update(self, **changes: object) -> dict[str, Any]:
        with self._lock:
            root = self._load()
            root.update(changes)
            self._write(root)
            return copy.deepcopy(root)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._load())

    def set_enabled(self, enabled: object) -> dict[str, Any]:
        if not isinstance(enabled, bool):
            raise PersonalAssetSyncStateValidationError("enabled must be a boolean")
        changes: dict[str, object] = {"enabled": enabled}
        if not enabled:
            changes.update(status="idle", operation="", retryAt="")
        return self._update(**changes)

    def mark_pending(self, revision: object) -> dict[str, Any]:
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise PersonalAssetSyncStateValidationError("revision is invalid")
        return self._update(
            status="pending",
            operation="",
            pendingRevision=revision,
            remoteEtag="",
            retryAt="",
            lastErrorCode="",
            resolution="",
        )

    def mark_syncing(self, operation: object) -> dict[str, Any]:
        value = _safe_text(operation, field="operation", maximum=24)
        if value not in {"upload", "restore"}:
            raise PersonalAssetSyncStateValidationError("operation is invalid")
        return self._update(status="syncing" if value == "upload" else "restoring", operation=value)

    def mark_synced(
        self,
        *,
        revision: object,
        fingerprint: object,
        etag: object,
    ) -> dict[str, Any]:
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise PersonalAssetSyncStateValidationError("revision is invalid")
        checked_fingerprint = _safe_text(
            fingerprint, field="fingerprint", maximum=64
        )
        if len(checked_fingerprint) != 64:
            raise PersonalAssetSyncStateValidationError("fingerprint is invalid")
        checked_etag = _safe_text(etag, field="etag")
        with self._lock:
            root = self._load()
            newer_revision_pending = int(root["pendingRevision"]) > revision
            root.update(
                status="pending" if newer_revision_pending else "synced",
                operation="",
                pendingRevision=root["pendingRevision"] if newer_revision_pending else 0,
                syncedRevision=revision,
                syncedFingerprint=checked_fingerprint,
                baseEtag=checked_etag,
                remoteEtag="",
                lastSyncedAt=self._iso_now(),
                retryAt="",
                attempt=0,
                lastErrorCode="",
                resolution="",
            )
            self._write(root)
            return copy.deepcopy(root)

    def mark_failed(self, error_code: object, *, retry_at: object) -> dict[str, Any]:
        code = _safe_text(error_code, field="errorCode", maximum=96)
        if not code:
            code = "personal_asset_sync_failed"
        with self._lock:
            root = self._load()
            root.update(
                status="failed",
                operation="",
                retryAt=_safe_text(retry_at, field="retryAt"),
                attempt=int(root["attempt"]) + 1,
                lastErrorCode=code,
            )
            self._write(root)
            return copy.deepcopy(root)

    def mark_conflict(self, *, remote_etag: object) -> dict[str, Any]:
        return self._update(
            status="conflict",
            operation="",
            remoteEtag=_safe_text(remote_etag, field="remoteEtag"),
            retryAt="",
            lastErrorCode="",
            resolution="",
        )

    def set_resolution(self, resolution: object) -> dict[str, Any]:
        value = _safe_text(resolution, field="resolution", maximum=24)
        if value not in {"local", "remote"}:
            raise PersonalAssetSyncStateValidationError("resolution must be local or remote")
        return self._update(status="pending", resolution=value, retryAt="", lastErrorCode="")
