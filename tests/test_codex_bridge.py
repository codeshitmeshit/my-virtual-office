#!/usr/bin/env python3
"""Focused tests for the Phase 5 Codex app-server bridge."""

import os
import stat
import sys
import tempfile

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
        prompt = params["input"][0]["text"]
        if "hang forever" in prompt:
            send({"id": request_id, "result": {"turn": {"id": "turn_hang"}}})
            send({"method": "turn/started", "params": {"threadId": params["threadId"], "turn": {"id": "turn_hang"}}})
            continue
        turn_id = "turn_approval" if "approval" in prompt else "turn_ok"
        send({"id": request_id, "result": {"turn": {"id": turn_id}}})
        send({"method": "turn/started", "params": {"threadId": params["threadId"], "turn": {"id": turn_id}}})
        if "approval" in prompt:
            send({"id": 900, "method": "item/commandExecution/requestApproval", "params": {"threadId": params["threadId"], "turnId": turn_id, "itemId": "cmd_1"}})
        else:
            item = {"id": "msg_1", "type": "agentMessage", "text": "real fake reply"}
            change = {"id": "file_1", "type": "fileChange", "status": "completed", "changes": [{"path": "app/demo.py", "kind": "update", "diff": ""}]}
            send({"method": "item/completed", "params": {"threadId": params["threadId"], "turnId": turn_id, "item": item}})
            send({"method": "item/completed", "params": {"threadId": params["threadId"], "turnId": turn_id, "item": change}})
            send({"method": "turn/completed", "params": {"threadId": params["threadId"], "turn": {"id": turn_id, "status": "completed", "items": [item, change]}}})
    elif request_id == 900:
        send({"method": "turn/completed", "params": {"threadId": thread_id, "turn": {"id": "turn_approval", "status": "interrupted", "items": []}}})
    elif method == "thread/compact/start":
        send({"id": request_id, "result": {}})
        send({"method": "thread/compacted", "params": {"threadId": params["threadId"]}})
    elif method == "turn/interrupt":
        send({"id": request_id, "result": {}})
'''


def make_fake_codex(tmp):
    path = os.path.join(tmp, "codex")
    with open(path, "w") as f:
        f.write(FAKE_SERVER)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


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


if __name__ == "__main__":
    test_execute_collects_reply_files_and_thread()
    test_approval_request_fails_closed()
    test_manual_compaction_keeps_thread()
    test_timeout_returns_terminal_result()
    print("ok")
