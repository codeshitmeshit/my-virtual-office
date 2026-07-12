#!/usr/bin/env python3
"""Phase 2-3 coverage for project cron overview and dispatch."""

import os
import shutil
import sys
import tempfile
import threading
import time

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
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as status_dir:
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


def test_run_now_preserves_gateway_success_when_local_dispatch_fails():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        fake_gateway = FakeCronGateway()
        server._gateway_rpc_call = fake_gateway
        server._handle_project_execution_project_start = lambda project_id, body=None: {
            "ok": False, "error": "local executor unavailable", "_status": 502,
        }
        try:
            project, _ = create_project_with_task(project_execution_enabled=True)
            created = server._handle_project_scheduled_cron_create(project["id"], {
                "name": "Gateway success local failure",
                "schedule": {"kind": "every", "everyMs": 120000},
                "targetType": "projectWorkflow",
            })
            result = server._handle_project_scheduled_cron_run(project["id"], created["id"])
            assert result["ok"] is True
            assert result["result"]["ok"] is True
            assert result["dispatch"]["ok"] is False
            assert result["dispatch"]["error"] == "local executor unavailable"
            binding = server._load_project_cron_bindings()["bindings"][created["id"]]
            assert binding["lastStatus"] == "failed"
            _, stored = server._project_find(project["id"])
            assert stored["scheduledCronHistory"][-1]["status"] == "failed"
        finally:
            restore_store(old)


def test_archived_project_dispatch_is_skipped_and_recorded():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        server._gateway_rpc_call = FakeCronGateway()
        try:
            project, _ = create_project_with_task(project_execution_enabled=True)
            created = server._handle_project_scheduled_cron_create(project["id"], {
                "name": "Archived dispatch",
                "schedule": {"kind": "every", "everyMs": 120000},
                "targetType": "projectWorkflow",
            })
            server._handle_project_update(project["id"], {"status": "archived"})
            result = server._handle_project_scheduled_cron_dispatch(project["id"], created["id"])
            assert result["status"] == "skipped"
            assert result["reason"] == "project_archived"
            _, stored = server._project_find(project["id"])
            assert stored["scheduledCronHistory"][-1]["reason"] == "project_archived"
        finally:
            restore_store(old)


def test_different_project_dispatches_preserve_each_history_concurrently():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        server._gateway_rpc_call = FakeCronGateway()
        barrier = threading.Barrier(2)

        def start(project_id, body=None):
            barrier.wait(timeout=3)
            return {"ok": True, "status": "started", "projectId": project_id}

        server._handle_project_execution_project_start = start
        try:
            pairs = []
            for index in range(2):
                project, _ = create_project_with_task(project_execution_enabled=True)
                created = server._handle_project_scheduled_cron_create(project["id"], {
                    "name": f"Concurrent {index}",
                    "schedule": {"kind": "every", "everyMs": 120000},
                    "targetType": "projectWorkflow",
                })
                pairs.append((project["id"], created["id"]))
            outcomes = []
            threads = [threading.Thread(target=lambda pair=pair: outcomes.append(
                server._handle_project_scheduled_cron_dispatch(pair[0], pair[1], source="concurrent")
            )) for pair in pairs]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(5)
            assert len(outcomes) == 2
            assert all(item["status"] == "started" for item in outcomes)
            for project_id, cron_id in pairs:
                _, stored = server._project_find(project_id)
                assert stored["scheduledCronHistory"][-1]["cronId"] == cron_id
                assert stored["scheduledCronHistory"][-1]["source"] == "concurrent"
        finally:
            restore_store(old)


def test_create_rejects_unbound_agent_and_external_delivery():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        gateway = FakeCronGateway()
        server._gateway_rpc_call = gateway
        try:
            project, _ = create_project_with_task(project_execution_enabled=True)
            base = {
                "schedule": {"kind": "every", "everyMs": 120000},
                "targetType": "projectWorkflow",
            }
            unbound = server._handle_project_scheduled_cron_create(
                project["id"], {**base, "agentId": "unbound-agent"},
            )
            assert unbound["_status"] == 400
            delivery = server._handle_project_scheduled_cron_create(
                project["id"], {**base, "delivery": {"mode": "announce"}},
            )
            assert delivery["_status"] == 400
            assert gateway.jobs == {}
            assert server._load_project_cron_bindings().get("bindings", {}) == {}
        finally:
            restore_store(old)


