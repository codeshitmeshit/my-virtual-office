#!/usr/bin/env python3
"""Focused tests for the Codex app-server bridge."""

import os
import stat
import sys
import tempfile
import threading
import time
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from providers.codex_bridge import CodexAppServerClient
import providers.codex_app_server as codex_app_server_module
from providers.codex_app_server import (
    CodexAppServerClient as CodexAppServerClientImpl,
    MAX_PRESTART_MESSAGES,
    PRESTART_VISIBILITY_DELAY_SEC,
    TERMINAL_DRAIN_TIMEOUT_SEC,
    _LateStartCleanup,
    _Operation,
)


FAKE_SERVER = r'''#!/usr/bin/env python3
import json
import os
import sys
import time

thread_id = "thr_fake"
turn_counts = {}

def send(value):
    sys.stdout.write(json.dumps(value) + "\n")
    sys.stdout.flush()

for raw in sys.stdin:
    msg = json.loads(raw)
    method = msg.get("method")
    request_id = msg.get("id")
    params = msg.get("params") or {}
    if method == "initialize":
        if not params.get("capabilities", {}).get("experimentalApi"):
            send({"id": request_id, "error": {"message": "experimental api capability missing"}})
            continue
        send({"id": request_id, "result": {"userAgent": "fake"}})
    elif method == "initialized":
        pass
    elif method == "thread/start":
        if os.environ.get("FAKE_CODEX_EXIT_THREAD_START"):
            sys.exit(17)
        flaky_path = os.environ.get("FAKE_CODEX_FLAKY_THREAD_START")
        if flaky_path:
            try:
                with open(flaky_path, "x") as marker:
                    marker.write("seen")
                continue
            except FileExistsError:
                pass
        send({"id": request_id, "result": {"thread": {"id": thread_id}}})
    elif method == "thread/resume":
        send({"id": request_id, "result": {"thread": {"id": params["threadId"]}}})
    elif method == "turn/start":
        if params.get("summary") != "detailed":
            send({"id": request_id, "error": {"message": "reasoning summary was not requested"}})
            continue
        prompt = params["input"][0]["text"]
        if "inspect image" in prompt and not any(item.get("type") == "localImage" for item in params["input"]):
            send({"id": request_id, "error": {"message": "local image input missing"}})
            continue
        if "hang forever" in prompt:
            send({"id": request_id, "result": {"turn": {"id": "turn_hang"}}})
            send({"method": "turn/started", "params": {"threadId": params["threadId"], "turn": {"id": "turn_hang"}}})
            continue
        if "stale start before response" in prompt:
            stale_turn_id = "turn_stale"
            turn_id = "turn_race"
            send({"method": "turn/started", "params": {"threadId": params["threadId"], "turn": {"id": stale_turn_id}}})
            send({"method": "item/agentMessage/delta", "params": {"threadId": params["threadId"], "turnId": stale_turn_id, "delta": "stale reply"}})
            send({"method": "turn/started", "params": {"threadId": params["threadId"], "turn": {"id": turn_id}}})
            item = {"id": "msg_race", "type": "agentMessage", "text": "current reply"}
            send({"method": "item/completed", "params": {"threadId": params["threadId"], "turnId": turn_id, "item": item}})
            send({"method": "turn/completed", "params": {"threadId": params["threadId"], "turn": {"id": turn_id, "status": "completed", "items": [item]}}})
            send({"id": request_id, "result": {"turn": {"id": turn_id}}})
            continue
        if "overflow before response" in prompt:
            turn_id = "turn_overflow"
            for index in range(513):
                send({"method": "item/reasoning/summaryTextDelta", "params": {"threadId": params["threadId"], "turnId": turn_id, "itemId": "reason_overflow", "summaryIndex": 0, "delta": str(index)}})
            send({"id": request_id, "result": {"turn": {"id": turn_id}}})
            continue
        if "delayed turn start response" in prompt:
            turn_id = "turn_delayed"
            time.sleep(1.5)
            send({"id": request_id, "result": {"turn": {"id": turn_id}}})
            send({"method": "turn/started", "params": {"threadId": params["threadId"], "turn": {"id": turn_id}}})
            item = {"id": "msg_delayed", "type": "agentMessage", "text": "delayed reply"}
            send({"method": "item/completed", "params": {"threadId": params["threadId"], "turnId": turn_id, "item": item}})
            send({"method": "turn/completed", "params": {"threadId": params["threadId"], "turn": {"id": turn_id, "status": "completed", "items": [item]}}})
            continue
        if "late response after timeout" in prompt:
            turn_id = "turn_late_timeout"
            time.sleep(0.3)
            send({"id": request_id, "result": {"turn": {"id": turn_id}}})
            continue
        if "stale candidate before timeout" in prompt:
            stale_turn_id = "turn_stale_timeout"
            send({"method": "turn/started", "params": {"threadId": params["threadId"], "turn": {"id": stale_turn_id}}})
            time.sleep(0.3)
            send({"id": request_id, "result": {"turn": {"id": "turn_authoritative_timeout"}}})
            continue
        if "empty turn id response" in prompt:
            stale_turn_id = "turn_empty_stale"
            send({"method": "turn/started", "params": {"threadId": params["threadId"], "turn": {"id": stale_turn_id}}})
            item = {"id": "msg_empty_stale", "type": "agentMessage", "text": "must not be accepted"}
            send({"method": "item/completed", "params": {"threadId": params["threadId"], "turnId": stale_turn_id, "item": item}})
            send({"id": request_id, "result": {"turn": {}}})
            continue
        if "empty turn id without notifications" in prompt:
            send({"id": request_id, "result": {"turn": {}}})
            continue
        if "start error after events" in prompt:
            turn_id = "turn_start_error"
            send({"method": "turn/started", "params": {"threadId": params["threadId"], "turn": {"id": turn_id}}})
            send({"id": 903, "method": "item/commandExecution/requestApproval", "params": {"threadId": params["threadId"], "turnId": turn_id, "itemId": "cmd_error"}})
            send({"id": request_id, "error": {"message": "turn start rejected after events"}})
            continue
        turn_base = "turn_permissions" if "permissions" in prompt else "turn_approval" if "approval" in prompt else "turn_input" if "question" in prompt else "turn_ok"
        turn_counts[turn_base] = turn_counts.get(turn_base, 0) + 1
        turn_id = turn_base if turn_counts[turn_base] == 1 else f"{turn_base}_{turn_counts[turn_base]}"
        send({"id": request_id, "result": {"turn": {"id": turn_id}}})
        send({"method": "turn/started", "params": {"threadId": params["threadId"], "turn": {"id": turn_id}}})
        if "approval" in prompt:
            send({"id": 900, "method": "item/commandExecution/requestApproval", "params": {"threadId": params["threadId"], "turnId": turn_id, "itemId": "cmd_1"}})
        elif "permissions" in prompt:
            send({"id": 902, "method": "item/permissions/requestApproval", "params": {"threadId": params["threadId"], "turnId": turn_id, "itemId": "perm_1", "permissions": {"fileSystem": {"write": ["/tmp/project"]}, "network": False}}})
        elif "question" in prompt:
            send({"id": 901, "method": "item/tool/requestUserInput", "params": {"threadId": params["threadId"], "turnId": turn_id, "itemId": "question_1", "questions": [{"id": "name", "label": "Name"}]}})
        else:
            reasoning = {"id": "reason_1", "type": "reasoning", "status": "inProgress"}
            send({"method": "item/started", "params": {"threadId": params["threadId"], "turnId": turn_id, "item": reasoning}})
            delta_index = 0
            for section_index, section_size in enumerate((7, 7, 6)):
                if section_index:
                    send({"method": "item/reasoning/summaryPartAdded", "params": {"threadId": params["threadId"], "turnId": turn_id, "itemId": "reason_1", "summaryIndex": section_index}})
                for _ in range(section_size):
                    send({"method": "item/reasoning/summaryTextDelta", "params": {"threadId": params["threadId"], "turnId": turn_id, "itemId": "reason_1", "summaryIndex": section_index, "delta": "part-%s " % delta_index}})
                    delta_index += 1
            send({"method": "item/reasoning/textDelta", "params": {"threadId": params["threadId"], "turnId": turn_id, "itemId": "reason_1", "delta": "raw-supported "}})
            reasoning.update({"status": "completed", "summary": ["first section", "second section", "third section"]})
            send({"method": "item/completed", "params": {"threadId": params["threadId"], "turnId": turn_id, "item": reasoning}})
            command = {"id": "cmd_1", "type": "commandExecution", "status": "inProgress", "command": "printf test"}
            send({"method": "item/started", "params": {"threadId": params["threadId"], "turnId": turn_id, "item": command}})
            send({"method": "item/commandExecution/outputDelta", "params": {"threadId": params["threadId"], "turnId": turn_id, "itemId": "cmd_1", "delta": "test"}})
            command["status"] = "completed"
            send({"method": "item/completed", "params": {"threadId": params["threadId"], "turnId": turn_id, "item": command}})
            item = {"id": "msg_1", "type": "agentMessage", "text": "real fake reply"}
            change = {"id": "file_1", "type": "fileChange", "status": "completed", "changes": [{"path": "app/demo.py", "kind": "update", "diff": ""}, {"file": "app/legacy.py"}, {"uri": "file:///tmp/out.txt"}]}
            send({"method": "item/completed", "params": {"threadId": params["threadId"], "turnId": turn_id, "item": item}})
            send({"method": "item/completed", "params": {"threadId": params["threadId"], "turnId": turn_id, "item": change}})
            send({"method": "thread/tokenUsage/updated", "params": {"threadId": params["threadId"], "tokenUsage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}}})
            send({"method": "turn/completed", "params": {"threadId": params["threadId"], "turn": {"id": turn_id, "status": "completed", "items": [item, change]}}})
    elif request_id == 900:
        if msg.get("result", {}).get("decision") in ("accept", "acceptForSession"):
            item = {"id": "msg_approval", "type": "agentMessage", "text": "approved reply"}
            send({"method": "item/completed", "params": {"threadId": thread_id, "turnId": "turn_approval", "item": item}})
            send({"method": "turn/completed", "params": {"threadId": thread_id, "turn": {"id": "turn_approval", "status": "completed", "items": [item]}}})
        else:
            send({"method": "turn/completed", "params": {"threadId": thread_id, "turn": {"id": "turn_approval", "status": "interrupted", "items": []}}})
    elif request_id == 901:
        answer = msg.get("result", {}).get("answers", {}).get("name", {}).get("answers", ["unknown"])[0]
        item = {"id": "msg_input", "type": "agentMessage", "text": "hello " + answer}
        send({"method": "item/completed", "params": {"threadId": thread_id, "turnId": "turn_input", "item": item}})
        send({"method": "turn/completed", "params": {"threadId": thread_id, "turn": {"id": "turn_input", "status": "completed", "items": [item]}}})
    elif request_id == 902:
        permissions = msg.get("result", {}).get("permissions", {})
        if permissions.get("fileSystem") and permissions.get("network") is False:
            item = {"id": "msg_permissions", "type": "agentMessage", "text": "permissions approved"}
            send({"method": "item/completed", "params": {"threadId": thread_id, "turnId": "turn_permissions", "item": item}})
            send({"method": "turn/completed", "params": {"threadId": thread_id, "turn": {"id": "turn_permissions", "status": "completed", "items": [item]}}})
        else:
            send({"method": "turn/completed", "params": {"threadId": thread_id, "turn": {"id": "turn_permissions", "status": "interrupted", "items": []}}})
    elif method == "thread/compact/start":
        send({"id": request_id, "result": {}})
        send({"method": "thread/compacted", "params": {"threadId": params["threadId"]}})
    elif method == "turn/interrupt":
        marker_path = os.environ.get("FAKE_CODEX_INTERRUPT_MARKER")
        if marker_path:
            with open(marker_path, "w") as marker:
                marker.write(str(params.get("turnId") or ""))
        interrupt_delay = float(os.environ.get("FAKE_CODEX_INTERRUPT_DELAY") or 0)
        if interrupt_delay:
            time.sleep(interrupt_delay)
        send({"id": request_id, "result": {}})
        send({"method": "turn/completed", "params": {"threadId": params["threadId"], "turn": {"id": params.get("turnId"), "status": "interrupted", "items": []}}})
'''


