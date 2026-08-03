"""Meeting prompt documents rendered through the common business bridge."""

from __future__ import annotations

from typing import Any, Mapping

from services import business_prompt_bridge
from services.human_decision_prompt_guidance import human_decision_section


TURN_SCHEMA = {
    "position": "...",
    "reasoning": "...",
    "disagreements": ["..."],
    "questions": ["..."],
    "suggestedNextStep": "...",
    "confidence": "high|medium|low",
}

RESULT_SCHEMA = {
    "outcome": "approved|rejected|no_consensus|needs_user_decision",
    "summary": "...",
    "decision": "...",
    "rationale": "...",
    "unresolvedQuestions": ["..."],
    "disagreements": ["..."],
    "actionItems": [{"owner": "...", "item": "..."}],
}

ADVISORY_SCHEMA = {
    "recommendation": "wait|reserve|replace|force_join",
    "estimatedAvailability": "例如 2-5 分钟、当前会议结束后、unknown",
    "busyReason": "用中文简述你为什么忙",
    "interruptionRisk": "用中文说明打断风险",
    "resumeNotes": "用中文说明如果被打断如何恢复或为什么不能恢复",
    "confidence": "high|medium|low",
}


def live_advisory_prompt(*, meeting: Mapping[str, Any], conflict: Mapping[str, Any], occupied_meeting_id: str = "") -> str:
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "meeting.advisory",
            "operation": "busy_agent",
            "locale": "zh-CN",
            "root": "meeting_live_advisory_prompt",
            "target": {"agentId": conflict.get("agentId") or ""},
            "sections": [
                {"name": "role", "value": "你是 Virtual Office 的 busy-agent subagent advisory turn。", "trusted": True},
                {"name": "situation", "value": "现在有人想邀请你参加另一场 AI 会议，但系统检测到你正在忙。", "trusted": True},
                {"name": "boundary", "value": "请只评估你自己的可用性和打断风险，不要替用户执行等待、更换或强制加入。", "trusted": True},
                {
                    "name": "candidate_meeting",
                    "value": {"topic": meeting.get("topic") or meeting.get("agenda") or meeting.get("id")},
                },
                {
                    "name": "conflict",
                    "value": {
                        "reason": conflict.get("reason") or conflict.get("busyKind"),
                        "summary": conflict.get("summary") or "",
                        "occupied_meeting_id": occupied_meeting_id,
                        "pause_capability": conflict.get("pauseCapability") or "unknown",
                        "risk_level": conflict.get("riskLevel") or "medium",
                    },
                },
                {"name": "json_schema", "value": ADVISORY_SCHEMA, "trusted": True},
            ],
            "output": "返回且只返回一个 JSON 对象，不要 Markdown，不要额外说明。",
        }
    )


def targeted_question_prompt(*, question: str) -> str:
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "meeting.targeted_question",
            "operation": "ask",
            "locale": "zh-CN",
            "root": "targeted_question",
            "sections": [
                {"name": "from", "value": "user", "trusted": True},
                {"name": "question", "value": question},
                {
                    "name": "rules",
                    "trusted": True,
                    "value": [
                        "Answer this targeted question once. Keep the same JSON schema.",
                        "Do not treat this as a formal round turn.",
                    ],
                },
            ],
        }
    )


def result_prompt(
    *,
    meeting: Mapping[str, Any],
    transcript: str,
    policy: str,
    outcome_rule: str,
    policy_rule: str,
) -> str:
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "meeting.result",
            "operation": "summarize",
            "locale": "zh-CN",
            "root": "meeting_result_prompt",
            "sections": [
                {"name": "role", "value": "You are the meeting moderator.", "trusted": True},
                {"name": "goal", "value": "Summarize and close this meeting based only on the transcript below.", "trusted": True},
                {
                    "name": "meeting",
                    "value": {
                        "topic": meeting.get("topic") or "Untitled Meeting",
                        "purpose": meeting.get("purpose") or "",
                        "type": meeting.get("meetingType") or "discussion",
                        "resolution_policy": policy,
                        "resolution_policy_summary": f"Resolution policy: {policy}",
                        "participants": ", ".join(meeting.get("participants") or []),
                    },
                },
                {"name": "transcript", "value": transcript or "(no participant turns yet)"},
                {
                    "name": "outcome_rules",
                    "trusted": True,
                    "value": {
                        "outcome_rule": outcome_rule,
                        "policy_rule": policy_rule,
                    },
                },
                human_decision_section("meeting"),
                {"name": "json_schema", "value": RESULT_SCHEMA, "trusted": True},
            ],
            "output": "Return exactly one JSON object and no surrounding prose or Markdown fences.",
        }
    )


def turn_prompt(
    *,
    meeting: Mapping[str, Any],
    speaker: str,
    stage: str,
    context_values: Mapping[str, str],
) -> str:
    sections: list[dict[str, Any]] = [
        {
            "name": "meeting",
            "value": {
                "topic": meeting.get("topic") or "Untitled Meeting",
                "agenda": f"Current agenda: {meeting.get('agenda') or meeting.get('topic') or 'Untitled Meeting'}",
                "purpose": meeting.get("purpose") or "",
                "type": meeting.get("meetingType") or "discussion",
                "stage": stage,
                "round": {
                    "name": "round",
                    "attrs": {"current": meeting.get("round") or 0, "max": meeting.get("maxRounds") or 0},
                    "value": "",
                },
                "speaker": speaker,
                "moderator": meeting.get("moderator") or "",
            },
        }
    ]
    for name, value in context_values.items():
        sections.append({"name": name, "value": value})
    sections.extend(
        [
            {"name": "instruction", "value": "Contribute to the meeting. Avoid repeating previous points.", "trusted": True},
            human_decision_section("meeting"),
            {"name": "json_schema", "value": TURN_SCHEMA, "trusted": True},
        ]
    )
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "meeting.turn",
            "operation": "participant",
            "locale": "zh-CN",
            "root": "meeting_turn_prompt",
            "target": {"speaker": speaker},
            "sections": sections,
            "output": "Return exactly one JSON object and no surrounding prose or Markdown fences.",
        }
    )


__all__ = [
    "ADVISORY_SCHEMA",
    "RESULT_SCHEMA",
    "TURN_SCHEMA",
    "live_advisory_prompt",
    "result_prompt",
    "targeted_question_prompt",
    "turn_prompt",
]
