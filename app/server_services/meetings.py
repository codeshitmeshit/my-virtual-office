"""Meetings service functions split from server.py.

The functions intentionally hydrate their globals from the importing server module
so this mechanical split can preserve the existing module-level helpers and
configuration while removing domain business bodies from server.py.
"""

import sys

__all__ = ['_exec_meeting_now', '_exec_meeting_parse_ts', '_meeting_preparing_timeout_sec', '_exec_meeting_empty_store', '_load_exec_meeting_store', '_save_exec_meeting_store', '_meeting_requests_file', '_meeting_request_empty_store', '_meeting_request_clean_type', '_meeting_request_find_project_task', '_meeting_request_summary', '_meeting_request_context_candidates', '_meeting_request_public', '_meeting_request_processed', '_meeting_request_sort_key', '_meeting_request_sort_time', '_sort_meeting_requests', '_meeting_request_error', '_meeting_request_urgency', '_project_high_priority_ai_meeting_requires_confirmation', '_meeting_request_auto_confirm_reason', '_meeting_request_auto_confirm_label', '_meeting_request_log_auto_confirm_activity', '_meeting_request_notification_related', '_meeting_request_notification_details', '_send_meeting_request_notification', '_meeting_request_approved_notification_details', '_meeting_open_url', '_handle_meeting_request_create', '_meeting_request_list_filtered', '_handle_meeting_request_detail', '_meeting_request_selected_context', '_meeting_project_ref', '_handle_meeting_request_confirm', '_handle_meeting_request_reject', '_exec_meeting_clean_participants', '_exec_meeting_archive_manager_participants', '_exec_meeting_archive_manager_error', '_meeting_context_mode', '_meeting_resolution_policy', '_meeting_context_budget', '_meeting_decision_window_sec', '_meeting_clamped_decision_window_sec', '_meeting_truncate_text', '_exec_meeting_next_seq', '_append_exec_meeting_event', '_meeting_mark_preparing_started', '_release_timed_out_preparing_meetings', '_meeting_formal_turn_exists', '_meeting_pending_formal_turn_exists', '_meeting_provider_completion_should_be_ignored', '_meeting_project_work_map', '_meeting_pending_provider_agents', '_meeting_busy_context_for_agent', '_meeting_conflict_advisory', '_meeting_advisory_timeout', '_meeting_live_advisory_prompt', '_meeting_call_advisory_provider', '_meeting_normalize_advisory_reply', '_meeting_complete_live_advisories', '_meeting_build_conflicts', '_meeting_has_open_conflicts', '_meeting_original_work_snapshot', '_meeting_resume_original_work', '_meeting_find_pending_call', '_meeting_skip_timed_out_provider_call', '_meeting_formal_round_complete', '_meeting_has_substantive_disagreement', '_meeting_arbitration_snapshot', '_meeting_open_decision_window', '_meeting_continue_from_decision_window', '_rebuild_exec_meeting_occupancy', '_exec_meeting_pending_calls_projection', '_meeting_normalize_action_item', '_meeting_ensure_action_item_drafts', '_exec_meeting_project_active', '_exec_meeting_transcript_projection', '_exec_meeting_project_history', '_meeting_active_projection', '_meeting_history_projection', '_meeting_find_action_draft', '_meeting_audit_action_item', '_meeting_action_item_snapshot', '_meeting_confirm_action_item_on_source_task', '_handle_executable_meeting_action_item', '_handle_executable_meeting_create', '_handle_executable_meeting_detail', '_handle_executable_meeting_events', '_handle_executable_meeting_conflict_action', '_handle_executable_meeting_transition', '_handle_executable_meeting_intervention', '_handle_executable_meeting_agenda_change', '_handle_executable_meeting_arbitration', '_handle_executable_meeting_moderator_takeover', '_meeting_build_targeted_prompt', '_handle_executable_meeting_targeted_question', '_meeting_events_text', '_meeting_update_rolling_summary', '_meeting_strip_json_fence', '_meeting_parse_json_object', '_meeting_coerce_list', '_meeting_structured_display_text', '_meeting_parse_structured_turn', '_meeting_extract_payload_text', '_meeting_provider_raw_summary', '_meeting_normalize_provider_reply', '_meeting_build_result_prompt', '_meeting_result_outcome', '_meeting_coerce_action_items', '_meeting_parse_result', '_meeting_fallback_result', '_handle_executable_meeting_end_with_moderator', '_meeting_build_prompt', '_meeting_provider_ref', '_meeting_provider_timeout', '_meeting_call_provider', '_handle_executable_meeting_run', '_handle_executable_meeting_reconcile', '_handle_meeting_create', '_handle_meeting_end', '_handle_meeting_end_all', '_handle_meeting_history_delete', '_meeting_request_unresolved_for_task', '_meeting_request_resolve_task_blocker']


def _server_module():
    return sys.modules.get("server") or sys.modules.get("__main__")


def _server_callable(name, fallback=None):
    srv = _server_module()
    candidate = getattr(srv, name, None) if srv is not None else None
    if callable(candidate):
        return candidate
    candidate = globals().get(name)
    if callable(candidate):
        return candidate
    return fallback


def _hydrate():
    srv = _server_module()
    if srv is None:
        return
    exported = set(__all__)
    for key, value in vars(srv).items():
        if key in {"_server_module", "_hydrate"}:
            continue
        if key in exported:
            globals()[key] = value
            continue
        globals()[key] = value


def _wrap_exports():
    for name in list(__all__):
        fn = globals().get(name)
        if not callable(fn) or getattr(fn, "_service_wrapper", False):
            continue

        def wrapper(*args, __fn=fn, **kwargs):
            _hydrate()
            return __fn(*args, **kwargs)

        wrapper.__name__ = getattr(fn, "__name__", name)
        wrapper.__doc__ = getattr(fn, "__doc__", None)
        wrapper.__module__ = __name__
        wrapper._service_wrapper = True
        globals()[name] = wrapper


_wrap_exports()
_hydrate()


def _exec_meeting_now():
    return datetime.now(timezone.utc).isoformat()

def _exec_meeting_parse_ts(value):
    if not value:
        return 0.0
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text).timestamp()
    except (TypeError, ValueError):
        return 0.0

def _meeting_preparing_timeout_sec():
    cfg = (VO_CONFIG.get("meetings") or {}).get("preparingTimeoutSec", 300)
    try:
        seconds = int(cfg)
    except (TypeError, ValueError):
        seconds = 300
    if seconds < 30:
        return 300
    return min(seconds, 86400)

def _exec_meeting_empty_store():
    return {"meetings": {}, "events": {}, "occupancy": {}, "idempotency": {}, "updatedAt": ""}

def _load_exec_meeting_store():
    try:
        with open(_exec_meetings_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _exec_meeting_empty_store()
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return _exec_meeting_empty_store()
    data.setdefault("meetings", {})
    data.setdefault("events", {})
    data.setdefault("occupancy", {})
    data.setdefault("idempotency", {})
    data.setdefault("updatedAt", "")
    if not isinstance(data["meetings"], dict):
        data["meetings"] = {}
    if not isinstance(data["events"], dict):
        data["events"] = {}
    if not isinstance(data["occupancy"], dict):
        data["occupancy"] = {}
    if not isinstance(data["idempotency"], dict):
        data["idempotency"] = {}
    return data

def _save_exec_meeting_store(data):
    data["updatedAt"] = _exec_meeting_now()
    path = _exec_meetings_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}-{threading.get_ident()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o666)
    except Exception:
        pass

def _meeting_requests_file():
    return os.path.join(STATUS_DIR, "meeting-requests.json")

def _meeting_request_empty_store():
    return {"requests": {}, "idempotency": {}, "updatedAt": ""}

def _meeting_request_clean_type(raw):
    value = str(raw or "discussion").strip()
    return value if value in {"information", "discussion", "task"} else "discussion"

def _meeting_request_find_project_task(project_id, task_id):
    project = _handle_project_get(project_id).get("project")
    if not project:
        return None, None
    task = next((t for t in project.get("tasks", []) if t.get("id") == task_id), None)
    return project, task

def _meeting_request_summary(value, limit=500):
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return _meeting_truncate_text(text, limit)

def _meeting_request_context_candidates(project, task):
    candidates = []
    project_id = project.get("id") or ""
    task_id = task.get("id") or ""
    candidates.append({
        "id": f"project:{project_id}",
        "sourceKind": "project",
        "title": project.get("title", "Project"),
        "summary": _meeting_request_summary(project.get("description") or project.get("title") or "", 800),
        "sourceRef": {"projectId": project_id},
        "selected": False,
    })
    candidates.append({
        "id": f"task:{task_id}",
        "sourceKind": "task",
        "title": task.get("title", "Task"),
        "summary": _meeting_request_summary(task.get("description") or task.get("title") or "", 1000),
        "sourceRef": {"projectId": project_id, "taskId": task_id},
        "selected": False,
    })
    related = []
    for item in project.get("tasks", []):
        if item.get("id") == task_id:
            continue
        if len(related) >= 5:
            break
        related.append({
            "id": f"related-task:{item.get('id')}",
            "sourceKind": "related_task",
            "title": item.get("title", "Task"),
            "summary": _meeting_request_summary(item.get("description") or item.get("title") or "", 600),
            "sourceRef": {"projectId": project_id, "taskId": item.get("id")},
            "selected": False,
        })
    candidates.extend(related)
    project_title = str(project.get("title") or "").strip().lower()
    for meeting in _meeting_history_projection():
        if len([c for c in candidates if c.get("sourceKind") == "meeting"]) >= 5:
            break
        source = meeting.get("source") or {}
        same_project = source.get("projectId") == project_id
        text = " ".join(str(meeting.get(k) or "") for k in ("topic", "purpose", "summary", "resolution")).lower()
        if not same_project and project_title and project_title not in text:
            continue
        candidates.append({
            "id": f"meeting:{meeting.get('id')}",
            "sourceKind": "meeting",
            "title": meeting.get("topic") or meeting.get("id") or "Meeting",
            "summary": _meeting_request_summary(meeting.get("summary") or meeting.get("resolution") or meeting.get("purpose") or "", 800),
            "sourceRef": {"projectId": project_id, "meetingId": meeting.get("id")},
            "selected": False,
        })
    return candidates

def _meeting_request_public(req):
    result = dict(req or {})
    result["contextCandidates"] = [dict(c, selected=False) for c in result.get("contextCandidates", [])]
    return result

def _meeting_request_processed(req):
    status = str((req or {}).get("status") or "").strip()
    if status in {"confirmed", "rejected"}:
        return True
    review = (req or {}).get("review") if isinstance((req or {}).get("review"), dict) else {}
    conversion = (req or {}).get("conversion") if isinstance((req or {}).get("conversion"), dict) else {}
    return bool(review.get("confirmedAt") or review.get("rejectedAt") or conversion.get("meetingId"))

def _meeting_request_sort_key(req):
    return 1 if _meeting_request_processed(req) else 0

def _meeting_request_sort_time(req):
    return str((req or {}).get("updatedAt") or (req or {}).get("createdAt") or "")

def _sort_meeting_requests(requests):
    result = list(requests or [])
    result.sort(key=_meeting_request_sort_time, reverse=True)
    result.sort(key=_meeting_request_sort_key)
    return result

def _meeting_request_error(message, status=400, code="bad_request"):
    return {"ok": False, "error": message, "code": code, "_status": status}

def _meeting_request_urgency(raw):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 3
    return max(1, min(5, value))

def _project_high_priority_ai_meeting_requires_confirmation(project):
    return bool((project or {}).get("highPriorityAiMeetingAutoApprove"))

def _meeting_request_auto_confirm_reason(project, urgency):
    if _project_high_priority_ai_meeting_requires_confirmation(project):
        return ""
    return "standard_project_ai_meeting_auto_approve"

def _meeting_request_auto_confirm_label(reason):
    labels = {
        "high_priority_project_ai_meeting_auto_approve": "已因高优先级项目自动批准",
        "standard_project_ai_meeting_auto_approve": "已按普通项目自动批准",
        "urgency": "已因高紧急度自动批准",
    }
    return labels.get(str(reason or ""), str(reason or ""))

def _meeting_request_log_auto_confirm_activity(req, meeting, reason):
    source = (req or {}).get("source") if isinstance((req or {}).get("source"), dict) else {}
    project_id = source.get("projectId")
    if not project_id:
        return
    data = _load_projects()
    project = next((p for p in data.get("projects", []) if p.get("id") == project_id), None)
    if not project:
        return
    label = _meeting_request_auto_confirm_label(reason)
    meeting_id = (meeting or {}).get("id") or ((req or {}).get("conversion") or {}).get("meetingId") or ""
    detail = label or "AI meeting request auto-approved"
    if meeting_id:
        detail = f"{detail}: {meeting_id}"
    _log_activity(project, "meeting_request_auto_confirmed", req.get("requestingAgentId") or "ai", detail, source.get("taskId"))
    project["updatedAt"] = _proj_now()
    _save_projects(data)

def _meeting_request_notification_related(req):
    source = (req or {}).get("source") if isinstance((req or {}).get("source"), dict) else {}
    return {
        "type": "meeting_request",
        "id": (req or {}).get("id") or "",
        "title": ((req or {}).get("originalProposal") or {}).get("topic") or source.get("taskTitle") or "Meeting request",
    }

def _meeting_request_notification_details(req):
    proposal = (req or {}).get("originalProposal") if isinstance((req or {}).get("originalProposal"), dict) else {}
    source = (req or {}).get("source") if isinstance((req or {}).get("source"), dict) else {}
    return [
        ("项目", source.get("projectTitle") or source.get("projectId") or "-"),
        ("任务", source.get("taskTitle") or source.get("taskId") or "-"),
        ("申请人", (req or {}).get("requestingAgentId") or "-"),
        ("目标", proposal.get("goal") or "-"),
        ("期望结果", proposal.get("expectedOutcome") or "-"),
        ("紧急度", (req or {}).get("urgency") or "-"),
    ]

def _send_meeting_request_notification(req, state="pending", *, summary="", actions=None, details=None):
    if not isinstance(req, dict):
        return {"ok": True, "status": "skipped_invalid_request"}
    notifications_cfg = VO_CONFIG.get("notifications", {}) or {}
    configured_status_dir = ((VO_CONFIG.get("presence") or {}).get("statusDir") or "")
    if configured_status_dir and os.path.realpath(str(STATUS_DIR)) != os.path.realpath(str(configured_status_dir)):
        local_config_path = os.path.join(STATUS_DIR, "vo-config.json")
        if not os.path.isfile(local_config_path):
            notifications_cfg = {}
    proposal = req.get("originalProposal") if isinstance(req.get("originalProposal"), dict) else {}
    title_prefix = {
        "pending": "会议申请待处理",
        "approved": "会议申请已同意",
        "rejected": "会议申请已拒绝",
        "processing": "会议申请处理中",
        "cancelled": "会议申请已取消",
        "expired": "会议申请已过期",
        "no_longer_actionable": "会议申请不再可处理",
    }.get(state, "会议申请通知")
    intent = {
        "id": f"meeting-request:{req.get('id')}:{state}",
        "type": "application_form",
        "title": f"{title_prefix}: {proposal.get('topic') or req.get('id')}",
        "summary": summary or proposal.get("purpose") or proposal.get("goal") or "会议申请状态已更新。",
        "state": state,
        "multi_participant": False,
        "related": _meeting_request_notification_related(req),
        "details": details if details is not None else _meeting_request_notification_details(req),
        "actions": actions if actions is not None else [
            {
                "category": "confirm",
                "text": "同意",
                "value": {"action": "confirm_meeting_request", "request_id": req.get("id")},
            },
            {
                "category": "cancel",
                "text": "拒绝",
                "value": {"action": "reject_meeting_request", "request_id": req.get("id")},
            },
            {
                "category": "jump",
                "text": "查看详情",
                "url": _vo_public_url("/#projects"),
            },
        ],
        "target": "feishu-meeting-request",
    }
    return send_feishu_notification(
        intent,
        webhook_url=notifications_cfg.get("feishuWebhook") or None,
        app_config=_feishu_app_send_config(notifications_cfg),
        status_dir=STATUS_DIR,
    )

def _meeting_request_approved_notification_details(req):
    details = _meeting_request_notification_details(req)
    review = req.get("review") if isinstance(req.get("review"), dict) else {}
    if review.get("autoConfirmed"):
        details.append(("同意方式", "AI 自动同意"))
        label = review.get("autoConfirmLabel") or _meeting_request_auto_confirm_label(review.get("autoConfirmReason"))
        if label:
            details.append(("自动同意原因", label))
    return details

def _meeting_open_url(meeting_id):
    meeting_id = urllib.parse.quote(str(meeting_id or ""))
    return _vo_public_url(f"/#meeting={meeting_id}" if meeting_id else "/#meetings")

def _handle_meeting_request_create(project_id, task_id, body):
    project, task = _meeting_request_find_project_task(project_id, task_id)
    if not project:
        return _meeting_request_error("Project not found", 404, "project_not_found")
    if not task:
        return _meeting_request_error("Task not found", 404, "task_not_found")
    source_type = str(body.get("sourceType") or "project_task").strip()
    if source_type != "project_task":
        return _meeting_request_error("Only project_task meeting requests are supported in this phase", 400, "unsupported_source")
    goal = str(body.get("goal") or body.get("meetingGoal") or "").strip()
    expected = str(body.get("expectedOutcome") or "").strip()
    reason = str(body.get("reason") or body.get("cannotCompleteAloneReason") or "").strip()
    if not goal:
        return _meeting_request_error("Meeting goal is required", 400, "goal_required")
    if not expected:
        return _meeting_request_error("Expected outcome is required", 400, "expected_outcome_required")
    if not reason:
        return _meeting_request_error("Reason why the AI cannot complete alone is required", 400, "reason_required")
    requester = str(body.get("requestingAgentId") or body.get("agentId") or task.get("executorAgentId") or task.get("assignee") or "").strip()
    if not requester:
        return _meeting_request_error("Requesting agent is required", 400, "requesting_agent_required")
    urgency = _meeting_request_urgency(body.get("urgency") or body.get("urgencyScore") or body.get("priority"))
    participants = _exec_meeting_clean_participants(body.get("suggestedParticipants") or body.get("participants") or [])
    if requester and requester not in participants:
        participants.insert(0, requester)
    blocked_participants = _exec_meeting_archive_manager_participants(participants)
    if blocked_participants:
        return _exec_meeting_archive_manager_error(blocked_participants)
    suggested_moderator = str(body.get("suggestedModerator") or body.get("moderator") or (participants[0] if participants else requester)).strip()
    if _is_archive_manager_agent(suggested_moderator):
        return _exec_meeting_archive_manager_error([suggested_moderator])
    now = _exec_meeting_now()
    request_id = str(body.get("id") or uuid.uuid4())
    idempotency_key = str(body.get("idempotencyKey") or "").strip()
    requested_context_ids = body.get("selectedContextIds") or body.get("contextIds") or []
    requested_supplemental_context = str(body.get("supplementalContext") or "").strip()
    with _MEETING_REQUEST_LOCK:
        store = _load_meeting_request_store()
        existing_unresolved = next((r for r in store.get("requests", {}).values() if _meeting_request_unresolved_for_task(r, project_id, task_id)), None)
        if existing_unresolved:
            return {"ok": True, "request": _meeting_request_public(existing_unresolved), "existingBlockingRequest": True, "idempotent": True}
        if idempotency_key and idempotency_key in store.get("idempotency", {}):
            existing = store.get("requests", {}).get(store["idempotency"][idempotency_key].get("requestId"))
            if existing:
                return {"ok": True, "request": _meeting_request_public(existing), "idempotent": True}
        request = {
            "id": request_id,
            "status": "pending",
            "sourceType": "project_task",
            "source": {"projectId": project_id, "taskId": task_id, "projectTitle": project.get("title", ""), "taskTitle": task.get("title", "")},
            "requestingAgentId": requester,
            "originalProposal": {
                "topic": str(body.get("topic") or task.get("title") or goal).strip(),
                "purpose": str(body.get("purpose") or goal).strip(),
                "meetingType": _meeting_request_clean_type(body.get("meetingType")),
                "goal": goal,
                "expectedOutcome": expected,
                "cannotCompleteAloneReason": reason,
                "suggestedParticipants": participants,
                "suggestedModerator": suggested_moderator,
                "maxRounds": body.get("maxRounds") or 2,
                "urgency": urgency,
            },
            "urgency": urgency,
            "blockingTask": True,
            "taskBlocker": {"status": "pending", "createdAt": now, "updatedAt": now, "resolvedAt": ""},
            "contextCandidates": _meeting_request_context_candidates(project, task),
            "requestedContext": {
                "selectedContextIds": list(requested_context_ids),
                "supplementalContext": requested_supplemental_context,
            },
            "review": {},
            "conversion": {},
            "idempotencyKey": idempotency_key,
            "createdAt": now,
            "updatedAt": now,
        }
        store.setdefault("requests", {})[request_id] = request
        if idempotency_key:
            store.setdefault("idempotency", {})[idempotency_key] = {"requestId": request_id}
        _save_meeting_request_store(store)
    blocked = _project_execution_block_for_meeting_request(project_id, task_id, request, "AI meeting requested; waiting for meeting resolution.")
    if not blocked.get("ok"):
        return blocked
    auto_confirm_reason = _meeting_request_auto_confirm_reason(project, urgency)
    if auto_confirm_reason:
        auto = _handle_meeting_request_confirm(request_id, {
            "confirmedBy": f"agent:{requester}",
            "autoConfirmed": True,
            "autoConfirmReason": auto_confirm_reason,
            "selectedContextIds": requested_context_ids,
            "supplementalContext": requested_supplemental_context,
            "idempotencyKey": f"meeting-request-auto:{request_id}",
        })
        if auto.get("ok"):
            auto["autoConfirmed"] = True
            return auto
        notification = _send_meeting_request_notification(request, "pending")
        return {"ok": True, "request": _meeting_request_public(request), "autoConfirmError": auto, "notification": notification}
    notification = _send_meeting_request_notification(request, "pending")
    return {"ok": True, "request": _meeting_request_public(request), "notification": notification}

