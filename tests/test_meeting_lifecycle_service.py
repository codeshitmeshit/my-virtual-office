import threading

from app.services.meeting_repository import MeetingDomainRepository
from app.services.meeting_lifecycle import (
    AgentTurnHooks, ArbitrationHooks, ConflictHooks, CreateHooks, MeetingLifecycleError,
    MutationHooks, TargetedQuestionHooks, TerminalHooks, TimeoutHooks, TransitionHooks,
    agenda_change_command, arbitration_command, claim_occupancy, commit_agent_turn,
    compare_token, conflict_action_command, create_command,
    commit_targeted_question, complete_meeting, intervention_command, prepare_agent_turn, prepare_targeted_question,
    rebuild_occupancy, release_occupancy,
    release_timed_out_preparing, replace_participant, validate_participant_eligibility,
    token_is_current, transition_command, validate_transition,
)


def meeting(mid="m1", stage="draft", version=1, participants=None):
    return {"id": mid, "stage": stage, "version": version, "participants": participants or ["a1", "a2"]}


def participant_error(value):
    if value != "archive-manager":
        return None
    return {
        "error": "Archive manager cannot participate in executable meetings",
        "code": "archive_manager_not_meeting_participant",
        "systemRole": "archive_manager",
        "_status": 400,
    }


def test_transition_matrix_and_version_gate():
    validate_transition(meeting(), "preparing", expected_version=1)
    try: validate_transition(meeting(), "completed"); assert False
    except MeetingLifecycleError as error: assert error.code == "meeting_transition_invalid"
    try: validate_transition(meeting(), "preparing", expected_version=2); assert False
    except MeetingLifecycleError as error: assert error.code == "meeting_version_stale"


def test_compare_token_rejects_phase_version_and_sequence_changes():
    value = meeting(stage="active_discussion", version=3)
    events = [{"sequence": 4}]
    token = compare_token(value, events, call_id="c1", participant="a1")
    assert token_is_current(value, events, token)
    assert not token_is_current({**value, "version": 4}, events, token)
    assert not token_is_current(value, events + [{"sequence": 5}], token)


def test_occupancy_claim_release_and_stale_owner_protection():
    data = {"meetings": {"m1": meeting(stage="active_discussion"), "m2": meeting("m2", "active_discussion", participants=["a3"] )}, "occupancy": {}}
    claim_occupancy(data, "m1", ["a1", "a2"])
    try: claim_occupancy(data, "m2", ["a1"]); assert False
    except MeetingLifecycleError as error: assert error.code == "meeting_participant_occupied"
    data["occupancy"]["a1"] = "m2"
    assert release_occupancy(data, "m1", ["a1", "a2"]) == ["a2"]
    assert data["occupancy"]["a1"] == "m2"


def test_rebuild_detects_two_active_owners_and_preserves_unknown_diagnostic_owner():
    data = {"meetings": {"m1": meeting(stage="active_discussion")}, "occupancy": {"external": "legacy-owner"}}
    assert rebuild_occupancy(data)["external"] == "legacy-owner"
    data = {"meetings": {"m1": meeting(stage="active_discussion"), "m2": meeting("m2", "preparing", participants=["a1"])}, "occupancy": {}}
    try: rebuild_occupancy(data); assert False
    except MeetingLifecycleError as error: assert error.code == "meeting_occupancy_conflict"
    forced_one = {**meeting(stage="active_discussion", participants=["a1"]), "participantState": {"a1": {"forcedJoin": True}}}
    forced_two = {**meeting("m2", "active_discussion", participants=["a1"]), "participantState": {"a1": {"forcedJoin": True}}}
    try: rebuild_occupancy({"meetings": {"m1": forced_one, "m2": forced_two}, "occupancy": {}}); assert False
    except MeetingLifecycleError as error: assert error.code == "meeting_occupancy_conflict"


def test_transition_command_owns_terminal_cleanup_event_and_idempotency():
    value = meeting(stage="summarizing", version=4)
    data = {"meetings": {"m1": value}, "events": {"m1": []}, "occupancy": {"a1": "m1", "a2": "m1"}, "idempotency": {}}
    def append_event(store, current, event_type, **kwargs):
        current["version"] += 1
        event = {"sequence": len(store["events"]["m1"]) + 1, "type": event_type}
        store["events"]["m1"].append(event)
        return event
    hooks = TransitionHooks(
        append_event=append_event, continue_decision=lambda *args, **kwargs: None,
        mark_preparing=lambda current: None, resume_original_work=lambda *args: None,
        ensure_action_items=lambda *args: None, award_points=lambda current: current.update({"awarded": True}),
    )
    result = transition_command(data, "m1", {"stage": "completed", "expectedVersion": 4, "idempotencyKey": "done"}, hooks)
    assert result["ok"] is True and result["terminal"] is True
    assert data["occupancy"] == {} and value["awarded"] is True
    repeated = transition_command(data, "m1", {"stage": "completed", "idempotencyKey": "done"}, hooks)
    assert repeated["idempotent"] is True


