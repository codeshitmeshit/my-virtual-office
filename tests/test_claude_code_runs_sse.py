#!/usr/bin/env python3
"""Claude Code background runs expose SSE progress without changing project flows."""

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "1")
STATUS_DIR = tempfile.mkdtemp(prefix="vo-claude-code-runs-sse-")
os.environ["VO_STATUS_DIR"] = STATUS_DIR

import server


AGENTS = [{
    "id": "claude-code-local",
    "statusKey": "claude-code-local",
    "providerAgentId": "local",
    "profile": "local",
    "providerKind": "claude-code",
    "name": "Claude Local",
}]


def test_claude_code_run_start_publishes_sse_events_and_progress_history():
    old = (server.STATUS_DIR, server.get_roster, server._handle_claude_code_chat)
    server.STATUS_DIR = STATUS_DIR
    server.get_roster = lambda: AGENTS

    def fake_chat(body):
        assert body["_streamRunId"].startswith("claude-code-")
        assert body["_streamProgressId"].startswith("claude-code-progress-")
        body["_onProgress"]({
            "reply": "partial",
            "sessionId": "sess-1",
            "runId": body["_streamRunId"],
            "status": "running",
            "thinking": "thinking",
            "tools": [{"id": "tool-1", "name": "Read", "status": "running", "arguments": {"path": "README.md"}}],
        })
        body["_onProgress"]({
            "reply": "partial done",
            "sessionId": "sess-1",
            "runId": body["_streamRunId"],
            "status": "completed",
            "tools": [{"id": "tool-1", "name": "Read", "status": "done", "result": "ok"}],
        })
        return {
            "ok": True,
            "reply": "final",
            "sessionId": "sess-1",
            "runId": body["_streamRunId"],
            "tools": [{"id": "tool-1", "name": "Read", "status": "done", "result": "ok"}],
            "thinking": "done thinking",
            "tokenUsage": {"input_tokens": 10, "output_tokens": 5},
        }

    server._handle_claude_code_chat = fake_chat
    try:
        started = server._handle_claude_code_run_start({"agentId": "claude-code-local", "message": "hello"})
        assert started["ok"] is True
        run_id = started["runId"]

        meta = None
        deadline = time.time() + 2
        while time.time() < deadline:
            meta = server._get_claude_code_stream_run(run_id)
            if meta and meta.get("done"):
                break
            time.sleep(0.02)
        assert meta and meta["done"] is True

        events = []
        q = meta["events"]
        while not q.empty():
            events.append(q.get_nowait())
        names = [e["event"] for e in events]
        assert "run.started" in names
        assert "message.delta" in names
        assert "tool.started" in names
        assert "tool.completed" in names
        assert names[-1] == "run.completed"

        assert meta["result"]["ok"] is True
        assert meta["result"]["runId"] == run_id
        history = server._load_claude_code_history("local", "")
        assert not [msg for msg in history if msg.get("ephemeral") == "claude-code-progress"]
    finally:
        server.STATUS_DIR, server.get_roster, server._handle_claude_code_chat = old


def test_claude_code_progress_history_is_recoverable_while_run_active():
    old = (server.STATUS_DIR, server.get_roster)
    server.STATUS_DIR = tempfile.mkdtemp(prefix="vo-claude-code-progress-active-")
    server.get_roster = lambda: AGENTS
    try:
        progress_id = "claude-code-progress-run-1"
        server._publish_claude_code_progress("local", "claude-code-local", progress_id, {
            "runId": "run-1",
            "sessionId": "sess-1",
            "status": "running",
            "reply": "partial",
            "thinking": "thinking",
            "tools": [{"id": "tool-1", "name": "Read", "status": "running"}],
        }, "conv-progress")
        history = server._load_claude_code_history("local", "conv-progress")
        assert len(history) == 1
        progress = history[0]
        assert progress["ephemeral"] == "claude-code-progress"
        assert progress["progressId"] == progress_id
        assert progress["status"] == "running"
        assert progress["text"] == "partial"
        assert progress["thinking"] == "thinking"
        assert progress["tools"][0]["name"] == "Read"
    finally:
        server.STATUS_DIR, server.get_roster = old


if __name__ == "__main__":
    test_claude_code_run_start_publishes_sse_events_and_progress_history()
    test_claude_code_progress_history_is_recoverable_while_run_active()
    print("test_claude_code_runs_sse.py passed")
