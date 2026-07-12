"""Single authoritative JSON repository for Meeting-domain state."""

from __future__ import annotations

import copy
import errno
import fcntl
import hashlib
import json
import os
import stat
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


SCHEMA_VERSION = 1
UNIFIED_FILENAME = "meeting-domain.json"
LEGACY_EXECUTABLE_FILENAME = "executable-meetings.json"
LEGACY_REQUEST_FILENAME = "meeting-requests.json"
TERMINAL_PHASES = frozenset({"completed", "cancelled", "failed"})
MEETING_PHASES = frozenset({
    "draft", "conflict", "preparing", "active_opening", "active_discussion", "paused",
    "awaiting_user_decision", "summarizing", "completed", "cancelled", "failed",
})
REQUEST_STATUSES = frozenset({"pending", "rejected", "confirmed"})
MAX_STORE_BYTES = 64 * 1024 * 1024
MAX_DOMAIN_RECORDS = 100_000
ACTIVE_LOCK_FILENAME = "meeting-store-active.lock"


class MeetingStoreError(RuntimeError):
    def __init__(self, message: str, *, code: str, status: int = 409):
        super().__init__(message)
        self.code = code
        self.status = status


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def empty_store() -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "meetings": {}, "events": {}, "occupancy": {}, "requests": {},
        "idempotency": {"meetings": {}, "requests": {}, "callbacks": {}, "actionItems": {}},
        "migration": {"sourceDigest": "", "migratedAt": "", "reportFile": ""},
        "updatedAt": "",
    }


def normalize_store(value: Any, *, strict: bool = True) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MeetingStoreError("Meeting store must be a JSON object", code="meeting_store_invalid")
    version = value.get("schemaVersion")
    if version != SCHEMA_VERSION:
        code = "meeting_store_version_unsupported" if version is not None else "meeting_store_invalid"
        raise MeetingStoreError("Unsupported Meeting store schema version", code=code)
    try:
        result = copy.deepcopy(value)
    except (RecursionError, MemoryError) as exc:
        raise MeetingStoreError("Meeting store structure is invalid", code="meeting_store_invalid") from exc
    for key in ("meetings", "events", "occupancy", "requests"):
        if not isinstance(result.get(key), dict):
            raise MeetingStoreError(f"Meeting store field {key} must be an object", code="meeting_store_invalid")
    idempotency = result.get("idempotency")
    if not isinstance(idempotency, dict):
        raise MeetingStoreError("Meeting store idempotency must be an object", code="meeting_store_invalid")
    for namespace in ("meetings", "requests", "callbacks", "actionItems"):
        current = idempotency.get(namespace, {})
        if not isinstance(current, dict):
            raise MeetingStoreError("Invalid Meeting idempotency namespace", code="meeting_store_invalid")
        idempotency[namespace] = current
    migration = result.get("migration", {})
    if not isinstance(migration, dict):
        raise MeetingStoreError("Meeting migration metadata must be an object", code="meeting_store_invalid")
    result["migration"] = {
        "sourceDigest": str(migration.get("sourceDigest") or ""),
        "migratedAt": str(migration.get("migratedAt") or ""),
        "reportFile": str(migration.get("reportFile") or ""),
    }
    result["updatedAt"] = str(result.get("updatedAt") or "")
    total_records = sum(len(result[key]) for key in ("meetings", "events", "occupancy", "requests"))
    total_records += sum(len(values) for values in idempotency.values())
    if total_records > MAX_DOMAIN_RECORDS:
        raise MeetingStoreError("Meeting store exceeds record limits", code="meeting_store_too_large", status=413)
    if strict:
        validate_relationships(result)
    return result


