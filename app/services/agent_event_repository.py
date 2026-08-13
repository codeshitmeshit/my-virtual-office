"""SQLite authority for bounded Agent/Codex activity events."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Mapping, Sequence

from .sqlite_runtime import connect_sqlite


DATABASE_FILENAME = "agent-events.sqlite3"
LEGACY_FILENAME = "codex-activity.json"
SCHEMA_VERSION = 1
DEFAULT_MAX_EVENTS = 5_000


def _encoded(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class AgentEventRepository:
    def __init__(self, status_dir: str | os.PathLike[str], *, max_events: int = DEFAULT_MAX_EVENTS) -> None:
        self.status_dir = Path(status_dir).expanduser().resolve()
        self.path = self.status_dir / DATABASE_FILENAME
        self.legacy_path = self.status_dir / LEGACY_FILENAME
        self.max_events = max(1, int(max_events))
        self._lock = threading.RLock()
        self._initialized = False

    def initialize(self, *, allow_legacy: bool = False) -> None:
        with self._lock:
            if self._initialized and self.path.exists():
                return
            if not self.path.exists() and self.legacy_path.exists() and not allow_legacy:
                raise RuntimeError("Agent event store migration is required")
            connection = connect_sqlite(self.path)
            try:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS agent_events (
                        ordinal INTEGER PRIMARY KEY AUTOINCREMENT,
                        agent_id TEXT NOT NULL,
                        conversation_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        provider_sequence INTEGER NOT NULL,
                        event_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        timestamp_ms INTEGER NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS agent_events_scope_sequence_idx
                        ON agent_events(agent_id, conversation_id, sequence, ordinal);
                    CREATE INDEX IF NOT EXISTS agent_events_scope_time_idx
                        ON agent_events(agent_id, conversation_id, timestamp_ms, ordinal);
                    """
                )
                connection.execute(
                    "INSERT OR IGNORE INTO metadata(key, value) VALUES('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
                self._initialized = True
            finally:
                connection.close()

    @staticmethod
    def _columns(event: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            str(event.get("agentId") or ""),
            str(event.get("conversationId") or ""),
            int(event.get("sequence") or 0),
            int(event.get("providerSequence") or 0),
            str(event.get("id") or ""),
            str(event.get("type") or ""),
            str(event.get("status") or ""),
            int(event.get("ts") or event.get("timestamp") or 0),
            _encoded(event),
        )

    def _insert(self, connection: sqlite3.Connection, event: Mapping[str, Any]) -> None:
        connection.execute(
            """INSERT INTO agent_events(
                   agent_id, conversation_id, sequence, provider_sequence,
                   event_id, event_type, status, timestamp_ms, payload_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            self._columns(event),
        )

    def _trim(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """DELETE FROM agent_events
               WHERE ordinal <= COALESCE(
                   (SELECT ordinal FROM agent_events ORDER BY ordinal DESC LIMIT 1 OFFSET ?),
                   0
               )""",
            (self.max_events,),
        )

    @staticmethod
    def _decode_rows(rows: Sequence[sqlite3.Row]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for row in rows:
            try:
                value = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise RuntimeError("agent event database contains invalid payload JSON") from exc
            if isinstance(value, dict):
                events.append(value)
        return events

    def load_all(self) -> list[dict[str, Any]]:
        self.initialize()
        with self._lock:
            connection = connect_sqlite(self.path, readonly=True)
            try:
                rows = connection.execute(
                    "SELECT payload_json FROM agent_events ORDER BY ordinal"
                ).fetchall()
            finally:
                connection.close()
            return self._decode_rows(rows)

    def list_scope(self, agent_id: str, conversation_id: str, *, after: int = 0) -> list[dict[str, Any]]:
        self.initialize()
        connection = connect_sqlite(self.path, readonly=True)
        try:
            rows = connection.execute(
                """SELECT payload_json FROM agent_events
                   WHERE agent_id = ? AND conversation_id = ? AND sequence > ?
                   ORDER BY sequence, ordinal""",
                (str(agent_id), str(conversation_id), int(after or 0)),
            ).fetchall()
            return self._decode_rows(rows)
        finally:
            connection.close()

    def max_sequence(self, agent_id: str, conversation_id: str) -> int:
        self.initialize()
        connection = connect_sqlite(self.path, readonly=True)
        try:
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) FROM agent_events WHERE agent_id = ? AND conversation_id = ?",
                (str(agent_id), str(conversation_id)),
            ).fetchone()
            return int(row[0] if row else 0)
        finally:
            connection.close()

    def append(self, event: Mapping[str, Any]) -> None:
        """Append one durable event without loading or rewriting prior events."""
        self.initialize()
        with self._lock:
            connection = connect_sqlite(self.path)
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._insert(connection, event)
                self._trim(connection)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def import_events(self, events: Sequence[Mapping[str, Any]], *, source_digest: str) -> dict[str, Any]:
        self.initialize(allow_legacy=True)
        bounded = [dict(item) for item in events[-self.max_events :] if isinstance(item, Mapping)]
        with self._lock:
            connection = connect_sqlite(self.path)
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = int(connection.execute("SELECT COUNT(*) FROM agent_events").fetchone()[0])
                digest_row = connection.execute(
                    "SELECT value FROM metadata WHERE key = 'source_digest'"
                ).fetchone()
                if existing:
                    if digest_row and str(digest_row[0]) == source_digest:
                        connection.rollback()
                        return {"status": "already_migrated", "events": existing}
                    raise RuntimeError("agent event database already contains different data")
                for event in bounded:
                    self._insert(connection, event)
                connection.execute(
                    "INSERT OR REPLACE INTO metadata(key, value) VALUES('source_digest', ?)",
                    (source_digest,),
                )
                connection.commit()
                return {"status": "migrated", "events": len(bounded)}
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def count(self) -> int:
        self.initialize()
        connection = connect_sqlite(self.path, readonly=True)
        try:
            return int(connection.execute("SELECT COUNT(*) FROM agent_events").fetchone()[0])
        finally:
            connection.close()
