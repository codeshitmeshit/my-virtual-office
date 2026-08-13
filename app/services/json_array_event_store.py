"""Cached atomic persistence for bounded JSON-array event journals."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any


class JsonArrayEventStore:
    """Avoid reparsing a whole event journal for every streamed event."""

    def __init__(self, *, max_events: int) -> None:
        self._max_events = max(1, int(max_events))
        self._lock = threading.RLock()
        self._path = ""
        self._signature: tuple[int, int, int] | None = None
        self._events: list[dict[str, Any]] | None = None

    @staticmethod
    def _file_signature(path: str) -> tuple[int, int, int] | None:
        try:
            stat = os.stat(path)
            return stat.st_ino, stat.st_size, stat.st_mtime_ns
        except OSError:
            return None

    def load(self, path: str) -> list[dict[str, Any]]:
        resolved = os.path.abspath(path)
        signature = self._file_signature(resolved)
        with self._lock:
            if (
                self._events is not None
                and self._path == resolved
                and self._signature == signature
            ):
                return self._events
            try:
                with open(resolved, "r", encoding="utf-8") as stream:
                    value = json.load(stream)
                events = value if isinstance(value, list) else []
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                events = []
            self._path = resolved
            self._signature = signature
            self._events = events
            return events

    def save(self, path: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        resolved = os.path.abspath(path)
        bounded = list(events[-self._max_events :])
        parent = Path(resolved).parent
        parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{Path(resolved).name}.",
            dir=str(parent),
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(
                    bounded,
                    stream,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            os.replace(temporary, resolved)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        with self._lock:
            self._path = resolved
            self._signature = self._file_signature(resolved)
            self._events = bounded
        return bounded
