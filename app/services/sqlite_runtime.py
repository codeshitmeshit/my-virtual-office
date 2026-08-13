"""Shared SQLite connection policy for single-user Virtual Office stores."""

from __future__ import annotations

import atexit
import os
import sqlite3
import stat
import threading
import time
from collections import OrderedDict
from pathlib import Path


_POOL_SIZE = 4
_MAX_POOLS = 32
_POOLS_LOCK = threading.RLock()
_POOLS: "OrderedDict[tuple[str, bool], _ConnectionPool]" = OrderedDict()
_POOLS_PID = os.getpid()


def _open_connection(target: Path, *, readonly: bool, timeout_seconds: float) -> sqlite3.Connection:
    connection = sqlite3.connect(
        str(target),
        timeout=max(0.1, float(timeout_seconds)),
        isolation_level=None,
        uri=False,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {int(max(100, timeout_seconds * 1000))}")
    if readonly:
        connection.execute("PRAGMA query_only = ON")
    else:
        # Persistent database settings belong to physical connection creation,
        # not to every repository operation.
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        os.chmod(target, 0o600, follow_symlinks=False)
    return connection


class _ConnectionPool:
    def __init__(self, target: Path, *, readonly: bool) -> None:
        self.target = target
        self.readonly = readonly
        self.condition = threading.Condition()
        self.available: list[sqlite3.Connection] = []
        self.connections: set[sqlite3.Connection] = set()
        self.closed = False

    def acquire(self, timeout_seconds: float) -> sqlite3.Connection:
        deadline = time.monotonic() + max(0.1, float(timeout_seconds))
        with self.condition:
            while True:
                while self.available:
                    connection = self.available.pop()
                    return connection
                if self.closed:
                    raise sqlite3.ProgrammingError("SQLite connection pool is closed")
                if len(self.connections) < _POOL_SIZE:
                    connection = _open_connection(
                        self.target,
                        readonly=self.readonly,
                        timeout_seconds=timeout_seconds,
                    )
                    self.connections.add(connection)
                    return connection
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise sqlite3.OperationalError("timed out waiting for a SQLite connection")
                self.condition.wait(remaining)

    def release(self, connection: sqlite3.Connection) -> None:
        with self.condition:
            if connection not in self.connections:
                return
            if self.closed:
                self.connections.discard(connection)
                connection.close()
            else:
                if connection.in_transaction:
                    connection.rollback()
                self.available.append(connection)
            self.condition.notify()

    def close(self) -> None:
        with self.condition:
            self.closed = True
            connections = list(self.connections)
            self.connections.clear()
            self.available.clear()
            self.condition.notify_all()
        for connection in connections:
            try:
                connection.close()
            except sqlite3.Error:
                pass

    def is_idle(self) -> bool:
        with self.condition:
            return len(self.available) == len(self.connections)


class _BorrowedConnection:
    """One exclusive lease over a pooled physical SQLite connection."""

    __slots__ = ("_pool", "_connection", "_released")

    def __init__(self, pool: _ConnectionPool, connection: sqlite3.Connection) -> None:
        self._pool = pool
        self._connection = connection
        self._released = False

    def __getattr__(self, name: str):
        return getattr(self._connection, name)

    def close(self) -> None:
        if not self._released:
            self._released = True
            self._pool.release(self._connection)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if exc_type is not None and self._connection.in_transaction:
            self._connection.rollback()
        self.close()


def close_sqlite_connections() -> None:
    """Close all runtime-owned physical connections."""
    with _POOLS_LOCK:
        pools = list(_POOLS.values())
        _POOLS.clear()
    for pool in pools:
        pool.close()


def close_sqlite_path(path: str | os.PathLike[str]) -> None:
    """Close idle pools for one database path before offline replacement."""
    target = str(Path(path).expanduser().resolve())
    with _POOLS_LOCK:
        matches = [key for key in _POOLS if key[0] == target]
        pools = []
        for key in matches:
            pool = _POOLS[key]
            if not pool.is_idle():
                raise sqlite3.OperationalError("SQLite database still has active connection leases")
            pools.append(_POOLS.pop(key))
    for pool in pools:
        pool.close()


def _reset_after_fork_if_needed() -> None:
    global _POOLS_PID
    current_pid = os.getpid()
    if current_pid == _POOLS_PID:
        return
    # Inherited sqlite handles must never be reused in a forked child.
    pools = list(_POOLS.values())
    _POOLS.clear()
    _POOLS_PID = current_pid
    for pool in pools:
        pool.close()


def _evict_idle_pools() -> None:
    if len(_POOLS) <= _MAX_POOLS:
        return
    for key, pool in list(_POOLS.items()):
        if len(_POOLS) <= _MAX_POOLS:
            break
        if pool.is_idle():
            _POOLS.pop(key, None)
            pool.close()


atexit.register(close_sqlite_connections)


def connect_sqlite(
    path: str | os.PathLike[str],
    *,
    readonly: bool = False,
    timeout_seconds: float = 5.0,
) -> sqlite3.Connection:
    target = Path(path).expanduser().resolve()
    requested = Path(path).expanduser().absolute()
    try:
        metadata = requested.lstat()
    except FileNotFoundError:
        metadata = None
    if metadata is not None and (stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode)):
        raise sqlite3.OperationalError("SQLite authority must be a regular file")
    if not readonly:
        target.parent.mkdir(parents=True, exist_ok=True)
    key = (str(target), bool(readonly))
    with _POOLS_LOCK:
        _reset_after_fork_if_needed()
        pool = _POOLS.get(key)
        if pool is None:
            pool = _ConnectionPool(target, readonly=readonly)
            _POOLS[key] = pool
            _evict_idle_pools()
        else:
            _POOLS.move_to_end(key)
    return _BorrowedConnection(pool, pool.acquire(timeout_seconds))
