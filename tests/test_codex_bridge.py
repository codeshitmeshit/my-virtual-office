#!/usr/bin/env python3
"""Focused tests for the Codex app-server bridge."""

import os
import stat
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from providers.codex_bridge import CodexAppServerClient


FAKE_SERVER = r'''#!/usr/bin/env python3
import json
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
        send({"id": request_id, "result": {"userAgent": "fake"}})
    elif method == "initialized":
        pass
    elif method == "thread/start":
        send({"id": request_id, "result": {"thread": {"id": thread_id}}})
    elif method == "thread/resume":
        send({"id": request_id, "result": {"thread": {"id": params["threadId"]}}})
    elif method == "turn/start":
        if params.get("summary") != "detailed":
            send({"id": request_id, "error": {"message": "reasoning summary was not requested"}})
            continue
        prompt = params["input"][0]["text"]
        if "hang forever" in prompt:
            send({"id": request_id, "result": {"turn": {"id": "turn_hang"}}})
            send({"method": "turn/started", "params": {"threadId": params["threadId"], "turn": {"id": "turn_hang"}}})
            continue
        turn_id = "turn_approval" if "approval" in prompt else "turn_input" if "question" in prompt else "turn_ok"
        send({"id": request_id, "result": {"turn": {"id": turn_id}}})
        send({"method": "turn/started", "params": {"threadId": params["threadId"], "turn": {"id": turn_id}}})
        if "approval" in prompt:
            send({"id": 900, "method": "item/commandExecution/requestApproval", "params": {"threadId": params["threadId"], "turnId": turn_id, "itemId": "cmd_1"}})
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
            change = {"id": "file_1", "type": "fileChange", "status": "completed", "changes": [{"path": "app/demo.py", "kind": "update", "diff": ""}]}
            send({"method": "item/completed", "params": {"threadId": params["threadId"], "turnId": turn_id, "item": item}})
            send({"method": "item/completed", "params": {"threadId": params["threadId"], "turnId": turn_id, "item": change}})
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
            assert result["modifiedFiles"] == ["app/demo.py"]

            resumed = client.execute("continue", thread_id=result["threadId"], timeout_sec=5)
            assert resumed["ok"] is True
            assert resumed["threadId"] == result["threadId"]
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
            assert client.respond("thr_fake", pending["interactionId"], "acceptForSession") is True
            worker.join(3)
            assert result["ok"] is True
            assert result["turnId"] == "turn_approval"
            assert result["reply"] == "approved reply"
        finally:
            client.close()


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


if __name__ == "__main__":
    test_execute_collects_reply_files_and_thread()
    test_approval_request_fails_closed()
    test_manual_compaction_keeps_thread()
    test_timeout_returns_terminal_result()
    test_activity_events_are_incremental_and_correlated()
    test_reasoning_events_are_distinct_and_sectioned()
    test_interactive_approval_continues_original_turn()
    test_interactive_user_input_continues_original_turn()
    print("ok")
