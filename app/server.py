#!/usr/bin/env python3
"""Virtual Office server.
Serves static files, status JSON, and proxies WebSocket to the OpenClaw gateway.
"""
import asyncio
import base64
import copy
import http.server
import json
import os
import mimetypes
import queue
import sys
import threading
import traceback
import uuid
import urllib.error
import urllib.parse
import urllib.request
import websockets
from datetime import datetime, timezone, timedelta
from websockets.asyncio.client import connect as ws_connect
import glob
import hashlib
import email.utils
import re
import shutil
import signal
import ssl
import sqlite3
import subprocess
import time
import difflib
import gateway_presence
import server_routes
from zoneinfo import ZoneInfo
from provider_execution import (
    collect_modified_files,
    normalize_active_operation,
    normalize_approval_record,
    normalize_provider_result,
    provider_http_status,
)
from feishu_notifications import send_feishu_notification
from feishu_long_connection import FeishuLongConnectionReceiver


_FEISHU_LONG_CONNECTION_RECEIVER = None
_FEISHU_LONG_CONNECTION_LOCK = threading.Lock()


def _normalize_presence_entry(entry):
    """Normalize transient gateway/presence state aliases for UI rendering."""
    if not isinstance(entry, dict):
        return {"state": "offline", "task": "", "updated": 0, "source": "invalid"}
    state = str(entry.get("state") or entry.get("status") or entry.get("presence") or entry.get("activity") or "offline").strip().lower()
    state = {
        "busy": "working",
        "thinking": "working",
        "processing": "working",
        "responding": "working",
        "running": "working",
        "reading": "working",
        "reading_file": "working",
        "reading-file": "working",
        "analyzing": "working",
        "planning": "working",
        "reasoning": "working",
        "inference": "working",
        "inferencing": "working",
        "generating": "working",
        "streaming": "working",
        "executing": "working",
        "command": "working",
        "command_output": "working",
        "tool": "working",
        "tool_start": "working",
        "running_command": "working",
        "available": "idle",
    }.get(state, state)
    if state not in {"working", "finishing", "idle", "meeting", "break", "offline"}:
        state = "offline" if not state else state
    normalized = dict(entry)
    normalized["state"] = state
    normalized["task"] = str(entry.get("task") or "")
    updated = entry.get("updated", 0)
    normalized["updated"] = int(updated) if str(updated or "").isdigit() else updated
    normalized["source"] = str(entry.get("source") or "legacy")
    try:
        updated_epoch = float(normalized.get("updated") or 0)
    except (TypeError, ValueError):
        updated_epoch = 0
    source_lower = str(normalized.get("source") or "").lower()
    task_lower = str(normalized.get("task") or "").strip().lower()
    # Active lifecycle/tool sources can be silent during long commands. Generic
    # chat/snapshot display states must still age out if maintenance missed the
    # terminal event, otherwise disconnected apps can show stale working status.
    has_active_work_source = source_lower.startswith(("agent-lifecycle", "agent-tool", "session-tool", "gateway", "hermes-", "provider-"))
    stale_limit_sec = 180 if (
        "tool" in source_lower or "command" in source_lower or
        any(token in task_lower for token in ("reading", "processing", "thinking", "running command", "editing", "writing", "searching", "fetching"))
    ) else 45
    if (
        not has_active_work_source
        and state in {"working", "finishing"}
        and updated_epoch > 0
        and (time.time() - updated_epoch) > stale_limit_sec
    ):
        normalized["state"] = "idle"
        normalized["task"] = ""
        normalized["source"] = f"{normalized.get('source') or 'presence'}-stale-idle"
    return normalized


def _normalize_presence_map(data):
    if not isinstance(data, dict):
        return {}
    result = {}
    for key, value in data.items():
        if key == "_meetings":
            result[key] = value if isinstance(value, list) else []
        elif isinstance(value, dict):
            result[key] = _normalize_presence_entry(value)
    return result


def _get_normalized_presence_state():
    gateway_presence._sync_meetings_from_file()
    state = _normalize_presence_map(gateway_presence.get_state())
    state["_meetings"] = _status_meeting_projection(state.get("_meetings", []))
    # Bubble commands still write to virtual-office-status.json. Presence owns
    # state/task, but these display-only fields must remain available to the UI.
    try:
        with open(STATUS_FILE, "r") as f:
            legacy_status = json.load(f)
        for key, entry in legacy_status.items():
            if key.startswith("_") or not isinstance(entry, dict):
                continue
            target = state.setdefault(key, {
                "state": "idle",
                "task": "",
                "updated": int(entry.get("updated") or time.time()),
                "source": "status-file",
            })
            for field in ("thought", "speech", "speechTarget"):
                target[field] = entry.get(field, "")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    # Provider adapters such as Hermes do not emit OpenClaw gateway events.
    # Keep them visible as idle/offline-capable office citizens unless a
    # manual/process override (working, idle, error) has more current data.
    now = int(time.time())
    for agent in get_roster():
        key = agent.get("statusKey") or agent.get("id")
        if not key or key in state:
            continue
        provider_kind = agent.get("providerKind", "openclaw")
        state[key] = {
            "state": "idle",
            "task": "",
            "updated": int(agent.get("lastActiveAt") or now),
            "source": f"{provider_kind}-discovery",
            "providerKind": provider_kind,
        }
    return state


def _status_meeting_projection(legacy_meetings):
    """Return the meeting list consumed by the office canvas."""
    meetings = legacy_meetings if isinstance(legacy_meetings, list) else []
    by_id = {m.get("id"): dict(m) for m in meetings if isinstance(m, dict) and m.get("id")}
    for meeting in _meeting_active_projection():
        meeting_id = meeting.get("id")
        if meeting_id:
            by_id[meeting_id] = meeting
    return list(by_id.values())


# ─── CONFIGURATION ───────────────────────────────────────────────
def _env_or(key, fallback):
    """Return env var value if set and non-empty, else fallback."""
    val = os.environ.get(key)
    return val if val else fallback

def _env_bool(key, fallback):
    """Return boolean env var override if set, else fallback."""
    val = os.environ.get(key)
    if val is None or str(val).strip() == "":
        return fallback
    return str(val).strip().lower() in ("1", "true", "yes", "on", "enabled")

def _resolve_config_path():
    """Return path to vo-config.json — prefers /data/ (persistent volume) over /app/ (container layer)."""
    if os.environ.get("VO_CONFIG"):
        return os.environ["VO_CONFIG"]
    data_cfg = os.path.join(os.environ.get("VO_STATUS_DIR", "/data"), "vo-config.json")
    app_cfg = os.path.join(os.path.dirname(__file__), "vo-config.json")
    # Prefer data volume config (survives container recreation)
    if os.path.isfile(data_cfg):
        return data_cfg
    # Migrate: if app config exists and has been customized, copy to data volume
    if os.path.isfile(app_cfg):
        try:
            with open(app_cfg, "r") as f:
                app_data = json.load(f)
            if app_data.get("_setupComplete"):
                os.makedirs(os.path.dirname(data_cfg), exist_ok=True)
                with open(data_cfg, "w") as f:
                    json.dump(app_data, f, indent=2)
                return data_cfg
        except (json.JSONDecodeError, OSError):
            pass
    # Fall back to app-bundled default
    return app_cfg

def _load_vo_config():
    """Load vo-config.json with env-var overrides. Returns merged dict."""
    cfg_path = _resolve_config_path()
    cfg = {}
    try:
        with open(cfg_path, "r") as f:
            cfg = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    env_gateway_token = (
        os.environ.get("VO_GATEWAY_TOKEN")
        or os.environ.get("OPENCLAW_GATEWAY_TOKEN")
    )

    # Auto-detect OpenClaw home — check env, config, then common paths
    oc_home = (
        os.environ.get("VO_OPENCLAW_PATH")
        or (cfg.get("openclaw") or {}).get("homePath")
    )
    if not oc_home:
        # Search common locations
        candidates = [
            os.path.expanduser("~/.openclaw"),
            "/openclaw",  # Docker mount convention
            "/root/.openclaw",  # common root install
        ]
        for c in candidates:
            if os.path.isdir(c) and (os.path.isfile(os.path.join(c, "openclaw.json")) or os.path.isdir(os.path.join(c, "agents"))):
                oc_home = c
                break
        if not oc_home:
            oc_home = os.path.expanduser("~/.openclaw")

    office = cfg.get("office") or {}
    openclaw = cfg.get("openclaw") or {}
    presence = cfg.get("presence") or {}
    features = cfg.get("features") or {}
    pc_metrics = cfg.get("pcMetrics") or {}
    whisper_cfg = cfg.get("whisper") or {}
    browser_cfg = cfg.get("browser") or {}
    meetings_cfg = cfg.get("meetings") or {}
    weather_cfg = cfg.get("weather") or {}
    sms_cfg = cfg.get("sms") or {}
    notifications_cfg = cfg.get("notifications") or {}
    hermes_cfg = cfg.get("hermes") or {}
    codex_cfg = cfg.get("codex") or {}
    claude_code_cfg = cfg.get("claudeCode") or cfg.get("claude_code") or {}
    codex_workspace_root = _env_or("VO_CODEX_WORKSPACE_ROOT", codex_cfg.get("workspaceRoot", os.path.join(_env_or("VO_STATUS_DIR", presence.get("statusDir", "/data")), "codex-agents")))
    codex_workspace = _env_or("VO_CODEX_WORKSPACE", codex_cfg.get("workspace", os.path.dirname(os.path.dirname(__file__))))
    claude_code_workspace_root = _env_or("VO_CLAUDE_CODE_WORKSPACE_ROOT", claude_code_cfg.get("workspaceRoot", os.path.join(_env_or("VO_STATUS_DIR", presence.get("statusDir", "/data")), "claude-code-agents")))
    claude_code_workspace = _env_or("VO_CLAUDE_CODE_WORKSPACE", claude_code_cfg.get("workspace", os.path.dirname(os.path.dirname(__file__))))
    hermes_api_enabled = hermes_cfg.get("apiEnabled", hermes_cfg.get("preferApi", False))
    gateway_port = "18789"
    try:
        oc_cfg_path = os.path.join(os.path.expanduser(oc_home), "openclaw.json")
        with open(oc_cfg_path, "r") as f:
            oc_cfg = json.load(f)
        configured_port = ((oc_cfg.get("gateway") or {}).get("port"))
        if configured_port:
            gateway_port = str(configured_port)
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
        pass
    default_gateway_url = f"ws://127.0.0.1:{gateway_port}"
    default_gateway_http = f"http://127.0.0.1:{gateway_port}"

    return {
        "office": {
            "name": _env_or("VO_OFFICE_NAME", office.get("name", "Virtual Office")),
            "port": int(_env_or("VO_PORT", office.get("port", 8090))),
            "wsPort": int(_env_or("VO_WS_PORT", office.get("wsPort", 8091))),
            "wsPath": _env_or("VO_WS_PATH", office.get("wsPath", "/ws")),
        },
        "openclaw": {
            "homePath": oc_home,
            "gatewayUrl": _env_or("VO_GATEWAY_URL", openclaw.get("gatewayUrl", default_gateway_url)),
            "gatewayHttp": _env_or("VO_GATEWAY_HTTP", openclaw.get("gatewayHttp", default_gateway_http)),
            "gatewayToken": env_gateway_token or openclaw.get("gatewayToken", ""),
        },
        "presence": {
            "statusDir": _env_or("VO_STATUS_DIR", presence.get("statusDir", "/data")),
            "inferenceEnabled": presence.get("inferenceEnabled", True),
            "inferenceIdleTimeoutSec": presence.get("inferenceIdleTimeoutSec", 300),
        },
        "features": {
            "pcMetrics": features.get("pcMetrics", False),
            "smsPanel": features.get("smsPanel", False),
            "browserPanel": _env_bool("VO_BROWSER_PANEL", features.get("browserPanel", False)),
            "whisper": features.get("whisper", False),
            "apiUsage": features.get("apiUsage", False),
        },
        "pcMetrics": {
            "url": pc_metrics.get("url"),
        },
        "whisper": {
            "url": _env_or("VO_WHISPER_URL", whisper_cfg.get("url", "http://127.0.0.1:8087")),
        },
        "browser": {
            "cdpUrl": _env_or("VO_CDP_URL", browser_cfg.get("cdpUrl")),
            "viewerUrl": _env_or("VO_VIEWER_URL", browser_cfg.get("viewerUrl")),
        },
        "meetings": {
            "preparingTimeoutSec": meetings_cfg.get("preparingTimeoutSec", 300),
        },
        "weather": {
            "location": _env_or("VO_WEATHER_LOCATION", weather_cfg.get("location")),
        },
        "sms": {
            "ownerAgentId": _env_or("VO_SMS_OWNER_AGENT_ID", _env_or("VO_SMS_AGENT_ID", sms_cfg.get("ownerAgentId") or sms_cfg.get("agentId"))),
            "agentId": _env_or("VO_SMS_OWNER_AGENT_ID", _env_or("VO_SMS_AGENT_ID", sms_cfg.get("ownerAgentId") or sms_cfg.get("agentId"))),
            "twilioAccountSid": _env_or("VO_TWILIO_ACCOUNT_SID", sms_cfg.get("twilioAccountSid")),
            "twilioAuthToken": _env_or("VO_TWILIO_AUTH_TOKEN", sms_cfg.get("twilioAuthToken")),
            "fromNumber": _env_or("VO_TWILIO_FROM_NUMBER", sms_cfg.get("fromNumber")),
        },
        "notifications": {
            "feishuWebhook": _env_or("VO_FEISHU_NOTIFICATION_WEBHOOK", notifications_cfg.get("feishuWebhook", "")),
            "feishuEnabled": _env_bool("VO_FEISHU_NOTIFICATION_ENABLED", notifications_cfg.get("feishuEnabled", True)),
            "feishuAppId": _env_or("VO_FEISHU_APP_ID", notifications_cfg.get("feishuAppId", "")),
            "feishuAppSecret": _env_or("VO_FEISHU_APP_SECRET", notifications_cfg.get("feishuAppSecret", "")),
            "feishuReceiveIdType": _env_or("VO_FEISHU_RECEIVE_ID_TYPE", notifications_cfg.get("feishuReceiveIdType", "chat_id")),
            "feishuReceiveId": _env_or("VO_FEISHU_RECEIVE_ID", notifications_cfg.get("feishuReceiveId", "")),
        },
        "hermes": {
            "enabled": str(_env_or("VO_HERMES_ENABLED", hermes_cfg.get("enabled", True))).lower() not in ("0", "false", "no", "off"),
            "homePath": _env_or("VO_HERMES_HOME", hermes_cfg.get("homePath", os.path.expanduser("~/.hermes"))),
            "binary": _env_or("VO_HERMES_BIN", hermes_cfg.get("binary", os.path.expanduser("~/.local/bin/hermes"))),
            "timeoutSec": int(_env_or("VO_HERMES_TIMEOUT_SEC", hermes_cfg.get("timeoutSec", 600))),
            "apiEnabled": _env_bool("VO_HERMES_API_ENABLED", _env_bool("VO_HERMES_PREFER_API", hermes_api_enabled)),
            "preferApi": _env_bool("VO_HERMES_API_ENABLED", _env_bool("VO_HERMES_PREFER_API", hermes_api_enabled)),
            "apiUrl": _env_or("VO_HERMES_API_URL", hermes_cfg.get("apiUrl", "http://127.0.0.1:8642")),
            "apiKey": _env_or("VO_HERMES_API_KEY", hermes_cfg.get("apiKey", "")),
        },
        "codex": {
            "enabled": _env_bool("VO_CODEX_ENABLED", codex_cfg.get("enabled", False)),
            "homePath": _env_or("VO_CODEX_HOME", codex_cfg.get("homePath", os.path.expanduser("~/.codex"))),
            "binary": _env_or("VO_CODEX_BIN", codex_cfg.get("binary", "codex")),
            "workspace": codex_workspace,
            "workspaceRoot": codex_workspace_root,
            "mainWorkspace": _env_or("VO_CODEX_MAIN_WORKSPACE", codex_cfg.get("mainWorkspace", codex_workspace)),
            "name": _env_or("VO_CODEX_AGENT_NAME", codex_cfg.get("name", "Codex")),
            "agentId": _env_or("VO_CODEX_AGENT_ID", codex_cfg.get("agentId", "local")),
            "model": _env_or("VO_CODEX_MODEL", codex_cfg.get("model", os.environ.get("OPENAI_MODEL", ""))),
            "replyText": _env_or("VO_CODEX_REPLY_TEXT", codex_cfg.get("replyText")),
            "bridgeUrl": _env_or("VO_CODEX_BRIDGE_URL", codex_cfg.get("bridgeUrl")),
            "sandbox": _env_or("VO_CODEX_SANDBOX", codex_cfg.get("sandbox", "workspace-write")),
            "approvalPolicy": _env_or("VO_CODEX_APPROVAL_POLICY", codex_cfg.get("approvalPolicy", "never")),
            "includeMain": _env_bool("VO_CODEX_INCLUDE_MAIN", codex_cfg.get("includeMain", True)),
            "includeNativeAgents": _env_bool("VO_CODEX_INCLUDE_NATIVE_AGENTS", codex_cfg.get("includeNativeAgents", True)),
            "registerNativeAgents": _env_bool("VO_CODEX_REGISTER_NATIVE_AGENTS", codex_cfg.get("registerNativeAgents", True)),
        },
        "claudeCode": {
            "enabled": _env_bool("VO_CLAUDE_CODE_ENABLED", claude_code_cfg.get("enabled", False)),
            "homePath": _env_or("VO_CLAUDE_CODE_HOME", claude_code_cfg.get("homePath", os.path.expanduser("~/.claude"))),
            "binary": _env_or("VO_CLAUDE_CODE_BIN", claude_code_cfg.get("binary", "claude")),
            "workspace": claude_code_workspace,
            "workspaceRoot": claude_code_workspace_root,
            "mainWorkspace": _env_or("VO_CLAUDE_CODE_MAIN_WORKSPACE", claude_code_cfg.get("mainWorkspace", claude_code_workspace)),
            "name": _env_or("VO_CLAUDE_CODE_AGENT_NAME", claude_code_cfg.get("name", "Claude Code")),
            "agentId": _env_or("VO_CLAUDE_CODE_AGENT_ID", claude_code_cfg.get("agentId", "local")),
            "model": _env_or("VO_CLAUDE_CODE_MODEL", claude_code_cfg.get("model", "")),
            "replyText": _env_or("VO_CLAUDE_CODE_REPLY_TEXT", claude_code_cfg.get("replyText")),
            "timeoutSec": int(_env_or("VO_CLAUDE_CODE_TIMEOUT_SEC", claude_code_cfg.get("timeoutSec", 900))),
            "permissionMode": _env_or("VO_CLAUDE_CODE_PERMISSION_MODE", claude_code_cfg.get("permissionMode", "acceptEdits")),
            "includeMain": _env_bool("VO_CLAUDE_CODE_INCLUDE_MAIN", claude_code_cfg.get("includeMain", True)),
            "includeNativeAgents": _env_bool("VO_CLAUDE_CODE_INCLUDE_NATIVE_AGENTS", claude_code_cfg.get("includeNativeAgents", True)),
            "registerNativeAgents": _env_bool("VO_CLAUDE_CODE_REGISTER_NATIVE_AGENTS", claude_code_cfg.get("registerNativeAgents", True)),
        },
    }

_SETUP_SECRET_KEYS = {"apiKey", "gatewayToken", "twilioAuthToken", "feishuWebhook", "feishuAppSecret"}


def _mask_feishu_webhook(value):
    text = str(value or "").strip()
    if not text:
        return ""
    prefix = 38
    suffix = 8
    if len(text) <= prefix + suffix:
        return text[:2] + "••••"
    return text[:prefix] + "••••••••" + text[-suffix:]


def _mask_secret_value(value, prefix=6, suffix=4):
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= prefix + suffix:
        return text[:2] + "••••"
    return text[:prefix] + "••••••••" + text[-suffix:]


def _feishu_app_configured(cfg):
    return bool(
        (cfg or {}).get("feishuAppId")
        and (cfg or {}).get("feishuAppSecret")
        and (cfg or {}).get("feishuReceiveId")
    )


def _feishu_app_send_config(cfg):
    cfg = cfg or {}
    return {
        "appId": cfg.get("feishuAppId") or "",
        "appSecret": cfg.get("feishuAppSecret") or "",
        "receiveIdType": cfg.get("feishuReceiveIdType") or "chat_id",
        "receiveId": cfg.get("feishuReceiveId") or "",
    }


# Runtime config/setup helpers live in server_services.config_runtime.



def _first_provider_agent_model(provider_kind):
    try:
        for agent in get_roster():
            if str(agent.get("providerKind") or "") == provider_kind:
                return agent.get("model") or ""
    except Exception:
        pass
    return ""

VO_CONFIG = _load_vo_config()

try:
    SMS_DEFAULT_TZ = ZoneInfo(os.environ.get("VO_SMS_TIMEZONE") or os.environ.get("TZ") or "UTC")
except Exception:
    SMS_DEFAULT_TZ = timezone.utc

PORT = VO_CONFIG["office"]["port"]
WS_PORT = VO_CONFIG["office"]["wsPort"]
WORKSPACE_BASE = VO_CONFIG["openclaw"]["homePath"]
STATUS_DIR = VO_CONFIG["presence"]["statusDir"]
os.makedirs(STATUS_DIR, exist_ok=True)
STATUS_FILE = os.path.join(STATUS_DIR, "virtual-office-status.json")
PROJECT_CRON_BINDINGS_FILE = os.path.join(STATUS_DIR, "project-cron-bindings.json")

_OPENCLAW_VERSION_CACHE = None


