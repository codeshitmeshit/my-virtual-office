#!/usr/bin/env python3
"""Server-side coverage for optional Hermes native API detection."""

import os
import sys
import tempfile
import time
import io
import json
import types
import threading

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


def call_office_handler(server, method, path, body=None, headers=None):
    payload = json.dumps(body).encode("utf-8") if body is not None else b""
    handler = server.OfficeHandler.__new__(server.OfficeHandler)
    handler.path = path
    handler.headers = {"Content-Length": str(len(payload)), **(headers or {})}
    handler.rfile = io.BytesIO(payload)
    handler.wfile = io.BytesIO()
    handler._status = None
    handler._headers = []

    def send_response(self, status, message=None):
        self._status = status

    def send_header(self, key, value):
        self._headers.append((key, value))

    def end_headers(self):
        return None

    handler.send_response = types.MethodType(send_response, handler)
    handler.send_header = types.MethodType(send_header, handler)
    handler.end_headers = types.MethodType(end_headers, handler)
    if method == "POST":
        server.OfficeHandler.do_POST(handler)
    else:
        server.OfficeHandler.do_GET(handler)
    return handler._status, json.loads(handler.wfile.getvalue().decode("utf-8"))


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
    stream_started = threading.Event()
    stream_release = threading.Event()

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
        if self.mode == "alternate_events":
            return {"runId": "run-native-alt"}
        return {"run_id": "run-native-1"}

    def stream_run_events(self, run_id, timeout_sec=None):
        if self.mode == "blocking":
            self.stream_started.set()
            self.stream_release.wait(2)
            yield {"event": "run.completed"}
            return
        if self.mode == "sensitive_failure":
            yield {"event": "message.delta", "delta": "safe", "apiKey": "sk-abcdefghijklmnop", "private": "/Users/private/file"}
            yield {"event": "run.failed", "error": "sk-abcdefghijklmnop at /Users/private/file"}
            return
        if self.mode == "approval":
            yield {"event": "message.delta", "delta": "needs approval"}
            yield {"event": "approval.request", "run_id": run_id, "command": "write-file", "description": "Approve write"}
            return
        if self.mode == "alternate_events":
            yield {"type": "reasoning", "text": "thinking alt"}
            yield {"type": "tool_call", "id": "tool-alt", "name": "search", "preview": "docs"}
            yield {"type": "tool_result", "id": "tool-alt", "name": "search", "result": "ok"}
            yield {"type": "response_delta", "data": {"delta": "alt "}}
            yield {"type": "message_completed", "content": "reply"}
            yield {"type": "completed", "output": "alt reply"}
            return
        yield {"event": "reasoning.available", "text": "thinking natively"}
        yield {"event": "tool.started", "id": "tool-1", "tool": "read", "preview": "README.md"}
        yield {"event": "tool.completed", "id": "tool-1", "tool": "read", "result": "ok"}
        yield {"event": "message.delta", "delta": "native "}
        yield {"event": "message.delta", "delta": "reply"}
        yield {"event": "run.completed"}

    def respond_approval(self, run_id, choice):
        self.calls.append({"respond_approval": run_id, "choice": choice})
        return {"ok": True, "run_id": run_id, "choice": choice}

    def stop_run(self, run_id):
        self.calls.append({"stop_run": run_id})
        self.stream_release.set()
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
        "license": server.get_license_status,
    }
    FakeHermesProvider.chats = []
    FakeHermesApiClient.calls = []
    FakeHermesApiClient.mode = api_mode
    FakeHermesApiClient.stream_started.clear()
    FakeHermesApiClient.stream_release.clear()
    server.HERMES_APPROVAL_SERVICE.clear()
    status_dir = tempfile.mkdtemp(prefix="vo-hermes-native-chat-")
    server.STATUS_DIR = status_dir
    server.HermesProvider = FakeHermesProvider
    server.HermesApiClient = FakeHermesApiClient
    server.get_roster = lambda: [AGENT]
    server.get_license_status = lambda: {"licensed": True, "tier": "DEV", "tierName": "Developer Mode", "demo": False, "limits": None}
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
    server.get_license_status = old["license"]


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


