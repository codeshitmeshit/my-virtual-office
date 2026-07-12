#!/usr/bin/env python3
"""Contract coverage for the project execution service-boundary pilot."""

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
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-service-boundary-import-"))

import server
from services import project_execution


def _project(workspace="/stored/workspace"):
    return {
        "id": "project-1",
        "title": "Boundary pilot",
        "workspacePath": workspace,
        "workspaceKind": None,
        "workspaceStatus": {},
        "projectExecutionEnabled": False,
        "updatedAt": "before",
    }


def _handler_for_post(payload, content_length=None):
    class _Connection:
        def settimeout(self, timeout):
            self.timeout = timeout

    handler = object.__new__(server.OfficeHandler)
    handler.path = "/api/projects/project-1/project-execution/workspace/validate"
    handler.headers = {"Content-Length": str(len(payload) if content_length is None else content_length)}
    handler.rfile = io.BytesIO(payload)
    handler.wfile = io.BytesIO()
    handler.connection = _Connection()
    handler.responses = []
    handler.response_headers = []
    handler.send_response = lambda status, *args, **kwargs: handler.responses.append(status)
    handler.send_header = lambda name, value: handler.response_headers.append((name, value))
    handler.end_headers = lambda: None
    return handler


def _authorize(handler):
    handler.headers["X-VO-Management-Token"] = server._MANAGEMENT_TOKEN
    return handler


def test_bounded_json_reader_accepts_object_and_rejects_malformed_scalar_and_large_body():
    valid = _handler_for_post(b'{"workspacePath":"/tmp"}')
    assert valid._read_limited_json_body(limit=1024) == ({"workspacePath": "/tmp"}, None)

    malformed = _handler_for_post(b"{")
    body, error = malformed._read_limited_json_body(limit=1024)
    assert body is None
    assert error["_status"] == 400

    scalar = _handler_for_post(b"[]")
    assert scalar._read_limited_json_body(limit=1024) == (
        None,
        {"ok": False, "error": "JSON body must be an object", "_status": 400},
    )

    oversized = _handler_for_post(b"{}", content_length=1025)
    assert oversized._read_limited_json_body(limit=1024) == (
        None,
        {"ok": False, "error": "Request body is too large", "_status": 413},
    )


def test_bounded_json_reader_returns_408_when_body_ends_early():
    handler = _handler_for_post(b"{}", content_length=10)
    body, error = handler._read_limited_json_body(limit=1024)
    assert body is None
    assert error["_status"] == 408


def test_shared_json_response_sets_length_request_id_and_security_header():
    handler = _handler_for_post(b"")

    handler._send_json({"ok": True, "message": "你好"}, allow_origin="*")

    raw = handler.wfile.getvalue()
    headers = dict(handler.response_headers)
    assert handler.responses == [200]
    assert json.loads(raw) == {"ok": True, "message": "你好"}
    assert headers["Content-Type"] == "application/json"
    assert headers["Content-Length"] == str(len(raw))
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert len(headers["X-Request-Id"]) == 32
    assert headers["Access-Control-Allow-Origin"] == "*"


def test_management_rejection_uses_shared_json_response(monkeypatch):
    handler = _handler_for_post(b"")
    monkeypatch.setattr(handler, "_management_request_allowed", lambda: False)

    assert handler._reject_untrusted_management_request() is True
    assert handler.responses == [403]
    assert json.loads(handler.wfile.getvalue()) == {
        "ok": False,
        "error": "A valid Virtual Office management token is required",
    }
    assert dict(handler.response_headers)["X-Content-Type-Options"] == "nosniff"


def test_project_put_requires_management_token_before_parsing_or_mutation(monkeypatch):
    handler = _handler_for_post(b'{"title":"changed"}')
    handler.path = "/api/projects/project-1"
    called = []
    monkeypatch.setattr(server, "_handle_project_update", lambda *args: called.append(args) or {"ok": True})

    handler.do_PUT()

    assert handler.responses == [403]
    assert called == []


