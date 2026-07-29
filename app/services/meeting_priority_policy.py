"""Priority-based defaults for AI-originated meetings."""

from __future__ import annotations

from typing import Any, Mapping


def urgency_score(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 3
    return max(1, min(5, value))


def priority_bucket_from_urgency(raw: Any) -> int:
    return max(0, 5 - urgency_score(raw))


def meeting_priority_bucket(meeting: Mapping[str, Any] | None) -> int:
    meeting = meeting or {}
    source = meeting.get("source") if isinstance(meeting.get("source"), Mapping) else {}
    return priority_bucket_from_urgency(source.get("urgency") or meeting.get("urgency"))


def normalize_resolution_policy(raw: Any) -> str:
    policy = str(raw or "user_decision").strip().lower().replace("-", "_")
    aliases = {
        "user": "user_decision",
        "manual": "user_decision",
        "user_arbitration": "user_decision",
        "strict_user": "user_decision",
        "moderator": "moderator_decision",
        "ai": "moderator_decision",
        "auto": "moderator_decision",
        "auto_close": "moderator_decision",
        "moderator_arbitration": "moderator_decision",
    }
    policy = aliases.get(policy, policy)
    return policy if policy in {"user_decision", "moderator_decision"} else "user_decision"


def default_ai_request_resolution_policy(urgency: Any) -> str:
    return "user_decision" if priority_bucket_from_urgency(urgency) == 0 else "moderator_decision"


def coerce_moderator_outcome_for_priority(meeting: Mapping[str, Any] | None, result: Mapping[str, Any]) -> dict[str, Any]:
    final = dict(result or {})
    if normalize_resolution_policy((meeting or {}).get("resolutionPolicy")) != "moderator_decision":
        return final
    if meeting_priority_bucket(meeting) == 0:
        return final
    if str(final.get("outcome") or "") != "needs_user_decision":
        return final
    final["outcome"] = "no_consensus"
    final["moderatorPolicyCoercedOutcomeFrom"] = "needs_user_decision"
    if not str(final.get("decision") or "").strip():
        final["decision"] = str(final.get("summary") or "").strip() or "Moderator decision: no consensus; keep the task blocked."
    if not str(final.get("rationale") or "").strip():
        final["rationale"] = "Non-P0 AI meeting uses moderator_decision policy, so unresolved disagreement is recorded as no_consensus instead of asking the user to arbitrate."
    return final
