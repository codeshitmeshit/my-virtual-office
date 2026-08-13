"""Meeting application facade extracted from the legacy server entry point.

The facade owns Meeting request, lifecycle, projection, prompt, and command
orchestration. Runtime collaborators are hydrated from ``server`` so transport
wiring and process-owned integrations remain injectable without importing the
entry point from focused ``app/services`` domain modules.
"""

from __future__ import annotations

import sys


__all__ = ['_exec_meeting_now', '_exec_meeting_parse_ts', '_meeting_preparing_timeout_sec', '_exec_meeting_empty_store', '_meeting_request_empty_store', '_meeting_request_clean_type', '_meeting_request_find_project_task', '_meeting_request_summary', '_meeting_request_context_candidates', '_meeting_request_public', '_meeting_request_processed', '_meeting_request_sort_key', '_meeting_request_sort_time', '_sort_meeting_requests', '_meeting_request_error', '_meeting_request_urgency', '_project_high_priority_ai_meeting_requires_confirmation', '_meeting_request_auto_confirm_reason', '_meeting_request_auto_confirm_label', '_meeting_request_log_auto_confirm_activity', '_meeting_request_notification_related', '_meeting_request_notification_details', '_send_meeting_request_notification', '_meeting_request_approved_notification_details', '_meeting_open_url', '_handle_meeting_request_create', '_meeting_request_list_filtered', '_handle_meeting_request_detail', '_meeting_request_selected_context', '_meeting_project_ref', '_handle_meeting_request_confirm', '_handle_meeting_request_reject', '_exec_meeting_clean_participants', '_exec_meeting_archive_manager_participants', '_exec_meeting_archive_manager_error', '_meeting_context_mode', '_meeting_resolution_policy', '_meeting_context_budget', '_meeting_decision_window_sec', '_meeting_clamped_decision_window_sec', '_meeting_truncate_text', '_exec_meeting_next_seq', '_append_exec_meeting_event', '_meeting_mark_preparing_started', '_release_timed_out_preparing_meetings', '_meeting_formal_turn_exists', '_meeting_pending_formal_turn_exists', '_meeting_provider_completion_should_be_ignored', '_meeting_project_work_map', '_meeting_pending_provider_agents', '_meeting_busy_context_for_agent', '_meeting_conflict_advisory', '_meeting_advisory_timeout', '_meeting_live_advisory_prompt', '_meeting_call_advisory_provider', '_meeting_normalize_advisory_reply', '_meeting_complete_live_advisories', '_meeting_build_conflicts', '_meeting_has_open_conflicts', '_meeting_original_work_snapshot', '_meeting_resume_original_work', '_meeting_find_pending_call', '_meeting_skip_timed_out_provider_call', '_meeting_formal_round_complete', '_meeting_has_substantive_disagreement', '_meeting_arbitration_snapshot', '_meeting_open_decision_window', '_meeting_continue_from_decision_window', '_rebuild_exec_meeting_occupancy', '_exec_meeting_pending_calls_projection', '_meeting_ensure_action_item_drafts', '_exec_meeting_project_active', '_exec_meeting_transcript_projection', '_exec_meeting_project_history', '_meeting_active_projection', '_meeting_history_projection', '_handle_executable_meeting_action_item', '_handle_executable_meeting_create', '_handle_executable_meeting_detail', '_handle_executable_meeting_conflict_action', '_handle_executable_meeting_transition', '_handle_executable_meeting_intervention', '_handle_executable_meeting_agenda_change', '_handle_executable_meeting_arbitration', '_handle_executable_meeting_moderator_takeover', '_meeting_build_targeted_prompt', '_handle_executable_meeting_targeted_question', '_meeting_events_text', '_meeting_update_rolling_summary', '_meeting_strip_json_fence', '_meeting_parse_json_object', '_meeting_coerce_list', '_meeting_structured_display_text', '_meeting_parse_structured_turn', '_meeting_extract_payload_text', '_meeting_provider_raw_summary', '_meeting_normalize_provider_reply', '_meeting_build_result_prompt', '_meeting_result_outcome', '_meeting_coerce_action_items', '_meeting_parse_result', '_meeting_fallback_result', '_handle_executable_meeting_end_with_moderator', '_meeting_build_prompt', '_meeting_provider_ref', '_meeting_provider_timeout', '_meeting_call_provider', '_handle_executable_meeting_run', '_handle_executable_meeting_reconcile', '_handle_meeting_create', '_handle_meeting_end', '_handle_meeting_end_all', '_handle_meeting_history_delete', '_meeting_request_unresolved_for_task', '_meeting_request_resolve_task_blocker', '_meeting_domain_repository', '_meeting_domain_file', '_meeting_domain_authority_status', '_is_meeting_domain_path', '_meeting_request_service_hooks', '_meeting_request_record_reconciliation', '_meeting_request_reconcile_project', '_meeting_request_reconciliation', '_deliver_meeting_notification', '_meeting_request_workflow', '_meeting_pending_formal_calls_for_round', '_meeting_pending_calls_for_purpose', '_append_ignored_provider_completion', '_meeting_history_summary_record', '_meeting_terminal_hooks', '_executable_meeting_commands', '_meeting_request_reset_project_task_blockers']


def _server_module():
    return sys.modules.get("server") or sys.modules.get("__main__")


_ORIGINAL_EXPORTS = {}


def _hydrate():
    server = _server_module()
    if server is None or server is sys.modules.get(__name__):
        return
    exported = set(__all__)
    for key, value in vars(server).items():
        if key.startswith("__") or key in {"_server_module", "_hydrate", "_wrap_exports"}:
            continue
        if key in exported and callable(value) and (
            getattr(value, "_service_wrapper", False) or getattr(value, "_service_wrapped", False)
        ):
            if key in _ORIGINAL_EXPORTS:
                globals()[key] = _ORIGINAL_EXPORTS[key]
            continue
        globals()[key] = value


def _wrap_exports():
    current = sys.modules[__name__]
    for name in __all__:
        value = globals().get(name)
        if not callable(value) or getattr(value, "_service_wrapped", False):
            continue
        _ORIGINAL_EXPORTS.setdefault(name, value)

        def make_wrapper(fn):
            def wrapper(*args, **kwargs):
                _hydrate()
                return fn(*args, **kwargs)
            wrapper.__name__ = fn.__name__
            wrapper.__doc__ = fn.__doc__
            wrapper.__dict__.update(getattr(fn, "__dict__", {}))
            wrapper._service_wrapped = True
            return wrapper

        setattr(current, name, make_wrapper(value))


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


def _meeting_domain_repository():
    key = os.path.realpath(STATUS_DIR)
    with _MEETING_DOMAIN_REPOSITORIES_LOCK:
        repository = _MEETING_DOMAIN_REPOSITORIES.get(key)
        if repository is None:
            repository = meeting_repository_service.MeetingDomainRepository(key)
            _MEETING_DOMAIN_REPOSITORIES[key] = repository
        return repository


def _meeting_domain_file():
    return os.path.join(STATUS_DIR, meeting_repository_service.UNIFIED_FILENAME)


def _meeting_domain_authority_status():
    repository = _meeting_domain_repository()
    state = "unified" if repository.ready() else repository.authority_state()
    if state == "migration_required":
        return {"ok": False, "code": "meeting_store_migration_required", "_status": 409}
    if state == "invalid":
        return {"ok": False, "code": "meeting_store_invalid", "_status": 500}
    return {"ok": True, "state": state, "schemaVersion": meeting_repository_service.SCHEMA_VERSION}


def _is_meeting_domain_path(path):
    parsed = urllib.parse.urlparse(str(path or "")).path
    return (
        parsed.startswith("/api/meetings")
        or parsed.endswith("/meeting-requests")
        or "/meeting-requests/" in parsed
    )


def _meeting_request_empty_store():
    return {"requests": {}, "idempotency": {}, "updatedAt": ""}


def _meeting_request_service_hooks():
    return meeting_requests_service.RequestHooks(
        now=_exec_meeting_now,
        new_id=lambda: str(uuid.uuid4()),
        clean_participants=_exec_meeting_clean_participants,
        participant_error=_system_agent_meeting_error,
        auto_confirm_label=_meeting_request_auto_confirm_label,
        lifecycle_hooks=meeting_lifecycle_service.CreateHooks(
            rebuild_occupancy=_rebuild_exec_meeting_occupancy,
            build_conflicts=_meeting_build_conflicts,
            append_event=_append_exec_meeting_event,
        ),
    )


def _meeting_request_record_reconciliation(request_id, operation, failure, context=None):
    return _meeting_request_reconciliation().record(request_id, operation, failure, context)


def _meeting_request_reconcile_project(request_id):
    return _meeting_request_reconciliation().reconcile(request_id)


def _meeting_request_reconciliation():
    return meeting_request_reconciliation.MeetingRequestReconciliation(
        meeting_request_reconciliation.ReconciliationPorts(
            repository=_meeting_domain_repository(), now=_exec_meeting_now,
            summarize=_meeting_request_summary,
            block_project=_project_execution_block_for_meeting_request,
            update_blocker=_project_execution_update_meeting_blocker,
            apply_meeting_result=_project_execution_apply_meeting_result,
        )
    )


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
    return urgency_score(raw)


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


def _deliver_meeting_notification(entity_kind, entity_id, intent):
    mutate = _meeting_domain_repository().mutate_request if entity_kind == "request" else _meeting_domain_repository().mutate_meeting
    _, staged = mutate(
        entity_id,
        lambda data: meeting_notifications_service.stage(
            data, entity_kind, entity_id, intent, _exec_meeting_now(),
        )
    )
    if staged.get("status") == "skipped_duplicate":
        return staged
    if not staged.get("ok"):
        return staged
    try:
        notifications_cfg = VO_CONFIG.get("notifications", {}) or {}
        result = send_notification_card(
            notification_config=notifications_cfg,
            base_app_config=_feishu_app_send_config(notifications_cfg),
            send=(
                send_feishu_notification
                if send_feishu_notification is not _DEFAULT_FEISHU_NOTIFICATION_SENDER
                else None
            ),
            intent=staged["intent"],
            webhook_url=notifications_cfg.get("feishuWebhook") or None,
            status_dir=STATUS_DIR,
        )
    except Exception as exc:
        result = {"ok": False, "status": "delivery_failed", "error": _project_execution_redact(str(exc))}
    try:
        mutate(
            entity_id,
            lambda data: meeting_notifications_service.mark(
                data, entity_kind, entity_id, staged["dedupeKey"], result, _exec_meeting_now(),
            )
        )
    except (OSError, meeting_repository_service.MeetingStoreError):
        pass
    return result


def _send_meeting_request_notification(req, state="pending", *, summary="", actions=None, details=None):
    if not isinstance(req, dict):
        return {"ok": True, "status": "skipped_invalid_request"}
    proposal = req.get("originalProposal") if isinstance(req.get("originalProposal"), dict) else {}
    conversion = req.get("conversion") if isinstance(req.get("conversion"), dict) else {}
    request_status = str(req.get("status") or "")
    if actions is None:
        if state == "pending" and request_status == "pending" and not conversion.get("meetingId"):
            actions = [
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
            ]
        else:
            meeting_id = str(conversion.get("meetingId") or "")
            actions = [{
                "category": "jump",
                "text": "查看会议" if meeting_id else "查看详情",
                "url": _meeting_open_url(meeting_id) if meeting_id else _vo_public_url("/#projects"),
            }]
    intent = meeting_notifications_service.request_intent(
        req, state, summary=summary, actions=actions,
        details=details if details is not None else _meeting_request_notification_details(req),
    )
    return _deliver_meeting_notification("request", str(req.get("id") or ""), intent)


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


def _meeting_request_workflow():
    return meeting_request_workflow.MeetingRequestWorkflow(meeting_request_workflow.MeetingRequestPorts(
        repository=_meeting_domain_repository(),
        find_project_task=_meeting_request_find_project_task,
        context_candidates=_meeting_request_context_candidates,
        request_hooks=_meeting_request_service_hooks,
        participant_error=_exec_meeting_archive_manager_error,
        block_project=_project_execution_block_for_meeting_request,
        update_blocker=_project_execution_update_meeting_blocker,
        record_reconciliation=_meeting_request_record_reconciliation,
        reconcile_project=_meeting_request_reconcile_project,
        auto_confirm_reason=_meeting_request_auto_confirm_reason,
        send_notification=_send_meeting_request_notification,
        project_ref=_meeting_project_ref,
        preparing_timeout=_meeting_preparing_timeout_sec,
        decision_window=lambda: _meeting_clamped_decision_window_sec(_meeting_decision_window_sec()),
        context_budget=_meeting_context_budget,
        new_id=lambda: str(uuid.uuid4()),
        log_auto_confirm=_meeting_request_log_auto_confirm_activity,
        approved_details=_meeting_request_approved_notification_details,
        meeting_open_url=_meeting_open_url,
        run_meeting=_handle_executable_meeting_run,
        now=_exec_meeting_now,
        task_comment=_handle_task_comment,
        notification_details=_meeting_request_notification_details,
    ))


def _handle_meeting_request_create(project_id, task_id, body):
    return _meeting_request_workflow().create(project_id, task_id, body)


def _meeting_request_list_filtered(query_string=""):
    parsed = urllib.parse.parse_qs(query_string or "")
    status_filter = (parsed.get("status") or [""])[0]
    project_id = (parsed.get("projectId") or [""])[0]
    task_id = (parsed.get("taskId") or [""])[0]
    return _meeting_request_workflow().list(status=status_filter, project_id=project_id, task_id=task_id)


def _handle_meeting_request_detail(request_id):
    return _meeting_request_workflow().detail(request_id)


def _handle_meeting_request_confirm(request_id, body):
    return _meeting_request_workflow().confirm(request_id, body)


def _handle_meeting_request_reject(request_id, body):
    return _meeting_request_workflow().reject(request_id, body)


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
    return meeting_lifecycle_service.release_timed_out_preparing(
        store, now_timestamp=now_dt.timestamp(), now_iso=now_dt.isoformat(),
        timeout_seconds=_meeting_preparing_timeout_sec(),
        hooks=meeting_lifecycle_service.TimeoutHooks(
            append_event=_append_exec_meeting_event, parse_timestamp=_exec_meeting_parse_ts,
        ),
    )


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


def _meeting_pending_formal_calls_for_round(events, stage, round_value):
    pending_calls = []
    for call in _exec_meeting_pending_calls_projection(events or []):
        if call.get("purpose"):
            continue
        if call.get("stage") == stage and int(call.get("round") or 0) == int(round_value or 0):
            pending_calls.append(call)
    return pending_calls


