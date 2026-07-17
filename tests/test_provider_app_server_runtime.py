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

from provider_app_server import AppServerResponseError, JsonlAppServerRuntime
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


class DelayedCloseStdout(FakeStdout):
    def close(self):
        threading.Timer(0.08, lambda: self.q.put(None)).start()


class DelayedCloseProcess(FakeProcess):
    def __init__(self, responder):
        super().__init__(responder)
        self.stdout = DelayedCloseStdout()
        self.stdin = FakeStdin(self.stdout, responder)


class GatedReadStdout(FakeStdout):
    def __init__(self):
        super().__init__()
        self.read_release = threading.Event()

    def __next__(self):
        self.read_release.wait(1)
        return super().__next__()


class GatedReadProcess(FakeProcess):
    def __init__(self, responder):
        super().__init__(responder)
        self.stdout = GatedReadStdout()
        self.stdin = FakeStdin(self.stdout, responder)


class BlockingWaitProcess(FakeProcess):
    def __init__(self, responder):
        super().__init__(responder)
        self.wait_entered = threading.Event()
        self.wait_release = threading.Event()

    def wait(self, timeout=None):
        self.wait_entered.set()
        self.wait_release.wait(1)
        return super().wait(timeout)


def test_runtime_routes_request_response():
    def responder(message):
        return {"id": message["id"], "result": {"method": message["method"], "ok": True}}

    runtime = JsonlAppServerRuntime(["fake"], popen_factory=lambda *a, **k: FakeProcess(responder))
    response = runtime.request("ping", {"x": 1}, timeout=1)
    assert response["result"]["method"] == "ping"
    runtime.close()


def test_runtime_distinguishes_explicit_rpc_error_from_transport_failure():
    def responder(message):
        return {"id": message["id"], "error": {"message": "invalid request"}}

    runtime = JsonlAppServerRuntime(["fake"], popen_factory=lambda *a, **k: FakeProcess(responder))
    try:
        try:
            runtime.request("invalid", {}, timeout=1)
            assert False, "expected explicit response error"
        except AppServerResponseError as exc:
            assert str(exc) == "invalid request"
    finally:
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
    diagnostics = runtime.diagnostics()
    assert diagnostics["inboundCounts"]["server_request:approval/request"] == 1
    assert diagnostics["inboundCounts"]["notification:turn/started"] == 1
    assert diagnostics["inboundCounts"]["response:result"] == 1
    approval_diagnostic = next(item for item in diagnostics["recentInbound"] if item["method"] == "approval/request")
    assert approval_diagnostic == {
        "at": approval_diagnostic["at"],
        "generation": diagnostics["generation"],
        "kind": "server_request",
        "method": "approval/request",
        "label": "approval/request",
        "threadId": "thr",
        "turnId": "",
    }
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


def test_runtime_routes_a_response_that_arrives_after_timeout_to_cleanup_callback():
    proc = None

    def delayed_response(message):
        threading.Timer(
            0.08,
            lambda: proc.stdout.put(json.dumps({"id": message["id"], "result": {"turn": {"id": "late-turn"}}}) + "\n"),
        ).start()
        return None

    proc = FakeProcess(delayed_response)
    runtime = JsonlAppServerRuntime(["fake"], popen_factory=lambda *a, **k: proc)
    late = []
    delivered = threading.Event()
    try:
        try:
            runtime.request(
                "turn/start",
                {},
                timeout=0.02,
                on_late_response=lambda response: (late.append(response), delivered.set()),
            )
            assert False, "expected timeout"
        except TimeoutError:
            pass
        assert delivered.wait(0.5)
        assert late[0]["result"]["turn"]["id"] == "late-turn"
        assert runtime._late_response_callbacks == {}
    finally:
        runtime.close()