def make_fake_codex(tmp):
    path = os.path.join(tmp, "codex")
    with open(path, "w") as f:
        f.write(FAKE_SERVER)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


def wait_for_file(path, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return True
        time.sleep(0.01)
    return os.path.exists(path) and os.path.getsize(path) > 0


def test_thread_start_timeout_restarts_app_server_once():
    with tempfile.TemporaryDirectory() as tmp:
        marker = os.path.join(tmp, "flaky-thread-start")
        old = os.environ.get("FAKE_CODEX_FLAKY_THREAD_START")
        old_timeout = os.environ.get("VO_CODEX_START_TIMEOUT_SEC")
        os.environ["FAKE_CODEX_FLAKY_THREAD_START"] = marker
        os.environ["VO_CODEX_START_TIMEOUT_SEC"] = "0.2"
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        try:
            result = client.execute("change one file", timeout_sec=5)
            assert result["ok"] is True
            assert result["reply"] == "real fake reply"
            assert os.path.exists(marker)
        finally:
            client.close()
            if old is None:
                os.environ.pop("FAKE_CODEX_FLAKY_THREAD_START", None)
            else:
                os.environ["FAKE_CODEX_FLAKY_THREAD_START"] = old
            if old_timeout is None:
                os.environ.pop("VO_CODEX_START_TIMEOUT_SEC", None)
            else:
                os.environ["VO_CODEX_START_TIMEOUT_SEC"] = old_timeout


def test_process_exit_during_thread_start_propagates_without_waiting_for_rpc_timeout():
    with tempfile.TemporaryDirectory() as tmp:
        old = os.environ.get("FAKE_CODEX_EXIT_THREAD_START")
        os.environ["FAKE_CODEX_EXIT_THREAD_START"] = "1"
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        started = time.monotonic()
        try:
            result = client.execute("change one file", timeout_sec=5)
            assert result["status"] == "bridge_unavailable"
            assert time.monotonic() - started < 1
        finally:
            client.close()
            if old is None:
                os.environ.pop("FAKE_CODEX_EXIT_THREAD_START", None)
            else:
                os.environ["FAKE_CODEX_EXIT_THREAD_START"] = old


def test_start_timeout_does_not_restart_runtime_with_unrelated_active_turn():
    with tempfile.TemporaryDirectory() as tmp:
        client = CodexAppServerClientImpl(tmp, binary=make_fake_codex(tmp), max_concurrent_turns=2)
        active = _Operation("thr-active")
        client._operations[active.thread_id] = active
        restart_calls = []
        client._request = lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("startup stalled"))
        client._restart_runtime = lambda: restart_calls.append(True)
        try:
            try:
                client._request_with_restart("thread/resume", {"threadId": "thr-stalled"}, timeout=0.01)
                raise AssertionError("expected startup timeout")
            except TimeoutError as exc:
                assert "startup stalled" in str(exc)
            assert restart_calls == []
            assert client._operations[active.thread_id] is active
            assert active.completed.is_set() is False
        finally:
            client.close()


def test_reasoning_summary_defaults_to_detailed():
    with tempfile.TemporaryDirectory() as tmp:
        old = os.environ.pop("VO_CODEX_REASONING_SUMMARY", None)
        try:
            client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
            try:
                assert client.reasoning_summary == "detailed"
            finally:
                client.close()
        finally:
            if old is not None:
                os.environ["VO_CODEX_REASONING_SUMMARY"] = old


def test_execute_collects_reply_files_and_thread():
    with tempfile.TemporaryDirectory() as tmp:
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        try:
            result = client.execute("change one file", timeout_sec=5)
            assert result["ok"] is True
            assert result["status"] == "completed"
            assert result["threadId"] == "thr_fake"
            assert result["turnId"] == "turn_ok"
            assert result["reply"] == "real fake reply"
            assert result["modifiedFiles"] == ["app/demo.py", "app/legacy.py", "file:///tmp/out.txt"]
            assert result["terminalFence"]["terminalObserved"] is True
            assert result["terminalFence"]["terminalFenceFallbacks"] == 0

            resumed = client.execute("continue", thread_id=result["threadId"], timeout_sec=5)
            assert resumed["ok"] is True
            assert resumed["threadId"] == result["threadId"]
        finally:
            client.close()


def test_turn_start_response_rejects_stale_notifications_that_arrive_first():
    with tempfile.TemporaryDirectory() as tmp:
        events = []
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        try:
            result = client.execute(
                "stale start before response",
                timeout_sec=5,
                event_callback=events.append,
            )
            assert result["ok"] is True
            assert result["status"] == "completed"
            assert result["turnId"] == "turn_race"
            assert result["reply"] == "current reply"
            assert events
            assert all(event.get("turnId") != "turn_stale" for event in events)
            assert client.terminal_diagnostics("thr_fake")["lateNotifications"] == 2
        finally:
            client.close()


def test_prestart_message_buffer_is_bounded_and_fails_closed():
    operation = _Operation("thr-prestart-bound")
    for index in range(MAX_PRESTART_MESSAGES):
        assert operation.defer_native_notification(
            "item/reasoning/summaryTextDelta",
            {"threadId": operation.thread_id, "turnId": "turn-bound", "delta": str(index)},
        ) is True
    assert operation.defer_native_notification(
        "item/reasoning/summaryTextDelta",
        {"threadId": operation.thread_id, "turnId": "turn-bound", "delta": "overflow"},
    ) is True

    assert operation.confirm_turn_identity("turn-bound") is False
    assert operation.fence_diagnostics()["prestartMessageOverflows"] == 1


