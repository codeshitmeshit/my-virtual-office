"""Shared, revision-driven snapshot feed for dashboard SSE clients."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any


JsonDict = dict[str, Any]


class DashboardSnapshotFeed:
    """Compute one dashboard snapshot per process and share it across clients.

    The producer publishes a new revision only when one of the dashboard section
    signatures changes.  Connected SSE handlers can therefore wait on a
    condition instead of independently rebuilding the same repository views.
    """

    def __init__(
        self,
        loader: Callable[[], JsonDict],
        *,
        interval_sec: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._loader = loader
        self._interval_sec = max(0.05, float(interval_sec))
        self._clock = clock
        self._condition = threading.Condition()
        self._snapshot: JsonDict | None = None
        self._revision = 0
        self._error: Exception | None = None
        self._started = False
        self._stopped = False

    def start(self) -> None:
        with self._condition:
            if self._started:
                return
            self._started = True
            thread = threading.Thread(
                target=self._run,
                daemon=True,
                name="dashboard-snapshot-feed",
            )
            thread.start()

    def close(self) -> None:
        with self._condition:
            self._stopped = True
            self._condition.notify_all()

    def current(self, *, timeout: float = 5.0) -> tuple[int, JsonDict]:
        self.start()
        deadline = self._clock() + max(0.0, float(timeout))
        with self._condition:
            while self._snapshot is None and not self._stopped:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
            if self._snapshot is not None:
                return self._revision, self._snapshot
            if self._error is not None:
                raise self._error
            raise TimeoutError("dashboard snapshot feed did not become ready")

    def wait_after(
        self,
        revision: int,
        *,
        timeout: float,
    ) -> tuple[int, JsonDict | None]:
        self.start()
        deadline = self._clock() + max(0.0, float(timeout))
        with self._condition:
            while self._revision <= revision and not self._stopped:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
            if self._revision > revision and self._snapshot is not None:
                return self._revision, self._snapshot
            return revision, None

    @staticmethod
    def _signatures(snapshot: JsonDict | None) -> Any:
        return snapshot.get("signatures") if isinstance(snapshot, dict) else None

    def _publish(self, snapshot: JsonDict) -> None:
        with self._condition:
            changed = (
                self._snapshot is None
                or self._signatures(snapshot) != self._signatures(self._snapshot)
            )
            self._error = None
            if changed:
                self._snapshot = snapshot
                self._revision += 1
                self._condition.notify_all()

    def _run(self) -> None:
        while True:
            with self._condition:
                if self._stopped:
                    return
            started = self._clock()
            try:
                snapshot = self._loader()
                if not isinstance(snapshot, dict):
                    raise TypeError("dashboard snapshot loader returned a non-object")
                self._publish(snapshot)
            except Exception as exc:
                with self._condition:
                    self._error = exc
                    self._condition.notify_all()
            remaining = self._interval_sec - (self._clock() - started)
            with self._condition:
                if self._stopped:
                    return
                self._condition.wait(max(0.01, remaining))
