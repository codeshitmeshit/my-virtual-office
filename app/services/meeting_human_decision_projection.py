"""Canonical projections for resolved meeting human decisions."""

from __future__ import annotations

from typing import Any, Mapping


EVENT_TYPE = "human_decision_resolved"


def _text(value: Any) -> str:
    return str(value or "").strip()


def build_event_payload(
    meeting: Mapping[str, Any],
    body: Mapping[str, Any],
) -> dict[str, Any]:
    answer = _text(body.get("decision"))
    custom_answer = _text(body.get("customAnswer"))
    if custom_answer == answer:
        custom_answer = ""
    return {
        "decisionId": _text(body.get("decisionId")),
        "title": _text(body.get("decisionTitle")),
        "answer": answer,
        "customAnswer": custom_answer,
        "stage": _text(meeting.get("decisionForStage") or meeting.get("stage")),
        "round": int(meeting.get("decisionForRound") or meeting.get("round") or 0),
    }


def project_transcript_event(event: Mapping[str, Any]) -> dict[str, Any] | None:
    if event.get("type") != EVENT_TYPE:
        return None
    payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
    actor = event.get("actor") if isinstance(event.get("actor"), Mapping) else {}
    return {
        "type": EVENT_TYPE,
        "sequence": event.get("sequence"),
        "stage": _text(payload.get("stage") or event.get("stage")),
        "round": int(payload.get("round") or event.get("round") or 0),
        "decisionId": _text(payload.get("decisionId")),
        "title": _text(payload.get("title")),
        "answer": _text(payload.get("answer")),
        "customAnswer": _text(payload.get("customAnswer")),
        "speaker": _text(actor.get("id")) or "human-decision-center",
        "actorType": "user",
        "ok": True,
        "durationMs": 0,
        "providerRef": {},
        "createdAt": _text(event.get("createdAt")),
    }


def format_agent_history_event(event: Mapping[str, Any]) -> str | None:
    turn = project_transcript_event(event)
    if turn is None:
        return None
    title = turn["title"] or "Untitled decision"
    custom = f" Additional input: {turn['customAnswer']}." if turn["customAnswer"] else ""
    return (
        f"human decision resolved [{turn['decisionId']}] {title}: {turn['answer']}."
        f"{custom} Treat this as authoritative and do not request another decision for the same issue."
    )


__all__ = [
    "EVENT_TYPE",
    "build_event_payload",
    "format_agent_history_event",
    "project_transcript_event",
]
