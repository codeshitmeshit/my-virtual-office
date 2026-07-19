#!/usr/bin/env python3
"""End-to-end HTTP contracts for conversation-confirmed direct creation."""

import io
import json
import hashlib
import os
import sys
import tempfile

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")
os.environ["VO_STATUS_DIR"] = tempfile.mkdtemp(prefix="vo-project-authoring-http-contract-")

import server
from project_store import MarkdownProjectStore
from services.project_authoring import ProjectAuthoringService
from services.project_authoring_store import ProjectAuthoringRootStore, REQUESTS_KEY
from services.project_recurrence import ProjectRecurrenceReconciler, RecurrenceRegistrationPorts
from services.project_repository import ProjectRepository


AGENTS = {
    "author": {"id": "author"},
    "other-agent": {"id": "other-agent"},
    "owner": {"id": "owner"},
    "builder": {"id": "builder"},
}
SUMMARY_TEXT = """我准备创建这个 VO 项目，请确认：

项目名称：HTTP project
项目类型：one_time
项目目标：HTTP contract project
维护模式：strict_confirmation
创建后状态：确认后会创建真实项目，但不会开始执行。
Reviewer 默认策略：不指定；如有建议，仅作为建议，确认分配前不会写入 reviewer。

任务清单：

| # | 任务名称 | 所属列 | 任务细节 | 验收标准 | 负责人 | 执行人 | Reviewer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Implement | Backlog | HTTP contract project | 完成任务 | owner | builder | 不指定 |

模板/复用配置：无
周期配置：无
需要你确认的点：无

请确认是否按以上方案创建真实项目。"""
SUMMARY_DIGEST = hashlib.sha256(SUMMARY_TEXT.encode("utf-8")).hexdigest()
MAINTENANCE_SUMMARY_TEXT = """我准备修改这个 VO 项目，请确认：

项目 ID：project-creation-1
项目名称：Strict
修改目标：更新项目标题
修改内容：

| # | 类型 | 对象 | 当前值 | 目标值 | 影响 |
| --- | --- | --- | --- | --- | --- |
| 1 | update_project | 项目标题 | Strict | Confirmed without grant | 项目标题会更新 |

不会修改的内容：任务、角色、reviewer、执行状态、周期配置
风险/注意事项：无
需要你确认的点：无

请确认是否按以上方案修改真实项目。"""
MAINTENANCE_SUMMARY_DIGEST = hashlib.sha256(MAINTENANCE_SUMMARY_TEXT.encode("utf-8")).hexdigest()
RECURRENCE_MAINTENANCE_SUMMARY_TEXT = """我准备修改这个 VO 项目，请确认：

项目 ID：project-creation-1
项目名称：Strict
修改目标：设置为可复用并每天 10:00 运行
修改内容：

| # | 类型 | 对象 | 当前值 | 目标值 | 影响 |
| --- | --- | --- | --- | --- | --- |
| 1 | update_recurrence | 项目周期配置 | 无 | 每天 10:00 Asia/Shanghai | 项目会记录自身周期属性 |

不会修改的内容：任务、角色、reviewer、执行状态
风险/注意事项：无
需要你确认的点：无

请确认是否按以上方案修改真实项目。"""
RECURRENCE_MAINTENANCE_SUMMARY_DIGEST = hashlib.sha256(RECURRENCE_MAINTENANCE_SUMMARY_TEXT.encode("utf-8")).hexdigest()


class _Connection:
    def settimeout(self, timeout):
        self.timeout = timeout


def _project(title):
    return {
        "title": title,
        "projectType": "one_time",
        "agentMaintenanceMode": "strict_confirmation",
        "columns": [{"id": "backlog", "title": "Backlog"}],
        "tasks": [{
            "title": "Implement",
            "columnId": "backlog",
            "responsibleActor": {"type": "agent", "id": "owner"},
            "executorActor": {"type": "agent", "id": "builder"},
            "reviewerRecommendation": {"recommended": False, "triggers": []},
        }],
        "template": {"mode": "none"},
        "recurrence": {"enabled": False},
    }