def test_prestart_starting_event_is_rejected_after_turn_identity_is_confirmed():
    events = []
    operation = _Operation("thr-starting-race", event_callback=events.append)
    assert operation.confirm_turn_identity("turn-confirmed") is True
    assert operation.emit_prestart_starting() is False
    assert events == []


def test_replay_detects_overflow_that_occurs_after_identity_confirmation():
    client = object.__new__(CodexAppServerClientImpl)
    operation = _Operation("thr-replay-overflow")
    operation.defer_native_notification(
        "item/reasoning/summaryTextDelta",
        {"threadId": operation.thread_id, "turnId": "turn-replay", "delta": "initial"},
    )
    assert operation.confirm_turn_identity("turn-replay") is True
    injected = {"done": False}

    def handle_notification(_operation, _method, _params):
        if injected["done"]:
            return
        injected["done"] = True
        for index in range(MAX_PRESTART_MESSAGES + 1):
            operation.defer_native_notification(
                "item/reasoning/summaryTextDelta",
                {"threadId": operation.thread_id, "turnId": "turn-replay", "delta": str(index)},
            )

    client._handle_operation_notification = handle_notification
    assert client._replay_prestart_messages(operation) is False
    assert operation.fence_diagnostics()["prestartMessageOverflows"] == 1


def test_replay_overflow_rejects_detached_prestart_server_requests():
    client = object.__new__(CodexAppServerClientImpl)
    sent = []
    client._send = lambda message: sent.append(message)
    operation = _Operation("thr-request-overflow", allow_interaction=True)
    for index in range(MAX_PRESTART_MESSAGES):
        assert operation.defer_native_message("server_request", {
            "id": 1000 + index,
            "method": "item/commandExecution/requestApproval",
            "params": {
                "threadId": operation.thread_id,
                "turnId": "turn-request-overflow",
                "itemId": f"cmd-{index}",
            },
        }) == "deferred"
    assert operation.defer_native_notification(
        "item/reasoning/summaryTextDelta",
        {"threadId": operation.thread_id, "turnId": "turn-request-overflow", "delta": "overflow"},
    ) is True
    assert operation.confirm_turn_identity("turn-request-overflow") is False

    assert client._replay_prestart_messages(operation) is False
    assert len(sent) == MAX_PRESTART_MESSAGES
    assert all(message["result"]["decision"] == "cancel" for message in sent)


def test_replay_overflow_failure_rejects_request_already_registered_for_approval():
    client = object.__new__(CodexAppServerClientImpl)
    client.profile = "default"
    client._operations_lock = threading.Lock()
    client._terminal_operations = OrderedDict()
    client._approval_lock = threading.Condition()
    client._pending_approvals = {}
    client._late_start_lock = threading.Lock()
    client._late_start_cleanups = OrderedDict()
    sent = []
    client._send = lambda message: sent.append(message)
    client._allocate_id = lambda: 9999

    operation = _Operation("thr-replayed-approval", allow_interaction=True)
    client._operations = {operation.thread_id: operation}
    operation.defer_native_message("server_request", {
        "id": 7,
        "method": "item/commandExecution/requestApproval",
        "params": {
            "threadId": operation.thread_id,
            "turnId": "turn-replayed-approval",
            "itemId": "cmd-replayed",
        },
    })
    operation.defer_native_notification(
        "item/reasoning/summaryTextDelta",
        {"threadId": operation.thread_id, "turnId": "turn-replayed-approval", "delta": "trigger"},
    )
    assert operation.confirm_turn_identity("turn-replayed-approval") is True

    def inject_overflow(_operation, _method, _params):
        for index in range(MAX_PRESTART_MESSAGES + 1):
            operation.defer_native_notification(
                "item/reasoning/summaryTextDelta",
                {"threadId": operation.thread_id, "turnId": operation.turn_id, "delta": str(index)},
            )

    client._handle_operation_notification = inject_overflow
    assert client._replay_prestart_messages(operation) is False
    assert operation.has_pending_request("7") is True

    client._fail_prestart_operation(operation, {
        "ok": False,
        "status": "protocol_error",
        "error": "replay overflow",
    }, [operation.turn_id])
    approval_responses = [message for message in sent if message.get("id") == 7]
    assert len(approval_responses) == 1
    assert approval_responses[0]["result"]["decision"] == "cancel"
    assert operation.pending_requests == {}
    assert client.pending_approval(operation.thread_id)["pending"] is None


def test_prestart_overflow_interrupts_the_authoritative_native_turn():
    with tempfile.TemporaryDirectory() as tmp:
        marker = os.path.join(tmp, "interrupted-turn")
        old_marker = os.environ.get("FAKE_CODEX_INTERRUPT_MARKER")
        os.environ["FAKE_CODEX_INTERRUPT_MARKER"] = marker
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        try:
            result = client.execute("overflow before response", timeout_sec=5)
            assert result["ok"] is False
            assert result["status"] == "protocol_error"
            assert result["terminalFence"]["prestartMessageOverflows"] == 1
            assert wait_for_file(marker)
            with open(marker) as stream:
                assert stream.read() == "turn_overflow"
        finally:
            client.close()
            if old_marker is None:
                os.environ.pop("FAKE_CODEX_INTERRUPT_MARKER", None)
            else:
                os.environ["FAKE_CODEX_INTERRUPT_MARKER"] = old_marker


def test_delayed_turn_start_response_emits_bounded_progress_without_orphaning_the_turn():
    with tempfile.TemporaryDirectory() as tmp:
        events = []
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        try:
            client._ensure_started()
            started = time.monotonic()
            result = client.execute(
                "delayed turn start response",
                timeout_sec=5,
                event_callback=lambda event: events.append((time.monotonic() - started, event)),
            )
            elapsed = time.monotonic() - started
            assert result["ok"] is True
            assert result["status"] == "completed"
            assert result["turnId"] == "turn_delayed"
            assert result["reply"] == "delayed reply"
            assert elapsed >= 1.4
            starting_events = [
                (delay, event) for delay, event in events
                if event.get("type") == "turn" and event.get("status") == "starting"
            ]
            assert len(starting_events) == 1
            delay, starting_event = starting_events[0]
            assert PRESTART_VISIBILITY_DELAY_SEC * 0.8 <= delay < 1.3
            assert starting_event["turnId"] == ""
        finally:
            client.close()


def test_cancel_before_turn_start_response_interrupts_the_confirmed_turn():
    with tempfile.TemporaryDirectory() as tmp:
        marker = os.path.join(tmp, "interrupted-turn")
        old_marker = os.environ.get("FAKE_CODEX_INTERRUPT_MARKER")
        os.environ["FAKE_CODEX_INTERRUPT_MARKER"] = marker
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        result = {}
        events = []
        worker = threading.Thread(target=lambda: result.update(client.execute(
            "delayed turn start response",
            timeout_sec=5,
            event_callback=events.append,
        )))
        try:
            worker.start()
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                with client._operations_lock:
                    if "thr_fake" in client._operations:
                        break
                time.sleep(0.01)
            assert client.cancel("thr_fake") is True
            worker.join(3)
            assert not worker.is_alive()
            assert result["ok"] is False
            assert result["status"] == "cancelled"
            assert all(event.get("status") != "starting" for event in events)
            assert wait_for_file(marker)
            with open(marker) as stream:
                assert stream.read() == "turn_delayed"
        finally:
            client.close()
            worker.join(1)
            if old_marker is None:
                os.environ.pop("FAKE_CODEX_INTERRUPT_MARKER", None)
            else:
                os.environ["FAKE_CODEX_INTERRUPT_MARKER"] = old_marker


