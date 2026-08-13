"""SQLite authority for Meeting-domain state and offline legacy import."""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import stat
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .sqlite_runtime import connect_sqlite


SCHEMA_VERSION = 1
DATABASE_FILENAME = "meeting-domain.sqlite3"
UNIFIED_FILENAME = DATABASE_FILENAME
LEGACY_UNIFIED_FILENAME = "meeting-domain.json"
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
        self.legacy_unified_path = self.status_dir / LEGACY_UNIFIED_FILENAME
        self._lock = threading.RLock()
        self._initialized = False
    def _legacy_data_exists(self) -> bool:
        if self.legacy_unified_path.exists():
            return True
        executable = self.status_dir / LEGACY_EXECUTABLE_FILENAME
        requests = self.status_dir / LEGACY_REQUEST_FILENAME
        return _legacy_has_data(executable, ("meetings", "events", "occupancy", "idempotency")) or _legacy_has_data(
            requests, ("requests", "idempotency"),
        )

    def authority_state(self) -> str:
        if self.path.exists():
            try:
                connection = connect_sqlite(self.path, readonly=True)
                try:
                    version = connection.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
                    if not version or int(version[0]) != SCHEMA_VERSION:
                        return "invalid"
                    quick_check = connection.execute("PRAGMA quick_check(1)").fetchone()
                    if not quick_check or quick_check[0] != "ok":
                        return "invalid"
                finally:
                    connection.close()
                return "unified"
            except (MeetingStoreError, OSError, sqlite3.DatabaseError, TypeError, ValueError):
                return "invalid"
        if self.legacy_unified_path.exists():
            try:
                normalize_store(json.loads(read_regular_no_follow(self.legacy_unified_path).decode("utf-8")), strict=True)
            except (MeetingStoreError, OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError):
                return "invalid"
            return "migration_required"
        if self._legacy_data_exists():
            return "migration_required"
        return "empty"

    def initialize_empty(self) -> None:
        if self._legacy_data_exists():
            raise MeetingStoreError("Meeting store migration is required", code="meeting_store_migration_required")
        self._initialize()

    def validate_database(self) -> None:
        """Validate the SQLite authority without exposing a full runtime store view."""
        data = self.export_for_migration()
        normalize_store(data, strict=True)

    def ready(self) -> bool:
        """Cheap hot-path readiness check; startup owns full authority validation."""
        return self._initialized and self.path.exists()

    def export_for_migration(self) -> dict[str, Any]:
        """Read all domain rows for migration verification and offline tooling only."""
        return self._read_disk()

    def _initialize(self) -> None:
        if self._initialized and self.path.exists():
            return
        connection = connect_sqlite(self.path)
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS meetings (id TEXT PRIMARY KEY, payload_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS meeting_events (
                    meeting_id TEXT NOT NULL, position INTEGER NOT NULL, payload_json TEXT NOT NULL,
                    PRIMARY KEY(meeting_id, position),
                    FOREIGN KEY(meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS meeting_event_streams (
                    meeting_id TEXT PRIMARY KEY,
                    FOREIGN KEY(meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS meeting_requests (id TEXT PRIMARY KEY, payload_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS occupancy (
                    agent_id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL,
                    FOREIGN KEY(meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS idempotency (
                    namespace TEXT NOT NULL, item_key TEXT NOT NULL, payload_json TEXT NOT NULL,
                    PRIMARY KEY(namespace, item_key)
                );
                CREATE INDEX IF NOT EXISTS meeting_events_owner_idx ON meeting_events(meeting_id, position);
                CREATE INDEX IF NOT EXISTS meeting_requests_status_idx
                    ON meeting_requests(json_extract(payload_json, '$.status'));
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO metadata(key,value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            self._initialized = True
        finally:
            connection.close()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _decoded(value: str) -> Any:
        return json.loads(value)

    def _read_disk(self) -> dict[str, Any]:
        if not self.path.exists():
            if self.legacy_unified_path.exists():
                try:
                    normalize_store(json.loads(read_regular_no_follow(self.legacy_unified_path).decode("utf-8")), strict=True)
                except MeetingStoreError:
                    raise
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
                    raise MeetingStoreError("Meeting store is invalid", code="meeting_store_invalid", status=500) from exc
                raise MeetingStoreError("Meeting store migration is required", code="meeting_store_migration_required")
            if self._legacy_data_exists():
                raise MeetingStoreError("Meeting store migration is required", code="meeting_store_migration_required")
            return empty_store()
        try:
            connection = connect_sqlite(self.path, readonly=True)
            try:
                version = connection.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
                if not version or int(version[0]) != SCHEMA_VERSION:
                    raise MeetingStoreError("Unsupported Meeting store schema version", code="meeting_store_version_unsupported")
                data = empty_store()
                for row in connection.execute("SELECT id,payload_json FROM meetings"):
                    data["meetings"][str(row["id"])] = self._decoded(row["payload_json"])
                for row in connection.execute("SELECT meeting_id FROM meeting_event_streams"):
                    data["events"][str(row["meeting_id"])] = []
                for row in connection.execute("SELECT meeting_id,payload_json FROM meeting_events ORDER BY meeting_id,position"):
                    data["events"].setdefault(str(row["meeting_id"]), []).append(self._decoded(row["payload_json"]))
                for row in connection.execute("SELECT id,payload_json FROM meeting_requests"):
                    data["requests"][str(row["id"])] = self._decoded(row["payload_json"])
                for row in connection.execute("SELECT agent_id,meeting_id FROM occupancy"):
                    data["occupancy"][str(row["agent_id"])] = str(row["meeting_id"])
                for row in connection.execute("SELECT namespace,item_key,payload_json FROM idempotency"):
                    data["idempotency"].setdefault(str(row["namespace"]), {})[str(row["item_key"])] = self._decoded(row["payload_json"])
                metadata = {str(row["key"]): str(row["value"]) for row in connection.execute("SELECT key,value FROM metadata")}
                data["updatedAt"] = metadata.get("updated_at", "")
                data["migration"] = self._decoded(metadata.get("migration_json", "{}"))
            finally:
                connection.close()
        except MeetingStoreError:
            raise
        except (OSError, sqlite3.DatabaseError, json.JSONDecodeError, TypeError, ValueError, RecursionError) as exc:
            raise MeetingStoreError("Meeting store is invalid", code="meeting_store_invalid", status=500) from exc
        return normalize_store(data, strict=True)

    def _read_rows(self, connection: sqlite3.Connection, *, meeting_id: str | None = None, request_id: str | None = None) -> dict[str, Any]:
        """Build a scoped domain view for one typed transaction, never the full compatibility snapshot."""
        data = empty_store()
        if meeting_id is not None:
            row = connection.execute("SELECT payload_json FROM meetings WHERE id=?", (str(meeting_id),)).fetchone()
            if row:
                data["meetings"][str(meeting_id)] = self._decoded(row[0])
                data["events"][str(meeting_id)] = [
                    self._decoded(event[0]) for event in connection.execute(
                        "SELECT payload_json FROM meeting_events WHERE meeting_id=? ORDER BY position", (str(meeting_id),),
                    )
                ]
                for occupancy in connection.execute("SELECT agent_id FROM occupancy WHERE meeting_id=?", (str(meeting_id),)):
                    data["occupancy"][str(occupancy[0])] = str(meeting_id)
        if request_id is not None:
            row = connection.execute("SELECT payload_json FROM meeting_requests WHERE id=?", (str(request_id),)).fetchone()
            if row:
                data["requests"][str(request_id)] = self._decoded(row[0])
        for row in connection.execute("SELECT namespace,item_key,payload_json FROM idempotency"):
            data["idempotency"].setdefault(str(row[0]), {})[str(row[1])] = self._decoded(row[2])
        return data

    def _read_collection_scope(self, connection, *, meetings=False, requests=False) -> dict[str, Any]:
        data = empty_store()
        if meetings:
            for row in connection.execute("SELECT id,payload_json FROM meetings"):
                data["meetings"][str(row[0])] = self._decoded(row[1])
            for row in connection.execute("SELECT agent_id,meeting_id FROM occupancy"):
                data["occupancy"][str(row[0])] = str(row[1])
        if requests:
            for row in connection.execute("SELECT id,payload_json FROM meeting_requests"):
                data["requests"][str(row[0])] = self._decoded(row[1])
        for row in connection.execute("SELECT namespace,item_key,payload_json FROM idempotency"):
            data["idempotency"].setdefault(str(row[0]), {})[str(row[1])] = self._decoded(row[2])
        return data

    def get_meeting(self, meeting_id: str) -> dict[str, Any] | None:
        self._initialize()
        connection = connect_sqlite(self.path, readonly=True)
        try:
            row = connection.execute("SELECT payload_json FROM meetings WHERE id=?", (str(meeting_id),)).fetchone()
            return copy.deepcopy(self._decoded(row[0])) if row else None
        finally:
            connection.close()

    def get_request(self, request_id: str) -> dict[str, Any] | None:
        self._initialize()
        connection = connect_sqlite(self.path, readonly=True)
        try:
            row = connection.execute("SELECT payload_json FROM meeting_requests WHERE id=?", (str(request_id),)).fetchone()
            return copy.deepcopy(self._decoded(row[0])) if row else None
        finally:
            connection.close()

    def list_meetings(self, *, terminal: bool | None = None) -> list[dict[str, Any]]:
        self._initialize()
        connection = connect_sqlite(self.path, readonly=True)
        try:
            if terminal is None:
                rows = connection.execute("SELECT payload_json FROM meetings")
            else:
                placeholders = ",".join("?" for _ in TERMINAL_PHASES)
                operator = "IN" if terminal else "NOT IN"
                rows = connection.execute(
                    f"SELECT payload_json FROM meetings WHERE COALESCE(json_extract(payload_json, '$.stage'), json_extract(payload_json, '$.phase'), 'draft') {operator} ({placeholders})",
                    tuple(TERMINAL_PHASES),
                )
            values = [self._decoded(row[0]) for row in rows]
        finally:
            connection.close()
        return copy.deepcopy(values)

    def list_meetings_with_events(self, *, terminal: bool | None = None) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
        """Load a projection collection and its event streams with one connection."""
        self._initialize()
        connection = connect_sqlite(self.path, readonly=True)
        try:
            meetings = [self._decoded(row[0]) for row in connection.execute("SELECT payload_json FROM meetings")]
            if terminal is not None:
                meetings = [
                    meeting for meeting in meetings
                    if (str(meeting.get("stage") or meeting.get("phase") or "") in TERMINAL_PHASES) is terminal
                ]
            events_by_meeting = {str(meeting.get("id") or ""): [] for meeting in meetings}
            ids = list(events_by_meeting)
            if ids:
                placeholders = ",".join("?" for _ in ids)
                rows = connection.execute(
                    f"SELECT meeting_id,payload_json FROM meeting_events WHERE meeting_id IN ({placeholders}) ORDER BY meeting_id,position",
                    ids,
                )
                for row in rows:
                    events_by_meeting[str(row[0])].append(self._decoded(row[1]))
            return copy.deepcopy([
                (meeting, events_by_meeting.get(str(meeting.get("id") or ""), [])) for meeting in meetings
            ])
        finally:
            connection.close()

    def list_requests(self) -> list[dict[str, Any]]:
        self._initialize()
        connection = connect_sqlite(self.path, readonly=True)
        try:
            return [copy.deepcopy(self._decoded(row[0])) for row in connection.execute("SELECT payload_json FROM meeting_requests")]
        finally:
            connection.close()

    def list_occupancy(self) -> dict[str, str]:
        self._initialize()
        connection = connect_sqlite(self.path, readonly=True)
        try:
            return {str(row[0]): str(row[1]) for row in connection.execute("SELECT agent_id,meeting_id FROM occupancy")}
        finally:
            connection.close()

    def list_events(self, meeting_id: str, *, after: int = 0) -> list[dict[str, Any]]:
        self._initialize()
        connection = connect_sqlite(self.path, readonly=True)
        try:
            rows = connection.execute(
                "SELECT payload_json FROM meeting_events WHERE meeting_id=? "
                "AND COALESCE(json_extract(payload_json, '$.sequence'), 0)>? ORDER BY position",
                (str(meeting_id), int(after or 0)),
            )
            values = [self._decoded(row[0]) for row in rows]
            return copy.deepcopy(values)
        finally:
            connection.close()

    def mutate_meeting(self, meeting_id: str, mutator: Callable[[dict[str, Any]], Any]) -> tuple[dict[str, Any], Any]:
        return self._mutate_scoped(meeting_id=str(meeting_id), request_id=None, mutator=mutator)

    @contextmanager
    def edit_meeting(self, meeting_id: str):
        """Edit one Meeting and its event stream in a single SQLite transaction."""
        self._initialize()
        with self._lock:
            connection = connect_sqlite(self.path)
            try:
                connection.execute("BEGIN IMMEDIATE")
                before = self._read_rows(connection, meeting_id=str(meeting_id), request_id=None)
                data = copy.deepcopy(before)
                yield data
                data["updatedAt"] = now_iso()
                self._validate_scoped(connection, data)
                self._write_changes_on(connection, before, data)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def mutate_request(self, request_id: str, mutator: Callable[[dict[str, Any]], Any]) -> tuple[dict[str, Any], Any]:
        return self._mutate_scoped(meeting_id=None, request_id=str(request_id), mutator=mutator)

    def create_meeting(self, mutator: Callable[[dict[str, Any]], Any]) -> tuple[dict[str, Any], Any]:
        return self._mutate_collection(meetings=True, requests=False, mutator=mutator)

    def create_request(self, mutator: Callable[[dict[str, Any]], Any]) -> tuple[dict[str, Any], Any]:
        return self._mutate_collection(meetings=False, requests=True, mutator=mutator)

    def mutate_request_with_meetings(self, request_id: str, mutator) -> tuple[dict[str, Any], Any]:
        return self._mutate_collection(meetings=True, requests=True, mutator=mutator, request_id=str(request_id))

    def mutate_all_meetings(self, mutator) -> tuple[dict[str, Any], Any]:
        return self._mutate_collection(meetings=True, requests=False, mutator=mutator, include_events=True)

    def mutate_preparing_meetings(self, mutator) -> tuple[dict[str, Any], Any]:
        """Mutate only preparing Meetings, their occupancy, events and idempotency state."""
        self._initialize()
        with self._lock:
            connection = connect_sqlite(self.path)
            try:
                connection.execute("BEGIN IMMEDIATE")
                before = empty_store()
                rows = connection.execute(
                    "SELECT id,payload_json FROM meetings WHERE json_extract(payload_json, '$.stage')='preparing'"
                )
                for row in rows:
                    meeting_id = str(row[0])
                    before["meetings"][meeting_id] = self._decoded(row[1])
                    before["events"][meeting_id] = [
                        self._decoded(event[0]) for event in connection.execute(
                            "SELECT payload_json FROM meeting_events WHERE meeting_id=? ORDER BY position", (meeting_id,),
                        )
                    ]
                for row in connection.execute(
                    "SELECT agent_id,meeting_id FROM occupancy WHERE meeting_id IN "
                    "(SELECT id FROM meetings WHERE json_extract(payload_json, '$.stage')='preparing')"
                ):
                    before["occupancy"][str(row[0])] = str(row[1])
                for row in connection.execute("SELECT namespace,item_key,payload_json FROM idempotency"):
                    before["idempotency"].setdefault(str(row[0]), {})[str(row[1])] = self._decoded(row[2])
                data = copy.deepcopy(before)
                result = mutator(data)
                data["updatedAt"] = now_iso()
                self._validate_scoped(connection, data)
                self._write_changes_on(connection, before, data)
                connection.commit()
                return copy.deepcopy(data), copy.deepcopy(result)
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def _mutate_collection(self, *, meetings, requests, mutator, request_id=None, include_events=False):
        self._initialize()
        with self._lock:
            connection = connect_sqlite(self.path)
            try:
                connection.execute("BEGIN IMMEDIATE")
                before = self._read_collection_scope(connection, meetings=meetings, requests=requests)
                if request_id is not None:
                    before["requests"] = {
                        key: value for key, value in before["requests"].items() if key == request_id
                    }
                if include_events:
                    for meeting_id in before["meetings"]:
                        before["events"][meeting_id] = [
                            self._decoded(row[0]) for row in connection.execute(
                                "SELECT payload_json FROM meeting_events WHERE meeting_id=? ORDER BY position", (meeting_id,),
                            )
                        ]
                data = copy.deepcopy(before)
                result = mutator(data)
                data["updatedAt"] = now_iso()
                self._validate_scoped(connection, data)
                self._write_changes_on(connection, before, data)
                connection.commit()
                return copy.deepcopy(data), copy.deepcopy(result)
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def _mutate_scoped(self, *, meeting_id: str | None, request_id: str | None, mutator) -> tuple[dict[str, Any], Any]:
        self._initialize()
        with self._lock:
            connection = connect_sqlite(self.path)
            try:
                connection.execute("BEGIN IMMEDIATE")
                before = self._read_rows(connection, meeting_id=meeting_id, request_id=request_id)
                data = copy.deepcopy(before)
                result = mutator(data)
                data["updatedAt"] = now_iso()
                self._validate_scoped(connection, data)
                self._write_changes_on(connection, before, data)
                connection.commit()
                return copy.deepcopy(data), copy.deepcopy(result)
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def _write_changes_on(self, connection: sqlite3.Connection, previous: Mapping[str, Any], data: Mapping[str, Any]) -> None:
        self._sync_map(connection, "meetings", "id", previous["meetings"], data["meetings"])
        self._sync_events(connection, previous["events"], data["events"])
        self._sync_map(connection, "meeting_requests", "id", previous["requests"], data["requests"])
        self._sync_occupancy(connection, previous["occupancy"], data["occupancy"])
        self._sync_idempotency(connection, previous["idempotency"], data["idempotency"])
        connection.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('updated_at',?)", (str(data["updatedAt"]),))

    def _validate_scoped(self, connection: sqlite3.Connection, data: Mapping[str, Any]) -> None:
        for meeting_id, meeting in data["meetings"].items():
            if not isinstance(meeting, dict) or str(meeting.get("id") or meeting_id) != str(meeting_id):
                raise MeetingStoreError("Meeting identity conflict", code="meeting_store_conflict")
            if str(meeting.get("stage") or meeting.get("phase") or "draft") not in MEETING_PHASES:
                raise MeetingStoreError("Unsupported Meeting phase", code="meeting_store_conflict")
            if not isinstance(meeting.get("participants", []), list):
                raise MeetingStoreError("Meeting participants must be a list", code="meeting_store_conflict")
        for request_id, request in data["requests"].items():
            if not isinstance(request, dict) or str(request.get("id") or request_id) != str(request_id):
                raise MeetingStoreError("Meeting request identity conflict", code="meeting_store_conflict")
            if str(request.get("status") or "pending") not in REQUEST_STATUSES:
                raise MeetingStoreError("Unsupported Meeting request status", code="meeting_store_conflict")
            conversion = request.get("conversion") or {}
            if not isinstance(conversion, dict):
                raise MeetingStoreError("Meeting request conversion must be an object", code="meeting_store_conflict")
            linked = str(conversion.get("meetingId") or "")
            exists = linked in data["meetings"] or (
                linked and connection.execute("SELECT 1 FROM meetings WHERE id=?", (linked,)).fetchone() is not None
            )
            if linked and not exists:
                raise MeetingStoreError("Meeting request references a missing Meeting", code="meeting_store_conflict")
        for agent_id, meeting_id in data["occupancy"].items():
            meeting = data["meetings"].get(meeting_id)
            if meeting is None:
                row = connection.execute("SELECT payload_json FROM meetings WHERE id=?", (str(meeting_id),)).fetchone()
                meeting = self._decoded(row[0]) if row else None
            if not isinstance(meeting, dict):
                raise MeetingStoreError("Occupancy references a missing Meeting", code="meeting_store_conflict")
            phase = str(meeting.get("stage") or meeting.get("phase") or "draft")
            if phase in TERMINAL_PHASES or agent_id not in (meeting.get("participants") or []):
                raise MeetingStoreError("Occupancy is incompatible with Meeting state", code="meeting_store_conflict")
        for meeting_id, events in data["events"].items():
            exists = meeting_id in data["meetings"] or connection.execute(
                "SELECT 1 FROM meetings WHERE id=?", (str(meeting_id),),
            ).fetchone() is not None
            if not exists or not isinstance(events, list):
                raise MeetingStoreError("Meeting events have invalid ownership", code="meeting_store_conflict")

    def _write_changes(self, previous: Mapping[str, Any], data: Mapping[str, Any]) -> None:
        if not self.path.exists() and self._legacy_data_exists():
            raise MeetingStoreError("Meeting store migration is required", code="meeting_store_migration_required")
        self._initialize()
        connection = connect_sqlite(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._write_changes_on(connection, previous, data)
            connection.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('migration_json',?)", (self._json(data["migration"]),))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _sync_map(self, connection, table, key_column, old, new):
        for key in old.keys() - new.keys():
            connection.execute(f"DELETE FROM {table} WHERE {key_column}=?", (str(key),))
        for key, value in new.items():
            if key not in old or old[key] != value:
                connection.execute(
                    f"INSERT INTO {table}({key_column},payload_json) VALUES(?,?) "
                    f"ON CONFLICT({key_column}) DO UPDATE SET payload_json=excluded.payload_json",
                    (str(key), self._json(value)),
                )

    def _sync_events(self, connection, old, new):
        for meeting_id in old.keys() - new.keys():
            connection.execute("DELETE FROM meeting_event_streams WHERE meeting_id=?", (str(meeting_id),))
            connection.execute("DELETE FROM meeting_events WHERE meeting_id=?", (str(meeting_id),))
        for meeting_id, events in new.items():
            prior = old.get(meeting_id, [])
            if meeting_id not in old:
                connection.execute("INSERT OR IGNORE INTO meeting_event_streams(meeting_id) VALUES(?)", (str(meeting_id),))
            if prior == events:
                continue
            prefix = len(prior) if len(events) >= len(prior) and events[:len(prior)] == prior else 0
            if not prefix:
                connection.execute("DELETE FROM meeting_events WHERE meeting_id=?", (str(meeting_id),))
            for position, event in enumerate(events[prefix:], start=prefix):
                connection.execute(
                    "INSERT OR REPLACE INTO meeting_events(meeting_id,position,payload_json) VALUES(?,?,?)",
                    (str(meeting_id), position, self._json(event)),
                )
            if len(events) < len(prior):
                connection.execute("DELETE FROM meeting_events WHERE meeting_id=? AND position>=?", (str(meeting_id), len(events)))

    def _sync_occupancy(self, connection, old, new):
        for agent_id in old.keys() - new.keys():
            connection.execute("DELETE FROM occupancy WHERE agent_id=?", (str(agent_id),))
        for agent_id, meeting_id in new.items():
            if old.get(agent_id) != meeting_id:
                connection.execute(
                    "INSERT INTO occupancy(agent_id,meeting_id) VALUES(?,?) ON CONFLICT(agent_id) DO UPDATE SET meeting_id=excluded.meeting_id",
                    (str(agent_id), str(meeting_id)),
                )

    def _sync_idempotency(self, connection, old, new):
        namespaces = set(old) | set(new)
        for namespace in namespaces:
            old_values, new_values = old.get(namespace, {}), new.get(namespace, {})
            for key in old_values.keys() - new_values.keys():
                connection.execute("DELETE FROM idempotency WHERE namespace=? AND item_key=?", (namespace, str(key)))
            for key, value in new_values.items():
                if key not in old_values or old_values[key] != value:
                    connection.execute(
                        "INSERT INTO idempotency(namespace,item_key,payload_json) VALUES(?,?,?) "
                        "ON CONFLICT(namespace,item_key) DO UPDATE SET payload_json=excluded.payload_json",
                        (namespace, str(key), self._json(value)),
                    )

    def import_store(self, data: Mapping[str, Any]) -> None:
        validated = normalize_store(data, strict=True)
        with self._lock:
            if self.path.exists():
                existing = self._read_disk()
                if existing == validated:
                    return
                raise MeetingStoreError("Meeting database already contains different data", code="meeting_store_conflict")
            self._initialize()
            self._write_changes(empty_store(), validated)


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
