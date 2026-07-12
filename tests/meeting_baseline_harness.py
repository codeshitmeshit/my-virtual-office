#!/usr/bin/env python3
"""Reproducible pre-unification Meeting-store I/O baseline."""

from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
if APP not in sys.path:
    sys.path.insert(0, APP)

os.environ["VO_HERMES_ENABLED"] = "0"
os.environ["VO_CODEX_ENABLED"] = "0"
os.environ["VO_STATUS_DIR"] = tempfile.mkdtemp(prefix="vo-meeting-baseline-import-")

import server
from project_store import MarkdownProjectStore


def fixture(size: int) -> tuple[dict, dict]:
    meetings = {}
    events = {}
    requests = {}
    occupancy = {}
    for index in range(size):
        meeting_id = f"m-{index:04d}"
        request_id = f"r-{index:04d}"
        participants = [f"agent-{index * 2}", f"agent-{index * 2 + 1}"]
        meetings[meeting_id] = {
            "id": meeting_id, "stage": "active_discussion", "version": 3,
            "participants": participants, "requestId": request_id,
        }
        events[meeting_id] = [
            {"id": f"{meeting_id}-e-{event}", "sequence": event + 1, "type": "turn"}
            for event in range(20)
        ]
        occupancy.update({participant: meeting_id for participant in participants})
        requests[request_id] = {
            "id": request_id, "status": "confirmed",
            "source": {"projectId": f"p-{index}", "taskId": f"t-{index}"},
            "conversion": {"meetingId": meeting_id},
        }
    return (
        {"meetings": meetings, "events": events, "occupancy": occupancy, "idempotency": {}, "updatedAt": ""},
        {"requests": requests, "idempotency": {}, "updatedAt": ""},
    )


def measure(operation, warmups: int = 3, runs: int = 20) -> dict:
    for _ in range(warmups):
        operation()
    values = []
    for _ in range(runs):
        started = time.perf_counter_ns()
        operation()
        values.append((time.perf_counter_ns() - started) / 1_000_000)
    ordered = sorted(values)
    return {
        "warmups": warmups,
        "runs": runs,
        "medianMs": round(statistics.median(values), 4),
        "p95Ms": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 4),
    }


def observed_request_conversion_writes() -> dict:
    """Execute the real pending-request confirmation path with instrumented stores."""
    original = (
        server.STATUS_DIR, server.STATUS_FILE, server.PROJECT_STORE, server.VO_CONFIG,
        server._save_exec_meeting_store, server._save_meeting_request_store,
    )
    counts = {"executable": 0, "requests": 0}
    with tempfile.TemporaryDirectory(prefix="vo-meeting-conversion-baseline-") as status:
        try:
            server.STATUS_DIR = status
            server.STATUS_FILE = os.path.join(status, "virtual-office-status.json")
            server.PROJECT_STORE = MarkdownProjectStore(status, watch_external_changes=False)
            server.VO_CONFIG = {
                **server.VO_CONFIG,
                "notifications": {"feishuWebhook": "", "feishuAppId": "", "feishuAppSecret": "", "feishuReceiveId": ""},
            }
            project = server._handle_project_create({
                "title": "Conversion baseline", "projectExecutionEnabled": False,
                "highPriorityAiMeetingAutoApprove": True,
            })["project"]
            task = server._handle_task_create(project["id"], {
                "title": "Resolve blocker", "assignee": "executor", "executorAgentId": "executor",
            })["task"]
            body = {
                "requestingAgentId": "executor", "topic": "Architecture", "purpose": "Choose direction",
                "goal": "Resolve blocker", "expectedOutcome": "Decision", "reason": "Needs review",
                "suggestedParticipants": ["executor", "reviewer"], "suggestedModerator": "executor",
                "urgency": 3, "idempotencyKey": "baseline-request",
            }
            created = server._handle_meeting_request_create(project["id"], task["id"], body)
            assert created.get("ok") and created["request"]["status"] == "pending"
            save_exec = server._save_exec_meeting_store
            save_requests = server._save_meeting_request_store

            def counted_exec(data):
                counts["executable"] += 1
                return save_exec(data)

            def counted_requests(data):
                counts["requests"] += 1
                return save_requests(data)

            server._save_exec_meeting_store = counted_exec
            server._save_meeting_request_store = counted_requests
            result = server._handle_meeting_request_confirm(created["request"]["id"], {
                "confirmedBy": "user", "idempotencyKey": "baseline-confirm",
            })
            assert result.get("ok") and result.get("meetingId")
        finally:
            (
                server.STATUS_DIR, server.STATUS_FILE, server.PROJECT_STORE, server.VO_CONFIG,
                server._save_exec_meeting_store, server._save_meeting_request_store,
            ) = original
    return {**counts, "total": counts["executable"] + counts["requests"], "providerCalls": 0}


def main() -> None:
    original_status = server.STATUS_DIR
    results = {
        "schema": 1, "fixtures": {}, "method": "3 warmups, 20 measured runs",
        "observedRequestConversion": observed_request_conversion_writes(),
        "targetUnifiedRequestConversionWrites": 1,
    }
    try:
        with tempfile.TemporaryDirectory(prefix="vo-meeting-baseline-") as status:
            server.STATUS_DIR = status
            for size in (1, 20, 100):
                executable, requests = fixture(size)
                server._save_exec_meeting_store(executable)
                server._save_meeting_request_store(requests)
                results["fixtures"][str(size)] = {
                    "meetings": size,
                    "events": size * 20,
                    "requests": size,
                    "occupancy": size * 2,
                    "legacyBytes": {
                        "executable": os.path.getsize(server._exec_meetings_file()),
                        "requests": os.path.getsize(server._meeting_requests_file()),
                    },
                    "operations": {
                        "loadExecutable": measure(server._load_exec_meeting_store),
                        "saveExecutable": measure(lambda: server._save_exec_meeting_store(executable)),
                        "loadRequests": measure(server._load_meeting_request_store),
                        "saveRequests": measure(lambda: server._save_meeting_request_store(requests)),
                    },
                }
    finally:
        server.STATUS_DIR = original_status
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