def test_hermes_test_rejects_unconfigured_request_target():
    old_provider = server.HermesProvider
    old_client = server.HermesApiClient
    old_config = server.VO_CONFIG
    FakeHermesApiClient.calls = []
    server.HermesProvider = FakeHermesProvider
    server.HermesApiClient = FakeHermesApiClient
    server.VO_CONFIG = {
        **server.VO_CONFIG,
        "hermes": {"apiEnabled": True, "apiUrl": "http://127.0.0.1:8642", "apiKey": "stored-secret"},
    }
    try:
        result = server._handle_hermes_test({"apiUrl": "http://attacker.invalid:9999"})
        assert result["ok"] is False
        assert result["_status"] == 400
        assert FakeHermesApiClient.calls == []
        assert "stored-secret" not in str(result)
        tcp_override = server._handle_hermes_test({
            "desktopUrl": server._default_hermes_desktop_url(),
            "desktopTcpHost": "attacker.invalid",
            "desktopTcpPort": 9999,
        })
        assert tcp_override["ok"] is False
        assert tcp_override["_status"] == 400
        assert "Desktop route" in tcp_override["error"]
        discover_override = server._handle_hermes_desktop_discover({
            "desktopTcpHost": "attacker.invalid",
            "desktopTcpPort": 9999,
        })
        assert discover_override["ok"] is False
        assert discover_override["_status"] == 400
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


def test_hermes_chat_accepts_alternate_native_event_shapes():
    old = install_native_fakes("alternate_events")
    try:
        result = server._handle_hermes_chat({"agentId": "hermes-default", "message": "hello", "conversationId": "conv-alt-events"})
        assert result["ok"] is True
        assert result["providerPath"] == "api"
        assert result["runId"] == "run-native-alt"
        assert result["reply"] == "alt reply"
        assert result["thinking"] == "thinking alt"
        assert any(t["id"] == "tool-alt" and t["status"] == "done" for t in result["tools"])
    finally:
        restore_native_fakes(old)


def test_hermes_native_approval_sends_feishu_notification_once():
    old = install_native_fakes("approval")
    old_send = server.send_feishu_notification
    sent = []
    try:
        def fake_send(intent, **kwargs):
            sent.append({"intent": intent, "kwargs": kwargs})
            return {"ok": True, "status": "sent", "record": {"id": intent["id"]}}

        server.send_feishu_notification = fake_send
        result = server._handle_hermes_chat({"agentId": "hermes-default", "message": "hello", "conversationId": "conv-approval-feishu"})
        assert result["approval"]["feishuNotification"]["status"] == "sent"
        assert len(sent) == 1
        intent = sent[0]["intent"]
        assert intent["type"] == "application_form"
        assert intent["target"] == "feishu-hermes-approval"
        assert intent["related"]["type"] == "hermes_approval"
        assert [a["text"] for a in intent["actions"][:4]] == ["允许一次", "本会话允许", "永久允许", "拒绝"]
        assert [a["value"]["action"] for a in intent["actions"][:4]] == [
            "hermes_approval_once",
            "hermes_approval_session",
            "hermes_approval_always",
            "hermes_approval_deny",
        ]

        duplicate = server._remember_hermes_approval_pending(result["approval"], agent_id="hermes-default", profile="default", session_id=result["sessionId"])
        assert duplicate["approval_id"] == result["approval"]["approval_id"]
        assert len(sent) == 1
    finally:
        server.send_feishu_notification = old_send
        restore_native_fakes(old)


def test_feishu_card_action_can_approve_hermes_native_approval():
    old = install_native_fakes("approval")
    old_send = server.send_feishu_notification
    try:
        server.send_feishu_notification = lambda intent, **kwargs: {"ok": True, "status": "sent"}
        result = server._handle_hermes_chat({"agentId": "hermes-default", "message": "hello", "conversationId": "conv-approval-action"})
        approval = result["approval"]
        action_result = server._handle_feishu_card_action({
            "schema": "2.0",
            "header": {"event_type": "card.action.trigger"},
            "event": {
                "operator": {"open_id": "ou_approver"},
                "open_message_id": "om_approval",
                "action": {
                    "value": {
                        "action": "hermes_approval_approve_once",
                        "approval_id": approval["approval_id"],
                        "agent_id": "hermes-default",
                        "session_id": approval["session_id"],
                        "run_id": approval["runId"],
                    }
                },
            },
        })

        assert action_result["ok"] is True
        assert action_result["outcome"]["businessStatus"] == "approved_once"
        assert {"respond_approval": "run-native-1", "choice": "once"} in FakeHermesApiClient.calls
        pending = server._get_hermes_approval_pending("hermes-default", approval["session_id"])
        assert pending["pending"] is None
    finally:
        server.send_feishu_notification = old_send
        restore_native_fakes(old)


