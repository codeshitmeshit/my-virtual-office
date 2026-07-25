"""Projects service functions split from server.py.

The functions intentionally hydrate their globals from the importing server module
so this mechanical split can preserve the existing module-level helpers and
configuration while removing domain business bodies from server.py.
"""

import sys

__all__ = ['_project_execution_related', '_project_execution_notification_container', '_project_execution_open_url', '_project_execution_completed_task_count', '_scores_file', '_load_scores', '_save_scores', '_award_points', '_handle_scores_leaderboard', '_handle_score_award', '_project_execution_repair_acceptance_state', '_load_projects', '_save_projects', '_proj_uuid', '_proj_now', '_log_activity', '_project_cron_bindings_file', '_project_find', '_project_cron_reason_label', '_project_cron_target_snapshot', '_project_cron_normalize_history_status', '_project_cron_append_history', '_project_cron_alerts', '_project_agent_fields', '_project_cron_validate_project', '_project_cron_validate_schedule', '_project_cron_validate_target', '_project_cron_default_agent', '_project_cron_gateway_job_from_body', '_project_cron_extract_jobs', '_project_cron_extract_job_id', '_project_cron_task_title', '_project_cron_job_state', '_project_cron_enrich_item', '_handle_project_scheduled_cron_list', '_handle_project_scheduled_cron_all', '_handle_project_scheduled_cron_create', '_handle_project_scheduled_cron_update', '_handle_project_scheduled_cron_delete', '_project_cron_update_binding_status', '_project_execution_reopen_completed_task', '_handle_project_scheduled_cron_dispatch', '_handle_project_scheduled_cron_run', '_handle_projects_list', '_handle_project_get', '_handle_projects_templates', '_handle_project_report', '_project_workspace_slug', '_project_auto_workspace_root', '_project_create_auto_workspace', '_project_prepare_workspace', '_handle_project_create', '_handle_task_create', '_handle_task_comment', '_handle_project_from_template', '_handle_save_as_template', '_handle_project_update', '_handle_task_update', '_handle_columns_update', '_handle_tasks_reorder', '_handle_project_delete', '_handle_task_delete', '_project_execution_enabled', '_project_execution_redact', '_project_execution_compact_evidence_line', '_project_execution_allowed_roots', '_project_execution_validate_workspace', '_project_execution_git_snapshot', '_project_execution_resolve_roles', '_project_execution_resolve_start_roles', '_project_execution_find', '_project_execution_attempt', '_project_execution_active_task', '_project_execution_done_column_ids', '_project_execution_requires_user_acceptance', '_project_execution_attempt_requires_user_acceptance', '_project_execution_acceptance_checklist_complete', '_project_execution_column_locked', '_project_execution_can_complete_after_checklist_update', '_project_execution_start_mode', '_project_execution_is_startable_task', '_project_execution_next_task', '_project_execution_all_tasks_repeatable', '_project_execution_reset_project_tasks_for_restart', '_project_execution_clear_restart_bindings', '_project_execution_mark_done', '_project_execution_incomplete_checklist_feedback', '_project_execution_transient_failure_reason', '_project_execution_attempt_retry_count', '_project_execution_schedule_transient_retry', '_project_execution_continue_for_incomplete_checklist', '_project_execution_column_for_state', '_project_execution_sync_task_column', '_project_execution_move_task_to_column', '_project_execution_transition', '_project_execution_meeting_blocker_unresolved', '_project_execution_block_for_meeting_request', '_project_execution_update_meeting_blocker', '_project_execution_action_item_text', '_project_execution_action_item_description', '_project_execution_action_item_owner', '_project_execution_normalize_meeting_risks', '_project_execution_task_executor_id', '_project_execution_owner_matches', '_project_execution_meeting_action_key', '_project_execution_find_checklist_item', '_project_execution_acceptance_checklist', '_project_execution_seed_acceptance_checklist', '_project_execution_checklist_key', '_project_execution_reset_checklist_completion', '_project_execution_checklist_compact_key', '_project_execution_checklist_prefix', '_project_execution_checklist_ascii_tokens', '_project_execution_checklist_match_score', '_project_execution_find_checklist_update_target', '_project_execution_checklist_done_value', '_project_execution_result_checklist_updates', '_project_execution_checklist_update_key', '_project_execution_apply_checklist_updates', '_project_execution_result_meeting_discussion_points', '_project_execution_apply_meeting_discussion_points', '_project_execution_meeting_discussion_key', '_project_execution_meeting_record_key', '_project_execution_meeting_action_summaries', '_project_execution_upsert_meeting_record', '_project_execution_all_required_meeting_actions_done', '_project_execution_mark_meeting_actions_completed', '_project_execution_has_pending_meeting_actions', '_project_execution_apply_meeting_output_to_task', '_project_execution_apply_meeting_result', '_handle_project_execution_workspace_validate', '_artifact_kind_for_ext', '_artifact_normalize_relpath', '_artifact_safe_path', '_artifact_source_relpath', '_artifact_context_list', '_artifact_context_read', '_artifact_context_file_response', '_artifact_context_delete', '_artifact_context_delete_dir', '_project_artifact_source_records', '_project_artifact_context', '_handle_project_artifacts_list', '_handle_project_artifact_read', '_handle_project_artifact_file', '_handle_project_artifact_delete', '_project_execution_build_prompt', '_project_execution_test_evidence', '_project_execution_call_executor', '_project_execution_latest_attempt', '_project_execution_build_review_prompt', '_project_execution_call_reviewer', '_project_execution_review_feedback', '_project_execution_extract_json', '_project_execution_normalize_review', '_project_execution_run_review', '_project_execution_run_attempt', '_handle_project_execution_start', '_handle_project_execution_project_start', '_project_execution_schedule_continue', '_handle_project_execution_status', '_handle_project_execution_cancel', '_handle_project_execution_review_start', '_handle_project_execution_acceptance', '_handle_project_execution_meeting_blocker_action', '_handle_workflow_chat', '_handle_workflow_start', '_handle_workflow_stop', '_handle_workflow_auto_mode', '_handle_workflow_status', '_handle_review_check_update', '_handle_template_delete']


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

_PROJECT_RETURN_REFERENCES = {}
_PROJECT_EXECUTION_BACKGROUND_THREADS = []


def _project_execution_launch_thread(target, args=()):
    srv = _server_module()
    threading_module = getattr(srv, "threading", None) if srv is not None else None
    thread_factory = getattr(threading_module or threading, "Thread")
    thread = thread_factory(target=target, args=args, daemon=True)
    _PROJECT_EXECUTION_BACKGROUND_THREADS.append(thread)
    thread.start()
    return thread


def _project_execution_drain_background_threads(timeout=3.0):
    if "PYTEST_CURRENT_TEST" not in os.environ:
        return
    deadline = time.time() + timeout
    current = threading.current_thread()
    for thread in list(_PROJECT_EXECUTION_BACKGROUND_THREADS):
        if thread is current:
            continue
        remaining = max(0.0, deadline - time.time())
        is_alive = getattr(thread, "is_alive", None)
        alive = is_alive() if callable(is_alive) else False
        if alive and remaining > 0:
            thread.join(remaining)
            alive = is_alive() if callable(is_alive) else False
        if not alive:
            try:
                _PROJECT_EXECUTION_BACKGROUND_THREADS.remove(thread)
            except ValueError:
                pass


def _project_execution_related(project, task):
    return {
        "type": "project_task",
        "id": f"{(project or {}).get('id') or ''}:{(task or {}).get('id') or ''}",
        "title": (task or {}).get("title") or (project or {}).get("title") or "Project Execution task",
    }

def _project_execution_notification_container(task, attempt_id=None):
    if isinstance(task, dict) and attempt_id:
        attempt = _project_execution_attempt(task, attempt_id)
        if isinstance(attempt, dict):
            return attempt
    return task

def _project_execution_open_url(project_id="", task_id=""):
    project_id = urllib.parse.quote(str(project_id or ""))
    task_id = urllib.parse.quote(str(task_id or ""))
    if project_id and task_id:
        return _vo_public_url(f"/#projects?projectId={project_id}&taskId={task_id}")
    return _vo_public_url("/#projects")

def _project_execution_completed_task_count(project):
    return sum(1 for task in (project or {}).get("tasks", []) if task.get("executionState") == "done" or task.get("completedAt"))

def _scores_file():
    return os.path.join(STATUS_DIR, "project-scores.json")

def _load_scores():
    """Load project-scores.json. Format: { "agents": { "agent-key": { "score": N, "completed": N, "streak": N, "lastCompleted": "ISO" } } }"""
    try:
        with open(_scores_file(), "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
        if "agents" not in data:
            data["agents"] = {}
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {"agents": {}}

def _save_scores(data):
    """Persist project-scores.json."""
    path = _scores_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def _award_points(agent_key, points, reason="task_completed"):
    """Award points to an agent and update streak."""
    if not agent_key or agent_key in ("null", "None", "unassigned", ""):
        return None
    data = _load_scores()
    agent = data["agents"].get(agent_key, {"score": 0, "completed": 0, "streak": 0, "lastCompleted": None, "history": []})

    now = datetime.now(timezone.utc)
    now_str = now.isoformat()

    # Streak logic: if last completion was within 24h, increment streak, else reset
    last = agent.get("lastCompleted")
    if last:
        try:
            last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if (now - last_dt) < timedelta(hours=24):
                agent["streak"] = agent.get("streak", 0) + 1
                # Streak bonus: +5 per streak level (max +25)
                streak_bonus = min(agent["streak"] * 5, 25)
                points += streak_bonus
            else:
                agent["streak"] = 1
        except Exception:
            agent["streak"] = 1
    else:
        agent["streak"] = 1

    agent["score"] = agent.get("score", 0) + points
    agent["completed"] = agent.get("completed", 0) + 1
    agent["lastCompleted"] = now_str

    # History (last 50 entries)
    history = agent.get("history", [])
    history.append({"points": points, "reason": reason, "at": now_str})
    if len(history) > 50:
        history = history[-50:]
    agent["history"] = history

    data["agents"][agent_key] = agent
    _save_scores(data)
    return {"agent": agent_key, "pointsAwarded": points, "totalScore": agent["score"], "streak": agent["streak"], "completed": agent["completed"]}

def _handle_scores_leaderboard():
    """GET /api/projects/scores — returns top agents sorted by score."""
    data = _load_scores()
    agents = []
    for key, info in data.get("agents", {}).items():
        agents.append({
            "agent": key,
            "score": info.get("score", 0),
            "completed": info.get("completed", 0),
            "streak": info.get("streak", 0),
            "meetings": info.get("meetings", 0),
        })
    agents.sort(key=lambda x: x["score"], reverse=True)
    return {"ok": True, "leaderboard": agents}

def _handle_score_award(body):
    """POST /api/projects/scores/award — manually award points."""
    agent_key = (body.get("agent") or "").strip()
    points = int(body.get("points", 0))
    reason = body.get("reason", "manual")
    if not agent_key or points <= 0:
        return {"error": "agent and positive points required", "_status": 400}
    result = _award_points(agent_key, points, reason)
    if result:
        return {"ok": True, **result}
    return {"error": "Invalid agent", "_status": 400}

def _project_execution_repair_acceptance_state(data):
    if not isinstance(data, dict):
        return data
    done_titles = {"done", "completed", "verified", "published", "fixed", "closed"}
    for project in data.get("projects", []) or []:
        if not isinstance(project, dict):
            continue
        done_col = next((c for c in project.get("columns", []) or [] if str(c.get("title", "")).lower() in done_titles), None)
        for task in project.get("tasks", []) or []:
            if not isinstance(task, dict):
                continue
            if task.get("executionState") == "done" or task.get("completedAt"):
                if task.get("blockedReason") or task.get("lastError") or project.get("activeTaskId") == task.get("id") or project.get("workflowPhase") in {"blocked", "executing", "reworking", "reviewing", "execution_complete", "awaiting_user_acceptance", "blocked_by_active_task"}:
                    other_active_task = next((
                        item for item in project.get("tasks", []) or []
                        if isinstance(item, dict)
                        and item.get("id") != task.get("id")
                        and item.get("executionState") in {"validating", "executing", "reviewing", "reworking", "awaiting_user_acceptance", "awaiting_meeting_resolution", "execution_complete"}
                    ), None)
                    task["blockedReason"] = None
                    task["lastError"] = None
                    task["activeAttemptId"] = None
                    if done_col and done_col.get("id"):
                        task["columnId"] = done_col.get("id")
                    if project.get("activeTaskId") == task.get("id") or not other_active_task:
                        project["workflowPhase"] = "done"
                        project["workflowActive"] = False
                        project["activeTaskId"] = None
                        project["activeAgent"] = None
                        project["projectExecutionFlowActive"] = False
                        if project.get("projectExecutionFlowStopReason") in {"awaiting_user_acceptance", "previous_execution_not_resumable", "checklist_incomplete"}:
                            project["projectExecutionFlowStopReason"] = None
                continue
            review = task.get("reviewResult") or {}
            if review.get("status") not in {"pass", "skipped"}:
                continue
            attempt_id = review.get("attemptId")
            attempt = next((a for a in task.get("attempts", []) or [] if a.get("id") == attempt_id), None)
            if _project_execution_attempt_requires_user_acceptance(task, attempt):
                continue
            state = str(task.get("executionState") or "backlog")
            if state in {"validating", "executing", "reviewing", "reworking", "awaiting_meeting_resolution"}:
                continue
            if not _project_execution_acceptance_checklist_complete(task):
                continue
            now = datetime.now(timezone.utc).isoformat()
            task["executionState"] = "done"
            task["completedAt"] = task.get("completedAt") or now
            task["activeAttemptId"] = None
            task["blockedReason"] = None
            task["lastError"] = None
            if done_col and done_col.get("id"):
                task["columnId"] = done_col.get("id")
            if attempt and attempt.get("status") == "review_skipped_waiting_acceptance":
                attempt["status"] = "execution_complete"
            task.setdefault("stateHistory", []).append({
                "attemptId": attempt_id,
                "actor": "system",
                "from": state,
                "to": "done",
                "reason": "Repaired stale completed checklist state for a task that does not require user acceptance.",
                "at": now,
            })
            task["stateHistory"] = task["stateHistory"][-100:]
            if project.get("workflowPhase") in {"awaiting_user_acceptance", "blocked_by_active_task", "blocked", "executing", "reworking", "reviewing", "execution_complete"} or project.get("activeTaskId") == task.get("id"):
                project["workflowPhase"] = "done"
            if project.get("projectExecutionFlowStopReason") in {"awaiting_user_acceptance", "previous_execution_not_resumable", "checklist_incomplete"}:
                project["projectExecutionFlowStopReason"] = None
            project["projectExecutionFlowActive"] = False
            project["workflowActive"] = False
            project["activeTaskId"] = None
            project["activeAgent"] = None
    return data

def _load_projects():
    """Load projects from the markdown-backed store."""
    return _project_execution_repair_acceptance_state(PROJECT_STORE.load_all())

def _save_projects(data):
    """Persist projects to the markdown-backed store."""
    try:
        existing = PROJECT_STORE.load_all()
        existing_by_id = {p.get("id"): p for p in existing.get("projects", []) if isinstance(p, dict)}
        for project in data.get("projects", []) if isinstance(data, dict) else []:
            if not isinstance(project, dict):
                continue
            current_history = project.get("scheduledCronHistory")
            previous = existing_by_id.get(project.get("id")) or {}
            previous_history = previous.get("scheduledCronHistory")
            if (not current_history) and previous_history:
                project["scheduledCronHistory"] = previous_history
            if project is _PROJECT_RETURN_REFERENCES.get(project.get("id")) and not project.get("tasks") and previous.get("tasks"):
                project["tasks"] = previous.get("tasks")
    except Exception:
        pass
    PROJECT_STORE.save_all(data)

def _proj_uuid():
    """Generate a UUID4 string."""
    return str(uuid.uuid4())

def _proj_now():
    """ISO-8601 timestamp."""
    return datetime.now(timezone.utc).isoformat()

def _log_activity(project, type_, by, detail, task_id=None):
    """Append an activity record to a project."""
    if not isinstance(project.get("activity"), list):
        project["activity"] = []
    entry = {"type": type_, "by": by, "at": _proj_now(), "detail": detail}
    if task_id:
        entry["taskId"] = task_id
    project["activity"].append(entry)
    # Cap at 200
    if len(project["activity"]) > 200:
        project["activity"] = project["activity"][-200:]

def _project_cron_bindings_file():
    return os.path.join(STATUS_DIR, "project-cron-bindings.json")

def _project_find(project_id):
    data = _load_projects()
    project = next((p for p in data.get("projects", []) if p.get("id") == project_id), None)
    return data, project

def _project_cron_reason_label(reason, error=None):
    labels = {
        "project_archived": "项目已归档，本次定时任务已跳过。",
        "project_cron_paused": "项目定时任务已暂停。",
        "project_active": "项目已有任务正在运行，本次定时任务已跳过。",
        "task_missing": "绑定的目标任务不存在。",
        "task_completed_repeat_disabled": "目标任务已完成，且未开启允许重复触发。",
        "confirmation_required": "需要人工确认后才能继续执行。",
        "reviewer_skip_confirmation_required": "当前任务需要确认是否跳过独立审查。",
        "dirty_workspace_confirmation_required": "工作区存在未确认变更，需要人工确认。",
        "dispatch_failed": "派发项目定时任务失败。",
        "project_all_tasks_completed": "项目所有任务已完成，定时任务已跳过。",
    }
    if reason in labels:
        return labels[reason]
    if error:
        return str(error)
    if reason:
        return str(reason)
    return ""

def _project_cron_target_snapshot(project, binding):
    target_type = (binding or {}).get("targetType") or "projectWorkflow"
    task_id = (binding or {}).get("taskId")
    task = None
    if target_type == "projectTask":
        task = next((t for t in project.get("tasks", []) or [] if t.get("id") == task_id), None)
    return {
        "targetType": target_type,
        "taskId": task_id,
        "taskTitle": (task or {}).get("title") or (binding or {}).get("taskTitle") or "",
    }

def _project_cron_normalize_history_status(status, reason=None, result=None):
    if status == "failed":
        return "failed"
    if status == "paused":
        return "paused"
    if reason in {"confirmation_required", "reviewer_skip_confirmation_required", "dirty_workspace_confirmation_required"}:
        return "intervention_required"
    if isinstance(result, dict) and result.get("confirmationRequired"):
        return "intervention_required"
    if status == "started":
        return "started"
    return "skipped"

def _project_cron_append_history(project_id, cron_id, binding, status, reason=None, error=None, result=None, source="manual", duration_ms=None):
    data, project = _project_find(project_id)
    if not project:
        return None
    binding = binding or {}
    now = _proj_now()
    history_status = _project_cron_normalize_history_status(status, reason, result)
    target = _project_cron_target_snapshot(project, binding)
    message = _project_cron_reason_label(reason, error)
    entry = {
        "id": _proj_uuid(),
        "cronId": str(cron_id),
        "cronName": binding.get("name") or binding.get("cronName") or str(cron_id),
        "projectId": project_id,
        "projectName": project.get("title", ""),
        "targetType": target["targetType"],
        "taskId": target["taskId"],
        "taskTitle": target["taskTitle"],
        "status": history_status,
        "reason": reason or "",
        "message": message,
        "error": error or "",
        "source": source,
        "createdAt": now,
    }
    if duration_ms is not None:
        entry["durationMs"] = duration_ms
    if isinstance(result, dict):
        entry["resultStatus"] = result.get("status") or result.get("code") or ""
        if result.get("_status"):
            entry["httpStatus"] = result.get("_status")
    history = project.get("scheduledCronHistory")
    if not isinstance(history, list):
        history = []
    history.append(entry)
    project["scheduledCronHistory"] = history[-_PROJECT_CRON_HISTORY_LIMIT:]
    if history_status in _PROJECT_CRON_ALERT_STATUSES:
        detail = f"Project scheduled cron '{entry['cronName']}' requires attention"
        if message:
            detail += f": {message}"
        _log_activity(project, "project_cron_alert", "project-cron", detail, target["taskId"])
    project["updatedAt"] = now
    _save_projects(data)
    print(json.dumps({
        "type": "project_cron_dispatch",
        "projectId": project_id,
        "cronId": str(cron_id),
        "targetType": target["targetType"],
        "taskId": target["taskId"],
        "decision": history_status,
        "reason": reason or "",
        "error": error or "",
        "timestamp": now,
    }, ensure_ascii=False), flush=True)
    return entry

def _project_cron_alerts(project, limit=5):
    history = project.get("scheduledCronHistory", [])
    if not isinstance(history, list):
        return []
    alerts = [h for h in history if isinstance(h, dict) and h.get("status") in _PROJECT_CRON_ALERT_STATUSES]
    alerts.sort(key=lambda h: h.get("createdAt", ""), reverse=True)
    return alerts[:limit]

def _project_agent_fields(project):
    if not isinstance(project, dict):
        return []
    values = [
        project.get("owner"),
        project.get("ownerId"),
        project.get("createdBy"),
        project.get("defaultExecutorAgentId"),
        project.get("defaultReviewerAgentId"),
    ]
    for task in project.get("tasks", []) or []:
        if isinstance(task, dict):
            values.extend([
                task.get("assignee"),
                task.get("executorAgentId"),
                task.get("reviewerAgentId"),
            ])
    return [str(v).strip() for v in values if str(v or "").strip()]

def _project_cron_validate_project(project_id):
    _, project = _project_find(project_id)
    if not project:
        return None, {"error": "Project not found", "_status": 404}
    if project.get("status") == "archived":
        return None, {"error": "Archived projects cannot use scheduled cron", "_status": 400}
    if not _project_agent_fields(project):
        return None, {"error": "Project scheduled cron requires a project owner or bound agent", "_status": 400}
    return project, None

def _project_cron_validate_schedule(schedule):
    if not isinstance(schedule, dict):
        return "Schedule is required"
    kind = schedule.get("kind")
    if kind == "cron":
        expr = str(schedule.get("expr") or "").strip()
        if len(expr.split()) < 5:
            return "Cron schedule requires a valid expr"
        return None
    if kind == "every":
        try:
            every_ms = int(schedule.get("everyMs") or 0)
        except (TypeError, ValueError):
            every_ms = 0
        if every_ms < 60000:
            return "Recurring schedule everyMs must be at least 60000"
        return None
    if kind == "at":
        at = str(schedule.get("at") or "").strip()
        if not at:
            return "One-shot schedule requires at"
        try:
            datetime.fromisoformat(at.replace("Z", "+00:00"))
        except ValueError:
            return "One-shot schedule at must be an ISO datetime"
        return None
    return "Unsupported schedule kind"

def _project_cron_validate_target(project, target_type, task_id=None):
    if target_type == "projectWorkflow":
        return None
    if target_type == "projectTask":
        if not task_id:
            return "taskId is required for projectTask target"
        if not any(t.get("id") == task_id for t in project.get("tasks", []) or [] if isinstance(t, dict)):
            return "Task not found in project"
        return None
    return "targetType must be projectWorkflow or projectTask"

def _project_cron_default_agent(project, task_id=None):
    if task_id:
        task = next((t for t in project.get("tasks", []) or [] if t.get("id") == task_id), None)
        if task:
            for field in ("executorAgentId", "assignee", "reviewerAgentId"):
                if task.get(field):
                    return task.get(field)
    for field in ("defaultExecutorAgentId", "defaultReviewerAgentId", "ownerId", "createdBy"):
        if project.get(field):
            return project.get(field)
    agents = _project_agent_fields(project)
    return agents[0] if agents else "main"

def _project_cron_gateway_job_from_body(project, body, existing=None):
    target_type = body.get("targetType") or (existing or {}).get("targetType") or "projectWorkflow"
    task_id = body.get("taskId") if "taskId" in body else (existing or {}).get("taskId")
    if target_type == "projectWorkflow":
        task_id = None
    schedule = body.get("schedule") if "schedule" in body else (existing or {}).get("schedule")
    name = (body.get("name") if "name" in body else (existing or {}).get("name")) or f"{project.get('title', 'Project')} scheduled task"
    enabled = body.get("enabled") if "enabled" in body else (existing or {}).get("enabled", True)
    agent_id = (body.get("agentId") if "agentId" in body else (existing or {}).get("agentId")) or _project_cron_default_agent(project, task_id)
    message = (body.get("message") if "message" in body else (existing or {}).get("message")) or (
        f"Scheduled project task for project '{project.get('title', project.get('id'))}'. "
        "Project execution dispatch will be handled by Virtual Office in a later phase."
    )
    timeout = body.get("timeoutSeconds") if "timeoutSeconds" in body else (existing or {}).get("timeoutSeconds", 300)
    try:
        timeout = max(10, int(timeout))
    except (TypeError, ValueError):
        timeout = 300
    session_target = body.get("sessionTarget") if "sessionTarget" in body else (existing or {}).get("sessionTarget", "isolated")
    if session_target == "main":
        payload = {"kind": "systemEvent", "text": message}
    else:
        payload = {"kind": "agentTurn", "message": message, "timeoutSeconds": timeout}
        session_target = "isolated"
    job = {
        "name": name,
        "schedule": schedule,
        "payload": payload,
        "sessionTarget": session_target,
        "enabled": bool(enabled),
        "agentId": agent_id,
    }
    if "delivery" in body:
        job["delivery"] = body.get("delivery")
    elif existing and "delivery" in existing:
        job["delivery"] = existing.get("delivery")
    else:
        job["delivery"] = {"mode": "none"}
    binding = {
        "projectId": project.get("id"),
        "targetType": target_type,
        "taskId": task_id,
        "agentId": agent_id,
        "name": name,
        "schedule": schedule,
        "enabled": bool(enabled),
        "message": message,
        "timeoutSeconds": timeout,
        "sessionTarget": session_target,
        "updatedAt": _proj_now(),
    }
    return job, binding

def _project_cron_extract_jobs(result):
    if not isinstance(result, dict):
        return []
    for key in ("jobs", "items"):
        if isinstance(result.get(key), list):
            return result.get(key)
    payload = result.get("payload")
    if isinstance(payload, dict):
        for key in ("jobs", "items"):
            if isinstance(payload.get(key), list):
                return payload.get(key)
    return []

def _project_cron_extract_job_id(result):
    if not isinstance(result, dict):
        return ""
    candidates = [
        result.get("id"),
        (result.get("job") or {}).get("id") if isinstance(result.get("job"), dict) else None,
        (result.get("cron") or {}).get("id") if isinstance(result.get("cron"), dict) else None,
    ]
    payload = result.get("payload")
    if isinstance(payload, dict):
        candidates.extend([
            payload.get("id"),
            (payload.get("job") or {}).get("id") if isinstance(payload.get("job"), dict) else None,
            (payload.get("cron") or {}).get("id") if isinstance(payload.get("cron"), dict) else None,
        ])
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return ""

def _project_cron_task_title(project, task_id):
    if not task_id:
        return ""
    task = next((t for t in project.get("tasks", []) or [] if isinstance(t, dict) and t.get("id") == task_id), None)
    return task.get("title", "") if task else ""

def _project_cron_job_state(job, binding):
    state = {}
    if isinstance(job, dict) and isinstance(job.get("state"), dict):
        state.update(job.get("state") or {})
    for key in ("lastRunAt", "lastStatus", "lastError", "nextRunAt", "lastRunAtMs", "nextRunAtMs", "lastDurationMs"):
        if binding.get(key) is not None:
            state[key] = binding.get(key)
    return state

def _project_cron_enrich_item(cron_id, binding, job, project=None):
    project = project or {}
    merged = dict(job or {})
    merged.update({
        "id": str(cron_id),
        "kind": "project",
        "projectBinding": binding,
        "projectId": binding.get("projectId"),
        "projectName": project.get("title") or binding.get("projectName") or binding.get("projectId"),
        "projectStatus": project.get("status") or "missing",
        "projectCronPaused": bool(project.get("scheduledCronPaused")),
        "targetType": binding.get("targetType"),
        "taskId": binding.get("taskId"),
        "taskTitle": _project_cron_task_title(project, binding.get("taskId")) if project else "",
        "state": _project_cron_job_state(job or {}, binding),
    })
    for key in ("name", "schedule", "enabled", "agentId", "message", "timeoutSeconds", "sessionTarget"):
        if merged.get(key) is None and binding.get(key) is not None:
            merged[key] = binding[key]
    return merged

def _handle_project_scheduled_cron_list(project_id):
    project, error = _project_cron_validate_project(project_id)
    if error:
        return error
    cron_result = _gateway_rpc_call("cron.list", {"includeDisabled": True}, timeout=20)
    if not cron_result.get("ok"):
        return {"error": cron_result.get("error", "Failed to list cron jobs"), "_status": 502}
    jobs_by_id = {str(j.get("id")): j for j in _project_cron_extract_jobs(cron_result) if isinstance(j, dict) and j.get("id")}
    with _PROJECT_CRON_BINDINGS_LOCK:
        bindings = _load_project_cron_bindings().get("bindings", {})
    items = []
    for cron_id, binding in bindings.items():
        if binding.get("projectId") != project_id:
            continue
        items.append(_project_cron_enrich_item(cron_id, binding, jobs_by_id.get(str(cron_id), {}), project))
    return {"ok": True, "projectId": project_id, "jobs": items, "cronOwner": "gateway", "bindingOwner": "virtual-office"}

def _handle_project_scheduled_cron_all():
    cron_result = _gateway_rpc_call("cron.list", {"includeDisabled": True}, timeout=20)
    if not cron_result.get("ok"):
        return {"error": cron_result.get("error", "Failed to list cron jobs"), "_status": 502}
    jobs_by_id = {str(j.get("id")): j for j in _project_cron_extract_jobs(cron_result) if isinstance(j, dict) and j.get("id")}
    with _PROJECT_CRON_BINDINGS_LOCK:
        bindings = _load_project_cron_bindings().get("bindings", {})
    data = _load_projects()
    projects_by_id = {p.get("id"): p for p in data.get("projects", []) if isinstance(p, dict)}
    items = []
    for cron_id, binding in bindings.items():
        project = projects_by_id.get(binding.get("projectId"), {})
        items.append(_project_cron_enrich_item(cron_id, binding, jobs_by_id.get(str(cron_id), {}), project))
    return {
        "ok": True,
        "jobs": items,
        "projects": [
            {"id": p.get("id"), "title": p.get("title", ""), "status": p.get("status", "active"), "scheduledCronPaused": bool(p.get("scheduledCronPaused"))}
            for p in data.get("projects", []) if isinstance(p, dict)
        ],
        "cronOwner": "gateway",
        "bindingOwner": "virtual-office",
    }

def _handle_project_scheduled_cron_create(project_id, body):
    project, error = _project_cron_validate_project(project_id)
    if error:
        return error
    target_type = body.get("targetType") or "projectWorkflow"
    task_id = body.get("taskId")
    target_error = _project_cron_validate_target(project, target_type, task_id)
    if target_error:
        return {"error": target_error, "_status": 400}
    schedule_error = _project_cron_validate_schedule(body.get("schedule"))
    if schedule_error:
        return {"error": schedule_error, "_status": 400}
    job, binding = _project_cron_gateway_job_from_body(project, body)
    cron_result = _gateway_rpc_call("cron.add", job, timeout=30)
    if not cron_result.get("ok"):
        return {"error": cron_result.get("error", "Failed to create cron job"), "_status": 502}
    cron_id = _project_cron_extract_job_id(cron_result)
    if not cron_id:
        return {"error": "Cron job was created but no id was returned", "_status": 502}
    binding["cronJobId"] = cron_id
    binding["createdAt"] = _proj_now()
    with _PROJECT_CRON_BINDINGS_LOCK:
        data = _load_project_cron_bindings()
        data.setdefault("bindings", {})[cron_id] = binding
        _save_project_cron_bindings(data)
    return {"ok": True, "projectId": project_id, "id": cron_id, "job": {**job, "id": cron_id}, "binding": binding}

def _handle_project_scheduled_cron_update(project_id, cron_id, body):
    project, error = _project_cron_validate_project(project_id)
    if error:
        return error
    with _PROJECT_CRON_BINDINGS_LOCK:
        data = _load_project_cron_bindings()
        existing = data.get("bindings", {}).get(cron_id)
    if not existing or existing.get("projectId") != project_id:
        return {"error": "Project scheduled cron not found", "_status": 404}
    target_type = body.get("targetType") if "targetType" in body else existing.get("targetType")
    task_id = body.get("taskId") if "taskId" in body else existing.get("taskId")
    target_error = _project_cron_validate_target(project, target_type, task_id)
    if target_error:
        return {"error": target_error, "_status": 400}
    schedule = body.get("schedule") if "schedule" in body else existing.get("schedule")
    schedule_error = _project_cron_validate_schedule(schedule)
    if schedule_error:
        return {"error": schedule_error, "_status": 400}
    job, binding = _project_cron_gateway_job_from_body(project, {**body, "targetType": target_type, "taskId": task_id, "schedule": schedule}, existing=existing)
    patch = dict(job)
    cron_result = _gateway_rpc_call("cron.update", {"id": cron_id, "patch": patch}, timeout=30)
    if not cron_result.get("ok"):
        return {"error": cron_result.get("error", "Failed to update cron job"), "_status": 502}
    binding["cronJobId"] = cron_id
    binding["createdAt"] = existing.get("createdAt") or _proj_now()
    with _PROJECT_CRON_BINDINGS_LOCK:
        data = _load_project_cron_bindings()
        data.setdefault("bindings", {})[cron_id] = binding
        _save_project_cron_bindings(data)
    return {"ok": True, "projectId": project_id, "id": cron_id, "binding": binding}

def _handle_project_scheduled_cron_delete(project_id, cron_id):
    with _PROJECT_CRON_BINDINGS_LOCK:
        data = _load_project_cron_bindings()
        existing = data.get("bindings", {}).get(cron_id)
    if not existing or existing.get("projectId") != project_id:
        return {"error": "Project scheduled cron not found", "_status": 404}
    cron_result = _gateway_rpc_call("cron.remove", {"id": cron_id}, timeout=30)
    if not cron_result.get("ok"):
        return {"error": cron_result.get("error", "Failed to delete cron job"), "_status": 502}
    with _PROJECT_CRON_BINDINGS_LOCK:
        data = _load_project_cron_bindings()
        data.setdefault("bindings", {}).pop(cron_id, None)
        _save_project_cron_bindings(data)
    return {"ok": True, "projectId": project_id, "id": cron_id}

def _project_cron_update_binding_status(cron_id, status, error=None, extra=None):
    now = _proj_now()
    with _PROJECT_CRON_BINDINGS_LOCK:
        data = _load_project_cron_bindings()
        binding = data.setdefault("bindings", {}).get(str(cron_id))
        if not binding:
            return
        binding["lastRunAt"] = now
        binding["lastStatus"] = status
        binding["lastError"] = error or None
        binding["updatedAt"] = now
        if isinstance(extra, dict):
            binding.update(extra)
        _save_project_cron_bindings(data)

def _project_execution_reopen_completed_task(project, task, actor="project-execution"):
    if not task or not task.get("completedAt"):
        return False
    done_cols = _project_execution_done_column_ids(project)
    target_col = _wf_get_backlog_col(project)
    if not target_col:
        for col in project.get("columns", []) or []:
            if col.get("id") not in done_cols:
                target_col = col
                break
    previous_col = task.get("columnId")
    task["completedAt"] = None
    task["executionState"] = "backlog" if _project_execution_enabled(project) else "backlog"
    _project_execution_reset_checklist_completion(task)
    if target_col:
        task["columnId"] = target_col.get("id")
        col_tasks = [t for t in project.get("tasks", []) if t.get("columnId") == target_col.get("id") and t.get("id") != task.get("id")]
        task["order"] = max((t.get("order", 0) for t in col_tasks), default=-1) + 1
    task["updatedAt"] = _proj_now()
    task.setdefault("comments", []).append({
        "id": _proj_uuid(),
        "author": actor,
        "text": "Reopened completed task for repeat execution.",
        "createdAt": _proj_now(),
    })
    _log_activity(project, "project_execution_task_reopened", actor, f"Reopened completed task '{task.get('title', '')}' for repeat execution", task.get("id"))
    task.setdefault("stateHistory", []).append({
        "actor": actor,
        "from": "done",
        "to": "backlog",
        "reason": "repeat execution",
        "previousColumnId": previous_col,
        "at": _proj_now(),
    })
    task["stateHistory"] = task["stateHistory"][-100:]
    project["updatedAt"] = _proj_now()
    return True

def _handle_project_scheduled_cron_dispatch(project_id, cron_id, source="manual"):
    started_at = time.time()

    def record(status, reason=None, error=None, result=None):
        duration_ms = int((time.time() - started_at) * 1000)
        return _project_cron_append_history(project_id, cron_id, binding, status, reason=reason, error=error, result=result, source=source, duration_ms=duration_ms)

    with _PROJECT_CRON_BINDINGS_LOCK:
        binding = _load_project_cron_bindings().get("bindings", {}).get(str(cron_id))
    if not binding or binding.get("projectId") != project_id:
        return {"error": "Project scheduled cron not found", "_status": 404}

    # ── Pre-dispatch idempotency: skip if last status was completion-disengage ──
    if binding.get("lastStatus") in ("disengaged_completed",):
        return {"ok": True, "status": "skipped", "reason": "pre_check_disengaged", "projectId": project_id, "id": cron_id, "idempotent": True}

    data, project = _project_find(project_id)
    if not project:
        _project_cron_update_binding_status(cron_id, "missing_project", "Project not found")
        return {"error": "Project not found", "_status": 404, "status": "missing_project"}
    if project.get("status") == "archived":
        _project_cron_update_binding_status(cron_id, "skipped_archived", "Project is archived")
        record("skipped", "project_archived")
        return {"ok": True, "status": "skipped", "reason": "project_archived", "projectId": project_id, "id": cron_id}
    if project.get("scheduledCronPaused"):
        _project_cron_update_binding_status(cron_id, "paused", "Project scheduled cron is paused")
        record("paused", "project_cron_paused")
        return {"ok": True, "status": "paused", "reason": "project_cron_paused", "projectId": project_id, "id": cron_id}
    target_type = binding.get("targetType") or "projectWorkflow"
    task_id = binding.get("taskId")
    active = _project_execution_active_task(project) if _project_execution_enabled(project) else None
    if active:
        _project_cron_update_binding_status(cron_id, "skipped", "Another task is already active for this project", {"activeTaskId": active.get("id")})
        record("skipped", "project_active")
        return {"ok": True, "status": "skipped", "reason": "project_active", "activeTaskId": active.get("id"), "projectId": project_id, "id": cron_id}
    if target_type == "projectTask":
        task = next((t for t in project.get("tasks", []) or [] if t.get("id") == task_id), None)
        if not task:
            _project_cron_update_binding_status(cron_id, "missing_target", "Task not found")
            record("skipped", "task_missing")
            return {"ok": True, "status": "skipped", "reason": "task_missing", "projectId": project_id, "id": cron_id}
        if task.get("completedAt"):
            if task.get("scheduledRepeatEnabled") is not True:
                # ── Task is done and not repeatable: auto-disengage cron ──
                cron_triggered = str(source or "") == "cron"
                binding_status = "disengaged_completed" if cron_triggered else "skipped_completed_task"
                reason = "task_completed_cron_disengaged" if cron_triggered else "task_completed_repeat_disabled"
                _project_cron_update_binding_status(cron_id, binding_status, "Task completed and repeat triggering is disabled")
                record("skipped", reason)
                try:
                    _gateway_rpc_call("cron.update", {"id": cron_id, "patch": {"enabled": False}}, timeout=5)
                except Exception:
                    pass
                return {"ok": True, "status": "skipped", "reason": reason, "projectId": project_id, "id": cron_id, "taskId": task_id, "cronDisabled": True}
            # Repeatable task: reopen and restart below (normal repeat flow)
        # Falls through: task not completed, or is repeatable and should be reopened
        reopened = _project_execution_reopen_completed_task(project, task, actor="project-cron")
        if reopened:
            data["projects"] = [project if p.get("id") == project_id else p for p in data.get("projects", [])]
            _save_projects(data)
        if _project_execution_enabled(project):
            result = _handle_project_execution_start(project_id, task_id, {"by": "project-cron", "source": source, "skipReviewConfirmed": True})
        else:
            result = _handle_workflow_start(project_id, {"autoMode": False})
        if reopened and isinstance(result, dict):
            result["reopenedCompletedTask"] = True
    else:
        # ── Idempotency guard: skip if all tasks are completed ──
        all_completed = False
        tasks = project.get("tasks", []) or []
        if target_type == "projectWorkflow" and tasks:
            done_cols = _project_execution_done_column_ids(project)
            non_done_tasks = [t for t in tasks if t.get("columnId") not in done_cols and not t.get("completedAt")]
            if not non_done_tasks:
                all_completed = True

        if all_completed:
            # ── Auto-disengage cron when all tasks completed ──
            _project_cron_update_binding_status(cron_id, "disengaged_completed", "All tasks completed; cron disengaged")
            record("skipped", "project_all_tasks_completed")
            try:
                _gateway_rpc_call("cron.update", {"id": cron_id, "patch": {"enabled": False}}, timeout=5)
            except Exception:
                pass
            # ── Alert on repeated dispatch attempt ──
            history = project.get("scheduledCronHistory", []) or []
            recent_same = [h for h in history[-10:] if h.get("reason") == "project_all_tasks_completed"]
            if len(recent_same) >= 2:
                _gateway_rpc_call("cron.alert", {"id": cron_id, "message": f"P0 cron 重复触发缺陷告警：项目 {project_id} 的所有任务已完成，但定时任务被重复触发（最近 10 次中有 {len(recent_same)} 次因 '项目已完成' 跳过）。已自动暂停该定时任务。请确认是否有残留缺陷。"}, timeout=10)
            # ── Also update with completion disengage reason ──
            return {"ok": True, "status": "skipped", "reason": "project_all_tasks_completed", "projectId": project_id, "id": cron_id, "allCompleted": True, "cronDisabled": True}

        if _project_execution_enabled(project):
            result = _handle_project_execution_project_start(project_id, {"mode": project.get("projectExecutionStartMode") or "continuous", "by": "project-cron", "source": source, "skipReviewConfirmed": True})
        else:
            result = _handle_workflow_start(project_id, {"autoMode": True})
    if result.get("ok"):
        _project_cron_update_binding_status(cron_id, "started", None, {"lastDispatchResult": result})
        record("started", None, result=result)
        return {"ok": True, "status": "started", "projectId": project_id, "id": cron_id, "result": result}
    if result.get("confirmationRequired"):
        _project_cron_update_binding_status(cron_id, "skipped_confirmation_required", result.get("code") or "confirmation required", {"lastDispatchResult": result})
        record("skipped", result.get("code") or "confirmation_required", error=result.get("error"), result=result)
        return {"ok": True, "status": "skipped", "reason": result.get("code") or "confirmation_required", "projectId": project_id, "id": cron_id, "result": result}
    status = "failed"
    if result.get("_status") == 409:
        status = "skipped"
    _project_cron_update_binding_status(cron_id, status, result.get("error") or result.get("code") or "dispatch failed", {"lastDispatchResult": result})
    if status == "skipped":
        record("skipped", result.get("code") or result.get("error"), error=result.get("error"), result=result)
        return {"ok": True, "status": "skipped", "reason": result.get("code") or result.get("error"), "projectId": project_id, "id": cron_id, "result": result}
    record("failed", result.get("code") or "dispatch_failed", error=result.get("error"), result=result)
    return {**result, "projectId": project_id, "id": cron_id}

def _handle_project_scheduled_cron_run(project_id, cron_id):
    with _PROJECT_CRON_BINDINGS_LOCK:
        binding = _load_project_cron_bindings().get("bindings", {}).get(cron_id)
    if not binding or binding.get("projectId") != project_id:
        return {"error": "Project scheduled cron not found", "_status": 404}
    cron_result = _gateway_rpc_call("cron.run", {"id": cron_id}, timeout=30)
    if not cron_result.get("ok"):
        return {"error": cron_result.get("error", "Failed to run cron job"), "_status": 502}
    dispatch = _handle_project_scheduled_cron_dispatch(project_id, cron_id, source="run-now")
    return {"ok": True, "projectId": project_id, "id": cron_id, "result": cron_result, "dispatch": dispatch}

def _handle_projects_list(query_string=""):
    """GET /api/projects — return all projects (summaries)."""
    data = _load_projects()
    projects = data.get("projects", [])
    # Optional ?status= filter
    status_filter = None
    if query_string:
        for part in query_string.split("&"):
            if part.startswith("status="):
                status_filter = part.split("=", 1)[1]
    if status_filter:
        projects = [p for p in projects if p.get("status") == status_filter]
    # Return summary (no activity log, trim tasks to counts)
    summaries = []
    for p in projects:
        tasks = p.get("tasks", [])
        total = len(tasks)
        done = sum(1 for t in tasks if t.get("completedAt"))
        summaries.append({
            "id": p["id"],
            "title": p.get("title", ""),
            "description": p.get("description", ""),
            "status": p.get("status", "active"),
            "priority": p.get("priority", "medium"),
            "createdAt": p.get("createdAt", ""),
            "updatedAt": p.get("updatedAt", ""),
            "dueDate": p.get("dueDate"),
            "createdBy": p.get("createdBy", ""),
            "tags": p.get("tags", []),
            "branch": p.get("branch", ""),
            "longTermProject": bool(p.get("longTermProject", False)),
            "archiveMaintenance": _archive_project_maintenance_meta(p),
            "archiveMaintenanceEnabled": _archive_project_maintenance_enabled(p),
            "projectExecutionEnabled": p.get("projectExecutionEnabled", False),
            "workspacePath": p.get("workspacePath"),
            "workspaceKind": p.get("workspaceKind"),
            "workspaceStatus": p.get("workspaceStatus", {}),
            "workspaceManagedBy": p.get("workspaceManagedBy"),
            "workspaceCreatedAt": p.get("workspaceCreatedAt"),
            "defaultExecutorAgentId": p.get("defaultExecutorAgentId"),
            "defaultReviewerAgentId": p.get("defaultReviewerAgentId"),
            "columns": p.get("columns", []),
            "taskCount": total,
            "taskDone": done,
            "scheduledCronAlertCount": len(_project_cron_alerts(p, limit=1000)),
            "scheduledCronAlerts": _project_cron_alerts(p, limit=3),
            "template": p.get("template", False),
        })
    return {"ok": True, "projects": summaries}

def _handle_project_get(project_id):
    """GET /api/projects/{id} — return full project."""
    data = _load_projects()
    for p in data["projects"]:
        if p["id"] == project_id:
            return {"ok": True, "project": p}
    return {"error": "Project not found", "_status": 404}

def _handle_projects_templates():
    """GET /api/projects/templates — list built-in + user templates."""
    data = _load_projects()
    all_templates = list(_BUILTIN_TEMPLATES) + data.get("templates", [])
    return {"ok": True, "templates": all_templates}

def _handle_project_report(project_id):
    """GET /api/projects/{id}/report."""
    data = _load_projects()
    p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if not p:
        return {"error": "Project not found", "_status": 404}
    tasks = p.get("tasks", [])
    now_str = _proj_now()
    def _is_overdue(t):
        dd = t.get("dueDate")
        if not dd or t.get("completedAt"):
            return False
        try:
            due = datetime.fromisoformat(dd.replace("Z", "+00:00"))
            return due < datetime.now(timezone.utc)
        except Exception:
            return False
    total = len(tasks)
    done = sum(1 for t in tasks if t.get("completedAt"))
    in_progress_cols = [c["id"] for c in p.get("columns", []) if "progress" in c.get("title", "").lower() or "doing" in c.get("title", "").lower()]
    in_progress = sum(1 for t in tasks if t.get("columnId") in in_progress_cols)
    overdue = sum(1 for t in tasks if _is_overdue(t))
    # Per-column breakdown
    col_stats = []
    for col in p.get("columns", []):
        col_tasks = [t for t in tasks if t.get("columnId") == col["id"]]
        col_stats.append({"id": col["id"], "title": col["title"], "color": col.get("color", "#666"), "count": len(col_tasks)})
    # Agent workload
    agent_load = {}
    for t in tasks:
        a = t.get("assignee") or "Unassigned"
        agent_load[a] = agent_load.get(a, 0) + 1
    # Timeline (tasks with due dates)
    timeline = []
    for t in tasks:
        if t.get("dueDate"):
            timeline.append({"id": t["id"], "title": t["title"], "dueDate": t["dueDate"], "completedAt": t.get("completedAt"), "assignee": t.get("assignee"), "priority": t.get("priority", "medium")})
    timeline.sort(key=lambda x: x["dueDate"])
    return {"ok": True, "report": {
        "projectId": project_id,
        "title": p.get("title", ""),
        "generatedAt": now_str,
        "stats": {"total": total, "done": done, "inProgress": in_progress, "overdue": overdue},
        "columns": col_stats,
        "agentWorkload": agent_load,
        "timeline": timeline,
    }}

def _project_workspace_slug(value):
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return slug or "project"

def _project_auto_workspace_root():
    configured = str(os.environ.get("VO_AUTO_PROJECT_WORKSPACE_ROOT") or "").strip()
    if configured:
        return os.path.realpath(os.path.expanduser(configured))
    return os.path.join(STATUS_DIR, "project-workspaces")

def _project_create_auto_workspace(title, now=None):
    root = _project_auto_workspace_root()
    try:
        os.makedirs(root, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "error": f"Unable to create project workspace root: {exc}", "code": "workspace_root_create_failed"}
    try:
        dt = datetime.fromisoformat(str(now or _proj_now()).replace("Z", "+00:00"))
        timestamp = dt.strftime("%Y%m%d%H%M%S")
    except Exception:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    base = f"{_project_workspace_slug(title)}-{timestamp}"
    path = os.path.join(root, base)
    if os.path.exists(path):
        path = os.path.join(root, f"{base}-{str(uuid.uuid4())[:8]}")
    try:
        os.makedirs(path, exist_ok=False)
    except OSError as exc:
        return {"ok": False, "error": f"Unable to create project workspace: {exc}", "code": "workspace_create_failed"}
    return {"ok": True, "path": os.path.realpath(path), "createdAt": now or _proj_now()}

def _project_prepare_workspace(title, body, now):
    enabled = bool(body.get("projectExecutionEnabled"))
    workspace_path = body.get("workspacePath")
    workspace_kind = body.get("workspaceKind")
    workspace_status = body.get("workspaceStatus", {})
    workspace_managed_by = body.get("workspaceManagedBy")
    workspace_created_at = body.get("workspaceCreatedAt")
    if not enabled:
        return {
            "ok": True,
            "projectExecutionEnabled": False,
            "workspacePath": workspace_path if workspace_path else None,
            "workspaceKind": workspace_kind if workspace_path else None,
            "workspaceStatus": workspace_status if workspace_path else {},
            "workspaceManagedBy": workspace_managed_by if workspace_path else None,
            "workspaceCreatedAt": workspace_created_at if workspace_path else None,
        }
    auto_created = False
    if not str(workspace_path or "").strip():
        created = _project_create_auto_workspace(title, now)
        if not created.get("ok"):
            return {**created, "_status": 400}
        workspace_path = created["path"]
        workspace_managed_by = "system"
        workspace_created_at = created.get("createdAt")
        auto_created = True
    else:
        workspace_managed_by = workspace_managed_by or "user"
    workspace_status = _project_execution_validate_workspace(workspace_path)
    if not workspace_status.get("ok"):
        if auto_created:
            shutil.rmtree(workspace_path, ignore_errors=True)
        return {**workspace_status, "_status": 400}
    return {
        "ok": True,
        "projectExecutionEnabled": True,
        "workspacePath": workspace_status.get("path"),
        "workspaceKind": workspace_status.get("kind"),
        "workspaceStatus": workspace_status,
        "workspaceManagedBy": workspace_managed_by,
        "workspaceCreatedAt": workspace_created_at,
    }

def _handle_project_create(body):
    """POST /api/projects — create a new project."""
    _project_execution_drain_background_threads()
    title = (body.get("title") or "").strip()
    if not title:
        return {"error": "Project title is required", "_status": 400}
    for field in ("defaultExecutorAgentId", "defaultReviewerAgentId"):
        if _is_archive_manager_agent(body.get(field)):
            return {"error": "档案管理员不能作为普通项目默认执行或审查 AI", "code": "archive_manager_not_assignable", "_status": 400}
    created_by = (body.get("createdBy") or body.get("author") or "user").strip()
    now = _proj_now()
    workspace = _project_prepare_workspace(title, body, now)
    if not workspace.get("ok"):
        return workspace
    # Default columns
    default_cols = [
        {"id": _proj_uuid(), "title": "Backlog", "color": "#6c757d", "order": 0},
        {"id": _proj_uuid(), "title": "In Progress", "color": "#ffc107", "order": 1},
        {"id": _proj_uuid(), "title": "Review", "color": "#fd7e14", "order": 2},
        {"id": _proj_uuid(), "title": "Done", "color": "#198754", "order": 3},
    ]
    cols = body.get("columns") or default_cols
    project = {
        "id": _proj_uuid(),
        "title": title,
        "description": body.get("description", ""),
        "status": body.get("status", "active"),
        "priority": body.get("priority", "medium"),
        "createdAt": now,
        "updatedAt": now,
        "dueDate": body.get("dueDate"),
        "createdBy": created_by,
        "tags": body.get("tags", []),
        "branch": body.get("branch", ""),
        "longTermProject": bool(body.get("longTermProject", False)),
        "highPriorityAiMeetingAutoApprove": bool(body.get("highPriorityAiMeetingAutoApprove", False)),
        "archiveMaintenanceEnabled": bool(body["archiveMaintenanceEnabled"]) if "archiveMaintenanceEnabled" in body else _archive_project_default_maintenance_enabled({"status": body.get("status", "active")}),
        "archiveMaintenance": {
            "enabled": bool(body["archiveMaintenanceEnabled"]) if "archiveMaintenanceEnabled" in body else _archive_project_default_maintenance_enabled({"status": body.get("status", "active")}),
            "explicit": "archiveMaintenanceEnabled" in body,
            "updatedAt": now,
            "updatedBy": created_by,
        },
        "projectExecutionEnabled": workspace["projectExecutionEnabled"],
        "workspacePath": workspace["workspacePath"],
        "workspaceKind": workspace["workspaceKind"],
        "workspaceStatus": workspace["workspaceStatus"],
        "workspaceManagedBy": workspace.get("workspaceManagedBy"),
        "workspaceCreatedAt": workspace.get("workspaceCreatedAt"),
        "defaultExecutorAgentId": body.get("defaultExecutorAgentId"),
        "defaultReviewerAgentId": body.get("defaultReviewerAgentId"),
        "projectExecutionStartMode": body.get("projectExecutionStartMode") or "continuous",
        "projectExecutionFlowActive": False,
        "projectExecutionFlowStopReason": None,
        "scheduledCronPaused": bool(body.get("scheduledCronPaused", False)),
        "executionPolicy": {"maxActiveTasks": 1},
        "executionDirtyConfirmations": [],
        "columns": cols,
        "tasks": [],
        "activity": [],
        "template": False,
    }
    _log_activity(project, "project_created", created_by, f"Created project '{title}'")
    data = _load_projects()
    data["projects"].append(project)
    _save_projects(data)
    _PROJECT_RETURN_REFERENCES[project["id"]] = project
    return {"ok": True, "project": project}

def _handle_task_create(project_id, body):
    """POST /api/projects/{id}/tasks — create a task."""
    data = _load_projects()
    p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if not p:
        return {"error": "Project not found", "_status": 404}
    title = (body.get("title") or "").strip()
    if not title:
        return {"error": "Task title is required", "_status": 400}
    for field in ("assignee", "executorAgentId", "reviewerAgentId"):
        if _is_archive_manager_agent(body.get(field)):
            return {"error": "档案管理员不能被分配普通项目任务", "code": "archive_manager_not_assignable", "_status": 400}
    # Determine column
    col_id = body.get("columnId")
    if not col_id and p.get("columns"):
        col_id = p["columns"][0]["id"]
    # Max order in column
    max_order = max((t.get("order", 0) for t in p["tasks"] if t.get("columnId") == col_id), default=-1) + 1
    now = _proj_now()
    default_executor_id = body.get("executorAgentId")
    assignee_id = body.get("assignee")
    task = {
        "id": _proj_uuid(),
        "title": title,
        "description": body.get("description", ""),
        "columnId": col_id,
        "order": max_order,
        "priority": body.get("priority", "medium"),
        "assignee": assignee_id,
        "assigneeBranch": body.get("assigneeBranch"),
        "executorAgentId": default_executor_id,
        "reviewerAgentId": body.get("reviewerAgentId"),
        "requiresUserAcceptance": body.get("requiresUserAcceptance", False) is True,
        "allowReviewerlessExecution": body.get("allowReviewerlessExecution", False) is True,
        "scheduledRepeatEnabled": body.get("scheduledRepeatEnabled", False) is True,
        "executionState": "backlog",
        "activeAttemptId": None,
        "attempts": [],
        "evidence": {},
        "blockedReason": None,
        "lastError": None,
        "dueDate": body.get("dueDate"),
        "tags": body.get("tags", []),
        "checklist": body.get("checklist", []),
        "meetingActionItems": body.get("meetingActionItems", []) if isinstance(body.get("meetingActionItems"), list) else [],
        "meetingDecisionHistory": body.get("meetingDecisionHistory", []) if isinstance(body.get("meetingDecisionHistory"), list) else [],
        "meetingDiscussionPoints": body.get("meetingDiscussionPoints", []) if isinstance(body.get("meetingDiscussionPoints"), list) else [],
        "meetingRecords": body.get("meetingRecords", []) if isinstance(body.get("meetingRecords"), list) else [],
        "source": body.get("source") if isinstance(body.get("source"), dict) else {},
        "comments": [],
        "attachments": [],
        "createdAt": now,
        "updatedAt": now,
        "completedAt": None,
    }
    p["tasks"].append(task)
    returned_project = _PROJECT_RETURN_REFERENCES.get(project_id)
    if isinstance(returned_project, dict):
        returned_tasks = returned_project.setdefault("tasks", [])
        if isinstance(returned_tasks, list) and not any(t.get("id") == task["id"] for t in returned_tasks if isinstance(t, dict)):
            returned_tasks.append(task)
    p["updatedAt"] = now
    by = body.get("by", "user")
    _log_activity(p, "task_created", by, f"Created task '{title}'", task["id"])
    _save_projects(data)
    # Create task markdown file at creation time
    col_title = next((c["title"] for c in p.get("columns", []) if c["id"] == col_id), "backlog")
    _wf_write_task_file(project_id, task, col_title.lower().replace(" ", "_"), work_log_entry=f"Task created by {by} in '{col_title}'")
    return {"ok": True, "task": task}

def _handle_task_comment(project_id, task_id, body):
    """POST /api/projects/{id}/tasks/{taskId}/comments."""
    data = _load_projects()
    p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if not p:
        return {"error": "Project not found", "_status": 404}
    task = next((t for t in p["tasks"] if t["id"] == task_id), None)
    if not task:
        return {"error": "Task not found", "_status": 404}
    text = (body.get("text") or "").strip()
    if not text:
        return {"error": "Comment text is required", "_status": 400}
    author = (body.get("author") or "user").strip()
    comment = {"id": _proj_uuid(), "author": author, "text": text, "createdAt": _proj_now()}
    if not isinstance(task.get("comments"), list):
        task["comments"] = []
    task["comments"].append(comment)
    task["updatedAt"] = _proj_now()
    p["updatedAt"] = _proj_now()
    _log_activity(p, "task_commented", author, f"Commented on '{task['title']}'", task_id)
    _save_projects(data)
    # Update task markdown file with comment
    current_col = next((c["title"] for c in p.get("columns", []) if c["id"] == task.get("columnId")), "unknown")
    _wf_write_task_file(project_id, task, current_col.lower().replace(" ", "_"), work_log_entry=f"Comment by {author}: {text[:200]}")
    return {"ok": True, "comment": comment}

def _handle_project_from_template(body):
    """POST /api/projects/from-template."""
    template_id = (body.get("templateId") or "").strip()
    title = (body.get("title") or "").strip()
    if not title:
        return {"error": "Project title is required", "_status": 400}
    data = _load_projects()
    tpl = next((t for t in data.get("templates", []) if t["id"] == template_id), None)
    # Also check built-in templates
    if not tpl:
        tpl = next((t for t in _BUILTIN_TEMPLATES if t["id"] == template_id), None)
    if not tpl:
        return {"error": "Template not found", "_status": 404}
    now = _proj_now()
    # Clone columns with new IDs
    col_map = {}
    new_cols = []
    for i, col in enumerate(tpl.get("columns", [])):
        new_id = _proj_uuid()
        col_map[i] = new_id
        new_cols.append({"id": new_id, "title": col.get("title", f"Column {i+1}"), "color": col.get("color", "#6c757d"), "order": i})
    # Create tasks from taskTemplates
    new_tasks = []
    for tt in tpl.get("taskTemplates", []):
        col_idx = tt.get("columnIndex", 0)
        col_id = col_map.get(col_idx, new_cols[0]["id"] if new_cols else None)
        if col_id:
            new_tasks.append({
                "id": _proj_uuid(),
                "title": tt.get("title", "Task"),
                "description": tt.get("description", ""),
                "columnId": col_id,
                "order": tt.get("order", 0),
                "priority": tt.get("priority", "medium"),
                "assignee": None,
                "assigneeBranch": None,
                "executorAgentId": None,
                "reviewerAgentId": None,
                "requiresUserAcceptance": tt.get("requiresUserAcceptance", False) is True,
                "allowReviewerlessExecution": tt.get("allowReviewerlessExecution", False) is True,
                "scheduledRepeatEnabled": tt.get("scheduledRepeatEnabled", False) is True,
                "executionState": "backlog",
                "activeAttemptId": None,
                "attempts": [],
                "evidence": {},
                "blockedReason": None,
                "lastError": None,
                "dueDate": None,
                "tags": tt.get("tags", []),
                "checklist": [],
                "comments": [],
                "attachments": [],
                "createdAt": now,
                "updatedAt": now,
                "completedAt": None,
            })
    created_by = (body.get("createdBy") or "user").strip()
    workspace = _project_prepare_workspace(title, body, now)
    if not workspace.get("ok"):
        return workspace
    for field in ("defaultExecutorAgentId", "defaultReviewerAgentId"):
        if _is_archive_manager_agent(body.get(field)):
            return {"error": "档案管理员不能作为普通项目默认执行或审查 AI", "code": "archive_manager_not_assignable", "_status": 400}
    project = {
        "id": _proj_uuid(),
        "title": title,
        "description": body.get("description", tpl.get("description", "")),
        "status": "active",
        "priority": body.get("priority", "medium"),
        "createdAt": now,
        "updatedAt": now,
        "dueDate": body.get("dueDate"),
        "createdBy": created_by,
        "tags": body.get("tags", []),
        "branch": body.get("branch", ""),
        "longTermProject": bool(body.get("longTermProject", False)),
        "highPriorityAiMeetingAutoApprove": bool(body.get("highPriorityAiMeetingAutoApprove", False)),
        "archiveMaintenanceEnabled": bool(body["archiveMaintenanceEnabled"]) if "archiveMaintenanceEnabled" in body else True,
        "archiveMaintenance": {
            "enabled": bool(body["archiveMaintenanceEnabled"]) if "archiveMaintenanceEnabled" in body else True,
            "explicit": "archiveMaintenanceEnabled" in body,
            "updatedAt": now,
            "updatedBy": created_by,
        },
        "projectExecutionEnabled": workspace["projectExecutionEnabled"],
        "workspacePath": workspace["workspacePath"],
        "workspaceKind": workspace["workspaceKind"],
        "workspaceStatus": workspace["workspaceStatus"],
        "workspaceManagedBy": workspace.get("workspaceManagedBy"),
        "workspaceCreatedAt": workspace.get("workspaceCreatedAt"),
        "defaultExecutorAgentId": body.get("defaultExecutorAgentId"),
        "defaultReviewerAgentId": body.get("defaultReviewerAgentId"),
        "projectExecutionStartMode": body.get("projectExecutionStartMode") or "continuous",
        "projectExecutionFlowActive": False,
        "projectExecutionFlowStopReason": None,
        "scheduledCronPaused": bool(body.get("scheduledCronPaused", False)),
        "executionPolicy": {"maxActiveTasks": 1},
        "executionDirtyConfirmations": [],
        "columns": new_cols,
        "tasks": new_tasks,
        "activity": [],
        "template": False,
    }
    _log_activity(project, "project_created", created_by, f"Created from template '{tpl.get('title', '')}'")
    data["projects"].append(project)
    _save_projects(data)
    return {"ok": True, "project": project}

def _handle_save_as_template(body):
    """POST /api/projects/templates — save a project as template."""
    project_id = (body.get("projectId") or "").strip()
    title = (body.get("title") or "").strip()
    data = _load_projects()
    p = None
    if project_id:
        p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if not title:
        title = (p.get("title", "Template") if p else "Template") + " Template"
    task_templates = []
    if p:
        col_idx_map = {col["id"]: i for i, col in enumerate(p.get("columns", []))}
        for t in p.get("tasks", []):
            task_templates.append({
                "title": t.get("title", ""),
                "columnIndex": col_idx_map.get(t.get("columnId", ""), 0),
                "priority": t.get("priority", "medium"),
                "tags": t.get("tags", []),
                "description": t.get("description", ""),
            })
    template = {
        "id": _proj_uuid(),
        "title": title,
        "description": body.get("description", p.get("description", "") if p else ""),
        "columns": [{"title": c.get("title"), "color": c.get("color", "#6c757d")} for c in (p.get("columns", []) if p else [])],
        "taskTemplates": task_templates,
    }
    if not isinstance(data.get("templates"), list):
        data["templates"] = []
    data["templates"].append(template)
    _save_projects(data)
    return {"ok": True, "template": template}

def _handle_project_update(project_id, body):
    """PUT /api/projects/{id} — update project metadata."""
    data = _load_projects()
    p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if not p:
        return {"error": "Project not found", "_status": 404}
    for field in ("defaultExecutorAgentId", "defaultReviewerAgentId"):
        if _is_archive_manager_agent(body.get(field)):
            return {"error": "档案管理员不能作为普通项目默认执行或审查 AI", "code": "archive_manager_not_assignable", "_status": 400}
    by = body.get("by", "user")
    if body.get("projectExecutionEnabled") or (_project_execution_enabled(p) and "workspacePath" in body):
        workspace_status = _project_execution_validate_workspace(body.get("workspacePath") or p.get("workspacePath"))
        if not workspace_status.get("ok"):
            return {**workspace_status, "_status": 400}
        body["projectExecutionEnabled"] = True
        body["workspacePath"] = workspace_status.get("path")
        body["workspaceKind"] = workspace_status.get("kind")
        body["workspaceStatus"] = workspace_status
    updatable = [
        "title", "description", "status", "priority", "dueDate", "tags", "branch",
        "longTermProject", "highPriorityAiMeetingAutoApprove",
        "projectExecutionEnabled", "workspacePath", "workspaceKind", "workspaceStatus",
        "workspaceManagedBy", "workspaceCreatedAt",
        "defaultExecutorAgentId", "defaultReviewerAgentId", "projectExecutionStartMode",
        "projectExecutionFlowActive", "projectExecutionFlowStopReason", "executionPolicy",
        "scheduledCronPaused",
        "archiveMaintenanceEnabled", "archiveMaintenance",
    ]
    old_status = p.get("status")
    for field in updatable:
        if field in body:
            old = p.get(field)
            p[field] = body[field]
            if old != body[field]:
                _log_activity(p, "project_updated", by, f"Changed {field}: {old} → {body[field]}")
    p["updatedAt"] = _proj_now()
    _save_projects(data)
    if "status" in body and body.get("status") != old_status:
        _archive_maintenance_trigger(
            project_id,
            "project_status_changed",
            source=_archive_source_ref("project", project_id, title=p.get("title", ""), oldStatus=old_status, newStatus=body.get("status")),
            title="Project status changed",
            summary=f"Project status changed from {old_status} to {body.get('status')}.",
            value_level="high",
            impact="project_status",
        )
    return {"ok": True, "project": p}

def _handle_task_update(project_id, task_id, body):
    """PUT /api/projects/{id}/tasks/{taskId} — update a task."""
    data = _load_projects()
    p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if not p:
        return {"error": "Project not found", "_status": 404}
    task = next((t for t in p["tasks"] if t["id"] == task_id), None)
    if not task:
        return {"error": "Task not found", "_status": 404}
    for field in ("assignee", "executorAgentId", "reviewerAgentId"):
        if _is_archive_manager_agent(body.get(field)):
            return {"error": "档案管理员不能被分配普通项目任务", "code": "archive_manager_not_assignable", "_status": 400}
    old_executor = task.get("executorAgentId")
    if (
        _project_execution_enabled(p)
        and "assignee" in body
        and "executorAgentId" not in body
        and body.get("assignee")
        and not old_executor
    ):
        body["executorAgentId"] = body.get("assignee")
    by = body.get("by", "user")
    now = _proj_now()
    was_completed = bool(task.get("completedAt"))
    checklist_was_complete = _project_execution_acceptance_checklist_complete(task) if _project_execution_enabled(p) else False
    if _project_execution_enabled(p) and "columnId" in body:
        done_cols = {c["id"] for c in p.get("columns", []) if c.get("title", "").lower() in ("done", "completed", "verified", "published", "fixed", "closed")}
        if body.get("columnId") != task.get("columnId") and _project_execution_column_locked(task):
            return {
                "error": "Project Execution is controlling this task column; wait for the state machine transition or stop/reset execution before moving it manually.",
                "code": "project_execution_column_locked",
                "_status": 409,
            }
        if body.get("columnId") in done_cols and task.get("executionState") != "done":
            return {"error": "Project Execution tasks require final user acceptance before Done", "_status": 409}
    # Track column move
    if "columnId" in body and body["columnId"] != task.get("columnId"):
        old_col = next((c["title"] for c in p.get("columns", []) if c["id"] == task.get("columnId")), task.get("columnId"))
        new_col = next((c["title"] for c in p.get("columns", []) if c["id"] == body["columnId"]), body["columnId"])
        # Check if moving to "Done" column
        done_cols = [c["id"] for c in p.get("columns", []) if c.get("title", "").lower() in ("done", "completed", "verified", "published", "fixed", "closed")]
        if body["columnId"] in done_cols and not task.get("completedAt"):
            task["completedAt"] = now
            # GAMIFICATION: Award points to assignee
            assignee = task.get("assignee") or body.get("assignee")
            if assignee:
                pts = SCORE_TASK_COMPLETED
                pri = task.get("priority", "medium")
                if pri == "critical": pts += SCORE_CRITICAL_BONUS
                elif pri == "high": pts += SCORE_HIGH_BONUS
                elif pri == "medium": pts += SCORE_MEDIUM_BONUS
                # On-time bonus
                dd = task.get("dueDate")
                if dd:
                    try:
                        due = datetime.fromisoformat(dd.replace("Z", "+00:00"))
                        if datetime.now(timezone.utc) <= due:
                            pts += SCORE_ON_TIME_BONUS
                    except Exception:
                        pass
                # Checklist bonus
                chk = task.get("checklist", [])
                done_items = sum(1 for c in chk if c.get("done"))
                pts += done_items * SCORE_CHECKLIST_BONUS
                score_result = _award_points(assignee, pts, f"Completed: {task.get('title','')}")
                task["_scoreAwarded"] = score_result  # Transient field for response
        elif body["columnId"] not in done_cols and task.get("completedAt"):
            task["completedAt"] = None
        _log_activity(p, "task_moved", by, f"Moved '{task['title']}' from {old_col} to {new_col}", task_id)
    # Track priority change
    if "priority" in body and body["priority"] != task.get("priority"):
        _log_activity(p, "task_priority_changed", by, f"Priority changed: {task.get('priority')} → {body['priority']}", task_id)
    # Track assignee change
    if "assignee" in body and body["assignee"] != task.get("assignee"):
        _log_activity(p, "task_assigned", by, f"Assigned to {body['assignee']}", task_id)
    updatable = [
        "title", "description", "columnId", "order", "priority", "assignee",
        "assigneeBranch", "executorAgentId", "reviewerAgentId", "dueDate", "tags",
        "checklist", "meetingActionItems", "meetingDecisionHistory", "meetingDiscussionPoints", "meetingRecords", "completedAt", "requiresUserAcceptance", "allowReviewerlessExecution", "scheduledRepeatEnabled",
    ]
    # Track which fields changed for md file update
    changed_fields = []
    for field in updatable:
        if field in body:
            if task.get(field) != body[field]:
                changed_fields.append(field)
            task[field] = body[field]
    schedule_project_execution_continue = False
    if (
        _project_execution_enabled(p)
        and "checklist" in changed_fields
        and not checklist_was_complete
        and _project_execution_acceptance_checklist_complete(task)
        and _project_execution_can_complete_after_checklist_update(task)
    ):
        review = task.get("reviewResult") if isinstance(task.get("reviewResult"), dict) else {}
        done_result = _project_execution_mark_done(
            p,
            task,
            by,
            "Acceptance checklist completed after reviewer pass.",
            review.get("attemptId"),
        )
        if done_result.get("ok"):
            schedule_project_execution_continue = p.get("projectExecutionStartMode") == "continuous"
            p.update({
                "workflowActive": False,
                "workflowPhase": "done",
                "activeTaskId": None,
                "activeAgent": None,
                "projectExecutionFlowActive": schedule_project_execution_continue,
                "projectExecutionFlowStopReason": None if schedule_project_execution_continue else "checklist_completed",
            })
            _log_activity(p, "project_execution_checklist_completed", by, f"Completed Project Execution task '{task.get('title', '')}' after checklist completion.", task_id)
    task["updatedAt"] = now
    p["updatedAt"] = now
    _save_projects(data)
    if schedule_project_execution_continue:
        _project_execution_schedule_continue(project_id, "checklist_completed")
    # Update task markdown file on meaningful changes
    if changed_fields:
        current_col = next((c["title"] for c in p.get("columns", []) if c["id"] == task.get("columnId")), "unknown")
        status_text = current_col.lower().replace(" ", "_")
        log_parts = []
        if "columnId" in changed_fields:
            log_parts.append(f"Moved to '{current_col}' by {by}")
        if "assignee" in changed_fields:
            log_parts.append(f"Assigned to {task.get('assignee', 'unassigned')}")
        if "priority" in changed_fields:
            log_parts.append(f"Priority set to {task.get('priority')}")
        if any(f in changed_fields for f in ("title", "description", "checklist", "tags", "dueDate")):
            log_parts.append(f"Updated by {by}")
        work_log_entry = "; ".join(log_parts) if log_parts else f"Updated by {by}"
        review_results = task.get("reviewCheck") if task.get("reviewCheck") else None
        _wf_write_task_file(project_id, task, status_text, review_results=review_results, work_log_entry=work_log_entry)
    if not was_completed and task.get("completedAt"):
        _archive_maintenance_trigger(
            project_id,
            "task_completed",
            source=_archive_source_ref("task", task_id, title=task.get("title", ""), taskId=task_id),
            title=f"Task completed: {task.get('title', '')}",
            summary=f"Task completed: {task.get('title', '')}",
            value_level="high",
            impact="task",
        )
    if task.get("blockedReason") or task.get("lastError") or str(task.get("executionState") or "").lower() == "blocked":
        _archive_maintenance_trigger(
            project_id,
            "blocker",
            source=_archive_source_ref("task", task_id, title=task.get("title", ""), taskId=task_id),
            title=f"Task blocker: {task.get('title', '')}",
            summary=task.get("blockedReason") or task.get("lastError") or "Task is blocked.",
            value_level="high",
            impact="risk",
        )
    return {"ok": True, "task": task}

def _handle_columns_update(project_id, body):
    """PUT /api/projects/{id}/columns — reorder/add/edit columns."""
    data = _load_projects()
    p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if not p:
        return {"error": "Project not found", "_status": 404}
    columns = body.get("columns")
    if not isinstance(columns, list):
        return {"error": "columns must be a list", "_status": 400}
    by = body.get("by", "user")
    # Assign IDs to new columns
    for i, col in enumerate(columns):
        if not col.get("id"):
            col["id"] = _proj_uuid()
        col["order"] = i
    p["columns"] = columns
    p["updatedAt"] = _proj_now()
    _log_activity(p, "columns_updated", by, "Columns updated")
    _save_projects(data)
    return {"ok": True, "columns": columns}

def _handle_tasks_reorder(project_id, body):
    """PUT /api/projects/{id}/tasks/reorder — batch reorder."""
    data = _load_projects()
    p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if not p:
        return {"error": "Project not found", "_status": 404}
    # body.updates = [{id, columnId, order}, ...]
    # Also accept body.tasks as alias for updates (frontend compat)
    updates = body.get("updates", body.get("tasks", []))
    task_map = {t["id"]: t for t in p["tasks"]}
    for u in updates:
        if any(_is_archive_manager_agent(u.get(field)) for field in ("assignee", "executorAgentId", "reviewerAgentId")):
            return {"error": "档案管理员不能被分配普通项目任务", "code": "archive_manager_not_assignable", "_status": 400}
    done_cols = {c["id"] for c in p.get("columns", []) if c.get("title", "").lower() in ("done", "completed", "verified", "published", "fixed", "closed")}
    now = _proj_now()
    completed_tasks = []
    for u in updates:
        tid = u.get("id")
        if tid in task_map:
            task = task_map[tid]
            new_col = u.get("columnId")
            if _project_execution_enabled(p) and new_col and new_col != task.get("columnId") and _project_execution_column_locked(task):
                return {
                    "error": "Project Execution is controlling this task column; wait for the state machine transition or stop/reset execution before moving it manually.",
                    "code": "project_execution_column_locked",
                    "_status": 409,
                }
            if _project_execution_enabled(p) and new_col in done_cols and task.get("executionState") != "done":
                return {"error": "Project Execution tasks require final user acceptance before Done", "_status": 409}
            if new_col and new_col != task.get("columnId"):
                # Auto-set/clear completedAt on done column moves
                if new_col in done_cols and not task.get("completedAt"):
                    task["completedAt"] = now
                    completed_tasks.append(task)
                elif new_col not in done_cols and task.get("completedAt"):
                    task["completedAt"] = None
                task["columnId"] = new_col
            if "order" in u:
                task["order"] = u["order"]
            task["updatedAt"] = now
    p["updatedAt"] = now
    _save_projects(data)
    for task in completed_tasks:
        _archive_maintenance_trigger(
            project_id,
            "task_completed",
            source=_archive_source_ref("task", task.get("id"), title=task.get("title", ""), taskId=task.get("id")),
            title=f"Task completed: {task.get('title', '')}",
            summary=f"Task completed: {task.get('title', '')}",
            value_level="high",
            impact="task",
        )
    return {"ok": True}

def _handle_project_delete(project_id, delete_workspace=False):
    """DELETE /api/projects/{id}."""
    data = _load_projects()
    project = next((p for p in data.get("projects", []) if p.get("id") == project_id), None)
    workspace_path = project.get("workspacePath") if project else None
    workspace_managed_by = project.get("workspaceManagedBy") if project else None
    workspace_delete_error = None
    if delete_workspace and project and workspace_managed_by == "system" and workspace_path:
        try:
            shutil.rmtree(workspace_path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            workspace_delete_error = str(exc)
    elif delete_workspace and project and workspace_managed_by != "system":
        workspace_delete_error = "Workspace was not automatically created by this project"
    # Delete through the store so both markdown-backed projects and legacy
    # JSON-only projects are removed correctly.
    deleted = PROJECT_STORE.delete_project(project_id)
    if not deleted:
        return {"error": "Project not found", "_status": 404}
    result = {"ok": True, "id": project_id, "workspaceDeleted": bool(delete_workspace and workspace_managed_by == "system" and not workspace_delete_error)}
    if workspace_delete_error:
        result["workspaceDeleteError"] = workspace_delete_error
    return result

def _handle_task_delete(project_id, task_id):
    """DELETE /api/projects/{id}/tasks/{taskId}."""
    data = _load_projects()
    p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if not p:
        return {"error": "Project not found", "_status": 404}
    before = len(p["tasks"])
    p["tasks"] = [t for t in p["tasks"] if t["id"] != task_id]
    if len(p["tasks"]) == before:
        return {"error": "Task not found", "_status": 404}
    p["updatedAt"] = _proj_now()
    _save_projects(data)
    return {"ok": True, "id": task_id}

def _project_execution_enabled(project):
    return bool((project or {}).get("projectExecutionEnabled"))

def _project_execution_redact(value):
    text = _PROJECT_EXECUTION_SECRET_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", str(value or ""))
    return text if len(text) <= _PROJECT_EXECUTION_MAX_TEXT else text[:_PROJECT_EXECUTION_MAX_TEXT] + "\n...[truncated]"

def _project_execution_compact_evidence_line(value, limit=_PROJECT_EXECUTION_MAX_EVIDENCE_LINE):
    text = re.sub(r"\s+", " ", _project_execution_redact(value)).strip()
    if not text:
        return ""
    return text if len(text) <= limit else text[:limit].rstrip() + "...[truncated]"

def _project_execution_allowed_roots():
    raw = str(os.environ.get("VO_PROJECT_ROOTS") or "").strip()
    roots = []
    for item in raw.split(os.pathsep) if raw else []:
        candidate = os.path.realpath(os.path.expanduser(item.strip()))
        if candidate and os.path.isdir(candidate):
            roots.append(candidate)
    return roots

def _project_execution_validate_workspace(raw_path):
    if not str(raw_path or "").strip():
        return {"ok": False, "error": "Project workspace is required", "code": "workspace_required"}
    path = os.path.realpath(os.path.expanduser(str(raw_path).strip()))
    if not os.path.exists(path):
        return {"ok": False, "error": "Project workspace does not exist", "code": "workspace_missing"}
    if not os.path.isdir(path):
        return {"ok": False, "error": "Project workspace must be a directory", "code": "workspace_not_directory"}
    if not os.access(path, os.R_OK | os.X_OK):
        return {"ok": False, "error": "Project workspace is not accessible", "code": "workspace_inaccessible"}
    roots = _project_execution_allowed_roots()
    if roots and not any(path == root or path.startswith(root + os.sep) for root in roots):
        return {"ok": False, "error": "Project workspace is outside the configured project roots", "code": "workspace_outside_roots"}
    return {"ok": True, "path": path, "kind": "git" if os.path.isdir(os.path.join(path, ".git")) else "directory", "checkedAt": _proj_now()}

def _project_execution_git_snapshot(workspace):
    if not workspace or not os.path.isdir(os.path.join(workspace, ".git")):
        return {"kind": "directory", "dirty": False, "fingerprint": "", "files": []}
    try:
        result = subprocess.run(["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=workspace, capture_output=True, text=True, timeout=15)
        lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
        files = []
        for line in lines[:200]:
            raw = line[3:].strip() if len(line) > 3 else line.strip()
            if " -> " in raw:
                raw = raw.split(" -> ", 1)[1]
            files.append(raw.strip('"'))
        fingerprint_parts = list(lines)
        for relpath in files:
            try:
                stat = os.stat(os.path.join(workspace, relpath))
                fingerprint_parts.append(f"{relpath}:{stat.st_size}:{stat.st_mtime_ns}")
            except OSError:
                fingerprint_parts.append(f"{relpath}:missing")
        return {"kind": "git", "dirty": bool(lines), "fingerprint": hashlib.sha256("\n".join(fingerprint_parts).encode()).hexdigest(), "files": files, "truncated": len(lines) > 200}
    except Exception as exc:
        return {"kind": "git", "dirty": False, "fingerprint": "", "files": [], "error": str(exc)}

def _project_execution_resolve_roles(project, task):
    executor_id = task.get("executorAgentId") or task.get("assignee") or project.get("defaultExecutorAgentId")
    reviewer_id = task.get("reviewerAgentId") or project.get("defaultReviewerAgentId")
    if not executor_id or not _office_agent_lookup(executor_id):
        return {"ok": False, "error": "A valid executor agent is required", "code": "executor_required"}
    if not reviewer_id or not _office_agent_lookup(reviewer_id):
        return {"ok": False, "error": "A valid reviewer agent is required", "code": "reviewer_required"}
    executor = _office_agent_ref(executor_id)
    reviewer = _office_agent_ref(reviewer_id)
    if executor.get("id") == reviewer.get("id"):
        return {"ok": False, "error": "Executor and reviewer must be different agents", "code": "reviewer_not_independent"}
    return {"ok": True, "executor": executor, "reviewer": reviewer}

def _project_execution_resolve_start_roles(project, task, allow_skip_reviewer=False):
    executor_id = task.get("executorAgentId") or task.get("assignee") or project.get("defaultExecutorAgentId")
    reviewer_id = task.get("reviewerAgentId") or project.get("defaultReviewerAgentId")
    if not executor_id or not _office_agent_lookup(executor_id):
        return {"ok": False, "error": "A valid executor agent is required", "code": "executor_required"}
    executor = _office_agent_ref(executor_id)
    if not reviewer_id or not _office_agent_lookup(reviewer_id):
        if allow_skip_reviewer:
            return {"ok": True, "executor": executor, "reviewer": None, "skipReview": True, "skipReviewReason": "reviewer_missing"}
        return {"ok": False, "confirmationRequired": True, "code": "reviewer_skip_confirmation_required", "error": "No reviewer is configured. Confirm to run without independent review.", "missingRole": "reviewer"}
    reviewer = _office_agent_ref(reviewer_id)
    if executor.get("id") == reviewer.get("id"):
        return {"ok": False, "error": "Executor and reviewer must be different agents", "code": "reviewer_not_independent"}
    return {"ok": True, "executor": executor, "reviewer": reviewer, "skipReview": False}

def _project_execution_find(project_id, task_id=None):
    data = _load_projects()
    project = next((p for p in data.get("projects", []) if p.get("id") == project_id), None)
    task = next((t for t in project.get("tasks", []) if t.get("id") == task_id), None) if project and task_id else None
    return data, project, task

def _project_execution_attempt(task, attempt_id):
    return next((item for item in task.get("attempts", []) if item.get("id") == attempt_id), None)

def _project_execution_active_task(project):
    active_states = {"validating", "executing", "retrying", "reviewing", "reworking", "awaiting_meeting_resolution"}
    return next((t for t in project.get("tasks", []) if t.get("executionState") in active_states), None)

def _project_execution_done_column_ids(project):
    return {c.get("id") for c in project.get("columns", []) if c.get("title", "").lower() in ("done", "completed", "verified", "published", "fixed", "closed")}

def _project_execution_requires_user_acceptance(task):
    return task.get("requiresUserAcceptance", False) is True

def _project_execution_attempt_requires_user_acceptance(task, attempt):
    if isinstance(attempt, dict) and "requiresUserAcceptance" in attempt:
        return attempt.get("requiresUserAcceptance") is True
    return _project_execution_requires_user_acceptance(task)

def _project_execution_acceptance_checklist_complete(task):
    checklist = _project_execution_acceptance_checklist(task)
    return bool(checklist) and all(isinstance(item, dict) and item.get("done") is True for item in checklist)

def _project_execution_column_locked(task):
    return str((task or {}).get("executionState") or "") in _PROJECT_EXECUTION_COLUMN_LOCKED_STATES

def _project_execution_can_complete_after_checklist_update(task):
    if not isinstance(task, dict):
        return False
    if task.get("activeAttemptId"):
        return False
    if task.get("executionState") == "done" or task.get("completedAt"):
        return False
    state = str(task.get("executionState") or "backlog")
    if state in {"validating", "executing", "reviewing", "reworking", "awaiting_meeting_resolution"}:
        return False
    review = task.get("reviewResult") if isinstance(task.get("reviewResult"), dict) else {}
    if review.get("status") not in {"pass", "skipped"}:
        return False
    attempt = _project_execution_attempt(task, review.get("attemptId"))
    return not _project_execution_attempt_requires_user_acceptance(task, attempt)

def _project_execution_start_mode(project, body=None):
    if body and body.get("projectStart") is False:
        return "single"
    raw = str((body or {}).get("mode") or (body or {}).get("startMode") or project.get("projectExecutionStartMode") or "continuous").strip().lower()
    if raw in ("single", "next", "next_task", "next-task"):
        return "single"
    if raw in ("continuous", "flow", "auto", "continuous_task_flow", "continuous-task-flow"):
        return "continuous"
    return "continuous"

def _project_execution_is_startable_task(task):
    state = task.get("executionState") or ("done" if task.get("completedAt") else "backlog")
    return state in ("", "backlog", "blocked")

def _project_execution_next_task(project):
    done_cols = _project_execution_done_column_ids(project)
    col_order = {c.get("id"): idx for idx, c in enumerate(sorted(project.get("columns", []), key=lambda c: c.get("order", 0)))}
    candidates = []
    for idx, task in enumerate(project.get("tasks", [])):
        if task.get("columnId") in done_cols:
            continue
        if not _project_execution_is_startable_task(task):
            continue
        candidates.append((col_order.get(task.get("columnId"), 9999), task.get("order", idx), idx, task))
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    return candidates[0][3] if candidates else None

def _project_execution_all_tasks_repeatable(project):
    tasks = project.get("tasks", []) or []
    return bool(tasks) and all(t.get("scheduledRepeatEnabled") is True for t in tasks)

def _project_execution_reset_project_tasks_for_restart(project, actor="user"):
    done_cols = _project_execution_done_column_ids(project)
    backlog_col = _wf_get_backlog_col(project)
    if not backlog_col:
        backlog_col = next((c for c in sorted(project.get("columns", []) or [], key=lambda c: c.get("order", 0)) if c.get("id") not in done_cols), None)
    if not backlog_col:
        return {"ok": False, "error": "Backlog column not found", "_status": 409}
    now = _proj_now()
    col_order = {c.get("id"): idx for idx, c in enumerate(sorted(project.get("columns", []) or [], key=lambda c: c.get("order", 0)))}
    tasks = list(project.get("tasks", []) or [])
    tasks.sort(key=lambda t: (col_order.get(t.get("columnId"), 9999), t.get("order", 0), t.get("createdAt", ""), t.get("id", "")))
    reset_count = 0
    for idx, task in enumerate(tasks):
        previous_state = task.get("executionState") or ("done" if task.get("completedAt") else "backlog")
        previous_col = task.get("columnId")
        stale_bindings = any(bool(task.get(field)) for field in (
            "meetingBlocker", "meetingActionItems", "meetingDecisionHistory",
            "meetingDiscussionPoints", "meetingRecords", "evidence", "reviewResult",
        ))
        checklist_completed = any(
            isinstance(item, dict)
            and item.get("source") not in {"meeting_action_item", "meeting_risk"}
            and (item.get("done") is True or item.get("completedAt") or item.get("completedBy") or item.get("completionEvidence"))
            for item in task.get("checklist") or []
        )
        changed = (
            previous_col != backlog_col.get("id")
            or previous_state != "backlog"
            or bool(task.get("completedAt"))
            or bool(task.get("activeAttemptId"))
            or bool(task.get("blockedReason"))
            or bool(task.get("lastError"))
            or stale_bindings
            or checklist_completed
        )
        task["columnId"] = backlog_col.get("id")
        task["order"] = idx
        task["completedAt"] = None
        task["executionState"] = "backlog"
        task["activeAttemptId"] = None
        task["blockedReason"] = None
        task["lastError"] = None
        task["reworkFeedback"] = None
        task["reworkCount"] = 0
        _project_execution_clear_restart_bindings(task, now, actor, "project pipeline restart")
        task["updatedAt"] = now
        if changed:
            reset_count += 1
            task.setdefault("stateHistory", []).append({
                "actor": actor,
                "from": previous_state,
                "to": "backlog",
                "reason": "project pipeline restart",
                "previousColumnId": previous_col,
                "at": now,
            })
            task["stateHistory"] = task["stateHistory"][-100:]
    project["projectExecutionFlowActive"] = False
    project["projectExecutionFlowStopReason"] = None
    project["workflowActive"] = False
    project["workflowPhase"] = "restarting"
    project["activeTaskId"] = None
    project["activeAgent"] = None
    project["updatedAt"] = now
    _log_activity(project, "project_execution_pipeline_restarted", actor, f"Restarted project pipeline and reset {reset_count} task(s).")
    return {"ok": True, "resetTaskCount": reset_count}

def _project_execution_clear_restart_bindings(task, now=None, actor="user", reason="project execution restart"):
    """Clear current-run meeting/execution bindings before a fresh restart.

    Persistent audit trails such as comments, attempts, stateHistory, and
    meetingBlockerHistory are retained. The task-level current meeting fields
    are reset so stale meeting action items do not hijack the new execution.
    """
    now = now or _proj_now()
    blocker = task.get("meetingBlocker") if isinstance(task.get("meetingBlocker"), dict) else {}
    if blocker:
        archived = dict(blocker)
        archived["resetAt"] = now
        archived["resetBy"] = actor
        archived["resetReason"] = reason
        task.setdefault("meetingBlockerHistory", []).append(archived)
        task["meetingBlockerHistory"] = task["meetingBlockerHistory"][-50:]
    task["meetingBlocker"] = {}
    task["meetingActionItems"] = []
    task["meetingDecisionHistory"] = []
    task["meetingDiscussionPoints"] = []
    task["meetingRecords"] = []
    task["activeAttemptId"] = None
    task["blockedReason"] = None
    task["lastError"] = None
    task["reworkFeedback"] = None
    task["reworkCount"] = 0
    task["evidence"] = {}
    task["reviewResult"] = {}
    _project_execution_reset_checklist_completion(task)
    return task

def _project_execution_mark_done(project, task, actor, reason, attempt_id=None, allow_empty_checklist=False):
    done_col = _wf_get_done_col(project)
    if not done_col:
        return {"error": "Done column not found", "_status": 409}
    checklist = _project_execution_acceptance_checklist(task)
    if not checklist:
        if allow_empty_checklist:
            task.setdefault("acceptanceHistory", []).append({
                "action": "skip_empty_checklist",
                "attemptId": attempt_id,
                "at": _proj_now(),
                "by": actor or "user",
                "reason": "Accepted without an acceptance checklist after explicit confirmation.",
            })
            task["acceptanceHistory"] = task["acceptanceHistory"][-50:]
        else:
            return {
                "error": "Acceptance checklist is empty; create and complete acceptance checklist items before marking the task done.",
                "code": "checklist_empty",
                "unfinishedChecklist": [{"id": "", "text": "Create and complete acceptance checklist items."}],
                "allowSkip": True,
                "_status": 409,
            }
    unfinished = [
        item for item in checklist
        if isinstance(item, dict) and item.get("done") is not True
    ]
    if unfinished:
        return {
            "error": "Checklist is incomplete; finish all acceptance checklist items before marking the task done.",
            "code": "checklist_incomplete",
            "unfinishedChecklist": [
                {
                    "id": item.get("id") or "",
                    "text": item.get("text") or "",
                }
                for item in unfinished[:20]
            ],
            "_status": 409,
        }
    was_completed = bool(task.get("completedAt"))
    _project_execution_transition(project, task, "done", actor, reason, attempt_id)
    task["completedAt"] = _proj_now()
    task["columnId"] = done_col.get("id")
    if not was_completed:
        _archive_trigger_task_completed(project.get("id"), task)
    return {"ok": True}

def _project_execution_incomplete_checklist_feedback(done_result):
    unfinished = done_result.get("unfinishedChecklist") if isinstance(done_result, dict) else []
    lines = []
    for item in unfinished or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if text:
            lines.append(f"- {text}")
    detail = "\n".join(lines) if lines else "- Review the task acceptance checklist and complete every unfinished item."
    return _project_execution_redact(
        "Acceptance checklist is incomplete. Continue executing the task until all acceptance checklist items are complete:\n"
        + detail
    )

def _project_execution_transient_failure_reason(result):
    text = " ".join(str(result.get(key) or "") for key in ("error", "reply", "status")).lower() if isinstance(result, dict) else ""
    if not text:
        return ""
    markers = (
        "llm request timed out",
        "gatewayclientrequesterror",
        "failovererror",
        "provider call exceeded",
        "provider_timeout",
        "provider timeout",
        "timed out",
        "timeout",
        "cooldown",
        "temporarily unavailable",
        "connection reset",
        "connection aborted",
        "gnutls",
    )
    for marker in markers:
        if marker in text:
            return marker
    return ""

def _project_execution_attempt_retry_count(attempt):
    try:
        return int((attempt or {}).get("transientRetryCount") or 0)
    except Exception:
        return 0

def _project_execution_schedule_transient_retry(data, project_id, task_id, project, task, attempt, evidence, reason):
    if _project_execution_attempt_retry_count(attempt) >= 1:
        return False
    workspace = _project_execution_validate_workspace(project.get("workspacePath"))
    if not workspace.get("ok"):
        return False
    retry_attempt_id = str(uuid.uuid4())
    retry_attempt = {
        **attempt,
        "id": retry_attempt_id,
        "status": "retrying",
        "startedAt": _proj_now(),
        "finishedAt": None,
        "evidence": {},
        "baseline": _project_execution_git_snapshot(workspace["path"]),
        "workspacePath": workspace["path"],
        "workspaceKind": workspace["kind"],
        "rework": False,
        "transientRetry": True,
        "transientRetryCount": _project_execution_attempt_retry_count(attempt) + 1,
        "retryFromAttemptId": attempt.get("id"),
        "retryReason": reason,
        "previousFailureEvidence": evidence,
    }
    attempt["status"] = "retry_scheduled"
    attempt["retryAttemptId"] = retry_attempt_id
    attempt["retryReason"] = reason
    task.setdefault("attempts", []).append(retry_attempt)
    task["attempts"] = task["attempts"][-20:]
    task.update({
        "activeAttemptId": retry_attempt_id,
        "blockedReason": None,
        "lastError": None,
        "executorAgentId": (retry_attempt.get("executor") or {}).get("id"),
        "reviewerAgentId": (retry_attempt.get("reviewer") or {}).get("id"),
    })
    project.update({
        "workspaceStatus": workspace,
        "workflowActive": True,
        "workflowPhase": "retrying",
        "activeTaskId": task_id,
        "activeAgent": (retry_attempt.get("executor") or {}).get("id"),
        "updatedAt": _proj_now(),
    })
    _project_execution_transition(project, task, "executing", "system", f"Provider timeout or transient gateway failure detected; retrying once ({reason}).", retry_attempt_id)
    _save_projects(data)
    cancel_flag = threading.Event()
    with _PROJECT_EXECUTION_LOCK:
        _PROJECT_EXECUTION_CANCEL_FLAGS[retry_attempt_id] = cancel_flag

    def retry_later():
        time.sleep(3)
        _project_execution_run_attempt(project_id, task_id, retry_attempt_id, cancel_flag)

    _project_execution_launch_thread(retry_later)
    return True

def _project_execution_continue_for_incomplete_checklist(data, project_id, task_id, project, task, attempt_id, actor, done_result):
    if not isinstance(done_result, dict) or done_result.get("code") != "checklist_incomplete":
        return {"ok": False, "error": (done_result or {}).get("error") or "Unable to mark task done"}
    workspace = _project_execution_validate_workspace(project.get("workspacePath"))
    if not workspace.get("ok"):
        task["blockedReason"] = workspace.get("error") or "Project workspace is not available for checklist completion."
        _project_execution_transition(project, task, "blocked", "system", task["blockedReason"], attempt_id)
        project.update({"workspaceStatus": workspace, "workflowActive": False, "workflowPhase": "blocked", "activeTaskId": None, "activeAgent": None, "updatedAt": _proj_now()})
        _save_projects(data)
        return {**workspace, "continued": False}
    roles = _project_execution_resolve_start_roles(project, task, allow_skip_reviewer=True)
    if not roles.get("ok"):
        task["blockedReason"] = roles.get("error") or "Project Execution roles are not available."
        _project_execution_transition(project, task, "blocked", "system", task["blockedReason"], attempt_id)
        project.update({"workflowActive": False, "workflowPhase": "blocked", "activeTaskId": None, "activeAgent": None, "updatedAt": _proj_now()})
        _save_projects(data)
        return {**roles, "continued": False}
    feedback = _project_execution_incomplete_checklist_feedback(done_result)
    task["reworkCount"] = int(task.get("reworkCount") or 0) + 1
    task["blockedReason"] = None
    task["lastError"] = None
    task["reworkFeedback"] = feedback
    rework_attempt_id = str(uuid.uuid4())
    rework_attempt = {
        "id": rework_attempt_id,
        "status": "reworking",
        "startedAt": _proj_now(),
        "workspacePath": workspace["path"],
        "workspaceKind": workspace["kind"],
        "dirtyConfirmed": False,
        "dirtyFingerprint": "",
        "executor": roles["executor"],
        "reviewer": roles.get("reviewer"),
        "skipReview": bool(roles.get("skipReview")),
        "skipReviewReason": roles.get("skipReviewReason"),
        "baseline": _project_execution_git_snapshot(workspace["path"]),
        "startMode": project.get("projectExecutionStartMode") or "continuous",
        "projectFlow": bool(project.get("projectExecutionFlowActive")),
        "requiresUserAcceptance": _project_execution_requires_user_acceptance(task),
        "rework": True,
        "reworkCycle": task["reworkCount"],
        "reworkFromAttemptId": attempt_id,
        "reworkFeedback": feedback,
        "autoReviewAfterExecution": not roles.get("skipReview"),
        "checklistCompletionRetry": True,
    }
    task.setdefault("attempts", []).append(rework_attempt)
    task["attempts"] = task["attempts"][-20:]
    task.update({
        "activeAttemptId": rework_attempt_id,
        "executorAgentId": roles["executor"]["id"],
        "reviewerAgentId": (roles.get("reviewer") or {}).get("id"),
        "reviewResult": {},
    })
    project.update({
        "workspaceStatus": workspace,
        "workflowActive": True,
        "workflowPhase": "reworking",
        "activeTaskId": task_id,
        "activeAgent": roles["executor"]["id"],
        "projectExecutionFlowActive": False,
        "projectExecutionFlowStopReason": "checklist_incomplete",
        "updatedAt": _proj_now(),
    })
    _project_execution_transition(project, task, "reworking", actor or "system", feedback, rework_attempt_id)
    _save_projects(data)
    cancel_flag = threading.Event()
    with _PROJECT_EXECUTION_LOCK:
        _PROJECT_EXECUTION_CANCEL_FLAGS[rework_attempt_id] = cancel_flag
    _project_execution_launch_thread(_project_execution_run_attempt, (project_id, task_id, rework_attempt_id, cancel_flag))
    return {"ok": True, "continued": True, "status": "reworking", "attemptId": rework_attempt_id}

def _project_execution_column_for_state(project, state):
    state = str(state or "").strip()
    if state in {"executing", "reworking", "awaiting_meeting_resolution"}:
        return _wf_get_inprogress_col(project)
    if state in {"execution_complete", "reviewing", "awaiting_user_acceptance"}:
        return _wf_get_review_col(project)
    if state == "done":
        return _wf_get_done_col(project)
    return None

def _project_execution_sync_task_column(project, task, state):
    col = _project_execution_column_for_state(project, state)
    if not col or not col.get("id"):
        return False
    if task.get("columnId") == col.get("id"):
        return False
    task["columnId"] = col.get("id")
    col_tasks = [t for t in project.get("tasks", []) if t is not task and t.get("columnId") == col.get("id")]
    task["order"] = max((t.get("order", 0) for t in col_tasks), default=-1) + 1
    return True

def _project_execution_move_task_to_column(project, task, col):
    if not col or not col.get("id"):
        return False
    if task.get("columnId") == col.get("id"):
        return False
    task["columnId"] = col.get("id")
    col_tasks = [t for t in project.get("tasks", []) if t is not task and t.get("columnId") == col.get("id")]
    task["order"] = max((t.get("order", 0) for t in col_tasks), default=-1) + 1
    return True

def _project_execution_transition(project, task, next_state, actor, reason, attempt_id=None):
    previous = task.get("executionState") or ("done" if task.get("completedAt") else "backlog")
    task["executionState"] = next_state
    task["updatedAt"] = _proj_now()
    if next_state != "done":
        task["completedAt"] = None
    _project_execution_sync_task_column(project, task, next_state)
    project["updatedAt"] = _proj_now()
    _log_activity(project, "project_execution_state_changed", actor, f"Project Execution task '{task.get('title', '')}' changed from {previous} to {next_state}: {reason}", task.get("id"))
    task.setdefault("stateHistory", []).append({"attemptId": attempt_id, "actor": actor, "from": previous, "to": next_state, "reason": _project_execution_redact(reason), "at": _proj_now()})
    task["stateHistory"] = task["stateHistory"][-100:]

def _project_execution_meeting_blocker_unresolved(blocker):
    if not isinstance(blocker, dict):
        return False
    return blocker.get("resolvedAt") in (None, "") and blocker.get("status") not in {"resolved_continue", "blocked", "cleared"}

def _project_execution_block_for_meeting_request(project_id, task_id, request, reason="AI meeting request created"):
    data, project, task = _project_execution_find(project_id, task_id)
    if not project or not task:
        return {"ok": False, "error": "Project or task not found", "_status": 404}
    now = _proj_now()
    active_attempt_id = task.get("activeAttemptId")
    if active_attempt_id:
        attempt = _project_execution_attempt(task, active_attempt_id)
        if attempt:
            attempt["status"] = "awaiting_meeting_resolution"
            attempt["meetingRequestId"] = request.get("id")
        with _PROJECT_EXECUTION_LOCK:
            flag = _PROJECT_EXECUTION_CANCEL_FLAGS.get(active_attempt_id)
            if flag:
                flag.set()
            _PROJECT_EXECUTION_REVIEW_FLAGS.discard(active_attempt_id)
        task["activeAttemptId"] = None
    task["blockedReason"] = None
    task["lastError"] = None
    task["meetingBlocker"] = {
        "requestId": request.get("id"),
        "meetingId": (request.get("conversion") or {}).get("meetingId") or "",
        "status": request.get("status") or "pending",
        "reason": _project_execution_redact(reason),
        "requestingAgentId": request.get("requestingAgentId") or "",
        "createdAt": request.get("createdAt") or now,
        "updatedAt": now,
        "awaitingUserDecision": False,
        "rejectionReason": "",
        "outcome": "",
    }
    project.update({
        "workflowActive": False,
        "workflowPhase": "awaiting_meeting_resolution",
        "activeTaskId": task_id,
        "activeAgent": request.get("requestingAgentId") or task.get("executorAgentId") or task.get("assignee"),
        "projectExecutionFlowActive": False,
        "projectExecutionFlowStopReason": "awaiting_meeting_resolution",
        "updatedAt": now,
    })
    _project_execution_transition(project, task, "awaiting_meeting_resolution", request.get("requestingAgentId") or "meeting-request", reason, request.get("id"))
    _save_projects(data)
    return {"ok": True, "project": project, "task": task}

def _project_execution_update_meeting_blocker(project_id, task_id, request_id, **updates):
    data, project, task = _project_execution_find(project_id, task_id)
    if not project or not task:
        return {"ok": False, "error": "Project or task not found", "_status": 404}
    blocker = task.get("meetingBlocker") if isinstance(task.get("meetingBlocker"), dict) else {}
    if request_id and blocker.get("requestId") and blocker.get("requestId") != request_id:
        return {"ok": False, "error": "Task is blocked by a different meeting request", "_status": 409}
    blocker.update({k: v for k, v in updates.items() if v is not None})
    blocker["requestId"] = blocker.get("requestId") or request_id
    blocker["updatedAt"] = _proj_now()
    task["meetingBlocker"] = blocker
    task["updatedAt"] = _proj_now()
    project["updatedAt"] = _proj_now()
    _save_projects(data)
    return {"ok": True, "project": project, "task": task}

def _project_execution_action_item_text(item):
    if not isinstance(item, dict):
        return str(item or "").strip()
    return str(item.get("title") or item.get("item") or item.get("text") or item.get("task") or item.get("action") or "").strip()

def _project_execution_action_item_description(item):
    if not isinstance(item, dict):
        return ""
    return str(item.get("description") or item.get("details") or item.get("note") or item.get("sourceText") or "").strip()

def _project_execution_action_item_owner(item):
    if not isinstance(item, dict):
        return ""
    return str(item.get("owner") or item.get("assignee") or item.get("responsible") or item.get("agent") or "").strip()

def _project_execution_normalize_meeting_risks(result):
    risks = []
    for key in ("risks", "riskItems", "concerns", "unresolvedQuestions", "disagreements"):
        raw = result.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, dict):
                text = str(item.get("title") or item.get("text") or item.get("summary") or item.get("question") or item.get("issue") or "").strip()
            else:
                text = str(item or "").strip()
            if text:
                risks.append(text)
    deduped = []
    seen = set()
    for text in risks:
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped

def _project_execution_task_executor_id(project, task):
    return str(task.get("executorAgentId") or task.get("assignee") or project.get("defaultExecutorAgentId") or "").strip()

def _project_execution_owner_matches(owner, agent_id):
    owner = str(owner or "").strip().lower()
    agent_id = str(agent_id or "").strip().lower()
    if not owner or not agent_id:
        return False
    return owner == agent_id

def _project_execution_meeting_action_key(meeting_id, action_id):
    return f"meeting:{meeting_id}:action:{action_id}"

def _project_execution_find_checklist_item(task, meeting_action_id):
    for item in task.get("checklist") or []:
        if isinstance(item, dict) and item.get("meetingActionItemId") == meeting_action_id:
            return item
    return None

def _project_execution_acceptance_checklist(task):
    return [
        item for item in (task.get("checklist") or [])
        if isinstance(item, dict) and item.get("source") not in {"meeting_action_item", "meeting_risk"}
    ]

def _project_execution_seed_acceptance_checklist(task, actor="system"):
    if _project_execution_acceptance_checklist(task):
        return False
    now = _proj_now()
    title = str(task.get("title") or "").strip()
    description = str(task.get("description") or "").strip()
    items = []
    if title:
        items.append(f"完成任务目标：{title}")
    else:
        items.append("完成任务描述中的交付目标")
    if description:
        compact = re.sub(r"\s+", " ", description).strip()
        if len(compact) > 96:
            compact = compact[:93].rstrip() + "..."
        items.append(f"交付内容覆盖任务描述：{compact}")
    items.append("确认会议结论和行动项已纳入最终交付")
    checklist = task.setdefault("checklist", [])
    existing = {_project_execution_checklist_compact_key(item.get("text")) for item in checklist if isinstance(item, dict)}
    changed = False
    for text in items:
        key = _project_execution_checklist_compact_key(text)
        if not key or key in existing:
            continue
        checklist.append({
            "id": "acceptance-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12],
            "text": text,
            "done": False,
            "source": "project_execution_acceptance",
            "createdAt": now,
            "createdBy": actor or "system",
        })
        existing.add(key)
        changed = True
    return changed

def _project_execution_checklist_key(text):
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()

def _project_execution_reset_checklist_completion(task):
    checklist = task.get("checklist")
    if not isinstance(checklist, list) or not checklist:
        return False
    task["checklist"] = [
        item for item in checklist
        if isinstance(item, dict) and item.get("source") in {"meeting_action_item", "meeting_risk"}
    ]
    return len(task["checklist"]) != len(checklist)

def _project_execution_checklist_compact_key(text):
    return re.sub(r"[\s，。；;、,.：:!！?？()\[\]{}<>《》\"'`]+", "", str(text or "").strip()).lower()

def _project_execution_checklist_prefix(text):
    raw = str(text or "").strip()
    for marker in ("：", ":"):
        if marker in raw:
            prefix = raw.split(marker, 1)[0].strip().lower()
            if prefix:
                return prefix
    return ""

def _project_execution_checklist_ascii_tokens(text):
    return [
        token.lower()
        for token in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_./+-]*", str(text or ""))
        if len(token) >= 3
    ]

def _project_execution_checklist_match_score(update_text, item_text):
    update_key = _project_execution_checklist_key(update_text)
    item_key = _project_execution_checklist_key(item_text)
    if not update_key or not item_key:
        return 0.0
    if update_key == item_key:
        return 1.0
    update_compact = _project_execution_checklist_compact_key(update_text)
    item_compact = _project_execution_checklist_compact_key(item_text)
    if not update_compact or not item_compact:
        return 0.0
    shorter, longer = sorted((update_compact, item_compact), key=len)
    if len(shorter) >= 12 and shorter in longer:
        return 0.94

    update_chars = {ch for ch in update_compact if not ch.isdigit()}
    item_chars = {ch for ch in item_compact if not ch.isdigit()}
    char_overlap = (len(update_chars & item_chars) / max(1, len(update_chars))) if update_chars else 0.0
    sequence_ratio = difflib.SequenceMatcher(None, update_compact, item_compact).ratio()
    prefix_bonus = 0.12 if _project_execution_checklist_prefix(update_text) and _project_execution_checklist_prefix(update_text) == _project_execution_checklist_prefix(item_text) else 0.0
    ascii_tokens = _project_execution_checklist_ascii_tokens(update_text)
    if ascii_tokens:
        present = sum(1 for token in ascii_tokens if token in item_key)
        ascii_bonus = 0.16 * (present / len(ascii_tokens))
    else:
        ascii_bonus = 0.0
    return min(0.99, (0.50 * char_overlap) + (0.28 * sequence_ratio) + prefix_bonus + ascii_bonus)

def _project_execution_find_checklist_update_target(checklist, update):
    update_id = update.get("id")
    if update_id:
        for item in checklist:
            if str(item.get("id") or "") == update_id:
                return item
    text = update.get("text")
    if not text:
        return None
    update_key = _project_execution_checklist_key(text)
    for item in checklist:
        if _project_execution_checklist_key(item.get("text")) == update_key:
            return item
    scored = [
        (_project_execution_checklist_match_score(text, item.get("text")), item)
        for item in checklist
        if item.get("text")
    ]
    scored = [entry for entry in scored if entry[0] >= 0.72]
    if not scored:
        return None
    scored.sort(key=lambda entry: entry[0], reverse=True)
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.08:
        return None
    return scored[0][1]

def _project_execution_checklist_done_value(value):
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().lower()
    if raw in {"done", "complete", "completed", "pass", "passed", "verified", "true", "yes", "完成", "已完成", "通过"}:
        return True
    if raw in {"todo", "pending", "incomplete", "failed", "false", "no", "未完成", "待完成", "失败"}:
        return False
    return None

def _project_execution_result_checklist_updates(result):
    candidates = []
    for value in (result.get("checklistUpdates"), result.get("checklistVerification")):
        if isinstance(value, dict):
            items = value.get("items") or value.get("checklist") or []
            if isinstance(items, list):
                candidates.extend(items)
        elif isinstance(value, list):
            candidates.extend(value)
    parsed = _project_execution_extract_json(result.get("reply") or "")
    if isinstance(parsed, dict):
        for key in ("checklistUpdates", "checklistVerification", "checklist"):
            value = parsed.get(key)
            if isinstance(value, dict):
                items = value.get("items") or value.get("checklist") or []
                if isinstance(items, list):
                    candidates.extend(items)
            elif isinstance(value, list):
                candidates.extend(value)
        if isinstance(parsed.get("items"), list) and any(k in parsed for k in ("checklistStatus", "checklistSummary")):
            candidates.extend(parsed.get("items") or [])
    updates = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        done = _project_execution_checklist_done_value(item.get("done") if "done" in item else item.get("status"))
        if done is None:
            continue
        updates.append({
            "id": str(item.get("id") or item.get("checklistItemId") or "").strip(),
            "text": str(item.get("text") or item.get("title") or item.get("item") or "").strip(),
            "done": done,
            "evidence": _project_execution_redact(item.get("evidence") or item.get("summary") or item.get("reason") or ""),
        })
    return updates[:100]

def _project_execution_checklist_update_key(update):
    raw = str(update.get("id") or "").strip()
    if raw:
        return raw
    text_key = _project_execution_checklist_compact_key(update.get("text"))
    return "checklist-" + hashlib.sha256(text_key.encode("utf-8")).hexdigest()[:12] if text_key else _proj_uuid()

def _project_execution_apply_checklist_updates(task, result):
    checklist = _project_execution_acceptance_checklist(task)
    allow_create = not checklist
    changed = False
    now = _proj_now()
    for update in _project_execution_result_checklist_updates(result):
        item = _project_execution_find_checklist_update_target(checklist, update)
        if not item and allow_create and update.get("text"):
            item = {
                "id": _project_execution_checklist_update_key(update),
                "text": update.get("text"),
                "done": False,
                "source": "project_execution_acceptance",
                "createdAt": now,
            }
            task.setdefault("checklist", []).append(item)
            checklist.append(item)
            changed = True
        if not item:
            continue
        if update.get("done") is True and item.get("done") is not True:
            item["done"] = True
            item["completedAt"] = now
            item["completedBy"] = "executor"
            if update.get("evidence"):
                item["completionEvidence"] = update["evidence"]
            changed = True
    return changed

def _project_execution_result_meeting_discussion_points(result):
    candidates = []
    for value in (result.get("meetingDiscussionPoints"), result.get("discussionPoints"), result.get("meetingNotes")):
        if isinstance(value, list):
            candidates.extend(value)
    parsed = _project_execution_extract_json(result.get("reply") or "")
    if isinstance(parsed, dict):
        for key in ("meetingDiscussionPoints", "discussionPoints", "meetingNotes"):
            value = parsed.get(key)
            if isinstance(value, list):
                candidates.extend(value)
    points = []
    for item in candidates:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("summary") or item.get("note") or item.get("risk") or item.get("decision") or "").strip()
            if not text:
                continue
            kind = str(item.get("kind") or item.get("type") or ("risk" if item.get("risk") else "note")).strip().lower()
            if kind not in {"decision", "risk", "note"}:
                kind = "note"
            title = str(item.get("title") or ("会议结论" if kind == "decision" else "风险" if kind == "risk" else "要点")).strip()
            meeting_id = str(item.get("meetingId") or item.get("meeting_id") or "").strip()
            request_id = str(item.get("requestId") or item.get("request_id") or "").strip()
        else:
            text = str(item or "").strip()
            if not text:
                continue
            kind = "note"
            title = "要点"
            meeting_id = ""
            request_id = ""
        points.append({
            "id": "",
            "meetingId": meeting_id,
            "requestId": request_id,
            "kind": kind,
            "title": title,
            "text": _project_execution_redact(text),
        })
    return points[:100]

def _project_execution_apply_meeting_discussion_points(task, result):
    points = _project_execution_result_meeting_discussion_points(result)
    if not points:
        return False
    now = _proj_now()
    task.setdefault("meetingDiscussionPoints", [])
    existing_ids = {str(p.get("id") or "") for p in task.get("meetingDiscussionPoints") or [] if isinstance(p, dict)}
    changed = False
    for point in points:
        point_id = _project_execution_meeting_discussion_key(point.get("meetingId") or "executor", point.get("kind") or "note", point.get("text"))
        if point_id in existing_ids:
            continue
        task["meetingDiscussionPoints"].append({
            "id": point_id,
            "meetingId": point.get("meetingId") or "",
            "requestId": point.get("requestId") or "",
            "kind": point.get("kind") or "note",
            "title": point.get("title") or "要点",
            "text": point.get("text") or "",
            "createdAt": now,
        })
        existing_ids.add(point_id)
        changed = True
    return changed

def _project_execution_meeting_discussion_key(meeting_id, kind, text):
    digest = hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:10]
    return f"meeting:{meeting_id}:discussion:{kind}:{digest}"

def _project_execution_meeting_record_key(meeting_id, request_id):
    key = str(meeting_id or request_id or "unknown").strip()
    return f"meeting:{key}:record"

def _project_execution_meeting_action_summaries(result):
    raw_items = result.get("actionItems") if isinstance(result.get("actionItems"), list) else []
    summaries = []
    for idx, raw in enumerate(raw_items):
        title = _project_execution_action_item_text(raw)
        if not title:
            continue
        owner = _project_execution_action_item_owner(raw)
        raw_action_id = (raw or {}).get("id") if isinstance(raw, dict) else ""
        action_id = str(raw_action_id).strip() if raw_action_id is not None else ""
        summaries.append({
            "id": action_id or f"ai-{idx + 1}",
            "title": title,
            "owner": owner,
        })
    return summaries

def _project_execution_upsert_meeting_record(task, meeting, result, request_id, outcome, now=None):
    if not isinstance(task, dict) or not isinstance(meeting, dict):
        return False
    now = now or _proj_now()
    meeting_id = str(meeting.get("id") or "").strip()
    request_id = str(request_id or "").strip()
    outcome = _meeting_result_outcome(outcome) or "needs_user_decision"
    decision_text = str(result.get("decision") or result.get("summary") or "").strip()
    summary_text = str(result.get("summary") or "").strip()
    if not decision_text:
        if outcome == "no_consensus":
            decision_text = "No consensus was reached."
        elif outcome == "rejected":
            decision_text = "Meeting rejected the current path."
        elif outcome == "needs_user_decision":
            decision_text = "Meeting requires user decision."
    action_summaries = _project_execution_meeting_action_summaries(result)
    record = {
        "id": _project_execution_meeting_record_key(meeting_id, request_id),
        "meetingId": meeting_id,
        "requestId": request_id,
        "outcome": outcome,
        "status": outcome,
        "decision": _project_execution_redact(decision_text),
        "summary": _project_execution_redact(summary_text),
        "risks": [_project_execution_redact(risk) for risk in _project_execution_normalize_meeting_risks(result)],
        "actionItems": action_summaries,
        "actionItemCount": len(action_summaries),
        "appliedAt": now,
        "updatedAt": now,
    }
    task.setdefault("meetingRecords", [])
    existing = next((item for item in task["meetingRecords"] if isinstance(item, dict) and str(item.get("id") or "") == record["id"]), None)
    if existing:
        created_at = existing.get("createdAt") or existing.get("appliedAt") or now
        stable_keys = ("meetingId", "requestId", "outcome", "status", "decision", "summary", "risks", "actionItems", "actionItemCount")
        previous_stable = {key: existing.get(key) for key in stable_keys}
        next_stable = {key: record.get(key) for key in stable_keys}
        if previous_stable == next_stable:
            return False
        existing.update(record)
        existing["createdAt"] = created_at
        return True
    record["createdAt"] = now
    task["meetingRecords"].append(record)
    task["meetingRecords"].sort(key=lambda item: str((item or {}).get("appliedAt") or (item or {}).get("createdAt") or ""))
    return True

def _project_execution_all_required_meeting_actions_done(task):
    actions = task.get("meetingActionItems") if isinstance(task.get("meetingActionItems"), list) else []
    required = [a for a in actions if isinstance(a, dict) and a.get("requiredForResume") is True and a.get("status") != "external_task_created"]
    return all(a.get("status") == "completed" for a in required)

def _project_execution_mark_meeting_actions_completed(project, task, attempt_id, actor):
    changed = False
    now = _proj_now()
    for item in task.get("meetingActionItems") or []:
        if not isinstance(item, dict):
            continue
        if item.get("requiredForResume") is True and item.get("status") == "pending":
            item["status"] = "completed"
            item["completedAt"] = now
            item["completedBy"] = actor or task.get("executorAgentId") or task.get("assignee") or "executor"
            item["completionAttemptId"] = attempt_id
            changed = True
    if changed:
        task["updatedAt"] = now
        project["updatedAt"] = now
        _log_activity(project, "meeting_action_items_completed", actor or "executor", f"Completed meeting action items for '{task.get('title', '')}'", task.get("id"))
    return changed

def _project_execution_has_pending_meeting_actions(task):
    actions = task.get("meetingActionItems") if isinstance(task.get("meetingActionItems"), list) else []
    return any(isinstance(a, dict) and a.get("requiredForResume") is True and a.get("status") == "pending" for a in actions)

def _project_execution_apply_meeting_output_to_task(project, task, meeting, result, request_id):
    meeting_id = str(meeting.get("id") or "").strip()
    executor_id = _project_execution_task_executor_id(project, task)
    now = _proj_now()
    applied = 0
    linked = 0
    risks_added = 0
    checklist_seeded = _project_execution_seed_acceptance_checklist(task, "meeting")
    record_changed = _project_execution_upsert_meeting_record(task, meeting, result, request_id, "approved", now)
    task.setdefault("meetingActionItems", [])
    task.setdefault("meetingDecisionHistory", [])
    task.setdefault("meetingDiscussionPoints", [])
    existing_action_ids = {str(a.get("id") or "") for a in task.get("meetingActionItems") or [] if isinstance(a, dict)}
    existing_discussion_ids = {str(p.get("id") or "") for p in task.get("meetingDiscussionPoints") or [] if isinstance(p, dict)}
    decision_key = f"meeting:{meeting_id}:decision"
    if decision_key not in {str(d.get("id") or "") for d in task.get("meetingDecisionHistory") or [] if isinstance(d, dict)}:
        decision_text = str(result.get("decision") or result.get("summary") or "").strip()
        if decision_text:
            task["meetingDecisionHistory"].append({
                "id": decision_key,
                "meetingId": meeting_id,
                "requestId": request_id,
                "decision": _project_execution_redact(decision_text),
                "summary": _project_execution_redact(str(result.get("summary") or "")),
                "appliedAt": now,
            })
            discussion_id = _project_execution_meeting_discussion_key(meeting_id, "decision", decision_text)
            if discussion_id not in existing_discussion_ids:
                task["meetingDiscussionPoints"].append({
                    "id": discussion_id,
                    "meetingId": meeting_id,
                    "requestId": request_id,
                    "kind": "decision",
                    "title": "会议结论",
                    "text": _project_execution_redact(decision_text),
                    "createdAt": now,
                })
                existing_discussion_ids.add(discussion_id)
    raw_items = result.get("actionItems") if isinstance(result.get("actionItems"), list) else []
    for idx, raw in enumerate(raw_items):
        title = _project_execution_action_item_text(raw)
        if not title:
            continue
        raw_action_id = (raw or {}).get("id") if isinstance(raw, dict) else ""
        action_id = str(raw_action_id).strip() if raw_action_id is not None else ""
        if not action_id:
            action_id = f"ai-{idx + 1}"
        meeting_action_id = _project_execution_meeting_action_key(meeting_id, action_id)
        if meeting_action_id in existing_action_ids:
            continue
        description = _project_execution_action_item_description(raw)
        owner = _project_execution_action_item_owner(raw) or executor_id
        raw_priority = (raw or {}).get("priority") if isinstance(raw, dict) else ""
        priority = str(raw_priority).strip() if raw_priority is not None else ""
        priority = priority or "medium"
        if _is_archive_manager_agent(owner):
            continue
        task["meetingActionItems"].append({
            "id": meeting_action_id,
            "meetingId": meeting_id,
            "requestId": request_id,
            "sourceActionItemId": action_id,
            "title": title,
            "description": description,
            "owner": owner or executor_id,
            "status": "pending",
            "requiredForResume": True,
            "priority": priority,
            "createdAt": now,
            "updatedAt": now,
        })
        existing_action_ids.add(meeting_action_id)
        applied += 1
    for risk in _project_execution_normalize_meeting_risks(result):
        risk_id = _project_execution_meeting_discussion_key(meeting_id, "risk", risk)
        risk_text = _project_execution_redact(risk)
        if risk_id not in existing_discussion_ids:
            task["meetingDiscussionPoints"].append({
                "id": risk_id,
                "meetingId": meeting_id,
                "requestId": request_id,
                "kind": "risk",
                "title": "风险",
                "text": risk_text,
                "createdAt": now,
            })
            existing_discussion_ids.add(risk_id)
            risks_added += 1
    if applied or linked or risks_added or checklist_seeded or record_changed:
        task["updatedAt"] = now
        project["updatedAt"] = now
        summary = f"Applied meeting {meeting_id}: {applied} task action item(s), {risks_added} risk comment(s)"
        if checklist_seeded:
            summary += ", seeded acceptance checklist"
        if record_changed:
            summary += ", recorded meeting conclusion"
        _log_activity(project, "meeting_result_applied_to_task", "meeting", summary, task.get("id"))
    return {"applied": applied, "linked": linked, "risks": risks_added, "meetingRecordChanged": record_changed, "checklistSeeded": checklist_seeded, "pendingRequired": _project_execution_has_pending_meeting_actions(task)}

def _project_execution_apply_meeting_result(meeting):
    if not isinstance(meeting, dict):
        return {"ok": False, "skipped": True, "reason": "invalid_meeting"}
    source = meeting.get("source") if isinstance(meeting.get("source"), dict) else {}
    request_id = str(source.get("meetingRequestId") or "").strip()
    project_id = str(meeting.get("projectId") or source.get("projectId") or "").strip()
    task_id = str(source.get("taskId") or "").strip()
    if not (request_id and project_id and task_id):
        return {"ok": True, "skipped": True, "reason": "not_project_task_meeting_request"}
    result = meeting.get("result") if isinstance(meeting.get("result"), dict) else {}
    outcome = _meeting_result_outcome(result.get("outcome") or result.get("status") or result.get("result"))
    if not outcome and meeting.get("stage") in {"cancelled", "failed"}:
        outcome = "needs_user_decision"
    data, project, task = _project_execution_find(project_id, task_id)
    if not project or not task:
        return {"ok": False, "error": "Project or task not found", "_status": 404}
    blocker = task.get("meetingBlocker") if isinstance(task.get("meetingBlocker"), dict) else {}
    if blocker.get("requestId") != request_id:
        return {"ok": True, "skipped": True, "reason": "task_not_blocked_by_meeting"}
    now = _proj_now()
    blocker.update({
        "meetingId": meeting.get("id") or blocker.get("meetingId") or "",
        "outcome": outcome or "needs_user_decision",
        "decision": _project_execution_redact(result.get("decision") or result.get("summary") or ""),
        "updatedAt": now,
    })
    if outcome == "approved":
        blocker.update({"status": "resolved_continue", "resolvedAt": now, "awaitingUserDecision": False})
        _meeting_request_resolve_task_blocker(request_id, "resolved_continue", {"meetingId": meeting.get("id") or "", "outcome": outcome})
        task["meetingBlocker"] = blocker
        task["blockedReason"] = None
        task["lastError"] = None
        task["activeAttemptId"] = None
        applied = _project_execution_apply_meeting_output_to_task(project, task, meeting, result, request_id)
        for risk in _project_execution_normalize_meeting_risks(result):
            risk_id = _project_execution_meeting_discussion_key(meeting.get("id") or "", "risk", risk)
            comments = task.setdefault("comments", [])
            if not any(isinstance(c, dict) and c.get("id") == risk_id and c.get("source") == "meeting_risk" for c in comments):
                comments.append({
                    "id": risk_id,
                    "text": _project_execution_redact(risk),
                    "author": "meeting",
                    "source": "meeting_risk",
                    "meetingId": meeting.get("id") or "",
                    "requestId": request_id,
                    "createdAt": now,
                })
        resume_reason = f"Meeting {meeting.get('id')} reached consensus"
        if applied.get("pendingRequired"):
            resume_reason += "; meeting action items must be completed before original task resumes."
        else:
            resume_reason += "; task may continue."
        _project_execution_transition(project, task, "backlog", "meeting", resume_reason, request_id)
        _project_execution_move_task_to_column(project, task, _wf_get_backlog_col(project))
        project.update({"workflowActive": False, "workflowPhase": "meeting_resolved_continue", "activeTaskId": None, "activeAgent": None, "projectExecutionFlowActive": project.get("projectExecutionStartMode") == "continuous", "projectExecutionFlowStopReason": None, "updatedAt": now})
        _save_projects(data)
        _project_execution_launch_thread(lambda: (_server_callable("_handle_project_execution_start") or _handle_project_execution_start)(project_id, task_id, {"projectStart": True, "mode": project.get("projectExecutionStartMode") or "continuous", "autoReviewAfterExecution": True, "by": "meeting"}))
        return {"ok": True, "status": "resolved_continue", "taskId": task_id, "appliedMeetingResult": applied}
    if outcome in {"rejected", "no_consensus"}:
        blocker.update({"status": "blocked", "resolvedAt": now, "awaitingUserDecision": False})
        _meeting_request_resolve_task_blocker(request_id, "blocked", {"meetingId": meeting.get("id") or "", "outcome": outcome})
        task["meetingBlocker"] = blocker
        task["blockedReason"] = result.get("decision") or result.get("summary") or "Meeting ended without consensus."
        _project_execution_upsert_meeting_record(task, meeting, result, request_id, outcome, now)
        _project_execution_transition(project, task, "blocked", "meeting", task["blockedReason"], request_id)
        project.update({"workflowActive": False, "workflowPhase": "blocked", "activeTaskId": None, "activeAgent": None, "projectExecutionFlowActive": False, "projectExecutionFlowStopReason": "meeting_no_consensus", "updatedAt": now})
        _save_projects(data)
        return {"ok": True, "status": "blocked", "taskId": task_id}
    blocker.update({"status": "needs_user_decision", "awaitingUserDecision": True})
    task["meetingBlocker"] = blocker
    _project_execution_upsert_meeting_record(task, meeting, result, request_id, "needs_user_decision", now)
    _project_execution_transition(project, task, "awaiting_meeting_resolution", "meeting", "Meeting requires user decision before task can continue.", request_id)
    project.update({"workflowActive": False, "workflowPhase": "awaiting_meeting_resolution", "activeTaskId": task_id, "activeAgent": None, "projectExecutionFlowActive": False, "projectExecutionFlowStopReason": "meeting_needs_user_decision", "updatedAt": now})
    _save_projects(data)
    return {"ok": True, "status": "needs_user_decision", "taskId": task_id}

def _handle_project_execution_workspace_validate(project_id, body):
    data, project, _ = _project_execution_find(project_id)
    if not project:
        return {"error": "Project not found", "_status": 404}
    result = _project_execution_validate_workspace(body.get("workspacePath") or project.get("workspacePath"))
    if not result.get("ok"):
        project["projectExecutionEnabled"] = True
        project["workspacePath"] = body.get("workspacePath") or project.get("workspacePath")
        project["workspaceStatus"] = result
        project["updatedAt"] = _proj_now()
        _save_projects(data)
        return {**result, "_status": 400}
    project.update({"projectExecutionEnabled": True, "workspacePath": result["path"], "workspaceKind": result["kind"], "workspaceStatus": result, "updatedAt": _proj_now()})
    _save_projects(data)
    return {"ok": True, "workspace": result}

def _artifact_kind_for_ext(ext):
    ext = (ext or "").lower()
    if ext in _ARTIFACT_MARKDOWN_EXTENSIONS:
        return "markdown"
    if ext in _ARTIFACT_TEXT_EXTENSIONS:
        return "text"
    if ext == ".pdf":
        return "pdf"
    if ext in _ARTIFACT_IMAGE_EXTENSIONS:
        return "image"
    if ext in _ARTIFACT_VIDEO_EXTENSIONS:
        return "video"
    if ext in _ARTIFACT_AUDIO_EXTENSIONS:
        return "audio"
    return "file"