def test_stale_reader_exit_cannot_clear_or_abort_the_next_runtime_generation():
    first = DelayedCloseProcess(lambda _message: None)
    second = FakeProcess(lambda message: {"id": message["id"], "result": {"generation": 2}})
    processes = iter((first, second))
    runtime = JsonlAppServerRuntime(["fake"], popen_factory=lambda *a, **k: next(processes))
    exits = []
    runtime.on_exit = lambda: exits.append(runtime._generation)
    try:
        runtime.start()
        first_generation = runtime._generation
        runtime.close()
        runtime.start()
        assert runtime._generation > first_generation
        time.sleep(0.15)
        assert exits == []
        response = runtime.request("ping", {}, timeout=1)
        assert response["result"]["generation"] == 2
    finally:
        runtime.close()


def test_natural_exit_is_finalized_before_replacement_generation_starts():
    first = DelayedCloseProcess(lambda _message: None)
    second = FakeProcess(lambda message: {"id": message["id"], "result": {"generation": 2}})
    processes = iter((first, second))
    runtime = JsonlAppServerRuntime(["fake"], popen_factory=lambda *a, **k: next(processes))
    exits = []
    request_error = []

    def request_pending():
        try:
            runtime.request("pending", {}, timeout=1)
        except Exception as exc:
            request_error.append(exc)

    request_worker = threading.Thread(target=request_pending)
    runtime.on_exit = lambda: exits.append(runtime.generation)
    try:
        runtime.start()
        request_worker.start()
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            with runtime._pending_lock:
                if runtime._pending:
                    break
            time.sleep(0.01)
        first._returncode = 1
        first.stdout.close()
        runtime.start()
        request_worker.join(0.5)
        assert not request_worker.is_alive()
        assert request_error and "App-server stopped" in str(request_error[0])
        assert len(exits) == 1
        with runtime._pending_lock:
            assert runtime._pending == {}
        response = runtime.request("ping", {}, timeout=1)
        assert response["result"]["generation"] == 2
    finally:
        runtime.close()


def test_replacement_waits_for_old_reader_to_deliver_buffered_response():
    first = GatedReadProcess(lambda message: {"id": message["id"], "result": {"generation": 1}})
    second = FakeProcess(lambda message: {"id": message["id"], "result": {"generation": 2}})
    processes = iter((first, second))
    runtime = JsonlAppServerRuntime(["fake"], popen_factory=lambda *a, **k: next(processes))
    exits = []
    response = {}
    request_worker = threading.Thread(target=lambda: response.update(runtime.request("pending", {}, timeout=1)))
    start_worker = threading.Thread(target=runtime.start)
    runtime.on_exit = lambda: exits.append(runtime.generation)
    try:
        runtime.start()
        request_worker.start()
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            with runtime._pending_lock:
                if runtime._pending:
                    break
            time.sleep(0.01)
        first._returncode = 0
        first.stdout.close()
        start_worker.start()
        time.sleep(0.05)
        assert start_worker.is_alive()
        assert request_worker.is_alive()

        first.stdout.read_release.set()
        request_worker.join(0.5)
        start_worker.join(0.5)
        assert not request_worker.is_alive()
        assert not start_worker.is_alive()
        assert response["result"]["generation"] == 1
        assert len(exits) == 1
        assert runtime.request("ping", {}, timeout=1)["result"]["generation"] == 2
    finally:
        first.stdout.read_release.set()
        runtime.close()