def _meeting_request_list_filtered(query_string=""):
    parsed = urllib.parse.parse_qs(query_string or "")
    status_filter = (parsed.get("status") or [""])[0]
    project_id = (parsed.get("projectId") or [""])[0]
    task_id = (parsed.get("taskId") or [""])[0]
    with _MEETING_REQUEST_LOCK:
        store = _load_meeting_request_store()
        requests = list(store.get("requests", {}).values())
    if status_filter:
        requests = [r for r in requests if r.get("status") == status_filter]
    if project_id:
        requests = [r for r in requests if (r.get("source") or {}).get("projectId") == project_id]
    if task_id:
        requests = [r for r in requests if (r.get("source") or {}).get("taskId") == task_id]
    requests = _sort_meeting_requests(requests)
    return {"ok": True, "requests": [_meeting_request_public(r) for r in requests], "pendingCount": sum(1 for r in requests if r.get("status") == "pending")}

def _handle_meeting_request_detail(request_id):
    with _MEETING_REQUEST_LOCK:
        req = _load_meeting_request_store().get("requests", {}).get(request_id)
    if not req:
        return _meeting_request_error("Meeting request not found", 404, "request_not_found")
    return {"ok": True, "request": _meeting_request_public(req)}

def _meeting_request_selected_context(req, selected_ids, supplemental_context):
    selected = set(str(x) for x in (selected_ids or []))
    pieces = []
    selected_candidates = []
    for candidate in req.get("contextCandidates", []):
        if str(candidate.get("id")) not in selected:
            continue
        item = dict(candidate)
        item["selected"] = True
        selected_candidates.append(item)
        title = item.get("title") or item.get("sourceKind") or "Context"
        summary = item.get("summary") or ""
        pieces.append(f"[{item.get('sourceKind')}] {title}\n{summary}".strip())
    supplemental = str(supplemental_context or "").strip()
    if supplemental:
        pieces.append("[supplemental]\n" + supplemental)
    return "\n\n".join([p for p in pieces if p]), selected_candidates

def _meeting_project_ref(project_id):
    project_id = str(project_id or "").strip()
    if not project_id:
        return {"ok": True, "projectId": "", "projectTitle": ""}
    data = _load_projects()
    project = next((p for p in data.get("projects", []) if p.get("id") == project_id), None)
    if not project:
        return {"ok": False, "error": "Project not found", "code": "project_not_found", "_status": 404}
    return {"ok": True, "projectId": project_id, "projectTitle": project.get("title", "")}

def _handle_meeting_request_confirm(request_id, body):
    idempotency_key = str(body.get("idempotencyKey") or "").strip()
    with _MEETING_REQUEST_LOCK:
        store = _load_meeting_request_store()
        req = store.get("requests", {}).get(request_id)
        if not req:
            return _meeting_request_error("Meeting request not found", 404, "request_not_found")
        if req.get("status") == "rejected":
            return _meeting_request_error("Rejected meeting request cannot be confirmed", 409, "request_rejected")
        if req.get("status") == "confirmed" and (req.get("conversion") or {}).get("meetingId"):
            if (req.get("review") or {}).get("autoConfirmed") and body.get("confirmedBy") and not body.get("autoConfirmed"):
                now = _exec_meeting_now()
                req["review"] = {
                    **(req.get("review") or {}),
                    "confirmedBy": str(body.get("confirmedBy") or "user"),
                    "confirmedAt": now,
                    "autoConfirmed": False,
                    "autoConfirmReason": "",
                    "autoConfirmLabel": "",
                    "humanOverrideAutoConfirmed": True,
                }
                req["updatedAt"] = now
                _save_meeting_request_store(store)
                return {"ok": True, "request": _meeting_request_public(req), "meetingId": req["conversion"]["meetingId"], "idempotent": False, "humanOverride": True}
            return {"ok": True, "request": _meeting_request_public(req), "meetingId": req["conversion"]["meetingId"], "idempotent": True}
        proposal = req.get("originalProposal") or {}
        selected_ids = body.get("selectedContextIds") or body.get("contextIds") or []
        context, selected_candidates = _meeting_request_selected_context(req, selected_ids, body.get("supplementalContext"))
        final_config = {
            "topic": str(body.get("topic") or proposal.get("topic") or "").strip(),
            "purpose": str(body.get("purpose") or proposal.get("purpose") or proposal.get("goal") or "").strip(),
            "meetingType": _meeting_request_clean_type(body.get("meetingType") or proposal.get("meetingType")),
            "participants": _exec_meeting_clean_participants(body.get("participants") or proposal.get("suggestedParticipants") or []),
            "moderator": str(body.get("moderator") or proposal.get("suggestedModerator") or "").strip(),
            "maxRounds": body.get("maxRounds") or proposal.get("maxRounds") or 2,
            "contextMode": body.get("contextMode") or "incremental",
            "resolutionPolicy": body.get("resolutionPolicy") or "moderator_decision",
            "context": context,
            "selectedContextIds": list(selected_ids),
            "selectedContextSnapshot": selected_candidates,
            "supplementalContext": str(body.get("supplementalContext") or "").strip(),
            "projectId": str(body.get("projectId") or (req.get("source") or {}).get("projectId") or "").strip(),
        }
        project_ref = _meeting_project_ref(final_config["projectId"])
        if not project_ref.get("ok"):
            return _meeting_request_error(project_ref.get("error") or "Project not found", project_ref.get("_status", 404), project_ref.get("code", "project_not_found"))
        final_config["projectId"], final_config["projectTitle"] = project_ref["projectId"], project_ref["projectTitle"]
        if final_config["moderator"] and final_config["moderator"] not in final_config["participants"]:
            final_config["participants"].insert(0, final_config["moderator"])
        blocked_participants = _exec_meeting_archive_manager_participants(final_config["participants"])
        if blocked_participants:
            return _exec_meeting_archive_manager_error(blocked_participants)
        edit_summary = []
        for key in ("topic", "purpose", "meetingType", "moderator", "maxRounds"):
            original = proposal.get(key if key != "moderator" else "suggestedModerator")
            if str(final_config.get(key) or "") != str(original or ""):
                edit_summary.append(key)
        req["review"] = {
            "finalConfig": final_config,
            "selectedContextIds": list(selected_ids),
            "supplementalContext": final_config["supplementalContext"],
            "editSummary": ", ".join(edit_summary) if edit_summary else "No configuration edits",
            "confirmedBy": str(body.get("confirmedBy") or "user"),
            "confirmedAt": _exec_meeting_now(),
            "autoConfirmed": bool(body.get("autoConfirmed")),
            "autoConfirmReason": str(body.get("autoConfirmReason") or ""),
            "autoConfirmLabel": _meeting_request_auto_confirm_label(body.get("autoConfirmReason")) if body.get("autoConfirmed") else "",
        }
        # Save review before conversion so a failure can be inspected/retried.
        req["updatedAt"] = req["review"]["confirmedAt"]
        _save_meeting_request_store(store)
    meeting_body = {
        "topic": final_config["topic"],
        "purpose": final_config["purpose"],
        "meetingType": final_config["meetingType"],
        "participants": final_config["participants"],
        "moderator": final_config["moderator"] or (final_config["participants"][0] if final_config["participants"] else ""),
        "maxRounds": final_config["maxRounds"],
        "context": final_config["context"],
        "contextMode": final_config["contextMode"],
        "resolutionPolicy": final_config["resolutionPolicy"],
        "organizer": req.get("requestingAgentId") or "ai",
        "createdBy": req.get("requestingAgentId") if body.get("autoConfirmed") else "user",
        "createdByType": "agent" if body.get("autoConfirmed") else "user",
        "createdByAgentId": req.get("requestingAgentId") if body.get("autoConfirmed") else "",
        "idempotencyKey": idempotency_key or f"meeting-request-confirm:{request_id}",
        "source": {
            "meetingRequestId": request_id,
            "requestingAgentId": req.get("requestingAgentId"),
            "urgency": req.get("urgency"),
            "autoConfirmed": bool(body.get("autoConfirmed")),
            "autoConfirmReason": str(body.get("autoConfirmReason") or ""),
            "autoConfirmLabel": _meeting_request_auto_confirm_label(body.get("autoConfirmReason")) if body.get("autoConfirmed") else "",
            **(req.get("source") or {}),
        },
        "projectId": final_config.get("projectId") or "",
    }
    created = _handle_executable_meeting_create(meeting_body)
    if not created.get("ok"):
        return created
    converted_at = _exec_meeting_now()
    confirmed_req = None
    with _MEETING_REQUEST_LOCK:
        store = _load_meeting_request_store()
        req = store.get("requests", {}).get(request_id)
        if req:
            req["status"] = "confirmed"
            req["conversion"] = {"meetingId": created["meeting"]["id"], "convertedAt": converted_at}
            req["taskBlocker"] = {**(req.get("taskBlocker") or {}), "status": "confirmed", "meetingId": created["meeting"]["id"], "updatedAt": converted_at}
            req["updatedAt"] = converted_at
            _save_meeting_request_store(store)
            source = req.get("source") or {}
            _project_execution_update_meeting_blocker(source.get("projectId"), source.get("taskId"), req.get("id"), status="confirmed", meetingId=created["meeting"]["id"], awaitingUserDecision=False)
            if body.get("autoConfirmed"):
                _meeting_request_log_auto_confirm_activity(req, created["meeting"], body.get("autoConfirmReason"))
            confirmed_req = _meeting_request_public(req)
    approved_notification = None
    if confirmed_req:
        approved_notification = _send_meeting_request_notification(
            confirmed_req,
            "approved",
            summary=f"会议申请已同意，会议 ID：{created['meeting']['id']}",
            details=_meeting_request_approved_notification_details(confirmed_req),
            actions=[{
                "category": "jump",
                "text": "查看会议",
                "url": _meeting_open_url(created["meeting"]["id"]),
            }],
        )
    auto_run_result = None
    auto_run_summary = {}
    if body.get("autoConfirmed"):
        auto_run_result = _handle_executable_meeting_run(created["meeting"]["id"], {
            "action": "auto_start",
            "actorId": req.get("requestingAgentId") or "agent",
            "actorType": "agent",
        })
        auto_run_summary = {
            "attempted": True,
            "startedAt": _exec_meeting_now(),
            "ok": bool(auto_run_result.get("ok")) if isinstance(auto_run_result, dict) else False,
            "stage": ((auto_run_result or {}).get("meeting") or {}).get("stage") if isinstance(auto_run_result, dict) else "",
            "error": (auto_run_result or {}).get("error") if isinstance(auto_run_result, dict) else "Auto run failed",
        }
        if isinstance(auto_run_result, dict) and auto_run_result.get("meeting"):
            created["meeting"] = auto_run_result["meeting"]
    with _MEETING_REQUEST_LOCK:
        store = _load_meeting_request_store()
        req = store.get("requests", {}).get(request_id)
        if req:
            req["conversion"] = req.get("conversion") or {"meetingId": created["meeting"]["id"], "convertedAt": converted_at}
            if auto_run_summary:
                req["conversion"]["autoRun"] = auto_run_summary
            req["updatedAt"] = _exec_meeting_now()
            _save_meeting_request_store(store)
            result = {"ok": True, "request": _meeting_request_public(req), "meeting": created["meeting"], "meetingId": created["meeting"]["id"], "idempotent": bool(created.get("idempotent"))}
            if auto_run_summary:
                result["autoRun"] = auto_run_summary
            result["notification"] = approved_notification
            return result
    result = {"ok": True, "meeting": created["meeting"], "meetingId": created["meeting"]["id"]}
    if auto_run_summary:
        result["autoRun"] = auto_run_summary
    result["notification"] = approved_notification or _send_meeting_request_notification(
        req,
        "approved",
        summary=f"会议申请已同意，会议 ID：{created['meeting']['id']}",
        details=_meeting_request_approved_notification_details(req),
        actions=[{
            "category": "jump",
            "text": "查看会议",
            "url": _meeting_open_url(created["meeting"]["id"]),
        }],
    )
    return result

def _handle_meeting_request_reject(request_id, body):
    reason = str(body.get("reason") or "").strip()
    if not reason:
        return _meeting_request_error("Rejection reason is required", 400, "reason_required")
    with _MEETING_REQUEST_LOCK:
        store = _load_meeting_request_store()
        req = store.get("requests", {}).get(request_id)
        if not req:
            return _meeting_request_error("Meeting request not found", 404, "request_not_found")
        if req.get("status") == "confirmed" and not (req.get("review") or {}).get("autoConfirmed"):
            return _meeting_request_error("Confirmed meeting request cannot be rejected", 409, "request_confirmed")
        if req.get("status") == "rejected":
            return {"ok": True, "request": _meeting_request_public(req), "idempotent": True}
        now = _exec_meeting_now()
        req["status"] = "rejected"
        req["review"] = {"rejectedBy": str(body.get("rejectedBy") or "user"), "rejectedAt": now, "rejectionReason": reason}
        req["taskBlocker"] = {**(req.get("taskBlocker") or {}), "status": "rejected", "rejectionReason": reason, "updatedAt": now}
        req["updatedAt"] = now
        _save_meeting_request_store(store)
    source = req.get("source") or {}
    _project_execution_update_meeting_blocker(source.get("projectId"), source.get("taskId"), req.get("id"), status="rejected", rejectionReason=reason, awaitingUserDecision=True)
    (_server_callable("_handle_task_comment") or _handle_task_comment)(source.get("projectId", ""), source.get("taskId", ""), {
        "author": "meeting-request",
        "text": f"AI meeting request rejected: {reason}",
    })
    notification = _send_meeting_request_notification(
        req,
        "rejected",
        summary=f"会议申请已拒绝：{reason}",
        actions=[],
        details=_meeting_request_notification_details(req) + [("拒绝原因", reason)],
    )
    return {"ok": True, "request": _meeting_request_public(req), "notification": notification}

def _exec_meeting_clean_participants(raw):
    if not isinstance(raw, list):
        return []
    result = []
    seen = set()
    for item in raw:
        participant = str(item or "").strip()
        if participant and participant not in seen:
            seen.add(participant)
            result.append(participant)
    return result

def _exec_meeting_archive_manager_participants(participants):
    return [p for p in (participants or []) if _is_archive_manager_agent(p)]

def _exec_meeting_archive_manager_error(blocked):
    return {
        "error": "档案管理员是系统档案角色，不能作为普通会议参与者；请在档案室进行归档维护。",
        "code": "archive_manager_not_meeting_participant",
        "blockedParticipants": blocked,
        "_status": 400,
    }

def _meeting_context_mode(raw):
    mode = str(raw or "incremental").strip().lower()
    return mode if mode in _MEETING_CONTEXT_MODES else "incremental"

def _meeting_resolution_policy(raw):
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

def _meeting_context_budget(raw):
    budget = dict(_MEETING_DEFAULT_CONTEXT_BUDGET)
    if isinstance(raw, dict):
        for key in budget:
            try:
                value = int(raw.get(key))
            except (TypeError, ValueError):
                continue
            if value > 0:
                budget[key] = min(value, 50000)
    return budget

def _meeting_decision_window_sec():
    return _meeting_clamped_decision_window_sec(os.environ.get("VO_MEETING_DECISION_WINDOW_SEC") or "20")

def _meeting_clamped_decision_window_sec(raw):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 20
    return max(10, min(value, 120))

def _meeting_truncate_text(value, limit):
    text = str(value or "")
    limit = max(0, int(limit or 0))
    if limit and len(text) > limit:
        return text[:limit] + "\n[truncated]"
    return text

def _exec_meeting_next_seq(store, meeting_id):
    events = store.setdefault("events", {}).setdefault(meeting_id, [])
    return (events[-1].get("sequence") or 0) + 1 if events else 1

def _append_exec_meeting_event(store, meeting, event_type, actor=None, payload=None, idempotency_key=None):
    meeting_id = meeting["id"]
    seq = _exec_meeting_next_seq(store, meeting_id)
    event = {
        "id": str(uuid.uuid4()),
        "meetingId": meeting_id,
        "sequence": seq,
        "version": meeting.get("version", 0) + 1,
        "type": event_type,
        "actor": actor or {"type": "system", "id": "system"},
        "stage": meeting.get("stage"),
        "round": meeting.get("round", 0),
        "payload": payload or {},
        "idempotencyKey": idempotency_key or "",
        "createdAt": _exec_meeting_now(),
    }
    store.setdefault("events", {}).setdefault(meeting_id, []).append(event)
    meeting["version"] = event["version"]
    meeting["lastEventSequence"] = seq
    meeting["updatedAt"] = event["createdAt"]
    return event

def _meeting_mark_preparing_started(meeting, now=None):
    if isinstance(meeting, dict) and meeting.get("stage") == "preparing":
        meeting["preparingStartedAt"] = now or _exec_meeting_now()

def _release_timed_out_preparing_meetings(store, now=None):
    now_dt = now if isinstance(now, datetime) else datetime.now(timezone.utc)
    now_ts = now_dt.timestamp()
    now_iso = now_dt.isoformat()
    timeout_sec = _meeting_preparing_timeout_sec()
    released = []
    for meeting in list((store.get("meetings") or {}).values()):
        if not isinstance(meeting, dict) or meeting.get("stage") != "preparing":
            continue
        if meeting.get("cancelReason") == "preparing_timeout":
            continue
        started_at = meeting.get("preparingStartedAt") or meeting.get("createdAt") or meeting.get("updatedAt")
        started_ts = _exec_meeting_parse_ts(started_at)
        if not started_ts or now_ts - started_ts < timeout_sec:
            continue
        meeting_id = meeting.get("id")
        previous = meeting.get("stage")
        meeting["previousStage"] = previous
        meeting["stage"] = "cancelled"
        meeting["currentSpeaker"] = ""
        meeting["cancelReason"] = "preparing_timeout"
        meeting["timedOutAt"] = now_iso
        meeting["preparingTimeoutSec"] = timeout_sec
        meeting["preparingTimedOutFrom"] = started_at
        released_agents = []
        for participant in meeting.get("participants") or []:
            if store.setdefault("occupancy", {}).get(participant) == meeting_id:
                store["occupancy"].pop(participant, None)
                released_agents.append(participant)
        _append_exec_meeting_event(
            store,
            meeting,
            "meeting_preparing_timed_out",
            actor={"type": "system", "id": "system"},
            payload={
                "from": previous,
                "to": "cancelled",
                "reason": "preparing_timeout",
                "timeoutSec": timeout_sec,
                "startedAt": started_at,
                "timedOutAt": now_iso,
                "releasedParticipants": released_agents,
            },
            idempotency_key=f"{meeting_id}:preparing-timeout",
        )
        released.append(meeting_id)
    return released

def _meeting_formal_turn_exists(events, stage, round_value, speaker):
    for event in events or []:
        if event.get("type") != "participant_turn":
            continue
        payload = event.get("payload") or {}
        if payload.get("kind") in {"targeted_response", "meeting_result"} or payload.get("purpose") == "meeting_result":
            continue
        if payload.get("stage") == stage and int(payload.get("round") or 0) == int(round_value or 0) and payload.get("speaker") == speaker:
            return True
    return False