def test_turn_start_timeout_reconciles_late_response_before_reusing_thread():
    with tempfile.TemporaryDirectory() as tmp:
        marker = os.path.join(tmp, "interrupted-turn")
        old_marker = os.environ.get("FAKE_CODEX_INTERRUPT_MARKER")
        old_interrupt_delay = os.environ.get("FAKE_CODEX_INTERRUPT_DELAY")
        old_timeout = codex_app_server_module.TURN_START_RESPONSE_TIMEOUT_SEC
        os.environ["FAKE_CODEX_INTERRUPT_MARKER"] = marker
        os.environ["FAKE_CODEX_INTERRUPT_DELAY"] = "0.3"
        codex_app_server_module.TURN_START_RESPONSE_TIMEOUT_SEC = 0.1
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        try:
            result = client.execute("late response after timeout", timeout_sec=5)
            assert result["ok"] is False
            assert result["status"] == "timeout"
            assert result["turnId"] == ""

            blocked = client.execute("continue", thread_id="thr_fake", timeout_sec=5)
            assert blocked["status"] == "busy"
            assert blocked["busyCode"] == "busy_by_late_turn_cleanup"

            assert wait_for_file(marker)
            with open(marker) as stream:
                assert stream.read() == "turn_late_timeout"
            still_stopping = client.execute("continue", thread_id="thr_fake", timeout_sec=5)
            assert still_stopping["busyCode"] == "busy_by_late_turn_cleanup"
            time.sleep(0.35)
            recovered = client.execute("continue", thread_id="thr_fake", timeout_sec=5)
            assert recovered["ok"] is True
        finally:
            client.close()
            codex_app_server_module.TURN_START_RESPONSE_TIMEOUT_SEC = old_timeout
            if old_marker is None:
                os.environ.pop("FAKE_CODEX_INTERRUPT_MARKER", None)
            else:
                os.environ["FAKE_CODEX_INTERRUPT_MARKER"] = old_marker
            if old_interrupt_delay is None:
                os.environ.pop("FAKE_CODEX_INTERRUPT_DELAY", None)
            else:
                os.environ["FAKE_CODEX_INTERRUPT_DELAY"] = old_interrupt_delay


def test_turn_start_timeout_does_not_expose_pre_response_candidate_turn_id():
    with tempfile.TemporaryDirectory() as tmp:
        marker = os.path.join(tmp, "interrupted-turn")
        old_marker = os.environ.get("FAKE_CODEX_INTERRUPT_MARKER")
        old_timeout = codex_app_server_module.TURN_START_RESPONSE_TIMEOUT_SEC
        os.environ["FAKE_CODEX_INTERRUPT_MARKER"] = marker
        codex_app_server_module.TURN_START_RESPONSE_TIMEOUT_SEC = 0.1
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        try:
            result = client.execute("stale candidate before timeout", timeout_sec=5)
            assert result["status"] == "timeout"
            assert result["turnId"] == ""
            assert wait_for_file(marker)
            with open(marker) as stream:
                assert stream.read() in {"turn_stale_timeout", "turn_authoritative_timeout"}
        finally:
            client.close()
            codex_app_server_module.TURN_START_RESPONSE_TIMEOUT_SEC = old_timeout
            if old_marker is None:
                os.environ.pop("FAKE_CODEX_INTERRUPT_MARKER", None)
            else:
                os.environ["FAKE_CODEX_INTERRUPT_MARKER"] = old_marker


def test_visible_prestart_progress_is_closed_by_terminal_failure_event():
    with tempfile.TemporaryDirectory() as tmp:
        old_timeout = codex_app_server_module.TURN_START_RESPONSE_TIMEOUT_SEC
        codex_app_server_module.TURN_START_RESPONSE_TIMEOUT_SEC = 1.2
        events = []
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        try:
            client._ensure_started()
            result = client.execute(
                "delayed turn start response",
                timeout_sec=5,
                event_callback=events.append,
            )
            assert result["status"] == "timeout"
            assert client.wait_for_terminal_callbacks("thr_fake", timeout=1) is True
            statuses = [event.get("status") for event in events if event.get("type") == "turn"]
            assert "starting" in statuses
            assert statuses[-1] == "failed"
        finally:
            client.close()
            codex_app_server_module.TURN_START_RESPONSE_TIMEOUT_SEC = old_timeout


def test_cancelled_prestart_timeout_reports_cancelled_terminal_outcome():
    with tempfile.TemporaryDirectory() as tmp:
        old_timeout = codex_app_server_module.TURN_START_RESPONSE_TIMEOUT_SEC
        codex_app_server_module.TURN_START_RESPONSE_TIMEOUT_SEC = 0.1
        events = []
        result = {}
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        worker = threading.Thread(target=lambda: result.update(client.execute(
            "late response after timeout",
            timeout_sec=5,
            event_callback=events.append,
        )))
        try:
            worker.start()
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                with client._operations_lock:
                    if "thr_fake" in client._operations:
                        break
                time.sleep(0.01)
            assert client.cancel("thr_fake") is True
            worker.join(1)
            assert result["status"] == "cancelled"
            assert client.wait_for_terminal_callbacks("thr_fake", timeout=1) is True
            turn_statuses = [event.get("status") for event in events if event.get("type") == "turn"]
            assert turn_statuses[-1] == "cancelled"
        finally:
            client.close()
            worker.join(1)
            codex_app_server_module.TURN_START_RESPONSE_TIMEOUT_SEC = old_timeout


def test_non_timeout_turn_start_error_fails_closed_and_interrupts_candidates():
    with tempfile.TemporaryDirectory() as tmp:
        marker = os.path.join(tmp, "interrupted-turn")
        old_marker = os.environ.get("FAKE_CODEX_INTERRUPT_MARKER")
        os.environ["FAKE_CODEX_INTERRUPT_MARKER"] = marker
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        try:
            result = client.execute("start error after events", timeout_sec=5, allow_interaction=True)
            assert result["status"] == "execution_failed"
            assert result["turnId"] == ""
            assert "turn start rejected" in str(result.get("error"))
            assert wait_for_file(marker)
            with open(marker) as stream:
                assert stream.read() == "turn_start_error"
            assert client.pending_approval("thr_fake")["pending"] is None
            assert client._late_start_cleanup_pending("thr_fake") is False
            recovered = client.execute("change one file", thread_id="thr_fake", timeout_sec=5)
            assert recovered["ok"] is True
        finally:
            client.close()
            if old_marker is None:
                os.environ.pop("FAKE_CODEX_INTERRUPT_MARKER", None)
            else:
                os.environ["FAKE_CODEX_INTERRUPT_MARKER"] = old_marker


def test_client_close_releases_running_operation_immediately():
    with tempfile.TemporaryDirectory() as tmp:
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        result = {}
        worker = threading.Thread(target=lambda: result.update(client.execute("hang forever", timeout_sec=30)))
        worker.start()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            with client._operations_lock:
                operation = client._operations.get("thr_fake")
            if operation and operation.turn_id == "turn_hang":
                break
            time.sleep(0.01)
        client.close()
        worker.join(1)
        assert not worker.is_alive()
        assert result["status"] == "bridge_unavailable"


def test_client_close_during_turn_start_preserves_bridge_unavailable_without_cleanup():
    with tempfile.TemporaryDirectory() as tmp:
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        result = {}
        worker = threading.Thread(target=lambda: result.update(client.execute(
            "delayed turn start response",
            timeout_sec=30,
        )))
        worker.start()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            with client._operations_lock:
                operation = client._operations.get("thr_fake")
            if operation and not operation.turn_id:
                break
            time.sleep(0.01)
        client.close()
        worker.join(1)
        assert not worker.is_alive()
        assert result["status"] == "bridge_unavailable"
        assert client._late_start_cleanup_pending("thr_fake") is False


def test_empty_turn_start_identity_fails_closed_and_interrupts_buffered_candidate():
    with tempfile.TemporaryDirectory() as tmp:
        marker = os.path.join(tmp, "interrupted-turn")
        old_marker = os.environ.get("FAKE_CODEX_INTERRUPT_MARKER")
        os.environ["FAKE_CODEX_INTERRUPT_MARKER"] = marker
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        try:
            result = client.execute("empty turn id response", timeout_sec=5)
            assert result["ok"] is False
            assert result["status"] == "protocol_error"
            assert result.get("reply") in {None, ""}
            assert wait_for_file(marker)
            with open(marker) as stream:
                assert stream.read() == "turn_empty_stale"
        finally:
            client.close()
            if old_marker is None:
                os.environ.pop("FAKE_CODEX_INTERRUPT_MARKER", None)
            else:
                os.environ["FAKE_CODEX_INTERRUPT_MARKER"] = old_marker


def test_empty_turn_start_identity_without_candidate_recovers_by_restarting_idle_runtime():
    with tempfile.TemporaryDirectory() as tmp:
        old_delay = codex_app_server_module.LATE_START_RECOVERY_DELAY_SEC
        codex_app_server_module.LATE_START_RECOVERY_DELAY_SEC = 0.2
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        try:
            result = client.execute("empty turn id without notifications", timeout_sec=5)
            assert result["status"] == "protocol_error"
            blocked = client.execute("continue", thread_id="thr_fake", timeout_sec=5)
            assert blocked["busyCode"] == "busy_by_late_turn_cleanup"
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline and client._late_start_cleanup_pending("thr_fake"):
                time.sleep(0.01)
            assert client._late_start_cleanup_pending("thr_fake") is False
            recovered = client.execute("continue", thread_id="thr_fake", timeout_sec=5)
            assert recovered["ok"] is True
        finally:
            client.close()
            codex_app_server_module.LATE_START_RECOVERY_DELAY_SEC = old_delay


