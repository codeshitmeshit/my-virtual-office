from app.services.human_decision_chat_continuation import ContinuationDispatchResult
from app.services.human_decision_meeting_continuation import (
    HumanDecisionMeetingContinuation,
    MeetingContinuationPorts,
)
from app.services.human_decisions import HumanDecisionContinuationClaim


def claim(decision_id="decision-1"):
    return HumanDecisionContinuationClaim(
        decision_id=decision_id,
        claim_token="claim-1",
        kind="meeting",
        agent_id="agent-1",
        binding={"meetingId": "meeting-1"},
        attempts=1,
        decision={
            "id": decision_id,
            "source": {"type": "meeting", "id": "meeting-1", "label": "Review"},
            "title": "Confirm rollout",
            "situation": "Choose rollout",
            "resolution": {"answer": "Approve staged rollout", "optionId": "B"},
        },
    )


def test_awaiting_meeting_transitions_and_wakes_once():
    state = {"id": "meeting-1", "stage": "awaiting_user_decision", "humanDecisionId": "decision-1"}
    transitions = []
    wakes = []

    def transition(meeting_id, body):
        transitions.append(body)
        state.update({"stage": "active_discussion", "humanDecisionResumeKey": body["idempotencyKey"]})
        return {"ok": True, "meeting": dict(state)}

    adapter = HumanDecisionMeetingContinuation(ports=MeetingContinuationPorts(
        load=lambda meeting_id: dict(state),
        transition=transition,
        wake=lambda meeting_id, prompt: wakes.append((meeting_id, prompt)) or {"ok": True},
    ))

    result = adapter.dispatch(claim())

    assert result == ContinuationDispatchResult("dispatched")
    assert transitions[0]["action"] == "continue_decision"
    assert transitions[0]["decision"] == "Approve staged rollout"
    assert transitions[0]["decisionTitle"] == "Confirm rollout"
    assert transitions[0]["customAnswer"] == ""
    assert transitions[0]["idempotencyKey"] == "human-decision-resume:decision-1"
    assert wakes[0][0] == "meeting-1"
    assert "Approve staged rollout" in wakes[0][1]


def test_replayed_meeting_resume_is_idempotent_without_second_wake():
    state = {
        "id": "meeting-1",
        "stage": "active_discussion",
        "humanDecisionResumeKey": "human-decision-resume:decision-1",
    }
    wakes = []
    adapter = HumanDecisionMeetingContinuation(ports=MeetingContinuationPorts(
        load=lambda meeting_id: dict(state),
        transition=lambda meeting_id, body: {"ok": True},
        wake=lambda meeting_id, prompt: wakes.append(meeting_id),
    ))

    assert adapter.dispatch(claim()) == ContinuationDispatchResult("dispatched")
    assert wakes == []


def test_terminal_meeting_is_not_resumed():
    adapter = HumanDecisionMeetingContinuation(ports=MeetingContinuationPorts(
        load=lambda meeting_id: {"id": meeting_id, "stage": "completed", "humanDecisionId": "decision-1"},
        transition=lambda meeting_id, body: {"ok": True},
        wake=lambda meeting_id, prompt: {"ok": True},
    ))

    assert adapter.dispatch(claim()) == ContinuationDispatchResult("failed", "meeting_not_resumable")
