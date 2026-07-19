"""Schema, path, connection, and migration guarantees for HR SQLite."""

import sqlite3
import stat
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_repository import (
    DATABASE_FILENAME,
    DEFAULT_MIGRATIONS,
    HRMigration,
    HRRepository,
    HRRepositoryMigrationError,
    HRRepositoryPathError,
    MAX_BUSY_TIMEOUT_MS,
    MIN_BUSY_TIMEOUT_MS,
    SCHEMA_NAME,
)


EXPECTED_TABLES = {
    "metadata",
    "agents",
    "agent_identity_history",
    "introductions",
    "daily_cycles",
    "report_requests",
    "daily_reports",
    "assessments",
    "assessment_jobs",
    "assessment_evidence",
    "access_grants",
    "access_log",
    "hr_activity",
}
FIXED_NOW = datetime(2026, 7, 19, 18, 30, tzinfo=timezone.utc)


def repository(tmp_path, **kwargs):
    return HRRepository(tmp_path / "status", clock=lambda: FIXED_NOW, **kwargs)


def test_construction_has_no_side_effect_and_initialize_creates_fixed_authority(tmp_path):
    repo = repository(tmp_path)
    assert repo.path == tmp_path / "status" / "human-resources" / DATABASE_FILENAME
    assert not repo.path.exists()

    info = repo.initialize()
    assert repo.path.is_file()
    assert stat.S_IMODE(repo.path.stat().st_mode) == 0o600
    assert info.path == str(repo.path)
    assert info.schema_name == SCHEMA_NAME
    assert info.schema_version == 2
    assert info.initialized_at == FIXED_NOW.isoformat()
    assert set(repo.table_names()) == EXPECTED_TABLES

    repeated = repo.initialize()
    assert repeated == info
    assert not list(repo.hr_dir.glob("*.tmp"))


def test_schema_metadata_matches_sqlite_user_version(tmp_path):
    repo = repository(tmp_path)
    repo.initialize()
    with sqlite3.connect(repo.path) as connection:
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
    assert user_version == 2
    assert metadata == {
        "initialized_at": FIXED_NOW.isoformat(),
        "last_migration": "add_access_grant_expiry",
        "schema_name": SCHEMA_NAME,
        "schema_version": "2",
    }


def test_existing_v1_repository_migrates_access_grant_expiry_in_place(tmp_path):
    v1_repository = repository(tmp_path, migrations=(DEFAULT_MIGRATIONS[0],))
    assert v1_repository.initialize().schema_version == 1
    with sqlite3.connect(v1_repository.path) as connection:
        before = {row[1] for row in connection.execute("PRAGMA table_info(access_grants)")}
    assert "expires_at" not in before

    upgraded = repository(tmp_path)
    assert upgraded.initialize().schema_version == 2
    with sqlite3.connect(upgraded.path) as connection:
        after = {row[1] for row in connection.execute("PRAGMA table_info(access_grants)")}
    assert "expires_at" in after


def test_connections_enable_foreign_keys_bound_busy_timeout_and_begin_immediate(tmp_path):
    repo = repository(tmp_path, busy_timeout_ms=1_234)
    repo.initialize()
    settings = repo.connection_settings()
    assert settings["foreignKeys"] is True
    assert settings["busyTimeoutMs"] == 1_234
    assert settings["journalMode"] in {"delete", "wal"}

    with pytest.raises(sqlite3.IntegrityError):
        with repo._write_transaction() as connection:
            assert connection.in_transaction is True
            assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            connection.execute(
                """INSERT INTO agent_identity_history(
                       ai_id, name, status, source, observed_at
                   ) VALUES ('missing', 'Missing', 'active', 'test', 'now')"""
            )
    with sqlite3.connect(repo.path) as connection:
        assert connection.execute("SELECT count(*) FROM agent_identity_history").fetchone()[0] == 0


@pytest.mark.parametrize("value", (True, 99, 30_001, 1.5, "5000"))
def test_busy_timeout_validation_rejects_unbounded_or_non_integer_values(tmp_path, value):
    with pytest.raises(ValueError, match="busy_timeout_ms"):
        repository(tmp_path, busy_timeout_ms=value)
    assert not (tmp_path / "status").exists()