def test_compaction_is_blocked_while_late_turn_cleanup_is_pending():
    with tempfile.TemporaryDirectory() as tmp:
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        cleanup = _LateStartCleanup(turn_id="turn-stopping", interrupt_sent=True)
        client._late_start_cleanups["thr_fake"] = cleanup
        try:
            result = client.compact("thr_fake", timeout_sec=5)
            assert result["status"] == "busy"
            assert result["busyCode"] == "busy_by_late_turn_cleanup"
        finally:
            client.close()


def test_compaction_rechecks_cleanup_after_waiting_for_the_thread_lock():
    with tempfile.TemporaryDirectory() as tmp:
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        held_lock = client._acquire_thread_lock("thr_fake")
        result = {}
        worker = threading.Thread(target=lambda: result.update(client.compact("thr_fake", timeout_sec=5)))
        try:
            worker.start()
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline:
                with client._thread_locks_guard:
                    references = client._thread_locks.get("thr_fake", {}).get("references", 0)
                if references >= 2:
                    break
                time.sleep(0.01)
            client._late_start_cleanups["thr_fake"] = _LateStartCleanup(turn_id="turn-stopping")
            client._release_thread_lock("thr_fake", held_lock)
            held_lock = None
            worker.join(1)
            assert result["busyCode"] == "busy_by_late_turn_cleanup"
        finally:
            if held_lock is not None:
                client._release_thread_lock("thr_fake", held_lock)
            client.close()
            worker.join(1)


def test_recovery_deadline_stops_new_admission_until_active_turns_drain():
    with tempfile.TemporaryDirectory() as tmp:
        old_delay = codex_app_server_module.LATE_START_RECOVERY_DELAY_SEC
        old_attempts = codex_app_server_module.LATE_START_RECOVERY_MAX_ATTEMPTS
        codex_app_server_module.LATE_START_RECOVERY_DELAY_SEC = 0.05
        codex_app_server_module.LATE_START_RECOVERY_MAX_ATTEMPTS = 1
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        active = _Operation("thr-active")
        client._operations[active.thread_id] = active
        cleanup = _LateStartCleanup()
        assert client._register_late_start_cleanup("thr-stuck", cleanup) is True
        try:
            client._schedule_late_start_recovery("thr-stuck", cleanup)
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline and not cleanup.force_recycle:
                time.sleep(0.01)
            assert cleanup.force_recycle is True
            blocked = client.execute("new work", timeout_sec=5)
            assert blocked["busyCode"] == "busy_by_late_turn_runtime_recovery"

            active.finish_without_event()
            with client._operations_lock:
                client._operations.pop(active.thread_id, None)
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline and client._late_start_cleanup_pending("thr-stuck"):
                time.sleep(0.01)
            assert client._late_start_cleanup_pending("thr-stuck") is False
        finally:
            client.close()
            codex_app_server_module.LATE_START_RECOVERY_DELAY_SEC = old_delay
            codex_app_server_module.LATE_START_RECOVERY_MAX_ATTEMPTS = old_attempts


def test_execute_rechecks_runtime_recovery_inside_generation_admission_fence():
    with tempfile.TemporaryDirectory() as tmp:
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        cleanup = _LateStartCleanup()
        assert client._register_late_start_cleanup("thr-stuck", cleanup) is True
        original_guard = client._execute_cleanup_guard
        checks = {"count": 0}

        def inject_recovery_before_inner_check(thread_id):
            checks["count"] += 1
            if checks["count"] == 2:
                cleanup.force_recycle = True
            return original_guard(thread_id)

        client._execute_cleanup_guard = inject_recovery_before_inner_check
        try:
            result = client.execute("new work", timeout_sec=5)
            assert result["busyCode"] == "busy_by_late_turn_runtime_recovery"
            assert checks["count"] == 2
            with client._operations_lock:
                assert client._operations == {}
        finally:
            client.close()


def test_compact_rechecks_runtime_recovery_inside_generation_admission_fence():
    with tempfile.TemporaryDirectory() as tmp:
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        cleanup = _LateStartCleanup()
        assert client._register_late_start_cleanup("thr-stuck", cleanup) is True
        original_guard = client._compact_cleanup_guard
        checks = {"count": 0}

        def inject_recovery_before_inner_check(thread_id):
            checks["count"] += 1
            if checks["count"] == 3:
                cleanup.force_recycle = True
            return original_guard(thread_id)

        client._compact_cleanup_guard = inject_recovery_before_inner_check
        try:
            result = client.compact("thr_fake", timeout_sec=5)
            assert result["busyCode"] == "busy_by_late_turn_runtime_recovery"
            assert checks["count"] == 3
            with client._operations_lock:
                assert client._operations == {}
        finally:
            client.close()


def test_execute_sends_image_attachment_as_local_image_input():
    with tempfile.TemporaryDirectory() as tmp:
        image_path = os.path.join(tmp, "latest.png")
        with open(image_path, "wb") as stream:
            stream.write(b"not-a-real-image-needed-for-protocol-test")
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        try:
            result = client.execute(
                "inspect image",
                attachments=[{"path": image_path, "mimeType": "image/png", "name": "latest.png"}],
                timeout_sec=5,
            )
            assert result["ok"] is True
            assert result["reply"] == "real fake reply"
        finally:
            client.close()


def test_execute_exposes_run_state_tools_thinking_and_token_usage():
    with tempfile.TemporaryDirectory() as tmp:
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        try:
            result = client.execute("change one file", timeout_sec=5)
            assert result["ok"] is True
            assert result["sessionId"] == "thr_fake"
            assert result["runId"] == "turn_ok"
            assert result["reply"] == "real fake reply"
            assert "raw-supported" in result["thinking"]
            assert any(tool["id"] == "cmd_1" and tool["name"] == "shell" for tool in result["tools"])
            assert any(tool["name"] == "file changes" for tool in result["tools"])
            assert result["tokenUsage"] == {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}
        finally:
            client.close()


def test_approval_request_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        try:
            result = client.execute("needs approval", timeout_sec=5)
            assert result["ok"] is False
            assert result["status"] == "needs_human_intervention"
            assert result["needsHumanIntervention"] is True
        finally:
            client.close()


def test_manual_compaction_keeps_thread():
    with tempfile.TemporaryDirectory() as tmp:
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        try:
            result = client.compact("thr_fake", timeout_sec=5)
            assert result["ok"] is True
            assert result["status"] == "compacted"
            assert result["threadId"] == "thr_fake"
        finally:
            client.close()


def test_timeout_returns_terminal_result():
    with tempfile.TemporaryDirectory() as tmp:
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        try:
            result = client.execute("hang forever", timeout_sec=1)
            assert result["ok"] is False
            assert result["status"] == "timeout"
            assert result["turnId"] == "turn_hang"
        finally:
            client.close()


def test_activity_events_are_incremental_and_correlated():
    with tempfile.TemporaryDirectory() as tmp:
        events = []
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        try:
            result = client.execute("change one file", timeout_sec=5, event_callback=events.append)
            assert result["ok"] is True
            activities = [event for event in events if event["type"] == "activity" and event.get("itemId") == "cmd_1"]
            assert [event["status"] for event in activities] == ["running", "running", "done"]
            assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
            assert all(event["threadId"] == "thr_fake" for event in events)
            assert len({event["operationId"] for event in events}) == 1
        finally:
            client.close()


def test_reasoning_events_are_distinct_and_sectioned():
    with tempfile.TemporaryDirectory() as tmp:
        events = []
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        try:
            result = client.execute("reason about one file", timeout_sec=5, event_callback=events.append)
            assert result["ok"] is True
            reasoning = [event for event in events if event["type"] == "reasoning"]
            deltas = [event for event in reasoning if event.get("text", "").startswith("part-")]
            boundaries = [event for event in reasoning if event.get("boundary")]
            raw = [event for event in reasoning if event.get("deltaKind") == "raw"]
            assert len(deltas) == 20
            assert len(boundaries) == 2
            assert len(raw) == 1
            assert reasoning[-1]["status"] == "done"
            assert reasoning[-1]["replace"] is True
            assert reasoning[-1]["text"] == "first section\n\nsecond section\n\nthird section"
            assert not any(event.get("name") == "reasoning" for event in events if event["type"] == "activity")
        finally:
            client.close()


