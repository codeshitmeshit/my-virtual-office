from app.services import meeting_lifecycle
from app.services.meeting_requests import (
    RequestHooks, confirm_command, create_command, public_request, reject_command,
    reset_project_task_blockers_command, resolve_blocker_command, selected_context,
    unresolved_for_task,
)


def hooks():
    def append_event(data, meeting, kind, **kwargs):
        meeting["version"] = int(meeting.get("version") or 0) + 1
        meeting["lastEventSequence"] = int(meeting.get("lastEventSequence") or 0) + 1
        event = {"sequence": meeting["lastEventSequence"], "type": kind}
        data.setdefault("events", {}).setdefault(meeting["id"], []).append(event)
        return event
    return RequestHooks(
        now=lambda: "now", new_id=lambda: "generated-id",
        clean_participants=lambda values: list(dict.fromkeys(str(value).strip() for value in values if str(value).strip())),
        participant_error=lambda value: ({
            "error": "Archive manager cannot participate in executable meetings",
            "code": "archive_manager_not_meeting_participant",
            "systemRole": "archive_manager",
            "_status": 400,
        } if value == "archive-manager" else None),
        auto_confirm_label=lambda reason: f"label:{reason}",
        lifecycle_hooks=meeting_lifecycle.CreateHooks(
            rebuild_occupancy=lambda data: meeting_lifecycle.rebuild_occupancy(data),
            build_conflicts=lambda *args, **kwargs: [], append_event=append_event,
        ),
    )


def empty_data():
    return {
        "meetings": {}, "events": {}, "occupancy": {}, "requests": {},
        "idempotency": {"meetings": {}, "requests": {}, "callbacks": {}, "actionItems": {}},
    }


def request_body(**changes):
    value = {
        "goal": "Decide", "expectedOutcome": "Decision", "reason": "Needs review",
        "requestingAgentId": "a1", "suggestedParticipants": ["a1", "a2"],
        "suggestedModerator": "a1", "idempotencyKey": "request-1",
    }
    value.update(changes)
    return value


def create_pending(data):
    result = create_command(
        data, {"id": "p1", "title": "Project"}, {"id": "t1", "title": "Task"},
        request_body(), [{"id": "task:t1", "sourceKind": "task", "title": "Task", "summary": "Context"}], hooks(),
    )
    assert result["ok"] is True
    return result["request"]


def test_create_validates_and_deduplicates_unresolved_task_request():
    data = empty_data()
    assert create_command(data, {"id": "p1"}, {"id": "t1"}, request_body(goal=""), [], hooks())["code"] == "goal_required"
    created = create_pending(data)
    assert data["requests"][created["id"]]["requestedContext"]["selectedContextIds"] == ["task:t1"]
    repeated = create_command(data, {"id": "p1"}, {"id": "t1"}, request_body(idempotencyKey="other"), [], hooks())
    assert repeated["idempotent"] is True and repeated["request"]["id"] == created["id"]


def test_confirm_atomically_creates_meeting_conversion_event_and_occupancy():
    data = empty_data(); request = create_pending(data)
    result = confirm_command(
        data, request["id"], {"selectedContextIds": ["task:t1"], "confirmedBy": "user"},
        project_title="Project",
        lifecycle_defaults={
            "meetingId": "m1", "preparingTimeoutSec": 300, "decisionWindowSec": 60,
            "contextBudget": {}, "allowConflicts": False,
        }, hooks=hooks(),
    )
    assert result["ok"] is True and result["meetingId"] == "m1"
    assert data["requests"][request["id"]]["conversion"]["meetingId"] == "m1"
    assert data["meetings"]["m1"]["source"]["meetingRequestId"] == request["id"]


def test_ai_request_resolution_policy_defaults_to_user_decision_only_for_p0():
    non_p0 = empty_data()
    non_p0_request = create_pending(non_p0)
    non_p0_confirmed = confirm_command(
        non_p0, non_p0_request["id"], {"confirmedBy": "user"},
        project_title="Project",
        lifecycle_defaults={
            "meetingId": "m-non-p0", "preparingTimeoutSec": 300, "decisionWindowSec": 60,
            "contextBudget": {}, "allowConflicts": False,
        }, hooks=hooks(),
    )
    assert non_p0_confirmed["ok"] is True
    assert non_p0["meetings"]["m-non-p0"]["resolutionPolicy"] == "moderator_decision"

    p0 = empty_data()
    p0_created = create_command(
        p0, {"id": "p1", "title": "Project"}, {"id": "t1", "title": "Task"},
        request_body(idempotencyKey="request-p0", urgency=5),
        [{"id": "task:t1", "sourceKind": "task", "title": "Task", "summary": "Context"}],
        hooks(),
    )
    p0_request = p0_created["request"]
    p0_confirmed = confirm_command(
        p0, p0_request["id"], {"confirmedBy": "user"},
        project_title="Project",
        lifecycle_defaults={
            "meetingId": "m-p0", "preparingTimeoutSec": 300, "decisionWindowSec": 60,
            "contextBudget": {}, "allowConflicts": False,
        }, hooks=hooks(),
    )
    assert p0_confirmed["ok"] is True
    assert p0["meetings"]["m-p0"]["resolutionPolicy"] == "user_decision"


