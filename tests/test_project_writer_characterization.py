#!/usr/bin/env python3
"""Characterization evidence for project-store writer coordination."""

import copy
import os
import sys
import tempfile
import unittest
import warnings


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")
os.environ["VO_STATUS_DIR"] = tempfile.mkdtemp(prefix="vo-writer-characterization-import-")

from project_store import MarkdownProjectStore
import server


def _project(project_id, title):
    return {
        "id": project_id,
        "title": title,
        "description": "",
        "status": "active",
        "columns": [],
        "tasks": [],
        "activity": [],
        "updatedAt": "before",
        "template": False,
    }


class ProjectWriterCharacterizationTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = MarkdownProjectStore(self.temp_dir.name)
        self.store.save_all({"projects": [_project("p1", "One"), _project("p2", "Two")], "templates": []})
        self.original_store = server.PROJECT_STORE
        server.PROJECT_STORE = self.store

    def tearDown(self):
        server.PROJECT_STORE = self.original_store
        self.temp_dir.cleanup()

    def test_different_project_stale_full_snapshots_should_preserve_both_writes(self):
        writer_a = server._load_projects()
        writer_b = server._load_projects()
        writer_a["projects"][0]["description"] = "written by A"
        writer_b["projects"][1]["description"] = "written by B"

        server._save_projects(writer_a)
        server._save_projects(writer_b)

        latest = {item["id"]: item for item in self.store.load_all()["projects"]}
        self.assertEqual(latest["p1"]["description"], "written by A")
        self.assertEqual(latest["p2"]["description"], "written by B")

    def test_same_project_legacy_and_execution_snapshots_should_preserve_owned_fields(self):
        legacy = server._load_projects()
        execution = copy.deepcopy(legacy)
        legacy["projects"][0]["activity"].append({"type": "activity", "at": "now", "by": "legacy", "detail": "legacy update"})
        execution["projects"][0]["workflowPhase"] = "executing"

        server._save_projects(execution)
        server._save_projects(legacy)

        latest = self.store.get_project("p1")
        self.assertEqual(latest["workflowPhase"], "executing")
        self.assertEqual(latest["activity"], [{"type": "activity", "at": "now", "by": "legacy", "detail": "legacy update"}])

    def test_direct_delete_removes_only_the_target_project(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            self.assertTrue(self.store.delete_project("p1"))
            latest = self.store.load_all()
            self.assertEqual([item["id"] for item in latest["projects"]], ["p2"])
            self.assertFalse(self.store.delete_project("missing"))

    def test_project_description_round_trips_from_top_level_project_section(self):
        data = self.store.load_all()
        data["projects"][0]["description"] = "Persistent project description"
        self.store.save_all(data)
        self.assertEqual(self.store.get_project("p1")["description"], "Persistent project description")


if __name__ == "__main__":
    unittest.main()