def _handler(path, body=None, *, headers=None, remote="127.0.0.1", content_length=None):
    payload = json.dumps(body).encode() if body is not None else b""
    handler = object.__new__(server.OfficeHandler)
    handler.path = path
    handler.client_address = (remote, 12345)
    handler.headers = {
        "Content-Length": str(len(payload) if content_length is None else content_length),
        **(headers or {}),
    }
    handler.rfile = io.BytesIO(payload)
    handler.wfile = io.BytesIO()
    handler.connection = _Connection()
    handler.responses = []
    handler.response_headers = []
    handler.send_response = lambda status, *args, **kwargs: handler.responses.append(status)
    handler.send_header = lambda name, value: handler.response_headers.append((name, value))
    handler.end_headers = lambda: None
    return handler


def _call(handler, method):
    getattr(handler, f"do_{method}")()
    raw = handler.wfile.getvalue()
    return handler.responses[-1], json.loads(raw) if raw else {}


@pytest.fixture
def authoring(tmp_path, monkeypatch):
    markdown = MarkdownProjectStore(str(tmp_path))
    markdown.save_all({"projects": [], "templates": []})
    repository = ProjectRepository(
        load_projects=markdown.load_all,
        save_projects=markdown.save_all,
        cache_namespace=lambda: (markdown, markdown.revision()),
    )
    creation_ids = iter(("creation-1", "creation-2", "creation-3", "creation-4"))
    secrets = iter(("direct-secret-1", "direct-secret-2", "direct-secret-3", "direct-secret-4"))
    service = ProjectAuthoringService(
        ProjectAuthoringRootStore(repository),
        lookup_agent=AGENTS.get,
        is_excluded_agent=lambda _agent_id: False,
        submission_enabled=lambda: True,
        recurrence_enabled=lambda: True,
        recurrence_paused=lambda: False,
        new_id=lambda: next(creation_ids),
        new_secret=lambda: next(secrets),
    )
    monkeypatch.setattr(server, "_PROJECT_AUTHORING_SERVICE", service)
    monkeypatch.setattr(
        server,
        "_PROJECT_RECURRENCE_RECONCILER",
        ProjectRecurrenceReconciler(
            service.store,
            RecurrenceRegistrationPorts(
                gateway=lambda method, _params, _timeout: (
                    {"ok": True, "id": "cron-http"} if method == "cron.add" else {"ok": True}
                ),
                validate_schedule=lambda _schedule: None,
                extract_job_id=lambda result: str(result.get("id") or ""),
                enabled=lambda: True,
                paused=lambda: False,
            ),
        ),
    )
    return markdown, service


def _create(project, key, *, agent="author", origin=""):
    headers = {"X-VO-Agent-Action": "project-authoring", "X-VO-Agent-Id": agent}
    if origin:
        headers["Origin"] = origin
    return _call(_handler(
        "/api/agent/project-authoring/projects",
        {
            "idempotencyKey": key,
            "confirmation": {
                "confirmed": True,
                "summaryDigest": SUMMARY_DIGEST,
                "summaryText": SUMMARY_TEXT,
            },
            "project": project,
        },
        headers=headers,
    ), "POST")


def _grant_headers(secret, *, agent="author"):
    return {
        "X-VO-Agent-Action": "project-authoring",
        "X-VO-Agent-Id": agent,
        "Authorization": f"Bearer {secret}",
    }