def test_project_put_accepts_management_token_and_bounded_object_json(monkeypatch):
    handler = _handler_for_post(b'{"title":"changed"}')
    handler.path = "/api/projects/project-1"
    handler.headers["X-VO-Management-Token"] = server._MANAGEMENT_TOKEN
    called = []
    monkeypatch.setattr(server, "_handle_project_update", lambda *args: called.append(args) or {"ok": True})

    handler.do_PUT()

    assert handler.responses == [200]
    assert called == [("project-1", {"title": "changed"})]


def test_project_post_requires_management_token_before_parsing_or_mutation(monkeypatch):
    handler = _handler_for_post(b'{"title":"new"}')
    handler.path = "/api/projects"
    called = []
    monkeypatch.setattr(server, "_handle_project_create", lambda body: called.append(body) or {"ok": True})

    handler.do_POST()

    assert handler.responses == [403]
    assert called == []


def test_project_frontend_routes_mutations_through_management_fetch():
    with open(os.path.join(APP_DIR, "projects.js"), encoding="utf-8") as source_file:
        source = source_file.read()
    mutation_lines = [
        line for line in source.splitlines()
        if "api/projects" in line and "method: 'POST'" in line
    ]
    assert mutation_lines
    assert all("projectMutationFetch(" in line for line in mutation_lines)
    assert "window.i18n.managementFetch(input, init)" in source
    with open(os.path.join(APP_DIR, "i18n.js"), encoding="utf-8") as source_file:
        i18n_source = source_file.read()
    assert "window.i18n =" in i18n_source
    assert "managementFetch: managementFetch" in i18n_source


def test_execution_agent_meeting_request_remains_reachable_without_browser_token(monkeypatch):
    handler = _handler_for_post(b'{"question":"Need a decision"}')
    handler.path = "/api/projects/project-1/tasks/task-1/meeting-requests"
    called = []
    monkeypatch.setattr(
        server,
        "_handle_meeting_request_create",
        lambda project_id, task_id, body: called.append((project_id, task_id, body)) or {"ok": True},
    )

    handler.do_POST()

    assert handler.responses == [200]
    assert called == [("project-1", "task-1", {"question": "Need a decision"})]


def _service_dependencies(project=None, validation=None):
    data = {"projects": [project] if project else []}
    saved = []
    validated = []

    def validate(path):
        validated.append(path)
        if isinstance(validation, BaseException):
            raise validation
        return validation or {"ok": True, "path": path, "kind": "directory"}

    return data, saved, validated, {
        "load_projects": lambda: data,
        "save_projects": lambda value: saved.append(value),
        "validate_workspace_path": validate,
        "now": lambda: "after",
    }


def test_workspace_service_success_is_http_independent():
    project = _project()
    data, saved, validated, dependencies = _service_dependencies(project)

    result = project_execution.validate_workspace("project-1", {}, **dependencies)

    assert result == project_execution.ServiceResult(
        status=200,
        payload={"ok": True, "workspace": {"ok": True, "path": "/stored/workspace", "kind": "directory"}},
    )
    assert validated == ["/stored/workspace"]
    assert saved == [data]
    assert project["workspacePath"] == "/stored/workspace"
    assert project["workspaceKind"] == "directory"
    assert project["updatedAt"] == "after"


def test_workspace_service_submitted_path_takes_precedence():
    project = _project()
    _, saved, validated, dependencies = _service_dependencies(project)

    result = project_execution.validate_workspace(
        "project-1", {"workspacePath": "/submitted/workspace"}, **dependencies
    )

    assert result.status == 200
    assert validated == ["/submitted/workspace"]
    assert len(saved) == 1


def test_workspace_service_missing_project_does_not_validate_or_save():
    _, saved, validated, dependencies = _service_dependencies()

    result = project_execution.validate_workspace("missing", {}, **dependencies)

    assert result == project_execution.ServiceResult(status=404, payload={"error": "Project not found"})
    assert validated == []
    assert saved == []


def test_workspace_service_invalid_workspace_persists_failure_once():
    project = _project()
    failure = {"ok": False, "error": "denied", "code": "workspace_not_allowed"}
    data, saved, _, dependencies = _service_dependencies(project, failure)

    result = project_execution.validate_workspace(
        "project-1", {"workspacePath": "/denied"}, **dependencies
    )

    assert result == project_execution.ServiceResult(status=400, payload=failure)
    assert saved == [data]
    assert project["workspaceStatus"] is failure
    assert project["workspacePath"] == "/denied"


