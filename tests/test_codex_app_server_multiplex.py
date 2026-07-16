#!/usr/bin/env python3
"""Deterministic proof that the Codex app-server protocol can multiplex threads."""

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

from providers.codex_app_server import CodexAppServerClient


MULTIPLEX_SERVER = r'''#!/usr/bin/env python3
import json
import sys

thread_count = 0
turns = {}
started = False
initialized = False

def send(value):
    sys.stdout.write(json.dumps(value) + "\n")
    sys.stdout.flush()

def maybe_interleave():
    global started
    if started or len(turns) != 2:
        return
    started = True
    ordered = sorted(turns)
    first, second = ordered
    send({"method": "turn/started", "params": {"threadId": first, "turn": {"id": turns[first]}}})
    send({"method": "turn/started", "params": {"threadId": second, "turn": {"id": turns[second]}}})
    send({"method": "item/reasoning/summaryTextDelta", "params": {"threadId": first, "turnId": turns[first], "itemId": "reason-1", "delta": "reason-one"}})
    send({"method": "item/reasoning/summaryTextDelta", "params": {"threadId": second, "turnId": turns[second], "itemId": "reason-2", "delta": "reason-two"}})
    send({"id": 9001, "method": "item/commandExecution/requestApproval", "params": {"threadId": first, "turnId": turns[first], "itemId": "command-one"}})
    send({"id": 9002, "method": "item/tool/requestUserInput", "params": {"threadId": second, "turnId": turns[second], "itemId": "input-two", "questions": [{"id": "value", "label": "Value"}]}})

for raw in sys.stdin:
    message = json.loads(raw)
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}
    if method == "initialize":
        send({"id": request_id, "result": {"userAgent": "multiplex-fixture"}})
    elif method == "initialized":
        initialized = True
    elif method == "thread/start":
        if not initialized:
            send({"id": request_id, "error": {"message": "thread started before initialization fence"}})
            continue
        thread_count += 1
        send({"id": request_id, "result": {"thread": {"id": "thr-%s" % thread_count}}})
    elif method == "turn/start":
        thread_id = params["threadId"]
        turn_id = "turn-" + thread_id.split("-")[-1]
        turns[thread_id] = turn_id
        send({"id": request_id, "result": {"turn": {"id": turn_id}}})
        maybe_interleave()
    elif request_id == 9001:
        thread_id = sorted(turns)[0]
        item = {"id": "answer-one", "type": "agentMessage", "text": "reply-" + thread_id}
        send({"method": "item/completed", "params": {"threadId": thread_id, "turnId": turns[thread_id], "item": item}})
        send({"method": "turn/completed", "params": {"threadId": thread_id, "turn": {"id": turns[thread_id], "status": "completed", "items": [item]}}})
    elif request_id == 9002:
        pass
    elif method == "turn/interrupt":
        thread_id = params["threadId"]
        send({"id": request_id, "result": {"interrupted": True, "threadId": thread_id}})
        send({"method": "turn/completed", "params": {"threadId": thread_id, "turn": {"id": turns[thread_id], "status": "interrupted", "items": []}}})
'''


def _make_server(directory):
    path = os.path.join(directory, "codex")
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(MULTIPLEX_SERVER)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


def test_two_native_threads_interleave_without_cross_delivery():
    with tempfile.TemporaryDirectory() as workspace:
        client = CodexAppServerClient(workspace, binary=_make_server(workspace), max_concurrent_turns=2)
        results = {"one": {}, "two": {}}
        events = {"one": [], "two": []}

        def execute(label):
            results[label].update(client.execute(
                f"message-{label}",
                timeout_sec=5,
                event_callback=events[label].append,
                allow_interaction=True,
            ))

        workers = [threading.Thread(target=execute, args=(label,)) for label in ("one", "two")]
        try:
            for worker in workers:
                worker.start()
            deadline = time.time() + 3
            approval = None
            user_input = None
            while time.time() < deadline and (not approval or not user_input):
                for label in ("one", "two"):
                    approval = approval or next((event for event in events[label] if event.get("interactionType") == "approval"), None)
                    user_input = user_input or next((event for event in events[label] if event.get("interactionType") == "input"), None)
                time.sleep(0.01)
            assert approval and user_input
            assert approval["threadId"] != user_input["threadId"]
            assert client.pending_approval(approval["threadId"])["pending_count"] == 1
            assert client.pending_approval(user_input["threadId"])["pending_count"] == 0
            assert client.respond(approval["threadId"], approval["interactionId"], "acceptForSession") is True
            assert client.cancel(user_input["threadId"]) is True

            for worker in workers:
                worker.join(2)
                assert not worker.is_alive()

            by_thread = {result["threadId"]: result for result in results.values()}
            assert by_thread[approval["threadId"]]["ok"] is True
            assert by_thread[approval["threadId"]]["reply"] == f"reply-{approval['threadId']}"
            assert by_thread[user_input["threadId"]]["status"] == "cancelled"
            assert {result["threadId"] for result in results.values()} == {"thr-1", "thr-2"}
            assert {result["turnId"] for result in results.values()} == {"turn-1", "turn-2"}

            for label, records in events.items():
                own_thread = results[label]["threadId"]
                own_turn = results[label]["turnId"]
                assert records
                assert {event["threadId"] for event in records} == {own_thread}
                assert {event["turnId"] for event in records if event.get("turnId")} == {own_turn}
            approval_events = [event for records in events.values() for event in records if event.get("interactionType") == "approval"]
            input_events = [event for records in events.values() for event in records if event.get("interactionType") == "input"]
            assert [event["status"] for event in approval_events] == ["pending", "resolved"]
            assert {event["threadId"] for event in approval_events} == {approval["threadId"]}
            assert [event["status"] for event in input_events] == ["pending"]
            assert input_events[0]["threadId"] == user_input["threadId"]
            assert client.pending_approval()["pending_count"] == 0
            with client._operations_lock:
                assert client._operations == {}
                assert set(client._terminal_operations) == {"thr-1", "thr-2"}
        finally:
            client.close()
