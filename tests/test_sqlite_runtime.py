import sys
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services import sqlite_runtime


def test_sequential_borrows_reuse_one_physical_connection(tmp_path):
    first = sqlite_runtime.connect_sqlite(tmp_path / "reuse.sqlite3")
    physical = first._connection
    first.close()

    second = sqlite_runtime.connect_sqlite(tmp_path / "reuse.sqlite3")
    try:
        assert second._connection is physical
        second.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY)")
    finally:
        second.close()


def test_close_releases_lease_and_rolls_back_open_transaction(tmp_path):
    path = tmp_path / "rollback.sqlite3"
    connection = sqlite_runtime.connect_sqlite(path)
    connection.execute("CREATE TABLE sample(value TEXT)")
    connection.execute("BEGIN IMMEDIATE")
    connection.execute("INSERT INTO sample(value) VALUES('uncommitted')")
    connection.close()

    reopened = sqlite_runtime.connect_sqlite(path)
    try:
        assert reopened.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 0
    finally:
        reopened.close()


def test_pool_serializes_leases_without_sharing_one_connection(tmp_path):
    path = tmp_path / "parallel.sqlite3"
    seed = sqlite_runtime.connect_sqlite(path)
    seed.execute("CREATE TABLE sample(value INTEGER)")
    seed.close()
    barrier = threading.Barrier(4)
    physical_ids = []
    errors = []

    def worker(value):
        try:
            barrier.wait()
            connection = sqlite_runtime.connect_sqlite(path)
            try:
                physical_ids.append(id(connection._connection))
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("INSERT INTO sample(value) VALUES(?)", (value,))
                connection.commit()
            finally:
                connection.close()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(value,)) for value in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    assert 1 <= len(set(physical_ids)) <= 4
    check = sqlite_runtime.connect_sqlite(path)
    try:
        assert check.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 4
    finally:
        check.close()


def test_close_path_releases_idle_physical_connections(tmp_path):
    path = tmp_path / "replace.sqlite3"
    connection = sqlite_runtime.connect_sqlite(path)
    physical = connection._connection
    connection.close()
    sqlite_runtime.close_sqlite_path(path)

    reopened = sqlite_runtime.connect_sqlite(path)
    try:
        assert reopened._connection is not physical
    finally:
        reopened.close()
