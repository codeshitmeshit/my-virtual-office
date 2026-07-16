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
from providers.codex_app_server import CodexAppServerClient as CodexAppServerClientImpl, TERMINAL_DRAIN_TIMEOUT_SEC, _Operation


FAKE_SERVER = r'''#!/usr/bin/env python3
import json
import os
import sys

thread_id = "thr_fake"

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
        turn_id = "turn_permissions" if "permissions" in prompt else "turn_approval" if "approval" in prompt else "turn_input" if "question" in prompt else "turn_ok"
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
        send({"id": request_id, "result": {}})
        send({"method": "turn/completed", "params": {"threadId": params["threadId"], "turn": {"id": params.get("turnId"), "status": "interrupted", "items": []}}})
'''


def make_fake_codex(tmp):
    path = os.path.join(tmp, "codex")
    with open(path, "w") as f:
        f.write(FAKE_SERVER)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


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
    client._operations_lock = threading.Lock()
    client._operations = {}
    client._terminal_operations = OrderedDict()
    operation = _Operation("thr-late")
    client._operations["thr-late"] = operation

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
    client._operations_lock = threading.Lock()
    client._operations = {}
    client._terminal_operations = OrderedDict()
    operation = _Operation("thr-no-reasoning")
    client._operations[operation.thread_id] = operation

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
    test_execute_collects_reply_files_and_thread()
    test_execute_exposes_run_state_tools_thinking_and_token_usage()
    test_approval_request_fails_closed()
    test_manual_compaction_keeps_thread()
    test_timeout_returns_terminal_result()
    test_activity_events_are_incremental_and_correlated()
    test_reasoning_events_are_distinct_and_sectioned()
    test_interactive_approval_continues_original_turn()
    test_reference_style_approval_response_continues_turn()
    test_interactive_permissions_approval_continues_original_turn()
    test_approval_response_mapping_covers_reference_shapes()
    test_interactive_user_input_continues_original_turn()
    print("ok")
