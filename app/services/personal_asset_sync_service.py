"""Best-effort OSS snapshot orchestration for Personal Assets."""

from __future__ import annotations

import hashlib
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from .oss_storage import ObjectMetadata, ObjectRef, OssStorageError, OssStorageService
from .personal_asset_store import (
    PersonalAssetConflictError,
    PersonalAssetStore,
    PersonalAssetStoreError,
    PersonalAssetValidationError,
)
from .personal_asset_sync_state import (
    PersonalAssetSyncStateError,
    PersonalAssetSyncStateStore,
    PersonalAssetSyncStateValidationError,
)


OSS_INTEGRATION_ID = "personal-assets"
OBJECT_ID = "profile-snapshot.json"
CONTENT_TYPE = "application/json"
SNAPSHOT_SCHEMA_VERSION = 1
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
_LOGGER = logging.getLogger(__name__)


class PersonalAssetSyncError(RuntimeError):
    code = "personal_asset_sync_failed"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class PersonalAssetSyncSnapshotError(PersonalAssetSyncError):
    code = "personal_asset_sync_snapshot_invalid"


class _LimitedBytesSink(io.BytesIO):
    def __init__(self, limit: int):
        super().__init__()
        self._limit = limit

    def write(self, value):
        if self.tell() + len(value) > self._limit:
            raise PersonalAssetSyncSnapshotError("remote snapshot is too large")
        return super().write(value)


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PersonalAssetSyncSnapshotError("snapshot contains invalid JSON") from exc


def _semantic_payload(profile: Mapping[str, object]) -> dict[str, object]:
    entries = profile.get("entries")
    suggestions = profile.get("suggestions")
    if not isinstance(entries, list) or not isinstance(suggestions, list):
        raise PersonalAssetSyncSnapshotError("profile collections are invalid")
    return {"entries": entries, "suggestions": suggestions}


def _fingerprint(profile: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical(_semantic_payload(profile))).hexdigest()


def _is_empty(profile: Mapping[str, object]) -> bool:
    return not profile.get("entries") and not profile.get("suggestions")


def _metadata_version(metadata: ObjectMetadata) -> str:
    if metadata.etag:
        return str(metadata.etag)
    modified = metadata.last_modified
    if isinstance(modified, datetime):
        modified = modified.isoformat()
    return f"size:{metadata.size}:modified:{modified or ''}"


