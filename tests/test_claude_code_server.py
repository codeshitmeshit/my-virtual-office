#!/usr/bin/env python3
"""Server-side tests for Claude Code provider chat/history integration."""

import os
import sys
import tempfile
import time
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

STATUS_DIR = tempfile.mkdtemp(prefix="vo-claude-code-server-test-")
os.environ["VO_STATUS_DIR"] = STATUS_DIR
os.environ["VO_HERMES_ENABLED"] = "0"
os.environ["VO_CODEX_ENABLED"] = "0"
os.environ["VO_CLAUDE_CODE_ENABLED"] = "1"
os.environ["VO_CLAUDE_CODE_REPLY_TEXT"] = "ack from claude server"

import server

os.environ.pop("VO_CLAUDE_CODE_REPLY_TEXT", None)


@pytest.fixture(autouse=True)
def claude_code_reply_text_config():
    old_config = server.VO_CONFIG
    server.VO_CONFIG = {
        **server.VO_CONFIG,
        "claudeCode": {
            **(server.VO_CONFIG.get("claudeCode") or {}),
            "enabled": True,
            "replyText": "ack from claude server",
        },
    }
    try:
        yield
    finally:
        server.VO_CONFIG = old_config


AGENT = {
    "id": "claude-code-local",
    "statusKey": "claude-code-local",
    "providerAgentId": "local",
    "providerKind": "claude-code",
    "name": "Claude Code",
    "profile": "local",
}


def test_claude_code_chat_saves_isolated_history():
    old_roster = server.get_roster
    server.get_roster = lambda: [AGENT]
    try:
        result = server._handle_claude_code_chat({
            "agentId": "claude-code-local",
            "message": "hello",
            "conversationId": "conv-a",
        })
        assert result["ok"] is True
        assert result["reply"] == "ack from claude server"
        assert result["sessionId"] == "demo-conv-a"

        history_a = server._load_claude_code_history("local", "conv-a")
        history_b = server._load_claude_code_history("local", "conv-b")
        assert [m["role"] for m in history_a] == ["user", "assistant"]
        assert history_a[-1]["text"] == "ack from claude server"
        assert history_b == []
    finally:
        server.get_roster = old_roster


def test_review_claude_code_chat_forces_plan_permission_mode():
    old_roster = server.get_roster
    old_provider = server.ClaudeCodeProvider
    captured = {}

    class ReviewProvider:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def send_chat_message(self, *args, **kwargs):
            return {
                "ok": True, "status": "completed", "reply": "reviewed",
                "sessionId": "review-session", "runId": "review-session",
            }

    server.get_roster = lambda: [AGENT]
    server.ClaudeCodeProvider = ReviewProvider
    try:
        result = server._handle_claude_code_chat({
            "agentId": "claude-code-local",
            "message": "read-only review",
            "conversationId": "conv-review-read-only",
            "_reviewReadOnly": True,
        })
        assert result["ok"] is True
        assert captured["permission_mode"] == "plan"
    finally:
        server.get_roster = old_roster
        server.ClaudeCodeProvider = old_provider


def test_claude_code_history_endpoint_source_is_conversation_scoped():
    server._save_claude_code_history("local", [
        {"role": "user", "text": "conv-a only", "ts": 1000, "agentId": "claude-code-local"},
    ], "conv-a", "session-a")
    server._save_claude_code_history("local", [
        {"role": "user", "text": "conv-b only", "ts": 2000, "agentId": "claude-code-local"},
    ], "conv-b", "session-b")

    messages = server._filter_recoverable_provider_progress_messages(
        server._sanitize_claude_code_history_messages(server._load_claude_code_history("local", "conv-b"))
    )
    assert [m.get("text") for m in messages] == ["conv-b only"]
    assert server._get_claude_code_session_id("local", "conv-b") == "session-b"


