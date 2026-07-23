from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-project-provider-history-"))
os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")

import server


def test_claude_workflow_uses_attempt_scoped_claude_history_not_openclaw():
    originals = {
        "is_hermes": server._is_hermes_agent,
        "is_codex": server._is_codex_agent,
        "is_claude": server._is_claude_code_agent,
        "get_claude": server._get_claude_code_agent,
        "load_claude": server._load_claude_code_history,
        "session_key": server._wf_task_session_key,
    }
    calls = []
    try:
        server._is_hermes_agent = lambda agent: False
        server._is_codex_agent = lambda agent: False
        server._is_claude_code_agent = lambda agent: agent == "claude-agent"
        server._get_claude_code_agent = lambda agent: {"id": agent, "profile": "claude-profile"}
        server._load_claude_code_history = lambda profile, conversation: calls.append((profile, conversation)) or [{
            "id": "claude-message", "role": "assistant", "text": "answer", "thinking": "analysis",
            "tools": [{"id": "tool", "status": "done"}], "error": "warning", "conversationId": conversation,
            "status": "completed", "source": "claude-code-history",
        }]
        server._wf_task_session_key = lambda *args: (_ for _ in ()).throw(AssertionError("OpenClaw lookup must not run"))
        messages = server._wf_get_task_session_messages(
            "claude-agent", "project", "attempt-claude", conversation_id="attempt-claude"
        )
        assert calls == [("claude-profile", "attempt-claude")]
        assert messages[0]["conversationId"] == "attempt-claude"
        assert messages[0]["tools"] == [{"id": "tool", "status": "done"}]
        assert messages[0]["error"] == "warning"
        assert messages[0]["status"] == "completed"
        assert messages[0]["source"] == "claude-code-history"
    finally:
        server._is_hermes_agent = originals["is_hermes"]
        server._is_codex_agent = originals["is_codex"]
        server._is_claude_code_agent = originals["is_claude"]
        server._get_claude_code_agent = originals["get_claude"]
        server._load_claude_code_history = originals["load_claude"]
        server._wf_task_session_key = originals["session_key"]


def test_completed_hermes_reasoning_is_terminal_and_attempt_isolated():
    originals = {
        "is_hermes": server._is_hermes_agent,
        "get_hermes": server._get_hermes_agent,
        "load_hermes": server._load_hermes_history,
    }
    calls = []
    try:
        server._is_hermes_agent = lambda agent: agent == "hermes-agent"
        server._get_hermes_agent = lambda agent: {"id": agent, "profile": "hermes-profile"}
        server._load_hermes_history = lambda profile, conversation: calls.append((profile, conversation)) or [{
            "id": "hermes-message", "role": "assistant", "text": "answer", "thinking": "finished reasoning",
            "conversationId": conversation, "error": "warning",
        }]
        messages = server._wf_get_task_session_messages(
            "hermes-agent", "project", "task", conversation_id="attempt-hermes"
        )
        assert calls == [("hermes-profile", "attempt-hermes")]
        assert messages[0]["reasoningStatus"] == "done"
        assert "status" not in messages[0]
        assert messages[0]["conversationId"] == "attempt-hermes"
        assert messages[0]["error"] == "warning"
    finally:
        server._is_hermes_agent = originals["is_hermes"]
        server._get_hermes_agent = originals["get_hermes"]
        server._load_hermes_history = originals["load_hermes"]
