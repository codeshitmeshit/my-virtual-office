#!/usr/bin/env python3
"""Validate or migrate Agent events and Meeting domain JSON stores to SQLite."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.agent_event_repository import (  # noqa: E402
    AgentEventRepository,
    DATABASE_FILENAME as AGENT_DATABASE_FILENAME,
    LEGACY_FILENAME as AGENT_LEGACY_FILENAME,
)
from services.meeting_repository import (  # noqa: E402
    DATABASE_FILENAME as MEETING_DATABASE_FILENAME,
    LEGACY_EXECUTABLE_FILENAME,
    LEGACY_REQUEST_FILENAME,
    LEGACY_UNIFIED_FILENAME,
    MeetingDomainRepository,
    MeetingStoreError,
    acquire_active_lock,
    merge_legacy,
    normalize_store,
    read_regular_no_follow,
    source_digest,
)
from services.sqlite_runtime import close_sqlite_path  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status-dir", required=True)
    parser.add_argument("--apply", action="store_true", help="create backups and cut over to SQLite")
    parser.add_argument("--report", help="defaults to performance-store-migration-report.json")
    return parser.parse_args()


def _digest(label: str, content: bytes) -> str:
    value = hashlib.sha256()
    value.update(label.encode("utf-8") + b"\0")
    value.update(len(content).to_bytes(8, "big"))
    value.update(content)
    return value.hexdigest()


def _decode_object(content: bytes, label: str) -> dict:
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise MeetingStoreError(f"Invalid {label} JSON", code="store_migration_input_invalid") from exc
    if not isinstance(value, dict):
        raise MeetingStoreError(f"Invalid {label} root", code="store_migration_input_invalid")
    return value


def _decode_events(content: bytes) -> list[dict]:
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise MeetingStoreError("Invalid Agent event JSON", code="store_migration_input_invalid") from exc
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise MeetingStoreError("Agent event store must be an array of objects", code="store_migration_input_invalid")
    return value


def _meeting_source(status: Path) -> tuple[dict | None, dict[str, bytes], str]:
    unified = status / LEGACY_UNIFIED_FILENAME
    if unified.exists():
        content = read_regular_no_follow(unified)
        data = normalize_store(_decode_object(content, "Meeting domain"), strict=True)
        digest = _digest(LEGACY_UNIFIED_FILENAME, content)
        data["migration"] = {
            "sourceDigest": digest,
            "migratedAt": datetime.now(timezone.utc).isoformat(),
            "reportFile": "performance-store-migration-report.json",
        }
        return data, {LEGACY_UNIFIED_FILENAME: content}, digest
    contents: dict[str, bytes] = {}
    for name in (LEGACY_EXECUTABLE_FILENAME, LEGACY_REQUEST_FILENAME):
        path = status / name
        if path.exists():
            contents[name] = read_regular_no_follow(path)
    if not contents:
        return None, {}, ""
    executable = contents.get(LEGACY_EXECUTABLE_FILENAME, b"{}")
    requests = contents.get(LEGACY_REQUEST_FILENAME, b"{}")
    digest = source_digest(executable, requests)
    return merge_legacy(
        _decode_object(executable, "executable Meeting"),
        _decode_object(requests, "Meeting request"),
        digest=digest,
    ), contents, digest


def _agent_source(status: Path) -> tuple[list[dict] | None, dict[str, bytes], str]:
    path = status / AGENT_LEGACY_FILENAME
    if not path.exists():
        return None, {}, ""
    content = read_regular_no_follow(path)
    return _decode_events(content), {AGENT_LEGACY_FILENAME: content}, _digest(AGENT_LEGACY_FILENAME, content)


def _write_private(path: Path, content: bytes, *, exclusive: bool = False) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    flags |= os.O_EXCL if exclusive else os.O_TRUNC
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short migration write")
            view = view[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)


def _write_report(path: Path, report: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        _write_private(temporary, json.dumps(report, indent=2, sort_keys=True).encode("utf-8"), exclusive=True)
        os.replace(temporary, path)
        os.chmod(path, 0o600, follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)


def _finalize_candidate(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
        if not row or row[0] != "ok":
            raise MeetingStoreError("SQLite integrity check failed", code="store_migration_verify_failed")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.execute("PRAGMA journal_mode=DELETE")
    finally:
        connection.close()


def _install_database(candidate: Path, destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.migration-{os.getpid()}")
    try:
        _write_private(temporary, candidate.read_bytes(), exclusive=True)
        os.replace(temporary, destination)
        os.chmod(destination, 0o600, follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)


def _agent_already_migrated(status: Path, digest: str, expected: int) -> bool:
    path = status / AGENT_DATABASE_FILENAME
    if not path.exists():
        return False
    connection = sqlite3.connect(path)
    try:
        row = connection.execute("SELECT value FROM metadata WHERE key='source_digest'").fetchone()
        count = int(connection.execute("SELECT COUNT(*) FROM agent_events").fetchone()[0])
        return bool(row and str(row[0]) == digest and count == min(expected, 5_000))
    finally:
        connection.close()


def _meeting_already_migrated(status: Path, digest: str) -> bool:
    path = status / MEETING_DATABASE_FILENAME
    if not path.exists():
        return False
    return str((MeetingDomainRepository(status).export_for_migration().get("migration") or {}).get("sourceDigest") or "") == digest


def main() -> int:
    args = parse_args()
    status = Path(args.status_dir).expanduser().resolve()
    report_path = Path(args.report).expanduser().resolve() if args.report else status / "performance-store-migration-report.json"
    report = {"ok": False, "mode": "apply" if args.apply else "dry-run", "status": "failed", "stores": {}}
    installed: list[Path] = []
    lock_fd = None
    try:
        status.mkdir(parents=True, exist_ok=True)
        report_path.relative_to(status)
        protected = {
            status / AGENT_LEGACY_FILENAME, status / LEGACY_UNIFIED_FILENAME,
            status / LEGACY_EXECUTABLE_FILENAME, status / LEGACY_REQUEST_FILENAME,
            status / AGENT_DATABASE_FILENAME, status / MEETING_DATABASE_FILENAME,
            status / "meeting-store-active.lock",
        }
        if report_path in protected:
            raise MeetingStoreError("Migration report conflicts with a protected path", code="store_migration_path_invalid")
        try:
            lock_fd = acquire_active_lock(status)
        except (BlockingIOError, OSError, MeetingStoreError) as exc:
            raise MeetingStoreError("Stop the server before store migration", code="store_migration_server_running") from exc

        agent_events, agent_sources, agent_digest = _agent_source(status)
        meeting_data, meeting_sources, meeting_digest = _meeting_source(status)
        report["stores"]["agentEvents"] = {
            "status": "validated" if agent_events is not None else "no_source",
            "records": len(agent_events or []), "sourceDigest": agent_digest,
            "destination": AGENT_DATABASE_FILENAME,
        }
        report["stores"]["meetings"] = {
            "status": "validated" if meeting_data is not None else "no_source",
            "records": ({key: len(meeting_data[key]) for key in ("meetings", "events", "occupancy", "requests")} if meeting_data else {}),
            "sourceDigest": meeting_digest, "destination": MEETING_DATABASE_FILENAME,
        }
        if agent_events is not None and _agent_already_migrated(status, agent_digest, len(agent_events)):
            report["stores"]["agentEvents"]["status"] = "already_migrated"
        if meeting_data is not None and _meeting_already_migrated(status, meeting_digest):
            report["stores"]["meetings"]["status"] = "already_migrated"
        report.update({"ok": True, "status": "validated"})
        if not args.apply:
            _write_report(report_path, report)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0

        current_statuses = {store["status"] for store in report["stores"].values()}
        if current_statuses <= {"already_migrated", "no_source"}:
            report["status"] = "already_migrated"
            _write_report(report_path, report)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        all_sources = {**agent_sources, **meeting_sources}
        backups = {}
        for name, content in all_sources.items():
            backup = status / f"{name}.backup-{timestamp}"
            _write_private(backup, content, exclusive=True)
            backups[name] = backup.name

        with tempfile.TemporaryDirectory(prefix="performance-store-migration-", dir=status) as temporary_dir:
            candidate_dir = Path(temporary_dir)
            candidates: list[tuple[Path, Path, str]] = []
            if agent_events is not None and report["stores"]["agentEvents"]["status"] != "already_migrated":
                destination = status / AGENT_DATABASE_FILENAME
                if destination.exists():
                    raise MeetingStoreError("Agent event database already exists", code="store_migration_destination_exists")
                repository = AgentEventRepository(candidate_dir)
                repository.import_events(agent_events, source_digest=agent_digest)
                close_sqlite_path(repository.path)
                _finalize_candidate(repository.path)
                candidates.append((repository.path, destination, "agentEvents"))
            if meeting_data is not None and report["stores"]["meetings"]["status"] != "already_migrated":
                destination = status / MEETING_DATABASE_FILENAME
                if destination.exists():
                    raise MeetingStoreError("Meeting database already exists", code="store_migration_destination_exists")
                meeting_data["migration"]["reportFile"] = report_path.name
                repository = MeetingDomainRepository(candidate_dir)
                repository.import_store(meeting_data)
                close_sqlite_path(repository.path)
                _finalize_candidate(repository.path)
                candidates.append((repository.path, destination, "meetings"))

            _write_report(report_path, {**report, "ok": False, "status": "prepared", "backups": backups})
            for name, before in all_sources.items():
                if read_regular_no_follow(status / name) != before:
                    raise MeetingStoreError("Migration source changed before cutover", code="migration_source_changed")
            for candidate, destination, store_name in candidates:
                _install_database(candidate, destination)
                installed.append(destination)
                _finalize_candidate(destination)
                report["stores"][store_name]["status"] = "migrated"

        statuses = {store["status"] for store in report["stores"].values()}
        final_status = "already_migrated" if statuses <= {"already_migrated", "no_source"} else "migrated"
        report.update({"ok": True, "status": final_status, "backups": backups})
        _write_report(report_path, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (MeetingStoreError, OSError, sqlite3.DatabaseError, ValueError, TypeError, MemoryError, RecursionError) as exc:
        for path in installed:
            path.unlink(missing_ok=True)
            path.with_name(path.name + "-wal").unlink(missing_ok=True)
            path.with_name(path.name + "-shm").unlink(missing_ok=True)
        report.update({"ok": False, "status": "failed", "code": getattr(exc, "code", "store_migration_failed"), "error": str(exc)})
        try:
            _write_report(report_path, report)
        except OSError:
            pass
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1
    finally:
        if lock_fd is not None:
            os.close(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
