import importlib.util
import io
import json
import os
import sys
import tempfile
import urllib.parse


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-routes-import-"))

import server  # noqa: E402

import server_routes  # noqa: E402


class FakeHeaders(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class FakeHandler:
    def __init__(self, path, body=None, method="GET"):
        self.path = path
        self.headers = FakeHeaders()
        raw = b""
        if body is not None:
            raw = json.dumps(body).encode("utf-8")
            self.headers["Content-Length"] = str(len(raw))
        self.rfile = io.BytesIO(raw)
        self.wfile = io.BytesIO()
        self.status = None
        self.response_headers = []
        self.method = method

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.response_headers.append((key, value))

    def end_headers(self):
        pass

    def guess_type(self, path):
        return "application/octet-stream"


FakeHandler.__module__ = "server"


def dispatch(method, path, body=None):
    handler = FakeHandler(path, body=body, method=method)
    handled = server_routes.dispatch(handler, method, urllib.parse.urlparse(path))
    assert handled is True
    payload = json.loads(handler.wfile.getvalue().decode("utf-8") or "{}")
    return handler.status, payload


def test_notifications_route_uses_config_handler(monkeypatch):
    monkeypatch.setattr(server, "_feishu_notification_config_response", lambda: {"ok": True, "feishuEnabled": True})
    status, payload = dispatch("GET", "/api/feishu-notification/config")
    assert status == 200
    assert payload["ok"] is True
    assert payload["feishuEnabled"] is True


def test_providers_route_uses_handler_context(monkeypatch):
    monkeypatch.setattr(server, "_handle_codex_test", lambda body=None: {"ok": True, "protocol": "codex"})
    status, payload = dispatch("POST", "/api/codex/test", {"enabled": True})
    assert status == 200
    assert payload == {"ok": True, "protocol": "codex"}


def test_meetings_route_preserves_history_shape(monkeypatch):
    monkeypatch.setattr(server, "_meeting_history_projection", lambda: [{"id": "m1"}])
    status, payload = dispatch("GET", "/api/meetings/history")
    assert status == 200
    assert payload == {"ok": True, "history": [{"id": "m1"}]}


def test_projects_task_delete_route_parses_task_id(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "_handle_task_delete", lambda project_id, task_id: calls.append((project_id, task_id)) or {"ok": True})
    status, payload = dispatch("DELETE", "/api/projects/p1/tasks/t1")
    assert status == 200
    assert payload == {"ok": True}
    assert calls == [("p1", "t1")]


def test_projects_put_route_uses_read_json(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "_handle_project_update", lambda project_id, body: calls.append((project_id, body)) or {"ok": True})
    status, payload = dispatch("PUT", "/api/projects/p1", {"title": "Updated"})
    assert status == 200
    assert payload == {"ok": True}
    assert calls == [("p1", {"title": "Updated"})]


def test_workflow_route_uses_workflow_service_compatibility(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "_handle_workflow_status", lambda project_id: calls.append(project_id) or {"ok": True, "phase": "idle"})
    status, payload = dispatch("GET", "/api/projects/p1/workflow/status")
    assert status == 200
    assert payload == {"ok": True, "phase": "idle"}
    assert calls == ["p1"]


def test_archive_room_route_uses_archive_service_compatibility(monkeypatch):
    monkeypatch.setattr(server, "_handle_archive_room_overview", lambda: {"ok": True, "projects": [{"id": "p1"}]})
    status, payload = dispatch("GET", "/api/archive-room")
    assert status == 200
    assert payload == {"ok": True, "projects": [{"id": "p1"}]}


def test_agent_bridge_route_uses_agent_bridge_service_compatibility(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "_handle_codex_chat", lambda body: calls.append(body) or {"ok": True, "reply": body["message"]})
    status, payload = dispatch("POST", "/api/codex/chat", {"message": "hello"})
    assert status == 200
    assert payload == {"ok": True, "reply": "hello"}
    assert calls == [{"message": "hello"}]


def test_agents_route_uses_agents_service_compatibility(monkeypatch):
    monkeypatch.setattr(server, "_handle_agents_list", lambda: {"agents": [{"id": "a1"}]})
    status, payload = dispatch("GET", "/api/agents")
    assert status == 200
    assert payload == {"agents": [{"id": "a1"}]}


def test_skills_route_uses_skills_service_compatibility(monkeypatch):
    monkeypatch.setattr(server, "_handle_skills_library_list", lambda: {"skills": [{"name": "s1"}]})
    status, payload = dispatch("GET", "/api/skills-library")
    assert status == 200
    assert payload == {"skills": [{"name": "s1"}]}


def test_config_route_uses_config_runtime_service_compatibility(monkeypatch):
    monkeypatch.setattr(server, "_handle_health", lambda: {"ok": True, "status": "patched"})
    status, payload = dispatch("GET", "/health")
    assert status == 200
    assert payload == {"ok": True, "status": "patched"}


def test_browser_route_uses_browser_runtime_service_compatibility(monkeypatch):
    monkeypatch.setattr(server, "_handle_browser_status", lambda: {"enabled": True, "cdpAvailable": False})
    status, payload = dispatch("GET", "/browser-status")
    assert status == 200
    assert payload == {"enabled": True, "cdpAvailable": False}
