#!/usr/bin/env python3
"""Reproducible post-unification Meeting-domain I/O baseline."""

from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
if APP not in sys.path: sys.path.insert(0, APP)

os.environ["VO_HERMES_ENABLED"] = "0"; os.environ["VO_CODEX_ENABLED"] = "0"
os.environ["VO_STATUS_DIR"] = tempfile.mkdtemp(prefix="vo-meeting-performance-import-")

import server
from services.meeting_repository import MeetingDomainRepository, empty_store
from project_store import MarkdownProjectStore


def fixture(size: int) -> dict:
    data = empty_store()
    for index in range(size):
        meeting_id = f"m-{index:04d}"; request_id = f"r-{index:04d}"
        participants = [f"agent-{index * 2}", f"agent-{index * 2 + 1}"]
        data["meetings"][meeting_id] = {"id": meeting_id, "stage": "active_discussion", "version": 3, "participants": participants}
        data["events"][meeting_id] = [{"id": f"{meeting_id}-e-{event}", "meetingId": meeting_id, "sequence": event + 1, "type": "turn"} for event in range(20)]
        data["occupancy"].update({participant: meeting_id for participant in participants})
        data["requests"][request_id] = {"id": request_id, "status": "confirmed", "source": {"projectId": f"p-{index}", "taskId": f"t-{index}"}, "conversion": {"meetingId": meeting_id}}
    return data


def measure(operation, warmups=3, runs=20):
    for _ in range(warmups): operation()
    values = []
    for _ in range(runs):
        started = time.perf_counter_ns(); operation(); values.append((time.perf_counter_ns() - started) / 1_000_000)
    ordered = sorted(values)
    return {"warmups": warmups, "runs": runs, "medianMs": round(statistics.median(values), 4), "p95Ms": round(ordered[max(0, int(len(ordered) * .95) - 1)], 4)}


def observed_request_conversion_writes():
    original = (server.STATUS_DIR, server.STATUS_FILE, server.PROJECT_STORE, server.VO_CONFIG, server._send_meeting_request_notification)
    counts = {"unifiedUpdates": 0, "providerCalls": 0, "notificationCalls": 0}
    with tempfile.TemporaryDirectory(prefix="vo-meeting-conversion-final-") as status:
        try:
            server.STATUS_DIR = status; server.STATUS_FILE = os.path.join(status, "virtual-office-status.json")
            server.PROJECT_STORE = MarkdownProjectStore(status, watch_external_changes=False)
            server.VO_CONFIG = {**server.VO_CONFIG, "notifications": {"feishuWebhook": "", "feishuAppId": "", "feishuAppSecret": "", "feishuReceiveId": ""}}
            project = server._handle_project_create({"title": "Conversion", "projectExecutionEnabled": False, "highPriorityAiMeetingAutoApprove": True})["project"]
            task = server._handle_task_create(project["id"], {"title": "Resolve", "assignee": "executor", "executorAgentId": "executor"})["task"]
            created = server._handle_meeting_request_create(project["id"], task["id"], {"requestingAgentId": "executor", "goal": "Resolve", "expectedOutcome": "Decision", "reason": "Review", "suggestedParticipants": ["executor", "reviewer"], "suggestedModerator": "executor", "idempotencyKey": "request"})
            repository = server._meeting_domain_repository(); original_update = repository.update
            def counted(mutator): counts["unifiedUpdates"] += 1; return original_update(mutator)
            def counted_notification(*args, **kwargs): counts["notificationCalls"] += 1; return {"ok": True, "status": "measured"}
            repository.update = counted
            server._send_meeting_request_notification = counted_notification
            try:
                result = server._handle_meeting_request_confirm(created["request"]["id"], {"confirmedBy": "user", "idempotencyKey": "confirm"})
            finally: repository.update = original_update
            assert result.get("ok") and result.get("meetingId")
        finally: server.STATUS_DIR, server.STATUS_FILE, server.PROJECT_STORE, server.VO_CONFIG, server._send_meeting_request_notification = original
    return counts


def main():
    results = {"schema": 2, "method": "3 warmups, 20 measured runs", "fixtures": {}, "observedRequestConversion": observed_request_conversion_writes(), "targetUnifiedRequestConversionWrites": 1}
    for size in (1, 20, 100):
        with tempfile.TemporaryDirectory(prefix=f"vo-meeting-performance-{size}-") as status:
            repository = MeetingDomainRepository(status); data = fixture(size); repository.update(lambda current: current.update(data))
            results["fixtures"][str(size)] = {
                "meetings": size, "events": size * 20, "requests": size, "occupancy": size * 2,
                "unifiedBytes": os.path.getsize(repository.path),
                "operations": {"loadUnified": measure(repository.snapshot), "saveUnified": measure(lambda: repository.update(lambda current: None))},
            }
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__": main()
