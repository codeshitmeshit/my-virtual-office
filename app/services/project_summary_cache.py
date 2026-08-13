"""Revision-keyed cache for lightweight project list projections."""

from __future__ import annotations

import copy
import threading
from collections.abc import Callable
from typing import Any


class ProjectSummaryCache:
    """Keep task-heavy project trees out of repeated list/dashboard reads."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: dict[tuple[Any, str], dict[str, Any]] = {}

    def get(
        self,
        revision: Any,
        status_filter: str,
        loader: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        if revision is None:
            return loader()
        key = (revision, str(status_filter or ""))
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                return copy.deepcopy(cached)
        loaded = loader()
        with self._lock:
            self._entries = {key: copy.deepcopy(loaded)}
        return loaded

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
