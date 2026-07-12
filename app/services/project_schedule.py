"""Project scheduled-Cron orchestration independent of HTTP and ``server.py``."""

from __future__ import annotations

import copy
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Mapping


Project = dict[str, Any]
Binding = dict[str, Any]


class KeyedOperationLocks:
    """Ref-counted per-Cron RLocks; never reuse the binding file I/O lock."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._entries: dict[str, list[Any]] = {}

    @contextmanager
    def hold(self, key: str):
        key = str(key)
        with self._guard:
            entry = self._entries.get(key)
            if entry is None:
                entry = [threading.RLock(), 0]
                self._entries[key] = entry
            entry[1] += 1
        entry[0].acquire()
        try:
            yield
        finally:
            entry[0].release()
            with self._guard:
                entry[1] -= 1
                if entry[1] == 0 and self._entries.get(key) is entry:
                    del self._entries[key]


@dataclass(frozen=True)
class SchedulePorts:
    gateway: Callable[[str, dict[str, Any], int], dict[str, Any]]
    validate_project: Callable[[str], tuple[Project | None, dict[str, Any] | None]]
    get_project: Callable[[str], Project | None]
    list_projects: Callable[[], list[Project]]
    bindings: Callable[[], dict[str, Binding]]
    put_binding: Callable[[str, Binding], Any]
    merge_binding: Callable[[str, Binding], Any]
    delete_binding: Callable[[str], Any]
    reserve_binding_slot: Callable[[int], str | None]
    release_binding_slot: Callable[[str], Any]
    operation_lock: Callable[[str], Any]
    validate_job_policy: Callable[[Project, Mapping[str, Any], Binding | None], str | None]
    sanitize_result: Callable[[Mapping[str, Any] | None], dict[str, Any]]
    update_binding_status: Callable[..., Any]
    validate_schedule: Callable[[Any], str | None]
    validate_target: Callable[[Project, str, str | None], str | None]
    build_job: Callable[[Project, dict[str, Any], Binding | None], tuple[dict[str, Any], Binding]]
    extract_jobs: Callable[[dict[str, Any]], list[dict[str, Any]]]
    extract_job_id: Callable[[dict[str, Any]], str]
    enrich_item: Callable[[str, Binding, dict[str, Any], Project | None], dict[str, Any]]
    now: Callable[[], str]
    next_occurrence_id: Callable[[str], str]
    binding_limit: int = 1000


@dataclass(frozen=True)
class DispatchPorts:
    get_binding: Callable[[str], Binding | None]
    get_project: Callable[[str], Project | None]
    update_binding_status: Callable[..., Any]
    append_history: Callable[..., Any]
    execution_enabled: Callable[[Project], bool]
    active_task: Callable[[Project], dict[str, Any] | None]
    done_column_ids: Callable[[Project], set[str]]
    reopen_task: Callable[[str, str], dict[str, Any]]
    start_task: Callable[[str, str, dict[str, Any]], dict[str, Any]]
    start_project: Callable[[str, dict[str, Any]], dict[str, Any]]
    start_legacy: Callable[[str, dict[str, Any]], dict[str, Any]]
    gateway: Callable[[str, dict[str, Any], int], dict[str, Any]]
    operation_lock: Callable[[str], Any]
    claim_dispatch: Callable[[str, str, str | None], dict[str, Any]]
    renew_dispatch: Callable[[str, str], bool]
    owns_dispatch: Callable[[str, str], bool]
    release_dispatch: Callable[[str, str], Any]
    sanitize_result: Callable[[Mapping[str, Any] | None], dict[str, Any]]
    monotonic: Callable[[], float] = time.monotonic
    lease_refresh_seconds: float = 20.0


def _gateway(ports: SchedulePorts | DispatchPorts, method: str, params: dict[str, Any], timeout: int) -> dict[str, Any]:
    try:
        result = ports.gateway(method, params, timeout)
    except Exception:
        return {"ok": False, "error": "Gateway request failed"}
    return result if isinstance(result, dict) else {"ok": False, "error": "Invalid Gateway response"}


def _gateway_error(default: str) -> dict[str, Any]:
    return {"error": default, "_status": 502}


def list_jobs(project_id: str, *, ports: SchedulePorts) -> dict[str, Any]:
    project, error = ports.validate_project(project_id)
    if error:
        return error
    cron_result = _gateway(ports, "cron.list", {"includeDisabled": True}, 20)
    if not cron_result.get("ok"):
        return _gateway_error("Failed to list cron jobs")
    jobs = {str(item.get("id")): _sanitize_gateway_job(item, ports) for item in ports.extract_jobs(cron_result) if isinstance(item, dict) and item.get("id")}
    items = [
        ports.enrich_item(cron_id, binding, jobs.get(str(cron_id), {}), project)
        for cron_id, binding in ports.bindings().items()
        if binding.get("projectId") == project_id
    ]
    return {"ok": True, "projectId": project_id, "jobs": items, "cronOwner": "gateway", "bindingOwner": "virtual-office"}


def list_all(*, ports: SchedulePorts) -> dict[str, Any]:
    cron_result = _gateway(ports, "cron.list", {"includeDisabled": True}, 20)
    if not cron_result.get("ok"):
        return _gateway_error("Failed to list cron jobs")
    jobs = {str(item.get("id")): _sanitize_gateway_job(item, ports) for item in ports.extract_jobs(cron_result) if isinstance(item, dict) and item.get("id")}
    projects = ports.list_projects()
    projects_by_id = {project.get("id"): project for project in projects}
    items = [
        ports.enrich_item(cron_id, binding, jobs.get(str(cron_id), {}), projects_by_id.get(binding.get("projectId"), {}))
        for cron_id, binding in ports.bindings().items()
    ]
    return {
        "ok": True, "jobs": items,
        "projects": [{
            "id": project.get("id"), "title": project.get("title", ""),
            "status": project.get("status", "active"),
            "scheduledCronPaused": bool(project.get("scheduledCronPaused")),
        } for project in projects],
        "cronOwner": "gateway", "bindingOwner": "virtual-office",
    }


def _sanitize_gateway_job(item: Mapping[str, Any], ports: SchedulePorts) -> dict[str, Any]:
    allowed = {"id", "name", "schedule", "sessionTarget", "enabled", "agentId", "delivery"}
    safe = {key: copy.deepcopy(value) for key, value in item.items() if key in allowed}
    state = item.get("state") if isinstance(item.get("state"), Mapping) else {}
    state_allowed = {"lastRunAt", "lastStatus", "nextRunAt", "lastRunAtMs", "nextRunAtMs", "lastDurationMs"}
    safe_state = {key: copy.deepcopy(value) for key, value in state.items() if key in state_allowed}
    if state.get("lastError"):
        safe_state["lastError"] = ports.sanitize_result({"error": state.get("lastError")}).get("error", "")
    if safe_state:
        safe["state"] = safe_state
    return safe


def create(project_id: str, body: Mapping[str, Any] | None, *, ports: SchedulePorts) -> dict[str, Any]:
    body = dict(body or {})
    project, error = ports.validate_project(project_id)
    if error:
        return error
    policy_error = ports.validate_job_policy(project, body, None)
    if policy_error:
        return {"error": policy_error, "_status": 400}
    reservation = ports.reserve_binding_slot(ports.binding_limit)
    if not reservation:
        return {"error": "Project scheduled cron binding limit reached", "code": "cron_binding_limit", "_status": 409}
    target_type = body.get("targetType") or "projectWorkflow"
    task_id = body.get("taskId")
    target_error = ports.validate_target(project, target_type, task_id)
    if target_error:
        ports.release_binding_slot(reservation)
        return {"error": target_error, "_status": 400}
    schedule_error = ports.validate_schedule(body.get("schedule"))
    if schedule_error:
        ports.release_binding_slot(reservation)
        return {"error": schedule_error, "_status": 400}
    job, binding = ports.build_job(project, body, None)
    cron_result = _gateway(ports, "cron.add", job, 30)
    if not cron_result.get("ok"):
        ports.release_binding_slot(reservation)
        return _gateway_error("Failed to create cron job")
    cron_id = ports.extract_job_id(cron_result)
    if not cron_id:
        ports.release_binding_slot(reservation)
        return {"error": "Cron job was created but no id was returned", "_status": 502}
    try:
        with ports.operation_lock(cron_id):
            binding.update({"cronJobId": cron_id, "createdAt": ports.now()})
            ports.merge_binding(cron_id, binding)
    except Exception:
        _gateway(ports, "cron.remove", {"id": cron_id}, 10)
        return {"error": "Failed to persist cron binding", "code": "cron_binding_persist_failed", "_status": 500}
    finally:
        ports.release_binding_slot(reservation)
    return {"ok": True, "projectId": project_id, "id": cron_id, "job": {**job, "id": cron_id}, "binding": binding}


def update(project_id: str, cron_id: str, body: Mapping[str, Any] | None, *, ports: SchedulePorts) -> dict[str, Any]:
    body = dict(body or {})
    project, error = ports.validate_project(project_id)
    if error:
        return error
    with ports.operation_lock(cron_id):
        existing = ports.bindings().get(str(cron_id))
        if not existing or existing.get("projectId") != project_id:
            return {"error": "Project scheduled cron not found", "_status": 404}
        policy_error = ports.validate_job_policy(project, body, existing)
        if policy_error:
            return {"error": policy_error, "_status": 400}
        target_type = body.get("targetType") if "targetType" in body else existing.get("targetType")
        task_id = body.get("taskId") if "taskId" in body else existing.get("taskId")
        target_error = ports.validate_target(project, target_type, task_id)
        if target_error:
            return {"error": target_error, "_status": 400}
        schedule = body.get("schedule") if "schedule" in body else existing.get("schedule")
        schedule_error = ports.validate_schedule(schedule)
        if schedule_error:
            return {"error": schedule_error, "_status": 400}
        job, binding = ports.build_job(project, {**body, "targetType": target_type, "taskId": task_id, "schedule": schedule}, existing)
        cron_result = _gateway(ports, "cron.update", {"id": cron_id, "patch": dict(job)}, 30)
        if not cron_result.get("ok"):
            return _gateway_error("Failed to update cron job")
        binding.update({"cronJobId": cron_id, "createdAt": existing.get("createdAt") or ports.now()})
        ports.merge_binding(str(cron_id), binding)
        return {"ok": True, "projectId": project_id, "id": cron_id, "binding": binding}


def delete(project_id: str, cron_id: str, *, ports: SchedulePorts) -> dict[str, Any]:
    with ports.operation_lock(cron_id):
        existing = ports.bindings().get(str(cron_id))
        if not existing or existing.get("projectId") != project_id:
            return {"error": "Project scheduled cron not found", "_status": 404}
        cron_result = _gateway(ports, "cron.remove", {"id": cron_id}, 30)
        if not cron_result.get("ok"):
            return _gateway_error("Failed to delete cron job")
        ports.delete_binding(str(cron_id))
        return {"ok": True, "projectId": project_id, "id": cron_id}


def run_now(project_id: str, cron_id: str, *, ports: SchedulePorts, dispatch: Callable[[str, str, str, str | None], dict[str, Any]]) -> dict[str, Any]:
    with ports.operation_lock(cron_id):
        binding = ports.bindings().get(str(cron_id))
        if not binding or binding.get("projectId") != project_id:
            return {"error": "Project scheduled cron not found", "_status": 404}
        occurrence_id = ports.next_occurrence_id(cron_id)
        cron_result = _gateway(ports, "cron.run", {"id": cron_id, "invocationId": occurrence_id}, 30)
        if not cron_result.get("ok"):
            return _gateway_error("Failed to run cron job")
        local = dispatch(project_id, cron_id, "run-now", occurrence_id)
        safe_gateway_result = ports.sanitize_result(cron_result)
    return {
        "ok": True, "projectId": project_id, "id": cron_id,
        "result": safe_gateway_result, "dispatch": local,
        "reconciliation": {
            "gatewayStatus": "started",
            "localStatus": local.get("status") or ("started" if local.get("ok") else "failed"),
            "required": local.get("ok") is not True,
        },
    }


def dispatch(project_id: str, cron_id: str, source: str = "manual", occurrence_id: str | None = None, *, ports: DispatchPorts) -> dict[str, Any]:
    started_at = ports.monotonic()
    binding = ports.get_binding(str(cron_id))
    if not binding or binding.get("projectId") != project_id:
        return {"error": "Project scheduled cron not found", "_status": 404}
    # Persisted claims protect paths that can actually launch work. Static
    # ineligible states do not need a claim and avoiding two binding writes is
    # material for frequent archived/paused scheduler callbacks.
    project = ports.get_project(project_id)
    if not project:
        ports.update_binding_status(cron_id, "missing_project", "Project not found")
        return {"error": "Project not found", "_status": 404, "status": "missing_project"}
    static_skip = None
    if binding.get("lastStatus") == "disengaged_completed":
        return {
            "ok": True, "status": "skipped", "reason": "pre_check_disengaged",
            "projectId": project_id, "id": cron_id, "idempotent": True,
        }
    if project.get("status") == "archived":
        static_skip = ("skipped_archived", "Project is archived", "skipped", "project_archived")
    elif project.get("scheduledCronPaused"):
        static_skip = ("paused", "Project scheduled cron is paused", "paused", "project_cron_paused")
    if static_skip:
        binding_status, message, status, reason = static_skip
        ports.update_binding_status(cron_id, binding_status, message)
        ports.append_history(
            project_id, cron_id, binding, status, reason=reason, source=source,
            duration_ms=int((ports.monotonic() - started_at) * 1000),
        )
        return {"ok": True, "status": status, "reason": reason, "projectId": project_id, "id": cron_id}
    claim = ports.claim_dispatch(str(cron_id), source, occurrence_id)
    if not claim.get("claimed"):
        reason = "duplicate_occurrence" if claim.get("status") == "completed_occurrence" else "dispatch_in_progress"
        return {
            "ok": True, "status": "skipped", "reason": reason,
            "projectId": project_id, "id": cron_id, "idempotent": True,
        }
    token = str(claim.get("token") or "")
    renewal_stop = threading.Event()

    def renew_lease() -> None:
        while not renewal_stop.wait(max(0.01, ports.lease_refresh_seconds)):
            if not ports.renew_dispatch(str(cron_id), token):
                return

    renewal = threading.Thread(target=renew_lease, name=f"cron-lease-{cron_id}", daemon=True)
    renewal.start()
    try:
        with ports.operation_lock(cron_id):
            if not ports.owns_dispatch(str(cron_id), token):
                return {
                    "ok": True, "status": "skipped", "reason": "dispatch_claim_superseded",
                    "projectId": project_id, "id": cron_id, "idempotent": True,
                }
            return _dispatch_locked(project_id, cron_id, source, ports=ports)
    finally:
        renewal_stop.set()
        renewal.join(timeout=max(0.02, min(1.0, ports.lease_refresh_seconds * 2)))
        ports.release_dispatch(str(cron_id), token)


def _dispatch_locked(project_id: str, cron_id: str, source: str, *, ports: DispatchPorts) -> dict[str, Any]:
    started_at = ports.monotonic()
    binding = ports.get_binding(str(cron_id))
    if not binding or binding.get("projectId") != project_id:
        return {"error": "Project scheduled cron not found", "_status": 404}

    def record(status: str, reason: str | None = None, error: str | None = None, result: dict[str, Any] | None = None) -> Any:
        return ports.append_history(
            project_id, cron_id, binding, status, reason=reason, error=error,
            result=result, source=source,
            duration_ms=int((ports.monotonic() - started_at) * 1000),
        )

    if binding.get("lastStatus") == "disengaged_completed":
        return {
            "ok": True, "status": "skipped", "reason": "pre_check_disengaged",
            "projectId": project_id, "id": cron_id, "idempotent": True,
        }
    project = ports.get_project(project_id)
    if not project:
        ports.update_binding_status(cron_id, "missing_project", "Project not found")
        return {"error": "Project not found", "_status": 404, "status": "missing_project"}
    if project.get("status") == "archived":
        ports.update_binding_status(cron_id, "skipped_archived", "Project is archived")
        record("skipped", "project_archived")
        return {"ok": True, "status": "skipped", "reason": "project_archived", "projectId": project_id, "id": cron_id}
    if project.get("scheduledCronPaused"):
        ports.update_binding_status(cron_id, "paused", "Project scheduled cron is paused")
        record("paused", "project_cron_paused")
        return {"ok": True, "status": "paused", "reason": "project_cron_paused", "projectId": project_id, "id": cron_id}
    target_type = binding.get("targetType") or "projectWorkflow"
    task_id = binding.get("taskId")
    active = ports.active_task(project) if ports.execution_enabled(project) else None
    if active:
        ports.update_binding_status(
            cron_id, "skipped", "Another task is already active for this project",
            {"activeTaskId": active.get("id")},
        )
        record("skipped", "project_active")
        return {
            "ok": True, "status": "skipped", "reason": "project_active",
            "activeTaskId": active.get("id"), "projectId": project_id, "id": cron_id,
        }

    if target_type == "projectTask":
        task = next((item for item in project.get("tasks", []) if item.get("id") == task_id), None)
        if not task:
            ports.update_binding_status(cron_id, "missing_target", "Task not found")
            record("skipped", "task_missing")
            return {"ok": True, "status": "skipped", "reason": "task_missing", "projectId": project_id, "id": cron_id}
        if task.get("completedAt") and task.get("scheduledRepeatEnabled") is not True:
            ports.update_binding_status(cron_id, "disengaged_completed", "Task completed, cron disengaged")
            record("skipped", "task_completed_cron_disengaged")
            _gateway(ports, "cron.update", {"id": cron_id, "patch": {"enabled": False}}, 5)
            return {
                "ok": True, "status": "skipped", "reason": "task_completed_cron_disengaged",
                "projectId": project_id, "id": cron_id, "taskId": task_id,
            }
        reopened = False
        if task.get("completedAt"):
            reopen = ports.reopen_task(project_id, task_id)
            if not reopen.get("ok"):
                result = reopen
            else:
                reopened = bool(reopen.get("reopened"))
                project = reopen.get("project") or project
                task = next((item for item in project.get("tasks", []) if item.get("id") == task_id), task)
                result = None
        else:
            result = None
        if result is None:
            if ports.execution_enabled(project):
                result = ports.start_task(project_id, task_id, {
                    "by": "project-cron", "source": source, "skipReviewConfirmed": True,
                })
            else:
                result = ports.start_legacy(project_id, {"autoMode": False})
        if reopened and isinstance(result, dict):
            result["reopenedCompletedTask"] = True
    else:
        tasks = project.get("tasks", []) or []
        all_completed = False
        if target_type == "projectWorkflow" and tasks:
            done_columns = ports.done_column_ids(project)
            all_completed = not any(
                task.get("columnId") not in done_columns and not task.get("completedAt")
                for task in tasks
            )
        if all_completed:
            ports.update_binding_status(cron_id, "disengaged_completed", "All tasks completed; cron disengaged")
            record("skipped", "project_all_tasks_completed")
            _gateway(ports, "cron.update", {"id": cron_id, "patch": {"enabled": False}}, 5)
            recent_same = [
                item for item in (project.get("scheduledCronHistory") or [])[-10:]
                if isinstance(item, dict) and item.get("reason") == "project_all_tasks_completed"
            ]
            if len(recent_same) >= 2:
                _gateway(ports, "cron.alert", {
                    "id": cron_id,
                    "message": (
                        f"P0 cron 重复触发缺陷告警：项目 {project_id} 的所有任务已完成，"
                        f"但定时任务被重复触发（最近 10 次中有 {len(recent_same)} 次因 '项目已完成' 跳过）。"
                        "已自动暂停该定时任务。请确认是否有残留缺陷。"
                    ),
                }, 10)
            return {
                "ok": True, "status": "skipped", "reason": "project_all_tasks_completed",
                "projectId": project_id, "id": cron_id, "allCompleted": True, "cronDisabled": True,
            }
        if ports.execution_enabled(project):
            result = ports.start_project(project_id, {
                "mode": project.get("projectExecutionStartMode") or "continuous",
                "by": "project-cron", "source": source, "skipReviewConfirmed": True,
            })
        else:
            result = ports.start_legacy(project_id, {"autoMode": True})

    result = ports.sanitize_result(result)
    if result.get("ok"):
        ports.update_binding_status(cron_id, "started", None, {"lastDispatchResult": result})
        record("started", result=result)
        return {"ok": True, "status": "started", "projectId": project_id, "id": cron_id, "result": result}
    if result.get("confirmationRequired"):
        reason = result.get("code") or "confirmation_required"
        ports.update_binding_status(cron_id, "skipped_confirmation_required", reason, {"lastDispatchResult": result})
        record("skipped", reason, error=result.get("error"), result=result)
        return {"ok": True, "status": "skipped", "reason": reason, "projectId": project_id, "id": cron_id, "result": result}
    status = "skipped" if result.get("_status") == 409 else "failed"
    failure = result.get("error") or result.get("code") or "dispatch failed"
    ports.update_binding_status(cron_id, status, failure, {"lastDispatchResult": result})
    if status == "skipped":
        reason = result.get("code") or result.get("error")
        record("skipped", reason, error=result.get("error"), result=result)
        return {"ok": True, "status": "skipped", "reason": reason, "projectId": project_id, "id": cron_id, "result": result}
    record("failed", result.get("code") or "dispatch_failed", error=result.get("error"), result=result)
    return {**result, "projectId": project_id, "id": cron_id}
