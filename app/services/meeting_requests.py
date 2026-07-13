"""Transport-independent AI Meeting request commands over the unified Store."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Mapping, MutableMapping

from . import meeting_lifecycle


def error(message: str, status: int = 400, code: str = "bad_request") -> dict[str, Any]:
    return {"ok": False, "error": message, "code": code, "_status": status}


def clean_type(raw: Any) -> str:
    value = str(raw or "discussion").strip()
    return value if value in {"information", "discussion", "task"} else "discussion"


def urgency(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 3
    return max(1, min(5, value))


def public_request(request: Mapping[str, Any] | None) -> dict[str, Any]:
    result = copy.deepcopy(dict(request or {}))
    result["contextCandidates"] = [dict(candidate, selected=False) for candidate in result.get("contextCandidates", [])]
    return result


def unresolved_for_task(request: Mapping[str, Any], project_id: str, task_id: str) -> bool:
    source = request.get("source") if isinstance(request.get("source"), Mapping) else {}
    if source.get("projectId") != project_id or source.get("taskId") != task_id or not request.get("blockingTask"):
        return False
    blocker = request.get("taskBlocker") if isinstance(request.get("taskBlocker"), Mapping) else {}
    if blocker.get("resolvedAt"):
        return False
    return request.get("status") in {"pending", "confirmed", "rejected"} or blocker.get("status") in {
        "pending", "confirmed", "rejected", "needs_user_decision",
    }


def _processed(request: Mapping[str, Any]) -> bool:
    if str(request.get("status") or "") in {"confirmed", "rejected"}:
        return True
    review = request.get("review") if isinstance(request.get("review"), Mapping) else {}
    conversion = request.get("conversion") if isinstance(request.get("conversion"), Mapping) else {}
    return bool(review.get("confirmedAt") or review.get("rejectedAt") or conversion.get("meetingId"))


def list_command(
    data: Mapping[str, Any], *, status: str = "", project_id: str = "", task_id: str = "",
) -> dict[str, Any]:
    requests = [request for request in data.get("requests", {}).values() if isinstance(request, Mapping)]
    if status: requests = [request for request in requests if request.get("status") == status]
    if project_id: requests = [request for request in requests if (request.get("source") or {}).get("projectId") == project_id]
    if task_id: requests = [request for request in requests if (request.get("source") or {}).get("taskId") == task_id]
    requests.sort(key=lambda request: str(request.get("updatedAt") or request.get("createdAt") or ""), reverse=True)
    requests.sort(key=lambda request: 1 if _processed(request) else 0)
    return {
        "ok": True, "requests": [public_request(request) for request in requests],
        "pendingCount": sum(1 for request in requests if request.get("status") == "pending"),
    }


def detail_command(data: Mapping[str, Any], request_id: str) -> dict[str, Any]:
    request = data.get("requests", {}).get(request_id)
    return {"ok": True, "request": public_request(request)} if isinstance(request, Mapping) else error(
        "Meeting request not found", 404, "request_not_found",
    )


def selected_context(request: Mapping[str, Any], selected_ids: list[Any], supplemental_context: Any) -> tuple[str, list[dict[str, Any]]]:
    selected = {str(value) for value in selected_ids or []}
    pieces: list[str] = []
    snapshots: list[dict[str, Any]] = []
    for candidate in request.get("contextCandidates") or []:
        if not isinstance(candidate, Mapping) or str(candidate.get("id")) not in selected:
            continue
        item = copy.deepcopy(dict(candidate)); item["selected"] = True; snapshots.append(item)
        title = item.get("title") or item.get("sourceKind") or "Context"
        summary = item.get("summary") or ""
        pieces.append(f"[{item.get('sourceKind')}] {title}\n{summary}".strip())
    supplemental = str(supplemental_context or "").strip()
    if supplemental:
        pieces.append("[supplemental]\n" + supplemental)
    return "\n\n".join(piece for piece in pieces if piece), snapshots


@dataclass(frozen=True)
class RequestHooks:
    now: Callable[[], str]
    new_id: Callable[[], str]
    clean_participants: Callable[[Any], list[str]]
    is_excluded: Callable[[str], bool]
    auto_confirm_label: Callable[[str], str]
    lifecycle_hooks: meeting_lifecycle.CreateHooks


def _request_idempotency(data: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    return data.setdefault("idempotency", {}).setdefault("requests", {})


def _lifecycle_view(data: MutableMapping[str, Any]) -> dict[str, Any]:
    return {
        "meetings": data.setdefault("meetings", {}),
        "events": data.setdefault("events", {}),
        "occupancy": data.setdefault("occupancy", {}),
        "idempotency": data.setdefault("idempotency", {}).setdefault("meetings", {}),
    }


def create_command(
    data: MutableMapping[str, Any], project: Mapping[str, Any], task: Mapping[str, Any],
    body: Mapping[str, Any], context_candidates: list[dict[str, Any]], hooks: RequestHooks,
) -> dict[str, Any]:
    source_type = str(body.get("sourceType") or "project_task").strip()
    if source_type != "project_task":
        return error("Only project_task meeting requests are supported in this phase", 400, "unsupported_source")
    goal = str(body.get("goal") or body.get("meetingGoal") or "").strip()
    expected = str(body.get("expectedOutcome") or "").strip()
    reason = str(body.get("reason") or body.get("cannotCompleteAloneReason") or "").strip()
    if not goal: return error("Meeting goal is required", 400, "goal_required")
    if not expected: return error("Expected outcome is required", 400, "expected_outcome_required")
    if not reason: return error("Reason why the AI cannot complete alone is required", 400, "reason_required")
    requester = str(body.get("requestingAgentId") or body.get("agentId") or task.get("executorAgentId") or task.get("assignee") or "").strip()
    if not requester: return error("Requesting agent is required", 400, "requesting_agent_required")
    participants = hooks.clean_participants(body.get("suggestedParticipants") or body.get("participants") or [])
    if requester not in participants: participants.insert(0, requester)
    moderator = str(body.get("suggestedModerator") or body.get("moderator") or (participants[0] if participants else requester)).strip()
    blocked = [participant for participant in participants if hooks.is_excluded(participant)]
    if moderator and hooks.is_excluded(moderator) and moderator not in blocked: blocked.append(moderator)
    if blocked:
        return error("Archive manager cannot participate in executable meetings", 400, "archive_manager_not_meeting_participant") | {"participants": blocked}
    project_id = str(project.get("id") or ""); task_id = str(task.get("id") or "")
    existing = next((item for item in data.get("requests", {}).values() if unresolved_for_task(item, project_id, task_id)), None)
    if existing:
        return {"ok": True, "request": public_request(existing), "existingBlockingRequest": True, "idempotent": True}
    idem_key = str(body.get("idempotencyKey") or "").strip()
    if idem_key:
        record = _request_idempotency(data).get(idem_key)
        existing = data.get("requests", {}).get(record.get("requestId")) if isinstance(record, Mapping) else None
        if existing: return {"ok": True, "request": public_request(existing), "idempotent": True}
    now = hooks.now(); request_id = str(body.get("id") or hooks.new_id())
    requested_ids = list(body.get("selectedContextIds") or body.get("contextIds") or [])
    request = {
        "id": request_id, "status": "pending", "sourceType": "project_task",
        "source": {"projectId": project_id, "taskId": task_id, "projectTitle": project.get("title", ""), "taskTitle": task.get("title", "")},
        "requestingAgentId": requester,
        "originalProposal": {
            "topic": str(body.get("topic") or task.get("title") or goal).strip(),
            "purpose": str(body.get("purpose") or goal).strip(), "meetingType": clean_type(body.get("meetingType")),
            "goal": goal, "expectedOutcome": expected, "cannotCompleteAloneReason": reason,
            "suggestedParticipants": participants, "suggestedModerator": moderator,
            "maxRounds": body.get("maxRounds") or 2, "urgency": urgency(body.get("urgency") or body.get("urgencyScore") or body.get("priority")),
        },
        "urgency": urgency(body.get("urgency") or body.get("urgencyScore") or body.get("priority")),
        "blockingTask": True, "taskBlocker": {"status": "pending", "createdAt": now, "updatedAt": now, "resolvedAt": ""},
        "contextCandidates": copy.deepcopy(context_candidates),
        "requestedContext": {"selectedContextIds": requested_ids, "supplementalContext": str(body.get("supplementalContext") or "").strip()},
        "review": {}, "conversion": {}, "idempotencyKey": idem_key, "createdAt": now, "updatedAt": now,
    }
    data.setdefault("requests", {})[request_id] = request
    if idem_key: _request_idempotency(data)[idem_key] = {"requestId": request_id}
    return {"ok": True, "request": public_request(request), "created": True}


def confirm_command(
    data: MutableMapping[str, Any], request_id: str, body: Mapping[str, Any],
    *, project_title: str, lifecycle_defaults: Mapping[str, Any], hooks: RequestHooks,
) -> dict[str, Any]:
    request = data.get("requests", {}).get(request_id)
    if not isinstance(request, MutableMapping): return error("Meeting request not found", 404, "request_not_found")
    if request.get("status") == "rejected": return error("Rejected meeting request cannot be confirmed", 409, "request_rejected")
    if request.get("status") == "confirmed" and (request.get("conversion") or {}).get("meetingId"):
        meeting_id = request["conversion"]["meetingId"]
        return {"ok": True, "request": public_request(request), "meeting": data.get("meetings", {}).get(meeting_id), "meetingId": meeting_id, "idempotent": True}
    proposal = request.get("originalProposal") if isinstance(request.get("originalProposal"), Mapping) else {}
    selected_ids = list(body.get("selectedContextIds") or body.get("contextIds") or [])
    context, snapshots = selected_context(request, selected_ids, body.get("supplementalContext"))
    participants = hooks.clean_participants(body.get("participants") or proposal.get("suggestedParticipants") or [])
    moderator = str(body.get("moderator") or proposal.get("suggestedModerator") or "").strip()
    if moderator and moderator not in participants: participants.insert(0, moderator)
    blocked = [participant for participant in participants if hooks.is_excluded(participant)]
    if blocked: return error("Archive manager cannot participate in executable meetings", 400, "archive_manager_not_meeting_participant") | {"participants": blocked}
    now = hooks.now(); source = request.get("source") if isinstance(request.get("source"), Mapping) else {}
    final = {
        "topic": str(body.get("topic") or proposal.get("topic") or "").strip(),
        "purpose": str(body.get("purpose") or proposal.get("purpose") or proposal.get("goal") or "").strip(),
        "meetingType": clean_type(body.get("meetingType") or proposal.get("meetingType")),
        "participants": participants, "moderator": moderator or (participants[0] if participants else ""),
        "maxRounds": body.get("maxRounds") or proposal.get("maxRounds") or 2,
        "contextMode": str(body.get("contextMode") or "incremental"),
        "resolutionPolicy": str(body.get("resolutionPolicy") or "moderator_decision"),
        "context": context, "selectedContextIds": selected_ids, "selectedContextSnapshot": snapshots,
        "supplementalContext": str(body.get("supplementalContext") or "").strip(),
        "projectId": str(body.get("projectId") or source.get("projectId") or "").strip(), "projectTitle": project_title,
    }
    edit_summary = []
    for key in ("topic", "purpose", "meetingType", "moderator", "maxRounds"):
        original = proposal.get(key if key != "moderator" else "suggestedModerator")
        if str(final.get(key) or "") != str(original or ""): edit_summary.append(key)
    auto_confirmed = bool(body.get("autoConfirmed")); auto_reason = str(body.get("autoConfirmReason") or "")
    request["review"] = {
        "finalConfig": copy.deepcopy(final), "selectedContextIds": selected_ids,
        "supplementalContext": final["supplementalContext"], "editSummary": ", ".join(edit_summary) if edit_summary else "No configuration edits",
        "confirmedBy": str(body.get("confirmedBy") or "user"), "confirmedAt": now,
        "autoConfirmed": auto_confirmed, "autoConfirmReason": auto_reason,
        "autoConfirmLabel": hooks.auto_confirm_label(auto_reason) if auto_confirmed else "",
    }
    meeting_id = str(lifecycle_defaults.get("meetingId") or hooks.new_id())
    lifecycle_data = _lifecycle_view(data)
    meeting_result = meeting_lifecycle.create_command(lifecycle_data, {
        **dict(lifecycle_defaults), "meetingId": meeting_id, "topic": final["topic"], "agenda": final["topic"],
        "purpose": final["purpose"], "meetingType": final["meetingType"], "participants": participants,
        "moderator": final["moderator"], "organizer": request.get("requestingAgentId") or "ai",
        "createdBy": request.get("requestingAgentId") if auto_confirmed else "user",
        "createdByType": "agent" if auto_confirmed else "user",
        "createdByAgentId": request.get("requestingAgentId") if auto_confirmed else "",
        "projectId": final["projectId"], "projectTitle": project_title, "maxRounds": final["maxRounds"],
        "resolutionPolicy": final["resolutionPolicy"], "context": final["context"], "contextMode": final["contextMode"],
        "source": {"meetingRequestId": request_id, "requestingAgentId": request.get("requestingAgentId"), "urgency": request.get("urgency"), "autoConfirmed": auto_confirmed, "autoConfirmReason": auto_reason, "autoConfirmLabel": hooks.auto_confirm_label(auto_reason) if auto_confirmed else "", **source},
        "idempotencyKey": str(body.get("idempotencyKey") or f"meeting-request-confirm:{request_id}"), "now": now,
        "actor": {"type": "agent" if auto_confirmed else "user", "id": request.get("requestingAgentId") if auto_confirmed else "user"},
    }, hooks.lifecycle_hooks)
    data["occupancy"] = lifecycle_data["occupancy"]
    if not meeting_result.get("ok"): return meeting_result
    meeting = meeting_result["meeting"]
    request["status"] = "confirmed"; request["conversion"] = {"meetingId": meeting["id"], "convertedAt": now}
    request["taskBlocker"] = {**(request.get("taskBlocker") or {}), "status": "confirmed", "meetingId": meeting["id"], "updatedAt": now}
    request["updatedAt"] = now
    return {"ok": True, "request": public_request(request), "meeting": meeting, "meetingId": meeting["id"], "idempotent": bool(meeting_result.get("idempotent"))}


def reject_command(data: MutableMapping[str, Any], request_id: str, body: Mapping[str, Any], hooks: RequestHooks) -> dict[str, Any]:
    reason = str(body.get("reason") or "").strip()
    if not reason: return error("Rejection reason is required", 400, "reason_required")
    request = data.get("requests", {}).get(request_id)
    if not isinstance(request, MutableMapping): return error("Meeting request not found", 404, "request_not_found")
    if request.get("status") == "confirmed": return error("Confirmed meeting request cannot be rejected", 409, "request_confirmed")
    if request.get("status") == "rejected": return {"ok": True, "request": public_request(request), "idempotent": True}
    now = hooks.now(); request["status"] = "rejected"
    request["review"] = {"rejectedBy": str(body.get("rejectedBy") or "user"), "rejectedAt": now, "rejectionReason": reason}
    request["taskBlocker"] = {**(request.get("taskBlocker") or {}), "status": "rejected", "rejectionReason": reason, "updatedAt": now}
    request["updatedAt"] = now
    return {"ok": True, "request": public_request(request)}


def resolve_blocker_command(data: MutableMapping[str, Any], request_id: str, status: str, extra: Mapping[str, Any] | None, hooks: RequestHooks) -> dict[str, Any]:
    if not request_id: return {"ok": True, "skipped": True}
    request = data.get("requests", {}).get(request_id)
    if not isinstance(request, MutableMapping): return error("Meeting request not found", 404, "request_not_found")
    now = hooks.now()
    request["taskBlocker"] = {**(request.get("taskBlocker") or {}), "status": status, "resolvedAt": now, "updatedAt": now, **dict(extra or {})}
    request["updatedAt"] = now
    return {"ok": True, "request": public_request(request)}
