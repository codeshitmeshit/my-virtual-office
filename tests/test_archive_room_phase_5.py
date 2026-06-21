#!/usr/bin/env python3
"""Focused coverage for Archive Room phase 5."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-archive-room-phase5-import-")
IMPORT_OC_HOME = tempfile.mkdtemp(prefix="vo-archive-room-phase5-openclaw-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR
os.environ["VO_OPENCLAW_PATH"] = IMPORT_OC_HOME

import server
from project_store import MarkdownProjectStore


def with_phase5_store(status_dir, oc_home):
    old = (
        server.STATUS_DIR,
        server.PROJECT_STORE,
        server.ARCHIVE_ROOM_DIR,
        server.ARCHIVE_ROOM_PROJECTS_DIR,
        server.WORKSPACE_BASE,
        server._discovered_roster,
        server._discovered_at,
        server._gateway_rpc_call,
    )
    server.STATUS_DIR = status_dir
    server.PROJECT_STORE = MarkdownProjectStore(status_dir)
    server.ARCHIVE_ROOM_DIR = os.path.join(status_dir, "archive-room")
    server.ARCHIVE_ROOM_PROJECTS_DIR = os.path.join(server.ARCHIVE_ROOM_DIR, "projects")
    server.WORKSPACE_BASE = oc_home
    server._discovered_roster = []
    server._discovered_at = 0
    return old


def restore_phase5_store(old):
    (
        server.STATUS_DIR,
        server.PROJECT_STORE,
        server.ARCHIVE_ROOM_DIR,
        server.ARCHIVE_ROOM_PROJECTS_DIR,
        server.WORKSPACE_BASE,
        server._discovered_roster,
        server._discovered_at,
        server._gateway_rpc_call,
    ) = old
    server.refresh_agent_maps()


def install_fake_gateway(oc_home):
    def fake_rpc(method, params=None, timeout=20):
        params = params or {}
        if method == "agents.list":
            return {"ok": True, "agents": [{"id": "main", "model": "fake-model"}]}
        if method == "agents.create":
            agent_id = "archive-manager"
            workspace = params.get("workspace") or os.path.join(oc_home, "workspace-archive-manager")
            os.makedirs(os.path.join(oc_home, "agents", agent_id, "sessions"), exist_ok=True)
            os.makedirs(workspace, exist_ok=True)
            cfg_path = os.path.join(oc_home, "openclaw.json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                __import__("json").dump({"agents": {"list": [{"id": agent_id, "name": agent_id, "workspace": workspace}]}}, f)
            return {"ok": True, "agentId": agent_id}
        return {"ok": True}

    server._gateway_rpc_call = fake_rpc


def setup_store():
    status_dir = tempfile.TemporaryDirectory()
    oc_home = tempfile.TemporaryDirectory()
    old = with_phase5_store(status_dir.name, oc_home.name)
    install_fake_gateway(oc_home.name)
    return status_dir, oc_home, old


def teardown_store(status_dir, oc_home, old):
    restore_phase5_store(old)
    status_dir.cleanup()
    oc_home.cleanup()


def test_maintenance_defaults_and_toggle():
    status_dir, oc_home, old = setup_store()
    try:
        active = server._handle_project_create({"title": "Active Project"})["project"]
        done = server._handle_project_create({"title": "Done Project", "status": "completed"})["project"]

        active_detail = server._handle_archive_room_project(active["id"])["project"]
        done_detail = server._handle_archive_room_project(done["id"])["project"]
        assert active_detail["archiveMaintenance"]["enabled"] is True
        assert done_detail["archiveMaintenance"]["enabled"] is False

        toggled = server._handle_archive_project_maintenance_update(active["id"], {"enabled": False})
        assert toggled["maintenance"]["enabled"] is False
        detail = server._handle_archive_room_project(active["id"])["project"]
        assert detail["archiveMaintenance"]["enabled"] is False
        assert "高价值事件" in detail["archiveMaintenance"]["explanation"]
    finally:
        teardown_store(status_dir, oc_home, old)


def test_task_completion_triggers_idempotent_archive_entry_when_maintenance_off():
    status_dir, oc_home, old = setup_store()
    try:
        project = server._handle_project_create({"title": "Task Trigger", "archiveMaintenanceEnabled": False})["project"]
        task = server._handle_task_create(project["id"], {"title": "Finish me"})["task"]
        done_col = next(c for c in project["columns"] if c["title"] == "Done")

        updated = server._handle_task_update(project["id"], task["id"], {"columnId": done_col["id"]})
        assert updated["ok"] is True
        detail = server._handle_archive_room_project(project["id"])["project"]
        entries = [e for e in detail["entries"] if e.get("kind") == "task_completed"]
        assert len(entries) == 1
        assert detail["managerMaintenance"][-1]["eventType"] == "task_completed"

        server._handle_task_update(project["id"], task["id"], {"title": "Finish me again"})
        detail2 = server._handle_archive_room_project(project["id"])["project"]
        entries2 = [e for e in detail2["entries"] if e.get("kind") == "task_completed"]
        assert len(entries2) == 1
    finally:
        teardown_store(status_dir, oc_home, old)


def test_low_value_skips_when_maintenance_off_and_daily_inspection_updates_only_maintained():
    status_dir, oc_home, old = setup_store()
    try:
        maintained = server._handle_project_create({"title": "Maintained"})["project"]
        skipped = server._handle_project_create({"title": "Skipped", "archiveMaintenanceEnabled": False})["project"]

        low = server._archive_maintenance_trigger(
            skipped["id"],
            "low_value_activity",
            source=server._archive_source_ref("chat", "m1"),
            title="Low value",
            summary="Small talk",
            value_level="low",
        )
        assert low["status"] == "skipped"
        low_detail = server._handle_archive_room_project(skipped["id"])["project"]
        assert not any(e.get("kind") == "low_value_activity" for e in low_detail["entries"])

        inspection = server._handle_archive_daily_inspection({"force": True})
        assert inspection["ok"] is True
        maintained_detail = server._handle_archive_room_project(maintained["id"])["project"]
        skipped_detail = server._handle_archive_room_project(skipped["id"])["project"]
        assert maintained_detail["inspections"].get("lastDailyInspectionAt")
        assert not skipped_detail["inspections"].get("lastDailyInspectionAt")
    finally:
        teardown_store(status_dir, oc_home, old)


def test_important_message_and_meeting_conclusion_create_pending_context():
    status_dir, oc_home, old = setup_store()
    try:
        project = server._handle_project_create({"title": "Collab Trigger"})["project"]
        msg = server._handle_archive_mark_important_message({
            "projectId": project["id"],
            "messageId": "msg-1",
            "text": "This is an important project decision.",
        })
        assert msg["ok"] is True
        detail = server._handle_archive_room_project(project["id"])["project"]
        assert any(e.get("kind") == "important_message" for e in detail["entries"])

        meeting = {
            "id": "meeting-1",
            "projectId": project["id"],
            "topic": "Decide path",
            "result": {"summary": "We decided to ship Phase 5 incrementally."},
        }
        server._archive_trigger_meeting_conclusion(meeting)
        detail2 = server._handle_archive_room_project(project["id"])["project"]
        assert any(e.get("kind") == "meeting_conclusion" for e in detail2["entries"])
        assert any(p.get("impact") == "state" for p in detail2["pendingConfirmations"])
    finally:
        teardown_store(status_dir, oc_home, old)


def test_pause_skips_automatic_triggers():
    status_dir, oc_home, old = setup_store()
    try:
        project = server._handle_project_create({"title": "Paused Trigger"})["project"]
        pause = server._handle_archive_manager_update({"action": "pause"})
        assert pause["archiveManager"]["paused"] is True
        result = server._archive_maintenance_trigger(
            project["id"],
            "project_status_changed",
            source=server._archive_source_ref("project", project["id"]),
            title="Project status changed",
            summary="status changed",
            value_level="high",
        )
        assert result["status"] == "skipped"
        assert "暂停" in result["activity"]["summary"]
    finally:
        teardown_store(status_dir, oc_home, old)


if __name__ == "__main__":
    test_maintenance_defaults_and_toggle()
    test_task_completion_triggers_idempotent_archive_entry_when_maintenance_off()
    test_low_value_skips_when_maintenance_off_and_daily_inspection_updates_only_maintained()
    test_important_message_and_meeting_conclusion_create_pending_context()
    test_pause_skips_automatic_triggers()
    print("ok")
