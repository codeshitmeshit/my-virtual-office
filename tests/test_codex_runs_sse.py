#!/usr/bin/env python3
"""Codex background runs use the shared repository/journal while preserving activity polling."""

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

STATUS_DIR = tempfile.mkdtemp(prefix="vo-codex-runs-sse-")
os.environ["VO_STATUS_DIR"] = STATUS_DIR
os.environ["VO_HERMES_ENABLED"] = "0"
os.environ["VO_CODEX_ENABLED"] = "0"

import server


AGENTS = [{
    "id": "codex-local",
    "statusKey": "codex-local",
    "providerAgentId": "local",
    "profile": "local",
    "providerKind": "codex",
    "name": "Codex Local",
}]


class FakeCodexProvider:
    def __init__(self, workspace):
        self.workspace = workspace
        self.calls = 0

    def send_message(self, message, conversation_id="", timeout_sec=None, thread_id="", event_callback=None, allow_interaction=False):
        self.calls += 1
        assert message == "hello"
        assert conversation_id == "conv-run"
        assert callable(event_callback)
        event_callback({
            "id": "tool-1",
            "sequence": 1,
            "type": "activity",
            "status": "running",
            "threadId": thread_id or "thr-run",
            "turnId": "turn-run",
            "name": "commandExecution",
            "ts": 1,
        })
        event_callback({
            "id": "approval-1",
            "sequence": 2,
            "type": "interaction",
            "status": "pending",
            "threadId": thread_id or "thr-run",
            "turnId": "turn-run",
            "operationId": "op-1",
            "interactionId": "int-1",
            "ts": 2,
        })
        event_callback({
            "id": "turn-completed-1",
            "sequence": 3,
            "type": "turn",
            "status": "completed",
            "threadId": thread_id or "thr-run",
            "turnId": "turn-run",
            "output": {"reply": "done", "modifiedFiles": []},
            "ts": 3,
        })
        return {
            "ok": True,
            "status": "completed",
            "reply": "done",
            "threadId": thread_id or "thr-run",
            "turnId": "turn-run",
            "modifiedFiles": [],
        }

    def cancel(self, thread_id):
        return True


def test_codex_run_start_publishes_bridge_events_and_keeps_activity():
    old = (server.STATUS_DIR, server.get_roster, server._codex_provider_from_config)
    server.STATUS_DIR = STATUS_DIR
    server.get_roster = lambda: AGENTS
    with tempfile.TemporaryDirectory() as workspace:
        server._codex_provider_from_config = lambda: FakeCodexProvider(workspace)
        try:
            started = server._handle_codex_run_start({
                "agentId": "codex-local",
                "message": "hello",
                "conversationId": "conv-run",
            })
            assert started["ok"] is True
            run_id = started["runId"]

            meta = None
            deadline = time.time() + 2
            while time.time() < deadline:
                meta = server.PROVIDER_RUN_REPOSITORY.get(run_id)
                if meta and meta.get("done"):
                    break
                time.sleep(0.02)
            assert meta and meta["done"] is True

            events = server.PROVIDER_EVENT_JOURNAL.run_events_after(run_id, 0)
            names = [event["event"] for event in events]
            assert "run.started" in names
            assert "tool.started" in names
            assert "approval.request" in names
            assert names[-1] == "run.completed"
            assert names.count("run.completed") == 1
            assert meta["result"]["ok"] is True

            activity = server._handle_codex_activity({
                "agentId": ["codex-local"],
                "conversationId": ["conv-run"],
            })
            assert activity["ok"] is True
            assert [event["sequence"] for event in activity["events"]] == [1, 2, 3]
            assert activity["events"][1]["type"] == "interaction"
            assert activity["events"][2]["type"] == "turn"

            history = server._load_comm_history(limit=20, conversation_id="conv-run", agent_id="codex-local")
            texts = [event.get("text") for event in history]
            assert "hello" in texts
            assert "done" in texts
            progress_events = [event for event in history if (event.get("metadata") or {}).get("ephemeral") == "codex-progress"]
            assert not progress_events
            user_event = next(event for event in history if event.get("text") == "hello")
            reply_event = next(event for event in history if event.get("text") == "done")
            assert user_event["from"]["id"] == "user"
            assert reply_event["from"]["id"] == "codex-local"
            assert reply_event["inReplyTo"] == user_event["id"]
            assert len([event for event in history if event.get("text") == "done"]) == 1
        finally:
            server.STATUS_DIR, server.get_roster, server._codex_provider_from_config = old


