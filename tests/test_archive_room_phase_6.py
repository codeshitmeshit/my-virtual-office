#!/usr/bin/env python3
"""Focused coverage for Archive Room phase 6."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-archive-room-phase6-import-")
IMPORT_OC_HOME = tempfile.mkdtemp(prefix="vo-archive-room-phase6-openclaw-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR
os.environ["VO_OPENCLAW_PATH"] = IMPORT_OC_HOME

import server
from project_store import MarkdownProjectStore


def with_phase6_store(status_dir, oc_home):
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


def restore_phase6_store(old):
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
    old = with_phase6_store(status_dir.name, oc_home.name)
    install_fake_gateway(oc_home.name)
    return status_dir, oc_home, old


def teardown_store(status_dir, oc_home, old):
    restore_phase6_store(old)
    status_dir.cleanup()
    oc_home.cleanup()


def make_project(title="Phase 6 Project", description="Build a finance archive with strict source-backed reporting."):
    project = server._handle_project_create({"title": title, "description": description})["project"]
    task = server._handle_task_create(project["id"], {
        "title": "Prepare project-specific report",
        "description": "Use confirmed archive facts and cite sources.",
    })["task"]
    return project, task


def test_archive_intro_basic_info_and_maps():
    status_dir, oc_home, old = setup_store()
    try:
        project, _ = make_project()
        detail = server._handle_archive_room_project(project["id"])["project"]

        intro = detail["archiveIntroduction"]
        assert "档案" in intro["title"]
        assert intro["brief"]
        assert len(intro["brief"]) <= 39
        assert "人类" in intro["purpose"]
        assert "AI" in intro["aiUse"]

        basic = detail["projectBasicInfo"]
        assert basic["name"] == project["title"]
        assert basic["description"]
        assert basic["taskProgress"].endswith("/ 1")
        assert basic["maintenanceLabel"]

        content_keys = {item["key"] for item in detail["archiveContentMap"]}
        usage_keys = {item["key"] for item in detail["archiveUsageMap"]}
        assert {"basic_info", "tasks", "artifacts", "pending_confirmations"} <= content_keys
        assert {"human_review", "handoff", "ai_onboarding", "task_context"} <= usage_keys

        index = detail["archiveIndexHighlights"]
        section_labels = {section["label"] for section in index["sections"]}
        assert {"当前任务", "关键决策", "风险/冲突", "待确认", "关键产物"} <= section_labels
        assert any(item["label"] == "当前任务" for item in index["attention"])
        current_task = next(section for section in index["sections"] if section["key"] == "current_task")
        assert current_task["items"][0]["title"] == "Prepare project-specific report"
    finally:
        teardown_store(status_dir, oc_home, old)


def test_context_package_is_task_first_and_preserves_confidence():
    status_dir, oc_home, old = setup_store()
    try:
        project, task = make_project()
        server._archive_maintenance_trigger(
            project["id"],
            "meeting_conclusion",
            source=server._archive_source_ref("meeting", "m1", title="Scope decision"),
            title="Meeting conclusion: scope",
            summary="Decision: reports must include source-backed assumptions.",
            value_level="high",
            impact="state",
        )
        for idx in range(4):
            server._archive_maintenance_trigger(
                project["id"],
                "important_message",
                source=server._archive_source_ref("chat", f"msg-{idx}", title="Important message"),
                title=f"Important message {idx}",
                summary=f"Important context note {idx}.",
                value_level="normal",
            )

        result = server._handle_archive_room_context(project["id"], f"taskId={task['id']}")
        assert result["ok"] is True
        context = result["context"]
        assert context["mode"] == "task"
        assert context["task"]["id"] == task["id"]
        assert context["conclusions"][0].startswith("当前任务")
        assert context["sourceReferences"]
        assert any(item["confidence"] in {server.ARCHIVE_INFERENCE, server.ARCHIVE_PENDING, server.ARCHIVE_CONFIRMED} for item in context["items"])
        assert context["optionalNextLoads"]
    finally:
        teardown_store(status_dir, oc_home, old)


def test_project_characterized_context_differs_by_project_and_has_boundary():
    status_dir, oc_home, old = setup_store()
    try:
        finance, finance_task = make_project("Finance Archive", "Finance reporting requires source-backed market assumptions.")
        design, design_task = make_project("Design Archive", "Design work prioritizes visual acceptance and media previews.")

        finance_ctx = server._handle_archive_room_context(finance["id"], f"taskId={finance_task['id']}")["context"]
        design_ctx = server._handle_archive_room_context(design["id"], f"taskId={design_task['id']}")["context"]

        assert "Finance" in finance_ctx["projectCharacteristics"]["businessBackground"]
        assert "Design" in design_ctx["projectCharacteristics"]["businessBackground"]
        assert finance_ctx["projectCharacteristics"]["businessBackground"] != design_ctx["projectCharacteristics"]["businessBackground"]
        assert "不改写 AI" in finance_ctx["boundary"]

        prompt = server._archive_context_prompt_block(finance, finance_task)
        assert "supplemental" in prompt
        assert "does not override your identity" in prompt
        assert "Finance" in prompt
    finally:
        teardown_store(status_dir, oc_home, old)


def test_missing_and_severe_reminders_are_graded():
    status_dir, oc_home, old = setup_store()
    try:
        project, task = make_project("Sparse Project", "")
        server._archive_maintenance_trigger(
            project["id"],
            "conflict_reminder",
            source=server._archive_source_ref("task", task["id"], title=task["title"]),
            title="Conflict reminder",
            summary="Task conflicts with a confirmed archive rule.",
            value_level="high",
            impact="risk",
        )

        context = server._handle_archive_room_context(project["id"], f"taskId={task['id']}")["context"]
        reminders = context["reminders"]
        assert any(r["severity"] == "missing" and r["proactive"] is False for r in reminders)
        assert any(r["severity"] == "severe_conflict" and r["proactive"] is True for r in reminders)
    finally:
        teardown_store(status_dir, oc_home, old)


if __name__ == "__main__":
    test_archive_intro_basic_info_and_maps()
    test_context_package_is_task_first_and_preserves_confidence()
    test_project_characterized_context_differs_by_project_and_has_boundary()
    test_missing_and_severe_reminders_are_graded()
    print("ok")
