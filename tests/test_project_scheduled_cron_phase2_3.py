#!/usr/bin/env python3
"""Phase 2-3 coverage for project cron overview and dispatch."""

import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-project-cron-phase23-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR

import server
from project_store import MarkdownProjectStore


def with_store(status_dir):
    old = (
        server.STATUS_DIR,
        server.PROJECT_STORE,
        server._gateway_rpc_call,
        server._handle_project_execution_project_start,
        server._handle_project_execution_start,
        server._handle_workflow_start,
    )
    server.STATUS_DIR = status_dir
    server.PROJECT_STORE = MarkdownProjectStore(status_dir)
    return old


def restore_store(old):
    (
        server.STATUS_DIR,
        server.PROJECT_STORE,
        server._gateway_rpc_call,
        server._handle_project_execution_project_start,
        server._handle_project_execution_start,
        server._handle_workflow_start,
    ) = old


class FakeCronGateway:
    def __init__(self):
        self.jobs = {}
        self.next_id = 1

    def __call__(self, method, params=None, timeout=20):
        params = params or {}
        if method == "cron.add":
            cron_id = f"cron-{self.next_id}"
            self.next_id += 1
            job = dict(params)
            job["id"] = cron_id
            job.setdefault("state", {})
            self.jobs[cron_id] = job
            return {"ok": True, "job": job}
        if method == "cron.list":
            return {"ok": True, "jobs": list(self.jobs.values())}
        if method == "cron.update":
            cron_id = params.get("id")
            if cron_id not in self.jobs:
                return {"ok": False, "error": "not found"}
            self.jobs[cron_id].update(params.get("patch") or {})
            return {"ok": True, "job": self.jobs[cron_id]}
        if method == "cron.remove":
            cron_id = params.get("id")
            self.jobs.pop(cron_id, None)
            return {"ok": True}
        if method == "cron.run":
            cron_id = params.get("id")
            if cron_id not in self.jobs:
                return {"ok": False, "error": "not found"}
            return {"ok": True, "id": cron_id, "action": "started"}
        return {"ok": False, "error": f"unexpected method {method}"}


_WORKSPACES = []


def temp_workspace():
    path = tempfile.mkdtemp(prefix="vo-project-cron-workspace-")
    _WORKSPACES.append(path)
    return path


def create_project_with_task(project_execution_enabled=True):
    project = server._handle_project_create({
        "title": "Phase 2 3 Cron Project",
        "createdBy": "owner",
        "defaultExecutorAgentId": "executor",
        "projectExecutionEnabled": project_execution_enabled,
        "workspacePath": temp_workspace() if project_execution_enabled else "",
    })["project"]
    task = server._handle_task_create(project["id"], {
        "title": "Recurring dispatch task",
        "columnId": project["columns"][0]["id"],
        "assignee": "executor",
    })["task"]
    return project, task


def test_global_project_cron_overview_enriches_project_context():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        fake_gateway = FakeCronGateway()
        server._gateway_rpc_call = fake_gateway
        try:
            project, task = create_project_with_task(project_execution_enabled=False)
            created = server._handle_project_scheduled_cron_create(project["id"], {
                "name": "Global visible project cron",
                "schedule": {"kind": "every", "everyMs": 120000},
                "targetType": "projectTask",
                "taskId": task["id"],
                "enabled": True,
            })
            assert created["ok"] is True

            overview = server._handle_project_scheduled_cron_all()
            assert overview["ok"] is True
            assert len(overview["jobs"]) == 1
            job = overview["jobs"][0]
            assert job["kind"] == "project"
            assert job["projectId"] == project["id"]
            assert job["projectName"] == project["title"]
            assert job["targetType"] == "projectTask"
            assert job["taskTitle"] == task["title"]
        finally:
            restore_store(old)


def test_run_now_dispatches_whole_project_and_updates_status():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        fake_gateway = FakeCronGateway()
        calls = []
        server._gateway_rpc_call = fake_gateway
        server._handle_project_execution_project_start = lambda project_id, body=None: calls.append((project_id, body or {})) or {"ok": True, "status": "started", "taskId": "next-task"}
        try:
            project, _ = create_project_with_task(project_execution_enabled=True)
            created = server._handle_project_scheduled_cron_create(project["id"], {
                "name": "Dispatch whole project",
                "schedule": {"kind": "every", "everyMs": 120000},
                "targetType": "projectWorkflow",
                "enabled": True,
            })
            ran = server._handle_project_scheduled_cron_run(project["id"], created["id"])
            assert ran["ok"] is True
            assert ran["dispatch"]["status"] == "started"
            assert calls and calls[0][0] == project["id"]
            binding = server._load_project_cron_bindings()["bindings"][created["id"]]
            assert binding["lastStatus"] == "started"
            assert binding["lastError"] is None
        finally:
            restore_store(old)


def test_dispatch_skips_when_project_cron_paused_or_active():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        fake_gateway = FakeCronGateway()
        server._gateway_rpc_call = fake_gateway
        try:
            project, _ = create_project_with_task(project_execution_enabled=True)
            created = server._handle_project_scheduled_cron_create(project["id"], {
                "name": "Paused dispatch",
                "schedule": {"kind": "every", "everyMs": 120000},
                "targetType": "projectWorkflow",
                "enabled": True,
            })
            server._handle_project_update(project["id"], {"scheduledCronPaused": True})
            paused = server._handle_project_scheduled_cron_dispatch(project["id"], created["id"])
            assert paused["status"] == "paused"
            assert server._load_project_cron_bindings()["bindings"][created["id"]]["lastStatus"] == "paused"

            server._handle_project_update(project["id"], {"scheduledCronPaused": False})
            data, stored = server._project_find(project["id"])
            stored["tasks"][0]["executionState"] = "executing"
            server._save_projects(data)
            skipped = server._handle_project_scheduled_cron_dispatch(project["id"], created["id"])
            assert skipped["status"] == "skipped"
            assert skipped["reason"] == "project_active"
        finally:
            restore_store(old)


