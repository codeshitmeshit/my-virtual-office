"""Reusable, stoppable periodic callback runner for VO background reconcilers."""

from __future__ import annotations

import threading
from typing import Callable


class PeriodicTimerValidationError(ValueError):
    """Raised when a periodic timer is constructed with an invalid contract."""


class PeriodicTimer:
    """Run one callback immediately and then at a fixed delay until stopped."""

    def __init__(
        self,
        callback: Callable[[], object],
        *,
        interval_seconds: float,
        name: str,
        on_error: Callable[[Exception], None] = lambda _exc: None,
    ) -> None:
        if not callable(callback):
            raise PeriodicTimerValidationError("periodic callback must be callable")
        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, (int, float))
            or not 0.01 <= float(interval_seconds) <= 86_400
        ):
            raise PeriodicTimerValidationError(
                "interval_seconds must be between 0.01 and 86400"
            )
        if not isinstance(name, str) or not name.strip():
            raise PeriodicTimerValidationError("periodic timer name must not be empty")
        if not callable(on_error):
            raise PeriodicTimerValidationError("periodic error callback must be callable")
        self._callback = callback
        self._interval_seconds = float(interval_seconds)
        self._name = name.strip()
        self._on_error = on_error
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._callback()
            except Exception as exc:
                try:
                    self._on_error(exc)
                except Exception:
                    pass
            self._stop.wait(self._interval_seconds)

    def start(self) -> bool:
        """Start at most one resident worker and report whether it was created."""
        with self._start_lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
                name=self._name,
            )
            self._thread.start()
            return True

    def stop(self, timeout_seconds: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.0, float(timeout_seconds)))
