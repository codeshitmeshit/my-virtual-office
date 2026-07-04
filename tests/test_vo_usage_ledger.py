#!/usr/bin/env python3
"""Regression checks for VO-recorded token usage ledger."""

import os
import sys
import tempfile
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-usage-ledger-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR

import server


def test_normalizes_nested_and_provider_usage_shapes():
    nested = {
        "last": {"inputTokens": 10, "outputTokens": 3, "totalTokens": 13},
        "total": {"inputTokens": 100, "outputTokens": 30, "totalTokens": 130},
    }
    claude = {
        "input_tokens": 7,
        "output_tokens": 5,
        "cache_creation_input_tokens": 2,
        "cache_read_input_tokens": 4,
    }

    assert server._normalize_vo_usage_counters(nested)["totalTokens"] == 13
    assert server._provider_context_used_from_token_usage(nested) == 13
    normalized = server._normalize_vo_usage_counters(claude)
    assert normalized["inputTokens"] == 7
    assert normalized["outputTokens"] == 5
    assert normalized["cacheWriteTokens"] == 2
    assert normalized["cacheReadTokens"] == 4
    assert normalized["totalTokens"] == 18


def test_usage_ledger_records_missing_usage_and_summarizes():
    with tempfile.TemporaryDirectory() as status_dir:
        old_status_dir = server.STATUS_DIR
        server.STATUS_DIR = status_dir
        try:
            agent = {
                "id": "codex-local",
                "name": "Codex Local",
                "providerKind": "codex",
                "provider": "Codex CLI",
                "model": "gpt-test",
                "profile": "local",
            }
            recorded = {
                "ok": True,
                "status": "completed",
                "conversationId": "conv-1",
                "threadId": "thread-1",
                "turnId": "turn-1",
                "runId": "run-1",
                "providerPath": "codex-app-server",
                "tokenUsage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
            }
            missing = {
                "ok": True,
                "status": "completed",
                "conversationId": "conv-2",
                "threadId": "thread-2",
                "turnId": "turn-2",
                "runId": "run-2",
                "providerPath": "codex-app-server",
                "tokenUsage": {},
            }

            first = server._append_vo_usage_record("codex", agent, recorded)
            duplicate = server._append_vo_usage_record("codex", agent, recorded)
            unavailable = server._append_vo_usage_record("codex", agent, missing)
            summary = server._get_vo_usage_summary()

            assert first is not None
            assert duplicate is None
            assert unavailable is not None
            assert unavailable["usageStatus"] == "unavailable"
            assert summary["totals"]["runs"] == 2
            assert summary["totals"]["recordedRuns"] == 1
            assert summary["totals"]["missingRuns"] == 1
            assert summary["totals"]["coveragePct"] == 50.0
            assert summary["totals"]["totalTokens"] == 18
            assert summary["byAgent"][0]["agentId"] == "codex-local"
            assert summary["byModel"][0]["model"] == "gpt-test"
            assert any(item["usageStatus"] == "unavailable" for item in summary["recent"])
            assert os.path.isfile(server._vo_usage_month_path())
        finally:
            server.STATUS_DIR = old_status_dir


