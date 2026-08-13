import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP = os.path.join(ROOT, "app")
if APP not in sys.path:
    sys.path.insert(0, APP)

from services.project_summary_cache import ProjectSummaryCache


def test_summary_cache_loads_once_per_revision_and_filter():
    cache = ProjectSummaryCache()
    calls = []

    def load():
        calls.append(1)
        return {"projects": [{"id": "p1", "taskCount": 1000}]}

    first = cache.get(1, "active", load)
    second = cache.get(1, "active", load)

    assert len(calls) == 1
    assert first == second
    assert first is not second

    cache.get(2, "active", load)
    assert len(calls) == 2


def test_summary_cache_does_not_share_mutable_results_with_callers():
    cache = ProjectSummaryCache()
    first = cache.get(1, "", lambda: {"projects": [{"id": "p1"}]})
    first["projects"][0]["id"] = "changed"

    second = cache.get(1, "", lambda: {})

    assert second["projects"][0]["id"] == "p1"


def test_summary_cache_is_bypassed_without_a_revision():
    cache = ProjectSummaryCache()
    calls = []
    cache.get(None, "", lambda: calls.append(1) or {"projects": []})
    cache.get(None, "", lambda: calls.append(1) or {"projects": []})
    assert len(calls) == 2
