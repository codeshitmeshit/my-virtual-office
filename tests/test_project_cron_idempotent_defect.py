#!/usr/bin/env python3
"""Phase 7 — Regression tests for P0 cron repeat-trigger defect fix.

Verifies:
1) A completed task with scheduledRepeatEnabled=False (or unset)
   no longer triggers dispatch; the cron binding is auto-disengaged.
2) A completed projectWorkflow with all tasks done no longer triggers
   dispatch; the cron binding is auto-disengaged.
"""

import os
import sys
import tempfile
import time
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-cron-defect-"))

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
    """Simulates the Hermes cron gateway for testing."""
    def __init__(self):
        self.jobs = {}
        self.next_id = 1
        self.alerts = []

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
        if method == "cron.alert":
            self.alerts.append(params)
            return {"ok": True}
        return {"ok": False, "error": f"unexpected method {method}"}


def create_project_with_done_column():
    """Create a project with a Done column at index 3."""
    project = server._handle_project_create({
        "title": "Cron Idempotency Test",
        "createdBy": "owner",
        "defaultExecutorAgentId": "executor",
    })["project"]
    # Ensure fourth column exists
    while len(project.get("columns", [])) < 4:
        project.setdefault("columns", []).append({"id": f"col-{len(project['columns'])}", "title": "Done", "color": "#198754", "order": len(project["columns"])})
    return project


def test_completed_project_task_does_not_repeat_dispatch():
    """Regression 1: A completed daily-report task must NOT be re-dispatched.

    Steps:
    1. Create project + task
    2. Mark task as completed (set completedAt)
    3. Create cron dispatch
    4. Verify dispatch returns skipped_completed_task status
    5. Verify binding status changes to 'disengaged_completed'
    6. Verify cron.update was called with enabled=False
    7. Verify second dispatch is idempotent-skipped at pre-check
    """
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        fake_gateway = FakeCronGateway()
        server._gateway_rpc_call = fake_gateway
        try:
            project = create_project_with_done_column()
            col0 = project["columns"][0]["id"]
            task = server._handle_task_create(project["id"], {
                "title": "Daily report",
                "columnId": col0,
                "assignee": "executor",
            })["task"]

            # Mark task completed
            done_col_id = project["columns"][3]["id"]
            task["completedAt"] = "2026-06-25T12:00:00Z"
            task["columnId"] = done_col_id
            # Persist
            data, _ = server._project_find(project["id"])
            for t in data["projects"][0]["tasks"]:
                if t["id"] == task["id"]:
                    t["completedAt"] = task["completedAt"]
                    t["columnId"] = done_col_id
            server._save_projects(data)

            # Create cron
            created = server._handle_project_scheduled_cron_create(project["id"], {
                "name": "Daily report cron",
                "schedule": {"kind": "cron", "expr": "0 9 * * *"},
                "targetType": "projectTask",
                "taskId": task["id"],
                "enabled": True,
                "message": "Run daily report",
            })
            assert created["ok"] is True
            cron_id = created["id"]

            # First dispatch — should skip and disengage
            result1 = server._handle_project_scheduled_cron_dispatch(project["id"], cron_id, source="cron")
            assert result1["ok"] is True, f"First dispatch failed: {result1}"
            assert result1["status"] == "skipped", f"Expected skipped, got {result1['status']}"
            assert result1["reason"] == "task_completed_cron_disengaged", \
                f"Expected task_completed_cron_disengaged, got {result1['reason']}"
            assert result1.get("cronDisabled") is True or result1.get("cronDisabled") is None, \
                f"Expected cronDisabled hint, got {result1}"

            # Verify gateway cron was disabled
            job = fake_gateway.jobs.get(cron_id, {})
            assert job.get("enabled") is False, f"Cron was not disabled by fix: {job}"

            # Verify binding lastStatus
            binding = server._load_project_cron_bindings()["bindings"].get(str(cron_id), {})
            assert binding.get("lastStatus") == "disengaged_completed", \
                f"Expected disengaged_completed, got {binding.get('lastStatus')}"

            # Second dispatch — pre-check idempotency should short-circuit
            result2 = server._handle_project_scheduled_cron_dispatch(project["id"], cron_id, source="cron")
            assert result2["ok"] is True, f"Second dispatch failed: {result2}"
            assert result2.get("idempotent") is True, \
                f"Expected idempotent skip, got {result2}"

        finally:
            restore_store(old)


