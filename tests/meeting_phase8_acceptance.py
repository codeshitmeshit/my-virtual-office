#!/usr/bin/env python3
"""Runtime Meeting acceptance against an application started by start.sh."""

import os
import requests

BASE = os.environ.get("VO_TEST_URL", "http://127.0.0.1:8090")
TOKEN = os.environ.get("VO_MANAGEMENT_TOKEN", "4285")
HEADERS = {"X-VO-Management-Token": TOKEN}


def call(method, path, body=None, *, auth=True):
    headers = {**(HEADERS if auth else {}), "Content-Type": "application/json"}
    response = requests.request(method, BASE + path, json=body, headers=headers, timeout=15)
    try: payload = response.json()
    except ValueError: payload = {"raw": response.text}
    return response.status_code, payload


def main():
    evidence = []
    status, health = call("GET", "/health")
    assert status == 200; evidence.append("health")
    denied_status, denied = call("POST", "/api/projects", {"title": "denied"}, auth=False)
    assert denied_status == 403 and denied.get("code") == "management_token_required"; evidence.append("management-auth")

    _, created = call("POST", "/api/meetings/executable/create", {
        "topic": "Phase 8 lifecycle", "purpose": "Runtime acceptance",
        "participants": ["accept-a", "accept-b"], "moderator": "accept-a",
        "idempotencyKey": "phase8-lifecycle",
    })
    meeting = created["meeting"]; meeting_id = meeting["id"]
    _, intervention = call("POST", f"/api/meetings/executable/{meeting_id}/intervention", {"text": "Runtime context", "expectedVersion": meeting["version"]})
    assert intervention["ok"] and intervention["event"]["type"] == "user_intervention"
    _, agenda = call("POST", f"/api/meetings/executable/{meeting_id}/agenda-change", {"agenda": "Updated runtime agenda", "expectedVersion": intervention["meeting"]["version"]})
    assert agenda["meeting"]["agenda"] == "Updated runtime agenda"
    _, cancelled = call("POST", f"/api/meetings/executable/{meeting_id}/transition", {"stage": "cancelled", "expectedVersion": agenda["meeting"]["version"], "idempotencyKey": "phase8-cancel"})
    assert cancelled["meeting"]["stage"] == "cancelled"
    _, reconciled = call("GET", "/api/meetings/executable/reconcile")
    assert meeting_id not in reconciled["occupancy"].values(); evidence.extend(["lifecycle", "intervention", "recovery", "occupancy-cleanup"])

    _, project_result = call("POST", "/api/projects", {"title": "Phase8 Meeting Project", "projectExecutionEnabled": False, "highPriorityAiMeetingAutoApprove": True})
    project = project_result["project"]
    _, task_result = call("POST", f"/api/projects/{project['id']}/tasks", {"title": "Meeting source task", "assignee": "accept-a", "executorAgentId": "accept-a"})
    task = task_result["task"]
    _, request_result = call("POST", f"/api/projects/{project['id']}/tasks/{task['id']}/meeting-requests", {
        "requestingAgentId": "accept-a", "goal": "Decide", "expectedOutcome": "Decision", "reason": "Needs review",
        "suggestedParticipants": ["accept-a", "accept-b"], "suggestedModerator": "accept-a", "idempotencyKey": "phase8-request",
    })
    request = request_result["request"]
    assert request["status"] == "pending" and request_result["notification"]["status"] == "skipped_missing_webhook"
    _, confirmed = call("POST", f"/api/meetings/requests/{request['id']}/confirm", {"confirmedBy": "phase8-user", "idempotencyKey": "phase8-confirm"})
    linked = confirmed["meeting"]; linked_id = linked["id"]
    _, opening = call("POST", f"/api/meetings/executable/{linked_id}/transition", {"stage": "active_opening", "expectedVersion": linked["version"]})
    _, summarizing = call("POST", f"/api/meetings/executable/{linked_id}/transition", {"stage": "summarizing", "expectedVersion": opening["meeting"]["version"]})
    _, completed = call("POST", f"/api/meetings/executable/{linked_id}/transition", {
        "stage": "completed", "expectedVersion": summarizing["meeting"]["version"],
        "result": {"outcome": "approved", "summary": "Accepted", "decision": "Ship", "actionItems": [{"title": "Follow up", "owner": "accept-a"}]},
    })
    draft = completed["meeting"]["actionItemDrafts"][0]
    _, converted = call("POST", f"/api/meetings/executable/{linked_id}/action-items/{draft['id']}", {"action": "confirm", "idempotencyKey": "phase8-action"})
    assert converted["ok"] and converted["actionItem"]["status"] == "confirmed"
    _, current_project = call("GET", f"/api/projects/{project['id']}")
    current_task = next(item for item in current_project["project"]["tasks"] if item["id"] == task["id"])
    assert current_task["meetingBlocker"]["status"] == "resolved_continue"
    assert len(current_task["meetingActionItems"]) == 1
    evidence.extend(["request-confirm", "project-resume", "action-item", "notification-degradation"])
    call("DELETE", f"/api/projects/{project['id']}")
    print({"ok": True, "evidence": evidence, "meetingId": linked_id, "requestId": request["id"]})


if __name__ == "__main__": main()
