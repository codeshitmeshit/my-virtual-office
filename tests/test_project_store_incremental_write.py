import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP = os.path.join(ROOT, "app")
if APP not in sys.path:
    sys.path.insert(0, APP)

from project_store import MarkdownProjectStore


def _project(project_id, title, tasks=1):
    return {
        "id": project_id,
        "title": title,
        "status": "active",
        "columns": [{"id": "backlog", "title": "Backlog"}],
        "tasks": [
            {"id": f"{project_id}-t-{index}", "title": f"Task {index}", "columnId": "backlog"}
            for index in range(tasks)
        ],
    }


def test_incremental_project_write_preserves_unrelated_files(tmp_path):
    store = MarkdownProjectStore(str(tmp_path))
    store.save_all({"projects": [_project("p1", "One"), _project("p2", "Two")], "templates": []})
    p2 = store.get_project("p2")
    p2_dir = store._project_dir(p2)
    before = os.stat(os.path.join(p2_dir, "project.md")).st_mtime_ns

    changed = store.get_project("p1")
    changed["title"] = "One renamed"
    changed["tasks"] = []
    store.save_project(changed)

    assert store.get_project("p1")["title"] == "One renamed"
    assert store.get_project("p1")["tasks"] == []
    assert store.get_project("p2")["title"] == "Two"
    assert os.stat(os.path.join(p2_dir, "project.md")).st_mtime_ns == before


def test_incremental_project_write_advances_revision_once(tmp_path):
    store = MarkdownProjectStore(str(tmp_path))
    store.save_all({"projects": [_project("p1", "One")], "templates": []})
    before = store.revision()
    store.save_project(_project("p1", "Changed", tasks=2))
    assert store.revision() == before + 1
