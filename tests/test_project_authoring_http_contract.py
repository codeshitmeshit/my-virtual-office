#!/usr/bin/env python3
"""End-to-end HTTP contracts for conversation-confirmed direct creation."""

import io
import json
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
SUMMARY_DIGEST = "b" * 64


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
            "confirmation": {"confirmed": True, "summaryDigest": SUMMARY_DIGEST},
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
    markdown, _ = authoring
    _, created = _create(_project("Granted"), "author:grant-http")
    secret = created["projectGrantSecret"]
    project_id = created["project"]["id"]

    def grant_status(value, *, target=project_id, agent="author"):
        return _call(_handler(
            f"/api/agent/projects/{target}/grant-status",
            headers=_grant_headers(value, agent=agent),
        ), "GET")

    assert grant_status(secret)[0] == 200
    before = markdown.load_all()
    assert grant_status(secret, target="different-project")[0] == 403
    assert grant_status(secret, agent="other-agent")[0] == 403
    assert markdown.load_all()["projects"] == before["projects"]

    rotate_path = f"/api/project-authoring/projects/{project_id}/grant/rotate"
    assert _call(_handler(rotate_path, {}), "POST")[0] == 403
    rotate_status, rotated = _call(_handler(
        rotate_path, {}, headers={"X-VO-Management-Token": server._MANAGEMENT_TOKEN},
    ), "POST")
    assert rotate_status == 200
    new_secret = rotated["grantSecret"]
    assert grant_status(secret)[0] == 403 and grant_status(new_secret)[0] == 200

    revoke_status, revoked = _call(_handler(
        f"/api/project-authoring/projects/{project_id}/grant/revoke",
        {},
        headers={"X-VO-Management-Token": server._MANAGEMENT_TOKEN},
    ), "POST")
    assert revoke_status == 200 and revoked["grant"]["state"] == "revoked"
    assert grant_status(new_secret)[0] == 403


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