def test_completed_workflow_does_not_repeat_dispatch():
    """Regression 2: A workflow with ALL tasks completed must NOT be re-dispatched.

    Steps:
    1. Create project with 2 tasks, both completed
    2. Create cron dispatch
    3. Verify dispatch skips and auto-disengages
    4. Verify second dispatch is idempotent-skipped
    """
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        fake_gateway = FakeCronGateway()
        server._gateway_rpc_call = fake_gateway
        try:
            project = create_project_with_done_column()
            col0 = project["columns"][0]["id"]
            done_col = project["columns"][3]["id"]

            # Create 2 tasks, both in Done column with completedAt
            task1 = server._handle_task_create(project["id"], {
                "title": "Task 1",
                "columnId": col0,
                "assignee": "executor",
            })["task"]
            task2 = server._handle_task_create(project["id"], {
                "title": "Task 2",
                "columnId": col0,
                "assignee": "executor",
            })["task"]

            # Mark both completed
            data, _ = server._project_find(project["id"])
            for t in data["projects"][0]["tasks"]:
                if t["id"] in (task1["id"], task2["id"]):
                    t["completedAt"] = "2026-06-25T12:00:00Z"
                    t["columnId"] = done_col
            server._save_projects(data)

            # Create cron (projectWorkflow target by omission of taskId)
            created = server._handle_project_scheduled_cron_create(project["id"], {
                "name": "Daily workflow cron",
                "schedule": {"kind": "cron", "expr": "0 9 * * *"},
                "targetType": "projectWorkflow",
                "enabled": True,
                "message": "Run daily workflow",
            })
            assert created["ok"] is True
            cron_id = created["id"]

            # Also set project.scheduledCronHistory to simulate prior ticks
            data, _ = server._project_find(project["id"])
            data["projects"][0]["scheduledCronHistory"] = [
                {"reason": "project_all_tasks_completed", "at": "2026-06-25T10:00:00Z"},
                {"reason": "project_all_tasks_completed", "at": "2026-06-25T11:00:00Z"},
            ]
            server._save_projects(data)

            # First dispatch — should skip + disengage + alert
            result1 = server._handle_project_scheduled_cron_dispatch(project["id"], cron_id, source="cron")
            assert result1["ok"] is True, f"First dispatch failed: {result1}"
            assert result1["status"] == "skipped"
            assert result1["reason"] in ("project_all_tasks_completed",), \
                f"Expected project_all_tasks_completed, got {result1}"

            # Verify cron was disabled
            job = fake_gateway.jobs.get(cron_id, {})
            assert job.get("enabled") is False, f"Cron not disabled: {job}"

            # Verify binding status
            binding = server._load_project_cron_bindings()["bindings"].get(str(cron_id), {})
            assert binding.get("lastStatus") == "disengaged_completed", \
                f"Expected disengaged_completed, got {binding.get('lastStatus')}"

            # Verify an alert was fired (>=2 prior skips in history)
            assert len(fake_gateway.alerts) >= 1, "Expected at least 1 alert"

            # Second dispatch — pre-check idempotency
            result2 = server._handle_project_scheduled_cron_dispatch(project["id"], cron_id, source="cron")
            assert result2["ok"] is True
            assert result2.get("idempotent") is True, \
                f"Expected idempotent skip, got {result2}"

        finally:
            restore_store(old)


if __name__ == "__main__":
    test_completed_project_task_does_not_repeat_dispatch()
    print("[PASS] test_completed_project_task_does_not_repeat_dispatch")
    test_completed_workflow_does_not_repeat_dispatch()
    print("[PASS] test_completed_workflow_does_not_repeat_dispatch")
    print("\n=== All regression tests PASSED ===")
