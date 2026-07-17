#!/usr/bin/env python3
"""Agent HTTP boundary for project draft submission and status."""

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
    return handler.responses[-1], json.loads(handler.wfile.getvalue())


class _FakeService:
    def __init__(self):
        self.submissions = []
        self.status_calls = []

    def create_pending(self, draft, **kwargs):
        self.submissions.append((draft, kwargs))
        return {"ok": True, "created": True, "request": {"id": "request-1", "state": "pending"}}

    def authenticate_agent_status(self, request_id, **kwargs):
        self.status_calls.append((request_id, kwargs))
        return {"id": request_id, "state": "pending"}


def test_agent_submission_is_loopback_only_originless_bounded_and_hash_only(monkeypatch):
    fake = _FakeService()
    monkeypatch.setattr(server, "_PROJECT_AUTHORING_SERVICE", fake)
    handler = _handler(
        "/api/agent/project-authoring/requests",
        {"idempotencyKey": "author:key-1", "draft": {"title": "Draft"}},
    )

    handler.do_POST()

    status, payload = _response(handler)
    assert status == 200
    assert payload["created"] is True
    assert payload["requestSecret"]
    assert len(fake.submissions) == 1
    _, kwargs = fake.submissions[0]
    assert kwargs["requesting_agent_id"] == "author"
    assert kwargs["request_secret_hash"].startswith("sha256:")
    assert payload["requestSecret"] not in kwargs["request_secret_hash"]

    for denied in (
        _handler(handler.path, {}, remote="10.0.0.9"),
        _handler(handler.path, {}, headers={"Origin": "http://localhost:3000"}),
        _handler(handler.path, {}, headers={"X-VO-Agent-Action": "wrong"}),
    ):
        denied.do_POST()
        assert _response(denied)[0] in {400, 403}
    assert len(fake.submissions) == 1

    oversized = _handler(
        handler.path, {},
        content_length=server.project_authoring_config_service.DEFAULT_CONFIG.body_limit_bytes + 1,
    )
    oversized.do_POST()
    assert _response(oversized)[0] == 413
    assert len(fake.submissions) == 1


def test_agent_id_mismatch_is_rejected_before_service(monkeypatch):
    fake = _FakeService()
    monkeypatch.setattr(server, "_PROJECT_AUTHORING_SERVICE", fake)
    handler = _handler(
        "/api/agent/project-authoring/requests",
        {"requestingAgentId": "different", "idempotencyKey": "author:key-1", "draft": {}},
    )

    handler.do_POST()

    assert _response(handler)[0] == 403
    assert fake.submissions == []


def test_agent_status_requires_same_agent_bearer_secret_and_exposes_no_hash(monkeypatch):
    fake = _FakeService()
    monkeypatch.setattr(server, "_PROJECT_AUTHORING_SERVICE", fake)
    path = "/api/agent/project-authoring/requests/request-1"
    handler = _handler(path, headers={"Authorization": "Bearer opaque-secret"})

    handler.do_GET()

    status, payload = _response(handler)
    assert status == 200
    assert payload == {"ok": True, "request": {"id": "request-1", "state": "pending"}}
    assert fake.status_calls == [("request-1", {
        "requesting_agent_id": "author",
        "request_secret": "opaque-secret",
    })]
    assert "hash" not in json.dumps(payload).lower()

    missing = _handler(path)
    missing.do_GET()
    assert _response(missing)[0] == 403
    assert len(fake.status_calls) == 1
