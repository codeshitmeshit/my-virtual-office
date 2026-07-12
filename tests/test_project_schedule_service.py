import os
import sys
import threading
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services import project_schedule


def _schedule_fixture():
    project = {"id": "p", "title": "Project", "status": "active", "createdBy": "owner", "tasks": [{"id": "t", "title": "Task"}]}
    bindings = {}
    jobs = {}
    reservations = set()
    reservation_lock = threading.Lock()

    def gateway(method, params, timeout):
        if method == "cron.add":
            jobs["c"] = {**params, "id": "c"}
            return {"ok": True, "job": jobs["c"]}
        if method == "cron.list":
            return {"ok": True, "jobs": list(jobs.values())}
        if method == "cron.update":
            jobs[params["id"]].update(params["patch"])
            return {"ok": True}
        if method == "cron.remove":
            jobs.pop(params["id"], None)
            return {"ok": True}
        if method == "cron.run":
            return {"ok": True, "id": params["id"]}
        return {"ok": False, "error": "unexpected"}

    def build_job(project_value, body, existing):
        target = body.get("targetType") or (existing or {}).get("targetType") or "projectWorkflow"
        schedule = body.get("schedule") or (existing or {}).get("schedule")
        job = {"name": body.get("name") or (existing or {}).get("name") or "Cron", "schedule": schedule, "enabled": body.get("enabled", True)}
        return job, {**job, "projectId": project_value["id"], "targetType": target, "taskId": body.get("taskId")}

    ports = project_schedule.SchedulePorts(
        gateway=gateway,
        validate_project=lambda project_id: (project, None) if project_id == "p" else (None, {"error": "Project not found", "_status": 404}),
        get_project=lambda project_id: project if project_id == "p" else None,
        list_projects=lambda: [project],
        bindings=lambda: {key: dict(value) for key, value in bindings.items()},
        put_binding=lambda cron_id, binding: bindings.__setitem__(cron_id, dict(binding)),
        merge_binding=lambda cron_id, binding: bindings.__setitem__(cron_id, {**bindings.get(cron_id, {}), **dict(binding)}),
        delete_binding=lambda cron_id: bindings.pop(cron_id, None),
        reserve_binding_slot=lambda limit: _reserve_slot(bindings, reservations, reservation_lock, limit),
        release_binding_slot=lambda token: _release_slot(reservations, reservation_lock, token),
        operation_lock=project_schedule.KeyedOperationLocks().hold,
        validate_job_policy=lambda project_value, body, existing: None,
        sanitize_result=lambda result: dict(result or {}),
        update_binding_status=lambda *args, **kwargs: None,
        validate_schedule=lambda schedule: None if schedule and schedule.get("kind") else "Schedule is required",
        validate_target=lambda project_value, target, task_id: None,
        build_job=build_job,
        extract_jobs=lambda result: result.get("jobs", []),
        extract_job_id=lambda result: str((result.get("job") or {}).get("id") or ""),
        enrich_item=lambda cron_id, binding, job, project_value: {**job, **binding, "id": cron_id},
        now=lambda: "now",
        next_occurrence_id=lambda cron_id: f"{cron_id}:run-now:1",
    )
    return ports, bindings, jobs


def _reserve_slot(bindings, reservations, lock, limit):
    with lock:
        if len(bindings) + len(reservations) >= limit:
            return None
        token = f"reservation-{len(reservations)}-{time.monotonic_ns()}"
        reservations.add(token)
        return token


def _release_slot(reservations, lock, token):
    with lock:
        reservations.discard(token)


def test_schedule_service_crud_preserves_gateway_then_binding_order():
    ports, bindings, jobs = _schedule_fixture()
    created = project_schedule.create("p", {
        "name": "Cron", "schedule": {"kind": "every", "everyMs": 60000},
        "targetType": "projectWorkflow",
    }, ports=ports)
    assert created["ok"] is True
    assert "c" in jobs and "c" in bindings
    listed = project_schedule.list_jobs("p", ports=ports)
    assert listed["jobs"][0]["id"] == "c"
    updated = project_schedule.update("p", "c", {"enabled": False}, ports=ports)
    assert updated["ok"] is True
    assert jobs["c"]["enabled"] is False
    deleted = project_schedule.delete("p", "c", ports=ports)
    assert deleted["ok"] is True
    assert jobs == {} and bindings == {}


def test_run_now_reports_gateway_success_local_failure_for_reconciliation():
    ports, bindings, _jobs = _schedule_fixture()
    project_schedule.create("p", {
        "schedule": {"kind": "every", "everyMs": 60000}, "targetType": "projectWorkflow",
    }, ports=ports)
    result = project_schedule.run_now(
        "p", "c", ports=ports,
        dispatch=lambda project_id, cron_id, source, occurrence_id=None: {"ok": False, "status": "failed", "error": "local failed"},
    )
    assert result["ok"] is True
    assert result["dispatch"]["error"] == "local failed"
    assert result["reconciliation"] == {
        "gatewayStatus": "started", "localStatus": "failed", "required": True,
    }


def test_gateway_exception_maps_to_502_without_binding_write():
    ports, bindings, _jobs = _schedule_fixture()
    broken = project_schedule.SchedulePorts(
        **{**ports.__dict__, "gateway": lambda *args: (_ for _ in ()).throw(RuntimeError("token=canary"))}
    )
    result = project_schedule.create("p", {
        "schedule": {"kind": "every", "everyMs": 60000}, "targetType": "projectWorkflow",
    }, ports=broken)
    assert result["_status"] == 502
    assert "canary" not in str(result)
    assert bindings == {}