class PersonalAssetSyncService:
    """Coordinates snapshots while keeping every OSS action off the local write path."""

    def __init__(
        self,
        profile_store: PersonalAssetStore,
        state_store: PersonalAssetSyncStateStore,
        storage: OssStorageService,
        *,
        now: Callable[[], datetime] | None = None,
    ):
        self.profile_store = profile_store
        self.state_store = state_store
        self.storage = storage
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._wake: Callable[[], None] = lambda: None
        self._ref = ObjectRef.for_scope(OSS_INTEGRATION_ID, OBJECT_ID)

    def set_waker(self, wake: Callable[[], None]) -> None:
        if not callable(wake):
            raise TypeError("wake must be callable")
        self._wake = wake

    def _public_state(self, state: Mapping[str, object]) -> dict[str, object]:
        return {
            "enabled": bool(state.get("enabled")),
            "status": str(state.get("status") or "idle"),
            "operation": str(state.get("operation") or ""),
            "pendingRevision": int(state.get("pendingRevision") or 0),
            "syncedRevision": int(state.get("syncedRevision") or 0),
            "lastSyncedAt": str(state.get("lastSyncedAt") or ""),
            "retryAt": str(state.get("retryAt") or ""),
            "attempt": int(state.get("attempt") or 0),
            "lastErrorCode": str(state.get("lastErrorCode") or ""),
            "hasConflict": state.get("status") == "conflict",
            "objectRef": self._ref.to_string(),
        }

    def status(self) -> dict[str, object]:
        try:
            return self._public_state(self.state_store.snapshot())
        except PersonalAssetSyncStateError:
            return {
                "enabled": True,
                "status": "failed",
                "operation": "",
                "pendingRevision": 0,
                "syncedRevision": 0,
                "lastSyncedAt": "",
                "retryAt": "",
                "attempt": 0,
                "lastErrorCode": "personal_asset_sync_state_unavailable",
                "hasConflict": False,
                "objectRef": self._ref.to_string(),
            }

    def on_profile_mutation(self, profile: Mapping[str, object]) -> None:
        try:
            state = self.state_store.snapshot()
            if not state["enabled"]:
                return
            revision = profile.get("revision")
            self.state_store.mark_pending(revision)
            self._wake()
        except Exception as exc:
            _LOGGER.warning(
                "Personal Assets sync enqueue failed code=%s",
                str(getattr(exc, "code", "personal_asset_sync_enqueue_failed")),
            )

    def set_enabled(self, enabled: object) -> dict[str, object]:
        state = self.state_store.set_enabled(enabled)
        if state["enabled"]:
            state = self.state_store.mark_pending(self.profile_store.snapshot()["revision"])
            self._wake()
        return self._public_state(state)

    def request_sync(self) -> dict[str, object]:
        state = self.state_store.snapshot()
        if state["enabled"]:
            state = self.state_store.mark_pending(self.profile_store.snapshot()["revision"])
            self._wake()
        return self._public_state(state)

    def resolve_conflict(self, resolution: object) -> dict[str, object]:
        state = self.state_store.snapshot()
        if state["status"] != "conflict":
            raise PersonalAssetSyncStateValidationError("no sync conflict is pending")
        state = self.state_store.set_resolution(resolution)
        self._wake()
        return self._public_state(state)

    def _envelope(self, profile: Mapping[str, object], state: Mapping[str, object]) -> bytes:
        revision = profile.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise PersonalAssetSyncSnapshotError("profile revision is invalid")
        payload = {
            "revision": revision,
            **_semantic_payload(profile),
        }
        envelope: dict[str, object] = {
            "schemaVersion": SNAPSHOT_SCHEMA_VERSION,
            "originId": state["originId"],
            "updatedAt": self._now().astimezone(timezone.utc).isoformat(),
            "localRevision": revision,
            "baseEtag": state.get("baseEtag") or "",
            "profileFingerprint": _fingerprint(profile),
            "payload": payload,
        }
        envelope["checksum"] = hashlib.sha256(_canonical(envelope)).hexdigest()
        value = _canonical(envelope)
        if len(value) > MAX_SNAPSHOT_BYTES:
            raise PersonalAssetSyncSnapshotError("snapshot is too large")
        return value

    def _read_remote(self) -> tuple[dict[str, object], ObjectMetadata]:
        sink = _LimitedBytesSink(MAX_SNAPSHOT_BYTES)
        metadata = self.storage.restore_to(OSS_INTEGRATION_ID, self._ref, sink)
        try:
            envelope = json.loads(sink.getvalue())
        except json.JSONDecodeError as exc:
            raise PersonalAssetSyncSnapshotError("remote snapshot is invalid JSON") from exc
        if not isinstance(envelope, dict) or envelope.get("schemaVersion") != SNAPSHOT_SCHEMA_VERSION:
            raise PersonalAssetSyncSnapshotError("remote snapshot schema is invalid")
        checksum = envelope.get("checksum")
        unsigned = {key: value for key, value in envelope.items() if key != "checksum"}
        expected_checksum = hashlib.sha256(_canonical(unsigned)).hexdigest()
        if not isinstance(checksum, str) or checksum != expected_checksum:
            raise PersonalAssetSyncSnapshotError("remote snapshot checksum is invalid")
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            raise PersonalAssetSyncSnapshotError("remote snapshot payload is invalid")
        fingerprint = envelope.get("profileFingerprint")
        if not isinstance(fingerprint, str) or fingerprint != _fingerprint(payload):
            raise PersonalAssetSyncSnapshotError("remote snapshot fingerprint is invalid")
        return envelope, metadata

    def _upload(
        self, profile: Mapping[str, object], state: Mapping[str, object]
    ) -> dict[str, object]:
        self.state_store.mark_syncing("upload")
        metadata = self.storage.save(
            OSS_INTEGRATION_ID,
            OBJECT_ID,
            io.BytesIO(self._envelope(profile, state)),
            content_type=CONTENT_TYPE,
        )
        synced = self.state_store.mark_synced(
            revision=profile["revision"],
            fingerprint=_fingerprint(profile),
            etag=_metadata_version(metadata),
        )
        return self._public_state(synced)

    def _restore(
        self, current_profile: Mapping[str, object]
    ) -> dict[str, object]:
        self.state_store.mark_syncing("restore")
        envelope, metadata = self._read_remote()
        restored = self.profile_store.restore_profile_snapshot(
            envelope["payload"], expected_revision=current_profile["revision"]
        )
        profile = restored["snapshot"]
        synced = self.state_store.mark_synced(
            revision=profile["revision"],
            fingerprint=_fingerprint(profile),
            etag=_metadata_version(metadata),
        )
        return self._public_state(synced)

    def _run_once(self) -> dict[str, object]:
        state = self.state_store.snapshot()
        if not state["enabled"]:
            return self._public_state(state)
        if state["status"] == "failed" and state.get("retryAt"):
            try:
                retry_at = datetime.fromisoformat(str(state["retryAt"]))
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                if self._now().astimezone(timezone.utc) < retry_at.astimezone(timezone.utc):
                    return self._public_state(state)
            except ValueError:
                # A malformed timestamp must not permanently stall a recoverable sync.
                pass
        profile = self.profile_store.snapshot()
        local_fingerprint = _fingerprint(profile)
        remote_exists = self.storage.exists(OSS_INTEGRATION_ID, self._ref)
        if not remote_exists:
            if _is_empty(profile):
                synced = self.state_store.mark_synced(
                    revision=profile["revision"],
                    fingerprint=local_fingerprint,
                    etag="",
                )
                return self._public_state(synced)
            return self._upload(profile, state)

        metadata = self.storage.metadata(OSS_INTEGRATION_ID, self._ref)
        remote_version = _metadata_version(metadata)
        resolution = state.get("resolution") or ""
        if resolution == "local":
            return self._upload(profile, state)
        if resolution == "remote" or _is_empty(profile):
            return self._restore(profile)

        base_version = str(state.get("baseEtag") or "")
        synced_fingerprint = str(state.get("syncedFingerprint") or "")
        if base_version:
            local_changed = local_fingerprint != synced_fingerprint
            remote_changed = remote_version != base_version
            if local_changed and remote_changed:
                conflict = self.state_store.mark_conflict(remote_etag=remote_version)
                return self._public_state(conflict)
            if remote_changed:
                return self._restore(profile)
            if local_changed:
                return self._upload(profile, state)
            synced = self.state_store.mark_synced(
                revision=profile["revision"],
                fingerprint=local_fingerprint,
                etag=remote_version,
            )
            return self._public_state(synced)

        envelope, _remote_metadata = self._read_remote()
        remote_fingerprint = str(envelope.get("profileFingerprint") or "")
        if remote_fingerprint == local_fingerprint:
            synced = self.state_store.mark_synced(
                revision=profile["revision"],
                fingerprint=local_fingerprint,
                etag=remote_version,
            )
            return self._public_state(synced)
        conflict = self.state_store.mark_conflict(remote_etag=remote_version)
        return self._public_state(conflict)

    def run_once(self) -> dict[str, object]:
        try:
            return self._run_once()
        except Exception as exc:
            if isinstance(exc, PersonalAssetSyncSnapshotError):
                code = exc.code
            elif isinstance(exc, OssStorageError):
                code = exc.code
            elif isinstance(
                exc,
                (
                    PersonalAssetValidationError,
                    PersonalAssetConflictError,
                    PersonalAssetStoreError,
                ),
            ):
                code = "personal_asset_sync_snapshot_invalid"
            else:
                code = str(getattr(exc, "code", "personal_asset_sync_failed"))
            try:
                attempt = int(self.state_store.snapshot().get("attempt") or 0)
                seconds = min(300, 2 ** min(attempt, 8))
                retry_at = (
                    self._now().astimezone(timezone.utc) + timedelta(seconds=seconds)
                ).isoformat()
                failed = self.state_store.mark_failed(code, retry_at=retry_at)
                return self._public_state(failed)
            except PersonalAssetSyncStateError:
                _LOGGER.warning("Personal Assets sync failed code=%s", code)
                return self.status()
