#!/usr/bin/env python3
"""Focused coverage for Archive Room phase 4."""

import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-archive-room-phase4-import-")
IMPORT_OC_HOME = tempfile.mkdtemp(prefix="vo-archive-room-phase4-openclaw-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR
os.environ["VO_OPENCLAW_PATH"] = IMPORT_OC_HOME

import server
from project_store import MarkdownProjectStore


def with_phase4_store(status_dir, oc_home):
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


def restore_phase4_store(old):
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


def install_fake_gateway(oc_home, fail_create=False):
    calls = []
    files = {}

    def fake_rpc(method, params=None, timeout=20):
        params = params or {}
        calls.append((method, dict(params)))
        if method == "agents.list":
            return {"ok": True, "agents": [{"id": "main", "model": "fake-model"}]}
        if method == "agents.create":
            if fail_create:
                return {"ok": False, "error": "gateway unavailable"}
            agent_id = "archive-manager"
            workspace = params.get("workspace") or os.path.join(oc_home, "workspace-archive-manager")
            os.makedirs(os.path.join(oc_home, "agents", agent_id, "sessions"), exist_ok=True)
            os.makedirs(workspace, exist_ok=True)
            cfg_path = os.path.join(oc_home, "openclaw.json")
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = __import__("json").load(f)
            except Exception:
                cfg = {"agents": {"list": []}}
            agents = cfg.setdefault("agents", {}).setdefault("list", [])
            if not any(a.get("id") == agent_id for a in agents):
                agents.append({"id": agent_id, "name": params.get("name"), "workspace": workspace, "model": params.get("model", "")})
            with open(cfg_path, "w", encoding="utf-8") as f:
                __import__("json").dump(cfg, f)
            return {"ok": True, "agentId": agent_id}
        if method == "agents.files.set":
            agent_id = params.get("agentId")
            name = params.get("name")
            content = params.get("content", "")
            workspace = os.path.join(oc_home, f"workspace-{agent_id}")
            os.makedirs(workspace, exist_ok=True)
            with open(os.path.join(workspace, name), "w", encoding="utf-8") as f:
                f.write(content)
            files[name] = content
            return {"ok": True}
        return {"ok": True}

    server._gateway_rpc_call = fake_rpc
    return calls, files


def test_archive_manager_auto_create_idempotent_and_profile_files():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as oc_home:
        old = with_phase4_store(status_dir, oc_home)
        try:
            calls, files = install_fake_gateway(oc_home)
            overview = server._handle_archive_room_overview()
            manager = overview["archiveManager"]
            assert manager["status"] == "idle"
            assert manager["label"] == "已自动创建"
            assert manager["autoCreated"] is True
            assert manager["profileVersion"] == server._archive_manager_profile_template_version()
            agent_md = os.path.join(oc_home, "workspace-archive-manager", "agent.md")
            assert os.path.exists(agent_md)
            with open(agent_md, "r", encoding="utf-8") as f:
                assert "不承担普通执行任务" in f.read()
            with open(os.path.join(oc_home, "workspace-archive-manager", "AGENTS.md"), "r", encoding="utf-8") as f:
                assert "vo-archive-manager" in f.read()

            second = server._handle_archive_room_overview()
            assert second["archiveManager"]["agentId"] == "archive-manager"
            create_calls = [c for c in calls if c[0] == "agents.create"]
            assert len(create_calls) == 1
        finally:
            restore_phase4_store(old)


def test_archive_manager_profile_files_load_from_template():
    profile = server._archive_manager_profile_files()
    assert profile["IDENTITY.md"].count("档案管理员") == 1
    assert "🗄️" in profile["IDENTITY.md"]
    assert server._archive_manager_profile_template_version() in profile["IDENTITY.md"]
    assert "vo-archive-manager" in profile["AGENTS.md"]
    assert "Manual Current-Project Maintenance Procedure" in profile["AGENTS.md"]
    assert "Field Rules" in profile["AGENTS.md"]
    assert "Use `status: needs_confirmation`" in profile["AGENTS.md"]
    assert "不承担普通执行任务" in profile["agent.md"]
    with open(os.path.join(APP_DIR, "server.py"), "r", encoding="utf-8") as f:
        server_source = f.read()
    assert "When producing operational maintenance output for Virtual Office" not in server_source


def test_archive_manager_existing_agent_updates_stale_profile_version():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as oc_home:
        old = with_phase4_store(status_dir, oc_home)
        try:
            install_fake_gateway(oc_home)
            create = server._gateway_rpc_call("agents.create", {"name": "archive-manager", "workspace": os.path.join(oc_home, "workspace-archive-manager")})
            assert create["ok"] is True
            workspace = os.path.join(oc_home, "workspace-archive-manager")
            with open(os.path.join(workspace, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("<!-- archive-manager-profile-version: old-version -->\n# stale\n")
            server._discovered_at = 0

            overview = server._handle_archive_room_overview()
            manager = overview["archiveManager"]
            assert manager["status"] == "idle"
            assert manager["profileVersion"] == server._archive_manager_profile_template_version()
            assert manager["recentActivity"][-1]["action"] == "profile_update"
            with open(os.path.join(workspace, "AGENTS.md"), "r", encoding="utf-8") as f:
                content = f.read()
            assert f"archive-manager-profile-version: {server._archive_manager_profile_template_version()}" in content
            assert "Manual Current-Project Maintenance Procedure" in content
        finally:
            restore_phase4_store(old)


def test_archive_manager_existing_agent_repairs_profile_files():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as oc_home:
        old = with_phase4_store(status_dir, oc_home)
        try:
            calls, files = install_fake_gateway(oc_home)
            create = server._gateway_rpc_call("agents.create", {"name": "archive-manager", "workspace": os.path.join(oc_home, "workspace-archive-manager")})
            assert create["ok"] is True
            server._discovered_at = 0

            overview = server._handle_archive_room_overview()
            manager = overview["archiveManager"]
            assert manager["status"] == "idle"
            assert manager["label"] == "已接入"
            with open(os.path.join(oc_home, "workspace-archive-manager", "AGENTS.md"), "r", encoding="utf-8") as f:
                assert "vo-archive-manager" in f.read()
            with open(os.path.join(oc_home, "workspace-archive-manager", "agent.md"), "r", encoding="utf-8") as f:
                assert "不承担普通执行任务" in f.read()
            create_calls = [c for c in calls if c[0] == "agents.create"]
            assert len(create_calls) == 1
        finally:
            restore_phase4_store(old)


def test_archive_manager_creation_failure_degrades_readonly():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as oc_home:
        old = with_phase4_store(status_dir, oc_home)
        try:
            install_fake_gateway(oc_home, fail_create=True)
            project = server._handle_project_create({"title": "Readable"})["project"]
            overview = server._handle_archive_room_overview()
            assert overview["archiveManager"]["status"] == "error"
            assert overview["archiveManager"]["label"] == "档案管理员创建失败"
            assert any(p["id"] == project["id"] for p in overview["projects"])
            detail = server._handle_archive_room_project(project["id"])
            assert detail["ok"] is True
        finally:
            restore_phase4_store(old)


def test_archive_manager_pause_resume_and_manual_maintain_current_project():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as oc_home:
        old = with_phase4_store(status_dir, oc_home)
        try:
            install_fake_gateway(oc_home)
            project = server._handle_project_create({"title": "Maintain Me"})["project"]
            pause = server._handle_archive_manager_update({"action": "pause"})
            assert pause["ok"] is True
            assert pause["archiveManager"]["paused"] is True
            detail = server._handle_archive_room_project(project["id"])
            assert detail["project"]["archiveManager"]["paused"] is True

            maintained = server._handle_archive_manager_manual_maintain(project["id"])
            assert maintained["ok"] is True
            assert maintained["archiveManager"]["paused"] is True
            assert maintained["project"]["managerMaintenance"][-1]["output"]["status"] == "ok"

            resume = server._handle_archive_manager_update({"action": "resume"})
            assert resume["ok"] is True
            assert resume["archiveManager"]["paused"] is False
            assert resume["archiveManager"]["status"] == "idle"
        finally:
            restore_phase4_store(old)


def test_archive_manager_cannot_be_deleted_or_assigned_to_project_tasks():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as oc_home:
        old = with_phase4_store(status_dir, oc_home)
        try:
            install_fake_gateway(oc_home)
            server._handle_archive_room_overview()
            blocked_delete = server._handle_agent_delete({"id": "archive-manager"})
            assert blocked_delete["_status"] == 403

            project_block = server._handle_project_create({
                "title": "Blocked Defaults",
                "defaultExecutorAgentId": "archive-manager",
            })
            assert project_block["_status"] == 400

            project = server._handle_project_create({"title": "Task Project"})["project"]
            task_block = server._handle_task_create(project["id"], {
                "title": "Should not assign",
                "assignee": "archive-manager",
            })
            assert task_block["_status"] == 400

            meta = server._agent_archive_manager_meta("archive-manager")
            assert meta["systemRole"] == "archive_manager"
            assert meta["assignable"] is False
        finally:
            restore_phase4_store(old)


def test_archive_manager_chat_boundary():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as oc_home:
        old = with_phase4_store(status_dir, oc_home)
        try:
            install_fake_gateway(oc_home)
            server._handle_archive_room_overview()
            unrelated = server._archive_manager_chat_guard("archive-manager", "帮我写一个登录页面")
            assert unrelated["status"] == "archive_manager_out_of_scope"
            assert "只处理档案室" in unrelated["reply"]
            related = server._archive_manager_chat_guard("archive-manager", "这个项目的档案上下文是什么？")
            assert related is None
        finally:
            restore_phase4_store(old)


@pytest.mark.xfail(
    strict=True,
    reason="Known pre-extraction defect: archive-manager reconciliation has no shared creation lock; task 2.4 must make this pass.",
)
def test_archive_manager_concurrent_reconciliation_creates_one_effective_agent():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as oc_home:
        old = with_phase4_store(status_dir, oc_home)
        try:
            calls, _ = install_fake_gateway(oc_home)
            with ThreadPoolExecutor(max_workers=2) as executor:
                states = list(executor.map(lambda _: server._archive_manager_create_if_missing(), range(2)))

            assert all(state["status"] == "idle" for state in states)
            assert len([call for call in calls if call[0] == "agents.create"]) == 1
        finally:
            restore_phase4_store(old)


def test_archive_manager_provider_timeout_is_persisted_as_degraded_error():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as oc_home:
        old = with_phase4_store(status_dir, oc_home)
        try:
            def timeout_rpc(method, params=None, timeout=20):
                raise TimeoutError(f"{method} timed out after {timeout}s")

            server._gateway_rpc_call = timeout_rpc
            state = server._archive_manager_create_if_missing()

            assert state["status"] == "error"
            assert state["label"] == "档案管理员创建失败"
            assert state["lastAction"] == "auto_create"
            assert "agents.list timed out after 10s" in state["lastError"]
            assert server._archive_manager_load_state()["lastError"] == state["lastError"]
        finally:
            restore_phase4_store(old)


def test_archive_manager_partial_profile_failure_repairs_existing_agent_without_recreate():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as oc_home:
        old = with_phase4_store(status_dir, oc_home)
        original_writer = server._archive_manager_write_profile_files
        try:
            calls, _ = install_fake_gateway(oc_home)
            server._archive_manager_write_profile_files = lambda _agent_id: {
                "ok": False,
                "error": "simulated profile write failure",
            }
            failed = server._archive_manager_create_if_missing()
            assert failed["status"] == "error"
            assert failed["agentId"] == "archive-manager"
            assert failed["lastError"] == "simulated profile write failure"

            workspace = os.path.join(oc_home, "workspace-archive-manager")
            server._archive_manager_write_profile_files = original_writer
            server._discovered_roster = [{
                "id": "archive-manager",
                "statusKey": "archive-manager",
                "name": "档案管理员",
                "providerKind": "openclaw",
                "workspace": workspace,
            }]
            server._discovered_at = time.time()
            repaired = server._archive_manager_create_if_missing()

            assert repaired["status"] == "idle"
            assert repaired["agentId"] == "archive-manager"
            assert repaired["lastError"] == ""
            assert os.path.isfile(os.path.join(workspace, "AGENTS.md"))
            assert len([call for call in calls if call[0] == "agents.create"]) == 1
        finally:
            server._archive_manager_write_profile_files = original_writer
            restore_phase4_store(old)


@pytest.mark.xfail(
    strict=True,
    reason="Known pre-extraction defect: a fresh negative roster cache can miss an externally created archive manager; shared reconciliation must refresh before create.",
)
def test_archive_manager_stale_negative_discovery_does_not_create_duplicate():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as oc_home:
        old = with_phase4_store(status_dir, oc_home)
        try:
            calls, _ = install_fake_gateway(oc_home)
            created = server._gateway_rpc_call("agents.create", {
                "name": "archive-manager",
                "workspace": os.path.join(oc_home, "workspace-archive-manager"),
            })
            assert created["ok"] is True
            server._discovered_roster = []
            server._discovered_at = time.time()

            state = server._archive_manager_create_if_missing()

            assert state["status"] == "idle"
            assert len([call for call in calls if call[0] == "agents.create"]) == 1
        finally:
            restore_phase4_store(old)


def test_archive_manager_repeated_startup_checks_reuse_agent(monkeypatch):
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as oc_home:
        old = with_phase4_store(status_dir, oc_home)
        try:
            calls, _ = install_fake_gateway(oc_home)
            monkeypatch.setattr(server.time, "sleep", lambda _seconds: None)

            server._archive_manager_profile_check_on_startup()
            server._archive_manager_profile_check_on_startup()

            assert server._archive_manager_public_state(ensure=False)["status"] == "idle"
            assert len([call for call in calls if call[0] == "agents.create"]) == 1
        finally:
            restore_phase4_store(old)


def test_archive_manager_persisted_pause_state_is_restart_visible():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as oc_home:
        old = with_phase4_store(status_dir, oc_home)
        try:
            install_fake_gateway(oc_home)
            server._archive_manager_create_if_missing()
            paused = server._handle_archive_manager_update({"action": "pause"})["archiveManager"]
            assert paused["paused"] is True

            server._discovered_roster = []
            server._discovered_at = time.time()
            reloaded = server._archive_manager_public_state(ensure=False)

            assert reloaded["agentId"] == "archive-manager"
            assert reloaded["status"] == "paused"
            assert reloaded["paused"] is True
            assert reloaded["lastAction"] == "pause"
        finally:
            restore_phase4_store(old)


if __name__ == "__main__":
    test_archive_manager_auto_create_idempotent_and_profile_files()
    test_archive_manager_profile_files_load_from_template()
    test_archive_manager_existing_agent_updates_stale_profile_version()
    test_archive_manager_existing_agent_repairs_profile_files()
    test_archive_manager_creation_failure_degrades_readonly()
    test_archive_manager_pause_resume_and_manual_maintain_current_project()
    test_archive_manager_cannot_be_deleted_or_assigned_to_project_tasks()
    test_archive_manager_chat_boundary()
    print("ok")
