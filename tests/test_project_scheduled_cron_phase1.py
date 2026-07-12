#!/usr/bin/env python3
"""Phase 1 coverage for project-bound cron metadata."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-project-cron-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR

import server
from project_store import MarkdownProjectStore


def with_store(status_dir):
    old = (server.STATUS_DIR, server.PROJECT_STORE, server._gateway_rpc_call)
    server.STATUS_DIR = status_dir
    server.PROJECT_STORE = MarkdownProjectStore(status_dir)
    return old


def restore_store(old):
    server.STATUS_DIR, server.PROJECT_STORE, server._gateway_rpc_call = old


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
        if method == "cron.update":
            cron_id = params.get("id")
            if cron_id not in self.jobs:
                return {"ok": False, "error": "not found"}
            self.jobs[cron_id].update(params.get("patch") or {})
            return {"ok": True, "job": self.jobs[cron_id]}
        if method == "cron.remove":
            cron_id = params.get("id")
            if cron_id not in self.jobs:
                return {"ok": False, "error": "not found"}
            self.jobs.pop(cron_id)
            return {"ok": True}
        if method == "cron.run":
            cron_id = params.get("id")
            if cron_id not in self.jobs:
                return {"ok": False, "error": "not found"}
            return {"ok": True, "id": cron_id, "action": "started"}
        return {"ok": False, "error": f"unexpected method {method}"}


def create_project_with_task():
    project = server._handle_project_create({
        "title": "Scheduled Cron Project",
        "createdBy": "owner",
        "defaultExecutorAgentId": "executor",
    })["project"]
    task = server._handle_task_create(project["id"], {
        "title": "Recurring task",
        "columnId": project["columns"][0]["id"],
        "assignee": "executor",
    })["task"]
    return project, task


def test_project_bound_cron_create_list_update_delete_and_persist():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as status_dir:
        old = with_store(status_dir)
        fake_gateway = FakeCronGateway()
        server._gateway_rpc_call = fake_gateway
        try:
            project, task = create_project_with_task()
            created = server._handle_project_scheduled_cron_create(project["id"], {
                "name": "Daily project wake",
                "schedule": {"kind": "cron", "expr": "0 9 * * *"},
                "targetType": "projectTask",
                "taskId": task["id"],
                "enabled": True,
                "message": "Run recurring task",
            })
            assert created["ok"] is True
            cron_id = created["id"]
            assert fake_gateway.jobs[cron_id]["schedule"]["expr"] == "0 9 * * *"

            listed = server._handle_project_scheduled_cron_list(project["id"])
            assert listed["ok"] is True
            assert len(listed["jobs"]) == 1
            assert listed["jobs"][0]["projectId"] == project["id"]
            assert listed["jobs"][0]["targetType"] == "projectTask"
            assert listed["jobs"][0]["taskId"] == task["id"]

            # Binding table is independent from provider job storage and survives reload.
            reloaded = server._load_project_cron_bindings()
            assert reloaded["bindings"][cron_id]["projectId"] == project["id"]

            updated = server._handle_project_scheduled_cron_update(project["id"], cron_id, {
                "enabled": False,
                "schedule": {"kind": "every", "everyMs": 120000},
            })
            assert updated["ok"] is True
            assert fake_gateway.jobs[cron_id]["enabled"] is False
            assert server._load_project_cron_bindings()["bindings"][cron_id]["schedule"]["kind"] == "every"

            ran = server._handle_project_scheduled_cron_run(project["id"], cron_id)
            assert ran["ok"] is True

            deleted = server._handle_project_scheduled_cron_delete(project["id"], cron_id)
            assert deleted["ok"] is True
            assert cron_id not in server._load_project_cron_bindings()["bindings"]
            assert cron_id not in fake_gateway.jobs
        finally:
            restore_store(old)


def test_project_bound_cron_rejects_invalid_project_target_and_schedule():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as status_dir:
        old = with_store(status_dir)
        server._gateway_rpc_call = FakeCronGateway()
        try:
            project, task = create_project_with_task()
            missing_project = server._handle_project_scheduled_cron_create("missing", {
                "schedule": {"kind": "cron", "expr": "0 9 * * *"},
                "targetType": "projectWorkflow",
            })
            assert missing_project["_status"] == 404

            invalid_task = server._handle_project_scheduled_cron_create(project["id"], {
                "schedule": {"kind": "cron", "expr": "0 9 * * *"},
                "targetType": "projectTask",
                "taskId": "other-task",
            })
            assert invalid_task["_status"] == 400
            assert "Task not found" in invalid_task["error"]

            invalid_schedule = server._handle_project_scheduled_cron_create(project["id"], {
                "schedule": {"kind": "every", "everyMs": 1000},
                "targetType": "projectWorkflow",
            })
            assert invalid_schedule["_status"] == 400

            data = server._load_projects()
            stored = next(p for p in data["projects"] if p["id"] == project["id"])
            stored["createdBy"] = ""
            stored["defaultExecutorAgentId"] = ""
            stored["defaultReviewerAgentId"] = ""
            stored["tasks"] = []
            server._save_projects(data)
            ineligible = server._handle_project_scheduled_cron_create(project["id"], {
                "schedule": {"kind": "cron", "expr": "0 9 * * *"},
                "targetType": "projectWorkflow",
            })
            assert ineligible["_status"] == 400
            assert "requires" in ineligible["error"]

            assert server._load_project_cron_bindings()["bindings"] == {}
        finally:
            restore_store(old)


if __name__ == "__main__":
    test_project_bound_cron_create_list_update_delete_and_persist()
    test_project_bound_cron_rejects_invalid_project_target_and_schedule()
    print("ok")
