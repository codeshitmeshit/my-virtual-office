"""Shared SQLite connection policy for single-user Virtual Office stores."""

from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path


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
    connection = sqlite3.connect(
        str(target),
        timeout=max(0.1, float(timeout_seconds)),
        isolation_level=None,
        uri=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {int(max(100, timeout_seconds * 1000))}")
    if readonly:
        connection.execute("PRAGMA query_only = ON")
    if not readonly:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        os.chmod(target, 0o600, follow_symlinks=False)
    return connection