def validate_relationships(data: Mapping[str, Any]) -> None:
    meetings = data["meetings"]
    requests = data["requests"]
    for meeting_id, meeting in meetings.items():
        if not isinstance(meeting, dict) or str(meeting.get("id") or meeting_id) != str(meeting_id):
            raise MeetingStoreError("Meeting identity conflict", code="meeting_store_conflict")
        phase = str(meeting.get("stage") or meeting.get("phase") or "draft")
        if phase not in MEETING_PHASES:
            raise MeetingStoreError("Unsupported Meeting phase", code="meeting_store_conflict")
        if not isinstance(meeting.get("participants", []), list):
            raise MeetingStoreError("Meeting participants must be a list", code="meeting_store_conflict")
    for request_id, request in requests.items():
        if not isinstance(request, dict) or str(request.get("id") or request_id) != str(request_id):
            raise MeetingStoreError("Meeting request identity conflict", code="meeting_store_conflict")
        status_value = str(request.get("status") or "pending")
        if status_value not in REQUEST_STATUSES:
            raise MeetingStoreError("Unsupported Meeting request status", code="meeting_store_conflict")
        conversion = request.get("conversion") or {}
        if not isinstance(conversion, dict):
            raise MeetingStoreError("Meeting request conversion must be an object", code="meeting_store_conflict")
        linked = str(conversion.get("meetingId") or "")
        if linked and linked not in meetings:
            raise MeetingStoreError("Meeting request references a missing Meeting", code="meeting_store_conflict")
    owners: dict[str, str] = {}
    for agent_id, meeting_id in data["occupancy"].items():
        meeting = meetings.get(meeting_id)
        if not isinstance(meeting, dict):
            raise MeetingStoreError("Occupancy references a missing Meeting", code="meeting_store_conflict")
        phase = str(meeting.get("stage") or meeting.get("phase") or "draft")
        if phase in TERMINAL_PHASES or agent_id not in (meeting.get("participants") or []):
            raise MeetingStoreError("Occupancy is incompatible with Meeting state", code="meeting_store_conflict")
        if agent_id in owners and owners[agent_id] != meeting_id:
            raise MeetingStoreError("Agent has conflicting Meeting owners", code="meeting_store_conflict")
        owners[agent_id] = meeting_id
    for meeting_id, events in data["events"].items():
        if meeting_id not in meetings or not isinstance(events, list):
            raise MeetingStoreError("Meeting events have invalid ownership", code="meeting_store_conflict")


def _legacy_has_data(path: Path, data_keys: tuple[str, ...]) -> bool:
    if not path.exists():
        return False
    try:
        content = read_regular_no_follow(path)
        if not content:
            return False
        value = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, MeetingStoreError, RecursionError):
        return True
    return not isinstance(value, dict) or any(bool(value.get(key)) for key in data_keys)