def test_codex_progress_history_is_recoverable_while_run_active_and_upserts():
    old = (server.STATUS_DIR, server.get_roster)
    server.STATUS_DIR = tempfile.mkdtemp(prefix="vo-codex-progress-active-")
    server.get_roster = lambda: AGENTS
    try:
        progress_id = "codex-progress-run-1"
        server._append_codex_progress_comm_event(AGENTS[0], "codex-local", "conv-progress", progress_id, {
            "runId": "run-1",
            "threadId": "thr-1",
            "turnId": "turn-1",
            "status": "running",
            "thinking": "completed",
        })
        server._append_codex_progress_comm_event(AGENTS[0], "codex-local", "conv-progress", progress_id, {
            "runId": "run-1",
            "threadId": "thr-1",
            "turnId": "turn-1",
            "status": "running",
            "reply": "partial",
            "thinking": "thinking",
            "tools": [{"id": "tool-1", "name": "Read", "status": "running"}],
        })
        history = server._load_comm_history(limit=20, conversation_id="conv-progress", agent_id="codex-local")
        progress_events = [event for event in history if (event.get("metadata") or {}).get("ephemeral") == "codex-progress"]
        assert len(progress_events) == 1
        progress = progress_events[0]["metadata"]["progress"]
        assert progress["progressId"] == progress_id
        assert progress["status"] == "running"
        assert progress["text"] == "partial"
        assert progress["thinking"] == "thinking"
        assert progress["tools"][0]["name"] == "Read"
        assert server._provider_visible_thinking("codex", {"status": "completed", "thinking": "Codex run 已完成"}) == ""
        assert server._provider_visible_thinking("codex", {"status": "running", "thinking": "reading files"}) == "reading files"

        server._remove_comm_progress_events("codex-progress", progress_id, "conv-progress")
        history = server._load_comm_history(limit=20, conversation_id="conv-progress", agent_id="codex-local")
        assert not [event for event in history if (event.get("metadata") or {}).get("ephemeral") == "codex-progress"]
    finally:
        server.STATUS_DIR, server.get_roster = old


def test_provider_progress_filters_stale_and_terminal_entries():
    now_ms = int(time.time() * 1000)
    fresh = {"ephemeral": "claude-code-progress", "progressId": "fresh", "status": "running", "ts": now_ms}
    stale = {"ephemeral": "claude-code-progress", "progressId": "stale", "status": "running", "ts": now_ms - server.PROVIDER_PROGRESS_MAX_AGE_MS - 1000}
    terminal = {"ephemeral": "hermes-progress", "progressId": "done", "status": "completed", "ts": now_ms}
    active_stale = {
        "ephemeral": "codex-progress",
        "progressId": "active-stale",
        "status": "running",
        "ts": now_ms - server.PROVIDER_PROGRESS_MAX_AGE_MS - 1000,
        "active": True,
    }
    normal = {"role": "assistant", "text": "final", "ts": now_ms}

    messages = server._filter_recoverable_provider_progress_messages([fresh, stale, terminal, active_stale, normal])
    assert messages == [fresh, active_stale, normal]

    events = server._filter_recoverable_comm_progress_events([
        {"id": "fresh-event", "metadata": {"ephemeral": "codex-progress", "progress": fresh}},
        {"id": "stale-event", "metadata": {"ephemeral": "codex-progress", "progress": stale}},
        {"id": "terminal-event", "metadata": {"ephemeral": "codex-progress", "progress": terminal}},
        {"id": "active-stale-event", "metadata": {"ephemeral": "codex-progress", "progress": active_stale}},
        {"id": "normal-event", "text": "done"},
    ])
    assert [event["id"] for event in events] == ["fresh-event", "active-stale-event", "normal-event"]


