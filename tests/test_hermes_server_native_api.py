#!/usr/bin/env python3
"""Server-side coverage for optional Hermes native API detection."""

import os
import sys
import tempfile
import time
import io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

STATUS_DIR = tempfile.mkdtemp(prefix="vo-hermes-server-native-test-")
os.environ["VO_STATUS_DIR"] = STATUS_DIR
os.environ["VO_HERMES_ENABLED"] = "0"
os.environ["VO_CODEX_ENABLED"] = "0"
os.environ["VO_CLAUDE_CODE_ENABLED"] = "0"

import server


class FakeHermesProvider:
    chats = []

    def __init__(self, home_path=None, binary=None, enabled=True, timeout_sec=None):
        self.home_path = home_path
        self.binary = binary
        self.enabled = enabled
        self.timeout_sec = timeout_sec

    def test(self):
        return {"ok": True, "binary": self.binary, "homePath": self.home_path, "agents": []}

    def send_chat_message(self, profile, message, session_id=None, timeout_sec=None, yolo_once=False):
        self.chats.append({"profile": profile, "message": message, "session_id": session_id})
        return {"ok": True, "reply": "cli fallback reply", "stderr": "", "exitCode": 0, "profile": profile, "sessionId": session_id or "cli-session"}

    def export_session(self, profile, session_id):
        return {"ok": False, "error": "not needed"}

    def delete_session(self, profile, session_id):
        return {"ok": True, "deleted": True, "profile": profile, "sessionId": session_id}


class FakeHermesApiClient:
    calls = []
    mode = "success"

    def __init__(self, base_url=None, api_key=None, timeout_sec=30):
        self.base_url = base_url
        self.api_key = api_key
        self.timeout_sec = timeout_sec
        self.calls.append({"base_url": base_url, "api_key": api_key, "timeout_sec": timeout_sec})

    def capabilities(self):
        return {
            "model": "hermes-native-model",
            "features": {
                "run_submission": True,
                "run_events_sse": True,
                "run_approval_response": True,
            },
        }

    def is_available(self):
        return self.mode != "unavailable"

    def start_run(self, message, session_id=None, session_key=None, instructions=None, conversation_history=None):
        self.calls.append({"start_message": message, "session_id": session_id, "session_key": session_key})
        return {"run_id": "run-native-1"}

    def stream_run_events(self, run_id, timeout_sec=None):
        if self.mode == "approval":
            yield {"event": "message.delta", "delta": "needs approval"}
            yield {"event": "approval.request", "run_id": run_id, "command": "write-file", "description": "Approve write"}
            return
        yield {"event": "reasoning.available", "text": "thinking natively"}
        yield {"event": "tool.started", "id": "tool-1", "tool": "read", "preview": "README.md"}
        yield {"event": "tool.completed", "id": "tool-1", "tool": "read", "result": "ok"}
        yield {"event": "message.delta", "delta": "native "}
        yield {"event": "message.delta", "delta": "reply"}
        yield {"event": "run.completed"}

    def stop_run(self, run_id):
        self.calls.append({"stop_run": run_id})
        return {"ok": True, "stopped": True, "run_id": run_id}


AGENT = {
    "id": "hermes-default",
    "statusKey": "hermes-default",
    "providerKind": "hermes",
    "providerAgentId": "default",
    "profile": "default",
    "name": "Hermes",
    "binary": "/tmp/hermes",
}


def install_native_fakes(api_mode="success"):
    old = {
        "provider": server.HermesProvider,
        "client": server.HermesApiClient,
        "config": server.VO_CONFIG,
        "roster": server.get_roster,
        "status_dir": server.STATUS_DIR,
    }
    FakeHermesProvider.chats = []
    FakeHermesApiClient.calls = []
    FakeHermesApiClient.mode = api_mode
    status_dir = tempfile.mkdtemp(prefix="vo-hermes-native-chat-")
    server.STATUS_DIR = status_dir
    server.HermesProvider = FakeHermesProvider
    server.HermesApiClient = FakeHermesApiClient
    server.get_roster = lambda: [AGENT]
    server.VO_CONFIG = {
        **server.VO_CONFIG,
        "hermes": {
            "enabled": True,
            "homePath": "/tmp/hermes-home",
            "binary": "/tmp/hermes",
            "timeoutSec": 5,
            "apiEnabled": True,
            "apiUrl": "http://127.0.0.1:8642",
            "apiKey": "secret-token",
        },
    }
    return old


