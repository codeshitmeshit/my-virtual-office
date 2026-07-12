#!/usr/bin/env python3
"""Offline, idempotent migration from two legacy Meeting stores to one Store."""

from __future__ import annotations

import argparse
import copy
import errno
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.meeting_repository import (
    LEGACY_EXECUTABLE_FILENAME, LEGACY_REQUEST_FILENAME, UNIFIED_FILENAME,
    MeetingDomainRepository, MeetingStoreError, acquire_active_lock, merge_legacy,
    normalize_store, read_regular_no_follow, source_digest,
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status-dir", required=True)
    parser.add_argument("--apply", action="store_true", help="write backups and unified Store")
    parser.add_argument("--report", help="report path (defaults inside status directory)")
    return parser.parse_args()


def _inside(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _decode(content: bytes, label: str) -> dict:
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MeetingStoreError(f"Invalid {label} JSON", code="meeting_store_migration_input_invalid") from exc
    if not isinstance(value, dict):
        raise MeetingStoreError(f"Invalid {label} root", code="meeting_store_migration_input_invalid")
    return value


def _counts(data):
    return {key: len(data[key]) for key in ("meetings", "events", "occupancy", "requests")}


def _relationship_checks(data):
    return {
        "eventOwnership": {"status": "pass", "checked": len(data["events"])},
        "requestMeetingLinks": {
            "status": "pass",
            "checked": sum(1 for request in data["requests"].values() if (request.get("conversion") or {}).get("meetingId")),
        },
        "occupancyCompatibility": {"status": "pass", "checked": len(data["occupancy"])},
        "identityAndStatus": {"status": "pass", "checked": len(data["meetings"]) + len(data["requests"])},
    }


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(descriptor)
    except OSError as exc:
        unsupported = {errno.EINVAL, errno.EBADF}
        for name in ("ENOTSUP", "EOPNOTSUPP"):
            value = getattr(errno, name, None)
            if value is not None: unsupported.add(value)
        if exc.errno not in unsupported:
            raise
    finally:
        os.close(descriptor)


def _semantic(data):
    return {
        key: copy.deepcopy(data[key])
        for key in ("schemaVersion", "meetings", "events", "occupancy", "requests", "idempotency")
    }


def _write_private(path: Path, content: bytes, *, exclusive: bool = False) -> None:
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= os.O_EXCL if exclusive else os.O_TRUNC
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write while persisting migration data")
            view = view[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _write_report(path: Path, report: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        _write_private(temporary, json.dumps(report, indent=2, sort_keys=True).encode("utf-8"), exclusive=True)
        os.replace(temporary, path)
        os.chmod(path, 0o600, follow_symlinks=False)
        _fsync_directory(path.parent)
    finally:
        try: temporary.unlink()
        except FileNotFoundError: pass


def main() -> int:
    args = parse_args()
    status = Path(args.status_dir).expanduser().resolve()
    executable_path = status / LEGACY_EXECUTABLE_FILENAME
    request_path = status / LEGACY_REQUEST_FILENAME
    destination = status / UNIFIED_FILENAME
    report_path = Path(args.report).expanduser().resolve() if args.report else status / "meeting-store-migration-report.json"
    report = {"ok": False, "mode": "apply" if args.apply else "dry-run", "status": "failed"}
    report_safe = False
    cutover_started = False
    try:
        if not all(_inside(status, path) for path in (executable_path, request_path, destination, report_path)):
            raise MeetingStoreError("Migration paths must stay inside status directory", code="meeting_store_migration_path_invalid")
        protected = (executable_path, request_path, destination, status / "meeting-store-active.lock")
        if report_path in protected or any(
            report_path.exists() and path.exists() and os.path.samefile(report_path, path) for path in protected
        ):
            raise MeetingStoreError("Migration report conflicts with a protected path", code="meeting_store_migration_path_invalid")
        report_safe = True
        try:
            lock_fd = acquire_active_lock(status)
        except (BlockingIOError, MeetingStoreError, OSError) as exc:
            raise MeetingStoreError("Stop the server before Meeting migration", code="meeting_store_server_running") from exc
        executable_bytes = read_regular_no_follow(executable_path)
        request_bytes = read_regular_no_follow(request_path)
        digest = source_digest(executable_bytes, request_bytes)
        merged = merge_legacy(_decode(executable_bytes, "executable Meeting"), _decode(request_bytes, "Meeting request"), digest=digest)
        report.update({
            "ok": True, "status": "validated", "sourceDigest": digest, "counts": _counts(merged),
            "relationshipChecks": _relationship_checks(merged),
            "sourceBytes": {"executable": len(executable_bytes), "requests": len(request_bytes)},
            "destination": destination.name,
        })
        if destination.exists():
            existing = MeetingDomainRepository(status).snapshot()
            if (existing.get("migration") or {}).get("sourceDigest") == digest:
                if _semantic(existing) != _semantic(merged):
                    raise MeetingStoreError("Existing migration content does not match", code="meeting_store_conflict")
                report["status"] = "already_migrated"
                report["alreadyMigrated"] = True
                _write_report(report_path, report)
                print(json.dumps(report, indent=2, sort_keys=True))
                os.close(lock_fd)
                return 0
            raise MeetingStoreError("Unified Store has a different source digest", code="migration_source_changed")
        if args.apply:
            if read_regular_no_follow(executable_path) != executable_bytes or read_regular_no_follow(request_path) != request_bytes:
                raise MeetingStoreError("Migration source changed during validation", code="migration_source_changed")
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backups = {
                "executable": status / f"{LEGACY_EXECUTABLE_FILENAME}.backup-{timestamp}",
                "requests": status / f"{LEGACY_REQUEST_FILENAME}.backup-{timestamp}",
            }
            _write_private(backups["executable"], executable_bytes, exclusive=True)
            _write_private(backups["requests"], request_bytes, exclusive=True)
            merged["migration"]["reportFile"] = report_path.name
            report.update({
                "status": "migrated", "backups": {key: path.name for key, path in backups.items()},
            })
            with tempfile.TemporaryDirectory(prefix="meeting-migration-candidate-", dir=status) as candidate_dir:
                candidate_repo = MeetingDomainRepository(candidate_dir)
                candidate_repo._write_atomic(merged)
                candidate = candidate_repo.snapshot()
                if _semantic(candidate) != _semantic(merged):
                    raise MeetingStoreError("Unified Store candidate verification failed", code="meeting_store_migration_verify_failed")
            prepared = {**report, "status": "prepared", "ok": False}
            _write_report(report_path, prepared)
            if read_regular_no_follow(executable_path) != executable_bytes or read_regular_no_follow(request_path) != request_bytes:
                raise MeetingStoreError("Migration source changed before cutover", code="migration_source_changed")
            repository = MeetingDomainRepository(status)
            cutover_started = True
            repository._write_atomic(merged)
            written = repository.snapshot()
            if _semantic(written) != _semantic(merged):
                destination.unlink(missing_ok=True)
                raise MeetingStoreError("Unified Store verification failed", code="meeting_store_migration_verify_failed")
            report["unifiedBytes"] = destination.stat().st_size
        _write_report(report_path, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        os.close(lock_fd)
        return 0
    except (MeetingStoreError, OSError, RecursionError, MemoryError, TypeError, ValueError) as exc:
        if cutover_started:
            try: destination.unlink()
            except FileNotFoundError: pass
        if "lock_fd" in locals() and isinstance(lock_fd, int):
            try: os.close(lock_fd)
            except OSError: pass
        report.update({"ok": False, "status": "failed", "code": getattr(exc, "code", "meeting_store_migration_failed"), "error": str(exc)})
        try:
            status.mkdir(parents=True, exist_ok=True)
            if report_safe and _inside(status, report_path):
                _write_report(report_path, report)
        except OSError:
            pass
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