def _get_openclaw_version():
    """Return the installed OpenClaw version for Gateway client identification."""
    global _OPENCLAW_VERSION_CACHE
    if _OPENCLAW_VERSION_CACHE:
        return _OPENCLAW_VERSION_CACHE
    try:
        cfg_file = os.path.join(WORKSPACE_BASE, "openclaw.json")
        with open(cfg_file, "r") as f:
            cfg = json.load(f)
        for value in (
            ((cfg.get("meta") or {}).get("lastTouchedVersion")),
            ((cfg.get("wizard") or {}).get("lastRunVersion")),
        ):
            if value:
                _OPENCLAW_VERSION_CACHE = str(value)
                return _OPENCLAW_VERSION_CACHE
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["openclaw", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        text_out = (result.stdout or result.stderr or "").strip()
        match = re.search(r"OpenClaw\s+([^\s]+)", text_out)
        if match:
            _OPENCLAW_VERSION_CACHE = match.group(1)
            return _OPENCLAW_VERSION_CACHE
    except Exception:
        pass
    _OPENCLAW_VERSION_CACHE = os.environ.get("OPENCLAW_VERSION", "unknown")
    return _OPENCLAW_VERSION_CACHE
PROJECTS_FILE = os.path.join(STATUS_DIR, "projects.json")
AGENT_WORKSPACES_FILE = os.path.join(STATUS_DIR, "agent-workspaces.json")
AUTH_PROFILES_PATH = os.path.join(WORKSPACE_BASE, "agents/main/agent/auth-profiles.json")
OPENCLAW_HOME = os.path.expanduser(os.environ.get("OPENCLAW_HOME") or WORKSPACE_BASE or "~/.openclaw")
OPENCLAW_AGENT_DIR = os.path.join(OPENCLAW_HOME, "agents/main/agent")


def _first_existing_executable(candidates):
    for candidate in candidates:
        if not candidate:
            continue
        candidate = os.path.expanduser(candidate)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


OPENCLAW_BIN = (
    os.environ.get("OPENCLAW_BIN")
    or VO_CONFIG.get("openclaw", {}).get("binary")
    or shutil.which("openclaw")
)
HERMES_HOME = os.path.expanduser(os.environ.get("HERMES_HOME") or VO_CONFIG.get("hermes", {}).get("homePath") or "~/.hermes")
HERMES_BIN = (
    os.environ.get("HERMES_BIN")
    or VO_CONFIG.get("hermes", {}).get("binary")
    or shutil.which("hermes")
)


def _run_json_command(args, timeout=30, env=None):
    """Run a native CLI command that returns JSON."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        if result.returncode != 0:
            return {
                "ok": False,
                "error": (result.stderr or result.stdout or f"exit {result.returncode}").strip(),
                "returnCode": result.returncode,
            }
        text_out = (result.stdout or "").strip()
        # Some CLIs print warnings before JSON. Keep the parser tolerant.
        start = min([i for i in [text_out.find("{"), text_out.find("[")] if i >= 0] or [-1])
        if start > 0:
            text_out = text_out[start:]
        return {"ok": True, "data": json.loads(text_out or "{}")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _run_text_command(args, timeout=30, env=None):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)
        return {
            "ok": result.returncode == 0,
            "text": (result.stdout or result.stderr or "").strip(),
            "returnCode": result.returncode,
        }
    except Exception as e:
        return {"ok": False, "text": str(e), "returnCode": -1}


def _provider_from_model_id(model_id):
    return str(model_id or "").split("/", 1)[0] if "/" in str(model_id or "") else ""


def _safe_provider_id(value):
    provider = str(value or "").strip().lower()
    provider = re.sub(r"[^a-z0-9_.:-]+", "-", provider).strip("-")
    return provider[:80]


def _parse_model_entries(value):
    entries = []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").replace(",", "\n").splitlines()
    seen = set()
    for item in raw_items:
        if isinstance(item, dict):
            model_id = str(item.get("id") or item.get("model") or item.get("name") or "").strip()
            name = str(item.get("name") or model_id).strip()
            context = item.get("contextWindow") or item.get("context") or 100000
            max_tokens = item.get("maxTokens") or 8192
        else:
            model_id = str(item or "").strip()
            name = model_id
            context = 100000
            max_tokens = 8192
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        try:
            context = int(context)
        except Exception:
            context = 100000
        try:
            max_tokens = int(max_tokens)
        except Exception:
            max_tokens = 8192
        entries.append({
            "id": model_id,
            "name": name,
            "contextWindow": context,
            "maxTokens": max_tokens,
        })
    return entries


def _mask_secret(value):
    value = str(value or "")
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "..." + value[-4:]


def _read_openclaw_auth_sqlite():
    db_path = os.path.join(OPENCLAW_AGENT_DIR, "openclaw-agent.sqlite")
    profiles = []
    if not os.path.exists(db_path):
        return profiles
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
        for table in tables:
            cols = [r[1] for r in con.execute(f"pragma table_info({table})")]
            if "store_json" in cols:
                for row in con.execute(f"select store_json from {table}").fetchall():
                    try:
                        data = json.loads(row["store_json"] or "{}")
                    except Exception:
                        continue
                    for profile_id, profile in (data.get("profiles") or {}).items():
                        provider = profile.get("provider") or profile_id.split(":", 1)[0]
                        ptype = profile.get("type") or profile.get("mode") or "profile"
                        email = profile.get("email") or ""
                        profiles.append({
                            "id": profile_id,
                            "provider": provider,
                            "type": ptype,
                            "label": profile_id + (f" ({email})" if email else ""),
                            "source": "sqlite",
                        })
                continue
            if not {"id", "provider"}.issubset(set(cols)):
                continue
            type_col = "type" if "type" in cols else ("mode" if "mode" in cols else None)
            rows = con.execute(f"select * from {table}").fetchall()
            for row in rows:
                provider = row["provider"]
                profile_id = row["id"]
                if not provider or not profile_id:
                    continue
                ptype = row[type_col] if type_col else ""
                email = row["email"] if "email" in cols else ""
                label = profile_id + (f" ({email})" if email else "")
                profiles.append({
                    "id": profile_id,
                    "provider": provider,
                    "type": ptype or "profile",
                    "label": label,
                    "source": "sqlite",
                })
        con.close()
    except Exception:
        return profiles
    # Deduplicate by id/provider/type.
    seen = set()
    unique = []
    for profile in profiles:
        key = (profile["id"], profile["provider"], profile["type"])
        if key not in seen:
            seen.add(key)
            unique.append(profile)
    return unique


def _read_openclaw_auth_json():
    profiles = []
    try:
        with open(AUTH_PROFILES_PATH, "r") as f:
            data = json.load(f)
    except Exception:
        return profiles
    for profile_id, profile in (data.get("profiles") or {}).items():
        if not isinstance(profile, dict):
            continue
        provider = profile.get("provider") or profile_id.split(":", 1)[0]
        ptype = profile.get("type") or profile.get("mode") or "profile"
        email = profile.get("email") or ""
        profiles.append({
            "id": profile_id,
            "provider": provider,
            "type": ptype,
            "label": profile_id + (f" ({email})" if email else ""),
            "source": "auth-profiles.json",
        })
    return profiles


def _read_openclaw_auth_profiles():
    sqlite_profiles = _read_openclaw_auth_sqlite()
    if sqlite_profiles:
        return sqlite_profiles
    return _read_openclaw_auth_json()


def _quote_sqlite_identifier(name):
    return '"' + str(name).replace('"', '""') + '"'


def _update_openclaw_sqlite_auth_stores(updater):
    db_path = os.path.join(OPENCLAW_AGENT_DIR, "openclaw-agent.sqlite")
    if not os.path.exists(db_path):
        return 0, None
    updated = 0
    con = None
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
        now_ms = int(time.time() * 1000)
        for table in tables:
            qtable = _quote_sqlite_identifier(table)
            cols = [r[1] for r in con.execute(f"pragma table_info({qtable})")]
            if not {"store_key", "store_json", "updated_at"}.issubset(set(cols)):
                continue
            rows = con.execute(f"select store_key, store_json from {qtable}").fetchall()
            for row in rows:
                try:
                    data = json.loads(row["store_json"] or "{}")
                except Exception:
                    continue
                if not isinstance(data.get("profiles"), dict):
                    continue
                changed = updater(data)
                if not changed:
                    continue
                con.execute(
                    f"update {qtable} set store_json = ?, updated_at = ? where store_key = ?",
                    (json.dumps(data, separators=(",", ":")), now_ms, row["store_key"]),
                )
                updated += 1
        con.commit()
        return updated, None
    except Exception as e:
        return updated, str(e)
    finally:
        try:
            if con:
                con.close()
        except Exception:
            pass


def _update_openclaw_auth_profiles_json(updater, create_if_missing=False):
    if not os.path.exists(AUTH_PROFILES_PATH) and not create_if_missing:
        return False, None
    try:
        os.makedirs(os.path.dirname(AUTH_PROFILES_PATH), exist_ok=True)
        try:
            with open(AUTH_PROFILES_PATH, "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {"version": 1, "profiles": {}, "lastGood": {}}
        data.setdefault("version", 1)
        data.setdefault("profiles", {})
        changed = updater(data)
        if not changed:
            return False, None
        tmp_path = AUTH_PROFILES_PATH + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, AUTH_PROFILES_PATH)
        return True, None
    except Exception as e:
        return False, str(e)


def _mirror_openclaw_config_auth_profile(provider, profile_id):
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)
        cfg.setdefault("auth", {}).setdefault("profiles", {})[profile_id] = {
            "provider": provider,
            "mode": "api_key",
        }
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
        return True, None
    except Exception as e:
        return False, str(e)


def _remove_openclaw_config_auth_profiles(profile_ids):
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)
        profiles = cfg.setdefault("auth", {}).setdefault("profiles", {})
        changed = False
        for profile_id in profile_ids:
            if profile_id in profiles:
                profiles.pop(profile_id, None)
                changed = True
        if changed:
            with open(CONFIG_PATH, "w") as f:
                json.dump(cfg, f, indent=2)
        return True, None
    except Exception as e:
        return False, str(e)


def _save_openclaw_api_key_direct(provider, profile_id, api_key):
    profile = {"type": "api_key", "provider": provider, "key": api_key}

    def updater(data):
        profiles = data.setdefault("profiles", {})
        if profiles.get(profile_id) == profile:
            return False
        profiles[profile_id] = dict(profile)
        last_good = data.get("lastGood")
        if isinstance(last_good, dict):
            last_good[provider] = profile_id
        return True

    sqlite_updates, sqlite_err = _update_openclaw_sqlite_auth_stores(updater)
    json_updated, json_err = _update_openclaw_auth_profiles_json(
        updater,
        create_if_missing=(sqlite_updates == 0 and not sqlite_err),
    )
    if sqlite_err and not json_updated:
        return {"ok": False, "error": f"Cannot write OpenClaw auth store: {sqlite_err}"}
    if json_err and sqlite_updates == 0:
        return {"ok": False, "error": f"Cannot write auth-profiles.json: {json_err}"}

    _mirror_openclaw_config_auth_profile(provider, profile_id)
    return {
        "ok": True,
        "provider": provider,
        "profileId": profile_id,
        "maskedKey": _mask_secret(api_key),
        "source": "direct-auth-store",
    }


def _delete_openclaw_auth_direct(provider, profile_id=""):
    deleted = set()

    def should_delete(pid, profile):
        if profile_id:
            return pid == profile_id
        if (profile.get("provider") or pid.split(":", 1)[0]) != provider:
            return False
        ptype = str(profile.get("type") or profile.get("mode") or "").lower()
        return ptype in {"api_key", "key"} or "key" in profile

    def updater(data):
        profiles = data.setdefault("profiles", {})
        remove = [pid for pid, profile in profiles.items() if isinstance(profile, dict) and should_delete(pid, profile)]
        for pid in remove:
            profiles.pop(pid, None)
            deleted.add(pid)
        last_good = data.get("lastGood")
        if isinstance(last_good, dict):
            for key, value in list(last_good.items()):
                if value in remove:
                    last_good.pop(key, None)
        return bool(remove)

    sqlite_updates, sqlite_err = _update_openclaw_sqlite_auth_stores(updater)
    json_updated, json_err = _update_openclaw_auth_profiles_json(updater, create_if_missing=False)
    if sqlite_err and not json_updated:
        return {"ok": False, "error": f"Cannot write OpenClaw auth store: {sqlite_err}"}
    if json_err and sqlite_updates == 0:
        return {"ok": False, "error": f"Cannot write auth-profiles.json: {json_err}"}

    _remove_openclaw_config_auth_profiles(deleted)
    return {"ok": True, "provider": provider, "deletedProfiles": sorted(deleted), "source": "direct-auth-store"}


def _read_openclaw_config_models(cfg):
    models = []
    default_model = cfg.get("agents", {}).get("defaults", {}).get("model", {}).get("primary", "")
    if default_model:
        models.append({
            "id": default_model,
            "key": default_model,
            "name": default_model.split("/", 1)[-1],
            "provider": _provider_from_model_id(default_model),
            "available": True,
            "missing": False,
            "tags": ["default"],
            "source": "openclaw-config",
        })
    for model_id, data in cfg.get("agents", {}).get("defaults", {}).get("models", {}).items():
        models.append({
            "id": model_id,
            "key": model_id,
            "name": model_id.split("/", 1)[-1],
            "provider": _provider_from_model_id(model_id),
            "input": ",".join(data.get("input", [])) if isinstance(data, dict) else "",
            "contextWindow": ((data or {}).get("params") or {}).get("contextWindow", 0) if isinstance(data, dict) else 0,
            "available": True,
            "missing": False,
            "tags": ["configured"],
            "source": "openclaw-config",
        })
    for provider, pdata in cfg.get("models", {}).get("providers", {}).items():
        for m in pdata.get("models", []):
            mid = f"{provider}/{m.get('id')}"
            models.append({
                "id": mid,
                "key": mid,
                "name": m.get("name") or m.get("id"),
                "provider": provider,
                "input": ",".join(m.get("input", [])) if isinstance(m.get("input"), list) else m.get("input"),
                "contextWindow": m.get("contextWindow", 0),
                "available": True,
                "missing": False,
                "tags": [],
                "source": "openclaw-config",
            })
    deduped = {}
    for model in models:
        deduped[model["id"]] = {**deduped.get(model["id"], {}), **model}
    return list(deduped.values())


_OPENCLAW_CLOUD_PROVIDER_IDS = {
    "anthropic",
    "openai",
    "openai-codex",
    "google",
    "gemini",
    "groq",
    "openrouter",
    "mistral",
    "cohere",
    "xai",
    "github-copilot",
    "copilot",
}


def _openclaw_provider_kind(provider, pdata):
    provider = _safe_provider_id(provider)
    pdata = pdata if isinstance(pdata, dict) else {}
    api = str(pdata.get("api") or "").lower()
    base_url = str(pdata.get("baseUrl") or "").strip()
    if provider in {"ollama", "lmstudio"} or api == "ollama":
        return "local"
    if base_url:
        return "local" if provider not in _OPENCLAW_CLOUD_PROVIDER_IDS else "cloud"
    if provider in _OPENCLAW_CLOUD_PROVIDER_IDS:
        return "cloud"
    return "local"


def _openclaw_local_providers_from_config(cfg):
    providers = []
    for provider, pdata in (cfg.get("models", {}).get("providers", {}) or {}).items():
        if _openclaw_provider_kind(provider, pdata) != "local":
            continue
        model_rows = []
        for model in pdata.get("models", []) or []:
            model_id = str(model.get("id") or "").strip()
            if not model_id:
                continue
            model_rows.append({
                "id": model_id,
                "name": model.get("name") or model_id,
                "contextWindow": model.get("contextWindow", 0),
                "maxTokens": model.get("maxTokens", 0),
            })
        providers.append({
            "id": provider,
            "provider": provider,
            "baseUrl": pdata.get("baseUrl", ""),
            "api": pdata.get("api", ""),
            "apiKeyConfigured": bool(pdata.get("apiKey")),
            "timeoutSeconds": pdata.get("timeoutSeconds"),
            "models": model_rows,
            "modelCount": len(model_rows),
            "source": "openclaw-config",
        })
    return sorted(providers, key=lambda item: item.get("provider", ""))


def _openclaw_cloud_providers_from_config(cfg, auth_profiles=None):
    auth_profiles = auth_profiles or []
    configured = {}
    for model_id, data in (cfg.get("agents", {}).get("defaults", {}).get("models", {}) or {}).items():
        provider = _provider_from_model_id(model_id)
        if provider in _OPENCLAW_CLOUD_PROVIDER_IDS:
            configured.setdefault(provider, []).append({
                "id": model_id,
                "name": model_id.split("/", 1)[-1],
                "contextWindow": ((data or {}).get("params") or {}).get("contextWindow", 0) if isinstance(data, dict) else 0,
                "source": "agents.defaults.models",
            })
    for provider, pdata in (cfg.get("models", {}).get("providers", {}) or {}).items():
        if _openclaw_provider_kind(provider, pdata) != "cloud":
            continue
        for model in pdata.get("models", []) or []:
            model_id = str(model.get("id") or "").strip()
            if not model_id:
                continue
            configured.setdefault(provider, []).append({
                "id": f"{provider}/{model_id}",
                "name": model.get("name") or model_id,
                "contextWindow": model.get("contextWindow", 0),
                "source": "models.providers",
            })
    for profile in auth_profiles:
        provider = profile.get("provider") or _provider_from_model_id(profile.get("id", ""))
        if provider in _OPENCLAW_CLOUD_PROVIDER_IDS:
            configured.setdefault(provider, [])

    cloud_providers = []
    for provider, models in configured.items():
        seen = set()
        model_rows = []
        for model in models:
            mid = model.get("id")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            model_rows.append(model)
        profiles = [p for p in auth_profiles if (p.get("provider") or _provider_from_model_id(p.get("id", ""))) == provider]
        cloud_providers.append({
            "id": provider,
            "provider": provider,
            "authProfiles": profiles,
            "authTypes": sorted({str(p.get("type") or p.get("mode") or "profile") for p in profiles if p}),
            "models": sorted(model_rows, key=lambda item: item.get("id", "")),
            "modelCount": len(model_rows),
            "source": "openclaw-cloud",
        })
    return sorted(cloud_providers, key=lambda item: item.get("provider", ""))


def _get_openclaw_native_fallback(reason=""):
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)
    except Exception as e:
        return {"ok": False, "error": str(e), "models": [], "authProfiles": [], "agents": {}}
    agents = {}
    for agent in cfg.get("agents", {}).get("list", []):
        agents[agent.get("id")] = {
            "id": agent.get("id"),
            "workspace": agent.get("workspace"),
            "model": agent.get("model", ""),
        }
    models = _read_openclaw_config_models(cfg)
    auth_profiles = _read_openclaw_auth_profiles()
    return {
        "ok": True,
        "warning": reason or "OpenClaw CLI unavailable; read mounted native config/auth store",
        "models": models,
        "authProfiles": auth_profiles,
        "authStatus": {"storePath": os.path.join(OPENCLAW_AGENT_DIR, "openclaw-agent.sqlite"), "source": "sqlite-fallback"},
        "defaultModel": cfg.get("agents", {}).get("defaults", {}).get("model", {}).get("primary", ""),
        "agents": agents,
        "providers": sorted({m["provider"] for m in models if m.get("provider")}),
        "localProviders": _openclaw_local_providers_from_config(cfg),
        "cloudProviders": _openclaw_cloud_providers_from_config(cfg, auth_profiles),
        "nativeCommands": {
            "list": "openclaw models list --all --json",
            "auth": "openclaw models auth list --json",
            "status": "openclaw models status --json",
            "assign": "openclaw config patch / agents.list[].model",
        },
    }


def _get_openclaw_native_models():
    """Return OpenClaw's native model/auth/catalog state."""
    openclaw_bin = OPENCLAW_BIN
    if not openclaw_bin:
        return _get_openclaw_native_fallback("OpenClaw CLI binary unavailable in this container")
    list_result = _run_json_command([openclaw_bin, "models", "list", "--all", "--json"], timeout=45)
    auth_result = _run_json_command([openclaw_bin, "models", "auth", "list", "--json"], timeout=30)
    status_result = _run_json_command([openclaw_bin, "models", "status", "--json"], timeout=30)

    if not list_result.get("ok"):
        return _get_openclaw_native_fallback(list_result.get("error") or "OpenClaw CLI model list failed")

    models = []
    if list_result.get("ok"):
        for m in (list_result.get("data") or {}).get("models", []):
            key = m.get("key") or m.get("id") or ""
            if not key:
                continue
            models.append({
                "id": key,
                "key": key,
                "name": m.get("name") or key.split("/", 1)[-1],
                "provider": m.get("provider") or _provider_from_model_id(key),
                "input": m.get("input"),
                "contextWindow": m.get("contextWindow") or 0,
                "available": bool(m.get("available", not m.get("missing", False))),
                "missing": bool(m.get("missing", False)),
                "local": bool(m.get("local", False)),
                "tags": m.get("tags") or [],
                "source": "openclaw",
            })

    auth_profiles = []
    if auth_result.get("ok"):
        auth_profiles = (auth_result.get("data") or {}).get("profiles", [])
    if not auth_profiles:
        auth_profiles = _read_openclaw_auth_profiles()

    status = status_result.get("data") if status_result.get("ok") else {}
    agents = {}
    default_model = ""
    local_providers = []
    cloud_providers = []
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)
        default_model = cfg.get("agents", {}).get("defaults", {}).get("model", {}).get("primary", "")
        local_providers = _openclaw_local_providers_from_config(cfg)
        cloud_providers = _openclaw_cloud_providers_from_config(cfg, auth_profiles)
        for agent in cfg.get("agents", {}).get("list", []):
            agents[agent.get("id")] = {
                "id": agent.get("id"),
                "workspace": agent.get("workspace"),
                "model": agent.get("model", ""),
            }
    except Exception:
        pass

    return {
        "ok": list_result.get("ok", False),
        "error": list_result.get("error"),
        "models": models,
        "authProfiles": auth_profiles,
        "authStatus": status.get("auth") if isinstance(status, dict) else None,
        "defaultModel": default_model,
        "agents": agents,
        "providers": sorted({m["provider"] for m in models if m.get("provider")}),
        "localProviders": local_providers,
        "cloudProviders": cloud_providers,
        "nativeCommands": {
            "list": "openclaw models list --all --json",
            "auth": "openclaw models auth list --json",
            "status": "openclaw models status --json",
            "assign": "openclaw config patch / agents.list[].model",
        },
    }


def _load_yaml_file(path):
    if not os.path.exists(path):
        return {}
    if yaml:
        try:
            with open(path, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
    # Minimal fallback parser for model and model_aliases when PyYAML is unavailable.
    data = {}
    current = None
    current_alias = None
    try:
        with open(path, "r") as f:
            for raw in f:
                line = raw.rstrip("\n")
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                if not line.startswith(" ") and line.endswith(":"):
                    current = line[:-1].strip()
                    current_alias = None
                    data.setdefault(current, {})
                    continue
                if current and line.startswith("  ") and ":" in line:
                    key, value = line.strip().split(":", 1)
                    value = value.strip().strip("\"'")
                    if current == "model_aliases" and not raw.startswith("    ") and not value:
                        current_alias = key.strip()
                        data.setdefault(current, {}).setdefault(current_alias, {})
                    elif current == "model_aliases" and current_alias and raw.startswith("    "):
                        data.setdefault(current, {}).setdefault(current_alias, {})[key.strip()] = value
                    else:
                        data.setdefault(current, {})[key.strip()] = value
    except Exception:
        return {}
    return data


def _hermes_profile_config_path(profile_id):
    profile_id = str(profile_id or "default")
    if profile_id in ("", "default"):
        return os.path.join(HERMES_HOME, "config.yaml")
    return os.path.join(HERMES_HOME, "profiles", profile_id, "config.yaml")


def _hermes_args(profile_id, *extra):
    args = [HERMES_BIN]
    if profile_id and profile_id != "default":
        args += ["--profile", profile_id]
    args += list(extra)
    return args


def _hermes_env():
    env = dict(os.environ)
    env["HERMES_HOME"] = HERMES_HOME
    return env


def _parse_hermes_auth_list(text_out):
    providers = []
    current = None
    for raw in (text_out or "").splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current = {"provider": line[:-1], "credentials": []}
            providers.append(current)
        elif current and line.strip().startswith("#"):
            parts = line.strip().split()
            current["credentials"].append({
                "label": " ".join(parts[1:-2]) if len(parts) > 3 else line.strip(),
                "type": parts[-2] if len(parts) >= 2 else "",
                "source": parts[-1].replace("←", "") if parts else "",
                "raw": line.strip(),
            })
    return providers


def _get_hermes_profile_auth(profile_id):
    paths = []
    if profile_id and profile_id != "default":
        paths.append(os.path.join(HERMES_HOME, "profiles", profile_id, "auth.json"))
    paths.append(os.path.join(HERMES_HOME, "auth.json"))
    merged = {}
    for path in paths:
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except Exception:
            continue
        for provider, state in (data.get("providers") or {}).items():
            merged.setdefault(provider, {"provider": provider, "credentials": []})
            if state:
                mode = state.get("auth_mode") or state.get("type") or "oauth"
                merged[provider]["credentials"].append({
                    "label": provider,
                    "type": mode,
                    "source": "auth.json",
                })
        for provider, entries in (data.get("credential_pool") or {}).items():
            if not entries:
                continue
            merged.setdefault(provider, {"provider": provider, "credentials": []})
            for entry in entries:
                merged[provider]["credentials"].append({
                    "label": entry.get("label") or entry.get("id") or provider,
                    "type": entry.get("auth_type") or "",
                    "source": entry.get("source") or "credential_pool",
                })
    return list(merged.values())


def _get_hermes_native_models():
    """Return Hermes profile/model/auth state using Hermes' native config layout."""
    profiles = []
    default_cfg = _load_yaml_file(os.path.join(HERMES_HOME, "config.yaml"))
    if default_cfg:
        profiles.append(("default", os.path.join(HERMES_HOME, "config.yaml")))
    profiles_dir = os.path.join(HERMES_HOME, "profiles")
    if os.path.isdir(profiles_dir):
        for name in sorted(os.listdir(profiles_dir)):
            cfg_path = os.path.join(profiles_dir, name, "config.yaml")
            if os.path.exists(cfg_path):
                profiles.append((name, cfg_path))

    provider_cache = {}
    cache_path = os.path.join(HERMES_HOME, "provider_models_cache.json")
    try:
        with open(cache_path, "r") as f:
            cache_data = json.load(f)
        for provider, entry in cache_data.items():
            provider_cache[provider] = entry.get("models", []) if isinstance(entry, dict) else []
    except Exception:
        pass

    result_profiles = []
    for profile_id, cfg_path in profiles:
        cfg = _load_yaml_file(cfg_path)
        model_cfg = cfg.get("model", {}) if isinstance(cfg, dict) else {}
        result_profiles.append({
            "id": profile_id,
            "configPath": cfg_path,
            "provider": model_cfg.get("provider") or "",
            "model": model_cfg.get("default") or model_cfg.get("model") or "",
            "baseUrl": model_cfg.get("base_url") or "",
            "auth": _get_hermes_profile_auth(profile_id),
            "authOk": True,
        })

    models = []
    for provider, names in provider_cache.items():
        for name in names:
            models.append({
                "id": f"{provider}/{name}",
                "provider": provider,
                "name": name,
                "source": "hermes",
                "available": True,
            })

    model_aliases = {}
    local_provider_map = {}
    for profile_id, cfg_path in profiles:
        cfg = _load_yaml_file(cfg_path)
        aliases = cfg.get("model_aliases", {}) if isinstance(cfg, dict) else {}
        if not isinstance(aliases, dict):
            continue
        for alias, entry in aliases.items():
            if not isinstance(entry, dict):
                continue
            provider = entry.get("provider") or "custom"
            model = entry.get("model") or alias
            base_url = entry.get("base_url") or ""
            model_aliases[alias] = {
                "alias": alias,
                "profile": profile_id,
                "provider": provider,
                "model": model,
                "baseUrl": base_url,
            }
            local_key = (profile_id, provider, base_url)
            local_provider_map.setdefault(local_key, {
                "id": f"{profile_id}:{provider}:{base_url}",
                "profile": profile_id,
                "provider": provider,
                "baseUrl": base_url,
                "models": [],
                "source": "hermes-model-aliases",
            })
            local_provider_map[local_key]["models"].append({
                "id": model,
                "name": model,
                "alias": alias,
            })
            mid = f"{provider}/{model}"
            if not any(m.get("id") == mid for m in models):
                models.append({
                    "id": mid,
                    "provider": provider,
                    "name": model,
                    "source": "hermes-alias",
                    "available": True,
                    "baseUrl": base_url,
                })

    return {
        "ok": bool(profiles),
        "profiles": result_profiles,
        "models": models,
        "providers": sorted(set(provider_cache.keys()) | {m.get("provider") for m in models if m.get("provider")}),
        "modelAliases": list(model_aliases.values()),
        "localProviders": [
            {**provider, "modelCount": len(provider.get("models", []))}
            for provider in sorted(local_provider_map.values(), key=lambda item: (item.get("profile", ""), item.get("provider", ""), item.get("baseUrl", "")))
        ],
        "nativeCommands": {
            "setup": "hermes model",
            "auth": "hermes auth list",
            "assign": "hermes config set model.provider <provider>; hermes config set model.default <model>",
        },
    }


def _get_native_model_state():
    return {
        "openclaw": _get_openclaw_native_models(),
        "hermes": _get_hermes_native_models(),
        "codex": _get_codex_native_setup_state(),
        "claudeCode": _get_claude_code_native_setup_state(),
    }


def _get_codex_native_setup_state():
    cfg = VO_CONFIG.get("codex", {}) or {}
    home_path = cfg.get("homePath") or os.path.expanduser("~/.codex")
    return {
        "ok": True,
        "enabled": bool(cfg.get("enabled", True)),
        "binary": cfg.get("binary") or "",
        "homePath": home_path,
        "workspaceRoot": cfg.get("workspaceRoot") or "",
        "mainWorkspace": cfg.get("mainWorkspace") or "",
        "model": cfg.get("model") or "",
        "sandbox": cfg.get("sandbox") or "workspace-write",
        "approvalPolicy": cfg.get("approvalPolicy") or "never",
        "preferAppServer": bool(cfg.get("preferAppServer", True)),
        "includeMain": bool(cfg.get("includeMain", True)),
        "includeNativeAgents": bool(cfg.get("includeNativeAgents", True)),
        "registerNativeAgents": bool(cfg.get("registerNativeAgents", True)),
        "nativeAgentsDir": os.path.join(home_path, "agents") if home_path else "",
        "nativeCommands": {
            "login": "codex login",
            "appServer": "codex app-server --stdio",
            "exec": "codex exec",
            "agents": "$CODEX_HOME/agents/*.toml",
        },
    }


def _get_claude_code_native_setup_state():
    cfg = VO_CONFIG.get("claudeCode", {}) or {}
    home_path = cfg.get("homePath") or os.path.expanduser("~/.claude")
    return {
        "ok": True,
        "enabled": bool(cfg.get("enabled", True)),
        "binary": cfg.get("binary") or "",
        "homePath": home_path,
        "workspaceRoot": cfg.get("workspaceRoot") or "",
        "mainWorkspace": cfg.get("mainWorkspace") or "",
        "model": cfg.get("model") or "",
        "permissionMode": cfg.get("permissionMode") or "acceptEdits",
        "includeMain": bool(cfg.get("includeMain", True)),
        "includeNativeAgents": bool(cfg.get("includeNativeAgents", True)),
        "registerNativeAgents": bool(cfg.get("registerNativeAgents", True)),
        "nativeAgentsDir": os.path.join(home_path, "agents") if home_path else "",
        "nativeCommands": {
            "login": "claude auth login",
            "status": "claude auth status --json",
            "stream": "claude -p --output-format stream-json --include-partial-messages",
            "agents": "$CLAUDE_CONFIG_DIR/agents/*.md",
        },
    }


def _set_hermes_profile_model(profile_id, provider, model, base_url=""):
    profile_id = str(profile_id or "default")
    provider = str(provider or "").strip()
    model = str(model or "").strip()
    if not provider or not model:
        return {"ok": False, "error": "provider and model are required"}
    if re.search(r"[^a-zA-Z0-9_.:-]", provider):
        return {"ok": False, "error": "invalid provider id"}
    cfg_path = _hermes_profile_config_path(profile_id)
    if not os.path.exists(cfg_path):
        return {"ok": False, "error": f"Hermes profile config not found: {cfg_path}"}
    try:
        with open(cfg_path, "r") as f:
            lines = f.read().splitlines()
        output = []
        in_model = False
        seen_model = False
        wrote = {"provider": False, "default": False, "base_url": False}
        for line in lines:
            stripped = line.strip()
            if not line.startswith(" ") and stripped.endswith(":"):
                if in_model:
                    if not wrote["default"]:
                        output.append(f"  default: {model}")
                    if not wrote["provider"]:
                        output.append(f"  provider: {provider}")
                    if base_url and not wrote["base_url"]:
                        output.append(f"  base_url: {str(base_url).strip()}")
                in_model = stripped == "model:"
                seen_model = seen_model or in_model
                output.append(line)
                continue
            if in_model and line.startswith("  ") and ":" in line:
                key = stripped.split(":", 1)[0]
                if key == "default":
                    output.append(f"  default: {model}")
                    wrote["default"] = True
                    continue
                if key == "provider":
                    output.append(f"  provider: {provider}")
                    wrote["provider"] = True
                    continue
                if key == "base_url" and base_url:
                    output.append(f"  base_url: {str(base_url).strip()}")
                    wrote["base_url"] = True
                    continue
            output.append(line)
        if in_model:
            if not wrote["default"]:
                output.append(f"  default: {model}")
            if not wrote["provider"]:
                output.append(f"  provider: {provider}")
            if base_url and not wrote["base_url"]:
                output.append(f"  base_url: {str(base_url).strip()}")
        if not seen_model:
            output.extend(["model:", f"  default: {model}", f"  provider: {provider}"])
            if base_url:
                output.append(f"  base_url: {str(base_url).strip()}")
        with open(cfg_path, "w") as f:
            f.write("\n".join(output) + "\n")
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "profile": profile_id, "provider": provider, "model": model}


def _write_yaml_file(path, data):
    if not yaml:
        return False, "PyYAML is not available; cannot update Hermes YAML config"
    try:
        with open(path, "w") as f:
            yaml.safe_dump(data, f, sort_keys=False)
        return True, None
    except Exception as e:
        return False, str(e)


def _yaml_scalar(value):
    return json.dumps(str(value or ""))


def _read_hermes_aliases_text(lines):
    aliases = {}
    start = None
    end = None
    for i, line in enumerate(lines):
        if line.strip() == "model_aliases:" and not line.startswith(" "):
            start = i
            end = len(lines)
            for j in range(i + 1, len(lines)):
                nxt = lines[j]
                if nxt.strip() and not nxt.startswith(" ") and not nxt.lstrip().startswith("#"):
                    end = j
                    break
            break
    if start is None:
        return aliases, None, None
    current = None
    for line in lines[start + 1:end]:
        if line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":"):
            current = line.strip()[:-1]
            aliases.setdefault(current, {})
            continue
        if current and line.startswith("    ") and ":" in line:
            key, value = line.strip().split(":", 1)
            aliases[current][key.strip()] = value.strip().strip("\"'")
    return aliases, start, end


def _write_hermes_aliases_text(path, aliases):
    try:
        with open(path, "r") as f:
            lines = f.read().splitlines()
    except Exception as e:
        return False, str(e)
    _, start, end = _read_hermes_aliases_text(lines)
    block = []
    if aliases:
        block.append("model_aliases:")
        for alias in sorted(aliases):
            entry = aliases[alias] or {}
            block.append(f"  {alias}:")
            block.append(f"    model: {_yaml_scalar(entry.get('model') or alias)}")
            block.append(f"    provider: {_yaml_scalar(entry.get('provider') or 'custom')}")
            if entry.get("base_url"):
                block.append(f"    base_url: {_yaml_scalar(entry.get('base_url'))}")
    if start is None:
        new_lines = lines + ([""] if lines and lines[-1].strip() else []) + block
    else:
        new_lines = lines[:start] + block + lines[end:]
    try:
        with open(path, "w") as f:
            f.write("\n".join(new_lines).rstrip() + "\n")
        return True, None
    except Exception as e:
        return False, str(e)


def _update_hermes_aliases_text(path, updater):
    try:
        with open(path, "r") as f:
            lines = f.read().splitlines()
    except Exception as e:
        return None, False, str(e)
    aliases, _, _ = _read_hermes_aliases_text(lines)
    aliases = updater(aliases)
    ok, err = _write_hermes_aliases_text(path, aliases)
    return aliases, ok, err


def _save_hermes_api_key(provider, api_key, label=""):
    provider = _safe_provider_id(provider)
    api_key = str(api_key or "").strip()
    label = str(label or "Virtual Office").strip()[:80]
    if not provider or not api_key:
        return {"ok": False, "error": "provider and API key are required"}
    if not HERMES_BIN:
        return {"ok": False, "error": "Hermes CLI is not configured"}
    args = [HERMES_BIN, "auth", "add", provider, "--type", "api-key", "--label", label, "--api-key", api_key]
    result = _run_text_command(args, timeout=30, env=_hermes_env())
    if not result.get("ok"):
        return {"ok": False, "error": result.get("text") or "Hermes auth add failed"}
    return {"ok": True, "provider": provider, "label": label, "maskedKey": _mask_secret(api_key)}


def _delete_hermes_auth(provider, target):
    provider = _safe_provider_id(provider)
    target = str(target or "").strip()
    if not provider or not target:
        return {"ok": False, "error": "provider and credential label/id/index are required"}
    if not HERMES_BIN:
        return {"ok": False, "error": "Hermes CLI is not configured"}
    result = _run_text_command([HERMES_BIN, "auth", "remove", provider, target], timeout=30, env=_hermes_env())
    if not result.get("ok"):
        return {"ok": False, "error": result.get("text") or "Hermes auth remove failed"}
    return {"ok": True, "provider": provider, "target": target}