def test_busy_timeout_accepts_documented_boundaries(tmp_path):
    assert repository(tmp_path, busy_timeout_ms=MIN_BUSY_TIMEOUT_MS).busy_timeout_ms == 100
    assert repository(tmp_path, busy_timeout_ms=MAX_BUSY_TIMEOUT_MS).busy_timeout_ms == 30_000


def test_status_directory_symlink_is_rejected_without_touching_target(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    status = tmp_path / "status"
    status.symlink_to(outside, target_is_directory=True)
    repo = HRRepository(status)
    with pytest.raises(HRRepositoryPathError, match="status directory"):
        repo.initialize()
    assert list(outside.iterdir()) == []


def test_hr_directory_and_database_symlinks_are_rejected(tmp_path):
    status = tmp_path / "status"
    status.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    hr_dir = status / "human-resources"
    hr_dir.symlink_to(outside, target_is_directory=True)
    with pytest.raises(HRRepositoryPathError, match="symbolic link"):
        HRRepository(status).initialize()
    assert list(outside.iterdir()) == []

    hr_dir.unlink()
    hr_dir.mkdir()
    outside_db = outside / "outside.sqlite3"
    outside_db.write_bytes(b"sentinel")
    (hr_dir / DATABASE_FILENAME).symlink_to(outside_db)
    with pytest.raises(HRRepositoryPathError, match="symbolic link"):
        HRRepository(status).initialize()
    assert outside_db.read_bytes() == b"sentinel"


@pytest.mark.parametrize(
    "migrations",
    [
        (),
        (HRMigration(2, "gap", lambda _connection: None),),
        (
            HRMigration(1, "one", lambda _connection: None),
            HRMigration(1, "duplicate", lambda _connection: None),
        ),
    ],
)
def test_migration_plan_must_be_monotonic_unique_and_contiguous(tmp_path, migrations):
    with pytest.raises(ValueError, match="migration"):
        repository(tmp_path, migrations=migrations)


def test_failed_upgrade_rolls_back_all_schema_and_metadata_changes(tmp_path):
    repo = repository(tmp_path)
    original = repo.initialize()

    def fail_after_ddl(connection):
        connection.execute("CREATE TABLE must_rollback(id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO metadata(key, value, updated_at) VALUES ('partial', 'yes', 'now')")
        connection.execute("THIS IS NOT VALID SQL")

    upgraded = repository(
        tmp_path,
        migrations=(*DEFAULT_MIGRATIONS, HRMigration(3, "failing_upgrade", fail_after_ddl)),
    )
    with pytest.raises(HRRepositoryMigrationError, match="initialization failed"):
        upgraded.initialize()

    assert repo.info() == original
    with sqlite3.connect(repo.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='must_rollback'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM metadata WHERE key='partial'"
        ).fetchone()[0] == 0


def test_failed_fresh_initialization_leaves_no_partial_schema(tmp_path):
    def fail_initial(connection):
        connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)")
        connection.execute("CREATE TABLE partial(id INTEGER)")
        raise RuntimeError("injected migration failure")

    repo = repository(
        tmp_path,
        migrations=(HRMigration(1, "failing_initial", fail_initial),),
    )
    with pytest.raises(HRRepositoryMigrationError, match="injected migration failure"):
        repo.initialize()
    with sqlite3.connect(repo.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()[0] == 0


def test_concurrent_initializers_serialize_without_duplicate_schema(tmp_path):
    repo = repository(tmp_path)
    barrier = threading.Barrier(3)
    results = []
    failures = []

    def initialize():
        barrier.wait()
        try:
            results.append(repo.initialize())
        except Exception as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    threads = [threading.Thread(target=initialize) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)
    assert not failures
    assert len(results) == 2
    assert results[0].schema_version == results[1].schema_version == 2
    assert set(repo.table_names()) == EXPECTED_TABLES


def test_metadata_and_user_version_mismatch_fails_closed(tmp_path):
    repo = repository(tmp_path)
    repo.initialize()
    with sqlite3.connect(repo.path) as connection:
        connection.execute("UPDATE metadata SET value = '0' WHERE key = 'schema_version'")
    with pytest.raises(HRRepositoryMigrationError, match="does not match"):
        repo.initialize()


def test_repository_module_has_no_server_or_transport_dependency():
    source = (APP_DIR / "services" / "hr_repository.py").read_text(encoding="utf-8")
    assert "import server" not in source
    assert "OfficeHandler" not in source
    assert "http.server" not in source