def test_workspace_service_propagates_validator_and_persistence_failures():
    project = _project()
    _, _, _, validator_dependencies = _service_dependencies(project, RuntimeError("validator failed"))
    with pytest.raises(RuntimeError, match="validator failed"):
        project_execution.validate_workspace("project-1", {}, **validator_dependencies)

    _, _, _, persistence_dependencies = _service_dependencies(_project())
    persistence_dependencies["save_projects"] = lambda value: (_ for _ in ()).throw(RuntimeError("save failed"))
    with pytest.raises(RuntimeError, match="save failed"):
        project_execution.validate_workspace("project-1", {}, **persistence_dependencies)


def test_project_execution_service_has_no_server_or_http_dependency():
    source_path = os.path.join(APP_DIR, "services", "project_execution.py")
    with open(source_path, encoding="utf-8") as source_file:
        source = source_file.read()
    assert "import server" not in source
    assert "OfficeHandler" not in source
    assert "http.server" not in source


def test_legacy_workspace_validate_http_route_returns_handler_payload(monkeypatch):
    handler = _authorize(_handler_for_post(json.dumps({"workspacePath": "/submitted"}).encode()))
    called = []
    monkeypatch.setattr(server, "_load_projects", lambda: {"projects": [{"id": "project-1", "workspacePath": "/stored"}]})
    monkeypatch.setattr(server, "_save_projects", lambda value: None)
    monkeypatch.setattr(
        server,
        "_project_execution_validate_workspace",
        lambda path: called.append(("project-1", {"workspacePath": path})) or {"ok": True, "path": path, "kind": "directory"},
    )
    monkeypatch.setattr(server, "_proj_now", lambda: "after")

    handler.do_POST()

    assert called == [("project-1", {"workspacePath": "/submitted"})]
    assert handler.responses == [200]
    assert json.loads(handler.wfile.getvalue()) == {
        "ok": True,
        "workspace": {"ok": True, "path": "/submitted", "kind": "directory"},
    }
    assert ("Access-Control-Allow-Origin", "*") in handler.response_headers
    assert dict(handler.response_headers)["X-Content-Type-Options"] == "nosniff"


def test_workspace_validate_http_route_rejects_malformed_json_before_service(monkeypatch):
    handler = _authorize(_handler_for_post(b"{"))
    called = []
    monkeypatch.setattr(server.project_execution_service, "validate_workspace", lambda *args, **kwargs: called.append(args))

    handler.do_POST()

    assert called == []
    assert handler.responses == [400]
    assert json.loads(handler.wfile.getvalue())["ok"] is False


def test_workspace_validate_http_route_rejects_scalar_json_before_service(monkeypatch):
    handler = _authorize(_handler_for_post(b"[]"))
    called = []
    monkeypatch.setattr(server.project_execution_service, "validate_workspace", lambda *args, **kwargs: called.append(args))

    handler.do_POST()

    assert called == []
    assert handler.responses == [400]
    assert json.loads(handler.wfile.getvalue())["error"] == "JSON body must be an object"


def test_workspace_validate_http_route_rejects_body_above_limit(monkeypatch):
    body = {"workspacePath": "/submitted", "padding": "x" * (65 * 1024)}
    payload = json.dumps(body).encode()
    handler = _authorize(_handler_for_post(payload))
    called = []
    monkeypatch.setattr(server.project_execution_service, "validate_workspace", lambda *args, **kwargs: called.append(args))

    handler.do_POST()

    assert called == []
    assert handler.responses == [413]


def test_workspace_validate_http_route_sanitizes_unexpected_service_failure(monkeypatch, capsys):
    handler = _authorize(_handler_for_post(b"{}"))
    monkeypatch.setattr(
        server.project_execution_service,
        "validate_workspace",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("token=super-secret /private/path")),
    )

    handler.do_POST()

    response = json.loads(handler.wfile.getvalue())
    assert handler.responses == [500]
    assert response["error"] == "Internal server error"
    assert response["requestId"] == dict(handler.response_headers)["X-Request-Id"]
    captured = capsys.readouterr()
    assert "super-secret" not in captured.err
