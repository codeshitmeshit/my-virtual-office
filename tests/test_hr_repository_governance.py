"""Successful access audit and HR activity persistence tests."""

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
        self.value = datetime(2026, 7, 19, 9, tzinfo=timezone.utc)
        self.lock = threading.Lock()

    def __call__(self):
        with self.lock:
            result = self.value
            self.value += timedelta(microseconds=1)
            return result


@pytest.fixture
def repository(tmp_path):
    result = HRRepository(tmp_path / "status", clock=TickClock())
    result.initialize()
    for ai_id, name in (("agent-1", "Researcher"), ("agent-2", "Builder")):
        result.upsert_agent(
            ai_id=ai_id,
            name=name,
            agent_kind="project",
            status="active",
            availability="available",
            source="test",
        )
    return result


def test_successful_access_is_exactly_once_and_snapshots_names(repository):
    first = repository.record_successful_access(
        access_id="access-1",
        viewer_ai_id="agent-1",
        target_ai_id="agent-2",
        viewed_at="2026-07-19T01:00:00Z",
        scope="public_work_summary",
        request_source="agent-api",
        occurrence_key="request-123",
    )
    assert first.result == "success"
    assert first.viewer_name == "Researcher"
    assert first.target_name == "Builder"
    assert repository.record_successful_access(
        access_id="access-1",
        viewer_ai_id="agent-1",
        target_ai_id="agent-2",
        viewed_at="2026-07-19T01:00:00Z",
        scope="public_work_summary",
        request_source="agent-api",
        occurrence_key="request-123",
    ) == first

    current = repository.get_agent("agent-2")
    repository.upsert_agent(
        ai_id="agent-2",
        name="Platform Builder",
        agent_kind=current.agent_kind,
        status="disabled",
        availability="unavailable",
        source="test-update",
        expected_revision=current.revision,
    )
    historical = repository.list_access_log(target_ai_id="agent-2").items[0]
    assert historical.target_name == "Builder"
    assert historical.target_ai_id == "agent-2"


def test_access_log_rejects_self_missing_and_occurrence_conflicts(repository):
    with pytest.raises(HRRepositoryValidationError):
        repository.record_successful_access(
            access_id="self",
            viewer_ai_id="agent-1",
            target_ai_id="agent-1",
            viewed_at="2026-07-19T01:00:00Z",
            scope="public",
            request_source="agent-api",
            occurrence_key="self",
        )
    with pytest.raises(HRRepositoryNotFoundError):
        repository.record_successful_access(
            access_id="missing",
            viewer_ai_id="agent-1",
            target_ai_id="missing",
            viewed_at="2026-07-19T01:00:00Z",
            scope="public",
            request_source="agent-api",
            occurrence_key="missing",
        )
    repository.record_successful_access(
        access_id="one",
        viewer_ai_id="agent-1",
        target_ai_id="agent-2",
        viewed_at="2026-07-19T01:00:00Z",
        scope="public",
        request_source="agent-api",
        occurrence_key="same-request",
    )
    with pytest.raises(HRRepositoryConflictError):
        repository.record_successful_access(
            access_id="two",
            viewer_ai_id="agent-2",
            target_ai_id="agent-1",
            viewed_at="2026-07-19T01:01:00Z",
            scope="public",
            request_source="agent-api",
            occurrence_key="same-request",
        )
    assert len(repository.list_access_log().items) == 1


def test_access_log_filters_and_cursor_pagination(repository):
    for index in range(3):
        repository.record_successful_access(
            access_id=f"access-{index}",
            viewer_ai_id="agent-1" if index < 2 else "agent-2",
            target_ai_id="agent-2" if index < 2 else "agent-1",
            viewed_at=f"2026-07-19T01:0{index}:00Z",
            scope="public",
            request_source="agent-api",
            occurrence_key=f"view-{index}",
        )
    first = repository.list_access_log(limit=2)
    second = repository.list_access_log(limit=2, cursor=first.next_cursor)
    assert len(first.items) == 2
    assert len(second.items) == 1
    assert len(repository.list_access_log(target_ai_id="agent-2").items) == 2
    assert len(repository.list_access_log(viewer_ai_id="agent-2").items) == 1


def test_concurrent_successful_access_occurrence_is_exactly_once(repository):
    barrier = threading.Barrier(3)
    results = []

    def record():
        barrier.wait()
        results.append(
            repository.record_successful_access(
                access_id="access-once",
                viewer_ai_id="agent-1",
                target_ai_id="agent-2",
                viewed_at="2026-07-19T01:00:00Z",
                scope="public",
                request_source="agent-api",
                occurrence_key="disclosure-once",
            )
        )

    threads = [threading.Thread(target=record) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)
    assert len(results) == 2
    assert results[0] == results[1]
    assert len(repository.list_access_log().items) == 1


def test_hr_activity_is_idempotent_json_validated_and_retained(repository):
    first = repository.append_hr_activity(
        activity_id="activity-1",
        ai_id="agent-1",
        action="introduction_requested",
        status="succeeded",
        message="Request delivered.",
        context={"attempt": 1},
        occurrence_key="intro:agent-1:v1",
    )
    assert repository.append_hr_activity(
        activity_id="activity-1",
        ai_id="agent-1",
        action="introduction_requested",
        status="succeeded",
        message="Request delivered.",
        context={"attempt": 1},
        occurrence_key="intro:agent-1:v1",
    ) == first
    with pytest.raises(HRRepositoryValidationError, match="valid JSON"):
        repository.append_hr_activity(
            activity_id="bad",
            ai_id=None,
            action="bad",
            status="failed",
            context="{broken",
        )

    current = repository.get_agent("agent-1")
    repository.upsert_agent(
        ai_id="agent-1",
        name=current.name,
        agent_kind=current.agent_kind,
        status="deleted",
        availability="unavailable",
        source="test-delete",
        expected_revision=current.revision,
    )
    assert repository.list_hr_activity(ai_id="agent-1").items == (first,)


def test_hr_activity_pagination_is_bounded(repository):
    for index in range(3):
        repository.append_hr_activity(
            activity_id=f"activity-{index}",
            ai_id=None,
            action="cycle",
            status="succeeded",
            context={"index": index},
        )
    first = repository.list_hr_activity(limit=2)
    second = repository.list_hr_activity(limit=2, cursor=first.next_cursor)
    assert len(first.items) == 2
    assert len(second.items) == 1
    with pytest.raises(HRRepositoryValidationError):
        repository.list_hr_activity(limit=101)