def _save_hermes_custom_provider(profile_id, provider, base_url, models):
    profile_id = str(profile_id or "default").strip() or "default"
    provider = _safe_provider_id(provider) or "custom"
    base_url = str(base_url or "").strip()
    entries = _parse_model_entries(models)
    if not base_url:
        return {"ok": False, "error": "base URL is required"}
    if not entries:
        return {"ok": False, "error": "at least one model is required"}
    cfg_path = _hermes_profile_config_path(profile_id)
    if not os.path.exists(cfg_path):
        return {"ok": False, "error": f"Hermes profile config not found: {cfg_path}"}
    def update_aliases(aliases):
        for alias, entry in list(aliases.items()):
            if isinstance(entry, dict) and _safe_provider_id(entry.get("provider")) == provider:
                aliases.pop(alias, None)
        for entry in entries:
            alias = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", entry["id"]).strip("-")[:100]
            aliases[alias] = {
                "model": entry["id"],
                "provider": provider,
                "base_url": base_url,
            }
        return aliases
    if yaml:
        cfg = _load_yaml_file(cfg_path)
        if not isinstance(cfg, dict):
            cfg = {}
        aliases = cfg.setdefault("model_aliases", {})
        if not isinstance(aliases, dict):
            aliases = {}
            cfg["model_aliases"] = aliases
        update_aliases(aliases)
        ok, err = _write_yaml_file(cfg_path, cfg)
        if not ok:
            return {"ok": False, "error": err}
    else:
        _, ok, err = _update_hermes_aliases_text(cfg_path, update_aliases)
        if not ok:
            return {"ok": False, "error": err}
    cache_path = os.path.join(HERMES_HOME, "provider_models_cache.json")
    try:
        with open(cache_path, "r") as f:
            cache_data = json.load(f)
    except Exception:
        cache_data = {}
    cache_data[provider] = {"models": [e["id"] for e in entries], "ts": int(time.time())}
    try:
        with open(cache_path, "w") as f:
            json.dump(cache_data, f, indent=2)
    except Exception:
        pass
    return {"ok": True, "profile": profile_id, "provider": provider, "modelCount": len(entries)}


def _delete_hermes_custom_provider(profile_id, provider):
    profile_id = str(profile_id or "default").strip() or "default"
    provider = _safe_provider_id(provider)
    if not provider:
        return {"ok": False, "error": "provider is required"}
    cfg_path = _hermes_profile_config_path(profile_id)
    if not os.path.exists(cfg_path):
        return {"ok": False, "error": f"Hermes profile config not found: {cfg_path}"}
    removed = []
    def remove_aliases(aliases):
        for alias, entry in list(aliases.items()):
            if isinstance(entry, dict) and _safe_provider_id(entry.get("provider")) == provider:
                removed.append(alias)
                aliases.pop(alias, None)
        return aliases
    if yaml:
        cfg = _load_yaml_file(cfg_path)
        if not isinstance(cfg, dict):
            cfg = {}
        aliases = cfg.get("model_aliases", {})
        if isinstance(aliases, dict):
            remove_aliases(aliases)
        ok, err = _write_yaml_file(cfg_path, cfg)
        if not ok:
            return {"ok": False, "error": err}
    else:
        _, ok, err = _update_hermes_aliases_text(cfg_path, remove_aliases)
        if not ok:
            return {"ok": False, "error": err}
    cache_path = os.path.join(HERMES_HOME, "provider_models_cache.json")
    try:
        with open(cache_path, "r") as f:
            cache_data = json.load(f)
        cache_data.pop(provider, None)
        with open(cache_path, "w") as f:
            json.dump(cache_data, f, indent=2)
    except Exception:
        pass
    return {"ok": True, "profile": profile_id, "provider": provider, "removedAliases": removed}


