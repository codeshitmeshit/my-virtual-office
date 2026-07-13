#!/usr/bin/env python3
"""Generic JSONL app-server runtime tests with a fake subprocess."""

import json
import os
import queue
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from provider_app_server import JsonlAppServerRuntime
from providers.codex_app_server import CodexAppServerClient, MAX_PENDING_APPROVALS


class FakeStdout:
    def __init__(self):
        self.q = queue.Queue()

    def put(self, item):
        self.q.put(item)

    def close(self):
        self.q.put(None)

    def __iter__(self):
        return self

    def __next__(self):
        item = self.q.get(timeout=2)
        if item is None:
            raise StopIteration
        return item


class FakeStderr:
    def __init__(self, lines=None):
        self.lines = list(lines or [])

    def __iter__(self):
        return iter(self.lines)


class FakeStdin:
    def __init__(self, stdout, responder):
        self.stdout = stdout
        self.responder = responder
        self.buffer = ""

    def write(self, data):
        self.buffer += data
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line.strip():
                response = self.responder(json.loads(line))
                if response is not None:
                    self.stdout.put(json.dumps(response) + "\n")

    def flush(self):
        return None


class FakeProcess:
    def __init__(self, responder, stderr_lines=None):
        self.stdout = FakeStdout()
        self.stdin = FakeStdin(self.stdout, responder)
        self.stderr = FakeStderr(stderr_lines)
        self._returncode = None

    def poll(self):
        return self._returncode

    def terminate(self):
        self._returncode = 0
        self.stdout.close()

    def wait(self, timeout=None):
        self._returncode = 0
        self.stdout.close()
        return 0

    def kill(self):
        self._returncode = -9
        self.stdout.close()


def test_runtime_routes_request_response():
    def responder(message):
        return {"id": message["id"], "result": {"method": message["method"], "ok": True}}

    runtime = JsonlAppServerRuntime(["fake"], popen_factory=lambda *a, **k: FakeProcess(responder))
    response = runtime.request("ping", {"x": 1}, timeout=1)
    assert response["result"]["method"] == "ping"
    runtime.close()


def test_runtime_dispatches_server_request_and_notification():
    seen_requests = []
    seen_notifications = []

    def responder(message):
        proc.stdout.put(json.dumps({"id": 99, "method": "approval/request", "params": {"threadId": "thr"}}) + "\n")
        proc.stdout.put(json.dumps({"method": "turn/started", "params": {"threadId": "thr"}}) + "\n")
        return {"id": message["id"], "result": {"ok": True}}

    proc = FakeProcess(responder)
    runtime = JsonlAppServerRuntime(["fake"], popen_factory=lambda *a, **k: proc)
    runtime.on_server_request = lambda message: seen_requests.append(message)
    runtime.on_notification = lambda method, params: seen_notifications.append((method, params))
    runtime.request("start", {}, timeout=1)

    deadline = time.time() + 1
    while time.time() < deadline and (not seen_requests or not seen_notifications):
        time.sleep(0.01)
    assert seen_requests[0]["method"] == "approval/request"
    assert seen_notifications[0][0] == "turn/started"
    runtime.close()


def test_runtime_timeout_and_close_fail_pending():
    def no_response(_message):
        return None

    runtime = JsonlAppServerRuntime(["fake"], popen_factory=lambda *a, **k: FakeProcess(no_response))
    try:
        try:
            runtime.request("slow", {}, timeout=0.05)
            assert False, "expected timeout"
        except TimeoutError:
            pass
    finally:
        runtime.close()


def test_runtime_preserves_stderr_in_exit_errors():
    def responder(_message):
        proc._returncode = 1
        proc.stdout.close()
        return None

    proc = FakeProcess(responder, stderr_lines=["codex failed", "auth missing"])
    runtime = JsonlAppServerRuntime(["fake"], popen_factory=lambda *a, **k: proc)
    try:
        try:
            runtime.request("start", {}, timeout=1)
            assert False, "expected runtime error"
        except RuntimeError as exc:
            text = str(exc)
            assert "codex failed" in text or "auth missing" in text
    finally:
        runtime.close()


def test_runtime_rejects_requests_at_aggregate_capacity():
    import provider_app_server

    old_limit = provider_app_server.MAX_PENDING_REQUESTS
    provider_app_server.MAX_PENDING_REQUESTS = 1
    runtime = JsonlAppServerRuntime(["fake"], popen_factory=lambda *a, **k: FakeProcess(lambda _message: None))
    runtime._pending[999] = queue.Queue(maxsize=1)
    try:
        try:
            runtime.request("overflow", {}, timeout=0.01)
            assert False, "expected capacity failure"
        except RuntimeError as exc:
            assert "capacity" in str(exc)
        assert list(runtime._pending) == [999]
    finally:
        runtime._pending.clear()
        runtime.close()
        provider_app_server.MAX_PENDING_REQUESTS = old_limit


def test_codex_pending_approval_store_is_bounded():
    client = object.__new__(CodexAppServerClient)
    client._approval_lock = threading.Condition()
    client._pending_approvals = {f"approval-{index}": {} for index in range(MAX_PENDING_APPROVALS)}
    stored = client._store_pending_approval(None, "overflow", "item/commandExecution/requestApproval", {}, {"id": "overflow"})
    assert stored is False
    assert len(client._pending_approvals) == MAX_PENDING_APPROVALS


if __name__ == "__main__":
    test_runtime_routes_request_response()
    test_runtime_dispatches_server_request_and_notification()
    test_runtime_timeout_and_close_fail_pending()
    test_runtime_preserves_stderr_in_exit_errors()
    test_runtime_rejects_requests_at_aggregate_capacity()
    test_codex_pending_approval_store_is_bounded()
    print("test_provider_app_server_runtime.py passed")
