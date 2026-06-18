#!/usr/bin/env python3
"""Phase 5 coverage for long-term project scheduled cron recommendations."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-project-cron-phase5-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR

import server
from project_store import MarkdownProjectStore


def with_store(status_dir):
    old = (server.STATUS_DIR, server.PROJECT_STORE)
    server.STATUS_DIR = status_dir
    server.PROJECT_STORE = MarkdownProjectStore(status_dir)
    return old


def restore_store(old):
    server.STATUS_DIR, server.PROJECT_STORE = old


def test_long_term_project_is_created_listed_updated_and_persisted():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            created = server._handle_project_create({
                "title": "Phase 5 Long Term",
                "createdBy": "tester",
                "projectExecutionEnabled": False,
                "longTermProject": True,
            })
            assert created["ok"] is True
            project_id = created["project"]["id"]
            assert created["project"]["longTermProject"] is True

            summary = server._handle_projects_list()["projects"][0]
            assert summary["id"] == project_id
            assert summary["longTermProject"] is True

            updated = server._handle_project_update(project_id, {"longTermProject": False})
            assert updated["ok"] is True
            assert updated["project"]["longTermProject"] is False

            reloaded = MarkdownProjectStore(status_dir).get_project(project_id)
            assert reloaded["longTermProject"] is False
        finally:
            restore_store(old)


def test_old_project_without_long_term_field_defaults_false():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            created = server._handle_project_create({
                "title": "Phase 5 Old Project",
                "createdBy": "tester",
                "projectExecutionEnabled": False,
            })
            project_id = created["project"]["id"]

            data, project = server._project_find(project_id)
            project.pop("longTermProject", None)
            server._save_projects(data)

            _, reloaded = server._project_find(project_id)
            assert reloaded.get("longTermProject") is False
            summary = server._handle_projects_list()["projects"][0]
            assert summary["longTermProject"] is False
        finally:
            restore_store(old)


if __name__ == "__main__":
    test_long_term_project_is_created_listed_updated_and_persisted()
    test_old_project_without_long_term_field_defaults_false()
    print("ok")
