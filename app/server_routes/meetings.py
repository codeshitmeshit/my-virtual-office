import urllib.parse

from .http import JsonBodyError, read_json, send_json


def _meetings_service():
    from server_services import meetings
    meetings._hydrate()
    return meetings


def _body(handler):
    try:
        return read_json(handler), None
    except JsonBodyError as e:
        return {}, {"ok": False, "error": str(e), "_status": 400}


def handle_get(handler, parsed_url):
    meetings_service = _meetings_service()
    path = parsed_url.path
    query = parsed_url.query or ""
    if path in ("/api/meetings", "/api/meetings/active"):
        return send_json(handler, {"ok": True, "meetings": meetings_service._meeting_active_projection()}, status=200)
    if path == "/api/meetings/history":
        return send_json(handler, {"ok": True, "history": meetings_service._meeting_history_projection()}, status=200)
    if path == "/api/meetings/requests":
        return send_json(handler, meetings_service._meeting_request_list_filtered(query))
    if path.startswith("/api/meetings/requests/"):
        request_id = urllib.parse.unquote(path.split("/api/meetings/requests/", 1)[1].strip("/"))
        return send_json(handler, meetings_service._handle_meeting_request_detail(request_id))
    if path == "/api/meetings/executable/reconcile":
        return send_json(handler, meetings_service._handle_executable_meeting_reconcile())
    if path.startswith("/api/meetings/executable/"):
        rest = path.split("/api/meetings/executable/", 1)[1].strip("/")
        if rest.endswith("/events"):
            meeting_id = urllib.parse.unquote(rest.rsplit("/events", 1)[0].strip("/"))
            return send_json(handler, meetings_service._handle_executable_meeting_events(meeting_id, query))
        meeting_id = urllib.parse.unquote(rest)
        return send_json(handler, meetings_service._handle_executable_meeting_detail(meeting_id))
    return False


def handle_post(handler, parsed_url):
    meetings_service = _meetings_service()
    path = parsed_url.path
    meeting_action_suffixes = {
        "transition": meetings_service._handle_executable_meeting_transition,
        "intervention": meetings_service._handle_executable_meeting_intervention,
        "agenda-change": meetings_service._handle_executable_meeting_agenda_change,
        "arbitration": meetings_service._handle_executable_meeting_arbitration,
        "moderator-takeover": meetings_service._handle_executable_meeting_moderator_takeover,
        "conflict": meetings_service._handle_executable_meeting_conflict_action,
        "targeted-question": meetings_service._handle_executable_meeting_targeted_question,
        "run": meetings_service._handle_executable_meeting_run,
    }
    if path.startswith("/api/meetings/requests/") and path.endswith("/confirm"):
        request_id = urllib.parse.unquote(path.split("/api/meetings/requests/", 1)[1].rsplit("/confirm", 1)[0].strip("/"))
        body, error = _body(handler)
        return send_json(handler, error or meetings_service._handle_meeting_request_confirm(request_id, body))
    if path.startswith("/api/meetings/requests/") and path.endswith("/reject"):
        request_id = urllib.parse.unquote(path.split("/api/meetings/requests/", 1)[1].rsplit("/reject", 1)[0].strip("/"))
        body, error = _body(handler)
        return send_json(handler, error or meetings_service._handle_meeting_request_reject(request_id, body))
    if path == "/api/meetings/executable/create":
        body, error = _body(handler)
        return send_json(handler, error or meetings_service._handle_executable_meeting_create(body))
    if path.startswith("/api/meetings/executable/") and "/action-items/" in path:
        rest = path.split("/api/meetings/executable/", 1)[1]
        meeting_id, item_rest = rest.split("/action-items/", 1)
        action_item_id = item_rest.strip("/")
        body, error = _body(handler)
        return send_json(handler, error or meetings_service._handle_executable_meeting_action_item(urllib.parse.unquote(meeting_id), urllib.parse.unquote(action_item_id), body))
    for suffix, fn in meeting_action_suffixes.items():
        marker = "/" + suffix
        if path.startswith("/api/meetings/executable/") and path.endswith(marker):
            meeting_id = urllib.parse.unquote(path.split("/api/meetings/executable/", 1)[1].rsplit(marker, 1)[0].strip("/"))
            body, error = _body(handler)
            return send_json(handler, error or fn(meeting_id, body))
    if path == "/api/meetings/create":
        body, error = _body(handler)
        return send_json(handler, error or meetings_service._handle_meeting_create(body))
    if path == "/api/meetings/end":
        body, error = _body(handler)
        return send_json(handler, error or meetings_service._handle_meeting_end(body))
    if path == "/api/meetings/end-all":
        return send_json(handler, meetings_service._handle_meeting_end_all())
    return False


def handle_put(handler, parsed_url):
    return False


def handle_delete(handler, parsed_url):
    if parsed_url.path.startswith("/api/meetings/history/"):
        meetings_service = _meetings_service()
        meet_id = parsed_url.path.split("/api/meetings/history/", 1)[1].strip("/")
        return send_json(handler, meetings_service._handle_meeting_history_delete(meet_id))
    return False