def test_interactive_approval_continues_original_turn():
    with tempfile.TemporaryDirectory() as tmp:
        events = []
        result = {}
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        worker = threading.Thread(target=lambda: result.update(client.execute(
            "needs approval", timeout_sec=5, event_callback=events.append, allow_interaction=True
        )))
        try:
            worker.start()
            deadline = time.time() + 3
            pending = None
            while time.time() < deadline and not pending:
                pending = next((event for event in events if event.get("status") == "pending"), None)
                time.sleep(0.02)
            assert pending
            provider_pending = client.pending_approval()
            assert provider_pending["pending_count"] == 1
            assert provider_pending["pending"]["status"] == "pending"
            assert client.respond("thr_fake", pending["interactionId"], "acceptForSession") is True
            worker.join(3)
            assert result["ok"] is True
            assert result["turnId"] == "turn_approval"
            assert result["reply"] == "approved reply"
            assert client.pending_approval()["pending_count"] == 0
        finally:
            client.close()


def test_reference_style_approval_response_continues_turn():
    with tempfile.TemporaryDirectory() as tmp:
        events = []
        result = {}
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        worker = threading.Thread(target=lambda: result.update(client.execute(
            "needs approval", timeout_sec=5, event_callback=events.append, allow_interaction=True
        )))
        try:
            worker.start()
            deadline = time.time() + 3
            pending = None
            while time.time() < deadline and not pending:
                pending_result = client.pending_approval()
                pending = pending_result.get("pending")
                time.sleep(0.02)
            assert pending
            submitted = client.respond_approval(pending["id"], "acceptForSession")
            assert submitted["ok"] is True
            assert submitted["choice"] == "acceptForSession"
            assert submitted["response"] == {"decision": "acceptForSession"}
            worker.join(3)
            assert result["ok"] is True
            assert result["reply"] == "approved reply"
            assert result["approval"]["status"] == "approved"
        finally:
            client.close()


def test_interactive_permissions_approval_continues_original_turn():
    with tempfile.TemporaryDirectory() as tmp:
        events = []
        result = {}
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        worker = threading.Thread(target=lambda: result.update(client.execute(
            "needs permissions", timeout_sec=5, event_callback=events.append, allow_interaction=True
        )))
        try:
            worker.start()
            deadline = time.time() + 3
            pending = None
            while time.time() < deadline and not pending:
                pending = client.pending_approval().get("pending")
                time.sleep(0.02)
            assert pending
            assert pending["kind"] == "permissions"
            submitted = client.respond_approval(pending["id"], "approve")
            assert submitted["ok"] is True
            assert submitted["response"] == {"permissions": {"fileSystem": {"write": ["/tmp/project"]}, "network": False}, "scope": "turn"}
            worker.join(3)
            assert result["ok"] is True
            assert result["reply"] == "permissions approved"
            assert result["approval"]["status"] == "approved"
        finally:
            client.close()


def test_approval_response_mapping_covers_reference_shapes():
    command_accept = CodexAppServerClientImpl._approval_response("item/commandExecution/requestApproval", {}, "approve")
    command_accept_for_session = CodexAppServerClientImpl._approval_response("item/commandExecution/requestApproval", {}, "acceptForSession")
    command_cancel = CodexAppServerClientImpl._approval_response("item/commandExecution/requestApproval", {}, "cancel")
    file_accept = CodexAppServerClientImpl._approval_response("item/fileChange/requestApproval", {}, "approve")
    permissions_accept = CodexAppServerClientImpl._approval_response(
        "item/permissions/requestApproval",
        {"permissions": {"fileSystem": {"write": ["/tmp/project"]}, "network": True, "other": "ignored"}},
        "approve",
    )
    permissions_accept_for_session = CodexAppServerClientImpl._approval_response(
        "item/permissions/requestApproval",
        {"permissions": {"fileSystem": {"write": ["/tmp/project"]}, "network": False}},
        "acceptForSession",
    )
    permissions_cancel = CodexAppServerClientImpl._approval_response(
        "item/permissions/requestApproval",
        {"permissions": {"fileSystem": {"write": ["/tmp/project"]}, "network": True}},
        "cancel",
    )
    legacy_patch = CodexAppServerClientImpl._approval_response("applyPatchApproval", {}, "approve")

    assert command_accept == {"decision": "accept"}
    assert command_accept_for_session == {"decision": "acceptForSession"}
    assert command_cancel == {"decision": "cancel"}
    assert file_accept == {"decision": "accept"}
    assert permissions_accept == {"permissions": {"fileSystem": {"write": ["/tmp/project"]}, "network": True}, "scope": "turn"}
    assert permissions_accept_for_session == {"permissions": {"fileSystem": {"write": ["/tmp/project"]}, "network": False}, "scope": "session"}
    assert permissions_cancel == {"permissions": {"fileSystem": None, "network": None}, "scope": "turn"}
    assert legacy_patch == {"decision": "approved"}


def test_interactive_user_input_continues_original_turn():
    with tempfile.TemporaryDirectory() as tmp:
        events = []
        result = {}
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        worker = threading.Thread(target=lambda: result.update(client.execute(
            "ask question", timeout_sec=5, event_callback=events.append, allow_interaction=True
        )))
        try:
            worker.start()
            deadline = time.time() + 3
            pending = None
            while time.time() < deadline and not pending:
                pending = next((event for event in events if event.get("interactionType") == "input"), None)
                time.sleep(0.02)
            assert pending
            assert client.respond("thr_fake", pending["interactionId"], "accept", {"name": "VO"}) is True
            worker.join(3)
            assert result["ok"] is True
            assert result["reply"] == "hello VO"
        finally:
            client.close()


def test_terminal_fence_releases_immediately_after_prior_callback_exits():
    entered = threading.Event()
    release = threading.Event()

    def callback(event):
        if event["type"] == "reasoning":
            entered.set()
            release.wait(1)

    operation = _Operation("thr-fence", event_callback=callback)
    prior = threading.Thread(target=lambda: operation.emit("reasoning", text="before terminal"))
    prior.start()
    assert entered.wait(0.5)
    terminal = threading.Thread(target=lambda: operation.emit("turn", terminal=True, status="completed"))
    terminal.start()
    terminal.join(0.2)
    assert not operation.completed.is_set()
    release.set()
    prior.join(0.5)
    assert operation.completed.wait(0.1)
    assert operation.fence_diagnostics()["terminalFenceFallbacks"] == 0


def test_callback_failure_is_contained_and_reader_serves_next_turn():
    with tempfile.TemporaryDirectory() as tmp:
        client = CodexAppServerClientImpl(tmp, binary=make_fake_codex(tmp))

        def fail_approval_persistence(event):
            if event.get("type") == "interaction" and event.get("status") == "pending":
                raise OSError("approval fsync failed")

        try:
            failed = client.execute(
                "needs approval",
                timeout_sec=5,
                event_callback=fail_approval_persistence,
                allow_interaction=True,
            )
            assert failed["ok"] is False
            assert failed["status"] == "event_callback_failed"
            assert failed["terminalFence"]["callbackErrors"] == 1

            recovered = client.execute("change one file", timeout_sec=5)
            assert recovered["ok"] is True
            assert recovered["reply"] == "real fake reply"
        finally:
            client.close()


def test_terminal_fence_has_bounded_fallback_for_stuck_prior_callback():
    entered = threading.Event()
    release = threading.Event()

    def callback(event):
        if event["type"] == "reasoning":
            entered.set()
            release.wait(1)

    operation = _Operation("thr-fallback", event_callback=callback)
    prior = threading.Thread(target=lambda: operation.emit("reasoning", text="stuck"))
    prior.start()
    assert entered.wait(0.5)
    operation.emit("turn", terminal=True, status="completed")
    assert operation.completed.wait(TERMINAL_DRAIN_TIMEOUT_SEC + 0.2)
    assert operation.fence_diagnostics()["terminalFenceFallbacks"] == 1
    release.set()
    prior.join(0.5)


def test_terminal_fence_bounds_terminal_callback_and_releases_reader():
    entered = threading.Event()
    release = threading.Event()

    def callback(event):
        if event["type"] == "turn":
            entered.set()
            release.wait(1)

    operation = _Operation("thr-terminal-callback", event_callback=callback)
    started = time.perf_counter()
    assert operation.emit("turn", terminal=True, status="completed") is True
    assert time.perf_counter() - started < 0.02
    assert entered.wait(0.2)
    assert operation.completed.wait(TERMINAL_DRAIN_TIMEOUT_SEC + 0.2)
    assert operation.fence_diagnostics()["terminalFenceFallbacks"] == 1
    assert operation.wait_for_callbacks(timeout=0) is False
    release.set()
    assert operation.wait_for_callbacks(timeout=0.5) is True


