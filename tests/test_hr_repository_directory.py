"""Transactional Agent directory and introduction persistence tests."""

import sqlite3
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_repository import (
    HRRepository,
    HRRepositoryConflictError,
    HRRepositoryNotFoundError,
    HRRepositoryValidationError,
)


class TickClock:
    def __init__(self):
        self._value = datetime(2026, 7, 19, 9, tzinfo=timezone.utc)
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            result = self._value
            self._value += timedelta(microseconds=1)
            return result


@pytest.fixture
def repository(tmp_path):
    result = HRRepository(tmp_path / "status", clock=TickClock())
    result.initialize()
    return result


def observe(repository, ai_id="agent-1", **overrides):
    values = {
        "ai_id": ai_id,
        "name": "Researcher",
        "agent_kind": "project",
        "provider_kind": "codex",
        "status": "active",
        "availability": "available",
        "source": "provider-roster",
    }
    values.update(overrides)
    return repository.upsert_agent(**values)


def test_duplicate_discovery_merges_by_stable_ai_id(repository):
    first = observe(repository)
    duplicate = observe(repository)

    assert duplicate.ai_id == first.ai_id
    assert duplicate.revision == first.revision == 1
    assert duplicate.last_seen_at > first.last_seen_at
    assert len(repository.list_agents().items) == 1
    assert len(repository.list_identity_history("agent-1").items) == 1


def test_rename_keeps_record_introduction_and_identity_history(repository):
    original = observe(repository)
    introduction = repository.save_introduction(
        ai_id="agent-1",
        state="published",
        raw_response="  I investigate incidents.\n",
        introduction="Investigates production incidents.",
        source="hr-coordination",
        actor_id="hr",
        expected_version=0,
    )

    renamed = observe(
        repository,
        name="Reliability Researcher",
        expected_revision=original.revision,
    )

    assert renamed.ai_id == original.ai_id
    assert renamed.name == "Reliability Researcher"
    assert renamed.revision == 2
    assert repository.get_current_introduction("agent-1") == introduction
    history = repository.list_identity_history("agent-1").items
    assert [item.name for item in history] == ["Reliability Researcher", "Researcher"]


def test_inactive_history_and_reactivation_preserve_same_record(repository):
    active = observe(repository)
    disabled = observe(
        repository,
        status="disabled",
        availability="unavailable",
        source="provider-health",
        expected_revision=active.revision,
    )
    assert disabled.status == "disabled"
    assert disabled.inactive_at is not None

    restored = observe(
        repository,
        name=disabled.name,
        expected_revision=disabled.revision,
    )
    assert restored.status == "active"
    assert restored.inactive_at is None
    assert restored.revision == 3
    assert [item.status for item in repository.list_identity_history("agent-1").items] == [
        "active",
        "disabled",
        "active",
    ]


def test_discovery_source_change_is_provenance_not_duplicate(repository):
    first = observe(repository)
    merged = observe(repository, source="workspace-scan", expected_revision=first.revision)
    assert merged.revision == 2
    assert merged.discovery_source == "workspace-scan"
    assert len(repository.list_agents().items) == 1
    assert {item.source for item in repository.list_identity_history("agent-1").items} == {
        "provider-roster",
        "workspace-scan",
    }


def test_agent_status_filter_and_cursor_pagination(repository):
    observe(repository, "agent-1")
    observe(repository, "agent-2")
    observe(repository, "agent-3", status="offline", availability="unavailable")

    first = repository.list_agents(limit=2)
    second = repository.list_agents(limit=2, cursor=first.next_cursor)
    assert len(first.items) == 2
    assert first.next_cursor
    assert len(second.items) == 1
    assert second.next_cursor is None
    assert {item.ai_id for item in (*first.items, *second.items)} == {
        "agent-1",
        "agent-2",
        "agent-3",
    }
    assert [item.ai_id for item in repository.list_agents(status="offline").items] == [
        "agent-3"
    ]


def test_identity_history_cursor_is_stable_when_timestamps_repeat(tmp_path):
    fixed = datetime(2026, 7, 19, tzinfo=timezone.utc)
    repository = HRRepository(tmp_path / "status", clock=lambda: fixed)
    repository.initialize()
    current = observe(repository)
    for name in ("Second", "Third"):
        current = observe(repository, name=name, expected_revision=current.revision)

    first = repository.list_identity_history("agent-1", limit=2)
    second = repository.list_identity_history("agent-1", limit=2, cursor=first.next_cursor)
    assert [item.name for item in first.items] == ["Third", "Second"]
    assert [item.name for item in second.items] == ["Researcher"]


def test_no_response_introduction_keeps_pending_without_invented_text(repository):
    observe(repository)
    pending = repository.save_introduction(
        ai_id="agent-1",
        state="introduction_pending",
        raw_response=None,
        introduction="",
        source="timeout-policy",
        actor_id="hr",
        expected_version=0,
    )
    assert pending.raw_response is None
    assert pending.introduction == ""
    assert pending.state == "introduction_pending"