def test_create_command_owns_conflict_and_atomic_initial_state():
    data = {"meetings": {}, "events": {}, "occupancy": {}, "idempotency": {}}
    def append_event(store, current, kind, **kwargs):
        current["version"] += 1; current["lastEventSequence"] += 1
        event = {"sequence": current["lastEventSequence"], "type": kind}
        store.setdefault("events", {}).setdefault(current["id"], []).append(event)
        return event
    config = {
        "meetingId": "m1", "topic": "Topic", "agenda": "Topic", "purpose": "Decide",
        "meetingType": "discussion", "participants": ["a1", "a2"], "moderator": "a1",
        "organizer": "a1", "createdBy": "user", "createdByType": "user", "createdByAgentId": "",
        "projectId": "", "projectTitle": "", "maxRounds": 2, "decisionWindowSec": 60,
        "resolutionPolicy": "moderator_decision", "context": "", "contextMode": "incremental",
        "contextBudget": {}, "source": {}, "preparingTimeoutSec": 300, "now": "now",
        "actor": {"type": "user", "id": "user"}, "idempotencyKey": "create-1", "allowConflicts": False,
    }
    hooks = CreateHooks(rebuild_occupancy=lambda store: rebuild_occupancy(store), build_conflicts=lambda *args: [], append_event=append_event)
    result = create_command(data, config, hooks)
    assert result["meeting"]["stage"] == "preparing"
    assert data["occupancy"] == {"a1": "m1", "a2": "m1"}
    assert create_command(data, config, hooks)["idempotent"] is True


def test_agent_turn_prepare_and_compare_commit_discards_stale_result():
    data = {"meetings": {"m1": meeting(stage="active_discussion", version=1)}, "events": {"m1": []}}
    ignored = []
    def append_event(store, current, kind, **kwargs):
        current["version"] += 1
        event = {"sequence": len(store["events"]["m1"]) + 1, "type": kind, "payload": kwargs.get("payload", {})}
        store["events"]["m1"].append(event); return event
    hooks = AgentTurnHooks(
        build_prompt=lambda *args: "prompt", append_event=append_event,
        normalize_reply=lambda reply: {"text": reply}, provider_ref=lambda speaker: {"agentId": speaker},
        formal_turn_exists=lambda *args: False, pending_turn_exists=lambda *args: False,
        append_ignored=lambda *args: ignored.append(args[6]), update_summary=lambda *args: None,
    )
    prepared = prepare_agent_turn(data, "m1", "active_discussion", "a1", hooks)
    data["meetings"]["m1"]["version"] += 1
    result = commit_agent_turn(data, "m1", "active_discussion", "a1", {"ok": True, "reply": "late"}, prepared["pending"], prepared["token"], hooks)
    assert result["ignoredProviderCompletion"] is True
    assert ignored == ["meeting_state_changed"]


def test_intervention_and_agenda_commands_validate_version_and_replay():
    value = {**meeting(stage="active_discussion", version=2), "agenda": "old", "round": 1, "lastEventSequence": 0}
    data = {"meetings": {"m1": value}, "events": {"m1": []}, "idempotency": {}}
    def append_event(store, current, kind, **kwargs):
        current["version"] += 1
        current["lastEventSequence"] += 1
        event = {"sequence": current["lastEventSequence"], "type": kind, "payload": kwargs["payload"]}
        store["events"]["m1"].append(event)
        return event
    hooks = MutationHooks(append_event=append_event)
    stale = intervention_command(data, "m1", {"text": "hello", "expectedVersion": 1}, hooks)
    assert stale["_status"] == 409 and data["events"]["m1"] == []
    first = intervention_command(data, "m1", {"text": "hello", "expectedVersion": 2, "idempotencyKey": "i1"}, hooks)
    assert first["event"]["payload"]["kind"] == "statement"
    replay = intervention_command(data, "m1", {"text": "changed", "idempotencyKey": "i1"}, hooks)
    assert replay["idempotent"] is True and len(data["events"]["m1"]) == 1
    changed = agenda_change_command(data, "m1", {"agenda": "new", "expectedVersion": 3, "idempotencyKey": "a1"}, hooks)
    assert changed["ok"] is True and value["agenda"] == "new"
    assert changed["event"]["payload"]["previousAgenda"] == "old"