def restore_native_fakes(old):
    server.HermesProvider = old["provider"]
    server.HermesApiClient = old["client"]
    server.VO_CONFIG = old["config"]
    server.get_roster = old["roster"]
    server.STATUS_DIR = old["status_dir"]


def test_hermes_test_reports_native_api_without_exposing_key():
    old_provider = server.HermesProvider
    old_client = server.HermesApiClient
    old_config = server.VO_CONFIG
    FakeHermesApiClient.calls = []
    server.HermesProvider = FakeHermesProvider
    server.HermesApiClient = FakeHermesApiClient
    server.VO_CONFIG = {
        **server.VO_CONFIG,
        "hermes": {
            "enabled": True,
            "homePath": "/tmp/hermes-home",
            "binary": "/tmp/hermes",
            "timeoutSec": 600,
            "apiEnabled": True,
            "apiUrl": "http://127.0.0.1:8642",
            "apiKey": "secret-token",
        },
    }
    try:
        result = server._handle_hermes_test()
        assert result["ok"] is True
        assert result["api"]["enabled"] is True
        assert result["api"]["ok"] is True
        assert result["api"]["url"] == "http://127.0.0.1:8642"
        assert result["api"]["model"] == "hermes-native-model"
        assert result["api"]["features"]["runSubmission"] is True
        assert result["api"]["features"]["runEventsSse"] is True
        assert result["api"]["features"]["runApprovalResponse"] is True
        assert "secret-token" not in str(result)
        assert FakeHermesApiClient.calls[0]["api_key"] == "secret-token"
    finally:
        server.HermesProvider = old_provider
        server.HermesApiClient = old_client
        server.VO_CONFIG = old_config


def test_hermes_test_skips_native_api_when_disabled():
    old_provider = server.HermesProvider
    old_client = server.HermesApiClient
    old_config = server.VO_CONFIG
    FakeHermesApiClient.calls = []
    server.HermesProvider = FakeHermesProvider
    server.HermesApiClient = FakeHermesApiClient
    server.VO_CONFIG = {
        **server.VO_CONFIG,
        "hermes": {
            "enabled": True,
            "homePath": "/tmp/hermes-home",
            "binary": "/tmp/hermes",
            "timeoutSec": 600,
            "apiEnabled": False,
            "apiUrl": "http://127.0.0.1:8642",
            "apiKey": "secret-token",
        },
    }
    try:
        result = server._handle_hermes_test()
        assert result["ok"] is True
        assert result["api"] == {"enabled": False, "ok": False, "url": "http://127.0.0.1:8642"}
        assert FakeHermesApiClient.calls == []
    finally:
        server.HermesProvider = old_provider
        server.HermesApiClient = old_client
        server.VO_CONFIG = old_config


def test_hermes_chat_uses_native_api_when_available():
    old = install_native_fakes("success")
    try:
        result = server._handle_hermes_chat({"agentId": "hermes-default", "message": "hello", "conversationId": "conv-native"})
        assert result["ok"] is True
        assert result["providerPath"] == "api"
        assert result["reply"] == "native reply"
        assert result["runId"] == "run-native-1"
        assert result["sessionId"].startswith("vo-hermes-")
        assert result["thinking"] == "thinking natively"
        assert any(t["id"] == "tool-1" and t["status"] == "done" for t in result["tools"])
        assert FakeHermesProvider.chats == []
        history = server._load_hermes_history("default", "conv-native")
        assert history[-1]["providerPath"] == "api"
        assert history[-1]["text"] == "native reply"
    finally:
        restore_native_fakes(old)


def test_hermes_chat_native_approval_records_pending_without_cli_fallback():
    old = install_native_fakes("approval")
    try:
        result = server._handle_hermes_chat({"agentId": "hermes-default", "message": "hello", "conversationId": "conv-approval"})
        assert result["ok"] is False
        assert result["providerPath"] == "api"
        assert result["approval"]["provider"] == "hermes-api"
        assert result["approval"]["command"] == "write-file"
        assert FakeHermesProvider.chats == []
        pending = server._get_hermes_approval_pending("hermes-default", result["sessionId"])
        assert pending["pending"]["approval_id"] == result["approval"]["approval_id"]
    finally:
        restore_native_fakes(old)