def test_introduction_versions_preserve_raw_response_and_current_pointer(repository):
    observe(repository)
    first = repository.save_introduction(
        ai_id="agent-1",
        state="published",
        raw_response="  original answer\nwith detail  ",
        introduction="Original summary.",
        source="hr-coordination",
        actor_id="hr",
        expected_version=0,
    )
    assert first.raw_response == "  original answer\nwith detail  "
    assert repository.save_introduction(
        ai_id="agent-1",
        state="published",
        raw_response=first.raw_response,
        introduction=first.introduction,
        source=first.source,
        actor_id=first.actor_id,
        expected_version=1,
    ) == first

    second = repository.save_introduction(
        ai_id="agent-1",
        state="published",
        raw_response="updated answer",
        introduction="Updated summary.",
        source="clarification",
        actor_id="hr",
        expected_version=1,
    )
    assert second.version == 2
    assert repository.get_current_introduction("agent-1") == second
    history = repository.list_introductions("agent-1").items
    assert [item.version for item in history] == [2, 1]
    assert [item.is_current for item in history] == [True, False]


def test_introduction_history_paginates_by_version(repository):
    observe(repository)
    for expected_version in range(3):
        repository.save_introduction(
            ai_id="agent-1",
            state="published",
            raw_response=f"answer {expected_version}",
            introduction=f"summary {expected_version}",
            source="hr-coordination",
            actor_id="hr",
            expected_version=expected_version,
        )
    first = repository.list_introductions("agent-1", limit=2)
    second = repository.list_introductions("agent-1", limit=2, cursor=first.next_cursor)
    assert [item.version for item in first.items] == [3, 2]
    assert [item.version for item in second.items] == [1]


def test_optimistic_agent_update_allows_one_concurrent_winner(repository):
    original = observe(repository)
    barrier = threading.Barrier(3)
    successes = []
    failures = []

    def rename(name):
        barrier.wait()
        try:
            successes.append(
                observe(
                    repository,
                    name=name,
                    expected_revision=original.revision,
                )
            )
        except Exception as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    threads = [threading.Thread(target=rename, args=(name,)) for name in ("Alpha", "Beta")]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)

    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], HRRepositoryConflictError)
    assert repository.get_agent("agent-1").revision == 2
    assert len(repository.list_identity_history("agent-1").items) == 2


def test_optimistic_introduction_update_allows_one_concurrent_winner(repository):
    observe(repository)
    initial = repository.save_introduction(
        ai_id="agent-1",
        state="introduction_pending",
        raw_response=None,
        introduction="",
        source="discovery",
        actor_id="hr",
        expected_version=0,
    )
    barrier = threading.Barrier(3)
    successes = []
    failures = []

    def publish(label):
        barrier.wait()
        try:
            successes.append(
                repository.save_introduction(
                    ai_id="agent-1",
                    state="published",
                    raw_response=f"answer {label}",
                    introduction=f"summary {label}",
                    source="hr-coordination",
                    actor_id="hr",
                    expected_version=initial.version,
                )
            )
        except Exception as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    threads = [threading.Thread(target=publish, args=(label,)) for label in ("A", "B")]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)

    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], HRRepositoryConflictError)
    assert repository.get_current_introduction("agent-1").version == 2


def test_conflicts_and_validation_leave_authority_unchanged(repository):
    original = observe(repository)
    with pytest.raises(HRRepositoryConflictError):
        observe(repository, name="Wrong revision", expected_revision=99)
    with pytest.raises(HRRepositoryValidationError):
        observe(repository, " agent-1 ")
    with pytest.raises(HRRepositoryValidationError):
        observe(repository, status="invented")
    with pytest.raises(HRRepositoryValidationError):
        repository.list_agents(limit=101)
    with pytest.raises(HRRepositoryValidationError):
        repository.list_agents(cursor="not a cursor")
    assert repository.get_agent("agent-1") == original


def test_introduction_requires_existing_agent_and_supported_published_content(repository):
    with pytest.raises(HRRepositoryNotFoundError):
        repository.save_introduction(
            ai_id="missing",
            state="introduction_pending",
            raw_response=None,
            introduction="",
            source="discovery",
            actor_id="hr",
        )
    observe(repository)
    with pytest.raises(HRRepositoryValidationError, match="must not be empty"):
        repository.save_introduction(
            ai_id="agent-1",
            state="published",
            raw_response="answer",
            introduction="",
            source="hr-coordination",
            actor_id="hr",
        )


def test_identity_history_has_database_index_and_foreign_key(repository):
    observe(repository)
    with sqlite3.connect(repository.path) as connection:
        indexes = {row[1] for row in connection.execute("PRAGMA index_list('agents')")}
        foreign_keys = list(connection.execute("PRAGMA foreign_key_list('agent_identity_history')"))
    assert "agents_status_updated_idx" in indexes
    assert foreign_keys and foreign_keys[0][2] == "agents"
