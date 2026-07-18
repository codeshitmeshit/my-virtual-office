import os
import sys
import tempfile
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

os.environ.setdefault("VO_CODEX_INCLUDE_NATIVE_AGENTS", "0")
os.environ.setdefault("VO_CLAUDE_CODE_INCLUDE_NATIVE_AGENTS", "0")
_IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-chat-command-api-import-")
os.environ["VO_STATUS_DIR"] = _IMPORT_STATUS_DIR
os.environ["VO_CONFIG"] = str(Path(_IMPORT_STATUS_DIR) / "vo-config.json")
import server


ROSTER = [
    {"id": "codex-local", "statusKey": "codex-local", "providerKind": "codex", "profile": "local"},
    {"id": "hermes-default", "statusKey": "hermes-default", "providerKind": "hermes", "profile": "default"},
    {"id": "adam", "statusKey": "adam", "providerKind": "openclaw", "profile": "adam"},
]


def configure(monkeypatch):
    status_dir = tempfile.mkdtemp(prefix="vo-chat-command-api-")
    monkeypatch.setattr(server, "STATUS_DIR", status_dir)
    monkeypatch.setattr(server, "get_roster", lambda: ROSTER)
    monkeypatch.setenv("VO_CHAT_SLASH_COMMANDS_ENABLED", "1")
    monkeypatch.setenv("VO_FEISHU_CHAT_SLASH_COMMANDS_ENABLED", "1")
    return status_dir


def test_vo_new_resolves_agent_and_reuses_durable_idempotent_result(monkeypatch):
    configure(monkeypatch)
    body = {"agentId": "codex-local", "conversationId": "old", "command": "/new", "idempotencyKey": "idem-new"}
    first = server._handle_chat_command_execute(body)
    duplicate = server._handle_chat_command_execute(body)
    assert first["ok"] is True and first["nextConversationId"].startswith("vo-")
    assert duplicate["ok"] is True and duplicate["duplicate"] is True
    assert duplicate["nextConversationId"] == first["nextConversationId"]


def test_provider_spoof_and_cross_agent_openclaw_session_are_rejected(monkeypatch):
    configure(monkeypatch)
    spoof = server._handle_chat_command_execute({
        "agentId": "codex-local", "providerKind": "hermes", "conversationId": "c",
        "command": "/new", "idempotencyKey": "spoof",
    })
    cross_agent = server._handle_chat_command_execute({
        "agentId": "adam", "sessionKey": "agent:other:main", "command": "/new", "idempotencyKey": "cross",
    })
    assert spoof["status"] == "invalid_scope" and spoof["_status"] == 400
    assert cross_agent["status"] == "invalid_scope" and cross_agent["_status"] == 400


def test_validation_flags_and_provider_capability_statuses(monkeypatch):
    configure(monkeypatch)
    missing_idempotency = server._handle_chat_command_execute({
        "agentId": "codex-local", "conversationId": "c", "command": "/new"
    })
    unsupported = server._handle_chat_command_execute({
        "agentId": "hermes-default", "conversationId": "c", "command": "/compact", "idempotencyKey": "compact"
    })
    monkeypatch.setenv("VO_CHAT_SLASH_COMMANDS_ENABLED", "0")
    disabled = server._handle_chat_command_execute({
        "agentId": "codex-local", "conversationId": "c", "command": "/new", "idempotencyKey": "disabled"
    })
    assert missing_idempotency["_status"] == 400
    assert unsupported["status"] == "unsupported" and unsupported["_status"] == 501
    assert disabled["status"] == "disabled" and disabled["_status"] == 404


def test_management_auth_requires_exact_process_token():
    handler = object.__new__(server.OfficeHandler)
    handler.headers = {"X-VO-Management-Token": server._MANAGEMENT_TOKEN}
    assert handler._management_request_allowed() is True
    handler.headers = {"X-VO-Management-Token": "wrong"}
    assert handler._management_request_allowed() is False


def test_command_route_is_inside_management_auth_branch():
    source = (APP / "server.py").read_text(encoding="utf-8")
    route = source.index('"/api/chat/commands/execute"')
    branch = source.rfind("if request_path in", 0, route)
    rejection = source.index("self._reject_untrusted_management_request()", branch)
    dispatch = source.index("_handle_chat_command_execute(body)", route)
    assert branch < route < rejection < dispatch