def _save_openclaw_api_key(provider, api_key, profile_id=""):
    provider = _safe_provider_id(provider)
    api_key = str(api_key or "").strip()
    profile_id = str(profile_id or f"{provider}:manual").strip()
    if not provider or not api_key:
        return {"ok": False, "error": "provider and API key are required"}
    if not OPENCLAW_BIN:
        return _save_openclaw_api_key_direct(provider, profile_id, api_key)
    try:
        result = subprocess.run(
            [OPENCLAW_BIN, "models", "auth", "paste-api-key", "--provider", provider, "--profile-id", profile_id],
            input=api_key + "\n",
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if result.returncode != 0:
        return {"ok": False, "error": (result.stderr or result.stdout or "OpenClaw auth write failed").strip()}
    return {"ok": True, "provider": provider, "profileId": profile_id, "maskedKey": _mask_secret(api_key)}

# ─── DYNAMIC AGENT DISCOVERY ─────────────────────────────────
from discovery import discover_all_agents, get_agent_workspace_dir, get_agent_session_id
from providers.hermes import HermesApiClient, HermesProvider
from providers.codex import CodexProvider
from providers.claude_code import ClaudeCodeProvider
from license import get_license_status, activate_license, deactivate_license, check_feature, get_agent_limit
from project_store import MarkdownProjectStore

PROJECT_STORE = MarkdownProjectStore(STATUS_DIR)


AGENT_PLATFORM_COMM_SKILL_NAME = "AgentPlatform-to-AgentPlatform_Communications"


# Agent workspace service logic lives in server_services.agents.



# Agent skills-library seed content lives in server_services.skills.


def _discover_roster():
    hermes = VO_CONFIG.get("hermes", {})
    codex = VO_CONFIG.get("codex", {})
    claude_code = VO_CONFIG.get("claudeCode", {})
    return discover_all_agents(
        WORKSPACE_BASE,
        hermes_home=hermes.get("homePath"),
        hermes_bin=hermes.get("binary"),
        hermes_enabled=hermes.get("enabled", True),
        codex=codex,
        claude_code=claude_code,
    )

_discovered_roster = _discover_roster()
_discovered_at = time.time()
DISCOVERY_REFRESH_SEC = 300  # re-discover every 5 min

def _refresh_discovery():
    """Refresh agent roster if stale."""
    global _discovered_roster, _discovered_at
    if time.time() - _discovered_at > DISCOVERY_REFRESH_SEC:
        _discovered_roster = _discover_roster()
        _discovered_at = time.time()

def get_roster():
    """Get current discovered agent roster."""
    _refresh_discovery()
    return _discovered_roster


def _apply_agent_limit_balanced(agents):
    """Apply product agent limits without hiding entire provider types.

    The old behavior sliced the discovered list, which meant newly added
    providers like Hermes could be detected but never visible in demo/limited
    modes because OpenClaw agents came first. This keeps licensing limits while
    trying to include at least one agent from each detected provider.
    """
    agent_limit = get_agent_limit()
    if agent_limit <= 0 or len(agents) <= agent_limit:
        return agents

    selected = []
    selected_keys = set()

    def key_for(a):
        return a.get("key") or a.get("statusKey") or a.get("agentId") or a.get("id")

    # First pass: one representative from each provider in discovery order.
    seen_providers = set()
    for agent in agents:
        provider = agent.get("providerKind", "openclaw")
        if provider in seen_providers:
            continue
        seen_providers.add(provider)
        k = key_for(agent)
        selected.append(agent)
        selected_keys.add(k)
        if len(selected) >= agent_limit:
            return selected

    # Fill remaining slots using original order.
    for agent in agents:
        k = key_for(agent)
        if k in selected_keys:
            continue
        selected.append(agent)
        selected_keys.add(k)
        if len(selected) >= agent_limit:
            break
    return selected


def _load_office_agent_overrides():
    overrides = {}
    branches = {}
    try:
        oc_path = os.path.join(STATUS_DIR, "office-config.json")
        with open(oc_path, "r") as f:
            data = json.load(f)
        for agent in data.get("agents", []):
            if not isinstance(agent, dict):
                continue
            keys = [
                agent.get("id"),
                agent.get("statusKey"),
                agent.get("agentId"),
                agent.get("providerAgentId"),
                agent.get("profile"),
            ]
            provider_kind = str(agent.get("providerKind") or "").strip()
            provider_agent_id = str(agent.get("providerAgentId") or agent.get("profile") or "").strip()
            if provider_kind and provider_agent_id:
                keys.append(f"{provider_kind}-{provider_agent_id}")
            for key in keys:
                if key:
                    overrides[str(key)] = agent
        for branch in data.get("branches", []):
            if not isinstance(branch, dict):
                continue
            branch_id = branch.get("id", "")
            if branch_id:
                branches[branch_id] = branch.get("name", branch_id)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return overrides, branches


def _office_agent_override_for(discovered_agent, overrides):
    candidates = [
        discovered_agent.get("statusKey"),
        discovered_agent.get("id"),
        discovered_agent.get("agentId"),
    ]
    provider_kind = str(discovered_agent.get("providerKind") or "").strip()
    provider_agent_id = str(discovered_agent.get("providerAgentId") or discovered_agent.get("profile") or "").strip()
    if provider_kind and provider_agent_id:
        candidates.append(f"{provider_kind}-{provider_agent_id}")
    if provider_kind in {"", "openclaw"}:
        candidates.extend([
            discovered_agent.get("providerAgentId"),
            discovered_agent.get("profile"),
        ])
    for key in candidates:
        if key and str(key) in overrides:
            return overrides[str(key)]
    return {}


# Build compatibility maps from discovery (these update on refresh)
def _build_agent_info():
    return {
        a["statusKey"]: {
            "id": a["id"],
            "emoji": a.get("emoji") or "🤖",
            "name": a.get("name") or a.get("id") or a.get("statusKey"),
            "branch": "",
            "providerKind": a.get("providerKind", "openclaw"),
        }
        for a in get_roster()
        if a.get("statusKey") and a.get("id")
    }
def _build_agent_workspaces():
    result = {}
    for a in get_roster():
        if a.get("providerKind", "openclaw") != "openclaw":
            result[a["statusKey"]] = a.get("home") or a.get("workspace") or ""
        else:
            workspace = a.get("workspace", "")
            result[a["statusKey"]] = get_agent_workspace_dir(WORKSPACE_BASE, a["id"]).replace(WORKSPACE_BASE + "/", "") if workspace.startswith(WORKSPACE_BASE) else os.path.basename(workspace)
    return result
def _build_agent_session_ids():
    return {a["statusKey"]: (a.get("providerAgentId") if a.get("providerKind", "openclaw") != "openclaw" else get_agent_session_id(a["id"])) for a in get_roster()}

# Compatibility properties (lazily rebuilt)
@property
def _agent_info_prop(self):
    return _build_agent_info()

# For now, build once and provide as module-level (callers use these directly)
AGENT_INFO = _build_agent_info()
AGENT_WORKSPACES = _build_agent_workspaces()
AGENT_SESSION_IDS = _build_agent_session_ids()

def _patch_default_config_agents(config_str):
    """Replace hardcoded agents in default config with actual roster agents.
    Returns JSON string with agents patched from the live discovery roster."""
    try:
        cfg = json.loads(config_str)
    except Exception:
        return config_str
    roster = get_roster()
    if not roster:
        return config_str
    # Build agent entries from roster with random/seeded appearances
    patched_agents = []
    for a in roster:
        agent_id = a.get("statusKey") or a.get("id", "main")
        name = a.get("name") or agent_id
        # Seed a deterministic hash for random appearance
        h = int(hashlib.md5(agent_id.encode()).hexdigest(), 16)
        skin_tones = ['#ffcc80','#d4a574','#c68642','#e8b88a','#fddcb5','#f5d0b0','#8d5524']
        hair_styles = ['short','medium','long','curly','spiky','buzz','wavy']
        hair_colors = ['#1a1a1a','#333333','#5d4037','#616161','#bf360c','#dcc282','#ffd700','#263238']
        desk_items = ['trophy','envelope','calendar','chart','plans','checklist','files','ruler','money','marker']
        gender = 'F' if (h >> 2) % 2 == 0 else 'M'
        patched_agents.append({
            "id": agent_id,
            "name": name,
            "role": a.get("role", "AI assistant"),
            "emoji": a.get("emoji", "🤖"),
            "color": _AGENT_COLORS_LIST[len(patched_agents) % len(_AGENT_COLORS_LIST)] if len(patched_agents) < len(_AGENT_COLORS_LIST) else '#607d8b',
            "gender": gender,
            "branch": "UNASSIGNED",
            "statusKey": agent_id,
            "appearance": {
                "skinTone": skin_tones[h % len(skin_tones)],
                "hairStyle": hair_styles[(h >> 3) % len(hair_styles)] if gender == 'M' else hair_styles[(h >> 3) % 3 + 2],
                "hairColor": hair_colors[(h >> 5) % len(hair_colors)],
                "hairHighlight": None,
                "eyebrowStyle": "thin" if gender == 'F' else "thick",
                "eyeColor": "#212121",
                "facialHair": None, "facialHairColor": None,
                "headwear": None, "headwearColor": None,
                "glasses": None, "glassesColor": None,
                "costume": None,
                "heldItem": None,
                "deskItem": desk_items[(h >> 8) % len(desk_items)]
            }
        })
    cfg["agents"] = patched_agents
    return json.dumps(cfg)

# Color palette used for default config agent patching
_AGENT_COLORS_LIST = ['#ffd700','#d32f2f','#1976d2','#388e3c','#f9a825','#e65100','#00897b','#7b1fa2','#6d4c41','#5c6bc0','#78909c','#4caf50','#00bcd4','#e91e90','#ff6d00','#795548','#607d8b','#9c27b0','#009688','#ff5722']

def refresh_agent_maps():
    """Call after discovery refresh to update compatibility maps."""
    global AGENT_INFO, AGENT_WORKSPACES, AGENT_SESSION_IDS
    AGENT_INFO = _build_agent_info()
    AGENT_WORKSPACES = _build_agent_workspaces()
    AGENT_SESSION_IDS = _build_agent_session_ids()


def _agent_display_label(agent_id_or_key):
    """Return a friendly VO label for an agent id/status key without exposing internals."""
    if not agent_id_or_key:
        return ""
    needle = str(agent_id_or_key)
    for a in get_roster():
        if needle in (a.get("id"), a.get("statusKey")):
            name = a.get("name") or needle
            emoji = a.get("emoji") or ""
            return f"{name} {emoji}".strip()
    return needle


def _agent_id_from_session_key(session_key):
    """Parse OpenClaw session keys like agent:<agentId>:<bucket>."""
    if not session_key:
        return ""
    m = re.match(r"^agent:([^:]+):", str(session_key))
    if m:
        return m.group(1)
    m = re.match(r"^agent-([^-:]+)-openai-", str(session_key))
    return m.group(1) if m else ""


def _openclaw_gateway_session_key(agent_id, session_key):
    if not agent_id or not session_key:
        return session_key or ""
    raw = str(session_key)
    if raw.startswith(f"agent:{agent_id}:"):
        return raw
    return f"agent:{agent_id}:{raw}"


def _openclaw_session_key_candidates(agent_id, session_key):
    raw = str(session_key or "")
    gateway_key = _openclaw_gateway_session_key(agent_id, raw)
    keys = []
    for key in (gateway_key, raw):
        if key and key not in keys:
            keys.append(key)
    return keys


def _openclaw_get_session_info(sessions_data, agent_id, session_key):
    if not isinstance(sessions_data, dict):
        return {}, ""
    for key in _openclaw_session_key_candidates(agent_id, session_key):
        info = sessions_data.get(key)
        if isinstance(info, dict):
            return info, key
    return {}, ""


def _is_hermes_agent(agent_id_or_key):
    needle = str(agent_id_or_key or "")
    for a in get_roster():
        if needle in (a.get("id"), a.get("statusKey"), a.get("providerAgentId")):
            return a.get("providerKind") == "hermes"
    return needle.startswith("hermes:") or needle.startswith("hermes-")


def _is_codex_agent(agent_id_or_key):
    needle = str(agent_id_or_key or "")
    for a in get_roster():
        if needle in (a.get("id"), a.get("statusKey"), a.get("providerAgentId")):
            return a.get("providerKind") == "codex"
    return needle.startswith("codex:")


def _is_claude_code_agent(agent_id_or_key):
    needle = str(agent_id_or_key or "")
    for a in get_roster():
        if needle in (a.get("id"), a.get("statusKey"), a.get("providerAgentId")):
            return a.get("providerKind") == "claude-code"
    return needle.startswith("claude-code:") or needle.startswith("claude-code-")


def _get_codex_agent(agent_id_or_key=None):
    needle = str(agent_id_or_key or "")
    for a in get_roster():
        if a.get("providerKind") == "codex" and (not needle or needle in (a.get("id"), a.get("statusKey"), a.get("providerAgentId"))):
            return a
    return None


def _get_claude_code_agent(agent_id_or_key=None):
    needle = str(agent_id_or_key or "")
    for a in get_roster():
        if a.get("providerKind") == "claude-code" and (not needle or needle in (a.get("id"), a.get("statusKey"), a.get("providerAgentId"))):
            return a
    return None


def _parse_iso_epoch_ms(value):
    """Convert ISO timestamps or epoch-ish values to browser-friendly epoch ms."""
    if not value:
        return 0
    if isinstance(value, (int, float)):
        return int(value if value > 1e12 else value * 1000)
    try:
        raw = str(value)
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return 0


def _read_tail_text(path, initial_bytes=64 * 1024, max_bytes=2 * 1024 * 1024, min_lines=20):
    """Read a complete-line tail from large JSONL files."""
    if not path or not os.path.exists(path):
        return ""
    try:
        with open(path, "rb") as fb:
            fb.seek(0, 2)
            fsize = fb.tell()
            tail_size = min(initial_bytes, fsize)
            while True:
                start = max(0, fsize - tail_size)
                fb.seek(start)
                tail_data = fb.read().decode("utf-8", errors="replace")
                if start > 0:
                    nl = tail_data.find("\n")
                    if nl >= 0:
                        tail_data = tail_data[nl + 1:]
                complete_lines = [x for x in tail_data.split("\n") if x.strip()]
                if start == 0 or len(complete_lines) >= min_lines or tail_size >= min(max_bytes, fsize):
                    return tail_data
                tail_size = min(tail_size * 4, max_bytes, fsize)
    except Exception:
        return ""


def _openclaw_session_paths(agent_id, session_key=None):
    """Resolve the active transcript and matching trajectory file for an agent session."""
    if not agent_id:
        return None, None, {}
    sessions_dir = os.path.join(WORKSPACE_BASE, f"agents/{agent_id}/sessions")
    sessions_json_path = os.path.join(sessions_dir, "sessions.json")
    session_info = {}
    try:
        with open(sessions_json_path, "r") as f:
            sessions = json.load(f)
        if session_key:
            session_info, _ = _openclaw_get_session_info(sessions, agent_id, session_key)
        if not session_info:
            best_ts = -1
            for val in sessions.values():
                if not isinstance(val, dict):
                    continue
                ts = val.get("updatedAt", 0)
                if ts > best_ts:
                    best_ts = ts
                    session_info = val
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        session_info = {}

    session_id = str(session_info.get("sessionId") or "")
    jsonl_file = os.path.join(sessions_dir, f"{session_id}.jsonl") if session_id else None
    trajectory_file = os.path.join(sessions_dir, f"{session_id}.trajectory.jsonl") if session_id else None
    if jsonl_file and not os.path.exists(jsonl_file):
        jsonl_file = None
    if trajectory_file and not os.path.exists(trajectory_file):
        trajectory_file = None
    return jsonl_file, trajectory_file, session_info


def _safe_tool_arguments(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {"value": value}
    return {}


def _limit_tool_payload(value, limit=2400):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            value = json.dumps(value, ensure_ascii=False)
        except Exception:
            value = str(value)
    value = str(value)
    if len(value) > limit:
        return value[:limit] + f"\n\n... [truncated - {len(value)} chars total] ..."
    return value


def _trajectory_activity_messages(trajectory_file, max_tools=60):
    """Recover recent tool calls/results from OpenClaw trajectory JSONL."""
    tail_data = _read_tail_text(trajectory_file, initial_bytes=256 * 1024, max_bytes=4 * 1024 * 1024, min_lines=80)
    if not tail_data:
        return []

    tools = {}
    order = []
    for line in tail_data.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = event.get("type") or ""
        if event_type not in ("tool.call", "tool.result"):
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        tool_id = str(data.get("toolCallId") or data.get("tool_call_id") or data.get("itemId") or event.get("id") or "")
        if not tool_id:
            tool_id = f"{event.get('seq', len(order))}:{event_type}"
        if tool_id not in tools:
            tools[tool_id] = {
                "id": tool_id,
                "runId": event.get("runId") or data.get("runId") or "",
                "status": "running",
                "name": data.get("name") or data.get("toolName") or "tool",
                "arguments": {},
                "result": "",
                "error": "",
                "ts": event.get("ts") or "",
                "epochMs": _parse_iso_epoch_ms(event.get("ts")),
                "source": "trajectory",
            }
            order.append(tool_id)
        tool = tools[tool_id]
        if event.get("ts"):
            tool["ts"] = event.get("ts")
            tool["epochMs"] = _parse_iso_epoch_ms(event.get("ts"))
        if event_type == "tool.call":
            tool["status"] = "running"
            tool["name"] = data.get("name") or data.get("toolName") or tool.get("name") or "tool"
            tool["arguments"] = _safe_tool_arguments(data.get("arguments") or data.get("args") or {})
        elif event_type == "tool.result":
            is_error = bool(data.get("isError") or data.get("error"))
            tool["status"] = "error" if is_error else "done"
            tool["name"] = data.get("name") or data.get("toolName") or tool.get("name") or "tool"
            result = data.get("output")
            if result is None:
                result = data.get("result")
            if result is None:
                result = data.get("error")
            if is_error:
                tool["error"] = _limit_tool_payload(result)
            else:
                tool["result"] = _limit_tool_payload(result)

    messages = []
    for tool_id in order[-max_tools:]:
        tool = tools.get(tool_id)
        if not tool:
            continue
        ts = tool.get("ts") or ""
        messages.append({
            "role": "assistant",
            "text": "",
            "ts": ts,
            "epochMs": tool.get("epochMs") or 0,
            "tools": [tool],
            "source": "trajectory",
        })
    return messages


def _session_trajectory_messages(session_key, max_tools=80):
    agent_id = _agent_id_from_session_key(session_key)
    if not agent_id:
        return []
    _, trajectory_file, _ = _openclaw_session_paths(agent_id, session_key=session_key)
    return _trajectory_activity_messages(trajectory_file, max_tools=max_tools)




# Provider bridge domain logic lives in server_services.agent_bridges.



# Agent platform communication service logic lives in server_services.agents.



def _parse_a2a_envelope(text):
    """Parse the lightweight VO A2A display envelope, if present.

    This is display metadata only. Agent trust/authority still comes from
    OpenClaw provenance or the sender wrapper, never from arbitrary text alone.
    Supported form:
      [A2A from=main name="Office Agent" to=agent-id isUser=false]
    """
    if not text:
        return None, text
    m = re.match(r"^\s*\[A2A\s+([^\]]+)\]\s*\n?", text)
    if not m:
        return None, text
    attrs = {}
    raw = m.group(1)
    for km in re.finditer(r"([A-Za-z][\w-]*)=(\"[^\"]*\"|'[^']*'|\S+)", raw):
        val = km.group(2).strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        attrs[km.group(1)] = val
    return attrs, text[m.end():].lstrip()

##############################################################################
# AGENT CREATION + SKILLS MANAGEMENT
##############################################################################

# Agent lifecycle helper logic lives in server_services.agents.



# Agent skills and skills-library handlers live in server_services.skills.



def _load_meetings_file():
    """Load the persistent meetings/status file."""
    try:
        with open(STATUS_FILE, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def _save_meetings_file(data):
    """Persist the meetings/status file with permissive mode for shared runtimes."""
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    with open(STATUS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    try:
        os.chmod(STATUS_FILE, 0o666)
    except Exception:
        pass


_EXEC_MEETING_LOCK = threading.RLock()
_EXEC_MEETING_TERMINAL = {"completed", "cancelled", "failed"}
_EXEC_MEETING_PHASES = {
    "draft", "conflict", "preparing", "active_opening", "active_discussion", "paused",
    "awaiting_user_decision", "summarizing", "completed", "cancelled", "failed",
}
_EXEC_MEETING_TRANSITIONS = {
    "draft": {"preparing", "cancelled"},
    "conflict": {"preparing", "cancelled", "failed"},
    "preparing": {"active_opening", "paused", "cancelled", "failed"},
    "active_opening": {"active_discussion", "paused", "summarizing", "cancelled", "failed"},
    "active_discussion": {"awaiting_user_decision", "summarizing", "paused", "cancelled", "failed"},
    "paused": {"preparing", "active_opening", "active_discussion", "awaiting_user_decision", "cancelled", "failed"},
    "awaiting_user_decision": {"active_discussion", "summarizing", "cancelled", "failed"},
    "summarizing": {"completed", "cancelled", "failed"},
    "completed": set(),
    "cancelled": set(),
    "failed": set(),
}
_MEETING_CONTEXT_MODES = {"incremental", "summary", "full"}
_MEETING_DEFAULT_CONTEXT_BUDGET = {
    "maxPromptChars": 12000,
    "maxInitialContextChars": 4000,
    "maxSummaryChars": 3000,
    "maxRecentEvents": 6,
}








def _exec_meetings_file():
    return os.path.join(STATUS_DIR, "executable-meetings.json")








_MEETING_REQUEST_LOCK = threading.RLock()
_MEETING_REQUEST_STATUSES = {"pending", "rejected", "confirmed"}






def _load_meeting_request_store():
    try:
        with open(_meeting_requests_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _meeting_request_empty_store()
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return _meeting_request_empty_store()
    data.setdefault("requests", {})
    data.setdefault("idempotency", {})
    data.setdefault("updatedAt", "")
    if not isinstance(data["requests"], dict):
        data["requests"] = {}
    if not isinstance(data["idempotency"], dict):
        data["idempotency"] = {}
    return data


def _save_meeting_request_store(data):
    data["updatedAt"] = _exec_meeting_now()
    path = _meeting_requests_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}-{threading.get_ident()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o666)
    except Exception:
        pass








































_PROJECT_EXECUTION_FEISHU_REWORK_FEEDBACK = "Requested rework from Feishu"
















def _send_project_execution_acceptance_notification(project, task, attempt_id, reason=""):
    if not isinstance(project, dict) or not isinstance(task, dict) or not attempt_id:
        return {"ok": True, "status": "skipped_invalid_project_task"}
    key = f"project-acceptance:{attempt_id}"
    marker_container = _project_execution_notification_container(task, attempt_id)
    if _feishu_notification_marker(marker_container, key):
        return {"ok": True, "status": "skipped_duplicate", "dedupeKey": key}
    project_id = project.get("id") or ""
    task_id = task.get("id") or ""
    intent = {
        "id": key,
        "type": "application_form",
        "title": f"项目任务等待验收: {task.get('title') or task_id}",
        "summary": reason or "Project Execution 已完成并通过 Review，等待用户验收。",
        "state": "pending",
        "multi_participant": False,
        "related": _project_execution_related(project, task),
        "details": [
            ("项目", project.get("title") or project_id or "-"),
            ("任务", task.get("title") or task_id or "-"),
            ("Attempt", attempt_id),
            ("Review", ((task.get("reviewResult") or {}).get("summary") or "-")),
        ],
        "inputs": [{
            "name": "feedback",
            "label": "返工原因",
            "placeholder": "点击“要求返工”前填写需要补充或重做的内容",
            "multiline": True,
            "required": False,
        }],
        "actions": [
            {
                "category": "confirm",
                "text": "接受",
                "value": {
                    "action": "project_execution_accept",
                    "project_id": project_id,
                    "task_id": task_id,
                    "attempt_id": attempt_id,
                },
            },
            {
                "category": "cancel",
                "text": "要求返工",
                "value": {
                    "action": "project_execution_rework",
                    "project_id": project_id,
                    "task_id": task_id,
                    "attempt_id": attempt_id,
                },
            },
            {
                "category": "jump",
                "text": "打开任务",
                "url": _project_execution_open_url(project_id, task_id),
            },
        ],
        "target": "feishu-project-execution-acceptance",
    }
    result = _send_feishu_workflow_notification(intent)
    _mark_feishu_notification(marker_container, key, result)
    return result


def _send_project_execution_intervention_notification(project, task, reason="", attempt_id=None, *, event="blocked", kind="warning"):
    if not isinstance(project, dict) or not isinstance(task, dict):
        return {"ok": True, "status": "skipped_invalid_project_task"}
    reason = _project_execution_redact(reason or task.get("blockedReason") or task.get("lastError") or "Project Execution needs user intervention.")
    key_seed = attempt_id or task.get("activeAttemptId") or ((task.get("evidence") or {}).get("attemptId")) or ""
    key = f"project-intervention:{event}:{key_seed or task.get('id')}"
    marker_container = _project_execution_notification_container(task, key_seed)
    if _feishu_notification_marker(marker_container, key):
        return {"ok": True, "status": "skipped_duplicate", "dedupeKey": key}
    project_id = project.get("id") or ""
    task_id = task.get("id") or ""
    intent = {
        "id": key,
        "type": kind if kind in {"warning", "error"} else "warning",
        "title": f"项目任务需要处理: {task.get('title') or task_id}",
        "summary": reason,
        "related": _project_execution_related(project, task),
        "details": [
            ("项目", project.get("title") or project_id or "-"),
            ("任务", task.get("title") or task_id or "-"),
            ("状态", task.get("executionState") or event),
            ("Attempt", key_seed or "-"),
        ],
        "actions": [{
            "category": "jump",
            "text": "打开任务",
            "url": _project_execution_open_url(project_id, task_id),
        }],
        "target": "feishu-project-execution-intervention",
    }
    result = _send_feishu_workflow_notification(intent)
    _mark_feishu_notification(marker_container, key, result)
    return result




def _send_project_execution_project_complete_notification(project, reason=""):
    if not isinstance(project, dict):
        return {"ok": True, "status": "skipped_invalid_project"}
    completed = _project_execution_completed_task_count(project)
    if completed <= 0:
        return {"ok": True, "status": "skipped_no_completed_tasks"}
    key = f"project-complete:{project.get('id') or ''}:{completed}"
    if _feishu_notification_marker(project, key):
        return {"ok": True, "status": "skipped_duplicate", "dedupeKey": key}
    intent = {
        "id": key,
        "type": "notification",
        "title": f"项目执行完成: {project.get('title') or project.get('id') or 'Untitled project'}",
        "summary": reason or f"Project Execution 已完成，当前没有可继续执行的任务。已完成任务数：{completed}。",
        "related": {"type": "project", "id": project.get("id") or "", "title": project.get("title") or "Project"},
        "details": [
            ("项目", project.get("title") or project.get("id") or "-"),
            ("已完成任务数", completed),
            ("总任务数", len(project.get("tasks") or [])),
        ],
        "actions": [{
            "category": "jump",
            "text": "打开项目",
            "url": _project_execution_open_url(project.get("id") or "", ""),
        }],
        "target": "feishu-project-execution-complete",
    }
    result = _send_feishu_workflow_notification(intent)
    _mark_feishu_notification(project, key, result)
    return result




def _send_meeting_failure_notification(meeting, failure=None):
    if not isinstance(meeting, dict):
        return {"ok": True, "status": "skipped_invalid_meeting"}
    failure = failure if isinstance(failure, dict) else {}
    meeting_id = meeting.get("id") or ""
    sequence = failure.get("failedAtSequence") or meeting.get("lastEventSequence") or ""
    key = f"meeting-failure:{meeting_id}:{sequence or failure.get('reason') or meeting.get('stage') or 'failed'}"
    if _feishu_notification_marker(meeting, key):
        return {"ok": True, "status": "skipped_duplicate", "dedupeKey": key}
    summary = _project_execution_redact(_meeting_truncate_text(
        failure.get("error") or meeting.get("error") or "AI meeting failed and needs user attention.",
        1000,
    ))
    intent = {
        "id": key,
        "type": "error",
        "title": f"AI 会议失败: {meeting.get('topic') or meeting_id}",
        "summary": summary,
        "error_variant": "user_facing",
        "related": {"type": "meeting", "id": meeting_id, "title": meeting.get("topic") or "AI meeting"},
        "details": [
            ("会议", meeting.get("topic") or meeting_id or "-"),
            ("阶段", meeting.get("stage") or "-"),
            ("主持人", failure.get("moderator") or meeting.get("moderator") or "-"),
            ("原因", failure.get("reason") or "meeting_failed"),
        ],
        "actions": [{
            "category": "jump",
            "text": "打开会议",
            "url": _meeting_open_url(meeting_id),
        }],
        "target": "feishu-meeting-failure",
    }
    result = _send_feishu_workflow_notification(intent)
    _mark_feishu_notification(meeting, key, result)
    return result




















def _record_feishu_card_action(body, event, value, outcome=None):
    record = {
        "id": str(uuid.uuid4()),
        "receivedAt": _exec_meeting_now(),
        "schema": str(body.get("schema") or ""),
        "type": str(body.get("type") or body.get("header", {}).get("event_type") or ""),
        "action": str(value.get("action") or value.get("action_category") or ""),
        "notificationId": str(value.get("notification_id") or ""),
        "requestId": str(value.get("request_id") or ""),
        "user": _feishu_card_action_user(event),
        "messageId": str(event.get("open_message_id") or event.get("message_id") or ""),
        "chatId": str(event.get("open_chat_id") or event.get("chat_id") or ""),
        "value": value,
    }
    if isinstance(outcome, dict):
        record["outcome"] = outcome
    os.makedirs(os.path.dirname(_feishu_card_action_log_path()), exist_ok=True)
    with open(_feishu_card_action_log_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record








def _dispatch_feishu_meeting_request_action(action, request_id, event):
    if action not in {"confirm_meeting_request", "reject_meeting_request"}:
        return {"handled": False}
    if not request_id:
        return {
            "handled": True,
            "ok": False,
            "businessStatus": "missing_request_id",
            "toast": _feishu_card_action_error("会议申请缺少 request_id，无法处理"),
        }
    actor = _feishu_meeting_action_actor(event)
    if action == "confirm_meeting_request":
        result = _handle_meeting_request_confirm(request_id, {
            "confirmedBy": actor,
            "idempotencyKey": f"feishu-confirm:{request_id}",
        })
        if result.get("ok"):
            idempotent = bool(result.get("idempotent"))
            meeting_id = str(result.get("meetingId") or "")
            run_result = None
            run_summary = {}
            if meeting_id:
                run_result = _handle_executable_meeting_run(meeting_id, {
                    "action": "start",
                    "actorId": actor,
                    "actorType": "user",
                })
                run_summary = {
                    "attempted": True,
                    "ok": bool(run_result.get("ok")) if isinstance(run_result, dict) else False,
                    "stage": ((run_result or {}).get("meeting") or {}).get("stage") if isinstance(run_result, dict) else "",
                    "error": (run_result or {}).get("error") if isinstance(run_result, dict) else "Meeting start failed",
                }
            if run_summary.get("attempted") and not run_summary.get("ok"):
                return {
                    "handled": True,
                    "ok": True,
                    "businessStatus": "confirmed_start_failed",
                    "businessError": str(run_summary.get("error") or "会议启动失败"),
                    "idempotent": idempotent,
                    "meetingId": meeting_id,
                    "run": run_summary,
                    "toast": _feishu_card_action_error(f"会议申请已同意，但启动会议失败：{run_summary.get('error') or '未知错误'}"),
                }
            return {
                "handled": True,
                "ok": True,
                "businessStatus": "confirmed_started" if run_summary.get("attempted") else "confirmed",
                "idempotent": idempotent,
                "meetingId": meeting_id,
                "run": run_summary,
                "toast": _feishu_card_action_success("会议申请已同意，会议已开始" + ("（已处理）" if idempotent else "")),
            }
        return {
            "handled": True,
            "ok": False,
            "businessStatus": str(result.get("code") or result.get("status") or "confirm_failed"),
            "businessError": str(result.get("error") or "会议申请无法同意"),
            "toast": _feishu_card_action_error(str(result.get("error") or "会议申请无法同意")),
        }
    result = _handle_meeting_request_reject(request_id, {
        "rejectedBy": actor,
        "reason": "Rejected from Feishu",
    })
    if result.get("ok"):
        idempotent = bool(result.get("idempotent"))
        return {
            "handled": True,
            "ok": True,
            "businessStatus": "rejected",
            "idempotent": idempotent,
            "toast": _feishu_card_action_success("会议申请已拒绝" + ("（已处理）" if idempotent else "")),
        }
    return {
        "handled": True,
        "ok": False,
        "businessStatus": str(result.get("code") or result.get("status") or "reject_failed"),
        "businessError": str(result.get("error") or "会议申请无法拒绝"),
        "toast": _feishu_card_action_error(str(result.get("error") or "会议申请无法拒绝")),
    }


def _dispatch_feishu_project_execution_action(action, value, event):
    if action not in {"project_execution_accept", "project_execution_rework"}:
        return {"handled": False}
    project_id = str(value.get("project_id") or value.get("projectId") or "").strip()
    task_id = str(value.get("task_id") or value.get("taskId") or "").strip()
    attempt_id = str(value.get("attempt_id") or value.get("attemptId") or "").strip()
    if not project_id or not task_id or not attempt_id:
        return {
            "handled": True,
            "ok": False,
            "businessStatus": "missing_project_execution_context",
            "toast": _feishu_card_action_error("项目任务验收缺少上下文，无法处理"),
        }
    actor = _feishu_meeting_action_actor(event)
    body = {
        "action": "accept" if action == "project_execution_accept" else "reject_and_rework",
        "attemptId": attempt_id,
        "actor": actor,
    }
    if action == "project_execution_rework":
        body["feedback"] = _feishu_card_action_form_text(event, "feedback", "rework_feedback", "reason") or _PROJECT_EXECUTION_FEISHU_REWORK_FEEDBACK
    result = _handle_project_execution_acceptance(project_id, task_id, body)
    if result.get("ok"):
        return {
            "handled": True,
            "ok": True,
            "businessStatus": str(result.get("status") or "accepted"),
            "toast": _feishu_card_action_success("项目任务已接受" if action == "project_execution_accept" else "已要求任务返工"),
        }
    return {
        "handled": True,
        "ok": False,
        "businessStatus": str(result.get("code") or result.get("status") or "project_execution_action_failed"),
        "businessError": str(result.get("error") or "项目任务验收操作失败"),
        "toast": _feishu_card_action_error(str(result.get("error") or "项目任务验收操作失败")),
    }




def _get_feishu_long_connection_receiver():
    global _FEISHU_LONG_CONNECTION_RECEIVER
    return _FEISHU_LONG_CONNECTION_RECEIVER


def _start_feishu_long_connection():
    global _FEISHU_LONG_CONNECTION_RECEIVER
    cfg = VO_CONFIG.get("notifications", {}) or {}
    if cfg.get("feishuEnabled", True) is False:
        return {"enabled": False, "running": False, "status": "disabled"}
    app_id = str(cfg.get("feishuAppId") or "").strip()
    app_secret = str(cfg.get("feishuAppSecret") or "").strip()
    if not app_id or not app_secret:
        return {"enabled": False, "running": False, "status": "missing_app_credentials"}
    with _FEISHU_LONG_CONNECTION_LOCK:
        existing = _FEISHU_LONG_CONNECTION_RECEIVER
        if existing and existing.app_id == app_id and existing.app_secret == app_secret:
            return existing.start()
        _FEISHU_LONG_CONNECTION_RECEIVER = FeishuLongConnectionReceiver(
            app_id=app_id,
            app_secret=app_secret,
            action_handler=_handle_feishu_card_action,
        )
        return _FEISHU_LONG_CONNECTION_RECEIVER.start()










































































def _append_ignored_provider_completion(store, meeting, speaker, result, normalized, pending, reason, expected_stage, expected_round, kind=""):
    payload = {
        "speaker": speaker,
        "kind": kind,
        "reason": reason,
        "expectedStage": expected_stage,
        "expectedRound": expected_round,
        "currentStage": meeting.get("stage"),
        "currentRound": meeting.get("round"),
        "text": normalized.get("text") or "",
        "rawText": normalized.get("rawText") or "",
        "structured": normalized.get("structured") or {},
        "parseError": normalized.get("parseError") or "",
        "ok": bool(result.get("ok")),
        "providerRef": result.get("providerRef") or _meeting_provider_ref(speaker),
        "conversationId": result.get("conversationId") or "",
        "durationMs": result.get("durationMs") or 0,
        "inReplyToSequence": pending.get("sequence") if pending else None,
    }
    if normalized.get("providerRaw"):
        payload["providerRaw"] = normalized.get("providerRaw")
    return _append_exec_meeting_event(store, meeting, "provider_call_ignored", actor={"type": "agent", "id": speaker}, payload=payload)






































































_MEETING_STRUCTURED_KEYS = {
    "position": "position",
    "reasoning": "reasoning",
    "disagreements": "disagreements",
    "questions": "questions",
    "suggestedNextStep": "suggestedNextStep",
    "suggested_next_step": "suggestedNextStep",
    "confidence": "confidence",
}


















































##############################################################################
# ─── PROJECTS SCORING / GAMIFICATION ─────────────────────────────────────────
SCORES_FILE = os.path.join(STATUS_DIR, "project-scores.json")





def _score_agent_entry():
    return {"score": 0, "completed": 0, "streak": 0, "lastCompleted": None, "history": [], "meetings": 0}

def _score_valid_agent_key(agent_key):
    key = str(agent_key or "").strip()
    if not key or key in ("null", "None", "unassigned"):
        return ""
    if _is_archive_manager_agent(key):
        return ""
    return key

def _award_meeting_participation_points(meeting, points=None):
    """Award lightweight XP for completed executable meeting participation.

    This intentionally does not use _award_points(): meeting participation
    should not increment task completion counts or task-completion streaks.
    """
    if not isinstance(meeting, dict) or meeting.get("stage") != "completed":
        return {"awarded": False, "reason": "meeting_not_completed"}
    meeting_id = str(meeting.get("id") or "").strip()
    if not meeting_id:
        return {"awarded": False, "reason": "missing_meeting_id"}
    score_awarded = meeting.setdefault("scoreAwarded", {})
    existing = score_awarded.get("meetingParticipantXp")
    if isinstance(existing, dict) and existing.get("awarded"):
        return {"awarded": False, "alreadyAwarded": True, "award": existing}

    try:
        award_points = int(points if points is not None else SCORE_MEETING_PARTICIPANT_XP)
    except (TypeError, ValueError):
        award_points = SCORE_MEETING_PARTICIPANT_XP
    if award_points <= 0:
        return {"awarded": False, "reason": "non_positive_points"}

    participants = []
    seen = set()
    for raw_participant in meeting.get("participants") or []:
        participant = _score_valid_agent_key(raw_participant)
        if participant and participant not in seen:
            participants.append(participant)
            seen.add(participant)

    now_str = datetime.now(timezone.utc).isoformat()
    topic = str(meeting.get("topic") or meeting.get("agenda") or "AI meeting").strip()
    reason = f"Meeting completed: {topic}"
    award = {
        "awarded": True,
        "type": "meeting_participation",
        "meetingId": meeting_id,
        "points": award_points,
        "participants": participants,
        "at": now_str,
        "reason": reason,
    }
    score_awarded["meetingParticipantXp"] = award

    if not participants:
        return {"awarded": False, "reason": "no_valid_participants", "award": award}

    data = _load_scores()
    agents = data.setdefault("agents", {})
    for participant in participants:
        agent = agents.get(participant)
        if not isinstance(agent, dict):
            agent = _score_agent_entry()
        agent.setdefault("score", 0)
        agent.setdefault("completed", 0)
        agent.setdefault("streak", 0)
        agent.setdefault("history", [])
        agent["score"] = int(agent.get("score") or 0) + award_points
        agent["meetings"] = int(agent.get("meetings") or 0) + 1
        history = agent.get("history") if isinstance(agent.get("history"), list) else []
        history.append({
            "type": "meeting_participation",
            "points": award_points,
            "reason": reason,
            "meetingId": meeting_id,
            "meetingTopic": topic,
            "at": now_str,
        })
        agent["history"] = history[-50:]
        agents[participant] = agent
    _save_scores(data)
    return {"awarded": True, "award": award}




# ── SCORING POINT VALUES ──────────────────────────────────────────────────────
SCORE_TASK_COMPLETED = 10        # Base points for completing a task
SCORE_CRITICAL_BONUS = 15       # Extra for critical priority
SCORE_HIGH_BONUS = 10           # Extra for high priority
SCORE_MEDIUM_BONUS = 5          # Extra for medium priority
SCORE_ON_TIME_BONUS = 10        # Extra for completing before due date
SCORE_CHECKLIST_BONUS = 2       # Per checklist item completed
SCORE_MEETING_PARTICIPANT_XP = 3  # Per participant in a completed executable meeting


# ─── PROJECTS API ────────────────────────────────────────────────────────────
##############################################################################

_PROJECTS_FILE_LOCK = threading.Lock()
_PROJECT_CRON_BINDINGS_LOCK = threading.Lock()
_PROJECT_CRON_HISTORY_LIMIT = 200
_PROJECT_CRON_ALERT_STATUSES = {"failed", "intervention_required"}
















def _load_project_cron_bindings():
    path = _project_cron_bindings_file()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    bindings = data.get("bindings")
    if not isinstance(bindings, dict):
        bindings = {}
    # Drop malformed entries at read time so older/bad files cannot break API responses.
    clean = {}
    for cron_id, binding in bindings.items():
        if isinstance(binding, dict) and binding.get("projectId") and binding.get("targetType"):
            clean[str(cron_id)] = binding
    return {"version": 1, "bindings": clean}


def _save_project_cron_bindings(data):
    path = _project_cron_bindings_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    payload = {
        "version": 1,
        "bindings": data.get("bindings", {}) if isinstance(data, dict) else {},
    }
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)






















































# ── Built-in templates ────────────────────────────────────────────────────────
_BUILTIN_TEMPLATES = [
    {
        "id": "tpl-software",
        "title": "Software Development",
        "description": "Standard software development workflow with sprint planning",
        "builtin": True,
        "columns": [
            {"title": "Backlog", "color": "#6c757d"},
            {"title": "Sprint", "color": "#0d6efd"},
            {"title": "In Progress", "color": "#ffc107"},
            {"title": "Code Review", "color": "#fd7e14"},
            {"title": "QA", "color": "#17a2b8"},
            {"title": "Done", "color": "#198754"},
        ],
        "taskTemplates": [
            {"title": "Set up development environment", "columnIndex": 0, "priority": "high"},
            {"title": "Define acceptance criteria", "columnIndex": 0, "priority": "medium"},
            {"title": "Write unit tests", "columnIndex": 0, "priority": "medium"},
        ],
    },
    {
        "id": "tpl-marketing",
        "title": "Marketing Campaign",
        "description": "Plan and execute marketing campaigns",
        "builtin": True,
        "columns": [
            {"title": "Ideas", "color": "#6c757d"},
            {"title": "Planning", "color": "#0d6efd"},
            {"title": "Creating", "color": "#ffc107"},
            {"title": "Review", "color": "#fd7e14"},
            {"title": "Published", "color": "#198754"},
        ],
        "taskTemplates": [
            {"title": "Define target audience", "columnIndex": 0, "priority": "high"},
            {"title": "Create content calendar", "columnIndex": 0, "priority": "medium"},
        ],
    },
    {
        "id": "tpl-bugs",
        "title": "Bug Tracking",
        "description": "Track and resolve bugs systematically",
        "builtin": True,
        "columns": [
            {"title": "Reported", "color": "#dc3545"},
            {"title": "Confirmed", "color": "#fd7e14"},
            {"title": "In Progress", "color": "#ffc107"},
            {"title": "Fixed", "color": "#0d6efd"},
            {"title": "Verified", "color": "#198754"},
        ],
        "taskTemplates": [],
    },
    {
        "id": "tpl-content",
        "title": "Content Pipeline",
        "description": "Manage content creation workflow",
        "builtin": True,
        "columns": [
            {"title": "Backlog", "color": "#6c757d"},
            {"title": "Research", "color": "#17a2b8"},
            {"title": "Writing", "color": "#ffc107"},
            {"title": "Editing", "color": "#fd7e14"},
            {"title": "Published", "color": "#198754"},
        ],
        "taskTemplates": [],
    },
]

# ── GET handlers ──────────────────────────────────────────────────────────────









# ── POST handlers ─────────────────────────────────────────────────────────────



















# ── PUT handlers ──────────────────────────────────────────────────────────────









# ── DELETE handlers ───────────────────────────────────────────────────────────





# ─── PHASE 7A UNIVERSAL PROJECT EXECUTION ────────────────────────────────────

_PROJECT_EXECUTION_LOCK = threading.Lock()
_PROJECT_EXECUTION_CANCEL_FLAGS = {}
_PROJECT_EXECUTION_REVIEW_FLAGS = set()
_PROJECT_EXECUTION_MAX_TEXT = 12000
_PROJECT_EXECUTION_MAX_EVIDENCE_LINE = 360
_PROJECT_EXECUTION_SECRET_RE = re.compile(
    r"(?i)(authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)\s*[:=]\s*([^\s,;]+)"
)
































_PROJECT_EXECUTION_COLUMN_LOCKED_STATES = {
    "executing",
    "retrying",
    "reworking",
    "reviewing",
    "execution_complete",
    "awaiting_user_acceptance",
    "awaiting_meeting_resolution",
}


















































































































_ARTIFACT_EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache", "dist", "build",
    "dist-packages",
}
_ARTIFACT_MARKDOWN_EXTENSIONS = {".md", ".markdown"}
_ARTIFACT_TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".csv", ".json", ".yaml", ".yml", ".log"}
_ARTIFACT_DOCUMENT_EXTENSIONS = _ARTIFACT_TEXT_EXTENSIONS | {".pdf"}
_ARTIFACT_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
_ARTIFACT_VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogg", ".mov", ".m4v"}
_ARTIFACT_AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"}
_ARTIFACT_ALLOWED_EXTENSIONS = (
    _ARTIFACT_DOCUMENT_EXTENSIONS
    | _ARTIFACT_IMAGE_EXTENSIONS
    | _ARTIFACT_VIDEO_EXTENSIONS
    | _ARTIFACT_AUDIO_EXTENSIONS
)
_ARTIFACT_MAX_ITEMS = 500
_ARTIFACT_MAX_READ_BYTES = 512 * 1024


































# Archive Room domain logic lives in server_services.archive_room.


# Project workflow engine lives in server_services.workflow.


# Agent delete service logic lives in server_services.agents.



##############################################################################

def get_agent_messages(agent_key, max_messages=500):
    """Read recent messages from an agent's active session JSONL."""
    agent_id = AGENT_SESSION_IDS.get(agent_key)
    if not agent_id:
        return []
    sessions_dir = os.path.join(WORKSPACE_BASE, f"agents/{agent_id}/sessions")
    jsonl_file = None
    trajectory_file = None
    # Find the most recently updated session entry first. If its transcript
    # file is missing (can happen after compaction/restart), do NOT fall back
    # to an older session-store entry; that makes bubbles show stale cron/DM
    # sessions. Instead, fall through to the newest real transcript by mtime.
    jsonl_file, trajectory_file, _session_info = _openclaw_session_paths(agent_id)
    if not jsonl_file:
        # Only consider primary transcript files named <uuid>.jsonl. Ignore
        # trajectory/checkpoint/reset JSONL artifacts, which can be newer but
        # are not suitable for chat bubbles.
        uuid_jsonl = re.compile(r"^[0-9a-fA-F-]{36}\.jsonl$")
        jsonls = [
            p for p in glob.glob(os.path.join(sessions_dir, "*.jsonl"))
            if uuid_jsonl.match(os.path.basename(p))
        ]
        if jsonls:
            jsonl_file = max(jsonls, key=os.path.getmtime)
            base = jsonl_file[:-len(".jsonl")]
            candidate_trajectory = base + ".trajectory.jsonl"
            if os.path.exists(candidate_trajectory):
                trajectory_file = candidate_trajectory
    if not jsonl_file:
        return _trajectory_activity_messages(trajectory_file, max_tools=min(80, max_messages))
    messages = []
    try:
        # Performance: read the tail instead of the whole JSONL. Some model/tool
        # messages (notably image reads) can be a single very large JSONL line;
        # grow the tail window until we have enough complete recent lines.
        tail_data = _read_tail_text(jsonl_file, initial_bytes=32 * 1024, max_bytes=2 * 1024 * 1024, min_lines=20)
        for line in tail_data.split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "message":
                    continue
                msg = entry.get("message", {})
                role = msg.get("role", "")
                ts = entry.get("timestamp", "")
                if role == "toolResult":
                    continue
                content = msg.get("content", "")
                text = ""
                media = []

                def _add_media_url(_url, _mime="", _name=""):
                    if not _url:
                        return
                    _url = str(_url).strip()
                    if not _url:
                        return
                    _name = _name or os.path.basename(urllib.parse.urlparse(_url).path) or "attachment"
                    _mime = _mime or mimetypes.guess_type(_name)[0] or mimetypes.guess_type(_url)[0] or ""
                    media.append({"url": _url, "mimeType": _mime, "name": _name})

                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    parts = []
                    tool_calls = []
                    for item in content:
                        if isinstance(item, dict):
                            item_type = item.get("type")
                            if item_type == "text":
                                t = item.get("text", "").strip()
                                if t:
                                    parts.append(t)
                            elif item_type in ("image", "image_url", "input_image", "file", "media", "attachment", "video", "audio"):
                                src = item.get("url") or item.get("path") or item.get("filePath") or item.get("mediaUrl")
                                if not src and isinstance(item.get("image_url"), dict):
                                    src = item.get("image_url", {}).get("url")
                                if not src and isinstance(item.get("source"), dict):
                                    src = item.get("source", {}).get("url") or item.get("source", {}).get("path")
                                _add_media_url(src, item.get("mimeType") or item.get("media_type") or item.get("contentType") or "", item.get("name") or item.get("filename") or "")
                            elif item.get("type") == "toolCall":
                                name = item.get("name", "")
                                args = item.get("arguments", {})
                                if name == "exec":
                                    cmd = args.get("command", "")
                                    if "office.py" in cmd:
                                        tool_calls.append(f"\u2699\ufe0f {cmd.split('office.py')[1].strip()[:80]}")
                                    elif "openclaw agent" in cmd:
                                        m_agent = re.search(r'--agent\s+(\S+)', cmd)
                                        m_msg = re.search(r'--message\s+"([^"]*)"', cmd)
                                        aname = m_agent.group(1) if m_agent else "?"
                                        mtxt = m_msg.group(1)[:60] if m_msg else ""
                                        tool_calls.append(f"\ud83d\udce1 \u2192 {aname}: {mtxt}")
                                    else:
                                        tool_calls.append(f"\u2699\ufe0f {cmd[:60]}")
                                elif name == "process":
                                    tool_calls.append("\u23f3 polling...")
                                elif name == "read":
                                    tool_calls.append("\ud83d\udcc4 reading file")
                                elif name == "sessions_send":
                                    smsg = args.get("message", "")[:60]
                                    slabel = args.get("label", args.get("sessionKey", ""))
                                    tool_calls.append(f"\ud83d\udce8 \u2192 {slabel}: {smsg}")
                                else:
                                    tool_calls.append(f"\ud83d\udd27 {name}")
                    text = "\n".join(parts)
                    if tool_calls:
                        tc_text = "\n".join(tool_calls)
                        text = f"{text}\n{tc_text}" if text else tc_text
                for _line in (text or "").splitlines():
                    _m = re.match(r"^\(attached file:\s*(.+?)\)$", _line.strip(), re.I) or re.match(r"^attached file:\s*(.+)$", _line.strip(), re.I)
                    if _m:
                        _path = _m.group(1).strip()
                        _mime = mimetypes.guess_type(_path)[0] or ""
                        _add_media_url(_path, _mime, os.path.basename(_path))
                if not text and not media:
                    continue

                # Sender attribution for agent-to-agent / inter-session turns.
                # OpenClaw keeps role='user' for provider compatibility, so VO
                # needs provenance/display metadata to avoid showing agent input
                # as a generic human "IN:" message.
                from_agent = ""
                from_agent_id = ""
                to_agent = _agent_display_label(agent_id)
                to_agent_id = agent_id
                is_inter_session = False
                provenance_kind = ""
                prov = msg.get("provenance", {}) if isinstance(msg.get("provenance", {}), dict) else {}
                if role == "user" and prov.get("kind") == "inter_session":
                    provenance_kind = "inter_session"
                    is_inter_session = True
                    source = prov.get("sourceSessionKey", "")
                    from_agent_id = _agent_id_from_session_key(source)
                    from_agent = _agent_display_label(from_agent_id) if from_agent_id else "Agent"

                a2a_meta, clean_text = _parse_a2a_envelope(text)
                if a2a_meta:
                    text = clean_text
                    is_inter_session = True
                    from_agent_id = a2a_meta.get("from") or from_agent_id
                    if a2a_meta.get("name"):
                        from_agent = a2a_meta.get("name")
                    elif from_agent_id:
                        from_agent = _agent_display_label(from_agent_id)
                    if a2a_meta.get("to"):
                        to_agent_id = a2a_meta.get("to")
                        to_agent = _agent_display_label(to_agent_id)

                # Send raw epoch ms to client — browser converts to local timezone
                epoch_ms = 0
                if ts:
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        epoch_ms = int(dt.timestamp() * 1000)
                    except Exception:
                        pass
                messages.append({
                    "role": role,
                    "text": text[:500],
                    "ts": ts,
                    "epochMs": epoch_ms,
                    "from": from_agent,
                    "fromAgentId": from_agent_id,
                    "to": to_agent,
                    "toAgentId": to_agent_id,
                    "isInterSession": is_inter_session,
                    "provenanceKind": provenance_kind,
                    "media": media[:4],
                })
    except Exception as e:
        return []
    if trajectory_file:
        messages.extend(_trajectory_activity_messages(trajectory_file, max_tools=80))
        messages.sort(key=lambda m: m.get("epochMs") or 0)
    return messages[-max_messages:]


def get_codex_agent_messages(profile, max_messages=500):
    """Read recent Codex provider history for floor chat bubbles."""
    messages = []
    for msg in _load_codex_history(profile)[-max_messages:]:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "assistant")
        text = str(msg.get("text") or "")
        tools = msg.get("tools") if isinstance(msg.get("tools"), list) else []
        thinking = str(msg.get("thinking") or "")
        approval = msg.get("approval") if isinstance(msg.get("approval"), dict) else None
        if not text and not tools and not thinking and not approval:
            continue
        epoch_ms = _codex_int(msg.get("epochMs") or msg.get("ts"), 0)
        messages.append({
            "role": role,
            "text": text[:500],
            "ts": epoch_ms,
            "epochMs": epoch_ms,
            "from": msg.get("from") or ("User" if role == "user" else ""),
            "fromType": msg.get("fromType") or "",
            "tools": tools,
            "thinking": thinking,
            "reasoningTokens": _codex_int(msg.get("reasoningTokens"), 0),
            "approval": approval,
            "source": msg.get("source") or "codex",
        })
    return messages[-max_messages:]


def get_claude_code_agent_messages(profile, max_messages=500):
    """Read recent Claude Code provider history for floor chat bubbles."""
    messages = []
    for msg in _load_claude_code_history(profile)[-max_messages:]:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "assistant")
        text = str(msg.get("text") or "")
        tools = msg.get("tools") if isinstance(msg.get("tools"), list) else []
        thinking = str(msg.get("thinking") or "")
        if not text and not tools and not thinking:
            continue
        epoch_ms = _codex_int(msg.get("epochMs") or msg.get("ts"), 0)
        messages.append({
            "role": role,
            "text": text[:500],
            "ts": epoch_ms,
            "epochMs": epoch_ms,
            "from": msg.get("from") or ("User" if role == "user" else ""),
            "fromType": msg.get("fromType") or "",
            "tools": tools,
            "thinking": thinking,
            "reasoningTokens": _codex_int(msg.get("reasoningTokens"), 0),
            "source": msg.get("source") or "claude-code",
        })
    return messages[-max_messages:]

