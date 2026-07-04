import json
import urllib.parse

from .http import JsonBodyError, read_json, send_json


def _bridge_service():
    from server_services import agent_bridges
    agent_bridges._hydrate()
    return agent_bridges


def _body(handler):
    try:
        return read_json(handler), None
    except JsonBodyError as e:
        return {}, {"ok": False, "error": str(e), "_status": 400}


def _sse(handler, event_name, payload):
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(f"event: {event_name}\ndata: {json.dumps(payload)}\n\n".encode("utf-8"))
    return True


def handle_get(handler, parsed_url):
    service = _bridge_service()
    path = parsed_url.path
    qs = urllib.parse.parse_qs(parsed_url.query or "")
    if path == "/api/hermes/history":
        agent_key = (qs.get("agentId") or qs.get("key") or ["hermes-default"])[0]
        conversation_id = (qs.get("conversationId") or qs.get("threadId") or [""])[0]
        agent = service._get_hermes_agent(agent_key)
        profile = (agent or {}).get("profile") or (agent or {}).get("providerAgentId") or "default"
        return send_json(handler, {
            "ok": True,
            "messages": service._filter_recoverable_provider_progress_messages(service._load_hermes_history(profile, conversation_id)),
            "sessionId": service._get_hermes_session_id(profile, conversation_id),
            "conversationId": conversation_id,
        })
    if path == "/api/codex/history":
        agent_key = (qs.get("agentId") or qs.get("key") or ["codex-default"])[0]
        conversation_id = (qs.get("conversationId") or [""])[0]
        agent = service._get_codex_agent(agent_key)
        profile = (agent or {}).get("profile") or (agent or {}).get("providerAgentId") or "default"
        state = service._load_codex_state(profile)
        token_usage = service._get_codex_token_usage(profile)
        messages = service._filter_recoverable_provider_progress_messages(service._load_codex_history(profile))
        events = service._filter_recoverable_comm_progress_events(service._dedupe_visible_comm_history(service._load_comm_history(limit=500, conversation_id=conversation_id, agent_id=agent_key)))
        return send_json(handler, {
            "ok": True,
            "events": events,
            "messages": messages,
            "sessionId": service._get_codex_session_id(profile),
            "tokenUsage": token_usage,
            "contextUsed": service._codex_context_used_from_token_usage(token_usage) or service._codex_int(state.get("contextUsed"), 0),
            "contextWindow": service._codex_context_window_from_token_usage(token_usage) or service._codex_int(state.get("contextWindow"), 0),
        })
    if path == "/api/claude-code/history":
        agent_key = (qs.get("agentId") or qs.get("key") or ["claude-code-main"])[0]
        conversation_id = (qs.get("conversationId") or [""])[0]
        agent = service._get_claude_code_agent(agent_key)
        profile = (agent or {}).get("profile") or (agent or {}).get("providerAgentId") or "main"
        state = service._load_claude_code_state(profile, conversation_id)
        token_usage = service._get_claude_code_token_usage(profile, conversation_id)
        return send_json(handler, {
            "ok": True,
            "messages": service._filter_recoverable_provider_progress_messages(service._sanitize_claude_code_history_messages(service._load_claude_code_history(profile, conversation_id))),
            "sessionId": service._get_claude_code_session_id(profile, conversation_id),
            "conversationId": conversation_id,
            "tokenUsage": token_usage,
            "contextUsed": service._codex_context_used_from_token_usage(token_usage) or service._codex_int(state.get("contextUsed"), 0),
            "contextWindow": service._codex_context_window_from_token_usage(token_usage) or service._codex_int(state.get("contextWindow"), 0),
        })
    if path == "/api/hermes/approval/pending":
        agent_key = (qs.get("agentId") or qs.get("key") or ["hermes-default"])[0]
        session_id = (qs.get("session_id") or qs.get("sessionId") or [""])[0]
        return send_json(handler, service._get_hermes_approval_pending(agent_key, session_id), status=200)
    if path == "/api/hermes/approval/stream":
        agent_key = (qs.get("agentId") or qs.get("key") or ["hermes-default"])[0]
        session_id = (qs.get("session_id") or qs.get("sessionId") or [""])[0]
        result = service._get_hermes_approval_pending(agent_key, session_id)
        return _sse(handler, "approval" if result.get("pending") else "idle", result)
    if path.startswith("/api/hermes/runs/") and path.endswith("/events"):
        service._handle_hermes_run_events(handler, urllib.parse.unquote(path[len("/api/hermes/runs/"):-len("/events")].strip("/")))
        return True
    if path == "/api/codex/activity":
        return send_json(handler, service._handle_codex_activity(qs))
    if path == "/api/codex/approval/pending":
        return send_json(handler, service._handle_codex_approval_pending(qs))
    if path.startswith("/api/codex/runs/") and path.endswith("/events"):
        service._handle_codex_run_events(handler, urllib.parse.unquote(path[len("/api/codex/runs/"):-len("/events")].strip("/")))
        return True
    if path.startswith("/api/claude-code/runs/") and path.endswith("/events"):
        service._handle_claude_code_run_events(handler, urllib.parse.unquote(path[len("/api/claude-code/runs/"):-len("/events")].strip("/")))
        return True
    return False


def handle_post(handler, parsed_url):
    service = _bridge_service()
    path = parsed_url.path
    if path in {"/api/hermes/runs", "/api/hermes/interrupt", "/api/hermes/chat", "/api/codex/runs", "/api/claude-code/runs", "/api/codex/chat", "/api/claude-code/chat", "/api/codex/interrupt", "/api/claude-code/interrupt", "/api/codex/approval/respond", "/api/hermes/approval/respond", "/api/hermes/history/clear", "/api/claude-code/history/clear", "/api/codex/reset", "/api/codex/compact", "/api/codex/interaction", "/api/codex/cancel", "/api/claude-code/cancel"}:
        body, error = _body(handler)
        if error:
            return send_json(handler, error)
        handlers = {
            "/api/hermes/runs": service._handle_hermes_run_start,
            "/api/hermes/interrupt": service._handle_hermes_interrupt,
            "/api/hermes/chat": service._handle_hermes_chat,
            "/api/codex/runs": service._handle_codex_run_start,
            "/api/claude-code/runs": service._handle_claude_code_run_start,
            "/api/codex/chat": service._handle_codex_chat,
            "/api/claude-code/chat": service._handle_claude_code_chat,
            "/api/codex/interrupt": service._handle_codex_interrupt,
            "/api/claude-code/interrupt": service._handle_claude_code_interrupt,
            "/api/codex/approval/respond": service._handle_codex_approval_respond,
            "/api/hermes/approval/respond": service._handle_hermes_approval_respond,
            "/api/hermes/history/clear": service._handle_hermes_history_clear,
            "/api/claude-code/history/clear": service._handle_claude_code_history_clear,
            "/api/codex/reset": service._handle_codex_reset,
            "/api/codex/compact": service._handle_codex_compact,
            "/api/codex/interaction": service._handle_codex_interaction,
            "/api/codex/cancel": service._handle_codex_cancel,
            "/api/claude-code/cancel": service._handle_claude_code_cancel,
        }
        return send_json(handler, handlers[path](body), status=200 if path.endswith("/history/clear") else None)
    if path.startswith("/api/hermes/runs/") and path.endswith("/stop"):
        body, error = _body(handler)
        if error:
            return send_json(handler, error)
        body["runId"] = body.get("runId") or urllib.parse.unquote(path[len("/api/hermes/runs/"):-len("/stop")].strip("/"))
        return send_json(handler, service._handle_hermes_run_stop(body))
    if path.startswith("/api/codex/runs/") and path.endswith("/stop"):
        body, error = _body(handler)
        if error:
            return send_json(handler, error)
        body["runId"] = body.get("runId") or urllib.parse.unquote(path[len("/api/codex/runs/"):-len("/stop")].strip("/"))
        return send_json(handler, service._handle_codex_run_stop(body))
    if path.startswith("/api/claude-code/runs/") and path.endswith("/stop"):
        body, error = _body(handler)
        if error:
            return send_json(handler, error)
        body["runId"] = urllib.parse.unquote(path[len("/api/claude-code/runs/"):-len("/stop")].strip("/"))
        return send_json(handler, service._handle_claude_code_interrupt(body))
    if path == "/api/codex/history/clear":
        body, error = _body(handler)
        if error:
            return send_json(handler, error)
        agent = service._get_codex_agent(body.get("agentId") or body.get("key") or "codex-default") or {}
        profile = agent.get("profile") or agent.get("providerAgentId") or "default"
        session_id = service._get_codex_session_id(profile)
        service._save_codex_history(profile, [])
        service._set_codex_session_id(profile, "")
        service._clear_codex_token_usage(profile)
        return send_json(handler, {"ok": True, "clearedCodexSession": bool(session_id), "sessionId": session_id}, status=200)
    return False


def handle_put(handler, parsed_url):
    return False


def handle_delete(handler, parsed_url):
    return False