def _meeting_pending_calls_for_purpose(events, stage, round_value, purpose):
    pending_calls = []
    for call in _exec_meeting_pending_calls_projection(events or []):
        if call.get("purpose") != purpose:
            continue
        if call.get("stage") == stage and int(call.get("round") or 0) == int(round_value or 0):
            pending_calls.append(call)
    return pending_calls


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
    return meeting_prompt_documents.live_advisory_prompt(
        meeting=meeting,
        conflict=conflict,
        occupied_meeting_id=occupied_meeting,
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
        return _meeting_call_provider(pseudo_meeting, agent_id, prompt)
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
    meeting = _meeting_domain_repository().get_meeting(meeting_id)
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
        def commit(store):
            meeting = store.get("meetings", {}).get(meeting_id)
            if not meeting or meeting.get("stage") in _EXEC_MEETING_TERMINAL:
                return None
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
            return meeting
        _meeting_domain_repository().mutate_meeting(meeting_id, commit)
    return _meeting_domain_repository().get_meeting(meeting_id)


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


def _append_ignored_provider_completion(store, meeting, speaker, result, normalized, pending, reason, expected_stage, expected_round, kind=""):
    payload = {
        "speaker": speaker,
        "kind": kind,
        "reason": reason,
        "expectedStage": expected_stage,
        "expectedRound": expected_round,
        "currentStage": meeting.get("stage"),
        "currentRound": meeting.get("round"),
        "text": normalized.get("text") or "",
        "rawText": normalized.get("rawText") or "",
        "structured": normalized.get("structured") or {},
        "parseError": normalized.get("parseError") or "",
        "ok": bool(result.get("ok")),
        "providerRef": result.get("providerRef") or _meeting_provider_ref(speaker),
        "conversationId": result.get("conversationId") or "",
        "durationMs": result.get("durationMs") or 0,
        "inReplyToSequence": pending.get("sequence") if pending else None,
    }
    if normalized.get("providerRaw"):
        payload["providerRaw"] = normalized.get("providerRaw")
    return _append_exec_meeting_event(store, meeting, "provider_call_ignored", actor={"type": "agent", "id": speaker}, payload=payload)


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
    return meeting_lifecycle_service.rebuild_occupancy(store)


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
        elif event_type in {"participant_turn", "provider_call_ignored"}:
            in_reply_to = payload.get("inReplyToSequence")
            if in_reply_to in pending:
                pending.pop(in_reply_to, None)
    return list(pending.values())


def _meeting_ensure_action_item_drafts(store, meeting):
    if not isinstance(meeting, dict): return []
    return meeting_action_items_service.ensure_drafts(
        store, meeting,
        meeting_action_items_service.ActionHooks(now=_exec_meeting_now, append_event=_append_exec_meeting_event),
    )


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
        "context": meeting.get("context") or "",
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
        **({"moderatorFailure": meeting.get("moderatorFailure") or {}} if meeting.get("moderatorFailure") else {}),
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
        elif event.get("type") == meeting_human_decision_projection_service.EVENT_TYPE:
            projected = meeting_human_decision_projection_service.project_transcript_event(event)
            if projected is not None:
                transcript.append(projected)
    return transcript


def _exec_meeting_project_history(meeting, events=None, summary=False):
    if summary:
        participants = meeting.get("participants", [])
        result = meeting.get("result") or {}
        return {
            "id": meeting.get("id"),
            "topic": meeting.get("topic", "Untitled Meeting"),
            "agenda": meeting.get("agenda") or meeting.get("topic", "Untitled Meeting"),
            "purpose": meeting.get("purpose", ""),
            "kind": meeting.get("meetingType", meeting.get("kind", "discussion")),
            "type": "group" if len(participants) > 2 else "1on1",
            "organizer": meeting.get("organizer", ""),
            "projectId": meeting.get("projectId", ""),
            "projectTitle": meeting.get("projectTitle", ""),
            "source": meeting.get("source") or {},
            "urgency": (meeting.get("source") or {}).get("urgency") or meeting.get("urgency"),
            "status": "completed" if meeting.get("stage") == "completed" else meeting.get("stage"),
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
            "summary": result.get("summary", ""),
            "resolution": result.get("decision", ""),
            "result": {"summary": result.get("summary", ""), "decision": result.get("decision", "")},
            "actionItems": [],
            "actionItemDrafts": [],
            "transcript": [],
            "pendingCalls": [],
            "originalWork": {},
            "detailLoaded": False,
            "endedAt": int(datetime.fromisoformat(meeting.get("updatedAt").replace("Z", "+00:00")).timestamp()) if meeting.get("updatedAt") else int(time.time()),
        }
    projected = _exec_meeting_project_active(meeting, events or [])
    projected["status"] = "completed" if meeting.get("stage") == "completed" else meeting.get("stage")
    projected["summary"] = (meeting.get("result") or {}).get("summary", "")
    projected["resolution"] = (meeting.get("result") or {}).get("decision", "")
    projected["actionItems"] = (meeting.get("result") or {}).get("actionItems", [])
    projected["actionItemDrafts"] = meeting.get("actionItemDrafts") or []
    projected["transcript"] = _exec_meeting_transcript_projection(events or [])
    projected["endedAt"] = int(datetime.fromisoformat(meeting.get("updatedAt").replace("Z", "+00:00")).timestamp()) if meeting.get("updatedAt") else int(time.time())
    return projected


def _meeting_history_summary_record(record):
    if not isinstance(record, dict):
        return record
    projected = dict(record)
    projected.pop("context", None)
    projected.pop("initialContext", None)
    projected.pop("originalContext", None)
    projected.pop("confirmedContext", None)
    projected.pop("originalWork", None)
    projected["transcript"] = []
    projected["pendingCalls"] = []
    projected["detailLoaded"] = False
    return projected


def _meeting_active_projection():
    data = _load_meetings_file()
    active = data.get("_meetings", [])
    if not isinstance(active, list):
        active = []
    _meeting_domain_repository().mutate_preparing_meetings(_release_timed_out_preparing_meetings)
    exec_active = [
        _exec_meeting_project_active(meeting, events)
        for meeting, events in _meeting_domain_repository().list_meetings_with_events(terminal=False)
    ]
    return active + exec_active


def _meeting_history_projection(summary=False):
    data = _load_meetings_file()
    history = data.get("_meetingHistory", [])
    if not isinstance(history, list):
        history = []
    if summary:
        history = [_meeting_history_summary_record(item) for item in history]
    with _EXEC_MEETING_LOCK:
        exec_history = [
            _exec_meeting_project_history(meeting, events, summary=summary)
            for meeting, events in _meeting_domain_repository().list_meetings_with_events(terminal=True)
        ]
    return history + exec_history


def _handle_executable_meeting_action_item(meeting_id, action_item_id, body):
    hooks = meeting_action_items_service.ActionHooks(now=_exec_meeting_now, append_event=_append_exec_meeting_event)
    _, prepared = _meeting_domain_repository().mutate_meeting(
        meeting_id,
        lambda data: meeting_action_items_service.mutate_command(data, meeting_id, action_item_id, body, hooks)
    )
    if not prepared.get("ok") or not prepared.get("prepared"):
        return prepared
    project_id = prepared.get("targetProjectId"); task_id = prepared.get("targetTaskId") or prepared.get("sourceTaskId")
    if not project_id or not task_id:
        return {"error": "Meeting action items must be attached to an existing project task", "code": "source_task_required", "_status": 400}
    def attach(project):
        result = meeting_action_items_service.attach_to_project(
            project, task_id, prepared["meeting"], prepared["actionItem"], action_item_id,
            prepared["actorId"], prepared["before"], _proj_now(),
        )
        if result.get("ok") and not result.get("idempotent"):
            _log_activity(
                project, "meeting_action_item_attached", prepared["actorId"] or "meeting",
                f"Attached meeting action item '{result['record'].get('title')}' to existing project task", task_id,
            )
        return result
    try:
        project_result = _PROJECT_REPOSITORY.update(project_id, attach)
    except ProjectNotFoundError:
        return {"error": "Project not found", "_status": 404}
    except ProjectConflictError:
        return {"error": "Project changed while confirming action item", "code": "project_action_item_conflict", "_status": 409}
    if not project_result.get("ok"):
        return project_result
    try:
        _, committed = _meeting_domain_repository().mutate_meeting(
            meeting_id,
            lambda data: meeting_action_items_service.commit_confirmation(
                data, meeting_id, action_item_id, prepared, project_result, hooks,
            )
        )
    except (OSError, meeting_repository_service.MeetingStoreError):
        return {
            "error": "Project action item was created but Meeting confirmation is pending retry",
            "code": "action_item_commit_pending", "_status": 503,
            "taskId": (project_result.get("task") or {}).get("id"),
            "meetingActionItemId": (project_result.get("record") or {}).get("id"),
        }
    if not committed.get("ok"):
        return {
            "error": "Project action item was created but Meeting confirmation is pending retry",
            "code": "action_item_commit_pending", "_status": 503,
            "reasonCode": committed.get("code") or "meeting_confirmation_failed",
            "taskId": (project_result.get("task") or {}).get("id"),
            "meetingActionItemId": (project_result.get("record") or {}).get("id"),
        }
    return committed


def _handle_executable_meeting_create(body):
    return _executable_meeting_commands().create(body)


def _handle_executable_meeting_detail(meeting_id):
    return _executable_meeting_commands().detail(meeting_id)


def _handle_executable_meeting_conflict_action(meeting_id, body):
    return _executable_meeting_commands().conflict_action(meeting_id, body)


def _handle_executable_meeting_transition(meeting_id, body):
    return _executable_meeting_commands().transition(meeting_id, body)


def _meeting_terminal_hooks():
    return meeting_lifecycle_service.TerminalHooks(
        append_event=_append_exec_meeting_event,
        resume_original_work=_meeting_resume_original_work,
        ensure_action_items=_meeting_ensure_action_item_drafts,
        award_points=_award_meeting_participation_points,
    )


def _executable_meeting_commands():
    return executable_meeting_commands.ExecutableMeetingCommands(
        executable_meeting_commands.ExecutableMeetingPorts(
            lock=_EXEC_MEETING_LOCK,
            repository=_meeting_domain_repository(),
            clean_participants=_exec_meeting_clean_participants,
            participant_error=_system_agent_meeting_error,
            participant_error_response=_exec_meeting_archive_manager_error,
            project_ref=_meeting_project_ref,
            now=_exec_meeting_now,
            new_id=lambda: str(uuid.uuid4()),
            decision_window=lambda raw: _meeting_clamped_decision_window_sec(raw or _meeting_decision_window_sec()),
            resolution_policy=_meeting_resolution_policy,
            context_mode=_meeting_context_mode,
            context_budget=_meeting_context_budget,
            preparing_timeout=_meeting_preparing_timeout_sec,
            rebuild_occupancy=_rebuild_exec_meeting_occupancy,
            build_conflicts=_meeting_build_conflicts,
            append_event=_append_exec_meeting_event,
            complete_live_advisories=_meeting_complete_live_advisories,
            ensure_action_items=_meeting_ensure_action_item_drafts,
            release_timed_out=_release_timed_out_preparing_meetings,
            project_history=_exec_meeting_project_history,
            project_active=_exec_meeting_project_active,
            busy_context=_meeting_busy_context_for_agent,
            advisory=_meeting_conflict_advisory,
            original_work_snapshot=_meeting_original_work_snapshot,
            has_open_conflicts=_meeting_has_open_conflicts,
            mark_preparing=_meeting_mark_preparing_started,
            continue_decision=_meeting_continue_from_decision_window,
            resume_original_work=_meeting_resume_original_work,
            award_points=_award_meeting_participation_points,
            apply_project_result=_project_execution_apply_meeting_result,
        )
    )


def _handle_executable_meeting_intervention(meeting_id, body):
    return _executable_meeting_commands().intervention(meeting_id, body)


def _handle_executable_meeting_agenda_change(meeting_id, body):
    return _executable_meeting_commands().agenda_change(meeting_id, body)


def _handle_executable_meeting_arbitration(meeting_id, body):
    hooks = meeting_lifecycle_service.ArbitrationHooks(
        append_event=_append_exec_meeting_event,
        continue_decision=_meeting_continue_from_decision_window,
        fallback_result=_meeting_fallback_result,
        truncate=_meeting_truncate_text,
        terminal=_meeting_terminal_hooks(),
    )
    _, result = _meeting_domain_repository().mutate_meeting(
        meeting_id,
        lambda store: meeting_lifecycle_service.arbitration_command(store, meeting_id, body, hooks),
    )
    meeting = result.get("meeting")
    if result.pop("invokeModerator", False):
        summarized = _handle_executable_meeting_end_with_moderator(
            meeting_id, {"actorId": str(body.get("actorId") or "user"), "actorType": "user"},
        )
        if isinstance(summarized, dict):
            summarized["event"] = result.get("event")
        return summarized
    if result.get("ok") and meeting and meeting.get("stage") == "completed":
        _project_execution_apply_meeting_result(meeting)
        _archive_trigger_meeting_conclusion(meeting)
    return result


def _handle_executable_meeting_moderator_takeover(meeting_id, body):
    hooks = meeting_lifecycle_service.TakeoverHooks(
        append_event=_append_exec_meeting_event,
        fallback_result=_meeting_fallback_result,
        normalize_outcome=_meeting_result_outcome,
        terminal=_meeting_terminal_hooks(),
    )
    def mutate(store):
        result = meeting_lifecycle_service.moderator_takeover_command(store, meeting_id, body, hooks)
        if result.get("ok"):
            result["events"] = store.get("events", {}).get(meeting_id, [])
        return result
    _, result = _meeting_domain_repository().mutate_meeting(meeting_id, mutate)
    meeting = result.get("meeting")
    if result.pop("invokeModerator", False):
        summarized = _handle_executable_meeting_end_with_moderator(
            meeting_id,
            {"actorId": str(body.get("actorId") or "user"), "actorType": str(body.get("actorType") or "user")},
        )
        if summarized.get("ok"):
            summarized["takeoverEvent"] = result.get("event")
        return summarized
    if result.get("ok") and meeting and meeting.get("stage") == "completed":
        source = meeting.get("source") if isinstance(meeting.get("source"), dict) else {}
        print(
            "[MEETING] moderator user takeover completed "
            f"meeting={meeting_id} outcome={(meeting.get('result') or {}).get('outcome')} "
            f"project={meeting.get('projectId') or source.get('projectId') or ''} task={source.get('taskId') or ''}"
        )
        _project_execution_apply_meeting_result(meeting)
        _archive_trigger_meeting_conclusion(meeting)
    return result


def _meeting_build_targeted_prompt(meeting, speaker, question, events):
    budget = _meeting_context_budget(meeting.get("contextBudget"))
    mode = _meeting_context_mode(meeting.get("contextMode"))
    speaker_seen = int((meeting.get("participantLastSeen") or {}).get(speaker) or 0)
    recent = _meeting_events_text(events[-budget["maxRecentEvents"]:])
    unseen = _meeting_events_text([event for event in events if int(event.get("sequence") or 0) > speaker_seen])
    context_values = {
        "confirmed_context": _meeting_truncate_text(meeting.get("context") or "", budget["maxInitialContextChars"]),
        "relevant_events": recent if mode != "incremental" or speaker_seen <= 0 else (unseen or "(none)"),
    }
    prompt = meeting_prompt_documents.turn_prompt(
        meeting=meeting,
        speaker=speaker,
        stage=meeting.get("decisionForStage") or meeting.get("stage"),
        context_values=context_values,
        targeted_question=_meeting_truncate_text(question, 2000),
    )
    return _meeting_truncate_text(prompt, budget["maxPromptChars"])


def _handle_executable_meeting_targeted_question(meeting_id, body):
    hooks = meeting_lifecycle_service.TargetedQuestionHooks(
        append_event=_append_exec_meeting_event,
        build_prompt=_meeting_build_targeted_prompt,
        normalize_reply=_meeting_normalize_provider_reply,
        provider_ref=_meeting_provider_ref,
        append_ignored=_append_ignored_provider_completion,
        update_summary=_meeting_update_rolling_summary,
    )
    _, prepared = _meeting_domain_repository().mutate_meeting(
        meeting_id,
        lambda store: meeting_lifecycle_service.prepare_targeted_question(store, meeting_id, body, hooks),
    )
    if not prepared.get("ok") or prepared.get("idempotent"):
        return prepared
    result = _meeting_call_provider(prepared["meeting"], prepared["target"], prepared["prompt"])
    _, committed = _meeting_domain_repository().mutate_meeting(
        meeting_id,
        lambda store: meeting_lifecycle_service.commit_targeted_question(
            store, meeting_id, prepared, result, hooks,
        ),
    )
    return committed


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
        elif event.get("type") == meeting_human_decision_projection_service.EVENT_TYPE:
            projected = meeting_human_decision_projection_service.format_agent_history_event(event)
            if projected:
                lines.append(f"- seq {event.get('sequence')} {projected}")
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
    outcome_rule = (
        "Outcome must be one of: approved, rejected, no_consensus, needs_user_decision. Use approved when the proposal or answer can be accepted, rejected when it should not pass, no_consensus when unresolved disagreements remain, and needs_user_decision only when a human decision is required."
    )
    if policy == "moderator_decision":
        policy_rule = "This meeting uses moderator_decision policy, so choose approved, rejected, or no_consensus; do not use needs_user_decision unless essential."
    else:
        policy_rule = "This meeting uses user_decision policy, so use needs_user_decision if the transcript still requires human arbitration."
    return _meeting_truncate_text(
        meeting_prompt_documents.result_prompt(
            meeting=meeting,
            transcript=transcript,
            policy=policy,
            outcome_rule=outcome_rule,
            policy_rule=policy_rule,
        ) + "\n",
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
    hooks = meeting_lifecycle_service.ModeratorHooks(
        append_event=_append_exec_meeting_event,
        build_prompt=_meeting_build_result_prompt,
        pending_calls=_meeting_pending_calls_for_purpose,
        normalize_reply=_meeting_normalize_provider_reply,
        parse_result=_meeting_parse_result,
        fallback_result=_meeting_fallback_result,
        provider_ref=_meeting_provider_ref,
        append_ignored=_append_ignored_provider_completion,
        terminal=_meeting_terminal_hooks(),
    )
    with _meeting_domain_repository().edit_meeting(meeting_id) as store:
        prepared = meeting_lifecycle_service.prepare_moderator_summary(store, meeting_id, actor, hooks)
        if not prepared.get("ok") or prepared.get("alreadyTerminal") or prepared.get("providerCallPending"):
            return prepared
    provider_result = _meeting_call_provider(prepared["meeting"], prepared["moderator"], prepared["prompt"])
    decision_window = _meeting_clamped_decision_window_sec(
        prepared["meeting"].get("decisionWindowSec") or _meeting_decision_window_sec()
    )
    failure_deadline = datetime.fromtimestamp(time.time() + decision_window, timezone.utc).isoformat()
    with _meeting_domain_repository().edit_meeting(meeting_id) as store:
        committed = meeting_lifecycle_service.commit_moderator_summary(
            store, meeting_id, prepared, provider_result, actor,
            failure_deadline=failure_deadline, decision_window_seconds=decision_window, hooks=hooks,
        )
        meeting = committed.get("meeting")
        if committed.get("ok") and meeting and meeting.get("stage") == "completed":
            meeting.pop("moderatorFailure", None)
            if isinstance(store.get("meetings"), dict) and isinstance(store["meetings"].get(meeting_id), dict):
                store["meetings"][meeting_id].pop("moderatorFailure", None)
                meeting = store["meetings"][meeting_id]
                committed["meeting"] = meeting
        committed["events"] = store.get("events", {}).get(meeting_id, [])
    if committed.get("notifyFailure"):
        _send_meeting_failure_notification(meeting, committed.get("moderatorFailure") or {})
        committed.pop("notifyFailure", None)
        return committed
    if committed.get("ok") and meeting and meeting.get("stage") == "completed":
        _project_execution_apply_meeting_result(meeting)
        _archive_trigger_meeting_conclusion(meeting)
    return committed


def _meeting_build_prompt(meeting, speaker, stage, events):
    budget = _meeting_context_budget(meeting.get("contextBudget"))
    mode = _meeting_context_mode(meeting.get("contextMode"))
    speaker_seen = int((meeting.get("participantLastSeen") or {}).get(speaker) or 0)
    topic = meeting.get("topic") or "Untitled Meeting"
    agenda = meeting.get("agenda") or topic
    initial = _meeting_truncate_text(meeting.get("context") or "", budget["maxInitialContextChars"])
    all_events = _meeting_events_text(events)
    unseen_events = _meeting_events_text([e for e in events if int(e.get("sequence") or 0) > speaker_seen])
    recent_events = _meeting_events_text(events[-budget["maxRecentEvents"]:])
    summary = _meeting_truncate_text(meeting.get("rollingSummary") or "", budget["maxSummaryChars"])
    context_values = {}
    if mode == "full":
        context_values = {
            "confirmed_context": f"Confirmed context\n{initial}",
            "full_transcript": f"Full transcript\n{all_events}",
        }
    elif mode == "summary":
        context_values = {
            "confirmed_context": f"Confirmed context\n{initial}",
            "rolling_summary": f"Rolling summary\n{summary}",
            "recent_statements": f"Relevant recent statements\n{recent_events}",
        }
    else:
        if speaker_seen <= 0:
            context_values = {
                "confirmed_context": f"Confirmed context\n{initial}",
                "prior_meeting_events": recent_events,
            }
        else:
            context_values = {
                "new_events_since_last_turn": f"New events since your last turn\n{unseen_events or '(none)'}",
            }
    prompt = meeting_prompt_documents.turn_prompt(
        meeting={**meeting, "topic": topic, "agenda": agenda},
        speaker=speaker,
        stage=stage,
        context_values=context_values,
    )
    return _meeting_truncate_text(prompt + "\n", budget["maxPromptChars"])


def _meeting_provider_ref(agent_id):
    agent = _office_agent_lookup(agent_id) or {}
    return {
        "providerKind": agent.get("providerKind", "openclaw"),
        "agentId": agent.get("id") or agent_id,
        "providerAgentId": agent.get("providerAgentId") or agent.get("id") or agent_id,
    }


def _meeting_provider_timeout():
    raw = os.environ.get("VO_MEETING_PROVIDER_TIMEOUT_SEC") or "300"
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 300
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
    agent = _office_agent_lookup(speaker) or {}
    provider_kind = agent.get("providerKind", "openclaw")
    timeout = _meeting_provider_timeout()
    try:
        if provider_kind == "codex":
            result = _handle_codex_chat({"agentId": speaker, "message": prompt, "conversationId": conversation_id, "timeoutSec": timeout, "fromType": "agent"})
            reply = result.get("reply") or result.get("error") or ""
            ok = bool(result.get("ok"))
            provider_ref = {"providerKind": "codex", "agentId": speaker, "conversationId": conversation_id, "threadId": result.get("threadId"), "turnId": result.get("turnId")}
        elif provider_kind == "hermes":
            result = _handle_hermes_chat({"agentId": speaker, "message": prompt, "conversationId": conversation_id, "timeoutSec": timeout, "fromType": "agent"})
            reply = result.get("reply") or result.get("error") or ""
            ok = bool(result.get("ok"))
            provider_ref = {"providerKind": "hermes", "agentId": speaker, "conversationId": conversation_id, "sessionId": result.get("sessionId")}
        elif provider_kind == "claude-code":
            result = _handle_claude_code_chat({"agentId": speaker, "message": prompt, "conversationId": conversation_id, "timeoutSec": timeout, "fromType": "agent"})
            reply = result.get("reply") or result.get("error") or ""
            ok = bool(result.get("ok"))
            provider_ref = {"providerKind": "claude-code", "agentId": speaker, "conversationId": conversation_id, "sessionId": result.get("sessionId")}
        else:
            reply = _wf_call_agent(speaker, prompt, timeout=timeout, project_id="meeting-for-ai", task_id=conversation_id)
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
    with _meeting_domain_repository().edit_meeting(meeting_id) as store:
        released = _release_timed_out_preparing_meetings(store)
        meeting = store.get("meetings", {}).get(meeting_id)
        if not meeting:
            return {"error": "Executable meeting not found", "_status": 404}
        if released:
            if meeting.get("stage") in _EXEC_MEETING_TERMINAL:
                return {"ok": True, "meeting": meeting, "alreadyTerminal": True, "preparingTimedOut": meeting.get("cancelReason") == "preparing_timeout"}
        if meeting.get("stage") in _EXEC_MEETING_TERMINAL:
            return {"ok": True, "meeting": meeting, "alreadyTerminal": True}
        if meeting.get("stage") == "conflict" or _meeting_has_open_conflicts(meeting):
            return {"error": "Meeting has unresolved participant conflicts", "conflicts": meeting.get("conflicts") or [], "_status": 409}
        if str(body.get("action") or "") == "provider_timeout_skip":
            skipped = _meeting_skip_timed_out_provider_call(store, meeting, body.get("pendingSequence"))
            if not skipped.get("error"):
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
                return {"ok": True, "meeting": meeting, "awaitingUserDecision": True}
            should_auto_advance = action in {"continue", "timeout"} or (deadline_ts and time.time() >= deadline_ts)
            should_summarize_after_window = should_auto_advance and (meeting.get("decisionNextStage") == "summarizing")
            if action in {"continue", "timeout"} or (deadline_ts and time.time() >= deadline_ts):
                if no_consensus_arbitration and deadline_ts and time.time() >= deadline_ts and action != "continue":
                    return {"ok": True, "meeting": meeting, "awaitingUserDecision": True}
                _meeting_continue_from_decision_window(store, meeting, reason="decision_timeout" if action == "timeout" or (deadline_ts and time.time() >= deadline_ts) else "user_continue")
                if should_summarize_after_window:
                    summarize_after_decision_window = True
            else:
                return {"ok": True, "meeting": meeting, "awaitingUserDecision": True}
        if not summarize_after_decision_window and meeting.get("stage") == "preparing":
            meeting["previousStage"] = "preparing"
            meeting["stage"] = "active_opening"
            _append_exec_meeting_event(store, meeting, "meeting_transitioned", payload={"from": "preparing", "to": "active_opening", "reason": "run"})
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
    turn_hooks = meeting_lifecycle_service.AgentTurnHooks(
        build_prompt=_meeting_build_prompt,
        append_event=_append_exec_meeting_event,
        normalize_reply=_meeting_normalize_provider_reply,
        provider_ref=_meeting_provider_ref,
        formal_turn_exists=_meeting_formal_turn_exists,
        pending_turn_exists=_meeting_pending_formal_turn_exists,
        append_ignored=_append_ignored_provider_completion,
        update_summary=_meeting_update_rolling_summary,
    )
    for stage, rounds in (("active_opening", 1), ("active_discussion", max_rounds)):
        for round_index in range(1, rounds + 1):
            with _meeting_domain_repository().edit_meeting(meeting_id) as store:
                meeting = store["meetings"][meeting_id]
                if meeting.get("stage") in _EXEC_MEETING_TERMINAL or meeting.get("stage") == "paused":
                    return {"ok": True, "meeting": meeting, "pausedOrTerminal": True}
                if meeting.get("stage") == "awaiting_user_decision":
                    return {"ok": True, "meeting": meeting, "awaitingUserDecision": True}
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
                    continue
                pending_calls = _meeting_pending_formal_calls_for_round(events, stage, meeting.get("round"))
                if pending_calls:
                    return {"ok": True, "meeting": meeting, "providerCallPending": True, "pendingCalls": pending_calls}
            for speaker in participants:
                with _meeting_domain_repository().edit_meeting(meeting_id) as store:
                    prepared = meeting_lifecycle_service.prepare_agent_turn(
                        store, meeting_id, stage, speaker, turn_hooks,
                    )
                    if prepared.get("skip"):
                        continue
                    if not prepared.get("ok"):
                        return prepared
                    meeting = prepared["meeting"]
                result = _meeting_call_provider(meeting, speaker, prepared["prompt"])
                with _meeting_domain_repository().edit_meeting(meeting_id) as store:
                    committed = meeting_lifecycle_service.commit_agent_turn(
                        store, meeting_id, stage, speaker, result, prepared["pending"], prepared["token"], turn_hooks,
                    )
                    if not committed.get("ok") or committed.get("ignoredProviderCompletion"):
                        return committed
            with _meeting_domain_repository().edit_meeting(meeting_id) as store:
                meeting = store["meetings"][meeting_id]
                if meeting.get("stage") in _EXEC_MEETING_TERMINAL or meeting.get("stage") == "paused":
                    return {"ok": True, "meeting": meeting, "pausedOrTerminal": True}
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
                return {"ok": True, "meeting": meeting, "events": store.get("events", {}).get(meeting_id, []), "awaitingUserDecision": True}
    with _meeting_domain_repository().edit_meeting(meeting_id) as store:
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
        meeting_lifecycle_service.complete_meeting(
            store, meeting, result, actor={"type": "system", "id": "system"},
            reason="run_complete", hooks=_meeting_terminal_hooks(),
        )
        result_payload = {"ok": True, "meeting": meeting, "events": store.get("events", {}).get(meeting_id, [])}
    _project_execution_apply_meeting_result(meeting)
    _archive_trigger_meeting_conclusion(meeting)
    return result_payload


def _handle_executable_meeting_reconcile():
    def reconcile(store):
        _release_timed_out_preparing_meetings(store)
        occupancy = _rebuild_exec_meeting_occupancy(store)
        non_terminal = [m for m in store.get("meetings", {}).values() if m.get("stage") not in _EXEC_MEETING_TERMINAL]
        return {"ok": True, "activeMeetings": len(non_terminal), "occupancy": occupancy}
    _, result = _meeting_domain_repository().mutate_all_meetings(reconcile)
    return result


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

    try:
        meeting_lifecycle_service.validate_participant_eligibility(
            clean_agents,
            organizer,
            participant_error=_system_agent_meeting_error,
        )
    except meeting_lifecycle_service.MeetingLifecycleError as error:
        if error.code == "archive_manager_not_meeting_participant":
            return _exec_meeting_archive_manager_error(error.details.get("participants") or [])
        return {
            "error": str(error),
            "code": error.code,
            "blockedParticipants": error.details.get("participants") or [],
            "_status": error.status,
        }

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
    _, result = _meeting_domain_repository().mutate_request(
        request_id,
        lambda data: meeting_requests_service.resolve_blocker_command(
            data, request_id, status, extra, _meeting_request_service_hooks(),
        )
    )
    return result


def _meeting_request_reset_project_task_blockers(project_id, task_ids, actor, reason):
    _, result = _meeting_domain_repository().create_request(
        lambda data: meeting_requests_service.reset_project_task_blockers_command(
            data,
            project_id,
            list(task_ids or []),
            actor=actor,
            reason=reason,
            hooks=_meeting_request_service_hooks(),
        )
    )
    return result


_wrap_exports()