def test_direct_create_is_atomic_idempotent_unstarted_and_origin_safe(authoring):
    markdown, _ = authoring

    status, created = _create(_project("Direct HTTP"), "author:direct-http")
    repeat_status, repeated = _create(_project("Direct HTTP"), "author:direct-http")

    assert status == repeat_status == 200
    assert created["created"] is True and repeated["created"] is False
    assert created["project"]["id"] == repeated["project"]["id"]
    assert "projectGrantSecret" in created and "projectGrantSecret" not in repeated
    root = markdown.load_all()
    assert root[REQUESTS_KEY] == {}
    assert len(root["projects"]) == 1
    assert root["projects"][0]["tasks"][0]["executionState"] == "backlog"
    assert root["projects"][0]["workflowActive"] is False
    assert root["projects"][0]["projectExecutionFlowActive"] is False

    denied_status, denied = _create(
        _project("Browser attempt"), "author:browser", origin="http://localhost:3000",
    )
    assert denied_status == 403
    assert denied["code"] == "agent_authoring_browser_origin_rejected"
    assert len(markdown.load_all()["projects"]) == 1

    missing_text_status, missing_text = _call(_handler(
        "/api/agent/project-authoring/projects",
        {
            "idempotencyKey": "author:missing-summary-text",
            "confirmation": {"confirmed": True, "summaryDigest": SUMMARY_DIGEST},
            "project": _project("Missing summary text"),
        },
        headers={"X-VO-Agent-Action": "project-authoring", "X-VO-Agent-Id": "author"},
    ), "POST")
    assert missing_text_status == 400
    assert missing_text["code"] == "confirmation_summary_text_required"
    assert len(markdown.load_all()["projects"]) == 1


def test_removed_draft_routes_do_not_mutate_or_expose_legacy_requests(authoring):
    markdown, _ = authoring
    before = markdown.load_all()
    for method, path, body in (
        ("POST", "/api/agent/project-authoring/requests", {"draft": _project("Old")}),
        ("GET", "/api/agent/project-authoring/requests/request-1", None),
        ("GET", "/api/project-authoring/requests", None),
        ("PUT", "/api/project-authoring/requests/request-1", {"expectedRevision": 1}),
        ("POST", "/api/project-authoring/requests/request-1/confirm", {"expectedRevision": 1}),
        ("POST", "/api/project-authoring/requests/request-1/reject", {"expectedRevision": 1}),
    ):
        assert _call(_handler(
            path,
            body,
            headers={"X-VO-Management-Token": server._MANAGEMENT_TOKEN},
        ), method)[0] == 404
    assert markdown.load_all() == before


def test_direct_reusable_project_keeps_management_template_instantiation(authoring):
    markdown, _ = authoring
    project = _project("Reusable HTTP")
    project.update({
        "projectType": "reusable",
        "template": {"mode": "create", "name": "Reusable HTTP template"},
    })
    _, created = _create(project, "author:template-http")
    template_id = created["project"]["templateRef"]["id"]
    endpoint = f"/api/project-authoring/templates/{template_id}/instantiate"
    body = {
        "version": 1,
        "idempotencyKey": "template:http-instance-1",
        "overrides": {"title": "HTTP instance"},
    }

    assert _call(_handler(endpoint, body), "POST")[0] == 403
    first_status, first = _call(_handler(
        endpoint, body, headers={"X-VO-Management-Token": server._MANAGEMENT_TOKEN},
    ), "POST")
    repeat_status, repeated = _call(_handler(
        endpoint, body, headers={"X-VO-Management-Token": server._MANAGEMENT_TOKEN},
    ), "POST")
    assert first_status == repeat_status == 200
    assert first["created"] is True and repeated["created"] is False
    assert first["project"]["id"] == repeated["project"]["id"]
    assert len(markdown.load_all()["projects"]) == 2


def test_direct_reusable_project_can_be_project_attribute_without_template(authoring):
    markdown, _ = authoring
    project = _project("Reusable without template")
    project.update({
        "projectType": "reusable",
        "template": {"mode": "none"},
    })

    status, created = _create(project, "author:reusable-no-template")

    assert status == 200
    assert created["project"]["projectType"] == "reusable"
    assert created["project"].get("templateRef") == {}
    assert len(markdown.load_all()["projects"]) == 1


