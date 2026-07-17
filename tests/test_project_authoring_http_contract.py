#!/usr/bin/env python3
"""End-to-end HTTP trust-boundary contracts for project authoring."""

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
from services.project_repository import ProjectRepository


AGENTS = {
    "author": {"id": "author"},
    "other-agent": {"id": "other-agent"},
    "owner": {"id": "owner"},
    "builder": {"id": "builder"},
}


class _Connection:
    def settimeout(self, timeout):
        self.timeout = timeout


def _draft(title):
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
    return handler.responses[-1], json.loads(handler.wfile.getvalue())


@pytest.fixture
def authoring(tmp_path, monkeypatch):
    markdown = MarkdownProjectStore(str(tmp_path))
    markdown.save_all({"projects": [], "templates": []})
    repository = ProjectRepository(
        load_projects=markdown.load_all,
        save_projects=markdown.save_all,
        cache_namespace=lambda: (markdown, markdown.revision()),
    )
    request_ids = iter(("request-1", "request-2", "request-3"))
    service = ProjectAuthoringService(
        ProjectAuthoringRootStore(repository),
        lookup_agent=AGENTS.get,
        is_excluded_agent=lambda agent_id: False,
        submission_enabled=lambda: True,
        new_id=lambda: next(request_ids),
    )
    monkeypatch.setattr(server, "_PROJECT_AUTHORING_SERVICE", service)
    return markdown, service


def _submit(title, key, *, agent="author", origin=""):
    headers = {
        "X-VO-Agent-Action": "project-authoring",
        "X-VO-Agent-Id": agent,
    }
    if origin:
        headers["Origin"] = origin
    return _call(_handler(
        "/api/agent/project-authoring/requests",
        {"idempotencyKey": key, "draft": _draft(title)},
        headers=headers,
    ), "POST")


def _status(request_id, secret, *, agent="author"):
    return _call(_handler(
        f"/api/agent/project-authoring/requests/{request_id}",
        headers={
            "X-VO-Agent-Action": "project-authoring",
            "X-VO-Agent-Id": agent,
            "Authorization": f"Bearer {secret}",
        },
    ), "GET")


def test_agent_submission_never_materializes_and_browser_origin_cannot_submit(authoring):
    markdown, _ = authoring

    status, created = _submit("First", "author:key-1")

    assert status == 200
    assert created["request"]["state"] == "pending"
    root = markdown.load_all()
    assert root["projects"] == []
    assert list(root[REQUESTS_KEY]) == ["request-1"]

    denied_status, denied = _submit(
        "Browser attempt", "author:key-browser",
        origin="http://localhost:3000",
    )
    assert denied_status == 403
    assert denied["code"] == "agent_authoring_browser_origin_rejected"
    assert list(markdown.load_all()[REQUESTS_KEY]) == ["request-1"]


def test_request_secret_cannot_cross_requests_or_agents(authoring):
    markdown, _ = authoring
    _, first = _submit("First", "author:key-1")
    _, second = _submit("Second", "author:key-2")
    first_secret = first["requestSecret"]
    second_secret = second["requestSecret"]

    assert _status("request-1", first_secret)[0] == 200
    assert _status("request-2", second_secret)[0] == 200
    cross_request_status, cross_request = _status("request-2", first_secret)
    assert cross_request_status == 403
    assert cross_request["code"] == "invalid_project_authoring_secret"
    assert _status("request-1", first_secret, agent="other-agent")[0] == 403

    status, payload = _status("request-1", first_secret)
    assert status == 200
    serialized = json.dumps(payload).lower()
    assert "requestsecret" not in serialized
    assert "secrethash" not in serialized
    assert markdown.load_all()["projects"] == []


def test_protected_routes_reject_invalid_management_token_before_body_or_mutation(authoring):
    markdown, _ = authoring
    _, created = _submit("Protected", "author:key-1")
    request_id = created["request"]["id"]
    confirm_path = f"/api/project-authoring/requests/{request_id}/confirm"
    before = markdown.load_all()

    for headers in (
        {},
        {"X-VO-Management-Token": "invalid"},
        {"Authorization": f"Bearer {created['requestSecret']}"},
    ):
        handler = _handler(
            confirm_path,
            body=None,
            headers=headers,
            content_length=server.OfficeHandler._MANAGEMENT_BODY_LIMIT + 1,
        )
        status, payload = _call(handler, "POST")
        assert status == 403
        assert payload["code"] == "management_token_required"

    after = markdown.load_all()
    assert after["projects"] == before["projects"] == []
    assert after[REQUESTS_KEY][request_id]["state"] == "pending"
    assert after[REQUESTS_KEY][request_id]["revision"] == 1


