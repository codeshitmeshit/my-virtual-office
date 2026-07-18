#!/usr/bin/env python3
"""Management HTTP boundaries retained after draft-flow removal."""

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
    raw = handler.wfile.getvalue()
    return handler.responses[-1], json.loads(raw) if raw else {}


def test_authoring_health_requires_management_token_and_reports_safe_aggregates():
    denied = _handler("/api/project-authoring/health", authorized=False)
    assert _call(denied, "GET")[0] == 403

    health = _handler("/api/project-authoring/health")
    status, payload = _call(health, "GET")
    assert status == 200
    assert payload["status"] in {"disabled", "healthy", "paused", "degraded", "intervention_required"}
    encoded = json.dumps(payload)
    assert "requestSecretHash" not in encoded
    assert "claimToken" not in encoded


def test_legacy_management_draft_routes_are_inactive():
    base = "/api/project-authoring/requests/request-1"
    for method, path, body in (
        ("GET", "/api/project-authoring/requests", None),
        ("GET", base, None),
        ("PUT", base, {"expectedRevision": 1, "draft": {}}),
        ("POST", base + "/confirm", {"expectedRevision": 1}),
        ("POST", base + "/reject", {"expectedRevision": 1, "reason": "No"}),
    ):
        assert _call(_handler(path, body), method)[0] == 404


def test_existing_project_mutations_still_require_management_token():
    denied = _handler("/api/projects", {"title": "No token"}, authorized=False)
    status, payload = _call(denied, "POST")
    assert status == 403
    assert payload["code"] == "management_token_required"