def test_hermes_chat_falls_back_to_cli_when_native_api_unavailable():
    old = install_native_fakes("unavailable")
    try:
        result = server._handle_hermes_chat({"agentId": "hermes-default", "message": "hello", "conversationId": "conv-fallback"})
        assert result["ok"] is True
        assert result.get("providerPath") != "api"
        assert result["reply"] == "cli fallback reply"
        assert FakeHermesProvider.chats
    finally:
        restore_native_fakes(old)


def test_hermes_history_clear_is_conversation_scoped():
    old = install_native_fakes("success")
    try:
        server._save_hermes_history("default", [{"role": "user", "text": "a"}], "conv-a")
        server._save_hermes_history("default", [{"role": "user", "text": "b"}], "conv-b")
        server._set_hermes_session_id("default", "session-a", "conv-a")
        server._set_hermes_session_id("default", "session-b", "conv-b")

        result = server._handle_hermes_history_clear({"agentId": "hermes-default", "conversationId": "conv-a"})

        assert result["ok"] is True
        assert result["sessionId"] == "session-a"
        assert result["conversationId"] == "conv-a"
        assert server._load_hermes_history("default", "conv-a") == []
        assert server._get_hermes_session_id("default", "conv-a") == ""
        assert server._load_hermes_history("default", "conv-b") == [{"role": "user", "text": "b"}]
        assert server._get_hermes_session_id("default", "conv-b") == "session-b"
    finally:
        restore_native_fakes(old)


def test_hermes_run_start_publishes_provider_bridge_events():
    old = install_native_fakes("success")
    try:
        started = server._handle_hermes_run_start({"agentId": "hermes-default", "message": "hello", "conversationId": "conv-run"})
        assert started["ok"] is True
        assert started["providerPath"] == "api"
        run_id = started["runId"]

        meta = None
        deadline = time.time() + 2
        while time.time() < deadline:
            meta = server.PROVIDER_RUN_BRIDGE.get(run_id)
            if meta and meta.get("done"):
                break
            time.sleep(0.02)
        assert meta and meta["done"] is True
        assert meta["result"]["ok"] is True
        assert meta["result"]["reply"] == "native reply"

        events = []
        q = meta["events"]
        while not q.empty():
            events.append(q.get_nowait())
        names = [item["event"] for item in events]
        assert names[0] == "run.started"
        assert "reasoning.available" in names
        assert "tool.started" in names
        assert "tool.completed" in names
        assert "message.delta" in names
        assert names[-1] == "run.completed"
        assert events[-1]["data"]["reply"] == "native reply"
        assert events[-1]["data"]["providerPath"] == "api"
        history = server._load_hermes_history("default", "conv-run")
        assert not [msg for msg in history if msg.get("ephemeral") == "hermes-progress"]
        assert history[-1]["text"] == "native reply"
        server.PROVIDER_RUN_BRIDGE.clear(run_id)
    finally:
        restore_native_fakes(old)


def test_hermes_run_start_idempotency_reuses_existing_run():
    old = install_native_fakes("success")
    try:
        body = {
            "agentId": "hermes-default",
            "message": "hello idem",
            "conversationId": "conv-hermes-idem",
            "idempotencyKey": "same-click",
        }
        first = server._handle_hermes_run_start(body)
        second = server._handle_hermes_run_start(body)
        assert first["ok"] is True
        assert second["ok"] is True
        assert second["status"] == "duplicate"
        assert second["runId"] == first["runId"]

        deadline = time.time() + 2
        while time.time() < deadline:
            meta = server.PROVIDER_RUN_BRIDGE.get(first["runId"])
            if meta and meta.get("done"):
                break
            time.sleep(0.02)
        history = server._load_hermes_history("default", "conv-hermes-idem")
        assert len([msg for msg in history if msg.get("role") == "user" and msg.get("text") == "hello idem"]) == 1
        server.PROVIDER_RUN_BRIDGE.clear(first["runId"])
    finally:
        restore_native_fakes(old)


def test_hermes_progress_history_is_recoverable_while_run_active():
    old = install_native_fakes("success")
    try:
        server._publish_hermes_progress("default", "hermes-default", "hermes-progress-run-1", {
            "runId": "run-1",
            "sessionId": "session-1",
            "status": "running",
            "reply": "partial",
            "thinking": "thinking natively",
            "tools": [{"id": "tool-1", "name": "read", "status": "running"}],
        }, "conv-progress")
        history = server._load_hermes_history("default", "conv-progress")
        assert len(history) == 1
        progress = history[0]
        assert progress["ephemeral"] == "hermes-progress"
        assert progress["status"] == "running"
        assert progress["text"] == "partial"
        assert progress["thinking"] == "thinking natively"
        assert progress["tools"][0]["name"] == "read"
    finally:
        restore_native_fakes(old)