def test_late_turn_notifications_and_approvals_do_not_cross_into_reused_thread():
    client = object.__new__(CodexAppServerClientImpl)
    client._late_start_lock = threading.Lock()
    client._late_start_cleanups = OrderedDict()
    client._operations_lock = threading.Lock()
    client._terminal_operations = OrderedDict()
    client._approval_lock = threading.Condition()
    client._pending_approvals = {}
    sent = []
    client._send = lambda message: sent.append(message)

    previous = _Operation("thr-reused", turn_id="turn-old")
    current = _Operation("thr-reused", allow_interaction=True)
    current.inherit_turn_history(previous)
    client._operations = {"thr-reused": current}

    client._handle_notification("item/agentMessage/delta", {
        "threadId": "thr-reused",
        "turnId": "turn-old",
        "delta": "stale reply",
    })
    client._handle_server_request({
        "id": 91,
        "method": "item/commandExecution/requestApproval",
        "params": {"threadId": "thr-reused", "turnId": "turn-old", "itemId": "old-tool"},
    })
    assert current.confirm_turn_identity("turn-new") is True
    client._replay_prestart_messages(current)

    assert current.state.reply_text() == ""
    assert current.pending_requests == {}
    assert sent[-1]["id"] == 91
    assert sent[-1]["result"]["decision"] == "cancel"
    assert current.fence_diagnostics()["lateNotifications"] == 2

    client._handle_notification("turn/started", {
        "threadId": "thr-reused",
        "turn": {"id": "turn-new", "status": "inProgress"},
    })
    client._handle_notification("turn/completed", {
        "threadId": "thr-reused",
        "turn": {"id": "turn-new", "status": "completed", "items": []},
    })
    assert current.turn_id == "turn-new"
    assert current.result["status"] == "completed"
    assert current.completed.wait(0.2)


def test_approval_response_revalidates_the_active_operation_and_turn():
    client = object.__new__(CodexAppServerClientImpl)
    client._late_start_lock = threading.Lock()
    client._late_start_cleanups = OrderedDict()
    client.profile = "default"
    client._operations_lock = threading.Lock()
    client._terminal_operations = OrderedDict()
    client._approval_lock = threading.Condition()
    client._pending_approvals = {}
    sent = []
    client._send = lambda message: sent.append(message)

    operation = _Operation("thr-approval-race", allow_interaction=True)
    client._operations = {operation.thread_id: operation}
    assert operation.confirm_turn_identity("turn-old") is True
    client._replay_prestart_messages(operation)
    client._handle_server_request({
        "id": 92,
        "method": "item/commandExecution/requestApproval",
        "params": {"threadId": operation.thread_id, "turnId": "turn-old", "itemId": "cmd-old"},
    })
    approval = client.pending_approval(operation.thread_id)["pending"]
    assert approval and approval["status"] == "pending"

    replacement = _Operation(operation.thread_id, allow_interaction=True)
    assert replacement.confirm_turn_identity("turn-new") is True
    client._replay_prestart_messages(replacement)
    client._operations[operation.thread_id] = replacement
    result = client.respond_approval(approval["id"], "approve")

    assert result["ok"] is False
    assert "different turn" in result["error"]
    assert operation.pending_requests == {}
    assert replacement.pending_requests == {}
    assert sent[-1]["id"] == 92
    assert sent[-1]["result"]["decision"] == "cancel"


def test_concurrent_single_approval_cleanup_preserves_other_thread_approvals():
    client = object.__new__(CodexAppServerClientImpl)
    client.profile = "default"
    client._operations_lock = threading.Lock()
    client._terminal_operations = OrderedDict()
    client._approval_lock = threading.Condition()
    client._pending_approvals = {}
    client._late_start_lock = threading.Lock()
    client._late_start_cleanups = OrderedDict()
    client._send = lambda _message: None
    operation = _Operation("thr-two-approvals", allow_interaction=True)
    client._operations = {operation.thread_id: operation}
    assert operation.confirm_turn_identity("turn-two-approvals") is True
    client._replay_prestart_messages(operation)

    def request(request_id):
        return {
            "id": request_id,
            "method": "item/commandExecution/requestApproval",
            "params": {
                "threadId": operation.thread_id,
                "turnId": operation.turn_id,
                "itemId": f"cmd-{request_id}",
            },
        }

    client._handle_server_request(request(1))
    first_approval = client.pending_approval(operation.thread_id)["pending"]
    original_store = client._store_pending_approval

    def store_then_resolve_current(op, request_key, method, params, approval):
        stored = original_store(op, request_key, method, params, approval)
        op.pop_pending_request(request_key)
        return stored

    client._store_pending_approval = store_then_resolve_current
    client._handle_server_request(request(2))

    remaining = client.pending_approval(operation.thread_id)
    assert remaining["pending_count"] == 1
    assert remaining["pending"]["id"] == first_approval["id"]
    assert operation.has_pending_request("1") is True


def test_unrelated_old_notification_cannot_release_late_start_cleanup_gate():
    client = object.__new__(CodexAppServerClientImpl)
    client._late_start_lock = threading.Lock()
    cleanup = _LateStartCleanup(turn_id="turn-authoritative", interrupt_sent=True)
    client._late_start_cleanups = OrderedDict({"thr-cleanup": cleanup})
    client._operations_lock = threading.Lock()
    client._operations = {}
    client._terminal_operations = OrderedDict()

    client._handle_notification("item/completed", {
        "threadId": "thr-cleanup",
        "turnId": "turn-old",
        "item": {"id": "old", "type": "agentMessage", "text": "old"},
    })
    assert client._late_start_cleanup_pending("thr-cleanup") is True

    client._handle_notification("turn/completed", {
        "threadId": "thr-cleanup",
        "turn": {"id": "turn-authoritative", "status": "interrupted", "items": []},
    })
    assert client._late_start_cleanup_pending("thr-cleanup") is False
    assert cleanup.event.is_set()


def test_terminal_before_late_authoritative_response_completes_matching_cleanup():
    client = object.__new__(CodexAppServerClientImpl)
    client._late_start_lock = threading.Lock()
    cleanup = _LateStartCleanup()
    client._late_start_cleanups = OrderedDict({"thr-cleanup-race": cleanup})

    assert client._handle_late_start_terminal("thr-cleanup-race", "turn-race") is True
    assert cleanup.observed_terminal_turn_ids == {"turn-race"}
    assert client._late_start_cleanup_pending("thr-cleanup-race") is True

    assert client._bind_late_start_turn("thr-cleanup-race", "turn-race", cleanup) is True
    assert client._late_start_cleanup_pending("thr-cleanup-race") is False
    assert cleanup.event.is_set()


def test_discarding_prestart_buffer_transfers_terminal_to_registered_cleanup():
    client = object.__new__(CodexAppServerClientImpl)
    client._late_start_lock = threading.Lock()
    cleanup = _LateStartCleanup(turn_id="turn-buffered-terminal", interrupt_sent=True)
    client._late_start_cleanups = OrderedDict({"thr-buffered-terminal": cleanup})
    client._send = lambda _message: None
    operation = _Operation("thr-buffered-terminal")
    operation.defer_native_notification("turn/completed", {
        "threadId": operation.thread_id,
        "turn": {"id": cleanup.turn_id, "status": "interrupted", "items": []},
    })

    client._cancel_prestart_requests(operation)
    assert client._late_start_cleanup_pending(operation.thread_id) is False
    assert cleanup.event.is_set()


def test_execution_terminal_observed_before_cleanup_binding_does_not_leave_gate():
    client = object.__new__(CodexAppServerClientImpl)
    client._late_start_lock = threading.Lock()
    cleanup = _LateStartCleanup()
    client._late_start_cleanups = OrderedDict({"thr-timeout-race": cleanup})
    operation = _Operation("thr-timeout-race", turn_id="turn-timeout-race")
    operation.finish_without_event()

    assert client._bind_late_start_turn(
        operation.thread_id,
        operation.turn_id,
        cleanup,
        operation,
    ) is True
    assert client._late_start_cleanup_pending(operation.thread_id) is False


def test_generation_cleanup_registration_uses_recovery_then_lifecycle_lock_order():
    events = []

    class RecordingContext:
        def __init__(self, name, value=None):
            self.name = name
            self.value = value

        def __enter__(self):
            events.append(f"enter:{self.name}")
            return self.value

        def __exit__(self, *_args):
            events.append(f"exit:{self.name}")

    class Runtime:
        generation = 7

        @staticmethod
        def lifecycle_fence():
            return RecordingContext("lifecycle", 7)

    client = object.__new__(CodexAppServerClientImpl)
    client._runtime = Runtime()
    client._recovery_admission_lock = RecordingContext("recovery")
    client._late_start_lock = threading.Lock()
    client._late_start_cleanups = OrderedDict()
    cleanup = _LateStartCleanup()

    assert client._register_late_start_cleanup_for_generation("thr-order", cleanup, 7) == "registered"
    assert events == [
        "enter:recovery",
        "enter:lifecycle",
        "exit:lifecycle",
        "exit:recovery",
    ]


