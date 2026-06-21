#!/usr/bin/env python3
"""Focused coverage for Archive Room phase 7 governance."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-archive-room-phase7-import-")
IMPORT_OC_HOME = tempfile.mkdtemp(prefix="vo-archive-room-phase7-openclaw-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR
os.environ["VO_OPENCLAW_PATH"] = IMPORT_OC_HOME

import server
from project_store import MarkdownProjectStore


def with_phase7_store(status_dir, oc_home):
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


def restore_phase7_store(old):
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
            return {"ok": True, "agentId": agent_id}
        return {"ok": True}

    server._gateway_rpc_call = fake_rpc


def setup_store():
    status_dir = tempfile.TemporaryDirectory()
    oc_home = tempfile.TemporaryDirectory()
    old = with_phase7_store(status_dir.name, oc_home.name)
    install_fake_gateway(oc_home.name)
    return status_dir, oc_home, old


def teardown_store(status_dir, oc_home, old):
    restore_phase7_store(old)
    status_dir.cleanup()
    oc_home.cleanup()


def make_project():
    project = server._handle_project_create({"title": "Phase 7 Governance", "description": "Govern archive trust."})["project"]
    task = server._handle_task_create(project["id"], {"title": "Produce governed result"})["task"]
    return project, task


def test_source_and_manager_authority_do_not_flood_human_queue():
    status_dir, oc_home, old = setup_store()
    try:
        project, task = make_project()
        done = server._archive_trigger_task_completed(project["id"], {**task, "completedAt": "2026-06-20T00:00:00+08:00"})
        assert done["ok"] is True
        msg = server._handle_archive_mark_important_message({
            "projectId": project["id"],
            "messageId": "msg-low-risk",
            "text": "Low-risk context summary with direct source.",
        })
        assert msg["ok"] is True

        detail = server._handle_archive_room_project(project["id"])["project"]
        entries = detail["entries"]
        task_entry = next(e for e in entries if e.get("kind") == "task_completed")
        message_entry = next(e for e in entries if e.get("kind") == "important_message")
        assert task_entry["authority"] in {server.ARCHIVE_AUTH_SOURCE, server.ARCHIVE_AUTH_SYSTEM}
        assert message_entry["authority"] == server.ARCHIVE_AUTH_MANAGER
        assert detail["pendingConfirmations"] == []
    finally:
        teardown_store(status_dir, oc_home, old)


def test_high_impact_pending_can_be_confirmed_and_rejected_history_is_not_active():
    status_dir, oc_home, old = setup_store()
    try:
        project, _ = make_project()
        server._archive_maintenance_trigger(
            project["id"],
            "meeting_conclusion",
            source=server._archive_source_ref("meeting", "m1", title="Phase decision"),
            title="Meeting conclusion: phase decision",
            summary="Decision: require human approval for release policy.",
            value_level="high",
            impact="state",
        )
        detail = server._handle_archive_room_project(project["id"])["project"]
        pending_id = detail["pendingConfirmations"][0]["id"]
        confirmed = server._handle_archive_governance_action(project["id"], pending_id, {"action": "edit_confirm", "text": "Release policy requires human approval.", "reason": "Owner accepted."})
        assert confirmed["ok"] is True
        detail2 = confirmed["project"]
        assert not detail2["pendingConfirmations"]
        assert any(e.get("authority") == server.ARCHIVE_AUTH_HUMAN and "Release policy" in e.get("text", "") for e in detail2["entries"])
        assert detail2["processedGovernance"][-1]["status"] == server.ARCHIVE_AUTH_HUMAN

        server._archive_maintenance_trigger(
            project["id"],
            "meeting_conclusion",
            source=server._archive_source_ref("meeting", "m2", title="Rejected idea"),
            title="Meeting conclusion: rejected idea",
            summary="Decision: remove human approval.",
            value_level="high",
            impact="state",
        )
        detail3 = server._handle_archive_room_project(project["id"])["project"]
        pending_id2 = detail3["pendingConfirmations"][0]["id"]
        rejected = server._handle_archive_governance_action(project["id"], pending_id2, {"action": "reject", "reason": "Conflicts with accepted policy."})
        assert rejected["ok"] is True
        context = server._handle_archive_room_context(project["id"])["context"]
        assert not any("remove human approval" in item.get("text", "") for item in context["items"])
    finally:
        teardown_store(status_dir, oc_home, old)


def test_defer_and_conflict_visibility():
    status_dir, oc_home, old = setup_store()
    try:
        project, task = make_project()
        server._archive_maintenance_trigger(
            project["id"],
            "meeting_conclusion",
            source=server._archive_source_ref("meeting", "m-human", title="Rule"),
            title="Rule",
            summary="Rule: deployment requires owner approval.",
            value_level="high",
            impact="state",
        )
        pending_id = server._handle_archive_room_project(project["id"])["project"]["pendingConfirmations"][0]["id"]
        server._handle_archive_governance_action(project["id"], pending_id, {"action": "confirm"})

        server._archive_maintenance_trigger(
            project["id"],
            "conflict_reminder",
            source=server._archive_source_ref("task", task["id"], title=task["title"]),
            title="Conflict reminder",
            summary="Task suggests deployment can proceed without approval.",
            value_level="high",
            impact="risk",
            reason="Conflicts with human-confirmed deployment rule.",
        )
        detail = server._handle_archive_room_project(project["id"])["project"]
        conflict = detail["pendingConfirmations"][0]
        assert conflict["conflict"] is True
        assert conflict["conflictSummary"]
        deferred = server._handle_archive_governance_action(project["id"], conflict["id"], {"action": "defer", "reason": "Need owner review."})
        assert deferred["ok"] is True
        deferred_item = deferred["project"]["pendingConfirmations"][-1]
        assert deferred_item["authority"] == server.ARCHIVE_AUTH_DEFERRED
    finally:
        teardown_store(status_dir, oc_home, old)


if __name__ == "__main__":
    test_source_and_manager_authority_do_not_flood_human_queue()
    test_high_impact_pending_can_be_confirmed_and_rejected_history_is_not_active()
    test_defer_and_conflict_visibility()
    print("ok")