def test_management_detail_never_exposes_stored_request_hash(authoring):
    _, _ = authoring
    _, created = _submit("Visible", "author:key-1")
    handler = _handler(
        f"/api/project-authoring/requests/{created['request']['id']}",
        headers={"X-VO-Management-Token": server._MANAGEMENT_TOKEN},
    )

    status, payload = _call(handler, "GET")

    assert status == 200
    serialized = json.dumps(payload).lower()
    assert "requestsecrethash" not in serialized
    assert created["requestSecret"] not in serialized


def test_management_can_idempotently_instantiate_a_pinned_template_version(authoring):
    markdown, _ = authoring
    draft = _draft("Reusable HTTP")
    draft["projectType"] = "reusable"
    draft["template"] = {"mode": "create", "name": "Reusable HTTP template"}
    status, submitted = _call(_handler(
        "/api/agent/project-authoring/requests",
        {"idempotencyKey": "author:template-http", "draft": draft},
        headers={"X-VO-Agent-Action": "project-authoring", "X-VO-Agent-Id": "author"},
    ), "POST")
    assert status == 200
    confirmed_status, confirmed = _call(_handler(
        f"/api/project-authoring/requests/{submitted['request']['id']}/confirm",
        {"expectedRevision": 1, "confirmationKey": "confirm:template-http"},
        headers={"X-VO-Management-Token": server._MANAGEMENT_TOKEN},
    ), "POST")
    assert confirmed_status == 200
    template_id = confirmed["project"]["templateRef"]["id"]
    endpoint = f"/api/project-authoring/templates/{template_id}/instantiate"
    body = {
        "version": 1,
        "idempotencyKey": "template:http-instance-1",
        "overrides": {"title": "HTTP instance"},
    }

    denied_status, denied = _call(_handler(endpoint, body), "POST")
    assert denied_status == 403
    assert denied["code"] == "management_token_required"

    first_status, first = _call(_handler(
        endpoint, body, headers={"X-VO-Management-Token": server._MANAGEMENT_TOKEN},
    ), "POST")
    repeat_status, repeated = _call(_handler(
        endpoint,
        {**body, "overrides": {"title": "Ignored retry"}},
        headers={"X-VO-Management-Token": server._MANAGEMENT_TOKEN},
    ), "POST")

    assert first_status == repeat_status == 200
    assert first["created"] is True and repeated["created"] is False
    assert first["project"]["id"] == repeated["project"]["id"]
    assert first["project"]["title"] == "HTTP instance"
    assert first["project"]["templateRef"] == {"id": template_id, "version": 1}
    assert len(markdown.load_all()["projects"]) == 2


def test_project_grant_rotation_revocation_and_scope_are_enforced(authoring):
    markdown, _ = authoring
    _, created = _submit("Granted", "author:key-1")
    request_secret = created["requestSecret"]
    request_id = created["request"]["id"]
    confirm = _handler(
        f"/api/project-authoring/requests/{request_id}/confirm",
        {"expectedRevision": 1, "confirmationKey": "confirm:grant-1"},
        headers={"X-VO-Management-Token": server._MANAGEMENT_TOKEN},
    )
    confirm_status, confirmed = _call(confirm, "POST")
    assert confirm_status == 200
    project_id = confirmed["project"]["id"]

    def grant_status(secret, *, target=project_id, agent="author"):
        return _call(_handler(
            f"/api/agent/projects/{target}/grant-status",
            headers={
                "X-VO-Agent-Action": "project-authoring",
                "X-VO-Agent-Id": agent,
                "Authorization": f"Bearer {secret}",
            },
        ), "GET")

    status, grant_payload = grant_status(request_secret)
    assert status == 200
    assert grant_payload["grant"]["projectId"] == project_id
    assert "secrethash" not in json.dumps(grant_payload).lower()

    before_cross_scope = markdown.load_all()
    assert grant_status(request_secret, target="different-project")[0] == 403
    assert grant_status(request_secret, agent="other-agent")[0] == 403
    after_cross_scope = markdown.load_all()
    assert after_cross_scope["projects"] == before_cross_scope["projects"]
    assert after_cross_scope["projectAuthoringGrants"] == before_cross_scope["projectAuthoringGrants"]

    denied_revoke = _handler(
        f"/api/project-authoring/projects/{project_id}/grant/revoke",
        {},
        headers={"X-VO-Management-Token": "invalid"},
    )
    assert _call(denied_revoke, "POST")[0] == 403
    assert grant_status(request_secret)[0] == 200

    rotate = _handler(
        f"/api/project-authoring/projects/{project_id}/grant/rotate",
        {},
        headers={"X-VO-Management-Token": server._MANAGEMENT_TOKEN},
    )
    rotate_status, rotated = _call(rotate, "POST")
    assert rotate_status == 200
    new_secret = rotated["grantSecret"]
    assert new_secret != request_secret
    assert "secretHash" not in rotated["grant"]
    assert grant_status(request_secret)[0] == 403
    assert grant_status(new_secret)[0] == 200

    revoke = _handler(
        f"/api/project-authoring/projects/{project_id}/grant/revoke",
        {},
        headers={"X-VO-Management-Token": server._MANAGEMENT_TOKEN},
    )
    revoke_status, revoked = _call(revoke, "POST")
    assert revoke_status == 200
    assert revoked["grant"]["state"] == "revoked"
    assert grant_status(new_secret)[0] == 403