def test_replacement_refuses_to_switch_generation_while_reader_is_still_draining():
    first = GatedReadProcess(lambda message: {"id": message["id"], "result": {"committed": True}})
    second = FakeProcess(lambda message: {"id": message["id"], "result": {"generation": 2}})
    processes = iter((first, second))
    runtime = JsonlAppServerRuntime(["fake"], popen_factory=lambda *a, **k: next(processes))
    response = {}
    request_worker = threading.Thread(target=lambda: response.update(runtime.request("commit", {}, timeout=1)))
    try:
        runtime.start()
        generation = runtime.generation
        request_worker.start()
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            with runtime._pending_lock:
                if runtime._pending:
                    break
            time.sleep(0.01)
        first._returncode = 0
        first.stdout.close()

        try:
            runtime.start()
            assert False, "replacement must not start before the old reader drains"
        except RuntimeError as exc:
            assert "still draining" in str(exc)
        assert runtime.generation == generation
        assert request_worker.is_alive()

        first.stdout.read_release.set()
        request_worker.join(0.5)
        assert not request_worker.is_alive()
        assert response["result"]["committed"] is True
        runtime.start()
        assert runtime.request("ping", {}, timeout=1)["result"]["generation"] == 2
    finally:
        first.stdout.read_release.set()
        runtime.close()


def test_exit_callback_runs_after_lifecycle_lock_is_released():
    proc = FakeProcess(lambda _message: None)
    runtime = JsonlAppServerRuntime(["fake"], popen_factory=lambda *a, **k: proc)
    callback_checked = threading.Event()
    helper_acquired = threading.Event()

    def on_exit():
        def acquire_lifecycle():
            with runtime.lifecycle_fence():
                helper_acquired.set()

        helper = threading.Thread(target=acquire_lifecycle)
        helper.start()
        assert helper_acquired.wait(0.2)
        helper.join(0.2)
        callback_checked.set()

    runtime.on_exit = on_exit
    runtime.start()
    proc._returncode = 1
    proc.stdout.close()
    assert callback_checked.wait(0.5)
    assert runtime._reader is not None
    runtime._reader.join(0.5)
    assert not runtime._reader.is_alive()


def test_close_finishes_old_generation_cleanup_before_allowing_new_requests():
    first = BlockingWaitProcess(lambda _message: None)
    second = FakeProcess(lambda message: {"id": message["id"], "result": {"generation": 2}})
    processes = iter((first, second))
    runtime = JsonlAppServerRuntime(["fake"], popen_factory=lambda *a, **k: next(processes))
    close_worker = threading.Thread(target=runtime.close)
    response = {}
    request_worker = threading.Thread(target=lambda: response.update(runtime.request("ping", {}, timeout=1)))
    try:
        runtime.start()
        close_worker.start()
        assert first.wait_entered.wait(0.5)
        request_worker.start()
        time.sleep(0.05)
        assert request_worker.is_alive()
        first.wait_release.set()
        close_worker.join(1)
        request_worker.join(1)
        assert not close_worker.is_alive()
        assert not request_worker.is_alive()
        assert response["result"]["generation"] == 2
    finally:
        first.wait_release.set()
        runtime.close()


def test_lifecycle_fence_keeps_generation_stable_until_admission_finishes():
    proc = FakeProcess(lambda _message: None)
    runtime = JsonlAppServerRuntime(["fake"], popen_factory=lambda *a, **k: proc)
    runtime.start()
    close_worker = threading.Thread(target=runtime.close)
    try:
        with runtime.lifecycle_fence() as generation:
            close_worker.start()
            time.sleep(0.05)
            assert close_worker.is_alive()
            assert runtime.generation == generation
        close_worker.join(0.5)
        assert not close_worker.is_alive()
        assert runtime.generation > generation
    finally:
        runtime.close()


def test_exit_callback_can_close_runtime_without_deadlocking_lifecycle_lock():
    proc = FakeProcess(lambda _message: None)
    runtime = JsonlAppServerRuntime(["fake"], popen_factory=lambda *a, **k: proc)
    exited = threading.Event()

    def close_from_exit():
        runtime.close()
        exited.set()

    runtime.on_exit = close_from_exit
    runtime.start()
    proc._returncode = 1
    proc.stdout.close()
    assert exited.wait(0.5)
    assert runtime._reader is not None
    runtime._reader.join(0.5)
    assert not runtime._reader.is_alive()


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
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"test_provider_app_server_runtime.py passed: {len(tests)} tests")