def test_claude_code_history_clear_is_conversation_scoped():
    server._save_claude_code_history("local", [{"role": "user", "text": "a"}], "conv-a", "session-a")
    server._save_claude_code_history("local", [{"role": "user", "text": "b"}], "conv-b", "session-b")

    old_roster = server.get_roster
    server.get_roster = lambda: [AGENT]
    try:
        result = server._handle_claude_code_history_clear({"agentId": "claude-code-local", "conversationId": "conv-a"})
    finally:
        server.get_roster = old_roster

    assert result["ok"] is True
    assert result["sessionId"] == "session-a"
    assert result["conversationId"] == "conv-a"
    assert server._load_claude_code_history("local", "conv-a") == []
    assert server._get_claude_code_session_id("local", "conv-a") == ""
    assert server._load_claude_code_history("local", "conv-b") == [{"role": "user", "text": "b"}]
    assert server._get_claude_code_session_id("local", "conv-b") == "session-b"


def test_claude_code_run_start_idempotency_reuses_existing_run():
    old_roster = server.get_roster
    server.get_roster = lambda: [AGENT]
    server.STATUS_DIR = tempfile.mkdtemp(prefix="vo-claude-code-run-idempotency-")
    try:
        body = {
            "agentId": "claude-code-local",
            "message": "hello idem",
            "conversationId": "conv-claude-idem",
            "idempotencyKey": "same-click",
        }
        first = server._handle_claude_code_run_start(body)
        second = server._handle_claude_code_run_start(body)
        assert first["ok"] is True
        assert second["ok"] is True
        assert second["status"] == "duplicate"
        assert second["runId"] == first["runId"]

        deadline = time.time() + 2
        while time.time() < deadline:
            meta = server.PROVIDER_RUN_REPOSITORY.get(first["runId"])
            if meta and meta.get("done"):
                break
            time.sleep(0.02)
        history = server._load_claude_code_history("local", "conv-claude-idem")
        assert len([msg for msg in history if msg.get("role") == "user" and msg.get("text") == "hello idem"]) == 1
    finally:
        server.get_roster = old_roster


def test_claude_code_conversation_history_feeds_map_bubbles():
    server._save_claude_code_history("local", [
        {"role": "user", "text": "hello map", "ts": 1000, "agentId": "claude-code-local"},
        {"role": "assistant", "text": "map bubble reply", "ts": 2000, "agentId": "claude-code-local", "thinking": "Claude Code completed."},
    ], "map-bubble-conv", "session-map")

    messages = server._load_provider_histories_for_bubbles("claude-code", "local", 20)
    texts = [m.get("text") for m in messages]
    assert "hello map" in texts
    assert "map bubble reply" in texts
    assert any(m.get("conversationId") == "map-bubble-conv" for m in messages)
    assert not [m for m in messages if m.get("thinking") == "Claude Code completed."]
    assert server._claude_code_visible_thinking({"status": "completed", "thinking": "Claude Code completed."}) == ""
    assert server._claude_code_visible_thinking({"status": "running", "thinking": "reading files"}) == "reading files"


def test_project_execution_dispatches_to_claude_code_executor():
    old_roster = server.get_roster
    server.get_roster = lambda: [AGENT]
    try:
        result = server._project_execution_call_executor(
            {"id": "claude-code-local", "providerKind": "claude-code"},
            "implement this",
            tempfile.gettempdir(),
            "attempt-1",
            timeout=5,
        )
        assert result["ok"] is True
        assert result["reply"] == "ack from claude server"
        assert result["conversationId"] == "attempt-1"
    finally:
        server.get_roster = old_roster


def test_meeting_dispatches_to_claude_code_provider():
    old_roster = server.get_roster
    server.get_roster = lambda: [AGENT]
    try:
        result = server._meeting_call_provider(
            {"id": "mtg-claude"},
            "claude-code-local",
            "please contribute",
        )
        assert result["ok"] is True
        assert result["reply"] == "ack from claude server"
        assert result["conversationId"] == "meeting:mtg-claude:participant:claude-code-local"
        assert result["providerRef"]["providerKind"] == "claude-code"
        assert result["providerRef"]["sessionId"] == "demo-meeting-mtg-claude-participant-claude-code-local"
    finally:
        server.get_roster = old_roster