def test_dispatch_project_task_uses_selected_task():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        fake_gateway = FakeCronGateway()
        calls = []
        server._gateway_rpc_call = fake_gateway
        server._handle_project_execution_start = lambda project_id, task_id, body=None: calls.append((project_id, task_id, body or {})) or {"ok": True, "status": "started", "taskId": task_id}
        try:
            project, task = create_project_with_task(project_execution_enabled=True)
            created = server._handle_project_scheduled_cron_create(project["id"], {
                "name": "Dispatch selected task",
                "schedule": {"kind": "every", "everyMs": 120000},
                "targetType": "projectTask",
                "taskId": task["id"],
                "enabled": True,
            })
            dispatched = server._handle_project_scheduled_cron_dispatch(project["id"], created["id"])
            assert dispatched["status"] == "started"
            assert calls == [(project["id"], task["id"], {"by": "project-cron", "source": "manual", "skipReviewConfirmed": True})]
        finally:
            restore_store(old)


def test_project_task_cron_reopens_completed_task_for_repeat_execution():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        fake_gateway = FakeCronGateway()
        calls = []
        server._gateway_rpc_call = fake_gateway
        server._handle_project_execution_start = lambda project_id, task_id, body=None: calls.append((project_id, task_id, body or {})) or {"ok": True, "status": "started", "taskId": task_id}
        try:
            project, task = create_project_with_task(project_execution_enabled=True)
            done_col = next(c for c in project["columns"] if c["title"].lower() == "done")
            data, stored = server._project_find(project["id"])
            stored_task = next(t for t in stored["tasks"] if t["id"] == task["id"])
            stored_task["columnId"] = done_col["id"]
            stored_task["completedAt"] = server._proj_now()
            stored_task["executionState"] = "done"
            stored_task["scheduledRepeatEnabled"] = True
            server._save_projects(data)

            created = server._handle_project_scheduled_cron_create(project["id"], {
                "name": "Repeat completed task",
                "schedule": {"kind": "every", "everyMs": 120000},
                "targetType": "projectTask",
                "taskId": task["id"],
                "enabled": True,
            })
            dispatched = server._handle_project_scheduled_cron_dispatch(project["id"], created["id"])
            assert dispatched["status"] == "started"
            assert dispatched["result"]["reopenedCompletedTask"] is True
            assert calls and calls[0][1] == task["id"]

            _, after_project = server._project_find(project["id"])
            after_task = next(t for t in after_project["tasks"] if t["id"] == task["id"])
            backlog_col = next(c for c in after_project["columns"] if c["title"].lower() == "backlog")
            assert after_task["columnId"] == backlog_col["id"]
            assert after_task["completedAt"] is None
            assert after_task["executionState"] == "backlog"
            assert any("Reopened completed task" in c.get("text", "") for c in after_task.get("comments", []))
        finally:
            restore_store(old)


def test_completed_task_cron_skips_when_repeat_not_enabled():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        fake_gateway = FakeCronGateway()
        calls = []
        server._gateway_rpc_call = fake_gateway
        server._handle_project_execution_start = lambda project_id, task_id, body=None: calls.append((project_id, task_id, body or {})) or {"ok": True, "status": "started", "taskId": task_id}
        try:
            project, task = create_project_with_task(project_execution_enabled=True)
            done_col = next(c for c in project["columns"] if c["title"].lower() == "done")
            data, stored = server._project_find(project["id"])
            stored_task = next(t for t in stored["tasks"] if t["id"] == task["id"])
            stored_task["columnId"] = done_col["id"]
            stored_task["completedAt"] = server._proj_now()
            stored_task["executionState"] = "done"
            stored_task["scheduledRepeatEnabled"] = False
            server._save_projects(data)

            created = server._handle_project_scheduled_cron_create(project["id"], {
                "name": "Skip completed task",
                "schedule": {"kind": "every", "everyMs": 120000},
                "targetType": "projectTask",
                "taskId": task["id"],
                "enabled": True,
            })
            dispatched = server._handle_project_scheduled_cron_dispatch(project["id"], created["id"])
            assert dispatched["status"] == "skipped"
            assert dispatched["reason"] == "task_completed_cron_disengaged"
            assert calls == []
            assert server._load_project_cron_bindings()["bindings"][created["id"]]["lastStatus"] == "disengaged_completed"
        finally:
            restore_store(old)


if __name__ == "__main__":
    try:
        test_global_project_cron_overview_enriches_project_context()
        test_run_now_dispatches_whole_project_and_updates_status()
        test_dispatch_skips_when_project_cron_paused_or_active()
        test_dispatch_project_task_uses_selected_task()
        test_project_task_cron_reopens_completed_task_for_repeat_execution()
        test_completed_task_cron_skips_when_repeat_not_enabled()
        print("ok")
    finally:
        for path in _WORKSPACES:
            shutil.rmtree(path, ignore_errors=True)