def test_confirmed_update_recurrence_applies_to_existing_project_attribute(authoring):
    markdown, _ = authoring
    status, created = _create(_project("Strict"), "author:recurrence-maintenance-source")
    assert status == 200
    project_id = created["project"]["id"]

    update_status, updated = _call(_handler(
        f"/api/agent/projects/{project_id}/maintenance",
        {
            "idempotencyKey": "author:update-recurrence-existing",
            "confirmation": {
                "confirmed": True,
                "summaryDigest": RECURRENCE_MAINTENANCE_SUMMARY_DIGEST,
                "summaryText": RECURRENCE_MAINTENANCE_SUMMARY_TEXT,
            },
            "mutation": {
                "operation": "update_recurrence",
                "changes": {
                    "schedule": {"kind": "cron", "expr": "0 10 * * *", "timezone": "Asia/Shanghai"},
                },
            },
        },
        headers={"X-VO-Agent-Action": "project-authoring", "X-VO-Agent-Id": "author"},
    ), "POST")

    assert update_status == 200
    assert updated["project"]["projectType"] == "recurring"
    assert updated["project"]["recurrence"]["enabled"] is True
    assert updated["project"]["recurrence"]["schedule"]["expr"] == "0 10 * * *"
    stored = next(item for item in markdown.load_all()["projects"] if item["id"] == project_id)
    assert stored["recurrence"]["schedule"]["timezone"] == "Asia/Shanghai"


def test_confirmed_agent_scheduled_cron_bypasses_management_token_and_is_idempotent(authoring, monkeypatch):
    status, created = _create(_project("Strict"), "author:cron-source")
    assert status == 200
    project_id = created["project"]["id"]
    calls = []

    monkeypatch.setattr(server, "_project_schedule_bindings", lambda: {
        "cron-agent-1": {
            "projectId": project_id,
            "agentScheduleIdempotencyKey": "author:daily-cron",
            "agentSchedulePayloadDigest": calls[0]["agentSchedulePayloadDigest"] if calls else "",
            "createdByAgentId": "author",
            "schedule": {"kind": "cron", "expr": "0 10 * * *", "timezone": "Asia/Shanghai"},
        }
    } if calls else {})

    def fake_create(pid, cron_body):
        calls.append(dict(cron_body))
        return {
            "ok": True,
            "projectId": pid,
            "id": "cron-agent-1",
            "binding": {
                "projectId": pid,
                "agentScheduleIdempotencyKey": cron_body.get("agentScheduleIdempotencyKey"),
                "agentSchedulePayloadDigest": cron_body.get("agentSchedulePayloadDigest"),
                "createdByAgentId": cron_body.get("createdByAgentId"),
                "schedule": cron_body.get("schedule"),
            },
        }

    monkeypatch.setattr(server, "_handle_agent_project_scheduled_cron_create", fake_create)
    payload = {
        "idempotencyKey": "author:daily-cron",
        "confirmation": {
            "confirmed": True,
            "summaryDigest": RECURRENCE_MAINTENANCE_SUMMARY_DIGEST,
            "summaryText": RECURRENCE_MAINTENANCE_SUMMARY_TEXT,
        },
        "projectType": "reusable",
        "longTermProject": True,
        "cron": {
            "name": "日报每日执行",
            "schedule": {"kind": "cron", "expr": "0 10 * * *", "timezone": "Asia/Shanghai"},
            "targetType": "projectWorkflow",
            "enabled": True,
        },
    }

    first_status, first = _call(_handler(
        f"/api/agent/projects/{project_id}/scheduled-cron",
        payload,
        headers={"X-VO-Agent-Action": "project-authoring", "X-VO-Agent-Id": "author"},
    ), "POST")
    repeat_status, repeated = _call(_handler(
        f"/api/agent/projects/{project_id}/scheduled-cron",
        payload,
        headers={"X-VO-Agent-Action": "project-authoring", "X-VO-Agent-Id": "author"},
    ), "POST")

    assert first_status == repeat_status == 200
    assert first["created"] is True
    assert repeated["created"] is False
    assert len(calls) == 1
    assert calls[0]["createdByAgentId"] == "author"


