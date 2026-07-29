"""Short-lived cache for settings diagnostics.

The settings drawer needs configuration values immediately, while provider
diagnostics can be moderately stale.  This cache keeps repeated /vo-config
loads from synchronously re-running heavyweight probes.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, TypeVar


T = TypeVar("T")


class SettingsProbeCache:
    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._values: dict[str, tuple[float, object]] = {}

    def get(self, key: str, ttl_sec: float, compute: Callable[[], T]) -> T:
        now = self._clock()
        with self._lock:
            cached = self._values.get(key)
            if cached and now - cached[0] < ttl_sec:
                return cached[1]  # type: ignore[return-value]

        value = compute()

        with self._lock:
            self._values[key] = (self._clock(), value)
        return value

    def invalidate(self, prefix: str | None = None) -> None:
        with self._lock:
            if prefix is None:
                self._values.clear()
                return
            for key in list(self._values):
                if key.startswith(prefix):
                    self._values.pop(key, None)

