#!/usr/bin/env python3
"""Focused coverage for the optional Hermes native API client."""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from providers.hermes import HermesApiClient


class HermesFixtureHandler(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, fmt, *args):
        return

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or "0")
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _send_json(self, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.requests.append({"method": "GET", "path": self.path, "headers": dict(self.headers)})
        if self.path == "/health":
            self._send_json({"status": "ok"})
            return
        if self.path == "/v1/capabilities":
            self._send_json({"features": {"run_submission": True, "run_events_sse": True}})
            return
        if self.path == "/v1/runs/run-1":
            self._send_json({"id": "run-1", "status": "completed"})
            return
        if self.path == "/v1/runs/run-1/events":
            body = (
                b": keepalive\n\n"
                b"data: {\"type\":\"message_delta\",\n"
                b"data: \"text\":\"hello\"}\n\n"
                b"data: not-json\n\n"
                b"data: {\"type\":\"completed\",\"status\":\"completed\"}\n\n"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        body = self._read_json()
        self.requests.append({"method": "POST", "path": self.path, "headers": dict(self.headers), "body": body})
        if self.path == "/v1/runs":
            self._send_json({"id": "run-1", "status": "running", "received": body})
            return
        if self.path == "/v1/runs/run-1/approval":
            self._send_json({"ok": True, "choice": body.get("choice")})
            return
        if self.path == "/v1/runs/run-1/stop":
            self._send_json({"ok": True, "stopped": True})
            return
        self.send_response(404)
        self.end_headers()


def with_server():
    HermesFixtureHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), HermesFixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def test_hermes_api_client_run_surface_and_sse_events():
    server, base_url = with_server()
    try:
        client = HermesApiClient(base_url=base_url, api_key="secret", timeout_sec=5)
        assert client.is_available() is True

        started = client.start_run(
            "hello",
            session_id="session-1",
            session_key="agent-session-key",
            instructions="be concise",
            conversation_history=[{"role": "user", "content": "prior"}],
        )
        assert started["id"] == "run-1"
        assert started["received"]["input"] == "hello"

        run = client.get_run("run-1")
        assert run["status"] == "completed"

        approved = client.respond_approval("run-1", "approve")
        assert approved["choice"] == "approve"

        stopped = client.stop_run("run-1")
        assert stopped["stopped"] is True

        events = list(client.stream_run_events("run-1", timeout_sec=5))
        assert events == [
            {"type": "message_delta", "text": "hello"},
            {"type": "completed", "status": "completed"},
        ]

        run_requests = [r for r in HermesFixtureHandler.requests if r["path"] == "/v1/runs"]
        assert run_requests[0]["headers"]["Authorization"] == "Bearer secret"
        assert run_requests[0]["headers"]["X-Hermes-Session-Key"] == "agent-session-key"
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    test_hermes_api_client_run_surface_and_sse_events()
    print("ok")