def test_direct_recurring_project_uses_source_grant_and_deduplicates_occurrence(authoring):
    markdown, _ = authoring
    project = _project("Recurring HTTP")
    project.update({
        "projectType": "recurring",
        "template": {"mode": "create", "name": "Recurring HTTP template"},
        "recurrence": {
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "0 9 * * 1", "timezone": "UTC"},
        },
    })
    _, created = _create(project, "author:recurrence-http")
    secret = created["projectGrantSecret"]
    recurrence_id = created["project"]["recurrenceRef"]["id"]
    endpoint = f"/api/agent/project-recurrences/{recurrence_id}/occurrences"
    headers = _grant_headers(secret)

    assert _call(_handler(
        endpoint,
        {"occurrenceId": "gateway-http-1"},
        headers={**headers, "Authorization": "Bearer wrong"},
    ), "POST")[0] == 403
    first_status, first = _call(_handler(
        endpoint, {"occurrenceId": "gateway-http-1"}, headers=headers,
    ), "POST")
    repeat_status, repeated = _call(_handler(
        endpoint, {"occurrenceId": "gateway-http-1"}, headers=headers,
    ), "POST")
    assert first_status == repeat_status == 200
    assert first["created"] is True and repeated["created"] is False
    assert first["project"]["id"] == repeated["project"]["id"]
    assert len(markdown.load_all()["projects"]) == 2


def test_direct_project_grant_rotation_revocation_and_scope_remain_protected(authoring):
    markdown, service = authoring
    _, created = _create(_project("Granted"), "author:grant-http")
    secret = created["projectGrantSecret"]
    project_id = created["project"]["id"]

    def authenticate(value, *, target=project_id, agent="author"):
        return service.authenticate_project_grant(
            target,
            requesting_agent_id=agent,
            grant_secret=value,
            required_operation="status",
        )

    assert authenticate(secret)["projectId"] == project_id
    before = markdown.load_all()
    with pytest.raises(Exception):
        authenticate(secret, target="different-project")
    with pytest.raises(Exception):
        authenticate(secret, agent="other-agent")
    assert markdown.load_all()["projects"] == before["projects"]

    rotate_path = f"/api/project-authoring/projects/{project_id}/grant/rotate"
    assert _call(_handler(rotate_path, {}), "POST")[0] == 403
    rotate_status, rotated = _call(_handler(
        rotate_path, {}, headers={"X-VO-Management-Token": server._MANAGEMENT_TOKEN},
    ), "POST")
    assert rotate_status == 200
    new_secret = rotated["grantSecret"]
    with pytest.raises(Exception):
        authenticate(secret)
    assert authenticate(new_secret)["projectId"] == project_id

    revoke_status, revoked = _call(_handler(
        f"/api/project-authoring/projects/{project_id}/grant/revoke",
        {},
        headers={"X-VO-Management-Token": server._MANAGEMENT_TOKEN},
    ), "POST")
    assert revoke_status == 200 and revoked["grant"]["state"] == "revoked"
    with pytest.raises(Exception):
        authenticate(new_secret)


