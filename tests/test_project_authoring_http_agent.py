#!/usr/bin/env python3
"""Agent HTTP boundary for conversation-confirmed direct project creation."""

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
os.environ["VO_STATUS_DIR"] = tempfile.mkdtemp(prefix="vo-project-authoring-http-")

import server


class _Connection:
    def settimeout(self, timeout):
        self.timeout = timeout


def _handler(path, body=None, *, headers=None, remote="127.0.0.1", content_length=None):
    payload = json.dumps(body).encode() if body is not None else b""
    handler = object.__new__(server.OfficeHandler)
    handler.path = path
    handler.client_address = (remote, 12345)
    handler.headers = {
        "Content-Length": str(len(payload) if content_length is None else content_length),
        "X-VO-Agent-Action": "project-authoring",
        "X-VO-Agent-Id": "author",
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


def _response(handler):
    raw = handler.wfile.getvalue()
    return handler.responses[-1], json.loads(raw) if raw else {}


class _FakeService:
    def __init__(self):
        self.creations = []

    def create_confirmed_project(self, project, **kwargs):
        self.creations.append((project, kwargs))
        return {
            "ok": True,
            "created": True,
            "project": {"id": "project-1"},
            "projectGrantSecret": "one-time-secret",
        }


def _body():
    return {
        "idempotencyKey": "author:direct-1",
        "confirmation": {"confirmed": True, "summaryDigest": "a" * 64},
        "project": {"title": "Direct project"},
    }


def test_agent_direct_creation_is_loopback_only_originless_and_bounded(monkeypatch):
    fake = _FakeService()
    monkeypatch.setattr(server, "_PROJECT_AUTHORING_SERVICE", fake)
    handler = _handler("/api/agent/project-authoring/projects", _body())

    handler.do_POST()

    status, payload = _response(handler)
    assert status == 200
    assert payload["project"]["id"] == "project-1"
    assert payload["projectGrantSecret"] == "one-time-secret"
    assert len(fake.creations) == 1
    project, kwargs = fake.creations[0]
    assert project == {"title": "Direct project"}
    assert kwargs["requesting_agent_id"] == "author"
    assert kwargs["idempotency_key"] == "author:direct-1"
    assert kwargs["confirmation"]["summaryDigest"] == "a" * 64
    assert kwargs["prepare_workspace"] is server._project_authoring_prepare_workspace
    assert kwargs["cleanup_workspace"] is server._project_authoring_cleanup_workspace

    for denied in (
        _handler(handler.path, _body(), remote="10.0.0.9"),
        _handler(handler.path, _body(), headers={"Origin": "http://localhost:3000"}),
        _handler(handler.path, _body(), headers={"X-VO-Agent-Action": "wrong"}),
    ):
        denied.do_POST()
        assert _response(denied)[0] in {400, 403}
    assert len(fake.creations) == 1

    oversized = _handler(
        handler.path,
        _body(),
        content_length=server.project_authoring_config_service.DEFAULT_CONFIG.body_limit_bytes + 1,
    )
    oversized.do_POST()
    assert _response(oversized)[0] == 413
    assert len(fake.creations) == 1


def test_agent_id_mismatch_is_rejected_before_direct_creation(monkeypatch):
    fake = _FakeService()
    monkeypatch.setattr(server, "_PROJECT_AUTHORING_SERVICE", fake)
    handler = _handler(
        "/api/agent/project-authoring/projects",
        {**_body(), "requestingAgentId": "different"},
    )

    handler.do_POST()

    assert _response(handler)[0] == 403
    assert fake.creations == []


def test_legacy_agent_draft_submission_and_status_routes_are_inactive(monkeypatch):
    fake = _FakeService()
    monkeypatch.setattr(server, "_PROJECT_AUTHORING_SERVICE", fake)

    submission = _handler("/api/agent/project-authoring/requests", _body())
    submission.do_POST()
    status = _handler("/api/agent/project-authoring/requests/request-1")
    status.do_GET()

    assert _response(submission)[0] == 404
    assert _response(status)[0] == 404
    assert fake.creations == []
