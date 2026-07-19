"""Transactional SQLite authority for the Virtual Office HR domain."""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence
from urllib.parse import quote


SCHEMA_NAME = "vo-human-resources"
DATABASE_FILENAME = "hr.sqlite3"
MIN_BUSY_TIMEOUT_MS = 100
MAX_BUSY_TIMEOUT_MS = 30_000
MAX_PAGE_SIZE = 100
MAX_AI_ID_LENGTH = 256
MIN_EXPORT_BYTES = 1_024
MAX_EXPORT_BYTES = 1_000_000
MAX_EXPORT_OFFSET = 1_000_000
AGENT_STATUSES = frozenset({"active", "offline", "disabled", "deleted", "unreachable"})
INTRODUCTION_STATES = frozenset(
    {
        "introduction_pending",
        "response_received",
        "published",
        "clarification_pending",
        "failed",
    }
)
SHA256_HEX_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


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


class HRRepositoryCorruptionError(HRRepositoryError):
    code = "hr_repository_corrupt"


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
    skill_readiness: str
    grant_readiness: str
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
    request_occurrence_key: str
    conversation_key: str
    requested_at: str | None
    responded_at: str | None
    attempt_count: int
    last_error: str
    claim_token: str
    claimed_by: str
    claim_expires_at: str | None
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


@dataclass(frozen=True, slots=True)
class DailyCycleRecord:
    id: str
    local_date: str
    timezone: str
    scheduled_at: str
    window_opens_at: str
    window_closes_at: str
    status: str
    roster_snapshot: tuple[str, ...]
    occurrence_key: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ReportRequestRecord:
    id: str
    cycle_id: str
    ai_id: str
    status: str
    occurrence_key: str
    conversation_key: str
    requested_at: str | None
    responded_at: str | None
    attempt_count: int
    last_error: str
    claim_token: str
    claimed_by: str
    claim_expires_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class DailyReportRecord:
    id: str
    cycle_id: str | None
    ai_id: str
    local_date: str
    submission_state: str
    raw_response: str | None
    normalized: dict[str, Any] | None
    normalizer_id: str
    requested_at: str | None
    window_closed_at: str | None
    submitted_at: str | None
    normalized_at: str | None
    revision: int
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class AssessmentEvidenceRecord:
    sequence: int
    evidence_type: str
    reference_id: str
    summary: str
    evidence_date: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AssessmentRecord:
    id: str
    ai_id: str
    local_date: str
    version: int
    is_current: bool
    status: str
    workload: str
    principal_contributions: tuple[str, ...]
    rationale: str
    blockers: tuple[str, ...]
    strengths: tuple[str, ...]
    improvements: tuple[str, ...]
    runtime_diagnosis: str
    information_sufficiency: str
    evidence_version: str
    hr_id: str
    revision_reason: str
    created_at: str
    updated_at: str
    evidence: tuple[AssessmentEvidenceRecord, ...] = ()


