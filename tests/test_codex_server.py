#!/usr/bin/env python3
"""Server-side lifecycle tests for Codex conversation state and busy handling."""

import os
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

STATUS_DIR = tempfile.mkdtemp(prefix="vo-codex-server-test-")
os.environ["VO_STATUS_DIR"] = STATUS_DIR
os.environ["VO_HERMES_ENABLED"] = "0"
os.environ["VO_CODEX_ENABLED"] = "0"

import server


AGENT = {
    "id": "codex-local",
    "statusKey": "codex-local",
    "providerAgentId": "local",
    "providerKind": "codex",
    "name": "Codex",
    "profile": "local",
}


class BlockingProvider:
    def __init__(self, workspace, started, release):
        self.workspace = workspace
        self.started = started
        self.release = release

    def send_message(self, message, conversation_id="", timeout_sec=None, thread_id="", event_callback=None, allow_interaction=False):
        self.started.set()
        if event_callback:
            event_callback({
                "id": "event-1", "sequence": 1, "type": "activity", "status": "running",
                "threadId": thread_id or "thr-server-test", "turnId": "turn-server-test",
                "itemId": "cmd-1", "name": "commandExecution", "input": {"token": "secret-value"},
                "ts": 1,
            })
        self.release.wait(5)
        return {
            "ok": True,
            "status": "completed",
            "reply": "done",
            "threadId": thread_id or "thr-server-test",
            "turnId": "turn-server-test",
            "modifiedFiles": [],
        }


def test_busy_rejects_second_request_and_releases_lock():
    with tempfile.TemporaryDirectory() as workspace:
        started = threading.Event()
        release = threading.Event()
        provider = BlockingProvider(workspace, started, release)
        old_roster = server.get_roster
        old_provider = server._codex_provider_from_config
        server.get_roster = lambda: [AGENT]
        server._codex_provider_from_config = lambda: provider
        first_result = {}

        def run_first():
            first_result.update(server._handle_codex_chat({
                "agentId": "codex-local",
                "message": "first",
                "conversationId": "conv-busy",
            }))

        worker = threading.Thread(target=run_first)
        try:
            worker.start()
            assert started.wait(2)
            second = server._handle_codex_chat({
                "agentId": "codex-local",
                "message": "second",
                "conversationId": "conv-busy",
            })
            assert second["ok"] is False
            assert second["status"] == "busy"
            assert second["_status"] == 409

            release.set()
            worker.join(5)
            assert first_result["ok"] is True

            third = server._handle_codex_chat({
                "agentId": "codex-local",
                "message": "third",
                "conversationId": "conv-busy",
            })
            assert third["ok"] is True
        finally:
            release.set()
            worker.join(5)
            server.get_roster = old_roster
            server._codex_provider_from_config = old_provider


def test_thread_mapping_persists_and_resets():
    old_status_dir = server.STATUS_DIR
    with tempfile.TemporaryDirectory() as status_dir:
        server.STATUS_DIR = status_dir
        try:
            server._set_codex_thread_id("codex-local", "conv-1", "thr-1")
            assert server._get_codex_thread_id("codex-local", "conv-1") == "thr-1"
            assert server._get_codex_thread_id("codex-local", "conv-2") == ""
            assert server._reset_codex_thread_id("codex-local", "conv-1") is True
            assert server._get_codex_thread_id("codex-local", "conv-1") == ""
        finally:
            server.STATUS_DIR = old_status_dir


def test_activity_persists_redacted_and_reports_active_conversation():
    old_status_dir = server.STATUS_DIR
    with tempfile.TemporaryDirectory() as status_dir:
        server.STATUS_DIR = status_dir
        try:
            server._append_codex_activity("codex-local", "conv-activity", {
                "id": "evt", "sequence": 1, "type": "activity", "status": "running",
                "input": {"Authorization": "Bearer top-secret", "nested": {"api_key": "abc"}},
            })
            result = server._handle_codex_activity({"agentId": ["codex-local"], "conversationId": ["conv-activity"]})
            assert result["ok"] is True
            payload = str(result["events"])
            assert "top-secret" not in payload
            assert "abc" not in payload
            assert "[REDACTED]" in payload
            server._append_codex_activity("codex-local", "conv-activity", {
                "id": "evt-2", "sequence": 1, "type": "turn", "status": "running",
            })
            result = server._handle_codex_activity({"agentId": ["codex-local"], "conversationId": ["conv-activity"]})
            assert [event["sequence"] for event in result["events"]] == [1, 2]
            assert result["events"][1]["providerSequence"] == 1
            server._append_codex_activity("codex-local", "conv-orphan", {
                "id": "pending", "sequence": 1, "type": "interaction", "status": "pending",
                "operationId": "old-operation", "interactionId": "10",
            })
            orphan = server._handle_codex_activity({"agentId": ["codex-local"], "conversationId": ["conv-orphan"]})
            assert orphan["events"][0]["status"] == "unavailable"
        finally:
            server.STATUS_DIR = old_status_dir


if __name__ == "__main__":
    test_busy_rejects_second_request_and_releases_lock()
    test_thread_mapping_persists_and_resets()
    test_activity_persists_redacted_and_reports_active_conversation()
    print("ok")
