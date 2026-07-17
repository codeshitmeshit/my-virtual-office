#!/usr/bin/env python3
"""Management-authenticated HTTP routes for project authoring review."""

import io
import json
import os
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")
os.environ["VO_STATUS_DIR"] = tempfile.mkdtemp(prefix="vo-project-authoring-management-http-")

import server


class _Connection:
    def settimeout(self, timeout):
        self.timeout = timeout


def _handler(path, body=None, *, authorized=True):
    payload = json.dumps(body).encode() if body is not None else b""
    handler = object.__new__(server.OfficeHandler)
    handler.path = path
    handler.headers = {"Content-Length": str(len(payload))}
    if authorized:
        handler.headers["X-VO-Management-Token"] = server._MANAGEMENT_TOKEN
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


class _FakeService:
    def __init__(self):
        self.calls = []

    def list_management(self, **kwargs):
        self.calls.append(("list", kwargs))
        return [{"id": "request-1", "state": "pending"}]

    def get_management(self, request_id):
        self.calls.append(("get", request_id))
        return {"id": request_id, "state": "pending"}

    def edit_pending(self, request_id, draft, **kwargs):
        self.calls.append(("edit", request_id, draft, kwargs))
        return {"id": request_id, "state": "pending", "revision": 2}

    def reject_pending(self, request_id, **kwargs):
        self.calls.append(("reject", request_id, kwargs))
        return {"id": request_id, "state": "rejected"}

    def confirm_and_materialize(self, request_id, **kwargs):
        self.calls.append(("confirm", request_id, kwargs))
        return {
            "ok": True,
            "project": {"id": "project-1"},
            "request": {"id": request_id, "state": "confirmed"},
        }


def test_authoring_health_requires_management_token_and_reports_safe_aggregates():
    denied = _handler("/api/project-authoring/health", authorized=False)
    assert _call(denied, "GET")[0] == 403

    health = _handler("/api/project-authoring/health")
    status, payload = _call(health, "GET")
    assert status == 200
    assert payload["status"] in {"disabled", "healthy", "paused", "degraded", "intervention_required"}
    assert set(payload["queues"]) == {
        "pendingRequests",
        "oldestPendingRequestAgeSeconds",
        "recurrenceOutbox",
        "oldestRecurrenceOutboxAgeSeconds",
    }
    encoded = json.dumps(payload)
    assert "requestSecretHash" not in encoded
    assert "claimToken" not in encoded


def test_management_list_and_detail_require_token(monkeypatch):
    fake = _FakeService()
    monkeypatch.setattr(server, "_PROJECT_AUTHORING_SERVICE", fake)

    denied = _handler("/api/project-authoring/requests", authorized=False)
    assert _call(denied, "GET")[0] == 403
    assert fake.calls == []

    listing = _handler("/api/project-authoring/requests?state=pending,failed&limit=10")
    status, payload = _call(listing, "GET")
    assert status == 200
    assert payload["requests"][0]["id"] == "request-1"
    assert fake.calls[-1] == ("list", {"states": {"pending", "failed"}, "limit": 10})

    detail = _handler("/api/project-authoring/requests/request-1")
    assert _call(detail, "GET") == (
        200,
        {"ok": True, "request": {"id": "request-1", "state": "pending"}},
    )


def test_management_edit_confirm_and_reject_are_authenticated_and_revisioned(monkeypatch):
    fake = _FakeService()
    monkeypatch.setattr(server, "_PROJECT_AUTHORING_SERVICE", fake)
    base = "/api/project-authoring/requests/request-1"

    denied = _handler(base, {"expectedRevision": 1, "draft": {}}, authorized=False)
    assert _call(denied, "PUT")[0] == 403
    assert fake.calls == []

    edited = _handler(base, {"expectedRevision": 1, "draft": {"title": "Edited"}})
    assert _call(edited, "PUT")[0] == 200
    assert fake.calls[-1][0] == "edit"
    assert fake.calls[-1][-1]["expected_revision"] == 1

    confirmed = _handler(base + "/confirm", {
        "expectedRevision": 2,
        "confirmationKey": "confirm:key-1",
    })
    status, payload = _call(confirmed, "POST")
    assert status == 200 and payload["project"]["id"] == "project-1"
    assert fake.calls[-1][0] == "confirm"
    assert fake.calls[-1][-1]["prepare_workspace"] is server._project_authoring_prepare_workspace
    assert fake.calls[-1][-1]["cleanup_workspace"] is server._project_authoring_cleanup_workspace

    rejected = _handler(base + "/reject", {
        "expectedRevision": 2,
        "reason": "No longer needed",
    })
    assert _call(rejected, "POST")[0] == 200
    assert fake.calls[-1][0] == "reject"


def test_management_mutations_reject_missing_revision_before_service(monkeypatch):
    fake = _FakeService()
    monkeypatch.setattr(server, "_PROJECT_AUTHORING_SERVICE", fake)
    base = "/api/project-authoring/requests/request-1"

    for method, path, body in (
        ("PUT", base, {"draft": {}}),
        ("POST", base + "/confirm", {"confirmationKey": "confirm:key-1"}),
        ("POST", base + "/reject", {"reason": "No"}),
    ):
        handler = _handler(path, body)
        status, payload = _call(handler, method)
        assert status == 400
        assert payload["code"] == "expected_revision_required"
    assert fake.calls == []
