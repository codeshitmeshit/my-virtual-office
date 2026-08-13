import os
import sys
import threading
import time


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP = os.path.join(ROOT, "app")
if APP not in sys.path:
    sys.path.insert(0, APP)

from services.dashboard_snapshot_feed import DashboardSnapshotFeed


def _snapshot(value):
    return {"value": value, "signatures": {"status": str(value)}}


def test_feed_computes_once_and_shares_the_same_revision_across_clients():
    calls = 0

    def load():
        nonlocal calls
        calls += 1
        return _snapshot(1)

    feed = DashboardSnapshotFeed(load, interval_sec=0.2)
    try:
        results = []
        threads = [threading.Thread(target=lambda: results.append(feed.current())) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert calls == 1
        assert len(results) == 8
        assert {revision for revision, _ in results} == {1}
        assert len({id(snapshot) for _, snapshot in results}) == 1
    finally:
        feed.close()


def test_feed_publishes_only_when_section_signatures_change():
    value = {"current": 1}
    feed = DashboardSnapshotFeed(lambda: _snapshot(value["current"]), interval_sec=0.02)
    try:
        revision, first = feed.current()
        assert revision == 1
        assert first["value"] == 1

        time.sleep(0.06)
        unchanged_revision, unchanged = feed.wait_after(revision, timeout=0.01)
        assert unchanged_revision == revision
        assert unchanged is None

        value["current"] = 2
        changed_revision, changed = feed.wait_after(revision, timeout=0.2)
        assert changed_revision == 2
        assert changed["value"] == 2
    finally:
        feed.close()