def _meeting_pending_formal_turn_exists(events, stage, round_value, speaker):
    for call in _exec_meeting_pending_calls_projection(events or []):
        if call.get("purpose"):
            continue
        if call.get("stage") == stage and int(call.get("round") or 0) == int(round_value or 0) and call.get("speaker") == speaker:
            return True
    return False

def _meeting_provider_completion_should_be_ignored(meeting, expected_stage, expected_round):
    current_stage = meeting.get("stage")
    if current_stage in _EXEC_MEETING_TERMINAL or current_stage == "paused":
        return True
    if expected_stage and current_stage not in {expected_stage, "awaiting_user_decision"}:
        return True
    if expected_round is not None and int(meeting.get("round") or 0) != int(expected_round or 0):
        return True
    return False

def _meeting_project_work_map():
    active_phases = {"in_progress", "dispatching", "reviewing", "rework"}
    work = {}
    with _WORKFLOW_LOCK:
        for project_id, wf in _WORKFLOW_STATE.items():
            if not wf.get("active") or wf.get("phase") not in active_phases:
                continue
            agent_id = str(wf.get("currentAssignee") or "").strip()
            if not agent_id:
                continue
            work[agent_id] = {
                "kind": "project_task",
                "projectId": project_id,
                "taskId": wf.get("currentTaskId") or "",
                "taskTitle": wf.get("currentTaskTitle") or "Project task",
                "phase": wf.get("phase") or "",
                "riskLevel": "high" if wf.get("phase") in {"dispatching", "reviewing", "rework"} else "medium",
                "pauseCapability": "logical",
                "summary": wf.get("currentTaskTitle") or "Project task",
            }
    try:
        if os.path.isfile(WORKFLOW_STATE_FILE):
            with open(WORKFLOW_STATE_FILE, "r", encoding="utf-8") as f:
                persisted = json.load(f)
            for project_id, wf in (persisted or {}).items():
                if not isinstance(wf, dict) or not wf.get("active") or wf.get("phase") not in active_phases:
                    continue
                agent_id = str(wf.get("currentAssignee") or "").strip()
                if agent_id and agent_id not in work:
                    work[agent_id] = {
                        "kind": "project_task",
                        "projectId": project_id,
                        "taskId": wf.get("currentTaskId") or "",
                        "taskTitle": wf.get("currentTaskTitle") or "Project task",
                        "phase": wf.get("phase") or "",
                        "riskLevel": "high" if wf.get("phase") in {"dispatching", "reviewing", "rework"} else "medium",
                        "pauseCapability": "logical",
                        "summary": wf.get("currentTaskTitle") or "Project task",
                    }
    except Exception:
        pass
    return work

def _meeting_pending_provider_agents(store):
    pending = {}
    for meeting_id, events in store.get("events", {}).items():
        meeting = store.get("meetings", {}).get(meeting_id) or {}
        if meeting.get("stage") in _EXEC_MEETING_TERMINAL:
            continue
        for call in _exec_meeting_pending_calls_projection(events):
            speaker = call.get("speaker") or ""
            if speaker:
                pending[speaker] = {"kind": "provider_call", "meetingId": meeting_id, "riskLevel": "high", "summary": "Provider call in progress"}
    return pending

def _meeting_busy_context_for_agent(store, agent_id, exclude_meeting_id=""):
    agent_id = str(agent_id or "").strip()
    if not agent_id:
        return {"agentId": agent_id, "busy": False, "riskLevel": "idle", "reason": "idle"}
    occupied_by = (store.get("occupancy") or {}).get(agent_id)
    if occupied_by and occupied_by != exclude_meeting_id:
        meeting = (store.get("meetings") or {}).get(occupied_by) or {}
        return {
            "agentId": agent_id,
            "busy": True,
            "riskLevel": "high",
            "reason": "meeting_occupied",
            "busyKind": "meeting",
            "meetingId": occupied_by,
            "summary": f"Already in meeting: {meeting.get('topic') or occupied_by}",
            "pauseCapability": "unavailable",
        }
    pending = _meeting_pending_provider_agents(store).get(agent_id)
    if pending:
        return {
            "agentId": agent_id,
            "busy": True,
            "riskLevel": "high",
            "reason": "provider_call",
            "busyKind": "provider_call",
            "meetingId": pending.get("meetingId"),
            "summary": pending.get("summary") or "Provider call in progress",
            "pauseCapability": "unavailable",
        }
    work = _meeting_project_work_map().get(agent_id)
    if work:
        return {
            "agentId": agent_id,
            "busy": True,
            "riskLevel": work.get("riskLevel") or "medium",
            "reason": "project_task",
            "busyKind": "project_task",
            "projectId": work.get("projectId") or "",
            "taskId": work.get("taskId") or "",
            "taskTitle": work.get("taskTitle") or "",
            "phase": work.get("phase") or "",
            "summary": work.get("summary") or work.get("taskTitle") or "Project task",
            "estimatedAvailability": "unknown",
            "pauseCapability": work.get("pauseCapability") or "logical",
        }
    return {"agentId": agent_id, "busy": False, "riskLevel": "idle", "reason": "idle", "summary": "Idle", "pauseCapability": "none"}

def _meeting_conflict_advisory(conflict):
    agent_id = conflict.get("agentId") or ""
    reason = conflict.get("reason") or "busy"
    summary = conflict.get("summary") or "The agent is busy."
    pause = conflict.get("pauseCapability") or "logical"
    if reason == "meeting_occupied":
        recommendation = "replace"
        risk = "Agent is already in another active meeting. Do not force join unless the existing meeting is cancelled."
        resume = "No original task can be resumed from this meeting conflict."
    elif reason == "provider_call":
        recommendation = "wait"
        risk = "A provider call is in progress. Interrupting can lose an in-flight response."
        resume = "Wait for the provider call to finish, then retry conflict handling."
    elif pause == "logical":
        recommendation = "wait"
        risk = "The current task can only be logically paused; the provider process may not stop immediately."
        resume = "Save current task context and resume from the recorded task state after the meeting."
    else:
        recommendation = "wait"
        risk = "Pause safety is uncertain."
        resume = "Recheck the agent state before forcing a meeting."
    return {
        "status": "completed",
        "agentId": agent_id,
        "recommendation": recommendation,
        "busyReason": summary,
        "estimatedAvailability": conflict.get("estimatedAvailability") or "unknown",
        "interruptionRisk": risk,
        "resumeNotes": resume,
        "source": "local_fallback",
        "createdAt": _exec_meeting_now(),
    }

def _meeting_advisory_timeout():
    raw = os.environ.get("VO_MEETING_ADVISORY_TIMEOUT_SEC") or "45"
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 45
    return max(5, min(value, 180))

def _meeting_live_advisory_prompt(meeting, conflict):
    source = conflict.get("source") if isinstance(conflict.get("source"), dict) else {}
    occupied_meeting = ""
    if source.get("meetingId"):
        occupied_meeting = str(source.get("meetingId") or "")
    return (
        "你是 Virtual Office 的 busy-agent subagent advisory turn。"
        "现在有人想邀请你参加另一场 AI 会议，但系统检测到你正在忙。"
        "请只评估你自己的可用性和打断风险，不要替用户执行等待、更换或强制加入。\n\n"
        f"待加入会议: {meeting.get('topic') or meeting.get('agenda') or meeting.get('id')}\n"
        f"当前冲突原因: {conflict.get('reason') or conflict.get('busyKind')}\n"
        f"当前忙碌摘要: {conflict.get('summary') or ''}\n"
        f"已占用会议ID: {occupied_meeting}\n"
        f"暂停能力: {conflict.get('pauseCapability') or 'unknown'}\n"
        f"风险级别: {conflict.get('riskLevel') or 'medium'}\n\n"
        "返回且只返回一个 JSON 对象，不要 Markdown，不要额外说明。"
        "Schema: {"
        "\"recommendation\":\"wait|reserve|replace|force_join\","
        "\"estimatedAvailability\":\"例如 2-5 分钟、当前会议结束后、unknown\","
        "\"busyReason\":\"用中文简述你为什么忙\","
        "\"interruptionRisk\":\"用中文说明打断风险\","
        "\"resumeNotes\":\"用中文说明如果被打断如何恢复或为什么不能恢复\","
        "\"confidence\":\"high|medium|low\""
        "}。"
    )

def _meeting_call_advisory_provider(meeting, conflict):
    agent_id = conflict.get("agentId") or ""
    prompt = _meeting_live_advisory_prompt(meeting, conflict)
    pseudo_meeting = {
        "id": f"{meeting.get('id')}:advisory:{agent_id}",
        "contextBudget": {"maxPromptChars": 6000},
    }
    old_timeout = os.environ.get("VO_MEETING_PROVIDER_TIMEOUT_SEC")
    os.environ["VO_MEETING_PROVIDER_TIMEOUT_SEC"] = str(_meeting_advisory_timeout())
    try:
        return (_server_callable("_meeting_call_provider") or _meeting_call_provider)(pseudo_meeting, agent_id, prompt)
    finally:
        if old_timeout is None:
            os.environ.pop("VO_MEETING_PROVIDER_TIMEOUT_SEC", None)
        else:
            os.environ["VO_MEETING_PROVIDER_TIMEOUT_SEC"] = old_timeout

def _meeting_normalize_advisory_reply(conflict, result):
    fallback = _meeting_conflict_advisory(conflict)
    fallback["source"] = "local_fallback_after_provider_failure"
    fallback["providerRef"] = result.get("providerRef") or {}
    fallback["durationMs"] = result.get("durationMs") or 0
    if not result.get("ok"):
        fallback["providerError"] = result.get("reply") or "advisory provider call failed"
        return fallback
    parsed = _meeting_parse_json_object(result.get("reply") or "")
    if not parsed:
        fallback["providerError"] = "advisory provider did not return JSON"
        fallback["rawText"] = _meeting_truncate_text(result.get("reply") or "", 1200)
        return fallback
    recommendation = str(parsed.get("recommendation") or fallback.get("recommendation") or "wait").strip().lower()
    if recommendation not in {"wait", "reserve", "replace", "force_join"}:
        recommendation = fallback.get("recommendation") or "wait"
    return {
        "status": "completed",
        "agentId": conflict.get("agentId") or "",
        "recommendation": recommendation,
        "busyReason": str(parsed.get("busyReason") or parsed.get("busy_reason") or fallback.get("busyReason") or "").strip(),
        "estimatedAvailability": str(parsed.get("estimatedAvailability") or parsed.get("estimated_availability") or fallback.get("estimatedAvailability") or "unknown").strip() or "unknown",
        "interruptionRisk": str(parsed.get("interruptionRisk") or parsed.get("interruption_risk") or fallback.get("interruptionRisk") or "").strip(),
        "resumeNotes": str(parsed.get("resumeNotes") or parsed.get("resume_notes") or fallback.get("resumeNotes") or "").strip(),
        "confidence": str(parsed.get("confidence") or "").strip(),
        "source": "agent_advisory_turn",
        "providerRef": result.get("providerRef") or {},
        "durationMs": result.get("durationMs") or 0,
        "createdAt": _exec_meeting_now(),
    }

def _meeting_complete_live_advisories(meeting_id):
    if os.environ.get("VO_MEETING_DISABLE_LIVE_ADVISORY"):
        return None
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        meeting = store.get("meetings", {}).get(meeting_id)
        if not meeting:
            return None
        pending = [
            dict(conflict)
            for conflict in (meeting.get("conflicts") or [])
            if conflict.get("riskLevel") in {"medium", "high"} and conflict.get("status") in {"open", "waiting", "reserved"}
        ]
    if not pending:
        return None
    for snapshot in pending:
        result = _meeting_call_advisory_provider(meeting, snapshot)
        advisory = _meeting_normalize_advisory_reply(snapshot, result)
        with _EXEC_MEETING_LOCK:
            store = _load_exec_meeting_store()
            meeting = store.get("meetings", {}).get(meeting_id)
            if not meeting or meeting.get("stage") in _EXEC_MEETING_TERMINAL:
                continue
            for conflict in meeting.get("conflicts") or []:
                if conflict.get("id") == snapshot.get("id"):
                    conflict["advisory"] = advisory
                    if advisory.get("estimatedAvailability"):
                        conflict["estimatedAvailability"] = advisory.get("estimatedAvailability")
                    if advisory.get("busyReason"):
                        conflict["summary"] = advisory.get("busyReason")
                    conflict["updatedAt"] = _exec_meeting_now()
                    _append_exec_meeting_event(store, meeting, "meeting_conflict_advisory", actor={"type": "agent", "id": conflict.get("agentId") or ""}, payload={"conflictId": conflict.get("id"), "agentId": conflict.get("agentId"), "advisory": advisory})
                    break
            _save_exec_meeting_store(store)
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        return store.get("meetings", {}).get(meeting_id)

def _meeting_build_conflicts(store, participants, exclude_meeting_id=""):
    conflicts = []
    for participant in participants:
        ctx = _meeting_busy_context_for_agent(store, participant, exclude_meeting_id=exclude_meeting_id)
        if not ctx.get("busy"):
            continue
        now = _exec_meeting_now()
        conflict = {
            "id": str(uuid.uuid4()),
            "agentId": participant,
            "status": "open",
            "reason": ctx.get("reason") or "busy",
            "busyKind": ctx.get("busyKind") or ctx.get("reason") or "busy",
            "riskLevel": ctx.get("riskLevel") or "medium",
            "summary": ctx.get("summary") or "",
            "estimatedAvailability": ctx.get("estimatedAvailability") or "unknown",
            "pauseCapability": ctx.get("pauseCapability") or "logical",
            "source": {k: v for k, v in ctx.items() if k in {"meetingId", "projectId", "taskId", "taskTitle", "phase"}},
            "createdAt": now,
            "updatedAt": now,
        }
        if conflict["riskLevel"] in {"medium", "high"}:
            conflict["advisory"] = _meeting_conflict_advisory(conflict)
        conflicts.append(conflict)
    return conflicts

def _meeting_has_open_conflicts(meeting):
    return any((c or {}).get("status") in {"open", "waiting", "reserved"} for c in meeting.get("conflicts") or [])

def _meeting_original_work_snapshot(conflict, action):
    pause_capability = conflict.get("pauseCapability") or "logical"
    return {
        "agentId": conflict.get("agentId") or "",
        "busyKind": conflict.get("busyKind") or conflict.get("reason") or "",
        "reason": conflict.get("reason") or "",
        "riskLevel": conflict.get("riskLevel") or "",
        "summary": conflict.get("summary") or "",
        "source": conflict.get("source") or {},
        "pauseCapability": pause_capability,
        "pauseState": "logical_paused" if pause_capability == "logical" else "pause_unavailable" if pause_capability == "unavailable" else "true_paused",
        "resolutionAction": action,
        "resumeToken": str(uuid.uuid4()),
        "resumeStatus": "pending",
        "capturedAt": _exec_meeting_now(),
        "resumeNotes": ((conflict.get("advisory") or {}).get("resumeNotes") or ""),
    }

def _meeting_resume_original_work(store, meeting, reason):
    snapshots = meeting.get("originalWork") or {}
    if not isinstance(snapshots, dict):
        snapshots = {}
    changed = False
    for agent_id, snap in snapshots.items():
        if not isinstance(snap, dict) or snap.get("resumeStatus") in {"resumed", "manual_required"}:
            continue
        if snap.get("pauseState") == "pause_unavailable":
            snap["resumeStatus"] = "manual_required"
            snap["resumeFailureReason"] = "Original work could not be paused reliably; manual recovery required."
            event_type = "original_work_resume_failed"
        else:
            snap["resumeStatus"] = "resumed"
            snap["resumedAt"] = _exec_meeting_now()
            event_type = "original_work_resumed"
        changed = True
        _append_exec_meeting_event(store, meeting, event_type, payload={"agentId": agent_id, "reason": reason, "snapshot": snap})
    if changed:
        meeting["originalWork"] = snapshots
    return changed

def _meeting_find_pending_call(events, sequence):
    try:
        wanted = int(sequence)
    except (TypeError, ValueError):
        return None
    for call in _exec_meeting_pending_calls_projection(events or []):
        if int(call.get("sequence") or 0) == wanted:
            return call
    return None

def _meeting_skip_timed_out_provider_call(store, meeting, pending_sequence):
    events = store.get("events", {}).get(meeting.get("id"), [])
    call = _meeting_find_pending_call(events, pending_sequence)
    if not call:
        return {"ok": True, "meeting": meeting, "skipped": False, "reason": "pending_not_found"}
    if not call.get("timedOut"):
        return {"error": "Provider call has not reached timeout", "pendingCall": call, "_status": 409}
    if call.get("purpose"):
        return {"error": "Only formal meeting turns can be skipped automatically", "pendingCall": call, "_status": 409}
    speaker = call.get("speaker") or ""
    stage = call.get("stage") or meeting.get("stage") or ""
    round_value = int(call.get("round") or meeting.get("round") or 0)
    if _meeting_formal_turn_exists(events, stage, round_value, speaker):
        return {"ok": True, "meeting": meeting, "skipped": False, "reason": "turn_already_recorded"}
    payload = {
        "speaker": speaker,
        "text": f"[TIMEOUT] Provider call exceeded {call.get('timeoutSec')}s and was skipped so the meeting can continue.",
        "rawText": "",
        "structured": {},
        "parseError": "provider_timeout_skipped",
        "ok": False,
        "stage": stage,
        "round": round_value,
        "providerRef": _meeting_provider_ref(speaker),
        "conversationId": f"meeting:{meeting.get('id')}:participant:{speaker}",
        "durationMs": int(call.get("elapsedSec") or 0) * 1000,
        "inReplyToSequence": call.get("sequence"),
        "timeoutSec": call.get("timeoutSec"),
        "elapsedSec": call.get("elapsedSec"),
        "skipReason": "provider_timeout",
    }
    event = _append_exec_meeting_event(store, meeting, "participant_turn", actor={"type": "agent", "id": speaker}, payload=payload)
    meeting.setdefault("participantLastSeen", {})[speaker] = event["sequence"]
    if meeting.get("currentSpeaker") == speaker:
        meeting["currentSpeaker"] = ""
    return {"ok": True, "meeting": meeting, "event": event, "skipped": True}

def _meeting_formal_round_complete(events, stage, round_value, participants):
    return all(_meeting_formal_turn_exists(events, stage, round_value, speaker) for speaker in (participants or []))

def _meeting_has_substantive_disagreement(value):
    text = str(value or "").strip()
    if not text:
        return False
    normalized = re.sub(r"[\s。.!！?？,，;；:：、\"'`]+", "", text.lower())
    if normalized in {"无", "没有", "暂无", "无分歧", "没有分歧", "无争议", "没有争议", "none", "no", "na", "n/a", "nil"}:
        return False
    false_prefixes = ("无新", "没有新", "暂无新", "nonew", "noadditional", "nofurther")
    if any(normalized.startswith(prefix) for prefix in false_prefixes):
        return False
    if normalized.startswith("无") and not any(marker in normalized for marker in ("不同意", "反对", "冲突", "争议", "分歧")):
        return False
    return True

def _meeting_arbitration_snapshot(meeting, events):
    positions = []
    disagreements = []
    latest_turns = {}
    for event in events or []:
        if event.get("type") != "participant_turn":
            continue
        payload = event.get("payload") or {}
        if payload.get("kind") == "targeted_response" or payload.get("purpose") == "meeting_result":
            continue
        speaker = payload.get("speaker") or (event.get("actor") or {}).get("id") or ""
        if speaker:
            latest_turns[speaker] = payload
    participant_order = list(meeting.get("participants") or [])
    ordered_payloads = []
    for speaker in participant_order:
        if speaker in latest_turns:
            ordered_payloads.append((speaker, latest_turns[speaker]))
    for speaker, payload in ordered_payloads:
        structured = payload.get("structured") or {}
        position = structured.get("position") or payload.get("text") or ""
        if speaker and position:
            positions.append({"speaker": speaker, "position": _meeting_truncate_text(position, 500)})
        for item in _meeting_coerce_list(structured.get("disagreements")):
            if _meeting_has_substantive_disagreement(item):
                disagreements.append(f"{speaker}: {item}" if speaker else item)
    suggestion = "用户裁决后结束，或继续一轮收敛分歧。"
    if not disagreements:
        return {}
    return {
        "reason": "no_consensus",
        "positions": positions[-len(meeting.get("participants") or []):],
        "disagreements": disagreements[-10:],
        "moderatorSuggestion": suggestion,
    }

