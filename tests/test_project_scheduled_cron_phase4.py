#!/usr/bin/env python3
"""Phase 4 coverage for project scheduled cron history and alerts."""

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
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-project-cron-phase4-import-")
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
            self.jobs[cron_id] = job
            return {"ok": True, "job": job}
        if method == "cron.list":
            return {"ok": True, "jobs": list(self.jobs.values())}
        if method == "cron.run":
            return {"ok": True, "id": params.get("id"), "action": "started"}
        return {"ok": True}


_WORKSPACES = []


def temp_workspace():
    path = tempfile.mkdtemp(prefix="vo-project-cron-phase4-workspace-")
    _WORKSPACES.append(path)
    return path


def create_project_with_task():
    project = server._handle_project_create({
        "title": "Phase 4 Cron Project",
        "createdBy": "owner",
        "defaultExecutorAgentId": "executor",
        "projectExecutionEnabled": True,
        "workspacePath": temp_workspace(),
    })["project"]
    task = server._handle_task_create(project["id"], {
        "title": "Scheduled history task",
        "columnId": project["columns"][0]["id"],
        "assignee": "executor",
    })["task"]
    return project, task


def create_cron(project_id, task_id=None):
    body = {
        "name": "History cron",
        "schedule": {"kind": "every", "everyMs": 120000},
        "targetType": "projectTask" if task_id else "projectWorkflow",
        "enabled": True,
    }
    if task_id:
        body["taskId"] = task_id
    return server._handle_project_scheduled_cron_create(project_id, body)


def latest_history(project_id):
    _, project = server._project_find(project_id)
    history = project.get("scheduledCronHistory") or []
    assert history
    return history[-1], project


def test_started_dispatch_writes_history_without_alert():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        server._gateway_rpc_call = FakeCronGateway()
        server._handle_project_execution_project_start = lambda project_id, body=None: {"ok": True, "status": "started", "taskId": "next-task"}
        try:
            project, _ = create_project_with_task()
            created = create_cron(project["id"])
            dispatched = server._handle_project_scheduled_cron_dispatch(project["id"], created["id"], source="test")
            assert dispatched["status"] == "started"
            entry, _ = latest_history(project["id"])
            assert entry["status"] == "started"
            assert entry["source"] == "test"
            summary = server._handle_projects_list()["projects"][0]
            assert summary["scheduledCronAlertCount"] == 0
            assert summary["scheduledCronAlerts"] == []
        finally:
            restore_store(old)


def test_paused_and_repeat_block_write_non_alert_history():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        server._gateway_rpc_call = FakeCronGateway()
        try:
            project, task = create_project_with_task()
            created = create_cron(project["id"], task["id"])

            server._handle_project_update(project["id"], {"scheduledCronPaused": True})
            paused = server._handle_project_scheduled_cron_dispatch(project["id"], created["id"])
            assert paused["status"] == "paused"
            entry, _ = latest_history(project["id"])
            assert entry["status"] == "paused"
            assert entry["reason"] == "project_cron_paused"

            server._handle_project_update(project["id"], {"scheduledCronPaused": False})
            data, stored = server._project_find(project["id"])
            stored_task = next(t for t in stored["tasks"] if t["id"] == task["id"])
            stored_task["completedAt"] = server._proj_now()
            stored_task["executionState"] = "done"
            stored_task["scheduledRepeatEnabled"] = False
            server._save_projects(data)
            skipped = server._handle_project_scheduled_cron_dispatch(project["id"], created["id"])
            assert skipped["reason"] == "task_completed_repeat_disabled"
            entry, _ = latest_history(project["id"])
            assert entry["status"] == "skipped"
            assert entry["message"]
            summary = server._handle_projects_list()["projects"][0]
            assert summary["scheduledCronAlertCount"] == 0
        finally:
            restore_store(old)


def test_failed_dispatch_creates_control_panel_alert():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        server._gateway_rpc_call = FakeCronGateway()
        server._handle_project_execution_project_start = lambda project_id, body=None: {"ok": False, "error": "executor offline", "_status": 502}
        try:
            project, _ = create_project_with_task()
            created = create_cron(project["id"])
            dispatched = server._handle_project_scheduled_cron_dispatch(project["id"], created["id"])
            assert dispatched["error"] == "executor offline"
            entry, _ = latest_history(project["id"])
            assert entry["status"] == "failed"
            assert entry["error"] == "executor offline"
            summary = server._handle_projects_list()["projects"][0]
            assert summary["scheduledCronAlertCount"] == 1
            assert summary["scheduledCronAlerts"][0]["status"] == "failed"
        finally:
            restore_store(old)


def test_confirmation_required_history_is_intervention_alert():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        server._gateway_rpc_call = FakeCronGateway()
        server._handle_project_execution_project_start = lambda project_id, body=None: {
            "ok": False,
            "confirmationRequired": True,
            "code": "reviewer_skip_confirmation_required",
        }
        try:
            project, _ = create_project_with_task()
            created = create_cron(project["id"])
            dispatched = server._handle_project_scheduled_cron_dispatch(project["id"], created["id"])
            assert dispatched["status"] == "skipped"
            assert dispatched["reason"] == "reviewer_skip_confirmation_required"
            entry, _ = latest_history(project["id"])
            assert entry["status"] == "intervention_required"
            assert "审查" in entry["message"]
            summary = server._handle_projects_list()["projects"][0]
            assert summary["scheduledCronAlertCount"] == 1
            assert summary["scheduledCronAlerts"][0]["status"] == "intervention_required"
        finally:
            restore_store(old)


def test_history_is_persisted_and_capped_at_200():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            project, _ = create_project_with_task()
            data, stored = server._project_find(project["id"])
            stored["scheduledCronHistory"] = [
                {"id": str(i), "status": "skipped", "createdAt": f"2026-01-01T00:00:{i % 60:02d}+00:00"}
                for i in range(205)
            ]
            server._save_projects(data)
            reloaded = MarkdownProjectStore(status_dir).get_project(project["id"])
            assert len(reloaded.get("scheduledCronHistory", [])) == 205

            binding = {"projectId": project["id"], "targetType": "projectWorkflow", "name": "Cap cron"}
            server._project_cron_append_history(project["id"], "cron-cap", binding, "started")
            _, capped = server._project_find(project["id"])
            assert len(capped.get("scheduledCronHistory", [])) == 200
            assert capped["scheduledCronHistory"][-1]["cronId"] == "cron-cap"
        finally:
            restore_store(old)


if __name__ == "__main__":
    try:
        test_started_dispatch_writes_history_without_alert()
        test_paused_and_repeat_block_write_non_alert_history()
        test_failed_dispatch_creates_control_panel_alert()
        test_confirmation_required_history_is_intervention_alert()
        test_history_is_persisted_and_capped_at_200()
        print("ok")
    finally:
        for path in _WORKSPACES:
            shutil.rmtree(path, ignore_errors=True)
        shutil.rmtree(IMPORT_STATUS_DIR, ignore_errors=True)
