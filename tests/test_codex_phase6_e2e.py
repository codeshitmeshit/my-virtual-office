#!/usr/bin/env python3
"""HTTP end-to-end coverage for Phase 6 Codex activity and controls."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_codex_bridge import make_fake_codex

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(base, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base + path,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data is not None else "GET",
    )
    try:
        with OPENER.open(req, timeout=10) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def wait_for(base, path, predicate, timeout=8):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            _, last = request(base, path)
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.1)
            continue
        if predicate(last):
            return last
        time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for {path}: {last}")


def run():
    with tempfile.TemporaryDirectory(prefix="vo-phase6-e2e-") as tmp:
        port = free_port()
        ws_port = free_port()
        env = os.environ.copy()
        config_path = os.path.join(tmp, "vo-config.json")
        with open(config_path, "w") as config_file:
            json.dump({
                "office": {"name": "Phase 6 E2E"},
                "openclaw": {"gatewayToken": ""},
                "features": {"apiUsage": False},
                "hermes": {"enabled": False},
                "codex": {"enabled": True},
            }, config_file)
        env.update({
            "_VO_INT": "1",
            "VO_PORT": str(port),
            "VO_WS_PORT": str(ws_port),
            "VO_STATUS_DIR": os.path.join(tmp, "status"),
            "VO_CONFIG": config_path,
            "VO_GATEWAY_TOKEN": "",
            "VO_CODEX_ENABLED": "1",
            "VO_CODEX_WORKSPACE": ROOT,
            "VO_CODEX_BIN": make_fake_codex(tmp),
            "VO_HERMES_ENABLED": "0",
            "VO_OPENCLAW_PATH": os.path.join(tmp, "no-openclaw"),
            "PYTHONUNBUFFERED": "1",
        })
        log_path = os.path.join(tmp, "server.log")
        log_file = open(log_path, "w+")
        proc = subprocess.Popen(
            [sys.executable, os.path.join(ROOT, "app", "server.py")],
            cwd=ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            try:
                wait_for(base, "/api/license", lambda value: value.get("demo") is False)
            except AssertionError as exc:
                log_file.flush()
                log_file.seek(0)
                raise AssertionError(f"{exc}\nServer log:\n{log_file.read()}") from exc

            status, normal = request(base, "/api/codex/chat", {
                "agentId": "codex-local", "conversationId": "e2e-normal",
                "message": "change one file", "fromType": "human",
            })
            assert status == 200 and normal["ok"] is True
            _, activity = request(base, "/api/codex/activity?" + urllib.parse.urlencode({
                "agentId": "codex-local", "conversationId": "e2e-normal",
            }))
            assert any(event.get("itemId") == "cmd_1" and event.get("status") == "running" for event in activity["events"])
            assert any(event.get("itemId") == "cmd_1" and event.get("status") == "done" for event in activity["events"])
            reasoning = [event for event in activity["events"] if event.get("type") == "reasoning" and event.get("itemId") == "reason_1"]
            assert len([event for event in reasoning if str(event.get("text") or "").startswith("part-")]) == 20
            assert len([event for event in reasoning if event.get("boundary")]) == 2
            assert any(event.get("deltaKind") == "raw" for event in reasoning)
            assert reasoning[-1]["status"] == "done"
            assert reasoning[-1]["text"] == "first section\n\nsecond section\n\nthird section"

            approval_result = {}
            worker = threading.Thread(target=lambda: approval_result.update(dict(zip(
                ("httpStatus", "body"),
                request(base, "/api/codex/chat", {
                    "agentId": "codex-local", "conversationId": "e2e-approval",
                    "message": "needs approval", "fromType": "human",
                }),
            ))))
            worker.start()
            pending = wait_for(
                base,
                "/api/codex/activity?" + urllib.parse.urlencode({"agentId": "codex-local", "conversationId": "e2e-approval"}),
                lambda value: any(event.get("type") == "interaction" and event.get("status") == "pending" for event in value.get("events", [])),
            )
            interaction = next(event for event in pending["events"] if event.get("status") == "pending")
            status, accepted = request(base, "/api/codex/interaction", {
                "agentId": "codex-local", "conversationId": "e2e-approval",
                "interactionId": interaction["interactionId"], "action": "accept",
            })
            assert status == 200 and accepted["ok"] is True
            worker.join(5)
            assert approval_result["httpStatus"] == 200
            assert approval_result["body"]["reply"] == "approved reply"

            cancel_result = {}
            cancel_worker = threading.Thread(target=lambda: cancel_result.update(dict(zip(
                ("httpStatus", "body"),
                request(base, "/api/codex/chat", {
                    "agentId": "codex-local", "conversationId": "e2e-cancel",
                    "message": "hang forever", "fromType": "human", "timeoutSec": 20,
                }),
            ))))
            cancel_worker.start()
            wait_for(base, "/api/codex/activity?" + urllib.parse.urlencode({
                "agentId": "codex-local", "conversationId": "e2e-cancel",
            }), lambda value: bool(value.get("active")))
            busy_status, busy = request(base, "/api/codex/chat", {
                "agentId": "codex-local", "conversationId": "e2e-other-window",
                "message": "second request", "fromType": "human",
            })
            assert busy_status == 409
            assert busy["status"] == "busy"
            assert busy["activeConversationId"] == "e2e-cancel"
            status, cancelled = request(base, "/api/codex/cancel", {
                "agentId": "codex-local", "conversationId": "e2e-cancel",
            })
            assert status == 200 and cancelled["status"] == "cancelling"
            cancel_worker.join(5)
            assert not cancel_worker.is_alive()
            assert cancel_result["body"]["ok"] is False
            assert cancel_result["body"]["status"] == "cancelled"
            assert cancel_result["httpStatus"] == 200

            restart_result = {}
            def run_restart_request():
                try:
                    restart_result["response"] = request(base, "/api/codex/chat", {
                        "agentId": "codex-local", "conversationId": "e2e-restart",
                        "message": "needs approval", "fromType": "human", "timeoutSec": 20,
                    })
                except Exception as exc:
                    restart_result["error"] = str(exc)

            restart_worker = threading.Thread(target=run_restart_request)
            restart_worker.start()
            wait_for(
                base,
                "/api/codex/activity?" + urllib.parse.urlencode({"agentId": "codex-local", "conversationId": "e2e-restart"}),
                lambda value: any(event.get("status") == "pending" for event in value.get("events", [])),
            )
            proc.terminate()
            proc.wait(timeout=5)
            restart_worker.join(5)
            proc = subprocess.Popen(
                [sys.executable, os.path.join(ROOT, "app", "server.py")],
                cwd=ROOT,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            wait_for(base, "/api/license", lambda value: value.get("demo") is False)
            recovered = wait_for(
                base,
                "/api/codex/activity?" + urllib.parse.urlencode({"agentId": "codex-local", "conversationId": "e2e-restart"}),
                lambda value: bool(value.get("events")),
            )
            orphan = next(event for event in recovered["events"] if event.get("type") == "interaction")
            assert orphan["status"] == "unavailable"
            assert recovered["active"] is None

            print("ok")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            log_file.close()


if __name__ == "__main__":
    run()