def _meeting_open_decision_window(store, meeting, completed_stage, completed_round, next_stage, next_round, reason):
    timeout_sec = _meeting_clamped_decision_window_sec(meeting.get("decisionWindowConfiguredSec") or meeting.get("decisionWindowSec") or _meeting_decision_window_sec())
    now = time.time()
    events = list(store.get("events", {}).get(meeting.get("id"), []))
    arbitration = _meeting_arbitration_snapshot(meeting, events) if reason == "no_consensus" else {}
    if reason == "no_consensus" and not arbitration:
        reason = "round_complete"
    if reason == "no_consensus" and _meeting_resolution_policy(meeting.get("resolutionPolicy")) == "moderator_decision":
        reason = "round_complete"
    meeting["previousStage"] = completed_stage
    meeting["stage"] = "awaiting_user_decision"
    meeting["currentSpeaker"] = ""
    meeting["decisionForStage"] = completed_stage
    meeting["decisionForRound"] = int(completed_round or 0)
    meeting["decisionNextStage"] = next_stage
    meeting["decisionNextRound"] = int(next_round or 0)
    meeting["decisionWindowSec"] = timeout_sec
    meeting["decisionDeadlineAt"] = datetime.fromtimestamp(now + timeout_sec, timezone.utc).isoformat()
    if arbitration and reason == "no_consensus":
        meeting["arbitration"] = arbitration
    else:
        meeting.pop("arbitration", None)
    _append_exec_meeting_event(
        store,
        meeting,
        "decision_window_opened",
        payload={
            "completedStage": completed_stage,
            "completedRound": int(completed_round or 0),
            "nextStage": next_stage,
            "nextRound": int(next_round or 0),
            "timeoutSec": timeout_sec,
            "deadlineAt": meeting["decisionDeadlineAt"],
            "reason": reason,
            "arbitration": arbitration,
            "resolutionPolicy": _meeting_resolution_policy(meeting.get("resolutionPolicy")),
        },
    )
    _append_exec_meeting_event(store, meeting, "meeting_transitioned", payload={"from": completed_stage, "to": "awaiting_user_decision", "reason": reason})

def _meeting_continue_from_decision_window(store, meeting, actor=None, reason="continue"):
    if meeting.get("stage") != "awaiting_user_decision":
        return meeting.get("stage")
    previous = meeting.get("stage")
    next_stage = meeting.get("decisionNextStage") or "active_discussion"
    next_round = int(meeting.get("decisionNextRound") or meeting.get("round") or 0)
    meeting["previousStage"] = previous
    meeting["stage"] = next_stage
    if next_stage == "active_discussion" and next_round:
        meeting["round"] = next_round
    meeting["currentSpeaker"] = (meeting.get("speakerQueue") or [""])[0] if next_stage in {"active_opening", "active_discussion"} else ""
    for key in ("decisionForStage", "decisionForRound", "decisionNextStage", "decisionNextRound", "decisionDeadlineAt", "arbitration"):
        meeting.pop(key, None)
    _append_exec_meeting_event(store, meeting, "decision_window_closed", actor=actor, payload={"to": next_stage, "round": next_round, "reason": reason})
    _append_exec_meeting_event(store, meeting, "meeting_transitioned", actor=actor, payload={"from": previous, "to": next_stage, "reason": reason})
    return next_stage

def _rebuild_exec_meeting_occupancy(store):
    occupancy = {}
    forced = {}
    for meeting in store.get("meetings", {}).values():
        if meeting.get("stage") in _EXEC_MEETING_TERMINAL:
            continue
        participant_state = meeting.get("participantState") if isinstance(meeting.get("participantState"), dict) else {}
        for participant in meeting.get("participants", []):
            state = participant_state.get(participant) if isinstance(participant_state.get(participant), dict) else {}
            if state.get("forcedJoin"):
                forced[participant] = meeting.get("id")
                continue
            occupancy[participant] = meeting.get("id")
    occupancy.update(forced)
    store["occupancy"] = occupancy
    return occupancy

def _exec_meeting_pending_calls_projection(events):
    pending = {}
    now_ts = time.time()
    timeout_sec = _meeting_provider_timeout()
    for event in events or []:
        event_type = event.get("type")
        payload = event.get("payload") or {}
        if event_type == "provider_call_started":
            sequence = event.get("sequence")
            created_at = event.get("createdAt") or ""
            created_ts = _exec_meeting_parse_ts(created_at) or now_ts
            elapsed_sec = max(0, int(now_ts - created_ts))
            pending[sequence] = {
                "sequence": sequence,
                "stage": payload.get("stage") or event.get("stage") or "",
                "round": int(payload.get("round") or event.get("round") or 0),
                "speaker": payload.get("speaker") or (event.get("actor") or {}).get("id") or "",
                "purpose": payload.get("purpose") or "",
                "promptChars": int(payload.get("promptChars") or 0),
                "contextMode": payload.get("contextMode") or "",
                "createdAt": created_at,
                "elapsedSec": elapsed_sec,
                "timeoutSec": timeout_sec,
                "timedOut": elapsed_sec >= timeout_sec,
            }
        elif event_type == "participant_turn":
            in_reply_to = payload.get("inReplyToSequence")
            if in_reply_to in pending:
                pending.pop(in_reply_to, None)
    return list(pending.values())

def _meeting_normalize_action_item(raw, index, meeting):
    if isinstance(raw, dict):
        title = str(raw.get("title") or raw.get("item") or raw.get("text") or raw.get("task") or raw.get("action") or "").strip()
        description = str(raw.get("description") or raw.get("details") or raw.get("note") or "").strip()
        owner = str(raw.get("owner") or raw.get("assignee") or raw.get("responsible") or "").strip()
        status = str(raw.get("status") or raw.get("nextStatus") or "todo").strip() or "todo"
        source_text = str(raw.get("sourceText") or raw.get("source") or "").strip()
        priority = str(raw.get("priority") or "medium").strip() or "medium"
    else:
        title = str(raw or "").strip()
        description = ""
        owner = ""
        status = "todo"
        source_text = ""
        priority = "medium"
    if not title:
        title = f"Action item {index + 1}"
    return {
        "id": f"ai-{index + 1}",
        "title": title,
        "description": description,
        "suggestedOwner": owner,
        "assignee": owner,
        "suggestedStatus": status,
        "priority": priority,
        "sourceMeetingId": meeting.get("id"),
        "sourceText": source_text or title,
        "targetProjectId": meeting.get("projectId") or "",
        "status": "draft",
        "createdAt": _exec_meeting_now(),
        "updatedAt": _exec_meeting_now(),
        "audit": [],
    }

def _meeting_ensure_action_item_drafts(store, meeting):
    if not isinstance(meeting, dict):
        return []
    result = meeting.get("result") if isinstance(meeting.get("result"), dict) else {}
    raw_items = result.get("actionItems") if isinstance(result.get("actionItems"), list) else []
    existing = meeting.get("actionItemDrafts")
    if isinstance(existing, list) and existing:
        return existing
    drafts = [_meeting_normalize_action_item(item, idx, meeting) for idx, item in enumerate(raw_items)]
    meeting["actionItemDrafts"] = drafts
    if drafts:
        _append_exec_meeting_event(store, meeting, "action_item_drafts_created", actor={"type": "system", "id": "system"}, payload={"count": len(drafts), "projectId": meeting.get("projectId") or ""})
    return drafts

def _exec_meeting_project_active(meeting, events=None):
    participants = meeting.get("participants", [])
    return {
        "id": meeting.get("id"),
        "topic": meeting.get("topic", "Untitled Meeting"),
        "agenda": meeting.get("agenda") or meeting.get("topic", "Untitled Meeting"),
        "purpose": meeting.get("purpose", ""),
        "kind": meeting.get("meetingType", meeting.get("kind", "discussion")),
        "type": "group" if len(participants) > 2 else "1on1",
        "organizer": meeting.get("organizer", ""),
        "createdBy": meeting.get("createdBy", ""),
        "createdByType": meeting.get("createdByType", ""),
        "createdByAgentId": meeting.get("createdByAgentId", ""),
        "projectId": meeting.get("projectId", ""),
        "projectTitle": meeting.get("projectTitle", ""),
        "source": meeting.get("source") or {},
        "urgency": (meeting.get("source") or {}).get("urgency") or meeting.get("urgency"),
        "status": "active",
        "participants": participants,
        "agents": participants,
        "executableMeeting": True,
        "executionStage": meeting.get("stage"),
        "executionPreviousStage": meeting.get("previousStage", ""),
        "executionVersion": meeting.get("version", 0),
        "currentRound": meeting.get("round", 0),
        "maxRounds": meeting.get("maxRounds", 0),
        "moderator": meeting.get("moderator"),
        "contextMode": meeting.get("contextMode", "incremental"),
        "resolutionPolicy": _meeting_resolution_policy(meeting.get("resolutionPolicy")),
        "currentSpeaker": meeting.get("currentSpeaker", ""),
        "decisionForStage": meeting.get("decisionForStage", ""),
        "decisionForRound": meeting.get("decisionForRound", 0),
        "decisionNextStage": meeting.get("decisionNextStage", ""),
        "decisionNextRound": meeting.get("decisionNextRound", 0),
        "decisionWindowSec": meeting.get("decisionWindowSec", 0),
        "decisionDeadlineAt": meeting.get("decisionDeadlineAt", ""),
        "arbitration": meeting.get("arbitration") or {},
        "moderatorFailure": meeting.get("moderatorFailure") or {},
        "preparingStartedAt": meeting.get("preparingStartedAt") or "",
        "preparingTimeoutSec": meeting.get("preparingTimeoutSec") or _meeting_preparing_timeout_sec(),
        "cancelReason": meeting.get("cancelReason") or "",
        "timedOutAt": meeting.get("timedOutAt") or "",
        "result": meeting.get("result", {}),
        "actionItemDrafts": meeting.get("actionItemDrafts") or [],
        "lastEventSequence": meeting.get("lastEventSequence", 0),
        "transcript": _exec_meeting_transcript_projection(events or []),
        "pendingCalls": _exec_meeting_pending_calls_projection(events or []),
        "conflicts": meeting.get("conflicts") or [],
        "reservation": meeting.get("reservation") or {},
        "originalWork": meeting.get("originalWork") or {},
        "participantState": meeting.get("participantState") or {},
    }

def _exec_meeting_transcript_projection(events):
    transcript = []
    for event in events or []:
        payload = event.get("payload") or {}
        if event.get("type") == "participant_turn":
            transcript.append({
                "type": "participant_turn",
                "sequence": event.get("sequence"),
                "stage": payload.get("stage") or event.get("stage") or "",
                "round": int(payload.get("round") or event.get("round") or 0),
                "speaker": payload.get("speaker") or (event.get("actor") or {}).get("id") or "",
                "kind": payload.get("kind") or "",
                "targetQuestion": payload.get("targetQuestion") or "",
                "text": payload.get("text") or "",
                "rawText": payload.get("rawText") or payload.get("text") or "",
                "structured": payload.get("structured") or {},
                "parseError": payload.get("parseError") or "",
                "ok": bool(payload.get("ok")),
                "durationMs": int(payload.get("durationMs") or 0),
                "providerRef": payload.get("providerRef") or {},
                "createdAt": event.get("createdAt") or "",
            })
        elif event.get("type") == "user_intervention":
            transcript.append({
                "type": "user_intervention",
                "sequence": event.get("sequence"),
                "stage": payload.get("stage") or event.get("stage") or "",
                "round": int(payload.get("round") or event.get("round") or 0),
                "speaker": payload.get("actorId") or (event.get("actor") or {}).get("id") or "user",
                "actorType": "user",
                "text": payload.get("text") or "",
                "context": payload.get("context") or "",
                "ok": True,
                "durationMs": 0,
                "providerRef": {},
                "createdAt": event.get("createdAt") or "",
            })
        elif event.get("type") == "targeted_question":
            transcript.append({
                "type": "targeted_question",
                "sequence": event.get("sequence"),
                "stage": payload.get("stage") or event.get("stage") or "",
                "round": int(payload.get("round") or event.get("round") or 0),
                "speaker": payload.get("actorId") or (event.get("actor") or {}).get("id") or "user",
                "target": payload.get("target") or "",
                "text": payload.get("question") or "",
                "ok": True,
                "durationMs": 0,
                "providerRef": {},
                "createdAt": event.get("createdAt") or "",
            })
        elif event.get("type") == "agenda_change":
            transcript.append({
                "type": "agenda_change",
                "sequence": event.get("sequence"),
                "stage": payload.get("stage") or event.get("stage") or "",
                "round": int(payload.get("round") or event.get("round") or 0),
                "speaker": payload.get("actorId") or (event.get("actor") or {}).get("id") or "user",
                "actorType": "user",
                "text": payload.get("agenda") or "",
                "previousAgenda": payload.get("previousAgenda") or "",
                "reason": payload.get("reason") or "",
                "ok": True,
                "durationMs": 0,
                "providerRef": {},
                "createdAt": event.get("createdAt") or "",
            })
        elif event.get("type") == "arbitration_decision":
            transcript.append({
                "type": "arbitration_decision",
                "sequence": event.get("sequence"),
                "stage": payload.get("stage") or event.get("stage") or "",
                "round": int(payload.get("round") or event.get("round") or 0),
                "speaker": payload.get("actorId") or (event.get("actor") or {}).get("id") or "user",
                "actorType": "user",
                "text": payload.get("decision") or payload.get("action") or "",
                "action": payload.get("action") or "",
                "rationale": payload.get("rationale") or "",
                "ok": True,
                "durationMs": 0,
                "providerRef": {},
                "createdAt": event.get("createdAt") or "",
            })
    return transcript

def _exec_meeting_project_history(meeting, events=None):
    projected = _exec_meeting_project_active(meeting, events or [])
    projected["status"] = "completed" if meeting.get("stage") == "completed" else meeting.get("stage")
    projected["summary"] = (meeting.get("result") or {}).get("summary", "")
    projected["resolution"] = (meeting.get("result") or {}).get("decision", "")
    projected["actionItems"] = (meeting.get("result") or {}).get("actionItems", [])
    projected["actionItemDrafts"] = meeting.get("actionItemDrafts") or []
    projected["transcript"] = _exec_meeting_transcript_projection(events or [])
    projected["endedAt"] = int(datetime.fromisoformat(meeting.get("updatedAt").replace("Z", "+00:00")).timestamp()) if meeting.get("updatedAt") else int(time.time())
    return projected

def _meeting_active_projection():
    data = _load_meetings_file()
    active = data.get("_meetings", [])
    if not isinstance(active, list):
        active = []
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        released = _release_timed_out_preparing_meetings(store)
        if released:
            _save_exec_meeting_store(store)
        exec_active = [
            _exec_meeting_project_active(m, store.get("events", {}).get(m.get("id"), []))
            for m in store.get("meetings", {}).values()
            if m.get("stage") not in _EXEC_MEETING_TERMINAL
        ]
    return active + exec_active

def _meeting_history_projection():
    data = _load_meetings_file()
    history = data.get("_meetingHistory", [])
    if not isinstance(history, list):
        history = []
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        released = _release_timed_out_preparing_meetings(store)
        if released:
            _save_exec_meeting_store(store)
        exec_history = [
            _exec_meeting_project_history(m, store.get("events", {}).get(m.get("id"), []))
            for m in store.get("meetings", {}).values()
            if m.get("stage") in _EXEC_MEETING_TERMINAL
        ]
    return history + exec_history

def _meeting_find_action_draft(meeting, action_item_id):
    drafts = meeting.setdefault("actionItemDrafts", [])
    for draft in drafts:
        if str(draft.get("id") or "") == str(action_item_id or ""):
            return draft
    return None

def _meeting_audit_action_item(draft, action, actor_id, before=None, extra=None):
    draft.setdefault("audit", []).append({
        "action": action,
        "actorId": actor_id or "user",
        "at": _exec_meeting_now(),
        "before": before or {},
        "after": {k: draft.get(k) for k in ("title", "description", "assignee", "targetProjectId", "priority", "status", "taskId")},
        **(extra or {}),
    })

def _meeting_action_item_snapshot(draft):
    return {k: copy.deepcopy(v) for k, v in (draft or {}).items() if k != "audit"}

def _meeting_confirm_action_item_on_source_task(project_id, task_id, meeting, draft, action_item_id, actor_id, source_snapshot=None):
    if not project_id or not task_id:
        return {"error": "Meeting action items must be attached to the source task", "code": "source_task_required", "_status": 400}
    data, project = _project_find(project_id)
    if not project:
        return {"error": "Project not found", "_status": 404}
    if project.get("status") == "archived":
        return {"error": "Archived projects cannot receive meeting action items", "_status": 400}
    task = next((t for t in project.get("tasks", []) if t.get("id") == task_id), None)
    if not task:
        return {"error": "Source task not found", "_status": 404}
    meeting_id = str(meeting.get("id") or "").strip()
    now = _proj_now()
    item_id = _project_execution_meeting_action_key(meeting_id, action_item_id)
    task.setdefault("meetingActionItems", [])
    existing = next((a for a in task["meetingActionItems"] if isinstance(a, dict) and str(a.get("id") or "") == item_id), None)
    record = {
        "id": item_id,
        "meetingId": meeting_id,
        "requestId": str(((meeting.get("source") or {}) if isinstance(meeting.get("source"), dict) else {}).get("meetingRequestId") or ""),
        "sourceActionItemId": action_item_id,
        "title": str(draft.get("title") or "").strip() or "Meeting action item",
        "description": str(draft.get("description") or draft.get("sourceText") or "").strip(),
        "owner": str(draft.get("assignee") or draft.get("suggestedOwner") or task.get("executorAgentId") or task.get("assignee") or "").strip(),
        "status": "pending",
        "requiredForResume": True,
        "priority": str(draft.get("priority") or "medium").strip() or "medium",
        "sourceSnapshot": copy.deepcopy(source_snapshot or draft),
        "confirmedBy": actor_id,
        "confirmedAt": now,
        "updatedAt": now,
    }
    if existing:
        existing.update({k: v for k, v in record.items() if k not in {"createdAt"}})
        record = existing
    else:
        record["createdAt"] = now
        task["meetingActionItems"].append(record)
    task["updatedAt"] = now
    project["updatedAt"] = now
    _log_activity(project, "meeting_action_item_attached", actor_id or "meeting", f"Attached meeting action item '{record.get('title')}' to source task", task.get("id"))
    _save_projects(data)
    return {"ok": True, "project": project, "task": task, "record": record}

