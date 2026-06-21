#!/usr/bin/env python3
"""Focused coverage for Archive Room phase 1-3."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-archive-room-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR

import server
from project_store import MarkdownProjectStore


def with_archive_store(status_dir):
    old = (
        server.STATUS_DIR,
        server.PROJECT_STORE,
        server.ARCHIVE_ROOM_DIR,
        server.ARCHIVE_ROOM_PROJECTS_DIR,
    )
    server.STATUS_DIR = status_dir
    server.PROJECT_STORE = MarkdownProjectStore(status_dir)
    server.ARCHIVE_ROOM_DIR = os.path.join(status_dir, "archive-room")
    server.ARCHIVE_ROOM_PROJECTS_DIR = os.path.join(server.ARCHIVE_ROOM_DIR, "projects")
    return old


def restore_archive_store(old):
    (
        server.STATUS_DIR,
        server.PROJECT_STORE,
        server.ARCHIVE_ROOM_DIR,
        server.ARCHIVE_ROOM_PROJECTS_DIR,
    ) = old


def create_project(title="Archive Project", workspace=None, execution=True):
    body = {"title": title, "description": "Project archive description."}
    if execution:
        body["projectExecutionEnabled"] = True
        body["workspacePath"] = workspace
    return server._handle_project_create(body)["project"]


def test_archive_overview_persists_under_status_dir_and_sorts_attention_first():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_archive_store(status_dir)
        try:
            quiet = create_project("Quiet Project", workspace)
            risky = create_project("Risky Project", workspace)
            task = server._handle_task_create(risky["id"], {
                "title": "Blocked task",
                "columnId": risky["columns"][0]["id"],
            })["task"]
            task["executionState"] = "blocked"
            task["blockedReason"] = "Needs decision"
            data = server._load_projects()
            for p in data["projects"]:
                if p["id"] == risky["id"]:
                    p["tasks"] = [task]
            server._save_projects(data)

            overview = server._handle_archive_room_overview()
            assert overview["ok"] is True
            assert overview["projects"][0]["id"] == risky["id"]
            assert overview["projects"][0]["metrics"]["riskCount"] >= 1
            assert isinstance(overview.get("archiveManager"), dict)

            path = server._archive_room_project_file(quiet["id"])
            assert os.path.realpath(path).startswith(os.path.realpath(status_dir) + os.sep)
            assert os.path.isfile(path)

            reloaded = server._handle_archive_room_project(quiet["id"])
            assert reloaded["ok"] is True
            assert reloaded["project"]["projectId"] == quiet["id"]
        finally:
            restore_archive_store(old)


def test_archive_artifacts_only_include_explicitly_associated_supported_files():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_archive_store(status_dir)
        try:
            associated = os.path.join(workspace, "deliverable.md")
            unassociated = os.path.join(workspace, "notes.md")
            image = os.path.join(workspace, "shot.png")
            with open(associated, "w", encoding="utf-8") as f:
                f.write("# Deliverable\n")
            with open(unassociated, "w", encoding="utf-8") as f:
                f.write("# Notes\n")
            with open(image, "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n")

            project = create_project("Artifact Project", workspace)
            task = server._handle_task_create(project["id"], {
                "title": "Produce artifact",
                "columnId": project["columns"][0]["id"],
            })["task"]
            task["evidence"] = {
                "changedFiles": ["deliverable.md", "shot.png"],
                "summary": "Created deliverable.md and shot.png",
                "capturedAt": "2026-06-19T00:00:00+00:00",
            }
            data = server._load_projects()
            for p in data["projects"]:
                if p["id"] == project["id"]:
                    p["tasks"] = [task]
            server._save_projects(data)

            detail = server._handle_archive_room_project(project["id"])
            assert detail["ok"] is True
            paths = {a["path"]: a for a in detail["project"]["artifacts"]}
            assert "deliverable.md" in paths
            assert "shot.png" in paths
            assert "notes.md" not in paths
            assert paths["shot.png"]["kind"] == "image"

            read = server._handle_project_artifact_read(project["id"], "archive=1&path=deliverable.md")
            assert read["ok"] is True
            assert "Deliverable" in read["artifact"]["content"]
        finally:
            restore_archive_store(old)


def test_archive_artifact_file_blocks_traversal_and_unassociated_files():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_archive_store(status_dir)
        try:
            with open(os.path.join(workspace, "registered.mp4"), "wb") as f:
                f.write(b"video")
            with open(os.path.join(workspace, "secret.mp4"), "wb") as f:
                f.write(b"secret")

            project = create_project("Safe Artifact Project", workspace)
            task = server._handle_task_create(project["id"], {
                "title": "Register video",
                "columnId": project["columns"][0]["id"],
            })["task"]
            task["evidence"] = {"changedFiles": ["registered.mp4"], "capturedAt": "2026-06-19T00:00:00+00:00"}
            data = server._load_projects()
            for p in data["projects"]:
                if p["id"] == project["id"]:
                    p["tasks"] = [task]
            server._save_projects(data)

            ok = server._handle_project_artifact_file(project["id"], "path=registered.mp4")
            assert ok["ok"] is True
            assert ok["kind"] == "video"

            unassociated = server._handle_project_artifact_file(project["id"], "path=secret.mp4")
            assert unassociated["_status"] == 403

            traversal = server._handle_project_artifact_file(project["id"], "path=../secret.mp4")
            assert traversal["_status"] == 400
        finally:
            restore_archive_store(old)


if __name__ == "__main__":
    test_archive_overview_persists_under_status_dir_and_sorts_attention_first()
    test_archive_artifacts_only_include_explicitly_associated_supported_files()
    test_archive_artifact_file_blocks_traversal_and_unassociated_files()
    print("ok")
