"""Transactional SQLite authority for the Virtual Office HR domain."""

from __future__ import annotations

import base64
import binascii
import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence
from urllib.parse import quote


SCHEMA_NAME = "vo-human-resources"
DATABASE_FILENAME = "hr.sqlite3"
MIN_BUSY_TIMEOUT_MS = 100
MAX_BUSY_TIMEOUT_MS = 30_000
MAX_PAGE_SIZE = 100
MAX_AI_ID_LENGTH = 256
AGENT_STATUSES = frozenset({"active", "offline", "disabled", "deleted", "unreachable"})
INTRODUCTION_STATES = frozenset(
    {"introduction_pending", "published", "clarification_pending", "failed"}
)


class HRRepositoryError(RuntimeError):
    """Base class for safe, diagnosable HR repository failures."""

    code = "hr_repository_error"


class HRRepositoryPathError(HRRepositoryError):
    code = "hr_repository_path_invalid"


class HRRepositoryMigrationError(HRRepositoryError):
    code = "hr_repository_migration_failed"


class HRRepositoryValidationError(HRRepositoryError):
    code = "hr_repository_validation_failed"


class HRRepositoryNotFoundError(HRRepositoryError):
    code = "hr_repository_not_found"


class HRRepositoryConflictError(HRRepositoryError):
    code = "hr_repository_conflict"


@dataclass(frozen=True, slots=True)
class HRMigration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("HR migration version must be a positive integer")
        if not self.name.strip():
            raise ValueError("HR migration name must not be empty")


@dataclass(frozen=True, slots=True)
class HRRepositoryInfo:
    path: str
    schema_name: str
    schema_version: int
    initialized_at: str


@dataclass(frozen=True, slots=True)
class AgentRecord:
    ai_id: str
    name: str
    agent_kind: str
    provider_kind: str
    status: str
    availability: str
    discovery_source: str
    discovered_at: str
    last_seen_at: str
    inactive_at: str | None
    revision: int
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class AgentIdentityRecord:
    id: int
    ai_id: str
    name: str
    status: str
    source: str
    observed_at: str