def _handle_executable_meeting_action_item(meeting_id, action_item_id, body):
    action = str(body.get("action") or "").strip()
    if action not in {"update", "reject", "keep", "confirm"}:
        return {"error": "Invalid action item action", "_status": 400}
    actor_id = str(body.get("actorId") or body.get("by") or "user").strip() or "user"
    idempotency_key = str(body.get("idempotencyKey") or "").strip()
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        meeting = store.get("meetings", {}).get(meeting_id)
        if not meeting:
            return {"error": "Executable meeting not found", "_status": 404}
        _meeting_ensure_action_item_drafts(store, meeting)
        draft = _meeting_find_action_draft(meeting, action_item_id)
        if not draft:
            return {"error": "Action item draft not found", "_status": 404}
        idem_key = f"{meeting_id}:action-item:{action_item_id}:{action}:{idempotency_key}" if idempotency_key else ""
        if idem_key and idem_key in store.get("idempotency", {}):
            idem = store.get("idempotency", {}).get(idem_key) or {}
            return {"ok": True, "meeting": meeting, "actionItem": draft, "taskId": idem.get("taskId") or draft.get("sourceTaskId") or draft.get("taskId"), "meetingActionItemId": idem.get("meetingActionItemId") or draft.get("meetingActionItemId"), "idempotent": True}
        before = _meeting_action_item_snapshot(draft)
        if action == "update":
            if draft.get("status") == "confirmed":
                return {"error": "Confirmed action items cannot be edited", "_status": 409}
            for key in ("title", "description", "assignee", "targetProjectId", "priority"):
                if key in body:
                    draft[key] = str(body.get(key) or "").strip()
            if not draft.get("targetProjectId") and body.get("projectId"):
                draft["targetProjectId"] = str(body.get("projectId") or "").strip()
            draft["updatedAt"] = _exec_meeting_now()
            _meeting_audit_action_item(draft, "update", actor_id, before)
        elif action == "reject":
            if draft.get("status") == "confirmed":
                return {"error": "Confirmed action items cannot be rejected", "_status": 409}
            draft["status"] = "rejected"
            draft["rejectionReason"] = str(body.get("reason") or body.get("rejectionReason") or "").strip()
            draft["updatedAt"] = _exec_meeting_now()
            _meeting_audit_action_item(draft, "reject", actor_id, before)
        elif action == "keep":
            if draft.get("status") == "confirmed":
                return {"error": "Confirmed action items cannot be changed to meeting-only", "_status": 409}
            draft["status"] = "kept_as_meeting_item"
            draft["updatedAt"] = _exec_meeting_now()
            _meeting_audit_action_item(draft, "keep", actor_id, before)
        elif action == "confirm":
            if draft.get("status") == "confirmed":
                confirmed_task_id = draft.get("sourceTaskId") or draft.get("taskId")
                if idem_key:
                    store.setdefault("idempotency", {})[idem_key] = {"meetingId": meeting_id, "taskId": confirmed_task_id}
                    _save_exec_meeting_store(store)
                return {"ok": True, "meeting": meeting, "actionItem": draft, "taskId": confirmed_task_id, "idempotent": True}
            source = meeting.get("source") if isinstance(meeting.get("source"), dict) else {}
            target_project_id = str(source.get("projectId") or meeting.get("projectId") or body.get("targetProjectId") or body.get("projectId") or draft.get("targetProjectId") or "").strip()
            source_task_id = str(source.get("taskId") or body.get("taskId") or draft.get("sourceTaskId") or "").strip()
            attach_result = _meeting_confirm_action_item_on_source_task(target_project_id, source_task_id, meeting, draft, action_item_id, actor_id, before)
            if attach_result.get("error"):
                return attach_result
            _save_exec_meeting_store(store)
        if action != "confirm":
            event = _append_exec_meeting_event(store, meeting, "action_item_updated", actor={"type": "user", "id": actor_id}, payload={"action": action, "actionItemId": action_item_id, "before": before, "after": draft}, idempotency_key=idempotency_key)
            if idem_key:
                store.setdefault("idempotency", {})[idem_key] = {"meetingId": meeting_id, "sequence": event["sequence"]}
            _save_exec_meeting_store(store)
            return {"ok": True, "meeting": meeting, "actionItem": draft}

    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        meeting = store.get("meetings", {}).get(meeting_id)
        if not meeting:
            return {"ok": True, "task": attach_result.get("task"), "taskId": (attach_result.get("task") or {}).get("id")}
        _meeting_ensure_action_item_drafts(store, meeting)
        draft = _meeting_find_action_draft(meeting, action_item_id)
        if draft:
            before2 = _meeting_action_item_snapshot(draft)
            task = attach_result.get("task") or {}
            record = attach_result.get("record") or {}
            draft.update({
                "status": "confirmed",
                "targetProjectId": target_project_id,
                "sourceTaskId": task.get("id"),
                "meetingActionItemId": record.get("id"),
                "confirmedBy": actor_id,
                "confirmedAt": record.get("confirmedAt") or _exec_meeting_now(),
                "updatedAt": _exec_meeting_now(),
            })
            _meeting_audit_action_item(draft, "confirm", actor_id, before2, {"taskId": task.get("id"), "projectId": target_project_id, "meetingActionItemId": record.get("id")})
            event = _append_exec_meeting_event(store, meeting, "action_item_confirmed", actor={"type": "user", "id": actor_id}, payload={"actionItemId": action_item_id, "projectId": target_project_id, "taskId": task.get("id"), "meetingActionItemId": record.get("id")}, idempotency_key=idempotency_key)
            if idem_key:
                store.setdefault("idempotency", {})[idem_key] = {"meetingId": meeting_id, "taskId": task.get("id"), "meetingActionItemId": record.get("id"), "sequence": event["sequence"]}
        _save_exec_meeting_store(store)
        return {"ok": True, "meeting": meeting, "actionItem": draft, "task": task, "taskId": task.get("id"), "meetingActionItem": attach_result.get("record")}

def _handle_executable_meeting_create(body):
    topic = str(body.get("topic") or "").strip()
    participants = _exec_meeting_clean_participants(body.get("participants") or body.get("agents") or [])
    if not topic:
        return {"error": "Meeting topic is required", "_status": 400}
    if len(participants) < 2:
        return {"error": "Executable meeting requires at least 2 participants", "_status": 400}
    blocked_participants = _exec_meeting_archive_manager_participants(participants)
    if blocked_participants:
        return _exec_meeting_archive_manager_error(blocked_participants)
    moderator = str(body.get("moderator") or body.get("moderatorId") or participants[0]).strip()
    if _is_archive_manager_agent(moderator):
        return _exec_meeting_archive_manager_error([moderator])
    if moderator not in participants:
        return {"error": "Moderator must be one of the participants", "_status": 400}
    meeting_type = str(body.get("meetingType") or body.get("kind") or "discussion").strip() or "discussion"
    if meeting_type not in {"information", "discussion", "task"}:
        meeting_type = "discussion"
    try:
        max_rounds = max(1, min(20, int(body.get("maxRounds") or 2)))
    except (TypeError, ValueError):
        max_rounds = 2
    now = _exec_meeting_now()
    meeting_id = str(body.get("id") or uuid.uuid4())
    actor = {"type": "user", "id": str(body.get("createdBy") or body.get("organizer") or "user")}
    idempotency_key = str(body.get("idempotencyKey") or "").strip()
    raw_project_id = body.get("projectId") or ((body.get("source") or {}) if isinstance(body.get("source"), dict) else {}).get("projectId")
    project_ref = _meeting_project_ref(raw_project_id)
    if not project_ref.get("ok"):
        return {"error": project_ref.get("error") or "Project not found", "code": project_ref.get("code", "project_not_found"), "_status": project_ref.get("_status", 404)}
    project_id, project_title = project_ref["projectId"], project_ref["projectTitle"]
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        if idempotency_key and idempotency_key in store.get("idempotency", {}):
            existing_id = store["idempotency"][idempotency_key].get("meetingId")
            existing = store.get("meetings", {}).get(existing_id)
            if existing:
                return {"ok": True, "meeting": existing, "idempotent": True}
        _rebuild_exec_meeting_occupancy(store)
        conflicts = _meeting_build_conflicts(store, participants)
        occupied_conflicts = {c.get("agentId"): (c.get("source") or {}).get("meetingId") for c in conflicts if c.get("reason") == "meeting_occupied"}
        allow_conflicts = bool(body.get("allowConflicts") or body.get("conflictAware"))
        if conflicts and not allow_conflicts:
            if occupied_conflicts:
                return {"error": "One or more participants are already in an executable meeting", "conflicts": occupied_conflicts, "_status": 409}
            return {"error": "One or more participants are busy", "conflicts": conflicts, "_status": 409}
        meeting_stage = "conflict" if conflicts else "preparing"
        meeting = {
            "id": meeting_id,
            "executableMeeting": True,
            "topic": topic,
            "agenda": str(body.get("agenda") or topic).strip(),
            "purpose": str(body.get("purpose") or "").strip(),
            "meetingType": meeting_type,
            "organizer": str(body.get("organizer") or participants[0]).strip(),
            "createdBy": str(body.get("createdBy") or body.get("organizer") or "user").strip(),
            "createdByType": str(body.get("createdByType") or ("agent" if body.get("createdByAgentId") else "user")).strip(),
            "createdByAgentId": str(body.get("createdByAgentId") or "").strip(),
            "projectId": project_id,
            "projectTitle": project_title,
            "moderator": moderator,
            "participants": participants,
            "stage": meeting_stage,
            "preparingStartedAt": now if meeting_stage == "preparing" else "",
            "preparingTimeoutSec": _meeting_preparing_timeout_sec(),
            "previousStage": "",
            "round": 0,
            "maxRounds": max_rounds,
            "decisionWindowSec": _meeting_clamped_decision_window_sec(body.get("decisionWindowSec") or body.get("decisionWindowSeconds") or _meeting_decision_window_sec()),
            "decisionWindowConfiguredSec": _meeting_clamped_decision_window_sec(body.get("decisionWindowSec") or body.get("decisionWindowSeconds") or _meeting_decision_window_sec()),
            "resolutionPolicy": _meeting_resolution_policy(body.get("resolutionPolicy") or body.get("arbitrationPolicy")),
            "currentSpeaker": "",
            "speakerQueue": list(participants),
        "context": str(body.get("context") or body.get("initialContext") or "").strip(),
            "contextMode": _meeting_context_mode(body.get("contextMode")),
            "contextBudget": _meeting_context_budget(body.get("contextBudget")),
            "rollingSummary": "",
            "participantLastSeen": {},
            "participantState": {p: {"status": "conflict" if any(c.get("agentId") == p and c.get("status") in {"open", "waiting", "reserved"} for c in conflicts) else "reserved", "joinedAt": now} for p in participants},
            "conflicts": conflicts,
            "originalWork": {},
            "reservation": {},
            "result": {},
            "source": body.get("source") if isinstance(body.get("source"), dict) else {},
            "version": 0,
            "lastEventSequence": 0,
            "createdAt": now,
            "updatedAt": now,
        }
        store.setdefault("meetings", {})[meeting_id] = meeting
        _append_exec_meeting_event(store, meeting, "meeting_created", actor=actor, payload={"stage": meeting_stage, "conflicts": conflicts}, idempotency_key=idempotency_key)
        if not conflicts:
            store.setdefault("occupancy", {}).update({p: meeting_id for p in participants})
        if idempotency_key:
            store.setdefault("idempotency", {})[idempotency_key] = {"meetingId": meeting_id, "sequence": meeting["lastEventSequence"]}
        _save_exec_meeting_store(store)
    if conflicts:
        live_meeting = _meeting_complete_live_advisories(meeting_id)
        if live_meeting:
            meeting = live_meeting
    return {"ok": True, "meeting": meeting}

def _handle_executable_meeting_detail(meeting_id):
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        meeting = store.get("meetings", {}).get(meeting_id)
        if not meeting:
            return {"error": "Executable meeting not found", "_status": 404}
        if meeting.get("stage") == "completed":
            _meeting_ensure_action_item_drafts(store, meeting)
            _save_exec_meeting_store(store)
        else:
            released = _release_timed_out_preparing_meetings(store)
            if released:
                _save_exec_meeting_store(store)
        return {"ok": True, "meeting": meeting, "events": store.get("events", {}).get(meeting_id, [])}

def _handle_executable_meeting_events(meeting_id, query_string=""):
    qs = urllib.parse.parse_qs(query_string or "")
    try:
        after = int((qs.get("after") or ["0"])[0] or 0)
    except (TypeError, ValueError):
        after = 0
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        if meeting_id not in store.get("meetings", {}):
            return {"error": "Executable meeting not found", "_status": 404}
        events = [e for e in store.get("events", {}).get(meeting_id, []) if int(e.get("sequence") or 0) > after]
        return {"ok": True, "meetingId": meeting_id, "after": after, "events": events}

def _handle_executable_meeting_conflict_action(meeting_id, body):
    action = str(body.get("action") or "").strip()
    if action not in {"wait", "reserve", "replace", "force_join", "cancel_conflict", "refresh"}:
        return {"error": "Invalid conflict action", "_status": 400}
    agent_id = str(body.get("agentId") or "").strip()
    actor = {"type": str(body.get("actorType") or "user"), "id": str(body.get("actorId") or "user")}
    idempotency_key = str(body.get("idempotencyKey") or "").strip()
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        idem_key = f"{meeting_id}:conflict:{action}:{idempotency_key}" if idempotency_key else ""
        meeting = store.get("meetings", {}).get(meeting_id)
        if not meeting:
            return {"error": "Executable meeting not found", "_status": 404}
        if idem_key and idem_key in store.get("idempotency", {}):
            seq = store["idempotency"][idem_key].get("sequence")
            event = next((e for e in store.get("events", {}).get(meeting_id, []) if e.get("sequence") == seq), None)
            return {"ok": True, "meeting": meeting, "event": event, "idempotent": True}
        if meeting.get("stage") in _EXEC_MEETING_TERMINAL:
            return {"error": "Cannot resolve conflicts on a terminal meeting", "stage": meeting.get("stage"), "_status": 409}
        conflicts = meeting.get("conflicts") if isinstance(meeting.get("conflicts"), list) else []
        if action == "refresh":
            refreshed = _meeting_build_conflicts(store, meeting.get("participants") or [], exclude_meeting_id=meeting_id)
            meeting["conflicts"] = refreshed
            meeting["stage"] = "conflict" if refreshed else "preparing"
            if not refreshed:
                _meeting_mark_preparing_started(meeting)
                store.setdefault("occupancy", {}).update({p: meeting_id for p in meeting.get("participants") or []})
                for p in meeting.get("participants") or []:
                    meeting.setdefault("participantState", {}).setdefault(p, {})["status"] = "reserved"
            event = _append_exec_meeting_event(store, meeting, "meeting_conflict_refreshed", actor=actor, payload={"conflicts": refreshed}, idempotency_key=idempotency_key)
            if idem_key:
                store.setdefault("idempotency", {})[idem_key] = {"meetingId": meeting_id, "sequence": event["sequence"]}
            _save_exec_meeting_store(store)
            if refreshed:
                live_meeting = _meeting_complete_live_advisories(meeting_id)
                if live_meeting:
                    meeting = live_meeting
            return {"ok": True, "meeting": meeting, "event": event}
        conflict = next((c for c in conflicts if c.get("agentId") == agent_id and c.get("status") in {"open", "waiting", "reserved"}), None)
        if not conflict:
            return {"error": "Open conflict not found for agent", "agentId": agent_id, "_status": 404}
        now = _exec_meeting_now()
        payload = {"action": action, "agentId": agent_id, "previous": dict(conflict)}
        if action == "wait":
            conflict["status"] = "waiting"
            conflict["resolution"] = {"action": "wait", "decidedAt": now, "decidedBy": actor["id"]}
        elif action == "reserve":
            conflict["status"] = "reserved"
            reservation = {
                "agentId": agent_id,
                "status": "scheduled",
                "mode": str(body.get("mode") or "try_later"),
                "targetAt": str(body.get("targetAt") or body.get("remindAt") or "").strip(),
                "note": str(body.get("note") or "Try again later; this is not a hard reservation.").strip(),
                "createdAt": now,
                "createdBy": actor["id"],
            }
            meeting.setdefault("reservation", {})[agent_id] = reservation
            conflict["reservation"] = reservation
            conflict["resolution"] = {"action": "reserve", "decidedAt": now, "decidedBy": actor["id"]}
        elif action == "replace":
            replacement = str(body.get("replacement") or body.get("replacementAgentId") or "").strip()
            if not replacement:
                return {"error": "Replacement agent is required", "_status": 400}
            if replacement in (meeting.get("participants") or []):
                return {"error": "Replacement agent is already a participant", "_status": 400}
            replacement_ctx = _meeting_busy_context_for_agent(store, replacement, exclude_meeting_id=meeting_id)
            if replacement_ctx.get("busy"):
                return {"error": "Replacement agent is busy", "conflict": replacement_ctx, "_status": 409}
            participants = [replacement if p == agent_id else p for p in meeting.get("participants") or []]
            meeting["participants"] = participants
            if meeting.get("moderator") == agent_id:
                meeting["moderator"] = replacement
            meeting["speakerQueue"] = [replacement if p == agent_id else p for p in meeting.get("speakerQueue") or []]
            meeting.setdefault("participantState", {}).pop(agent_id, None)
            meeting.setdefault("participantState", {})[replacement] = {"status": "reserved", "joinedAt": now, "replacedAgentId": agent_id}
            conflict["status"] = "resolved"
            conflict["resolution"] = {"action": "replace", "replacement": replacement, "decidedAt": now, "decidedBy": actor["id"]}
            payload["replacement"] = replacement
        elif action == "force_join":
            if not body.get("confirmForce"):
                return {"error": "Force join requires second confirmation", "advisory": conflict.get("advisory") or {}, "_status": 409}
            if not conflict.get("advisory"):
                conflict["advisory"] = _meeting_conflict_advisory(conflict)
            snapshot = _meeting_original_work_snapshot(conflict, "force_join")
            meeting.setdefault("originalWork", {})[agent_id] = snapshot
            meeting.setdefault("participantState", {}).setdefault(agent_id, {})["status"] = "reserved"
            meeting["participantState"][agent_id]["pauseState"] = snapshot["pauseState"]
            meeting["participantState"][agent_id]["forcedJoin"] = True
            conflict["status"] = "resolved"
            conflict["resolution"] = {"action": "force_join", "decidedAt": now, "decidedBy": actor["id"], "confirmForce": True}
            payload["snapshot"] = snapshot
        elif action == "cancel_conflict":
            conflict["status"] = "cancelled"
            conflict["resolution"] = {"action": "cancel_conflict", "decidedAt": now, "decidedBy": actor["id"]}
        conflict["updatedAt"] = now
        if not _meeting_has_open_conflicts(meeting):
            meeting["previousStage"] = meeting.get("stage")
            meeting["stage"] = "preparing"
            _meeting_mark_preparing_started(meeting, now)
            for p in meeting.get("participants") or []:
                meeting.setdefault("participantState", {}).setdefault(p, {})["status"] = "reserved"
            _rebuild_exec_meeting_occupancy(store)
            occupied = {p: store.get("occupancy", {}).get(p) for p in meeting.get("participants") or [] if store.get("occupancy", {}).get(p) and store.get("occupancy", {}).get(p) != meeting_id}
            if occupied:
                meeting["stage"] = "conflict"
                for p, occupied_by in occupied.items():
                    new_conflict = {
                        "id": str(uuid.uuid4()),
                        "agentId": p,
                        "status": "open",
                        "reason": "meeting_occupied",
                        "busyKind": "meeting",
                        "riskLevel": "high",
                        "summary": f"Already in meeting: {occupied_by}",
                        "estimatedAvailability": "unknown",
                        "pauseCapability": "unavailable",
                        "source": {"meetingId": occupied_by},
                        "createdAt": now,
                        "updatedAt": now,
                    }
                    new_conflict["advisory"] = _meeting_conflict_advisory(new_conflict)
                    meeting.setdefault("conflicts", []).append(new_conflict)
            else:
                store.setdefault("occupancy", {}).update({p: meeting_id for p in meeting.get("participants") or []})
        event = _append_exec_meeting_event(store, meeting, "meeting_conflict_resolved", actor=actor, payload=payload, idempotency_key=idempotency_key)
        if idem_key:
            store.setdefault("idempotency", {})[idem_key] = {"meetingId": meeting_id, "sequence": event["sequence"]}
        _save_exec_meeting_store(store)
    if meeting.get("stage") in _EXEC_MEETING_TERMINAL:
        _project_execution_apply_meeting_result(meeting)
    return {"ok": True, "meeting": meeting, "event": event}

def _handle_executable_meeting_transition(meeting_id, body):
    target = str(body.get("stage") or body.get("to") or body.get("action") or "").strip()
    aliases = {
        "start": "active_opening",
        "opening": "active_opening",
        "discussion": "active_discussion",
        "pause": "paused",
        "resume_preparing": "preparing",
        "resume_opening": "active_opening",
        "resume_discussion": "active_discussion",
        "continue": "active_discussion",
        "continue_decision": "active_discussion",
        "await_decision": "awaiting_user_decision",
        "summarize": "summarizing",
        "complete": "completed",
        "cancel": "cancelled",
        "fail": "failed",
    }
    target = aliases.get(target, target)
    if target not in _EXEC_MEETING_PHASES:
        return {"error": "Invalid meeting stage", "_status": 400}
    expected = body.get("expectedVersion")
    idempotency_key = str(body.get("idempotencyKey") or "").strip()
    actor = {"type": str(body.get("actorType") or "user"), "id": str(body.get("actorId") or "user")}
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        idem_key = f"{meeting_id}:transition:{idempotency_key}" if idempotency_key else ""
        if idem_key and idem_key in store.get("idempotency", {}):
            meeting = store.get("meetings", {}).get(meeting_id)
            return {"ok": True, "meeting": meeting, "idempotent": True}
        meeting = store.get("meetings", {}).get(meeting_id)
        if not meeting:
            return {"error": "Executable meeting not found", "_status": 404}
        current = meeting.get("stage")
        if current == "awaiting_user_decision" and str(body.get("action") or "").strip() in {"continue", "continue_decision"}:
            _meeting_continue_from_decision_window(store, meeting, actor=actor, reason=body.get("reason") or "user_continue")
            event = store.get("events", {}).get(meeting_id, [])[-1]
            _save_exec_meeting_store(store)
            return {"ok": True, "meeting": meeting, "event": event}
        if expected is not None and int(expected) != int(meeting.get("version", 0)):
            return {"error": "Meeting version conflict", "currentVersion": meeting.get("version", 0), "_status": 409}
        if target not in _EXEC_MEETING_TRANSITIONS.get(current, set()):
            return {"error": f"Illegal transition from {current} to {target}", "stage": current, "_status": 409}
        meeting["previousStage"] = current
        meeting["stage"] = target
        if target == "preparing":
            _meeting_mark_preparing_started(meeting)
        if target in {"active_opening", "active_discussion"}:
            meeting["currentSpeaker"] = (meeting.get("speakerQueue") or [""])[0]
        if target == "active_discussion":
            meeting["round"] = max(1, int(meeting.get("round") or 0))
        if target in _EXEC_MEETING_TERMINAL:
            meeting["currentSpeaker"] = ""
            for participant in meeting.get("participants", []):
                store.get("occupancy", {}).pop(participant, None)
            _meeting_resume_original_work(store, meeting, target)
            if target == "completed":
                result = body.get("result") if isinstance(body.get("result"), dict) else {}
                if body.get("summary"):
                    result.setdefault("summary", str(body.get("summary") or ""))
                meeting["result"] = {**meeting.get("result", {}), **result}
                _meeting_ensure_action_item_drafts(store, meeting)
                _award_meeting_participation_points(meeting)
        event = _append_exec_meeting_event(store, meeting, "meeting_transitioned", actor=actor, payload={"from": current, "to": target, "reason": body.get("reason") or ""}, idempotency_key=idempotency_key)
        if idem_key:
            store.setdefault("idempotency", {})[idem_key] = {"meetingId": meeting_id, "sequence": event["sequence"]}
        _save_exec_meeting_store(store)
    if target in _EXEC_MEETING_TERMINAL:
        _project_execution_apply_meeting_result(meeting)
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        meeting = store.get("meetings", {}).get(meeting_id, meeting)
        return {"ok": True, "meeting": meeting, "event": event}

