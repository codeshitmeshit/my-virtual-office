import urllib.parse

from .http import JsonBodyError, read_json, send_json


def _agents_service():
    from server_services import agents
    agents._hydrate()
    return agents


def _skills_service():
    from server_services import skills
    skills._hydrate()
    return skills


def _body(handler):
    try:
        return read_json(handler), None
    except JsonBodyError as e:
        return {}, {"ok": False, "error": str(e), "_status": 400}


def _workspace_key(path):
    return urllib.parse.unquote(path.split("/api/agent-workspace/", 1)[1].strip("/"))


def handle_get(handler, parsed_url):
    service = _agents_service()
    path = parsed_url.path
    if path == "/api/agents":
        return send_json(handler, service._handle_agents_list())
    if path.startswith("/api/agent-workspace/"):
        return send_json(handler, service._get_agent_workspace_payload(_workspace_key(path)))
    if path == "/api/agent-platforms":
        return send_json(handler, service._handle_agent_platforms(), status=200)
    if path == "/api/agent-platform-communications/skill":
        handler.send_response(200)
        handler.send_header("Content-Type", "text/markdown; charset=utf-8")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        handler.wfile.write(_skills_service()._agent_platform_comm_skill_content().encode("utf-8"))
        return True
    if path == "/api/agent-platform-communications/history":
        qs = urllib.parse.parse_qs(parsed_url.query or "")
        return send_json(handler, service._handle_agent_platform_comm_history(qs), status=200)
    return False


def handle_post(handler, parsed_url):
    service = _agents_service()
    path = parsed_url.path
    if path == "/api/agent/create":
        body, error = _body(handler)
        return send_json(handler, error or service._handle_agent_create(body))
    if path.startswith("/api/agent-workspace/"):
        body, error = _body(handler)
        return send_json(handler, error or service._handle_agent_workspace_update(_workspace_key(path), body))
    if path == "/api/agent-platform-communications/send":
        body, error = _body(handler)
        return send_json(handler, error or service._handle_agent_platform_comm_send(body))
    return False


def handle_put(handler, parsed_url):
    return False


def handle_delete(handler, parsed_url):
    service = _agents_service()
    if parsed_url.path == "/api/agent/delete":
        body, error = _body(handler)
        return send_json(handler, error or service._handle_agent_delete(body))
    return False