def test_preparing_timeout_releases_only_owned_occupancy_and_is_idempotent():
    value = {**meeting(stage="preparing"), "preparingStartedAt": "old"}
    data = {"meetings": {"m1": value}, "events": {"m1": []}, "occupancy": {"a1": "new-owner", "a2": "m1"}}
    def append_event(store, current, kind, **kwargs):
        event = {"sequence": 1, "type": kind, "payload": kwargs["payload"]}
        store["events"]["m1"].append(event)
        return event
    hooks = TimeoutHooks(append_event=append_event, parse_timestamp=lambda value: 10.0)
    released = release_timed_out_preparing(data, now_timestamp=50.0, now_iso="now", timeout_seconds=30, hooks=hooks)
    assert released == ["m1"] and value["stage"] == "cancelled"
    assert data["occupancy"] == {"a1": "new-owner"}
    assert data["events"]["m1"][0]["payload"]["releasedParticipants"] == ["a2"]
    assert release_timed_out_preparing(data, now_timestamp=60.0, now_iso="later", timeout_seconds=30, hooks=hooks) == []


def test_targeted_question_uses_sequence_token_to_discard_completion_after_intervention():
    value = {**meeting(stage="awaiting_user_decision", version=1), "decisionForStage": "active_discussion", "round": 1}
    data = {"meetings": {"m1": value}, "events": {"m1": []}, "idempotency": {}}
    ignored = []
    def append_event(store, current, kind, **kwargs):
        current["version"] += 1
        event = {"sequence": len(store["events"]["m1"]) + 1, "type": kind, "payload": kwargs.get("payload", {})}
        store["events"]["m1"].append(event)
        return event
    def append_ignored(*args, **kwargs):
        ignored.append(args[6])
        return {"reason": args[6]}
    hooks = TargetedQuestionHooks(
        append_event=append_event, build_prompt=lambda *args: "prompt",
        normalize_reply=lambda reply: {"text": reply}, provider_ref=lambda target: {"agentId": target},
        append_ignored=append_ignored, update_summary=lambda *args: None,
    )
    prepared = prepare_targeted_question(data, "m1", {"question": "why", "target": "a1"}, hooks)
    append_event(data, value, "user_intervention", payload={})
    committed = commit_targeted_question(data, "m1", prepared, {"ok": True, "reply": "late"}, hooks)
    assert committed.get("ignored") is not None
    assert ignored == ["meeting_state_changed"]
    assert not any(event["type"] == "participant_turn" for event in data["events"]["m1"])


def test_participant_eligibility_and_replacement_are_domain_invariants():
    try:
        validate_participant_eligibility(
            ["a1", "archive-manager"], "a1", participant_error=participant_error,
        )
        assert False
    except MeetingLifecycleError as error:
        assert error.code == "archive_manager_not_meeting_participant"
    value = {**meeting(stage="conflict"), "moderator": "a1", "speakerQueue": ["a1", "a2"], "participantState": {"a1": {}, "a2": {}}}
    replace_participant(value, "a1", "a3", now="now")
    assert value["participants"] == ["a3", "a2"]
    assert value["moderator"] == "a3" and value["speakerQueue"] == ["a3", "a2"]
    assert value["participantState"]["a3"]["replacedAgentId"] == "a1"


def test_complete_meeting_cleans_up_without_releasing_a_new_owner():
    value = meeting(stage="summarizing")
    data = {"meetings": {"m1": value}, "events": {"m1": []}, "occupancy": {"a1": "m2", "a2": "m1"}}
    def append_event(store, current, kind, **kwargs):
        event = {"sequence": len(store["events"]["m1"]) + 1, "type": kind, "payload": kwargs.get("payload", {})}
        store["events"]["m1"].append(event)
        return event
    hooks = TerminalHooks(
        append_event=append_event, resume_original_work=lambda *args: None,
        ensure_action_items=lambda *args: None, award_points=lambda current: current.update({"awarded": True}),
    )
    completed = complete_meeting(
        data, value, {"summary": "done"}, actor={"type": "system", "id": "system"},
        reason="done", hooks=hooks,
    )
    assert value["stage"] == "completed" and completed["releasedParticipants"] == ["a2"]
    assert data["occupancy"] == {"a1": "m2"} and value["awarded"] is True


