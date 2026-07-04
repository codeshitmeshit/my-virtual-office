import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP = os.path.join(ROOT, "app")
if APP not in sys.path:
    sys.path.insert(0, APP)

from dashboard_realtime import build_dashboard_snapshot, diff_dashboard_events


def test_dashboard_snapshot_projects_status_meetings_and_actions():
    status = {
        "agent-a": {"state": "working", "task": "Run task"},
        "agent-b": {"state": "idle", "task": ""},
        "_meetings": [{"id": "legacy", "agents": ["agent-c"]}],
    }
    meetings = [
        {
            "id": "m-1",
            "topic": "Decision",
            "participants": ["agent-a", "agent-b"],
            "stage": "awaiting_user_decision",
            "decisionForStage": "active_discussion",
            "decisionForRound": 1,
            "pendingCalls": [{"sequence": 7, "speaker": "agent-a", "timedOut": True}],
            "conflicts": [{"id": "c-1", "agentId": "agent-b", "status": "open"}],
        }
    ]
    requests = [
        {"id": "r-1", "status": "pending", "goal": "Review proposal", "source": {"projectId": "p", "taskId": "t"}},
        {"id": "r-2", "status": "approved", "goal": "Already handled"},
    ]

    snapshot = build_dashboard_snapshot(status, meetings, requests)

    assert snapshot["status"]["counts"]["working"] == 1
    assert snapshot["status"]["counts"]["idle"] == 1
    assert snapshot["meetings"]["activeCount"] == 1
    assert snapshot["meetings"]["pendingRequestCount"] == 1

    action_types = {item["type"] for item in snapshot["actions"]}
    assert "meeting_request_pending" in action_types
    assert "meeting_conflict" in action_types
    assert "provider_timeout" in action_types
    assert "meeting_user_decision" in action_types
    assert all("r-2" not in item["id"] for item in snapshot["actions"])


def test_dashboard_diff_emits_only_changed_sections():
    before = build_dashboard_snapshot(
        {"agent-a": {"state": "idle", "task": ""}},
        [],
        [],
    )
    after = build_dashboard_snapshot(
        {"agent-a": {"state": "working", "task": "Task"}},
        [],
        [],
    )

    events = diff_dashboard_events(before, after)

    assert [name for name, _ in events] == ["dashboard.status"]


def test_dashboard_diff_emits_projects_when_project_progress_changes():
    before = build_dashboard_snapshot(
        {"agent-a": {"state": "idle", "task": ""}},
        [],
        [],
        [{"id": "p-1", "title": "Project", "taskCount": 2, "taskDone": 0, "projectExecutionActive": True, "projectExecutionPhase": "executing"}],
    )
    after = build_dashboard_snapshot(
        {"agent-a": {"state": "idle", "task": ""}},
        [],
        [],
        [{"id": "p-1", "title": "Project", "taskCount": 2, "taskDone": 1, "projectExecutionActive": True, "projectExecutionPhase": "executing"}],
    )

    events = diff_dashboard_events(before, after)

    assert [name for name, _ in events] == ["dashboard.projects"]
    assert events[0][1]["projects"][0]["taskDone"] == 1
    assert events[0][1]["projects"][0]["taskCount"] == 2


def test_dashboard_diff_emits_meetings_and_actions_when_needed():
    before = build_dashboard_snapshot(
        {"agent-a": {"state": "idle", "task": ""}},
        [],
        [],
    )
    after = build_dashboard_snapshot(
        {"agent-a": {"state": "idle", "task": ""}},
        [{"id": "m-1", "topic": "Needs decision", "stage": "awaiting_user_decision"}],
        [{"id": "r-1", "status": "pending", "goal": "Confirm meeting"}],
    )

    events = diff_dashboard_events(before, after)

    assert [name for name, _ in events] == ["dashboard.meetings", "dashboard.actions"]
    assert events[0][1]["meetings"]["activeCount"] == 1
    assert {item["type"] for item in events[1][1]["actions"]} == {
        "meeting_request_pending",
        "meeting_user_decision",
    }


def test_dashboard_actions_exclude_routine_and_resolved_items():
    snapshot = build_dashboard_snapshot(
        {"agent-a": {"state": "working", "task": "Routine work"}},
        [
            {
                "id": "m-1",
                "topic": "Routine meeting",
                "stage": "active_discussion",
                "conflicts": [{"id": "c-1", "agentId": "agent-a", "status": "resolved"}],
                "pendingCalls": [{"sequence": 1, "speaker": "agent-a", "timedOut": False}],
            }
        ],
        [
            {"id": "r-1", "status": "approved", "goal": "Already approved"},
            {"id": "r-2", "status": "rejected", "goal": "Already rejected"},
        ],
    )

    assert snapshot["meetings"]["pendingRequestCount"] == 0
    assert snapshot["actions"] == []


def test_dashboard_initial_diff_emits_snapshot():
    snapshot = build_dashboard_snapshot({}, [], [])
    events = diff_dashboard_events(None, snapshot)
    assert len(events) == 1
    assert events[0][0] == "dashboard.snapshot"
