from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _read_sse_event(response: http.client.HTTPResponse, expected: str) -> dict:
    event_name = ""
    data_lines: list[str] = []
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        raw = response.readline()
        if not raw:
            break
        line = raw.decode("utf-8").rstrip("\r\n")
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
        elif not line:
            if event_name == expected:
                return json.loads("\n".join(data_lines))
            event_name = ""
            data_lines = []
    raise AssertionError(f"SSE event {expected!r} was not received")


def _post_json(port: int, path: str, payload: dict, token: str) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-VO-Management-Token": token,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_formal_http_and_sse_custom_answer_e2e():
    port = _free_port()
    token = "browser-e2e-token"
    env = {
        **os.environ,
        "VO_BROWSER_FIXTURE_PORT": str(port),
        "VO_BROWSER_FIXTURE_TOKEN": token,
    }
    process = subprocess.Popen(
        [sys.executable, "tests/human_decision_browser_fixture.py"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    stream = None
    try:
        ready = process.stdout.readline().strip() if process.stdout else ""
        assert ready == f"human decision browser fixture: http://127.0.0.1:{port}"

        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=7)
        connection.request("GET", "/api/dashboard/events")
        stream = connection.getresponse()
        assert stream.status == 200
        initial = _read_sse_event(stream, "dashboard.snapshot")
        initial_decisions = initial["decisions"]["decisions"]
        assert len(initial_decisions) == 1
        decision_id = initial_decisions[0]["id"]
        assert initial_decisions[0]["status"] == "pending"
        assert initial_decisions[0]["sync"] == {
            "application": "fixture",
            "feishuStatus": "fixture_only",
        }

        status, resolved = _post_json(
            port,
            f"/api/human-decisions/{decision_id}/resolve",
            {
                "optionId": "B",
                "customAnswer": "先给 20 位内部用户灰度 48 小时",
            },
            token,
        )
        assert status == 200
        decision = resolved["decision"]
        assert decision["resolution"]["answer"] == "先给 20 位内部用户灰度 48 小时"
        assert decision["resolution"]["optionId"] is None
        assert decision["resolution"]["channel"] == "local"

        changed = _read_sse_event(stream, "dashboard.decisions")
        projected = changed["decisions"]["decisions"][0]
        assert projected["status"] == "resolved"
        assert projected["resolution"]["answer"] == "先给 20 位内部用户灰度 48 小时"
        assert projected["resolution"]["optionId"] is None
    finally:
        if stream is not None:
            stream.close()
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