GATEWAY_URL = VO_CONFIG["openclaw"]["gatewayUrl"]
GATEWAY_URL_FALLBACK = GATEWAY_URL.replace("127.0.0.1", "localhost") if "127.0.0.1" in GATEWAY_URL else GATEWAY_URL

# Extract gateway port for local Host header override.
# When connecting via Docker bridge (host.docker.internal), websockets sets
# Host: host.docker.internal:PORT which the gateway treats as non-local,
# triggering origin allowlist checks. By overriding Host to 127.0.0.1:PORT,
# the gateway correctly recognizes the connection as local and skips the check.
def _compute_local_host_header(gw_url):
    from urllib.parse import urlparse
    parsed = urlparse(gw_url)
    port = parsed.port or 18789
    return f"127.0.0.1:{port}"

_GW_LOCAL_HOST = _compute_local_host_header(GATEWAY_URL)


def _get_gateway_token():
    """Get the gateway auth token.

    Resolution order:
    1. Explicit env var override
    2. Fresh read from vo-config.json (user override saved in setup/settings)
    3. Current in-memory VO_CONFIG copy
    4. openclaw.json gateway auth token
    """
    env_token = os.environ.get("VO_GATEWAY_TOKEN") or os.environ.get("OPENCLAW_GATEWAY_TOKEN")
    if env_token:
        return env_token

    cfg_path = _resolve_config_path()
    for try_path in [cfg_path, os.path.join(os.path.dirname(__file__), "vo-config.json")]:
        try:
            with open(try_path, "r") as f:
                cfg = json.load(f)
            vo_token = ((cfg.get("openclaw") or {}).get("gatewayToken") or "").strip()
            if vo_token:
                return vo_token
        except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
            continue

    vo_token = ((VO_CONFIG.get("openclaw") or {}).get("gatewayToken") or "").strip()
    if vo_token:
        return vo_token

    # Fall back to openclaw.json
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)
        return ((cfg.get("gateway", {}).get("auth", {}).get("token", "") or "").strip())
    except Exception:
        return ""


def _auto_configure_gateway_origin():
    """Auto-configure the OpenClaw gateway to accept connections from this VO instance.

    Adds the VO's origin to gateway.controlUi.allowedOrigins in openclaw.json
    and signals the gateway to reload. This makes Docker bridge networking
    work without any manual gateway configuration — truly plug and play.

    Safe for all setups:
    - --network host: gateway treats connection as local, skips origin check (no-op)
    - Docker bridge: origin gets added to allowlist on first boot
    - Already configured: detects existing entry, skips
    """
    origin = f"http://127.0.0.1:{PORT}"
    try:
        try:
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"⚠️  Gateway auto-config: cannot read {CONFIG_PATH}")
            return

        gateway_cfg = cfg.setdefault("gateway", {})
        control_ui = gateway_cfg.setdefault("controlUi", {})

        origins = control_ui.get("allowedOrigins", [])
        if not isinstance(origins, list):
            origins = []

        if origin in origins:
            return  # already configured

        origins.append(origin)
        control_ui["allowedOrigins"] = origins
        control_ui["allowInsecureAuth"] = True
        control_ui["dangerouslyDisableDeviceAuth"] = True

        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)

        # Signal gateway to reload config
        try:
            r = subprocess.run(["systemctl", "--user", "kill", "-s", "USR1", "openclaw-gateway.service"],
                               capture_output=True, timeout=5)
            if r.returncode == 0:
                print(f"✅ Gateway auto-config: added origin {origin}, gateway reloaded")
                return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Fallback: scan /proc for gateway process and send SIGUSR1
        try:
            for entry in os.listdir("/proc"):
                if not entry.isdigit():
                    continue
                try:
                    with open(f"/proc/{entry}/cmdline", "r") as f:
                        cmdline = f.read()
                    if "openclaw" in cmdline and "gateway" in cmdline:
                        os.kill(int(entry), signal.SIGUSR1)
                        print(f"✅ Gateway auto-config: added origin {origin}, signaled PID {entry}")
                        return
                except (PermissionError, FileNotFoundError, ProcessLookupError):
                    continue
        except FileNotFoundError:
            pass  # not on Linux

        print(f"✅ Gateway auto-config: added origin {origin} (gateway will pick up on next restart)")
    except Exception as e:
        print(f"⚠️  Gateway auto-config failed: {e}")
GATEWAY_HTTP = VO_CONFIG["openclaw"]["gatewayHttp"]
CONFIG_PATH = os.path.join(WORKSPACE_BASE, "openclaw.json")
APP_DIR = os.path.dirname(os.path.abspath(__file__))


def _reload_gateway_globals():
    """Reload all gateway-related globals from current VO_CONFIG.
    Call after VO_CONFIG has been refreshed (e.g. after /setup/save)."""
    global GATEWAY_URL, GATEWAY_URL_FALLBACK, _GW_LOCAL_HOST, GATEWAY_HTTP
    global CONFIG_PATH, AUTH_PROFILES_PATH, OPENCLAW_HOME, OPENCLAW_AGENT_DIR, OPENCLAW_BIN, HERMES_HOME, HERMES_BIN
    GATEWAY_URL = VO_CONFIG["openclaw"]["gatewayUrl"]
    GATEWAY_URL_FALLBACK = GATEWAY_URL.replace("127.0.0.1", "localhost") if "127.0.0.1" in GATEWAY_URL else GATEWAY_URL
    _GW_LOCAL_HOST = _compute_local_host_header(GATEWAY_URL)
    GATEWAY_HTTP = VO_CONFIG["openclaw"]["gatewayHttp"]
    CONFIG_PATH = os.path.join(WORKSPACE_BASE, "openclaw.json")
    AUTH_PROFILES_PATH = os.path.join(WORKSPACE_BASE, "agents/main/agent/auth-profiles.json")
    OPENCLAW_HOME = os.path.expanduser(os.environ.get("OPENCLAW_HOME") or WORKSPACE_BASE or "~/.openclaw")
    OPENCLAW_AGENT_DIR = os.path.join(OPENCLAW_HOME, "agents/main/agent")
    OPENCLAW_BIN = (
        os.environ.get("OPENCLAW_BIN")
        or VO_CONFIG.get("openclaw", {}).get("binary")
        or shutil.which("openclaw")
    )
    HERMES_HOME = os.path.expanduser(os.environ.get("HERMES_HOME") or VO_CONFIG.get("hermes", {}).get("homePath") or "~/.hermes")
    HERMES_BIN = (
        os.environ.get("HERMES_BIN")
        or VO_CONFIG.get("hermes", {}).get("binary")
        or shutil.which("hermes")
    )


# ---------------------------------------------------------------------------
# API Usage Collector — background thread that fetches quota data directly
# from provider APIs using credentials from OpenClaw auth profiles.
# No CLI dependency. Pure Python. Works in any environment.
# ---------------------------------------------------------------------------

# Provider display names
_PROVIDER_LABELS = {
    "anthropic": "Claude",
    "openai-codex": "Codex",
    "openai": "OpenAI",
    "github-copilot": "Copilot",
    "google-gemini-cli": "Gemini",
    "minimax": "MiniMax",
    "zai": "Z.AI",
}