def test_same_cron_updates_are_serialized_and_binding_matches_gateway():
    ports, bindings, jobs = _schedule_fixture()
    project_schedule.create("p", {
        "schedule": {"kind": "every", "everyMs": 60000}, "targetType": "projectWorkflow",
    }, ports=ports)
    active = 0
    max_active = 0
    guard = threading.Lock()
    original_gateway = ports.gateway

    def slow_gateway(method, params, timeout):
        nonlocal active, max_active
        if method == "cron.update":
            with guard:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.03)
            result = original_gateway(method, params, timeout)
            with guard:
                active -= 1
            return result
        return original_gateway(method, params, timeout)

    serial_ports = project_schedule.SchedulePorts(**{**ports.__dict__, "gateway": slow_gateway})
    outcomes = []
    threads = [
        threading.Thread(target=lambda enabled=enabled: outcomes.append(
            project_schedule.update("p", "c", {"enabled": enabled}, ports=serial_ports)
        ))
        for enabled in (False, True)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(2)
    assert len(outcomes) == 2 and all(item["ok"] for item in outcomes)
    assert max_active == 1
    assert bindings["c"]["enabled"] == jobs["c"]["enabled"]


def test_binding_limit_rejects_before_gateway_write():
    ports, bindings, jobs = _schedule_fixture()
    bindings["existing"] = {"projectId": "p"}
    limited = project_schedule.SchedulePorts(**{**ports.__dict__, "binding_limit": 1})
    result = project_schedule.create("p", {
        "schedule": {"kind": "every", "everyMs": 60000}, "targetType": "projectWorkflow",
    }, ports=limited)
    assert result["_status"] == 409
    assert result["code"] == "cron_binding_limit"
    assert jobs == {}


def test_binding_limit_reservation_is_atomic_for_concurrent_create():
    ports, bindings, jobs = _schedule_fixture()
    bindings["existing"] = {"projectId": "p"}
    calls = 0
    guard = threading.Lock()
    original_gateway = ports.gateway

    def counted_gateway(method, params, timeout):
        nonlocal calls
        if method == "cron.add":
            with guard:
                calls += 1
            time.sleep(0.03)
        return original_gateway(method, params, timeout)

    limited = project_schedule.SchedulePorts(**{
        **ports.__dict__, "gateway": counted_gateway, "binding_limit": 2,
    })
    outcomes = []
    threads = [threading.Thread(target=lambda: outcomes.append(project_schedule.create("p", {
        "schedule": {"kind": "every", "everyMs": 60000}, "targetType": "projectWorkflow",
    }, ports=limited))) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(2)
    assert calls == 1
    assert len(bindings) == 2
    assert sorted(item.get("_status", 200) for item in outcomes) == [200, 409]


def test_gateway_success_binding_failure_is_compensated_and_releases_slot():
    ports, bindings, jobs = _schedule_fixture()
    broken = project_schedule.SchedulePorts(**{
        **ports.__dict__, "merge_binding": lambda *_: (_ for _ in ()).throw(OSError("disk full")),
    })
    result = project_schedule.create("p", {
        "schedule": {"kind": "every", "everyMs": 60000}, "targetType": "projectWorkflow",
    }, ports=broken)
    assert result["_status"] == 500
    assert result["code"] == "cron_binding_persist_failed"
    assert jobs == {}
    retry = project_schedule.create("p", {
        "schedule": {"kind": "every", "everyMs": 60000}, "targetType": "projectWorkflow",
    }, ports=ports)
    assert retry["ok"] is True


def test_update_binding_failure_restores_previous_gateway_job():
    ports, bindings, jobs = _schedule_fixture()
    project_schedule.create("p", {
        "schedule": {"kind": "every", "everyMs": 60000}, "targetType": "projectWorkflow",
    }, ports=ports)
    before_job = dict(jobs["c"])
    broken = project_schedule.SchedulePorts(**{
        **ports.__dict__, "merge_binding": lambda *_: (_ for _ in ()).throw(OSError("disk full")),
    })
    result = project_schedule.update("p", "c", {"enabled": False}, ports=broken)
    assert result["_status"] == 500
    assert result["code"] == "cron_binding_persist_failed"
    assert result["reconciliationRequired"] is False
    assert jobs["c"] == before_job
    assert bindings["c"]["enabled"] is True


def test_delete_binding_failure_can_retry_when_gateway_reports_missing():
    ports, bindings, jobs = _schedule_fixture()
    project_schedule.create("p", {
        "schedule": {"kind": "every", "everyMs": 60000}, "targetType": "projectWorkflow",
    }, ports=ports)
    broken = project_schedule.SchedulePorts(**{
        **ports.__dict__, "delete_binding": lambda *_: (_ for _ in ()).throw(OSError("disk full")),
    })
    first = project_schedule.delete("p", "c", ports=broken)
    assert first["_status"] == 500
    assert first["code"] == "cron_binding_delete_failed"
    assert "c" not in jobs and "c" in bindings

    original_gateway = ports.gateway

    def missing_gateway(method, params, timeout):
        if method == "cron.remove":
            return {"ok": False, "code": "not_found", "error": "job not found"}
        return original_gateway(method, params, timeout)

    retry_ports = project_schedule.SchedulePorts(**{**ports.__dict__, "gateway": missing_gateway})
    retry = project_schedule.delete("p", "c", ports=retry_ports)
    assert retry["ok"] is True
    assert bindings == {}