def test_codex_run_start_idempotency_reuses_existing_run():
    old = (server.STATUS_DIR, server.get_roster, server._codex_provider_from_config)
    server.STATUS_DIR = tempfile.mkdtemp(prefix="vo-codex-run-idempotency-")
    server.get_roster = lambda: AGENTS
    with tempfile.TemporaryDirectory() as workspace:
        provider = FakeCodexProvider(workspace)
        server._codex_provider_from_config = lambda: provider
        try:
            body = {
                "agentId": "codex-local",
                "message": "hello",
                "conversationId": "conv-run",
                "idempotencyKey": "same-click",
            }
            first = server._handle_codex_run_start(body)
            second = server._handle_codex_run_start(body)
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
            assert provider.calls == 1
            history = server._load_comm_history(limit=20, conversation_id="conv-run", agent_id="codex-local")
            assert len([event for event in history if event.get("direction") == "request" and event.get("text") == "hello"]) == 1
        finally:
            server.STATUS_DIR, server.get_roster, server._codex_provider_from_config = old


def test_visible_comm_history_keeps_distinct_same_text_requests():
    first = {
        "id": "req-1",
        "direction": "request",
        "conversationId": "conv",
        "from": {"id": "user"},
        "to": {"id": "codex-local"},
        "text": "你好",
    }
    second = {**first, "id": "req-2"}
    deduped = server._dedupe_visible_comm_history([first, second, first])
    assert [event["id"] for event in deduped] == ["req-1", "req-2"]


def test_codex_run_stop_uses_existing_cancel_and_emits_terminal_event():
    old = (server.STATUS_DIR, server.get_roster, server._codex_provider_from_config)
    server.STATUS_DIR = STATUS_DIR
    server.get_roster = lambda: AGENTS
    with tempfile.TemporaryDirectory() as workspace:
        provider = FakeCodexProvider(workspace)
        server._codex_provider_from_config = lambda: provider
        run_id = "codex-test-stop"
        server.PROVIDER_RUN_REPOSITORY.reserve_start(
            provider_kind="codex", agent_id="codex-local", conversation_id="conv-stop", run_id=run_id, meta={
            "agentKey": "codex-local",
            "profile": "local",
            "done": False,
        })
        with server._CODEX_ACTIVE_LOCK:
            server._CODEX_ACTIVE_OPERATIONS["codex-local"] = {
                "agentId": "codex-local",
                "conversationId": "conv-stop",
                "threadId": "thr-stop",
                "status": "running",
            }
        try:
            before_event_id = server.PROVIDER_EVENT_JOURNAL.next_event_id
            result = server._handle_codex_run_stop({"runId": run_id})
            assert result["ok"] is True
            meta = server.PROVIDER_RUN_REPOSITORY.get(run_id)
            assert meta["done"] is True
            events = server.PROVIDER_EVENT_JOURNAL.run_events_after(run_id, before_event_id)
            assert len(events) == 1
            event = events[0]
            assert event["event"] == "run.cancelled"
        finally:
            with server._CODEX_ACTIVE_LOCK:
                server._CODEX_ACTIVE_OPERATIONS.pop("codex-local", None)
            server.PROVIDER_RUN_REPOSITORY.clear(run_id)
            server.STATUS_DIR, server.get_roster, server._codex_provider_from_config = old


if __name__ == "__main__":
    test_codex_run_start_publishes_bridge_events_and_keeps_activity()
    test_codex_progress_history_is_recoverable_while_run_active_and_upserts()
    test_provider_progress_filters_stale_and_terminal_entries()
    test_codex_run_start_idempotency_reuses_existing_run()
    test_visible_comm_history_keeps_distinct_same_text_requests()
    test_codex_run_stop_uses_existing_cancel_and_emits_terminal_event()
    print("test_codex_runs_sse.py passed")