def test_hermes_feishu_e2e_routes_create_and_approve_via_http():
    old = install_native_fakes("success")
    old_send = server.send_feishu_notification
    sent = []
    try:
        def fake_send(intent, **kwargs):
            sent.append({"intent": intent, "kwargs": kwargs})
            return {"ok": True, "status": "sent", "record": {"id": intent["id"]}}

        server.send_feishu_notification = fake_send
        status, created = call_office_handler(server, "POST", "/api/hermes/approval/feishu-e2e-create", {
            "agentId": "hermes-default",
            "suffix": "route-http",
            "command": "touch /tmp/vo-hermes-feishu-e2e-route-http",
        })
        assert status == 200
        assert created["ok"] is True
        approval = created["approval"]
        assert approval["approval_id"] == "hermes-feishu-e2e-route-http"
        assert approval["feishuNotification"]["status"] == "sent"
        assert sent[0]["intent"]["target"] == "feishu-hermes-approval"

        status, action = call_office_handler(server, "POST", "/api/hermes/approval/feishu-e2e-action", {
            "schema": "2.0",
            "header": {"event_type": "card.action.trigger"},
            "event": {
                "operator": {"open_id": "ou_route_approver"},
                "open_message_id": "om_route_approval",
                "action": {
                    "value": {
                        "action": "hermes_approval_session",
                        "approval_id": approval["approval_id"],
                        "agent_id": "hermes-default",
                        "session_id": approval["session_id"],
                        "run_id": approval["runId"],
                    }
                },
            },
        })
        assert status == 200
        assert action["ok"] is True
        assert action["outcome"]["businessStatus"] == "approved_session"
        assert {"respond_approval": approval["runId"], "choice": "session"} in FakeHermesApiClient.calls
        pending = server._get_hermes_approval_pending("hermes-default", approval["session_id"])
        assert pending["pending"] is None

        with open(os.path.join(server.STATUS_DIR, "feishu-card-actions.jsonl"), "r", encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
        assert rows[-1]["action"] == "hermes_approval_session"
        assert rows[-1]["outcome"]["businessStatus"] == "approved_session"
    finally:
        server.send_feishu_notification = old_send
        restore_native_fakes(old)


def test_feishu_card_action_can_always_approve_hermes_native_approval():
    old = install_native_fakes("approval")
    old_send = server.send_feishu_notification
    try:
        server.send_feishu_notification = lambda intent, **kwargs: {"ok": True, "status": "sent"}
        result = server._handle_hermes_chat({"agentId": "hermes-default", "message": "hello", "conversationId": "conv-approval-always"})
        approval = result["approval"]
        action_result = server._handle_feishu_card_action({
            "schema": "2.0",
            "header": {"event_type": "card.action.trigger"},
            "event": {
                "operator": {"open_id": "ou_always_approver"},
                "open_message_id": "om_approval_always",
                "action": {
                    "value": {
                        "action": "hermes_approval_always",
                        "approval_id": approval["approval_id"],
                        "agent_id": "hermes-default",
                        "session_id": approval["session_id"],
                        "run_id": approval["runId"],
                    }
                },
            },
        })

        assert action_result["ok"] is True
        assert action_result["outcome"]["businessStatus"] == "approved_always"
        assert {"respond_approval": "run-native-1", "choice": "always"} in FakeHermesApiClient.calls
    finally:
        server.send_feishu_notification = old_send
        restore_native_fakes(old)


def test_hermes_approval_replay_does_not_call_provider_twice_and_cross_run_fails_closed():
    old = install_native_fakes("approval")
    old_send = server.send_feishu_notification
    try:
        server.send_feishu_notification = lambda intent, **kwargs: {"ok": True, "status": "sent"}
        result = server._handle_hermes_chat({"agentId": "hermes-default", "message": "hello", "conversationId": "conv-approval-replay"})
        approval = result["approval"]
        forged = server._handle_hermes_approval_respond({
            "agentId": "hermes-default", "approval_id": approval["approval_id"],
            "session_id": approval["session_id"], "runId": "other-run", "choice": "once",
        })
        assert forged["ok"] is False
        assert forged["status"] == "approval_not_found"
        request = {
            "agentId": "hermes-default", "approval_id": approval["approval_id"],
            "session_id": approval["session_id"], "runId": approval["runId"], "choice": "once",
        }
        first = server._handle_hermes_approval_respond(request)
        replay = server._handle_hermes_approval_respond(request)
        assert first["ok"] is True
        assert replay == first
        calls = [call for call in FakeHermesApiClient.calls if call.get("respond_approval") == approval["runId"]]
        assert len(calls) == 1
    finally:
        server.send_feishu_notification = old_send
        restore_native_fakes(old)


def test_hermes_notification_failure_does_not_remove_pending_approval():
    old = install_native_fakes("approval")
    old_send = server.send_feishu_notification
    try:
        def fail_notification(intent, **kwargs):
            raise RuntimeError("Feishu unavailable")

        server.send_feishu_notification = fail_notification
        result = server._handle_hermes_chat({"agentId": "hermes-default", "message": "hello", "conversationId": "conv-notification-failure"})
        assert result["approval"]["feishuNotification"]["ok"] is False
        pending = server._get_hermes_approval_pending("hermes-default", result["sessionId"])
        assert pending["pending"]["approval_id"] == result["approval"]["approval_id"]
    finally:
        server.send_feishu_notification = old_send
        restore_native_fakes(old)


def test_hermes_feishu_e2e_action_route_rejects_non_test_approval_ids():
    old = install_native_fakes("success")
    try:
        status, result = call_office_handler(server, "POST", "/api/hermes/approval/feishu-e2e-action", {
            "schema": "2.0",
            "event": {
                "action": {
                    "value": {
                        "action": "hermes_approval_approve_once",
                        "approval_id": "real-approval-id",
                        "agent_id": "hermes-default",
                    }
                }
            },
        })
        assert status == 403
        assert result["ok"] is False
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


def test_hermes_attachment_descriptors_are_validated_before_adapter_delivery():
    old = install_native_fakes("unavailable")
    try:
        upload_dir = os.path.join(server.STATUS_DIR, "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        path = os.path.join(upload_dir, "note.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("hello")
        result = server._handle_hermes_chat({
            "agentId": "hermes-default", "message": "read it", "conversationId": "conv-attachment",
            "attachments": [{"name": "note.txt", "mimeType": "text/plain", "size": 5, "path": path, "raw": "ignored"}],
        })
        assert result["ok"] is True
        delivered = FakeHermesProvider.chats[-1]["message"]
        assert "note.txt" in delivered and path in delivered
        rejected = server._handle_hermes_chat({
            "agentId": "hermes-default", "message": "read secret", "conversationId": "conv-attachment",
            "attachments": [{"name": "passwd", "path": "/etc/passwd"}],
        })
        assert rejected["ok"] is False
        assert rejected["status"] == "invalid_attachment"
        assert rejected["_status"] == 400
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
            meta = server.PROVIDER_RUN_REPOSITORY.get(run_id)
            if meta and meta.get("done"):
                break
            time.sleep(0.02)
        assert meta and meta["done"] is True
        assert meta["result"]["ok"] is True
        assert meta["result"]["reply"] == "native reply"

        events = server.PROVIDER_EVENT_JOURNAL.run_events_after(run_id)
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
        server.PROVIDER_RUN_REPOSITORY.clear(run_id)
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
            meta = server.PROVIDER_RUN_REPOSITORY.get(first["runId"])
            if meta and meta.get("done"):
                break
            time.sleep(0.02)
        history = server._load_hermes_history("default", "conv-hermes-idem")
        assert len([msg for msg in history if msg.get("role") == "user" and msg.get("text") == "hello idem"]) == 1
        server.PROVIDER_RUN_REPOSITORY.clear(first["runId"])
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
            meta = server.PROVIDER_RUN_REPOSITORY.get(run_id)
            if meta and meta.get("done"):
                break
            time.sleep(0.02)
        meta = server.PROVIDER_RUN_REPOSITORY.get(run_id)
        assert meta and meta["done"] is True
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
            meta = server.PROVIDER_RUN_REPOSITORY.get(run_id)
            if meta and meta.get("done"):
                break
            time.sleep(0.02)
        assert meta and meta["done"] is True
        events = server.PROVIDER_EVENT_JOURNAL.run_events_after(run_id)
        names = [item["event"] for item in events]
        assert "approval.required" in names
        assert names[-1] == "run.failed"
        approval_event = next(item for item in events if item["event"] == "approval.required")
        assert approval_event["data"]["approval"]["provider"] == "hermes-api"
        server.PROVIDER_RUN_REPOSITORY.clear(run_id)
    finally:
        restore_native_fakes(old)


def test_hermes_run_stop_delegates_to_native_api_and_emits_terminal():
    old = install_native_fakes("success")
    try:
        run_id = "hermes-test-stop"
        server.PROVIDER_RUN_REPOSITORY.reserve_start(
            provider_kind="hermes", agent_id="hermes-default", conversation_id="conv-stop", run_id=run_id, meta={
            "profile": "default",
            "turnId": "native-run-to-stop",
            "done": False,
        })
        result = server._handle_hermes_run_stop({"runId": run_id})
        assert result["ok"] is True
        assert result["status"] == "cancelled"
        assert any(call.get("stop_run") == "native-run-to-stop" for call in FakeHermesApiClient.calls)
        meta = server.PROVIDER_RUN_REPOSITORY.get(run_id)
        assert meta["done"] is True
        item = server.PROVIDER_EVENT_JOURNAL.run_events_after(run_id)[-1]
        assert item["event"] == "run.cancelled"
        server.PROVIDER_RUN_REPOSITORY.clear(run_id)
    finally:
        restore_native_fakes(old)


def test_coordinated_hermes_cancel_fences_late_native_completion():
    old = install_native_fakes("blocking")
    try:
        started = server._handle_hermes_run_start({"agentId": "hermes-default", "message": "wait", "conversationId": "conv-cancel-coordinated"})
        assert FakeHermesApiClient.stream_started.wait(1)
        result = server._handle_hermes_run_stop({"runId": started["runId"]})
        assert result["ok"] is True
        assert result["status"] == "cancelled"
        deadline = time.time() + 1
        while time.time() < deadline:
            snapshot = server.PROVIDER_RUN_REPOSITORY.get(started["runId"])
            if snapshot and snapshot.get("terminal"):
                break
            time.sleep(0.01)
        events = server.PROVIDER_EVENT_JOURNAL.run_events_after(started["runId"])
        terminals = [item for item in events if item["event"] in {"run.completed", "run.failed", "run.cancelled"}]
        assert [item["event"] for item in terminals] == ["run.cancelled"]
        assert len([call for call in FakeHermesApiClient.calls if call.get("stop_run") == "run-native-1"]) == 1, FakeHermesApiClient.calls
    finally:
        FakeHermesApiClient.stream_release.set()
        restore_native_fakes(old)


def test_hermes_run_redacts_sensitive_native_event_and_error_data():
    old = install_native_fakes("sensitive_failure")
    try:
        started = server._handle_hermes_run_start({"agentId": "hermes-default", "message": "fail safely", "conversationId": "conv-sensitive"})
        deadline = time.time() + 1
        while time.time() < deadline:
            snapshot = server.PROVIDER_RUN_REPOSITORY.get(started["runId"])
            if snapshot and snapshot.get("terminal"):
                break
            time.sleep(0.01)
        snapshot = server.PROVIDER_RUN_REPOSITORY.get(started["runId"])
        events = server.PROVIDER_EVENT_JOURNAL.run_events_after(started["runId"])
        public = json.dumps(events, ensure_ascii=False)
        assert "sk-abcdefghijklmnop" not in public
        assert "/Users/private/file" not in public
        assert "rawEvent" not in public
        assert "sk-abcdefghijklmnop" not in str(snapshot["result"].get("error"))
        assert "/Users/private/file" not in str(snapshot["result"].get("error"))
    finally:
        restore_native_fakes(old)


def test_hermes_cancel_fences_pending_approval_before_late_decision():
    old = install_native_fakes("approval")
    try:
        started = server._handle_hermes_run_start({"agentId": "hermes-default", "message": "needs approval", "conversationId": "conv-cancel-approval"})
        deadline = time.time() + 1
        while time.time() < deadline:
            snapshot = server.PROVIDER_RUN_REPOSITORY.get(started["runId"])
            if snapshot and snapshot.get("terminal"):
                break
            time.sleep(0.01)
        snapshot = server.PROVIDER_RUN_REPOSITORY.get(started["runId"])
        approval = snapshot["result"]["approval"]
        cancelled = server._handle_hermes_run_stop({"runId": started["runId"]})
        assert cancelled["ok"] is True
        assert cancelled["status"] == "cancelled"
        assert server._get_hermes_approval_pending("hermes-default", approval["session_id"])["pending"] is None
        late = server._handle_hermes_approval_respond({
            "agentId": "hermes-default", "approval_id": approval["approval_id"],
            "session_id": approval["session_id"], "runId": approval["runId"], "choice": "once",
        })
        assert late["ok"] is False
        assert late["status"] == "approval_already_resolved"
        assert len([call for call in FakeHermesApiClient.calls if call.get("stop_run") == approval["runId"]]) == 1
        assert not [call for call in FakeHermesApiClient.calls if call.get("respond_approval") == approval["runId"]]
    finally:
        restore_native_fakes(old)


def test_hermes_reset_fences_late_conversation_history_and_native_id_write():
    old = install_native_fakes("blocking")
    result_holder = []
    try:
        thread = threading.Thread(target=lambda: result_holder.append(server._handle_hermes_chat({"agentId": "hermes-default", "message": "late", "conversationId": "conv-reset-race"})))
        thread.start()
        assert FakeHermesApiClient.stream_started.wait(1)
        cleared = server._handle_hermes_history_clear({"agentId": "hermes-default", "conversationId": "conv-reset-race"})
        assert cleared["ok"] is True
        FakeHermesApiClient.stream_release.set()
        thread.join(1)
        assert result_holder and result_holder[0]["ok"] is True
        assert server._load_hermes_history("default", "conv-reset-race") == []
        assert server._get_hermes_session_id("default", "conv-reset-race") == ""
    finally:
        FakeHermesApiClient.stream_release.set()
        restore_native_fakes(old)


if __name__ == "__main__":
    test_hermes_test_reports_native_api_without_exposing_key()
    test_hermes_test_skips_native_api_when_disabled()
    test_hermes_test_rejects_unconfigured_request_target()
    test_hermes_chat_uses_native_api_when_available()
    test_hermes_chat_native_approval_records_pending_without_cli_fallback()
    test_hermes_chat_accepts_alternate_native_event_shapes()
    test_hermes_native_approval_sends_feishu_notification_once()
    test_feishu_card_action_can_approve_hermes_native_approval()
    test_hermes_feishu_e2e_routes_create_and_approve_via_http()
    test_feishu_card_action_can_always_approve_hermes_native_approval()
    test_hermes_feishu_e2e_action_route_rejects_non_test_approval_ids()
    test_hermes_chat_falls_back_to_cli_when_native_api_unavailable()
    test_hermes_history_clear_is_conversation_scoped()
    test_hermes_run_start_publishes_provider_bridge_events()
    test_hermes_run_start_idempotency_reuses_existing_run()
    test_hermes_progress_history_is_recoverable_while_run_active()
    test_hermes_run_events_replays_terminal_for_late_sse_connection()
    test_hermes_run_start_publishes_approval_event_before_failure_terminal()
    test_hermes_run_stop_delegates_to_native_api_and_emits_terminal()
    print("ok")