class MeetingDomainRepository:
    def __init__(self, status_dir: str | os.PathLike[str]):
        self.status_dir = Path(status_dir).expanduser().resolve()
        self.path = self.status_dir / UNIFIED_FILENAME
        self._lock = threading.RLock()
        self._cache: dict[str, Any] | None = None
        self._cache_key: tuple[int, int, int, int] | None = None

    def _metadata(self) -> tuple[int, int, int, int] | None:
        try:
            value = self.path.stat()
            return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns
        except FileNotFoundError:
            return None

    def authority_state(self) -> str:
        if self.path.exists():
            try:
                self.snapshot()
                return "unified"
            except MeetingStoreError:
                return "invalid"
        executable = self.status_dir / LEGACY_EXECUTABLE_FILENAME
        requests = self.status_dir / LEGACY_REQUEST_FILENAME
        if _legacy_has_data(executable, ("meetings", "events", "occupancy", "idempotency")) or _legacy_has_data(
            requests, ("requests", "idempotency"),
        ):
            return "migration_required"
        return "empty"

    def _read_disk(self) -> dict[str, Any]:
        try:
            raw = json.loads(read_regular_no_follow(self.path).decode("utf-8"))
        except FileNotFoundError:
            if _legacy_has_data(self.status_dir / LEGACY_EXECUTABLE_FILENAME, ("meetings", "events", "occupancy", "idempotency")) or _legacy_has_data(
                self.status_dir / LEGACY_REQUEST_FILENAME, ("requests", "idempotency"),
            ):
                raise MeetingStoreError("Meeting store migration is required", code="meeting_store_migration_required")
            return empty_store()
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
            raise MeetingStoreError("Meeting store is invalid", code="meeting_store_invalid", status=500) from exc
        return normalize_store(raw, strict=True)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            metadata = self._metadata()
            if self._cache is None or metadata != self._cache_key:
                self._cache = self._read_disk()
                self._cache_key = metadata
            return copy.deepcopy(self._cache)

    def update(self, mutator: Callable[[dict[str, Any]], Any]) -> tuple[dict[str, Any], Any]:
        with self._lock:
            data = self._read_disk()
            result = mutator(data)
            data["updatedAt"] = now_iso()
            validated = normalize_store(data, strict=True)
            self._write_atomic(validated)
            self._cache = copy.deepcopy(validated)
            self._cache_key = self._metadata()
            return copy.deepcopy(validated), copy.deepcopy(result)

    def _write_atomic(self, data: Mapping[str, Any]) -> None:
        self.status_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp-{os.getpid()}-{threading.get_ident()}")
        descriptor = None
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                descriptor = None
                json.dump(data, stream, indent=2, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600, follow_symlinks=False)
            candidate = json.loads(read_regular_no_follow(temporary).decode("utf-8"))
            normalize_store(candidate, strict=True)
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600, follow_symlinks=False)
            try:
                directory_fd = os.open(self.status_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError as exc:
                unsupported = {errno.EINVAL, errno.EBADF}
                for name in ("ENOTSUP", "EOPNOTSUPP"):
                    value = getattr(errno, name, None)
                    if value is not None:
                        unsupported.add(value)
                if exc.errno not in unsupported:
                    raise
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def executable_view(self) -> dict[str, Any]:
        data = self.snapshot()
        return {
            "meetings": data["meetings"], "events": data["events"], "occupancy": data["occupancy"],
            "idempotency": data["idempotency"]["meetings"], "updatedAt": data["updatedAt"],
        }

    def replace_executable(self, legacy: Mapping[str, Any]) -> None:
        def mutate(data):
            for key in ("meetings", "events", "occupancy"):
                data[key] = copy.deepcopy(legacy.get(key) if isinstance(legacy.get(key), dict) else {})
            data["idempotency"]["meetings"] = copy.deepcopy(
                legacy.get("idempotency") if isinstance(legacy.get("idempotency"), dict) else {},
            )
        self.update(mutate)

    def request_view(self) -> dict[str, Any]:
        data = self.snapshot()
        return {
            "requests": data["requests"], "idempotency": data["idempotency"]["requests"],
            "updatedAt": data["updatedAt"],
        }

    def replace_requests(self, legacy: Mapping[str, Any]) -> None:
        def mutate(data):
            data["requests"] = copy.deepcopy(legacy.get("requests") if isinstance(legacy.get("requests"), dict) else {})
            data["idempotency"]["requests"] = copy.deepcopy(
                legacy.get("idempotency") if isinstance(legacy.get("idempotency"), dict) else {},
            )
        self.update(mutate)


def source_digest(executable_bytes: bytes, request_bytes: bytes) -> str:
    digest = hashlib.sha256()
    for label, content in ((b"executable\0", executable_bytes), (b"requests\0", request_bytes)):
        digest.update(label); digest.update(len(content).to_bytes(8, "big")); digest.update(content)
    return digest.hexdigest()


def merge_legacy(executable: Mapping[str, Any], requests: Mapping[str, Any], *, digest: str = "") -> dict[str, Any]:
    data = empty_store()
    for key in ("meetings", "events", "occupancy"):
        value = executable.get(key, {})
        if not isinstance(value, dict):
            raise MeetingStoreError(f"Invalid legacy executable field {key}", code="meeting_store_conflict")
        data[key] = copy.deepcopy(value)
    request_values = requests.get("requests", {})
    if not isinstance(request_values, dict):
        raise MeetingStoreError("Invalid legacy requests", code="meeting_store_conflict")
    data["requests"] = copy.deepcopy(request_values)
    for source, namespace in ((executable, "meetings"), (requests, "requests")):
        values = source.get("idempotency", {})
        if not isinstance(values, dict):
            raise MeetingStoreError("Invalid legacy idempotency", code="meeting_store_conflict")
        data["idempotency"][namespace] = copy.deepcopy(values)
    data["migration"] = {"sourceDigest": digest, "migratedAt": now_iso(), "reportFile": ""}
    data["updatedAt"] = max(str(executable.get("updatedAt") or ""), str(requests.get("updatedAt") or ""))
    return normalize_store(data)


def read_regular_no_follow(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise MeetingStoreError("Migration input is not a regular file", code="meeting_store_migration_input_invalid")
        if metadata.st_size > MAX_STORE_BYTES:
            raise MeetingStoreError("Meeting store exceeds byte limit", code="meeting_store_too_large", status=413)
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            content = stream.read(MAX_STORE_BYTES + 1)
        if len(content) > MAX_STORE_BYTES:
            raise MeetingStoreError("Meeting store exceeds byte limit", code="meeting_store_too_large", status=413)
        return content
    finally:
        os.close(descriptor)


def acquire_active_lock(status_dir: str | os.PathLike[str], *, blocking: bool = False) -> int:
    directory = Path(status_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ACTIVE_LOCK_FILENAME
    descriptor = os.open(
        path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise MeetingStoreError("Meeting active lock is unsafe", code="meeting_store_lock_invalid")
        operation = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        fcntl.flock(descriptor, operation)
        os.ftruncate(descriptor, 0)
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o600)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise
