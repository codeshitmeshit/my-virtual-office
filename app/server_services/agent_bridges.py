"""Agent provider bridge service split from server.py.

Owns Hermes, Codex, and Claude Code chat/run/activity/approval bridge helpers.
Historical `_handle_*` and provider helper names remain exported for server.py
compatibility and tests.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from datetime import datetime, timezone

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_DIR = os.environ.get("VO_STATUS_DIR") or os.path.join(APP_DIR, "status")

__all__ = [
    'HERMES_TASK_BREAKDOWN_STEPS',
    'HERMES_APPROVAL_LOCK',
    'HERMES_APPROVAL_PENDING',
    'HERMES_ACTIVE_RUNS_LOCK',
    'HERMES_ACTIVE_RUNS',
    'HERMES_PROFILE_API_LOCK',
    'HERMES_PROFILE_API_PROCESSES',
    'PROVIDER_PROGRESS_MAX_AGE_MS',
    'PROVIDER_PROGRESS_TERMINAL_STATUSES',
    'PROVIDER_RUN_BRIDGE',
    'CLAUDE_CODE_STREAM_RUNS_LOCK',
    'CLAUDE_CODE_STREAM_RUNS',
    '_CODEX_OPERATION_LOCKS',
    '_CODEX_OPERATION_LOCKS_GUARD',
    '_CODEX_THREAD_STATE_LOCK',
    '_CODEX_ACTIVITY_LOCK',
    '_CODEX_ACTIVE_LOCK',
    '_CODEX_ACTIVE_OPERATIONS',
    '_CODEX_RUN_IDEMPOTENCY',
    '_CODEX_RUN_IDEMPOTENCY_TTL_MS',
    '_PROVIDER_RUN_IDEMPOTENCY',
    '_PROVIDER_RUN_IDEMPOTENCY_TTL_MS',
    '_CODEX_SECRET_KEYS',
    '_CODEX_MAX_EVENT_TEXT',
    'ProviderRunBridge',
    '_get_hermes_agent',
    '_safe_hermes_path_part',
    '_hermes_history_path',
    '_load_hermes_history',
    '_load_provider_histories_for_bubbles',
    '_load_hermes_state',
    '_save_hermes_history',
    '_get_hermes_session_id',
    '_set_hermes_session_id',
    '_jsonish',
    '_extract_hermes_turn_activity',
    '_remember_hermes_active_run',
    '_get_hermes_active_run',
    '_find_hermes_active_run',
    '_clear_hermes_active_run',
    '_hermes_task_breakdown_tool',
    '_hermes_api_client',
    '_hermes_event_name',
    '_hermes_event_text',
    '_hermes_api_tool_card',
    '_hermes_api_approval_from_event',
    '_handle_hermes_api_chat',
    '_remove_hermes_progress_messages',
    '_publish_hermes_progress',
    '_publish_hermes_api_progress',
    '_format_hermes_attachment_context',
    '_hermes_tool_activity_messages',
    '_hermes_approval_key',
    '_normalize_hermes_approval_choice',
    '_remember_hermes_approval_pending',
    '_get_hermes_approval_pending',
    '_resolve_hermes_approval_pending',
    '_detect_hermes_approval_request',
    '_approval_result_message',
    '_parse_url_port',
    '_is_local_http_url',
    '_hermes_profile_api_port',
    '_hermes_profile_api_config',
    '_hermes_api_client_for_profile',
    '_ensure_hermes_profile_api',
    '_hermes_event_tool_card',
    '_build_hermes_delivery_message',
    '_handle_hermes_interrupt',
    '_handle_hermes_chat',
    '_handle_codex_interrupt',
    '_handle_codex_approval_pending',
    '_handle_codex_approval_respond',
    'msg_matches_ephemeral',
    '_handle_hermes_approval_respond',
    '_hermes_stream_event_payload',
    '_handle_hermes_run_start',
    '_handle_hermes_run_events',
    '_handle_hermes_run_stop',
    '_handle_hermes_history_clear',
    '_codex_provider_from_config',
    '_codex_activity_path',
    '_sanitize_codex_value',
    '_load_codex_activity',
    '_save_codex_activity',
    '_append_codex_activity',
    '_get_codex_activity',
    '_get_codex_active',
    '_codex_thread_state_path',
    '_load_codex_thread_state',
    '_save_codex_thread_state',
    '_codex_thread_key',
    '_get_codex_thread_id',
    '_set_codex_thread_id',
    '_reset_codex_thread_id',
    '_codex_operation_lock',
    '_codex_idempotency_key',
    '_codex_idempotency_scope',
    '_prune_codex_idempotency',
    '_provider_run_idempotency_key',
    '_provider_run_idempotency_scope',
    '_prune_provider_run_idempotency',
    '_provider_run_duplicate_response',
    '_register_provider_run_idempotency',
    '_finish_provider_run_idempotency',
    '_codex_git_paths',
    '_append_codex_user_comm_event',
    '_handle_codex_chat',
    '_codex_stream_event_payload',
    '_codex_activity_bridge_event_name',
    '_handle_codex_run_start',
    '_handle_codex_run_events',
    '_handle_codex_run_stop',
    '_handle_codex_activity',
    '_handle_codex_interaction',
    '_normalize_codex_approval_choice',
    '_codex_approval_result_message',
    '_codex_history_has_approval',
    '_codex_approval_conversation_id',
    '_append_codex_approval_result_comm_event',
    '_handle_codex_cancel',
    '_handle_codex_reset',
    '_handle_codex_compact',
    '_codex_history_path',
    '_load_codex_state',
    '_load_codex_history',
    '_save_codex_state',
    '_save_codex_history',
    '_get_codex_session_id',
    '_set_codex_session_id',
    '_set_codex_active_run',
    '_get_codex_token_usage',
    '_set_codex_token_usage',
    '_clear_codex_token_usage',
    '_claude_code_provider_from_config',
    '_claude_code_history_path',
    '_load_claude_code_state',
    '_load_claude_code_history',
    '_sanitize_claude_code_history_messages',
    '_save_claude_code_history',
    '_get_claude_code_session_id',
    '_get_claude_code_token_usage',
    '_set_claude_code_token_usage',
    '_clear_claude_code_token_usage',
    '_codex_int',
    '_provider_context_used_from_token_usage',
    '_provider_context_window_from_token_usage',
    '_codex_context_used_from_token_usage',
    '_codex_context_window_from_token_usage',
    '_provider_visible_thinking',
    '_provider_progress_status',
    '_is_recoverable_provider_progress',
    '_filter_recoverable_provider_progress_messages',
    '_filter_recoverable_comm_progress_events',
    '_provider_progress_message',
    '_upsert_ephemeral_message',
    '_remove_provider_progress_messages',
    '_set_claude_code_session_id',
    '_set_claude_code_active_run',
    '_publish_claude_code_progress',
    '_remove_claude_code_progress_messages',
    '_remember_claude_code_stream_run',
    '_get_claude_code_stream_run',
    '_clear_claude_code_stream_run',
    '_claude_code_visible_thinking',
    '_claude_code_stream_event_payload',
    '_claude_code_tool_stream_key',
    '_handle_claude_code_run_start',
    '_handle_claude_code_run_events',
    '_handle_claude_code_interrupt',
    '_handle_claude_code_history_clear',
    '_handle_claude_code_chat',
    '_handle_claude_code_cancel',
]


def _server_module():
    return sys.modules.get("server") or sys.modules.get("__main__")


_ORIGINAL_EXPORTS = {}


def _hydrate():
    server = _server_module()
    if server is None or server is sys.modules.get(__name__):
        return
    exported = set(__all__)
    for key, value in vars(server).items():
        if key.startswith("__") or key in ("_server_module", "_hydrate", "_wrap_exports"):
            continue
        if key in exported and callable(value) and (
            getattr(value, "_service_wrapper", False) or getattr(value, "_service_wrapped", False)
        ):
            if key in _ORIGINAL_EXPORTS:
                globals()[key] = _ORIGINAL_EXPORTS[key]
            continue
        globals()[key] = value


def _wrap_exports():
    current = sys.modules[__name__]
    for name in __all__:
        value = globals().get(name)
        if not callable(value) or getattr(value, "_service_wrapped", False):
            continue
        _ORIGINAL_EXPORTS.setdefault(name, value)

        def make_wrapper(fn):
            def wrapper(*args, **kwargs):
                _hydrate()
                return fn(*args, **kwargs)
            wrapper.__name__ = fn.__name__
            wrapper.__doc__ = fn.__doc__
            wrapper.__dict__.update(getattr(fn, "__dict__", {}))
            wrapper._service_wrapped = True
            return wrapper

        setattr(current, name, make_wrapper(value))


def _get_hermes_agent(agent_id_or_key=None):
    needle = str(agent_id_or_key or "")
    for a in get_roster():
        if a.get("providerKind") == "hermes" and (not needle or needle in (a.get("id"), a.get("statusKey"), a.get("providerAgentId"))):
            return a
    return None


def _safe_hermes_path_part(value, fallback="default", limit=80):
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value or fallback))[:limit].strip(".-")
    return safe or fallback


def _hermes_history_path(profile="default", conversation_id=None):
    safe_profile = re.sub(r"[^a-zA-Z0-9_.-]+", "-", profile or "default")[:80] or "default"
    if conversation_id:
        raw_conversation = str(conversation_id)
        safe_conversation = _safe_hermes_path_part(raw_conversation, "conversation", 80)
        digest = hashlib.sha1(raw_conversation.encode("utf-8")).hexdigest()[:10]
        return os.path.join(STATUS_DIR, f"hermes-chat-{safe_profile}-conv-{safe_conversation}-{digest}.json")
    return os.path.join(STATUS_DIR, f"hermes-chat-{safe_profile}.json")


def _load_hermes_history(profile="default", conversation_id=None):
    path = _hermes_history_path(profile, conversation_id)
    try:
        with open(path, "r") as f:
            data = json.load(f)
        messages = data.get("messages", []) if isinstance(data, dict) else []
        return messages if isinstance(messages, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _load_provider_histories_for_bubbles(provider_kind, profile="default", limit=500):
    """Load global and conversation-scoped provider history for map bubbles."""
    safe_profile = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(profile or "default"))[:80] or "default"
    prefixes = {
        "hermes": f"hermes-chat-{safe_profile}",
        "claude-code": f"claude-code-chat-{safe_profile}",
    }
    prefix = prefixes.get(provider_kind)
    if not prefix:
        return []
    messages = []
    seen = set()
    for path in sorted(glob.glob(os.path.join(STATUS_DIR, f"{prefix}*.json"))):
        try:
            with open(path, "r") as f:
                state = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
        file_messages = state.get("messages") if isinstance(state, dict) else []
        if not isinstance(file_messages, list):
            continue
        conversation_id = state.get("conversationId") if isinstance(state, dict) else ""
        for msg in file_messages:
            if not isinstance(msg, dict):
                continue
            item = dict(msg)
            item.setdefault("conversationId", conversation_id or "")
            if provider_kind == "claude-code":
                item["thinking"] = _claude_code_visible_thinking(item)
            key = (
                item.get("role") or "",
                item.get("text") or "",
                item.get("ts") or "",
                item.get("conversationId") or "",
                item.get("agentId") or "",
            )
            if key in seen:
                continue
            seen.add(key)
            messages.append(item)
    messages.sort(key=lambda item: int(item.get("epochMs") or item.get("ts") or 0))
    return messages[-max(1, min(int(limit or 500), 1000)):]


def _load_hermes_state(profile="default", conversation_id=None):
    path = _hermes_history_path(profile, conversation_id)
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return {"profile": profile, "conversationId": conversation_id or "", "messages": []}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"profile": profile, "conversationId": conversation_id or "", "messages": []}


def _save_hermes_history(profile, messages, conversation_id=None):
    path = _hermes_history_path(profile, conversation_id)
    try:
        existing = _load_hermes_state(profile, conversation_id)
        existing["profile"] = profile
        if conversation_id:
            existing["conversationId"] = conversation_id
        else:
            existing.pop("conversationId", None)
        existing["messages"] = messages[-500:]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(existing, f, indent=2)
        try:
            os.chmod(path, 0o666)
        except OSError:
            pass
    except OSError as e:
        print(f"[HERMES] Failed to save history: {e}")


def _get_hermes_session_id(profile="default", conversation_id=None):
    state = _load_hermes_state(profile, conversation_id)
    session_id = state.get("sessionId") or state.get("session_id")
    return str(session_id).strip() if session_id else ""


def _set_hermes_session_id(profile="default", session_id="", conversation_id=None):
    path = _hermes_history_path(profile, conversation_id)
    state = _load_hermes_state(profile, conversation_id)
    state["profile"] = profile
    if conversation_id:
        state["conversationId"] = conversation_id
    else:
        state.pop("conversationId", None)
    if session_id:
        state["sessionId"] = session_id
    else:
        state.pop("sessionId", None)
        state.pop("session_id", None)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
        try:
            os.chmod(path, 0o666)
        except OSError:
            pass
    except OSError as e:
        print(f"[HERMES] Failed to save session id: {e}")


def _jsonish(value):
    if value in (None, ""):
        return {}
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {"value": value}
    return {"value": value}


def _extract_hermes_turn_activity(exported_session, user_content):
    """Convert public Hermes session export messages into chat activity cards."""
    if not isinstance(exported_session, dict):
        return {"tools": [], "thinking": "", "reasoningTokens": 0}
    messages = exported_session.get("messages") or []
    if not isinstance(messages, list):
        return {"tools": [], "thinking": "", "reasoningTokens": int(exported_session.get("reasoning_tokens") or 0)}

    start_idx = -1
    needle = str(user_content or "").strip()
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i] if isinstance(messages[i], dict) else {}
        if msg.get("role") == "user" and (not needle or str(msg.get("content") or "").strip() == needle):
            start_idx = i
            break
    turn = messages[start_idx + 1:] if start_idx >= 0 else messages[-8:]

    pending: dict[str, dict] = {}
    tools: list[dict] = []
    thinking_parts: list[str] = []

    for msg in turn:
        if not isinstance(msg, dict):
            continue
        reasoning = msg.get("reasoning") or msg.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning.strip():
            thinking_parts.append(reasoning.strip())
        details = msg.get("reasoning_details")
        if isinstance(details, list):
            for item in details:
                if isinstance(item, dict):
                    txt = item.get("text") or item.get("summary")
                    if isinstance(txt, str) and txt.strip():
                        thinking_parts.append(txt.strip())

        for call in msg.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            fn = call.get("function") if isinstance(call.get("function"), dict) else {}
            call_id = str(call.get("id") or call.get("call_id") or "")
            tool = {
                "id": call_id,
                "status": "running",
                "name": fn.get("name") or call.get("name") or call.get("tool_name") or "tool",
                "arguments": _jsonish(fn.get("arguments") or call.get("arguments") or call.get("args") or {}),
                "result": "",
            }
            tools.append(tool)
            if call_id:
                pending[call_id] = tool

        if msg.get("role") == "tool":
            call_id = str(msg.get("tool_call_id") or "")
            tool = pending.get(call_id)
            if not tool:
                tool = {
                    "id": call_id,
                    "status": "done",
                    "name": msg.get("tool_name") or "tool result",
                    "arguments": {},
                    "result": "",
                }
                tools.append(tool)
            tool["status"] = "error" if msg.get("finish_reason") == "error" else "done"
            if msg.get("tool_name"):
                tool["name"] = msg.get("tool_name")
            tool["result"] = msg.get("content") or ""

    for tool in tools:
        if tool.get("status") == "running":
            tool["status"] = "done"
    return {
        "tools": tools[-40:],
        "thinking": "\n\n".join(dict.fromkeys(thinking_parts))[:12000],
        "reasoningTokens": int(exported_session.get("reasoning_tokens") or 0),
    }


HERMES_TASK_BREAKDOWN_STEPS = [
    "Receive message from Virtual Office",
    "Load Hermes profile and current session",
    "Run Hermes request through the selected profile",
    "Collect Hermes reply and public activity",
    "Render reply, tool calls, and task summary",
]

HERMES_APPROVAL_LOCK = threading.Lock()
HERMES_APPROVAL_PENDING = {}
HERMES_ACTIVE_RUNS_LOCK = threading.Lock()
HERMES_ACTIVE_RUNS = {}


def _remember_hermes_active_run(meta):
    if not isinstance(meta, dict) or not meta.get("runId"):
        return
    with HERMES_ACTIVE_RUNS_LOCK:
        HERMES_ACTIVE_RUNS[str(meta["runId"])] = dict(meta)


def _get_hermes_active_run(run_id):
    with HERMES_ACTIVE_RUNS_LOCK:
        meta = HERMES_ACTIVE_RUNS.get(str(run_id or ""))
        return dict(meta) if isinstance(meta, dict) else None


def _find_hermes_active_run(agent_key="", profile=""):
    with HERMES_ACTIVE_RUNS_LOCK:
        for meta in reversed(list(HERMES_ACTIVE_RUNS.values())):
            if agent_key and agent_key in {meta.get("agentId"), meta.get("agentKey")}:
                return dict(meta)
            if profile and profile == meta.get("profile"):
                return dict(meta)
    return None


def _clear_hermes_active_run(run_id):
    with HERMES_ACTIVE_RUNS_LOCK:
        HERMES_ACTIVE_RUNS.pop(str(run_id or ""), None)


def _hermes_task_breakdown_tool(status="running", result=""):
    return {
        "id": "hermes-task-breakdown",
        "status": status,
        "name": "Hermes task breakdown",
        "arguments": {"willDo": HERMES_TASK_BREAKDOWN_STEPS},
        "result": result or "Running Hermes native API stream and collecting public activity.",
    }


def _hermes_api_client():
    hermes_cfg = VO_CONFIG.get("hermes", {})
    return HermesApiClient(
        base_url=hermes_cfg.get("apiUrl"),
        api_key=hermes_cfg.get("apiKey"),
        timeout_sec=min(int(hermes_cfg.get("timeoutSec") or 600), 60),
    )


def _hermes_event_name(event):
    return str((event or {}).get("event") or (event or {}).get("type") or "").strip().lower().replace("_", ".")


def _hermes_event_text(event):
    if not isinstance(event, dict):
        return ""
    for key in ("delta", "text", "content", "output"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    for key in ("delta", "text", "content", "output"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _hermes_api_tool_card(event, status="running", fallback_id=""):
    event = event if isinstance(event, dict) else {}
    name = str(event.get("tool") or event.get("name") or event.get("tool_name") or "Hermes tool")
    preview = str(event.get("preview") or event.get("label") or event.get("command") or "")
    result = str(event.get("result") or event.get("output") or event.get("error") or "")
    return {
        "id": str(event.get("toolCallId") or event.get("tool_call_id") or event.get("id") or fallback_id or f"hermes-tool-{int(time.time() * 1000)}"),
        "name": name,
        "status": status,
        "arguments": {"command": preview} if preview else {},
        "result": result or ("Running" if status == "running" else "Completed"),
    }


def _hermes_api_approval_from_event(event, agent_id="", profile="", session_id="", original_message=""):
    event = event if isinstance(event, dict) else {}
    command = str(event.get("command") or event.get("preview") or event.get("tool") or "Hermes approval request")
    run_id = str(event.get("run_id") or event.get("runId") or "")
    seed = f"{agent_id}|{profile}|{session_id}|{run_id}|{command}|{original_message}"
    approval_id = "hermes-api-approval-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    return {
        "id": approval_id,
        "approval_id": approval_id,
        "provider": "hermes-api",
        "status": "pending",
        "kind": "command",
        "title": "Hermes approval required",
        "description": str(event.get("description") or "Hermes needs approval before it can continue this run."),
        "command": command,
        "message": original_message,
        "agentId": agent_id or "hermes-default",
        "profile": profile or "default",
        "session_id": session_id or "",
        "runId": run_id,
        "choices": event.get("choices") or ["approve_once", "deny"],
    }


def _handle_hermes_api_chat(agent, profile, delivery_message, original_message, conversation_id, timeout, on_event=None):
    hermes_cfg = VO_CONFIG.get("hermes", {})
    if not hermes_cfg.get("apiEnabled"):
        return {"ok": False, "fallback": True, "error": "Hermes native API is disabled"}
    client = _hermes_api_client()
    try:
        if not client.is_available():
            return {"ok": False, "fallback": True, "error": "Hermes native API is not available"}
        session_id = _get_hermes_session_id(profile, conversation_id) or f"vo-hermes-{_safe_hermes_path_part(profile)}"
        started = client.start_run(delivery_message, session_id=session_id, session_key=f"virtual-office:hermes:{profile}")
        run_id = str(started.get("run_id") or started.get("runId") or started.get("id") or "")
        if not run_id:
            return {"ok": False, "fallback": True, "error": started.get("error") or "Hermes native API did not return a run id"}
        _set_hermes_session_id(profile, session_id, conversation_id)
        if callable(on_event):
            on_event({"event": "run.native.started", "run_id": run_id, "session_id": session_id})

        reply = ""
        thinking_parts = []
        tools_by_id = {}
        tool_order = []
        approval = None
        terminal = ""
        error_text = ""
        for event in client.stream_run_events(run_id, timeout_sec=int(timeout) + 30):
            name = _hermes_event_name(event)
            if callable(on_event):
                on_event(event if isinstance(event, dict) else {})
            if name in {"message.delta", "message.delta.text", "response.delta", "delta"}:
                reply += _hermes_event_text(event)
            elif name in {"message", "message.completed", "run.completed", "completed"} and _hermes_event_text(event):
                if name in {"run.completed", "completed"}:
                    reply = _hermes_event_text(event) or reply
                else:
                    reply += _hermes_event_text(event)
            elif name in {"reasoning.available", "reasoning", "thinking"}:
                text = _hermes_event_text(event)
                if text:
                    thinking_parts.append(text)
            elif name in {"tool.started", "tool.call", "tool"}:
                card = _hermes_api_tool_card(event, "running", f"{run_id}:tool:{len(tool_order) + 1}")
                tools_by_id[card["id"]] = card
                tool_order.append(card["id"])
            elif name in {"tool.completed", "tool.result", "tool.failed"}:
                status = "error" if name == "tool.failed" or event.get("error") else "done"
                card = _hermes_api_tool_card(event, status, str(event.get("id") or event.get("toolCallId") or ""))
                if card["id"] in tools_by_id:
                    tools_by_id[card["id"]].update(card)
                else:
                    tools_by_id[card["id"]] = card
                    tool_order.append(card["id"])
            elif name in {"approval.request", "approval"}:
                approval = _remember_hermes_approval_pending(
                    _hermes_api_approval_from_event(event, agent_id=agent.get("id") or agent.get("statusKey"), profile=profile, session_id=session_id, original_message=original_message),
                    agent_id=agent.get("id") or agent.get("statusKey"),
                    profile=profile,
                    session_id=session_id,
                )
            elif name in {"run.completed", "completed"}:
                terminal = "completed"
                if _hermes_event_text(event):
                    reply = _hermes_event_text(event) or reply
                break
            elif name in {"run.failed", "failed", "run.cancelled", "run.canceled", "cancelled", "canceled"}:
                terminal = name
                error_text = str(event.get("error") or event.get("message") or name)
                break
        tools = [tools_by_id[tid] for tid in tool_order if tid in tools_by_id]
        if approval:
            return {
                "ok": False,
                "providerPath": "api",
                "reply": reply,
                "error": "Hermes is waiting for approval.",
                "sessionId": session_id,
                "runId": run_id,
                "tools": tools,
                "thinking": "\n\n".join(thinking_parts),
                "reasoningTokens": 0,
                "approval": approval,
                "exitCode": 1,
            }
        ok = terminal in {"completed", ""}
        return {
            "ok": ok,
            "providerPath": "api",
            "reply": reply,
            "error": None if ok else error_text,
            "sessionId": session_id,
            "runId": run_id,
            "tools": tools,
            "thinking": "\n\n".join(thinking_parts),
            "reasoningTokens": 0,
            "approval": None,
            "exitCode": 0 if ok else 1,
        }
    except Exception as exc:
        return {"ok": False, "fallback": True, "providerPath": "api", "error": str(exc)}


def _remove_hermes_progress_messages(messages):
    return _remove_provider_progress_messages(messages, "hermes")


def _publish_hermes_progress(profile, agent_id, progress_id, run_state, conversation_id=None):
    if not progress_id:
        return
    run_state = run_state if isinstance(run_state, dict) else {}
    progress_message = _provider_progress_message("hermes", agent_id, progress_id, run_state, conversation_id, "Waiting for Hermes run events.")
    history = _load_hermes_history(profile, conversation_id)
    history = _upsert_ephemeral_message(history, "hermes-progress", progress_id, progress_message)
    _save_hermes_history(profile, history, conversation_id)


def _publish_hermes_api_progress(profile, agent_id, run_id, tools=None, reasoning_parts=None, reply="", conversation_id=None):
    _publish_hermes_progress(profile, agent_id, f"hermes-progress-{run_id}", {
        "runId": run_id,
        "status": "running",
        "thinking": "\n\n".join(reasoning_parts or []),
        "reply": reply or "",
        "tools": tools or [],
    }, conversation_id)


def _format_hermes_attachment_context(attachments):
    if not isinstance(attachments, list) or not attachments:
        return ""
    lines = [
        "Attachments provided by Virtual Office:",
        "Use these attachments when answering. Prefer the URL if the local path is not readable from your runtime.",
    ]
    for idx, item in enumerate(attachments, 1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("filename") or f"attachment-{idx}").strip()
        path = str(item.get("path") or item.get("filePath") or "").strip()
        url = str(item.get("url") or item.get("mediaUrl") or "").strip()
        mime_type = str(item.get("mimeType") or item.get("contentType") or item.get("media_type") or "").strip()
        size = item.get("size") or item.get("bytes") or ""
        if path and not url:
            url = "/chat-media?path=" + urllib.parse.quote(path)
        if url.startswith("/"):
            url = f"http://127.0.0.1:{PORT}{url}"
        details = [f"{idx}. {name}"]
        if mime_type:
            details.append(f"type: {mime_type}")
        if size:
            details.append(f"size: {size} bytes")
        if path:
            details.append(f"path: {path}")
        if url:
            details.append(f"url: {url}")
        lines.append(" | ".join(details))
    return "\n".join(lines) if len(lines) > 2 else ""


def _hermes_tool_activity_messages(tools, agent_id="", run_id="", base_ts=None, coerce_complete=False):
    """Store Hermes tools like OpenClaw recovered activity: one tool-only message per card."""
    if not isinstance(tools, list) or not tools:
        return []
    start_ts = int(base_ts if base_ts is not None else time.time() * 1000)
    messages = []
    for idx, tool in enumerate(tools):
        if not isinstance(tool, dict):
            continue
        item = dict(tool)
        item["runId"] = item.get("runId") or run_id or ""
        status = str(item.get("status") or "").lower()
        if coerce_complete and status == "running":
            item["status"] = "done"
            if not item.get("result") or str(item.get("result")).strip().lower() == "running":
                item["result"] = "Completed"
        messages.append({
            "role": "assistant",
            "text": "",
            "ts": start_ts + idx,
            "agentId": agent_id,
            "runId": item.get("runId") or run_id or "",
            "tools": [item],
            "source": "hermes-tool-activity",
        })
    return messages


def _hermes_approval_key(agent_id="", profile="", session_id=""):
    if session_id:
        return f"session:{session_id}"
    if profile:
        return f"profile:{profile}"
    return f"agent:{agent_id or 'hermes-default'}"


def _normalize_hermes_approval_choice(choice):
    choice = str(choice or "").strip().lower()
    return {
        "once": "approve_once",
        "allow_once": "approve_once",
        "approve": "approve_once",
        "approved_once": "approve_once",
        "no": "deny",
        "denied": "deny",
    }.get(choice, choice)


def _remember_hermes_approval_pending(approval, agent_id="", profile="", session_id=""):
    if not isinstance(approval, dict):
        return None
    approval = dict(approval)
    approval_id = approval.get("approval_id") or approval.get("id")
    if approval_id:
        approval["id"] = approval_id
        approval["approval_id"] = approval_id
    approval["session_id"] = approval.get("session_id") or session_id or ""
    approval["agentId"] = approval.get("agentId") or agent_id or "hermes-default"
    approval["profile"] = approval.get("profile") or profile or ""
    approval["queuedAt"] = approval.get("queuedAt") or int(time.time() * 1000)
    approval["status"] = approval.get("status") or "pending"
    key = _hermes_approval_key(approval.get("agentId"), approval.get("profile"), approval.get("session_id"))
    with HERMES_APPROVAL_LOCK:
        queue = HERMES_APPROVAL_PENDING.setdefault(key, [])
        existing_idx = next((i for i, item in enumerate(queue) if item.get("id") == approval.get("id")), None)
        if existing_idx is None:
            queue.append(approval)
        else:
            queue[existing_idx] = {**queue[existing_idx], **approval}
        return approval


def _get_hermes_approval_pending(agent_key="hermes-default", session_id=""):
    agent = _get_hermes_agent(agent_key) or {}
    agent_id = agent.get("id") or agent_key or "hermes-default"
    profile = agent.get("profile") or agent.get("providerAgentId") or "default"
    keys = [
        _hermes_approval_key(agent_id, profile, session_id),
        _hermes_approval_key(agent_id, profile, ""),
        _hermes_approval_key(agent_id, "", ""),
    ]
    with HERMES_APPROVAL_LOCK:
        for key in dict.fromkeys(keys):
            queue = [item for item in HERMES_APPROVAL_PENDING.get(key, []) if item.get("status", "pending") == "pending"]
            HERMES_APPROVAL_PENDING[key] = queue
            if queue:
                return {"ok": True, "pending": queue[0], "pending_count": len(queue), "session_id": session_id or queue[0].get("session_id", "")}
        for key, items in list(HERMES_APPROVAL_PENDING.items()):
            queue = [
                item for item in items
                if item.get("status", "pending") == "pending"
                and (item.get("agentId") == agent_id or item.get("profile") == profile)
            ]
            HERMES_APPROVAL_PENDING[key] = queue
            if queue:
                return {"ok": True, "pending": queue[0], "pending_count": len(queue), "session_id": session_id or queue[0].get("session_id", "")}
    return {"ok": True, "pending": None, "pending_count": 0, "session_id": session_id or ""}


def _resolve_hermes_approval_pending(agent_key="hermes-default", approval_id="", session_id="", choice=""):
    agent = _get_hermes_agent(agent_key) or {}
    agent_id = agent.get("id") or agent_key or "hermes-default"
    profile = agent.get("profile") or agent.get("providerAgentId") or "default"
    keys = [
        _hermes_approval_key(agent_id, profile, session_id),
        _hermes_approval_key(agent_id, profile, ""),
        _hermes_approval_key(agent_id, "", ""),
    ]
    with HERMES_APPROVAL_LOCK:
        for key in dict.fromkeys(keys):
            queue = HERMES_APPROVAL_PENDING.get(key, [])
            for idx, item in enumerate(queue):
                if not approval_id or item.get("id") == approval_id or item.get("approval_id") == approval_id:
                    resolved = {**item, "status": choice or "resolved", "resolvedAt": int(time.time() * 1000)}
                    del queue[idx]
                    HERMES_APPROVAL_PENDING[key] = queue
                    return resolved
        for key, queue in list(HERMES_APPROVAL_PENDING.items()):
            for idx, item in enumerate(queue):
                if (
                    (item.get("agentId") == agent_id or item.get("profile") == profile)
                    and (not approval_id or item.get("id") == approval_id or item.get("approval_id") == approval_id)
                ):
                    resolved = {**item, "status": choice or "resolved", "resolvedAt": int(time.time() * 1000)}
                    del queue[idx]
                    HERMES_APPROVAL_PENDING[key] = queue
                    return resolved
    return None


def _detect_hermes_approval_request(reply="", stderr="", original_message="", agent_key="hermes-default"):
    text = f"{reply or ''}\n{stderr or ''}"
    lower = text.lower()
    approval_markers = (
        "blocked: user denied",
        "approval required",
        "requires approval",
        "dangerous command",
        "command approval",
        "permission prompt",
        "approval prompt",
    )
    if not any(marker in lower for marker in approval_markers):
        return None
    command = ""
    command_patterns = [
        r"`([^`\n]{3,500})`",
        r"command(?: was)?[:\s]+([^\n]{3,500})",
    ]
    for pattern in command_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if candidate and "BLOCKED:" not in candidate:
                command = candidate[:500]
                break
    seed = f"{agent_key}:{original_message}:{command}:{int(time.time() // 60)}"
    approval_id = "hermes-approval-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    return {
        "id": approval_id,
        "approval_id": approval_id,
        "provider": "hermes",
        "status": "pending",
        "kind": "command",
        "title": "Hermes approval required",
        "description": "Hermes needs permission to retry this turn with approval bypass for this invocation only.",
        "command": command or "Approval-gated Hermes command",
        "message": original_message,
        "agentId": agent_key,
        "choices": ["approve_once", "deny"],
    }


def _approval_result_message(approval, choice):
    label = "approved once and retried" if choice == "approve_once" else "denied"
    return {
        "role": "assistant",
        "text": "",
        "ts": int(time.time() * 1000),
        "agentId": approval.get("agentId") or "hermes-default",
        "approval": {**approval, "status": label, "resolvedAt": int(time.time() * 1000)},
        "tools": [],
        "thinking": "",
        "reasoningTokens": 0,
    }


def _hermes_api_client():
    hermes_cfg = VO_CONFIG.get("hermes", {})
    return HermesApiClient(
        base_url=hermes_cfg.get("apiUrl"),
        api_key=hermes_cfg.get("apiKey"),
        timeout_sec=min(int(hermes_cfg.get("timeoutSec") or 600), 60),
    )


HERMES_PROFILE_API_LOCK = threading.Lock()
HERMES_PROFILE_API_PROCESSES = {}


def _parse_url_port(url, default=8642):
    try:
        parsed = urllib.parse.urlparse(str(url or ""))
        return int(parsed.port or default)
    except Exception:
        return default


def _is_local_http_url(url):
    try:
        parsed = urllib.parse.urlparse(str(url or ""))
        return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    except Exception:
        return False


def _hermes_profile_api_port(profile):
    hermes_cfg = VO_CONFIG.get("hermes", {})
    base = hermes_cfg.get("apiProfilePortBase") or os.environ.get("VO_HERMES_API_PROFILE_PORT_BASE")
    try:
        base = int(base)
    except (TypeError, ValueError):
        base = _parse_url_port(hermes_cfg.get("apiUrl"), 8642) + 1
    digest = hashlib.sha1(str(profile or "default").encode("utf-8")).hexdigest()
    return base + (int(digest[:6], 16) % 1000)


def _hermes_profile_api_config(profile):
    hermes_cfg = VO_CONFIG.get("hermes", {})
    profile_cfgs = hermes_cfg.get("apiProfiles") if isinstance(hermes_cfg.get("apiProfiles"), dict) else {}
    profile_cfg = profile_cfgs.get(profile) if isinstance(profile_cfgs.get(profile), dict) else {}
    auto_start_all = hermes_cfg.get("autoStartProfileApis", True) is not False
    if profile == "default":
        url = profile_cfg.get("apiUrl") or hermes_cfg.get("apiUrl") or f"http://127.0.0.1:{_hermes_profile_api_port(profile)}"
        auto_start = profile_cfg.get("autoStart", hermes_cfg.get("autoStartDefaultApi", auto_start_all)) is not False
        return {
            "url": url,
            "key": profile_cfg.get("apiKey") or hermes_cfg.get("apiKey"),
            "autoStart": bool(auto_start and _is_local_http_url(url)),
            "port": _parse_url_port(url, 8642),
        }
    port = _hermes_profile_api_port(profile)
    url = profile_cfg.get("apiUrl") or f"http://127.0.0.1:{port}"
    auto_start = profile_cfg.get("autoStart", auto_start_all) is not False
    return {
        "url": url,
        "key": profile_cfg.get("apiKey") or hermes_cfg.get("apiKey"),
        "autoStart": bool(auto_start and _is_local_http_url(url)),
        "port": _parse_url_port(url, port),
    }


def _hermes_api_client_for_profile(profile):
    profile = profile or "default"
    cfg = _hermes_profile_api_config(profile)
    if cfg.get("autoStart"):
        _ensure_hermes_profile_api(profile, cfg)
    return HermesApiClient(
        base_url=cfg.get("url"),
        api_key=cfg.get("key"),
        timeout_sec=min(int(VO_CONFIG.get("hermes", {}).get("timeoutSec") or 600), 60),
    )


def _ensure_hermes_profile_api(profile, api_cfg):
    """Start a profile-scoped Hermes API server when one is not already up."""
    if not profile:
        return
    api_key = api_cfg.get("key") or ""
    if not api_key or not api_cfg.get("autoStart") or not _is_local_http_url(api_cfg.get("url")):
        return
    client = HermesApiClient(
        base_url=api_cfg.get("url"),
        api_key=api_key,
        timeout_sec=5,
    )
    if client.is_available():
        return

    with HERMES_PROFILE_API_LOCK:
        proc = HERMES_PROFILE_API_PROCESSES.get(profile)
        if proc and proc.poll() is None:
            return

        hermes_cfg = VO_CONFIG.get("hermes", {})
        hermes_bin = os.path.expanduser(hermes_cfg.get("binary") or "~/.local/bin/hermes")
        hermes_home = os.path.expanduser(hermes_cfg.get("homePath") or "~/.hermes")
        if not os.path.exists(hermes_bin):
            return

        env = os.environ.copy()
        env.update({
            "API_SERVER_ENABLED": "true",
            "API_SERVER_HOST": "127.0.0.1",
            "API_SERVER_PORT": str(api_cfg.get("port") or _parse_url_port(api_cfg.get("url"), 8642)),
            "API_SERVER_KEY": api_key,
            "API_SERVER_MODEL_NAME": f"hermes-{HermesProvider._safe_suffix(profile)}",
            "VO_HERMES_HOME": hermes_home,
        })
        if os.path.basename(hermes_home.rstrip(os.sep)) == ".hermes":
            env["HOME"] = os.path.dirname(hermes_home.rstrip(os.sep)) or env.get("HOME", "")

        log_path = os.path.join(STATUS_DIR, f"hermes-api-{HermesProvider._safe_suffix(profile)}.log")
        try:
            log_f = open(log_path, "ab", buffering=0)
            cmd = [hermes_bin]
            if profile != "default":
                cmd.extend(["--profile", profile])
            cmd.extend(["gateway", "run"])
            proc = subprocess.Popen(
                cmd,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
            HERMES_PROFILE_API_PROCESSES[profile] = proc
        except Exception as exc:
            print(f"⚠️ Hermes profile API start failed for {profile}: {exc}")
            return

    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            if client.is_available():
                return
        except Exception:
            pass
        proc = HERMES_PROFILE_API_PROCESSES.get(profile)
        if proc and proc.poll() is not None:
            return
        time.sleep(0.5)


def _hermes_event_tool_card(event, status="running", fallback_id=""):
    tool = str(event.get("tool") or event.get("name") or event.get("tool_name") or "Hermes tool")
    preview = str(event.get("preview") or event.get("label") or "")
    duration = event.get("duration")
    result = "Running" if status == "running" else "Completed"
    if event.get("error"):
        result = "Failed"
    if duration is not None and status != "running":
        result = f"{result} in {duration}s"
    card = {
        "id": str(event.get("toolCallId") or event.get("tool_call_id") or event.get("id") or fallback_id or f"hermes-tool-{int(time.time() * 1000)}"),
        "name": tool,
        "status": status,
        "args_preview": preview,
        "result": result,
    }
    if preview:
        card["arguments"] = {"command": preview}
    return card


def _hermes_api_approval_from_event(event, agent_id="", profile="", session_id="", original_message=""):
    command = str(event.get("command") or event.get("preview") or event.get("tool") or "Hermes approval request")
    description = str(event.get("description") or "Hermes needs approval before it can continue this run.")
    run_id = str(event.get("run_id") or "")
    seed = f"{agent_id}|{profile}|{session_id}|{run_id}|{command}|{original_message}"
    approval_id = "hermes-api-approval-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    return {
        "id": approval_id,
        "approval_id": approval_id,
        "provider": "hermes-api",
        "kind": "dangerous_command",
        "title": "Hermes approval required",
        "description": description,
        "command": command,
        "message": original_message,
        "agentId": agent_id or "hermes-default",
        "profile": profile or "default",
        "session_id": session_id or "",
        "runId": run_id,
        "choices": event.get("choices") or ["once", "deny"],
        "status": "pending",
        "createdAt": int(time.time() * 1000),
    }


def _build_hermes_delivery_message(agent, agent_key, message, body):
    from_type = str(body.get("fromType") or body.get("senderType") or "").strip().lower()
    is_human_source = from_type in {"human", "user", "chat", "ui"}
    attachments = body.get("attachments") if isinstance(body.get("attachments"), list) else []
    attachment_context = _format_hermes_attachment_context(attachments)
    source_app = str(body.get("sourceApp") or body.get("app") or "virtual-office").strip() or "virtual-office"
    source_surface = str(body.get("sourceSurface") or body.get("surface") or "chat-window").strip() or "chat-window"
    source_label = str(body.get("sourceLabel") or "").strip()
    sender_name = str(body.get("fromDisplayName") or body.get("displayName") or body.get("fromName") or "User").strip() or "User"
    delivery_message = message
    if is_human_source:
        pretty_surface = source_label or ("Virtual Office Chat" if source_app == "virtual-office" and source_surface in {"chat-window", "chat"} else f"{source_app.replace('-', ' ').title()} {source_surface.replace('-', ' ').title()}".strip())
        delivery_message = (
            f"[A2A from=user name={json.dumps(sender_name)} to={agent.get('id') or agent_key} isUser=true sourceApp={json.dumps(source_app)} sourceSurface={json.dumps(source_surface)}]\n"
            f"Message from {sender_name} via {pretty_surface}.\n\n"
            f"{message}\n\n"
            "Reply directly to the user. Do not assume the user's name unless they identify themselves."
        )
    if attachment_context:
        delivery_message = f"{delivery_message}\n\n{attachment_context}"
    return {
        "deliveryMessage": delivery_message,
        "fromType": from_type,
        "isHumanSource": is_human_source,
        "attachments": attachments,
        "sourceApp": source_app,
        "sourceSurface": source_surface,
        "sourceLabel": source_label,
        "senderName": sender_name,
    }


def _handle_hermes_api_chat(agent, profile, delivery_message, original_message, conversation_id=None, timeout=None, on_event=None):
    """Run a Hermes turn through the native Hermes API Server + SSE events."""
    if isinstance(conversation_id, (int, float)) and timeout is None:
        timeout = conversation_id
        conversation_id = None
    conversation_id = str(conversation_id or "").strip()
    timeout = int(timeout or VO_CONFIG.get("hermes", {}).get("timeoutSec") or 600)
    agent_id = agent.get("id") or agent.get("statusKey") or "hermes-default"
    status_key = agent.get("statusKey") or agent_id
    client = _hermes_api_client_for_profile(profile)
    if not client.is_available():
        return {"ok": False, "fallback": True, "error": "Hermes API Server is not available"}

    session_id = _get_hermes_session_id(profile, conversation_id) or f"vo-hermes-{_safe_hermes_path_part(profile)}"
    session_key = f"virtual-office:hermes:{profile}"
    started = client.start_run(delivery_message, session_id=session_id, session_key=session_key)
    run_id = started.get("run_id")
    if not run_id:
        return {"ok": False, "fallback": True, "error": started.get("error") or "Hermes API did not return a run_id"}

    _set_hermes_session_id(profile, session_id, conversation_id)
    gateway_presence.set_provider_event(status_key, "hermes", {"event": "run.started", "run_id": run_id})
    if callable(on_event):
        on_event({"event": "run.started", "run_id": run_id, "session_id": session_id})

    reply = ""
    reasoning_parts = []
    tools = []
    started_tools = {}
    started_tool_keys = {}
    tool_seq = 0
    approval = None
    terminal_event = None
    error_text = ""
    last_progress_publish = 0.0

    def publish_progress(force=False):
        nonlocal last_progress_publish
        now = time.time()
        if force or now - last_progress_publish >= 0.25:
            _publish_hermes_api_progress(profile, agent_id, run_id, tools=tools, reasoning_parts=reasoning_parts, reply=reply, conversation_id=conversation_id)
            last_progress_publish = now

    publish_progress(force=True)

    try:
        for event in client.stream_run_events(run_id, timeout_sec=int(timeout) + 30):
            gateway_presence.set_provider_event(status_key, "hermes", event)
            if callable(on_event):
                on_event(event if isinstance(event, dict) else {})
            event_name = str(event.get("event") or "").lower()
            if event_name == "message.delta":
                reply += str(event.get("delta") or "")
                publish_progress()
            elif event_name == "reasoning.available":
                text = str(event.get("text") or "")
                if text:
                    reasoning_parts.append(text)
                    publish_progress(force=True)
            elif event_name == "tool.started":
                tool_seq += 1
                fallback_id = f"{run_id}:tool:{tool_seq}"
                card = _hermes_event_tool_card(event, "running", fallback_id=fallback_id)
                event_tool_key = f"{event.get('tool') or event.get('name') or 'tool'}:{event.get('preview') or event.get('label') or ''}"
                started_tool_keys[event_tool_key] = card["id"]
                started_tools[card["id"]] = card
                tools.append(card)
                publish_progress(force=True)
            elif event_name in {"tool.completed", "tool.failed"}:
                event_tool_key = f"{event.get('tool') or event.get('name') or 'tool'}:{event.get('preview') or event.get('label') or ''}"
                fallback_id = started_tool_keys.get(event_tool_key)
                if not fallback_id:
                    matching_id = next((tid for tid, item in reversed(list(started_tools.items())) if item.get("name") == (event.get("tool") or event.get("name"))), "")
                    fallback_id = matching_id or f"{run_id}:tool:{len(started_tools) + 1}"
                card = _hermes_event_tool_card(event, "done" if event_name == "tool.completed" else "error", fallback_id=fallback_id)
                if card["id"] in started_tools:
                    started_tools[card["id"]].update(card)
                else:
                    tools.append(card)
                publish_progress(force=True)
            elif event_name == "approval.request":
                approval = _remember_hermes_approval_pending(
                    _hermes_api_approval_from_event(event, agent_id=agent_id, profile=profile, session_id=session_id, original_message=original_message),
                    agent_id=agent_id,
                    profile=profile,
                    session_id=session_id,
                )
                publish_progress(force=True)
                continue
            elif event_name in {"run.completed", "run.failed", "run.cancelled", "run.canceled"}:
                terminal_event = event
                if event.get("output"):
                    reply = str(event.get("output") or reply)
                if event.get("error"):
                    error_text = str(event.get("error") or "")
                if event_name == "run.completed":
                    approval = None
                publish_progress(force=True)
                break
    except Exception as exc:
        gateway_presence.set_provider_event(status_key, "hermes", {"event": "run.failed", "run_id": run_id, "error": str(exc)})
        return {"ok": False, "error": str(exc), "providerPath": "api", "runId": run_id}

    terminal_name = str((terminal_event or {}).get("event") or "").lower()
    ok = terminal_name == "run.completed"
    if approval:
        ok = False
        error_text = "Hermes is waiting for approval."
    elif terminal_name in {"run.failed", "run.cancelled", "run.canceled"}:
        ok = False
        error_text = error_text or terminal_name.replace("run.", "Hermes run ")

    thinking = "\n\n".join(reasoning_parts)
    if thinking.strip() == reply.strip():
        thinking = ""

    return {
        "ok": ok,
        "reply": reply,
        "stderr": "",
        "exitCode": 0 if ok else 1,
        "sessionId": session_id,
        "runId": run_id,
        "tools": tools,
        "thinking": thinking,
        "reasoningTokens": 0,
        "approval": approval,
        "error": error_text or None,
        "providerPath": "api",
    }


def _handle_hermes_interrupt(body):
    agent_key = body.get("agentId") or body.get("key") or "hermes-default"
    run_id = str(body.get("runId") or body.get("run_id") or "").strip()
    agent = _get_hermes_agent(agent_key) or {}
    profile = agent.get("profile") or agent.get("providerAgentId") or ""
    meta = _get_hermes_active_run(run_id) if run_id else _find_hermes_active_run(agent_key, profile)
    if not meta:
        return {"ok": False, "error": "No active Hermes run is running for this agent.", "_status": 409}
    run_id = meta.get("runId") or run_id
    profile = meta.get("profile") or profile or "default"
    try:
        client = _hermes_api_client_for_profile(profile)
        result = client.stop_run(run_id)
        gateway_presence.set_provider_event(meta.get("statusKey") or agent.get("statusKey") or agent_key, "hermes", {"event": "run.stop_requested", "run_id": run_id})
        return {"ok": True, "providerPath": "api", "runId": run_id, "result": result, "message": "Hermes stop requested."}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "providerPath": "api", "runId": run_id, "_status": 500}


def _handle_hermes_chat(body):
    """Send one message to a local Hermes agent.

    Prefer Hermes' native API Server run/SSE surface when available, then fall
    back to the public Hermes CLI bridge for installs without the API server.
    """
    message = (body.get("message") or "").strip()
    agent_key = body.get("agentId") or body.get("key") or body.get("sessionKey") or "hermes-default"
    conversation_id = str(body.get("conversationId") or body.get("threadId") or "").strip()
    if not message:
        return {"ok": False, "error": "message is required", "_status": 400}

    agent = _get_hermes_agent(agent_key)
    if not agent:
        return {"ok": False, "error": f"Hermes agent '{agent_key}' not found", "_status": 404}
    archive_guard = _archive_manager_chat_guard(agent.get("id") or agent_key, message)
    if archive_guard:
        profile = agent.get("profile") or agent.get("providerAgentId") or "default"
        now_ms = int(time.time() * 1000)
        history = _load_hermes_history(profile, conversation_id)
        history.append({"role": "user", "text": message, "ts": now_ms, "agentId": agent.get("id"), "from": "User", "fromType": body.get("fromType") or ""})
        history.append({"role": "assistant", "text": archive_guard["reply"], "ts": int(time.time() * 1000), "agentId": agent.get("id")})
        _save_hermes_history(profile, history, conversation_id)
        return {**archive_guard, "conversationId": conversation_id}

    hermes_cfg = VO_CONFIG.get("hermes", {})
    hermes_bin = os.path.expanduser(agent.get("binary") or hermes_cfg.get("binary") or "~/.local/bin/hermes")
    timeout = int(body.get("timeoutSec") or hermes_cfg.get("timeoutSec") or 600)
    profile = agent.get("profile") or agent.get("providerAgentId") or "default"
    used_api = False

    from_type = str(body.get("fromType") or body.get("senderType") or "").strip().lower()
    is_human_source = from_type in {"human", "user", "chat", "ui"}
    attachments = body.get("attachments") if isinstance(body.get("attachments"), list) else []
    attachment_context = _format_hermes_attachment_context(attachments)
    source_app = str(body.get("sourceApp") or body.get("app") or "virtual-office").strip() or "virtual-office"
    source_surface = str(body.get("sourceSurface") or body.get("surface") or "chat-window").strip() or "chat-window"
    source_label = str(body.get("sourceLabel") or "").strip()
    sender_name = str(body.get("fromDisplayName") or body.get("displayName") or body.get("fromName") or "User").strip() or "User"
    delivery_message = message
    yolo_once = bool(body.get("yoloOnce") or body.get("approvalApprovedOnce"))
    if is_human_source:
        pretty_surface = source_label or ("Virtual Office Chat" if source_app == "virtual-office" and source_surface in {"chat-window", "chat"} else f"{source_app.replace('-', ' ').title()} {source_surface.replace('-', ' ').title()}".strip())
        delivery_message = (
            f"[A2A from=user name={json.dumps(sender_name)} to={agent.get('id') or agent_key} isUser=true sourceApp={json.dumps(source_app)} sourceSurface={json.dumps(source_surface)}]\n"
            f"Message from {sender_name} via {pretty_surface}.\n\n"
            f"{message}\n\n"
            "Reply directly to the user. Do not assume the user's name unless they identify themselves."
        )
    if attachment_context:
        delivery_message = f"{delivery_message}\n\n{attachment_context}"

    now_ms = int(time.time() * 1000)
    history = _load_hermes_history(profile, conversation_id)
    history.append({
        "role": "user",
        "text": message,
        "ts": now_ms,
        "agentId": agent.get("id"),
        "from": sender_name if is_human_source else "You",
        "fromType": from_type or "",
        "sourceApp": source_app if is_human_source else "",
        "sourceSurface": source_surface if is_human_source else "",
        "sourceLabel": source_label if is_human_source else "",
        "conversationId": conversation_id,
    })
    _save_hermes_history(profile, history, conversation_id)

    progress_id = f"hermes-progress-{now_ms}"
    history.append({
        "role": "assistant",
        "text": "",
        "ts": int(time.time() * 1000),
        "agentId": agent.get("id"),
        "ephemeral": "hermes-progress",
        "progressId": progress_id,
        "tools": [],
        "thinking": "Waiting for native Hermes API events.",
        "reasoningTokens": 0,
        "conversationId": conversation_id,
    })
    _save_hermes_history(profile, history, conversation_id)

    gateway_presence.set_manual_override(agent.get("statusKey") or agent.get("id"), "working", "Hermes task")
    try:
        api_result = None
        if hermes_cfg.get("apiEnabled"):
            api_result = _handle_hermes_api_chat(agent, profile, delivery_message, message, conversation_id, timeout, on_event=body.get("_onHermesApiEvent"))
            if not api_result.get("fallback"):
                used_api = True
                active_session_id = api_result.get("sessionId") or _get_hermes_session_id(profile, conversation_id)
                reply = api_result.get("reply", "")
                exit_code = api_result.get("exitCode")
                task_status = "done" if api_result.get("ok") else ("running" if api_result.get("approval") else "error")
                task_result = (
                    "Hermes native API run completed."
                    if api_result.get("ok")
                    else (api_result.get("error") or "Hermes native API run did not complete.")
                )
                visible_tools = [_hermes_task_breakdown_tool(task_status, task_result)] + (api_result.get("tools") or [])
                history = _remove_hermes_progress_messages(_load_hermes_history(profile, conversation_id))
                history.append({
                    "role": "assistant",
                    "text": reply,
                    "ts": int(time.time() * 1000),
                    "agentId": agent.get("id"),
                    "exitCode": exit_code,
                    "sessionId": active_session_id,
                    "runId": api_result.get("runId") or "",
                    "providerPath": "api",
                    "tools": visible_tools,
                    "thinking": api_result.get("thinking") or "",
                    "reasoningTokens": api_result.get("reasoningTokens") or 0,
                    "approval": api_result.get("approval"),
                    "conversationId": conversation_id,
                })
                _save_hermes_history(profile, history, conversation_id)
                state = "idle" if api_result.get("ok") else ("working" if api_result.get("approval") else "offline")
                gateway_presence.set_manual_override(agent.get("statusKey") or agent.get("id"), state, "")
                return {
                    "ok": bool(api_result.get("ok")),
                    "reply": reply,
                    "stderr": "",
                    "exitCode": exit_code,
                    "sessionId": active_session_id,
                    "runId": api_result.get("runId") or "",
                    "providerPath": "api",
                    "tools": visible_tools,
                    "thinking": api_result.get("thinking") or "",
                    "reasoningTokens": api_result.get("reasoningTokens") or 0,
                    "approval": api_result.get("approval"),
                    "error": api_result.get("error"),
                    "conversationId": conversation_id,
                    "agent": {"id": agent.get("id"), "name": agent.get("name"), "providerKind": "hermes", "profile": profile},
                }

        provider = HermesProvider(
            home_path=hermes_cfg.get("homePath"),
            binary=hermes_bin,
            enabled=hermes_cfg.get("enabled", True),
            timeout_sec=timeout,
        )
        session_id = _get_hermes_session_id(profile, conversation_id)
        result = provider.send_chat_message(profile, delivery_message, session_id=session_id, timeout_sec=timeout, yolo_once=yolo_once)
        if result.get("sessionId"):
            _set_hermes_session_id(profile, result.get("sessionId"), conversation_id)
        activity = {"tools": [], "thinking": "", "reasoningTokens": 0}
        active_session_id = result.get("sessionId") or session_id
        if not used_api and active_session_id:
            exported = provider.export_session(profile, active_session_id)
            if exported.get("ok"):
                activity = _extract_hermes_turn_activity(exported.get("session"), delivery_message)
        reply = result.get("reply", "")
        stderr = result.get("stderr", "")
        exit_code = result.get("exitCode")
        task_status = "done" if result.get("ok") else "error"
        task_result = "Hermes reply and session activity collected." if result.get("ok") else (result.get("error") or stderr or "Hermes request failed.")
        task_tools = [] if used_api else [_hermes_task_breakdown_tool(task_status, task_result)]
        visible_tools = task_tools + (activity.get("tools") or [])
        approval = result.get("approval")
        if not approval:
            approval = _detect_hermes_approval_request(reply, stderr, message, agent.get("id") or agent_key)
        if approval:
            approval = _remember_hermes_approval_pending(
                approval,
                agent_id=agent.get("id") or agent_key,
                profile=profile,
                session_id=active_session_id or "",
            )
        history = _remove_hermes_progress_messages(_load_hermes_history(profile, conversation_id))
        final_ts = int(time.time() * 1000)
        history.append({
            "role": "assistant",
            "text": reply,
            "ts": final_ts + len(visible_tools),
            "agentId": agent.get("id"),
            "exitCode": exit_code,
            "sessionId": active_session_id,
            "runId": result.get("runId"),
            "tools": [],
            "thinking": activity.get("thinking") or "",
            "reasoningTokens": activity.get("reasoningTokens") or 0,
            "approval": approval,
            "conversationId": conversation_id,
        })
        _save_hermes_history(profile, history, conversation_id)
        state = "idle" if result.get("ok") else "offline"
        gateway_presence.set_manual_override(agent.get("statusKey") or agent.get("id"), state, "")
        return {
            "ok": bool(result.get("ok")),
            "reply": reply,
            "stderr": stderr[:2000],
            "exitCode": exit_code,
            "sessionId": active_session_id,
            "runId": result.get("runId"),
            "providerPath": result.get("providerPath") or ("api" if used_api else "cli"),
            "tools": visible_tools,
            "thinking": activity.get("thinking") or "",
            "reasoningTokens": activity.get("reasoningTokens") or 0,
            "approval": approval,
            "error": result.get("error"),
            "conversationId": conversation_id,
            "agent": {"id": agent.get("id"), "name": agent.get("name"), "providerKind": "hermes", "profile": profile},
        }
    except Exception as e:
        history = _remove_hermes_progress_messages(_load_hermes_history(profile, conversation_id))
        history.append({
            "role": "assistant",
            "text": "",
            "ts": int(time.time() * 1000),
            "agentId": agent.get("id"),
            "tools": [_hermes_task_breakdown_tool("error", str(e))],
            "thinking": "",
            "reasoningTokens": 0,
            "conversationId": conversation_id,
        })
        _save_hermes_history(profile, history, conversation_id)
        gateway_presence.set_manual_override(agent.get("statusKey") or agent.get("id"), "offline", "Hermes CLI error")
        return {"ok": False, "error": str(e), "conversationId": conversation_id, "_status": 500}


def _handle_codex_interrupt(body):
    agent_key = body.get("agentId") or body.get("key") or body.get("sessionKey") or "codex-default"
    agent = _get_codex_agent(agent_key)
    if not agent:
        return {"ok": False, "error": f"Codex agent '{agent_key}' not found", "_status": 404}
    profile = agent.get("profile") or agent.get("providerAgentId") or "default"
    result = _codex_provider().interrupt(profile)
    if result.get("ok"):
        history = _load_codex_history(profile)
        history.append({
            "role": "assistant",
            "text": "",
            "ts": int(time.time() * 1000),
            "agentId": agent.get("id"),
            "ephemeral": "codex-progress",
            "progressId": f"codex-interrupt-{int(time.time() * 1000)}",
            "sessionId": result.get("threadId") or _get_codex_session_id(profile),
            "runId": result.get("turnId") or "",
            "tools": [],
            "thinking": "Stop requested. Waiting for Codex to interrupt the active turn.",
            "reasoningTokens": 0,
        })
        _save_codex_history(profile, history)
    else:
        result["_status"] = 409
    return result


def _handle_codex_approval_pending(agent_key="codex-default"):
    agent = _get_codex_agent(agent_key)
    if not agent:
        return {"ok": False, "error": f"Codex agent '{agent_key}' not found", "_status": 404}
    profile = agent.get("profile") or agent.get("providerAgentId") or "default"
    result = _codex_provider().pending_approval(profile)
    pending = result.get("pending") if isinstance(result.get("pending"), dict) else None
    if pending:
        pending["agentId"] = pending.get("agentId") or agent.get("id") or agent_key
        pending["profile"] = pending.get("profile") or profile
    return result


def _handle_codex_approval_respond(body):
    approval = body.get("approval") if isinstance(body.get("approval"), dict) else {}
    choice = _normalize_codex_approval_choice(body.get("choice") or body.get("action") or "")
    agent_key = body.get("agentId") or approval.get("agentId") or "codex-default"
    approval_id = str(body.get("approval_id") or body.get("approvalId") or approval.get("approval_id") or approval.get("id") or "").strip()
    if not approval_id:
        return {"ok": False, "error": "approval_id is required", "_status": 400}
    agent = _get_codex_agent(agent_key)
    if not agent:
        return {"ok": False, "error": f"Codex agent '{agent_key}' not found", "_status": 404}
    profile = agent.get("profile") or agent.get("providerAgentId") or "default"
    result = _codex_provider().respond_approval(profile, approval_id, choice)
    if not result.get("ok"):
        result["_status"] = 409
        return result

    resolved_approval = result.get("approval") if isinstance(result.get("approval"), dict) else {**approval, "approval_id": approval_id, "id": approval_id}
    resolved_approval["agentId"] = resolved_approval.get("agentId") or agent.get("id") or agent_key
    resolved_approval["profile"] = resolved_approval.get("profile") or profile
    history = _load_codex_history(profile)
    if not _history_has_approval(history, approval_id):
        history.append(_codex_approval_result_message(resolved_approval, choice))
        _save_codex_history(profile, history)
    gateway_presence.set_provider_event(agent.get("statusKey") or agent.get("id"), "codex", {
        "event": "approval.responded",
        "choice": choice,
        "approval_id": approval_id,
        "thread_id": resolved_approval.get("threadId") or resolved_approval.get("session_id") or "",
        "turn_id": resolved_approval.get("turnId") or resolved_approval.get("runId") or "",
    })
    return {
        "ok": True,
        "choice": choice,
        "approvalChoice": choice,
        "providerPath": "app-server",
        "approval": resolved_approval,
        "message": "Codex approval approved." if choice == "approve" else "Codex approval cancelled.",
    }


def msg_matches_ephemeral(msg, marker):
    return isinstance(msg, dict) and msg.get("ephemeral") == marker






def _handle_hermes_approval_respond(body):
    approval = body.get("approval") if isinstance(body.get("approval"), dict) else {}
    choice = _normalize_hermes_approval_choice(body.get("choice") or body.get("action") or "")
    if choice not in {"approve_once", "deny"}:
        return {"ok": False, "error": "choice must be approve_once or deny", "_status": 400}
    agent_key = body.get("agentId") or approval.get("agentId") or "hermes-default"
    approval_id = str(body.get("approval_id") or body.get("approvalId") or approval.get("approval_id") or approval.get("id") or "").strip()
    session_id = str(body.get("session_id") or body.get("sessionId") or approval.get("session_id") or approval.get("sessionId") or "").strip()
    queued_approval = _resolve_hermes_approval_pending(agent_key, approval_id, session_id, choice)
    if queued_approval:
        approval = {**queued_approval, **approval}
    message = str(body.get("message") or approval.get("message") or "").strip()
    agent = _get_hermes_agent(agent_key)
    if not agent:
        return {"ok": False, "error": f"Hermes agent '{agent_key}' not found", "_status": 404}
    profile = agent.get("profile") or agent.get("providerAgentId") or "default"
    if approval.get("provider") == "hermes-api" and approval.get("runId"):
        run_id = str(approval.get("runId"))
        api_choice = "deny" if choice == "deny" else "once"
        try:
            client = _hermes_api_client_for_profile(profile)
            approved = client.respond_approval(run_id, api_choice)
            history = _load_hermes_history(profile)
            history.append(_approval_result_message({**approval, "agentId": agent.get("id") or agent_key, "message": message}, choice))
            _save_hermes_history(profile, history)
            if choice == "deny":
                gateway_presence.set_provider_event(agent.get("statusKey") or agent.get("id"), "hermes", {"event": "run.cancelled", "run_id": run_id})
                return {"ok": True, "choice": "deny", "providerPath": "api", "runId": run_id, "message": "Hermes approval denied."}

            gateway_presence.set_provider_event(agent.get("statusKey") or agent.get("id"), "hermes", {"event": "approval.responded", "run_id": run_id})
            return {
                "ok": True,
                "choice": "approve_once",
                "approvalChoice": "approve_once",
                "providerPath": "api",
                "runId": run_id,
                "sessionId": approval.get("session_id") or "",
                "message": "Hermes approval approved. The active run will continue streaming.",
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "providerPath": "api", "runId": run_id, "_status": 500}
    if choice == "deny":
        history = _load_hermes_history(profile)
        history.append(_approval_result_message({**approval, "agentId": agent.get("id") or agent_key, "message": message}, "deny"))
        _save_hermes_history(profile, history)
        return {"ok": True, "choice": "deny", "message": "Hermes approval denied."}
    if not message:
        return {"ok": False, "error": "original approval message is missing", "_status": 400}
    history = _load_hermes_history(profile)
    history.append(_approval_result_message({**approval, "agentId": agent.get("id") or agent_key, "message": message}, "approve_once"))
    _save_hermes_history(profile, history)
    retry_body = {
        "agentId": agent_key,
        "message": message,
        "fromType": "human",
        "fromDisplayName": body.get("fromDisplayName") or "User",
        "sourceApp": "virtual-office",
        "sourceSurface": "chat-window-approval",
        "sourceLabel": "Virtual Office Approval",
        "yoloOnce": True,
        "approvalRetry": True,
    }
    result = _handle_hermes_chat(retry_body)
    result["approvalChoice"] = "approve_once"
    return result


def _hermes_stream_event_payload(run_id, agent, profile, result=None, **extra):
    result = result if isinstance(result, dict) else {}
    visible_thinking = _provider_visible_thinking("hermes", result)
    payload = {
        "runId": run_id,
        "agentId": (agent or {}).get("id") or "",
        "profile": profile or "",
        "sessionId": result.get("sessionId") or _get_hermes_session_id(profile, extra.get("conversationId") or "") or "",
        "turnId": result.get("runId") or run_id,
        "reply": result.get("reply") or "",
        "tools": result.get("tools") or [],
        "thinking": visible_thinking,
        "error": result.get("error") or "",
        "status": result.get("status") or ("completed" if result.get("ok") else "failed" if result else ""),
        "providerPath": result.get("providerPath") or "api",
    }
    if result.get("approval"):
        payload["approval"] = result.get("approval")
    payload.update({k: v for k, v in extra.items() if v is not None})
    return payload


def _handle_hermes_run_start(body):
    """Start a Hermes message in the background and expose progress through ProviderRunBridge."""
    message = (body.get("message") or "").strip()
    agent_key = body.get("agentId") or body.get("key") or body.get("sessionKey") or "hermes-default"
    if not message:
        return {"ok": False, "error": "message is required", "_status": 400}
    agent = _get_hermes_agent(agent_key)
    if not agent:
        return {"ok": False, "error": f"Hermes agent '{agent_key}' not found", "_status": 404}

    profile = agent.get("profile") or agent.get("providerAgentId") or "default"
    conversation_id = str(body.get("conversationId") or body.get("threadId") or "").strip()
    agent_id = agent.get("id") or agent_key
    idempotency_key = _provider_run_idempotency_key(body)
    idempotency_scope = _provider_run_idempotency_scope("hermes", agent_id, conversation_id, idempotency_key) if idempotency_key else ""
    if idempotency_scope:
        with _CODEX_ACTIVE_LOCK:
            _prune_provider_run_idempotency()
            existing = _PROVIDER_RUN_IDEMPOTENCY.get(idempotency_scope)
            if existing:
                return _provider_run_duplicate_response("hermes", conversation_id, idempotency_key, existing)

    run_id = f"hermes-{int(time.time() * 1000)}-{str(uuid.uuid4())[:8]}"
    status_key = agent.get("statusKey") or agent.get("id")
    events = queue.Queue()
    meta = {
        "runId": run_id,
        "agentId": agent.get("id"),
        "agentKey": agent_key,
        "profile": profile,
        "statusKey": status_key,
        "conversationId": conversation_id,
        "events": events,
        "startedAt": int(time.time() * 1000),
        "done": False,
        "result": None,
        "idempotencyKey": idempotency_key,
    }
    PROVIDER_RUN_BRIDGE.remember(meta)
    _register_provider_run_idempotency(idempotency_scope, run_id, "hermes", agent_id, conversation_id, idempotency_key, "api")

    def enqueue(event_name, payload=None):
        PROVIDER_RUN_BRIDGE.emit(run_id, event_name, payload)

    def worker():
        enqueue("run.started", {"providerPath": "api", "conversationId": conversation_id})
        progress_id = f"hermes-progress-{run_id}"
        _publish_hermes_progress(profile, agent.get("id") or agent_key, progress_id, {
            "runId": run_id,
            "status": "running",
            "thinking": "Waiting for Hermes run events.",
            "tools": [_hermes_task_breakdown_tool("running", "Hermes native API run queued.")],
        }, conversation_id)
        if hasattr(gateway_presence, "set_provider_event"):
            gateway_presence.set_provider_event(status_key, "hermes", {"event": "run.started", "run_id": run_id})

        def on_native_event(event):
            event = event if isinstance(event, dict) else {}
            name = _hermes_event_name(event)
            provider_run_id = str(event.get("run_id") or event.get("runId") or "")
            if provider_run_id:
                PROVIDER_RUN_BRIDGE.update(run_id, turnId=provider_run_id)
            payload = {
                "runId": run_id,
                "agentId": agent.get("id") or "",
                "profile": profile,
                "sessionId": event.get("session_id") or event.get("sessionId") or _get_hermes_session_id(profile, conversation_id) or "",
                "turnId": provider_run_id or run_id,
                "providerPath": "api",
                "rawEvent": event,
            }
            text = _hermes_event_text(event)
            if text:
                payload["delta"] = text
                payload["reply"] = text
                payload["thinking"] = text
            progress_state = {
                "runId": run_id,
                "sessionId": payload.get("sessionId") or "",
                "turnId": payload.get("turnId") or "",
                "status": name or "running",
                "reply": payload.get("reply") or "",
                "thinking": payload.get("thinking") or "",
                "tools": [],
            }
            if name in {"message.delta", "message.delta.text", "response.delta", "delta", "message", "message.completed"}:
                enqueue("message.delta", payload)
            elif name in {"reasoning.available", "reasoning", "thinking"}:
                enqueue("reasoning.available", payload)
            elif name in {"tool.started", "tool.call", "tool"}:
                tool_card = _hermes_api_tool_card(event, "running", f"{run_id}:tool")
                progress_state["tools"] = [tool_card]
                enqueue("tool.started", {**payload, "toolCard": tool_card})
            elif name in {"tool.completed", "tool.result"}:
                tool_card = _hermes_api_tool_card(event, "done", f"{run_id}:tool")
                progress_state["tools"] = [tool_card]
                enqueue("tool.completed", {**payload, "toolCard": tool_card})
            elif name == "tool.failed":
                tool_card = _hermes_api_tool_card(event, "error", f"{run_id}:tool")
                progress_state["tools"] = [tool_card]
                enqueue("tool.failed", {**payload, "toolCard": tool_card})
            _publish_hermes_progress(profile, agent.get("id") or agent_key, progress_id, progress_state, conversation_id)

        run_body = dict(body)
        run_body["_onHermesApiEvent"] = on_native_event
        run_body.setdefault("fromType", "human")
        run_body.setdefault("fromDisplayName", "User")
        run_body.setdefault("sourceApp", "virtual-office")
        run_body.setdefault("sourceSurface", "chat-window")
        run_body.setdefault("sourceLabel", "Virtual Office Chat")
        try:
            result = _handle_hermes_chat(run_body)
        except Exception as exc:
            result = {"ok": False, "error": str(exc), "_status": 500}
        terminal_payload = _hermes_stream_event_payload(run_id, agent, profile, result, conversationId=conversation_id)
        if result.get("approval"):
            enqueue("approval.required", terminal_payload)
        status = str(result.get("status") or "").lower()
        if result.get("ok"):
            enqueue("run.completed", terminal_payload)
            presence_event = "run.completed"
        elif status in {"cancelled", "canceled"}:
            enqueue("run.cancelled", terminal_payload)
            presence_event = "run.cancelled"
        else:
            terminal_payload["error"] = result.get("error") or result.get("reply") or "Hermes run failed"
            enqueue("run.failed", terminal_payload)
            presence_event = "run.failed"
        if hasattr(gateway_presence, "set_provider_event"):
            gateway_presence.set_provider_event(status_key, "hermes", {"event": presence_event, "run_id": run_id, "error": terminal_payload.get("error") or ""})
        PROVIDER_RUN_BRIDGE.update(
            run_id,
            done=True,
            result=result,
            sessionId=result.get("sessionId") or "",
            turnId=result.get("runId") or run_id,
        )
        _finish_provider_run_idempotency(idempotency_scope, result)
        threading.Timer(600, PROVIDER_RUN_BRIDGE.clear, args=(run_id,)).start()

    threading.Thread(target=worker, daemon=True, name=f"hermes-run-{run_id}").start()
    return {
        "ok": True,
        "runId": run_id,
        "providerPath": "api",
        "conversationId": conversation_id,
        "idempotencyKey": idempotency_key,
        "agent": {"id": agent.get("id"), "name": agent.get("name"), "providerKind": "hermes", "profile": profile},
    }


def _handle_hermes_run_events(handler, run_id):
    PROVIDER_RUN_BRIDGE.stream_events(handler, run_id, "Hermes")


def _handle_hermes_run_stop(body):
    run_id = str(body.get("runId") or "").strip()
    meta = PROVIDER_RUN_BRIDGE.get(run_id)
    hermes_cfg = VO_CONFIG.get("hermes", {})
    result = {"ok": False, "error": "Hermes run not found", "_status": 404}
    if meta:
        provider_run_id = str((meta.get("result") or {}).get("runId") or meta.get("turnId") or run_id)
        if hermes_cfg.get("apiEnabled"):
            try:
                result = _hermes_api_client().stop_run(provider_run_id)
                result = {"ok": result.get("ok", True), "status": "cancelled", "runId": provider_run_id, "providerPath": "api", **result}
            except Exception as exc:
                result = {"ok": False, "error": str(exc), "runId": provider_run_id, "providerPath": "api", "_status": 500}
        else:
            result = {"ok": False, "error": "Hermes native API stop is unavailable", "providerPath": "api", "_status": 409}
        event_name = "run.cancelled" if result.get("ok") else "run.failed"
        PROVIDER_RUN_BRIDGE.emit(run_id, event_name, {
            "runId": run_id,
            "agentId": meta.get("agentId") or "",
            "profile": meta.get("profile") or "",
            "conversationId": meta.get("conversationId") or "",
            "status": result.get("status") or "",
            "error": result.get("error") or "",
            "providerPath": "api",
        })
        PROVIDER_RUN_BRIDGE.update(run_id, done=True, result=result)
    return result


def _handle_hermes_history_clear(body):
    body = body or {}
    agent = _get_hermes_agent(body.get("agentId") or body.get("key") or "hermes-default") or {}
    profile = agent.get("profile") or agent.get("providerAgentId") or "default"
    conversation_id = str(body.get("conversationId") or "").strip()
    session_id = _get_hermes_session_id(profile, conversation_id)
    delete_result = {"ok": True, "deleted": False}
    if session_id:
        hermes_cfg = VO_CONFIG.get("hermes", {})
        hermes_bin = os.path.expanduser(agent.get("binary") or hermes_cfg.get("binary") or "~/.local/bin/hermes")
        provider = HermesProvider(
            home_path=hermes_cfg.get("homePath"),
            binary=hermes_bin,
            enabled=hermes_cfg.get("enabled", True),
            timeout_sec=int(hermes_cfg.get("timeoutSec") or 600),
        )
        delete_result = provider.delete_session(profile, session_id)
    _save_hermes_history(profile, [], conversation_id)
    _set_hermes_session_id(profile, "", conversation_id)
    return {
        "ok": True,
        "deletedHermesSession": bool(delete_result.get("deleted")),
        "sessionId": session_id,
        "conversationId": conversation_id,
        "profile": profile,
    }




def _codex_provider_from_config():
    cfg = VO_CONFIG.get("codex", {})
    return CodexProvider(
        enabled=cfg.get("enabled", False),
        workspace=cfg.get("workspace"),
        home_path=cfg.get("homePath"),
        binary=cfg.get("binary"),
        workspace_root=cfg.get("workspaceRoot"),
        main_workspace=cfg.get("mainWorkspace"),
        name=cfg.get("name"),
        agent_id=cfg.get("agentId"),
        model=cfg.get("model"),
        reply_text=cfg.get("replyText") or os.environ.get("VO_CLAUDE_CODE_REPLY_TEXT"),
        bridge_url=cfg.get("bridgeUrl"),
        sandbox=cfg.get("sandbox", "workspace-write"),
        approval_policy=cfg.get("approvalPolicy", "never"),
        include_main=cfg.get("includeMain", True),
        include_native_agents=cfg.get("includeNativeAgents", True),
        register_native_agents=cfg.get("registerNativeAgents", True),
    )


_CODEX_OPERATION_LOCKS = {}
_CODEX_OPERATION_LOCKS_GUARD = threading.Lock()
_CODEX_THREAD_STATE_LOCK = threading.Lock()
_CODEX_ACTIVITY_LOCK = threading.Lock()
_CODEX_ACTIVE_LOCK = threading.Lock()
_CODEX_ACTIVE_OPERATIONS = {}
_CODEX_RUN_IDEMPOTENCY = {}
_CODEX_RUN_IDEMPOTENCY_TTL_MS = 10 * 60 * 1000
_PROVIDER_RUN_IDEMPOTENCY = {}
_PROVIDER_RUN_IDEMPOTENCY_TTL_MS = 10 * 60 * 1000

_CODEX_SECRET_KEYS = {"authorization", "cookie", "token", "api_key", "apikey", "password", "secret", "access_token", "refresh_token"}
_CODEX_MAX_EVENT_TEXT = 12000


def _codex_activity_path():
    return os.path.join(STATUS_DIR, "codex-activity.json")


def _sanitize_codex_value(value, key=""):
    key_lower = str(key or "").lower().replace("-", "_")
    if any(secret in key_lower for secret in _CODEX_SECRET_KEYS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _sanitize_codex_value(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_codex_value(item) for item in value[:200]]
    if isinstance(value, str):
        text = re.sub(r"(?i)(bearer\s+)[a-z0-9._~+/=-]+", r"\1[REDACTED]", value)
        text = re.sub(r"(?i)(https?://[^\s/:]+:)[^@\s]+@", r"\1[REDACTED]@", text)
        if len(text) > _CODEX_MAX_EVENT_TEXT:
            return text[:_CODEX_MAX_EVENT_TEXT] + "\n[TRUNCATED]"
        return text
    return value


def _load_codex_activity():
    try:
        with open(_codex_activity_path(), "r") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save_codex_activity(events):
    path = _codex_activity_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(events[-5000:], f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _append_codex_activity(agent_id, conversation_id, event):
    with _CODEX_ACTIVITY_LOCK:
        events = _load_codex_activity()
        last_sequence = max(
            (int(item.get("sequence") or 0) for item in events if item.get("agentId") == agent_id and item.get("conversationId") == conversation_id),
            default=0,
        )
        record = _sanitize_codex_value({
            **event,
            "providerSequence": int(event.get("sequence") or 0),
            "sequence": last_sequence + 1,
            "agentId": agent_id,
            "conversationId": conversation_id,
        })
        events.append(record)
        _save_codex_activity(events)
    with _CODEX_ACTIVE_LOCK:
        active = _CODEX_ACTIVE_OPERATIONS.get(agent_id)
        if active and active.get("conversationId") == conversation_id:
            active["threadId"] = record.get("threadId") or active.get("threadId", "")
            active["turnId"] = record.get("turnId") or active.get("turnId", "")
            active["status"] = record.get("status") or active.get("status", "running")
            active["updatedAt"] = record.get("ts") or int(time.time() * 1000)
            if record.get("type") == "interaction":
                if record.get("status") == "pending":
                    active["pending"] = normalize_approval_record("codex", agent_id, conversation_id, record)
                    active["pending"]["raw"] = record
                elif active.get("pending", {}).get("interactionId") == record.get("interactionId"):
                    active["pending"] = None
    return record


def _get_codex_activity(agent_id, conversation_id, after=0):
    with _CODEX_ACTIVITY_LOCK:
        events = _load_codex_activity()
    return [event for event in events if event.get("agentId") == agent_id and event.get("conversationId") == conversation_id and int(event.get("sequence") or 0) > int(after or 0)]


def _get_codex_active(agent_id):
    with _CODEX_ACTIVE_LOCK:
        active = _CODEX_ACTIVE_OPERATIONS.get(agent_id)
        return dict(active) if active else None


def _codex_thread_state_path():
    return os.path.join(STATUS_DIR, "codex-conversation-threads.json")


def _load_codex_thread_state():
    try:
        with open(_codex_thread_state_path(), "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_codex_thread_state(state):
    path = _codex_thread_state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _codex_thread_key(agent_id, conversation_id):
    return f"{agent_id}::{conversation_id}"


def _get_codex_thread_id(agent_id, conversation_id):
    if not conversation_id:
        return ""
    with _CODEX_THREAD_STATE_LOCK:
        item = _load_codex_thread_state().get(_codex_thread_key(agent_id, conversation_id)) or {}
    return str(item.get("threadId") or "")


def _set_codex_thread_id(agent_id, conversation_id, thread_id):
    if not conversation_id or not thread_id:
        return
    with _CODEX_THREAD_STATE_LOCK:
        state = _load_codex_thread_state()
        state[_codex_thread_key(agent_id, conversation_id)] = {
            "agentId": agent_id,
            "conversationId": conversation_id,
            "threadId": thread_id,
            "updatedAt": int(time.time() * 1000),
        }
        _save_codex_thread_state(state)


def _reset_codex_thread_id(agent_id, conversation_id):
    with _CODEX_THREAD_STATE_LOCK:
        state = _load_codex_thread_state()
        removed = state.pop(_codex_thread_key(agent_id, conversation_id), None)
        _save_codex_thread_state(state)
    return bool(removed)


def _codex_operation_lock(agent_id):
    with _CODEX_OPERATION_LOCKS_GUARD:
        return _CODEX_OPERATION_LOCKS.setdefault(agent_id, threading.Lock())


def _codex_idempotency_key(body):
    value = str((body or {}).get("idempotencyKey") or (body or {}).get("requestId") or "").strip()
    if not value:
        return ""
    return value[:200]


def _codex_idempotency_scope(agent_id, conversation_id, key):
    return f"{agent_id}\n{conversation_id}\n{key}"


def _prune_codex_idempotency(now_ms=None):
    now_ms = int(now_ms or time.time() * 1000)
    for key, entry in list(_CODEX_RUN_IDEMPOTENCY.items()):
        if now_ms - int((entry or {}).get("ts") or 0) > _CODEX_RUN_IDEMPOTENCY_TTL_MS:
            _CODEX_RUN_IDEMPOTENCY.pop(key, None)


def _provider_run_idempotency_key(body):
    value = str((body or {}).get("idempotencyKey") or (body or {}).get("requestId") or "").strip()
    if not value:
        return ""
    return value[:200]


def _provider_run_idempotency_scope(provider_kind, agent_id, conversation_id, key):
    return f"{provider_kind}\n{agent_id}\n{conversation_id}\n{key}"


def _prune_provider_run_idempotency(now_ms=None):
    now_ms = int(now_ms or time.time() * 1000)
    for key, entry in list(_PROVIDER_RUN_IDEMPOTENCY.items()):
        if now_ms - int((entry or {}).get("ts") or 0) > _PROVIDER_RUN_IDEMPOTENCY_TTL_MS:
            _PROVIDER_RUN_IDEMPOTENCY.pop(key, None)


def _provider_run_duplicate_response(provider_kind, conversation_id, idempotency_key, entry):
    entry = entry if isinstance(entry, dict) else {}
    provider_path = entry.get("providerPath") or provider_kind
    if not entry.get("done") and entry.get("runId"):
        return {
            "ok": True,
            "status": "duplicate",
            "runId": entry.get("runId"),
            "conversationId": conversation_id,
            "idempotencyKey": idempotency_key,
            "providerPath": provider_path,
        }
    return {
        "ok": True,
        "status": "duplicate_completed",
        "runId": entry.get("runId") or "",
        "conversationId": conversation_id,
        "idempotencyKey": idempotency_key,
        "result": entry.get("result") or {},
        "providerPath": provider_path,
    }


def _register_provider_run_idempotency(scope, run_id, provider_kind, agent_id, conversation_id, idempotency_key, provider_path):
    if not scope:
        return
    with _CODEX_ACTIVE_LOCK:
        _PROVIDER_RUN_IDEMPOTENCY[scope] = {
            "runId": run_id,
            "providerKind": provider_kind,
            "agentId": agent_id,
            "conversationId": conversation_id,
            "idempotencyKey": idempotency_key,
            "providerPath": provider_path,
            "ts": int(time.time() * 1000),
            "done": False,
            "result": None,
        }


def _finish_provider_run_idempotency(scope, result):
    if not scope:
        return
    with _CODEX_ACTIVE_LOCK:
        entry = _PROVIDER_RUN_IDEMPOTENCY.get(scope)
        if entry:
            entry["done"] = True
            entry["result"] = result if isinstance(result, dict) else {}
            entry["ts"] = int(time.time() * 1000)


def _codex_git_paths(workspace):
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=10,
        )
        paths = set()
        for line in (result.stdout or "").splitlines():
            raw = line[3:].strip() if len(line) > 3 else ""
            if " -> " in raw:
                raw = raw.split(" -> ", 1)[1]
            if raw:
                paths.add(raw.strip('"'))
        return paths
    except Exception:
        return set()


def _append_codex_user_comm_event(agent, agent_id, conversation_id, message, body):
    from_type = str(body.get("fromType") or body.get("senderType") or "").strip().lower()
    if from_type not in {"human", "user", "chat", "ui"}:
        return None
    sender_name = str(body.get("fromDisplayName") or body.get("displayName") or body.get("fromName") or "User").strip() or "User"
    source_app = str(body.get("sourceApp") or body.get("app") or "virtual-office").strip() or "virtual-office"
    source_surface = str(body.get("sourceSurface") or body.get("surface") or "chat-window").strip() or "chat-window"
    source_label = str(body.get("sourceLabel") or "").strip()
    metadata = {
        "providerKind": "codex",
        "sourceApp": source_app,
        "sourceSurface": source_surface,
        "fromType": from_type,
    }
    if source_label:
        metadata["sourceLabel"] = source_label
    idempotency_key = _codex_idempotency_key(body)
    if idempotency_key:
        metadata["idempotencyKey"] = idempotency_key
    return _append_comm_event({
        "type": "message",
        "direction": "request",
        "conversationId": conversation_id,
        "from": {
            "id": "user",
            "providerKind": "human",
            "name": sender_name,
            "emoji": "",
            "sourceApp": source_app,
            "sourceSurface": source_surface,
            "sourceLabel": source_label,
        },
        "to": _office_agent_ref(agent_id),
        "text": message,
        "metadata": metadata,
        "visibleInOffice": True,
    })


def _handle_codex_chat(body):
    """Send one office-mediated message to the Codex harness adapter."""
    message = (body.get("message") or "").strip()
    agent_key = body.get("agentId") or body.get("key") or body.get("sessionKey") or "codex-local"
    if not message:
        return {"ok": False, "error": "message is required", "_status": 400}
    agent = _get_codex_agent(agent_key)
    if not agent:
        return {"ok": False, "error": f"Codex agent '{agent_key}' not found", "_status": 404}
    archive_guard = _archive_manager_chat_guard(agent.get("id") or agent_key, message)
    if archive_guard:
        return archive_guard
    conversation_id = str(body.get("conversationId") or body.get("threadId") or "").strip()
    if not conversation_id:
        return {"ok": False, "status": "invalid_request", "error": "conversationId is required", "_status": 400}
    agent_id = agent.get("id") or agent_key
    inbound_event = None
    operation_lock = _codex_operation_lock(agent_id)
    if not operation_lock.acquire(blocking=False):
        active = _get_codex_active(agent_id) or {}
        return {
            "ok": False,
            "status": "busy",
            "error": "Codex is already working. Wait for the current operation to finish.",
            "reply": "Codex is already working. Please wait.",
            "conversationId": conversation_id,
            "activeConversationId": active.get("conversationId", ""),
            "activeStatus": active.get("status", "running"),
            "_status": 409,
        }
    provider = _codex_provider_from_config()
    requested_workspace = str(body.get("workspace") or "").strip()
    if requested_workspace:
        provider.workspace = os.path.realpath(os.path.expanduser(requested_workspace))
    elif agent.get("workspace"):
        provider.workspace = os.path.realpath(os.path.expanduser(str(agent.get("workspace"))))
    inbound_event = _append_codex_user_comm_event(agent, agent_id, conversation_id, message, body)
    before_paths = _codex_git_paths(provider.workspace)
    allow_interaction = str(body.get("fromType") or "agent").lower() in {"human", "user", "chat", "ui"}
    with _CODEX_ACTIVE_LOCK:
        _CODEX_ACTIVE_OPERATIONS[agent_id] = normalize_active_operation(
            "codex",
            agent_id,
            conversation_id,
            thread_id=_get_codex_thread_id(agent_id, conversation_id),
        )
    activity_callback = body.get("_onActivity")
    reply_event_appended = {"done": False}

    def append_reply_event(reply, metadata=None, ok=True):
        text = str(reply or "")
        if not inbound_event or not text or reply_event_appended["done"]:
            return
        meta = metadata if isinstance(metadata, dict) else {}
        _append_comm_event({
            "type": "message",
            "direction": "reply",
            "conversationId": conversation_id,
            "from": _office_agent_ref(agent_id),
            "to": inbound_event.get("from") or {"id": "user", "providerKind": "human", "name": "User"},
            "text": text,
            "inReplyTo": inbound_event.get("id"),
            "metadata": {
                "providerKind": "codex",
                "threadId": meta.get("threadId") or "",
                "turnId": meta.get("turnId") or "",
                "modifiedFiles": meta.get("modifiedFiles") or [],
                "needsHumanIntervention": bool(meta.get("needsHumanIntervention")),
            },
            "visibleInOffice": True,
            "ok": bool(ok),
        })
        reply_event_appended["done"] = True

    def on_event(event):
        record = _append_codex_activity(agent_id, conversation_id, event)
        if record.get("type") == "turn" and str(record.get("status") or "").lower() in {"completed", "done", "success"}:
            output = record.get("output") if isinstance(record.get("output"), dict) else {}
            append_reply_event(output.get("reply") or record.get("reply") or "", {
                "threadId": record.get("threadId") or "",
                "turnId": record.get("turnId") or "",
                "modifiedFiles": output.get("modifiedFiles") or record.get("modifiedFiles") or [],
                "needsHumanIntervention": record.get("needsHumanIntervention"),
            }, ok=True)
        if callable(activity_callback):
            try:
                activity_callback(record)
            except Exception:
                pass

    try:
        result = provider.send_message(
            message,
            conversation_id=conversation_id,
            timeout_sec=int(body.get("timeoutSec") or 600),
            thread_id=_get_codex_thread_id(agent_id, conversation_id),
            event_callback=on_event,
            allow_interaction=allow_interaction,
        )
    except Exception as exc:
        result = {
            "ok": False,
            "status": "execution_failed",
            "error": str(exc),
            "reply": "",
        }
    finally:
        operation_lock.release()
    thread_id = str(result.get("threadId") or "")
    if thread_id:
        _set_codex_thread_id(agent_id, conversation_id, thread_id)
    after_paths = _codex_git_paths(provider.workspace)
    modified_files = collect_modified_files(result.get("modifiedFiles") or [], before_paths, after_paths)
    with _CODEX_ACTIVE_LOCK:
        _CODEX_ACTIVE_OPERATIONS.pop(agent_id, None)
    normalized = normalize_provider_result(
        "codex",
        agent,
        result,
        conversation_id=conversation_id,
        thread_id=thread_id,
        turn_id=result.get("turnId", ""),
        modified_files=modified_files,
    )
    if inbound_event and normalized.get("reply"):
        append_reply_event(normalized.get("reply") or "", {
            "threadId": normalized.get("threadId") or thread_id,
            "turnId": normalized.get("turnId") or result.get("turnId", ""),
            "modifiedFiles": modified_files,
            "needsHumanIntervention": bool(normalized.get("needsHumanIntervention")),
        }, ok=bool(normalized.get("ok")))
    normalized["_status"] = provider_http_status(normalized)
    return normalized


def _codex_stream_event_payload(run_id, agent, record=None, result=None, **extra):
    record = record if isinstance(record, dict) else {}
    result = result if isinstance(result, dict) else {}
    payload = {
        "runId": run_id,
        "agentId": (agent or {}).get("id") or record.get("agentId") or "",
        "profile": (agent or {}).get("profile") or (agent or {}).get("providerAgentId") or "",
        "conversationId": record.get("conversationId") or result.get("conversationId") or "",
        "threadId": record.get("threadId") or result.get("threadId") or "",
        "turnId": record.get("turnId") or result.get("turnId") or "",
        "status": record.get("status") or result.get("status") or "",
        "providerPath": "codex-app-server",
    }
    text = record.get("text") or record.get("delta") or record.get("message") or record.get("content") or ""
    if text:
        payload["text"] = text
        payload["delta"] = text
    if record.get("type") in {"reasoning", "thinking"}:
        visible_thinking = _provider_visible_thinking("codex", {**record, "thinking": text})
        if visible_thinking:
            payload["thinking"] = visible_thinking
    if record:
        payload["activity"] = record
    if result:
        payload.update({
            "reply": result.get("reply") or "",
            "error": result.get("error") or "",
            "modifiedFiles": result.get("modifiedFiles") or [],
            "needsHumanIntervention": bool(result.get("needsHumanIntervention")),
        })
    payload.update({k: v for k, v in extra.items() if v is not None})
    return payload


def _codex_activity_bridge_event_name(record):
    record = record if isinstance(record, dict) else {}
    event_type = str(record.get("type") or "").lower()
    status = str(record.get("status") or "").lower()
    if event_type == "interaction" and status == "pending":
        return "approval.request"
    if event_type in {"message", "assistant_message", "assistant", "text", "output"}:
        return "message.delta"
    if event_type in {"reasoning", "thinking"}:
        text = record.get("text") or record.get("delta") or record.get("message") or record.get("content") or ""
        return "reasoning.available" if _provider_visible_thinking("codex", {**record, "thinking": text}) else "provider.activity"
    if event_type in {"tool", "tool_call", "command", "activity"}:
        if status in {"done", "completed", "success"}:
            return "tool.completed"
        if status in {"error", "failed", "failure"}:
            return "tool.failed"
        return "tool.started"
    if event_type in {"turn", "run"} and status in {"done", "completed", "success"}:
        return "run.completed"
    if event_type in {"turn", "run"} and status in {"cancelled", "canceled"}:
        return "run.cancelled"
    if event_type in {"turn", "run"} and status in {"error", "failed", "failure"}:
        return "run.failed"
    return "provider.activity"


def _handle_codex_run_start(body):
    """Start a Codex message in the background and expose legacy activity over SSE."""
    message = (body.get("message") or "").strip()
    agent_key = body.get("agentId") or body.get("key") or body.get("sessionKey") or "codex-local"
    if not message:
        return {"ok": False, "error": "message is required", "_status": 400}
    agent = _get_codex_agent(agent_key)
    if not agent:
        return {"ok": False, "error": f"Codex agent '{agent_key}' not found", "_status": 404}
    conversation_id = str(body.get("conversationId") or body.get("threadId") or "").strip()
    if not conversation_id:
        return {"ok": False, "status": "invalid_request", "error": "conversationId is required", "_status": 400}

    agent_id = agent.get("id") or agent_key
    idempotency_key = _codex_idempotency_key(body)
    idempotency_scope = _codex_idempotency_scope(agent_id, conversation_id, idempotency_key) if idempotency_key else ""
    if idempotency_scope:
        with _CODEX_ACTIVE_LOCK:
            _prune_codex_idempotency()
            existing = _CODEX_RUN_IDEMPOTENCY.get(idempotency_scope)
            if existing:
                if not existing.get("done") and existing.get("runId"):
                    return {
                        "ok": True,
                        "status": "duplicate",
                        "runId": existing.get("runId"),
                        "conversationId": conversation_id,
                        "idempotencyKey": idempotency_key,
                        "providerPath": "codex-app-server",
                    }
                return {
                    "ok": True,
                    "status": "duplicate_completed",
                    "runId": existing.get("runId") or "",
                    "conversationId": conversation_id,
                    "idempotencyKey": idempotency_key,
                    "result": existing.get("result") or {},
                    "providerPath": "codex-app-server",
                }

    run_id = f"codex-{int(time.time() * 1000)}-{str(uuid.uuid4())[:8]}"
    profile = agent.get("profile") or agent.get("providerAgentId") or "local"
    status_key = agent.get("statusKey") or agent.get("id")
    events = queue.Queue()
    meta = {
        "runId": run_id,
        "agentId": agent.get("id"),
        "agentKey": agent_key,
        "profile": profile,
        "statusKey": status_key,
        "conversationId": conversation_id,
        "events": events,
        "startedAt": int(time.time() * 1000),
        "done": False,
        "result": None,
        "idempotencyKey": idempotency_key,
    }
    PROVIDER_RUN_BRIDGE.remember(meta)
    if idempotency_scope:
        with _CODEX_ACTIVE_LOCK:
            _CODEX_RUN_IDEMPOTENCY[idempotency_scope] = {
                "runId": run_id,
                "agentId": agent_id,
                "conversationId": conversation_id,
                "idempotencyKey": idempotency_key,
                "ts": int(time.time() * 1000),
                "done": False,
                "result": None,
            }

    def enqueue(event_name, payload=None):
        PROVIDER_RUN_BRIDGE.emit(run_id, event_name, payload)

    def worker():
        enqueue("run.started", {"providerPath": "codex-app-server", "conversationId": conversation_id})
        progress_id = f"codex-progress-{run_id}"
        _append_codex_progress_comm_event(agent, agent.get("id") or agent_key, conversation_id, progress_id, {
            "runId": run_id,
            "status": "running",
            "thinking": "Waiting for Codex run events.",
        })
        if hasattr(gateway_presence, "set_provider_event"):
            gateway_presence.set_provider_event(status_key, "codex", {"event": "run.started", "run_id": run_id})

        def on_activity(record):
            progress_state = {
                "runId": run_id,
                "threadId": record.get("threadId") or meta.get("threadId") or "",
                "turnId": record.get("turnId") or meta.get("turnId") or "",
                "status": record.get("status") or "running",
                "reply": record.get("text") or "",
                "thinking": _provider_visible_thinking("codex", {**record, "thinking": record.get("text")}) if record.get("type") in {"reasoning", "thinking"} else "",
                "tools": [record] if record.get("type") in {"activity", "tool", "command"} else [],
                "approval": record if record.get("type") == "interaction" and record.get("status") == "pending" else None,
            }
            _append_codex_progress_comm_event(agent, agent.get("id") or agent_key, conversation_id, progress_id, progress_state)
            PROVIDER_RUN_BRIDGE.update(
                run_id,
                threadId=record.get("threadId") or meta.get("threadId") or "",
                turnId=record.get("turnId") or meta.get("turnId") or "",
            )
            event_name = _codex_activity_bridge_event_name(record)
            enqueue(event_name, _codex_stream_event_payload(run_id, agent, record))
            if hasattr(gateway_presence, "set_provider_event"):
                gateway_presence.set_provider_event(status_key, "codex", {
                    "event": event_name,
                    "run_id": run_id,
                    "thread_id": record.get("threadId") or "",
                    "turn_id": record.get("turnId") or "",
                    "status": record.get("status") or "",
                })

        run_body = dict(body)
        run_body["_streamRunId"] = run_id
        run_body["_onActivity"] = on_activity
        run_body.setdefault("fromType", "human")
        run_body.setdefault("fromDisplayName", "User")
        run_body.setdefault("sourceApp", "virtual-office")
        run_body.setdefault("sourceSurface", "chat-window")
        run_body.setdefault("sourceLabel", "Virtual Office Chat")
        try:
            result = _handle_codex_chat(run_body)
        except Exception as exc:
            result = {"ok": False, "status": "execution_failed", "error": str(exc), "_status": 500}
        _remove_comm_progress_events("codex-progress", progress_id, conversation_id)
        terminal_payload = _codex_stream_event_payload(run_id, agent, result=result, conversationId=conversation_id)
        status = str(result.get("status") or "").lower()
        if result.get("ok"):
            enqueue("run.completed", terminal_payload)
            presence_event = "run.completed"
        elif status in {"cancelled", "canceled"}:
            enqueue("run.cancelled", terminal_payload)
            presence_event = "run.cancelled"
        else:
            terminal_payload["error"] = result.get("error") or result.get("reply") or "Codex run failed"
            enqueue("run.failed", terminal_payload)
            presence_event = "run.failed"
        if hasattr(gateway_presence, "set_provider_event"):
            gateway_presence.set_provider_event(status_key, "codex", {"event": presence_event, "run_id": run_id, "error": terminal_payload.get("error") or ""})
        PROVIDER_RUN_BRIDGE.update(run_id, done=True, result=result)
        if idempotency_scope:
            with _CODEX_ACTIVE_LOCK:
                entry = _CODEX_RUN_IDEMPOTENCY.get(idempotency_scope)
                if entry:
                    entry["done"] = True
                    entry["result"] = result
                    entry["ts"] = int(time.time() * 1000)
        threading.Timer(600, PROVIDER_RUN_BRIDGE.clear, args=(run_id,)).start()

    threading.Thread(target=worker, daemon=True, name=f"codex-run-{run_id}").start()
    return {
        "ok": True,
        "runId": run_id,
        "providerPath": "codex-app-server",
        "conversationId": conversation_id,
        "idempotencyKey": idempotency_key,
        "agent": {"id": agent.get("id"), "name": agent.get("name"), "providerKind": "codex", "profile": profile},
    }


def _handle_codex_run_events(handler, run_id):
    PROVIDER_RUN_BRIDGE.stream_events(handler, run_id, "Codex")


def _handle_codex_run_stop(body):
    run_id = str(body.get("runId") or "").strip()
    meta = PROVIDER_RUN_BRIDGE.get(run_id)
    if meta:
        body = {**body, "agentId": body.get("agentId") or meta.get("agentId") or meta.get("agentKey") or "codex-local", "conversationId": body.get("conversationId") or meta.get("conversationId") or ""}
    result = _handle_codex_cancel(body)
    if meta:
        event_name = "run.cancelled" if result.get("ok") else "run.failed"
        PROVIDER_RUN_BRIDGE.emit(run_id, event_name, {
            "runId": run_id,
            "agentId": meta.get("agentId") or "",
            "profile": meta.get("profile") or "",
            "conversationId": meta.get("conversationId") or "",
            "status": result.get("status") or "",
            "error": result.get("error") or "",
            "providerPath": "codex-app-server",
        })
        PROVIDER_RUN_BRIDGE.update(run_id, done=True, result=result)
    return result


def _handle_codex_activity(query):
    agent_id = str((query.get("agentId") or ["codex-local"])[0])
    conversation_id = str((query.get("conversationId") or [""])[0])
    after = int((query.get("after") or [0])[0] or 0)
    if not conversation_id:
        return {"ok": False, "error": "conversationId is required", "_status": 400}
    active = _get_codex_active(agent_id)
    events = _get_codex_activity(agent_id, conversation_id, after)
    if not active or active.get("conversationId") != conversation_id:
        resolved = {
            (event.get("operationId"), event.get("interactionId"))
            for event in _get_codex_activity(agent_id, conversation_id, 0)
            if event.get("type") == "interaction" and event.get("status") == "resolved"
        }
        events = [
            {
                **event,
                "status": "unavailable",
                "error": "The original Codex process is no longer available; this interaction cannot be resumed.",
            }
            if event.get("type") == "interaction"
            and event.get("status") == "pending"
            and (event.get("operationId"), event.get("interactionId")) not in resolved
            else event
            for event in events
        ]
    return {
        "ok": True,
        "events": events,
        "active": active if active and active.get("conversationId") == conversation_id else None,
        "activeConversationId": (active or {}).get("conversationId", ""),
    }


def _handle_codex_interaction(body):
    agent_id = str(body.get("agentId") or "codex-local")
    conversation_id = str(body.get("conversationId") or "")
    interaction_id = str(body.get("interactionId") or "")
    action = str(body.get("action") or "")
    active = _get_codex_active(agent_id)
    if not active or active.get("conversationId") != conversation_id:
        return {"ok": False, "error": "No matching active Codex operation", "_status": 404}
    if not interaction_id or action not in {"accept", "acceptForSession", "decline", "cancel", "answer"}:
        return {"ok": False, "error": "Invalid interaction response", "_status": 400}
    provider = _codex_provider_from_config()
    protocol_action = "accept" if action == "answer" else action
    ok = provider.respond(active.get("threadId", ""), interaction_id, protocol_action, body.get("answers") or {})
    return {"ok": ok, "status": "submitted" if ok else "stale", "_status": 200 if ok else 409}


def _handle_codex_approval_pending(query_or_body=None):
    data = query_or_body if isinstance(query_or_body, dict) else {}
    def _first(value, fallback=""):
        if isinstance(value, list):
            return value[0] if value else fallback
        return value if value not in (None, "") else fallback
    agent_key = _first(data.get("agentId") or data.get("key") or data.get("sessionKey"), "codex-local")
    agent = _get_codex_agent(agent_key)
    if not agent:
        return {"ok": False, "error": f"Codex agent '{agent_key}' not found", "_status": 404}
    profile = agent.get("profile") or agent.get("providerAgentId") or "local"
    result = _codex_provider_from_config().pending_approval(profile)
    result.setdefault("ok", True)
    result.setdefault("profile", profile)
    result.setdefault("agentId", agent.get("id") or agent_key)
    return result


def _normalize_codex_approval_choice(choice):
    value = str(choice or "").strip().lower()
    if value in {"approve", "approved", "accept", "allow", "allow_once", "approve_once", "yes"}:
        return "approve"
    return "cancel"


def _codex_approval_result_message(approval, choice):
    approval = approval if isinstance(approval, dict) else {}
    normalized_choice = _normalize_codex_approval_choice(choice)
    status = "approved" if normalized_choice == "approve" else "cancelled"
    approval_id = str(approval.get("approval_id") or approval.get("approvalId") or approval.get("id") or "").strip()
    resolved = dict(approval)
    if approval_id:
        resolved.setdefault("id", approval_id)
        resolved.setdefault("approval_id", approval_id)
        resolved.setdefault("approvalId", approval_id)
    resolved["status"] = status
    return {
        "role": "assistant",
        "text": f"Codex approval {status}.",
        "approval": resolved,
        "tools": [],
        "thinking": "",
        "reasoningTokens": 0,
    }


def _codex_history_has_approval(conversation_id, agent_id, approval_id):
    if not conversation_id or not approval_id:
        return False
    for event in _load_comm_history(limit=1000, conversation_id=conversation_id, agent_id=agent_id):
        metadata = event.get("metadata") if isinstance(event, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        codex_meta = metadata.get("codex") if isinstance(metadata.get("codex"), dict) else {}
        approval = metadata.get("approval") if isinstance(metadata.get("approval"), dict) else {}
        candidates = {
            str(metadata.get("approvalId") or ""),
            str(metadata.get("approval_id") or ""),
            str(codex_meta.get("approvalId") or ""),
            str(codex_meta.get("approval_id") or ""),
            str(approval.get("approvalId") or ""),
            str(approval.get("approval_id") or ""),
            str(approval.get("id") or ""),
        }
        if str(approval_id) in candidates:
            return True
    return False


def _codex_approval_conversation_id(body, approval, agent_id, session_id):
    conversation_id = str(body.get("conversationId") or body.get("conversation_id") or approval.get("conversationId") or approval.get("conversation_id") or "").strip()
    if conversation_id:
        return conversation_id
    active = _get_codex_active(agent_id)
    active_thread = str((active or {}).get("threadId") or "")
    if active and (not session_id or session_id == active_thread):
        return str(active.get("conversationId") or "")
    return ""


def _append_codex_approval_result_comm_event(agent, agent_id, conversation_id, approval, choice):
    approval = approval if isinstance(approval, dict) else {}
    approval_id = str(approval.get("approval_id") or approval.get("approvalId") or approval.get("id") or "").strip()
    if not conversation_id or not approval_id:
        return None
    if _codex_history_has_approval(conversation_id, agent_id, approval_id):
        return None
    message = _codex_approval_result_message(approval, choice)
    resolved = message.get("approval") if isinstance(message.get("approval"), dict) else {}
    normalized_choice = _normalize_codex_approval_choice(choice)
    return _append_comm_event({
        "type": "message",
        "direction": "reply",
        "conversationId": conversation_id,
        "from": _office_agent_ref(agent_id),
        "to": {"id": "user", "providerKind": "human", "name": "User"},
        "text": message.get("text") or "",
        "metadata": {
            "providerKind": "codex",
            "event": "approval.responded",
            "approvalId": approval_id,
            "approvalChoice": normalized_choice,
            "threadId": resolved.get("threadId") or resolved.get("sessionId") or "",
            "turnId": resolved.get("turnId") or resolved.get("runId") or "",
            "approval": resolved,
            "codex": {
                "event": "approval.responded",
                "approvalId": approval_id,
                "approvalChoice": normalized_choice,
            },
        },
        "visibleInOffice": True,
        "ok": True,
    })


def _handle_codex_approval_respond(body):
    body = body if isinstance(body, dict) else {}
    approval = body.get("approval") if isinstance(body.get("approval"), dict) else {}
    agent_key = body.get("agentId") or body.get("key") or approval.get("agentId") or "codex-local"
    agent = _get_codex_agent(agent_key)
    if not agent:
        return {"ok": False, "error": f"Codex agent '{agent_key}' not found", "_status": 404}
    approval_id = str(body.get("approval_id") or body.get("approvalId") or approval.get("approval_id") or approval.get("id") or "").strip()
    if not approval_id:
        return {"ok": False, "error": "approvalId is required", "_status": 400}
    choice = str(body.get("choice") or body.get("action") or "cancel")
    session_id = str(body.get("sessionId") or body.get("session_id") or body.get("threadId") or approval.get("sessionId") or approval.get("session_id") or approval.get("threadId") or "").strip()
    profile = agent.get("profile") or agent.get("providerAgentId") or "local"
    result = _codex_provider_from_config().respond_approval(profile, approval_id, choice, session_id=session_id or None)
    normalized_choice = _normalize_codex_approval_choice(choice)
    agent_id = agent.get("id") or agent_key
    result_approval = result.get("approval") if isinstance(result.get("approval"), dict) else {}
    merged_approval = {
        **approval,
        **result_approval,
        "id": result_approval.get("id") or approval.get("id") or approval_id,
        "approval_id": result_approval.get("approval_id") or approval.get("approval_id") or approval_id,
        "approvalId": result_approval.get("approvalId") or approval.get("approvalId") or approval_id,
        "threadId": result_approval.get("threadId") or approval.get("threadId") or session_id,
        "turnId": result_approval.get("turnId") or approval.get("turnId") or result.get("turnId") or "",
        "status": "approved" if normalized_choice == "approve" else "cancelled",
    }
    conversation_id = _codex_approval_conversation_id(body, merged_approval, agent_id, session_id)
    result_message = _codex_approval_result_message(merged_approval, normalized_choice)
    history_event = None
    if result.get("ok"):
        history_event = _append_codex_approval_result_comm_event(agent, agent_id, conversation_id, merged_approval, normalized_choice)
        status_key = agent.get("statusKey") or agent_id
        if hasattr(gateway_presence, "set_provider_event"):
            gateway_presence.set_provider_event(status_key, "codex", {
                "event": "approval.responded",
                "provider": "codex",
                "approval_id": approval_id,
                "approvalId": approval_id,
                "thread_id": merged_approval.get("threadId") or "",
                "threadId": merged_approval.get("threadId") or "",
                "turn_id": merged_approval.get("turnId") or "",
                "turnId": merged_approval.get("turnId") or "",
                "choice": normalized_choice,
                "status": merged_approval.get("status") or "",
                "conversationId": conversation_id,
            })
    result.setdefault("profile", profile)
    result.setdefault("agentId", agent_id)
    result.setdefault("approvalId", approval_id)
    result.setdefault("approval_id", approval_id)
    result.setdefault("choice", normalized_choice)
    result.setdefault("approvalChoice", normalized_choice)
    result["approval"] = merged_approval
    result.setdefault("message", result_message)
    result.setdefault("historyEventId", (history_event or {}).get("id") or "")
    result.setdefault("conversationId", conversation_id)
    result.setdefault("providerPath", "codex-app-server")
    status = str(result.get("status") or "").lower()
    result["_status"] = 200 if result.get("ok") else 409 if status in {"stale", "not_found"} else 500
    return result


def _handle_codex_cancel(body):
    agent_id = str(body.get("agentId") or "codex-local")
    conversation_id = str(body.get("conversationId") or "")
    active = _get_codex_active(agent_id)
    if not active or (conversation_id and active.get("conversationId") != conversation_id):
        return {"ok": False, "error": "No matching active Codex operation", "_status": 404}
    provider = _codex_provider_from_config()
    requested_workspace = str(body.get("workspace") or "").strip()
    if requested_workspace:
        provider.workspace = os.path.realpath(os.path.expanduser(requested_workspace))
    ok = provider.cancel(active.get("threadId", ""))
    return {"ok": ok, "status": "cancelling" if ok else "stale", "_status": 200 if ok else 409}


def _handle_codex_reset(body):
    agent_key = body.get("agentId") or body.get("key") or "codex-local"
    conversation_id = str(body.get("conversationId") or "").strip()
    agent = _get_codex_agent(agent_key)
    if not agent:
        return {"ok": False, "error": f"Codex agent '{agent_key}' not found", "_status": 404}
    if not conversation_id:
        return {"ok": False, "error": "conversationId is required", "_status": 400}
    agent_id = agent.get("id") or agent_key
    if _codex_operation_lock(agent_id).locked():
        return {"ok": False, "status": "busy", "error": "Codex is already working", "_status": 409}
    removed = _reset_codex_thread_id(agent_id, conversation_id)
    return {"ok": True, "reset": removed, "conversationId": conversation_id}


def _handle_codex_compact(body):
    agent_key = body.get("agentId") or body.get("key") or "codex-local"
    conversation_id = str(body.get("conversationId") or "").strip()
    agent = _get_codex_agent(agent_key)
    if not agent:
        return {"ok": False, "error": f"Codex agent '{agent_key}' not found", "_status": 404}
    if not conversation_id:
        return {"ok": False, "error": "conversationId is required", "_status": 400}
    agent_id = agent.get("id") or agent_key
    thread_id = _get_codex_thread_id(agent_id, conversation_id)
    if not thread_id:
        return {"ok": False, "status": "not_found", "error": "No Codex context exists for this conversation", "_status": 404}
    operation_lock = _codex_operation_lock(agent_id)
    if not operation_lock.acquire(blocking=False):
        return {"ok": False, "status": "busy", "error": "Codex is already working", "_status": 409}
    gateway_presence.set_manual_override(agent_id, "working", "Compressing Codex context")
    try:
        result = _codex_provider_from_config().compact_context(thread_id, int(body.get("timeoutSec") or 120))
    finally:
        gateway_presence.set_manual_override(agent_id, "idle", "")
        operation_lock.release()
    event = _append_comm_event({
        "type": "operation",
        "operation": "context_compaction",
        "direction": "system",
        "conversationId": conversation_id,
        "from": _office_agent_ref(agent_id),
        "to": {"id": "user", "providerKind": "human", "name": "User"},
        "text": result.get("reply") or result.get("error") or "Codex context compression finished",
        "metadata": {
            "status": result.get("status"),
            "threadId": thread_id,
            "durationMs": result.get("durationMs"),
        },
        "visibleInOffice": True,
        "ok": bool(result.get("ok")),
    })
    return {**result, "conversationId": conversation_id, "eventId": event.get("id"), "_status": 200 if result.get("ok") else 500}




def _codex_history_path(profile="default"):
    safe_profile = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(profile or "default"))[:80] or "default"
    return os.path.join(STATUS_DIR, f"codex-chat-{safe_profile}.json")


def _load_codex_state(profile="default"):
    path = _codex_history_path(profile)
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("profile", profile)
            data.setdefault("messages", [])
            return data
        if isinstance(data, list):
            return {"profile": profile, "messages": data}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {"profile": profile, "messages": []}


def _load_codex_history(profile="default"):
    state = _load_codex_state(profile)
    messages = state.get("messages") if isinstance(state.get("messages"), list) else []
    return messages


def _save_codex_state(profile, state):
    state = state if isinstance(state, dict) else {}
    state["profile"] = profile
    if not isinstance(state.get("messages"), list):
        state["messages"] = []
    path = _codex_history_path(profile)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _save_codex_history(profile, messages):
    state = _load_codex_state(profile)
    state["messages"] = (messages or [])[-500:]
    _save_codex_state(profile, state)


def _get_codex_session_id(profile="default"):
    state = _load_codex_state(profile)
    session_id = state.get("sessionId") or state.get("threadId") or state.get("session_id")
    return str(session_id).strip() if session_id else ""


def _set_codex_session_id(profile="default", session_id=""):
    state = _load_codex_state(profile)
    if session_id:
        state["sessionId"] = session_id
        state["threadId"] = session_id
    else:
        state.pop("sessionId", None)
        state.pop("threadId", None)
    _save_codex_state(profile, state)


def _set_codex_active_run(profile="default", session_id="", run_id=""):
    state = _load_codex_state(profile)
    if run_id:
        state["activeRunId"] = run_id
        state["activeSessionId"] = session_id or state.get("sessionId") or ""
        state["activeRunUpdatedAt"] = int(time.time() * 1000)
    else:
        state.pop("activeRunId", None)
        state.pop("activeSessionId", None)
        state.pop("activeRunUpdatedAt", None)
    _save_codex_state(profile, state)


def _get_codex_token_usage(profile="default"):
    state = _load_codex_state(profile)
    token_usage = state.get("tokenUsage") if isinstance(state.get("tokenUsage"), dict) else {}
    return token_usage


def _set_codex_token_usage(profile="default", token_usage=None):
    token_usage = token_usage if isinstance(token_usage, dict) else {}
    state = _load_codex_state(profile)
    if token_usage:
        state["tokenUsage"] = token_usage
        context_used = _provider_context_used_from_token_usage(token_usage)
        context_window = _provider_context_window_from_token_usage(token_usage)
        if context_used:
            state["contextUsed"] = context_used
        if context_window:
            state["contextWindow"] = context_window
    else:
        state.pop("tokenUsage", None)
    _save_codex_state(profile, state)


def _clear_codex_token_usage(profile="default"):
    state = _load_codex_state(profile)
    state.pop("tokenUsage", None)
    state.pop("contextUsed", None)
    state.pop("contextWindow", None)
    _save_codex_state(profile, state)


def _claude_code_provider_from_config():
    cfg = VO_CONFIG.get("claudeCode", {})
    return ClaudeCodeProvider(
        enabled=cfg.get("enabled", False),
        home_path=cfg.get("homePath"),
        binary=cfg.get("binary"),
        workspace=cfg.get("workspace"),
        workspace_root=cfg.get("workspaceRoot"),
        main_workspace=cfg.get("mainWorkspace"),
        name=cfg.get("name"),
        agent_id=cfg.get("agentId"),
        model=cfg.get("model"),
        reply_text=cfg.get("replyText") or os.environ.get("VO_CLAUDE_CODE_REPLY_TEXT"),
        timeout_sec=int(cfg.get("timeoutSec") or 900),
        permission_mode=cfg.get("permissionMode", "acceptEdits"),
        include_main=cfg.get("includeMain", True),
        include_native_agents=cfg.get("includeNativeAgents", True),
        register_native_agents=cfg.get("registerNativeAgents", True),
    )


def _claude_code_history_path(profile="local", conversation_id=None):
    safe_profile = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(profile or "local"))[:80] or "local"
    if conversation_id:
        raw = str(conversation_id)
        safe_conversation = re.sub(r"[^a-zA-Z0-9_.-]+", "-", raw)[:80].strip(".-") or "conversation"
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
        return os.path.join(STATUS_DIR, f"claude-code-chat-{safe_profile}-conv-{safe_conversation}-{digest}.json")
    return os.path.join(STATUS_DIR, f"claude-code-chat-{safe_profile}.json")


def _load_claude_code_state(profile="local", conversation_id=None):
    path = _claude_code_history_path(profile, conversation_id)
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {"profile": profile, "conversationId": conversation_id or "", "messages": []}


def _load_claude_code_history(profile="local", conversation_id=None):
    state = _load_claude_code_state(profile, conversation_id)
    messages = state.get("messages") if isinstance(state.get("messages"), list) else []
    return messages


def _sanitize_claude_code_history_messages(messages):
    cleaned = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        item = dict(msg)
        item["thinking"] = _claude_code_visible_thinking(item)
        cleaned.append(item)
    return cleaned


def _save_claude_code_history(profile, messages, conversation_id=None, session_id=""):
    path = _claude_code_history_path(profile, conversation_id)
    state = _load_claude_code_state(profile, conversation_id)
    state["profile"] = profile
    state["messages"] = messages[-500:]
    if conversation_id:
        state["conversationId"] = conversation_id
    else:
        state.pop("conversationId", None)
    if session_id:
        state["sessionId"] = session_id
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
        try:
            os.chmod(path, 0o666)
        except OSError:
            pass
    except OSError as e:
        print(f"[CLAUDE-CODE] Failed to save history: {e}")


def _get_claude_code_session_id(profile="local", conversation_id=None):
    state = _load_claude_code_state(profile, conversation_id)
    session_id = state.get("sessionId") or state.get("session_id")
    return str(session_id).strip() if session_id else ""


def _get_claude_code_token_usage(profile="local", conversation_id=None):
    state = _load_claude_code_state(profile, conversation_id)
    return state.get("tokenUsage") if isinstance(state.get("tokenUsage"), dict) else {}


def _set_claude_code_token_usage(profile="local", token_usage=None, conversation_id=None):
    token_usage = token_usage if isinstance(token_usage, dict) else {}
    state = _load_claude_code_state(profile, conversation_id)
    if token_usage:
        state["tokenUsage"] = token_usage
        context_used = _provider_context_used_from_token_usage(token_usage)
        context_window = _provider_context_window_from_token_usage(token_usage)
        if context_used:
            state["contextUsed"] = context_used
        if context_window:
            state["contextWindow"] = context_window
    else:
        state.pop("tokenUsage", None)
    _save_claude_code_history(profile, state.get("messages") or [], conversation_id, state.get("sessionId") or "")


def _clear_claude_code_token_usage(profile="local", conversation_id=None):
    state = _load_claude_code_state(profile, conversation_id)
    state.pop("tokenUsage", None)
    state.pop("contextUsed", None)
    state.pop("contextWindow", None)
    _save_claude_code_history(profile, state.get("messages") or [], conversation_id, state.get("sessionId") or "")


def _codex_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _provider_context_used_from_token_usage(token_usage):
    if not isinstance(token_usage, dict):
        return 0
    for key in ("total_tokens", "totalTokens", "tokens", "contextUsed"):
        value = token_usage.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    total = 0
    for key in ("input_tokens", "inputTokens", "prompt_tokens", "promptTokens", "output_tokens", "outputTokens", "completion_tokens", "completionTokens"):
        value = token_usage.get(key)
        if isinstance(value, (int, float)):
            total += int(value)
    return total


def _provider_context_window_from_token_usage(token_usage):
    if not isinstance(token_usage, dict):
        return 0
    for key in ("context_window", "contextWindow", "max_context_tokens", "maxContextTokens"):
        value = token_usage.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def _codex_context_used_from_token_usage(token_usage):
    return _provider_context_used_from_token_usage(token_usage)


def _codex_context_window_from_token_usage(token_usage):
    return _provider_context_window_from_token_usage(token_usage)


def _provider_visible_thinking(provider_kind, run_state):
    run_state = run_state if isinstance(run_state, dict) else {}
    thinking = str(run_state.get("thinking") or "").strip()
    status = str(run_state.get("status") or "").strip().lower()
    if not thinking or thinking.lower() == status:
        return ""
    terminal_or_status = {"queued", "starting", "running", "completed", "complete", "done", "success", "failed", "error", "execution_failed", "cancelled", "canceled"}
    if thinking.lower() in terminal_or_status:
        return ""
    provider = str(provider_kind or "").lower()
    if provider == "claude-code" and thinking.lower() in {"claude code completed.", "claude code completed"}:
        return ""
    if provider == "codex" and thinking.lower() in {"codex run 已完成", "codex run 未完成", "codex run 正在执行", "codex run 正在取消", "waiting for codex run events."}:
        return ""
    return thinking


PROVIDER_PROGRESS_MAX_AGE_MS = 120000
PROVIDER_PROGRESS_TERMINAL_STATUSES = {"completed", "complete", "done", "success", "failed", "error", "execution_failed", "cancelled", "canceled"}


def _provider_progress_status(progress):
    progress = progress if isinstance(progress, dict) else {}
    status = str(progress.get("status") or "").strip().lower()
    if not status and progress.get("error"):
        status = "failed"
    return status


def _is_recoverable_provider_progress(progress, now_ms=None):
    progress = progress if isinstance(progress, dict) else {}
    if _provider_progress_status(progress) in PROVIDER_PROGRESS_TERMINAL_STATUSES:
        return False
    if progress.get("active") or progress.get("activeRunId") or progress.get("runActive") or progress.get("activeConversationId"):
        return True
    try:
        ts = int(progress.get("ts") or progress.get("epochMs") or progress.get("updatedAt") or progress.get("startedAt") or 0)
    except (TypeError, ValueError):
        ts = 0
    if ts > 0 and int(now_ms or time.time() * 1000) - ts > PROVIDER_PROGRESS_MAX_AGE_MS:
        return False
    return True


def _filter_recoverable_provider_progress_messages(messages):
    result = []
    now_ms = int(time.time() * 1000)
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        marker = msg.get("ephemeral")
        if marker in {"codex-progress", "claude-code-progress", "hermes-progress"} and not _is_recoverable_provider_progress(msg, now_ms):
            continue
        result.append(msg)
    return result


def _filter_recoverable_comm_progress_events(events):
    result = []
    now_ms = int(time.time() * 1000)
    for event in events or []:
        if not isinstance(event, dict):
            continue
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        marker = metadata.get("ephemeral") or event.get("ephemeral")
        progress = metadata.get("progress") if isinstance(metadata.get("progress"), dict) else event
        if marker in {"codex-progress", "claude-code-progress", "hermes-progress"} and not _is_recoverable_provider_progress(progress, now_ms):
            continue
        result.append(event)
    return result


def _provider_progress_message(
    provider_kind,
    agent_id,
    progress_id,
    run_state,
    conversation_id=None,
    default_thinking="",
):
    run_state = run_state if isinstance(run_state, dict) else {}
    token_usage = run_state.get("tokenUsage") if isinstance(run_state.get("tokenUsage"), dict) else {}
    session_id = run_state.get("sessionId") or run_state.get("threadId") or ""
    run_id = run_state.get("runId") or run_state.get("turnId") or session_id or progress_id
    progress_message = {
        "role": "assistant",
        "text": run_state.get("reply") or run_state.get("text") or "",
        "reply": run_state.get("reply") or run_state.get("text") or "",
        "ts": int(time.time() * 1000),
        "agentId": agent_id,
        "ephemeral": f"{provider_kind}-progress",
        "progressId": progress_id,
        "sessionId": session_id,
        "threadId": run_state.get("threadId") or session_id,
        "turnId": run_state.get("turnId") or run_state.get("runId") or "",
        "runId": run_id,
        "status": run_state.get("status") or "",
        "tools": run_state.get("tools") or [],
        "thinking": _provider_visible_thinking(provider_kind, {**run_state, "thinking": run_state.get("thinking") or default_thinking}),
        "reasoningTokens": run_state.get("reasoningTokens") or 0,
        "error": run_state.get("error") or None,
        "conversationId": conversation_id or "",
    }
    if run_state.get("approval"):
        progress_message["approval"] = run_state.get("approval")
    if token_usage:
        progress_message["tokenUsage"] = token_usage
        progress_message["contextUsed"] = _provider_context_used_from_token_usage(token_usage)
        context_window = _provider_context_window_from_token_usage(token_usage)
        if context_window:
            progress_message["contextWindow"] = context_window
    return progress_message


def _upsert_ephemeral_message(messages, ephemeral, progress_id, progress_message):
    cleaned = [
        msg for msg in (messages or [])
        if not (
            isinstance(msg, dict)
            and msg.get("ephemeral") == ephemeral
            and (not progress_id or msg.get("progressId") == progress_id)
        )
    ]
    cleaned.append(progress_message)
    return cleaned


def _remove_provider_progress_messages(messages, provider_kind=None, progress_id=None):
    markers = {f"{provider_kind}-progress"} if provider_kind else {"codex-progress", "claude-code-progress", "hermes-progress"}
    result = []
    for msg in messages or []:
        if not isinstance(msg, dict) or msg.get("ephemeral") not in markers:
            result.append(msg)
            continue
        if progress_id and msg.get("progressId") != progress_id:
            result.append(msg)
    return result


def _set_claude_code_session_id(profile="local", session_id="", conversation_id=None):
    path = _claude_code_history_path(profile, conversation_id)
    state = _load_claude_code_state(profile, conversation_id)
    state["sessionId"] = session_id or ""
    state.setdefault("messages", [])
    state["updatedAt"] = int(time.time() * 1000)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)
    try:
        os.chmod(path, 0o666)
    except OSError:
        pass


def _set_claude_code_active_run(profile="local", session_id="", run_id="", conversation_id=None):
    path = _claude_code_history_path(profile, conversation_id)
    state = _load_claude_code_state(profile, conversation_id)
    state["sessionId"] = session_id or state.get("sessionId") or ""
    state["runId"] = run_id or ""
    state.setdefault("messages", [])
    state["updatedAt"] = int(time.time() * 1000)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)
    try:
        os.chmod(path, 0o666)
    except OSError:
        pass


def _publish_claude_code_progress(profile, agent_id, progress_id, run_state, conversation_id=None):
    if not progress_id:
        return
    run_state = run_state if isinstance(run_state, dict) else {}
    history = _load_claude_code_history(profile, conversation_id)
    session_id = run_state.get("sessionId") or run_state.get("threadId") or _get_claude_code_session_id(profile, conversation_id) or ""
    run_state = {**run_state, "sessionId": session_id, "runId": run_state.get("runId") or session_id}
    progress_message = _provider_progress_message("claude-code", agent_id, progress_id, run_state, conversation_id, "Waiting for Claude Code stream events.")
    history = _upsert_ephemeral_message(history, "claude-code-progress", progress_id, progress_message)
    _save_claude_code_history(profile, history, conversation_id, session_id)
    if session_id or progress_message.get("runId"):
        _set_claude_code_active_run(profile, session_id, progress_message.get("runId") or "", conversation_id)


def _remove_claude_code_progress_messages(messages):
    return _remove_provider_progress_messages(messages, "claude-code")


class ProviderRunBridge:
    """Provider-neutral run registry and SSE event distributor."""

    def __init__(self):
        self._lock = threading.Lock()
        self._runs = {}

    def remember(self, meta):
        if not isinstance(meta, dict) or not meta.get("runId"):
            return
        with self._lock:
            self._runs[str(meta["runId"])] = meta

    def get(self, run_id):
        with self._lock:
            meta = self._runs.get(str(run_id or ""))
            return meta if isinstance(meta, dict) else None

    def clear(self, run_id):
        with self._lock:
            self._runs.pop(str(run_id or ""), None)

    def update(self, run_id, **updates):
        with self._lock:
            meta = self._runs.get(str(run_id or ""))
            if isinstance(meta, dict):
                meta.update({k: v for k, v in updates.items() if v is not None})
            return meta if isinstance(meta, dict) else None

    def emit(self, run_id, event_name, payload=None):
        meta = self.get(run_id)
        if not meta:
            return False
        events = meta.get("events")
        if not isinstance(events, queue.Queue):
            return False
        payload = payload if isinstance(payload, dict) else {}
        payload.setdefault("runId", run_id)
        payload.setdefault("agentId", meta.get("agentId") or "")
        payload.setdefault("profile", meta.get("profile") or "")
        try:
            events.put_nowait({"event": event_name, "data": payload, "ts": int(time.time() * 1000)})
            return True
        except Exception:
            return False

    def stream_events(self, handler, run_id, missing_provider_label="Provider"):
        meta = self.get(run_id)
        if not meta:
            handler.send_response(404)
            handler.send_header("Content-Type", "text/event-stream")
            handler.send_header("Cache-Control", "no-cache")
            handler.send_header("Access-Control-Allow-Origin", "*")
            handler.end_headers()
            payload = json.dumps({"error": f"{missing_provider_label} run not found"}, ensure_ascii=False)
            handler.wfile.write(f"event: run.failed\ndata: {payload}\n\n".encode("utf-8"))
            return

        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "keep-alive")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()

        events = meta.get("events")
        if not isinstance(events, queue.Queue):
            return

        last_keepalive = time.time()
        try:
            while True:
                try:
                    item = events.get(timeout=0.5)
                except queue.Empty:
                    if meta.get("done") and events.empty():
                        result = meta.get("result") if isinstance(meta.get("result"), dict) else {}
                        status = str(result.get("status") or "").lower()
                        event_name = "run.completed" if result.get("ok") else ("run.cancelled" if status in {"cancelled", "canceled"} else "run.failed")
                        payload = result if isinstance(result, dict) else {}
                        payload = dict(payload)
                        payload.setdefault("runId", run_id)
                        payload.setdefault("agentId", meta.get("agentId") or "")
                        payload.setdefault("profile", meta.get("profile") or "")
                        encoded = json.dumps(payload, ensure_ascii=False, default=str)
                        handler.wfile.write(f"event: {event_name}\ndata: {encoded}\n\n".encode("utf-8"))
                        handler.wfile.flush()
                        break
                    if time.time() - last_keepalive >= 10:
                        handler.wfile.write(b": keepalive\n\n")
                        handler.wfile.flush()
                        last_keepalive = time.time()
                    continue

                event_name = str(item.get("event") or "message")
                payload = item.get("data") if isinstance(item.get("data"), dict) else {}
                encoded = json.dumps(payload, ensure_ascii=False, default=str)
                handler.wfile.write(f"event: {event_name}\ndata: {encoded}\n\n".encode("utf-8"))
                handler.wfile.flush()
                if event_name in {"run.completed", "run.failed", "run.cancelled", "run.canceled"}:
                    break
        except (BrokenPipeError, ConnectionError, OSError):
            pass
        finally:
            if meta.get("done"):
                self.clear(run_id)


PROVIDER_RUN_BRIDGE = ProviderRunBridge()
CLAUDE_CODE_STREAM_RUNS_LOCK = PROVIDER_RUN_BRIDGE._lock
CLAUDE_CODE_STREAM_RUNS = PROVIDER_RUN_BRIDGE._runs


def _remember_claude_code_stream_run(meta):
    PROVIDER_RUN_BRIDGE.remember(meta)


def _get_claude_code_stream_run(run_id):
    return PROVIDER_RUN_BRIDGE.get(run_id)


def _clear_claude_code_stream_run(run_id):
    PROVIDER_RUN_BRIDGE.clear(run_id)


def _claude_code_visible_thinking(run_state):
    return _provider_visible_thinking("claude-code", run_state)


def _claude_code_stream_event_payload(run_id, agent, profile, run_state=None, **extra):
    run_state = run_state if isinstance(run_state, dict) else {}
    token_usage = run_state.get("tokenUsage") if isinstance(run_state.get("tokenUsage"), dict) else {}
    payload = {
        "runId": run_id,
        "agentId": (agent or {}).get("id") or "",
        "profile": profile or "",
        "sessionId": run_state.get("sessionId") or run_state.get("threadId") or _get_claude_code_session_id(profile) or "",
        "turnId": run_state.get("runId") or run_state.get("sessionId") or "",
        "reply": run_state.get("reply") or "",
        "tools": run_state.get("tools") or [],
        "thinking": _claude_code_visible_thinking(run_state),
        "error": run_state.get("error") or "",
        "status": run_state.get("status") or "",
        "providerPath": "claude-code-cli",
    }
    if token_usage:
        payload["tokenUsage"] = token_usage
        payload["contextUsed"] = _provider_context_used_from_token_usage(token_usage)
        context_window = _provider_context_window_from_token_usage(token_usage)
        if context_window:
            payload["contextWindow"] = context_window
    payload.update({k: v for k, v in extra.items() if v is not None})
    return payload


def _claude_code_tool_stream_key(tool, idx=0):
    if not isinstance(tool, dict):
        return f"claude-code-tool-{idx}"
    return str(tool.get("id") or f"{idx}:{tool.get('name') or 'tool'}:{json.dumps(tool.get('arguments') or {}, sort_keys=True, default=str)[:120]}")


def _handle_claude_code_run_start(body):
    """Start a Claude Code message in the background and expose progress over SSE."""
    message = (body.get("message") or "").strip()
    agent_key = body.get("agentId") or body.get("key") or body.get("sessionKey") or "claude-code-local"
    if not message:
        return {"ok": False, "error": "message is required", "_status": 400}

    agent = _get_claude_code_agent(agent_key)
    if not agent:
        return {"ok": False, "error": f"Claude Code agent '{agent_key}' not found", "_status": 404}

    profile = agent.get("profile") or agent.get("providerAgentId") or "local"
    conversation_id = str(body.get("conversationId") or body.get("threadId") or "").strip()
    agent_id = agent.get("id") or agent_key
    idempotency_key = _provider_run_idempotency_key(body)
    idempotency_scope = _provider_run_idempotency_scope("claude-code", agent_id, conversation_id, idempotency_key) if idempotency_key else ""
    if idempotency_scope:
        with _CODEX_ACTIVE_LOCK:
            _prune_provider_run_idempotency()
            existing = _PROVIDER_RUN_IDEMPOTENCY.get(idempotency_scope)
            if existing:
                return _provider_run_duplicate_response("claude-code", conversation_id, idempotency_key, existing)

    run_id = f"claude-code-{int(time.time() * 1000)}-{str(uuid.uuid4())[:8]}"
    progress_id = f"claude-code-progress-{run_id}"
    events = queue.Queue()
    status_key = agent.get("statusKey") or agent.get("id")
    meta = {
        "runId": run_id,
        "agentId": agent.get("id"),
        "agentKey": agent_key,
        "profile": profile,
        "statusKey": status_key,
        "conversationId": conversation_id,
        "events": events,
        "startedAt": int(time.time() * 1000),
        "done": False,
        "result": None,
        "idempotencyKey": idempotency_key,
    }
    _remember_claude_code_stream_run(meta)
    _register_provider_run_idempotency(idempotency_scope, run_id, "claude-code", agent_id, conversation_id, idempotency_key, "claude-code-cli")

    def enqueue(event_name, payload=None):
        PROVIDER_RUN_BRIDGE.emit(run_id, event_name, payload)

    def worker():
        last_reply = ""
        last_thinking = ""
        last_token_usage_signature = ""
        seen_tools = {}
        enqueue("run.started", {"providerPath": "claude-code-cli"})
        _publish_claude_code_progress(profile, agent.get("id") or agent_key, progress_id, {
            "runId": run_id,
            "status": "running",
            "thinking": "Waiting for Claude Code stream events.",
        }, conversation_id)
        if hasattr(gateway_presence, "set_provider_event"):
            gateway_presence.set_provider_event(status_key, "claude-code", {"event": "run.started", "run_id": run_id})

        def on_progress(run_state):
            nonlocal last_reply, last_thinking, last_token_usage_signature
            run_state = run_state if isinstance(run_state, dict) else {}
            PROVIDER_RUN_BRIDGE.update(
                run_id,
                sessionId=run_state.get("sessionId") or run_state.get("threadId") or meta.get("sessionId") or "",
                turnId=run_state.get("runId") or meta.get("turnId") or "",
            )
            _publish_claude_code_progress(profile, agent.get("id") or agent_key, progress_id, {
                **run_state,
                "runId": run_id,
                "turnId": run_state.get("runId") or meta.get("turnId") or "",
            }, conversation_id)
            if hasattr(gateway_presence, "set_provider_event"):
                gateway_presence.set_provider_event(status_key, "claude-code", {
                    "event": "turn.stream",
                    "session_id": run_state.get("sessionId") or run_state.get("threadId") or "",
                    "run_id": run_state.get("runId") or run_id,
                    "status": run_state.get("status") or "",
                })

            token_usage = run_state.get("tokenUsage") if isinstance(run_state.get("tokenUsage"), dict) else {}
            if token_usage:
                token_usage_signature = json.dumps(token_usage, sort_keys=True, default=str)
                if token_usage_signature != last_token_usage_signature:
                    last_token_usage_signature = token_usage_signature
                    enqueue("session.metrics", _claude_code_stream_event_payload(run_id, agent, profile, run_state))

            reply = str(run_state.get("reply") or "")
            if reply and reply != last_reply:
                delta = reply[len(last_reply):] if reply.startswith(last_reply) else ""
                last_reply = reply
                enqueue("message.delta", _claude_code_stream_event_payload(run_id, agent, profile, run_state, delta=delta))

            thinking = _claude_code_visible_thinking(run_state)
            if thinking and thinking != last_thinking:
                last_thinking = thinking
                enqueue("reasoning.available", _claude_code_stream_event_payload(run_id, agent, profile, run_state))

            for idx, tool in enumerate(run_state.get("tools") or []):
                if not isinstance(tool, dict):
                    continue
                key = _claude_code_tool_stream_key(tool, idx)
                status = str(tool.get("status") or "").lower()
                is_terminal = status in {"done", "error", "failed"}
                prior = seen_tools.get(key)
                if not prior:
                    enqueue("tool.started", _claude_code_stream_event_payload(run_id, agent, profile, run_state, toolCard=tool, toolCallId=key))
                    if hasattr(gateway_presence, "set_provider_event"):
                        gateway_presence.set_provider_event(status_key, "claude-code", {"event": "tool.started", "run_id": run_id, "toolCallId": key, "name": tool.get("name") or "Claude tool"})
                if is_terminal and (not prior or prior.get("status") != status or prior.get("result") != tool.get("result") or prior.get("error") != tool.get("error")):
                    event_name = "tool.failed" if status in {"error", "failed"} or tool.get("error") else "tool.completed"
                    enqueue(event_name, _claude_code_stream_event_payload(run_id, agent, profile, run_state, toolCard=tool, toolCallId=key))
                    if hasattr(gateway_presence, "set_provider_event"):
                        gateway_presence.set_provider_event(status_key, "claude-code", {"event": event_name, "run_id": run_id, "toolCallId": key, "name": tool.get("name") or "Claude tool"})
                seen_tools[key] = dict(tool)

        run_body = dict(body)
        run_body["_streamRunId"] = run_id
        run_body["_streamProgressId"] = progress_id
        run_body["_onProgress"] = on_progress
        try:
            result = _handle_claude_code_chat(run_body)
        except Exception as exc:
            result = {"ok": False, "error": str(exc), "_status": 500}
        history = _remove_claude_code_progress_messages(_load_claude_code_history(profile, conversation_id))
        _save_claude_code_history(profile, history, conversation_id, result.get("sessionId") or _get_claude_code_session_id(profile, conversation_id) or "")
        token_usage = result.get("tokenUsage") if isinstance(result.get("tokenUsage"), dict) else {}
        payload = {
            "runId": run_id,
            "agentId": agent.get("id") or "",
            "profile": profile,
            "sessionId": result.get("sessionId") or _get_claude_code_session_id(profile, conversation_id) or "",
            "turnId": result.get("runId") or result.get("sessionId") or meta.get("turnId") or "",
            "reply": result.get("reply") or "",
            "tools": result.get("tools") or [],
            "thinking": result.get("thinking") or "",
            "tokenUsage": token_usage,
            "contextUsed": _provider_context_used_from_token_usage(token_usage),
            "contextWindow": _provider_context_window_from_token_usage(token_usage),
            "providerPath": result.get("providerPath") or "claude-code-cli",
        }
        if result.get("ok"):
            enqueue("run.completed", payload)
            if hasattr(gateway_presence, "set_provider_event"):
                gateway_presence.set_provider_event(status_key, "claude-code", {"event": "run.completed", "run_id": run_id})
        else:
            payload["error"] = result.get("error") or result.get("reply") or "Claude Code run failed"
            enqueue("run.failed", payload)
            if hasattr(gateway_presence, "set_provider_event"):
                gateway_presence.set_provider_event(status_key, "claude-code", {"event": "run.failed", "run_id": run_id, "error": payload["error"]})
        PROVIDER_RUN_BRIDGE.update(run_id, done=True, result=result)
        _finish_provider_run_idempotency(idempotency_scope, result)
        threading.Timer(600, _clear_claude_code_stream_run, args=(run_id,)).start()

    threading.Thread(target=worker, daemon=True, name=f"claude-code-run-{run_id}").start()
    return {
        "ok": True,
        "runId": run_id,
        "providerPath": "claude-code-cli",
        "conversationId": conversation_id,
        "idempotencyKey": idempotency_key,
        "agent": {"id": agent.get("id"), "name": agent.get("name"), "providerKind": "claude-code", "profile": profile},
    }


def _handle_claude_code_run_events(handler, run_id):
    PROVIDER_RUN_BRIDGE.stream_events(handler, run_id, "Claude Code")


def _handle_claude_code_interrupt(body):
    body = body or {}
    agent_key = body.get("agentId") or body.get("key") or body.get("sessionKey") or "claude-code-local"
    conversation_id = str(body.get("conversationId") or body.get("threadId") or "").strip()
    agent = _get_claude_code_agent(agent_key)
    if not agent:
        return {"ok": False, "error": f"Claude Code agent '{agent_key}' not found", "_status": 404}
    result = _handle_claude_code_cancel(body)
    profile = agent.get("profile") or agent.get("providerAgentId") or "local"
    history = _load_claude_code_history(profile, conversation_id)
    history.append({
        "role": "assistant",
        "text": "Claude Code run interrupted.",
        "ts": int(time.time() * 1000),
        "agentId": agent.get("id"),
        "ephemeral": "claude-code-progress",
        "progressId": f"claude-code-interrupt-{int(time.time() * 1000)}",
        "error": result.get("error") or "",
    })
    _save_claude_code_history(profile, history, conversation_id, _get_claude_code_session_id(profile, conversation_id))
    return result


def _handle_claude_code_history_clear(body):
    body = body or {}
    agent = _get_claude_code_agent(body.get("agentId") or body.get("key") or "claude-code-main") or {}
    profile = agent.get("profile") or agent.get("providerAgentId") or "main"
    conversation_id = str(body.get("conversationId") or "").strip()
    session_id = _get_claude_code_session_id(profile, conversation_id)
    _save_claude_code_history(profile, [], conversation_id, "")
    _set_claude_code_session_id(profile, "", conversation_id)
    _clear_claude_code_token_usage(profile, conversation_id)
    return {
        "ok": True,
        "clearedClaudeCodeSession": bool(session_id),
        "sessionId": session_id,
        "conversationId": conversation_id,
        "profile": profile,
    }


def _handle_claude_code_chat(body):
    message = (body.get("message") or "").strip()
    agent_key = body.get("agentId") or body.get("key") or body.get("sessionKey") or "claude-code-local"
    conversation_id = str(body.get("conversationId") or body.get("threadId") or "").strip()
    stream_progress_id = body.get("_streamProgressId") or ""
    on_progress = body.get("_onProgress") if callable(body.get("_onProgress")) else None
    if not message:
        return {"ok": False, "error": "message is required", "_status": 400}
    agent = _get_claude_code_agent(agent_key)
    if not agent:
        return {"ok": False, "error": f"Claude Code agent '{agent_key}' not found", "_status": 404}
    archive_guard = _archive_manager_chat_guard(agent.get("id") or agent_key, message)
    if archive_guard:
        return archive_guard
    cfg = VO_CONFIG.get("claudeCode", {})
    provider = ClaudeCodeProvider(
        enabled=cfg.get("enabled", False),
        home_path=cfg.get("homePath"),
        binary=agent.get("binary") or cfg.get("binary"),
        workspace=body.get("workspace") or agent.get("workspace") or cfg.get("workspace"),
        name=agent.get("name") or cfg.get("name"),
        agent_id=agent.get("providerAgentId") or agent.get("profile") or cfg.get("agentId"),
        model=agent.get("model") or cfg.get("model"),
        reply_text=cfg.get("replyText") or os.environ.get("VO_CLAUDE_CODE_REPLY_TEXT"),
        timeout_sec=int(body.get("timeoutSec") or cfg.get("timeoutSec") or 900),
    )
    profile = agent.get("profile") or agent.get("providerAgentId") or "local"
    history = _load_claude_code_history(profile, conversation_id)
    now_ms = int(time.time() * 1000)
    history.append({
        "role": "user",
        "text": message,
        "ts": now_ms,
        "agentId": agent.get("id"),
        "from": body.get("fromDisplayName") or "User",
        "fromType": body.get("fromType") or "",
        "conversationId": conversation_id,
    })
    _save_claude_code_history(profile, history, conversation_id, _get_claude_code_session_id(profile, conversation_id))
    gateway_presence.set_manual_override(agent.get("statusKey") or agent.get("id"), "working", "Claude Code task")
    session_id = _get_claude_code_session_id(profile, conversation_id)
    result = provider.send_chat_message(
        message,
        conversation_id=conversation_id,
        timeout_sec=int(body.get("timeoutSec") or cfg.get("timeoutSec") or 900),
        session_id=session_id,
    )
    active_session_id = result.get("sessionId") or session_id
    progress_state = {
        "reply": result.get("reply") or "",
        "sessionId": active_session_id,
        "runId": result.get("runId") or active_session_id,
        "tools": result.get("tools") or [],
        "thinking": result.get("thinking") or "",
        "tokenUsage": result.get("tokenUsage") or {},
        "status": result.get("status", "completed" if result.get("ok") else "execution_failed"),
        "error": result.get("error") or "",
    }
    if on_progress:
        try:
            on_progress(progress_state)
        except Exception as e:
            print(f"[CLAUDE-CODE] Progress callback failed: {e}")
    if stream_progress_id:
        _publish_claude_code_progress(profile, agent.get("id"), stream_progress_id, progress_state, conversation_id)
    history = _load_claude_code_history(profile, conversation_id)
    history = _remove_claude_code_progress_messages(history)
    history.append({
        "role": "assistant",
        "text": result.get("reply") or "",
        "ts": int(time.time() * 1000),
        "agentId": agent.get("id"),
        "sessionId": active_session_id,
        "tools": result.get("tools") or [],
        "thinking": result.get("thinking") or "",
        "tokenUsage": result.get("tokenUsage") or {},
        "error": result.get("error") or "",
        "conversationId": conversation_id,
    })
    _save_claude_code_history(profile, history, conversation_id, active_session_id)
    gateway_presence.set_manual_override(agent.get("statusKey") or agent.get("id"), "idle" if result.get("ok") else "offline", "")
    normalized = normalize_provider_result(
        "claude-code",
        agent,
        result,
        conversation_id=conversation_id,
        session_id=active_session_id,
        run_id=result.get("runId") or active_session_id,
        modified_files=result.get("modifiedFiles") or [],
    )
    normalized["_status"] = provider_http_status(normalized)
    return normalized




def _handle_claude_code_cancel(body):
    agent_key = body.get("agentId") or body.get("key") or "claude-code-local"
    agent = _get_claude_code_agent(agent_key) or {}
    cfg = VO_CONFIG.get("claudeCode", {})
    provider = ClaudeCodeProvider(
        enabled=cfg.get("enabled", False),
        home_path=cfg.get("homePath"),
        binary=agent.get("binary") or cfg.get("binary"),
        workspace=agent.get("workspace") or cfg.get("workspace"),
        name=agent.get("name") or cfg.get("name"),
        agent_id=agent.get("providerAgentId") or agent.get("profile") or cfg.get("agentId"),
        model=agent.get("model") or cfg.get("model"),
        reply_text=cfg.get("replyText"),
        timeout_sec=int(cfg.get("timeoutSec") or 900),
    )
    result = provider.interrupt(agent.get("providerAgentId") or agent.get("profile") or cfg.get("agentId") or "local")
    result["_status"] = 200 if result.get("ok") else 404
    return result


_wrap_exports()
_hydrate()