def test_unbound_late_cleanup_bounds_observed_terminal_ids():
    client = object.__new__(CodexAppServerClientImpl)
    client._late_start_lock = threading.Lock()
    cleanup = _LateStartCleanup()
    client._late_start_cleanups = OrderedDict({"thr-bounded": cleanup})

    for index in range(codex_app_server_module.MAX_OBSERVED_TERMINAL_TURNS + 20):
        assert client._handle_late_start_terminal("thr-bounded", f"turn-{index}") is True
    assert len(cleanup.observed_terminal_turn_ids) == codex_app_server_module.MAX_OBSERVED_TERMINAL_TURNS


def test_successful_terminal_has_no_fixed_sleep_tail():
    operation = _Operation("thr-immediate")
    started = time.perf_counter()
    operation.emit("turn", terminal=True, status="completed")
    elapsed = time.perf_counter() - started
    assert operation.completed.is_set()
    assert elapsed < 0.02
    import inspect
    assert "time.sleep(0.2)" not in inspect.getsource(CodexAppServerClientImpl._execute_locked)


def test_post_terminal_metrics_are_diagnostic_and_late_content_cannot_mutate_reply():
    client = object.__new__(CodexAppServerClientImpl)
    client._late_start_lock = threading.Lock()
    client._late_start_cleanups = OrderedDict()
    client._operations_lock = threading.Lock()
    client._operations = {}
    client._terminal_operations = OrderedDict()
    operation = _Operation("thr-late")
    client._operations["thr-late"] = operation
    assert operation.confirm_turn_identity("turn-late") is True
    client._replay_prestart_messages(operation)

    client._handle_notification("turn/completed", {
        "threadId": "thr-late",
        "turn": {"id": "turn-late", "status": "completed", "items": [{"id": "answer", "type": "agentMessage", "text": "final"}]},
    })
    assert operation.completed.is_set()
    client._handle_notification("item/completed", {
        "threadId": "thr-late",
        "turnId": "turn-late",
        "item": {"id": "late", "type": "agentMessage", "text": "must not replace final"},
    })
    client._handle_notification("thread/tokenUsage/updated", {
        "threadId": "thr-late",
        "tokenUsage": {"total_tokens": 99},
    })

    assert operation.state.reply_text() == "final"
    diagnostics = client.terminal_diagnostics("thr-late")
    assert diagnostics["lateNotifications"] == 1
    assert diagnostics["postTerminalMetrics"] == 1


def test_terminal_diagnostics_are_retained_without_reasoning_notifications():
    client = object.__new__(CodexAppServerClientImpl)
    client._late_start_lock = threading.Lock()
    client._late_start_cleanups = OrderedDict()
    client._operations_lock = threading.Lock()
    client._operations = {}
    client._terminal_operations = OrderedDict()
    operation = _Operation("thr-no-reasoning")
    client._operations[operation.thread_id] = operation
    assert operation.confirm_turn_identity("turn-no-reasoning") is True
    client._replay_prestart_messages(operation)

    client._handle_notification("turn/completed", {
        "threadId": operation.thread_id,
        "turn": {"id": "turn-no-reasoning", "status": "completed", "items": []},
    })
    with client._operations_lock:
        client._operations.pop(operation.thread_id, None)

    diagnostics = client.terminal_diagnostics(operation.thread_id)
    assert diagnostics["terminalObserved"] is True
    assert diagnostics["callbackErrors"] == 0


def test_runtime_exit_releases_operation_through_terminal_fence():
    client = object.__new__(CodexAppServerClientImpl)
    client._recovery_admission_lock = threading.RLock()
    client._late_start_lock = threading.Lock()
    client._late_start_cleanups = OrderedDict()
    client._operations_lock = threading.Lock()
    operation = _Operation("thr-exit")
    client._operations = {"thr-exit": operation}
    client._terminal_operations = OrderedDict()
    client._runtime = type("Runtime", (), {"stderr_text": lambda self: "runtime ended"})()
    client._approval_lock = threading.Condition()
    client._pending_approvals = {}

    client._handle_runtime_exit()
    assert operation.completed.is_set()
    assert operation.result["status"] == "bridge_unavailable"
    assert client.terminal_diagnostics("thr-exit")["terminalObserved"] is True


def test_cancelled_turn_completes_through_terminal_fence():
    with tempfile.TemporaryDirectory() as tmp:
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp))
        result = {}
        worker = threading.Thread(target=lambda: result.update(client.execute("hang forever", timeout_sec=5)))
        try:
            worker.start()
            deadline = time.time() + 2
            while time.time() < deadline:
                with client._operations_lock:
                    operation = client._operations.get("thr_fake")
                if operation and operation.turn_id == "turn_hang":
                    break
                time.sleep(0.01)
            assert client.cancel("thr_fake") is True
            worker.join(1)
            assert result["status"] == "cancelled"
            assert result["terminalFence"]["terminalFenceFallbacks"] == 0
        finally:
            client.close()


def test_capacity_two_runs_different_threads_and_rejects_third_explicitly():
    with tempfile.TemporaryDirectory() as tmp:
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp), max_concurrent_turns=2)
        release = threading.Event()
        both_started = threading.Event()
        active = set()
        active_lock = threading.Lock()
        results = {}

        def fake_execute(message, thread_id="", **_kwargs):
            with active_lock:
                active.add(thread_id)
                if len(active) == 2:
                    both_started.set()
            release.wait(1)
            with active_lock:
                active.discard(thread_id)
            return {"ok": True, "status": "completed", "threadId": thread_id, "reply": message}

        client._execute_locked = fake_execute
        workers = [
            threading.Thread(target=lambda key=key: results.update({key: client.execute(key, thread_id=key)}))
            for key in ("thr-one", "thr-two")
        ]
        try:
            for worker in workers:
                worker.start()
            assert both_started.wait(0.5)
            busy = client.execute("third", thread_id="thr-three")
            assert busy["status"] == "busy"
            assert busy["busyCode"] == "busy_by_capacity"
            assert busy["busyReason"] == "capacity"
            release.set()
            for worker in workers:
                worker.join(1)
            diagnostics = client.admission_diagnostics()
            assert diagnostics["acceptedTurns"] == 2
            assert diagnostics["busyByCapacity"] == 1
            assert diagnostics["peakActiveTurns"] == 2
            assert diagnostics["activeTurns"] == 0
            assert diagnostics["orderedThreads"] == 0
        finally:
            release.set()
            client.close()


def test_same_native_thread_is_ordered_without_consuming_parallel_capacity():
    with tempfile.TemporaryDirectory() as tmp:
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp), max_concurrent_turns=2)
        first_started = threading.Event()
        release_first = threading.Event()
        calls = []
        results = []

        def fake_execute(message, thread_id="", **_kwargs):
            calls.append(message)
            if message == "first":
                first_started.set()
                release_first.wait(1)
            return {"ok": True, "status": "completed", "threadId": thread_id, "reply": message}

        client._execute_locked = fake_execute
        workers = [
            threading.Thread(target=lambda message=message: results.append(client.execute(message, thread_id="shared-thread")))
            for message in ("first", "second")
        ]
        try:
            workers[0].start()
            assert first_started.wait(0.5)
            workers[1].start()
            time.sleep(0.05)
            assert calls == ["first"]
            release_first.set()
            for worker in workers:
                worker.join(1)
            assert calls == ["first", "second"]
            assert client.admission_diagnostics()["peakActiveTurns"] == 1
            assert client.admission_diagnostics()["orderedThreads"] == 0
        finally:
            release_first.set()
            client.close()


def test_capacity_configuration_is_clamped_and_invalid_values_fail_safe():
    with tempfile.TemporaryDirectory() as tmp:
        assert CodexAppServerClient(tmp, binary=make_fake_codex(tmp), max_concurrent_turns=99).max_concurrent_turns == 4
        assert CodexAppServerClient(tmp, binary=make_fake_codex(tmp), max_concurrent_turns="invalid").max_concurrent_turns == 1


def test_capacity_one_preserves_single_active_turn_behavior():
    with tempfile.TemporaryDirectory() as tmp:
        client = CodexAppServerClient(tmp, binary=make_fake_codex(tmp), max_concurrent_turns=1)
        started = threading.Event()
        release = threading.Event()

        def fake_execute(message, thread_id="", **_kwargs):
            started.set()
            release.wait(1)
            return {"ok": True, "status": "completed", "threadId": thread_id, "reply": message}

        client._execute_locked = fake_execute
        first_result = {}
        worker = threading.Thread(target=lambda: first_result.update(client.execute("first", thread_id="thread-one")))
        try:
            worker.start()
            assert started.wait(0.5)
            second = client.execute("second", thread_id="thread-two")
            assert second["status"] == "busy"
            assert second["busyCode"] == "busy_by_capacity"
            release.set()
            worker.join(1)
            assert first_result["ok"] is True
        finally:
            release.set()
            client.close()


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"test_codex_bridge.py passed: {len(tests)} tests")