def test_confirm_uses_default_detailed_context_when_not_overridden():
    data = empty_data(); request = create_pending(data)
    result = confirm_command(
        data, request["id"], {"confirmedBy": "user"},
        project_title="Project",
        lifecycle_defaults={
            "meetingId": "m1", "preparingTimeoutSec": 300, "decisionWindowSec": 60,
            "contextBudget": {}, "allowConflicts": False,
        }, hooks=hooks(),
    )
    assert result["ok"] is True
    assert "Context" in data["meetings"]["m1"]["context"]
    assert data["requests"][request["id"]]["review"]["selectedContextIds"] == ["task:t1"]


def test_explicit_empty_context_selection_is_respected():
    data = empty_data()
    result = create_command(
        data, {"id": "p1", "title": "Project"}, {"id": "t1", "title": "Task"},
        request_body(selectedContextIds=[]),
        [{"id": "task:t1", "sourceKind": "task", "title": "Task", "summary": "Context"}],
        hooks(),
    )
    request = result["request"]
    assert data["requests"][request["id"]]["requestedContext"]["selectedContextIds"] == []
    confirmed = confirm_command(
        data, request["id"], {"confirmedBy": "user"},
        project_title="Project",
        lifecycle_defaults={
            "meetingId": "m1", "preparingTimeoutSec": 300, "decisionWindowSec": 60,
            "contextBudget": {}, "allowConflicts": False,
        }, hooks=hooks(),
    )
    assert confirmed["ok"] is True
    assert data["meetings"]["m1"]["context"] == ""
    assert data["events"]["m1"][0]["type"] == "meeting_created"
    assert data["occupancy"] == {"a1": "m1", "a2": "m1"}
    repeated = confirm_command(
        data, request["id"], {}, project_title="Project",
        lifecycle_defaults={"meetingId": "other"}, hooks=hooks(),
    )
    assert repeated["idempotent"] is True and len(data["meetings"]) == 1


def test_hr_is_eligible_in_request_and_confirmed_meeting_occupancy():
    data = empty_data()
    created = create_command(
        data,
        {"id": "p1", "title": "Project"},
        {"id": "t1", "title": "Task"},
        request_body(
            requestingAgentId="a1",
            suggestedParticipants=["a1", "hr"],
            suggestedModerator="hr",
        ),
        [],
        hooks(),
    )
    assert created["ok"] is True
    confirmed = confirm_command(
        data,
        created["request"]["id"],
        {"participants": ["a1", "hr"], "moderator": "hr", "confirmedBy": "user"},
        project_title="Project",
        lifecycle_defaults={
            "meetingId": "meeting-with-hr",
            "preparingTimeoutSec": 300,
            "decisionWindowSec": 60,
            "contextBudget": {},
            "allowConflicts": False,
        },
        hooks=hooks(),
    )
    assert confirmed["ok"] is True
    assert data["occupancy"] == {"a1": "meeting-with-hr", "hr": "meeting-with-hr"}


def test_context_public_projection_reject_and_resolution_are_compatible():
    data = empty_data(); request = create_pending(data)
    context, snapshots = selected_context(data["requests"][request["id"]], ["task:t1"], "extra")
    assert "Context" in context and "extra" in context and snapshots[0]["selected"] is True
    assert all(not item["selected"] for item in public_request(data["requests"][request["id"]])["contextCandidates"])
    rejected = reject_command(data, request["id"], {"reason": "Not needed"}, hooks())
    assert rejected["request"]["status"] == "rejected"
    resolved = resolve_blocker_command(data, request["id"], "cleared", {"outcome": "manual"}, hooks())
    assert resolved["request"]["taskBlocker"]["status"] == "cleared"


def test_project_reset_resolves_unresolved_task_blockers_without_deleting_audit_records():
    data = empty_data()
    request = create_pending(data)

    result = reset_project_task_blockers_command(
        data,
        "p1",
        ["t1"],
        actor="tester",
        reason="project reset: task_state",
        hooks=hooks(),
    )

    stored = data["requests"][request["id"]]
    assert result == {"ok": True, "resetRequestIds": [request["id"]], "resetRequestCount": 1}
    assert stored["status"] == "pending"
    assert stored["taskBlocker"]["status"] == "cleared"
    assert stored["taskBlocker"]["resolvedAt"] == "now"
    assert stored["taskBlocker"]["resetBy"] == "tester"
    assert unresolved_for_task(stored, "p1", "t1") is False

    recreated = create_command(
        data, {"id": "p1", "title": "Project"}, {"id": "t1", "title": "Task"},
        request_body(idempotencyKey="request-after-reset"),
        [{"id": "task:t1", "sourceKind": "task", "title": "Task", "summary": "Context"}],
        hooks(),
    )
    assert recreated["ok"] is True
    assert recreated.get("created") is True
    assert recreated["request"]["id"] != request["id"]
