"""Incremental JSONL snapshot cache for chat-history source files."""

from __future__ import annotations

import json
import os
import threading
from collections import OrderedDict
from typing import Callable


DEFAULT_ENTRY_LIMIT = 32
DEFAULT_BYTE_LIMIT = 64 * 1024 * 1024


class JsonlSnapshotCache:
    def __init__(self, *, entry_limit: int = DEFAULT_ENTRY_LIMIT, byte_limit: int = DEFAULT_BYTE_LIMIT):
        self.entry_limit = int(entry_limit)
        self.byte_limit = int(byte_limit)
        self._entries: OrderedDict[tuple[str, str, int], dict] = OrderedDict()
        self._bytes = 0
        self._lock = threading.RLock()
        self.hits = 0
        self.misses = 0
        self.incremental_hits = 0

    @property
    def bytes(self) -> int:
        with self._lock:
            return self._bytes

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "hits": self.hits,
                "misses": self.misses,
                "incrementalHits": self.incremental_hits,
                "bytes": self._bytes,
                "entries": len(self._entries),
            }

    def load(
        self,
        path: str,
        cache_key: str,
        max_records: int = 1000,
        predicate: Callable[[dict], bool] | None = None,
        *,
        reverse_iter: Callable[[str], object],
    ) -> list[dict]:
        limit = max(1, min(int(max_records or 1000), 1000))
        key = (os.path.abspath(path or ""), str(cache_key or ""), limit)
        signature = self._file_signature(path)

        with self._lock:
            cached = self._entries.get(key)
            if cached and cached.get("signature") == signature:
                self.hits += 1
                self._entries.move_to_end(key)
                return [dict(row) for row in cached["rows"]]
            if cached and self._can_increment(signature, cached.get("signature")):
                rows = self._append_new_rows(path, cached, limit, predicate)
                if rows is not None:
                    self.hits += 1
                    self.incremental_hits += 1
                    self._replace_locked(key, signature, rows)
                    return [dict(row) for row in rows]
            self.misses += 1

        rows = self._load_reverse(path, limit, predicate, reverse_iter) if signature else []
        with self._lock:
            self._replace_locked(key, signature, rows)
        return [dict(row) for row in rows]

    @staticmethod
    def _file_signature(path: str):
        try:
            stat = os.stat(path)
            return (stat.st_ino, stat.st_size, stat.st_mtime_ns)
        except (FileNotFoundError, OSError):
            return None

    @staticmethod
    def _can_increment(current, previous) -> bool:
        if not current or not previous:
            return False
        return current[0] == previous[0] and current[1] >= previous[1]

    @staticmethod
    def _row_matches(row, predicate) -> bool:
        return isinstance(row, dict) and (not predicate or predicate(row))

    def _append_new_rows(self, path: str, cached: dict, limit: int, predicate) -> list[dict] | None:
        previous_signature = cached.get("signature")
        if not previous_signature:
            return None
        try:
            with open(path, "rb") as stream:
                stream.seek(int(previous_signature[1] or 0))
                payload = stream.read()
        except OSError:
            return None
        rows = [dict(row) for row in cached.get("rows") or []]
        for line in payload.splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            if self._row_matches(row, predicate):
                rows.append(row)
        return rows[-limit:]

    def _load_reverse(self, path: str, limit: int, predicate, reverse_iter) -> list[dict]:
        newest_first = []
        for line in reverse_iter(path):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not self._row_matches(row, predicate):
                continue
            newest_first.append(row)
            if len(newest_first) >= limit:
                break
        return list(reversed(newest_first))

    @staticmethod
    def _estimate_rows_bytes(rows: list[dict]) -> int:
        return len(json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    def _replace_locked(self, key, signature, rows: list[dict]) -> None:
        previous = self._entries.pop(key, None)
        if previous:
            self._bytes -= int(previous.get("bytes") or 0)
        estimated_bytes = self._estimate_rows_bytes(rows)
        self._entries[key] = {
            "signature": signature,
            "rows": rows,
            "bytes": estimated_bytes,
        }
        self._bytes += estimated_bytes
        while len(self._entries) > self.entry_limit or self._bytes > self.byte_limit:
            _, evicted = self._entries.popitem(last=False)
            self._bytes -= int(evicted.get("bytes") or 0)
