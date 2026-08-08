"""Integration coverage for decisions created during live meeting/project runs."""

from __future__ import annotations

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ["VO_STATUS_DIR"] = tempfile.mkdtemp(prefix="vo-human-decision-runtime-import-")

import server
from tests.test_meeting_for_ai_phase1 import (
    create_meeting,
    restore_meeting_store,
    with_meeting_store,
)
from tests.test_project_execution import (
    create_project_execution_project,
    restore_store,
    wait_for,
    with_store,
)


def test_meeting_provider_completion_does_not_overwrite_human_decision_pause():
    """Catches accepting a late participant reply after a decision bound the meeting."""

    with tempfile.TemporaryDirectory() as status_dir:
        old_store = with_meeting_store(status_dir)
        old_provider = server._meeting_call_provider

        def provider(meeting, speaker, prompt):
            bound = server._human_decision_bind_native(
                {
                    "id": "decision-meeting-live",
                    "source": {
                        "type": "meeting",
                        "id": meeting["id"],
                        "label": meeting["topic"],
                    },
                },
                speaker,
            )
            assert bound and bound["kind"] == "meeting"
            return {
                "ok": True,
                "reply": json.dumps({
                    "position": "This reply belongs to the paused turn.",
                    "reasoning": "The human decision must win the race.",
                    "disagreements": [],
                    "questions": [],
                    "suggestedNextStep": "wait",
                    "confidence": "low",
                }),
                "providerRef": {"providerKind": "fixture", "agentId": speaker},
                "durationMs": 1,
            }

        server._meeting_call_provider = provider
        try:
            created = create_meeting(
                participants=["main", "hermes-default"],
                moderator="main",
                maxRounds=1,
                idempotencyKey="meeting-live-human-decision",
            )

            result = server._handle_executable_meeting_run(created["meeting"]["id"])
            detail = server._handle_executable_meeting_detail(created["meeting"]["id"])

            assert result["ignoredProviderCompletion"] is True
            assert detail["meeting"]["stage"] == "awaiting_user_decision"
            assert detail["meeting"]["humanDecisionId"] == "decision-meeting-live"
            assert not any(event["type"] == "participant_turn" for event in detail["events"])
        finally:
            server._meeting_call_provider = old_provider
            restore_meeting_store(old_store)


def test_project_executor_completion_does_not_overwrite_human_decision_pause():
    """Catches the project runner completing an attempt after it requested a decision."""

    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old_store = with_store(status_dir)
        old_executor = server._project_execution_call_executor

        def executor(executor_ref, prompt, workspace_path, attempt_id, project_id=None, task_id=None, timeout=600):
            bound = server._human_decision_bind_native(
                {
                    "id": "decision-project-live",
                    "source": {
                        "type": "task",
                        "id": task_id,
                        "projectId": project_id,
                        "label": "Implement fixture",
                    },
                },
                executor_ref["id"],
            )
            assert bound and bound["kind"] == "task"
            return {
                "ok": True,
                "status": "completed",
                "reply": "Paused for decision; this must not complete the attempt.",
                "modifiedFiles": [],
                "checklistUpdates": [{
                    "id": "deliverable",
                    "text": "Complete implementation",
                    "done": True,
                    "evidence": "must not be applied before the decision",
                }],
            }

        server._project_execution_call_executor = executor
        try:
            project, task = create_project_execution_project(workspace)
            started = server._handle_project_execution_start(project["id"], task["id"], {})

            def settled_task():
                current = server._handle_project_get(project["id"])["project"]
                candidate = next(item for item in current["tasks"] if item["id"] == task["id"])
                attempt = next(item for item in candidate["attempts"] if item["id"] == started["attemptId"])
                return candidate if attempt.get("status") != "executing" else None

            current_task = wait_for(settled_task)
            attempt = next(item for item in current_task["attempts"] if item["id"] == started["attemptId"])

            assert current_task["activeAttemptId"] == started["attemptId"]
            assert current_task["executionState"] == "awaiting_user_decision"
            assert attempt["status"] == "awaiting_user_decision"
            assert attempt["humanDecisionId"] == "decision-project-live"
            assert "evidence" not in attempt
        finally:
            server._project_execution_call_executor = old_executor
            restore_store(old_store)
