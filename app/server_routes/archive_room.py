import urllib.parse

from .http import JsonBodyError, read_json, send_json


def _archive_service():
    from server_services import archive_room
    archive_room._hydrate()
    return archive_room


def _body(handler):
    try:
        return read_json(handler), None
    except JsonBodyError as e:
        return {}, {"ok": False, "error": str(e), "_status": 400}


def _project_id(path, suffix):
    return urllib.parse.unquote(path.split("/api/archive-room/projects/", 1)[1].rsplit(suffix, 1)[0].strip("/"))


def handle_get(handler, parsed_url):
    archive_service = _archive_service()
    path = parsed_url.path
    if path == "/api/archive-room":
        return send_json(handler, archive_service._handle_archive_room_overview())
    if path.startswith("/api/archive-room/projects/"):
        tail = path.split("/api/archive-room/projects/", 1)[1].strip("/")
        if tail.endswith("/context"):
            return send_json(handler, archive_service._handle_archive_room_context(_project_id(path, "/context"), parsed_url.query or ""))
        if "/" in tail:
            return send_json(handler, {"error": "Not found", "_status": 404})
        return send_json(handler, archive_service._handle_archive_room_project(urllib.parse.unquote(tail)))
    return False


def handle_post(handler, parsed_url):
    archive_service = _archive_service()
    path = parsed_url.path
    if path == "/api/archive-room/manager":
        body, error = _body(handler)
        return send_json(handler, error or archive_service._handle_archive_manager_update(body))
    if path == "/api/archive-room/audit-count":
        return send_json(handler, archive_service._handle_archive_room_audit_count())
    if path == "/api/archive-room/inspect/daily":
        body, error = _body(handler)
        return send_json(handler, error or archive_service._handle_archive_daily_inspection(body))
    if path == "/api/archive-room/important-message":
        body, error = _body(handler)
        return send_json(handler, error or archive_service._handle_archive_mark_important_message(body))
    if path.startswith("/api/archive-room/projects/") and path.endswith("/maintain"):
        return send_json(handler, archive_service._handle_archive_manager_manual_maintain(_project_id(path, "/maintain")))
    if path.startswith("/api/archive-room/projects/") and path.endswith("/ai-refine"):
        body, error = _body(handler)
        return send_json(handler, error or archive_service._handle_archive_manager_ai_refine(_project_id(path, "/ai-refine"), body))
    if path.startswith("/api/archive-room/projects/") and path.endswith("/maintenance"):
        body, error = _body(handler)
        return send_json(handler, error or archive_service._handle_archive_project_maintenance_update(_project_id(path, "/maintenance"), body))
    if path.startswith("/api/archive-room/projects/") and "/governance/" in path:
        body, error = _body(handler)
        tail = path.split("/api/archive-room/projects/", 1)[1].strip("/")
        proj_id, item_id = tail.split("/governance/", 1)
        result = error or archive_service._handle_archive_governance_action(
            urllib.parse.unquote(proj_id),
            urllib.parse.unquote(item_id.strip("/")),
            body,
        )
        return send_json(handler, result)
    return False


def handle_put(handler, parsed_url):
    return False


def handle_delete(handler, parsed_url):
    return False
