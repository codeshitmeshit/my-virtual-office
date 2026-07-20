"""Shared periodic timer behavior used by VO reconcilers."""

import sys
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.periodic_timer import PeriodicTimer


def test_periodic_timer_starts_once_runs_immediately_and_stops():
    called = threading.Event()
    timer = PeriodicTimer(
        called.set,
        interval_seconds=60,
        name="test-periodic-timer",
    )
    assert timer.start() is True
    assert timer.start() is False
    assert called.wait(timeout=2)
    timer.stop()


def test_periodic_timer_isolates_callback_and_error_handler_failures():
    errors = []
    called = threading.Event()

    def fail():
        called.set()
        raise RuntimeError("secret provider details")

    timer = PeriodicTimer(
        fail,
        interval_seconds=60,
        name="test-periodic-error",
        on_error=lambda exc: errors.append(type(exc).__name__),
    )
    timer.start()
    assert called.wait(timeout=2)
    timer.stop()
    assert errors == ["RuntimeError"]


def test_hr_and_project_reconcilers_use_the_shared_timer_interface():
    scheduler = (APP_DIR / "services" / "hr_scheduler.py").read_text(encoding="utf-8")
    server = (APP_DIR / "server.py").read_text(encoding="utf-8")
    assert "PeriodicTimer(" in scheduler
    assert "periodic_timer_service.PeriodicTimer(" in server
    assert "def _project_recurrence_reconcile_loop" not in server
