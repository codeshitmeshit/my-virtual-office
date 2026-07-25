import os
import shutil
import urllib.parse

from .http import JsonBodyError, read_json, send_json


def _projects_service():
    from server_services import projects
    projects._hydrate()
    return projects


def _meetings_service():
    from server_services import meetings
    meetings._hydrate()
    return meetings


def _body(handler):
    try:
        return read_json(handler), None
    except JsonBodyError as e:
        return {}, {"ok": False, "error": str(e), "_status": 400}


def _project_task_ids(path, suffix):
    rest = path.split("/api/projects/", 1)[1]
    proj_id, task_rest = rest.split("/tasks/", 1)
    task_id = task_rest.rsplit(suffix, 1)[0]
    return proj_id, task_id


def handle_get(handler, parsed_url):
    projects_service = _projects_service()
    meetings_service = _meetings_service()
    path = parsed_url.path
    query = parsed_url.query or ""
    if path == "/api/projects":
        return send_json(handler, projects_service._handle_projects_list(query), status=200)
    if path == "/api/projects/scores":
        return send_json(handler, projects_service._handle_scores_leaderboard(), status=200)
    if path == "/api/projects/templates":
        return send_json(handler, projects_service._handle_projects_templates(), status=200)
    if path == "/api/projects/scheduled-cron":
        return send_json(handler, projects_service._handle_project_scheduled_cron_all())
    if path.startswith("/api/projects/") and path.endswith("/scheduled-cron"):
        proj_id = path.split("/api/projects/", 1)[1].rsplit("/scheduled-cron", 1)[0]
        return send_json(handler, projects_service._handle_project_scheduled_cron_list(proj_id))
    if path.startswith("/api/projects/") and path.endswith("/artifacts/read"):
        proj_id = path.split("/api/projects/", 1)[1].rsplit("/artifacts/read", 1)[0]
        return send_json(handler, projects_service._handle_project_artifact_read(proj_id, query))
    if path.startswith("/api/projects/") and path.endswith("/artifacts/file"):
        proj_id = path.split("/api/projects/", 1)[1].rsplit("/artifacts/file", 1)[0]
        result = projects_service._handle_project_artifact_file(proj_id, query)
        if not result.get("ok"):
            return send_json(handler, result)
        file_path = result.get("path")
        try:
            size = os.path.getsize(file_path)
            handler.send_response(200)
            handler.send_header("Content-Type", handler.guess_type(file_path))
            handler.send_header("Content-Length", str(size))
            handler.send_header("Access-Control-Allow-Origin", "*")
            handler.send_header("Content-Disposition", f"inline; filename={projects_service.json.dumps(os.path.basename(file_path))}")
            handler.end_headers()
            with open(file_path, "rb") as f:
                shutil.copyfileobj(f, handler.wfile)
        except OSError:
            send_json(handler, {"error": "Artifact not found"}, status=404)
        return True
    if path.startswith("/api/projects/") and path.endswith("/artifacts"):
        proj_id = path.split("/api/projects/", 1)[1].rsplit("/artifacts", 1)[0]
        return send_json(handler, projects_service._handle_project_artifacts_list(proj_id))
    if path.startswith("/api/projects/") and "/tasks/" not in path and path.endswith("/project-execution/status"):
        proj_id = path.split("/api/projects/", 1)[1].rsplit("/project-execution/status", 1)[0]
        return send_json(handler, projects_service._handle_project_execution_status(proj_id))
    if path.startswith("/api/projects/") and "/tasks/" in path and path.endswith("/project-execution/status"):
        proj_id, task_id = _project_task_ids(path, "/project-execution/status")
        return send_json(handler, projects_service._handle_project_execution_status(proj_id, task_id))
    if path.startswith("/api/projects/") and "/tasks/" in path and path.endswith("/meeting-requests"):
        proj_id, task_id = _project_task_ids(path, "/meeting-requests")
        q = f"projectId={urllib.parse.quote(proj_id)}&taskId={urllib.parse.quote(task_id)}"
        return send_json(handler, meetings_service._meeting_request_list_filtered(q))
    if path.startswith("/api/projects/") and path.endswith("/report"):
        proj_id = path.split("/api/projects/", 1)[1].rsplit("/report", 1)[0]
        return send_json(handler, projects_service._handle_project_report(proj_id))
    if path.startswith("/api/projects/") and "/tasks" not in path and "/report" not in path and "/workflow" not in path:
        proj_id = path.split("/api/projects/", 1)[1].strip("/")
        if proj_id and proj_id != "templates":
            return send_json(handler, projects_service._handle_project_get(proj_id))
    return False