def test_conflict_replacement_rejects_archive_manager_and_updates_participant_atomically():
    value = {
        **meeting(stage="conflict"), "moderator": "a1", "speakerQueue": ["a1", "a2"],
        "participantState": {"a1": {}, "a2": {}},
        "conflicts": [{"agentId": "a1", "status": "open"}],
    }
    data = {"meetings": {"m1": value}, "events": {"m1": []}, "occupancy": {}, "idempotency": {}}
    def append_event(store, current, kind, **kwargs):
        event = {"sequence": len(store["events"]["m1"]) + 1, "type": kind}
        store["events"]["m1"].append(event); return event
    hooks = ConflictHooks(
        append_event=append_event, build_conflicts=lambda *args, **kwargs: [],
        busy_context=lambda *args, **kwargs: {"busy": False}, advisory=lambda item: {},
        original_work_snapshot=lambda *args: {"pauseState": {}},
        has_open_conflicts=lambda current: any(item.get("status") == "open" for item in current.get("conflicts", [])),
        mark_preparing=lambda *args: None, rebuild_occupancy=lambda store: None,
        participant_error=participant_error, now=lambda: "now", new_id=lambda: "c1",
    )
    rejected = conflict_action_command(data, "m1", {"action": "replace", "agentId": "a1", "replacement": "archive-manager"}, hooks)
    assert rejected["code"] == "archive_manager_not_meeting_participant"
    result = conflict_action_command(data, "m1", {"action": "replace", "agentId": "a1", "replacement": "a3"}, hooks)
    assert result["ok"] is True and value["participants"] == ["a3", "a2"]


def test_arbitration_completion_uses_shared_terminal_cleanup():
    value = {**meeting(stage="awaiting_user_decision"), "round": 1, "arbitration": {}}
    data = {"meetings": {"m1": value}, "events": {"m1": []}, "occupancy": {"a1": "m1", "a2": "m1"}, "idempotency": {}}
    def append_event(store, current, kind, **kwargs):
        event = {"sequence": len(store["events"]["m1"]) + 1, "type": kind}
        store["events"]["m1"].append(event); return event
    terminal = TerminalHooks(append_event=append_event, resume_original_work=lambda *args: None, ensure_action_items=lambda *args: None, award_points=lambda *args: None)
    hooks = ArbitrationHooks(
        append_event=append_event, continue_decision=lambda *args, **kwargs: None,
        fallback_result=lambda *args: {"summary": "base", "actionItems": []},
        truncate=lambda text, limit: text[:limit], terminal=terminal,
    )
    result = arbitration_command(data, "m1", {"action": "decide", "decision": "ship"}, hooks)
    assert result["ok"] is True and value["stage"] == "completed"
    assert value["result"]["decision"] == "ship" and data["occupancy"] == {}


def test_repository_serializes_competing_claims_but_allows_unrelated_meetings(tmp_path):
    repo = MeetingDomainRepository(tmp_path)
    repo.update(lambda data: None)
    barrier = threading.Barrier(3)
    outcomes = []
    def create_and_claim(meeting_id, participant):
        barrier.wait()
        try:
            def mutate(data):
                current = meeting(meeting_id, "preparing", participants=[participant])
                data["meetings"][meeting_id] = current
                claim_occupancy(data, meeting_id, [participant])
            repo.update(mutate)
            outcomes.append((meeting_id, "ok"))
        except MeetingLifecycleError as error:
            outcomes.append((meeting_id, error.code))
    threads = [
        threading.Thread(target=create_and_claim, args=("m1", "shared")),
        threading.Thread(target=create_and_claim, args=("m2", "shared")),
    ]
    for thread in threads: thread.start()
    barrier.wait()
    for thread in threads: thread.join(timeout=3)
    assert sorted(status for _, status in outcomes) == ["meeting_participant_occupied", "ok"]
    snapshot = repo.snapshot()
    assert snapshot["occupancy"]["shared"] in {"m1", "m2"}
    repo.update(lambda data: (data["meetings"].update({"m3": meeting("m3", "preparing", participants=["other"])}), claim_occupancy(data, "m3", ["other"])))
    assert repo.snapshot()["occupancy"]["other"] == "m3"