def _handle_executable_meeting_intervention(meeting_id, body):
    text = str(body.get("text") or body.get("message") or "").strip()
    context = str(body.get("context") or body.get("additionalContext") or "").strip()
    if not text and not context:
        return {"error": "User intervention requires text or context", "_status": 400}
    expected = body.get("expectedVersion")
    idempotency_key = str(body.get("idempotencyKey") or "").strip()
    actor_id = str(body.get("actorId") or "user").strip() or "user"
    actor = {"type": "user", "id": actor_id}
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        idem_key = f"{meeting_id}:intervention:{idempotency_key}" if idempotency_key else ""
        meeting = store.get("meetings", {}).get(meeting_id)
        if not meeting:
            return {"error": "Executable meeting not found", "_status": 404}
        if idem_key and idem_key in store.get("idempotency", {}):
            seq = store["idempotency"][idem_key].get("sequence")
            event = next((e for e in store.get("events", {}).get(meeting_id, []) if e.get("sequence") == seq), None)
            return {"ok": True, "meeting": meeting, "event": event, "idempotent": True}
        if meeting.get("stage") in _EXEC_MEETING_TERMINAL:
            return {"error": "Cannot add context to a terminal meeting", "stage": meeting.get("stage"), "_status": 409}
        if expected is not None:
            try:
                expected_version = int(expected)
            except (TypeError, ValueError):
                return {"error": "Invalid expectedVersion", "_status": 400}
            if expected_version != int(meeting.get("version", 0)):
                return {"error": "Meeting version conflict", "currentVersion": meeting.get("version", 0), "_status": 409}
        if text and context:
            kind = "statement_context"
        elif context:
            kind = "context"
        else:
            kind = "statement"
        payload = {
            "kind": kind,
            "text": text,
            "context": context,
            "actorId": actor_id,
            "stage": meeting.get("stage"),
            "round": meeting.get("round", 0),
            "appliesFromSequence": meeting.get("lastEventSequence", 0),
        }
        event = _append_exec_meeting_event(store, meeting, "user_intervention", actor=actor, payload=payload, idempotency_key=idempotency_key)
        if idem_key:
            store.setdefault("idempotency", {})[idem_key] = {"meetingId": meeting_id, "sequence": event["sequence"]}
        _save_exec_meeting_store(store)
        return {"ok": True, "meeting": meeting, "event": event}

def _handle_executable_meeting_agenda_change(meeting_id, body):
    agenda = str(body.get("agenda") or body.get("topic") or body.get("newAgenda") or "").strip()
    reason = str(body.get("reason") or "").strip()
    if not agenda:
        return {"error": "Agenda change requires agenda", "_status": 400}
    expected = body.get("expectedVersion")
    idempotency_key = str(body.get("idempotencyKey") or "").strip()
    actor_id = str(body.get("actorId") or "user").strip() or "user"
    actor = {"type": "user", "id": actor_id}
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        idem_key = f"{meeting_id}:agenda:{idempotency_key}" if idempotency_key else ""
        meeting = store.get("meetings", {}).get(meeting_id)
        if not meeting:
            return {"error": "Executable meeting not found", "_status": 404}
        if idem_key and idem_key in store.get("idempotency", {}):
            seq = store["idempotency"][idem_key].get("sequence")
            event = next((e for e in store.get("events", {}).get(meeting_id, []) if e.get("sequence") == seq), None)
            return {"ok": True, "meeting": meeting, "event": event, "idempotent": True}
        if meeting.get("stage") in _EXEC_MEETING_TERMINAL:
            return {"error": "Cannot change agenda for a terminal meeting", "stage": meeting.get("stage"), "_status": 409}
        if expected is not None:
            try:
                expected_version = int(expected)
            except (TypeError, ValueError):
                return {"error": "Invalid expectedVersion", "_status": 400}
            if expected_version != int(meeting.get("version", 0)):
                return {"error": "Meeting version conflict", "currentVersion": meeting.get("version", 0), "_status": 409}
        previous = meeting.get("agenda") or meeting.get("topic") or ""
        payload = {
            "agenda": agenda,
            "previousAgenda": previous,
            "reason": reason,
            "actorId": actor_id,
            "stage": meeting.get("stage"),
            "round": meeting.get("round", 0),
            "appliesFromSequence": meeting.get("lastEventSequence", 0),
        }
        meeting["agenda"] = agenda
        event = _append_exec_meeting_event(store, meeting, "agenda_change", actor=actor, payload=payload, idempotency_key=idempotency_key)
        if idem_key:
            store.setdefault("idempotency", {})[idem_key] = {"meetingId": meeting_id, "sequence": event["sequence"]}
        _save_exec_meeting_store(store)
        return {"ok": True, "meeting": meeting, "event": event}

def _handle_executable_meeting_arbitration(meeting_id, body):
    action = str(body.get("action") or body.get("decisionAction") or "").strip() or "decide"
    if action not in {"decide", "end_no_consensus", "continue_discussion", "consensus_summary"}:
        return {"error": "Unsupported arbitration action", "_status": 400}
    decision = str(body.get("decision") or body.get("resolution") or "").strip()
    rationale = str(body.get("rationale") or body.get("reason") or "").strip()
    if action == "decide" and not decision:
        return {"error": "Arbitration decision is required", "_status": 400}
    idempotency_key = str(body.get("idempotencyKey") or "").strip()
    actor_id = str(body.get("actorId") or "user").strip() or "user"
    actor = {"type": "user", "id": actor_id}
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        meeting = store.get("meetings", {}).get(meeting_id)
        if not meeting:
            return {"error": "Executable meeting not found", "_status": 404}
        if meeting.get("stage") in _EXEC_MEETING_TERMINAL:
            return {"error": "Cannot arbitrate a terminal meeting", "stage": meeting.get("stage"), "_status": 409}
        if meeting.get("stage") != "awaiting_user_decision":
            return {"error": "Arbitration is only allowed during the user decision window", "stage": meeting.get("stage"), "_status": 409}
        idem_key = f"{meeting_id}:arbitration:{idempotency_key}" if idempotency_key else ""
        if idem_key and idem_key in store.get("idempotency", {}):
            seq = store["idempotency"][idem_key].get("sequence")
            event = next((e for e in store.get("events", {}).get(meeting_id, []) if e.get("sequence") == seq), None)
            return {"ok": True, "meeting": meeting, "event": event, "idempotent": True}
        payload = {
            "action": action,
            "decision": decision,
            "rationale": rationale,
            "actorId": actor_id,
            "stage": meeting.get("decisionForStage") or meeting.get("stage"),
            "round": int(meeting.get("decisionForRound") or meeting.get("round") or 0),
            "arbitration": meeting.get("arbitration") or {},
        }
        event = _append_exec_meeting_event(store, meeting, "arbitration_decision", actor=actor, payload=payload, idempotency_key=idempotency_key)
        if action == "continue_discussion":
            meeting["maxRounds"] = max(int(meeting.get("maxRounds") or 1), int(meeting.get("round") or 0) + 1)
            meeting["decisionNextStage"] = "active_discussion"
            meeting["decisionNextRound"] = int(meeting.get("round") or 0) + 1
            _meeting_continue_from_decision_window(store, meeting, actor=actor, reason="arbitration_continue")
        elif action == "consensus_summary":
            previous = meeting.get("stage")
            meeting["previousStage"] = previous
            meeting["stage"] = "summarizing"
            meeting["currentSpeaker"] = meeting.get("moderator") or (meeting.get("participants") or [""])[0]
            for key in ("decisionForStage", "decisionForRound", "decisionNextStage", "decisionNextRound", "decisionWindowSec", "decisionDeadlineAt", "arbitration"):
                meeting.pop(key, None)
            _append_exec_meeting_event(store, meeting, "decision_window_closed", actor=actor, payload={"to": "summarizing", "round": int(meeting.get("round") or 0), "reason": "arbitration_consensus_summary"})
            _append_exec_meeting_event(store, meeting, "meeting_transitioned", actor=actor, payload={"from": previous, "to": "summarizing", "reason": "arbitration_consensus_summary"})
        else:
            events = list(store.get("events", {}).get(meeting_id, []))
            fallback = _meeting_fallback_result(meeting, events)
            arbitration = payload.get("arbitration") or {}
            final_decision = decision if action == "decide" else "No consensus. Meeting ended with unresolved disagreement."
            summary_suffix = rationale or arbitration.get("moderatorSuggestion") or ""
            result = {
                **fallback,
                "summary": _meeting_truncate_text((fallback.get("summary") or "") + ("\n" + summary_suffix if summary_suffix else ""), 2000),
                "decision": final_decision,
                "unresolvedQuestions": arbitration.get("disagreements") or fallback.get("unresolvedQuestions") or [],
                "disagreements": arbitration.get("disagreements") or fallback.get("disagreements") or [],
                "arbitration": {"action": action, "decision": decision, "rationale": rationale, "actorId": actor_id},
            }
            meeting["result"] = result
            _meeting_ensure_action_item_drafts(store, meeting)
            previous = meeting.get("stage")
            meeting["previousStage"] = previous
            meeting["stage"] = "completed"
            meeting["currentSpeaker"] = ""
            for key in ("decisionForStage", "decisionForRound", "decisionNextStage", "decisionNextRound", "decisionWindowSec", "decisionDeadlineAt", "arbitration"):
                meeting.pop(key, None)
            for participant in meeting.get("participants", []):
                store.get("occupancy", {}).pop(participant, None)
            _meeting_resume_original_work(store, meeting, "arbitration")
            _award_meeting_participation_points(meeting)
            _append_exec_meeting_event(store, meeting, "meeting_result", actor=actor, payload=result)
            _append_exec_meeting_event(store, meeting, "meeting_transitioned", actor=actor, payload={"from": previous, "to": "completed", "reason": action})
        if idem_key:
            store.setdefault("idempotency", {})[idem_key] = {"meetingId": meeting_id, "sequence": event["sequence"]}
        _save_exec_meeting_store(store)
    if action != "consensus_summary" and isinstance(meeting, dict) and meeting.get("stage") == "completed":
        _project_execution_apply_meeting_result(meeting)
        _archive_trigger_meeting_conclusion(meeting)
    if action == "consensus_summary":
        summarized = _handle_executable_meeting_end_with_moderator(meeting_id, {"actorId": actor_id, "actorType": "user"})
        if isinstance(summarized, dict):
            summarized["event"] = event
        return summarized
    return {"ok": True, "meeting": meeting, "event": event}

def _handle_executable_meeting_moderator_takeover(meeting_id, body):
    action = str(body.get("action") or "").strip()
    actor = {"type": str(body.get("actorType") or "user"), "id": str(body.get("actorId") or "user")}
    if action not in {"user_takeover", "replace_moderator"}:
        return {"error": "Invalid moderator takeover action", "_status": 400}
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        meeting = store.get("meetings", {}).get(meeting_id)
        if not meeting:
            return {"error": "Executable meeting not found", "_status": 404}
        if meeting.get("stage") in _EXEC_MEETING_TERMINAL:
            return {"error": "Meeting already ended", "_status": 409}
        if meeting.get("stage") != "awaiting_user_decision" or (meeting.get("moderatorFailure") or {}).get("reason") != "moderator_failed":
            return {"error": "Meeting is not waiting for moderator takeover", "stage": meeting.get("stage"), "_status": 409}
        failure = dict(meeting.get("moderatorFailure") or {})
        if action == "replace_moderator":
            replacement = str(body.get("moderator") or body.get("newModerator") or "").strip()
            if replacement not in (meeting.get("participants") or []):
                return {"error": "Replacement moderator must be a participant", "_status": 400}
            previous_moderator = meeting.get("moderator") or ""
            meeting["moderator"] = replacement
            meeting["moderatorFailure"] = {**failure, "resolvedBy": "replace_moderator", "replacement": replacement}
            previous = meeting.get("stage")
            meeting["previousStage"] = previous
            meeting["stage"] = "summarizing"
            meeting["currentSpeaker"] = replacement
            for key in ("decisionForStage", "decisionForRound", "decisionNextStage", "decisionNextRound", "decisionDeadlineAt"):
                meeting.pop(key, None)
            event = _append_exec_meeting_event(store, meeting, "moderator_takeover", actor=actor, payload={
                "action": "replace_moderator",
                "previousModerator": previous_moderator,
                "moderator": replacement,
                "failure": failure,
            })
            _append_exec_meeting_event(store, meeting, "meeting_transitioned", actor=actor, payload={"from": previous, "to": "summarizing", "reason": "moderator_replaced"})
            _save_exec_meeting_store(store)
        result = None
    if action == "replace_moderator":
        result = _handle_executable_meeting_end_with_moderator(meeting_id, {"actorId": actor["id"], "actorType": actor["type"]})
        if result.get("ok"):
            result["takeoverEvent"] = event
        return result

    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        meeting = store.get("meetings", {}).get(meeting_id)
        if not meeting:
            return {"error": "Executable meeting not found", "_status": 404}
        summary = str(body.get("summary") or "").strip()
        decision = str(body.get("decision") or body.get("resolution") or "").strip()
        if not summary:
            return {"error": "Summary is required for user takeover", "_status": 400}
        action_items = body.get("actionItems") if isinstance(body.get("actionItems"), list) else []
        events = list(store.get("events", {}).get(meeting_id, []))
        failure = dict(meeting.get("moderatorFailure") or {})
        fallback = _meeting_fallback_result(meeting, events)
        final_result = {
            **fallback,
            "summary": summary,
            "decision": decision or "Meeting closed by user after moderator failure.",
            "actionItems": action_items,
            "moderatorFailure": failure,
            "moderatorTakeover": {"action": "user_takeover", "actorId": actor["id"]},
        }
        meeting["result"] = final_result
        meeting["currentSpeaker"] = ""
        previous = meeting.get("stage")
        event = _append_exec_meeting_event(store, meeting, "moderator_takeover", actor=actor, payload={
            "action": "user_takeover",
            "summary": summary,
            "decision": final_result["decision"],
            "failure": failure,
        })
        _append_exec_meeting_event(store, meeting, "meeting_result", actor=actor, payload=final_result)
        meeting["previousStage"] = previous
        meeting["stage"] = "completed"
        for participant in meeting.get("participants", []):
            store.get("occupancy", {}).pop(participant, None)
        _meeting_resume_original_work(store, meeting, "moderator_takeover")
        _award_meeting_participation_points(meeting)
        _append_exec_meeting_event(store, meeting, "meeting_transitioned", actor=actor, payload={"from": previous, "to": "completed", "reason": "user_moderator_takeover"})
        _save_exec_meeting_store(store)
        result_payload = {"ok": True, "meeting": meeting, "event": event, "events": store.get("events", {}).get(meeting_id, [])}
    _archive_trigger_meeting_conclusion(meeting)
    return result_payload

def _meeting_build_targeted_prompt(meeting, speaker, question, events):
    base = _meeting_build_prompt(meeting, speaker, meeting.get("decisionForStage") or meeting.get("stage"), events)
    instruction = (
        "\nTargeted question from the user:\n"
        f"{_meeting_truncate_text(question, 2000)}\n\n"
        "Answer this targeted question once. Keep the same JSON schema. "
        "Do not treat this as a formal round turn.\n"
    )
    budget = _meeting_context_budget(meeting.get("contextBudget"))
    return _meeting_truncate_text(base + instruction, budget["maxPromptChars"])

def _handle_executable_meeting_targeted_question(meeting_id, body):
    question = str(body.get("question") or body.get("text") or body.get("message") or "").strip()
    target = str(body.get("target") or body.get("targetParticipant") or body.get("speaker") or "").strip()
    if not question:
        return {"error": "Targeted question requires text", "_status": 400}
    if not target:
        return {"error": "Target participant is required", "_status": 400}
    idempotency_key = str(body.get("idempotencyKey") or "").strip()
    actor_id = str(body.get("actorId") or "user").strip() or "user"
    actor = {"type": "user", "id": actor_id}
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        meeting = store.get("meetings", {}).get(meeting_id)
        if not meeting:
            return {"error": "Executable meeting not found", "_status": 404}
        if meeting.get("stage") in _EXEC_MEETING_TERMINAL:
            return {"error": "Cannot target a terminal meeting", "stage": meeting.get("stage"), "_status": 409}
        if meeting.get("stage") != "awaiting_user_decision":
            return {"error": "Targeted questions are only allowed during the user decision window", "stage": meeting.get("stage"), "_status": 409}
        if target not in (meeting.get("participants") or []):
            return {"error": "Target participant is not in this meeting", "target": target, "_status": 400}
        idem_key = f"{meeting_id}:targeted:{idempotency_key}" if idempotency_key else ""
        if idem_key and idem_key in store.get("idempotency", {}):
            seq = store["idempotency"][idem_key].get("sequence")
            event = next((e for e in store.get("events", {}).get(meeting_id, []) if e.get("sequence") == seq), None)
            return {"ok": True, "meeting": meeting, "event": event, "idempotent": True}
        target_stage = meeting.get("decisionForStage") or meeting.get("previousStage") or meeting.get("stage")
        target_round = int(meeting.get("decisionForRound") or meeting.get("round") or 0)
        question_event = _append_exec_meeting_event(
            store,
            meeting,
            "targeted_question",
            actor=actor,
            payload={"target": target, "question": question, "actorId": actor_id, "stage": target_stage, "round": target_round},
            idempotency_key=idempotency_key,
        )
        prompt = _meeting_build_targeted_prompt(meeting, target, question, store.get("events", {}).get(meeting_id, []))
        pending = _append_exec_meeting_event(
            store,
            meeting,
            "provider_call_started",
            actor={"type": "agent", "id": target},
            payload={"speaker": target, "stage": target_stage, "round": target_round, "contextMode": meeting.get("contextMode"), "promptChars": len(prompt), "purpose": "targeted_response", "inReplyToSequence": question_event.get("sequence")},
        )
        if idem_key:
            store.setdefault("idempotency", {})[idem_key] = {"meetingId": meeting_id, "sequence": question_event["sequence"]}
        _save_exec_meeting_store(store)

    result = (_server_callable("_meeting_call_provider") or _meeting_call_provider)(meeting, target, prompt)

    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        meeting = store["meetings"][meeting_id]
        normalized = _meeting_normalize_provider_reply(result.get("reply") or "")
        if _meeting_provider_completion_should_be_ignored(meeting, target_stage, target_round):
            ignored = _append_ignored_provider_completion(store, meeting, target, result, normalized, pending, "meeting_state_changed", target_stage, target_round, kind="targeted_response")
            _save_exec_meeting_store(store)
            return {"ok": True, "meeting": meeting, "questionEvent": question_event, "ignored": ignored, "pending": pending}
        payload = {
            "kind": "targeted_response",
            "speaker": target,
            "targetQuestion": question,
            "text": normalized.get("text") or "",
            "rawText": normalized.get("rawText") or "",
            "structured": normalized.get("structured") or {},
            "parseError": normalized.get("parseError") or "",
            "ok": bool(result.get("ok")),
            "stage": target_stage,
            "round": target_round,
            "providerRef": result.get("providerRef") or _meeting_provider_ref(target),
            "conversationId": result.get("conversationId") or "",
            "durationMs": result.get("durationMs") or 0,
            "inReplyToSequence": pending.get("sequence"),
            "questionSequence": question_event.get("sequence"),
        }
        if normalized.get("providerRaw"):
            payload["providerRaw"] = normalized.get("providerRaw")
        turn = _append_exec_meeting_event(store, meeting, "participant_turn", actor={"type": "agent", "id": target}, payload=payload)
        meeting.setdefault("participantLastSeen", {})[target] = turn["sequence"]
        _meeting_update_rolling_summary(meeting, target, payload["text"])
        _save_exec_meeting_store(store)
        return {"ok": True, "meeting": meeting, "questionEvent": question_event, "event": turn, "pending": pending}

