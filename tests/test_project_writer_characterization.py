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

from project_store import MarkdownProjectStore


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

    def tearDown(self):
        self.temp_dir.cleanup()

    @unittest.expectedFailure
    def test_different_project_stale_full_snapshots_should_preserve_both_writes(self):
        """Documents the pre-repository lost-update defect across projects."""
        writer_a = self.store.load_all()
        writer_b = self.store.load_all()
        writer_a["projects"][0]["description"] = "written by A"
        writer_b["projects"][1]["description"] = "written by B"

        self.store.save_all(writer_a)
        self.store.save_all(writer_b)

        latest = {item["id"]: item for item in self.store.load_all()["projects"]}
        self.assertEqual(latest["p1"]["description"], "written by A")
        self.assertEqual(latest["p2"]["description"], "written by B")

    @unittest.expectedFailure
    def test_same_project_legacy_and_execution_snapshots_should_preserve_owned_fields(self):
        """Documents stale legacy data overwriting execution-owned fields."""
        legacy = self.store.load_all()
        execution = copy.deepcopy(legacy)
        legacy["projects"][0]["activity"].append({"type": "legacy"})
        execution["projects"][0]["workflowPhase"] = "executing"

        self.store.save_all(execution)
        self.store.save_all(legacy)

        latest = self.store.get_project("p1")
        self.assertEqual(latest["workflowPhase"], "executing")
        self.assertEqual(latest["activity"], [{"type": "legacy"}])

    def test_direct_delete_removes_only_the_target_project(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            self.assertTrue(self.store.delete_project("p1"))
            latest = self.store.load_all()
            self.assertEqual([item["id"] for item in latest["projects"]], ["p2"])
            self.assertFalse(self.store.delete_project("missing"))


if __name__ == "__main__":
    unittest.main()
