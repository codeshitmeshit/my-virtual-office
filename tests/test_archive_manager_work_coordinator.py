from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.archive_manager_work_coordinator import (  # noqa: E402
    ArchiveManagerBusyError,
    ArchiveManagerWorkCoordinator,
    InvalidArchiveManagerLease,
)


def coordinator() -> ArchiveManagerWorkCoordinator:
    tokens = iter(["lease-1", "lease-2"])
    return ArchiveManagerWorkCoordinator(
        clock=lambda: "2026-07-30T12:00:00+00:00",
        token_factory=lambda: next(tokens),
        coordinator_id="test-coordinator",
    )


def test_acquire_exposes_detached_holder_metadata_and_release_is_idempotent():
    work = coordinator()
    source = {"projectId": "project-1"}

    lease = work.acquire(
        "archive-maintenance",
        label="整理项目档案",
        metadata=source,
    )
    source["projectId"] = "mutated"

    assert work.holder() == {
        "kind": "archive-maintenance",
        "label": "整理项目档案",
        "startedAt": "2026-07-30T12:00:00+00:00",
        "metadata": {"projectId": "project-1"},
    }
    snapshot = work.holder()
    snapshot["metadata"]["projectId"] = "also-mutated"
    assert work.holder()["metadata"]["projectId"] == "project-1"
    assert work.release(lease) is True
    assert work.release(lease) is False
    assert work.holder() is None


def test_later_acquire_is_rejected_immediately_instead_of_queued():
    work = coordinator()
    first = work.acquire("archive-ai-refinement")
    outcomes: list[object] = []

    def contend() -> None:
        try:
            work.acquire("skill-organization")
        except ArchiveManagerBusyError as exc:
            outcomes.append((exc.code, exc.holder["kind"]))

    thread = threading.Thread(target=contend)
    thread.start()
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert outcomes == [("archive_manager_busy", "archive-ai-refinement")]
    assert work.holder()["kind"] == "archive-ai-refinement"
    work.release(first)


def test_context_manager_releases_after_operation_error():
    work = coordinator()

    with pytest.raises(RuntimeError, match="operation failed"):
        with work.lease("archive-count-audit"):
            assert work.holder()["kind"] == "archive-count-audit"
            raise RuntimeError("operation failed")

    assert work.holder() is None
    with work.lease("skill-organization"):
        assert work.holder()["kind"] == "skill-organization"


def test_foreign_or_stale_lease_cannot_release_current_holder():
    first = coordinator()
    second = ArchiveManagerWorkCoordinator(coordinator_id="other")
    foreign = second.acquire("foreign")
    current = first.acquire("current")

    with pytest.raises(InvalidArchiveManagerLease, match="another coordinator"):
        first.release(foreign)

    assert first.holder()["kind"] == "current"
    first.release(current)


def test_startup_reconciliation_recovers_only_stale_running_records():
    work = coordinator()
    records = [
        {"id": "running", "status": "running"},
        {"id": "done", "status": "completed"},
        {"id": "failed", "status": "failed"},
    ]
    recovered: list[str] = []

    count = work.reconcile_stale_start(
        records,
        is_stale=lambda record: record["status"] == "running",
        recover=lambda record: recovered.append(record["id"]),
    )

    assert count == 1
    assert recovered == ["running"]
    assert work.holder() is None


def test_startup_reconciliation_does_not_touch_records_while_live_work_exists():
    work = coordinator()
    lease = work.acquire("archive-maintenance")
    recovered: list[str] = []

    with pytest.raises(ArchiveManagerBusyError):
        work.reconcile_stale_start(
            [{"id": "running", "status": "running"}],
            is_stale=lambda _record: True,
            recover=lambda record: recovered.append(record["id"]),
        )

    assert recovered == []
    work.release(lease)
