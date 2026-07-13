from app.services.meeting_action_items import (
    ActionHooks, attach_to_project, commit_confirmation, ensure_drafts,
    mutate_command, normalize, project_action_key,
)


def hooks():
    def append_event(data, meeting, kind, **kwargs):
        meeting["version"] = int(meeting.get("version") or 0) + 1
        event = {"sequence": len(data.setdefault("events", {}).setdefault(meeting["id"], [])) + 1, "type": kind}
        data["events"][meeting["id"]].append(event)
        return event
    return ActionHooks(now=lambda: "now", append_event=append_event)


def data_with_actions():
    meeting = {
        "id": "m1", "version": 1, "projectId": "p1",
        "source": {"projectId": "p1", "taskId": "t1", "meetingRequestId": "r1"},
        "result": {"actionItems": [
            {"title": "Implement", "owner": "a1", "priority": "high"},
            "Review",
        ]},
    }
    return {
        "meetings": {"m1": meeting}, "events": {"m1": []},
        "idempotency": {"meetings": {}, "requests": {}, "callbacks": {}, "actionItems": {}},
    }, meeting


def test_normalization_and_draft_identity_are_stable_and_old_shape_compatible():
    data, meeting = data_with_actions()
    drafts = ensure_drafts(data, meeting, hooks())
    assert [draft["id"] for draft in drafts] == ["ai-1", "ai-2"]
    assert drafts[0]["assignee"] == "a1" and drafts[1]["title"] == "Review"
    assert ensure_drafts(data, meeting, hooks()) is drafts
    assert len([event for event in data["events"]["m1"] if event["type"] == "action_item_drafts_created"]) == 1


def test_legacy_confirmed_draft_projects_canonical_and_compatibility_task_ids():
    data, meeting = data_with_actions()
    meeting["actionItemDrafts"] = [{
        "id": "legacy", "status": "confirmed", "sourceTaskId": "t-old", "meetingActionItemId": "legacy-record",
    }]
    drafts = ensure_drafts(data, meeting, hooks())
    assert drafts[0]["targetTaskId"] == "t-old"
    assert drafts[0]["sourceTaskId"] == "t-old"


def test_update_reject_keep_and_audit_history_are_bounded():
    data, meeting = data_with_actions(); ensure_drafts(data, meeting, hooks())
    updated = mutate_command(data, "m1", "ai-1", {"action": "update", "title": "Changed", "actorId": "u"}, hooks())
    assert updated["actionItem"]["title"] == "Changed"
    rejected = mutate_command(data, "m1", "ai-2", {"action": "reject", "reason": "No"}, hooks())
    assert rejected["actionItem"]["status"] == "rejected"
    for index in range(105):
        mutate_command(data, "m1", "ai-1", {"action": "update", "description": str(index)}, hooks())
    assert len(meeting["actionItemDrafts"][0]["audit"]) == 100


def test_project_projection_dedupes_and_preserves_unrelated_concurrent_fields():
    data, meeting = data_with_actions(); draft = ensure_drafts(data, meeting, hooks())[0]
    project = {"id": "p1", "title": "P", "concurrentField": "keep", "tasks": [{"id": "t1", "title": "T", "meetingActionItems": [], "meetingBlocker": {"requestId": "r1", "meetingId": "m1"}}]}
    first = attach_to_project(project, "t1", meeting, draft, "ai-1", "u", draft, "now")
    second = attach_to_project(project, "t1", meeting, draft, "ai-1", "u", draft, "later")
    assert first["record"]["id"] == project_action_key("m1", "ai-1")
    assert second["idempotent"] is True and len(project["tasks"][0]["meetingActionItems"]) == 1
    assert project["concurrentField"] == "keep"


def test_compare_commit_rejects_stale_draft_and_retry_commits_existing_projection():
    data, meeting = data_with_actions(); ensure_drafts(data, meeting, hooks())
    prepared = mutate_command(data, "m1", "ai-1", {"action": "confirm", "idempotencyKey": "c1"}, hooks())
    project = {"id": "p1", "tasks": [{"id": "t1", "meetingActionItems": [], "meetingBlocker": {"requestId": "r1", "meetingId": "m1"}}]}
    projected = attach_to_project(project, "t1", prepared["meeting"], prepared["actionItem"], "ai-1", "u", prepared["before"], "now")
    meeting["actionItemDrafts"][0]["updatedAt"] = "changed"
    stale = commit_confirmation(data, "m1", "ai-1", prepared, projected, hooks())
    assert stale["code"] == "action_item_stale"
    meeting["actionItemDrafts"][0]["updatedAt"] = prepared["compare"]["updatedAt"]
    committed = commit_confirmation(data, "m1", "ai-1", prepared, projected, hooks())
    assert committed["actionItem"]["status"] == "confirmed"
    assert committed["meetingActionItem"]["id"] == "meeting:m1:action:ai-1"
