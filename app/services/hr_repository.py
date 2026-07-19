"""Transactional SQLite authority for the Virtual Office HR domain."""

from __future__ import annotations

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


class HRRepositoryError(RuntimeError):
    """Base class for safe, diagnosable HR repository failures."""

    code = "hr_repository_error"


class HRRepositoryPathError(HRRepositoryError):
    code = "hr_repository_path_invalid"


class HRRepositoryMigrationError(HRRepositoryError):
    code = "hr_repository_migration_failed"


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
        observed_at TEXT NOT NULL,
        UNIQUE(ai_id, name, status, source, observed_at)
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