def test_usage_ledger_keeps_payloads_out_and_filters_summary():
    with tempfile.TemporaryDirectory() as status_dir:
        old_status_dir = server.STATUS_DIR
        server.STATUS_DIR = status_dir
        try:
            agent = {
                "id": "privacy-agent",
                "name": "Privacy Agent",
                "provider": "Claude Code",
                "model": "claude-test",
                "profile": "local",
            }
            server._append_vo_usage_record("claude-code", agent, {
                "ok": True,
                "status": "completed",
                "conversationId": "privacy-conv",
                "sessionId": "privacy-session",
                "runId": "privacy-run",
                "reply": "SECRET_REPLY_SHOULD_NOT_BE_STORED",
                "prompt": "SECRET_PROMPT_SHOULD_NOT_BE_STORED",
                "toolOutput": "SECRET_TOOL_OUTPUT_SHOULD_NOT_BE_STORED",
                "tokenUsage": {"inputTokens": 20, "outputTokens": 8},
            })
            server._append_vo_usage_record("codex", {
                "id": "other-agent",
                "name": "Other Agent",
                "provider": "Codex CLI",
                "model": "gpt-other",
            }, {
                "ok": True,
                "status": "completed",
                "conversationId": "other-conv",
                "threadId": "other-thread",
                "turnId": "other-turn",
                "runId": "other-run",
                "tokenUsage": {"inputTokens": 1, "outputTokens": 1},
            })

            with open(server._vo_usage_month_path(), "r", encoding="utf-8") as f:
                ledger_text = f.read()
            assert "SECRET_REPLY_SHOULD_NOT_BE_STORED" not in ledger_text
            assert "SECRET_PROMPT_SHOULD_NOT_BE_STORED" not in ledger_text
            assert "SECRET_TOOL_OUTPUT_SHOULD_NOT_BE_STORED" not in ledger_text

            rows = [json.loads(line) for line in ledger_text.splitlines()]
            assert "reply" not in rows[0]
            assert "prompt" not in rows[0]
            assert "toolOutput" not in rows[0]

            by_agent = server._get_vo_usage_summary({"agentId": ["privacy-agent"]})
            assert by_agent["totals"]["runs"] == 1
            assert by_agent["totals"]["totalTokens"] == 28
            assert by_agent["byAgent"][0]["agentId"] == "privacy-agent"

            by_model = server._get_vo_usage_summary({"model": ["gpt-other"]})
            assert by_model["totals"]["runs"] == 1
            assert by_model["totals"]["totalTokens"] == 2
            assert by_model["byModel"][0]["model"] == "gpt-other"
        finally:
            server.STATUS_DIR = old_status_dir


def test_codex_missing_model_uses_codex_default_label():
    with tempfile.TemporaryDirectory() as status_dir:
        old_status_dir = server.STATUS_DIR
        server.STATUS_DIR = status_dir
        try:
            record = server._append_vo_usage_record("codex", {
                "id": "codex-local",
                "name": "Codex",
                "provider": "OpenAI Codex",
            }, {
                "ok": True,
                "status": "completed",
                "conversationId": "codex-default-model",
                "threadId": "codex-thread",
                "turnId": "codex-turn",
                "runId": "codex-run",
                "tokenUsage": {"inputTokens": 9, "outputTokens": 3},
            })
            summary = server._get_vo_usage_summary()

            assert record["model"] == "gpt-5.5"
            assert summary["byModel"][0]["model"] == "gpt-5.5"
            assert summary["recent"][0]["model"] == "gpt-5.5"
        finally:
            server.STATUS_DIR = old_status_dir


def test_claude_code_exception_path_records_unavailable_usage():
    class RaisingClaudeCodeProvider:
        def __init__(self, *args, **kwargs):
            pass

        def send_chat_message(self, *args, **kwargs):
            raise RuntimeError("simulated claude failure")

    with tempfile.TemporaryDirectory() as status_dir:
        old_status_dir = server.STATUS_DIR
        old_provider = server.ClaudeCodeProvider
        old_get_agent = server._get_claude_code_agent
        server.STATUS_DIR = status_dir
        server.ClaudeCodeProvider = RaisingClaudeCodeProvider
        server._get_claude_code_agent = lambda agent_id=None: {
            "id": "claude-code-test",
            "name": "Claude Code Test",
            "providerKind": "claude-code",
            "provider": "Claude Code",
            "profile": "local",
            "model": "claude-test",
            "statusKey": "claude-code-test",
        }
        try:
            result = server._handle_claude_code_chat({
                "agentId": "claude-code-test",
                "message": "hello",
                "conversationId": "exception-conv",
            })
            summary = server._get_vo_usage_summary()

            assert result["ok"] is False
            assert result["_status"] == 500
            assert summary["totals"]["runs"] == 1
            assert summary["totals"]["recordedRuns"] == 0
            assert summary["totals"]["missingRuns"] == 1
            assert summary["recent"][0]["usageStatus"] == "unavailable"
            assert summary["recent"][0]["providerKind"] == "claude-code"
            assert summary["recent"][0]["agentId"] == "claude-code-test"
        finally:
            server.STATUS_DIR = old_status_dir
            server.ClaudeCodeProvider = old_provider
            server._get_claude_code_agent = old_get_agent


if __name__ == "__main__":
    test_normalizes_nested_and_provider_usage_shapes()
    test_usage_ledger_records_missing_usage_and_summarizes()
    test_usage_ledger_keeps_payloads_out_and_filters_summary()
    test_codex_missing_model_uses_codex_default_label()
    test_claude_code_exception_path_records_unavailable_usage()
    print("ok")
