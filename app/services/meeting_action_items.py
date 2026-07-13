"""Meeting action-item normalization, selection, projection, and idempotency."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Mapping, MutableMapping


@dataclass(frozen=True)
class ActionHooks:
    now: Callable[[], str]
    append_event: Callable[..., dict[str, Any]]


def normalize(raw: Any, index: int, meeting: Mapping[str, Any], now: str) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        title = str(raw.get("title") or raw.get("item") or raw.get("text") or raw.get("task") or raw.get("action") or "").strip()
        description = str(raw.get("description") or raw.get("details") or raw.get("note") or "").strip()
        owner = str(raw.get("owner") or raw.get("assignee") or raw.get("responsible") or "").strip()
        status = str(raw.get("status") or raw.get("nextStatus") or "todo").strip() or "todo"
        source_text = str(raw.get("sourceText") or raw.get("source") or "").strip()
        priority = str(raw.get("priority") or "medium").strip() or "medium"
    else:
        title = str(raw or "").strip(); description = ""; owner = ""; status = "todo"; source_text = ""; priority = "medium"
    title = title or f"Action item {index + 1}"
    return {
        "id": f"ai-{index + 1}", "title": title, "description": description,
        "suggestedOwner": owner, "assignee": owner, "suggestedStatus": status,
        "priority": priority, "sourceMeetingId": meeting.get("id"), "sourceText": source_text or title,
        "targetProjectId": meeting.get("projectId") or "", "status": "draft",
        "createdAt": now, "updatedAt": now, "audit": [],
    }


def ensure_drafts(data: MutableMapping[str, Any], meeting: MutableMapping[str, Any], hooks: ActionHooks) -> list[dict[str, Any]]:
    existing = meeting.get("actionItemDrafts")
    if isinstance(existing, list) and existing:
        for draft in existing:
            if not isinstance(draft, MutableMapping):
                continue
            target_task_id = draft.get("targetTaskId") or draft.get("sourceTaskId") or draft.get("taskId")
            if target_task_id:
                draft.setdefault("targetTaskId", target_task_id)
                draft.setdefault("sourceTaskId", target_task_id)
        return existing
    result = meeting.get("result") if isinstance(meeting.get("result"), Mapping) else {}
    raw_items = result.get("actionItems") if isinstance(result.get("actionItems"), list) else []
    now = hooks.now(); drafts = [normalize(item, index, meeting, now) for index, item in enumerate(raw_items)]
    meeting["actionItemDrafts"] = drafts
    if drafts:
        hooks.append_event(
            data, meeting, "action_item_drafts_created", actor={"type": "system", "id": "system"},
            payload={"count": len(drafts), "projectId": meeting.get("projectId") or ""},
        )
    return drafts


def find_draft(meeting: MutableMapping[str, Any], action_item_id: str) -> MutableMapping[str, Any] | None:
    return next((draft for draft in meeting.setdefault("actionItemDrafts", []) if str(draft.get("id") or "") == str(action_item_id or "")), None)


def snapshot(draft: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in draft.items() if key != "audit"}


def audit(draft: MutableMapping[str, Any], action: str, actor_id: str, now: str, before=None, extra=None) -> None:
    entries = draft.setdefault("audit", [])
    entries.append({
        "action": action, "actorId": actor_id or "user", "at": now, "before": before or {},
        "after": {key: draft.get(key) for key in ("title", "description", "assignee", "targetProjectId", "priority", "status", "taskId")},
        **dict(extra or {}),
    })
    draft["audit"] = entries[-100:]


def _idempotency(data: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    root = data.setdefault("idempotency", {})
    return root.setdefault("actionItems", {}) if "actionItems" in root or any(key in root for key in ("meetings", "requests", "callbacks")) else root


def mutate_command(
    data: MutableMapping[str, Any], meeting_id: str, action_item_id: str,
    body: Mapping[str, Any], hooks: ActionHooks,
) -> dict[str, Any]:
    action = str(body.get("action") or "").strip()
    if action not in {"update", "reject", "keep", "confirm"}:
        return {"error": "Invalid action item action", "_status": 400}
    meeting = data.get("meetings", {}).get(meeting_id)
    if not isinstance(meeting, MutableMapping): return {"error": "Executable meeting not found", "_status": 404}
    ensure_drafts(data, meeting, hooks); draft = find_draft(meeting, action_item_id)
    if not draft: return {"error": "Action item draft not found", "_status": 404}
    actor_id = str(body.get("actorId") or body.get("by") or "user").strip() or "user"
    idem_value = str(body.get("idempotencyKey") or "").strip()
    idem_key = f"{meeting_id}:action-item:{action_item_id}:{action}:{idem_value}" if idem_value else ""
    idem = _idempotency(data).get(idem_key) if idem_key else None
    if isinstance(idem, Mapping):
        task_id = idem.get("taskId") or draft.get("targetTaskId") or draft.get("sourceTaskId") or draft.get("taskId")
        return {"ok": True, "meeting": meeting, "actionItem": draft, "taskId": task_id, "targetTaskId": task_id, "meetingActionItemId": idem.get("meetingActionItemId") or draft.get("meetingActionItemId"), "idempotent": True}
    before = snapshot(draft); now = hooks.now()
    if action == "confirm":
        if draft.get("status") == "confirmed":
            task_id = draft.get("targetTaskId") or draft.get("sourceTaskId") or draft.get("taskId")
            if idem_key: _idempotency(data)[idem_key] = {"meetingId": meeting_id, "taskId": task_id}
            return {"ok": True, "meeting": meeting, "actionItem": draft, "taskId": task_id, "targetTaskId": task_id, "idempotent": True}
        source = meeting.get("source") if isinstance(meeting.get("source"), Mapping) else {}
        target_task_id = str(source.get("taskId") or body.get("taskId") or draft.get("targetTaskId") or draft.get("sourceTaskId") or "").strip()
        return {
            "ok": True, "prepared": True, "meeting": copy.deepcopy(meeting), "actionItem": copy.deepcopy(draft),
            "before": before, "actorId": actor_id, "idempotencyKey": idem_key, "rawIdempotencyKey": idem_value,
            "targetProjectId": str(source.get("projectId") or meeting.get("projectId") or body.get("targetProjectId") or body.get("projectId") or draft.get("targetProjectId") or "").strip(),
            "targetTaskId": target_task_id, "sourceTaskId": target_task_id,
            "compare": {"status": draft.get("status"), "updatedAt": draft.get("updatedAt"), "meetingVersion": meeting.get("version")},
        }
    if draft.get("status") == "confirmed":
        messages = {"update": "Confirmed action items cannot be edited", "reject": "Confirmed action items cannot be rejected", "keep": "Confirmed action items cannot be changed to meeting-only"}
        return {"error": messages[action], "_status": 409}
    if action == "update":
        for key in ("title", "description", "assignee", "targetProjectId", "priority"):
            if key in body: draft[key] = str(body.get(key) or "").strip()
        if not draft.get("targetProjectId") and body.get("projectId"): draft["targetProjectId"] = str(body.get("projectId") or "").strip()
    elif action == "reject":
        draft["status"] = "rejected"; draft["rejectionReason"] = str(body.get("reason") or body.get("rejectionReason") or "").strip()
    else:
        draft["status"] = "kept_as_meeting_item"
    draft["updatedAt"] = now; audit(draft, action, actor_id, now, before)
    event = hooks.append_event(data, meeting, "action_item_updated", actor={"type": "user", "id": actor_id}, payload={"action": action, "actionItemId": action_item_id, "before": before, "after": draft}, idempotency_key=idem_value)
    if idem_key: _idempotency(data)[idem_key] = {"meetingId": meeting_id, "sequence": event["sequence"]}
    return {"ok": True, "meeting": meeting, "actionItem": draft}


def project_action_key(meeting_id: str, action_item_id: str) -> str:
    return f"meeting:{meeting_id}:action:{action_item_id}"


def attach_to_project(
    project: MutableMapping[str, Any], task_id: str, meeting: Mapping[str, Any], draft: Mapping[str, Any],
    action_item_id: str, actor_id: str, before: Mapping[str, Any], now: str,
) -> dict[str, Any]:
    if project.get("status") == "archived": return {"error": "Archived projects cannot receive meeting action items", "_status": 400}
    task = next((item for item in project.get("tasks", []) if item.get("id") == task_id), None)
    if not task: return {"error": "Target project task not found", "_status": 404}
    meeting_id = str(meeting.get("id") or ""); item_id = project_action_key(meeting_id, action_item_id)
    meeting_source = meeting.get("source") if isinstance(meeting.get("source"), Mapping) else {}
    request_id = str(meeting_source.get("meetingRequestId") or "")
    blocker = task.get("meetingBlocker") if isinstance(task.get("meetingBlocker"), Mapping) else {}
    if request_id and blocker.get("requestId") and blocker.get("requestId") != request_id:
        return {"error": "Target task Meeting linkage is stale", "code": "action_item_meeting_link_stale", "_status": 409}
    if blocker.get("meetingId") and str(blocker.get("meetingId")) != meeting_id:
        return {"error": "Target task is linked to a different Meeting", "code": "action_item_meeting_link_stale", "_status": 409}
    items = task.setdefault("meetingActionItems", [])
    existing = next((item for item in items if isinstance(item, Mapping) and str(item.get("id") or "") == item_id), None)
    record = {
        "id": item_id, "meetingId": meeting_id, "requestId": request_id,
        "sourceActionItemId": action_item_id, "title": str(draft.get("title") or "").strip() or "Meeting action item",
        "description": str(draft.get("description") or draft.get("sourceText") or "").strip(),
        "owner": str(draft.get("assignee") or draft.get("suggestedOwner") or task.get("executorAgentId") or task.get("assignee") or "").strip(),
        "status": "pending", "requiredForResume": True, "priority": str(draft.get("priority") or "medium").strip() or "medium",
        "sourceSnapshot": copy.deepcopy(dict(before)), "confirmedBy": actor_id, "confirmedAt": now, "updatedAt": now,
    }
    if existing:
        existing.update(record); record = existing; idempotent = True
    else:
        record["createdAt"] = now; items.append(record); idempotent = False
    task["updatedAt"] = now; project["updatedAt"] = now
    return {"ok": True, "task": task, "record": record, "idempotent": idempotent}


def commit_confirmation(
    data: MutableMapping[str, Any], meeting_id: str, action_item_id: str,
    prepared: Mapping[str, Any], project_result: Mapping[str, Any], hooks: ActionHooks,
) -> dict[str, Any]:
    meeting = data.get("meetings", {}).get(meeting_id)
    if not isinstance(meeting, MutableMapping):
        task_id = (project_result.get("task") or {}).get("id")
        return {"ok": True, "task": project_result.get("task"), "taskId": task_id, "targetTaskId": task_id}
    ensure_drafts(data, meeting, hooks); draft = find_draft(meeting, action_item_id)
    if not draft: return {"error": "Action item draft not found", "_status": 404}
    compare = prepared.get("compare") if isinstance(prepared.get("compare"), Mapping) else {}
    if draft.get("status") == "confirmed" and draft.get("meetingActionItemId") == (project_result.get("record") or {}).get("id"):
        task_id = (project_result.get("task") or {}).get("id")
        return {"ok": True, "meeting": meeting, "actionItem": draft, "task": project_result.get("task"), "taskId": task_id, "targetTaskId": task_id, "idempotent": True}
    if draft.get("status") != compare.get("status") or draft.get("updatedAt") != compare.get("updatedAt"):
        return {"error": "Action item changed while project task was being updated", "code": "action_item_stale", "_status": 409}
    task = project_result.get("task") or {}; record = project_result.get("record") or {}; before = snapshot(draft); now = hooks.now()
    draft.update({
        "status": "confirmed", "targetProjectId": prepared.get("targetProjectId"),
        "targetTaskId": task.get("id"), "sourceTaskId": task.get("id"),
        "meetingActionItemId": record.get("id"), "confirmedBy": prepared.get("actorId"),
        "confirmedAt": record.get("confirmedAt") or now, "updatedAt": now,
    })
    audit(draft, "confirm", str(prepared.get("actorId") or "user"), now, before, {"taskId": task.get("id"), "projectId": prepared.get("targetProjectId"), "meetingActionItemId": record.get("id")})
    event = hooks.append_event(data, meeting, "action_item_confirmed", actor={"type": "user", "id": prepared.get("actorId")}, payload={"actionItemId": action_item_id, "projectId": prepared.get("targetProjectId"), "taskId": task.get("id"), "meetingActionItemId": record.get("id")}, idempotency_key=prepared.get("rawIdempotencyKey"))
    if prepared.get("idempotencyKey"):
        _idempotency(data)[prepared["idempotencyKey"]] = {"meetingId": meeting_id, "taskId": task.get("id"), "meetingActionItemId": record.get("id"), "sequence": event["sequence"]}
    return {"ok": True, "meeting": meeting, "actionItem": draft, "task": task, "taskId": task.get("id"), "targetTaskId": task.get("id"), "meetingActionItem": record}
