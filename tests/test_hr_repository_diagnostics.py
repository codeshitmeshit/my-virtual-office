"""Read-only management health and bounded JSON export tests."""

import base64
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_repository import (
    HRRepository,
    HRRepositoryCorruptionError,
    HRRepositoryValidationError,
)


FIXED_NOW = datetime(2026, 7, 19, 9, tzinfo=timezone.utc)


@pytest.fixture
def repository(tmp_path):
    result = HRRepository(tmp_path / "status", clock=lambda: FIXED_NOW)
    result.initialize()
    for index in range(3):
        result.upsert_agent(
            ai_id=f"agent-{index}",
            name=f"Agent {index}",
            agent_kind="project",
            status="active",
            availability="available",
            source="test",
        )
    return result


def test_uninitialized_health_is_read_only_and_does_not_create_directories(tmp_path):
    repository = HRRepository(tmp_path / "status")
    health = repository.management_health()
    assert health.status == "uninitialized"
    assert health.code == "hr_repository_uninitialized"
    assert not (tmp_path / "status").exists()


def test_ready_health_reports_schema_integrity_and_is_read_only(repository):
    before_bytes = repository.path.read_bytes()
    before_mtime = repository.path.stat().st_mtime_ns
    health = repository.management_health()
    assert health.status == "ready"
    assert health.code == "ok"
    assert health.schema_version == health.target_schema_version == 3
    assert health.database_bytes == len(before_bytes)
    assert health.page_count > 0
    assert health.page_size > 0
    assert health.integrity == "ok"
    assert health.foreign_key_violations == 0
    assert repository.path.read_bytes() == before_bytes
    assert repository.path.stat().st_mtime_ns == before_mtime


def test_health_reports_schema_metadata_failure_without_mutation(repository):
    with sqlite3.connect(repository.path) as connection:
        connection.execute("UPDATE metadata SET value = '0' WHERE key = 'schema_version'")
    before = repository.path.read_bytes()
    health = repository.management_health()
    assert health.status == "migration_failed"
    assert health.code == "hr_repository_migration_failed"
    assert "does not match" in health.error
    assert repository.path.read_bytes() == before


def test_health_reports_corrupt_database_without_raising_or_replacing_it(tmp_path):
    repository = HRRepository(tmp_path / "status")
    repository.hr_dir.mkdir(parents=True)
    corrupt = b"not a sqlite database"
    repository.path.write_bytes(corrupt)
    health = repository.management_health()
    assert health.status == "corrupt"
    assert health.code == "hr_repository_corrupt"
    assert "DatabaseError" in health.error
    assert repository.path.read_bytes() == corrupt


def test_health_detects_foreign_key_corruption(repository):
    with sqlite3.connect(repository.path) as connection:
        connection.execute(
            """INSERT INTO agent_identity_history(ai_id, name, status, source, observed_at)
               VALUES ('missing', 'Missing', 'active', 'manual-corruption', 'now')"""
        )
    health = repository.management_health()
    assert health.status == "corrupt"
    assert health.foreign_key_violations == 1


def test_export_is_json_safe_paged_and_read_only(repository):
    before_bytes = repository.path.read_bytes()
    before_files = sorted(path.name for path in repository.hr_dir.iterdir())
    first = repository.management_export("agents", limit=2)
    second = repository.management_export("agents", limit=2, cursor=first.next_cursor)
    assert [row["ai_id"] for row in first.rows] == ["agent-0", "agent-1"]
    assert [row["ai_id"] for row in second.rows] == ["agent-2"]
    assert first.next_cursor is not None
    assert second.next_cursor is None
    assert first.byte_size <= 256_000
    assert repository.path.read_bytes() == before_bytes
    assert sorted(path.name for path in repository.hr_dir.iterdir()) == before_files == ["hr.sqlite3"]


def test_export_decodes_typed_json_fields(repository):
    repository.save_daily_report(
        report_id="report-1",
        cycle_id=None,
        ai_id="agent-0",
        local_date="2026-07-19",
        submission_state="normalized",
        raw_response="original",
        normalized={"completed": ["diagnostics"]},
        normalizer_id="hr",
        expected_revision=0,
    )
    row = repository.management_export("daily_reports").rows[0]
    assert row["normalized"] == {"completed": ["diagnostics"]}
    assert "normalized_json" not in row


@pytest.mark.parametrize(
    "table", ("unknown", "access_grants", "agents; DROP TABLE agents", "sqlite_master")
)
def test_export_rejects_non_allowlisted_tables(repository, table):
    with pytest.raises(HRRepositoryValidationError, match="not exportable"):
        repository.management_export(table)
    assert len(repository.list_agents().items) == 3


@pytest.mark.parametrize(
    "kwargs",
    (
        {"limit": 0},
        {"limit": 101},
        {"max_bytes": 1_023},
        {"max_bytes": 1_000_001},
        {"cursor": "invalid cursor"},
    ),
)
def test_export_enforces_page_cursor_and_size_bounds(repository, kwargs):
    with pytest.raises(HRRepositoryValidationError):
        repository.management_export("agents", **kwargs)


def test_export_rejects_resource_amplifying_offset(repository):
    cursor = base64.urlsafe_b64encode(json.dumps([1_000_001]).encode()).decode().rstrip("=")
    with pytest.raises(HRRepositoryValidationError, match="cursor"):
        repository.management_export("agents", cursor=cursor)


def test_export_rejects_single_row_larger_than_response_budget(repository):
    current = repository.get_agent("agent-0")
    repository.save_introduction(
        ai_id="agent-0",
        state="published",
        raw_response="r" * 2_000,
        introduction="summary",
        source="hr",
        actor_id="hr",
        expected_version=0,
    )
    with pytest.raises(HRRepositoryValidationError, match="row exceeds"):
        repository.management_export("introductions", max_bytes=1_024)
    assert repository.get_agent("agent-0") == current


def test_export_reports_invalid_stored_json_and_does_not_repair_authority(repository):
    repository.save_daily_report(
        report_id="report-1",
        cycle_id=None,
        ai_id="agent-0",
        local_date="2026-07-19",
        submission_state="normalized",
        raw_response="original",
        normalized={"completed": []},
        expected_revision=0,
    )
    with sqlite3.connect(repository.path) as connection:
        connection.execute("UPDATE daily_reports SET normalized_json = '{broken'")
    before = repository.path.read_bytes()
    with pytest.raises(HRRepositoryCorruptionError, match="invalid JSON"):
        repository.management_export("daily_reports")
    assert repository.path.read_bytes() == before