def test_same_cron_concurrent_dispatch_is_claimed_once():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        server._gateway_rpc_call = FakeCronGateway()
        entered = threading.Event()
        release = threading.Event()
        calls = []

        def start(project_id, body=None):
            calls.append(project_id)
            entered.set()
            assert release.wait(3)
            return {"ok": True, "status": "started", "projectId": project_id}

        server._handle_project_execution_project_start = start
        try:
            project, _ = create_project_with_task(project_execution_enabled=True)
            created = server._handle_project_scheduled_cron_create(project["id"], {
                "schedule": {"kind": "every", "everyMs": 120000},
                "targetType": "projectWorkflow",
            })
            outcomes = []
            first = threading.Thread(target=lambda: outcomes.append(
                server._handle_project_scheduled_cron_dispatch(project["id"], created["id"], "callback")
            ))
            first.start()
            assert entered.wait(2)
            second = threading.Thread(target=lambda: outcomes.append(
                server._handle_project_scheduled_cron_dispatch(project["id"], created["id"], "manual")
            ))
            second.start()
            second.join(2)
            release.set()
            first.join(3)
            assert calls == [project["id"]]
            assert sorted(item["status"] for item in outcomes) == ["skipped", "started"]
            skipped = next(item for item in outcomes if item["status"] == "skipped")
            assert skipped["reason"] == "dispatch_in_progress"
        finally:
            release.set()
            restore_store(old)


def test_dispatch_result_and_history_redact_secrets_and_drop_raw_fields():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        server._gateway_rpc_call = FakeCronGateway()
        server._handle_project_execution_project_start = lambda project_id, body=None: {
            "ok": False,
            "status": "failed",
            "error": "api_key=canary-secret at /private/workspace/file.py",
            "rawProviderPayload": "canary-raw-" + ("x" * 10000),
            "_status": 502,
        }
        try:
            project, _ = create_project_with_task(project_execution_enabled=True)
            created = server._handle_project_scheduled_cron_create(project["id"], {
                "schedule": {"kind": "every", "everyMs": 120000},
                "targetType": "projectWorkflow",
            })
            result = server._handle_project_scheduled_cron_dispatch(project["id"], created["id"])
            serialized = str(result)
            assert "canary-secret" not in serialized
            assert "rawProviderPayload" not in serialized
            binding = server._load_project_cron_bindings()["bindings"][created["id"]]
            assert "canary-secret" not in str(binding)
            assert "rawProviderPayload" not in str(binding)
            _, stored = server._project_find(project["id"])
            history = stored["scheduledCronHistory"][-1]
            assert "canary-secret" not in str(history)
            assert "rawProviderPayload" not in str(history)
            assert len(history["error"]) <= 360
        finally:
            restore_store(old)


def test_schedule_sanitizer_handles_bearer_and_json_secrets():
    safe = server._project_schedule_sanitize_result({
        "error": 'Authorization: Bearer sk-secret {"api_key":"json-secret"}',
    })
    assert "sk-secret" not in safe["error"]
    assert "json-secret" not in safe["error"]
    assert "[REDACTED]" in safe["error"]


def test_cron_list_drops_untrusted_gateway_job_fields():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        gateway = FakeCronGateway()
        server._gateway_rpc_call = gateway
        try:
            project, _ = create_project_with_task(project_execution_enabled=True)
            created = server._handle_project_scheduled_cron_create(project["id"], {
                "schedule": {"kind": "every", "everyMs": 120000},
                "targetType": "projectWorkflow",
            })
            gateway.jobs[created["id"]]["debug"] = {"Authorization": "Bearer gateway-secret"}
            gateway.jobs[created["id"]]["payload"] = {"raw": "provider-secret"}
            gateway.jobs[created["id"]]["state"] = {
                "lastStatus": "failed",
                "lastError": "Authorization: Bearer state-secret",
                "internalTrace": "trace-secret",
            }
            listed = server._handle_project_scheduled_cron_list(project["id"])["jobs"][0]
            serialized = str(listed)
            assert "debug" not in listed and "payload" not in listed
            assert "gateway-secret" not in serialized
            assert "provider-secret" not in serialized
            assert "state-secret" not in serialized
            assert "internalTrace" not in serialized
            assert listed["state"]["lastStatus"] == "failed"
        finally:
            restore_store(old)