def test_direct_project_maintenance_keeps_strict_and_autonomous_boundaries(authoring):
    markdown, _ = authoring
    _, strict = _create(_project("Strict"), "author:strict-http")
    strict_project = strict["project"]
    strict_headers = _grant_headers(strict["projectGrantSecret"])
    status, pending = _call(_handler(
        f"/api/agent/projects/{strict_project['id']}/maintenance",
        {
            "idempotencyKey": "maintenance:http-1",
            "mutation": {"operation": "update_project", "changes": {"title": "Confirmed title"}},
        },
        headers=strict_headers,
    ), "POST")
    assert status == 200
    assert markdown.load_all()["projects"][0]["title"] == "Strict"
    maintenance_id = pending["request"]["id"]
    management_path = (
        f"/api/project-authoring/projects/{strict_project['id']}"
        f"/maintenance/{maintenance_id}/confirm"
    )
    assert _call(_handler(management_path, {"expectedRevision": 1}), "POST")[0] == 403
    applied_status, _ = _call(_handler(
        management_path,
        {"expectedRevision": 1},
        headers={"X-VO-Management-Token": server._MANAGEMENT_TOKEN},
    ), "POST")
    assert applied_status == 200

    autonomous_project = _project("Autonomous")
    autonomous_project["agentMaintenanceMode"] = "autonomous"
    autonomous_project["tasks"][0]["executorActor"] = {"type": "agent", "id": "author"}
    _, autonomous = _create(autonomous_project, "author:auto-http")
    project = autonomous["project"]
    update_status, updated = _call(_handler(
        f"/api/agent/projects/{project['id']}/maintenance",
        {
            "idempotencyKey": "routine:http-direct",
            "mutation": {
                "operation": "routine_task_update",
                "taskId": project["tasks"][0]["id"],
                "changes": {"description": "Direct autonomous HTTP update"},
            },
        },
        headers=_grant_headers(autonomous["projectGrantSecret"]),
    ), "POST")
    assert update_status == 200 and updated["created"] is True
    stored = next(item for item in markdown.load_all()["projects"] if item["id"] == project["id"])
    assert stored["tasks"][0]["description"] == "Direct autonomous HTTP update"


def test_confirmed_agent_maintenance_without_grant_applies_after_summary_confirmation(authoring):
    markdown, _ = authoring
    _, created = _create(_project("Strict"), "author:confirmed-maintenance-http")
    project = created["project"]
    headers = {"X-VO-Agent-Action": "project-authoring", "X-VO-Agent-Id": "other-agent"}

    missing_status, missing = _call(_handler(
        f"/api/agent/projects/{project['id']}/maintenance",
        {
            "idempotencyKey": "maintenance:no-confirmation",
            "mutation": {"operation": "update_project", "changes": {"title": "Should not apply"}},
        },
        headers=headers,
    ), "POST")
    assert missing_status == 400
    assert missing["code"] == "maintenance_confirmation_required"
    assert markdown.load_all()["projects"][0]["title"] == "Strict"

    status, updated = _call(_handler(
        f"/api/agent/projects/{project['id']}/maintenance",
        {
            "idempotencyKey": "maintenance:confirmed-1",
            "confirmation": {
                "confirmed": True,
                "summaryDigest": MAINTENANCE_SUMMARY_DIGEST,
                "summaryText": MAINTENANCE_SUMMARY_TEXT,
            },
            "mutation": {"operation": "update_project", "changes": {"title": "Confirmed without grant"}},
        },
        headers=headers,
    ), "POST")

    assert status == 200
    assert updated["created"] is True
    assert updated["project"]["title"] == "Confirmed without grant"
    assert markdown.load_all()["projects"][0]["title"] == "Confirmed without grant"

    repeat_status, repeated = _call(_handler(
        f"/api/agent/projects/{project['id']}/maintenance",
        {
            "idempotencyKey": "maintenance:confirmed-1",
            "confirmation": {
                "confirmed": True,
                "summaryDigest": MAINTENANCE_SUMMARY_DIGEST,
                "summaryText": MAINTENANCE_SUMMARY_TEXT,
            },
            "mutation": {"operation": "update_project", "changes": {"title": "Confirmed without grant"}},
        },
        headers=headers,
    ), "POST")
    assert repeat_status == 200
    assert repeated["created"] is False

    conflict_status, conflict = _call(_handler(
        f"/api/agent/projects/{project['id']}/maintenance",
        {
            "idempotencyKey": "maintenance:confirmed-1",
            "confirmation": {
                "confirmed": True,
                "summaryDigest": MAINTENANCE_SUMMARY_DIGEST,
                "summaryText": MAINTENANCE_SUMMARY_TEXT,
            },
            "mutation": {"operation": "update_project", "changes": {"title": "Different title"}},
        },
        headers=headers,
    ), "POST")
    assert conflict_status == 409
    assert conflict["code"] == "maintenance_idempotency_conflict"
