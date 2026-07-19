"""Transport-independent Meeting lifecycle and occupancy invariants."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Mapping, MutableMapping


TERMINAL = frozenset({"completed", "cancelled", "failed"})
PHASES = frozenset({
    "draft", "conflict", "preparing", "active_opening", "active_discussion", "paused",
    "awaiting_user_decision", "summarizing", "completed", "cancelled", "failed",
})
TRANSITIONS = {
    "draft": frozenset({"preparing", "cancelled"}),
    "conflict": frozenset({"preparing", "cancelled", "failed"}),
    "preparing": frozenset({"active_opening", "paused", "cancelled", "failed"}),
    "active_opening": frozenset({"active_discussion", "paused", "summarizing", "cancelled", "failed"}),
    "active_discussion": frozenset({"awaiting_user_decision", "summarizing", "paused", "cancelled", "failed"}),
    "paused": frozenset({"preparing", "active_opening", "active_discussion", "awaiting_user_decision", "cancelled", "failed"}),
    "awaiting_user_decision": frozenset({"active_discussion", "summarizing", "cancelled", "failed"}),
    "summarizing": frozenset({"completed", "cancelled", "failed"}),
    "completed": frozenset(), "cancelled": frozenset(), "failed": frozenset(),
}
TRANSITION_ALIASES = {
    "start": "active_opening", "opening": "active_opening", "discussion": "active_discussion",
    "pause": "paused", "resume_preparing": "preparing", "resume_opening": "active_opening",
    "resume_discussion": "active_discussion", "continue": "active_discussion",
    "continue_decision": "active_discussion", "await_decision": "awaiting_user_decision",
    "summarize": "summarizing", "complete": "completed", "cancel": "cancelled", "fail": "failed",
}


class MeetingLifecycleError(RuntimeError):
    def __init__(self, message: str, *, code: str, status: int = 409, details: dict | None = None):
        super().__init__(message)
        self.code = code; self.status = status; self.details = details or {}


@dataclass(frozen=True)
class MeetingCompareToken:
    meeting_id: str
    phase: str
    version: int
    sequence: int
    call_id: str = ""
    participant: str = ""


@dataclass(frozen=True)
class TransitionHooks:
    append_event: Callable[..., dict[str, Any]]
    continue_decision: Callable[..., Any]
    mark_preparing: Callable[[MutableMapping[str, Any]], Any]
    resume_original_work: Callable[..., Any]
    ensure_action_items: Callable[..., Any]
    award_points: Callable[[MutableMapping[str, Any]], Any]


@dataclass(frozen=True)
class CreateHooks:
    rebuild_occupancy: Callable[[MutableMapping[str, Any]], Any]
    build_conflicts: Callable[..., list[dict[str, Any]]]
    append_event: Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class AgentTurnHooks:
    build_prompt: Callable[..., str]
    append_event: Callable[..., dict[str, Any]]
    normalize_reply: Callable[[str], dict[str, Any]]
    provider_ref: Callable[[str], dict[str, Any]]
    formal_turn_exists: Callable[..., bool]
    pending_turn_exists: Callable[..., bool]
    append_ignored: Callable[..., Any]
    update_summary: Callable[..., Any]


@dataclass(frozen=True)
class MutationHooks:
    append_event: Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class TimeoutHooks:
    append_event: Callable[..., dict[str, Any]]
    parse_timestamp: Callable[[Any], float]


@dataclass(frozen=True)
class TargetedQuestionHooks:
    append_event: Callable[..., dict[str, Any]]
    build_prompt: Callable[..., str]
    normalize_reply: Callable[[str], dict[str, Any]]
    provider_ref: Callable[[str], dict[str, Any]]
    append_ignored: Callable[..., Any]
    update_summary: Callable[..., Any]


@dataclass(frozen=True)
class TerminalHooks:
    append_event: Callable[..., dict[str, Any]]
    resume_original_work: Callable[..., Any]
    ensure_action_items: Callable[..., Any]
    award_points: Callable[[MutableMapping[str, Any]], Any]


@dataclass(frozen=True)
class ModeratorHooks:
    append_event: Callable[..., dict[str, Any]]
    build_prompt: Callable[..., str]
    pending_calls: Callable[..., list[dict[str, Any]]]
    normalize_reply: Callable[[str], dict[str, Any]]
    parse_result: Callable[[str], dict[str, Any]]
    fallback_result: Callable[..., dict[str, Any]]
    provider_ref: Callable[[str], dict[str, Any]]
    append_ignored: Callable[..., Any]
    terminal: TerminalHooks


@dataclass(frozen=True)
class ConflictHooks:
    append_event: Callable[..., dict[str, Any]]
    build_conflicts: Callable[..., list[dict[str, Any]]]
    busy_context: Callable[..., dict[str, Any]]
    advisory: Callable[[Mapping[str, Any]], dict[str, Any]]
    original_work_snapshot: Callable[..., dict[str, Any]]
    has_open_conflicts: Callable[[Mapping[str, Any]], bool]
    mark_preparing: Callable[..., Any]
    rebuild_occupancy: Callable[[MutableMapping[str, Any]], Any]
    participant_error: Callable[[str], Mapping[str, Any] | None]
    now: Callable[[], str]
    new_id: Callable[[], str]


@dataclass(frozen=True)
class ArbitrationHooks:
    append_event: Callable[..., dict[str, Any]]
    continue_decision: Callable[..., Any]
    fallback_result: Callable[..., dict[str, Any]]
    truncate: Callable[[str, int], str]
    terminal: TerminalHooks


@dataclass(frozen=True)
class TakeoverHooks:
    append_event: Callable[..., dict[str, Any]]
    fallback_result: Callable[..., dict[str, Any]]
    normalize_outcome: Callable[[Any], str]
    terminal: TerminalHooks


def moderator_takeover_command(
    data: MutableMapping[str, Any], meeting_id: str, body: Mapping[str, Any], hooks: TakeoverHooks,
) -> dict[str, Any]:
    action = str(body.get("action") or "").strip()
    actor = {"type": str(body.get("actorType") or "user"), "id": str(body.get("actorId") or "user")}
    if action not in {"user_takeover", "replace_moderator"}:
        return {"error": "Invalid moderator takeover action", "_status": 400}
    meeting = data.get("meetings", {}).get(meeting_id)
    if not isinstance(meeting, MutableMapping):
        return {"error": "Executable meeting not found", "_status": 404}
    if phase(meeting) in TERMINAL:
        return {"error": "Meeting already ended", "_status": 409}
    failure = meeting.get("moderatorFailure") if isinstance(meeting.get("moderatorFailure"), Mapping) else {}
    if phase(meeting) != "awaiting_user_decision" or failure.get("reason") != "moderator_failed":
        return {"error": "Meeting is not waiting for moderator takeover", "stage": phase(meeting), "_status": 409}
    failure = copy.deepcopy(dict(failure))
    if action == "replace_moderator":
        replacement = str(body.get("moderator") or body.get("newModerator") or "").strip()
        if replacement not in list(meeting.get("participants") or []):
            return {"error": "Replacement moderator must be a participant", "_status": 400}
        previous_moderator = str(meeting.get("moderator") or "")
        meeting["moderator"] = replacement
        meeting["moderatorFailure"] = {**failure, "resolvedBy": "replace_moderator", "replacement": replacement}
        previous = phase(meeting); meeting["previousStage"] = previous; meeting["stage"] = "summarizing"; meeting["currentSpeaker"] = replacement
        for key in ("decisionForStage", "decisionForRound", "decisionNextStage", "decisionNextRound", "decisionDeadlineAt"):
            meeting.pop(key, None)
        event = hooks.append_event(data, meeting, "moderator_takeover", actor=actor, payload={
            "action": "replace_moderator", "previousModerator": previous_moderator,
            "moderator": replacement, "failure": failure,
        })
        hooks.append_event(data, meeting, "meeting_transitioned", actor=actor, payload={"from": previous, "to": "summarizing", "reason": "moderator_replaced"})
        return {"ok": True, "meeting": meeting, "event": event, "invokeModerator": True}
    summary = str(body.get("summary") or "").strip()
    if not summary:
        return {"error": "Summary is required for user takeover", "_status": 400}
    decision = str(body.get("decision") or body.get("resolution") or "").strip()
    manual_result = body.get("result") if isinstance(body.get("result"), Mapping) else {}
    manual_outcome = hooks.normalize_outcome(
        manual_result.get("outcome") or manual_result.get("status") or manual_result.get("result") or body.get("outcome")
    )
    action_items = body.get("actionItems") if isinstance(body.get("actionItems"), list) else []
    if not action_items and isinstance(manual_result.get("actionItems"), list):
        action_items = manual_result.get("actionItems") or []
    fallback = hooks.fallback_result(meeting, list(data.get("events", {}).get(meeting_id, [])))
    final_result = {
        **fallback, **{key: value for key, value in manual_result.items() if value not in ("", [], {})},
        "summary": summary, "outcome": manual_outcome or fallback.get("outcome") or "needs_user_decision",
        "decision": decision or manual_result.get("decision") or "Meeting closed by user after moderator failure.",
        "actionItems": action_items, "moderatorFailure": failure,
        "moderatorTakeover": {"action": "user_takeover", "actorId": actor["id"]},
    }
    event = hooks.append_event(data, meeting, "moderator_takeover", actor=actor, payload={
        "action": "user_takeover", "summary": summary, "decision": final_result["decision"], "failure": failure,
    })
    complete_meeting(
        data, meeting, final_result, actor=actor, reason="user_moderator_takeover",
        resume_reason="moderator_takeover", hooks=hooks.terminal, ensure_action_items=False,
    )
    return {"ok": True, "meeting": meeting, "event": event}


def arbitration_command(
    data: MutableMapping[str, Any], meeting_id: str, body: Mapping[str, Any], hooks: ArbitrationHooks,
) -> dict[str, Any]:
    action = str(body.get("action") or body.get("decisionAction") or "").strip() or "decide"
    if action not in {"decide", "end_no_consensus", "continue_discussion", "consensus_summary"}:
        return {"error": "Unsupported arbitration action", "_status": 400}
    decision = str(body.get("decision") or body.get("resolution") or "").strip()
    rationale = str(body.get("rationale") or body.get("reason") or "").strip()
    if action == "decide" and not decision:
        return {"error": "Arbitration decision is required", "_status": 400}
    meeting = data.get("meetings", {}).get(meeting_id)
    if not isinstance(meeting, MutableMapping):
        return {"error": "Executable meeting not found", "_status": 404}
    if phase(meeting) in TERMINAL:
        return {"error": "Cannot arbitrate a terminal meeting", "stage": phase(meeting), "_status": 409}
    if phase(meeting) != "awaiting_user_decision":
        return {"error": "Arbitration is only allowed during the user decision window", "stage": phase(meeting), "_status": 409}
    idempotency_key = str(body.get("idempotencyKey") or "").strip()
    idem_key = f"{meeting_id}:arbitration:{idempotency_key}" if idempotency_key else ""
    replay = _idempotent_event(data, meeting_id, idem_key)
    if replay is not None:
        return {"ok": True, "meeting": meeting, "event": replay, "idempotent": True}
    actor_id = str(body.get("actorId") or "user").strip() or "user"
    actor = {"type": "user", "id": actor_id}
    payload = {
        "action": action, "decision": decision, "rationale": rationale, "actorId": actor_id,
        "stage": meeting.get("decisionForStage") or phase(meeting),
        "round": int(meeting.get("decisionForRound") or meeting.get("round") or 0),
        "arbitration": meeting.get("arbitration") or {},
    }
    event = hooks.append_event(
        data, meeting, "arbitration_decision", actor=actor, payload=payload,
        idempotency_key=idempotency_key,
    )
    if action == "continue_discussion":
        meeting["maxRounds"] = max(int(meeting.get("maxRounds") or 1), int(meeting.get("round") or 0) + 1)
        meeting["decisionNextStage"] = "active_discussion"
        meeting["decisionNextRound"] = int(meeting.get("round") or 0) + 1
        hooks.continue_decision(data, meeting, actor=actor, reason="arbitration_continue")
    elif action == "consensus_summary":
        previous = phase(meeting); meeting["previousStage"] = previous; meeting["stage"] = "summarizing"
        meeting["currentSpeaker"] = meeting.get("moderator") or (meeting.get("participants") or [""])[0]
        for key in ("decisionForStage", "decisionForRound", "decisionNextStage", "decisionNextRound", "decisionWindowSec", "decisionDeadlineAt", "arbitration"):
            meeting.pop(key, None)
        hooks.append_event(data, meeting, "decision_window_closed", actor=actor, payload={"to": "summarizing", "round": int(meeting.get("round") or 0), "reason": "arbitration_consensus_summary"})
        hooks.append_event(data, meeting, "meeting_transitioned", actor=actor, payload={"from": previous, "to": "summarizing", "reason": "arbitration_consensus_summary"})
    else:
        fallback = hooks.fallback_result(meeting, list(data.get("events", {}).get(meeting_id, [])))
        arbitration = payload.get("arbitration") or {}
        final_decision = decision if action == "decide" else "No consensus. Meeting ended with unresolved disagreement."
        suffix = rationale or arbitration.get("moderatorSuggestion") or ""
        result = {
            **fallback,
            "summary": hooks.truncate((fallback.get("summary") or "") + ("\n" + suffix if suffix else ""), 2000),
            "decision": final_decision,
            "unresolvedQuestions": arbitration.get("disagreements") or fallback.get("unresolvedQuestions") or [],
            "disagreements": arbitration.get("disagreements") or fallback.get("disagreements") or [],
            "arbitration": {"action": action, "decision": decision, "rationale": rationale, "actorId": actor_id},
        }
        complete_meeting(
            data, meeting, result, actor=actor, reason=action, resume_reason="arbitration",
            hooks=hooks.terminal,
            clear_keys=("decisionForStage", "decisionForRound", "decisionNextStage", "decisionNextRound", "decisionWindowSec", "decisionDeadlineAt", "arbitration"),
            action_items_before_result_event=True,
        )
    if idem_key:
        data.setdefault("idempotency", {})[idem_key] = {"meetingId": meeting_id, "sequence": event["sequence"]}
    return {"ok": True, "meeting": meeting, "event": event, "invokeModerator": action == "consensus_summary"}


def conflict_action_command(
    data: MutableMapping[str, Any], meeting_id: str, body: Mapping[str, Any], hooks: ConflictHooks,
) -> dict[str, Any]:
    action = str(body.get("action") or "").strip()
    if action not in {"wait", "reserve", "replace", "force_join", "cancel_conflict", "refresh"}:
        return {"error": "Invalid conflict action", "_status": 400}
    agent_id = str(body.get("agentId") or "").strip()
    actor = {"type": str(body.get("actorType") or "user"), "id": str(body.get("actorId") or "user")}
    idempotency_key = str(body.get("idempotencyKey") or "").strip()
    idem_key = f"{meeting_id}:conflict:{action}:{idempotency_key}" if idempotency_key else ""
    meeting = data.get("meetings", {}).get(meeting_id)
    if not isinstance(meeting, MutableMapping):
        return {"error": "Executable meeting not found", "_status": 404}
    replay = _idempotent_event(data, meeting_id, idem_key)
    if replay is not None:
        return {"ok": True, "meeting": meeting, "event": replay, "idempotent": True}
    if phase(meeting) in TERMINAL:
        return {"error": "Cannot resolve conflicts on a terminal meeting", "stage": phase(meeting), "_status": 409}
    if action == "refresh":
        refreshed = hooks.build_conflicts(data, meeting.get("participants") or [], exclude_meeting_id=meeting_id)
        meeting["conflicts"] = refreshed; meeting["stage"] = "conflict" if refreshed else "preparing"
        if not refreshed:
            hooks.mark_preparing(meeting)
            claim_occupancy(data, meeting_id, list(meeting.get("participants") or []))
            for participant in meeting.get("participants") or []:
                meeting.setdefault("participantState", {}).setdefault(participant, {})["status"] = "reserved"
        event = hooks.append_event(
            data, meeting, "meeting_conflict_refreshed", actor=actor,
            payload={"conflicts": refreshed}, idempotency_key=idempotency_key,
        )
        if idem_key:
            data.setdefault("idempotency", {})[idem_key] = {"meetingId": meeting_id, "sequence": event["sequence"]}
        return {"ok": True, "meeting": meeting, "event": event, "needsLiveAdvisory": bool(refreshed)}
    conflicts = meeting.get("conflicts") if isinstance(meeting.get("conflicts"), list) else []
    conflict = next(
        (item for item in conflicts if item.get("agentId") == agent_id and item.get("status") in {"open", "waiting", "reserved"}),
        None,
    )
    if not conflict:
        return {"error": "Open conflict not found for agent", "agentId": agent_id, "_status": 404}
    now = hooks.now()
    payload = {"action": action, "agentId": agent_id, "previous": copy.deepcopy(dict(conflict))}
    if action == "wait":
        conflict["status"] = "waiting"
        conflict["resolution"] = {"action": "wait", "decidedAt": now, "decidedBy": actor["id"]}
    elif action == "reserve":
        conflict["status"] = "reserved"
        reservation = {
            "agentId": agent_id, "status": "scheduled", "mode": str(body.get("mode") or "try_later"),
            "targetAt": str(body.get("targetAt") or body.get("remindAt") or "").strip(),
            "note": str(body.get("note") or "Try again later; this is not a hard reservation.").strip(),
            "createdAt": now, "createdBy": actor["id"],
        }
        meeting.setdefault("reservation", {})[agent_id] = reservation
        conflict["reservation"] = reservation
        conflict["resolution"] = {"action": "reserve", "decidedAt": now, "decidedBy": actor["id"]}
    elif action == "replace":
        replacement = str(body.get("replacement") or body.get("replacementAgentId") or "").strip()
        rejected = hooks.participant_error(replacement)
        if isinstance(rejected, Mapping):
            return dict(rejected)
        replacement_context = hooks.busy_context(data, replacement, exclude_meeting_id=meeting_id)
        if replacement_context.get("busy"):
            return {"error": "Replacement agent is busy", "conflict": replacement_context, "_status": 409}
        try:
            replace_participant(meeting, agent_id, replacement, now=now)
        except MeetingLifecycleError as error:
            return {"error": str(error), "_status": error.status}
        conflict["status"] = "resolved"
        conflict["resolution"] = {"action": "replace", "replacement": replacement, "decidedAt": now, "decidedBy": actor["id"]}
        payload["replacement"] = replacement
    elif action == "force_join":
        if not body.get("confirmForce"):
            return {"error": "Force join requires second confirmation", "advisory": conflict.get("advisory") or {}, "_status": 409}
        if not conflict.get("advisory"):
            conflict["advisory"] = hooks.advisory(conflict)
        snapshot = hooks.original_work_snapshot(conflict, "force_join")
        meeting.setdefault("originalWork", {})[agent_id] = snapshot
        participant_state = meeting.setdefault("participantState", {}).setdefault(agent_id, {})
        participant_state.update({"status": "reserved", "pauseState": snapshot["pauseState"], "forcedJoin": True})
        conflict["status"] = "resolved"
        conflict["resolution"] = {"action": "force_join", "decidedAt": now, "decidedBy": actor["id"], "confirmForce": True}
        payload["snapshot"] = snapshot
    else:
        conflict["status"] = "cancelled"
        conflict["resolution"] = {"action": "cancel_conflict", "decidedAt": now, "decidedBy": actor["id"]}
    conflict["updatedAt"] = now
    if not hooks.has_open_conflicts(meeting):
        meeting["previousStage"] = phase(meeting); meeting["stage"] = "preparing"
        hooks.mark_preparing(meeting, now)
        for participant in meeting.get("participants") or []:
            meeting.setdefault("participantState", {}).setdefault(participant, {})["status"] = "reserved"
        try:
            hooks.rebuild_occupancy(data)
        except MeetingLifecycleError as error:
            return {"error": str(error), "code": error.code, "details": error.details, "_status": error.status}
        occupied = {
            participant: data.get("occupancy", {}).get(participant)
            for participant in meeting.get("participants") or []
            if data.get("occupancy", {}).get(participant) and data.get("occupancy", {}).get(participant) != meeting_id
        }
        if occupied:
            meeting["stage"] = "conflict"
            for participant, owner in occupied.items():
                new_conflict = {
                    "id": hooks.new_id(), "agentId": participant, "status": "open", "reason": "meeting_occupied",
                    "busyKind": "meeting", "riskLevel": "high", "summary": f"Already in meeting: {owner}",
                    "estimatedAvailability": "unknown", "pauseCapability": "unavailable",
                    "source": {"meetingId": owner}, "createdAt": now, "updatedAt": now,
                }
                new_conflict["advisory"] = hooks.advisory(new_conflict)
                meeting.setdefault("conflicts", []).append(new_conflict)
        else:
            claim_occupancy(data, meeting_id, list(meeting.get("participants") or []))
    event = hooks.append_event(
        data, meeting, "meeting_conflict_resolved", actor=actor, payload=payload,
        idempotency_key=idempotency_key,
    )
    if idem_key:
        data.setdefault("idempotency", {})[idem_key] = {"meetingId": meeting_id, "sequence": event["sequence"]}
    return {"ok": True, "meeting": meeting, "event": event}


def prepare_moderator_summary(
    data: MutableMapping[str, Any], meeting_id: str, actor: Mapping[str, Any], hooks: ModeratorHooks,
) -> dict[str, Any]:
    meeting = data.get("meetings", {}).get(meeting_id)
    if not isinstance(meeting, MutableMapping):
        return {"error": "Executable meeting not found", "_status": 404}
    if phase(meeting) in TERMINAL:
        return {"ok": True, "meeting": meeting, "alreadyTerminal": True}
    previous = phase(meeting)
    if previous != "summarizing":
        if not transition_allowed(previous, "summarizing"):
            return {"error": f"Cannot summarize meeting from {previous}", "stage": previous, "_status": 409}
        meeting["previousStage"] = previous
        meeting["stage"] = "summarizing"
        meeting["currentSpeaker"] = meeting.get("moderator") or (meeting.get("participants") or [""])[0]
        hooks.append_event(
            data, meeting, "meeting_transitioned", actor=dict(actor),
            payload={"from": previous, "to": "summarizing", "reason": "user_end"},
        )
    events = list(data.get("events", {}).get(meeting_id, []))
    moderator = str(meeting.get("moderator") or (meeting.get("participants") or [""])[0])
    pending_calls = hooks.pending_calls(events, "summarizing", meeting.get("round"), "meeting_result")
    if pending_calls:
        return {"ok": True, "meeting": meeting, "providerCallPending": True, "pendingCalls": pending_calls}
    prompt = hooks.build_prompt(meeting, events)
    pending = hooks.append_event(
        data, meeting, "provider_call_started", actor={"type": "agent", "id": moderator},
        payload={
            "speaker": moderator, "stage": "summarizing", "round": meeting.get("round"),
            "contextMode": meeting.get("contextMode"), "promptChars": len(prompt), "purpose": "meeting_result",
        },
    )
    token = compare_token(
        meeting, data.get("events", {}).get(meeting_id, []),
        call_id=str(pending.get("sequence") or ""), participant=moderator,
    )
    return {"ok": True, "meeting": meeting, "moderator": moderator, "prompt": prompt, "pending": pending, "token": token}


def commit_moderator_summary(
    data: MutableMapping[str, Any], meeting_id: str, prepared: Mapping[str, Any],
    provider_result: Mapping[str, Any], actor: Mapping[str, Any], *, failure_deadline: str,
    decision_window_seconds: int, hooks: ModeratorHooks,
) -> dict[str, Any]:
    meeting = data.get("meetings", {}).get(meeting_id)
    if not isinstance(meeting, MutableMapping):
        return {"error": "Executable meeting not found", "_status": 404}
    moderator = str(prepared["moderator"]); pending = prepared["pending"]
    normalized = hooks.normalize_reply(str(provider_result.get("reply") or ""))
    events = list(data.get("events", {}).get(meeting_id, []))
    if not token_is_current(meeting, events, prepared["token"]):
        pending_payload = pending.get("payload") if isinstance(pending.get("payload"), Mapping) else {}
        ignored = hooks.append_ignored(
            data, meeting, moderator, provider_result, normalized, pending, "meeting_state_changed",
            "summarizing", pending_payload.get("round", meeting.get("round")), kind="meeting_result",
        )
        return {"ok": True, "meeting": meeting, "ignored": ignored, "alreadyTerminal": phase(meeting) in TERMINAL}
    moderator_payload = {
        "speaker": moderator, "text": normalized.get("text") or "", "rawText": normalized.get("rawText") or "",
        "structured": normalized.get("structured") or {}, "parseError": normalized.get("parseError") or "",
        "ok": bool(provider_result.get("ok")), "stage": "summarizing", "round": meeting.get("round"),
        "providerRef": provider_result.get("providerRef") or hooks.provider_ref(moderator),
        "conversationId": provider_result.get("conversationId") or "",
        "durationMs": provider_result.get("durationMs") or 0, "inReplyToSequence": pending.get("sequence"),
        "purpose": "meeting_result",
    }
    if normalized.get("providerRaw"):
        moderator_payload["providerRaw"] = normalized["providerRaw"]
    hooks.append_event(data, meeting, "participant_turn", actor={"type": "agent", "id": moderator}, payload=moderator_payload)
    if not provider_result.get("ok"):
        previous = phase(meeting)
        meeting["previousStage"] = previous; meeting["stage"] = "awaiting_user_decision"; meeting["currentSpeaker"] = ""
        failure = {
            "reason": "moderator_failed", "moderator": moderator,
            "error": str(normalized.get("text") or normalized.get("rawText") or provider_result.get("reply") or "Moderator failed")[:1000],
            "providerRef": moderator_payload.get("providerRef") or {}, "failedAtSequence": meeting.get("lastEventSequence"),
        }
        meeting["moderatorFailure"] = failure
        meeting["decisionForStage"] = previous; meeting["decisionForRound"] = int(meeting.get("round") or 0)
        meeting["decisionNextStage"] = "summarizing"; meeting["decisionNextRound"] = int(meeting.get("round") or 0)
        meeting["decisionWindowSec"] = decision_window_seconds; meeting["decisionDeadlineAt"] = failure_deadline
        hooks.append_event(data, meeting, "moderator_failure", actor={"type": "agent", "id": moderator}, payload=failure)
        hooks.append_event(
            data, meeting, "meeting_transitioned", actor={"type": "agent", "id": moderator},
            payload={"from": previous, "to": "awaiting_user_decision", "reason": "moderator_failed"},
        )
        return {"ok": False, "meeting": meeting, "moderatorFailure": failure, "notifyFailure": True}
    parsed = hooks.parse_result(str(normalized.get("rawText") or normalized.get("text") or ""))
    fallback = hooks.fallback_result(meeting, list(data.get("events", {}).get(meeting_id, [])))
    final_result = {
        **fallback, **{key: value for key, value in parsed.items() if value not in ("", [], {})},
        "moderator": moderator, "moderatorProviderRef": moderator_payload.get("providerRef") or {},
    }
    meeting.pop("moderatorFailure", None)
    complete_meeting(
        data, meeting, final_result, actor=actor, reason="moderator_summary_complete",
        hooks=hooks.terminal, ensure_action_items=False,
        result_actor={"type": "agent", "id": moderator},
    )
    return {"ok": True, "meeting": meeting}


def complete_meeting(
    data: MutableMapping[str, Any], meeting: MutableMapping[str, Any], result: Mapping[str, Any],
    *, actor: Mapping[str, Any], reason: str, hooks: TerminalHooks,
    resume_reason: str | None = None, result_event: bool = True,
    clear_keys: tuple[str, ...] = (), ensure_action_items: bool = True,
    action_items_before_result_event: bool = False, result_actor: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    meeting_id = str(meeting.get("id") or "")
    previous = phase(meeting)
    meeting["result"] = copy.deepcopy(dict(result))
    meeting["currentSpeaker"] = ""
    for key in clear_keys:
        meeting.pop(key, None)
    if ensure_action_items and action_items_before_result_event:
        hooks.ensure_action_items(data, meeting)
    if result_event:
        hooks.append_event(data, meeting, "meeting_result", actor=dict(result_actor or actor), payload=dict(result))
    meeting["previousStage"] = previous
    meeting["stage"] = "completed"
    if ensure_action_items and not action_items_before_result_event:
        hooks.ensure_action_items(data, meeting)
    released = release_occupancy(data, meeting_id, list(meeting.get("participants") or []))
    hooks.resume_original_work(data, meeting, resume_reason or reason)
    hooks.award_points(meeting)
    event = hooks.append_event(
        data, meeting, "meeting_transitioned", actor=dict(actor),
        payload={"from": previous, "to": "completed", "reason": reason},
    )
    return {"meeting": meeting, "event": event, "releasedParticipants": released}


def prepare_targeted_question(
    data: MutableMapping[str, Any], meeting_id: str, body: Mapping[str, Any], hooks: TargetedQuestionHooks,
) -> dict[str, Any]:
    question = str(body.get("question") or body.get("text") or body.get("message") or "").strip()
    target = str(body.get("target") or body.get("targetParticipant") or body.get("speaker") or "").strip()
    if not question:
        return {"error": "Targeted question requires text", "_status": 400}
    if not target:
        return {"error": "Target participant is required", "_status": 400}
    meeting = data.get("meetings", {}).get(meeting_id)
    if not isinstance(meeting, MutableMapping):
        return {"error": "Executable meeting not found", "_status": 404}
    if phase(meeting) in TERMINAL:
        return {"error": "Cannot target a terminal meeting", "stage": phase(meeting), "_status": 409}
    if phase(meeting) != "awaiting_user_decision":
        return {"error": "Targeted questions are only allowed during the user decision window", "stage": phase(meeting), "_status": 409}
    if target not in list(meeting.get("participants") or []):
        return {"error": "Target participant is not in this meeting", "target": target, "_status": 400}
    idempotency_key = str(body.get("idempotencyKey") or "").strip()
    idem_key = f"{meeting_id}:targeted:{idempotency_key}" if idempotency_key else ""
    replay = _idempotent_event(data, meeting_id, idem_key)
    if replay is not None:
        return {"ok": True, "meeting": meeting, "event": replay, "idempotent": True}
    actor_id = str(body.get("actorId") or "user").strip() or "user"
    target_stage = str(meeting.get("decisionForStage") or meeting.get("previousStage") or phase(meeting))
    target_round = int(meeting.get("decisionForRound") or meeting.get("round") or 0)
    question_event = hooks.append_event(
        data, meeting, "targeted_question", actor={"type": "user", "id": actor_id},
        payload={"target": target, "question": question, "actorId": actor_id, "stage": target_stage, "round": target_round},
        idempotency_key=idempotency_key,
    )
    prompt = hooks.build_prompt(meeting, target, question, data.get("events", {}).get(meeting_id, []))
    pending = hooks.append_event(
        data, meeting, "provider_call_started", actor={"type": "agent", "id": target},
        payload={
            "speaker": target, "stage": target_stage, "round": target_round,
            "contextMode": meeting.get("contextMode"), "promptChars": len(prompt),
            "purpose": "targeted_response", "inReplyToSequence": question_event.get("sequence"),
        },
    )
    if idem_key:
        data.setdefault("idempotency", {})[idem_key] = {"meetingId": meeting_id, "sequence": question_event["sequence"]}
    token = compare_token(
        meeting, data.get("events", {}).get(meeting_id, []),
        call_id=str(pending.get("sequence") or ""), participant=target,
    )
    return {
        "ok": True, "meeting": meeting, "target": target, "question": question,
        "targetStage": target_stage, "targetRound": target_round,
        "questionEvent": question_event, "pending": pending, "prompt": prompt, "token": token,
    }


def commit_targeted_question(
    data: MutableMapping[str, Any], meeting_id: str, prepared: Mapping[str, Any],
    provider_result: Mapping[str, Any], hooks: TargetedQuestionHooks,
) -> dict[str, Any]:
    meeting = data.get("meetings", {}).get(meeting_id)
    if not isinstance(meeting, MutableMapping):
        return {"error": "Executable meeting not found", "_status": 404}
    target = str(prepared["target"]); question = str(prepared["question"])
    stage = str(prepared["targetStage"]); round_index = int(prepared["targetRound"])
    pending = prepared["pending"]; question_event = prepared["questionEvent"]
    normalized = hooks.normalize_reply(str(provider_result.get("reply") or ""))
    events = list(data.get("events", {}).get(meeting_id, []))
    if not token_is_current(meeting, events, prepared["token"]):
        ignored = hooks.append_ignored(
            data, meeting, target, provider_result, normalized, pending,
            "meeting_state_changed", stage, round_index, kind="targeted_response",
        )
        return {"ok": True, "meeting": meeting, "questionEvent": question_event, "ignored": ignored, "pending": pending}
    payload = {
        "kind": "targeted_response", "speaker": target, "targetQuestion": question,
        "text": normalized.get("text") or "", "rawText": normalized.get("rawText") or "",
        "structured": normalized.get("structured") or {}, "parseError": normalized.get("parseError") or "",
        "ok": bool(provider_result.get("ok")), "stage": stage, "round": round_index,
        "providerRef": provider_result.get("providerRef") or hooks.provider_ref(target),
        "conversationId": provider_result.get("conversationId") or "",
        "durationMs": provider_result.get("durationMs") or 0,
        "inReplyToSequence": pending.get("sequence"), "questionSequence": question_event.get("sequence"),
    }
    if normalized.get("providerRaw"):
        payload["providerRaw"] = normalized["providerRaw"]
    turn = hooks.append_event(data, meeting, "participant_turn", actor={"type": "agent", "id": target}, payload=payload)
    meeting.setdefault("participantLastSeen", {})[target] = turn["sequence"]
    hooks.update_summary(meeting, target, payload["text"])
    return {"ok": True, "meeting": meeting, "questionEvent": question_event, "event": turn, "pending": pending}


def release_timed_out_preparing(
    data: MutableMapping[str, Any], *, now_timestamp: float, now_iso: str,
    timeout_seconds: int, hooks: TimeoutHooks,
) -> list[str]:
    released: list[str] = []
    for meeting in list(data.get("meetings", {}).values()):
        if not isinstance(meeting, MutableMapping) or phase(meeting) != "preparing":
            continue
        if meeting.get("cancelReason") == "preparing_timeout":
            continue
        started_at = meeting.get("preparingStartedAt") or meeting.get("createdAt") or meeting.get("updatedAt")
        started_timestamp = hooks.parse_timestamp(started_at)
        if not started_timestamp or now_timestamp - started_timestamp < timeout_seconds:
            continue
        meeting_id = str(meeting.get("id") or "")
        meeting["previousStage"] = "preparing"
        meeting["stage"] = "cancelled"
        meeting["currentSpeaker"] = ""
        meeting["cancelReason"] = "preparing_timeout"
        meeting["timedOutAt"] = now_iso
        meeting["preparingTimeoutSec"] = timeout_seconds
        meeting["preparingTimedOutFrom"] = started_at
        released_agents = release_occupancy(data, meeting_id, list(meeting.get("participants") or []))
        hooks.append_event(
            data, meeting, "meeting_preparing_timed_out",
            actor={"type": "system", "id": "system"},
            payload={
                "from": "preparing", "to": "cancelled", "reason": "preparing_timeout",
                "timeoutSec": timeout_seconds, "startedAt": started_at, "timedOutAt": now_iso,
                "releasedParticipants": released_agents,
            },
            idempotency_key=f"{meeting_id}:preparing-timeout",
        )
        released.append(meeting_id)
    return released


def _idempotent_event(data: Mapping[str, Any], meeting_id: str, key: str) -> dict[str, Any] | None:
    record = data.get("idempotency", {}).get(key) if key else None
    if not isinstance(record, Mapping):
        return None
    sequence = record.get("sequence")
    return next(
        (event for event in data.get("events", {}).get(meeting_id, []) if event.get("sequence") == sequence),
        None,
    )


def _validate_expected_version(meeting: Mapping[str, Any], expected: Any) -> dict[str, Any] | None:
    if expected is None:
        return None
    try:
        expected_version = int(expected)
    except (TypeError, ValueError):
        return {"error": "Invalid expectedVersion", "_status": 400}
    if expected_version != int(meeting.get("version") or 0):
        return {"error": "Meeting version conflict", "currentVersion": meeting.get("version", 0), "_status": 409}
    return None


def intervention_command(
    data: MutableMapping[str, Any], meeting_id: str, body: Mapping[str, Any], hooks: MutationHooks,
) -> dict[str, Any]:
    text = str(body.get("text") or body.get("message") or "").strip()
    context = str(body.get("context") or body.get("additionalContext") or "").strip()
    if not text and not context:
        return {"error": "User intervention requires text or context", "_status": 400}
    meeting = data.get("meetings", {}).get(meeting_id)
    if not isinstance(meeting, MutableMapping):
        return {"error": "Executable meeting not found", "_status": 404}
    idempotency_key = str(body.get("idempotencyKey") or "").strip()
    idem_key = f"{meeting_id}:intervention:{idempotency_key}" if idempotency_key else ""
    replay = _idempotent_event(data, meeting_id, idem_key)
    if replay is not None:
        return {"ok": True, "meeting": meeting, "event": replay, "idempotent": True}
    if phase(meeting) in TERMINAL:
        return {"error": "Cannot add context to a terminal meeting", "stage": phase(meeting), "_status": 409}
    conflict = _validate_expected_version(meeting, body.get("expectedVersion"))
    if conflict:
        return conflict
    actor_id = str(body.get("actorId") or "user").strip() or "user"
    kind = "statement_context" if text and context else "context" if context else "statement"
    event = hooks.append_event(data, meeting, "user_intervention", actor={"type": "user", "id": actor_id}, payload={
        "kind": kind, "text": text, "context": context, "actorId": actor_id,
        "stage": phase(meeting), "round": meeting.get("round", 0),
        "appliesFromSequence": meeting.get("lastEventSequence", 0),
    }, idempotency_key=idempotency_key)
    if idem_key:
        data.setdefault("idempotency", {})[idem_key] = {"meetingId": meeting_id, "sequence": event["sequence"]}
    return {"ok": True, "meeting": meeting, "event": event}


def agenda_change_command(
    data: MutableMapping[str, Any], meeting_id: str, body: Mapping[str, Any], hooks: MutationHooks,
) -> dict[str, Any]:
    agenda = str(body.get("agenda") or body.get("topic") or body.get("newAgenda") or "").strip()
    if not agenda:
        return {"error": "Agenda change requires agenda", "_status": 400}
    meeting = data.get("meetings", {}).get(meeting_id)
    if not isinstance(meeting, MutableMapping):
        return {"error": "Executable meeting not found", "_status": 404}
    idempotency_key = str(body.get("idempotencyKey") or "").strip()
    idem_key = f"{meeting_id}:agenda:{idempotency_key}" if idempotency_key else ""
    replay = _idempotent_event(data, meeting_id, idem_key)
    if replay is not None:
        return {"ok": True, "meeting": meeting, "event": replay, "idempotent": True}
    if phase(meeting) in TERMINAL:
        return {"error": "Cannot change agenda for a terminal meeting", "stage": phase(meeting), "_status": 409}
    conflict = _validate_expected_version(meeting, body.get("expectedVersion"))
    if conflict:
        return conflict
    actor_id = str(body.get("actorId") or "user").strip() or "user"
    previous = meeting.get("agenda") or meeting.get("topic") or ""
    meeting["agenda"] = agenda
    event = hooks.append_event(data, meeting, "agenda_change", actor={"type": "user", "id": actor_id}, payload={
        "agenda": agenda, "previousAgenda": previous, "reason": str(body.get("reason") or "").strip(),
        "actorId": actor_id, "stage": phase(meeting), "round": meeting.get("round", 0),
        "appliesFromSequence": meeting.get("lastEventSequence", 0),
    }, idempotency_key=idempotency_key)
    if idem_key:
        data.setdefault("idempotency", {})[idem_key] = {"meetingId": meeting_id, "sequence": event["sequence"]}
    return {"ok": True, "meeting": meeting, "event": event}


def phase(meeting: Mapping[str, Any]) -> str:
    return str(meeting.get("stage") or meeting.get("phase") or "draft")


def validate_participant_eligibility(
    participants: list[str], moderator: str, *,
    participant_error: Callable[[str], Mapping[str, Any] | None],
) -> None:
    rejected: list[tuple[str, Mapping[str, Any]]] = []
    for participant in participants:
        error = participant_error(participant)
        if isinstance(error, Mapping):
            rejected.append((participant, error))
    if moderator and moderator not in participants:
        error = participant_error(moderator)
        if isinstance(error, Mapping):
            rejected.append((moderator, error))
    if rejected:
        first = rejected[0][1]
        raise MeetingLifecycleError(
            str(first.get("error") or "System Agent cannot participate in this meeting"),
            code=str(first.get("code") or "system_agent_not_meeting_eligible"),
            status=int(first.get("_status") or 400),
            details={
                "participants": [item[0] for item in rejected],
                "systemRole": first.get("systemRole"),
            },
        )
    if moderator not in participants:
        raise MeetingLifecycleError("Moderator must be one of the participants", code="meeting_moderator_invalid", status=400)


def replace_participant(
    meeting: MutableMapping[str, Any], conflicted_agent: str, replacement: str, *, now: str,
) -> None:
    if not replacement:
        raise MeetingLifecycleError("Replacement agent is required", code="meeting_replacement_required", status=400)
    if replacement in list(meeting.get("participants") or []):
        raise MeetingLifecycleError("Replacement agent is already a participant", code="meeting_replacement_duplicate", status=400)
    meeting["participants"] = [replacement if item == conflicted_agent else item for item in meeting.get("participants") or []]
    if meeting.get("moderator") == conflicted_agent:
        meeting["moderator"] = replacement
    meeting["speakerQueue"] = [replacement if item == conflicted_agent else item for item in meeting.get("speakerQueue") or []]
    meeting.setdefault("participantState", {}).pop(conflicted_agent, None)
    meeting.setdefault("participantState", {})[replacement] = {
        "status": "reserved", "joinedAt": now, "replacedAgentId": conflicted_agent,
    }


def transition_allowed(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, frozenset())


def validate_transition(meeting: Mapping[str, Any], target: str, *, expected_version: Any = None) -> None:
    current = phase(meeting)
    if target not in PHASES:
        raise MeetingLifecycleError("Invalid Meeting stage", code="meeting_stage_invalid", status=400)
    if expected_version is not None:
        try: expected = int(expected_version)
        except (TypeError, ValueError) as exc:
            raise MeetingLifecycleError("Invalid expected version", code="meeting_version_invalid", status=400) from exc
        if expected != int(meeting.get("version") or 0):
            raise MeetingLifecycleError("Meeting version is stale", code="meeting_version_stale")
    if not transition_allowed(current, target):
        raise MeetingLifecycleError(
            f"Cannot transition Meeting from {current} to {target}", code="meeting_transition_invalid",
            details={"current": current, "target": target},
        )


def compare_token(meeting: Mapping[str, Any], events: list[Mapping[str, Any]], *, call_id="", participant="") -> MeetingCompareToken:
    return MeetingCompareToken(
        meeting_id=str(meeting.get("id") or ""), phase=phase(meeting),
        version=int(meeting.get("version") or 0),
        sequence=max((int(event.get("sequence") or 0) for event in events if isinstance(event, Mapping)), default=0),
        call_id=str(call_id or ""), participant=str(participant or ""),
    )


def token_is_current(meeting: Mapping[str, Any], events: list[Mapping[str, Any]], token: MeetingCompareToken) -> bool:
    current = compare_token(meeting, events, call_id=token.call_id, participant=token.participant)
    return (
        current.meeting_id == token.meeting_id and current.phase == token.phase
        and current.version == token.version and current.sequence == token.sequence
    )


def claim_occupancy(data: MutableMapping[str, Any], meeting_id: str, participants: list[str]) -> None:
    meetings = data.setdefault("meetings", {})
    occupancy = data.setdefault("occupancy", {})
    for participant in participants:
        owner = str(occupancy.get(participant) or "")
        owner_meeting = meetings.get(owner) if owner else None
        if owner and owner != meeting_id and isinstance(owner_meeting, Mapping) and phase(owner_meeting) not in TERMINAL:
            raise MeetingLifecycleError(
                "Agent is already occupied by another Meeting", code="meeting_participant_occupied",
                details={"agentId": participant, "meetingId": owner},
            )
    occupancy.update({participant: meeting_id for participant in participants})


def release_occupancy(data: MutableMapping[str, Any], meeting_id: str, participants: list[str]) -> list[str]:
    occupancy = data.setdefault("occupancy", {})
    released = []
    for participant in participants:
        if occupancy.get(participant) == meeting_id:
            occupancy.pop(participant, None); released.append(participant)
    return released


def rebuild_occupancy(data: MutableMapping[str, Any], *, preserve_unknown: bool = True) -> dict[str, str]:
    meetings = data.setdefault("meetings", {})
    previous = data.get("occupancy") if isinstance(data.get("occupancy"), dict) else {}
    rebuilt: dict[str, str] = {}
    forced: dict[str, str] = {}
    for meeting_id, meeting in sorted(meetings.items()):
        if not isinstance(meeting, Mapping) or phase(meeting) in TERMINAL:
            continue
        for participant in meeting.get("participants") or []:
            participant_state = meeting.get("participantState") if isinstance(meeting.get("participantState"), dict) else {}
            state = participant_state.get(participant) if isinstance(participant_state.get(participant), dict) else {}
            if state.get("forcedJoin"):
                existing_forced = forced.get(str(participant))
                if existing_forced and existing_forced != str(meeting_id):
                    raise MeetingLifecycleError(
                        "Agent has conflicting forced Meeting owners", code="meeting_occupancy_conflict",
                        details={"agentId": participant, "meetings": [existing_forced, meeting_id]},
                    )
                forced[str(participant)] = str(meeting_id)
                continue
            owner = rebuilt.get(participant)
            if owner and owner != meeting_id:
                raise MeetingLifecycleError(
                    "Agent has conflicting active Meeting owners", code="meeting_occupancy_conflict",
                    details={"agentId": participant, "meetings": [owner, meeting_id]},
                )
            rebuilt[str(participant)] = str(meeting_id)
    rebuilt.update(forced)
    if preserve_unknown:
        for participant, owner in previous.items():
            if owner not in meetings:
                rebuilt.setdefault(str(participant), str(owner))
    data["occupancy"] = rebuilt
    return copy.deepcopy(rebuilt)


def transition_command(
    data: MutableMapping[str, Any], meeting_id: str, body: Mapping[str, Any], hooks: TransitionHooks,
) -> dict[str, Any]:
    raw_target = str(body.get("stage") or body.get("to") or body.get("action") or "").strip()
    target = TRANSITION_ALIASES.get(raw_target, raw_target)
    if target not in PHASES:
        return {"error": "Invalid meeting stage", "_status": 400}
    expected = body.get("expectedVersion")
    try:
        expected_version = int(expected) if expected is not None else None
    except (TypeError, ValueError):
        return {"error": "Invalid expectedVersion", "_status": 400}
    idempotency_key = str(body.get("idempotencyKey") or "").strip()
    idem_key = f"{meeting_id}:transition:{idempotency_key}" if idempotency_key else ""
    if idem_key and idem_key in data.get("idempotency", {}):
        return {"ok": True, "meeting": data.get("meetings", {}).get(meeting_id), "idempotent": True}
    meeting = data.get("meetings", {}).get(meeting_id)
    if not isinstance(meeting, MutableMapping):
        return {"error": "Executable meeting not found", "_status": 404}
    current = phase(meeting)
    try:
        validate_transition(meeting, target, expected_version=expected_version)
    except MeetingLifecycleError as error:
        if error.code == "meeting_version_stale":
            return {"error": "Meeting version conflict", "currentVersion": meeting.get("version", 0), "_status": 409}
        return {"error": f"Illegal transition from {current} to {target}", "stage": current, "_status": error.status}
    actor = {"type": str(body.get("actorType") or "user"), "id": str(body.get("actorId") or "user")}
    if current == "awaiting_user_decision" and raw_target in {"continue", "continue_decision"}:
        hooks.continue_decision(data, meeting, actor=actor, reason=body.get("reason") or "user_continue")
        return {"ok": True, "meeting": meeting, "event": data.get("events", {}).get(meeting_id, [])[-1]}
    meeting["previousStage"] = current
    meeting["stage"] = target
    if target == "preparing":
        hooks.mark_preparing(meeting)
    if target in {"active_opening", "active_discussion"}:
        meeting["currentSpeaker"] = (meeting.get("speakerQueue") or [""])[0]
    if target == "active_discussion":
        meeting["round"] = max(1, int(meeting.get("round") or 0))
    if target in TERMINAL:
        meeting["currentSpeaker"] = ""
        release_occupancy(data, meeting_id, meeting.get("participants") or [])
        hooks.resume_original_work(data, meeting, target)
        if target == "completed":
            result = body.get("result") if isinstance(body.get("result"), dict) else {}
            if body.get("summary"):
                result.setdefault("summary", str(body.get("summary") or ""))
            meeting["result"] = {**meeting.get("result", {}), **result}
            hooks.ensure_action_items(data, meeting)
            hooks.award_points(meeting)
    event = hooks.append_event(
        data, meeting, "meeting_transitioned", actor=actor,
        payload={"from": current, "to": target, "reason": body.get("reason") or ""},
        idempotency_key=idempotency_key,
    )
    if idem_key:
        data.setdefault("idempotency", {})[idem_key] = {"meetingId": meeting_id, "sequence": event["sequence"]}
    return {"ok": True, "meeting": meeting, "event": event, "terminal": target in TERMINAL}


def create_command(
    data: MutableMapping[str, Any], config: Mapping[str, Any], hooks: CreateHooks,
) -> dict[str, Any]:
    meeting_id = str(config["meetingId"])
    participants = list(config["participants"])
    idempotency_key = str(config.get("idempotencyKey") or "")
    if idempotency_key and idempotency_key in data.get("idempotency", {}):
        existing_id = data["idempotency"][idempotency_key].get("meetingId")
        existing = data.get("meetings", {}).get(existing_id)
        if existing:
            return {"ok": True, "meeting": existing, "idempotent": True}
    try:
        hooks.rebuild_occupancy(data)
    except MeetingLifecycleError as error:
        return {"error": str(error), "code": error.code, "details": error.details, "_status": error.status}
    conflicts = hooks.build_conflicts(data, participants)
    occupied = {
        item.get("agentId"): (item.get("source") or {}).get("meetingId")
        for item in conflicts if item.get("reason") == "meeting_occupied"
    }
    if conflicts and not config.get("allowConflicts"):
        if occupied:
            return {"error": "One or more participants are already in an executable meeting", "conflicts": occupied, "_status": 409}
        return {"error": "One or more participants are busy", "conflicts": conflicts, "_status": 409}
    stage = "conflict" if conflicts else "preparing"
    now = str(config["now"])
    meeting = {
        "id": meeting_id, "executableMeeting": True, "topic": config["topic"],
        "agenda": config["agenda"], "purpose": config["purpose"], "meetingType": config["meetingType"],
        "organizer": config["organizer"], "createdBy": config["createdBy"],
        "createdByType": config["createdByType"], "createdByAgentId": config["createdByAgentId"],
        "projectId": config["projectId"], "projectTitle": config["projectTitle"],
        "moderator": config["moderator"], "participants": participants, "stage": stage,
        "preparingStartedAt": now if stage == "preparing" else "",
        "preparingTimeoutSec": config["preparingTimeoutSec"], "previousStage": "", "round": 0,
        "maxRounds": config["maxRounds"], "decisionWindowSec": config["decisionWindowSec"],
        "decisionWindowConfiguredSec": config["decisionWindowSec"],
        "resolutionPolicy": config["resolutionPolicy"], "currentSpeaker": "", "speakerQueue": participants,
        "context": config["context"], "contextMode": config["contextMode"], "contextBudget": config["contextBudget"],
        "rollingSummary": "", "participantLastSeen": {},
        "participantState": {
            participant: {
                "status": "conflict" if any(
                    item.get("agentId") == participant and item.get("status") in {"open", "waiting", "reserved"}
                    for item in conflicts
                ) else "reserved",
                "joinedAt": now,
            } for participant in participants
        },
        "conflicts": conflicts, "originalWork": {}, "reservation": {}, "result": {},
        "source": copy.deepcopy(config.get("source") or {}), "version": 0, "lastEventSequence": 0,
        "createdAt": now, "updatedAt": now,
    }
    data.setdefault("meetings", {})[meeting_id] = meeting
    event = hooks.append_event(
        data, meeting, "meeting_created", actor=config["actor"],
        payload={"stage": stage, "conflicts": conflicts}, idempotency_key=idempotency_key,
    )
    if not conflicts:
        claim_occupancy(data, meeting_id, participants)
    if idempotency_key:
        data.setdefault("idempotency", {})[idempotency_key] = {"meetingId": meeting_id, "sequence": event["sequence"]}
    return {"ok": True, "meeting": meeting, "conflicts": bool(conflicts)}


def prepare_agent_turn(
    data: MutableMapping[str, Any], meeting_id: str, stage: str, speaker: str, hooks: AgentTurnHooks,
) -> dict[str, Any]:
    meeting = data.get("meetings", {}).get(meeting_id)
    if not isinstance(meeting, MutableMapping):
        return {"error": "Executable meeting not found", "_status": 404}
    events = list(data.get("events", {}).get(meeting_id, []))
    round_index = meeting.get("round")
    if hooks.formal_turn_exists(events, stage, round_index, speaker):
        return {"ok": True, "skip": "formal_turn_exists"}
    if hooks.pending_turn_exists(events, stage, round_index, speaker):
        return {"ok": True, "skip": "provider_call_pending"}
    meeting["currentSpeaker"] = speaker
    prompt = hooks.build_prompt(meeting, speaker, stage, events)
    pending = hooks.append_event(
        data, meeting, "provider_call_started", actor={"type": "agent", "id": speaker},
        payload={
            "speaker": speaker, "stage": stage, "round": round_index,
            "contextMode": meeting.get("contextMode"), "promptChars": len(prompt),
        },
    )
    token = compare_token(meeting, data.get("events", {}).get(meeting_id, []), call_id=str(pending.get("sequence") or ""), participant=speaker)
    return {"ok": True, "meeting": meeting, "prompt": prompt, "pending": pending, "token": token}


def commit_agent_turn(
    data: MutableMapping[str, Any], meeting_id: str, stage: str, speaker: str,
    provider_result: Mapping[str, Any], pending: Mapping[str, Any], token: MeetingCompareToken,
    hooks: AgentTurnHooks,
) -> dict[str, Any]:
    meeting = data.get("meetings", {}).get(meeting_id)
    if not isinstance(meeting, MutableMapping):
        return {"error": "Executable meeting not found", "_status": 404}
    normalized = hooks.normalize_reply(str(provider_result.get("reply") or ""))
    pending_payload = pending.get("payload") if isinstance(pending.get("payload"), dict) else {}
    expected_round = pending_payload.get("round", meeting.get("round"))
    events = list(data.get("events", {}).get(meeting_id, []))
    if hooks.formal_turn_exists(events, stage, expected_round, speaker):
        hooks.append_ignored(data, meeting, speaker, provider_result, normalized, pending, "formal_turn_already_exists", stage, expected_round)
        return {"ok": True, "meeting": meeting, "ignoredProviderCompletion": True}
    if not token_is_current(meeting, events, token):
        hooks.append_ignored(data, meeting, speaker, provider_result, normalized, pending, "meeting_state_changed", stage, expected_round)
        return {"ok": True, "meeting": meeting, "ignoredProviderCompletion": True}
    payload = {
        "speaker": speaker, "text": normalized.get("text") or "", "rawText": normalized.get("rawText") or "",
        "structured": normalized.get("structured") or {}, "parseError": normalized.get("parseError") or "",
        "ok": bool(provider_result.get("ok")), "stage": stage, "round": meeting.get("round"),
        "providerRef": provider_result.get("providerRef") or hooks.provider_ref(speaker),
        "conversationId": provider_result.get("conversationId") or "",
        "durationMs": provider_result.get("durationMs") or 0, "inReplyToSequence": pending.get("sequence"),
    }
    if normalized.get("providerRaw"):
        payload["providerRaw"] = normalized["providerRaw"]
    event = hooks.append_event(data, meeting, "participant_turn", actor={"type": "agent", "id": speaker}, payload=payload)
    meeting.setdefault("participantLastSeen", {})[speaker] = event["sequence"]
    hooks.update_summary(meeting, speaker, payload["text"])
    return {"ok": True, "meeting": meeting, "event": event}