@dataclass(frozen=True, slots=True)
class IntroductionRecord:
    id: int
    ai_id: str
    version: int
    state: str
    raw_response: str | None
    introduction: str
    source: str
    actor_id: str
    clarification_question: str
    is_current: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class AgentPage:
    items: tuple[AgentRecord, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class IdentityHistoryPage:
    items: tuple[AgentIdentityRecord, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class IntroductionPage:
    items: tuple[IntroductionRecord, ...]
    next_cursor: str | None


_SCHEMA_V1 = (
    """CREATE TABLE metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    ) WITHOUT ROWID""",
    """CREATE TABLE agents (
        ai_id TEXT PRIMARY KEY CHECK(length(trim(ai_id)) > 0),
        name TEXT NOT NULL CHECK(length(trim(name)) > 0),
        agent_kind TEXT NOT NULL DEFAULT 'unknown',
        provider_kind TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active',
        availability TEXT NOT NULL DEFAULT 'unknown',
        discovery_source TEXT NOT NULL DEFAULT '',
        discovered_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        inactive_at TEXT,
        revision INTEGER NOT NULL DEFAULT 1 CHECK(revision >= 1),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    ) WITHOUT ROWID""",
    "CREATE INDEX agents_status_updated_idx ON agents(status, updated_at DESC, ai_id)",
    """CREATE TABLE agent_identity_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ai_id TEXT NOT NULL REFERENCES agents(ai_id) ON UPDATE CASCADE ON DELETE RESTRICT,
        name TEXT NOT NULL,
        status TEXT NOT NULL,
        source TEXT NOT NULL,
        observed_at TEXT NOT NULL
    )""",
    "CREATE INDEX identity_history_agent_idx ON agent_identity_history(ai_id, observed_at DESC, id DESC)",
    """CREATE TABLE introductions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ai_id TEXT NOT NULL REFERENCES agents(ai_id) ON UPDATE CASCADE ON DELETE RESTRICT,
        version INTEGER NOT NULL CHECK(version >= 1),
        state TEXT NOT NULL,
        raw_response TEXT,
        introduction TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        clarification_question TEXT NOT NULL DEFAULT '',
        is_current INTEGER NOT NULL DEFAULT 1 CHECK(is_current IN (0, 1)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(ai_id, version)
    )""",
    "CREATE UNIQUE INDEX introductions_current_idx ON introductions(ai_id) WHERE is_current = 1",
    """CREATE TABLE daily_cycles (
        id TEXT PRIMARY KEY CHECK(length(trim(id)) > 0),
        local_date TEXT NOT NULL UNIQUE,
        timezone TEXT NOT NULL,
        scheduled_at TEXT NOT NULL,
        window_opens_at TEXT NOT NULL,
        window_closes_at TEXT NOT NULL,
        status TEXT NOT NULL,
        roster_snapshot_json TEXT NOT NULL DEFAULT '[]',
        occurrence_key TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    ) WITHOUT ROWID""",
    "CREATE INDEX daily_cycles_status_idx ON daily_cycles(status, local_date DESC)",
    """CREATE TABLE report_requests (
        id TEXT PRIMARY KEY CHECK(length(trim(id)) > 0),
        cycle_id TEXT NOT NULL REFERENCES daily_cycles(id) ON UPDATE CASCADE ON DELETE RESTRICT,
        ai_id TEXT NOT NULL REFERENCES agents(ai_id) ON UPDATE CASCADE ON DELETE RESTRICT,
        status TEXT NOT NULL,
        occurrence_key TEXT NOT NULL UNIQUE,
        conversation_key TEXT NOT NULL DEFAULT '',
        requested_at TEXT,
        responded_at TEXT,
        attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
        last_error TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(cycle_id, ai_id)
    ) WITHOUT ROWID""",
    "CREATE INDEX report_requests_state_idx ON report_requests(cycle_id, status, ai_id)",
    """CREATE TABLE daily_reports (
        id TEXT PRIMARY KEY CHECK(length(trim(id)) > 0),
        cycle_id TEXT REFERENCES daily_cycles(id) ON UPDATE CASCADE ON DELETE RESTRICT,
        ai_id TEXT NOT NULL REFERENCES agents(ai_id) ON UPDATE CASCADE ON DELETE RESTRICT,
        local_date TEXT NOT NULL,
        submission_state TEXT NOT NULL,
        raw_response TEXT,
        normalized_json TEXT,
        normalizer_id TEXT NOT NULL DEFAULT '',
        requested_at TEXT,
        window_closed_at TEXT,
        submitted_at TEXT,
        normalized_at TEXT,
        revision INTEGER NOT NULL DEFAULT 1 CHECK(revision >= 1),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(ai_id, local_date)
    ) WITHOUT ROWID""",
    "CREATE INDEX daily_reports_date_state_idx ON daily_reports(local_date DESC, submission_state, ai_id)",
    """CREATE TABLE assessments (
        id TEXT PRIMARY KEY CHECK(length(trim(id)) > 0),
        ai_id TEXT NOT NULL REFERENCES agents(ai_id) ON UPDATE CASCADE ON DELETE RESTRICT,
        local_date TEXT NOT NULL,
        version INTEGER NOT NULL CHECK(version >= 1),
        is_current INTEGER NOT NULL DEFAULT 1 CHECK(is_current IN (0, 1)),
        status TEXT NOT NULL,
        workload TEXT NOT NULL CHECK(workload IN ('low','appropriate','high','overloaded','insufficient_information')),
        principal_contributions_json TEXT NOT NULL DEFAULT '[]',
        rationale TEXT NOT NULL,
        blockers_json TEXT NOT NULL DEFAULT '[]',
        strengths_json TEXT NOT NULL DEFAULT '[]',
        improvements_json TEXT NOT NULL DEFAULT '[]',
        runtime_diagnosis TEXT NOT NULL,
        information_sufficiency TEXT NOT NULL,
        evidence_version TEXT NOT NULL,
        hr_id TEXT NOT NULL,
        revision_reason TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(ai_id, local_date, version)
    ) WITHOUT ROWID""",
    "CREATE UNIQUE INDEX assessments_current_idx ON assessments(ai_id, local_date) WHERE is_current = 1",
    "CREATE INDEX assessments_date_status_idx ON assessments(local_date DESC, status, ai_id)",
    """CREATE TABLE assessment_evidence (
        assessment_id TEXT NOT NULL REFERENCES assessments(id) ON UPDATE CASCADE ON DELETE CASCADE,
        sequence INTEGER NOT NULL CHECK(sequence >= 0),
        evidence_type TEXT NOT NULL,
        reference_id TEXT NOT NULL,
        summary TEXT NOT NULL,
        evidence_date TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(assessment_id, sequence)
    ) WITHOUT ROWID""",
    """CREATE TABLE access_grants (
        ai_id TEXT PRIMARY KEY REFERENCES agents(ai_id) ON UPDATE CASCADE ON DELETE RESTRICT,
        key_id TEXT NOT NULL UNIQUE,
        secret_digest TEXT NOT NULL CHECK(length(secret_digest) >= 32),
        status TEXT NOT NULL,
        issued_at TEXT NOT NULL,
        rotated_at TEXT,
        revoked_at TEXT,
        revocation_reason TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL
    ) WITHOUT ROWID""",
    """CREATE TABLE access_log (
        id TEXT PRIMARY KEY CHECK(length(trim(id)) > 0),
        viewer_ai_id TEXT NOT NULL REFERENCES agents(ai_id) ON UPDATE CASCADE ON DELETE RESTRICT,
        target_ai_id TEXT NOT NULL REFERENCES agents(ai_id) ON UPDATE CASCADE ON DELETE RESTRICT,
        viewed_at TEXT NOT NULL,
        scope TEXT NOT NULL,
        request_source TEXT NOT NULL,
        result TEXT NOT NULL,
        occurrence_key TEXT NOT NULL UNIQUE,
        CHECK(viewer_ai_id <> target_ai_id)
    ) WITHOUT ROWID""",
    "CREATE INDEX access_log_target_idx ON access_log(target_ai_id, viewed_at DESC)",
    "CREATE INDEX access_log_viewer_idx ON access_log(viewer_ai_id, viewed_at DESC)",
    """CREATE TABLE hr_activity (
        id TEXT PRIMARY KEY CHECK(length(trim(id)) > 0),
        ai_id TEXT REFERENCES agents(ai_id) ON UPDATE CASCADE ON DELETE SET NULL,
        action TEXT NOT NULL,
        status TEXT NOT NULL,
        message TEXT NOT NULL DEFAULT '',
        error TEXT NOT NULL DEFAULT '',
        context_json TEXT NOT NULL DEFAULT '{}',
        occurrence_key TEXT UNIQUE,
        created_at TEXT NOT NULL
    ) WITHOUT ROWID""",
    "CREATE INDEX hr_activity_created_idx ON hr_activity(created_at DESC, id)",
    "CREATE INDEX hr_activity_agent_idx ON hr_activity(ai_id, created_at DESC)",
)


def _apply_schema_v1(connection: sqlite3.Connection) -> None:
    for statement in _SCHEMA_V1:
        connection.execute(statement)


DEFAULT_MIGRATIONS = (HRMigration(1, "initial_hr_schema", _apply_schema_v1),)


def _validated_migrations(migrations: Sequence[HRMigration]) -> tuple[HRMigration, ...]:
    ordered = tuple(sorted(migrations, key=lambda item: item.version))
    if not ordered:
        raise ValueError("HR repository requires at least one migration")
    expected = tuple(range(1, ordered[-1].version + 1))
    actual = tuple(item.version for item in ordered)
    if actual != expected:
        raise ValueError("HR migrations must be unique and contiguous from version 1")
    return ordered


def _required_text(value: object, field: str, *, maximum: int = 512) -> str:
    result = str(value or "").strip()
    if not result:
        raise HRRepositoryValidationError(f"{field} must not be empty")
    if len(result) > maximum or any(ord(character) < 32 for character in result):
        raise HRRepositoryValidationError(f"{field} is invalid")
    return result


def _stable_ai_id(value: object, field: str = "ai_id") -> str:
    if not isinstance(value, str):
        raise HRRepositoryValidationError(f"{field} is invalid")
    result = _required_text(value, field, maximum=MAX_AI_ID_LENGTH)
    if result != value or any(character.isspace() for character in result):
        raise HRRepositoryValidationError(f"{field} is invalid")
    return result


def _optional_text(value: object, field: str, *, maximum: int = 20_000) -> str:
    result = str(value or "").strip()
    if len(result) > maximum or any(
        ord(character) < 32 and character not in "\n\r\t" for character in result
    ):
        raise HRRepositoryValidationError(f"{field} is invalid")
    return result


def _raw_text(value: object | None, field: str, *, maximum: int = 40_000) -> str | None:
    if value is None:
        return None
    result = str(value)
    if len(result) > maximum or any(
        ord(character) < 32 and character not in "\n\r\t" for character in result
    ):
        raise HRRepositoryValidationError(f"{field} is invalid")
    return result


def _page_limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_PAGE_SIZE:
        raise HRRepositoryValidationError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    return value


def _encode_cursor(parts: Sequence[object]) -> str:
    payload = json.dumps(list(parts), ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None, *, fields: int) -> tuple[object, ...] | None:
    if cursor is None:
        return None
    try:
        value = _required_text(cursor, "cursor", maximum=2_048)
        padding = "=" * (-len(value) % 4)
        payload = base64.b64decode(value + padding, altchars=b"-_", validate=True)
        decoded = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError, binascii.Error) as exc:
        raise HRRepositoryValidationError("cursor is invalid") from exc
    if not isinstance(decoded, list) or len(decoded) != fields:
        raise HRRepositoryValidationError("cursor is invalid")
    return tuple(decoded)


def _agent_from_row(row: sqlite3.Row) -> AgentRecord:
    return AgentRecord(**dict(row))


def _identity_from_row(row: sqlite3.Row) -> AgentIdentityRecord:
    return AgentIdentityRecord(**dict(row))


def _introduction_from_row(row: sqlite3.Row) -> IntroductionRecord:
    values = dict(row)
    values["is_current"] = bool(values["is_current"])
    return IntroductionRecord(**values)


class HRRepository:
    """Owns HR schema initialization, connections, and write transactions."""

    def __init__(
        self,
        status_dir: str | os.PathLike[str],
        *,
        busy_timeout_ms: int = 5_000,
        clock: Callable[[], datetime | str] = lambda: datetime.now(timezone.utc),
        migrations: Sequence[HRMigration] = DEFAULT_MIGRATIONS,
    ):
        if isinstance(busy_timeout_ms, bool) or not isinstance(busy_timeout_ms, int):
            raise ValueError("busy_timeout_ms must be an integer")
        if not MIN_BUSY_TIMEOUT_MS <= busy_timeout_ms <= MAX_BUSY_TIMEOUT_MS:
            raise ValueError(
                f"busy_timeout_ms must be between {MIN_BUSY_TIMEOUT_MS} and {MAX_BUSY_TIMEOUT_MS}"
            )
        self.status_dir = Path(status_dir).absolute()
        self.hr_dir = self.status_dir / "human-resources"
        self.path = self.hr_dir / DATABASE_FILENAME
        self.busy_timeout_ms = busy_timeout_ms
        self._clock = clock
        self._migrations = _validated_migrations(migrations)

    @property
    def target_schema_version(self) -> int:
        return self._migrations[-1].version

    def _timestamp(self) -> str:
        value = self._clock()
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                raise HRRepositoryError("HR repository clock must be timezone-aware")
            return value.isoformat()
        result = str(value or "").strip()
        if not result:
            raise HRRepositoryError("HR repository clock returned an empty timestamp")
        return result

    def _validate_path(self, *, create_parent: bool) -> None:
        if self.status_dir.is_symlink():
            raise HRRepositoryPathError("VO status directory must not be a symbolic link")
        if self.hr_dir.is_symlink() or self.path.is_symlink():
            raise HRRepositoryPathError("HR repository path must not be a symbolic link")
        if self.path.exists() and not self.path.is_file():
            raise HRRepositoryPathError("HR repository target must be a regular file")
        if create_parent:
            self.hr_dir.mkdir(parents=True, exist_ok=True)
        resolved_status = self.status_dir.resolve(strict=False)
        resolved_path = self.path.resolve(strict=False)
        try:
            resolved_path.relative_to(resolved_status)
        except ValueError as exc:
            raise HRRepositoryPathError("HR repository escapes the VO status directory") from exc

    @contextmanager
    def _connection(self, *, readonly: bool = False) -> Iterator[sqlite3.Connection]:
        self._validate_path(create_parent=not readonly)
        if readonly and not self.path.is_file():
            raise HRRepositoryError("HR repository is not initialized")
        target = (
            f"file:{quote(str(self.path))}?mode=ro"
            if readonly else str(self.path)
        )
        connection = sqlite3.connect(
            target,
            timeout=self.busy_timeout_ms / 1000,
            isolation_level=None,
            uri=readonly,
        )
        try:
            if not readonly:
                os.chmod(self.path, 0o600, follow_symlinks=False)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        return row is not None

    @contextmanager
    def _write_transaction(self) -> Iterator[sqlite3.Connection]:
        """Internal write boundary used by repository-owned domain methods."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def _current_version(self, connection: sqlite3.Connection) -> int:
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if user_version > self.target_schema_version:
            raise HRRepositoryMigrationError(
                f"HR schema version {user_version} is newer than supported {self.target_schema_version}"
            )
        if not self._table_exists(connection, "metadata"):
            if user_version != 0:
                raise HRRepositoryMigrationError("HR schema metadata table is missing")
            return 0
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        try:
            metadata_version = int(row[0]) if row is not None else 0
        except (TypeError, ValueError) as exc:
            raise HRRepositoryMigrationError("HR schema metadata version is invalid") from exc
        if metadata_version != user_version:
            raise HRRepositoryMigrationError(
                "HR schema metadata version does not match SQLite user_version"
            )
        return user_version

    def _record_migration(
        self,
        connection: sqlite3.Connection,
        migration: HRMigration,
        timestamp: str,
    ) -> None:
        if not self._table_exists(connection, "metadata"):
            raise HRRepositoryMigrationError("HR migration did not create metadata authority")
        facts = {
            "schema_name": SCHEMA_NAME,
            "schema_version": str(migration.version),
            "last_migration": migration.name,
        }
        for key, value in facts.items():
            connection.execute(
                """INSERT INTO metadata(key, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
                (key, value, timestamp),
            )
        connection.execute(
            "INSERT OR IGNORE INTO metadata(key, value, updated_at) VALUES ('initialized_at', ?, ?)",
            (timestamp, timestamp),
        )
        connection.execute(f"PRAGMA user_version = {migration.version}")

    def initialize(self) -> HRRepositoryInfo:
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    current = self._current_version(connection)
                    for migration in self._migrations:
                        if migration.version <= current:
                            continue
                        migration.apply(connection)
                        self._record_migration(connection, migration, self._timestamp())
                        current = migration.version
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
        except HRRepositoryError:
            raise
        except Exception as exc:
            raise HRRepositoryMigrationError(
                f"HR repository initialization failed: {str(exc).strip() or exc.__class__.__name__}"
            ) from exc
        return self.info()

    def info(self) -> HRRepositoryInfo:
        with self._connection(readonly=True) as connection:
            version = self._current_version(connection)
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'initialized_at'"
            ).fetchone()
            return HRRepositoryInfo(
                path=str(self.path),
                schema_name=SCHEMA_NAME,
                schema_version=version,
                initialized_at=str(row[0] if row is not None else ""),
            )

    def connection_settings(self) -> dict[str, Any]:
        with self._connection(readonly=True) as connection:
            return {
                "foreignKeys": bool(connection.execute("PRAGMA foreign_keys").fetchone()[0]),
                "busyTimeoutMs": int(connection.execute("PRAGMA busy_timeout").fetchone()[0]),
                "journalMode": str(connection.execute("PRAGMA journal_mode").fetchone()[0]),
            }

    def table_names(self) -> tuple[str, ...]:
        with self._connection(readonly=True) as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            return tuple(str(row[0]) for row in rows)

    def upsert_agent(
        self,
        *,
        ai_id: str,
        name: str,
        agent_kind: str,
        provider_kind: str = "",
        status: str = "active",
        availability: str = "unknown",
        source: str,
        expected_revision: int | None = None,
    ) -> AgentRecord:
        """Merge one discovery observation into the stable AI-ID authority."""
        ai_id = _stable_ai_id(ai_id)
        name = _required_text(name, "name")
        agent_kind = _required_text(agent_kind, "agent_kind", maximum=64)
        provider_kind = _optional_text(provider_kind, "provider_kind", maximum=64)
        status = _required_text(status, "status", maximum=32)
        availability = _required_text(availability, "availability", maximum=64)
        source = _required_text(source, "source", maximum=256)
        if status not in AGENT_STATUSES:
            raise HRRepositoryValidationError(f"unsupported Agent status: {status}")
        if expected_revision is not None and (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 0
        ):
            raise HRRepositoryValidationError("expected_revision must be a non-negative integer")
        observed_at = self._timestamp()
        with self._write_transaction() as connection:
            row = connection.execute("SELECT * FROM agents WHERE ai_id = ?", (ai_id,)).fetchone()
            if row is None:
                if expected_revision not in (None, 0):
                    raise HRRepositoryConflictError(
                        f"Agent {ai_id} does not match expected revision {expected_revision}"
                    )
                inactive_at = None if status == "active" else observed_at
                connection.execute(
                    """INSERT INTO agents(
                           ai_id, name, agent_kind, provider_kind, status, availability,
                           discovery_source, discovered_at, last_seen_at, inactive_at,
                           revision, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                    (
                        ai_id,
                        name,
                        agent_kind,
                        provider_kind,
                        status,
                        availability,
                        source,
                        observed_at,
                        observed_at,
                        inactive_at,
                        observed_at,
                        observed_at,
                    ),
                )
                connection.execute(
                    """INSERT INTO agent_identity_history(
                           ai_id, name, status, source, observed_at
                       ) VALUES (?, ?, ?, ?, ?)""",
                    (ai_id, name, status, source, observed_at),
                )
            else:
                current = _agent_from_row(row)
                if expected_revision is not None and current.revision != expected_revision:
                    raise HRRepositoryConflictError(
                        f"Agent {ai_id} revision is {current.revision}, expected {expected_revision}"
                    )
                material = (
                    current.name,
                    current.agent_kind,
                    current.provider_kind,
                    current.status,
                    current.availability,
                    current.discovery_source,
                ) != (name, agent_kind, provider_kind, status, availability, source)
                if material:
                    revision = current.revision + 1
                    inactive_at = (
                        None
                        if status == "active"
                        else current.inactive_at or observed_at
                    )
                    connection.execute(
                        """UPDATE agents SET
                               name = ?, agent_kind = ?, provider_kind = ?, status = ?,
                               availability = ?, discovery_source = ?, last_seen_at = ?,
                               inactive_at = ?, revision = ?, updated_at = ?
                           WHERE ai_id = ?""",
                        (
                            name,
                            agent_kind,
                            provider_kind,
                            status,
                            availability,
                            source,
                            observed_at,
                            inactive_at,
                            revision,
                            observed_at,
                            ai_id,
                        ),
                    )
                    connection.execute(
                        """INSERT INTO agent_identity_history(
                               ai_id, name, status, source, observed_at
                           ) VALUES (?, ?, ?, ?, ?)""",
                        (ai_id, name, status, source, observed_at),
                    )
                else:
                    connection.execute(
                        "UPDATE agents SET last_seen_at = ?, updated_at = ? WHERE ai_id = ?",
                        (observed_at, observed_at, ai_id),
                    )
            result = connection.execute("SELECT * FROM agents WHERE ai_id = ?", (ai_id,)).fetchone()
            return _agent_from_row(result)

    def get_agent(self, ai_id: str) -> AgentRecord | None:
        ai_id = _stable_ai_id(ai_id)
        with self._connection(readonly=True) as connection:
            row = connection.execute("SELECT * FROM agents WHERE ai_id = ?", (ai_id,)).fetchone()
            return _agent_from_row(row) if row is not None else None

    def list_agents(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> AgentPage:
        limit = _page_limit(limit)
        if status is not None:
            status = _required_text(status, "status", maximum=32)
            if status not in AGENT_STATUSES:
                raise HRRepositoryValidationError(f"unsupported Agent status: {status}")
        after = _decode_cursor(cursor, fields=2)
        parameters: list[object] = []
        clauses: list[str] = []
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status)
        if after is not None:
            updated_at, ai_id = after
            if not isinstance(updated_at, str) or not isinstance(ai_id, str):
                raise HRRepositoryValidationError("cursor is invalid")
            clauses.append("(updated_at < ? OR (updated_at = ? AND ai_id > ?))")
            parameters.extend((updated_at, updated_at, ai_id))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit + 1)
        with self._connection(readonly=True) as connection:
            rows = connection.execute(
                f"SELECT * FROM agents{where} ORDER BY updated_at DESC, ai_id ASC LIMIT ?",
                parameters,
            ).fetchall()
        items = tuple(_agent_from_row(row) for row in rows[:limit])
        next_cursor = None
        if len(rows) > limit:
            last = items[-1]
            next_cursor = _encode_cursor((last.updated_at, last.ai_id))
        return AgentPage(items=items, next_cursor=next_cursor)

    def list_identity_history(
        self,
        ai_id: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> IdentityHistoryPage:
        ai_id = _stable_ai_id(ai_id)
        limit = _page_limit(limit)
        after = _decode_cursor(cursor, fields=2)
        parameters: list[object] = [ai_id]
        condition = ""
        if after is not None:
            observed_at, row_id = after
            if not isinstance(observed_at, str) or isinstance(row_id, bool) or not isinstance(row_id, int):
                raise HRRepositoryValidationError("cursor is invalid")
            condition = " AND (observed_at < ? OR (observed_at = ? AND id < ?))"
            parameters.extend((observed_at, observed_at, row_id))
        parameters.append(limit + 1)
        with self._connection(readonly=True) as connection:
            rows = connection.execute(
                """SELECT id, ai_id, name, status, source, observed_at
                   FROM agent_identity_history WHERE ai_id = ?"""
                + condition
                + " ORDER BY observed_at DESC, id DESC LIMIT ?",
                parameters,
            ).fetchall()
        items = tuple(_identity_from_row(row) for row in rows[:limit])
        next_cursor = None
        if len(rows) > limit:
            last = items[-1]
            next_cursor = _encode_cursor((last.observed_at, last.id))
        return IdentityHistoryPage(items=items, next_cursor=next_cursor)

    def save_introduction(
        self,
        *,
        ai_id: str,
        state: str,
        raw_response: str | None,
        introduction: str,
        source: str,
        actor_id: str,
        clarification_question: str = "",
        expected_version: int | None = None,
    ) -> IntroductionRecord:
        ai_id = _stable_ai_id(ai_id)
        state = _required_text(state, "state", maximum=64)
        raw_response = _raw_text(raw_response, "raw_response")
        introduction = _optional_text(introduction, "introduction", maximum=4_000)
        source = _required_text(source, "source", maximum=256)
        actor_id = _stable_ai_id(actor_id, "actor_id")
        clarification_question = _optional_text(
            clarification_question, "clarification_question", maximum=2_000
        )
        if state not in INTRODUCTION_STATES:
            raise HRRepositoryValidationError(f"unsupported introduction state: {state}")
        if state == "published" and not introduction:
            raise HRRepositoryValidationError("published introduction must not be empty")
        if expected_version is not None and (
            isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 0
        ):
            raise HRRepositoryValidationError("expected_version must be a non-negative integer")
        timestamp = self._timestamp()
        with self._write_transaction() as connection:
            if connection.execute("SELECT 1 FROM agents WHERE ai_id = ?", (ai_id,)).fetchone() is None:
                raise HRRepositoryNotFoundError(f"Agent {ai_id} does not exist")
            row = connection.execute(
                "SELECT * FROM introductions WHERE ai_id = ? AND is_current = 1",
                (ai_id,),
            ).fetchone()
            current = _introduction_from_row(row) if row is not None else None
            current_version = current.version if current is not None else 0
            if expected_version is not None and expected_version != current_version:
                raise HRRepositoryConflictError(
                    f"Agent {ai_id} introduction version is {current_version}, expected {expected_version}"
                )
            content = (
                state,
                raw_response,
                introduction,
                source,
                actor_id,
                clarification_question,
            )
            if current is not None and content == (
                current.state,
                current.raw_response,
                current.introduction,
                current.source,
                current.actor_id,
                current.clarification_question,
            ):
                return current
            if current is not None:
                connection.execute(
                    "UPDATE introductions SET is_current = 0, updated_at = ? WHERE id = ?",
                    (timestamp, current.id),
                )
            version = current_version + 1
            cursor = connection.execute(
                """INSERT INTO introductions(
                       ai_id, version, state, raw_response, introduction, source, actor_id,
                       clarification_question, is_current, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (
                    ai_id,
                    version,
                    state,
                    raw_response,
                    introduction,
                    source,
                    actor_id,
                    clarification_question,
                    timestamp,
                    timestamp,
                ),
            )
            result = connection.execute(
                "SELECT * FROM introductions WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            return _introduction_from_row(result)

    def get_current_introduction(self, ai_id: str) -> IntroductionRecord | None:
        ai_id = _stable_ai_id(ai_id)
        with self._connection(readonly=True) as connection:
            row = connection.execute(
                "SELECT * FROM introductions WHERE ai_id = ? AND is_current = 1",
                (ai_id,),
            ).fetchone()
            return _introduction_from_row(row) if row is not None else None

    def list_introductions(
        self,
        ai_id: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> IntroductionPage:
        ai_id = _stable_ai_id(ai_id)
        limit = _page_limit(limit)
        after = _decode_cursor(cursor, fields=1)
        parameters: list[object] = [ai_id]
        condition = ""
        if after is not None:
            version = after[0]
            if isinstance(version, bool) or not isinstance(version, int):
                raise HRRepositoryValidationError("cursor is invalid")
            condition = " AND version < ?"
            parameters.append(version)
        parameters.append(limit + 1)
        with self._connection(readonly=True) as connection:
            rows = connection.execute(
                "SELECT * FROM introductions WHERE ai_id = ?"
                + condition
                + " ORDER BY version DESC LIMIT ?",
                parameters,
            ).fetchall()
        items = tuple(_introduction_from_row(row) for row in rows[:limit])
        next_cursor = None
        if len(rows) > limit:
            next_cursor = _encode_cursor((items[-1].version,))
        return IntroductionPage(items=items, next_cursor=next_cursor)