class FakeSseHandler:
    def __init__(self):
        self.headers = []
        self.status = None
        self.wfile = io.BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.headers.append((name, value))

    def end_headers(self):
        pass


def test_hermes_run_events_replays_terminal_for_late_sse_connection():
    old = install_native_fakes("success")
    try:
        started = server._handle_hermes_run_start({"agentId": "hermes-default", "message": "hello", "conversationId": "conv-run-late"})
        assert started["ok"] is True
        run_id = started["runId"]

        deadline = time.time() + 2
        while time.time() < deadline:
            meta = server.PROVIDER_RUN_BRIDGE.get(run_id)
            if meta and meta.get("done"):
                break
            time.sleep(0.02)
        meta = server.PROVIDER_RUN_BRIDGE.get(run_id)
        assert meta and meta["done"] is True
        while not meta["events"].empty():
            meta["events"].get_nowait()

        handler = FakeSseHandler()
        server._handle_hermes_run_events(handler, run_id)
        output = handler.wfile.getvalue().decode("utf-8")
        assert handler.status == 200
        assert "event: run.completed" in output
        assert "native reply" in output
    finally:
        restore_native_fakes(old)


def test_hermes_run_start_publishes_approval_event_before_failure_terminal():
    old = install_native_fakes("approval")
    try:
        started = server._handle_hermes_run_start({"agentId": "hermes-default", "message": "hello", "conversationId": "conv-run-approval"})
        run_id = started["runId"]
        meta = None
        deadline = time.time() + 2
        while time.time() < deadline:
            meta = server.PROVIDER_RUN_BRIDGE.get(run_id)
            if meta and meta.get("done"):
                break
            time.sleep(0.02)
        assert meta and meta["done"] is True
        events = []
        q = meta["events"]
        while not q.empty():
            events.append(q.get_nowait())
        names = [item["event"] for item in events]
        assert "approval.required" in names
        assert names[-1] == "run.failed"
        approval_event = next(item for item in events if item["event"] == "approval.required")
        assert approval_event["data"]["approval"]["provider"] == "hermes-api"
        server.PROVIDER_RUN_BRIDGE.clear(run_id)
    finally:
        restore_native_fakes(old)


def test_hermes_run_stop_delegates_to_native_api_and_emits_terminal():
    old = install_native_fakes("success")
    try:
        run_id = "hermes-test-stop"
        server.PROVIDER_RUN_BRIDGE.remember({
            "runId": run_id,
            "agentId": "hermes-default",
            "profile": "default",
            "conversationId": "conv-stop",
            "events": server.queue.Queue(),
            "turnId": "native-run-to-stop",
            "done": False,
        })
        result = server._handle_hermes_run_stop({"runId": run_id})
        assert result["ok"] is True
        assert result["status"] == "cancelled"
        assert any(call.get("stop_run") == "native-run-to-stop" for call in FakeHermesApiClient.calls)
        meta = server.PROVIDER_RUN_BRIDGE.get(run_id)
        assert meta["done"] is True
        item = meta["events"].get_nowait()
        assert item["event"] == "run.cancelled"
        server.PROVIDER_RUN_BRIDGE.clear(run_id)
    finally:
        restore_native_fakes(old)


if __name__ == "__main__":
    test_hermes_test_reports_native_api_without_exposing_key()
    test_hermes_test_skips_native_api_when_disabled()
    test_hermes_chat_uses_native_api_when_available()
    test_hermes_chat_native_approval_records_pending_without_cli_fallback()
    test_hermes_chat_falls_back_to_cli_when_native_api_unavailable()
    test_hermes_history_clear_is_conversation_scoped()
    test_hermes_run_start_publishes_provider_bridge_events()
    test_hermes_run_start_idempotency_reuses_existing_run()
    test_hermes_progress_history_is_recoverable_while_run_active()
    test_hermes_run_events_replays_terminal_for_late_sse_connection()
    test_hermes_run_start_publishes_approval_event_before_failure_terminal()
    test_hermes_run_stop_delegates_to_native_api_and_emits_terminal()
    print("ok")
