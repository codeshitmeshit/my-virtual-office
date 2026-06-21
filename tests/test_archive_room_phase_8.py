#!/usr/bin/env python3
"""Focused coverage for Archive Room phase 8 scheduling and auto governance."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-archive-room-phase8-import-")
IMPORT_OC_HOME = tempfile.mkdtemp(prefix="vo-archive-room-phase8-openclaw-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR
os.environ["VO_OPENCLAW_PATH"] = IMPORT_OC_HOME

import server
from project_store import MarkdownProjectStore


def with_phase8_store(status_dir, oc_home):
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


def restore_phase8_store(old):
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
    old = with_phase8_store(status_dir.name, oc_home.name)
    install_fake_gateway(oc_home.name)
    return status_dir, oc_home, old


def teardown_store(status_dir, oc_home, old):
    restore_phase8_store(old)
    status_dir.cleanup()
    oc_home.cleanup()


def make_project(title="Phase 8 Governance"):
    return server._handle_project_create({
        "title": title,
        "description": "Validate archive scheduling and archive-manager-first governance.",
    })["project"]


def test_schedule_mode_update_persists_and_rejects_unknown_values():
    status_dir, oc_home, old = setup_store()
    try:
        project = make_project()
        default_detail = server._handle_archive_room_project(project["id"])["project"]
        assert default_detail["archiveMaintenance"]["scheduleMode"] == server.ARCHIVE_SCHEDULE_DAILY
        assert "每日" in default_detail["archiveMaintenance"]["frequencyLabel"]

        updated = server._handle_archive_project_maintenance_update(project["id"], {"scheduleMode": "weekly"})
        assert updated["ok"] is True
        assert updated["maintenance"]["scheduleMode"] == server.ARCHIVE_SCHEDULE_WEEKLY
        assert "每周" in updated["maintenance"]["frequencyLabel"]

        disabled = server._handle_archive_project_maintenance_update(project["id"], {"enabled": False})
        assert disabled["maintenance"]["enabled"] is False
        assert disabled["maintenance"]["scheduleMode"] == server.ARCHIVE_SCHEDULE_WEEKLY

        bad = server._handle_archive_project_maintenance_update(project["id"], {"scheduleMode": "hourly-ish"})
        assert bad["_status"] == 400
    finally:
        teardown_store(status_dir, oc_home, old)


def test_event_only_skips_scheduled_inspection_but_keeps_event_trigger_active():
    status_dir, oc_home, old = setup_store()
    try:
        project = make_project("Phase 8 Event Only")
        server._handle_archive_project_maintenance_update(project["id"], {"scheduleMode": "event_only"})

        inspection = server._archive_run_inspection("daily_inspection")
        skipped = next(item for item in inspection["results"] if item["projectId"] == project["id"])
        assert skipped["status"] == "skipped"
        detail = server._handle_archive_room_project(project["id"])["project"]
        assert "仅事件触发" in detail["archiveMaintenance"]["frequencyLabel"]
        assert "仅事件触发" in detail["archiveMaintenance"]["lastSkippedReason"]

        event = server._archive_maintenance_trigger(
            project["id"],
            "important_message",
            source=server._archive_source_ref("chat", "phase8-event", title="Phase8 event"),
            title="运行事实",
            summary="低风险运行事实由档案管理员记录。",
            value_level="normal",
            impact="summary",
        )
        assert event["ok"] is True
        detail2 = server._handle_archive_room_project(project["id"])["project"]
        assert detail2["archiveMaintenance"]["lastEventTriggeredAt"]
        assert detail2["pendingConfirmations"] == []
    finally:
        teardown_store(status_dir, oc_home, old)


def test_archive_manager_auto_supersedes_non_human_context_and_context_excludes_stale():
    status_dir, oc_home, old = setup_store()
    try:
        project = make_project("Phase 8 Auto Governance")
        first = server._archive_maintenance_trigger(
            project["id"],
            "meeting_conclusion",
            source=server._archive_source_ref("meeting", "m-old", title="Old meeting"),
            title="当前交付范围",
            summary="当前交付范围包括频率展示。",
            value_level="high",
            impact="state",
            reason="非人工确认的阶段会议摘要。",
        )
        assert first["ok"] is True
        second = server._archive_maintenance_trigger(
            project["id"],
            "meeting_conclusion",
            source=server._archive_source_ref("meeting", "m-new", title="New meeting"),
            title="当前交付范围",
            summary="当前交付范围包括频率展示和来源对比。",
            value_level="high",
            impact="state",
            reason="更新后的会议摘要来源更强。",
        )
        assert second["ok"] is True

        detail = server._handle_archive_room_project(project["id"])["project"]
        entries = [e for e in detail["entries"] if e["title"] == "当前交付范围"]
        stale_entries = [e for e in entries if e.get("stale")]
        current_entries = [e for e in entries if not e.get("stale")]
        assert stale_entries
        assert current_entries
        assert stale_entries[0]["replacedBy"] == current_entries[0]["id"]
        assert current_entries[0]["replaces"] == stale_entries[0]["id"]
        assert current_entries[0]["sourceComparison"]["oldEntryId"] == stale_entries[0]["id"]
        assert detail["automaticGovernanceNotices"]
        assert detail["pendingConfirmations"] == []

        context = server._handle_archive_room_context(project["id"])["context"]
        active_text = "\n".join(item.get("text", "") for item in context["items"])
        assert "频率展示和来源对比" in active_text
        assert "包括频率展示。" not in active_text
    finally:
        teardown_store(status_dir, oc_home, old)


def test_human_confirmed_conflict_stays_in_owner_queue():
    status_dir, oc_home, old = setup_store()
    try:
        project = make_project("Phase 8 Human Boundary")
        seed = server._archive_maintenance_trigger(
            project["id"],
            "meeting_conclusion",
            source=server._archive_source_ref("meeting", "human-seed", title="Owner rule"),
            title="发布规则",
            summary="Rule: release requires owner approval.",
            value_level="high",
            impact="state",
        )
        assert seed["ok"] is True
        pending_id = server._handle_archive_room_project(project["id"])["project"]["pendingConfirmations"][0]["id"]
        server._handle_archive_governance_action(project["id"], pending_id, {"action": "confirm"})

        conflict = server._archive_maintenance_trigger(
            project["id"],
            "conflict_reminder",
            source=server._archive_source_ref("meeting", "conflict", title="AI suggestion"),
            title="发布规则",
            summary="New suggestion says release can proceed without owner approval.",
            value_level="high",
            impact="risk",
            reason="Conflicts with human-confirmed release rule.",
        )
        assert conflict["ok"] is True
        detail = server._handle_archive_room_project(project["id"])["project"]
        pending = detail["pendingConfirmations"][0]
        assert pending["humanDecisionNeeded"]
        assert pending["automationInsufficientReason"]
        assert pending["sourceComparison"]["oldEntryId"]
        assert not detail["automaticGovernanceNotices"]
    finally:
        teardown_store(status_dir, oc_home, old)


if __name__ == "__main__":
    test_schedule_mode_update_persists_and_rejects_unknown_values()
    test_event_only_skips_scheduled_inspection_but_keeps_event_trigger_active()
    test_archive_manager_auto_supersedes_non_human_context_and_context_excludes_stale()
    test_human_confirmed_conflict_stays_in_owner_queue()
    print("ok")