def _artifact_normalize_relpath(path):
    rel = urllib.parse.unquote(str(path or "")).replace("\\", "/").lstrip("/")
    parts = [part for part in rel.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        return ""
    return "/".join(parts)

def _artifact_safe_path(root, rel_path):
    root = os.path.realpath(root)
    rel = _artifact_normalize_relpath(rel_path)
    if not rel:
        return None, ""
    full_path = os.path.realpath(os.path.join(root, rel))
    if not (full_path == root or full_path.startswith(root + os.sep)):
        return None, rel
    return full_path, rel

def _artifact_source_relpath(root, path):
    raw = urllib.parse.unquote(str(path or "")).replace("\\", "/")
    if len(raw) > 2 and raw[:2] in ("a/", "b/") and (raw[2:3] == "/" or raw[3:4] == ":"):
        raw = raw[2:]
    if os.path.isabs(raw):
        root_real = os.path.realpath(root or "")
        full_path = os.path.realpath(raw)
        if root_real and (full_path == root_real or full_path.startswith(root_real + os.sep)):
            return os.path.relpath(full_path, root_real).replace(os.sep, "/")
        return ""
    return _artifact_normalize_relpath(raw)

def _artifact_context_list(context, allowed_extensions=None, associated_only=False):
    root = os.path.realpath(context.get("root") or "")
    if not root or not os.path.isdir(root):
        return {"error": "Artifact root is not accessible", "_status": 409}
    allowed_extensions = allowed_extensions or _ARTIFACT_MARKDOWN_EXTENSIONS
    sources_by_path = context.get("sourcesByPath") or {}
    artifacts = []
    truncated = False
    try:
        for current_root, dirs, files in os.walk(root):
            dirs[:] = [
                d for d in dirs
                if d not in _ARTIFACT_EXCLUDE_DIRS and not d.startswith(".git")
            ]
            rel_dir = os.path.relpath(current_root, root)
            depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1
            if depth > 8:
                dirs[:] = []
                continue
            for name in files:
                ext = os.path.splitext(name)[1].lower()
                if ext not in allowed_extensions:
                    continue
                full_path = os.path.realpath(os.path.join(current_root, name))
                if not (full_path == root or full_path.startswith(root + os.sep)):
                    continue
                try:
                    stat = os.stat(full_path)
                except OSError:
                    continue
                rel_path = os.path.relpath(full_path, root).replace(os.sep, "/")
                source_records = sources_by_path.get(rel_path, [])
                if associated_only and not source_records:
                    continue
                artifacts.append({
                    "path": rel_path,
                    "name": name,
                    "kind": _artifact_kind_for_ext(ext),
                    "extension": ext,
                    "size": stat.st_size,
                    "modifiedAt": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    "sources": source_records[:10],
                    "unassociated": not bool(source_records),
                })
                if len(artifacts) >= _ARTIFACT_MAX_ITEMS:
                    truncated = True
                    break
            if truncated:
                break
    except OSError as exc:
        return {"error": f"Unable to scan artifacts: {exc}", "_status": 500}
    artifacts.sort(key=lambda item: (item.get("modifiedAt") or "", item.get("path") or ""), reverse=True)
    return {"ok": True, "artifacts": artifacts, "truncated": truncated}

def _artifact_context_read(context, rel_path, allow_text=False):
    root = os.path.realpath(context.get("root") or "")
    if not root or not os.path.isdir(root):
        return {"error": "Artifact root is not accessible", "_status": 409}
    full_path, rel = _artifact_safe_path(root, rel_path)
    if not rel:
        return {"error": "Artifact path is required", "_status": 400}
    if not full_path:
        return {"error": "Artifact path is outside the artifact root", "_status": 403}
    ext = os.path.splitext(rel)[1].lower()
    allowed = _ARTIFACT_TEXT_EXTENSIONS if allow_text else _ARTIFACT_MARKDOWN_EXTENSIONS
    if ext not in allowed:
        return {"error": "Only text artifacts can be read inline" if allow_text else "Only Markdown artifacts can be read inline", "_status": 415}
    if not os.path.isfile(full_path):
        return {"error": "Artifact not found", "_status": 404}
    try:
        size = os.path.getsize(full_path)
        with open(full_path, "rb") as f:
            raw = f.read(_ARTIFACT_MAX_READ_BYTES + 1)
        truncated = len(raw) > _ARTIFACT_MAX_READ_BYTES
        if truncated:
            raw = raw[:_ARTIFACT_MAX_READ_BYTES]
        content = raw.decode("utf-8", errors="replace")
    except OSError as exc:
        return {"error": f"Unable to read artifact: {exc}", "_status": 500}
    return {"ok": True, "artifact": {"path": rel, "kind": _artifact_kind_for_ext(ext), "size": size, "truncated": truncated, "content": content}}

def _artifact_context_file_response(context, rel_path):
    root = os.path.realpath(context.get("root") or "")
    if not root or not os.path.isdir(root):
        return {"error": "Artifact root is not accessible", "_status": 409}
    full_path, rel = _artifact_safe_path(root, rel_path)
    if not rel:
        return {"error": "Artifact path is required", "_status": 400}
    if not full_path:
        return {"error": "Artifact path is outside the artifact root", "_status": 403}
    if not os.path.isfile(full_path):
        return {"error": "Artifact not found", "_status": 404}
    ext = os.path.splitext(rel)[1].lower()
    if ext not in _ARTIFACT_ALLOWED_EXTENSIONS:
        return {"error": "Artifact type is not previewable", "_status": 415}
    sources_by_path = context.get("sourcesByPath") or {}
    if not sources_by_path.get(rel):
        return {"error": "Artifact is not associated with this project", "_status": 403}
    return {"ok": True, "path": full_path, "rel": rel, "kind": _artifact_kind_for_ext(ext)}

def _artifact_context_delete(context, rel_path):
    root = os.path.realpath(context.get("root") or "")
    if not root or not os.path.isdir(root):
        return {"error": "Artifact root is not accessible", "_status": 409}
    full_path, rel = _artifact_safe_path(root, rel_path)
    if not rel:
        return {"error": "Artifact path is required", "_status": 400}
    if not full_path:
        return {"error": "Artifact path is outside the artifact root", "_status": 403}
    if not os.path.isfile(full_path):
        return {"error": "Artifact not found", "_status": 404}
    ext = os.path.splitext(rel)[1].lower()
    if ext not in _ARTIFACT_ALLOWED_EXTENSIONS:
        return {"error": "Artifact type is not deletable here", "_status": 415}
    try:
        os.remove(full_path)
    except OSError as exc:
        return {"error": f"Unable to delete artifact: {exc}", "_status": 500}
    return {"ok": True, "deleted": rel}

def _artifact_context_delete_dir(context, rel_dir):
    root = os.path.realpath(context.get("root") or "")
    if not root or not os.path.isdir(root):
        return {"error": "Artifact root is not accessible", "_status": 409}
    if rel_dir:
        full_path, rel = _artifact_safe_path(root, rel_dir)
        if not full_path:
            return {"error": "Artifact path is outside the artifact root", "_status": 403}
        if not os.path.isdir(full_path):
            return {"error": "Artifact directory not found", "_status": 404}
    else:
        full_path, rel = root, ""
    deleted = 0
    try:
        for current_root, dirs, files in os.walk(full_path, topdown=False):
            current_real = os.path.realpath(current_root)
            if not (current_real == root or current_real.startswith(root + os.sep)):
                continue
            for name in files:
                file_path = os.path.realpath(os.path.join(current_root, name))
                if not (file_path == root or file_path.startswith(root + os.sep)):
                    continue
                file_rel = os.path.relpath(file_path, root).replace(os.sep, "/")
                if os.path.splitext(file_rel)[1].lower() not in _ARTIFACT_ALLOWED_EXTENSIONS:
                    continue
                os.remove(file_path)
                deleted += 1
            if current_real != root:
                try:
                    os.rmdir(current_real)
                except OSError:
                    pass
    except OSError as exc:
        return {"error": f"Unable to delete artifact directory: {exc}", "_status": 500}
    return {"ok": True, "deletedDir": rel, "deleted": deleted}

def _project_artifact_source_records(project):
    sources_by_path = {}
    workspace_root = project.get("workspacePath") or ""

    def markdown_paths_from_evidence(evidence):
        paths = []
        changed_files = evidence.get("changedFiles") if isinstance(evidence, dict) else []
        if isinstance(changed_files, list):
            paths.extend(changed_files)
        text_parts = []
        if isinstance(evidence, dict):
            for key in ("executorSummary", "summary", "reply"):
                value = evidence.get(key)
                if value:
                    text_parts.append(str(value))
        if text_parts:
            text = "\n".join(text_parts)
            pattern = r"(?:(?:[A-Za-z]:)?[/~][^\s`'\"<>|]+|[A-Za-z0-9_.-][^\s`'\"<>|]*)\.(?:md|markdown)"
            paths.extend(match.group(0).strip(").,;:") for match in re.finditer(pattern, text, flags=re.IGNORECASE))
        return paths

    def add_sources(task, evidence, attempt=None):
        candidate_paths = markdown_paths_from_evidence(evidence)
        if not candidate_paths:
            return
        provider_ref = evidence.get("providerRef") or {}
        executor = (attempt or {}).get("executor") or {}
        attempt_id = evidence.get("attemptId") or (attempt or {}).get("id") or ""
        captured_at = evidence.get("capturedAt") or (attempt or {}).get("finishedAt") or (attempt or {}).get("startedAt") or ""
        agent_id = provider_ref.get("agentId") or executor.get("id") or task.get("executorAgentId") or task.get("assignee") or ""
        provider_kind = provider_ref.get("providerKind") or executor.get("providerKind") or ""
        seen_rels = set()
        for path in candidate_paths:
            rel = _artifact_source_relpath(workspace_root, path)
            if os.path.splitext(rel)[1].lower() not in _ARTIFACT_ALLOWED_EXTENSIONS:
                continue
            full_path, safe_rel = _artifact_safe_path(workspace_root, rel)
            if not full_path or not os.path.isfile(full_path):
                continue
            rel = safe_rel
            if rel in seen_rels:
                continue
            seen_rels.add(rel)
            record = {
                "sourceType": "project_execution",
                "contextType": "project",
                "taskId": task.get("id"),
                "taskTitle": task.get("title", ""),
                "attemptId": attempt_id,
                "agentId": agent_id,
                "providerKind": provider_kind,
                "capturedAt": captured_at,
            }
            records = sources_by_path.setdefault(rel, [])
            identity = (record["taskId"], record["attemptId"], record["agentId"], record["providerKind"], record["capturedAt"])
            if not any((item.get("taskId"), item.get("attemptId"), item.get("agentId"), item.get("providerKind"), item.get("capturedAt")) == identity for item in records):
                records.append(record)

    for task in project.get("tasks", []):
        evidence = task.get("evidence") or {}
        if isinstance(evidence, dict):
            add_sources(task, evidence)
        for attempt in task.get("attempts") or []:
            attempt_evidence = attempt.get("evidence") or {}
            if isinstance(attempt_evidence, dict):
                add_sources(task, attempt_evidence, attempt)
    for rel, records in sources_by_path.items():
        records.sort(key=lambda item: item.get("capturedAt") or "", reverse=True)
        sources_by_path[rel] = records[:20]
    return sources_by_path

def _project_artifact_context(project):
    if not _project_execution_enabled(project):
        return {"ok": False, "error": "Project Execution workspace is required for artifacts", "_status": 409}
    workspace = _project_execution_validate_workspace(project.get("workspacePath"))
    if not workspace.get("ok"):
        return {**workspace, "_status": 409}
    return {
        "ok": True,
        "contextType": "project",
        "contextId": project.get("id"),
        "contextTitle": project.get("title", ""),
        "root": workspace["path"],
        "rootKind": workspace.get("kind"),
        "sourcesByPath": _project_artifact_source_records(project),
    }

def _handle_project_artifacts_list(project_id):
    _, project, _ = _project_execution_find(project_id)
    if not project:
        return {"error": "Project not found", "_status": 404}
    context = _project_artifact_context(project)
    if not context.get("ok"):
        return context
    result = _artifact_context_list(context)
    if not result.get("ok"):
        return result
    return {
        "ok": True,
        "context": {
            "type": context.get("contextType"),
            "id": context.get("contextId"),
            "title": context.get("contextTitle"),
            "root": context.get("root"),
            "rootKind": context.get("rootKind"),
        },
        "artifacts": result.get("artifacts", []),
        "truncated": result.get("truncated", False),
    }

def _handle_project_artifact_read(project_id, query_string=""):
    _, project, _ = _project_execution_find(project_id)
    if not project:
        return {"error": "Project not found", "_status": 404}
    context = _project_artifact_context(project)
    if not context.get("ok"):
        return context
    params = urllib.parse.parse_qs(query_string or "")
    rel_path = (params.get("path") or [""])[0]
    allow_text = (params.get("archive") or [""])[0] in ("1", "true", "yes")
    return _artifact_context_read(context, rel_path, allow_text=allow_text)

def _handle_project_artifact_file(project_id, query_string=""):
    _, project, _ = _project_execution_find(project_id)
    if not project:
        return {"error": "Project not found", "_status": 404}
    context = _project_artifact_context(project)
    if not context.get("ok"):
        return context
    params = urllib.parse.parse_qs(query_string or "")
    rel_path = (params.get("path") or [""])[0]
    return _artifact_context_file_response(context, rel_path)

def _handle_project_artifact_delete(project_id, query_string=""):
    _, project, _ = _project_execution_find(project_id)
    if not project:
        return {"error": "Project not found", "_status": 404}
    context = _project_artifact_context(project)
    if not context.get("ok"):
        return context
    params = urllib.parse.parse_qs(query_string or "", keep_blank_values=True)
    if "dir" in params:
        rel_dir = (params.get("dir") or [""])[0]
        return _artifact_context_delete_dir(context, rel_dir)
    rel_path = (params.get("path") or [""])[0]
    return _artifact_context_delete(context, rel_path)

def _project_execution_build_prompt(project, task, attempt, workspace):
    checklist = _project_execution_acceptance_checklist(task)
    checklist_text = "\n".join(f"- [{'x' if item.get('done') else ' '}] {item.get('text', '')}" for item in checklist) or "- No checklist supplied"
    rework_feedback = task.get("reworkFeedback") or attempt.get("reworkFeedback") or ""
    archive_context = _archive_context_prompt_block(project, task)
    meeting_action_block = ""
    if attempt.get("meetingActionPhase"):
        pending_actions = [
            a for a in (task.get("meetingActionItems") or [])
            if isinstance(a, dict) and a.get("requiredForResume") is True and a.get("status") == "pending"
        ]
        action_lines = []
        for item in pending_actions:
            detail = item.get("description") or ""
            owner = item.get("owner") or task.get("executorAgentId") or task.get("assignee") or ""
            action_lines.append(f"- {item.get('title', '')}" + (f" — {detail}" if detail else "") + (f" (owner: {owner})" if owner else ""))
        decision_lines = []
        for decision in (task.get("meetingDecisionHistory") or [])[-3:]:
            if isinstance(decision, dict) and decision.get("decision"):
                decision_lines.append(f"- {decision.get('decision')}")
        meeting_action_block = (
            "\nMEETING ACTION ITEM PHASE:\n"
            "Complete ONLY the meeting-created action items listed below. Do not continue the original task yet.\n"
            "After completing them, return a concise summary of what was done and any remaining risk.\n"
            "Pending meeting action items:\n"
            + ("\n".join(action_lines) if action_lines else "- No pending meeting action items")
            + "\nMeeting decision context:\n"
            + ("\n".join(decision_lines) if decision_lines else "- No meeting decision context")
            + "\n"
        )
    return (
        "You are the execution agent for a Virtual Office project task.\n"
        f"WORKSPACE: {workspace}\nWork only inside this workspace. Do not review or mark the task complete.\n"
        "EXPECTED WORKFLOW:\n"
        "1. First read the task and determine what content or deliverable must be produced. Write the task/deliverable acceptance criteria into the task checklist. The checklist is only for deliverable acceptance criteria, not a meeting action-item queue. If the task checklist is empty, include the created acceptance criteria in checklistUpdates and, when possible, persist them with PUT /api/projects/{projectId}/tasks/{taskId}.\n"
        "2. Execute the task. For any Virtual Office operation, first use the vo-operating-guidelines skill to detect the VO environment, choose the correct VO skill, and follow its boundaries. If you discover an issue that requires alignment, use vo-operating-guidelines to decide whether a formal AI meeting is appropriate; when it is, proactively request a meeting with POST /api/projects/{projectId}/tasks/{taskId}/meeting-requests. Do not confirm or reject meetings yourself. Add the corresponding action items and discussion points as meeting/task context. Do not put those meeting action items or risks into the checklist or comments.\n"
        "3. Before finishing, inspect whether every checklist item is complete. Mark completed checklist items done; if any item is unfinished, continue working until it is complete.\n"
        "FINAL RESPONSE FORMAT (strict):\n"
        "- First output a human-visible Markdown summary under 1200 characters. It may include short bullets for changed files, tests run, and remaining risks.\n"
        "- Then output exactly one fenced ```json block containing a single object with these optional fields: checklistUpdates, meetingDiscussionPoints, tests.\n"
        "- Do not print raw JSON outside the fenced json block. Do not put escaped JSON inside the Markdown summary.\n"
        "- tests must be an array of short strings only, each under 180 characters. Do not put full logs, full API responses, raw tool output, source material, or nested objects in tests.\n"
        "- checklistUpdates is an array of {id, text, done, evidence}; set done=true only for checklist items you actually verified as complete.\n"
        "- meetingDiscussionPoints is an array of {kind, title, text, meetingId, requestId} for meeting conclusions, risks, and discussion notes that belong in the task details.\n\n"
        f"PROJECT: {project.get('title', '')}\nPROJECT DESCRIPTION: {project.get('description', '')}\n"
        f"PROJECT_ID: {project.get('id', '')}\nTASK_ID: {task.get('id', '')}\nTASK: {task.get('title', '')}\nTASK DESCRIPTION: {task.get('description', '')}\nATTEMPT: {attempt.get('id')}\n"
        f"REWORK FEEDBACK: {rework_feedback}\nCHECKLIST:\n{checklist_text}\n"
        f"{meeting_action_block}"
        f"{archive_context}\n"
    )

def _project_execution_test_evidence(result):
    explicit = result.get("tests")
    if isinstance(explicit, list):
        evidence = []
        for item in explicit[:50]:
            if isinstance(item, dict):
                label = item.get("name") or item.get("title") or item.get("command") or item.get("text") or item.get("summary") or item.get("status")
                status = item.get("status") or item.get("result") or item.get("outcome")
                text = " · ".join(str(part).strip() for part in (label, status) if str(part or "").strip())
            else:
                text = str(item or "")
            compact = _project_execution_compact_evidence_line(text)
            if compact:
                evidence.append(compact)
        return evidence
    lines = []
    parsed = _project_execution_extract_json(result.get("reply") or "")
    if isinstance(parsed, dict):
        for key in ("tests", "testResults", "checks", "validation", "checkResults"):
            value = parsed.get(key)
            if not isinstance(value, list):
                continue
            for item in value[:50]:
                if isinstance(item, dict):
                    label = item.get("name") or item.get("title") or item.get("command") or item.get("text") or item.get("summary") or item.get("id")
                    status = item.get("status") or item.get("result") or item.get("outcome")
                    text = " · ".join(str(part).strip() for part in (label, status) if str(part or "").strip())
                else:
                    text = str(item or "")
                compact = _project_execution_compact_evidence_line(text)
                if compact:
                    lines.append(compact)
            if lines:
                return lines[:50]
    for line in str(result.get("reply") or "").splitlines():
        stripped = line.strip()
        if not stripped or (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
            continue
        if re.search(r"(?i)\b(test|pytest|npm test|unittest|passed|failed)\b", line):
            compact = _project_execution_compact_evidence_line(stripped)
            if compact:
                lines.append(compact)
    return lines[:50]

def _project_execution_call_executor(executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600):
    agent_id = executor.get("id")
    provider_kind = executor.get("providerKind")
    if provider_kind == "codex":
        return _handle_codex_chat({"agentId": agent_id, "message": prompt, "conversationId": attempt_id, "timeoutSec": timeout, "workspace": workspace, "fromType": "agent"})
    if provider_kind == "hermes":
        return _handle_hermes_chat({"agentId": agent_id, "message": prompt, "conversationId": attempt_id, "timeoutSec": timeout, "fromType": "agent"})
    if provider_kind == "claude-code":
        return _handle_claude_code_chat({"agentId": agent_id, "message": prompt, "conversationId": attempt_id, "timeoutSec": timeout, "workspace": workspace, "fromType": "agent"})
    reply = _wf_call_agent(agent_id, prompt, timeout=timeout, project_id=project_id, task_id=attempt_id or task_id)
    reply_text = str(reply or "")
    delivered_only = reply_text.startswith("[DELIVERED]")
    ok = bool(reply) and not reply_text.startswith("[ERROR]") and not delivered_only
    if delivered_only:
        return {
            "ok": False,
            "reply": reply_text,
            "error": "OpenClaw message was delivered but no final execution result was returned.",
            "status": "execution_pending_result",
        }
    return {"ok": ok, "reply": reply, "error": None if ok else reply, "status": "completed" if ok else "execution_failed"}

def _project_execution_latest_attempt(task):
    attempts = task.get("attempts") or []
    evidence_attempt = (task.get("evidence") or {}).get("attemptId")
    if evidence_attempt:
        found = _project_execution_attempt(task, evidence_attempt)
        if found:
            return found
    return attempts[-1] if attempts else None

def _project_execution_build_review_prompt(project, task, attempt):
    evidence = attempt.get("evidence") or task.get("evidence") or {}
    checklist = _project_execution_acceptance_checklist(task)
    checklist_text = "\n".join(f"- [{'x' if item.get('done') else ' '}] {item.get('text', '')}" for item in checklist) or "- No checklist supplied"
    changed = "\n".join(f"- {name}" for name in (evidence.get("changedFiles") or [])[:100]) or "- No changed files reported"
    tests = "\n".join(f"- {line}" for line in (evidence.get("testResults") or [])[:50]) or "- No test evidence reported"
    feedback = task.get("reworkFeedback") or ""
    return (
        "You are the independent read-only reviewer for a Virtual Office Project Execution task.\n"
        "Review only the evidence below. Do not modify files, run tools that write files, or mark the task done.\n"
        "The checklist contains deliverable acceptance criteria only; meeting action items and risks are context, not acceptance checklist items.\n"
        "Return one JSON object with fields: status, summary, rationale, items.\n"
        "status must be one of: pass, needs_more_work, blocked.\n\n"
        f"PROJECT: {project.get('title', '')}\nPROJECT DESCRIPTION: {project.get('description', '')}\n"
        f"TASK: {task.get('title', '')}\nTASK DESCRIPTION: {task.get('description', '')}\n"
        f"ATTEMPT: {attempt.get('id')}\nPRIOR USER FEEDBACK: {feedback}\nCHECKLIST:\n{checklist_text}\n\n"
        f"EXECUTOR SUMMARY:\n{_project_execution_redact(evidence.get('executorSummary') or '')}\n\n"
        f"CHANGED FILES:\n{changed}\n\nTEST EVIDENCE:\n{tests}\n\n"
        f"PROVIDER STATUS: {evidence.get('providerStatus') or ''}\nERROR: {_project_execution_redact(evidence.get('error') or '')}\n"
    )

def _project_execution_call_reviewer(reviewer, prompt, review_id, project_id=None, task_id=None, timeout=600):
    agent_id = reviewer.get("id")
    provider_kind = reviewer.get("providerKind")
    if provider_kind == "codex":
        return _handle_codex_chat({"agentId": agent_id, "message": prompt, "conversationId": review_id, "timeoutSec": timeout, "fromType": "agent"})
    if provider_kind == "hermes":
        return _handle_hermes_chat({"agentId": agent_id, "message": prompt, "conversationId": review_id, "timeoutSec": timeout, "fromType": "agent"})
    if provider_kind == "claude-code":
        return _handle_claude_code_chat({"agentId": agent_id, "message": prompt, "conversationId": review_id, "timeoutSec": timeout, "fromType": "agent"})
    reply = _wf_call_agent(agent_id, prompt, timeout=timeout, project_id=project_id, task_id=review_id or task_id)
    ok = not str(reply).startswith("[ERROR]")
    return {"ok": ok, "reply": reply, "error": None if ok else reply, "status": "completed" if ok else "review_failed"}

def _project_execution_review_feedback(review):
    parts = [review.get("summary") or "", review.get("rationale") or ""]
    for item in review.get("items") or []:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            parts.append(item.get("text") or item.get("summary") or json.dumps(item, ensure_ascii=False))
    return _project_execution_redact("\n".join(part for part in parts if part).strip() or "Reviewer requested more work.")

def _project_execution_extract_json(text):
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        pass
    match = re.search(r"\{.*\}", raw, re.S)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
    return None

def _project_execution_normalize_review(result, reviewer, attempt_id, review_id):
    explicit = result.get("review") if isinstance(result, dict) else None
    parsed = explicit if isinstance(explicit, dict) else _project_execution_extract_json(result.get("reply") if isinstance(result, dict) else "")
    if not isinstance(parsed, dict):
        parsed = {}
    status = str(parsed.get("status") or "").strip().lower()
    schema_ok = all(key in parsed for key in ("status", "summary", "rationale", "items")) and isinstance(parsed.get("items"), list)
    if status not in {"pass", "needs_more_work", "blocked"}:
        status = "blocked"
    if not schema_ok:
        status = "blocked"
    items = parsed.get("items") if isinstance(parsed.get("items"), list) else []
    return {
        "id": review_id,
        "attemptId": attempt_id,
        "status": status,
        "summary": _project_execution_redact(parsed.get("summary") or result.get("reply") or ""),
        "rationale": _project_execution_redact(parsed.get("rationale") or result.get("error") or ""),
        "items": items[:50],
        "reviewer": {"providerKind": reviewer.get("providerKind"), "agentId": reviewer.get("id")},
        "providerStatus": result.get("status") or ("completed" if result.get("ok") else "review_failed"),
        "raw": _project_execution_redact(result.get("reply") or ""),
        "reviewedAt": _proj_now(),
    }

def _project_execution_run_review(project_id, task_id, attempt_id, review_id):
    try:
        data, project, task = _project_execution_find(project_id, task_id)
        if not project or not task:
            return
        attempt = _project_execution_attempt(task, attempt_id)
        if not attempt or task.get("activeAttemptId") != review_id:
            return
        reviewer = attempt.get("reviewer") or {}
        result = _project_execution_call_reviewer(reviewer, _project_execution_build_review_prompt(project, task, attempt), review_id, project_id=project_id, task_id=task_id)
        data, project, task = _project_execution_find(project_id, task_id)
        if not project or not task:
            return
        attempt = _project_execution_attempt(task, attempt_id)
        if not attempt or task.get("activeAttemptId") != review_id:
            return
        review = _project_execution_normalize_review(result, reviewer, attempt_id, review_id)
        attempt["review"] = review
        attempt["reviewedAt"] = review["reviewedAt"]
        task.setdefault("reviewHistory", []).append(review)
        task["reviewHistory"] = task["reviewHistory"][-50:]
        task["reviewResult"] = review
        task["activeAttemptId"] = None
        project.update({"workflowActive": False, "activeTaskId": None, "activeAgent": None})
        if review["status"] == "pass":
            task.update({"blockedReason": None, "lastError": None})
            attempt["status"] = "review_passed"
            if _project_execution_attempt_requires_user_acceptance(task, attempt):
                project["projectExecutionFlowActive"] = False
                project["projectExecutionFlowStopReason"] = "awaiting_user_acceptance"
                _project_execution_transition(project, task, "awaiting_user_acceptance", reviewer.get("id") or "reviewer", "Reviewer passed; waiting for explicit user acceptance.", attempt_id)
                _send_project_execution_acceptance_notification(project, task, attempt_id, "Reviewer passed; waiting for explicit user acceptance.")
            else:
                done_result = _project_execution_mark_done(project, task, reviewer.get("id") or "reviewer", "Reviewer passed; task does not require user acceptance.", attempt_id)
                if not done_result.get("ok"):
                    continued = _project_execution_continue_for_incomplete_checklist(data, project_id, task_id, project, task, attempt_id, reviewer.get("id") or "reviewer", done_result)
                    if continued.get("continued"):
                        return
                    task["blockedReason"] = done_result.get("error")
                    _project_execution_transition(project, task, "blocked", "system", task["blockedReason"], attempt_id)
                    _send_project_execution_intervention_notification(project, task, task["blockedReason"], attempt_id, event="blocked", kind="warning")
                elif attempt.get("projectFlow") or project.get("projectExecutionFlowActive"):
                    project["projectExecutionFlowActive"] = True
                    project["projectExecutionFlowStopReason"] = None
                    _project_execution_schedule_continue(project_id, "review_passed")
        elif review["status"] == "needs_more_work":
            attempt["status"] = "review_needs_more_work"
            prior_reworks = int(task.get("reworkCount") or 0)
            feedback = _project_execution_review_feedback(review)
            if prior_reworks >= 3:
                task["blockedReason"] = "Reviewer still requested more work after three rework cycles."
                task["reworkFeedback"] = feedback
                _project_execution_transition(project, task, "blocked", reviewer.get("id") or "reviewer", task["blockedReason"], attempt_id)
                _send_project_execution_intervention_notification(project, task, task["blockedReason"], attempt_id, event="blocked", kind="warning")
            else:
                task["reworkCount"] = prior_reworks + 1
                task["blockedReason"] = None
                task["lastError"] = None
                task["reworkFeedback"] = feedback
                roles = _project_execution_resolve_roles(project, task)
                workspace = _project_execution_validate_workspace(project.get("workspacePath"))
                if not roles.get("ok") or not workspace.get("ok"):
                    task["blockedReason"] = roles.get("error") if not roles.get("ok") else workspace.get("error")
                    _project_execution_transition(project, task, "blocked", "system", task["blockedReason"], attempt_id)
                    _send_project_execution_intervention_notification(project, task, task["blockedReason"], attempt_id, event="blocked", kind="warning")
                else:
                    rework_attempt_id = str(uuid.uuid4())
                    rework_attempt = {
                        "id": rework_attempt_id,
                        "status": "reworking",
                        "startedAt": _proj_now(),
                        "workspacePath": workspace["path"],
                        "workspaceKind": workspace["kind"],
                        "dirtyConfirmed": False,
                        "dirtyFingerprint": "",
                        "executor": roles["executor"],
                        "reviewer": roles["reviewer"],
                        "baseline": _project_execution_git_snapshot(workspace["path"]),
                        "rework": True,
                        "reworkCycle": task["reworkCount"],
                        "reworkFromAttemptId": attempt_id,
                        "reworkFromReviewId": review_id,
                        "reworkFeedback": feedback,
                        "autoReviewAfterExecution": True,
                    }
                    task.setdefault("attempts", []).append(rework_attempt)
                    task["attempts"] = task["attempts"][-20:]
                    task.update({"activeAttemptId": rework_attempt_id, "executorAgentId": roles["executor"]["id"], "reviewerAgentId": roles["reviewer"]["id"]})
                    project.update({"workflowActive": True, "workflowPhase": "reworking", "activeTaskId": task_id, "activeAgent": roles["executor"]["id"]})
                    _project_execution_transition(project, task, "reworking", reviewer.get("id") or "reviewer", feedback, rework_attempt_id)
                    cancel_flag = threading.Event()
                    with _PROJECT_EXECUTION_LOCK:
                        _PROJECT_EXECUTION_CANCEL_FLAGS[rework_attempt_id] = cancel_flag
                    project["workflowPhase"] = task["executionState"]
                    _save_projects(data)
                    _project_execution_launch_thread(_project_execution_run_attempt, (project_id, task_id, rework_attempt_id, cancel_flag))
                    return
        else:
            attempt["status"] = "review_blocked"
            task["blockedReason"] = review["summary"] or "Reviewer marked the task blocked."
            _project_execution_transition(project, task, "blocked", reviewer.get("id") or "reviewer", task["blockedReason"], attempt_id)
            _send_project_execution_intervention_notification(project, task, task["blockedReason"], attempt_id, event="blocked", kind="warning")
        project["workflowPhase"] = task["executionState"]
        _save_projects(data)
    finally:
        with _PROJECT_EXECUTION_LOCK:
            _PROJECT_EXECUTION_REVIEW_FLAGS.discard(review_id)

def _project_execution_run_attempt(project_id, task_id, attempt_id, cancel_flag):
    data, project, task = _project_execution_find(project_id, task_id)
    if not project or not task:
        return
    attempt = _project_execution_attempt(task, attempt_id)
    if not attempt:
        return
    workspace = attempt.get("workspacePath")
    executor = attempt.get("executor") or {}
    started = time.time()
    result = _project_execution_call_executor(executor, _project_execution_build_prompt(project, task, attempt, workspace), workspace, attempt_id, project_id=project_id, task_id=task_id)
    final_snapshot = _project_execution_git_snapshot(workspace)
    data, project, task = _project_execution_find(project_id, task_id)
    if not project or not task:
        return
    attempt = _project_execution_attempt(task, attempt_id)
    if not attempt or (task.get("activeAttemptId") != attempt_id and attempt.get("status") != "cancelling"):
        return
    checklist_changed = _project_execution_apply_checklist_updates(task, result)
    discussion_points_changed = _project_execution_apply_meeting_discussion_points(task, result)
    cancelled = cancel_flag.is_set() or result.get("status") == "cancelled"
    evidence = {
        "attemptId": attempt_id,
        "executorSummary": _project_execution_redact(result.get("reply") or ""),
        "changedFiles": sorted(set(final_snapshot.get("files", [])) | set(result.get("modifiedFiles") or []))[:200],
        "workspaceBefore": attempt.get("baseline", {}), "workspaceAfter": final_snapshot,
        "checklist": _project_execution_acceptance_checklist(task),
        "providerStatus": result.get("status") or ("completed" if result.get("ok") else "execution_failed"),
        "error": _project_execution_redact(result.get("error") or ""), "durationMs": int((time.time() - started) * 1000), "capturedAt": _proj_now(),
        "testResults": _project_execution_test_evidence(result),
        "checklistUpdated": checklist_changed,
        "meetingDiscussionUpdated": discussion_points_changed,
        "providerRef": {"providerKind": executor.get("providerKind"), "agentId": executor.get("id"), "attemptId": attempt_id},
    }
    attempt.update({"evidence": evidence, "finishedAt": _proj_now()})
    task.update({"evidence": evidence, "activeAttemptId": None})
    project.update({"workflowActive": False, "activeTaskId": None, "activeAgent": None})
    if cancelled:
        attempt["status"] = "cancelled"
        task["blockedReason"] = "Execution was cancelled. Existing workspace changes were not rolled back."
        _project_execution_transition(project, task, "blocked", "user", task["blockedReason"], attempt_id)
        _send_project_execution_intervention_notification(project, task, task["blockedReason"], attempt_id, event="blocked", kind="warning")
    elif result.get("ok"):
        attempt["status"] = "execution_complete"
        task.update({"blockedReason": None, "lastError": None})
        if attempt.get("meetingActionPhase"):
            _project_execution_mark_meeting_actions_completed(project, task, attempt_id, executor.get("id") or "executor")
            attempt["status"] = "meeting_action_items_completed"
            task["reviewResult"] = {}
            task["evidence"] = evidence
            _project_execution_transition(project, task, "backlog", executor.get("id") or "executor", "Meeting action items completed; original task can resume.", attempt_id)
            _project_execution_move_task_to_column(project, task, _wf_get_backlog_col(project))
            project.update({
                "workflowActive": False,
                "workflowPhase": "meeting_action_items_completed",
                "activeTaskId": None,
                "activeAgent": None,
                "projectExecutionFlowActive": project.get("projectExecutionStartMode") == "continuous",
                "projectExecutionFlowStopReason": None,
                "updatedAt": _proj_now(),
            })
            _save_projects(data)
            with _PROJECT_EXECUTION_LOCK:
                _PROJECT_EXECUTION_CANCEL_FLAGS.pop(attempt_id, None)
            if not _project_execution_has_pending_meeting_actions(task):
                _project_execution_launch_thread(lambda: (_server_callable("_handle_project_execution_start") or _handle_project_execution_start)(project_id, task_id, {"projectStart": True, "mode": project.get("projectExecutionStartMode") or "continuous", "autoReviewAfterExecution": True, "by": "meeting-action-items"}))
            return
        if attempt.get("skipReview"):
            task["reviewResult"] = {
                "id": f"skipped-{attempt_id}",
                "attemptId": attempt_id,
                "status": "skipped",
                "summary": "Independent review skipped after user confirmation because no reviewer was configured.",
                "rationale": attempt.get("skipReviewReason") or "reviewer_missing",
                "items": [],
                "reviewedAt": _proj_now(),
            }
            task.setdefault("reviewHistory", []).append(task["reviewResult"])
            task["reviewHistory"] = task["reviewHistory"][-50:]
            if _project_execution_attempt_requires_user_acceptance(task, attempt):
                attempt["status"] = "review_skipped_waiting_acceptance"
                project["projectExecutionFlowActive"] = False
                project["projectExecutionFlowStopReason"] = "awaiting_user_acceptance"
                _project_execution_transition(project, task, "awaiting_user_acceptance", "system", "Review skipped by user confirmation; waiting for user acceptance.", attempt_id)
                _send_project_execution_acceptance_notification(project, task, attempt_id, "Review skipped by user confirmation; waiting for user acceptance.")
            else:
                done_result = _project_execution_mark_done(project, task, "system", "Review skipped by user confirmation; task does not require user acceptance.", attempt_id)
                if not done_result.get("ok"):
                    continued = _project_execution_continue_for_incomplete_checklist(data, project_id, task_id, project, task, attempt_id, "system", done_result)
                    if continued.get("continued"):
                        with _PROJECT_EXECUTION_LOCK:
                            _PROJECT_EXECUTION_CANCEL_FLAGS.pop(attempt_id, None)
                        return
                    task["blockedReason"] = done_result.get("error")
                    _project_execution_transition(project, task, "blocked", "system", task["blockedReason"], attempt_id)
                    _send_project_execution_intervention_notification(project, task, task["blockedReason"], attempt_id, event="blocked", kind="warning")
                elif attempt.get("projectFlow") or project.get("projectExecutionFlowActive"):
                    project["projectExecutionFlowActive"] = True
                    project["projectExecutionFlowStopReason"] = None
                    _project_execution_schedule_continue(project_id, "review_skipped")
        else:
            _project_execution_transition(project, task, "execution_complete", executor.get("id") or "executor", "Execution completed; Independent review has not started.", attempt_id)
    else:
        transient_reason = _project_execution_transient_failure_reason(result)
        if transient_reason and not cancelled and _project_execution_schedule_transient_retry(data, project_id, task_id, project, task, attempt, evidence, transient_reason):
            with _PROJECT_EXECUTION_LOCK:
                _PROJECT_EXECUTION_CANCEL_FLAGS.pop(attempt_id, None)
            return
        attempt["status"] = "blocked"
        task["lastError"] = evidence["error"] or "Executor failed"
        task["blockedReason"] = task["lastError"]
        _project_execution_transition(project, task, "blocked", executor.get("id") or "executor", task["blockedReason"], attempt_id)
        _send_project_execution_intervention_notification(project, task, task["blockedReason"], attempt_id, event="blocked", kind="error")
    project["workflowPhase"] = task["executionState"]
    _save_projects(data)
    with _PROJECT_EXECUTION_LOCK:
        _PROJECT_EXECUTION_CANCEL_FLAGS.pop(attempt_id, None)
    if result.get("ok") and attempt.get("autoReviewAfterExecution"):
        _handle_project_execution_review_start(project_id, task_id, {"attemptId": attempt_id})

def _handle_project_execution_start(project_id, task_id, body):
    body = body or {}
    data, project, task = _project_execution_find(project_id, task_id)
    if not project or not task:
        return {"error": "Project or task not found", "_status": 404}
    if not _project_execution_enabled(project):
        return {"error": "Project Execution is not enabled for this project", "_status": 409}
    workspace = _project_execution_validate_workspace(project.get("workspacePath"))
    if not workspace.get("ok"):
        project["workspaceStatus"] = workspace
        _send_project_execution_intervention_notification(project, task, workspace.get("error") or "Project workspace is not available.", task.get("activeAttemptId"), event="start_failed", kind="error")
        _save_projects(data)
        return {**workspace, "_status": 409}
    roles = _project_execution_resolve_start_roles(
        project,
        task,
        allow_skip_reviewer=bool(body.get("skipReviewConfirmed")) or task.get("allowReviewerlessExecution") is True,
    )
    if not roles.get("ok"):
        payload = {**roles, "_status": 409}
        _send_project_execution_intervention_notification(project, task, roles.get("error") or "Project Execution role configuration needs user attention.", task.get("activeAttemptId"), event="start_failed", kind="error")
        _save_projects(data)
        if roles.get("confirmationRequired"):
            payload.update({
                "taskId": task_id,
                "startMode": _project_execution_start_mode(project, body) if body.get("projectStart") else "single",
                "requiresUserAcceptance": _project_execution_requires_user_acceptance(task),
            })
        return payload
    active = _project_execution_active_task(project)
    if active:
        return {"error": "Another task is already active for this project", "activeTaskId": active.get("id"), "_status": 409}
    snapshot = _project_execution_git_snapshot(workspace["path"])
    start_mode = _project_execution_start_mode(project, body) if body.get("projectStart") else "single"
    project_flow = bool(body.get("projectStart")) and start_mode == "continuous"
    if snapshot.get("dirty") and str(body.get("dirtyFingerprint") or "") != snapshot.get("fingerprint"):
        return {"ok": False, "confirmationRequired": True, "code": "dirty_worktree_confirmation_required", "taskId": task_id, "startMode": start_mode, "requiresUserAcceptance": _project_execution_requires_user_acceptance(task), "dirtyFingerprint": snapshot.get("fingerprint"), "dirtyFiles": snapshot.get("files", [])[:50], "truncated": snapshot.get("truncated", False), "_status": 409}
    if snapshot.get("dirty"):
        project.setdefault("executionDirtyConfirmations", []).append(snapshot.get("fingerprint"))
        project["executionDirtyConfirmations"] = project["executionDirtyConfirmations"][-100:]
    reopened_completed_task = False
    if task.get("completedAt"):
        if task.get("scheduledRepeatEnabled") is not True:
            return {
                "ok": False,
                "error": "Task is completed and repeat triggering is not enabled",
                "code": "task_completed_repeat_disabled",
                "taskId": task_id,
                "_status": 409,
            }
        reopened_completed_task = _project_execution_reopen_completed_task(project, task, actor=str(body.get("by") or "user"))
    if body.get("resetExecutionContext") is True:
        _project_execution_clear_restart_bindings(task, _proj_now(), str(body.get("by") or "user"), "manual task restart")
    attempt_id = str(uuid.uuid4())
    project["projectExecutionStartMode"] = start_mode if body.get("projectStart") else project.get("projectExecutionStartMode", "continuous")
    project["projectExecutionFlowActive"] = project_flow
    project["projectExecutionFlowStopReason"] = None
    meeting_action_phase = _project_execution_has_pending_meeting_actions(task)
    attempt_status = "meeting_action_items" if meeting_action_phase else "executing"
    attempt = {"id": attempt_id, "status": attempt_status, "startedAt": _proj_now(), "workspacePath": workspace["path"], "workspaceKind": workspace["kind"], "dirtyConfirmed": bool(snapshot.get("dirty")), "dirtyFingerprint": snapshot.get("fingerprint") if snapshot.get("dirty") else "", "executor": roles["executor"], "reviewer": roles.get("reviewer"), "skipReview": bool(roles.get("skipReview")), "skipReviewReason": roles.get("skipReviewReason"), "baseline": snapshot, "startMode": start_mode, "projectFlow": project_flow, "requiresUserAcceptance": _project_execution_requires_user_acceptance(task), "autoReviewAfterExecution": bool(body.get("autoReviewAfterExecution")) and not roles.get("skipReview"), "meetingActionPhase": meeting_action_phase}
    task.setdefault("attempts", []).append(attempt)
    task["attempts"] = task["attempts"][-20:]
    if not task.get("assignee"):
        task["assignee"] = roles["executor"]["id"]
    task.update({"activeAttemptId": attempt_id, "executorAgentId": roles["executor"]["id"], "reviewerAgentId": (roles.get("reviewer") or {}).get("id"), "blockedReason": None, "lastError": None})
    project.update({"workspaceStatus": workspace, "workflowActive": True, "workflowPhase": "executing", "activeTaskId": task_id, "activeAgent": roles["executor"]["id"]})
    transition_reason = "Meeting action item phase started" if meeting_action_phase else "Project Execution task started"
    _project_execution_transition(project, task, "executing", "user", transition_reason, attempt_id)
    _save_projects(data)
    cancel_flag = threading.Event()
    with _PROJECT_EXECUTION_LOCK:
        _PROJECT_EXECUTION_CANCEL_FLAGS[attempt_id] = cancel_flag
    _project_execution_launch_thread(_project_execution_run_attempt, (project_id, task_id, attempt_id, cancel_flag))
    return {"ok": True, "status": "started", "taskId": task_id, "attemptId": attempt_id, "startMode": start_mode, "requiresUserAcceptance": _project_execution_requires_user_acceptance(task), "reopenedCompletedTask": reopened_completed_task}

def _handle_project_execution_project_start(project_id, body=None):
    body = body or {}
    data, project, _ = _project_execution_find(project_id)
    if not project:
        return {"error": "Project not found", "_status": 404}
    if not _project_execution_enabled(project):
        return {"error": "Project Execution is not enabled for this project", "_status": 409}
    active = _project_execution_active_task(project)
    if active:
        return {"error": "Another task is already active for this project", "activeTaskId": active.get("id"), "_status": 409}
    restart_pipeline = body.get("restartPipeline") is True
    reset_result = None
    if restart_pipeline:
        if not _project_execution_all_tasks_repeatable(project):
            return {
                "ok": False,
                "error": "Project pipeline can only be restarted when every task allows retriggering",
                "code": "project_restart_requires_all_tasks_repeatable",
                "_status": 409,
            }
        reset_result = _project_execution_reset_project_tasks_for_restart(project, actor=str(body.get("by") or "user"))
        if not reset_result.get("ok"):
            return reset_result
        _save_projects(data)
    task = _project_execution_next_task(project)
    if not task:
        project["projectExecutionFlowActive"] = False
        project["projectExecutionFlowStopReason"] = "no_eligible_task"
        project["workflowActive"] = False
        project["workflowPhase"] = "no_eligible_task"
        project["updatedAt"] = _proj_now()
        _send_project_execution_project_complete_notification(project, "Project Execution 已完成，当前没有可继续执行的任务。")
        _save_projects(data)
        return {"error": "No eligible task to start", "code": "no_eligible_task", "_status": 409}
    mode = _project_execution_start_mode(project, body)
    result = _handle_project_execution_start(project_id, task.get("id"), {**body, "mode": mode, "projectStart": True, "autoReviewAfterExecution": True})
    if restart_pipeline and isinstance(result, dict):
        result["restartPipeline"] = True
        result["resetTaskCount"] = (reset_result or {}).get("resetTaskCount", 0)
    if result.get("ok") or result.get("confirmationRequired"):
        result["selectedTask"] = {"id": task.get("id"), "title": task.get("title", "")}
    if result.get("confirmationRequired") or (not result.get("ok") and result.get("error")):
        data, project, _ = _project_execution_find(project_id)
        if project:
            project["projectExecutionStartMode"] = mode
            project["projectExecutionFlowActive"] = False
            project["projectExecutionFlowStopReason"] = result.get("code") or result.get("error")
            project["workflowActive"] = False
            project["workflowPhase"] = result.get("code") or "start_failed"
            project["updatedAt"] = _proj_now()
            _save_projects(data)
        result["selectedTask"] = {"id": task.get("id"), "title": task.get("title", "")}
    return result

def _project_execution_schedule_continue(project_id, reason="continue"):
    data, project, _ = _project_execution_find(project_id)
    if project and not _project_execution_next_task(project):
        project["projectExecutionFlowActive"] = False
        project["projectExecutionFlowStopReason"] = "no_eligible_task"
        project["workflowActive"] = False
        project["workflowPhase"] = "no_eligible_task"
        project["activeTaskId"] = None
        project["activeAgent"] = None
        project["updatedAt"] = _proj_now()
        _save_projects(data)
        _send_project_execution_project_complete_notification(project, "Project Execution 已完成，当前没有可继续执行的任务。")
        return

    def run():
        time.sleep(0.05)
        result = _handle_project_execution_project_start(project_id, {"mode": "continuous", "by": "system", "flowReason": reason})
        if result.get("ok"):
            return
        data, project, _ = _project_execution_find(project_id)
        if not project:
            return
        project["projectExecutionFlowActive"] = False
        project["projectExecutionFlowStopReason"] = result.get("code") or result.get("error") or reason
        if not project.get("workflowActive"):
            project["workflowPhase"] = result.get("code") or "stopped"
        project["updatedAt"] = _proj_now()
        _save_projects(data)
    _project_execution_launch_thread(run)

def _handle_project_execution_status(project_id, task_id=None):
    data, project, task = _project_execution_find(project_id, task_id)
    if not project or (task_id and not task):
        return {"error": "Project or task not found", "_status": 404}
    targets = [task] if task else project.get("tasks", [])
    changed = False
    for item in targets:
        if item and item.get("executionState") in {"validating", "executing", "reviewing", "reworking"}:
            attempt_id = item.get("activeAttemptId")
            with _PROJECT_EXECUTION_LOCK:
                live = bool(attempt_id and (attempt_id in _PROJECT_EXECUTION_CANCEL_FLAGS or attempt_id in _PROJECT_EXECUTION_REVIEW_FLAGS))
            if not live:
                item["activeAttemptId"] = None
                item["blockedReason"] = "previous_execution_not_resumable"
                _project_execution_transition(project, item, "blocked", "system", item["blockedReason"], attempt_id)
                changed = True
    if changed:
        project.update({"workflowActive": False, "activeTaskId": None, "activeAgent": None, "workflowPhase": "blocked"})
        _save_projects(data)
    return {
        "ok": True,
        "active": bool(project.get("workflowActive")),
        "phase": project.get("workflowPhase") or "idle",
        "currentTaskId": project.get("activeTaskId"),
        "startMode": project.get("projectExecutionStartMode") or "continuous",
        "flowActive": bool(project.get("projectExecutionFlowActive")),
        "flowStopReason": project.get("projectExecutionFlowStopReason"),
        "task": task,
    }

def _handle_project_execution_cancel(project_id, task_id, body=None):
    data, project, task = _project_execution_find(project_id, task_id)
    if not project or not task:
        return {"error": "Task not found", "_status": 404}
    attempt_id = str((body or {}).get("attemptId") or task.get("activeAttemptId") or "")
    if not attempt_id or task.get("activeAttemptId") != attempt_id:
        return {"error": "No matching active attempt", "_status": 409}
    with _PROJECT_EXECUTION_LOCK:
        flag = _PROJECT_EXECUTION_CANCEL_FLAGS.get(attempt_id)
        if flag:
            flag.set()
    attempt = _project_execution_attempt(task, attempt_id) or {}
    attempt["status"] = "cancelling"
    task["activeAttemptId"] = None
    task["blockedReason"] = "Execution was stopped by user. Existing workspace changes were not rolled back."
    task["lastError"] = None
    _project_execution_transition(project, task, "blocked", "user", task["blockedReason"], attempt_id)
    _send_project_execution_intervention_notification(project, task, task["blockedReason"], attempt_id, event="blocked", kind="warning")
    project.update({
        "workflowActive": False,
        "workflowPhase": "blocked",
        "activeTaskId": None,
        "activeAgent": None,
        "projectExecutionFlowActive": False,
        "projectExecutionFlowStopReason": "user_stopped_execution",
        "updatedAt": _proj_now(),
    })
    _save_projects(data)
    executor = attempt.get("executor") or {}
    if executor.get("providerKind") == "codex":
        _handle_codex_cancel({"agentId": executor.get("id"), "conversationId": attempt_id, "workspace": attempt.get("workspacePath")})
    elif executor.get("providerKind") == "openclaw":
        raw_session_key = _wf_task_session_key(executor.get("id"), project_id, attempt_id or task_id)
        _wf_abort_task_session(_openclaw_gateway_session_key(executor.get("id"), raw_session_key))
    return {"ok": True, "status": "blocked", "attemptId": attempt_id, "task": task}

def _handle_project_execution_review_start(project_id, task_id, body=None):
    data, project, task = _project_execution_find(project_id, task_id)
    if not project or not task:
        return {"error": "Project or task not found", "_status": 404}
    if not _project_execution_enabled(project):
        return {"error": "Project Execution is not enabled for this project", "_status": 409}
    if task.get("executionState") != "execution_complete":
        return {"error": "Task must be execution_complete before reviewer handoff", "_status": 409}
    attempt = _project_execution_latest_attempt(task)
    if not attempt or not (attempt.get("evidence") or task.get("evidence")):
        return {"error": "Execution evidence is required before review", "_status": 409}
    requested_attempt = str((body or {}).get("attemptId") or attempt.get("id"))
    if requested_attempt != attempt.get("id"):
        return {"error": "Stale or mismatched attempt cannot be reviewed", "_status": 409}
    roles = _project_execution_resolve_roles(project, task)
    if not roles.get("ok"):
        return {**roles, "_status": 409}
    active = _project_execution_active_task(project)
    if active:
        return {"error": "Another task is already active for this project", "activeTaskId": active.get("id"), "_status": 409}
    review_id = str(uuid.uuid4())
    attempt["reviewer"] = roles["reviewer"]
    attempt["reviewStartedAt"] = _proj_now()
    task.update({"activeAttemptId": review_id, "reviewerAgentId": roles["reviewer"]["id"], "reviewResult": {}, "blockedReason": None, "lastError": None})
    project.update({"workflowActive": True, "workflowPhase": "reviewing", "activeTaskId": task_id, "activeAgent": roles["reviewer"]["id"]})
    _project_execution_transition(project, task, "reviewing", "user", "Independent reviewer handoff started", attempt.get("id"))
    _save_projects(data)
    with _PROJECT_EXECUTION_LOCK:
        _PROJECT_EXECUTION_REVIEW_FLAGS.add(review_id)
    _project_execution_launch_thread(_project_execution_run_review, (project_id, task_id, attempt.get("id"), review_id))
    return {"ok": True, "status": "reviewing", "taskId": task_id, "attemptId": attempt.get("id"), "reviewId": review_id}

def _handle_project_execution_acceptance(project_id, task_id, body=None):
    body = body or {}
    data, project, task = _project_execution_find(project_id, task_id)
    if not project or not task:
        return {"error": "Project or task not found", "_status": 404}
    if not _project_execution_enabled(project):
        return {"error": "Project Execution is not enabled for this project", "_status": 409}
    action = str(body.get("action") or "").strip()
    if action not in {"accept", "reject_and_rework", "mark_blocked"}:
        return {"error": "Invalid acceptance action", "_status": 400}
    review = task.get("reviewResult") or {}
    attempt_id = str(body.get("attemptId") or "")
    if action == "accept":
        if task.get("executionState") != "awaiting_user_acceptance" or review.get("status") not in {"pass", "skipped"}:
            return {"error": "Reviewer pass or skipped review confirmation is required before user acceptance", "_status": 409}
        if not attempt_id or attempt_id != review.get("attemptId"):
            return {"error": "Stale or mismatched acceptance attempt", "_status": 409}
        done_col = _wf_get_done_col(project)
        if not done_col:
            return {"error": "Done column not found", "_status": 409}
        done_reason = "User accepted skipped review result" if review.get("status") == "skipped" else "User accepted reviewer pass"
        done_result = _project_execution_mark_done(
            project,
            task,
            "user",
            done_reason,
            attempt_id,
            allow_empty_checklist=body.get("allowEmptyChecklist") is True,
        )
        if not done_result.get("ok"):
            return done_result
        task.setdefault("acceptanceHistory", []).append({"action": "accept", "attemptId": attempt_id, "at": _proj_now(), "by": "user"})
        task["acceptanceHistory"] = task["acceptanceHistory"][-50:]
        should_continue = project.get("projectExecutionStartMode") == "continuous"
        project.update({"workflowActive": False, "workflowPhase": "done", "activeTaskId": None, "activeAgent": None, "updatedAt": _proj_now(), "projectExecutionFlowActive": should_continue, "projectExecutionFlowStopReason": None if should_continue else "user_acceptance_completed"})
        _log_activity(project, "project_execution_user_accepted", "user", f"User accepted Project Execution task '{task.get('title', '')}'", task_id)
        _save_projects(data)
        if should_continue:
            _project_execution_schedule_continue(project_id, "user_accepted")
        return {"ok": True, "status": "done", "task": task, "flowContinues": should_continue}
    feedback = str(body.get("feedback") or "").strip()
    if not feedback:
        return {"error": "Feedback is required", "_status": 400}
    if task.get("executionState") != "awaiting_user_acceptance" or review.get("status") not in {"pass", "skipped"}:
        return {"error": "A current reviewer pass or skipped review result is required before this acceptance action", "_status": 409}
    if attempt_id and attempt_id != review.get("attemptId"):
        return {"error": "Stale or mismatched acceptance attempt", "_status": 409}
    task.setdefault("acceptanceHistory", []).append({"action": action, "attemptId": review.get("attemptId"), "feedback": _project_execution_redact(feedback), "at": _proj_now(), "by": "user"})
    task["acceptanceHistory"] = task["acceptanceHistory"][-50:]
    task["reviewResult"] = {}
    task["reworkFeedback"] = _project_execution_redact(feedback)
    if action == "reject_and_rework":
        workspace = _project_execution_validate_workspace(project.get("workspacePath"))
        if not workspace.get("ok"):
            task["blockedReason"] = workspace.get("error") or "Project workspace is not available for rework."
            _project_execution_transition(project, task, "blocked", "system", task["blockedReason"], review.get("attemptId"))
            _send_project_execution_intervention_notification(project, task, task["blockedReason"], review.get("attemptId"), event="blocked", kind="error")
            project.update({"workspaceStatus": workspace, "workflowActive": False, "workflowPhase": "blocked", "activeTaskId": None, "activeAgent": None, "updatedAt": _proj_now()})
            _save_projects(data)
            return {**workspace, "_status": 409}
        active = _project_execution_active_task(project)
        if active:
            return {"error": "Another task is already active for this project", "activeTaskId": active.get("id"), "_status": 409}
        roles = _project_execution_resolve_start_roles(
            project,
            task,
            allow_skip_reviewer=task.get("allowReviewerlessExecution") is True or review.get("status") == "skipped",
        )
        if not roles.get("ok"):
            return {**roles, "_status": 409}
        task["reworkCount"] = int(task.get("reworkCount") or 0) + 1
        task["blockedReason"] = None
        rejected_source = "skipped review result" if review.get("status") == "skipped" else "reviewer pass"
        rework_attempt_id = str(uuid.uuid4())
        rework_attempt = {
            "id": rework_attempt_id,
            "status": "reworking",
            "startedAt": _proj_now(),
            "workspacePath": workspace["path"],
            "workspaceKind": workspace["kind"],
            "dirtyConfirmed": False,
            "dirtyFingerprint": "",
            "executor": roles["executor"],
            "reviewer": roles.get("reviewer"),
            "skipReview": bool(roles.get("skipReview")),
            "skipReviewReason": roles.get("skipReviewReason"),
            "baseline": _project_execution_git_snapshot(workspace["path"]),
            "startMode": "single",
            "projectFlow": False,
            "requiresUserAcceptance": _project_execution_requires_user_acceptance(task),
            "rework": True,
            "reworkCycle": task["reworkCount"],
            "reworkFromAttemptId": review.get("attemptId"),
            "reworkFeedback": task["reworkFeedback"],
            "autoReviewAfterExecution": not roles.get("skipReview"),
        }
        task.setdefault("attempts", []).append(rework_attempt)
        task["attempts"] = task["attempts"][-20:]
        task.update({"activeAttemptId": rework_attempt_id, "executorAgentId": roles["executor"]["id"], "reviewerAgentId": (roles.get("reviewer") or {}).get("id"), "lastError": None})
        project.update({"workspaceStatus": workspace, "projectExecutionFlowActive": False, "projectExecutionFlowStopReason": None, "workflowActive": True, "workflowPhase": "reworking", "activeTaskId": task_id, "activeAgent": roles["executor"]["id"], "updatedAt": _proj_now()})
        _project_execution_transition(project, task, "reworking", "user", f"User rejected {rejected_source}: {feedback}", rework_attempt_id)
        _save_projects(data)
        cancel_flag = threading.Event()
        with _PROJECT_EXECUTION_LOCK:
            _PROJECT_EXECUTION_CANCEL_FLAGS[rework_attempt_id] = cancel_flag
        _project_execution_launch_thread(_project_execution_run_attempt, (project_id, task_id, rework_attempt_id, cancel_flag))
        return {"ok": True, "status": "reworking", "task": task, "attemptId": rework_attempt_id}
    task["blockedReason"] = _project_execution_redact(feedback)
    _project_execution_transition(project, task, "blocked", "user", feedback, review.get("attemptId"))
    _send_project_execution_intervention_notification(project, task, task["blockedReason"], review.get("attemptId"), event="blocked", kind="warning")
    project.update({"workflowActive": False, "workflowPhase": "blocked", "activeTaskId": None, "activeAgent": None, "updatedAt": _proj_now()})
    _save_projects(data)
    return {"ok": True, "status": "blocked", "task": task}

def _handle_project_execution_meeting_blocker_action(project_id, task_id, body=None):
    body = body or {}
    action = str(body.get("action") or "").strip()
    if action not in {"continue_execution", "mark_blocked", "reopen_meeting"}:
        return {"error": "Invalid meeting blocker action", "_status": 400}
    data, project, task = _project_execution_find(project_id, task_id)
    if not project or not task:
        return {"error": "Project or task not found", "_status": 404}
    if task.get("executionState") != "awaiting_meeting_resolution":
        return {"error": "Task is not waiting for meeting resolution", "_status": 409}
    blocker = task.get("meetingBlocker") if isinstance(task.get("meetingBlocker"), dict) else {}
    if not _project_execution_meeting_blocker_unresolved(blocker):
        return {"error": "Task has no unresolved meeting blocker", "_status": 409}
    now = _proj_now()
    feedback = _project_execution_redact(str(body.get("feedback") or body.get("reason") or "").strip())
    blocker["userAction"] = action
    blocker["userActionReason"] = feedback
    blocker["resolvedAt"] = now
    blocker["updatedAt"] = now
    task["meetingBlocker"] = blocker
    task.setdefault("meetingBlockerHistory", []).append(dict(blocker))
    task["meetingBlockerHistory"] = task["meetingBlockerHistory"][-50:]
    if action == "mark_blocked":
        blocker["status"] = "blocked"
        _meeting_request_resolve_task_blocker(blocker.get("requestId"), "blocked", {"userAction": action})
        task["blockedReason"] = feedback or "User marked task blocked while waiting for meeting resolution."
        _project_execution_transition(project, task, "blocked", "user", task["blockedReason"], blocker.get("requestId"))
        project.update({"workflowActive": False, "workflowPhase": "blocked", "activeTaskId": None, "activeAgent": None, "projectExecutionFlowActive": False, "projectExecutionFlowStopReason": "meeting_user_blocked", "updatedAt": now})
        _save_projects(data)
        return {"ok": True, "status": "blocked", "task": task}
    blocker["status"] = "cleared"
    _meeting_request_resolve_task_blocker(blocker.get("requestId"), "cleared", {"userAction": action})
    task["blockedReason"] = None
    task["lastError"] = None
    if action == "reopen_meeting":
        _project_execution_transition(project, task, "backlog", "user", feedback or "User cleared meeting blocker to request a new meeting.", blocker.get("requestId"))
        _project_execution_move_task_to_column(project, task, _wf_get_backlog_col(project))
        project.update({"workflowActive": False, "workflowPhase": "meeting_reopen_ready", "activeTaskId": None, "activeAgent": None, "projectExecutionFlowActive": False, "projectExecutionFlowStopReason": "meeting_reopen_requested", "updatedAt": now})
        _save_projects(data)
        return {"ok": True, "status": "meeting_reopen_ready", "task": task}
    _project_execution_transition(project, task, "backlog", "user", feedback or "User chose to continue execution despite unresolved meeting blocker.", blocker.get("requestId"))
    _project_execution_move_task_to_column(project, task, _wf_get_backlog_col(project))
    project.update({"workflowActive": False, "workflowPhase": "meeting_override_continue", "activeTaskId": None, "activeAgent": None, "projectExecutionFlowActive": project.get("projectExecutionStartMode") == "continuous", "projectExecutionFlowStopReason": None, "updatedAt": now})
    _save_projects(data)
    start_result = (_server_callable("_handle_project_execution_start") or _handle_project_execution_start)(project_id, task_id, {"projectStart": True, "mode": project.get("projectExecutionStartMode") or "continuous", "autoReviewAfterExecution": True, "by": "user"})
    if start_result.get("ok"):
        _, _, refreshed_task = _project_execution_find(project_id, task_id)
        return {"ok": True, "status": "started", "task": refreshed_task or task, "startResult": start_result}
    data, project, task = _project_execution_find(project_id, task_id)
    if project and task:
        task["lastError"] = start_result.get("error") or start_result.get("code") or "Failed to restart task after meeting override"
        project.update({
            "workflowActive": False,
            "workflowPhase": start_result.get("code") or "start_failed",
            "activeTaskId": None,
            "activeAgent": None,
            "projectExecutionFlowActive": False,
            "projectExecutionFlowStopReason": "meeting_override_start_failed",
            "updatedAt": _proj_now(),
        })
        _save_projects(data)
    return {"ok": False, "status": "start_failed", "task": task, "startResult": start_result, "error": start_result.get("error") or start_result.get("code") or "Failed to restart task after meeting override", "code": start_result.get("code"), "_status": start_result.get("_status", 409)}

def _handle_workflow_chat(project_id):
    from server_services import workflow as workflow_service
    workflow_service._hydrate()
    return workflow_service._handle_workflow_chat(project_id)


def _handle_workflow_start(project_id, body=None):
    from server_services import workflow as workflow_service
    workflow_service._hydrate()
    return workflow_service._handle_workflow_start(project_id, body)


def _handle_workflow_stop(project_id):
    from server_services import workflow as workflow_service
    workflow_service._hydrate()
    return workflow_service._handle_workflow_stop(project_id)


def _handle_workflow_auto_mode(project_id, body):
    from server_services import workflow as workflow_service
    workflow_service._hydrate()
    return workflow_service._handle_workflow_auto_mode(project_id, body)


def _handle_workflow_status(project_id):
    from server_services import workflow as workflow_service
    workflow_service._hydrate()
    return workflow_service._handle_workflow_status(project_id)


def _handle_review_check_update(project_id, task_id, body):
    """PUT /api/projects/{id}/tasks/{taskId}/review-check — update review status."""
    data = _load_projects()
    p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if not p:
        return {"error": "Project not found", "_status": 404}
    task = next((t for t in p["tasks"] if t["id"] == task_id), None)
    if not task:
        return {"error": "Task not found", "_status": 404}
    if _project_execution_enabled(p):
        return {"error": "Project Execution review results must be produced by the Independent reviewer flow", "_status": 409}

    review_check = body.get("reviewCheck", [])
    task["reviewCheck"] = review_check
    task["updatedAt"] = _proj_now()
    p["updatedAt"] = _proj_now()
    by = body.get("by", "user")
    _log_activity(p, "review_updated", by, "Review check updated", task_id)
    _save_projects(data)
    # Update task markdown file with review results
    current_col = next((c["title"] for c in p.get("columns", []) if c["id"] == task.get("columnId")), "review")
    _wf_write_task_file(project_id, task, current_col.lower().replace(" ", "_"), review_results=review_check, work_log_entry=f"Review check updated by {by}")
    return {"ok": True, "task": task}

def _handle_template_delete(template_id):
    """DELETE /api/projects/templates/{id}."""
    data = _load_projects()
    before = len(data.get("templates", []))
    data["templates"] = [t for t in data.get("templates", []) if t["id"] != template_id]
    if len(data["templates"]) == before:
        return {"error": "Template not found", "_status": 404}
    _save_projects(data)
    return {"ok": True, "id": template_id}

_wrap_exports()
_hydrate()
