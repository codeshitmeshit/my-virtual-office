#!/usr/bin/env python3
"""Seed a real project fixture for meeting action item acceptance."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_STATUS_DIR", os.path.join(ROOT, "data"))

import server


def main():
    data = server._load_projects()
    data["projects"] = [p for p in data.get("projects", []) if p.get("title") != "Meeting Action Items Acceptance"]
    server._save_projects(data)

    project = server._handle_project_create({
        "title": "Meeting Action Items Acceptance",
        "description": "Fixture for validating meeting action items applied back to the source task.",
        "projectExecutionEnabled": True,
        "defaultExecutorAgentId": "executor",
        "defaultReviewerAgentId": "reviewer",
    })["project"]
    task = server._handle_task_create(project["id"], {
        "title": "Implement source task after meeting",
        "description": "This task was blocked by an AI meeting. Meeting action items must be completed before the original task resumes.",
        "columnId": project["columns"][0]["id"],
        "assignee": "executor",
        "executorAgentId": "executor",
        "reviewerAgentId": "reviewer",
        "checklist": [{"id": "base-check", "text": "Original acceptance remains intact", "done": False}],
    })["task"]

    request_id = "fixture-meeting-request"
    meeting = {
        "id": "fixture-meeting-action-items",
        "projectId": project["id"],
        "topic": "Resolve source task ambiguity",
        "source": {"meetingRequestId": request_id, "projectId": project["id"], "taskId": task["id"]},
        "stage": "completed",
        "result": {
            "outcome": "approved",
            "summary": "The agents agreed on a smaller implementation path.",
            "decision": "Apply the meeting decision first, then continue the original task.",
            "actionItems": [
                {"id": "a1", "title": "Apply meeting decision to the current implementation", "owner": "executor", "description": "Update the active task plan before continuing."},
                {"id": "a2", "title": "Prepare linked follow-up copy review", "owner": "reviewer", "description": "Review the user-facing copy after executor changes."},
            ],
            "risks": ["Original task must not resume before meeting action items are checked."],
        },
    }
    _, project, task = server._project_execution_find(project["id"], task["id"])
    task["meetingBlocker"] = {
        "requestId": request_id,
        "meetingId": meeting["id"],
        "status": "confirmed",
        "createdAt": server._proj_now(),
        "updatedAt": server._proj_now(),
    }
    task["executionState"] = "awaiting_meeting_resolution"
    server._save_projects({"projects": [project]})
    applied = server._project_execution_apply_meeting_result(meeting)
    print({"projectId": project["id"], "taskId": task["id"], "applied": applied})


if __name__ == "__main__":
    main()
