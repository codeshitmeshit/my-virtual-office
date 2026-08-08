from app.services.meeting_human_decision_projection import (
    build_event_payload,
    format_agent_history_event,
    project_transcript_event,
)


def resolved_event(**payload_overrides):
    payload = {
        "decisionId": "decision-1",
        "title": "确认发布策略",
        "answer": "分阶段发布",
        "customAnswer": "",
        "stage": "active_discussion",
        "round": 2,
    }
    payload.update(payload_overrides)
    return {
        "type": "human_decision_resolved",
        "sequence": 9,
        "createdAt": "2026-08-08T17:00:00+08:00",
        "actor": {"type": "user", "id": "human-decision-center"},
        "payload": payload,
    }


def test_build_event_payload_uses_originating_round_and_decision_metadata():
    payload = build_event_payload(
        {
            "stage": "awaiting_user_decision",
            "round": 3,
            "decisionForStage": "active_discussion",
            "decisionForRound": 2,
        },
        {
            "decisionId": "decision-1",
            "decisionTitle": "确认发布策略",
            "decision": "分阶段发布",
            "customAnswer": "企业租户延长到 14 天",
        },
    )

    assert payload == {
        "decisionId": "decision-1",
        "title": "确认发布策略",
        "answer": "分阶段发布",
        "customAnswer": "企业租户延长到 14 天",
        "stage": "active_discussion",
        "round": 2,
    }


def test_build_event_payload_suppresses_custom_answer_that_duplicates_final_answer():
    payload = build_event_payload(
        {"stage": "awaiting_user_decision", "decisionForStage": "active_opening"},
        {"decisionId": "decision-1", "decision": "使用自定义策略", "customAnswer": "使用自定义策略"},
    )

    assert payload["customAnswer"] == ""


def test_resolved_decision_projects_to_transcript_and_agent_history():
    event = resolved_event()

    turn = project_transcript_event(event)
    text = format_agent_history_event(event)

    assert turn == {
        "type": "human_decision_resolved",
        "sequence": 9,
        "stage": "active_discussion",
        "round": 2,
        "decisionId": "decision-1",
        "title": "确认发布策略",
        "answer": "分阶段发布",
        "customAnswer": "",
        "speaker": "human-decision-center",
        "actorType": "user",
        "ok": True,
        "durationMs": 0,
        "providerRef": {},
        "createdAt": "2026-08-08T17:00:00+08:00",
    }
    assert "确认发布策略" in text
    assert "分阶段发布" in text
    assert "do not request another decision for the same issue" in text


def test_non_decision_event_is_not_projected():
    event = {"type": "participant_turn", "payload": {"text": "hello"}}

    assert project_transcript_event(event) is None
    assert format_agent_history_event(event) is None