@dataclass(frozen=True, slots=True)
class DailyReportPage:
    items: tuple[DailyReportRecord, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class AssessmentPage:
    items: tuple[AssessmentRecord, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class AccessGrantRecord:
    ai_id: str
    key_id: str
    secret_digest: str
    status: str
    issued_at: str
    rotated_at: str | None
    revoked_at: str | None
    revocation_reason: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class AccessLogRecord:
    id: str
    viewer_ai_id: str
    viewer_name: str
    target_ai_id: str
    target_name: str
    viewed_at: str
    scope: str
    request_source: str
    result: str
    occurrence_key: str


@dataclass(frozen=True, slots=True)
class HRActivityRecord:
    id: str
    ai_id: str | None
    action: str
    status: str
    message: str
    error: str
    context: dict[str, Any]
    occurrence_key: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class AccessLogPage:
    items: tuple[AccessLogRecord, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class HRActivityPage:
    items: tuple[HRActivityRecord, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class HRRepositoryHealth:
    status: str
    code: str
    path: str
    schema_version: int | None
    target_schema_version: int
    database_bytes: int
    page_count: int
    page_size: int
    integrity: str
    foreign_key_violations: int
    error: str


@dataclass(frozen=True, slots=True)
class HRExportPage:
    table: str
    rows: tuple[dict[str, Any], ...]
    next_cursor: str | None
    byte_size: int


_EXPORT_TABLES = {
    "metadata": ("key",),
    "agents": ("ai_id",),
    "agent_identity_history": ("id",),
    "introductions": ("id",),
    "daily_cycles": ("local_date", "id"),
    "report_requests": ("id",),
    "daily_reports": ("local_date", "ai_id"),
    "assessments": ("local_date", "ai_id", "version"),
    "assessment_evidence": ("assessment_id", "sequence"),
    "access_grants": ("ai_id",),
    "access_log": ("viewed_at", "id"),
    "hr_activity": ("created_at", "id"),
}
_EXPORT_JSON_FIELDS = frozenset(
    {
        "roster_snapshot_json",
        "normalized_json",
        "principal_contributions_json",
        "blockers_json",
        "strengths_json",
        "improvements_json",
        "metadata_json",
        "context_json",
    }
)


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
        skill_readiness TEXT NOT NULL DEFAULT 'pending',
        grant_readiness TEXT NOT NULL DEFAULT 'pending',
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
        request_occurrence_key TEXT NOT NULL DEFAULT '',
        conversation_key TEXT NOT NULL DEFAULT '',
        requested_at TEXT,
        responded_at TEXT,
        attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
        last_error TEXT NOT NULL DEFAULT '',
        claim_token TEXT NOT NULL DEFAULT '',
        claimed_by TEXT NOT NULL DEFAULT '',
        claim_expires_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(ai_id, version)
    )""",
    "CREATE UNIQUE INDEX introductions_current_idx ON introductions(ai_id) WHERE is_current = 1",
    "CREATE UNIQUE INDEX introductions_request_occurrence_idx ON introductions(request_occurrence_key) WHERE request_occurrence_key <> ''",
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
        claim_token TEXT NOT NULL DEFAULT '',
        claimed_by TEXT NOT NULL DEFAULT '',
        claim_expires_at TEXT,
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
        viewer_name TEXT NOT NULL,
        target_ai_id TEXT NOT NULL REFERENCES agents(ai_id) ON UPDATE CASCADE ON DELETE RESTRICT,
        target_name TEXT NOT NULL,
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


def _opaque_id(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise HRRepositoryValidationError(f"{field} is invalid")
    result = _required_text(value, field, maximum=256)
    if result != value or any(character.isspace() for character in result):
        raise HRRepositoryValidationError(f"{field} is invalid")
    return result


def _timestamp_text(value: object, field: str) -> str:
    result = _required_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(result)
    except ValueError as exc:
        raise HRRepositoryValidationError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HRRepositoryValidationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


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


def _local_date(value: object) -> str:
    result = _required_text(value, "local_date", maximum=10)
    try:
        if date.fromisoformat(result).isoformat() != result:
            raise ValueError
    except ValueError as exc:
        raise HRRepositoryValidationError("local_date must use YYYY-MM-DD") from exc
    return result


def _json_value(value: object, field: str, expected: type, *, maximum: int = 40_000) -> str:
    try:
        decoded = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError as exc:
        raise HRRepositoryValidationError(f"{field} must be valid JSON") from exc
    if not isinstance(decoded, expected):
        raise HRRepositoryValidationError(f"{field} has the wrong JSON shape")
    try:
        encoded = json.dumps(decoded, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise HRRepositoryValidationError(f"{field} must be JSON serializable") from exc
    if len(encoded) > maximum:
        raise HRRepositoryValidationError(f"{field} is too large")
    return encoded


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


def _cycle_from_row(row: sqlite3.Row) -> DailyCycleRecord:
    values = dict(row)
    values["roster_snapshot"] = tuple(json.loads(values.pop("roster_snapshot_json")))
    return DailyCycleRecord(**values)


def _request_from_row(row: sqlite3.Row) -> ReportRequestRecord:
    return ReportRequestRecord(**dict(row))


def _report_from_row(row: sqlite3.Row) -> DailyReportRecord:
    values = dict(row)
    normalized_json = values.pop("normalized_json")
    values["normalized"] = json.loads(normalized_json) if normalized_json is not None else None
    return DailyReportRecord(**values)


def _assessment_from_row(
    row: sqlite3.Row,
    evidence: Sequence[AssessmentEvidenceRecord] = (),
) -> AssessmentRecord:
    values = dict(row)
    values["is_current"] = bool(values["is_current"])
    for field in ("principal_contributions", "blockers", "strengths", "improvements"):
        values[field] = tuple(json.loads(values.pop(f"{field}_json")))
    values["evidence"] = tuple(evidence)
    return AssessmentRecord(**values)


def _grant_from_row(row: sqlite3.Row) -> AccessGrantRecord:
    return AccessGrantRecord(**dict(row))


def _access_log_from_row(row: sqlite3.Row) -> AccessLogRecord:
    return AccessLogRecord(**dict(row))


def _activity_from_row(row: sqlite3.Row) -> HRActivityRecord:
    values = dict(row)
    values["context"] = json.loads(values.pop("context_json"))
    return HRActivityRecord(**values)


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

    def update_agent_enablement(
        self,
        *,
        ai_id: str,
        skill_readiness: str,
        grant_readiness: str,
        expected_revision: int,
    ) -> AgentRecord:
        ai_id = _stable_ai_id(ai_id)
        skill_readiness = _required_text(skill_readiness, "skill_readiness", maximum=64)
        grant_readiness = _required_text(grant_readiness, "grant_readiness", maximum=64)
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 1
        ):
            raise HRRepositoryValidationError("expected_revision must be a positive integer")
        timestamp = self._timestamp()
        with self._write_transaction() as connection:
            row = connection.execute("SELECT * FROM agents WHERE ai_id = ?", (ai_id,)).fetchone()
            if row is None:
                raise HRRepositoryNotFoundError(f"Agent {ai_id} does not exist")
            current = _agent_from_row(row)
            if current.revision != expected_revision:
                raise HRRepositoryConflictError(
                    f"Agent {ai_id} revision is {current.revision}, expected {expected_revision}"
                )
            if (
                current.skill_readiness == skill_readiness
                and current.grant_readiness == grant_readiness
            ):
                return current
            connection.execute(
                """UPDATE agents SET
                       skill_readiness = ?, grant_readiness = ?,
                       revision = revision + 1, updated_at = ?
                   WHERE ai_id = ?""",
                (skill_readiness, grant_readiness, timestamp, ai_id),
            )
            row = connection.execute("SELECT * FROM agents WHERE ai_id = ?", (ai_id,)).fetchone()
            return _agent_from_row(row)

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

    def ensure_introduction_request(
        self,
        *,
        ai_id: str,
        occurrence_key: str,
        conversation_key: str,
        actor_id: str,
    ) -> IntroductionRecord:
        ai_id = _stable_ai_id(ai_id)
        occurrence_key = _opaque_id(occurrence_key, "occurrence_key")
        conversation_key = _opaque_id(conversation_key, "conversation_key")
        actor_id = _stable_ai_id(actor_id, "actor_id")
        timestamp = self._timestamp()
        with self._write_transaction() as connection:
            if connection.execute("SELECT 1 FROM agents WHERE ai_id = ?", (ai_id,)).fetchone() is None:
                raise HRRepositoryNotFoundError(f"Agent {ai_id} does not exist")
            row = connection.execute(
                "SELECT * FROM introductions WHERE ai_id = ? AND is_current = 1",
                (ai_id,),
            ).fetchone()
            if row is not None:
                current = _introduction_from_row(row)
                if current.state in {"response_received", "published", "clarification_pending"}:
                    return current
                if current.request_occurrence_key not in ("", occurrence_key):
                    raise HRRepositoryConflictError("another introduction request is current")
                if current.request_occurrence_key == "":
                    connection.execute(
                        """UPDATE introductions SET
                               request_occurrence_key = ?, conversation_key = ?,
                               actor_id = ?, updated_at = ? WHERE id = ?""",
                        (occurrence_key, conversation_key, actor_id, timestamp, current.id),
                    )
                    row = connection.execute(
                        "SELECT * FROM introductions WHERE id = ?", (current.id,)
                    ).fetchone()
                    return _introduction_from_row(row)
                if current.conversation_key != conversation_key:
                    raise HRRepositoryConflictError("introduction conversation key changed")
                return current
            try:
                cursor = connection.execute(
                    """INSERT INTO introductions(
                           ai_id, version, state, raw_response, introduction, source,
                           actor_id, clarification_question, is_current,
                           request_occurrence_key, conversation_key, created_at, updated_at
                       ) VALUES (?, 1, 'introduction_pending', NULL, '',
                                 'hr-introduction-request', ?, '', 1, ?, ?, ?, ?)""",
                    (
                        ai_id,
                        actor_id,
                        occurrence_key,
                        conversation_key,
                        timestamp,
                        timestamp,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise HRRepositoryConflictError("introduction request identity already exists") from exc
            row = connection.execute(
                "SELECT * FROM introductions WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            return _introduction_from_row(row)

    def claim_introduction_request(
        self,
        *,
        ai_id: str,
        claimed_by: str,
        claim_token: str,
        now: str,
        claim_expires_at: str,
    ) -> IntroductionRecord | None:
        ai_id = _stable_ai_id(ai_id)
        claimed_by = _opaque_id(claimed_by, "claimed_by")
        claim_token = _opaque_id(claim_token, "claim_token")
        now = _timestamp_text(now, "now")
        claim_expires_at = _timestamp_text(claim_expires_at, "claim_expires_at")
        if claim_expires_at <= now:
            raise HRRepositoryValidationError("claim expiry must be after now")
        with self._write_transaction() as connection:
            updated = connection.execute(
                """UPDATE introductions SET
                       state = 'introduction_pending', claim_token = ?, claimed_by = ?,
                       claim_expires_at = ?, requested_at = COALESCE(requested_at, ?),
                       attempt_count = attempt_count + 1, last_error = '', updated_at = ?
                   WHERE ai_id = ? AND is_current = 1
                     AND state IN ('introduction_pending', 'failed')
                     AND request_occurrence_key <> ''
                     AND (claim_token = '' OR claim_expires_at <= ?)""",
                (
                    claim_token,
                    claimed_by,
                    claim_expires_at,
                    now,
                    now,
                    ai_id,
                    now,
                ),
            ).rowcount
            if updated != 1:
                return None
            row = connection.execute(
                "SELECT * FROM introductions WHERE ai_id = ? AND is_current = 1",
                (ai_id,),
            ).fetchone()
            return _introduction_from_row(row)

    def finish_introduction_request(
        self,
        *,
        ai_id: str,
        claim_token: str,
        finished_at: str,
        raw_response: str | None,
        error: str = "",
    ) -> IntroductionRecord:
        ai_id = _stable_ai_id(ai_id)
        claim_token = _opaque_id(claim_token, "claim_token")
        finished_at = _timestamp_text(finished_at, "finished_at")
        raw_response = _raw_text(raw_response, "raw_response")
        error = _optional_text(error, "error", maximum=2_000)
        if raw_response is not None and error:
            raise HRRepositoryValidationError("introduction result cannot contain response and error")
        state = "response_received" if raw_response is not None else ("failed" if error else "introduction_pending")
        with self._write_transaction() as connection:
            updated = connection.execute(
                """UPDATE introductions SET
                       state = ?, raw_response = ?, responded_at = ?, last_error = ?,
                       claim_token = '', claimed_by = '', claim_expires_at = NULL,
                       updated_at = ?
                   WHERE ai_id = ? AND is_current = 1
                     AND state = 'introduction_pending' AND claim_token = ?
                     AND claim_expires_at > ?""",
                (
                    state,
                    raw_response,
                    finished_at if raw_response is not None else None,
                    error,
                    finished_at,
                    ai_id,
                    claim_token,
                    finished_at,
                ),
            ).rowcount
            if updated != 1:
                raise HRRepositoryConflictError("introduction request claim is stale or invalid")
            row = connection.execute(
                "SELECT * FROM introductions WHERE ai_id = ? AND is_current = 1",
                (ai_id,),
            ).fetchone()
            return _introduction_from_row(row)

    def ensure_daily_cycle(
        self,
        *,
        cycle_id: str,
        local_date: str,
        timezone_name: str,
        scheduled_at: str,
        window_opens_at: str,
        window_closes_at: str,
        status: str,
        roster_snapshot: Sequence[str],
        occurrence_key: str,
    ) -> DailyCycleRecord:
        cycle_id = _opaque_id(cycle_id, "cycle_id")
        local_date = _local_date(local_date)
        timezone_name = _required_text(timezone_name, "timezone", maximum=128)
        scheduled_at = _timestamp_text(scheduled_at, "scheduled_at")
        window_opens_at = _timestamp_text(window_opens_at, "window_opens_at")
        window_closes_at = _timestamp_text(window_closes_at, "window_closes_at")
        if not window_opens_at <= scheduled_at <= window_closes_at:
            raise HRRepositoryValidationError("daily cycle window is invalid")
        status = _required_text(status, "status", maximum=32)
        occurrence_key = _opaque_id(occurrence_key, "occurrence_key")
        if isinstance(roster_snapshot, (str, bytes)):
            raise HRRepositoryValidationError("roster_snapshot must be a sequence of AI IDs")
        roster = tuple(_stable_ai_id(item) for item in roster_snapshot)
        if len(roster) > 1_000:
            raise HRRepositoryValidationError("roster_snapshot is too large")
        if len(set(roster)) != len(roster):
            raise HRRepositoryValidationError("roster_snapshot contains duplicate AI IDs")
        roster_json = _json_value(list(roster), "roster_snapshot", list)
        timestamp = self._timestamp()
        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT * FROM daily_cycles WHERE local_date = ? OR occurrence_key = ?",
                (local_date, occurrence_key),
            ).fetchone()
            if row is not None:
                existing = _cycle_from_row(row)
                expected = (
                    cycle_id,
                    local_date,
                    timezone_name,
                    scheduled_at,
                    window_opens_at,
                    window_closes_at,
                    status,
                    roster,
                    occurrence_key,
                )
                actual = (
                    existing.id,
                    existing.local_date,
                    existing.timezone,
                    existing.scheduled_at,
                    existing.window_opens_at,
                    existing.window_closes_at,
                    existing.status,
                    existing.roster_snapshot,
                    existing.occurrence_key,
                )
                if actual != expected:
                    raise HRRepositoryConflictError("daily cycle date or occurrence already exists")
                return existing
            try:
                connection.execute(
                    """INSERT INTO daily_cycles(
                           id, local_date, timezone, scheduled_at, window_opens_at,
                           window_closes_at, status, roster_snapshot_json, occurrence_key,
                           created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        cycle_id,
                        local_date,
                        timezone_name,
                        scheduled_at,
                        window_opens_at,
                        window_closes_at,
                        status,
                        roster_json,
                        occurrence_key,
                        timestamp,
                        timestamp,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise HRRepositoryConflictError("daily cycle identity already exists") from exc
            row = connection.execute("SELECT * FROM daily_cycles WHERE id = ?", (cycle_id,)).fetchone()
            return _cycle_from_row(row)

    def get_daily_cycle(self, cycle_id: str) -> DailyCycleRecord | None:
        cycle_id = _opaque_id(cycle_id, "cycle_id")
        with self._connection(readonly=True) as connection:
            row = connection.execute("SELECT * FROM daily_cycles WHERE id = ?", (cycle_id,)).fetchone()
            return _cycle_from_row(row) if row is not None else None

    def ensure_report_request(
        self,
        *,
        request_id: str,
        cycle_id: str,
        ai_id: str,
        occurrence_key: str,
        conversation_key: str,
    ) -> ReportRequestRecord:
        request_id = _opaque_id(request_id, "request_id")
        cycle_id = _opaque_id(cycle_id, "cycle_id")
        ai_id = _stable_ai_id(ai_id)
        occurrence_key = _opaque_id(occurrence_key, "occurrence_key")
        conversation_key = _opaque_id(conversation_key, "conversation_key")
        timestamp = self._timestamp()
        with self._write_transaction() as connection:
            row = connection.execute(
                """SELECT * FROM report_requests
                   WHERE (cycle_id = ? AND ai_id = ?) OR occurrence_key = ?""",
                (cycle_id, ai_id, occurrence_key),
            ).fetchone()
            if row is not None:
                existing = _request_from_row(row)
                if (
                    existing.id,
                    existing.cycle_id,
                    existing.ai_id,
                    existing.occurrence_key,
                    existing.conversation_key,
                ) != (request_id, cycle_id, ai_id, occurrence_key, conversation_key):
                    raise HRRepositoryConflictError("report request identity already exists")
                return existing
            try:
                connection.execute(
                    """INSERT INTO report_requests(
                           id, cycle_id, ai_id, status, occurrence_key, conversation_key,
                           created_at, updated_at
                       ) VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)""",
                    (
                        request_id,
                        cycle_id,
                        ai_id,
                        occurrence_key,
                        conversation_key,
                        timestamp,
                        timestamp,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise HRRepositoryConflictError("report request dependency is invalid") from exc
            row = connection.execute(
                "SELECT * FROM report_requests WHERE id = ?", (request_id,)
            ).fetchone()
            return _request_from_row(row)

    def claim_report_request(
        self,
        *,
        request_id: str,
        claimed_by: str,
        claim_token: str,
        claim_expires_at: str,
        now: str,
    ) -> ReportRequestRecord | None:
        request_id = _opaque_id(request_id, "request_id")
        claimed_by = _opaque_id(claimed_by, "claimed_by")
        claim_token = _opaque_id(claim_token, "claim_token")
        claim_expires_at = _timestamp_text(claim_expires_at, "claim_expires_at")
        now = _timestamp_text(now, "now")
        if claim_expires_at <= now:
            raise HRRepositoryValidationError("claim expiry must be after now")
        with self._write_transaction() as connection:
            updated = connection.execute(
                """UPDATE report_requests SET
                       status = 'claimed', claimed_by = ?, claim_token = ?,
                       claim_expires_at = ?, attempt_count = attempt_count + 1,
                       requested_at = COALESCE(requested_at, ?), updated_at = ?
                   WHERE id = ? AND status IN ('pending', 'retry', 'claimed')
                     AND (claim_token = '' OR claim_expires_at <= ?)""",
                (
                    claimed_by,
                    claim_token,
                    claim_expires_at,
                    now,
                    now,
                    request_id,
                    now,
                ),
            ).rowcount
            if updated != 1:
                return None
            row = connection.execute(
                "SELECT * FROM report_requests WHERE id = ?", (request_id,)
            ).fetchone()
            return _request_from_row(row)

    def finish_report_request(
        self,
        *,
        request_id: str,
        claim_token: str,
        status: str,
        finished_at: str,
        last_error: str = "",
    ) -> ReportRequestRecord:
        request_id = _opaque_id(request_id, "request_id")
        claim_token = _opaque_id(claim_token, "claim_token")
        status = _required_text(status, "status", maximum=32)
        if status not in {"submitted", "no_response", "failed", "skipped", "retry"}:
            raise HRRepositoryValidationError("unsupported report request terminal status")
        finished_at = _timestamp_text(finished_at, "finished_at")
        last_error = _optional_text(last_error, "last_error", maximum=2_000)
        with self._write_transaction() as connection:
            updated = connection.execute(
                """UPDATE report_requests SET
                       status = ?, responded_at = ?, last_error = ?, claim_token = '',
                       claimed_by = '', claim_expires_at = NULL, updated_at = ?
                   WHERE id = ? AND status = 'claimed' AND claim_token = ?
                     AND claim_expires_at > ?""",
                (status, finished_at, last_error, finished_at, request_id, claim_token, finished_at),
            ).rowcount
            if updated != 1:
                raise HRRepositoryConflictError("report request claim is stale or invalid")
            row = connection.execute(
                "SELECT * FROM report_requests WHERE id = ?", (request_id,)
            ).fetchone()
            return _request_from_row(row)

    def get_report_request(self, request_id: str) -> ReportRequestRecord | None:
        request_id = _opaque_id(request_id, "request_id")
        with self._connection(readonly=True) as connection:
            row = connection.execute(
                "SELECT * FROM report_requests WHERE id = ?", (request_id,)
            ).fetchone()
            return _request_from_row(row) if row is not None else None

    def save_daily_report(
        self,
        *,
        report_id: str,
        cycle_id: str | None,
        ai_id: str,
        local_date: str,
        submission_state: str,
        raw_response: str | None,
        normalized: object | None,
        normalizer_id: str = "",
        requested_at: str | None = None,
        window_closed_at: str | None = None,
        submitted_at: str | None = None,
        normalized_at: str | None = None,
        expected_revision: int | None = None,
    ) -> DailyReportRecord:
        report_id = _opaque_id(report_id, "report_id")
        cycle_id = _opaque_id(cycle_id, "cycle_id") if cycle_id is not None else None
        ai_id = _stable_ai_id(ai_id)
        local_date = _local_date(local_date)
        submission_state = _required_text(submission_state, "submission_state", maximum=32)
        if submission_state not in {
            "not_due",
            "waiting",
            "submitted",
            "normalized",
            "late_submitted",
            "not_submitted",
            "normalization_failed",
            "skipped",
            "complete",
            "failed",
        }:
            raise HRRepositoryValidationError("unsupported daily report state")
        raw_response = _raw_text(raw_response, "raw_response")
        normalized_json = (
            _json_value(normalized, "normalized", dict) if normalized is not None else None
        )
        normalizer_id = _optional_text(normalizer_id, "normalizer_id", maximum=256)
        timestamps = [requested_at, window_closed_at, submitted_at, normalized_at]
        requested_at, window_closed_at, submitted_at, normalized_at = (
            _timestamp_text(value, field)
            if value is not None
            else None
            for value, field in zip(
                timestamps,
                ("requested_at", "window_closed_at", "submitted_at", "normalized_at"),
            )
        )
        if expected_revision is not None and (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 0
        ):
            raise HRRepositoryValidationError("expected_revision must be a non-negative integer")
        timestamp = self._timestamp()
        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT * FROM daily_reports WHERE ai_id = ? AND local_date = ?",
                (ai_id, local_date),
            ).fetchone()
            current = _report_from_row(row) if row is not None else None
            current_revision = current.revision if current is not None else 0
            if expected_revision is not None and expected_revision != current_revision:
                raise HRRepositoryConflictError(
                    f"daily report revision is {current_revision}, expected {expected_revision}"
                )
            if current is not None:
                if current.raw_response is not None and raw_response not in (
                    None,
                    current.raw_response,
                ):
                    raise HRRepositoryConflictError("daily report raw response is immutable")
                raw_response = (
                    current.raw_response if current.raw_response is not None else raw_response
                )
                normalized_value = (
                    json.loads(normalized_json)
                    if normalized_json is not None
                    else current.normalized
                )
                normalized_json = (
                    _json_value(normalized_value, "normalized", dict)
                    if normalized_value is not None
                    else None
                )
                normalizer_id = normalizer_id or current.normalizer_id
                requested_at = requested_at or current.requested_at
                window_closed_at = window_closed_at or current.window_closed_at
                submitted_at = submitted_at or current.submitted_at
                normalized_at = normalized_at or current.normalized_at
            payload = (
                cycle_id,
                submission_state,
                raw_response,
                json.loads(normalized_json) if normalized_json is not None else None,
                normalizer_id,
                requested_at,
                window_closed_at,
                submitted_at,
                normalized_at,
            )
            if current is not None and payload == (
                current.cycle_id,
                current.submission_state,
                current.raw_response,
                current.normalized,
                current.normalizer_id,
                current.requested_at,
                current.window_closed_at,
                current.submitted_at,
                current.normalized_at,
            ):
                return current
            try:
                if current is None:
                    connection.execute(
                        """INSERT INTO daily_reports(
                               id, cycle_id, ai_id, local_date, submission_state,
                               raw_response, normalized_json, normalizer_id, requested_at,
                               window_closed_at, submitted_at, normalized_at, revision,
                               created_at, updated_at
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                        (
                            report_id,
                            cycle_id,
                            ai_id,
                            local_date,
                            submission_state,
                            raw_response,
                            normalized_json,
                            normalizer_id,
                            requested_at,
                            window_closed_at,
                            submitted_at,
                            normalized_at,
                            timestamp,
                            timestamp,
                        ),
                    )
                else:
                    if report_id != current.id:
                        raise HRRepositoryConflictError("daily report ID cannot change")
                    connection.execute(
                        """UPDATE daily_reports SET
                               cycle_id = ?, submission_state = ?, raw_response = ?,
                               normalized_json = ?, normalizer_id = ?, requested_at = ?,
                               window_closed_at = ?, submitted_at = ?, normalized_at = ?,
                               revision = revision + 1, updated_at = ?
                           WHERE id = ?""",
                        (*payload[:3], normalized_json, *payload[4:], timestamp, report_id),
                    )
            except sqlite3.IntegrityError as exc:
                raise HRRepositoryConflictError("daily report dependency or identity is invalid") from exc
            row = connection.execute("SELECT * FROM daily_reports WHERE id = ?", (report_id,)).fetchone()
            return _report_from_row(row)

    def get_daily_report(self, ai_id: str, local_date: str) -> DailyReportRecord | None:
        ai_id = _stable_ai_id(ai_id)
        local_date = _local_date(local_date)
        with self._connection(readonly=True) as connection:
            row = connection.execute(
                "SELECT * FROM daily_reports WHERE ai_id = ? AND local_date = ?",
                (ai_id, local_date),
            ).fetchone()
            return _report_from_row(row) if row is not None else None

    def list_daily_reports(
        self,
        *,
        ai_id: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> DailyReportPage:
        ai_id = _stable_ai_id(ai_id) if ai_id is not None else None
        limit = _page_limit(limit)
        after = _decode_cursor(cursor, fields=2)
        clauses = []
        parameters: list[object] = []
        if ai_id is not None:
            clauses.append("ai_id = ?")
            parameters.append(ai_id)
        if after is not None:
            local_date, cursor_ai_id = after
            if not isinstance(local_date, str) or not isinstance(cursor_ai_id, str):
                raise HRRepositoryValidationError("cursor is invalid")
            clauses.append("(local_date < ? OR (local_date = ? AND ai_id > ?))")
            parameters.extend((local_date, local_date, cursor_ai_id))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit + 1)
        with self._connection(readonly=True) as connection:
            rows = connection.execute(
                f"SELECT * FROM daily_reports{where} ORDER BY local_date DESC, ai_id ASC LIMIT ?",
                parameters,
            ).fetchall()
        items = tuple(_report_from_row(row) for row in rows[:limit])
        next_cursor = (
            _encode_cursor((items[-1].local_date, items[-1].ai_id))
            if len(rows) > limit
            else None
        )
        return DailyReportPage(items, next_cursor)

    def save_assessment(
        self,
        *,
        assessment_id: str,
        ai_id: str,
        local_date: str,
        status: str,
        workload: str,
        principal_contributions: object,
        rationale: str,
        blockers: object,
        strengths: object,
        improvements: object,
        runtime_diagnosis: str,
        information_sufficiency: str,
        evidence_version: str,
        hr_id: str,
        evidence: Sequence[dict[str, object]],
        revision_reason: str = "",
        expected_version: int | None = None,
    ) -> AssessmentRecord:
        assessment_id = _opaque_id(assessment_id, "assessment_id")
        ai_id = _stable_ai_id(ai_id)
        local_date = _local_date(local_date)
        status = _required_text(status, "status", maximum=32)
        workload = _required_text(workload, "workload", maximum=32)
        if workload not in {"low", "appropriate", "high", "overloaded", "insufficient_information"}:
            raise HRRepositoryValidationError("unsupported assessment workload")
        list_values = {}
        for field, value in (
            ("principal_contributions", principal_contributions),
            ("blockers", blockers),
            ("strengths", strengths),
            ("improvements", improvements),
        ):
            encoded = _json_value(value, field, list, maximum=10_000)
            if not all(isinstance(item, str) for item in json.loads(encoded)):
                raise HRRepositoryValidationError(f"{field} must contain strings")
            list_values[field] = encoded
        rationale = _required_text(rationale, "rationale", maximum=8_000)
        runtime_diagnosis = _required_text(runtime_diagnosis, "runtime_diagnosis", maximum=4_000)
        information_sufficiency = _required_text(
            information_sufficiency, "information_sufficiency", maximum=4_000
        )
        evidence_version = _opaque_id(evidence_version, "evidence_version")
        hr_id = _stable_ai_id(hr_id, "hr_id")
        revision_reason = _optional_text(revision_reason, "revision_reason", maximum=2_000)
        if expected_version is not None and (
            isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 0
        ):
            raise HRRepositoryValidationError("expected_version must be a non-negative integer")
        if isinstance(evidence, (str, bytes)) or len(evidence) > 100:
            raise HRRepositoryValidationError("assessment evidence count is invalid")
        evidence_rows = []
        for sequence, item in enumerate(evidence):
            if not isinstance(item, dict):
                raise HRRepositoryValidationError("assessment evidence must be objects")
            evidence_date = item.get("evidence_date")
            evidence_rows.append(
                AssessmentEvidenceRecord(
                    sequence=sequence,
                    evidence_type=_required_text(item.get("evidence_type"), "evidence_type", maximum=64),
                    reference_id=_opaque_id(item.get("reference_id"), "reference_id"),
                    summary=_required_text(item.get("summary"), "summary", maximum=2_000),
                    evidence_date=_local_date(evidence_date) if evidence_date is not None else None,
                    metadata=json.loads(
                        _json_value(item.get("metadata", {}), "evidence.metadata", dict, maximum=4_000)
                    ),
                )
            )
        timestamp = self._timestamp()
        with self._write_transaction() as connection:
            row = connection.execute(
                """SELECT * FROM assessments
                   WHERE ai_id = ? AND local_date = ? AND is_current = 1""",
                (ai_id, local_date),
            ).fetchone()
            current = _assessment_from_row(row) if row is not None else None
            current_version = current.version if current is not None else 0
            if current is not None and current.evidence_version == evidence_version:
                return self._load_assessment_evidence(connection, current)
            if expected_version is not None and expected_version != current_version:
                raise HRRepositoryConflictError(
                    f"assessment version is {current_version}, expected {expected_version}"
                )
            if current is not None:
                connection.execute(
                    "UPDATE assessments SET is_current = 0, updated_at = ? WHERE id = ?",
                    (timestamp, current.id),
                )
            version = current_version + 1
            try:
                connection.execute(
                    """INSERT INTO assessments(
                           id, ai_id, local_date, version, is_current, status, workload,
                           principal_contributions_json, rationale, blockers_json,
                           strengths_json, improvements_json, runtime_diagnosis,
                           information_sufficiency, evidence_version, hr_id,
                           revision_reason, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        assessment_id,
                        ai_id,
                        local_date,
                        version,
                        status,
                        workload,
                        list_values["principal_contributions"],
                        rationale,
                        list_values["blockers"],
                        list_values["strengths"],
                        list_values["improvements"],
                        runtime_diagnosis,
                        information_sufficiency,
                        evidence_version,
                        hr_id,
                        revision_reason,
                        timestamp,
                        timestamp,
                    ),
                )
                for item in evidence_rows:
                    connection.execute(
                        """INSERT INTO assessment_evidence(
                               assessment_id, sequence, evidence_type, reference_id,
                               summary, evidence_date, metadata_json
                           ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            assessment_id,
                            item.sequence,
                            item.evidence_type,
                            item.reference_id,
                            item.summary,
                            item.evidence_date,
                            json.dumps(
                                item.metadata,
                                ensure_ascii=False,
                                separators=(",", ":"),
                                sort_keys=True,
                            ),
                        ),
                    )
            except sqlite3.IntegrityError as exc:
                raise HRRepositoryConflictError("assessment identity or dependency is invalid") from exc
            row = connection.execute(
                "SELECT * FROM assessments WHERE id = ?", (assessment_id,)
            ).fetchone()
            return self._load_assessment_evidence(connection, _assessment_from_row(row))

    @staticmethod
    def _load_assessment_evidence(
        connection: sqlite3.Connection,
        assessment: AssessmentRecord,
    ) -> AssessmentRecord:
        rows = connection.execute(
            """SELECT sequence, evidence_type, reference_id, summary, evidence_date, metadata_json
               FROM assessment_evidence WHERE assessment_id = ? ORDER BY sequence""",
            (assessment.id,),
        ).fetchall()
        evidence = tuple(
            AssessmentEvidenceRecord(
                sequence=int(row["sequence"]),
                evidence_type=str(row["evidence_type"]),
                reference_id=str(row["reference_id"]),
                summary=str(row["summary"]),
                evidence_date=row["evidence_date"],
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        )
        return replace(assessment, evidence=evidence)

    def get_current_assessment(self, ai_id: str, local_date: str) -> AssessmentRecord | None:
        ai_id = _stable_ai_id(ai_id)
        local_date = _local_date(local_date)
        with self._connection(readonly=True) as connection:
            row = connection.execute(
                """SELECT * FROM assessments
                   WHERE ai_id = ? AND local_date = ? AND is_current = 1""",
                (ai_id, local_date),
            ).fetchone()
            if row is None:
                return None
            return self._load_assessment_evidence(connection, _assessment_from_row(row))

    def list_assessments(
        self,
        *,
        ai_id: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> AssessmentPage:
        ai_id = _stable_ai_id(ai_id) if ai_id is not None else None
        limit = _page_limit(limit)
        after = _decode_cursor(cursor, fields=3)
        clauses = []
        parameters: list[object] = []
        if ai_id is not None:
            clauses.append("ai_id = ?")
            parameters.append(ai_id)
        if after is not None:
            cursor_date, cursor_ai_id, version = after
            if (
                not isinstance(cursor_date, str)
                or not isinstance(cursor_ai_id, str)
                or isinstance(version, bool)
                or not isinstance(version, int)
            ):
                raise HRRepositoryValidationError("cursor is invalid")
            clauses.append(
                "(local_date < ? OR (local_date = ? AND ai_id > ?) "
                "OR (local_date = ? AND ai_id = ? AND version < ?))"
            )
            parameters.extend(
                (cursor_date, cursor_date, cursor_ai_id, cursor_date, cursor_ai_id, version)
            )
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit + 1)
        with self._connection(readonly=True) as connection:
            rows = connection.execute(
                f"SELECT * FROM assessments{where} "
                "ORDER BY local_date DESC, ai_id ASC, version DESC LIMIT ?",
                parameters,
            ).fetchall()
            items = tuple(
                self._load_assessment_evidence(connection, _assessment_from_row(row))
                for row in rows[:limit]
            )
        next_cursor = (
            _encode_cursor((items[-1].local_date, items[-1].ai_id, items[-1].version))
            if len(rows) > limit
            else None
        )
        return AssessmentPage(items, next_cursor)

    def rotate_access_grant(
        self,
        *,
        ai_id: str,
        key_id: str,
        secret_digest: str,
        issued_at: str,
        expected_key_id: str | None = None,
    ) -> AccessGrantRecord:
        """Insert or rotate a grant using a SHA-256 hex digest; raw grants are never accepted."""
        ai_id = _stable_ai_id(ai_id)
        key_id = _opaque_id(key_id, "key_id")
        if not isinstance(secret_digest, str) or SHA256_HEX_PATTERN.fullmatch(secret_digest) is None:
            raise HRRepositoryValidationError("secret_digest must be a lowercase SHA-256 hex digest")
        issued_at = _timestamp_text(issued_at, "issued_at")
        if expected_key_id is not None:
            expected_key_id = _opaque_id(expected_key_id, "expected_key_id")
        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT * FROM access_grants WHERE ai_id = ?", (ai_id,)
            ).fetchone()
            current = _grant_from_row(row) if row is not None else None
            if current is None:
                if expected_key_id is not None:
                    raise HRRepositoryConflictError("access grant does not exist")
                try:
                    connection.execute(
                        """INSERT INTO access_grants(
                               ai_id, key_id, secret_digest, status, issued_at, updated_at
                           ) VALUES (?, ?, ?, 'active', ?, ?)""",
                        (ai_id, key_id, secret_digest, issued_at, issued_at),
                    )
                except sqlite3.IntegrityError as exc:
                    raise HRRepositoryConflictError("access grant identity is invalid") from exc
            else:
                if expected_key_id is not None and current.key_id != expected_key_id:
                    raise HRRepositoryConflictError("access grant key changed concurrently")
                if (
                    current.key_id == key_id
                    and current.secret_digest == secret_digest
                    and current.status == "active"
                ):
                    return current
                try:
                    connection.execute(
                        """UPDATE access_grants SET
                               key_id = ?, secret_digest = ?, status = 'active',
                               issued_at = ?, rotated_at = ?, revoked_at = NULL,
                               revocation_reason = '', updated_at = ?
                           WHERE ai_id = ?""",
                        (key_id, secret_digest, issued_at, issued_at, issued_at, ai_id),
                    )
                except sqlite3.IntegrityError as exc:
                    raise HRRepositoryConflictError("access grant key is already in use") from exc
            row = connection.execute(
                "SELECT * FROM access_grants WHERE ai_id = ?", (ai_id,)
            ).fetchone()
            return _grant_from_row(row)

    def revoke_access_grant(
        self,
        *,
        ai_id: str,
        key_id: str,
        revoked_at: str,
        reason: str,
    ) -> AccessGrantRecord:
        ai_id = _stable_ai_id(ai_id)
        key_id = _opaque_id(key_id, "key_id")
        revoked_at = _timestamp_text(revoked_at, "revoked_at")
        reason = _required_text(reason, "reason", maximum=1_000)
        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT * FROM access_grants WHERE ai_id = ?", (ai_id,)
            ).fetchone()
            if row is None:
                raise HRRepositoryNotFoundError("access grant does not exist")
            current = _grant_from_row(row)
            if current.key_id != key_id:
                raise HRRepositoryConflictError("access grant key changed concurrently")
            if current.status == "revoked":
                if current.revocation_reason == reason:
                    return current
                raise HRRepositoryConflictError("access grant is already revoked")
            connection.execute(
                """UPDATE access_grants SET
                       status = 'revoked', revoked_at = ?, revocation_reason = ?, updated_at = ?
                   WHERE ai_id = ?""",
                (revoked_at, reason, revoked_at, ai_id),
            )
            row = connection.execute(
                "SELECT * FROM access_grants WHERE ai_id = ?", (ai_id,)
            ).fetchone()
            return _grant_from_row(row)

    def get_access_grant(self, ai_id: str) -> AccessGrantRecord | None:
        ai_id = _stable_ai_id(ai_id)
        with self._connection(readonly=True) as connection:
            row = connection.execute(
                "SELECT * FROM access_grants WHERE ai_id = ?", (ai_id,)
            ).fetchone()
            return _grant_from_row(row) if row is not None else None

    def record_successful_access(
        self,
        *,
        access_id: str,
        viewer_ai_id: str,
        target_ai_id: str,
        viewed_at: str,
        scope: str,
        request_source: str,
        occurrence_key: str,
    ) -> AccessLogRecord:
        access_id = _opaque_id(access_id, "access_id")
        viewer_ai_id = _stable_ai_id(viewer_ai_id, "viewer_ai_id")
        target_ai_id = _stable_ai_id(target_ai_id, "target_ai_id")
        if viewer_ai_id == target_ai_id:
            raise HRRepositoryValidationError("cross-Agent access requires different Agents")
        viewed_at = _timestamp_text(viewed_at, "viewed_at")
        scope = _required_text(scope, "scope", maximum=256)
        request_source = _required_text(request_source, "request_source", maximum=256)
        occurrence_key = _opaque_id(occurrence_key, "occurrence_key")
        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT * FROM access_log WHERE occurrence_key = ?", (occurrence_key,)
            ).fetchone()
            if row is not None:
                existing = _access_log_from_row(row)
                if (
                    existing.id,
                    existing.viewer_ai_id,
                    existing.target_ai_id,
                    existing.viewed_at,
                    existing.scope,
                    existing.request_source,
                ) != (
                    access_id,
                    viewer_ai_id,
                    target_ai_id,
                    viewed_at,
                    scope,
                    request_source,
                ):
                    raise HRRepositoryConflictError("access occurrence already records another view")
                return existing
            names = connection.execute(
                "SELECT ai_id, name FROM agents WHERE ai_id IN (?, ?)",
                (viewer_ai_id, target_ai_id),
            ).fetchall()
            name_by_id = {str(item["ai_id"]): str(item["name"]) for item in names}
            if set(name_by_id) != {viewer_ai_id, target_ai_id}:
                raise HRRepositoryNotFoundError("access viewer or target Agent does not exist")
            try:
                connection.execute(
                    """INSERT INTO access_log(
                           id, viewer_ai_id, viewer_name, target_ai_id, target_name,
                           viewed_at, scope, request_source, result, occurrence_key
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'success', ?)""",
                    (
                        access_id,
                        viewer_ai_id,
                        name_by_id[viewer_ai_id],
                        target_ai_id,
                        name_by_id[target_ai_id],
                        viewed_at,
                        scope,
                        request_source,
                        occurrence_key,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise HRRepositoryConflictError("access identity already exists") from exc
            row = connection.execute(
                "SELECT * FROM access_log WHERE id = ?", (access_id,)
            ).fetchone()
            return _access_log_from_row(row)

    def list_access_log(
        self,
        *,
        target_ai_id: str | None = None,
        viewer_ai_id: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> AccessLogPage:
        target_ai_id = (
            _stable_ai_id(target_ai_id, "target_ai_id") if target_ai_id is not None else None
        )
        viewer_ai_id = (
            _stable_ai_id(viewer_ai_id, "viewer_ai_id") if viewer_ai_id is not None else None
        )
        limit = _page_limit(limit)
        after = _decode_cursor(cursor, fields=2)
        clauses = []
        parameters: list[object] = []
        if target_ai_id is not None:
            clauses.append("target_ai_id = ?")
            parameters.append(target_ai_id)
        if viewer_ai_id is not None:
            clauses.append("viewer_ai_id = ?")
            parameters.append(viewer_ai_id)
        if after is not None:
            viewed_at, access_id = after
            if not isinstance(viewed_at, str) or not isinstance(access_id, str):
                raise HRRepositoryValidationError("cursor is invalid")
            clauses.append("(viewed_at < ? OR (viewed_at = ? AND id > ?))")
            parameters.extend((viewed_at, viewed_at, access_id))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit + 1)
        with self._connection(readonly=True) as connection:
            rows = connection.execute(
                f"SELECT * FROM access_log{where} ORDER BY viewed_at DESC, id ASC LIMIT ?",
                parameters,
            ).fetchall()
        items = tuple(_access_log_from_row(row) for row in rows[:limit])
        next_cursor = (
            _encode_cursor((items[-1].viewed_at, items[-1].id)) if len(rows) > limit else None
        )
        return AccessLogPage(items, next_cursor)

    def append_hr_activity(
        self,
        *,
        activity_id: str,
        ai_id: str | None,
        action: str,
        status: str,
        message: str = "",
        error: str = "",
        context: object | None = None,
        occurrence_key: str | None = None,
    ) -> HRActivityRecord:
        activity_id = _opaque_id(activity_id, "activity_id")
        ai_id = _stable_ai_id(ai_id) if ai_id is not None else None
        action = _required_text(action, "action", maximum=128)
        status = _required_text(status, "status", maximum=32)
        message = _optional_text(message, "message", maximum=2_000)
        error = _optional_text(error, "error", maximum=2_000)
        context_json = _json_value(context or {}, "context", dict, maximum=8_000)
        occurrence_key = (
            _opaque_id(occurrence_key, "occurrence_key") if occurrence_key is not None else None
        )
        timestamp = self._timestamp()
        with self._write_transaction() as connection:
            if occurrence_key is not None:
                row = connection.execute(
                    "SELECT * FROM hr_activity WHERE occurrence_key = ?", (occurrence_key,)
                ).fetchone()
                if row is not None:
                    existing = _activity_from_row(row)
                    expected = (
                        activity_id,
                        ai_id,
                        action,
                        status,
                        message,
                        error,
                        json.loads(context_json),
                    )
                    actual = (
                        existing.id,
                        existing.ai_id,
                        existing.action,
                        existing.status,
                        existing.message,
                        existing.error,
                        existing.context,
                    )
                    if actual != expected:
                        raise HRRepositoryConflictError("activity occurrence already exists")
                    return existing
            try:
                connection.execute(
                    """INSERT INTO hr_activity(
                           id, ai_id, action, status, message, error, context_json,
                           occurrence_key, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        activity_id,
                        ai_id,
                        action,
                        status,
                        message,
                        error,
                        context_json,
                        occurrence_key,
                        timestamp,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise HRRepositoryConflictError("activity identity or Agent is invalid") from exc
            row = connection.execute(
                "SELECT * FROM hr_activity WHERE id = ?", (activity_id,)
            ).fetchone()
            return _activity_from_row(row)

    def list_hr_activity(
        self,
        *,
        ai_id: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> HRActivityPage:
        ai_id = _stable_ai_id(ai_id) if ai_id is not None else None
        limit = _page_limit(limit)
        after = _decode_cursor(cursor, fields=2)
        clauses = []
        parameters: list[object] = []
        if ai_id is not None:
            clauses.append("ai_id = ?")
            parameters.append(ai_id)
        if after is not None:
            created_at, activity_id = after
            if not isinstance(created_at, str) or not isinstance(activity_id, str):
                raise HRRepositoryValidationError("cursor is invalid")
            clauses.append("(created_at < ? OR (created_at = ? AND id > ?))")
            parameters.extend((created_at, created_at, activity_id))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit + 1)
        with self._connection(readonly=True) as connection:
            rows = connection.execute(
                f"SELECT * FROM hr_activity{where} ORDER BY created_at DESC, id ASC LIMIT ?",
                parameters,
            ).fetchall()
        items = tuple(_activity_from_row(row) for row in rows[:limit])
        next_cursor = (
            _encode_cursor((items[-1].created_at, items[-1].id)) if len(rows) > limit else None
        )
        return HRActivityPage(items, next_cursor)

    def management_health(self) -> HRRepositoryHealth:
        """Return a read-only health snapshot for the authenticated management surface."""
        if not self.path.is_file():
            return HRRepositoryHealth(
                status="uninitialized",
                code="hr_repository_uninitialized",
                path=str(self.path),
                schema_version=None,
                target_schema_version=self.target_schema_version,
                database_bytes=0,
                page_count=0,
                page_size=0,
                integrity="not_checked",
                foreign_key_violations=0,
                error="HR repository is not initialized",
            )
        database_bytes = self.path.stat().st_size
        try:
            with self._connection(readonly=True) as connection:
                version = self._current_version(connection)
                integrity_row = connection.execute("PRAGMA quick_check(1)").fetchone()
                integrity = str(integrity_row[0] if integrity_row is not None else "unknown")
                page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
                page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
                foreign_key_violations = len(
                    connection.execute(
                        "SELECT 1 FROM pragma_foreign_key_check LIMIT 101"
                    ).fetchall()
                )
            healthy = integrity == "ok" and foreign_key_violations == 0
            return HRRepositoryHealth(
                status="ready" if healthy else "corrupt",
                code="ok" if healthy else "hr_repository_integrity_failed",
                path=str(self.path),
                schema_version=version,
                target_schema_version=self.target_schema_version,
                database_bytes=database_bytes,
                page_count=page_count,
                page_size=page_size,
                integrity=integrity,
                foreign_key_violations=foreign_key_violations,
                error="" if healthy else "HR repository integrity checks failed",
            )
        except HRRepositoryMigrationError as exc:
            return HRRepositoryHealth(
                status="migration_failed",
                code=exc.code,
                path=str(self.path),
                schema_version=None,
                target_schema_version=self.target_schema_version,
                database_bytes=database_bytes,
                page_count=0,
                page_size=0,
                integrity="not_checked",
                foreign_key_violations=0,
                error=str(exc),
            )
        except (sqlite3.DatabaseError, OSError, HRRepositoryError) as exc:
            return HRRepositoryHealth(
                status="corrupt",
                code=HRRepositoryCorruptionError.code,
                path=str(self.path),
                schema_version=None,
                target_schema_version=self.target_schema_version,
                database_bytes=database_bytes,
                page_count=0,
                page_size=0,
                integrity="failed",
                foreign_key_violations=0,
                error=f"HR repository health check failed: {exc.__class__.__name__}",
            )

    def management_export(
        self,
        table: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
        max_bytes: int = 256_000,
    ) -> HRExportPage:
        """Read one bounded JSON-safe page without creating a second authority."""
        table = _required_text(table, "table", maximum=64)
        if table not in _EXPORT_TABLES:
            raise HRRepositoryValidationError("table is not exportable")
        limit = _page_limit(limit)
        if (
            isinstance(max_bytes, bool)
            or not isinstance(max_bytes, int)
            or not MIN_EXPORT_BYTES <= max_bytes <= MAX_EXPORT_BYTES
        ):
            raise HRRepositoryValidationError(
                f"max_bytes must be between {MIN_EXPORT_BYTES} and {MAX_EXPORT_BYTES}"
            )
        decoded = _decode_cursor(cursor, fields=1)
        offset = 0
        if decoded is not None:
            offset = decoded[0]
            if (
                isinstance(offset, bool)
                or not isinstance(offset, int)
                or not 0 <= offset <= MAX_EXPORT_OFFSET
            ):
                raise HRRepositoryValidationError("cursor is invalid")
        order_by = ", ".join(_EXPORT_TABLES[table])
        columns = "*"
        if table == "access_grants":
            columns = (
                "ai_id, key_id, status, issued_at, rotated_at, revoked_at, "
                "revocation_reason, updated_at"
            )
        try:
            with self._connection(readonly=True) as connection:
                self._current_version(connection)
                rows = connection.execute(
                    f"SELECT {columns} FROM {table} ORDER BY {order_by} LIMIT ? OFFSET ?",
                    (limit + 1, offset),
                ).fetchall()
        except (sqlite3.DatabaseError, json.JSONDecodeError) as exc:
            raise HRRepositoryCorruptionError("HR repository export could not be read") from exc
        exported: list[dict[str, Any]] = []
        stopped_for_size = False
        for row in rows[:limit]:
            item = dict(row)
            try:
                for field in tuple(item):
                    if field in _EXPORT_JSON_FIELDS:
                        decoded_value = json.loads(item.pop(field)) if item[field] is not None else None
                        item[field.removesuffix("_json")] = decoded_value
            except json.JSONDecodeError as exc:
                raise HRRepositoryCorruptionError(
                    f"HR repository {table} contains invalid JSON"
                ) from exc
            tentative = (*exported, item)
            size = len(
                json.dumps(
                    {"table": table, "rows": tentative},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            if size > max_bytes:
                if not exported:
                    raise HRRepositoryValidationError("one export row exceeds max_bytes")
                stopped_for_size = True
                break
            exported.append(item)
        has_more = stopped_for_size or len(rows) > len(exported)
        next_cursor = _encode_cursor((offset + len(exported),)) if has_more else None
        payload_size = len(
            json.dumps(
                {"table": table, "rows": exported, "nextCursor": next_cursor},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        if payload_size > max_bytes:
            raise HRRepositoryValidationError("export envelope exceeds max_bytes")
        return HRExportPage(
            table=table,
            rows=tuple(exported),
            next_cursor=next_cursor,
            byte_size=payload_size,
        )