def test_agent_maintenance_request_needs_management_confirmation(authoring):
    markdown, _ = authoring
    _, created = _submit("Maintainable", "author:key-1")
    secret = created["requestSecret"]
    request_id = created["request"]["id"]
    confirm_status, confirmed = _call(_handler(
        f"/api/project-authoring/requests/{request_id}/confirm",
        {"expectedRevision": 1, "confirmationKey": "confirm:maintenance-http"},
        headers={"X-VO-Management-Token": server._MANAGEMENT_TOKEN},
    ), "POST")
    assert confirm_status == 200
    project_id = confirmed["project"]["id"]

    maintenance_status, maintenance = _call(_handler(
        f"/api/agent/projects/{project_id}/maintenance",
        {
            "idempotencyKey": "maintenance:http-1",
            "mutation": {"operation": "update_project", "changes": {"title": "Confirmed title"}},
        },
        headers={
            "X-VO-Agent-Action": "project-authoring",
            "X-VO-Agent-Id": "author",
            "Authorization": f"Bearer {secret}",
        },
    ), "POST")
    assert maintenance_status == 200
    maintenance_id = maintenance["request"]["id"]
    assert markdown.load_all()["projects"][0]["title"] == "Maintainable"

    management_path = f"/api/project-authoring/projects/{project_id}/maintenance/{maintenance_id}/confirm"
    assert _call(_handler(management_path, {"expectedRevision": 1}), "POST")[0] == 403
    assert markdown.load_all()["projects"][0]["title"] == "Maintainable"

    applied_status, applied = _call(_handler(
        management_path,
        {"expectedRevision": 1},
        headers={"X-VO-Management-Token": server._MANAGEMENT_TOKEN},
    ), "POST")
    assert applied_status == 200
    assert applied["project"]["title"] == "Confirmed title"
    assert markdown.load_all()["projects"][0]["title"] == "Confirmed title"


def test_agent_autonomous_routine_update_uses_same_scoped_maintenance_endpoint(authoring):
    markdown, _ = authoring
    draft = _draft("Autonomous HTTP")
    draft["agentMaintenanceMode"] = "autonomous"
    draft["tasks"][0]["executorActor"] = {"type": "agent", "id": "author"}
    headers = {"X-VO-Agent-Action": "project-authoring", "X-VO-Agent-Id": "author"}
    _, created = _call(_handler(
        "/api/agent/project-authoring/requests",
        {"idempotencyKey": "author:auto-http", "draft": draft},
        headers=headers,
    ), "POST")
    secret = created["requestSecret"]
    _, confirmed = _call(_handler(
        f"/api/project-authoring/requests/{created['request']['id']}/confirm",
        {"expectedRevision": 1, "confirmationKey": "confirm:auto-http"},
        headers={"X-VO-Management-Token": server._MANAGEMENT_TOKEN},
    ), "POST")
    project = confirmed["project"]

    status, updated = _call(_handler(
        f"/api/agent/projects/{project['id']}/maintenance",
        {
            "idempotencyKey": "routine:http-direct",
            "mutation": {
                "operation": "routine_task_update",
                "taskId": project["tasks"][0]["id"],
                "changes": {"description": "Direct autonomous HTTP update"},
            },
        },
        headers={**headers, "Authorization": f"Bearer {secret}"},
    ), "POST")

    assert status == 200
    assert updated["created"] is True
    assert markdown.load_all()["projects"][0]["tasks"][0]["description"] == "Direct autonomous HTTP update"
