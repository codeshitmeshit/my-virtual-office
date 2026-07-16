#!/usr/bin/env python3
"""VO-mediated agent communication routing and history coverage."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-agent-routing-test-"))
os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")

import server


SENDER = {
    "id": "coordinator",
    "statusKey": "coordinator",
    "providerKind": "openclaw",
    "providerAgentId": "coordinator",
    "name": "Coordinator",
    "emoji": "🧭",
}
TARGET = {
    "id": "codex-reviewer",
    "statusKey": "codex-reviewer",
    "providerKind": "codex",
    "providerAgentId": "reviewer",
    "name": "Reviewer",
    "emoji": "⚡",
}


def _patch_routing(monkeypatch, status_dir, provider_result):
    monkeypatch.setattr(server, "STATUS_DIR", status_dir)
    monkeypatch.setattr(server, "get_roster", lambda: [SENDER, TARGET])
    monkeypatch.setattr(server, "_archive_manager_chat_guard", lambda *args: None)
    monkeypatch.setattr(server, "_handle_codex_chat", lambda body: dict(provider_result))
    monkeypatch.setattr(server.gateway_presence, "set_manual_override", lambda *args, **kwargs: None)


def test_sender_and_target_must_resolve_from_current_roster(monkeypatch):
    with tempfile.TemporaryDirectory() as status_dir:
        _patch_routing(monkeypatch, status_dir, {"ok": True, "status": "completed", "reply": "ok"})
        missing_sender = server._handle_agent_platform_comm_send({
            "fromAgentId": "stale-agent",
            "toAgentId": TARGET["id"],
            "message": "review",
        })
        assert missing_sender["ok"] is False
        assert missing_sender["_status"] == 404
        assert server._load_comm_history() == []

        missing_target = server._handle_agent_platform_comm_send({
            "fromAgentId": SENDER["id"],
            "toAgentId": "stale-target",
            "message": "review",
        })
        assert missing_target["ok"] is False
        assert missing_target["_status"] == 404
        assert server._load_comm_history() == []


def test_non_ready_openclaw_sender_is_rejected_before_history_or_provider(monkeypatch):
    with tempfile.TemporaryDirectory() as status_dir:
        provider_calls = []
        non_ready = {
            **SENDER,
            "communicationSkill": {"ready": False, "status": "conflict", "updated": False},
        }
        monkeypatch.setattr(server, "STATUS_DIR", status_dir)
        monkeypatch.setattr(server, "get_roster", lambda: [non_ready, TARGET])
        monkeypatch.setattr(server, "_archive_manager_chat_guard", lambda *args: None)
        monkeypatch.setattr(server, "_handle_codex_chat", lambda body: provider_calls.append(body) or {"ok": True, "reply": "unexpected"})
        result = server._handle_agent_platform_comm_send({
            "fromAgentId": SENDER["id"],
            "toAgentId": TARGET["id"],
            "conversationId": "blocked-conv",
            "message": "review",
        })
        assert result["ok"] is False
        assert result["_status"] == 409
        assert result["code"] == "communication_skill_not_ready"
        assert result["status"] == "conflict"
        assert provider_calls == []
        assert server._load_comm_history(conversation_id="blocked-conv") == []


def test_readiness_gate_preserves_human_and_non_openclaw_senders(monkeypatch):
    with tempfile.TemporaryDirectory() as status_dir:
        claude_sender = {
            "id": "claude-code-local",
            "statusKey": "claude-code-local",
            "providerKind": "claude-code",
            "providerAgentId": "local",
            "name": "Claude Code",
            "communicationSkill": {"ready": False, "status": "not_applicable"},
        }
        monkeypatch.setattr(server, "STATUS_DIR", status_dir)
        monkeypatch.setattr(server, "get_roster", lambda: [claude_sender, TARGET])
        monkeypatch.setattr(server, "_archive_manager_chat_guard", lambda *args: None)
        monkeypatch.setattr(server, "_handle_codex_chat", lambda body: {"ok": True, "status": "completed", "reply": "ok"})
        monkeypatch.setattr(server.gateway_presence, "set_manual_override", lambda *args, **kwargs: None)
        agent_result = server._handle_agent_platform_comm_send({
            "fromAgentId": claude_sender["id"], "toAgentId": TARGET["id"],
            "conversationId": "claude-conv", "message": "review",
        })
        human_result = server._handle_agent_platform_comm_send({
            "fromType": "human", "fromDisplayName": "User", "toAgentId": TARGET["id"],
            "conversationId": "human-conv", "message": "review",
        })
        assert agent_result["ok"] is True
        assert human_result["ok"] is True


def test_success_uses_stable_conversation_and_persists_actual_identities(monkeypatch):
    with tempfile.TemporaryDirectory() as status_dir:
        _patch_routing(monkeypatch, status_dir, {"ok": True, "status": "completed", "reply": "looks good"})
        body = {
            "fromAgentId": SENDER["id"],
            "toAgentId": TARGET["id"],
            "conversationId": "coordinator__reviewer__market",
            "message": "review market direction",
        }
        first = server._handle_agent_platform_comm_send(body)
        second = server._handle_agent_platform_comm_send({**body, "message": "follow up"})
        assert first["ok"] is True and second["ok"] is True
        assert first["conversationId"] == second["conversationId"] == body["conversationId"]
        history = server._handle_agent_platform_comm_history({"conversationId": [body["conversationId"]]})["events"]
        assert [event["direction"] for event in history] == ["request", "reply", "request", "reply"]
        assert history[0]["from"]["id"] == SENDER["id"]
        assert history[0]["to"]["id"] == TARGET["id"]
        assert history[1]["from"]["id"] == TARGET["id"]
        assert history[1]["to"]["id"] == SENDER["id"]


def test_timeout_and_empty_reply_are_terminal_non_success_outcomes(monkeypatch):
    with tempfile.TemporaryDirectory() as status_dir:
        _patch_routing(monkeypatch, status_dir, {"ok": False, "status": "timeout", "error": "timed out"})
        timed_out = server._handle_agent_platform_comm_send({
            "fromAgentId": SENDER["id"], "toAgentId": TARGET["id"],
            "conversationId": "timeout-conv", "message": "review",
        })
        assert timed_out["ok"] is False
        assert timed_out["status"] == "timeout"
        assert len(server._load_comm_history(conversation_id="timeout-conv")) == 2

        monkeypatch.setattr(server, "_handle_codex_chat", lambda body: {"ok": True, "status": "completed", "reply": ""})
        empty = server._handle_agent_platform_comm_send({
            "fromAgentId": SENDER["id"], "toAgentId": TARGET["id"],
            "conversationId": "empty-conv", "message": "review",
        })
        assert empty["ok"] is False
        assert empty["status"] == "empty_reply"
        events = server._load_comm_history(conversation_id="empty-conv")
        assert len(events) == 2 and events[-1]["ok"] is False


def test_canonical_skill_forbids_private_fallback_and_preserves_terminal_statuses():
    content = server._agent_platform_comm_skill_content()
    for forbidden in ("OpenClaw 私有 session", "sessions_send", "私人 CLI", "本地 Codex subagent"):
        assert forbidden in content
    assert "status=busy" in content
    assert "status=timeout" in content
    assert "reply` 为空" in content
    assert "OpenClaw、Hermes、Claude Code、Codex" in content
    assert "vo-codex-communication" not in content
    assert '"toAgentId": "codex-local"' in content