def test_run_now_suppresses_delayed_gateway_callback_duplicate():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        server._gateway_rpc_call = FakeCronGateway()
        calls = []
        server._handle_project_execution_project_start = lambda project_id, body=None: calls.append(project_id) or {
            "ok": True, "status": "started", "projectId": project_id,
        }
        try:
            project, _ = create_project_with_task(project_execution_enabled=True)
            created = server._handle_project_scheduled_cron_create(project["id"], {
                "schedule": {"kind": "every", "everyMs": 120000},
                "targetType": "projectWorkflow",
            })
            ran = server._handle_project_scheduled_cron_run(project["id"], created["id"])
            occurrence_id = server._load_project_cron_bindings()["bindings"][created["id"]]["lastDispatchClaim"]["occurrenceId"]
            callback = server._handle_project_scheduled_cron_dispatch(
                project["id"], created["id"], "cron", occurrence_id,
            )
            assert ran["dispatch"]["status"] == "started"
            assert callback["status"] == "skipped"
            assert callback["reason"] == "duplicate_occurrence"
            assert calls == [project["id"]]
            binding = server._load_project_cron_bindings()["bindings"][created["id"]]
            assert binding["completedRunNowSequence"] == 1

            # A later legitimate schedule occurrence has a distinct/no id and
            # must not be swallowed when the run-now callback never arrives.
            later = server._handle_project_scheduled_cron_dispatch(project["id"], created["id"], "cron")
            assert later["status"] == "started"
            assert calls == [project["id"], project["id"]]
        finally:
            restore_store(old)


def test_old_run_now_occurrence_remains_duplicate_after_many_newer_runs():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        server._gateway_rpc_call = FakeCronGateway()
        calls = []
        server._handle_project_execution_project_start = lambda project_id, body=None: calls.append(project_id) or {
            "ok": True, "status": "started", "projectId": project_id,
        }
        try:
            project, _ = create_project_with_task(project_execution_enabled=True)
            created = server._handle_project_scheduled_cron_create(project["id"], {
                "schedule": {"kind": "every", "everyMs": 120000},
                "targetType": "projectWorkflow",
            })
            first = server._project_schedule_next_occurrence_id(created["id"])
            for sequence in range(1, 61):
                occurrence_id = f"{created['id']}:run-now:{sequence}"
                claim = server._project_schedule_claim_dispatch(created["id"], "run-now", occurrence_id)
                if claim.get("claimed"):
                    assert server._project_schedule_release_dispatch(created["id"], claim["token"])
            replay = server._handle_project_scheduled_cron_dispatch(project["id"], created["id"], "cron", first)
            assert replay["status"] == "skipped"
            assert replay["reason"] == "duplicate_occurrence"
            assert calls == []
            binding = server._load_project_cron_bindings()["bindings"][created["id"]]
            assert binding["completedRunNowSequence"] == 60
        finally:
            restore_store(old)


def test_binding_capacity_reservation_persists_atomically_in_server_adapter():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            barrier = threading.Barrier(2)
            tokens = []

            def reserve():
                barrier.wait(timeout=2)
                tokens.append(server._project_schedule_reserve_binding_slot(1))

            threads = [threading.Thread(target=reserve) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(2)
            assert sum(token is not None for token in tokens) == 1
            persisted = server._load_project_cron_bindings()
            assert list(persisted["reservations"]) == [next(token for token in tokens if token)]
            assert server._project_schedule_release_binding_slot(next(token for token in tokens if token)) is True
            assert server._load_project_cron_bindings()["reservations"] == {}
        finally:
            restore_store(old)


def test_dispatch_lease_is_renewed_while_start_is_blocked():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        server._gateway_rpc_call = FakeCronGateway()
        entered = threading.Event()
        release = threading.Event()
        calls = []

        def start(project_id, body=None):
            calls.append(project_id)
            entered.set()
            assert release.wait(3)
            return {"ok": True, "status": "started", "projectId": project_id}

        server._handle_project_execution_project_start = start
        try:
            project, _ = create_project_with_task(project_execution_enabled=True)
            created = server._handle_project_scheduled_cron_create(project["id"], {
                "schedule": {"kind": "every", "everyMs": 120000},
                "targetType": "projectWorkflow",
            })
            ports = server._project_schedule_dispatch_ports()
            ports = server.project_schedule_service.DispatchPorts(**{
                **ports.__dict__, "lease_refresh_seconds": 0.01,
            })
            outcomes = []
            first = threading.Thread(target=lambda: outcomes.append(server.project_schedule_service.dispatch(
                project["id"], created["id"], "cron", ports=ports,
            )))
            first.start()
            assert entered.wait(2)
            with server._PROJECT_CRON_BINDINGS_LOCK:
                data = server._load_project_cron_bindings()
                data["bindings"][created["id"]]["dispatchClaim"]["expiresAtEpoch"] = time.time() + 0.005
                server._save_project_cron_bindings(data)
            time.sleep(0.04)
            claim = server._load_project_cron_bindings()["bindings"][created["id"]]["dispatchClaim"]
            assert claim.get("renewedAt")
            assert claim["expiresAtEpoch"] > time.time() + 80
            second = server.project_schedule_service.dispatch(project["id"], created["id"], "cron", ports=ports)
            assert second["reason"] == "dispatch_in_progress"
            release.set()
            first.join(3)
            assert calls == [project["id"]]
        finally:
            release.set()
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
