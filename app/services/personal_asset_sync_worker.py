"""Single daemon worker for weak Personal Assets synchronization."""

from __future__ import annotations

import logging
import threading
from typing import Callable


_LOGGER = logging.getLogger(__name__)


class PersonalAssetSyncWorker:
    def __init__(self, run_once: Callable[[], object], *, retry_interval: float = 60.0):
        if not callable(run_once):
            raise TypeError("run_once must be callable")
        if retry_interval <= 0 or retry_interval > 60:
            raise ValueError("retry_interval must be between 0 and 60 seconds")
        self._run_once = run_once
        self._retry_interval = float(retry_interval)
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._loop,
                name="personal-assets-oss-sync",
                daemon=True,
            )
            self._thread.start()

    def wake(self) -> None:
        self._wake_event.set()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._thread = None
            self._stop_event.set()
            self._wake_event.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self._wake_event.wait(timeout=self._retry_interval)
            self._wake_event.clear()
            if self._stop_event.is_set():
                return
            try:
                self._run_once()
            except Exception as exc:
                _LOGGER.warning(
                    "Personal Assets sync worker iteration failed code=%s",
                    str(getattr(exc, "code", "personal_asset_sync_worker_failed")),
                )
