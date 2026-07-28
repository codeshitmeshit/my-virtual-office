from .http import JsonBodyError, query_dict, read_json, send_json


def _workflow_service():
    from server_services import workflow
    workflow._hydrate()
    return workflow


def _body(handler):
    try:
        return read_json(handler), None
    except JsonBodyError as e:
        return {}, {"ok": False, "error": str(e), "_status": 400}


def _project_id(path, suffix):
    return path.split("/api/projects/", 1)[1].rsplit(suffix, 1)[0]


def handle_get(handler, parsed_url):
    workflow_service = _workflow_service()
    path = parsed_url.path
    if path.startswith("/api/projects/") and path.endswith("/workflow/chat"):
        query = query_dict(parsed_url)
        task_scope = (query.get("taskId") or query.get("taskScope") or [""])[0]
        return send_json(
            handler,
            workflow_service._handle_workflow_chat(
                _project_id(path, "/workflow/chat"),
                task_scope=task_scope,
            ),
        )
    if path.startswith("/api/projects/") and path.endswith("/workflow/status"):
        return send_json(handler, workflow_service._handle_workflow_status(_project_id(path, "/workflow/status")))
    return False


def handle_post(handler, parsed_url):
    workflow_service = _workflow_service()
    path = parsed_url.path
    if path.startswith("/api/projects/") and path.endswith("/workflow/start"):
        body, error = _body(handler)
        return send_json(handler, error or workflow_service._handle_workflow_start(_project_id(path, "/workflow/start"), body))
    if path.startswith("/api/projects/") and path.endswith("/workflow/stop"):
        return send_json(handler, workflow_service._handle_workflow_stop(_project_id(path, "/workflow/stop")), status=200)
    return False


def handle_put(handler, parsed_url):
    workflow_service = _workflow_service()
    path = parsed_url.path
    if path.startswith("/api/projects/") and path.endswith("/workflow/auto-mode"):
        body, error = _body(handler)
        return send_json(handler, error or workflow_service._handle_workflow_auto_mode(_project_id(path, "/workflow/auto-mode"), body))
    return False


def handle_delete(handler, parsed_url):
    return False