class ApiUsageCollector:
    """Collects API usage/quota data directly from provider endpoints.

    Reads auth profiles from OpenClaw's auth-profiles.json, then calls each
    provider's usage API to get real quota windows (daily/weekly percentages,
    reset times, etc.).

    Runs in a background thread. The HTTP handler reads the cached result.
    """

    INTERVAL = 60  # seconds between collections
    REQUEST_TIMEOUT = 15  # seconds per provider API call

    def __init__(self, auth_profiles_path):
        self._auth_profiles_path = auth_profiles_path
        self._data = {"providers": [], "timestamp": 0, "source": "initializing"}
        self._lock = threading.Lock()
        self._thread = None

    def start(self):
        """Start the background collection thread."""
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="api-usage-collector")
        self._thread.start()

    def get_data(self):
        """Thread-safe read of the latest usage data."""
        with self._lock:
            return dict(self._data)

    def _run_loop(self):
        time.sleep(3)  # let server start
        while True:
            try:
                data = self._collect()
                with self._lock:
                    self._data = data
            except Exception as e:
                with self._lock:
                    self._data = {"providers": [], "timestamp": time.time(), "error": str(e), "source": "error"}
            time.sleep(self.INTERVAL)

    def _read_profiles(self):
        """Read OpenClaw auth profiles from the configured native store."""
        sqlite_profiles = self._read_profiles_from_sqlite()
        if sqlite_profiles:
            return sqlite_profiles
        try:
            with open(self._auth_profiles_path, "r") as f:
                ap = json.load(f)
            return ap.get("profiles", {})
        except Exception:
            return {}

    def _read_profiles_from_sqlite(self):
        db_path = os.path.join(OPENCLAW_AGENT_DIR, "openclaw-agent.sqlite")
        if not os.path.exists(db_path):
            return {}
        try:
            con = sqlite3.connect(db_path)
            con.row_factory = sqlite3.Row
            table_names = [
                row[0]
                for row in con.execute("select name from sqlite_master where type='table'")
            ]
            for table in ("auth_profile_store", "auth_profile_stores"):
                if table not in table_names:
                    continue
                cols = [row[1] for row in con.execute(f"pragma table_info({table})")]
                if "store_json" not in cols:
                    continue
                for row in con.execute(f"select store_json from {table}").fetchall():
                    try:
                        data = json.loads(row["store_json"] or "{}")
                    except Exception:
                        continue
                    profiles = data.get("profiles")
                    if isinstance(profiles, dict) and profiles:
                        con.close()
                        return profiles
            con.close()
        except Exception:
            return {}
        return {}

    def _profile_rank(self, profile):
        """Prefer profiles that can expose real quota windows over plain API keys."""
        prov = profile.get("provider", "")
        has_token = bool(profile.get("access") or profile.get("token"))
        has_key = bool(profile.get("key"))
        ptype = str(profile.get("type") or profile.get("mode") or "").lower()
        if prov in ("openai", "openai-codex") and has_token:
            return 0
        if prov == "anthropic" and has_token:
            return 0
        if prov == "github-copilot" and has_token:
            return 1
        if has_token or ptype in ("oauth", "token", "subscription"):
            return 2
        if has_key:
            return 5
        return 9

    def _collect(self):
        """Run one collection cycle across all configured providers."""
        now = time.time()
        profiles = self._read_profiles()
        if not profiles:
            return {"providers": [], "timestamp": now, "source": "no-profiles"}

        providers = []
        grouped = {}
        for pid, profile in profiles.items():
            if not isinstance(profile, dict):
                continue
            prov = profile.get("provider") or pid.split(":", 1)[0]
            if not prov:
                continue
            profile = dict(profile)
            profile["_profileId"] = pid
            canonical = "openai" if prov == "openai-codex" else prov
            grouped.setdefault(canonical, []).append(profile)

        for canonical, provider_profiles in grouped.items():
            provider_profiles.sort(key=self._profile_rank)
            profile = provider_profiles[0]
            prov = profile.get("provider") or canonical

            token = profile.get("access") or profile.get("token")
            api_key = profile.get("key")
            account_id = profile.get("accountId")

            result = None
            if prov == "anthropic" and token:
                result = self._fetch_claude(token, now)
            elif prov in ("openai", "openai-codex") and token:
                result = self._fetch_codex(token, account_id, now)
            elif prov == "github-copilot" and token:
                result = self._fetch_copilot(token, now)
            elif api_key and canonical not in ("ollama", "lmstudio"):
                result = {
                    "provider": canonical,
                    "displayName": _PROVIDER_LABELS.get(canonical, canonical.replace("-", " ").title()),
                    "type": "api_key",
                    "usage": None,
                    "status": "configured",
                    "message": "API key configured. This provider does not expose account quota windows through the standard API key interface.",
                }

            if result:
                result.setdefault("provider", canonical)
                result.setdefault("profileId", profile.get("_profileId", ""))
                result.setdefault("authType", str(profile.get("type") or profile.get("mode") or ("oauth" if token else "api_key")))
                result.setdefault("profilesFound", len(provider_profiles))
                providers.append(result)

        return {"providers": providers, "timestamp": now, "source": "openclaw-native-auth"}

    def _http_get(self, url, headers):
        """Make an HTTP GET request. Returns (status, response_body_dict_or_None)."""
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.REQUEST_TIMEOUT) as resp:
                body = json.loads(resp.read().decode())
                return resp.status, body
        except urllib.error.HTTPError as e:
            # Try to parse error body
            try:
                body = json.loads(e.read().decode())
            except Exception:
                body = None
            return e.code, body
        except Exception:
            return 0, None

    # --- Anthropic (Claude) ---
    def _fetch_claude(self, token, now):
        """Fetch Claude usage from Anthropic OAuth endpoint."""
        status, data = self._http_get("https://api.anthropic.com/api/oauth/usage", {
            "Authorization": f"Bearer {token}",
            "User-Agent": "openclaw",
            "Accept": "application/json",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "oauth-2025-04-20",
        })
        entry = {
            "provider": "anthropic",
            "displayName": _PROVIDER_LABELS.get("anthropic", "Claude"),
            "type": "oauth",
        }
        if status != 200 or not data:
            msg = ""
            if data and isinstance(data, dict):
                msg = data.get("error", {}).get("message", "") if isinstance(data.get("error"), dict) else str(data.get("error", ""))
            entry["error"] = f"HTTP {status}: {msg}" if msg else f"HTTP {status}"
            if status == 429:
                entry["message"] = "Claude usage endpoint is rate limited. Model access can still work; usage will refresh after the provider allows another check."
            return entry

        # Parse usage windows
        windows = []
        if isinstance(data.get("five_hour"), dict) and data["five_hour"].get("utilization") is not None:
            windows.append({
                "label": "5h",
                "usedPercent": min(100, max(0, data["five_hour"]["utilization"])),
                "resetAt": int(self._parse_ts(data["five_hour"].get("resets_at"))) if data["five_hour"].get("resets_at") else 0,
            })
        if isinstance(data.get("seven_day"), dict) and data["seven_day"].get("utilization") is not None:
            windows.append({
                "label": "Week",
                "usedPercent": min(100, max(0, data["seven_day"]["utilization"])),
                "resetAt": int(self._parse_ts(data["seven_day"].get("resets_at"))) if data["seven_day"].get("resets_at") else 0,
            })
        # Model-specific windows (sonnet/opus)
        for key, label in [("seven_day_sonnet", "Sonnet"), ("seven_day_opus", "Opus")]:
            mw = data.get(key)
            if isinstance(mw, dict) and mw.get("utilization") is not None:
                windows.append({
                    "label": label,
                    "usedPercent": min(100, max(0, mw["utilization"])),
                })

        if windows:
            entry["usage"] = self._windows_to_usage(windows, now)
            entry["windows"] = windows
        return entry

    # --- OpenAI Codex ---
    def _fetch_codex(self, token, account_id, now):
        """Fetch ChatGPT/Codex usage from OpenAI's OAuth-backed usage endpoint."""
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "CodexBar",
            "Accept": "application/json",
        }
        if account_id:
            headers["ChatGPT-Account-Id"] = account_id

        status, data = self._http_get("https://chatgpt.com/backend-api/wham/usage", headers)
        entry = {
            "provider": "openai",
            "displayName": _PROVIDER_LABELS.get("openai", "OpenAI"),
            "type": "oauth",
        }
        if status != 200 or not data:
            entry["error"] = f"HTTP {status}"
            entry["message"] = "OpenAI usage requires a valid ChatGPT/Codex OAuth session. API-key billing usage is not exposed here."
            return entry

        windows = []
        rl = data.get("rate_limit", {})

        # Primary window (usually 3h or 5h)
        pw = rl.get("primary_window")
        if pw:
            hours = round((pw.get("limit_window_seconds", 10800)) / 3600)
            windows.append({
                "label": f"{hours}h",
                "usedPercent": min(100, max(0, pw.get("used_percent", 0))),
                "resetAt": int(pw["reset_at"] * 1000) if pw.get("reset_at") else 0,
            })

        # Secondary window (usually week)
        sw = rl.get("secondary_window")
        if sw:
            hours = round((sw.get("limit_window_seconds", 86400)) / 3600)
            # Determine label
            label = "Week" if hours >= 168 else f"{hours}h" if hours < 24 else "Day"
            # Check if gap between resets suggests weekly
            if pw and sw.get("reset_at") and pw.get("reset_at"):
                if sw["reset_at"] - pw["reset_at"] >= 4320 * 60:
                    label = "Week"
            windows.append({
                "label": label,
                "usedPercent": min(100, max(0, sw.get("used_percent", 0))),
                "resetAt": int(sw["reset_at"] * 1000) if sw.get("reset_at") else 0,
            })

        # Plan info
        plan = data.get("plan_type")
        credits = data.get("credits", {})
        if credits.get("balance") is not None:
            balance = float(credits["balance"]) if credits["balance"] else 0
            plan = f"{plan} (${balance:.2f})" if plan else f"${balance:.2f}"
        entry["plan"] = plan

        if windows:
            entry["usage"] = self._windows_to_usage(windows, now)
            entry["windows"] = windows
        return entry

    # --- GitHub Copilot ---
    def _fetch_copilot(self, token, now):
        """Fetch GitHub Copilot usage."""
        status, data = self._http_get("https://api.github.com/copilot_internal/v2/token", {
            "Authorization": f"token {token}",
            "Accept": "application/json",
            "User-Agent": "openclaw",
        })
        entry = {
            "provider": "github-copilot",
            "displayName": _PROVIDER_LABELS.get("github-copilot", "Copilot"),
        }
        if status != 200:
            entry["error"] = f"HTTP {status}"
        # Copilot doesn't expose usage windows in the same way
        return entry

    # --- Helpers ---
    @staticmethod
    def _windows_to_usage(windows, now):
        """Convert raw windows list to structured usage object with pctLeft/timeLeft."""
        usage = {}
        for w in windows:
            label = (w.get("label") or "").lower()
            used = w.get("usedPercent", 0)
            left = 100 - used
            reset_at = w.get("resetAt", 0)
            time_left = ApiUsageCollector._format_time_left(reset_at, now) if reset_at else ""

            if label in ("5h", "day", "daily", "24h", "3h"):
                usage["dailyPctLeft"] = left
                usage["dailyWindow"] = w.get("label", "Day")
                usage["dailyTimeLeft"] = time_left
            elif label in ("week", "weekly"):
                usage["weeklyPctLeft"] = left
                usage["weeklyTimeLeft"] = time_left
            elif label in ("month", "monthly"):
                usage["monthlyPctLeft"] = left
                usage["monthlyTimeLeft"] = time_left
            elif label in ("sonnet", "opus"):
                usage[f"{label}PctLeft"] = left
            else:
                usage[f"{label}PctLeft"] = left
                usage[f"{label}TimeLeft"] = time_left
        return usage

    @staticmethod
    def _format_time_left(reset_at_ms, now_s):
        """Format time until reset as human-readable string."""
        diff = (reset_at_ms / 1000) - now_s
        if diff <= 0:
            return "resetting..."
        hours = int(diff // 3600)
        mins = int((diff % 3600) // 60)
        if hours > 24:
            days = hours // 24
            return f"{days}d {hours % 24}h"
        if hours > 0:
            return f"{hours}h {mins}m"
        return f"{mins}m"

    @staticmethod
    def _parse_ts(val):
        """Parse a timestamp string to milliseconds."""
        if not val:
            return 0
        if isinstance(val, (int, float)):
            return val * 1000 if val < 1e12 else val
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            return dt.timestamp() * 1000
        except Exception:
            return 0


# Initialize the collector (started in __main__)
_api_usage_collector = ApiUsageCollector(AUTH_PROFILES_PATH)


# Browser runtime helpers live in server_services.browser_runtime.



# Domain service compatibility exports. Existing tests and internal callers still
# access many `_handle_*` names through `server`, while route modules call the
# service modules directly. Hydrate after all module-level helpers above exist.
from server_services import skills as _skills_service
from server_services import agents as _agents_service
from server_services import config_runtime as _config_runtime_service
from server_services import browser_runtime as _browser_runtime_service
from server_services import archive_room as _archive_room_service
from server_services import agent_bridges as _agent_bridges_service
from server_services import notifications as _notifications_service
from server_services import meetings as _meetings_service
from server_services import projects as _projects_service
from server_services import providers as _providers_service
from server_services import workflow as _workflow_service

_skills_service._hydrate()
from server_services.skills import *  # noqa: F401,F403,E402

_agents_service._hydrate()
from server_services.agents import *  # noqa: F401,F403,E402

_config_runtime_service._hydrate()
from server_services.config_runtime import *  # noqa: F401,F403,E402

_browser_runtime_service._hydrate()
from server_services.browser_runtime import *  # noqa: F401,F403,E402

_agent_bridges_service._hydrate()
from server_services.agent_bridges import *  # noqa: F401,F403,E402

_archive_room_service._hydrate()
from server_services.archive_room import *  # noqa: F401,F403,E402

_notifications_service._hydrate()
from server_services.notifications import *  # noqa: F401,F403,E402

_meetings_service._hydrate()
from server_services.meetings import *  # noqa: F401,F403,E402

_projects_service._hydrate()
from server_services.projects import *  # noqa: F401,F403,E402

_providers_service._hydrate()
from server_services.providers import *  # noqa: F401,F403,E402

_workflow_service._hydrate()
from server_services.workflow import *  # noqa: F401,F403,E402

_skills_service._hydrate()
_agents_service._hydrate()
_config_runtime_service._hydrate()
_browser_runtime_service._hydrate()
_agent_bridges_service._hydrate()
_archive_room_service._hydrate()
_notifications_service._hydrate()
_meetings_service._hydrate()
_projects_service._hydrate()
_providers_service._hydrate()
_workflow_service._hydrate()


class OfficeHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=APP_DIR, **kwargs)

    def end_headers(self):
        if urllib.parse.urlparse(self.path).path.endswith(".woff2"):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        super().end_headers()

    def _serve_website_asset(self, request_path):
        website_dir = os.path.realpath(os.path.join(APP_DIR, "..", "website"))
        relative_path = request_path[len("/website/"):].lstrip("/") or "index.html"
        target_path = os.path.realpath(os.path.join(website_dir, relative_path))
        if not target_path.startswith(website_dir + os.sep) or not os.path.isfile(target_path):
            self.send_error(404, "Website asset not found")
            return
        content_type = self.guess_type(target_path)
        with open(target_path, "rb") as asset:
            content = asset.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_browser_viewer_asset(self, request_path, parsed_url):
        upstream_base, headers = _browser_viewer_upstream_parts()
        if not upstream_base:
            self.send_error(404, "Browser viewer is not configured")
            return
        relative_path = request_path[len("/browser-viewer/"):].lstrip("/")
        upstream_path = "/" + relative_path if relative_path else "/"
        upstream_url = upstream_base + upstream_path
        if parsed_url.query:
            upstream_url += "?" + parsed_url.query
        try:
            req = urllib.request.Request(upstream_url, headers=headers, method="GET")
            context = ssl._create_unverified_context() if upstream_url.startswith("https://") else None
            with urllib.request.urlopen(req, timeout=8, context=context) as resp:
                content = resp.read()
                content_type = resp.headers.get("Content-Type") or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode())

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        request_path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)
        if request_path == "/website":
            self.send_response(301)
            self.send_header("Location", "/website/")
            self.end_headers()
            return
        if request_path.startswith("/website/"):
            self._serve_website_asset(request_path)
            return
        if request_path in ("/browser-viewer", "/browser-viewer/") and not parsed_url.query:
            password = urllib.parse.quote(_browser_viewer_password(), safe="")
            location = (
                f"/browser-viewer/?host={urllib.parse.quote(self.headers.get('Host', '').split(':')[0] or 'localhost', safe='')}"
                f"&port={WS_PORT}&path=browser-viewer-websockify&password={password}"
                f"&resize=scale&autoconnect=1&_vo_embed=1"
            )
            self.send_response(302)
            self.send_header("Location", location)
            self.end_headers()
            return
        if request_path.startswith("/browser-viewer/"):
            self._serve_browser_viewer_asset(request_path, parsed_url)
            return
        if server_routes.dispatch(self, "GET", parsed_url):
            return
        # Setup wizard page
        if self.path == "/setup":
            setup_path = os.path.join(os.path.dirname(__file__), "setup.html")
            try:
                with open(setup_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Setup page not found")
            return
        elif self.path == "/agents-list":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            # Return dynamically discovered agent roster
            refresh_agent_maps()
            # Load office-config overrides for agent names/emoji/branch
            _oc_overrides, _oc_branches = _load_office_agent_overrides()
            agents = []
            for a in get_roster():
                provider_kind = a.get("providerKind", "openclaw")
                if provider_kind == "hermes":
                    session_key = f"hermes:{a.get('profile', a['id'])}"
                elif provider_kind == "codex":
                    session_key = f"codex:{a.get('profile') or a.get('providerAgentId') or a['id']}"
                elif provider_kind == "claude-code":
                    session_key = f"claude-code:{a.get('profile') or a.get('providerAgentId') or a['id']}"
                else:
                    session_key = f"agent:{a['id']}:main"
                # Prefer office-config name/emoji over provider discovery.
                oc = _office_agent_override_for(a, _oc_overrides)
                # Resolve branch ID to display name
                branch_id = oc.get("branch", "")
                branch_name = _oc_branches.get(branch_id, "") if branch_id else ""
                if not branch_name:
                    branch_name = provider_kind.title() if provider_kind != "openclaw" else "Unassigned"
                agent_payload = {
                    "key": a["statusKey"],
                    "agentId": a["id"],
                    "sessionKey": session_key,
                    "providerKind": provider_kind,
                    "providerType": a.get("providerType", "runtime"),
                    "providerAgentId": a.get("providerAgentId", a["id"]),
                    "profile": a.get("profile") or a.get("providerAgentId") or "",
                    "emoji": oc.get("emoji") or a["emoji"],
                    "name": oc.get("name") or a["name"],
                    "role": a.get("role", ""),
                    "model": a.get("model", ""),
                    "provider": a.get("provider", ""),
                    "lastActiveAt": a.get("lastActiveAt", 0),
                    "branch": branch_name,
                }
                agent_payload.update(_agent_archive_manager_meta(a.get("statusKey") or a.get("id")))
                agents.append(agent_payload)
            # Enforce agent limit in demo mode without hiding whole providers.
            agents = _apply_agent_limit_balanced(agents)
            self.wfile.write(json.dumps({"agents": agents}).encode())
        elif self.path == "/gateway-info":
            # Tell the browser WS port + gateway token for chat connection
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "wsPort": WS_PORT,
                "wsPath": VO_CONFIG["office"].get("wsPath", "/ws"),
                "token": _get_gateway_token(),
                "openclawVersion": _get_openclaw_version(),
            }).encode())
        elif request_path == "/api/session-activity":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            session_key = (query_params.get("sessionKey") or [""])[0]
            try:
                limit = int((query_params.get("limit") or ["80"])[0])
            except Exception:
                limit = 80
            limit = max(1, min(120, limit))
            messages = _session_trajectory_messages(session_key, max_tools=limit)
            self.wfile.write(json.dumps({"ok": True, "messages": messages}).encode())
        elif self.path == "/agent-chat":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            result = {}
            for agent_key in AGENT_SESSION_IDS:
                if _is_hermes_agent(agent_key):
                    agent = _get_hermes_agent(agent_key) or {}
                    profile = agent.get("profile") or agent.get("providerAgentId") or "default"
                    msgs = _load_provider_histories_for_bubbles("hermes", profile, 500)
                elif _is_codex_agent(agent_key):
                    msgs = []
                elif _is_claude_code_agent(agent_key):
                    agent = _get_claude_code_agent(agent_key) or {}
                    profile = agent.get("profile") or agent.get("providerAgentId") or "local"
                    msgs = _load_provider_histories_for_bubbles("claude-code", profile, 500)
                else:
                    msgs = get_agent_messages(agent_key, max_messages=500)
                if msgs:
                    result[agent_key] = msgs
            result = _merge_comm_events_into_agent_chat(result)
            # Build project-work map: which agents are currently working on project tasks
            # Primary detection: check each agent's most recently active session key
            # for the "wf-" prefix (workflow sessions created by the project system).
            # This works across all VO instances since they read the same session files.
            project_work = {}
            for agent_key, agent_id in AGENT_SESSION_IDS.items():
                if _is_hermes_agent(agent_key) or _is_codex_agent(agent_key) or _is_claude_code_agent(agent_key):
                    continue
                try:
                    sdir = os.path.join(WORKSPACE_BASE, f"agents/{agent_id}/sessions")
                    sjson = os.path.join(sdir, "sessions.json")
                    with open(sjson, "r") as _sf:
                        sdata = json.load(_sf)
                    best_ts = 0
                    best_key = ""
                    for skey, sval in sdata.items():
                        if not isinstance(sval, dict):
                            continue
                        sts = sval.get("updatedAt", 0)
                        if sts > best_ts:
                            best_ts = sts
                            best_key = skey
                    # Detect workflow session: key contains ":wf-"
                    if best_key and ":wf-" in best_key:
                        if time.time() - best_ts / 1000 < 300:
                            project_work[agent_key] = {
                                "projectId": "",
                                "taskId": "",
                                "taskTitle": "Project task",
                                "phase": "in_progress",
                            }
                except Exception:
                    pass
            # Enrich with in-memory workflow state / persisted state (has task titles etc.)
            active_phases = ("in_progress", "dispatching", "reviewing", "rework")
            # 1) Collect from in-memory workflow state
            wf_entries = {}
            with _WORKFLOW_LOCK:
                for pid, wf in _WORKFLOW_STATE.items():
                    wf_entries[pid] = dict(wf)
            # 2) Merge persisted state for workflows not in memory
            try:
                if os.path.isfile(WORKFLOW_STATE_FILE):
                    with open(WORKFLOW_STATE_FILE, "r") as _pwf:
                        persisted_wfs = json.load(_pwf)
                    for pid, pwf in persisted_wfs.items():
                        if pid not in wf_entries:
                            wf_entries[pid] = pwf
                        else:
                            for k in ("currentAssignee", "currentTaskTitle", "currentTaskId"):
                                if not wf_entries[pid].get(k) and pwf.get(k):
                                    wf_entries[pid][k] = pwf[k]
            except Exception:
                pass
            # Build from workflow entries
            proj_data = None
            for pid, wf in wf_entries.items():
                if not wf.get("active") or wf.get("phase") not in active_phases:
                    continue
                agent_id = wf.get("currentAssignee")
                task_title = wf.get("currentTaskTitle", "")
                task_id = wf.get("currentTaskId", "")
                if not agent_id and task_id:
                    if not proj_data:
                        proj_data = _load_projects()
                    p = next((x for x in proj_data.get("projects", []) if x["id"] == pid), None)
                    if p:
                        task = next((t for t in p.get("tasks", []) if t["id"] == task_id), None)
                        if task:
                            agent_id = task.get("assignee")
                            if not task_title:
                                task_title = task.get("title", "")
                if not agent_id:
                    continue
                for sk, aid in AGENT_SESSION_IDS.items():
                    if aid == agent_id:
                        project_work[sk] = {
                            "projectId": pid,
                            "taskId": task_id,
                            "taskTitle": task_title,
                            "phase": wf.get("phase", ""),
                        }
                        break
            # 3) Fallback: scan projects.json for workflowActive projects with
            #    tasks sitting in "In Progress" or "Review" columns — covers the
            #    case where the workflow thread died or the container restarted
            #    but the task was never moved back.
            if not proj_data:
                proj_data = _load_projects()
            for p in proj_data.get("projects", []):
                pid = p["id"]
                if pid in project_work:
                    continue  # already found via workflow state
                if not p.get("workflowActive"):
                    continue
                active_col_ids = set()
                for c in p.get("columns", []):
                    ct = c.get("title", "").lower()
                    if ct in ("in progress", "review"):
                        active_col_ids.add(c["id"])
                if not active_col_ids:
                    continue
                for task in p.get("tasks", []):
                    if task.get("columnId") not in active_col_ids:
                        continue
                    assignee = task.get("assignee")
                    if not assignee:
                        continue
                    col_title = ""
                    for c in p.get("columns", []):
                        if c["id"] == task.get("columnId"):
                            col_title = c.get("title", "")
                            break
                    phase = "in_progress" if col_title.lower() == "in progress" else "reviewing"
                    for sk, aid in AGENT_SESSION_IDS.items():
                        if aid == assignee and sk not in project_work:
                            project_work[sk] = {
                                "projectId": pid,
                                "taskId": task["id"],
                                "taskTitle": task.get("title", ""),
                                "phase": phase,
                            }
                            break
            # Update shared file so other VO instances can see project work
            if project_work:
                try:
                    shared = {}
                    now_ms = int(time.time() * 1000)
                    for sk, info in project_work.items():
                        agent_id = AGENT_SESSION_IDS.get(sk, sk)
                        shared[agent_id] = {
                            "projectId": info.get("projectId", ""),
                            "taskId": info.get("taskId", ""),
                            "taskTitle": info.get("taskTitle", ""),
                            "phase": info.get("phase", ""),
                            "updatedAt": now_ms,
                        }
                    shared_path = os.path.join(WORKSPACE_BASE, "shared", "project-work.json")
                    os.makedirs(os.path.dirname(shared_path), exist_ok=True)
                    with open(shared_path, "w") as _spf:
                        json.dump(shared, _spf)
                except Exception:
                    pass
            result["_projectWork"] = project_work
            self.wfile.write(json.dumps(result).encode())
        elif self.path == "/session-info" or self.path.startswith("/session-info?"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            agent_id = (
                (query.get("agent") or query.get("agentId") or query.get("key") or query.get("sessionKey") or [""])[0]
                or None
            )
            info = self._get_session_info(agent_id=agent_id)
            self.wfile.write(json.dumps(info).encode())
        elif self.path == "/models":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            models = self._get_models()
            self.wfile.write(json.dumps(models).encode())
        elif self.path == "/api/native-models":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(_get_native_model_state()).encode())
        elif self.path == "/pc-metrics":
            # Proxy PC metrics from remote machine (configurable)
            _pc_url = VO_CONFIG["pcMetrics"].get("url")
            if not _pc_url or not VO_CONFIG["features"]["pcMetrics"]:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'{"error":"PC metrics not configured"}')
                return
            try:
                req = urllib.request.urlopen(_pc_url, timeout=4)
                data = req.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        elif self.path == "/api-usage":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            data = self._get_api_usage()
            self.wfile.write(json.dumps(data).encode())
        elif self.path.startswith("/agent-bio/"):
            agent_key = self.path.split("/agent-bio/")[1]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            bio = self._read_agent_bio(agent_key)
            self.wfile.write(json.dumps(bio).encode())
        elif request_path == "/sms-status":
            # SMS feature health/config check
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            sms_cfg = VO_CONFIG.get("sms", {})
            enabled = VO_CONFIG.get("features", {}).get("smsPanel", False) and check_feature("smsPanel")
            owner_agent = self._get_sms_owner_agent_info()
            self.wfile.write(json.dumps({
                "enabled": enabled,
                "agentId": owner_agent.get("id"),
                "ownerAgentId": owner_agent.get("id"),
                "ownerAgent": owner_agent,
                "hasCredentials": bool(sms_cfg.get("twilioAccountSid") and sms_cfg.get("twilioAuthToken") and sms_cfg.get("fromNumber")),
            }).encode())
        elif request_path == "/sms-log":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            sms_log = self._get_sms_log()
            self.wfile.write(json.dumps(sms_log).encode())
        elif request_path == "/sms-threads":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            limit = query_params.get("limit", ["200"])[0]
            try:
                limit = max(1, min(1000, int(limit)))
            except Exception:
                limit = 200
            self.wfile.write(json.dumps(self._get_sms_threads(limit=limit)).encode())
        elif request_path == "/sms-thread":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            phone = (query_params.get("phone", [""])[0] or "").strip()
            limit = query_params.get("limit", ["250"])[0]
            try:
                limit = max(1, min(1000, int(limit)))
            except Exception:
                limit = 250
            self.wfile.write(json.dumps(self._get_sms_thread(phone, limit=limit)).encode())
        elif request_path == "/sms-media":
            self._handle_sms_media_proxy(query_params)
        elif request_path == "/chat-media":
            self._serve_chat_media(query_params)
        elif request_path == "/sms-mode":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            mode = self._read_global_sms_mode()
            self.wfile.write(json.dumps(mode).encode())
        elif request_path == "/sms-contacts":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            contacts = self._get_sms_contacts()
            self.wfile.write(json.dumps(contacts).encode())
        elif request_path == "/api/sse/test":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            def send_sse(event_name, payload):
                data = json.dumps(payload, ensure_ascii=False)
                self.wfile.write(f"event: {event_name}\ndata: {data}\n\n".encode("utf-8"))
                self.wfile.flush()

            test_id = str(uuid.uuid4())[:8]
            started = time.time()
            send_sse("sse.test.start", {"ok": True, "testId": test_id, "seq": 0, "serverElapsedMs": 0})
            for seq in (1, 2):
                time.sleep(0.45)
                send_sse("sse.test.tick", {"ok": True, "testId": test_id, "seq": seq, "serverElapsedMs": int((time.time() - started) * 1000)})
            time.sleep(0.45)
            send_sse("sse.test.done", {"ok": True, "testId": test_id, "seq": 3, "serverElapsedMs": int((time.time() - started) * 1000)})
        elif self.path == "/api/presence" or self.path.startswith("/api/presence/"):
            # Presence API — read from gateway_presence in-memory state
            if self.path == "/api/presence":
                result = _get_normalized_presence_state()
            elif self.path == "/api/presence/debug":
                result = gateway_presence.get_connection_status()
            else:
                agent_id = self.path.split("/api/presence/")[1].strip("/")
                result = _normalize_presence_entry(gateway_presence.get_agent_state(agent_id))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        else:
            super().do_GET()

    def _chat_media_allowed_roots(self):
        roots = []
        for candidate in [STATUS_DIR, WORKSPACE_BASE, os.path.expanduser("~/.openclaw"), "/tmp/vo-data"]:
            try:
                if candidate and os.path.isdir(candidate):
                    roots.append(os.path.realpath(candidate))
            except Exception:
                pass
        return roots

    def _resolve_chat_media_path(self, raw_path):
        """Resolve chat media paths across VO instances without assuming one data dir.

        Chat transcripts may contain paths produced by another Virtual Office
        instance (for example /tmp/vo-data/uploads/...) while the current
        instance has a different STATUS_DIR (for example /data).  Try the
        literal path first, then remap upload-relative paths under allowed
        OpenClaw roots so both personal and product offices can display the
        same attachments.
        """
        if raw_path.startswith("file://"):
            raw_path = urllib.parse.urlparse(raw_path).path
        raw_path = urllib.parse.unquote(raw_path)
        candidates = []
        if raw_path.startswith("/tmp/vo-data/"):
            candidates.append(os.path.join(STATUS_DIR, raw_path[len("/tmp/vo-data/"):]))
        candidates.append(raw_path)
        if not os.path.isabs(raw_path):
            candidates.append(os.path.join(WORKSPACE_BASE, raw_path))

        norm_parts = raw_path.replace("\\", "/").split("/")
        if "uploads" in norm_parts:
            idx = norm_parts.index("uploads")
            upload_suffix = os.path.join(*norm_parts[idx:])
            for root in self._chat_media_allowed_roots():
                candidates.append(os.path.join(root, upload_suffix))
            # Also scan one level below OpenClaw roots (data/uploads,
            # workspace/uploads, etc.). This keeps the
            # product generic while still supporting multiple VO instances.
            for base in [WORKSPACE_BASE, os.path.expanduser("~/.openclaw")]:
                try:
                    candidates.extend(glob.glob(os.path.join(base, "*", upload_suffix)))
                except Exception:
                    pass

        allowed_roots = self._chat_media_allowed_roots()
        seen = set()
        for candidate in candidates:
            if not candidate:
                continue
            if not os.path.isabs(candidate):
                candidate = os.path.join(WORKSPACE_BASE, candidate)
            real_path = os.path.realpath(candidate)
            if real_path in seen:
                continue
            seen.add(real_path)
            allowed = any(real_path == root or real_path.startswith(root + os.sep) for root in allowed_roots)
            if allowed and os.path.isfile(real_path):
                return real_path
        return None

    def _serve_chat_media(self, query_params):
        raw_path = (query_params.get("path", [""])[0] or "").strip()
        if not raw_path:
            self.send_response(400)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b"Missing media path")
            return
        real_path = self._resolve_chat_media_path(raw_path)
        if not real_path:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b"Media not found")
            return
        content_type = mimetypes.guess_type(real_path)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "private, max-age=3600")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        with open(real_path, "rb") as f:
            shutil.copyfileobj(f, self.wfile)

    def _get_api_usage(self):
        """Return the latest API usage data collected by the background thread."""
        now = time.time()
        data = dict(_api_usage_collector.get_data())
        data["ageSeconds"] = round(now - data.get("timestamp", 0), 1)
        return data

    def _read_agent_bio(self, agent_key):
        """Read agent's .md files and return structured bio data."""
        ws_dir = AGENT_WORKSPACES.get(agent_key)
        if not ws_dir:
            return {"error": f"Unknown agent: {agent_key}"}

        ws_path = os.path.join(WORKSPACE_BASE, ws_dir)
        result = {}

        for fname in ["AGENTS.md", "SOUL.md", "MEMORY.md", "TOOLS.md", "IDENTITY.md", "USER.md", "HEARTBEAT.md"]:
            fpath = os.path.join(ws_path, fname)
            try:
                with open(fpath, "r") as f:
                    result[fname] = f.read()
            except FileNotFoundError:
                result[fname] = ""
            except Exception as e:
                result[fname] = f"(error reading: {e})"

        # Read latest daily memory file
        mem_dir = os.path.join(ws_path, "memory")
        result["daily"] = ""
        result["dailyFile"] = ""
        if os.path.isdir(mem_dir):
            md_files = sorted([f for f in os.listdir(mem_dir) if f.endswith(".md")], reverse=True)
            if md_files:
                latest = md_files[0]
                result["dailyFile"] = latest
                try:
                    with open(os.path.join(mem_dir, latest), "r") as f:
                        result["daily"] = f.read()
                except Exception:
                    pass

        return result

    _model_cache = {}  # {provider: {models: [...], ts: timestamp}}
    _CACHE_TTL = 300  # 5 minutes
    _MAX_CACHE_SIZE = 50  # max entries per cache dict

    def _fetch_provider_models(self, provider, api_key):
        """Fetch live model list from a cloud provider's API."""

        # Check cache
        cached = self.__class__._model_cache.get(provider)
        if cached and (time.time() - cached["ts"]) < self.__class__._CACHE_TTL:
            return cached["models"]

        models = []
        try:
            if provider == "openai":
                req = urllib.request.Request("https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())
                for m in data.get("data", []):
                    models.append(m.get("id", ""))

            elif provider == "anthropic":
                req = urllib.request.Request("https://api.anthropic.com/v1/models",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())
                for m in data.get("data", []):
                    mid = m.get("id", "")
                    if mid:
                        models.append(mid)

            elif provider == "google":
                url = "https://generativelanguage.googleapis.com/v1beta/models"
                req = urllib.request.Request(url, headers={"x-goog-api-key": api_key})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())
                for m in data.get("models", []):
                    models.append(m.get("name", "").replace("models/", ""))

            elif provider == "groq":
                req = urllib.request.Request("https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())
                for m in data.get("data", []):
                    mid = m.get("id", "")
                    if mid:
                        models.append(mid)

            models.sort()
            cache = self.__class__._model_cache
            cache[provider] = {"models": models, "ts": time.time()}
            # Evict oldest entries if cache exceeds max size
            if len(cache) > self.__class__._MAX_CACHE_SIZE:
                oldest = min(cache, key=lambda k: cache[k]["ts"])
                del cache[oldest]
        except Exception as e:
            # Return cached if available, even if stale
            if cached:
                return cached["models"]
            return [f"(error: {str(e)[:60]})"]

        return models

    # OAuth provider model discovery via OpenClaw CLI
    _oauth_model_cache = {}  # {provider: {models: [...], ts: timestamp}}
    _OAUTH_CACHE_TTL = 600  # 10 minutes

    @classmethod
    def _discover_oauth_provider_models(cls):
        """Discover actually-served models for OAuth providers via `openclaw models list`.

        Read-only legacy helper for older picker surfaces. New model settings
        use /api/native-models and OpenClaw's native JSON output directly.
        """
        oauth_providers = set()
        try:
            for profile in _read_openclaw_auth_sqlite():
                if str(profile.get("type") or "").lower() in {"oauth", "token", "subscription"}:
                    provider = profile.get("provider")
                    if provider:
                        oauth_providers.add(provider)
        except Exception:
            pass

        for provider in oauth_providers:
            cached = cls._oauth_model_cache.get(provider)
            if cached and (time.time() - cached["ts"]) < cls._OAUTH_CACHE_TTL:
                continue  # Still fresh

            try:
                openclaw_bin = OPENCLAW_BIN
                if not openclaw_bin:
                    continue
                result = subprocess.run(
                    [openclaw_bin, "models", "list", "--provider", provider, "--all", "--json"],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode != 0:
                    continue
                data = json.loads(result.stdout)
                discovered = []
                for m in data.get("models", []):
                    tags = m.get("tags", [])
                    if "missing" not in tags:
                        key = m.get("key", "")
                        if key:
                            discovered.append(key)

                cls._oauth_model_cache[provider] = {"models": discovered, "ts": time.time()}
            except Exception:
                pass  # Silently skip — will retry next cache expiry

    @classmethod
    def _sync_config_models(cls, provider, discovered_models):
        """Sync agents.defaults.models with actually-discovered models for a provider.

        Removes config entries for models NOT served by the provider.
        Adds entries for discovered models not yet in config.
        Does NOT touch models from other providers.
        """
        try:
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)

            models_cfg = cfg.get("agents", {}).get("defaults", {}).get("models", {})
            prefix = f"{provider}/"
            discovered_set = set(discovered_models)
            changed = False

            # Remove config entries not in discovered set
            to_remove = [k for k in models_cfg if k.startswith(prefix) and k not in discovered_set]
            for k in to_remove:
                del models_cfg[k]
                changed = True

            # Add discovered models not yet in config
            for m in discovered_models:
                if m not in models_cfg:
                    models_cfg[m] = {}
                    changed = True

            if changed:
                with open(CONFIG_PATH, "w") as f:
                    json.dump(cfg, f, indent=2)
        except Exception:
            pass  # Config sync is best-effort

    _registry_cache = {}  # {provider: {models: [...], ts: timestamp}}
    _REGISTRY_TTL = 600  # 10 minutes

    def _fetch_registry_models(self, provider):
        """Fetch models for a provider from configured models in openclaw.json.
        Provider may be "anthropic-token" but we search for "anthropic/" prefix.
        """

        cached = self.__class__._registry_cache.get(provider)
        if cached and (time.time() - cached["ts"]) < self.__class__._REGISTRY_TTL:
            return cached["models"]

        # Extract base provider name (e.g., "anthropic" from "anthropic-token")
        base_provider = provider.replace("-token", "").replace("-oauth", "")

        models = []
        try:
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)
            configured_models = cfg.get("agents", {}).get("defaults", {}).get("models", {})
            prefix = f"{base_provider}/"
            for model_id in configured_models.keys():
                if model_id.startswith(prefix):
                    short_id = model_id[len(prefix):]
                    models.append(short_id)
            models.sort()
            cache = self.__class__._registry_cache
            cache[provider] = {"models": models, "ts": time.time()}
            # Evict oldest entries if cache exceeds max size
            if len(cache) > self.__class__._MAX_CACHE_SIZE:
                oldest = min(cache, key=lambda k: cache[k]["ts"])
                del cache[oldest]
        except Exception as e:
            if cached:
                return cached["models"]
            return [f"(error: {str(e)[:60]})"]

        return models

    def _load_model_config(self):
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _default_config_model(self, cfg):
        cfg = cfg if isinstance(cfg, dict) else {}
        model_cfg = (cfg.get("agents") or {}).get("defaults", {}).get("model", "")
        if isinstance(model_cfg, dict):
            return str(model_cfg.get("primary") or model_cfg.get("default") or model_cfg.get("id") or "").strip()
        return str(model_cfg or "").strip()

    def _provider_for_model(self, model, cfg):
        model = str(model or "")
        cfg = cfg if isinstance(cfg, dict) else {}
        if "/" in model:
            return model.split("/", 1)[0]
        for provider, pdata in (cfg.get("models", {}).get("providers", {}) or {}).items():
            for item in pdata.get("models", []) or []:
                if str(item.get("id") or "") == model:
                    return provider
        return _provider_from_model_id(model) if model else ""

    def _get_configured_model(self, agent_id=None):
        """Return configured model metadata for a specific agent or default.

        When agent_id is provided, resolves that agent's configured model
        (per-agent override or default). Otherwise returns the main/default agent model.
        """
        helper = self if self is not None else OfficeHandler
        cfg = helper._load_model_config(helper) if self is None else helper._load_model_config()
        default_model = helper._default_config_model(helper, cfg) if self is None else helper._default_config_model(cfg)
        if agent_id and _is_hermes_agent(agent_id):
            agent = _get_hermes_agent(agent_id) or {}
            model = agent.get("model") or "Hermes"
            provider = agent.get("provider") or "Hermes"
            return {"model": model, "provider": provider, "providerKind": "hermes", "contextWindow": 0}
        if agent_id and _is_codex_agent(agent_id):
            agent = _get_codex_agent(agent_id) or {}
            model = agent.get("model") or "Codex"
            provider = agent.get("provider") or "OpenAI Codex"
            return {"model": model, "provider": provider, "providerKind": "codex", "contextWindow": 0}
        if agent_id and _is_claude_code_agent(agent_id):
            agent = _get_claude_code_agent(agent_id) or {}
            model = agent.get("model") or "Claude Code"
            provider = agent.get("provider") or "Claude Code"
            return {"model": model, "provider": provider, "providerKind": "claude-code", "contextWindow": 0}
        return {
            "model": default_model,
            "provider": helper._provider_for_model(helper, default_model, cfg) if self is None else helper._provider_for_model(default_model, cfg),
            "providerKind": "openclaw",
            "contextWindow": helper._context_window_for_model(helper, default_model, cfg) if self is None else helper._context_window_for_model(default_model, cfg),
        }

    def _context_window_for_model(self, model, cfg):
        model = str(model or "")
        cfg = cfg if isinstance(cfg, dict) else {}
        # Known context windows - keyed by full provider/model AND by model name alone.
        # The model-name-only keys act as fallbacks for alternative providers
        # (e.g. openai-codex/gpt-5.4-pro matches via "gpt-5.4-pro" -> "gpt-5" family).
        known_context = {
            # Anthropic
            "anthropic/claude-opus-4-6": 1000000,
            "anthropic/claude-sonnet-4-6": 1000000,
            "anthropic/claude-sonnet-4-20250514": 200000,
            "anthropic/claude-haiku-3-5-20241022": 200000,
            "anthropic/claude-3-5-sonnet-20241022": 200000,
            # Google
            "google/gemini-2.5-flash": 1048576,
            "google/gemini-2.5-pro": 1048576,
            "google/gemini-2.0-flash": 1048576,
            "google/gemini-3-flash-preview": 1048576,
            "google/gemini-3.1-pro-preview": 1048576,
            "google/gemini-3.1-flash-lite-preview": 1048576,
            # OpenAI
            "openai/gpt-4o": 128000,
            "openai/gpt-4o-mini": 128000,
            "openai/gpt-5.4": 200000,
            "openai/o3": 200000,
            "openai/o4-mini": 200000,
        }
        known_context_prefixes = [
            ("claude-opus", 1000000),
            ("claude-sonnet-4", 1000000),
            ("claude-sonnet", 200000),
            ("claude-haiku", 200000),
            ("gemini-3", 1048576),
            ("gemini-2.5", 1048576),
            ("gemini-2.0", 1048576),
            ("gpt-5", 200000),
            ("gpt-4o", 128000),
            ("o3", 200000),
            ("o4-mini", 200000),
        ]

        for prov_name, prov_data in cfg.get("models", {}).get("providers", {}).items():
            for m in prov_data.get("models", []):
                full_id = f"{prov_name}/{m['id']}"
                if full_id == model and m.get("contextWindow"):
                    return m["contextWindow"]

        context_window = known_context.get(model, 0)
        if context_window == 0 and "/" in model:
            model_name = model.split("/", 1)[1]
            for prefix, ctx in known_context_prefixes:
                if model_name.startswith(prefix):
                    return ctx
        return context_window

    def _get_session_info(self, agent_id=None):
        """Return model name and context window for a specific agent (or default).

        When agent_id is provided, resolves that agent's configured model
        (per-agent override or default). Otherwise returns the main/default agent model.
        """
        helper = self if self is not None else OfficeHandler
        cfg = helper._load_model_config(helper) if self is None else helper._load_model_config()
        default_model = helper._default_config_model(helper, cfg) if self is None else helper._default_config_model(cfg)
        if agent_id and _is_hermes_agent(agent_id):
            agent = _get_hermes_agent(agent_id) or {}
            model = agent.get("model") or "Hermes"
            provider = agent.get("provider") or "Hermes"
            return {"model": model, "provider": provider, "providerKind": "hermes", "contextWindow": 0}
        if agent_id and _is_codex_agent(agent_id):
            agent = _get_codex_agent(agent_id) or {}
            model = agent.get("model") or VO_CONFIG.get("codex", {}).get("model") or default_model
            provider = agent.get("provider") or "Codex CLI"
            profile = agent.get("profile") or agent.get("providerAgentId") or "default"
            token_usage = _get_codex_token_usage(profile)
            state = _load_codex_state(profile)
            context_used = _codex_context_used_from_token_usage(token_usage) or _codex_int(state.get("contextUsed"), 0)
            token_context_window = _codex_context_window_from_token_usage(token_usage) or _codex_int(state.get("contextWindow"), 0)
            return {
                "model": model,
                "provider": provider,
                "providerKind": "codex",
                "contextWindow": token_context_window or (helper._context_window_for_model(helper, model, cfg) if self is None else helper._context_window_for_model(model, cfg)),
                "contextUsed": context_used,
                "tokenUsage": token_usage,
            }
        if agent_id and _is_claude_code_agent(agent_id):
            agent = _get_claude_code_agent(agent_id) or {}
            model = agent.get("model") or VO_CONFIG.get("claudeCode", {}).get("model") or default_model
            if model == "inherit":
                model = VO_CONFIG.get("claudeCode", {}).get("model") or default_model
            provider = agent.get("provider") or "Claude Code"
            profile = agent.get("profile") or agent.get("providerAgentId") or "main"
            token_usage = _get_claude_code_token_usage(profile)
            state = _load_claude_code_state(profile)
            context_used = _codex_context_used_from_token_usage(token_usage) or _codex_int(state.get("contextUsed"), 0)
            token_context_window = _codex_context_window_from_token_usage(token_usage) or _codex_int(state.get("contextWindow"), 0)
            return {
                "model": model,
                "provider": provider,
                "providerKind": "claude-code",
                "contextWindow": token_context_window or (helper._context_window_for_model(helper, model, cfg) if self is None else helper._context_window_for_model(model, cfg)),
                "contextUsed": context_used,
                "tokenUsage": token_usage,
            }

        model = default_model

        # If a specific agent was requested, look up its model override
        if agent_id:
            for a in cfg.get("agents", {}).get("list", []):
                if a.get("id") == agent_id:
                    if a.get("model"):
                        model = a["model"]
                    break

        return {"model": model, "contextWindow": helper._context_window_for_model(helper, model, cfg) if self is None else helper._context_window_for_model(model, cfg)}

    def _get_providers(self):
        """Read providers, auth profiles, and models for the model manager UI."""
        try:
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)
        except Exception as e:
            return {"error": str(e)}

        # Read auth-profiles.json for actual keys and OAuth tokens
        # Separate API keys from subscription/token auth
        auth_profiles = {}
        raw_keys = {}  # provider -> actual key (for API calls)
        try:
            with open(AUTH_PROFILES_PATH, "r") as f:
                ap = json.load(f)
            for pid, profile in ap.get("profiles", {}).items():
                base_provider = profile.get("provider", pid.split(":")[0])
                key = profile.get("key", "")
                access = profile.get("access", "")
                token = profile.get("token", "")
                is_oauth = profile.get("type") in ("oauth", "token") or bool(access) or bool(token)
                
                # For providers with both API key and subscription, create separate entries
                if key:
                    # API key entry
                    masked = (key[:4] + "••••••••") if len(key) > 4 else ""
                    auth_profiles[base_provider] = {
                        "hasKey": True, "maskedKey": masked, "profileId": pid, 
                        "isOAuth": False, "authType": "api_key"
                    }
                    raw_keys[base_provider] = key
                
                if is_oauth and (access or token):
                    # Subscription/OAuth entry - use separate provider name
                    sub_provider = f"{base_provider}-token" if token and not access else f"{base_provider}-oauth"
                    expires = profile.get("expires", 0)
                    if expires:
                        remaining = (expires / 1000 - time.time()) if expires > 1e12 else (expires - time.time())
                        days = max(0, int(remaining / 86400))
                        masked = f"OAuth (expires {days}d)"
                    elif token:
                        masked = f"OAuth ({token[:8]}••••)"
                    else:
                        masked = "OAuth"
                    auth_profiles[sub_provider] = {
                        "hasKey": True, "maskedKey": masked, "profileId": pid,
                        "isOAuth": True, "authType": "subscription"
                    }
        except Exception:
            pass

        # Fetch live models for providers with keys
        for provider, key in raw_keys.items():
            if provider in auth_profiles:
                live_models = self._fetch_provider_models(provider, key)
                auth_profiles[provider]["models"] = live_models

        # For OAuth/token providers without API keys, use OpenClaw's model registry
        for provider, info in auth_profiles.items():
            if info.get("isOAuth") and provider not in raw_keys and "models" not in info:
                registry_models = self._fetch_registry_models(provider)
                info["models"] = registry_models

        # Custom providers (ollama etc) from models.providers
        custom_providers = {}
        for prov_name, prov_data in cfg.get("models", {}).get("providers", {}).items():
            custom_providers[prov_name] = {
                "baseUrl": prov_data.get("baseUrl", ""),
                "api": prov_data.get("api", ""),
                "apiKeyConfigured": bool(prov_data.get("apiKey")),
                "timeoutSeconds": prov_data.get("timeoutSeconds"),
                "models": [{"id": m["id"], "name": m.get("name", m["id"]),
                            "contextWindow": m.get("contextWindow", 0),
                            "maxTokens": m.get("maxTokens", 0)}
                           for m in prov_data.get("models", [])]
            }

        # Read model params from agents.defaults.models
        model_params = {}
        for mid, mdata in cfg.get("agents", {}).get("defaults", {}).get("models", {}).items():
            p = mdata.get("params", {})
            if p:
                model_params[mid] = p

        # Configured models from agents.defaults.models
        configured_models = {}
        for mid, mdata in cfg.get("agents", {}).get("defaults", {}).get("models", {}).items():
            configured_models[mid] = mdata

        safe_vo_config = _build_safe_vo_config()
        native_providers = {
            "hermes": {
                "enabled": safe_vo_config.get("hermes", {}).get("enabled", True),
                "detected": safe_vo_config.get("hermes", {}).get("detected", False),
                "model": _first_provider_agent_model("hermes"),
                "homePath": safe_vo_config.get("hermes", {}).get("homePath"),
                "binary": safe_vo_config.get("hermes", {}).get("binary"),
                "timeoutSec": safe_vo_config.get("hermes", {}).get("timeoutSec"),
                "apiEnabled": safe_vo_config.get("hermes", {}).get("apiEnabled", False),
                "preferApi": safe_vo_config.get("hermes", {}).get("preferApi", safe_vo_config.get("hermes", {}).get("apiEnabled", False)),
                "apiUrl": safe_vo_config.get("hermes", {}).get("apiUrl"),
                "apiDetected": safe_vo_config.get("hermes", {}).get("apiDetected", False),
                "configSurface": "models-native",
            },
            "codex": {
                "enabled": safe_vo_config.get("codex", {}).get("enabled", False),
                "detected": safe_vo_config.get("codex", {}).get("detected", False),
                "model": safe_vo_config.get("codex", {}).get("model") or _first_provider_agent_model("codex"),
                "homePath": safe_vo_config.get("codex", {}).get("homePath"),
                "binary": safe_vo_config.get("codex", {}).get("binary"),
                "workspace": safe_vo_config.get("codex", {}).get("workspace"),
                "workspaceRoot": safe_vo_config.get("codex", {}).get("workspaceRoot"),
                "mainWorkspace": safe_vo_config.get("codex", {}).get("mainWorkspace"),
                "bridgeUrl": safe_vo_config.get("codex", {}).get("bridgeUrl"),
                "sandbox": safe_vo_config.get("codex", {}).get("sandbox"),
                "approvalPolicy": safe_vo_config.get("codex", {}).get("approvalPolicy"),
                "includeMain": safe_vo_config.get("codex", {}).get("includeMain", True),
                "includeNativeAgents": safe_vo_config.get("codex", {}).get("includeNativeAgents", True),
                "registerNativeAgents": safe_vo_config.get("codex", {}).get("registerNativeAgents", True),
                "preferAppServer": safe_vo_config.get("codex", {}).get("preferAppServer", True),
                "configSurface": "models-native",
            },
            "claude-code": {
                "enabled": safe_vo_config.get("claudeCode", {}).get("enabled", False),
                "detected": safe_vo_config.get("claudeCode", {}).get("detected", False),
                "model": safe_vo_config.get("claudeCode", {}).get("model") or _first_provider_agent_model("claude-code"),
                "homePath": safe_vo_config.get("claudeCode", {}).get("homePath"),
                "binary": safe_vo_config.get("claudeCode", {}).get("binary"),
                "workspace": safe_vo_config.get("claudeCode", {}).get("workspace"),
                "workspaceRoot": safe_vo_config.get("claudeCode", {}).get("workspaceRoot"),
                "mainWorkspace": safe_vo_config.get("claudeCode", {}).get("mainWorkspace"),
                "timeoutSec": safe_vo_config.get("claudeCode", {}).get("timeoutSec"),
                "permissionMode": safe_vo_config.get("claudeCode", {}).get("permissionMode"),
                "includeMain": safe_vo_config.get("claudeCode", {}).get("includeMain", True),
                "includeNativeAgents": safe_vo_config.get("claudeCode", {}).get("includeNativeAgents", True),
                "registerNativeAgents": safe_vo_config.get("claudeCode", {}).get("registerNativeAgents", True),
                "configSurface": "models-native",
            },
        }

        return {"authProfiles": auth_profiles, "customProviders": custom_providers, "modelParams": model_params, "configuredModels": configured_models, "nativeProviders": native_providers}

    def _save_provider_key(self, provider, key):
        """Save a cloud provider API key to auth-profiles.json via watcher."""
        request = {
            "type": "save-key",
            "provider": provider,
            "key": key
        }
        return self._send_watcher_request(request)

    def _delete_provider_key(self, provider, profile_id=""):
        """Delete a cloud provider API key."""
        request = {
            "type": "delete-key",
            "provider": provider,
            "profileId": profile_id
        }
        return self._send_watcher_request(request)

    def _save_custom_provider(self, provider, base_url, models, params=None, api=None, api_key=None, timeout_seconds=None):
        """Save a custom provider config."""
        request = {
            "type": "save-custom-provider",
            "provider": provider,
            "baseUrl": base_url,
            "models": models,
        }
        if api:
            request["api"] = api
        if api_key:
            request["apiKey"] = api_key
        if timeout_seconds:
            request["timeoutSeconds"] = timeout_seconds
        if params:
            request["params"] = params
        return self._send_watcher_request(request)

    def _send_watcher_request(self, request):
        """Handle config change requests directly — no external watcher needed."""
        try:
            req_type = request.get("type", "")

            if req_type == "set-model":
                return self._handle_set_model(request)
            elif req_type == "save-key":
                return self._handle_save_key(request)
            elif req_type == "delete-key":
                return self._handle_delete_key(request)
            elif req_type == "save-custom-provider":
                return self._handle_save_custom_provider(request)
            elif req_type == "delete-custom-provider":
                return self._handle_delete_custom_provider(request)
            else:
                return {"ok": False, "error": f"Unknown request type: {req_type}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @staticmethod
    def _write_openclaw_config(cfg):
        """Write openclaw.json — handles read-only Docker mounts gracefully."""
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(cfg, f, indent=2)
            return True, None
        except OSError as e:
            if e.errno in (30, 13):  # EROFS, EACCES
                return False, (
                    "OpenClaw directory is mounted read-only. "
                    "In docker-compose.yml, ensure the volume does NOT end with ':ro'. "
                    "Example: '~/.openclaw:/openclaw' (not '~/.openclaw:/openclaw:ro')"
                )
            return False, str(e)

    def _handle_set_model(self, req):
        """Set an agent's model in openclaw.json and signal the gateway."""
        agent_id = req["agent_id"]
        model_id = req.get("model", "")

        with open(CONFIG_PATH) as f:
            cfg = json.load(f)

        found = False
        for a in cfg.get("agents", {}).get("list", []):
            if a["id"] == agent_id:
                if model_id:
                    a["model"] = model_id
                elif "model" in a:
                    del a["model"]
                found = True
                break

        if not found:
            return {"ok": False, "error": f"Agent {agent_id} not found in config"}

        ok, err = self._write_openclaw_config(cfg)
        if not ok:
            return {"ok": False, "error": err}

        self._signal_gateway(restart=True)
        return {"ok": True, "agent": agent_id, "model": model_id or "(default)"}

    def _handle_save_key(self, req):
        """Save an API key to auth-profiles and openclaw.json."""
        provider = req["provider"]
        key = req["key"]

        # Update auth-profiles.json
        try:
            with open(AUTH_PROFILES_PATH) as f:
                ap = json.load(f)
        except Exception:
            ap = {"version": 1, "profiles": {}, "lastGood": {}}

        profile_id = f"{provider}:default"
        ap["profiles"][profile_id] = {"type": "api_key", "provider": provider, "key": key}
        ap["lastGood"][provider] = profile_id

        try:
            with open(AUTH_PROFILES_PATH, "w") as f:
                json.dump(ap, f, indent=2)
        except OSError as e:
            return {"ok": False, "error": f"Cannot write auth-profiles.json: {e}"}

        # Mirror in openclaw.json
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        cfg.setdefault("auth", {}).setdefault("profiles", {})[profile_id] = {"provider": provider, "mode": "api_key"}
        ok, err = self._write_openclaw_config(cfg)
        if not ok:
            return {"ok": False, "error": err}

        self._signal_gateway(restart=False)
        masked = key[:4] + "••••••••" if len(key) > 4 else "****"
        return {"ok": True, "provider": provider, "maskedKey": masked}

    def _handle_delete_key(self, req):
        """Delete an API key from auth-profiles and openclaw.json."""
        provider = _safe_provider_id(req.get("provider", ""))
        profile_id = str(req.get("profileId") or "").strip()
        if not provider and not profile_id:
            return {"ok": False, "error": "provider or profileId is required"}
        result = _delete_openclaw_auth_direct(provider, profile_id)
        if not result.get("ok"):
            return result
        self._signal_gateway(restart=False)
        return result

    def _handle_save_custom_provider(self, req):
        """Save a custom provider (ollama, lmstudio, etc.) to openclaw.json."""
        provider = _safe_provider_id(req.get("provider", ""))
        base_url = str(req.get("baseUrl", "") or "").strip()
        models = _parse_model_entries(req.get("models", []))
        if not provider:
            return {"ok": False, "error": "provider is required"}
        if not base_url:
            return {"ok": False, "error": "base URL is required"}
        if not models:
            return {"ok": False, "error": "at least one model is required"}

        with open(CONFIG_PATH) as f:
            cfg = json.load(f)

        cfg.setdefault("models", {}).setdefault("providers", {})
        existing = cfg["models"]["providers"].get(provider, {})

        requested_api = req.get("api")
        requested_api_key = req.get("apiKey")
        requested_timeout = req.get("timeoutSeconds")
        if provider == "ollama":
            # OpenClaw 2026.5.x expects the native Ollama API root, not /v1.
            base_url = re.sub(r"/v1/?$", "", (base_url or "").strip())
            requested_api = requested_api or "ollama"
            requested_api_key = requested_api_key or existing.get("apiKey")
            requested_timeout = requested_timeout or existing.get("timeoutSeconds") or 300

        existing["baseUrl"] = base_url
        if requested_api:
            existing["api"] = requested_api
        elif not existing.get("api"):
            existing["api"] = "openai-completions"
        if requested_api_key:
            existing["apiKey"] = requested_api_key
        if requested_timeout:
            existing["timeoutSeconds"] = int(requested_timeout)

        old_models = {m["id"]: m for m in existing.get("models", [])}
        new_models = []
        for m in models:
            if m["id"] in old_models:
                updated = old_models[m["id"]]
                updated["name"] = m.get("name", updated.get("name", m["id"]))
                if "contextWindow" in m:
                    updated["contextWindow"] = m["contextWindow"]
                if "maxTokens" in m:
                    updated["maxTokens"] = m["maxTokens"]
                new_models.append(updated)
            else:
                new_models.append({
                    "id": m["id"],
                    "name": m.get("name", m["id"]),
                    "reasoning": False,
                    "input": ["text"],
                    "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                    "contextWindow": m.get("contextWindow", 100000),
                    "maxTokens": m.get("maxTokens", 8192),
                })
        existing["models"] = new_models
        cfg["models"]["providers"][provider] = existing

        # Save inference params
        params = req.get("params", {})
        if params:
            defaults_models = cfg.setdefault("agents", {}).setdefault("defaults", {}).setdefault("models", {})
            for model_id, model_params in params.items():
                defaults_models.setdefault(model_id, {})["params"] = model_params

        ok, err = self._write_openclaw_config(cfg)
        if not ok:
            return {"ok": False, "error": err}

        self._signal_gateway(restart=False)
        return {"ok": True, "provider": provider, "modelCount": len(new_models)}

    def _delete_custom_provider(self, provider):
        return self._send_watcher_request({"type": "delete-custom-provider", "provider": provider})

    def _handle_delete_custom_provider(self, req):
        provider = _safe_provider_id(req.get("provider", ""))
        if not provider:
            return {"ok": False, "error": "provider is required"}
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        providers = cfg.setdefault("models", {}).setdefault("providers", {})
        if provider not in providers:
            return {"ok": False, "error": f"Provider {provider} is not configured"}
        providers.pop(provider, None)
        defaults_models = cfg.setdefault("agents", {}).setdefault("defaults", {}).setdefault("models", {})
        for model_id in list(defaults_models.keys()):
            if model_id.startswith(provider + "/"):
                defaults_models.pop(model_id, None)
        for agent in cfg.get("agents", {}).get("list", []):
            if str(agent.get("model") or "").startswith(provider + "/"):
                agent.pop("model", None)
        ok, err = self._write_openclaw_config(cfg)
        if not ok:
            return {"ok": False, "error": err}
        self._signal_gateway(restart=False)
        return {"ok": True, "provider": provider}

    @staticmethod
    def _signal_gateway(restart=False):
        """Signal the OpenClaw gateway to reload config.

        Tries multiple approaches in order:
        1. systemctl --user (Linux service — works when running on host)
        2. Signal via /proc scan (works with --pid host in Docker)
        3. Signal file (gateway watches for restart trigger)

        Config changes are persisted to disk regardless — gateway picks them up
        on next restart/heartbeat even if signaling fails.
        """

        # Method 1: systemctl (works on host or with systemd access)
        try:
            if restart:
                r = subprocess.run(["systemctl", "--user", "restart", "openclaw-gateway.service"],
                                   capture_output=True, timeout=10)
            else:
                r = subprocess.run(["systemctl", "--user", "kill", "-s", "USR1", "openclaw-gateway.service"],
                                   capture_output=True, timeout=5)
            if r.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Method 2: scan /proc for gateway process (works with --pid host)
        try:
            for pid_dir in os.listdir("/proc"):
                if not pid_dir.isdigit():
                    continue
                try:
                    with open(f"/proc/{pid_dir}/cmdline", "rb") as f:
                        cmdline = f.read().decode("utf-8", errors="ignore")
                    if "openclaw" in cmdline and ("gateway" in cmdline or "serve" in cmdline):
                        os.kill(int(pid_dir), signal.SIGUSR2 if restart else signal.SIGUSR1)
                        return True
                except (PermissionError, ProcessLookupError, FileNotFoundError):
                    continue
        except Exception:
            pass

        # Method 3: pgrep fallback
        try:
            result = subprocess.run(["pgrep", "-f", "openclaw"],
                                    capture_output=True, text=True, timeout=5)
            for pid in result.stdout.strip().split("\n"):
                if pid.strip():
                    os.kill(int(pid.strip()), signal.SIGUSR1)
                    return True
        except Exception:
            pass

        # Config saved to disk — gateway will pick up changes on next restart
        return False

    def _get_models(self):
        """Read available models from openclaw.json."""
        # Ensure OAuth provider models are synced with live discovery before reading config
        try:
            self._discover_oauth_provider_models()
        except Exception:
            pass

        try:
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)
        except Exception as e:
            return {"error": str(e), "models": [], "agents": {}}

        models = []
        # Default model
        default_model = cfg.get("agents", {}).get("defaults", {}).get("model", {}).get("primary", "")
        if default_model:
            models.append({"id": default_model, "label": default_model + " (default)", "provider": default_model.split("/")[0] if "/" in default_model else ""})

        # Cloud models from providers with API keys (live-fetched, cached 5min)
        try:
            with open(AUTH_PROFILES_PATH, "r") as f:
                ap = json.load(f)
            for pid, profile in ap.get("profiles", {}).items():
                provider = profile.get("provider", pid.split(":")[0])
                key = profile.get("key", "")
                if key:
                    live_models = self._fetch_provider_models(provider, key)
                    for m in live_models:
                        if m.startswith("(error"):
                            continue
                        full_id = f"{provider}/{m}"
                        if full_id != default_model and not any(x["id"] == full_id for x in models):
                            models.append({"id": full_id, "label": full_id, "provider": provider})
        except Exception:
            pass

        # Add configured models from agents.defaults.models (includes OAuth providers like openai-codex)
        try:
            configured_models = cfg.get("agents", {}).get("defaults", {}).get("models", {})
            for mid, mdata in configured_models.items():
                if not any(x["id"] == mid for x in models):
                    provider = mid.split("/")[0] if "/" in mid else ""
                    label = mid
                    alias = mdata.get("alias", "")
                    if alias:
                        label = f"{mid} ({alias})"
                    models.append({"id": mid, "label": label, "provider": provider})
        except Exception:
            pass

        # Add subscription/OAuth models from configured models
        try:
            with open(AUTH_PROFILES_PATH, "r") as f:
                ap = json.load(f)
            # Build oauth_providers mapping from auth-profiles
            oauth_providers = {}  # base_provider -> display_name
            for pid, profile in ap.get("profiles", {}).items():
                base_prov = profile.get("provider", pid.split(":")[0])
                if profile.get("type") == "token" or profile.get("token"):
                    oauth_providers[base_prov] = f"{base_prov}-token"
                elif profile.get("type") == "oauth" or profile.get("access"):
                    oauth_providers[base_prov] = f"{base_prov}-oauth"
            
            pass  # oauth_providers built
            
            # Add subscription versions of configured models for providers with both API+token
            subscription_models = []
            configured_models = cfg.get("agents", {}).get("defaults", {}).get("models", {})
            for model in models:
                if "/" not in model["id"]:
                    continue
                base_prov = model["id"].split("/")[0]
                if base_prov in oauth_providers:
                    # Only add subscription version if model is configured (not live API-only)
                    if model["id"] in configured_models:
                        sub_model = dict(model)
                        sub_model["provider"] = oauth_providers[base_prov]
                        if not any(x["id"] == sub_model["id"] and x["provider"] == sub_model["provider"] for x in models):
                            subscription_models.append(sub_model)
            models.extend(subscription_models)
        except Exception as e:
            pass  # silently ignore subscription model errors

        # Ollama models from config
        for prov_name, prov_data in cfg.get("models", {}).get("providers", {}).items():
            for m in prov_data.get("models", []):
                mid = f'{prov_name}/{m["id"]}'
                label = m.get("name", m["id"])
                if not any(x["id"] == mid for x in models):
                    models.append({"id": mid, "label": f"{prov_name}/{label}", "provider": prov_name})

        # Per-agent current models
        agents = {}
        for a in cfg.get("agents", {}).get("list", []):
            agents[a["id"]] = a.get("model", "")
        # Map statusKey to agent id
        status_to_agent = {}
        for sk, ws in AGENT_WORKSPACES.items():
            # Find matching agent id
            for a in cfg.get("agents", {}).get("list", []):
                if a.get("workspace", "").endswith(ws) or a["id"] == sk or a["id"] == AGENT_SESSION_IDS.get(sk, ""):
                    status_to_agent[sk] = a["id"]
                    break

        agent_models = {}
        for sk, aid in status_to_agent.items():
            agent_models[sk] = agents.get(aid, "")

        # Identify subscription/OAuth providers for frontend tagging
        sub_providers = {}
        configured_models_map = {}
        try:
            with open(AUTH_PROFILES_PATH, "r") as f:
                ap2 = json.load(f)
            for pid, profile in ap2.get("profiles", {}).items():
                base_prov = profile.get("provider", pid.split(":")[0])
                if profile.get("type") in ("oauth", "token") or profile.get("access") or profile.get("token"):
                    # Map to display provider name
                    if profile.get("token"):
                        display_prov = f"{base_prov}-token"
                    else:
                        display_prov = f"{base_prov}-oauth"
                    sub_providers[display_prov] = True
        except Exception:
            pass
        try:
            for mid, mdata in cfg.get("agents", {}).get("defaults", {}).get("models", {}).items():
                configured_models_map[mid] = True
        except Exception:
            pass

        return {"models": models, "agentModels": agent_models, "defaultModel": default_model, "subProviders": sub_providers, "configuredModels": configured_models_map}

    def _set_agent_model(self, status_key, model_id):
        """Set an agent's model by writing a request file for the host-side watcher."""

        # Map statusKey to agent id
        try:
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)
        except Exception as e:
            return {"ok": False, "error": f"Failed to read config: {e}"}

        agent_id = None
        for sk, ws in AGENT_WORKSPACES.items():
            if sk == status_key:
                for a in cfg.get("agents", {}).get("list", []):
                    if a.get("workspace", "").endswith(ws) or a["id"] == sk or a["id"] == AGENT_SESSION_IDS.get(sk, ""):
                        agent_id = a["id"]
                        break
                break

        if not agent_id:
            return {"ok": False, "error": f"Unknown agent: {status_key}"}

        # Validate model_id format
        if model_id and "/" not in model_id:
            return {"ok": False, "error": f"Invalid model format: {model_id}. Must be provider/model"}

        request = {"type": "set-model", "agent_id": agent_id, "model": model_id, "status_key": status_key}
        return self._send_watcher_request(request)

    def do_PUT(self):
        parsed_url = urllib.parse.urlparse(self.path)
        if server_routes.dispatch(self, "PUT", parsed_url):
            return
        self.send_response(404)
        self.end_headers()

    def do_DELETE(self):
        parsed_url = urllib.parse.urlparse(self.path)
        if server_routes.dispatch(self, "DELETE", parsed_url):
            return
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        request_path = parsed_url.path
        if server_routes.dispatch(self, "POST", parsed_url):
            return
        # --- SETUP WIZARD ---
        # --- AGENT CREATION API ---
        # --- PRESENCE API ---
        elif self.path.startswith("/api/presence/"):
            agent_id = self.path.split("/api/presence/")[1].strip("/")
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            state = body.get("state", "idle")
            task = body.get("task", "")
            if state not in ("idle", "working", "meeting", "break"):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Invalid state"}).encode())
                return
            gateway_presence.set_manual_override(agent_id, state, task)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "agent": agent_id, "state": state}).encode())
            return
        elif self.path == "/transcribe":
            # Proxy to host whisper server
            length = int(self.headers.get('Content-Length', 0))
            audio = self.rfile.read(length) if length else b''
            try:
                _whisper_url = VO_CONFIG["whisper"]["url"].rstrip("/") + "/transcribe"
                req = urllib.request.Request(_whisper_url, data=audio,
                    headers={'Content-Type': self.headers.get('Content-Type', 'audio/webm')})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    result = resp.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(result)
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            return
        elif self.path.startswith("/agent-bio-save/"):
            # Save agent workspace file
            agent_key = self.path.split("/agent-bio-save/")[1]
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            filename = body.get("filename", "")
            content = body.get("content", "")
            # Security: only allow known filenames
            allowed = ["AGENTS.md", "SOUL.md", "MEMORY.md", "TOOLS.md", "IDENTITY.md", "USER.md", "HEARTBEAT.md"]
            ws_dir = AGENT_WORKSPACES.get(agent_key)
            if not ws_dir or filename not in allowed:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Invalid agent or filename: {agent_key}/{filename}"}).encode())
                return
            ws_path = os.path.join(WORKSPACE_BASE, ws_dir)
            fpath = os.path.join(ws_path, filename)
            try:
                with open(fpath, "w") as f:
                    f.write(content)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "saved": filename}).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            return
        elif self.path == "/set-model":
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            agent_key = body.get("agent", "")
            model_id = body.get("model", "")
            result = self._set_agent_model(agent_key, model_id)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        elif self.path == "/api/native-models/openclaw/agent-model":
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            result = self._set_agent_model(body.get("agent", ""), body.get("model", ""))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        elif self.path == "/api/native-models/openclaw/auth/api-key":
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            result = _save_openclaw_api_key(body.get("provider", ""), body.get("apiKey", ""), body.get("profileId", ""))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        elif self.path == "/api/native-models/openclaw/auth/delete":
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            result = self._delete_provider_key(body.get("provider", ""), body.get("profileId", ""))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        elif self.path == "/api/native-models/openclaw/provider":
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            result = self._save_custom_provider(
                _safe_provider_id(body.get("provider", "")),
                body.get("baseUrl", ""),
                _parse_model_entries(body.get("models", "")),
                api=body.get("api", ""),
                api_key=body.get("apiKey", ""),
                timeout_seconds=body.get("timeoutSeconds", None),
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        elif self.path == "/api/native-models/openclaw/provider/delete":
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            result = self._delete_custom_provider(body.get("provider", ""))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        elif self.path == "/api/native-models/hermes/profile-model":
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            result = _set_hermes_profile_model(
                body.get("profile", "default"),
                body.get("provider", ""),
                body.get("model", ""),
                body.get("baseUrl", ""),
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        elif self.path == "/api/native-models/hermes/auth/api-key":
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            result = _save_hermes_api_key(body.get("provider", ""), body.get("apiKey", ""), body.get("label", ""))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        elif self.path == "/api/native-models/hermes/auth/delete":
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            result = _delete_hermes_auth(body.get("provider", ""), body.get("target", ""))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        elif self.path == "/api/native-models/hermes/provider":
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            result = _save_hermes_custom_provider(
                body.get("profile", "default"),
                body.get("provider", ""),
                body.get("baseUrl", ""),
                body.get("models", ""),
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        elif self.path == "/api/native-models/hermes/provider/delete":
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            result = _delete_hermes_custom_provider(body.get("profile", "default"), body.get("provider", ""))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        elif self.path == "/api/gateway/configure":
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            result = self._configure_gateway_origin(body.get("origin", ""))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
            return
        elif self.path == "/clear-notify":
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        elif request_path == "/sms-thread-mode":
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            phone = self._normalize_sms_phone(body.get("phone", ""))
            mode = body.get("active", "agent")
            if mode not in ("user", "agent"):
                mode = "agent"
            if not phone:
                result = {"ok": False, "error": "Missing phone"}
            else:
                result = self._set_sms_thread_mode(phone, mode)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        elif request_path == "/sms-mode":
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            mode = body.get("active", "agent")
            if mode not in ("user", "agent"):
                mode = "agent"
            self._write_global_sms_mode(mode)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "active": mode}).encode())
        elif request_path == "/sms-send":
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            result = self._send_sms_intervention(body.get("to", ""), body.get("body", ""), body.get("name", ""), body.get("sender", "user"))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())

        elif self.path == "/upload":
            # Self-contained file upload — saves to STATUS_DIR/uploads/
            MAX_UPLOAD = 50 * 1024 * 1024  # 50MB
            length = int(self.headers.get('Content-Length', 0))
            if length > MAX_UPLOAD:
                self.send_response(413)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "File too large (max 50MB)"}).encode())
                return
            try:
                body = json.loads(self.rfile.read(length)) if length else {}
                filename = os.path.basename(body.get("filename", "upload"))
                mime_type = str(body.get("mimeType") or body.get("contentType") or mimetypes.guess_type(filename)[0] or "")
                content = base64.b64decode(body.get("content", ""))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
                return
            upload_dir = os.path.join(STATUS_DIR, "uploads")
            os.makedirs(upload_dir, exist_ok=True)
            dest = os.path.join(upload_dir, filename)
            if os.path.exists(dest):
                stem, ext = os.path.splitext(filename)
                dest = os.path.join(upload_dir, f"{stem}_{int(time.time())}{ext}")
            with open(dest, "wb") as f:
                f.write(content)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "path": dest,
                "url": "/chat-media?path=" + urllib.parse.quote(dest),
                "mimeType": mime_type,
                "size": len(content)
            }).encode())
            print(f"📎 Upload: {dest} ({len(content):,} bytes)")

        else:
            self.send_response(404)
            self.end_headers()

    def _configure_gateway_origin(self, origin):
        """Configure gateway to allow the given origin, and set insecure auth flags for Docker."""
        if not origin:
            return {"ok": False, "error": "No origin provided"}
        try:
            try:
                with open(CONFIG_PATH, "r") as f:
                    cfg = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                cfg = {}

            gateway_cfg = cfg.setdefault("gateway", {})
            control_ui = gateway_cfg.setdefault("controlUi", {})

            # Get current allowed origins
            origins = control_ui.get("allowedOrigins", [])
            if not isinstance(origins, list):
                origins = []

            added = origin not in origins
            if added:
                origins.append(origin)
            control_ui["allowedOrigins"] = origins

            # Ensure insecure auth flags for Docker
            control_ui["allowInsecureAuth"] = True
            control_ui["dangerouslyDisableDeviceAuth"] = True

            with open(CONFIG_PATH, "w") as f:
                json.dump(cfg, f, indent=2)

            # Signal gateway to reload
            self._signal_gateway(restart=False)

            return {"ok": True, "added": added, "origins": origins}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _test_gateway_connection(self):
        """Test server-side connectivity to the OpenClaw gateway."""
        import asyncio as _asyncio
        import concurrent.futures

        async def _do_test():
            try:
                gw_url = VO_CONFIG["openclaw"]["gatewayUrl"]
                origin = f"http://127.0.0.1:{PORT}"
                token = _get_gateway_token()

                import websockets as _ws
                from websockets.asyncio.client import connect as _ws_connect

                async with _asyncio.timeout(5):
                    ws = await _ws_connect(
                        gw_url,
                        max_size=1024 * 1024,
                        additional_headers={"Origin": origin},
                        close_timeout=3,
                    )
                    async with ws:
                        # Wait for challenge
                        raw = await _asyncio.wait_for(ws.recv(), timeout=5)
                        msg = json.loads(raw)
                        if msg.get("event") != "connect.challenge":
                            return {"ok": False, "gateway": "unexpected_response"}

                        # Send connect
                        connect_msg = {
                            "type": "req",
                            "id": "gw-test-1",
                            "method": "connect",
                            "params": {
                                "minProtocol": 4, "maxProtocol": 4,
                                "client": {"id": "openclaw-control-ui", "version": _get_openclaw_version(), "platform": "server", "mode": "webchat"},
                                "role": "operator",
                                "scopes": ["operator.read"],
                                "caps": [], "commands": [], "permissions": {},
                                "auth": {"token": token}
                            }
                        }
                        await ws.send(json.dumps(connect_msg))

                        raw2 = await _asyncio.wait_for(ws.recv(), timeout=5)
                        res = json.loads(raw2)
                        if not res.get("ok"):
                            err = res.get("error", {}).get("message", "unknown")
                            return {"ok": True, "gateway": "reachable", "token": False, "error": err, "agents": 0}

                        # Connected — query sessions
                        req = {"type": "req", "id": "gw-test-2", "method": "sessions.list", "params": {}}
                        await ws.send(json.dumps(req))
                        raw3 = await _asyncio.wait_for(ws.recv(), timeout=5)
                        res3 = json.loads(raw3)
                        sessions = res3.get("payload", {}).get("sessions", []) if res3.get("ok") else []
                        agent_ids = {
                            s.get("key", "").split(":", 2)[1]
                            for s in sessions
                            if isinstance(s, dict)
                            and s.get("key", "").startswith("agent:")
                            and len(s.get("key", "").split(":", 2)) >= 2
                        }
                        agent_count = len(agent_ids)

                        return {"ok": True, "gateway": "reachable", "token": True, "agents": agent_count}

            except (ConnectionRefusedError, ConnectionResetError, OSError):
                return {"ok": False, "gateway": "unreachable", "token": False, "agents": 0}
            except Exception as e:
                return {"ok": False, "gateway": "error", "error": str(e)[:200], "token": False, "agents": 0}

        # Run async test in a thread pool to avoid blocking the HTTP server
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: _asyncio.run(_do_test()))
            try:
                return future.result(timeout=10)
            except Exception as e:
                return {"ok": False, "gateway": "error", "error": str(e)[:200]}

    def _sms_owner_agent_id(self):
        sms_cfg = VO_CONFIG.get("sms", {}) or {}
        owner_id = (sms_cfg.get("ownerAgentId") or sms_cfg.get("agentId") or "").strip()
        return owner_id or None

    def _get_sms_owner_agent_info(self):
        owner_id = self._sms_owner_agent_id()
        info = {"id": owner_id, "name": owner_id or "Unassigned", "emoji": "🤖"}
        if not owner_id:
            return info
        try:
            refresh_agent_maps()
            for agent in get_roster():
                if agent.get("id") == owner_id or agent.get("statusKey") == owner_id:
                    return {
                        "id": agent.get("id") or owner_id,
                        "statusKey": agent.get("statusKey") or owner_id,
                        "name": agent.get("name") or owner_id,
                        "emoji": agent.get("emoji") or "🤖",
                        "role": agent.get("role") or "",
                    }
        except Exception:
            pass
        return info

    def _normalize_sms_phone(self, phone):
        if not phone:
            return ""
        phone = str(phone).strip()
        phone = re.sub(r"[\s\-()]+", "", phone)
        if phone.startswith("00"):
            phone = "+" + phone[2:]
        if phone.startswith("+"):
            return phone
        if phone.isdigit():
            if len(phone) == 10:
                return "+1" + phone
            if len(phone) == 11 and phone.startswith("1"):
                return "+" + phone
        return phone

    def _sms_primary_data_dir(self):
        owner_id = self._sms_owner_agent_id()
        if owner_id:
            candidate = os.path.join(WORKSPACE_BASE, get_agent_workspace_dir(WORKSPACE_BASE, owner_id))
            if os.path.isdir(candidate):
                return candidate
        return STATUS_DIR

    def _sms_data_dirs(self):
        dirs = []
        for candidate in [self._sms_primary_data_dir(), STATUS_DIR]:
            if candidate and candidate not in dirs and os.path.isdir(candidate):
                dirs.append(candidate)
        if not dirs:
            dirs.append(STATUS_DIR)
        return dirs

    def _sms_log_paths(self):
        paths = []
        for base_dir in self._sms_data_dirs():
            for rel_path in ["sms-log.jsonl", os.path.join("sms-archive", "sms-log-all.jsonl")]:
                full_path = os.path.join(base_dir, rel_path)
                if os.path.isfile(full_path) and full_path not in paths:
                    paths.append(full_path)
        return paths

    def _sms_contacts_paths(self):
        paths = []
        for base_dir in self._sms_data_dirs():
            for name in ["contacts.json", "sms-contacts.json"]:
                full_path = os.path.join(base_dir, name)
                if os.path.isfile(full_path) and full_path not in paths:
                    paths.append(full_path)
        return paths

    def _sms_primary_log_path(self):
        primary_dir = self._sms_primary_data_dir()
        os.makedirs(primary_dir, exist_ok=True)
        return os.path.join(primary_dir, "sms-log.jsonl")

    def _sms_primary_contacts_path(self):
        primary_dir = self._sms_primary_data_dir()
        os.makedirs(primary_dir, exist_ok=True)
        preferred = "contacts.json" if primary_dir != STATUS_DIR else "sms-contacts.json"
        return os.path.join(primary_dir, preferred)

    def _sms_thread_modes_path(self):
        return os.path.join(STATUS_DIR, "sms-thread-modes.json")

    def _read_global_sms_mode(self):
        try:
            with open(os.path.join(STATUS_DIR, "sms-mode.json")) as f:
                mode = json.load(f)
            active = mode.get("active", "agent")
            if active not in ("agent", "user"):
                active = "agent"
            return {"active": active}
        except Exception:
            return {"active": "agent"}

    def _write_global_sms_mode(self, mode):
        os.makedirs(STATUS_DIR, exist_ok=True)
        with open(os.path.join(STATUS_DIR, "sms-mode.json"), "w") as f:
            json.dump({"active": mode}, f)

    def _read_sms_thread_modes(self):
        try:
            with open(self._sms_thread_modes_path()) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {}
            cleaned = {}
            for phone, mode in data.items():
                normalized_phone = self._normalize_sms_phone(phone)
                if normalized_phone and mode in ("agent", "user"):
                    cleaned[normalized_phone] = mode
            return cleaned
        except Exception:
            return {}

    def _set_sms_thread_mode(self, phone, mode):
        phone = self._normalize_sms_phone(phone)
        if not phone:
            return {"ok": False, "error": "Missing phone"}
        modes = self._read_sms_thread_modes()
        modes[phone] = mode if mode in ("agent", "user") else "agent"
        os.makedirs(STATUS_DIR, exist_ok=True)
        with open(self._sms_thread_modes_path(), "w") as f:
            json.dump(modes, f, indent=2, sort_keys=True)
        return {"ok": True, "phone": phone, "active": modes[phone]}

    def _sms_mode_for_phone(self, phone):
        phone = self._normalize_sms_phone(phone)
        modes = self._read_sms_thread_modes()
        if phone and phone in modes:
            return modes[phone]
        return self._read_global_sms_mode().get("active", "agent")

    def _normalize_sms_timestamp(self, entry):
        timestamp = entry.get("timestamp")
        if not timestamp:
            return timestamp
        try:
            dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        except Exception:
            return timestamp
        try:
            if dt.tzinfo is None:
                return dt.replace(tzinfo=SMS_DEFAULT_TZ).isoformat()
            return dt.astimezone(SMS_DEFAULT_TZ).isoformat()
        except Exception:
            return timestamp

    def _sms_sort_value(self, timestamp):
        if not timestamp:
            return 0.0
        try:
            dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                return dt.timestamp()
            return dt.timestamp()
        except Exception:
            return 0.0

    def _is_twilio_media_url(self, url):
        if not url:
            return False
        try:
            parsed = urllib.parse.urlparse(str(url))
            return (parsed.scheme == "https" and parsed.netloc.lower() == "api.twilio.com"
                    and parsed.path.startswith("/2010-04-01/Accounts/") and "/Media/" in parsed.path)
        except Exception:
            return False

    def _sms_media_proxy_url(self, url, content_type=""):
        if self._is_twilio_media_url(url):
            query = {"url": url}
            if content_type:
                query["contentType"] = content_type
            return "/sms-media?" + urllib.parse.urlencode(query)
        return url

    def _normalize_sms_media(self, entry):
        media = []
        def add_media(url, content_type="", filename=""):
            url = str(url or "").strip()
            if not url:
                return
            item = {"url": url, "contentType": str(content_type or "").strip(), "filename": str(filename or "").strip()}
            item["proxyUrl"] = self._sms_media_proxy_url(item["url"], item["contentType"])
            media.append(item)
        raw_media = entry.get("media") or entry.get("mediaUrls") or entry.get("attachments")
        if isinstance(raw_media, list):
            for item in raw_media:
                if isinstance(item, str):
                    add_media(item)
                elif isinstance(item, dict):
                    add_media(item.get("url") or item.get("mediaUrl") or item.get("MediaUrl") or item.get("href"),
                              item.get("contentType") or item.get("mediaContentType") or item.get("ContentType") or item.get("type"),
                              item.get("filename") or item.get("name"))
        elif isinstance(raw_media, dict):
            add_media(raw_media.get("url") or raw_media.get("mediaUrl") or raw_media.get("MediaUrl") or raw_media.get("href"),
                      raw_media.get("contentType") or raw_media.get("mediaContentType") or raw_media.get("ContentType") or raw_media.get("type"),
                      raw_media.get("filename") or raw_media.get("name"))
        try:
            num_media = int(entry.get("NumMedia") or entry.get("numMedia") or entry.get("num_media") or 0)
        except Exception:
            num_media = 0
        for idx in range(max(0, min(20, num_media))):
            add_media(entry.get(f"MediaUrl{idx}") or entry.get(f"mediaUrl{idx}"),
                      entry.get(f"MediaContentType{idx}") or entry.get(f"mediaContentType{idx}"))
        deduped = []
        seen = set()
        for item in media:
            key = (item.get("url"), item.get("contentType"), item.get("filename"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _twilio_api_get_json(self, url):
        sms_cfg = VO_CONFIG.get("sms", {})
        account_sid = sms_cfg.get("twilioAccountSid")
        auth_token = sms_cfg.get("twilioAuthToken")
        if not account_sid or not auth_token:
            return None
        credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Basic {credentials}")
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())

    def _twilio_message_media(self, message_sid):
        if not message_sid:
            return []
        cache = getattr(self.__class__, "_sms_twilio_media_cache", {})
        now = time.time()
        cached = cache.get(message_sid)
        if cached and now - cached.get("ts", 0) < 300:
            return cached.get("media", [])
        sms_cfg = VO_CONFIG.get("sms", {})
        account_sid = sms_cfg.get("twilioAccountSid")
        if not account_sid:
            return []
        try:
            data = self._twilio_api_get_json(f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages/{message_sid}/Media.json")
            media = []
            for item in (data or {}).get("media_list", []):
                uri = item.get("uri") or ""
                if uri.endswith(".json"):
                    uri = uri[:-5]
                url = "https://api.twilio.com" + uri if uri.startswith("/") else uri
                if url:
                    media.append({"url": url, "contentType": item.get("content_type") or "",
                                  "filename": item.get("sid") or "MMS media",
                                  "proxyUrl": self._sms_media_proxy_url(url, item.get("content_type") or "")})
            cache[message_sid] = {"ts": now, "media": media}
            self.__class__._sms_twilio_media_cache = cache
            return media
        except Exception:
            return []

    def _recent_twilio_messages_with_media(self):
        cache = getattr(self.__class__, "_sms_twilio_recent_media_cache", None)
        now = time.time()
        if cache and now - cache.get("ts", 0) < 60:
            return cache.get("messages", [])
        sms_cfg = VO_CONFIG.get("sms", {})
        account_sid = sms_cfg.get("twilioAccountSid")
        if not account_sid:
            return []
        try:
            data = self._twilio_api_get_json(f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json?PageSize=50")
            messages = []
            for msg in (data or {}).get("messages", []):
                try:
                    num_media = int(msg.get("num_media") or 0)
                except Exception:
                    num_media = 0
                if num_media <= 0:
                    continue
                media = self._twilio_message_media(msg.get("sid"))
                if not media:
                    continue
                try:
                    sent_dt = email.utils.parsedate_to_datetime(msg.get("date_sent") or msg.get("date_created") or "")
                except Exception:
                    sent_dt = None
                messages.append({"sid": msg.get("sid"), "from": self._normalize_sms_phone(msg.get("from")),
                                 "to": self._normalize_sms_phone(msg.get("to")), "body": msg.get("body") or "",
                                 "timestamp": sent_dt.timestamp() if sent_dt else 0, "media": media})
            self.__class__._sms_twilio_recent_media_cache = {"ts": now, "messages": messages}
            return messages
        except Exception:
            return []

    def _enrich_sms_entries_with_twilio_media(self, entries):
        candidates = [e for e in entries if not e.get("media") and e.get("type") in ("inbound", "outbound") and e.get("phone")]
        if not candidates:
            return entries
        twilio_messages = self._recent_twilio_messages_with_media()
        if not twilio_messages:
            return entries
        for entry in candidates:
            entry_phone = self._normalize_sms_phone(entry.get("phone"))
            body = entry.get("body") or ""
            entry_ts = self._sms_sort_value(entry.get("timestamp"))
            best = None
            best_score = 999999
            for msg in twilio_messages:
                if entry_phone not in (msg.get("from"), msg.get("to")):
                    continue
                if body and msg.get("body") and body.strip() != msg.get("body", "").strip():
                    continue
                delta = abs((entry_ts or 0) - (msg.get("timestamp") or 0)) if entry_ts and msg.get("timestamp") else 0
                if delta and delta > 900:
                    continue
                if delta < best_score:
                    best = msg; best_score = delta
            if best:
                entry["sid"] = entry.get("sid") or best.get("sid")
                entry["media"] = best.get("media") or []
        return entries

    def _handle_sms_media_proxy(self, query_params):
        url = (query_params.get("url", [""])[0] or "").strip()
        requested_type = (query_params.get("contentType", [""])[0] or "").strip()
        if not self._is_twilio_media_url(url):
            self.send_response(400); self.send_header("Content-Type", "text/plain"); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(b"Invalid SMS media URL"); return
        sms_cfg = VO_CONFIG.get("sms", {})
        account_sid = sms_cfg.get("twilioAccountSid")
        auth_token = sms_cfg.get("twilioAuthToken")
        if not account_sid or not auth_token:
            self.send_response(503); self.send_header("Content-Type", "text/plain"); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(b"SMS media proxy is not configured"); return
        try:
            credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"Basic {credentials}")
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = resp.read(); content_type = resp.headers.get("Content-Type") or requested_type or "application/octet-stream"
            self.send_response(200); self.send_header("Content-Type", content_type); self.send_header("Cache-Control", "private, max-age=3600"); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(payload)
        except Exception as e:
            self.send_response(502); self.send_header("Content-Type", "text/plain"); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(f"Could not fetch SMS media: {e}".encode())

    def _load_sms_contacts_map(self):
        contacts = {}
        for path in self._sms_contacts_paths():
            try:
                with open(path) as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                for phone, info in data.items():
                    normalized_phone = self._normalize_sms_phone(phone)
                    if not normalized_phone:
                        continue
                    info = info if isinstance(info, dict) else {}
                    existing = contacts.get(normalized_phone, {})
                    merged = dict(existing)
                    merged.update(info)
                    merged["name"] = merged.get("name") or existing.get("name") or "Unknown"
                    contacts[normalized_phone] = merged
            except Exception:
                pass
        return contacts

    def _read_sms_entries(self, limit=None, phone=None):
        contacts = self._load_sms_contacts_map()
        normalized_phone = self._normalize_sms_phone(phone) if phone else ""
        entries = []
        seen = set()
        for path in self._sms_log_paths():
            try:
                with open(path) as f:
                    for raw_line in f:
                        raw_line = raw_line.strip()
                        if not raw_line:
                            continue
                        try:
                            entry = json.loads(raw_line)
                        except Exception:
                            continue
                        entry_phone = self._normalize_sms_phone(entry.get("phone", ""))
                        if normalized_phone and entry_phone != normalized_phone:
                            continue
                        entry["phone"] = entry_phone or entry.get("phone", "")
                        if entry_phone:
                            contact_name = contacts.get(entry_phone, {}).get("name")
                            if contact_name and (not entry.get("name") or entry.get("name") == "Unknown"):
                                entry["name"] = contact_name
                        entry["timestamp"] = self._normalize_sms_timestamp(entry)
                        media = self._normalize_sms_media(entry)
                        if media:
                            entry["media"] = media
                        key = (
                            entry.get("sid") or "",
                            entry.get("type") or "",
                            entry.get("phone") or "",
                            entry.get("timestamp") or "",
                            entry.get("body") or "",
                            json.dumps(media, sort_keys=True),
                        )
                        if key in seen:
                            continue
                        seen.add(key)
                        entries.append(entry)
            except FileNotFoundError:
                continue
            except Exception:
                continue
        entries.sort(key=lambda item: self._sms_sort_value(item.get("timestamp")))
        entries = self._enrich_sms_entries_with_twilio_media(entries)
        if limit and len(entries) > limit:
            entries = entries[-limit:]
        return entries

    def _build_sms_threads(self, limit=200):
        contacts = self._load_sms_contacts_map()
        threads = {}
        for message in self._read_sms_entries(limit=None):
            if message.get("type") == "blocked":
                continue
            phone = self._normalize_sms_phone(message.get("phone", ""))
            if not phone or phone == "Unknown":
                continue
            thread = threads.setdefault(phone, {
                "phone": phone,
                "name": contacts.get(phone, {}).get("name") or message.get("name") or "Unknown",
                "lastMessage": "",
                "lastTimestamp": "",
                "lastType": "",
                "messageCount": 0,
            })
            thread["messageCount"] += 1
            body = message.get("body", "")
            media_count = len(message.get("media") or [])
            thread["lastMessage"] = body or (f"📎 {media_count} media attachment" + ("s" if media_count != 1 else "") if media_count else "")
            thread["lastTimestamp"] = message.get("timestamp", "")
            thread["lastType"] = message.get("type", "")
            if (not thread.get("name") or thread.get("name") == "Unknown") and message.get("name"):
                thread["name"] = message.get("name")

        for phone, info in contacts.items():
            threads.setdefault(phone, {
                "phone": phone,
                "name": (info or {}).get("name") or "Unknown",
                "lastMessage": "",
                "lastTimestamp": "",
                "lastType": "",
                "messageCount": 0,
            })

        results = []
        for phone, thread in threads.items():
            thread["activeMode"] = self._sms_mode_for_phone(phone)
            thread["displayName"] = thread.get("name") or phone
            results.append(thread)

        results.sort(key=lambda item: (
            0 if item.get("lastTimestamp") else 1,
            -self._sms_sort_value(item.get("lastTimestamp")),
            (item.get("displayName") or item.get("phone") or "").lower(),
        ))
        if limit and len(results) > limit:
            results = results[:limit]
        return results

    def _get_sms_log(self, limit=100):
        try:
            return {"ok": True, "messages": self._read_sms_entries(limit=limit)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _get_sms_contacts(self):
        try:
            return {"ok": True, "contacts": self._load_sms_contacts_map()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _get_sms_threads(self, limit=200):
        try:
            return {
                "ok": True,
                "threads": self._build_sms_threads(limit=limit),
                "ownerAgent": self._get_sms_owner_agent_info(),
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "threads": []}

    def _get_sms_thread(self, phone, limit=250):
        phone = self._normalize_sms_phone(phone)
        if not phone:
            return {"ok": False, "error": "Missing phone", "messages": []}
        contacts = self._load_sms_contacts_map()
        messages = self._read_sms_entries(limit=limit, phone=phone)
        thread = {
            "phone": phone,
            "name": contacts.get(phone, {}).get("name") or (messages[-1].get("name") if messages else "Unknown") or "Unknown",
            "activeMode": self._sms_mode_for_phone(phone),
            "messageCount": len(messages),
            "ownerAgent": self._get_sms_owner_agent_info(),
        }
        if messages:
            last = messages[-1]
            media_count = len(last.get("media") or [])
            thread["lastMessage"] = last.get("body", "") or (f"📎 {media_count} media attachment" + ("s" if media_count != 1 else "") if media_count else "")
            thread["lastTimestamp"] = last.get("timestamp", "")
            thread["lastType"] = last.get("type", "")
        return {"ok": True, "thread": thread, "messages": messages}

    def _send_sms_intervention(self, to, body, name="", sender="user"):
        """Send SMS via Twilio (config-driven credentials)."""
        to = self._normalize_sms_phone(to)
        if not to or not body:
            return {"ok": False, "error": "Missing 'to' or 'body'"}
        sms_cfg = VO_CONFIG.get("sms", {})
        account_sid = sms_cfg.get("twilioAccountSid")
        auth_token = sms_cfg.get("twilioAuthToken")
        from_number = sms_cfg.get("fromNumber")
        if not account_sid or not auth_token or not from_number:
            return {"ok": False, "error": "SMS not configured. Set Twilio credentials in Settings or /setup."}

        sender = "agent" if sender == "agent" else "user"
        entry_type = "outbound" if sender == "agent" else "intervention"
        sms_log_path = self._sms_primary_log_path()
        contacts_path = self._sms_primary_contacts_path()

        try:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
            data = urllib.parse.urlencode({"To": to, "From": from_number, "Body": body}).encode()
            credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Authorization", f"Basic {credentials}")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read().decode())

            entry = {
                "type": entry_type,
                "phone": to,
                "name": name or self._load_sms_contacts_map().get(to, {}).get("name") or "Unknown",
                "body": body,
                "sid": result.get("sid"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            with open(sms_log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")

            try:
                with open(contacts_path) as f:
                    contacts = json.load(f)
                if not isinstance(contacts, dict):
                    contacts = {}
            except Exception:
                contacts = {}

            if to not in contacts:
                contacts[to] = {
                    "name": name or "Unknown",
                    "added": datetime.now().strftime("%Y-%m-%d"),
                    "note": "Added via Virtual Office",
                }
            elif name and contacts[to].get("name") in (None, "", "Unknown"):
                contacts[to]["name"] = name

            with open(contacts_path, "w") as f:
                json.dump(contacts, f, indent=2)

            return {
                "ok": True,
                "sid": result.get("sid"),
                "status": result.get("status"),
                "phone": to,
                "sender": sender,
                "type": entry_type,
            }
        except urllib.error.HTTPError as e:
            err = e.read().decode()
            try:
                return {"ok": False, "error": json.loads(err).get("message", err[:200])}
            except Exception:
                return {"ok": False, "error": err[:200]}
        except Exception as e:
            return {"ok": False, "error": str(e)}

# ─── WS PROXY QUIET MODE ─────────────────────────────────────────
_ws_proxy_connected_logged = False
_ws_proxy_failed_logged = False


async def try_connect_gateway():
    """Try connecting to gateway, with fallback URLs."""
    global _ws_proxy_connected_logged, _ws_proxy_failed_logged
    for url in [GATEWAY_URL, GATEWAY_URL_FALLBACK]:
        try:
            gw = await asyncio.wait_for(
                ws_connect(url, max_size=10 * 1024 * 1024, additional_headers={"Origin": f"http://127.0.0.1:{PORT}"}),
                timeout=3
            )
            if not _ws_proxy_connected_logged:
                print(f"✅ Connected to gateway (WS proxy): {url}")
                _ws_proxy_connected_logged = True
            _ws_proxy_failed_logged = False
            return gw
        except Exception:
            pass
    if not _ws_proxy_failed_logged:
        print(f"⚠️  WS proxy: gateway not reachable — will retry silently")
        _ws_proxy_failed_logged = True
    return None


async def browser_viewer_ws_proxy(client_ws):
    """Proxy the embedded Kasm viewer websocket through the VO websocket port."""
    upstream_base, headers = _browser_viewer_upstream_parts()
    if not upstream_base:
        await client_ws.close(1011, "Browser viewer is not configured")
        return

    parsed = urllib.parse.urlparse(upstream_base)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        await client_ws.close(1011, "Browser viewer URL is invalid")
        return

    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    upstream_url = urllib.parse.urlunparse((ws_scheme, parsed.netloc, "/websockify", "", "", ""))
    upstream_headers = dict(headers)
    upstream_headers.setdefault("Sec-WebSocket-Origin", upstream_base)
    connect_kwargs = {
        "max_size": 10 * 1024 * 1024,
        "additional_headers": upstream_headers,
        "origin": upstream_base,
        "subprotocols": ["binary", "base64"],
    }
    if ws_scheme == "wss":
        connect_kwargs["ssl"] = ssl._create_unverified_context()

    try:
        upstream_ws = await ws_connect(upstream_url, **connect_kwargs)
    except Exception as e:
        print(f"⚠️  Browser viewer WS proxy failed: {e}")
        await client_ws.close(1011, "Cannot reach browser viewer websocket")
        return

    async def client_to_upstream():
        try:
            async for msg in client_ws:
                await upstream_ws.send(msg)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception:
            pass
        finally:
            try:
                await upstream_ws.close()
            except Exception:
                pass

    async def upstream_to_client():
        try:
            async for msg in upstream_ws:
                await client_ws.send(msg)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception:
            pass
        finally:
            try:
                await client_ws.close()
            except Exception:
                pass

    await asyncio.gather(client_to_upstream(), upstream_to_client())


async def ws_proxy(client_ws):
    """Proxy a browser WebSocket connection to the OpenClaw gateway."""
    global _ws_proxy_connected_logged, _ws_proxy_failed_logged
    try:
        req = getattr(client_ws, "request", None)
        ws_path = getattr(req, "path", "") or getattr(client_ws, "path", "") or ""
    except Exception:
        ws_path = ""
    if urllib.parse.urlparse(ws_path).path == "/browser-viewer-websockify":
        await browser_viewer_ws_proxy(client_ws)
        return

    gw = await try_connect_gateway()
    if not gw:
        await client_ws.close(1011, "Cannot reach gateway")
        return

    async def client_to_gw():
        global _ws_proxy_connected_logged
        try:
            async for msg in client_ws:
                await gw.send(msg)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception:
            pass
        finally:
            _ws_proxy_connected_logged = False  # allow re-log on next connect
            await gw.close()

    async def gw_to_client():
        global _ws_proxy_connected_logged
        try:
            async for msg in gw:
                await client_ws.send(msg)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception:
            pass
        finally:
            _ws_proxy_connected_logged = False  # allow re-log on next connect
            await client_ws.close()

    async def ping_loop():
        """Send periodic pings to keep the gateway connection alive."""
        try:
            while True:
                await asyncio.sleep(30)
                await gw.ping()
        except Exception:
            pass

    await asyncio.gather(client_to_gw(), gw_to_client(), ping_loop())


def select_ws_subprotocol(_connection, offered):
    if "binary" in offered:
        return "binary"
    if "base64" in offered:
        return "base64"
    return None


async def run_ws_server():
    """Run the WebSocket proxy server."""
    async with websockets.serve(
        ws_proxy,
        "0.0.0.0",
        WS_PORT,
        max_size=10 * 1024 * 1024,
        subprotocols=["binary", "base64"],
        select_subprotocol=select_ws_subprotocol,
    ):
        print(f"🔌 WebSocket proxy on :{WS_PORT} → gateway")
        await asyncio.Future()  # run forever


def start_ws_server():
    asyncio.run(run_ws_server())


def start_http_server():
    # Initialize gateway presence with discovered agents
    agent_ids = [a["statusKey"] for a in get_roster()]
    gateway_presence.init_agents(agent_ids)

    # Set the meetings file path (office.py still writes meetings here)
    gateway_presence.set_meetings_file(STATUS_FILE)

    # Load disk snapshot for crash recovery
    snapshot_path = os.path.join(STATUS_DIR, "presence-snapshot.json")
    gateway_presence.load_snapshot(snapshot_path)

    # Also load meetings from old status file if it exists (migration)
    try:
        with open(STATUS_FILE, "r") as f:
            old_status = json.load(f)
        meetings = old_status.get("_meetings", [])
        if meetings:
            gateway_presence.set_meetings(meetings)
            print(f"Migrated {len(meetings)} meetings from old status file")
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Auto-configure gateway to accept our origin (plug and play for Docker bridge)
    _auto_configure_gateway_origin()

    # Read gateway token (vo-config override, then openclaw.json)
    gw_token = _get_gateway_token()

    # Start gateway presence listener
    gw_url = VO_CONFIG["openclaw"]["gatewayUrl"]
    if gw_token:
        gateway_presence.start(gw_url, gw_token, port=PORT, client_version=_get_openclaw_version())
    else:
        print("⚠️  No gateway token found — gateway presence disabled")

    # Start periodic snapshot saver (every 30s)
    def snapshot_loop():
        while True:
            time.sleep(30)
            gateway_presence.save_snapshot(snapshot_path)
    snap_thread = threading.Thread(target=snapshot_loop, daemon=True, name="presence-snapshot")
    snap_thread.start()

    _oname = VO_CONFIG["office"]["name"]
    print(f"🏢 {_oname} → http://localhost:{PORT}")
    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), OfficeHandler)
    server.serve_forever()


# Workflow auto-resume lives in server_services.workflow.


if __name__ == "__main__":
    # Start API usage collector background thread
    _api_usage_collector.start()
    print("📊 API usage collector started (polls every 60s)")

    # Start WS proxy in a background thread
    ws_thread = threading.Thread(target=start_ws_server, daemon=True)
    ws_thread.start()

    # Auto-resume interrupted workflows (in background, after server starts)
    resume_thread = threading.Thread(target=_wf_auto_resume_on_startup, daemon=True, name="wf-auto-resume")
    resume_thread.start()

    # Keep built-in Archive Room manager profile aligned with the bundled template.
    archive_manager_thread = threading.Thread(target=_archive_manager_profile_check_on_startup, daemon=True, name="archive-manager-profile-check")
    archive_manager_thread.start()
    archive_inspection_thread = threading.Thread(target=_archive_manager_startup_inspection, daemon=True, name="archive-manager-startup-inspection")
    archive_inspection_thread.start()

    feishu_status = _start_feishu_long_connection()
    print(f"📣 Feishu long connection: {feishu_status.get('status')}")

    # Start HTTP server in main thread
    start_http_server()