def _meeting_events_text(events):
    lines = []
    for event in events:
        payload = event.get("payload") or {}
        if event.get("type") == "participant_turn":
            lines.append(f"- seq {event.get('sequence')} {payload.get('speaker')}: {payload.get('text') or payload.get('reply') or ''}")
        elif event.get("type") == "user_intervention":
            parts = []
            if payload.get("text"):
                parts.append(f"user said: {payload.get('text')}")
            if payload.get("context"):
                parts.append(f"user added context: {payload.get('context')}")
            lines.append(f"- seq {event.get('sequence')} " + " | ".join(parts))
        elif event.get("type") == "targeted_question":
            lines.append(f"- seq {event.get('sequence')} user asked {payload.get('target')}: {payload.get('question') or ''}")
        elif event.get("type") == "agenda_change":
            reason = f" reason: {payload.get('reason')}" if payload.get("reason") else ""
            lines.append(f"- seq {event.get('sequence')} user changed agenda to: {payload.get('agenda') or ''}{reason}")
        elif event.get("type") == "arbitration_decision":
            lines.append(f"- seq {event.get('sequence')} user arbitration {payload.get('action')}: {payload.get('decision') or ''} {payload.get('rationale') or ''}".strip())
    return "\n".join(lines)

def _meeting_update_rolling_summary(meeting, speaker, text):
    current = str(meeting.get("rollingSummary") or "")
    addition = f"{speaker}: {str(text or '').strip()[:500]}"
    combined = (current + "\n" + addition).strip()
    meeting["rollingSummary"] = _meeting_truncate_text(combined, (meeting.get("contextBudget") or {}).get("maxSummaryChars", 3000))

def _meeting_strip_json_fence(text):
    raw = str(text or "").strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    return raw

def _meeting_parse_json_object(text):
    raw = _meeting_strip_json_fence(text)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except (TypeError, json.JSONDecodeError):
        pass
    for marker in ("{",):
        idx = raw.find(marker)
        while idx >= 0:
            try:
                parsed, _ = json.JSONDecoder().raw_decode(raw[idx:])
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                idx = raw.find(marker, idx + 1)
    return None

def _meeting_coerce_list(value):
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]

def _meeting_structured_display_text(structured):
    if not structured:
        return ""
    parts = []
    labels = [
        ("position", "Position"),
        ("reasoning", "Reasoning"),
        ("disagreements", "Disagreements"),
        ("questions", "Questions"),
        ("suggestedNextStep", "Suggested next step"),
        ("confidence", "Confidence"),
    ]
    for key, label in labels:
        value = structured.get(key)
        if isinstance(value, list):
            value = "; ".join([str(item) for item in value if str(item).strip()])
        if value:
            parts.append(f"{label}: {value}")
    return "\n".join(parts)

def _meeting_parse_structured_turn(text):
    parsed = _meeting_parse_json_object(text)
    if not parsed:
        return {}, "structured_json_not_found"
    structured = {}
    for raw_key, value in parsed.items():
        key = _MEETING_STRUCTURED_KEYS.get(str(raw_key))
        if not key:
            continue
        if key in {"disagreements", "questions"}:
            structured[key] = _meeting_coerce_list(value)
        else:
            structured[key] = str(value or "").strip()
    if not any(structured.values()):
        return {}, "structured_fields_missing"
    structured.setdefault("disagreements", [])
    structured.setdefault("questions", [])
    structured.setdefault("confidence", "")
    return structured, ""

def _meeting_extract_payload_text(obj):
    if not isinstance(obj, dict):
        return ""
    result = obj.get("result")
    candidates = []
    def add_payload_items(payload):
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    candidates.append(item.get("text") or item.get("content") or item.get("message") or "")
                else:
                    candidates.append(item)
        elif isinstance(payload, dict):
            candidates.append(payload.get("text") or payload.get("content") or payload.get("message") or "")
        elif isinstance(payload, str):
            candidates.append(payload)
    if isinstance(result, dict):
        add_payload_items(result.get("payload"))
        add_payload_items(result.get("payloads"))
        for key in ("text", "reply", "message", "content"):
            if result.get(key):
                candidates.append(result.get(key))
    add_payload_items(obj.get("payload"))
    add_payload_items(obj.get("payloads"))
    for key in ("text", "reply", "message", "content"):
        if obj.get(key):
            candidates.append(obj.get(key))
    return "\n".join([str(item).strip() for item in candidates if str(item or "").strip()]).strip()

def _meeting_provider_raw_summary(raw):
    if raw is None:
        return None
    try:
        encoded = json.dumps(raw, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        encoded = str(raw)
    return _meeting_truncate_text(encoded, 8000)

def _meeting_normalize_provider_reply(reply):
    raw_text = str(reply or "")
    provider_raw = None
    speaker_text = raw_text.strip()
    parsed = _meeting_parse_json_object(raw_text)
    if parsed and any(key in parsed for key in ("status", "result", "payload", "meta")):
        extracted = _meeting_extract_payload_text(parsed)
        if extracted:
            provider_raw = parsed
            speaker_text = extracted
    structured, parse_error = _meeting_parse_structured_turn(speaker_text)
    display_text = _meeting_structured_display_text(structured) if structured else speaker_text
    normalized = {
        "text": display_text,
        "rawText": speaker_text,
        "structured": structured,
        "parseError": parse_error,
    }
    raw_summary = _meeting_provider_raw_summary(provider_raw)
    if raw_summary:
        normalized["providerRaw"] = raw_summary
    return normalized

def _meeting_build_result_prompt(meeting, events):
    transcript = _meeting_events_text(events)
    policy = _meeting_resolution_policy(meeting.get("resolutionPolicy"))
    outcome_instruction = (
        "Outcome must be one of: approved, rejected, no_consensus, needs_user_decision. "
        "Use approved when the proposal or answer can be accepted, rejected when it should not pass, "
        "no_consensus when unresolved disagreements remain, and needs_user_decision only when a human decision is required. "
    )
    if policy == "moderator_decision":
        outcome_instruction += "This meeting uses moderator_decision policy, so choose approved, rejected, or no_consensus; do not use needs_user_decision unless essential.\n"
    else:
        outcome_instruction += "This meeting uses user_decision policy, so use needs_user_decision if the transcript still requires human arbitration.\n"
    return _meeting_truncate_text(
        "You are the meeting moderator. Summarize and close this meeting based only on the transcript below.\n"
        f"Meeting topic: {meeting.get('topic') or 'Untitled Meeting'}\n"
        f"Purpose: {meeting.get('purpose') or ''}\n"
        f"Type: {meeting.get('meetingType') or 'discussion'}\n"
        f"Resolution policy: {policy}\n"
        f"Participants: {', '.join(meeting.get('participants') or [])}\n\n"
        f"Transcript:\n{transcript or '(no participant turns yet)'}\n\n"
        "Return exactly one JSON object and no surrounding prose or Markdown fences. "
        + outcome_instruction +
        "Use this schema: {\"outcome\":\"approved|rejected|no_consensus|needs_user_decision\",\"summary\":\"...\",\"decision\":\"...\",\"rationale\":\"...\",\"unresolvedQuestions\":[\"...\"],"
        "\"disagreements\":[\"...\"],\"actionItems\":[{\"owner\":\"...\",\"item\":\"...\"}]}.\n",
        (meeting.get("contextBudget") or {}).get("maxPromptChars", 12000),
    )

def _meeting_result_outcome(raw):
    outcome = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "pass": "approved",
        "passed": "approved",
        "approve": "approved",
        "通过": "approved",
        "不通过": "rejected",
        "fail": "rejected",
        "failed": "rejected",
        "reject": "rejected",
        "rejected": "rejected",
        "无共识": "no_consensus",
        "no_consensus": "no_consensus",
        "needs_human": "needs_user_decision",
        "needs_user": "needs_user_decision",
        "user_decision": "needs_user_decision",
    }
    outcome = aliases.get(outcome, outcome)
    return outcome if outcome in {"approved", "rejected", "no_consensus", "needs_user_decision"} else ""

def _meeting_coerce_action_items(value):
    if not value:
        return []
    if not isinstance(value, list):
        value = [value]
    items = []
    for item in value:
        if isinstance(item, dict):
            owner = str(item.get("owner") or item.get("agent") or item.get("assignee") or "").strip()
            text = str(item.get("item") or item.get("text") or item.get("task") or item.get("action") or "").strip()
            if owner or text:
                items.append({"owner": owner, "item": text})
        else:
            text = str(item or "").strip()
            if text:
                items.append({"item": text})
    return items

def _meeting_parse_result(raw_text):
    parsed = _meeting_parse_json_object(raw_text)
    if not parsed:
        return {
            "outcome": "",
            "summary": _meeting_truncate_text(raw_text or "", 2000),
            "decision": "Meeting ended by user. Review transcript for final decision.",
            "rationale": "",
            "unresolvedQuestions": [],
            "disagreements": [],
            "actionItems": [],
            "parseError": "result_json_not_found",
        }
    return {
        "outcome": _meeting_result_outcome(parsed.get("outcome") or parsed.get("status") or parsed.get("result")),
        "summary": _meeting_truncate_text(str(parsed.get("summary") or ""), 2000),
        "decision": str(parsed.get("decision") or "").strip(),
        "rationale": str(parsed.get("rationale") or parsed.get("reasoning") or "").strip(),
        "unresolvedQuestions": _meeting_coerce_list(parsed.get("unresolvedQuestions") or parsed.get("unresolved_questions")),
        "disagreements": _meeting_coerce_list(parsed.get("disagreements")),
        "actionItems": _meeting_coerce_action_items(parsed.get("actionItems") or parsed.get("action_items")),
    }

def _meeting_fallback_result(meeting, events):
    turns = [e for e in events if e.get("type") == "participant_turn"]
    contributions = {}
    for turn in turns:
        payload = turn.get("payload") or {}
        speaker = payload.get("speaker")
        contributions.setdefault(speaker, [])
        contributions[speaker].append(payload.get("text") or "")
    return {
        "outcome": "approved",
        "summary": _meeting_truncate_text(meeting.get("rollingSummary") or "", 2000),
        "decision": "Meeting completed. Review transcript for final decision.",
        "rationale": "",
        "unresolvedQuestions": [],
        "disagreements": [],
        "contributions": {k: _meeting_truncate_text("\n".join(v), 1200) for k, v in contributions.items()},
        "actionItems": [],
    }

def _handle_executable_meeting_end_with_moderator(meeting_id, body=None):
    body = body or {}
    actor = {"type": str(body.get("actorType") or "user"), "id": str(body.get("actorId") or "user")}
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        meeting = store.get("meetings", {}).get(meeting_id)
        if not meeting:
            return {"error": "Executable meeting not found", "_status": 404}
        if meeting.get("stage") in _EXEC_MEETING_TERMINAL:
            return {"ok": True, "meeting": meeting, "alreadyTerminal": True}
        previous = meeting.get("stage")
        if "summarizing" not in _EXEC_MEETING_TRANSITIONS.get(previous, set()) and previous != "summarizing":
            return {"error": f"Cannot summarize meeting from {previous}", "stage": previous, "_status": 409}
        if previous != "summarizing":
            meeting["previousStage"] = previous
            meeting["stage"] = "summarizing"
            meeting["currentSpeaker"] = meeting.get("moderator") or (meeting.get("participants") or [""])[0]
            _append_exec_meeting_event(store, meeting, "meeting_transitioned", actor=actor, payload={"from": previous, "to": "summarizing", "reason": "user_end"})
            _save_exec_meeting_store(store)

    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        meeting = store["meetings"][meeting_id]
        events = list(store.get("events", {}).get(meeting_id, []))
        moderator = meeting.get("moderator") or (meeting.get("participants") or [""])[0]
        prompt = _meeting_build_result_prompt(meeting, events)
        pending = _append_exec_meeting_event(store, meeting, "provider_call_started", actor={"type": "agent", "id": moderator}, payload={"speaker": moderator, "stage": "summarizing", "round": meeting.get("round"), "contextMode": meeting.get("contextMode"), "promptChars": len(prompt), "purpose": "meeting_result"})
        _save_exec_meeting_store(store)

    result = (_server_callable("_meeting_call_provider") or _meeting_call_provider)(meeting, moderator, prompt)

    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        meeting = store["meetings"][meeting_id]
        normalized = _meeting_normalize_provider_reply(result.get("reply") or "")
        if meeting.get("stage") in _EXEC_MEETING_TERMINAL:
            pending_payload = pending.get("payload") if isinstance(pending.get("payload"), dict) else {}
            ignored = _append_ignored_provider_completion(
                store,
                meeting,
                moderator,
                result,
                normalized,
                pending,
                "meeting_state_changed",
                "summarizing",
                pending_payload.get("round", meeting.get("round")),
                kind="meeting_result",
            )
            _save_exec_meeting_store(store)
            return {"ok": True, "meeting": meeting, "ignored": ignored, "alreadyTerminal": True}
        moderator_payload = {
            "speaker": moderator,
            "text": normalized.get("text") or "",
            "rawText": normalized.get("rawText") or "",
            "structured": normalized.get("structured") or {},
            "parseError": normalized.get("parseError") or "",
            "ok": bool(result.get("ok")),
            "stage": "summarizing",
            "round": meeting.get("round"),
            "providerRef": result.get("providerRef") or _meeting_provider_ref(moderator),
            "conversationId": result.get("conversationId") or "",
            "durationMs": result.get("durationMs") or 0,
            "inReplyToSequence": pending.get("sequence"),
            "purpose": "meeting_result",
        }
        if normalized.get("providerRaw"):
            moderator_payload["providerRaw"] = normalized.get("providerRaw")
        _append_exec_meeting_event(store, meeting, "participant_turn", actor={"type": "agent", "id": moderator}, payload=moderator_payload)
        if not result.get("ok"):
            previous = meeting.get("stage")
            meeting["previousStage"] = previous
            meeting["stage"] = "awaiting_user_decision"
            meeting["currentSpeaker"] = ""
            meeting["moderatorFailure"] = {
                "reason": "moderator_failed",
                "moderator": moderator,
                "error": _meeting_truncate_text(normalized.get("text") or normalized.get("rawText") or result.get("reply") or "Moderator failed", 1000),
                "providerRef": moderator_payload.get("providerRef") or {},
                "failedAtSequence": meeting.get("lastEventSequence"),
            }
            meeting["decisionForStage"] = previous
            meeting["decisionForRound"] = int(meeting.get("round") or 0)
            meeting["decisionNextStage"] = "summarizing"
            meeting["decisionNextRound"] = int(meeting.get("round") or 0)
            meeting["decisionWindowSec"] = meeting.get("decisionWindowSec") or _meeting_decision_window_sec()
            _append_exec_meeting_event(store, meeting, "moderator_failure", actor={"type": "agent", "id": moderator}, payload=meeting["moderatorFailure"])
            _append_exec_meeting_event(store, meeting, "meeting_transitioned", actor={"type": "agent", "id": moderator}, payload={"from": previous, "to": "awaiting_user_decision", "reason": "moderator_failed"})
            _send_meeting_failure_notification(meeting, meeting["moderatorFailure"])
            _save_exec_meeting_store(store)
            return {"ok": False, "meeting": meeting, "events": store.get("events", {}).get(meeting_id, []), "moderatorFailure": meeting["moderatorFailure"]}
        events = list(store.get("events", {}).get(meeting_id, []))
        parsed_result = _meeting_parse_result(normalized.get("rawText") or normalized.get("text") or "")
        fallback = _meeting_fallback_result(meeting, events)
        final_result = {
            **fallback,
            **{k: v for k, v in parsed_result.items() if v not in ("", [], {})},
            "moderator": moderator,
            "moderatorProviderRef": moderator_payload.get("providerRef") or {},
        }
        meeting["result"] = final_result
        meeting["currentSpeaker"] = ""
        _append_exec_meeting_event(store, meeting, "meeting_result", actor={"type": "agent", "id": moderator}, payload=final_result)
        previous = meeting.get("stage")
        meeting["previousStage"] = previous
        meeting["stage"] = "completed"
        for participant in meeting.get("participants", []):
            store.get("occupancy", {}).pop(participant, None)
        _meeting_resume_original_work(store, meeting, "moderator_summary_complete")
        _award_meeting_participation_points(meeting)
        _append_exec_meeting_event(store, meeting, "meeting_transitioned", actor=actor, payload={"from": previous, "to": "completed", "reason": "moderator_summary_complete"})
        _save_exec_meeting_store(store)
        result_payload = {"ok": True, "meeting": meeting, "events": store.get("events", {}).get(meeting_id, [])}
    _project_execution_apply_meeting_result(meeting)
    _archive_trigger_meeting_conclusion(meeting)
    return result_payload

def _meeting_build_prompt(meeting, speaker, stage, events):
    budget = _meeting_context_budget(meeting.get("contextBudget"))
    mode = _meeting_context_mode(meeting.get("contextMode"))
    speaker_seen = int((meeting.get("participantLastSeen") or {}).get(speaker) or 0)
    topic = meeting.get("topic") or "Untitled Meeting"
    agenda = meeting.get("agenda") or topic
    fixed = (
        f"Meeting topic: {topic}\n"
        f"Current agenda: {agenda}\n"
        f"Purpose: {meeting.get('purpose') or ''}\n"
        f"Type: {meeting.get('meetingType') or 'discussion'}\n"
        f"Stage: {stage}\n"
        f"Round: {meeting.get('round') or 0} of {meeting.get('maxRounds') or 0}\n"
        f"You are: {speaker}\n"
        f"Moderator: {meeting.get('moderator') or ''}\n"
    )
    initial = _meeting_truncate_text(meeting.get("context") or "", budget["maxInitialContextChars"])
    all_events = _meeting_events_text(events)
    unseen_events = _meeting_events_text([e for e in events if int(e.get("sequence") or 0) > speaker_seen])
    recent_events = _meeting_events_text(events[-budget["maxRecentEvents"]:])
    summary = _meeting_truncate_text(meeting.get("rollingSummary") or "", budget["maxSummaryChars"])
    if mode == "full":
        body = f"{fixed}\nConfirmed context:\n{initial}\n\nFull transcript:\n{all_events}\n"
    elif mode == "summary":
        body = f"{fixed}\nConfirmed context:\n{initial}\n\nRolling summary:\n{summary}\n\nRelevant recent statements:\n{recent_events}\n"
    else:
        if speaker_seen <= 0:
            body = f"{fixed}\nConfirmed context:\n{initial}\n\nPrior meeting events:\n{recent_events}\n"
        else:
            body = f"{fixed}\nNew events since your last turn:\n{unseen_events or '(none)'}\n"
    instruction = (
        "\nInstruction:\n"
        "Contribute to the meeting. Avoid repeating previous points. "
        "Return exactly one JSON object and no surrounding prose or Markdown fences. "
        "Use this schema: {\"position\":\"...\",\"reasoning\":\"...\",\"disagreements\":[\"...\"],"
        "\"questions\":[\"...\"],\"suggestedNextStep\":\"...\",\"confidence\":\"high|medium|low\"}.\n"
    )
    prompt = body + instruction
    return _meeting_truncate_text(prompt, budget["maxPromptChars"])

def _meeting_provider_ref(agent_id):
    agent = _office_agent_lookup(agent_id) or {}
    return {
        "providerKind": agent.get("providerKind", "openclaw"),
        "agentId": agent.get("id") or agent_id,
        "providerAgentId": agent.get("providerAgentId") or agent.get("id") or agent_id,
    }

def _meeting_provider_timeout():
    raw = os.environ.get("VO_MEETING_PROVIDER_TIMEOUT_SEC") or "120"
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 120
    return max(5, min(value, 600))

