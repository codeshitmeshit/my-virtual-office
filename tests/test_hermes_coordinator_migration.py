import io
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
os.environ["VO_STATUS_DIR"] = tempfile.mkdtemp(prefix="vo-hermes-coordinator-test-")
os.environ["VO_HERMES_ENABLED"] = "0"
os.environ["VO_CODEX_ENABLED"] = "0"
os.environ["VO_CLAUDE_CODE_ENABLED"] = "0"
import server


AGENT = {
    "id": "hermes-default",
    "statusKey": "hermes-default",
    "providerKind": "hermes",
    "providerAgentId": "default",
    "profile": "default",
    "name": "Hermes",
    "desktopUrl": "http://127.0.0.1:9999",
}


class FakeDesktopClient:
    sends = 0
    ready = True

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def test(self, verify_ws=False):
        return {"ok": self.ready, "chatReady": self.ready, "authRequired": False, "error": "desktop unavailable" if not self.ready else ""}

    def send_chat_message(self, message, session_id=None, timeout_sec=None, on_event=None, run_id=None):
        type(self).sends += 1
        on_event("reasoning.available", {"thinking": "desktop thinking", "sessionId": "desktop-session"})
        on_event("tool.started", {"toolCard": {"id": "tool-1", "name": "read", "status": "running"}})
        on_event("tool.completed", {"toolCard": {"id": "tool-1", "name": "read", "status": "done", "result": "ok"}})
        on_event("message.delta", {"delta": "desktop reply"})
        return {"ok": True, "reply": "desktop reply", "sessionId": "desktop-session", "tools": []}


class FakeSseHandler:
    def __init__(self):
        self.status = None
        self.headers = []
        self.wfile = io.BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.headers.append((name, value))

    def end_headers(self):
        pass


def wait_terminal(run_id):
    deadline = time.time() + 2
    while time.time() < deadline:
        snapshot = server.PROVIDER_RUN_REPOSITORY.get(run_id)
        if snapshot and snapshot.get("terminal"):
            return snapshot
        time.sleep(0.01)
    raise AssertionError("Hermes Desktop run did not finish")


def test_desktop_run_uses_coordinator_and_shared_sse(monkeypatch, tmp_path):
    FakeDesktopClient.sends = 0
    FakeDesktopClient.ready = True
    monkeypatch.setattr(server, "HermesDesktopBackendClient", FakeDesktopClient)
    monkeypatch.setattr(server, "get_roster", lambda: [AGENT])
    monkeypatch.setattr(server, "STATUS_DIR", str(tmp_path))
    monkeypatch.setattr(server, "VO_CONFIG", {
        **server.VO_CONFIG,
        "hermes": {
            "enabled": True,
            "desktopUrl": AGENT["desktopUrl"],
            "preferDesktop": True,
            "apiEnabled": True,
            "timeoutSec": 5,
        },
    })
    body = {"agentId": "hermes-default", "message": "hello desktop", "conversationId": "desktop-conv", "idempotencyKey": "desktop-once"}
    first = server._handle_hermes_run_start(body)
    duplicate = server._handle_hermes_run_start(body)
    assert first["providerPath"] == "desktop"
    assert duplicate["runId"] == first["runId"]
    assert duplicate["status"] in {"duplicate", "duplicate_completed"}
    snapshot = wait_terminal(first["runId"])
    assert snapshot["result"]["reply"] == "desktop reply"
    assert FakeDesktopClient.sends == 1
    assert server.PROVIDER_RUN_REPOSITORY.get(first["runId"])["generation"] == snapshot["generation"]

    handler = FakeSseHandler()
    server._handle_hermes_run_events(handler, first["runId"])
    output = handler.wfile.getvalue().decode()
    assert handler.status == 200
    assert "event: reasoning.available" in output
    assert "event: tool.completed" in output
    assert "event: run.completed" in output
    assert "desktop reply" in output

    history = server._load_hermes_history("default", "desktop-conv")
    assert len([item for item in history if item.get("role") == "user"]) == 1
    assert history[-1]["text"] == "desktop reply"


def test_desktop_unavailable_preserves_api_fallback_precedence(monkeypatch, tmp_path):
    FakeDesktopClient.sends = 0
    FakeDesktopClient.ready = False
    monkeypatch.setattr(server, "HermesDesktopBackendClient", FakeDesktopClient)
    monkeypatch.setattr(server, "get_roster", lambda: [AGENT])
    monkeypatch.setattr(server, "STATUS_DIR", str(tmp_path))
    monkeypatch.setattr(server, "VO_CONFIG", {
        **server.VO_CONFIG,
        "hermes": {"enabled": True, "desktopUrl": AGENT["desktopUrl"], "preferDesktop": True, "apiEnabled": True, "timeoutSec": 5},
    })
    monkeypatch.setattr(server, "_handle_hermes_chat", lambda body: {"ok": True, "reply": "api fallback", "providerPath": "api", "runId": "native-api-run", "sessionId": "api-session"})
    started = server._handle_hermes_run_start({"agentId": "hermes-default", "message": "fallback", "conversationId": "fallback-conv"})
    snapshot = wait_terminal(started["runId"])
    assert started["providerPath"] == "api"
    assert snapshot["result"]["providerPath"] == "api"
    assert snapshot["result"]["reply"] == "api fallback"
    assert FakeDesktopClient.sends == 0


def test_gateway_platform_keeps_queued_delivery_semantics(monkeypatch):
    gateway = {**AGENT, "id": "hermes-gateway", "statusKey": "hermes-gateway", "profile": "gateway"}
    monkeypatch.setattr(server, "get_roster", lambda: [gateway])
    monkeypatch.setattr(server, "_is_hermes_gateway_platform_agent", lambda agent: True)
    result = server._handle_hermes_run_start({"agentId": "hermes-gateway", "message": "queued only", "conversationId": "gateway-conv"})
    assert result["ok"] is False
    assert result["providerPath"] == "gateway-platform"
    assert result["_status"] == 409
