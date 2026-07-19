"""Durable execution state for asynchronous HR management commands."""

import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_command_status import HRCommandStatusTracker
from services.hr_repository import HRRepository


NOW = datetime(2026, 7, 20, 10, tzinfo=timezone.utc)


def test_command_state_is_queryable_during_work_and_survives_repository_reopen(tmp_path):
    status_dir = tmp_path / "status"
    repository = HRRepository(status_dir, clock=lambda: NOW)
    repository.initialize()
    tracker = HRCommandStatusTracker(repository)

    accepted = tracker.accepted("sync-1", "sync")
    assert accepted.status == "accepted"
    tracker.running("sync-1", context={"stage": "discovering"})

    active = HRRepository(status_dir, clock=lambda: NOW).list_active_hr_commands()
    assert [(item.id, item.action, item.status) for item in active] == [
        ("sync-1", "sync", "processing")
    ]
    assert active[0].context["stage"] == "discovering"

    tracker.complete(
        "sync-1",
        message="discovered=14, failed=0",
        context={"discovered": 14, "failed": 0},
    )
    assert repository.list_active_hr_commands() == ()
    activity = repository.list_hr_activity().items[0]
    assert activity.id == "sync-1"
    assert activity.status == "complete"
    assert activity.context["commandId"] == "sync-1"
    assert activity.context["discovered"] == 14


def test_failed_command_replaces_running_state_without_duplicate_activity(tmp_path):
    repository = HRRepository(tmp_path / "status", clock=lambda: NOW)
    repository.initialize()
    tracker = HRCommandStatusTracker(repository)
    tracker.accepted("daily-1", "manual_daily_sync", context={"requested": 2})
    tracker.running("daily-1", context={"requested": 2})
    tracker.failed("daily-1", "hr_provider_timeout", context={"requested": 2})

    items = repository.list_hr_activity().items
    assert len(items) == 1
    assert items[0].status == "failed"
    assert items[0].error == "hr_provider_timeout"
    assert repository.list_active_hr_commands() == ()


def test_startup_recovery_marks_commands_from_previous_process_interrupted(tmp_path):
    repository = HRRepository(tmp_path / "status", clock=lambda: NOW)
    repository.initialize()
    tracker = HRCommandStatusTracker(repository)
    tracker.accepted("old-run", "run")
    tracker.running("old-run")

    assert tracker.interrupt_active() == 1
    recovered = repository.list_hr_activity().items[0]
    assert recovered.status == "failed"
    assert recovered.error == "hr_command_interrupted"
    assert recovered.context["previousStatus"] == "processing"