def _meeting_call_provider(meeting, speaker, prompt):
    if os.environ.get("VO_MEETING_FAKE_PROVIDER"):
        return {
            "ok": True,
            "reply": json.dumps({
                "position": f"fake contribution from {speaker}",
                "reasoning": "deterministic Phase 2 fixture",
                "disagreements": [],
                "questions": [],
                "suggestedNextStep": "continue",
                "confidence": "high",
            }),
            "providerRef": {"providerKind": "fake", "agentId": speaker},
            "durationMs": 0,
            "conversationId": f"meeting:{meeting.get('id')}:participant:{speaker}",
        }
    conversation_id = f"meeting:{meeting.get('id')}:participant:{speaker}"
    started = time.time()
    agent = (_server_callable("_office_agent_lookup") or _office_agent_lookup)(speaker) or {}
    provider_kind = agent.get("providerKind", "openclaw")
    timeout = _meeting_provider_timeout()
    try:
        if provider_kind == "codex":
            result = (_server_callable("_handle_codex_chat") or _handle_codex_chat)({"agentId": speaker, "message": prompt, "conversationId": conversation_id, "timeoutSec": timeout, "fromType": "agent"})
            reply = result.get("reply") or result.get("error") or ""
            ok = bool(result.get("ok"))
            provider_ref = {"providerKind": "codex", "agentId": speaker, "conversationId": conversation_id, "threadId": result.get("threadId"), "turnId": result.get("turnId")}
        elif provider_kind == "hermes":
            result = (_server_callable("_handle_hermes_chat") or _handle_hermes_chat)({"agentId": speaker, "message": prompt, "conversationId": conversation_id, "timeoutSec": timeout, "fromType": "agent"})
            reply = result.get("reply") or result.get("error") or ""
            ok = bool(result.get("ok"))
            provider_ref = {"providerKind": "hermes", "agentId": speaker, "conversationId": conversation_id, "sessionId": result.get("sessionId")}
        elif provider_kind == "claude-code":
            result = (_server_callable("_handle_claude_code_chat") or _handle_claude_code_chat)({"agentId": speaker, "message": prompt, "conversationId": conversation_id, "timeoutSec": timeout, "fromType": "agent"})
            reply = result.get("reply") or result.get("error") or ""
            ok = bool(result.get("ok"))
            provider_ref = {"providerKind": "claude-code", "agentId": speaker, "conversationId": conversation_id, "sessionId": result.get("sessionId")}
        else:
            reply = (_server_callable("_wf_call_agent") or _wf_call_agent)(speaker, prompt, timeout=timeout, project_id="meeting-for-ai", task_id=conversation_id)
            ok = not str(reply or "").startswith("[ERROR]")
            provider_ref = {"providerKind": provider_kind, "agentId": speaker, "conversationId": conversation_id}
    except Exception as exc:
        ok = False
        reply = f"[ERROR] provider call failed for {speaker}: {exc}"
        provider_ref = {"providerKind": provider_kind, "agentId": speaker, "conversationId": conversation_id}
    return {"ok": ok, "reply": reply, "providerRef": provider_ref, "durationMs": int((time.time() - started) * 1000), "conversationId": conversation_id}

def _handle_executable_meeting_run(meeting_id, body=None):
    body = body or {}
    summarize_after_decision_window = False
    continue_after_provider_timeout_skip = False
    provider_timeout_skip_result = None
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        released = _release_timed_out_preparing_meetings(store)
        meeting = store.get("meetings", {}).get(meeting_id)
        if not meeting:
            if released:
                _save_exec_meeting_store(store)
            return {"error": "Executable meeting not found", "_status": 404}
        if released:
            _save_exec_meeting_store(store)
            if meeting.get("stage") in _EXEC_MEETING_TERMINAL:
                return {"ok": True, "meeting": meeting, "alreadyTerminal": True, "preparingTimedOut": meeting.get("cancelReason") == "preparing_timeout"}
        if meeting.get("stage") in _EXEC_MEETING_TERMINAL:
            return {"ok": True, "meeting": meeting, "alreadyTerminal": True}
        if meeting.get("stage") == "conflict" or _meeting_has_open_conflicts(meeting):
            return {"error": "Meeting has unresolved participant conflicts", "conflicts": meeting.get("conflicts") or [], "_status": 409}
        if str(body.get("action") or "") == "provider_timeout_skip":
            skipped = _meeting_skip_timed_out_provider_call(store, meeting, body.get("pendingSequence"))
            if not skipped.get("error"):
                _save_exec_meeting_store(store)
                if skipped.get("skipped") and not bool(body.get("_noAutoContinue")):
                    continue_after_provider_timeout_skip = True
                    provider_timeout_skip_result = dict(skipped)
                else:
                    return skipped
            else:
                return skipped
        if meeting.get("stage") == "summarizing":
            return {"ok": True, "meeting": meeting, "summarizing": True}
        if meeting.get("stage") == "awaiting_user_decision":
            deadline_raw = meeting.get("decisionDeadlineAt") or ""
            try:
                deadline_ts = datetime.fromisoformat(deadline_raw.replace("Z", "+00:00")).timestamp() if deadline_raw else 0
            except (TypeError, ValueError):
                deadline_ts = 0
            action = str(body.get("action") or "").strip()
            no_consensus_arbitration = (meeting.get("arbitration") or {}).get("reason") == "no_consensus"
            if no_consensus_arbitration and action == "timeout":
                _save_exec_meeting_store(store)
                return {"ok": True, "meeting": meeting, "awaitingUserDecision": True}
            should_auto_advance = action in {"continue", "timeout"} or (deadline_ts and time.time() >= deadline_ts)
            should_summarize_after_window = should_auto_advance and (meeting.get("decisionNextStage") == "summarizing")
            if action in {"continue", "timeout"} or (deadline_ts and time.time() >= deadline_ts):
                if no_consensus_arbitration and deadline_ts and time.time() >= deadline_ts and action != "continue":
                    _save_exec_meeting_store(store)
                    return {"ok": True, "meeting": meeting, "awaitingUserDecision": True}
                _meeting_continue_from_decision_window(store, meeting, reason="decision_timeout" if action == "timeout" or (deadline_ts and time.time() >= deadline_ts) else "user_continue")
                _save_exec_meeting_store(store)
                if should_summarize_after_window:
                    summarize_after_decision_window = True
            else:
                _save_exec_meeting_store(store)
                return {"ok": True, "meeting": meeting, "awaitingUserDecision": True}
        if not summarize_after_decision_window and meeting.get("stage") == "preparing":
            meeting["previousStage"] = "preparing"
            meeting["stage"] = "active_opening"
            _append_exec_meeting_event(store, meeting, "meeting_transitioned", payload={"from": "preparing", "to": "active_opening", "reason": "run"})
            _save_exec_meeting_store(store)
    if continue_after_provider_timeout_skip:
        continued = _handle_executable_meeting_run(meeting_id, {"_afterProviderTimeoutSkip": True})
        if isinstance(continued, dict):
            continued["skipped"] = True
            continued["timeoutSkipped"] = True
            if provider_timeout_skip_result:
                continued["event"] = provider_timeout_skip_result.get("event")
                continued["skipResult"] = provider_timeout_skip_result
        return continued
    if summarize_after_decision_window:
        return _handle_executable_meeting_end_with_moderator(meeting_id, {"actorId": "system", "actorType": "system"})

    participants = list(meeting.get("participants") or [])
    max_rounds = max(1, int(meeting.get("maxRounds") or 1))
    for stage, rounds in (("active_opening", 1), ("active_discussion", max_rounds)):
        for round_index in range(1, rounds + 1):
            with _EXEC_MEETING_LOCK:
                store = _load_exec_meeting_store()
                meeting = store["meetings"][meeting_id]
                if meeting.get("stage") in _EXEC_MEETING_TERMINAL or meeting.get("stage") == "paused":
                    _save_exec_meeting_store(store)
                    return {"ok": True, "meeting": meeting, "pausedOrTerminal": True, "events": store.get("events", {}).get(meeting_id, [])}
                if meeting.get("stage") == "awaiting_user_decision":
                    _save_exec_meeting_store(store)
                    return {"ok": True, "meeting": meeting, "awaitingUserDecision": True, "events": store.get("events", {}).get(meeting_id, [])}
                if stage == "active_opening" and meeting.get("stage") not in {"active_opening"}:
                    continue
                if stage == "active_discussion" and meeting.get("stage") not in {"active_opening", "active_discussion"}:
                    continue
                if stage == "active_discussion" and meeting.get("stage") == "active_opening":
                    meeting["previousStage"] = "active_opening"
                    meeting["stage"] = "active_discussion"
                    meeting["round"] = round_index
                    _append_exec_meeting_event(store, meeting, "meeting_transitioned", payload={"from": "active_opening", "to": "active_discussion", "reason": "opening_complete"})
                elif stage == "active_discussion":
                    meeting["round"] = round_index
                events = list(store.get("events", {}).get(meeting_id, []))
                if _meeting_formal_round_complete(events, stage, meeting.get("round"), participants):
                    _save_exec_meeting_store(store)
                    continue
                _save_exec_meeting_store(store)
            for speaker in participants:
                with _EXEC_MEETING_LOCK:
                    store = _load_exec_meeting_store()
                    meeting = store["meetings"][meeting_id]
                    events = list(store.get("events", {}).get(meeting_id, []))
                    if _meeting_formal_turn_exists(events, stage, meeting.get("round"), speaker):
                        continue
                    if _meeting_pending_formal_turn_exists(events, stage, meeting.get("round"), speaker):
                        continue
                    meeting["currentSpeaker"] = speaker
                    prompt = _meeting_build_prompt(meeting, speaker, stage, store.get("events", {}).get(meeting_id, []))
                    pending = _append_exec_meeting_event(store, meeting, "provider_call_started", actor={"type": "agent", "id": speaker}, payload={"speaker": speaker, "stage": stage, "round": meeting.get("round"), "contextMode": meeting.get("contextMode"), "promptChars": len(prompt)})
                    _save_exec_meeting_store(store)
                result = (_server_callable("_meeting_call_provider") or _meeting_call_provider)(meeting, speaker, prompt)
                with _EXEC_MEETING_LOCK:
                    store = _load_exec_meeting_store()
                    meeting = store["meetings"][meeting_id]
                    normalized = _meeting_normalize_provider_reply(result.get("reply") or "")
                    pending_payload = pending.get("payload") if isinstance(pending.get("payload"), dict) else {}
                    expected_round = pending_payload.get("round", meeting.get("round"))
                    if _meeting_provider_completion_should_be_ignored(meeting, stage, expected_round):
                        _append_ignored_provider_completion(store, meeting, speaker, result, normalized, pending, "meeting_state_changed", stage, expected_round)
                        _save_exec_meeting_store(store)
                        return {"ok": True, "meeting": meeting, "ignoredProviderCompletion": True, "events": store.get("events", {}).get(meeting_id, [])}
                    payload = {
                        "speaker": speaker,
                        "text": normalized.get("text") or "",
                        "rawText": normalized.get("rawText") or "",
                        "structured": normalized.get("structured") or {},
                        "parseError": normalized.get("parseError") or "",
                        "ok": bool(result.get("ok")),
                        "stage": stage,
                        "round": meeting.get("round"),
                        "providerRef": result.get("providerRef") or _meeting_provider_ref(speaker),
                        "conversationId": result.get("conversationId") or "",
                        "durationMs": result.get("durationMs") or 0,
                        "inReplyToSequence": pending.get("sequence"),
                    }
                    if normalized.get("providerRaw"):
                        payload["providerRaw"] = normalized.get("providerRaw")
                    event = _append_exec_meeting_event(store, meeting, "participant_turn", actor={"type": "agent", "id": speaker}, payload=payload)
                    meeting.setdefault("participantLastSeen", {})[speaker] = event["sequence"]
                    _meeting_update_rolling_summary(meeting, speaker, payload["text"])
                    _save_exec_meeting_store(store)
            with _EXEC_MEETING_LOCK:
                store = _load_exec_meeting_store()
                meeting = store["meetings"][meeting_id]
                if meeting.get("stage") in _EXEC_MEETING_TERMINAL or meeting.get("stage") == "paused":
                    _save_exec_meeting_store(store)
                    return {"ok": True, "meeting": meeting, "pausedOrTerminal": True, "events": store.get("events", {}).get(meeting_id, [])}
                next_stage = "active_discussion"
                next_round = 1
                if stage == "active_discussion":
                    if round_index < max_rounds:
                        next_round = round_index + 1
                        window_reason = "round_complete"
                    else:
                        next_stage = "summarizing"
                        next_round = round_index
                        window_reason = "no_consensus"
                else:
                    window_reason = "round_complete"
                _meeting_open_decision_window(store, meeting, stage, meeting.get("round"), next_stage, next_round, window_reason)
                _save_exec_meeting_store(store)
                return {"ok": True, "meeting": meeting, "awaitingUserDecision": True, "events": store.get("events", {}).get(meeting_id, [])}
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        meeting = store["meetings"][meeting_id]
        events = store.get("events", {}).get(meeting_id, [])
        meeting["currentSpeaker"] = ""
        meeting["previousStage"] = meeting.get("stage")
        meeting["stage"] = "summarizing"
        _append_exec_meeting_event(store, meeting, "meeting_transitioned", payload={"from": "active_discussion", "to": "summarizing", "reason": "rounds_complete"})
        turns = [e for e in events if e.get("type") == "participant_turn"]
        contributions = {}
        for turn in turns:
            speaker = (turn.get("payload") or {}).get("speaker")
            contributions.setdefault(speaker, [])
            contributions[speaker].append((turn.get("payload") or {}).get("text") or "")
        result = {
            "summary": _meeting_truncate_text(meeting.get("rollingSummary") or "", 2000),
            "decision": "Meeting completed. Review transcript for final decision.",
            "unresolvedQuestions": [],
            "disagreements": [],
            "contributions": {k: _meeting_truncate_text("\n".join(v), 1200) for k, v in contributions.items()},
            "actionItems": [],
        }
        meeting["result"] = result
        _append_exec_meeting_event(store, meeting, "meeting_result", payload=result)
        previous = meeting.get("stage")
        meeting["stage"] = "completed"
        _meeting_ensure_action_item_drafts(store, meeting)
        for participant in meeting.get("participants", []):
            store.get("occupancy", {}).pop(participant, None)
        _meeting_resume_original_work(store, meeting, "run_complete")
        _award_meeting_participation_points(meeting)
        _append_exec_meeting_event(store, meeting, "meeting_transitioned", payload={"from": previous, "to": "completed", "reason": "run_complete"})
        _save_exec_meeting_store(store)
        result_payload = {"ok": True, "meeting": meeting, "events": store.get("events", {}).get(meeting_id, [])}
    _project_execution_apply_meeting_result(meeting)
    _archive_trigger_meeting_conclusion(meeting)
    return result_payload

def _handle_executable_meeting_reconcile():
    with _EXEC_MEETING_LOCK:
        store = _load_exec_meeting_store()
        _release_timed_out_preparing_meetings(store)
        occupancy = _rebuild_exec_meeting_occupancy(store)
        non_terminal = [m for m in store.get("meetings", {}).values() if m.get("stage") not in _EXEC_MEETING_TERMINAL]
        _save_exec_meeting_store(store)
        return {"ok": True, "activeMeetings": len(non_terminal), "occupancy": occupancy}

def _handle_meeting_create(body):
    """Create/update a meeting in the canonical server-side status file."""
    topic = (body.get("topic") or "").strip()
    meet_id = (body.get("id") or "").strip()
    if not meet_id:
        meet_id = str(uuid.uuid4())[:8]
    meet_type = (body.get("type") or "").strip()
    agents = body.get("agents") or body.get("participants") or []
    organizer = (body.get("organizer") or "").strip()
    purpose = (body.get("purpose") or body.get("topic") or "").strip()
    kind = (body.get("kind") or "discussion").strip() or "discussion"

    if not topic:
        return {"error": "Meeting topic is required", "_status": 400}
    if not isinstance(agents, list) or len(agents) < 2:
        return {"error": "Meeting requires at least 2 agents", "_status": 400}

    clean_agents = [str(a).strip() for a in agents if str(a).strip()]
    if len(clean_agents) < 2:
        return {"error": "Meeting requires at least 2 valid agent keys", "_status": 400}

    if not organizer:
        organizer = clean_agents[0]

    if meet_type not in ("1on1", "group"):
        meet_type = "1on1" if len(clean_agents) == 2 else "group"

    data = _load_meetings_file()
    meetings = data.get("_meetings", [])
    if not isinstance(meetings, list):
        meetings = []
    meetings = [m for m in meetings if m.get("id") != meet_id]
    meeting = {
        "id": meet_id,
        "topic": topic,
        "purpose": purpose,
        "kind": kind,
        "type": meet_type,
        "organizer": organizer,
        "status": "active",
        "participants": clean_agents,
        "agents": clean_agents,
        "rules": {
            "mode": "discussion-not-work",
            "endWhen": "purpose-complete",
            "resumeStateAfterEnd": "working-or-idle"
        }
    }
    meetings.append(meeting)
    data["_meetings"] = meetings
    _save_meetings_file(data)
    gateway_presence.set_meetings(meetings)
    return {"ok": True, "meeting": meeting}

def _handle_meeting_end(body):
    """End one meeting by id. Requires a summary from the organizer."""
    meet_id = (body.get("id") or body.get("meetingId") or "").strip()
    if not meet_id:
        return {"error": "Meeting id is required", "_status": 400}

    summary = (body.get("summary") or "").strip()
    resolution = (body.get("resolution") or "").strip()
    ended_by = (body.get("endedBy") or body.get("organizer") or "").strip()
    action_items = body.get("actionItems") or []
    responses = body.get("responses") or {}  # {agentKey: "what they said"}

    data = _load_meetings_file()
    meetings = data.get("_meetings", [])
    if not isinstance(meetings, list):
        meetings = []

    # Find the meeting being ended
    ended_meeting = None
    for m in meetings:
        if m.get("id") == meet_id:
            ended_meeting = dict(m)
            break

    if not ended_meeting:
        detail = _handle_executable_meeting_detail(meet_id)
        if detail.get("ok"):
            return _handle_executable_meeting_end_with_moderator(meet_id, {"actorId": ended_by or "user", "actorType": "user"})
        return {"error": f"Meeting '{meet_id}' not found", "_status": 404}

    if not summary:
        return {"error": "A meeting summary is required to end the meeting", "_status": 400}

    # Build completed meeting record
    completed = dict(ended_meeting)
    completed["status"] = "completed"
    completed["endedBy"] = ended_by or completed.get("organizer", "unknown")
    completed["summary"] = summary
    completed["resolution"] = resolution
    completed["actionItems"] = action_items if isinstance(action_items, list) else []
    completed["responses"] = responses if isinstance(responses, dict) else {}
    completed["endedAt"] = int(time.time())

    # Remove from active meetings
    meetings = [m for m in meetings if m.get("id") != meet_id]
    data["_meetings"] = meetings

    # Store in meeting history
    history = data.get("_meetingHistory", [])
    if not isinstance(history, list):
        history = []
    history.append(completed)
    # Keep last 50 meetings in history
    if len(history) > 50:
        history = history[-50:]
    data["_meetingHistory"] = history

    _save_meetings_file(data)
    gateway_presence.set_meetings(meetings)
    return {"ok": True, "id": meet_id, "completed": completed}

def _handle_meeting_end_all():
    """End all meetings. Requires summaries per meeting or a bulk summary."""
    data = _load_meetings_file()
    data["_meetings"] = []
    _save_meetings_file(data)
    gateway_presence.set_meetings([])
    return {"ok": True}

def _handle_meeting_history_delete(meet_id):
    """Delete a completed meeting from history."""
    if not meet_id:
        return {"error": "Meeting id is required", "_status": 400}
    data = _load_meetings_file()
    history = data.get("_meetingHistory", [])
    if not isinstance(history, list):
        history = []
    before = len(history)
    history = [m for m in history if m.get("id") != meet_id]
    data["_meetingHistory"] = history
    _save_meetings_file(data)
    return {"ok": True, "removed": len(history) < before, "id": meet_id}

def _meeting_request_unresolved_for_task(req, project_id, task_id):
    if not isinstance(req, dict):
        return False
    source = req.get("source") or {}
    if source.get("projectId") != project_id or source.get("taskId") != task_id:
        return False
    if not req.get("blockingTask"):
        return False
    blocker = req.get("taskBlocker") or {}
    if blocker.get("resolvedAt"):
        return False
    return req.get("status") in {"pending", "confirmed", "rejected"} or blocker.get("status") in {"pending", "confirmed", "rejected", "needs_user_decision"}

def _meeting_request_resolve_task_blocker(request_id, status, extra=None):
    if not request_id:
        return {"ok": True, "skipped": True}
    with _MEETING_REQUEST_LOCK:
        store = _load_meeting_request_store()
        req = store.get("requests", {}).get(request_id)
        if not req:
            return {"ok": False, "error": "Meeting request not found", "_status": 404}
        now = _exec_meeting_now()
        req["taskBlocker"] = {**(req.get("taskBlocker") or {}), "status": status, "resolvedAt": now, "updatedAt": now, **(extra or {})}
        req["updatedAt"] = now
        _save_meeting_request_store(store)
        return {"ok": True, "request": _meeting_request_public(req)}

_wrap_exports()
_hydrate()
