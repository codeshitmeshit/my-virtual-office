"""OpenClaw stays a queued conversation capability, not a synthetic run path."""

from pathlib import Path
import importlib.util
import os
import sys
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))


@pytest.fixture(scope="module")
def server_module():
    state_root = tempfile.mkdtemp(prefix="vo-openclaw-conversation-")
    previous = {key: os.environ.get(key) for key in (
        "VO_STATUS_DIR", "VO_CONFIG", "VO_OPENCLAW_PATH", "VO_CODEX_INCLUDE_NATIVE_AGENTS", "VO_CLAUDE_CODE_INCLUDE_NATIVE_AGENTS"
    )}
    os.environ.update({
        "VO_STATUS_DIR": state_root,
        "VO_CONFIG": str(Path(state_root) / "vo-config.json"),
        "VO_OPENCLAW_PATH": str(Path(state_root) / "openclaw"),
        "VO_CODEX_INCLUDE_NATIVE_AGENTS": "0",
        "VO_CLAUDE_CODE_INCLUDE_NATIVE_AGENTS": "0",
    })
    spec = importlib.util.spec_from_file_location("vo_server_openclaw_conversation_test", APP / "server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_representative_delivery_uses_isolated_gateway_conversation_without_run(monkeypatch, server_module):
    server = server_module
    calls = []
    monkeypatch.setattr(server, "_find_agent_record", lambda agent_id: {
        "id": agent_id,
        "name": "Adam",
        "providerKind": "openclaw",
        "profile": "adam",
    })
    monkeypatch.setattr(
        server,
        "_wf_call_agent",
        lambda agent_id, message, timeout=600, project_id=None, task_id=None, session_key=None: calls.append(
            (agent_id, message, session_key)
        ) or "queued reply",
    )
    outcome = server._dispatch_representative_agent_message(
        "adam",
        "hello",
        "feishu-dm:conversation-a",
        {"senderName": "User", "attachments": []},
    )
    first_session = calls[-1][2]
    server._dispatch_representative_agent_message(
        "adam",
        "again",
        "feishu-dm:conversation-a",
        {"senderName": "User", "attachments": []},
    )
    server._dispatch_representative_agent_message(
        "adam",
        "other",
        "feishu-dm:conversation-b",
        {"senderName": "User", "attachments": []},
    )
    assert outcome["ok"] is True and outcome["reply"] == "queued reply"
    assert first_session.startswith("agent:adam:conversation-")
    assert calls[1][2] == first_session
    assert calls[2][2] != first_session
    assert server.PROVIDER_CONVERSATION_SERVICE.diagnostics()["scopedConversations"] >= 0


def test_openclaw_delivery_preserves_http_ws_cli_fallback_and_explicit_session(monkeypatch, server_module):
    server = server_module
    calls = []
    monkeypatch.setattr(server, "_is_hermes_agent", lambda _agent: False)
    monkeypatch.setattr(server, "_is_codex_agent", lambda _agent: False)
    monkeypatch.setattr(server, "_wf_call_agent_http", lambda agent, message, timeout, session_key=None: calls.append(("http", session_key)) or "[ERROR] Gateway returned HTTP 500")
    monkeypatch.setattr(server, "_wf_call_agent_ws", lambda agent, message, timeout, session_key=None: calls.append(("ws", session_key)) or None)
    monkeypatch.setattr(server, "_wf_call_agent_cli", lambda agent, message, timeout, session_key=None: calls.append(("cli", session_key)) or "done")
    reply = server._wf_call_agent("adam", "hello", session_key="agent:adam:conversation-a")
    assert reply == "done"
    assert calls == [
        ("http", "agent:adam:conversation-a"),
        ("ws", "agent:adam:conversation-a"),
        ("cli", "agent:adam:conversation-a"),
    ]


def test_project_task_session_behavior_is_unchanged(monkeypatch, server_module):
    server = server_module
    calls = []
    monkeypatch.setattr(server, "_is_hermes_agent", lambda _agent: False)
    monkeypatch.setattr(server, "_is_codex_agent", lambda _agent: False)
    monkeypatch.setattr(server, "_wf_call_agent_http", lambda agent, message, timeout, session_key=None: calls.append(session_key) or "ok")
    expected = server._wf_task_session_key("adam", "project-1", "task-1")
    assert server._wf_call_agent("adam", "work", project_id="project-1", task_id="task-1") == "ok"
    assert calls == [expected]


def test_conversation_service_has_no_gateway_auth_or_sse_dependency():
    source = (APP / "services" / "provider_conversations.py").read_text(encoding="utf-8")
    assert "_get_gateway_token" not in source
    assert "sessions.reset" not in source
    assert "ProviderRunCoordinator" not in source
    assert "SSE" not in source