def test_claude_code_platform_session_and_safe_config_metadata():
    old_roster = server.get_roster
    old_hermes = server._handle_hermes_test
    old_codex = server._handle_codex_test
    old_claude = server._handle_claude_code_test
    server.get_roster = lambda: [{**AGENT, "model": "sonnet", "provider": "Anthropic Claude Code"}]
    server._handle_hermes_test = lambda body=None: {"ok": False, "error": "disabled"}
    server._handle_codex_test = lambda: {"ok": False, "error": "disabled"}
    server._handle_claude_code_test = lambda body=None: {"ok": True, "agents": [AGENT]}
    try:
        platforms = server._handle_agent_platforms()
        claude_platform = next(p for p in platforms["platforms"] if p["id"] == "claude-code")
        assert claude_platform["available"] is True
        assert claude_platform["create"] is True
        assert claude_platform["delete"] is True

        session_info = server.OfficeHandler._get_session_info(None, "claude-code-local")
        assert session_info["providerKind"] == "claude-code"
        assert session_info["model"] == "sonnet"
        assert session_info["provider"] == "Anthropic Claude Code"

        agent = server.get_roster()[0]
        session_key = f"claude-code:{agent.get('profile') or agent.get('providerAgentId') or agent['id']}"
        assert session_key == "claude-code:local"
    finally:
        server.get_roster = old_roster
        server._handle_hermes_test = old_hermes
        server._handle_codex_test = old_codex
        server._handle_claude_code_test = old_claude


def test_claude_code_agent_create_delete_handlers_use_native_provider():
    old_config = server.VO_CONFIG
    old_roster = server.get_roster
    old_refresh = server.refresh_agent_maps
    with tempfile.TemporaryDirectory() as tmp:
        server.VO_CONFIG = {
            **server.VO_CONFIG,
            "claudeCode": {
                "enabled": True,
                "homePath": os.path.join(tmp, "home"),
                "binary": "claude",
                "workspace": os.path.join(tmp, "legacy"),
                "workspaceRoot": os.path.join(tmp, "agents"),
                "mainWorkspace": os.path.join(tmp, "main"),
                "name": "Claude Code",
                "agentId": "local",
                "model": "sonnet",
                "replyText": "ok",
                "timeoutSec": 900,
                "includeMain": True,
                "includeNativeAgents": True,
                "registerNativeAgents": True,
            },
        }
        server.refresh_agent_maps = lambda: None
        try:
            created = server._handle_agent_create({
                "agentPlatform": "claude-code",
                "name": "Review Bot",
                "id": "review-bot",
                "role": "Reviewer",
            })
            assert created["ok"] is True
            assert created["providerKind"] == "claude-code"
            assert os.path.isdir(created["workspace"])

            server.get_roster = lambda: [{
                "id": "claude-code-review-bot",
                "statusKey": "claude-code-review-bot",
                "providerKind": "claude-code",
                "providerAgentId": "review-bot",
                "profile": "review-bot",
                "name": "Review Bot",
            }]
            deleted = server._handle_agent_delete({"id": "claude-code-review-bot"})
            assert deleted["ok"] is True
            assert not os.path.exists(created["workspace"])
        finally:
            server.VO_CONFIG = old_config
            server.get_roster = old_roster
            server.refresh_agent_maps = old_refresh


if __name__ == "__main__":
    test_claude_code_chat_saves_isolated_history()
    test_claude_code_history_endpoint_source_is_conversation_scoped()
    test_claude_code_history_clear_is_conversation_scoped()
    test_claude_code_run_start_idempotency_reuses_existing_run()
    test_claude_code_conversation_history_feeds_map_bubbles()
    test_project_execution_dispatches_to_claude_code_executor()
    test_meeting_dispatches_to_claude_code_provider()
    test_claude_code_platform_session_and_safe_config_metadata()
    test_claude_code_agent_create_delete_handlers_use_native_provider()
    print("ok")
