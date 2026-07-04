import urllib.parse

from .http import JsonBodyError, read_json, send_json


def _skills_service():
    from server_services import skills
    skills._hydrate()
    return skills


def _body(handler):
    try:
        return read_json(handler), None
    except JsonBodyError as e:
        return {}, {"ok": False, "error": str(e), "_status": 400}


def _agent_skill_parts(path, marker):
    rest = path.split("/api/agent/", 1)[1]
    agent_key, tail = rest.split(marker, 1)
    return urllib.parse.unquote(agent_key.strip("/")), urllib.parse.unquote(tail.strip("/"))


def _library_skill(path):
    return urllib.parse.unquote(path.split("/api/skills-library/", 1)[1].strip("/"))


def handle_get(handler, parsed_url):
    service = _skills_service()
    path = parsed_url.path
    if path.startswith("/api/agent/") and path.endswith("/skills"):
        agent_key, _ = _agent_skill_parts(path, "/skills")
        return send_json(handler, service._handle_skill_list(agent_key))
    if path == "/api/skills-library":
        return send_json(handler, service._handle_skills_library_list(), status=200)
    if path == "/api/skills-workshop":
        return send_json(handler, service._handle_skill_workshop_list(urllib.parse.parse_qs(parsed_url.query or "")))
    if path == "/api/skills-workshop/inspect":
        return send_json(handler, service._handle_skill_workshop_inspect(urllib.parse.parse_qs(parsed_url.query or "")))
    if path.startswith("/api/skills-library/") and path not in {"/api/skills-library/apply", "/api/skills-library/upload"}:
        return send_json(handler, service._handle_skills_library_get(_library_skill(path)))
    return False


def handle_post(handler, parsed_url):
    service = _skills_service()
    path = parsed_url.path
    if path.startswith("/api/agent/") and "/skills" in path:
        agent_key, skill_path = _agent_skill_parts(path, "/skills")
        body, error = _body(handler)
        return send_json(handler, error or service._handle_skill_write(agent_key, skill_path, body))
    handlers = {
        "/api/skills-library": service._handle_skills_library_create,
        "/api/skills-library/apply": service._handle_skills_library_apply,
        "/api/skills-library/save-from-agent": service._handle_skills_library_save_from_agent,
        "/api/skills-library/upload": service._handle_skills_library_upload,
        "/api/skills-workshop/action": service._handle_skill_workshop_action,
    }
    if path in handlers:
        body, error = _body(handler)
        return send_json(handler, error or handlers[path](body))
    return False


def handle_put(handler, parsed_url):
    return False


def handle_delete(handler, parsed_url):
    service = _skills_service()
    path = parsed_url.path
    if path.startswith("/api/agent/") and "/skills/" in path:
        agent_key, skill_name = _agent_skill_parts(path, "/skills/")
        return send_json(handler, service._handle_skill_delete(agent_key, skill_name))
    if path.startswith("/api/skills-library/"):
        return send_json(handler, service._handle_skills_library_delete(_library_skill(path)))
    return False