def handle_post(handler, parsed_url):
    projects_service = _projects_service()
    meetings_service = _meetings_service()
    path = parsed_url.path
    if path == "/api/projects":
        body, error = _body(handler)
        return send_json(handler, error or projects_service._handle_project_create(body))
    if path == "/api/projects/scores/award":
        body, error = _body(handler)
        return send_json(handler, error or projects_service._handle_score_award(body))
    if path == "/api/projects/from-template":
        body, error = _body(handler)
        return send_json(handler, error or projects_service._handle_project_from_template(body))
    if path == "/api/projects/templates":
        body, error = _body(handler)
        return send_json(handler, error or projects_service._handle_save_as_template(body))
    project_body_suffixes = {
        "/project-execution/workspace/validate": projects_service._handle_project_execution_workspace_validate,
        "/project-execution/start": projects_service._handle_project_execution_project_start,
        "/scheduled-cron": projects_service._handle_project_scheduled_cron_create,
    }
    for suffix, fn in project_body_suffixes.items():
        if path.startswith("/api/projects/") and "/tasks/" not in path and path.endswith(suffix):
            proj_id = path.split("/api/projects/", 1)[1].rsplit(suffix, 1)[0]
            body, error = _body(handler)
            return send_json(handler, error or fn(proj_id, body))
    task_suffixes = {
        "/project-execution/start": projects_service._handle_project_execution_start,
        "/project-execution/cancel": projects_service._handle_project_execution_cancel,
        "/project-execution/review/start": projects_service._handle_project_execution_review_start,
        "/project-execution/accept": projects_service._handle_project_execution_acceptance,
        "/project-execution/meeting-blocker": projects_service._handle_project_execution_meeting_blocker_action,
        "/meeting-requests": meetings_service._handle_meeting_request_create,
    }
    for suffix, fn in task_suffixes.items():
        if path.startswith("/api/projects/") and "/tasks/" in path and path.endswith(suffix):
            proj_id, task_id = _project_task_ids(path, suffix)
            body, error = _body(handler)
            return send_json(handler, error or fn(proj_id, task_id, body))
    if path.startswith("/api/projects/") and path.endswith("/run") and "/scheduled-cron/" in path:
        rest = path.split("/api/projects/", 1)[1]
        proj_id, cron_rest = rest.split("/scheduled-cron/", 1)
        cron_id = cron_rest.rsplit("/run", 1)[0].strip("/")
        return send_json(handler, projects_service._handle_project_scheduled_cron_run(proj_id, cron_id))
    if path.startswith("/api/projects/") and "/tasks" in path and "/comments" in path:
        rest = path.split("/api/projects/", 1)[1]
        proj_id, task_rest = rest.split("/tasks/", 1)
        task_id = task_rest.split("/comments", 1)[0].strip("/")
        body, error = _body(handler)
        return send_json(handler, error or projects_service._handle_task_comment(proj_id, task_id, body))
    if path.startswith("/api/projects/") and path.endswith("/tasks"):
        proj_id = path.split("/api/projects/", 1)[1].rsplit("/tasks", 1)[0]
        body, error = _body(handler)
        return send_json(handler, error or projects_service._handle_task_create(proj_id, body))
    return False


def handle_put(handler, parsed_url):
    projects_service = _projects_service()
    path = parsed_url.path
    if not path.startswith("/api/projects/"):
        return False
    body, error = _body(handler)
    if error:
        return send_json(handler, error)
    if "/tasks/" in path and path.endswith("/review-check"):
        proj_id, task_id = _project_task_ids(path, "/review-check")
        return send_json(handler, projects_service._handle_review_check_update(proj_id, task_id, body))
    if "/scheduled-cron/" in path:
        rest = path.split("/api/projects/", 1)[1]
        proj_id, cron_rest = rest.split("/scheduled-cron/", 1)
        return send_json(handler, projects_service._handle_project_scheduled_cron_update(proj_id, cron_rest.strip("/"), body))
    parts = path.split("/api/projects/", 1)[1].strip("/").split("/")
    proj_id = parts[0]
    if len(parts) == 1:
        result = projects_service._handle_project_update(proj_id, body)
    elif len(parts) == 2 and parts[1] == "columns":
        result = projects_service._handle_columns_update(proj_id, body)
    elif len(parts) == 3 and parts[1] == "tasks" and parts[2] == "reorder":
        result = projects_service._handle_tasks_reorder(proj_id, body)
    elif len(parts) == 3 and parts[1] == "tasks":
        result = projects_service._handle_task_update(proj_id, parts[2], body)
    else:
        result = {"error": "Not found", "_status": 404}
    return send_json(handler, result)


def handle_delete(handler, parsed_url):
    projects_service = _projects_service()
    path = parsed_url.path
    if path.startswith("/api/projects/templates/"):
        return send_json(handler, projects_service._handle_template_delete(path.split("/api/projects/templates/", 1)[1].strip("/")))
    if not path.startswith("/api/projects/"):
        return False
    if "/tasks/" in path:
        rest = path.split("/api/projects/", 1)[1]
        proj_id, task_rest = rest.split("/tasks/", 1)
        task_id = task_rest.strip("/")
        return send_json(handler, projects_service._handle_task_delete(proj_id, task_id.strip("/")))
    if "/scheduled-cron/" in path:
        rest = path.split("/api/projects/", 1)[1]
        proj_id, cron_rest = rest.split("/scheduled-cron/", 1)
        return send_json(handler, projects_service._handle_project_scheduled_cron_delete(proj_id, cron_rest.strip("/")))
    if path.endswith("/artifacts"):
        proj_id = path.split("/api/projects/", 1)[1].rsplit("/artifacts", 1)[0]
        return send_json(handler, projects_service._handle_project_artifact_delete(proj_id, parsed_url.query or ""))
    proj_id = path.split("/api/projects/", 1)[1].strip("/")
    qs = urllib.parse.parse_qs(parsed_url.query or "")
    delete_workspace = str((qs.get("deleteWorkspace") or ["false"])[0]).lower() in ("1", "true", "yes")
    return send_json(handler, projects_service._handle_project_delete(proj_id, delete_workspace=delete_workspace))
