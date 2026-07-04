"""Archive Room service split from server.py.

This module owns archive manager, archive project records, governance, and
maintenance helpers. Historical `_archive_*` and `_handle_archive_*` names remain
exported for server.py compatibility and existing tests.
"""

import json
import os
import re
import sys
import threading
import time
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_DIR = os.environ.get("VO_STATUS_DIR") or os.path.join(APP_DIR, "status")
WORKSPACE_BASE = os.environ.get("VO_OPENCLAW_PATH") or os.path.expanduser("~/.openclaw")

__all__ = [
    'ARCHIVE_ROOM_DIR',
    'ARCHIVE_ROOM_PROJECTS_DIR',
    'ARCHIVE_MANAGER_FILE',
    'ARCHIVE_MANAGER_AGENT_ID',
    'ARCHIVE_MANAGER_NAME',
    'ARCHIVE_MANAGER_EMOJI',
    'ARCHIVE_MANAGER_PROFILE_TEMPLATE',
    'ARCHIVE_MANAGER_PROFILE_VERSION_RE',
    'ARCHIVE_CONFIRMED',
    'ARCHIVE_INFERENCE',
    'ARCHIVE_PENDING',
    'ARCHIVE_AUTH_SYSTEM',
    'ARCHIVE_AUTH_SOURCE',
    'ARCHIVE_AUTH_MANAGER',
    'ARCHIVE_AUTH_HUMAN',
    'ARCHIVE_AUTH_PENDING_HUMAN',
    'ARCHIVE_AUTH_DEFERRED',
    'ARCHIVE_AUTH_REJECTED',
    'ARCHIVE_GOVERNANCE_ACTIONS',
    'ARCHIVE_MANAGER_ACTIVITY_LIMIT',
    'ARCHIVE_HIGH_VALUE_EVENTS',
    'ARCHIVE_TRIGGER_EVENT_TYPES',
    'ARCHIVE_INSPECTION_KINDS',
    'ARCHIVE_SCHEDULE_EVENT_ONLY',
    'ARCHIVE_SCHEDULE_DAILY',
    'ARCHIVE_SCHEDULE_WEEKLY',
    'ARCHIVE_SCHEDULE_CUSTOM',
    'ARCHIVE_SCHEDULE_MODES',
    'ARCHIVE_DEFAULT_SCHEDULE_MODE',
    '_archive_manager_file',
    '_archive_manager_default_state',
    '_archive_manager_load_state',
    '_archive_manager_save_state',
    '_archive_manager_append_activity',
    '_archive_project_status',
    '_archive_project_default_maintenance_enabled',
    '_archive_project_maintenance_enabled',
    '_archive_normalize_schedule_mode',
    '_archive_maintenance_schedule_mode',
    '_archive_schedule_label',
    '_archive_parse_dt',
    '_archive_iso_after',
    '_archive_schedule_state',
    '_archive_project_maintenance_meta',
    '_archive_source_ref',
    '_archive_event_key',
    '_archive_project_maintenance_records',
    '_archive_project_processed_events',
    '_archive_append_project_maintenance',
    '_archive_update_schedule_state',
    '_archive_inspection_schedule_decision',
    '_archive_entry_from_event',
    '_archive_upsert_entry',
    '_archive_pending_priority',
    '_archive_sort_pending_confirmations',
    '_archive_processed_history',
    '_archive_add_governance_history',
    '_archive_auto_governance_notices',
    '_archive_add_auto_governance_notice',
    '_archive_source_label',
    '_archive_source_comparison',
    '_archive_find_non_human_superseded_entry',
    '_archive_mark_entry_stale',
    '_archive_add_pending_confirmation',
    '_archive_manager_profile_files',
    '_archive_manager_profile_template_version',
    '_archive_manager_roster_agent',
    '_archive_manager_workspace',
    '_archive_manager_write_direct_profile_file',
    '_archive_manager_read_profile_file_version',
    '_archive_manager_profile_needs_update',
    '_archive_manager_write_profile_files',
    '_archive_manager_create_if_missing',
    '_archive_manager_profile_check_on_startup',
    '_archive_manager_public_state',
    '_agent_archive_manager_meta',
    '_is_archive_manager_agent',
    '_is_archive_related_message',
    '_archive_manager_out_of_scope_response',
    '_archive_manager_chat_guard',
    '_handle_archive_manager_update',
    '_handle_archive_manager_manual_maintain',
    '_archive_manager_ai_refine_prompt',
    '_archive_apply_ai_refinement',
    '_archive_validate_ai_refinement',
    '_handle_archive_manager_ai_refine',
    '_archive_maintenance_trigger',
    '_archive_run_inspection',
    '_archive_manager_startup_inspection',
    '_handle_archive_project_maintenance_update',
    '_handle_archive_daily_inspection',
    '_handle_archive_mark_important_message',
    '_archive_trigger_task_completed',
    '_archive_trigger_task_blocker',
    '_archive_trigger_meeting_conclusion',
    '_archive_room_project_file',
    '_archive_room_load_project_record',
    '_archive_room_save_project_record',
    '_archive_entry',
    '_archive_authority_for_confidence',
    '_archive_normalize_authority',
    '_archive_apply_authority',
    '_archive_task_counts',
    '_archive_display_value',
    '_archive_tasks',
    '_archive_task_is_done',
    '_archive_task_is_current',
    '_archive_current_task',
    '_archive_entry_kind',
    '_archive_source_types',
    '_archive_content_presence',
    '_archive_usage_map',
    '_archive_archive_introduction',
    '_archive_project_basic_info',
    '_archive_entry_brief',
    '_archive_task_brief',
    '_archive_artifact_brief',
    '_archive_index_highlights',
    '_archive_relevant_entries',
    '_archive_context_item',
    '_archive_context_trust_level',
    '_archive_project_characteristics',
    '_archive_missing_context_reminders',
    '_archive_severe_conflict_reminders',
    '_archive_build_context_package',
    '_archive_context_prompt_block',
    '_archive_room_derive_project',
    '_archive_room_project_summary',
    '_handle_archive_room_overview',
    '_handle_archive_room_audit_count',
    '_handle_archive_room_project',
    '_handle_archive_room_context',
    '_handle_archive_governance_action',
]


def _server_module():
    return sys.modules.get("server") or sys.modules.get("__main__")


def _hydrate():
    server = _server_module()
    if server is None or server is sys.modules.get(__name__):
        return
    exported = set(__all__)
    for key, value in vars(server).items():
        if key.startswith("__") or key in ("_server_module", "_hydrate", "_wrap_exports"):
            continue
        if key in exported and callable(value) and (
            getattr(value, "_service_wrapper", False) or getattr(value, "_service_wrapped", False)
        ):
            continue
        globals()[key] = value


def _wrap_exports():
    current = sys.modules[__name__]
    for name in __all__:
        value = globals().get(name)
        if not callable(value) or getattr(value, "_service_wrapped", False):
            continue

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


ARCHIVE_ROOM_DIR = os.path.join(STATUS_DIR, "archive-room")
ARCHIVE_ROOM_PROJECTS_DIR = os.path.join(ARCHIVE_ROOM_DIR, "projects")
ARCHIVE_MANAGER_FILE = os.path.join(ARCHIVE_ROOM_DIR, "manager.json")
ARCHIVE_MANAGER_AGENT_ID = "archive-manager"
ARCHIVE_MANAGER_NAME = "档案管理员"
ARCHIVE_MANAGER_EMOJI = "🗄️"
ARCHIVE_MANAGER_PROFILE_TEMPLATE = os.path.join(APP_DIR, "archive-manager-profile.md")
ARCHIVE_MANAGER_PROFILE_VERSION_RE = re.compile(r"archive-manager-profile-version:\s*([^\s>]+)", re.IGNORECASE)
ARCHIVE_CONFIRMED = "confirmed_fact"
ARCHIVE_INFERENCE = "ai_inference"
ARCHIVE_PENDING = "pending_confirmation_suggestion"
ARCHIVE_AUTH_SYSTEM = "system_confirmed"
ARCHIVE_AUTH_SOURCE = "source_confirmed"
ARCHIVE_AUTH_MANAGER = "archive_manager_confirmed"
ARCHIVE_AUTH_HUMAN = "human_confirmed"
ARCHIVE_AUTH_PENDING_HUMAN = "pending_human_confirmation"
ARCHIVE_AUTH_DEFERRED = "deferred"
ARCHIVE_AUTH_REJECTED = "rejected"
ARCHIVE_GOVERNANCE_ACTIONS = {"confirm", "reject", "defer", "edit_confirm"}
ARCHIVE_MANAGER_ACTIVITY_LIMIT = 60
ARCHIVE_HIGH_VALUE_EVENTS = {
    "task_completed",
    "task_failed",
    "project_status_changed",
    "important_artifact",
    "blocker",
    "conflict_reminder",
    "meeting_conclusion",
}
ARCHIVE_TRIGGER_EVENT_TYPES = ARCHIVE_HIGH_VALUE_EVENTS | {
    "ai_stage_summary",
    "important_message",
    "important_chat_classification",
    "low_value_activity",
}
ARCHIVE_INSPECTION_KINDS = {"startup_inspection", "daily_inspection"}
ARCHIVE_SCHEDULE_EVENT_ONLY = "event_only"
ARCHIVE_SCHEDULE_DAILY = "daily"
ARCHIVE_SCHEDULE_WEEKLY = "weekly"
ARCHIVE_SCHEDULE_CUSTOM = "custom"
ARCHIVE_SCHEDULE_MODES = {
    ARCHIVE_SCHEDULE_EVENT_ONLY,
    ARCHIVE_SCHEDULE_DAILY,
    ARCHIVE_SCHEDULE_WEEKLY,
    ARCHIVE_SCHEDULE_CUSTOM,
}
ARCHIVE_DEFAULT_SCHEDULE_MODE = ARCHIVE_SCHEDULE_DAILY


def _archive_manager_file():
    return os.path.join(ARCHIVE_ROOM_DIR, "manager.json")


def _archive_manager_default_state():
    now = _proj_now()
    return {
        "agentId": ARCHIVE_MANAGER_AGENT_ID,
        "name": ARCHIVE_MANAGER_NAME,
        "emoji": ARCHIVE_MANAGER_EMOJI,
        "providerKind": "openclaw",
        "status": "missing",
        "label": "未接入",
        "phase": "phase-4",
        "paused": False,
        "autoCreated": False,
        "createdAt": None,
        "updatedAt": now,
        "lastAction": "",
        "lastError": "",
        "recentActivity": [],
    }


def _archive_manager_load_state():
    try:
        with open(_archive_manager_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    state = _archive_manager_default_state()
    state.update({k: v for k, v in data.items() if k in state or k in {"workspace", "profileFiles", "profileVersion", "profileUpdatedAt"}})
    if not isinstance(state.get("recentActivity"), list):
        state["recentActivity"] = []
    return state


def _archive_manager_save_state(state):
    os.makedirs(ARCHIVE_ROOM_DIR, exist_ok=True)
    payload = dict(state or {})
    payload["recentActivity"] = (payload.get("recentActivity") or [])[-ARCHIVE_MANAGER_ACTIVITY_LIMIT:]
    payload["updatedAt"] = payload.get("updatedAt") or _proj_now()
    tmp = _archive_manager_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, _archive_manager_file())
    try:
        os.chmod(_archive_manager_file(), 0o666)
    except OSError:
        pass
    return payload


def _archive_manager_append_activity(state, action, status="ok", message="", project_id=None, error=""):
    entry = {
        "id": _proj_uuid(),
        "action": action,
        "status": status,
        "message": message or "",
        "projectId": project_id or "",
        "error": error or "",
        "at": _proj_now(),
    }
    activity = state.get("recentActivity") if isinstance(state.get("recentActivity"), list) else []
    activity.append(entry)
    state["recentActivity"] = activity[-ARCHIVE_MANAGER_ACTIVITY_LIMIT:]
    state["lastAction"] = action
    state["lastError"] = error or ""
    state["updatedAt"] = entry["at"]
    return entry


def _archive_project_status(project):
    return str((project or {}).get("status") or "active").strip().lower() or "active"


def _archive_project_default_maintenance_enabled(project):
    return _archive_project_status(project) in {"active", "ongoing", "in_progress", "running"}


def _archive_project_maintenance_enabled(project):
    project = project or {}
    if "archiveMaintenanceEnabled" in project:
        return bool(project.get("archiveMaintenanceEnabled"))
    if "archiveMaintenance" in project and isinstance(project.get("archiveMaintenance"), dict):
        val = project["archiveMaintenance"].get("enabled")
        if val is not None:
            return bool(val)
    return _archive_project_default_maintenance_enabled(project)


def _archive_normalize_schedule_mode(mode, default=None):
    mode = str(mode or "").strip().lower()
    aliases = {
        "event": ARCHIVE_SCHEDULE_EVENT_ONLY,
        "event-only": ARCHIVE_SCHEDULE_EVENT_ONLY,
        "event_only": ARCHIVE_SCHEDULE_EVENT_ONLY,
        "events": ARCHIVE_SCHEDULE_EVENT_ONLY,
        "daily": ARCHIVE_SCHEDULE_DAILY,
        "day": ARCHIVE_SCHEDULE_DAILY,
        "weekly": ARCHIVE_SCHEDULE_WEEKLY,
        "week": ARCHIVE_SCHEDULE_WEEKLY,
        "custom": ARCHIVE_SCHEDULE_CUSTOM,
    }
    if not mode:
        return default
    return aliases.get(mode)


def _archive_maintenance_schedule_mode(project):
    maintenance = (project or {}).get("archiveMaintenance") if isinstance((project or {}).get("archiveMaintenance"), dict) else {}
    mode = maintenance.get("scheduleMode") or maintenance.get("frequency") or ""
    return _archive_normalize_schedule_mode(mode, ARCHIVE_DEFAULT_SCHEDULE_MODE)


def _archive_schedule_label(mode):
    return {
        ARCHIVE_SCHEDULE_EVENT_ONLY: "仅事件触发",
        ARCHIVE_SCHEDULE_DAILY: "事件触发 + 每日巡检",
        ARCHIVE_SCHEDULE_WEEKLY: "事件触发 + 每周巡检",
        ARCHIVE_SCHEDULE_CUSTOM: "事件触发 + 自定义巡检",
    }.get(mode or "", "事件触发 + 每日巡检")


def _archive_parse_dt(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _archive_iso_after(value, days=1):
    base = _archive_parse_dt(value) or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return (base + timedelta(days=days)).isoformat()


def _archive_schedule_state(record):
    state = record.get("archiveMaintenanceSchedule") if isinstance(record.get("archiveMaintenanceSchedule"), dict) else {}
    record["archiveMaintenanceSchedule"] = state
    return state


def _archive_project_maintenance_meta(project, record=None):
    explicit = "archiveMaintenanceEnabled" in (project or {}) or (
        isinstance((project or {}).get("archiveMaintenance"), dict)
        and (project.get("archiveMaintenance") or {}).get("enabled") is not None
    )
    mode = _archive_maintenance_schedule_mode(project)
    schedule = {}
    if isinstance(record, dict):
        schedule = record.get("archiveMaintenanceSchedule") if isinstance(record.get("archiveMaintenanceSchedule"), dict) else {}
    last_scheduled = schedule.get("lastScheduledAt") or ((record or {}).get("inspections") or {}).get("lastDailyInspectionAt", "")
    if mode == ARCHIVE_SCHEDULE_EVENT_ONLY:
        next_scheduled = ""
    elif mode == ARCHIVE_SCHEDULE_WEEKLY:
        next_scheduled = schedule.get("nextScheduledAt") or _archive_iso_after(last_scheduled, 7)
    elif mode == ARCHIVE_SCHEDULE_CUSTOM:
        next_scheduled = schedule.get("nextScheduledAt") or ""
    else:
        next_scheduled = schedule.get("nextScheduledAt") or _archive_iso_after(last_scheduled, 1)
    project_maintenance = project.get("archiveMaintenance") if isinstance((project or {}).get("archiveMaintenance"), dict) else {}
    return {
        "enabled": _archive_project_maintenance_enabled(project),
        "defaultEnabled": _archive_project_default_maintenance_enabled(project),
        "explicit": bool(explicit),
        "status": _archive_project_status(project),
        "scheduleMode": mode,
        "frequency": mode,
        "frequencyLabel": _archive_schedule_label(mode),
        "nextScheduledAt": next_scheduled,
        "lastScheduledAt": schedule.get("lastScheduledAt") or "",
        "lastScheduledKind": schedule.get("lastScheduledKind") or "",
        "lastEventTriggeredAt": schedule.get("lastEventTriggeredAt") or "",
        "lastSkippedAt": schedule.get("lastSkippedAt") or "",
        "lastSkippedReason": schedule.get("lastSkippedReason") or "",
        "lastSkippedKind": schedule.get("lastSkippedKind") or "",
        "customIntervalHours": schedule.get("customIntervalHours") or project_maintenance.get("customIntervalHours"),
        "explanation": "计划巡检按频率执行；事件触发整理独立生效；关闭长期维护或暂停管理员时计划整理会跳过，高价值事件仍会保留处理入口。"
    }


def _archive_source_ref(source_type, source_id="", title="", **extra):
    ref = {"type": source_type, "id": str(source_id or ""), "title": str(title or ""), "at": _proj_now()}
    for key, value in extra.items():
        if value not in (None, ""):
            ref[key] = value
    return ref


def _archive_event_key(project_id, event_type, source=None, fallback=""):
    source = source if isinstance(source, dict) else {}
    raw = "|".join([
        str(project_id or ""),
        str(event_type or ""),
        str(source.get("type") or ""),
        str(source.get("id") or ""),
        str(source.get("taskId") or ""),
        str(source.get("meetingId") or ""),
        str(source.get("path") or ""),
        str(fallback or ""),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _archive_project_maintenance_records(record):
    items = record.get("managerMaintenance")
    if not isinstance(items, list):
        items = []
    record["managerMaintenance"] = items
    return items


def _archive_project_processed_events(record):
    processed = record.get("processedEvents")
    if not isinstance(processed, dict):
        processed = {}
    record["processedEvents"] = processed
    return processed


def _archive_append_project_maintenance(record, item):
    history = _archive_project_maintenance_records(record)
    history.append(item)
    record["managerMaintenance"] = history[-80:]
    return item


def _archive_update_schedule_state(record, *, kind="", status="", at="", reason=""):
    schedule = _archive_schedule_state(record)
    now = at or _proj_now()
    if status in {"ok", "no_update"} and kind in {"daily_inspection", "weekly_inspection", "custom_inspection"}:
        schedule["lastScheduledAt"] = now
        schedule["lastScheduledKind"] = kind
        if kind == "weekly_inspection":
            schedule["nextScheduledAt"] = _archive_iso_after(now, 7)
        elif kind == "custom_inspection":
            hours = int(schedule.get("customIntervalHours") or 0)
            schedule["nextScheduledAt"] = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat() if hours > 0 else ""
        else:
            schedule["nextScheduledAt"] = _archive_iso_after(now, 1)
    elif status == "event":
        schedule["lastEventTriggeredAt"] = now
    elif status == "skipped":
        schedule["lastSkippedAt"] = now
        schedule["lastSkippedKind"] = kind
        schedule["lastSkippedReason"] = reason
    record["archiveMaintenanceSchedule"] = schedule
    return schedule


def _archive_inspection_schedule_decision(project, record, kind, force=False):
    if kind == "startup_inspection":
        return {"run": True, "scheduledKind": "startup_inspection", "reason": ""}
    mode = _archive_maintenance_schedule_mode(project)
    if mode == ARCHIVE_SCHEDULE_EVENT_ONLY:
        return {"run": False, "scheduledKind": "daily_inspection", "reason": "项目设置为仅事件触发，计划巡检已跳过。"}
    schedule = _archive_schedule_state(record)
    now = datetime.now(timezone.utc)
    if mode == ARCHIVE_SCHEDULE_WEEKLY:
        last = _archive_parse_dt(schedule.get("lastScheduledAt") or ((record.get("inspections") or {}).get("lastWeeklyInspectionAt")))
        if last and (now - last) < timedelta(days=7) and not force:
            return {"run": False, "scheduledKind": "weekly_inspection", "reason": "每周计划巡检尚未到期。"}
        return {"run": True, "scheduledKind": "weekly_inspection", "reason": ""}
    if mode == ARCHIVE_SCHEDULE_CUSTOM:
        hours = int(schedule.get("customIntervalHours") or ((project.get("archiveMaintenance") or {}).get("customIntervalHours") if isinstance(project.get("archiveMaintenance"), dict) else 0) or 0)
        if hours <= 0:
            return {"run": False, "scheduledKind": "custom_inspection", "reason": "自定义巡检间隔未配置。"}
        last = _archive_parse_dt(schedule.get("lastScheduledAt"))
        if last and (now - last) < timedelta(hours=hours) and not force:
            return {"run": False, "scheduledKind": "custom_inspection", "reason": "自定义计划巡检尚未到期。"}
        return {"run": True, "scheduledKind": "custom_inspection", "reason": ""}
    last = _archive_parse_dt(schedule.get("lastScheduledAt") or ((record.get("inspections") or {}).get("lastDailyInspectionAt")))
    if last and last.date() == now.date() and not force:
        return {"run": False, "scheduledKind": "daily_inspection", "reason": "每日计划巡检今日已完成。"}
    return {"run": True, "scheduledKind": "daily_inspection", "reason": ""}


def _archive_entry_from_event(event_key, title, text, confidence, source, stale=False, kind="event"):
    entry_id = f"{kind}-{event_key[:16]}"
    entry = _archive_entry(entry_id, title, text, confidence, source, stale=stale)
    entry["kind"] = kind
    entry["updatedAt"] = _proj_now()
    return entry


def _archive_upsert_entry(record, entry):
    entries = record.get("entries") if isinstance(record.get("entries"), list) else []
    entry_id = entry.get("id")
    replaced = False
    for idx, existing in enumerate(entries):
        if existing.get("id") == entry_id:
            entries[idx] = {**existing, **entry}
            replaced = True
            break
    if not replaced:
        entries.append(entry)
    record["entries"] = entries[-200:]
    return "updated" if replaced else "created"


def _archive_pending_priority(item):
    if not isinstance(item, dict):
        return 50
    status = str(item.get("status") or "")
    if status in {"deferred", ARCHIVE_AUTH_DEFERRED} or item.get("authority") == ARCHIVE_AUTH_DEFERRED:
        return 90
    if item.get("conflict") or item.get("conflictSummary"):
        return 0
    impact = str(item.get("impact") or "").lower()
    if impact in {"risk", "project_status", "task_conclusion", "risk_judgment"}:
        return 5
    if impact in {"state", "task"}:
        return 10
    kind = str(item.get("kind") or "").lower()
    title = str(item.get("title") or "").lower()
    if kind == "rule" or "rule" in title or "规则" in title:
        return 20
    return 40


def _archive_sort_pending_confirmations(pending):
    items = [p for p in pending or [] if isinstance(p, dict)]
    items.sort(key=lambda p: (_archive_pending_priority(p), p.get("createdAt") or "", p.get("id") or ""))
    return items


def _archive_processed_history(record):
    history = record.get("processedGovernance")
    if not isinstance(history, list):
        history = []
    record["processedGovernance"] = history
    return history


def _archive_add_governance_history(record, item):
    history = _archive_processed_history(record)
    history.append(item)
    record["processedGovernance"] = history[-200:]
    return item


def _archive_auto_governance_notices(record):
    notices = record.get("automaticGovernanceNotices")
    if not isinstance(notices, list):
        notices = []
    record["automaticGovernanceNotices"] = notices
    return notices


def _archive_add_auto_governance_notice(record, title, summary, action="auto_resolved", source_comparison=None):
    item = {
        "id": f"auto-governance-{_proj_uuid()}",
        "at": _proj_now(),
        "action": action,
        "title": title or "自动治理",
        "summary": summary or "",
        "sourceComparison": source_comparison or {},
        "actor": ARCHIVE_MANAGER_AGENT_ID,
    }
    notices = _archive_auto_governance_notices(record)
    notices.append(item)
    record["automaticGovernanceNotices"] = notices[-20:]
    _archive_add_governance_history(record, {
        "id": f"governance-{_proj_uuid()}",
        "pendingId": "",
        "action": action,
        "status": ARCHIVE_AUTH_MANAGER,
        "actor": ARCHIVE_MANAGER_AGENT_ID,
        "at": item["at"],
        "reason": summary or "",
        "title": title or "自动治理",
        "text": summary or "",
        "sourceComparison": source_comparison or {},
    })
    return item


def _archive_source_label(source):
    source = source if isinstance(source, dict) else {}
    return source.get("title") or source.get("id") or source.get("type") or source.get("sourceType") or ""


def _archive_source_comparison(old_entry, new_entry, judgment):
    old_sources = (old_entry or {}).get("sources") or []
    new_sources = (new_entry or {}).get("sources") or []
    old_source = old_sources[0] if old_sources and isinstance(old_sources[0], dict) else {}
    new_source = new_sources[0] if new_sources and isinstance(new_sources[0], dict) else {}
    return {
        "oldEntryId": (old_entry or {}).get("id") or "",
        "oldTitle": (old_entry or {}).get("title") or "",
        "oldText": (old_entry or {}).get("text") or "",
        "oldSource": old_source,
        "oldSourceLabel": _archive_source_label(old_source),
        "oldSourceType": old_source.get("type") or old_source.get("sourceType") or "",
        "oldSourceAt": old_source.get("at") or "",
        "newEntryId": (new_entry or {}).get("id") or "",
        "newTitle": (new_entry or {}).get("title") or "",
        "newText": (new_entry or {}).get("text") or "",
        "newSource": new_source,
        "newSourceLabel": _archive_source_label(new_source),
        "newSourceType": new_source.get("type") or new_source.get("sourceType") or "",
        "newSourceAt": new_source.get("at") or "",
        "managerJudgment": judgment or "",
    }


def _archive_find_non_human_superseded_entry(record, new_entry):
    title = str((new_entry or {}).get("title") or "").strip().lower()
    kind = str((new_entry or {}).get("kind") or "").strip().lower()
    text = str((new_entry or {}).get("text") or "").strip().lower()
    for entry in record.get("entries") or []:
        if not isinstance(entry, dict) or entry.get("id") == (new_entry or {}).get("id"):
            continue
        authority = _archive_normalize_authority(entry)
        if authority in {ARCHIVE_AUTH_HUMAN, ARCHIVE_AUTH_REJECTED, ARCHIVE_AUTH_PENDING_HUMAN, ARCHIVE_AUTH_DEFERRED}:
            continue
        if entry.get("stale"):
            continue
        same_title = title and title == str(entry.get("title") or "").strip().lower()
        same_kind = kind and kind == str(entry.get("kind") or "").strip().lower()
        overlapping_text = text and str(entry.get("text") or "").strip().lower() and (text in str(entry.get("text") or "").strip().lower() or str(entry.get("text") or "").strip().lower() in text)
        if same_title or (same_kind and overlapping_text):
            return entry
    return None


def _archive_mark_entry_stale(entry, replacement, reason, source_comparison=None):
    if not isinstance(entry, dict):
        return entry
    entry["stale"] = True
    entry["staleAt"] = _proj_now()
    entry["staleReason"] = reason or "Superseded by newer archive manager governance."
    entry["replacedBy"] = (replacement or {}).get("id") or ""
    entry["sourceComparison"] = source_comparison or entry.get("sourceComparison") or {}
    entry["updatedAt"] = _proj_now()
    return entry


def _archive_add_pending_confirmation(record, event_key, title, text, source, reason="", impact="state", conflict=None, kind="pending"):
    pending = record.get("pendingConfirmations")
    if not isinstance(pending, list):
        pending = []
    item_id = f"pending-{event_key[:16]}"
    existing = next((item for item in pending if item.get("id") == item_id), None)
    payload = {
        "id": item_id,
        "title": title,
        "text": text,
        "confidence": ARCHIVE_PENDING,
        "authority": ARCHIVE_AUTH_PENDING_HUMAN,
        "impact": impact,
        "reason": reason,
        "sources": [source] if source else [],
        "createdAt": (existing or {}).get("createdAt") or _proj_now(),
        "updatedAt": _proj_now(),
        "status": ARCHIVE_AUTH_PENDING_HUMAN,
        "kind": kind,
        "entryId": f"{kind}-{event_key[:16]}",
    }
    if isinstance(conflict, dict):
        payload["conflict"] = True
        payload["conflictSummary"] = conflict.get("summary") or reason or "New archive suggestion conflicts with confirmed content."
        payload["confirmedSide"] = conflict.get("confirmedSide") or {}
        payload["suggestedSide"] = conflict.get("suggestedSide") or {"title": title, "text": text}
    if existing:
        existing.update(payload)
    else:
        pending.append(payload)
    record["pendingConfirmations"] = _archive_sort_pending_confirmations(pending)[-100:]
    return payload


def _archive_manager_profile_files():
    try:
        with open(ARCHIVE_MANAGER_PROFILE_TEMPLATE, "r", encoding="utf-8") as f:
            template = f.read()
    except OSError as exc:
        raise RuntimeError(f"Archive manager profile template cannot be read: {exc}") from exc

    version = _archive_manager_profile_template_version(template)
    files = {}
    current_name = None
    current_lines = []
    marker_re = re.compile(r"^--- file:\s*([A-Za-z0-9_.-]+)\s*---\s*$")
    for line in template.splitlines():
        marker = marker_re.match(line)
        if marker:
            if current_name:
                files[current_name] = "\n".join(current_lines).strip() + "\n"
            current_name = marker.group(1)
            current_lines = []
            continue
        if current_name:
            current_lines.append(line)
    if current_name:
        files[current_name] = "\n".join(current_lines).strip() + "\n"

    replacements = {
        "{{ARCHIVE_MANAGER_NAME}}": ARCHIVE_MANAGER_NAME,
        "{{ARCHIVE_MANAGER_EMOJI}}": ARCHIVE_MANAGER_EMOJI,
        "{{ARCHIVE_MANAGER_AGENT_ID}}": ARCHIVE_MANAGER_AGENT_ID,
        "{{ARCHIVE_MANAGER_PROFILE_VERSION}}": version,
    }
    rendered = {}
    for filename, content in files.items():
        for token, value in replacements.items():
            content = content.replace(token, value)
        rendered[filename] = content

    required = {"IDENTITY.md", "SOUL.md", "AGENTS.md", "agent.md", "MEMORY.md", "HEARTBEAT.md"}
    missing = sorted(required - set(rendered))
    if missing:
        raise RuntimeError(f"Archive manager profile template missing files: {', '.join(missing)}")
    return rendered


def _archive_manager_profile_template_version(template=None):
    if template is None:
        try:
            with open(ARCHIVE_MANAGER_PROFILE_TEMPLATE, "r", encoding="utf-8") as f:
                template = f.read(4096)
        except OSError as exc:
            raise RuntimeError(f"Archive manager profile template cannot be read: {exc}") from exc
    for line in str(template or "").splitlines()[:20]:
        if line.lower().startswith("archive-manager-profile-version:"):
            version = line.split(":", 1)[1].strip()
            if version:
                return version
    raise RuntimeError("Archive manager profile template missing Archive-Manager-Profile-Version header")


def _archive_manager_roster_agent():
    refresh_agent_maps()
    for agent in get_roster():
        if str(agent.get("id") or "") == ARCHIVE_MANAGER_AGENT_ID or str(agent.get("statusKey") or "") == ARCHIVE_MANAGER_AGENT_ID:
            return agent
        if str(agent.get("name") or "").strip() == ARCHIVE_MANAGER_NAME:
            return agent
    return None


def _archive_manager_workspace(agent_id):
    safe_id = _sanitize_agent_id(agent_id or ARCHIVE_MANAGER_AGENT_ID)
    roster_agent = _archive_manager_roster_agent()
    workspace = ""
    if roster_agent and str(roster_agent.get("id") or "") == (agent_id or ARCHIVE_MANAGER_AGENT_ID):
        workspace = str(roster_agent.get("workspace") or "")
    if not workspace:
        workspace = os.path.join(WORKSPACE_BASE, f"workspace-{safe_id}")
    base = os.path.realpath(WORKSPACE_BASE)
    real_workspace = os.path.realpath(workspace)
    if not (real_workspace == base or real_workspace.startswith(base + os.sep)):
        raise ValueError("Archive manager workspace is outside OpenClaw home")
    return real_workspace


def _archive_manager_write_direct_profile_file(agent_id, filename, content):
    workspace = _archive_manager_workspace(agent_id)
    os.makedirs(workspace, exist_ok=True)
    path = os.path.realpath(os.path.join(workspace, filename))
    if not path.startswith(workspace + os.sep):
        raise ValueError("Archive manager profile path is outside workspace")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
        if content and not content.endswith("\n"):
            f.write("\n")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o666)
    except OSError:
        pass
    return workspace


def _archive_manager_read_profile_file_version(workspace, filename):
    path = os.path.realpath(os.path.join(workspace, filename))
    real_workspace = os.path.realpath(workspace)
    if not path.startswith(real_workspace + os.sep):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            head = f.read(512)
    except OSError:
        return ""
    match = ARCHIVE_MANAGER_PROFILE_VERSION_RE.search(head)
    return match.group(1).strip() if match else ""


def _archive_manager_profile_needs_update(agent_id, profile_files, target_version):
    try:
        workspace = _archive_manager_workspace(agent_id)
    except Exception:
        return True
    for filename in profile_files:
        if _archive_manager_read_profile_file_version(workspace, filename) != target_version:
            return True
    return False


def _archive_manager_write_profile_files(agent_id):
    try:
        profile_files = _archive_manager_profile_files()
        target_version = _archive_manager_profile_template_version()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    if not _archive_manager_profile_needs_update(agent_id, profile_files, target_version):
        try:
            workspace = _archive_manager_workspace(agent_id)
        except Exception:
            workspace = ""
        return {"ok": True, "profileFiles": list(profile_files.keys()), "workspace": workspace, "profileVersion": target_version, "updated": False}
    written = []
    workspace = ""
    for filename, content in profile_files.items():
        try:
            workspace = _archive_manager_write_direct_profile_file(agent_id, filename, content)
            written.append(filename)
        except Exception as exc:
            return {"ok": False, "error": f"failed to write {filename}: {exc}"}
    return {"ok": True, "profileFiles": written, "workspace": workspace, "profileVersion": target_version, "updated": True}


def _archive_manager_create_if_missing():
    state = _archive_manager_load_state()
    existing = _archive_manager_roster_agent()
    if existing:
        profile_result = _archive_manager_write_profile_files(existing.get("id") or ARCHIVE_MANAGER_AGENT_ID)
        if not profile_result.get("ok"):
            state["agentId"] = existing.get("id") or ARCHIVE_MANAGER_AGENT_ID
            state["name"] = ARCHIVE_MANAGER_NAME
            state["providerKind"] = existing.get("providerKind", "openclaw")
            state["workspace"] = existing.get("workspace", "")
            state["status"] = "error"
            state["label"] = "档案管理员配置失败"
            state["lastError"] = profile_result.get("error", "")
            _archive_manager_append_activity(state, "profile_repair", "error", "档案管理员 profile 写入失败", error=state["lastError"])
            return _archive_manager_save_state(state)
        state["agentId"] = existing.get("id") or ARCHIVE_MANAGER_AGENT_ID
        state["name"] = ARCHIVE_MANAGER_NAME
        state["providerKind"] = existing.get("providerKind", "openclaw")
        state["workspace"] = profile_result.get("workspace") or existing.get("workspace", "")
        state["profileFiles"] = profile_result.get("profileFiles", [])
        state["profileVersion"] = profile_result.get("profileVersion", "")
        if profile_result.get("updated"):
            state["profileUpdatedAt"] = _proj_now()
            _archive_manager_append_activity(state, "profile_update", "ok", f"档案管理员 profile 已更新到版本 {state.get('profileVersion', '')}")
        state["status"] = "paused" if state.get("paused") else "idle"
        state["label"] = "已暂停" if state.get("paused") else ("已自动创建" if state.get("autoCreated") else "已接入")
        state["lastError"] = ""
        _archive_manager_save_state(state)
        return state

    now = _proj_now()
    workspace_dir = os.path.join(WORKSPACE_BASE, f"workspace-{ARCHIVE_MANAGER_AGENT_ID}")
    try:
        create_params = {
            "name": ARCHIVE_MANAGER_AGENT_ID,
            "workspace": workspace_dir,
            "emoji": ARCHIVE_MANAGER_EMOJI,
        }
        selected_model = _default_openclaw_agent_model()
        if selected_model:
            create_params["model"] = selected_model
        result = _gateway_rpc_call("agents.create", create_params, timeout=30)
        if not result.get("ok"):
            state["status"] = "error"
            state["label"] = "档案管理员创建失败"
            state["lastError"] = result.get("error", "OpenClaw agent creation failed")
            _archive_manager_append_activity(state, "auto_create", "error", "自动创建档案管理员失败", error=state["lastError"])
            return _archive_manager_save_state(state)

        agent_id = result.get("agentId") or ARCHIVE_MANAGER_AGENT_ID
        profile_result = _archive_manager_write_profile_files(agent_id)
        if not profile_result.get("ok"):
            state["status"] = "error"
            state["label"] = "档案管理员创建失败"
            state["agentId"] = agent_id
            state["lastError"] = profile_result.get("error", "")
            _archive_manager_append_activity(state, "auto_create", "error", "档案管理员已创建但 profile 写入失败", error=state["lastError"])
            return _archive_manager_save_state(state)

        global _discovered_at
        _discovered_at = 0
        server = _server_module()
        if server is not None and hasattr(server, "_discovered_at"):
            server._discovered_at = 0
        refresh_agent_maps()
        state.update({
            "agentId": agent_id,
            "name": ARCHIVE_MANAGER_NAME,
            "providerKind": "openclaw",
            "status": "idle",
            "label": "已自动创建",
            "paused": False,
            "autoCreated": True,
            "createdAt": now,
            "workspace": profile_result.get("workspace") or workspace_dir,
            "profileFiles": profile_result.get("profileFiles", []),
            "profileVersion": profile_result.get("profileVersion", ""),
            "profileUpdatedAt": now if profile_result.get("updated") else None,
            "lastError": "",
        })
        _archive_manager_append_activity(state, "auto_create", "ok", "已自动创建档案管理员")
        return _archive_manager_save_state(state)
    except Exception as exc:
        state["status"] = "error"
        state["label"] = "档案管理员创建失败"
        state["lastError"] = str(exc)
        _archive_manager_append_activity(state, "auto_create", "error", "自动创建档案管理员失败", error=str(exc))
        return _archive_manager_save_state(state)


def _archive_manager_profile_check_on_startup():
    """Keep the built-in archive manager profile in sync with VO's template."""
    time.sleep(4)
    try:
        state = _archive_manager_create_if_missing()
        if state.get("status") == "error":
            print(f"[ARCHIVE MANAGER] profile check failed: {state.get('lastError') or 'unknown error'}")
            return
        version = state.get("profileVersion") or ""
        if version:
            print(f"[ARCHIVE MANAGER] profile ready: {state.get('agentId') or ARCHIVE_MANAGER_AGENT_ID} version={version}")
        else:
            print(f"[ARCHIVE MANAGER] profile ready: {state.get('agentId') or ARCHIVE_MANAGER_AGENT_ID}")
    except Exception as exc:
        print(f"[ARCHIVE MANAGER] startup profile check failed: {exc}")


def _archive_manager_public_state(ensure=True):
    state = _archive_manager_create_if_missing() if ensure else _archive_manager_load_state()
    if state.get("paused"):
        state["status"] = "paused"
        state["label"] = "已暂停"
    return {
        "agentId": state.get("agentId") or ARCHIVE_MANAGER_AGENT_ID,
        "name": state.get("name") or ARCHIVE_MANAGER_NAME,
        "emoji": state.get("emoji") or ARCHIVE_MANAGER_EMOJI,
        "providerKind": state.get("providerKind", "openclaw"),
        "status": state.get("status", "missing"),
        "label": state.get("label", "未接入"),
        "phase": "phase-4",
        "paused": bool(state.get("paused")),
        "autoCreated": bool(state.get("autoCreated")),
        "createdAt": state.get("createdAt"),
        "updatedAt": state.get("updatedAt"),
        "profileVersion": state.get("profileVersion", ""),
        "profileUpdatedAt": state.get("profileUpdatedAt"),
        "lastAction": state.get("lastAction", ""),
        "lastError": state.get("lastError", ""),
        "recentActivity": (state.get("recentActivity") or [])[-12:],
    }


def _agent_archive_manager_meta(agent_id_or_key):
    state = _archive_manager_load_state()
    if not _is_archive_manager_agent(agent_id_or_key):
        return {}
    if state.get("status") == "missing" and str(agent_id_or_key or "") in {ARCHIVE_MANAGER_AGENT_ID, ARCHIVE_MANAGER_NAME}:
        state["status"] = "idle"
        state["label"] = "已接入"
        state["agentId"] = ARCHIVE_MANAGER_AGENT_ID
        state["name"] = ARCHIVE_MANAGER_NAME
    return {
        "systemRole": "archive_manager",
        "assignable": False,
        "archiveManager": True,
        "archiveManagerStatus": state.get("status", "missing"),
        "archiveManagerPaused": bool(state.get("paused")),
        "archiveManagerLabel": state.get("label", "未接入"),
    }


def _is_archive_manager_agent(agent_id_or_key):
    needle = str(agent_id_or_key or "")
    if needle in {ARCHIVE_MANAGER_AGENT_ID, ARCHIVE_MANAGER_NAME}:
        return True
    state = _archive_manager_load_state()
    return bool(needle and needle in {str(state.get("agentId") or ""), str(state.get("name") or "")})


def _is_archive_related_message(message):
    text = str(message or "").lower()
    keywords = [
        "档案", "归档", "档案室", "项目产物", "产物", "上下文", "入场包", "目录", "来源", "证据",
        "archive", "archives", "archival", "artifact", "artifacts", "onboarding", "context",
        "catalog", "source", "sources", "evidence", "summary", "summaries",
    ]
    return any(k in text for k in keywords)


def _archive_manager_out_of_scope_response():
    return (
        "我是档案管理员，只处理档案室、项目上下文、产物来源、入场包和归档维护相关问题。"
        "普通执行、编码、审查、闲聊或项目任务分配请转给对应执行 AI。"
    )


def _archive_manager_chat_guard(to_agent_id, message):
    if not _is_archive_manager_agent(to_agent_id):
        return None
    if _is_archive_related_message(message):
        return None
    return {
        "ok": True,
        "reply": _archive_manager_out_of_scope_response(),
        "status": "archive_manager_out_of_scope",
        "archiveManager": _archive_manager_public_state(ensure=False),
    }


def _handle_archive_manager_update(body):
    action = str((body or {}).get("action") or "").strip().lower()
    try:
        state = _archive_manager_create_if_missing()
    except Exception as exc:
        state = _archive_manager_load_state()
        state["status"] = "error"
        state["label"] = "档案管理员不可用"
        state["lastError"] = str(exc)
        _archive_manager_append_activity(state, f"auto_{event_type}", "error", "自动整理失败", project_id=project_id, error=str(exc))
        try:
            _archive_manager_save_state(state)
        except Exception:
            pass
        return {"ok": False, "status": "error", "error": str(exc), "eventType": event_type}
    if action == "pause":
        state["paused"] = True
        state["status"] = "paused"
        state["label"] = "已暂停"
        _archive_manager_append_activity(state, "pause", "ok", "档案管理员已暂停")
        gateway_presence.set_manual_override(state.get("agentId") or ARCHIVE_MANAGER_AGENT_ID, "break", "Archive manager paused")
        saved = _archive_manager_save_state(state)
        return {"ok": True, "archiveManager": _archive_manager_public_state(ensure=False), "activity": (saved.get("recentActivity") or [])[-1]}
    if action == "resume":
        state["paused"] = False
        state["status"] = "idle"
        state["label"] = "已接入"
        _archive_manager_append_activity(state, "resume", "ok", "档案管理员已恢复")
        gateway_presence.set_manual_override(state.get("agentId") or ARCHIVE_MANAGER_AGENT_ID, "idle", "")
        saved = _archive_manager_save_state(state)
        return {"ok": True, "archiveManager": _archive_manager_public_state(ensure=False), "activity": (saved.get("recentActivity") or [])[-1]}
    return {"error": "Unsupported archive manager action", "_status": 400}


def _handle_archive_manager_manual_maintain(project_id):
    data = _load_projects()
    project = next((p for p in data.get("projects", []) if isinstance(p, dict) and p.get("id") == project_id), None)
    if not project:
        return {"error": "Project not found", "_status": 404}
    try:
        state = _archive_manager_create_if_missing()
    except Exception as exc:
        state = _archive_manager_load_state()
        state["status"] = "error"
        state["label"] = "档案管理员不可用"
        state["lastError"] = str(exc)
        _archive_manager_append_activity(state, f"auto_{event_type}", "error", "自动整理失败", project_id=project_id, error=str(exc))
        try:
            _archive_manager_save_state(state)
        except Exception:
            pass
        return {"ok": False, "status": "error", "error": str(exc), "eventType": event_type}
    if state.get("status") == "error":
        _archive_manager_append_activity(state, "manual_maintain", "error", "当前项目手动整理失败", project_id=project_id, error=state.get("lastError", "archive manager unavailable"))
        _archive_manager_save_state(state)
        return {"error": state.get("lastError") or "Archive manager unavailable", "archiveManager": _archive_manager_public_state(ensure=False), "_status": 409}
    started_at = _proj_now()
    state["status"] = "working"
    state["label"] = "整理中"
    _archive_manager_append_activity(state, "manual_maintain", "running", f"开始整理项目：{project.get('title', '')}", project_id=project_id)
    _archive_manager_save_state(state)
    record = _archive_room_derive_project(project)
    record.setdefault("managerMaintainedAt", started_at)
    record.setdefault("managerMaintenance", [])
    record["managerMaintenance"] = (record.get("managerMaintenance") or [])[-20:] + [{
        "at": started_at,
        "managerAgentId": state.get("agentId") or ARCHIVE_MANAGER_AGENT_ID,
        "status": "ok",
        "summary": "Manual current-project archive maintenance completed.",
        "output": {
            "status": "ok",
            "projectId": project_id,
            "summary": "当前项目档案已根据现有项目、任务和产物记录刷新。",
            "sources": [{"type": "project", "id": project_id}],
            "updates": [{"kind": "summary", "confidence": ARCHIVE_INFERENCE, "text": record.get("summary", {}).get("currentState", "")}],
            "error": "",
        },
    }]
    _archive_room_save_project_record(project_id, record)
    state["status"] = "paused" if state.get("paused") else "idle"
    state["label"] = "已暂停" if state.get("paused") else "已接入"
    _archive_manager_append_activity(state, "manual_maintain", "ok", f"完成整理项目：{project.get('title', '')}", project_id=project_id)
    _archive_manager_save_state(state)
    return {"ok": True, "project": record, "archiveManager": _archive_manager_public_state(ensure=False)}


def _archive_manager_ai_refine_prompt(project, record):
    metrics = record.get("metrics") or {}
    entries = record.get("entries") if isinstance(record.get("entries"), list) else []
    pending = record.get("pendingConfirmations") if isinstance(record.get("pendingConfirmations"), list) else []
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), list) else []
    compact_entries = [
        {
            "id": e.get("id"),
            "title": e.get("title"),
            "kind": e.get("kind"),
            "authority": _archive_normalize_authority(e),
            "stale": bool(e.get("stale")),
            "text": str(e.get("text") or "")[:600],
        }
        for e in entries[:20]
        if isinstance(e, dict)
    ]
    compact_pending = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "impact": item.get("impact"),
            "reason": item.get("reason") or item.get("automationInsufficientReason"),
            "text": str(item.get("text") or "")[:500],
        }
        for item in pending[:10]
        if isinstance(item, dict)
    ]
    compact_artifacts = [
        {
            "path": a.get("path"),
            "kind": a.get("kind"),
            "sources": [
                {
                    "taskTitle": s.get("taskTitle"),
                    "agentId": s.get("agentId"),
                    "providerKind": s.get("providerKind"),
                    "capturedAt": s.get("capturedAt"),
                }
                for s in (a.get("sources") or [])[:3]
                if isinstance(s, dict)
            ],
        }
        for a in artifacts[:20]
        if isinstance(a, dict)
    ]
    payload = {
        "project": {
            "id": project.get("id"),
            "title": project.get("title"),
            "description": project.get("description"),
            "status": project.get("status"),
            "metrics": metrics,
            "currentTask": (_archive_current_task(project) or {}).get("title") or "",
        },
        "archive": {
            "summary": record.get("summary") or {},
            "entries": compact_entries,
            "pendingConfirmations": compact_pending,
            "artifacts": compact_artifacts,
            "archiveIntroduction": record.get("archiveIntroduction") or {},
            "projectBasicInfo": record.get("projectBasicInfo") or {},
        },
    }
    return (
        "你是 Virtual Office 的档案管理员 archive-manager。请对当前项目档案做一次精确整理和概括。\n"
        "工作边界：只整理档案室上下文，不执行普通项目任务，不修改项目代码，不创建会议。\n"
        "请基于输入中的项目、任务、产物、已有档案、待确认项和来源信息，产出稳定 JSON。不要输出 JSON 以外的文字。\n"
        "如果信息不足，请在 gaps 中说明，不要编造事实。stale 或 pending 内容不能当作已确认事实。\n\n"
        "必须返回如下 JSON 对象：\n"
        "{\n"
        "  \"status\": \"ok|needs_human|error\",\n"
        "  \"summary\": \"面向人类的项目档案精整摘要，2-4 句\",\n"
        "  \"currentState\": \"当前状态，一句话\",\n"
        "  \"nextStep\": \"建议下一步，一句话；不确定则写空字符串\",\n"
        "  \"highlights\": [\"关键事实或判断，最多 5 条\"],\n"
        "  \"risks\": [\"风险/冲突/待确认，最多 5 条\"],\n"
        "  \"gaps\": [\"缺失信息或需要人工确认的问题，最多 5 条\"],\n"
        "  \"archiveEntries\": [\n"
        "    {\"title\":\"条目标题\",\"kind\":\"summary|risk|decision|artifact|context\",\"text\":\"条目内容\",\"confidence\":\"ai_inference|manager_confirmed\"}\n"
        "  ]\n"
        "}\n\n"
        "输入数据：\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _archive_apply_ai_refinement(record, parsed, source, now):
    if not isinstance(parsed, dict):
        return []
    summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
    if parsed.get("currentState"):
        summary["currentState"] = str(parsed.get("currentState") or "").strip()
    if parsed.get("nextStep") is not None:
        summary["nextStep"] = str(parsed.get("nextStep") or "").strip()
    if parsed.get("summary"):
        summary["goal"] = summary.get("goal") or str(parsed.get("summary") or "").strip()
    record["summary"] = summary
    updates = []
    for idx, item in enumerate(parsed.get("archiveEntries") or []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        text = str(item.get("text") or "").strip()
        if not title or not text:
            continue
        entry = _archive_entry(
            f"ai-refine-{hashlib.sha1((title + text).encode('utf-8')).hexdigest()[:16]}",
            title,
            text,
            item.get("confidence") or ARCHIVE_INFERENCE,
            source,
        )
        entry["kind"] = str(item.get("kind") or "summary").strip() or "summary"
        entry["updatedAt"] = now
        _archive_apply_authority(entry, ARCHIVE_AUTH_MANAGER, actor=ARCHIVE_MANAGER_AGENT_ID)
        _archive_upsert_entry(record, entry)
        updates.append(entry)
        if len(updates) >= 8:
            break
    return updates


def _archive_validate_ai_refinement(parsed, raw_reply=""):
    if str(raw_reply or "").startswith("[ERROR]"):
        return "档案管理员调用失败，未产生有效精整结果。"
    if not isinstance(parsed, dict):
        return "档案管理员未返回可解析的稳定 JSON。"
    if parsed.get("runId") or parsed.get("timeoutPhase") or parsed.get("providerStarted"):
        return "档案管理员调用超时或被中断，未产生有效精整结果。"
    status = str(parsed.get("status") or "").strip()
    if status not in {"ok", "needs_human", "error"}:
        return "档案管理员返回的 JSON status 不符合约定。"
    if status == "error":
        return str(parsed.get("summary") or parsed.get("error") or "档案管理员返回精整失败。")
    content_keys = ("summary", "currentState", "nextStep", "highlights", "risks", "gaps", "archiveEntries")
    if not any(parsed.get(k) for k in content_keys):
        return "档案管理员返回的 JSON 缺少可入档内容。"
    return ""


def _handle_archive_manager_ai_refine(project_id, body=None):
    data = _load_projects()
    project = next((p for p in data.get("projects", []) if isinstance(p, dict) and p.get("id") == project_id), None)
    if not project:
        return {"error": "Project not found", "_status": 404}
    try:
        state = _archive_manager_create_if_missing()
    except Exception as exc:
        return {"error": str(exc), "archiveManager": _archive_manager_public_state(ensure=False), "_status": 409}
    if state.get("status") == "error":
        return {"error": state.get("lastError") or "Archive manager unavailable", "archiveManager": _archive_manager_public_state(ensure=False), "_status": 409}
    if state.get("paused") and not (body or {}).get("allowWhenPaused"):
        return {"error": "档案管理员已暂停，不能执行 AI 精整。", "archiveManager": _archive_manager_public_state(ensure=False), "_status": 409}
    now = _proj_now()
    state["status"] = "working"
    state["label"] = "精整中"
    _archive_manager_append_activity(state, "ai_refine", "running", f"开始 AI 精整项目档案：{project.get('title', '')}", project_id=project_id)
    _archive_manager_save_state(state)
    record = _archive_room_derive_project(project)
    prompt = _archive_manager_ai_refine_prompt(project, record)
    reply = _wf_call_agent(state.get("agentId") or ARCHIVE_MANAGER_AGENT_ID, prompt, timeout=int((body or {}).get("timeoutSec") or 600), project_id=project_id, task_id="archive-ai-refine")
    parsed = _meeting_parse_json_object(reply)
    source = _archive_source_ref("archive_manager_ai_refine", f"ai-refine:{now}", title="档案管理员 AI 精整", agentId=state.get("agentId") or ARCHIVE_MANAGER_AGENT_ID)
    status = "ok"
    error = _archive_validate_ai_refinement(parsed, reply)
    updates = []
    if error:
        status = "error"
    else:
        updates = _archive_apply_ai_refinement(record, parsed, source, now)
    record.setdefault("managerMaintainedAt", now)
    item = {
        "id": _proj_uuid(),
        "at": now,
        "managerAgentId": state.get("agentId") or ARCHIVE_MANAGER_AGENT_ID,
        "status": status,
        "eventType": "ai_refine",
        "triggerType": "manual_ai_refine",
        "projectId": project_id,
        "summary": (parsed or {}).get("summary") if isinstance(parsed, dict) else ("档案管理员 AI 精整失败" if status == "error" else "档案管理员 AI 精整完成"),
        "prompt": prompt,
        "rawReply": reply,
        "output": {
            "status": status,
            "projectId": project_id,
            "summary": (parsed or {}).get("summary") if isinstance(parsed, dict) else "",
            "parsed": parsed or {},
            "sources": [source],
            "updates": updates,
            "error": error,
        },
        "error": error,
    }
    _archive_append_project_maintenance(record, item)
    record["archiveUpdatedAt"] = now
    _archive_room_save_project_record(project_id, record)
    state["status"] = "paused" if state.get("paused") else "idle"
    state["label"] = "已暂停" if state.get("paused") else "已接入"
    _archive_manager_append_activity(state, "ai_refine", status, "完成 AI 精整项目档案" if status == "ok" else "AI 精整项目档案失败", project_id=project_id, error=error)
    _archive_manager_save_state(state)
    derived = _archive_room_derive_project(project)
    return {"ok": status == "ok", "status": status, "project": derived, "archiveManager": _archive_manager_public_state(ensure=False), "maintenance": item, "error": error, "_status": 200 if status == "ok" else 502}


def _archive_maintenance_trigger(project_id, event_type, source=None, title="", summary="", value_level=None, reason="", impact="", allow_when_paused=False):
    source = source if isinstance(source, dict) else {}
    event_type = str(event_type or "").strip()
    if event_type not in ARCHIVE_TRIGGER_EVENT_TYPES and event_type not in ARCHIVE_INSPECTION_KINDS:
        return {"ok": False, "status": "error", "error": "Unsupported archive maintenance event", "eventType": event_type}
    data = _load_projects()
    project = next((p for p in data.get("projects", []) if isinstance(p, dict) and p.get("id") == project_id), None)
    if not project:
        return {"ok": False, "status": "error", "error": "Project not found", "_status": 404}
    try:
        state = _archive_manager_create_if_missing()
    except Exception as exc:
        state = _archive_manager_load_state()
        state["status"] = "error"
        state["label"] = "档案管理员不可用"
        state["lastError"] = str(exc)
        _archive_manager_append_activity(state, f"auto_{event_type}", "error", "自动整理失败", project_id=project_id, error=str(exc))
        try:
            _archive_manager_save_state(state)
        except Exception:
            pass
        return {"ok": False, "status": "error", "error": str(exc), "eventType": event_type}
    event_key = _archive_event_key(project_id, event_type, source, fallback=summary or title)
    high_value = event_type in ARCHIVE_HIGH_VALUE_EVENTS or value_level == "high"
    routine = event_type in ARCHIVE_INSPECTION_KINDS
    maintenance = _archive_project_maintenance_meta(project)
    record = _archive_room_derive_project(project)
    now = _proj_now()

    def save_outcome(status, message, entry=None, noisy=True, error=""):
        if status == "skipped" and routine:
            _archive_update_schedule_state(record, kind=source.get("scheduleKind") or event_type, status="skipped", at=now, reason=message)
        item = {
            "id": _proj_uuid(),
            "at": now,
            "managerAgentId": state.get("agentId") or ARCHIVE_MANAGER_AGENT_ID,
            "status": status,
            "eventType": event_type,
            "triggerType": event_type,
            "projectId": project_id,
            "source": source,
            "summary": message,
            "classificationReason": reason or "",
            "valueLevel": "high" if high_value else (value_level or "normal"),
            "eventKey": event_key,
            "error": error or "",
            "output": {
                "status": status,
                "projectId": project_id,
                "summary": message,
                "sources": [source] if source else [],
                "updates": [entry] if entry else [],
                "error": error or "",
            },
        }
        if noisy:
            _archive_append_project_maintenance(record, item)
        _archive_room_save_project_record(project_id, record)
        _archive_manager_append_activity(state, f"auto_{event_type}", status, message, project_id=project_id, error=error)
        _archive_manager_save_state(state)
        return {"ok": status not in {"error"}, "status": status, "project": record, "activity": item, "archiveManager": _archive_manager_public_state(ensure=False)}

    if state.get("status") == "error":
        return save_outcome("error", "自动整理失败：档案管理员不可用", error=state.get("lastError", "archive manager unavailable"))
    if state.get("paused") and not allow_when_paused:
        return save_outcome("skipped", "档案管理员已暂停，自动整理已跳过。", noisy=True)
    if not maintenance.get("enabled") and not high_value:
        return save_outcome("skipped", "项目未开启长期维护，低价值事件已跳过。", noisy=False)
    processed = _archive_project_processed_events(record)
    if processed.get(event_key):
        return save_outcome("skipped", "该来源事件已整理，已幂等跳过。", noisy=False)

    if routine:
        inspection_key = "lastStartupInspectionAt" if event_type == "startup_inspection" else "lastDailyInspectionAt"
        record.setdefault("inspections", {})[inspection_key] = now
        schedule_kind = source.get("scheduleKind") or ("startup_inspection" if event_type == "startup_inspection" else "daily_inspection")
        if schedule_kind == "weekly_inspection":
            record.setdefault("inspections", {})["lastWeeklyInspectionAt"] = now
        _archive_update_schedule_state(record, kind=schedule_kind, status="no_update", at=now)
        record["archiveUpdatedAt"] = now
        processed[event_key] = {"eventType": event_type, "processedAt": now, "status": "no_update"}
        return save_outcome("no_update", "巡检完成，未发现需要更新的档案内容。", noisy=False)

    objective_events = {"task_completed", "important_artifact", "project_status_changed"}
    manager_confirmed_events = {"important_message", "important_chat_classification", "ai_stage_summary"}
    confidence = ARCHIVE_CONFIRMED if event_type in objective_events else ARCHIVE_INFERENCE
    text = summary or title or f"Archive maintenance event: {event_type}"
    entry_title = title or event_type.replace("_", " ").title()
    high_impact = (impact or "").strip().lower() in {"state", "task", "risk", "project_status", "task_conclusion", "risk_judgment"}
    human_conflict = event_type == "conflict_reminder" and any(
        _archive_normalize_authority(e) == ARCHIVE_AUTH_HUMAN
        for e in record.get("entries", []) if isinstance(e, dict)
    )
    owner_decision_terms = ["owner", "人类", "human", "approval", "批准", "规则", "rule", "policy", "策略"]
    owner_decision = high_impact and any(term in (text + " " + entry_title + " " + reason).lower() for term in owner_decision_terms)
    non_human_meeting_conclusion = event_type == "meeting_conclusion" and any(
        term in str(reason or "").lower()
        for term in ("非人工", "non-human", "not human", "来源更强")
    )
    archive_manager_first_auto = (
        event_type in {"conflict_reminder"} or non_human_meeting_conclusion
    ) and not human_conflict and not owner_decision
    requires_human_confirmation = event_type not in objective_events and not archive_manager_first_auto and (
        event_type in {"meeting_conclusion", "conflict_reminder"} or high_impact or confidence == ARCHIVE_PENDING
    )
    entry = _archive_entry_from_event(event_key, entry_title, text, confidence, source, kind=event_type)
    if event_type in objective_events:
        _archive_apply_authority(entry, ARCHIVE_AUTH_SYSTEM if event_type == "project_status_changed" else ARCHIVE_AUTH_SOURCE)
        entry["confirmedBy"] = "system"
        entry["confirmedAt"] = now
        entry["confirmationReason"] = "Objective VO source event."
    elif requires_human_confirmation:
        _archive_apply_authority(entry, ARCHIVE_AUTH_PENDING_HUMAN)
    elif archive_manager_first_auto:
        _archive_apply_authority(entry, ARCHIVE_AUTH_MANAGER, actor=state.get("agentId") or ARCHIVE_MANAGER_AGENT_ID)
        entry["confirmedAt"] = now
        entry["confirmationReason"] = reason or "Archive manager automatically resolved non-human-confirmed governance."
    elif event_type in manager_confirmed_events and not high_value and (impact or "").strip().lower() not in {"state", "task", "risk", "project_status", "task_conclusion", "risk_judgment"}:
        _archive_apply_authority(entry, ARCHIVE_AUTH_MANAGER, actor=state.get("agentId") or ARCHIVE_MANAGER_AGENT_ID)
        entry["confirmedAt"] = now
        entry["confirmationReason"] = reason or "Archive manager judged this source-backed summary low risk."
    else:
        _archive_apply_authority(entry, ARCHIVE_AUTH_MANAGER, actor=state.get("agentId") or ARCHIVE_MANAGER_AGENT_ID)
    superseded = None
    source_comparison = None
    if archive_manager_first_auto:
        superseded = _archive_find_non_human_superseded_entry(record, entry)
        if superseded:
            source_comparison = _archive_source_comparison(superseded, entry, reason or "新来源更强，档案管理员自动更新非人工确认内容。")
            entry["sourceComparison"] = source_comparison
            entry["replaces"] = superseded.get("id") or ""
            _archive_mark_entry_stale(superseded, entry, "新来源更强，档案管理员自动标记旧内容过期。", source_comparison)
    change = _archive_upsert_entry(record, entry)
    if archive_manager_first_auto:
        _archive_add_auto_governance_notice(
            record,
            entry_title,
            "档案管理员已自动处理非人工确认内容。" + (" 旧内容已标记过期。" if superseded else ""),
            action="auto_governance_resolved",
            source_comparison=source_comparison,
        )
    pending_item = None
    if requires_human_confirmation:
        conflict = None
        if event_type == "conflict_reminder":
            confirmed_side = next((e for e in record.get("entries", []) if _archive_normalize_authority(e) == ARCHIVE_AUTH_HUMAN), None)
            source_comparison = _archive_source_comparison(confirmed_side or {}, entry, reason or "新建议与人工确认内容冲突，需要 owner 判断。")
            conflict = {
                "summary": reason or text or "New suggestion conflicts with human-confirmed archive content.",
                "confirmedSide": confirmed_side or {},
                "suggestedSide": {"title": entry_title, "text": text, "sources": [source] if source else []},
                "sourceComparison": source_comparison,
            }
        pending_item = _archive_add_pending_confirmation(
            record,
            event_key,
            entry_title,
            text,
            source,
            reason=reason or "High-impact archive update requires human confirmation.",
            impact=impact or ("risk" if event_type == "conflict_reminder" else "state"),
            conflict=conflict,
            kind=event_type,
        )
        pending_item["managerJudgment"] = "档案管理员判断该事项需要人工确认。"
        pending_item["automationInsufficientReason"] = reason or ("涉及人工确认内容或 owner 级决策，不能自动处理。" if human_conflict or owner_decision else "高影响内容需要人工确认。")
        pending_item["humanDecisionNeeded"] = "请确认、编辑确认、暂缓或拒绝该档案建议。"
        if source_comparison:
            pending_item["sourceComparison"] = source_comparison
        record["pendingConfirmations"] = _archive_sort_pending_confirmations(record.get("pendingConfirmations") or [])
    record["archiveUpdatedAt"] = now
    _archive_update_schedule_state(record, status="event", at=now)
    processed[event_key] = {"eventType": event_type, "processedAt": now, "status": change, "source": source}
    if pending_item:
        entry["pendingConfirmationId"] = pending_item.get("id")
    return save_outcome("ok", f"自动整理完成：{entry_title}", entry=entry, noisy=True)


def _archive_run_inspection(kind="startup_inspection", force=False):
    if kind not in ARCHIVE_INSPECTION_KINDS:
        return {"ok": False, "error": "Unsupported inspection kind", "_status": 400}
    data = _load_projects()
    results = []
    today = datetime.now(timezone.utc).date().isoformat()
    for project in data.get("projects", []) if isinstance(data, dict) else []:
        if not isinstance(project, dict) or project.get("template"):
            continue
        record = _archive_room_load_project_record(project.get("id"))
        if not _archive_project_maintenance_enabled(project):
            if kind == "daily_inspection":
                _archive_update_schedule_state(record, kind="daily_inspection", status="skipped", reason="项目长期维护已关闭，计划巡检已跳过。")
                _archive_room_save_project_record(project.get("id"), record)
            continue
        decision = _archive_inspection_schedule_decision(project, record, kind, force=force)
        if not decision.get("run"):
            _archive_update_schedule_state(record, kind=decision.get("scheduledKind") or kind, status="skipped", reason=decision.get("reason") or "计划巡检已跳过。")
            _archive_room_save_project_record(project.get("id"), record)
            results.append({"ok": True, "status": "skipped", "projectId": project.get("id"), "eventType": kind, "scheduleKind": decision.get("scheduledKind"), "reason": decision.get("reason")})
            continue
        schedule_kind = decision.get("scheduledKind") or kind
        source = _archive_source_ref("inspection", f"{kind}:{schedule_kind}:{today if kind == 'daily_inspection' else 'startup'}", title=kind, scheduleKind=schedule_kind)
        if kind == "daily_inspection":
            last = ((record.get("inspections") or {}).get("lastDailyInspectionAt") or "")[:10]
            if schedule_kind == "daily_inspection" and last == today and not force:
                continue
        results.append(_archive_maintenance_trigger(
            project.get("id"),
            kind,
            source=source,
            title="Archive inspection",
            summary="Scheduled archive inspection completed.",
            value_level="routine",
        ))
    return {"ok": True, "kind": kind, "results": results, "checkedProjectCount": len(results)}


def _archive_manager_startup_inspection():
    time.sleep(6)
    try:
        _archive_run_inspection("startup_inspection")
    except Exception as exc:
        state = _archive_manager_load_state()
        _archive_manager_append_activity(state, "startup_inspection", "error", "启动巡检失败", error=str(exc))
        _archive_manager_save_state(state)


def _handle_archive_project_maintenance_update(project_id, body):
    data = _load_projects()
    project = next((p for p in data.get("projects", []) if isinstance(p, dict) and p.get("id") == project_id), None)
    if not project:
        return {"error": "Project not found", "_status": 404}
    body = body or {}
    current = project.get("archiveMaintenance") if isinstance(project.get("archiveMaintenance"), dict) else {}
    enabled = bool(body.get("enabled")) if "enabled" in body else _archive_project_maintenance_enabled(project)
    schedule_mode = current.get("scheduleMode") or current.get("frequency") or ARCHIVE_DEFAULT_SCHEDULE_MODE
    if "scheduleMode" in body or "frequency" in body:
        requested = _archive_normalize_schedule_mode(body.get("scheduleMode", body.get("frequency")))
        if requested not in ARCHIVE_SCHEDULE_MODES:
            return {"error": "Unsupported archive maintenance schedule mode", "_status": 400}
        schedule_mode = requested
    custom_hours = current.get("customIntervalHours")
    if "customIntervalHours" in body:
        try:
            custom_hours = max(1, int(body.get("customIntervalHours") or 0))
        except Exception:
            return {"error": "customIntervalHours must be a positive integer", "_status": 400}
    project["archiveMaintenanceEnabled"] = enabled
    project["archiveMaintenance"] = {
        **current,
        "enabled": enabled,
        "scheduleMode": schedule_mode,
        "frequency": schedule_mode,
        "customIntervalHours": custom_hours,
        "updatedAt": _proj_now(),
        "updatedBy": str((body or {}).get("by") or "user"),
    }
    project["updatedAt"] = _proj_now()
    _save_projects(data)
    record = _archive_room_derive_project(project)
    schedule = _archive_schedule_state(record)
    if schedule_mode != ARCHIVE_SCHEDULE_CUSTOM:
        schedule.pop("customIntervalHours", None)
    elif custom_hours:
        schedule["customIntervalHours"] = custom_hours
    record["archiveMaintenanceSchedule"] = schedule
    _archive_room_save_project_record(project_id, record)
    return {"ok": True, "project": project, "archive": record, "maintenance": _archive_project_maintenance_meta(project, record)}


def _handle_archive_daily_inspection(body=None):
    return _archive_run_inspection("daily_inspection", force=bool((body or {}).get("force")))


def _handle_archive_mark_important_message(body):
    project_id = str((body or {}).get("projectId") or "").strip()
    text = str((body or {}).get("text") or (body or {}).get("message") or "").strip()
    message_id = str((body or {}).get("messageId") or uuid.uuid4()).strip()
    if not project_id:
        return {"error": "projectId is required", "_status": 400}
    if not text:
        return {"error": "text is required", "_status": 400}
    source = _archive_source_ref("chat", message_id, title="Important message", conversationId=(body or {}).get("conversationId"))
    result = _archive_maintenance_trigger(
        project_id,
        "important_message",
        source=source,
        title="Important message",
        summary=text,
        value_level="normal",
        reason="User marked this message as important.",
        impact=str((body or {}).get("impact") or "context"),
    )
    return result


def _archive_trigger_task_completed(project_id, task):
    if not project_id or not isinstance(task, dict):
        return None
    return _archive_maintenance_trigger(
        project_id,
        "task_completed",
        source=_archive_source_ref("task", task.get("id"), title=task.get("title", ""), taskId=task.get("id")),
        title=f"Task completed: {task.get('title', '')}",
        summary=f"Task completed: {task.get('title', '')}",
        value_level="high",
        impact="task",
    )


def _archive_trigger_task_blocker(project_id, task):
    if not project_id or not isinstance(task, dict):
        return None
    reason = task.get("blockedReason") or task.get("lastError") or ""
    if not reason and str(task.get("executionState") or "").lower() != "blocked":
        return None
    return _archive_maintenance_trigger(
        project_id,
        "blocker",
        source=_archive_source_ref("task", task.get("id"), title=task.get("title", ""), taskId=task.get("id")),
        title=f"Task blocker: {task.get('title', '')}",
        summary=reason or "Task is blocked.",
        value_level="high",
        impact="risk",
    )


def _archive_trigger_meeting_conclusion(meeting):
    if not isinstance(meeting, dict):
        return None
    project_id = str(meeting.get("projectId") or "").strip()
    if not project_id:
        return None
    result = meeting.get("result") if isinstance(meeting.get("result"), dict) else {}
    summary = result.get("summary") or result.get("decision") or meeting.get("topic") or "Meeting completed."
    return _archive_maintenance_trigger(
        project_id,
        "meeting_conclusion",
        source=_archive_source_ref("meeting", meeting.get("id"), title=meeting.get("topic", ""), meetingId=meeting.get("id")),
        title=f"Meeting conclusion: {meeting.get('topic', '')}",
        summary=summary,
        value_level="high",
        reason="Meeting completed with a project-linked conclusion.",
        impact="state",
    )


def _archive_room_project_file(project_id):
    safe = _safe_agent_workspace_key(project_id or "project")
    return os.path.join(ARCHIVE_ROOM_PROJECTS_DIR, f"{safe}.json")


def _archive_room_load_project_record(project_id):
    path = _archive_room_project_file(project_id)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _archive_room_save_project_record(project_id, record):
    os.makedirs(ARCHIVE_ROOM_PROJECTS_DIR, exist_ok=True)
    path = _archive_room_project_file(project_id)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o666)
    except OSError:
        pass


def _archive_entry(entry_id, title, text, confidence=ARCHIVE_INFERENCE, source=None, stale=False):
    authority = _archive_authority_for_confidence(confidence)
    return {
        "id": entry_id,
        "title": title,
        "text": text or "",
        "confidence": confidence,
        "authority": authority,
        "status": authority,
        "stale": bool(stale),
        "sources": [source] if source else [],
    }


def _archive_authority_for_confidence(confidence):
    if confidence == ARCHIVE_CONFIRMED:
        return ARCHIVE_AUTH_SOURCE
    if confidence == ARCHIVE_PENDING:
        return ARCHIVE_AUTH_PENDING_HUMAN
    return ARCHIVE_AUTH_MANAGER


def _archive_normalize_authority(item, default=None):
    item = item if isinstance(item, dict) else {}
    status = str(item.get("status") or "").strip()
    authority = str(item.get("authority") or "").strip()
    confidence = item.get("confidence")
    if authority:
        return authority
    if status in {
        ARCHIVE_AUTH_SYSTEM,
        ARCHIVE_AUTH_SOURCE,
        ARCHIVE_AUTH_MANAGER,
        ARCHIVE_AUTH_HUMAN,
        ARCHIVE_AUTH_PENDING_HUMAN,
        ARCHIVE_AUTH_DEFERRED,
        ARCHIVE_AUTH_REJECTED,
    }:
        return status
    if status == "pending":
        return ARCHIVE_AUTH_PENDING_HUMAN
    if status == "deferred":
        return ARCHIVE_AUTH_DEFERRED
    if status == "rejected":
        return ARCHIVE_AUTH_REJECTED
    if confidence == ARCHIVE_CONFIRMED:
        return default or ARCHIVE_AUTH_SOURCE
    if confidence == ARCHIVE_PENDING:
        return ARCHIVE_AUTH_PENDING_HUMAN
    return default or ARCHIVE_AUTH_MANAGER


def _archive_apply_authority(item, authority=None, actor=None):
    if not isinstance(item, dict):
        return item
    auth = authority or _archive_normalize_authority(item)
    item["authority"] = auth
    item["status"] = auth
    if auth == ARCHIVE_AUTH_HUMAN:
        item["confidence"] = ARCHIVE_CONFIRMED
    elif auth in {ARCHIVE_AUTH_SYSTEM, ARCHIVE_AUTH_SOURCE}:
        item["confidence"] = ARCHIVE_CONFIRMED
    elif auth == ARCHIVE_AUTH_PENDING_HUMAN:
        item["confidence"] = ARCHIVE_PENDING
    elif auth == ARCHIVE_AUTH_DEFERRED:
        item["confidence"] = ARCHIVE_PENDING
    elif auth == ARCHIVE_AUTH_REJECTED:
        item["confidence"] = ARCHIVE_PENDING
    else:
        item["confidence"] = item.get("confidence") or ARCHIVE_INFERENCE
    if actor and not item.get("confirmedBy"):
        item["confirmedBy"] = actor
    return item


def _archive_task_counts(project):
    tasks = project.get("tasks", []) or []
    total = len(tasks)
    done = sum(1 for t in tasks if t.get("completedAt"))
    active_states = {"validating", "executing", "reviewing", "reworking", "running"}
    active_ai = sorted({
        str(t.get("executorAgentId") or t.get("assignee") or "").strip()
        for t in tasks
        if (t.get("executionState") in active_states) and (t.get("executorAgentId") or t.get("assignee"))
    })
    blockers = [
        t for t in tasks
        if t.get("blockedReason") or str(t.get("executionState") or "").lower() == "blocked" or t.get("lastError")
    ]
    pending = [
        t for t in tasks
        if t.get("requiresUserAcceptance") and t.get("completedAt") and not t.get("acceptedAt")
    ]
    return {
        "total": total,
        "done": done,
        "completionRate": round((done / total) * 100) if total else 0,
        "activeAi": [a for a in active_ai if a],
        "riskCount": len(blockers) + len(_project_cron_alerts(project, limit=1000)),
        "pendingConfirmationCount": len(pending),
    }


def _archive_display_value(value, missing="未记录"):
    text = str(value or "").strip()
    return text if text else missing


def _archive_tasks(project):
    tasks = project.get("tasks") if isinstance(project.get("tasks"), list) else []
    return [t for t in tasks if isinstance(t, dict)]


def _archive_task_is_done(task):
    return bool(task.get("completedAt")) or str(task.get("status") or "").lower() in {"done", "completed"}


def _archive_task_is_current(task):
    state = str(task.get("executionState") or task.get("status") or "").lower()
    if state in {"executing", "running", "validating", "reviewing", "reworking", "blocked", "todo", "in_progress"}:
        return True
    return not _archive_task_is_done(task)


def _archive_current_task(project):
    for task in _archive_tasks(project):
        if _archive_task_is_current(task):
            return task
    tasks = _archive_tasks(project)
    return tasks[-1] if tasks else None


def _archive_entry_kind(entry):
    kind = str((entry or {}).get("kind") or "").strip()
    if kind:
        return kind
    title = str((entry or {}).get("title") or "").lower()
    if "risk" in title or "blocker" in title:
        return "risk"
    if "decision" in title:
        return "decision"
    if "rule" in title:
        return "rule"
    return "summary"


def _archive_source_types(entries, artifacts=None, pending=None):
    types = set()
    for entry in entries or []:
        for source in entry.get("sources") or []:
            if isinstance(source, dict) and (source.get("type") or source.get("sourceType")):
                types.add(str(source.get("type") or source.get("sourceType")))
    for artifact in artifacts or []:
        for source in artifact.get("sources") or []:
            if isinstance(source, dict) and (source.get("sourceType") or source.get("type")):
                types.add(str(source.get("sourceType") or source.get("type")))
    for item in pending or []:
        for source in item.get("sources") or []:
            if isinstance(source, dict) and (source.get("type") or source.get("sourceType")):
                types.add(str(source.get("type") or source.get("sourceType")))
    return sorted(types)


def _archive_content_presence(project, entries, artifacts, pending):
    tasks = _archive_tasks(project)
    kinds = {_archive_entry_kind(entry) for entry in entries or []}
    meeting_sources = any(
        any(isinstance(s, dict) and s.get("type") == "meeting" for s in entry.get("sources") or [])
        for entry in entries or []
    )
    important_messages = "important_message" in kinds or any(
        any(isinstance(s, dict) and s.get("type") == "chat" for s in entry.get("sources") or [])
        for entry in entries or []
    )
    items = [
        ("basic_info", "基础信息", bool(project.get("title") or project.get("description") or project.get("status")), "项目名称、描述、状态和进度"),
        ("tasks", "任务", bool(tasks), f"{len(tasks)} 个任务"),
        ("artifacts", "产物", bool(artifacts), f"{len(artifacts or [])} 个产物"),
        ("decisions", "决策", bool({"decision", "meeting_conclusion"} & kinds), "关键决策和会议结论"),
        ("risks", "风险", bool({"risk", "blocker", "conflict_reminder"} & kinds), "风险、阻塞和冲突"),
        ("meetings", "会议", meeting_sources or "meeting_conclusion" in kinds, "项目相关会议结论"),
        ("important_messages", "重要消息", important_messages, "被标记或识别的重要上下文"),
        ("pending_confirmations", "待确认", bool(pending), f"{len(pending or [])} 个待确认项"),
    ]
    return [
        {"key": key, "label": label, "present": present, "summary": summary if present else "暂无记录"}
        for key, label, present, summary in items
    ]


def _archive_usage_map(project, counts, artifact_count, pending_count):
    return [
        {"key": "human_review", "label": "人类验收", "available": True, "summary": "查看项目状态、产物和维护记录。"},
        {"key": "handoff", "label": "交接", "available": True, "summary": "用基础信息、上下文目录和入场包快速交接。"},
        {"key": "ai_onboarding", "label": "AI 入场", "available": True, "summary": "为新 AI 提供项目目标、状态、规则、风险和来源。"},
        {"key": "task_context", "label": "任务上下文", "available": counts.get("total", 0) > 0, "summary": "围绕当前任务加载相关决策、风险和产物。"},
        {"key": "risk_governance", "label": "风险治理", "available": counts.get("riskCount", 0) > 0 or pending_count > 0, "summary": "追踪风险、冲突、缺失和待确认内容。"},
        {"key": "artifact_browsing", "label": "产物浏览", "available": artifact_count > 0, "summary": "按来源或路径查看项目产物。"},
    ]


def _archive_archive_introduction(project, counts, entries, artifacts, pending):
    title = _archive_display_value(project.get("title"), "未命名项目")
    artifact_count = len(artifacts or [])
    pending_count = len(pending or [])
    present = [item["label"] for item in _archive_content_presence(project, entries, artifacts, pending) if item["present"]]
    missing = [item["label"] for item in _archive_content_presence(project, entries, artifacts, pending) if not item["present"]]
    return {
        "title": f"{title} 的项目档案",
        "purpose": "这个档案用于沉淀项目长期上下文，帮助人类验收、追踪和交接，也帮助新加入的 AI 快速获得项目背景。",
        "currentlyContains": present,
        "missingOrSparse": missing,
        "futureContent": ["关键决策", "风险/阻塞", "会议结论", "重要消息", "任务结果", "产物来源", "待确认项"],
        "humanUse": "人类可以用它理解项目状态、检查产物、查看维护记录和识别待补充信息。",
        "aiUse": "AI 可以用它获取项目入场包、任务上下文、来源引用和风险提醒，而不需要读取全部原始历史。",
        "readiness": {
            "label": "可用" if (counts.get("total", 0) or artifact_count or entries) else "待补充",
            "summary": f"{counts.get('done', 0)} / {counts.get('total', 0)} 个任务完成，{artifact_count} 个产物，{pending_count} 个待确认项。",
        },
    }


def _archive_project_basic_info(project, counts, artifact_count, pending_count, source_types):
    maintenance = _archive_project_maintenance_meta(project)
    participants = sorted(set([a for a in counts.get("activeAi", []) if a]))
    return {
        "name": _archive_display_value(project.get("title"), "未命名项目"),
        "description": _archive_display_value(project.get("description")),
        "status": _archive_display_value(project.get("status"), "active"),
        "taskProgress": f"{counts.get('done', 0)} / {counts.get('total', 0)}",
        "completionRate": counts.get("completionRate", 0),
        "updatedAt": project.get("updatedAt") or project.get("createdAt") or "",
        "maintenanceEnabled": maintenance.get("enabled"),
        "maintenanceLabel": "长期维护已开启" if maintenance.get("enabled") else "长期维护已关闭",
        "activeAi": participants,
        "participantsLabel": "、".join(participants) if participants else "暂无活跃 AI",
        "artifactCount": artifact_count,
        "pendingConfirmationCount": pending_count,
        "sourceTypes": source_types,
        "sourceTypesLabel": "、".join(source_types) if source_types else "暂无来源记录",
    }


def _archive_entry_brief(entry):
    authority = _archive_normalize_authority(entry)
    return {
        "id": entry.get("id") or "",
        "title": entry.get("title") or entry.get("id") or "未命名条目",
        "summary": entry.get("text") or "",
        "kind": _archive_entry_kind(entry),
        "confidence": entry.get("confidence") or ARCHIVE_INFERENCE,
        "authority": authority,
        "status": entry.get("status") or authority,
        "sources": entry.get("sources") or [],
    }


def _archive_task_brief(task):
    return {
        "id": task.get("id") or "",
        "title": task.get("title") or "未命名任务",
        "summary": task.get("description") or task.get("blockedReason") or task.get("lastError") or "",
        "status": task.get("executionState") or task.get("status") or ("done" if _archive_task_is_done(task) else "todo"),
        "priority": task.get("priority") or "",
        "assignee": task.get("executorAgentId") or task.get("assignee") or "",
    }


def _archive_artifact_brief(artifact):
    sources = artifact.get("sources") or []
    first_source = sources[0] if sources and isinstance(sources[0], dict) else {}
    source_label = first_source.get("taskTitle") or first_source.get("agentId") or first_source.get("sourceType") or ""
    return {
        "path": artifact.get("path") or "",
        "title": artifact.get("name") or artifact.get("path") or "未命名产物",
        "summary": source_label or artifact.get("path") or "",
        "kind": artifact.get("kind") or artifact.get("extension") or "file",
        "sources": sources[:3],
    }


def _archive_index_highlights(project, entries, artifacts, pending):
    entries = entries or []
    artifacts = artifacts or []
    pending = pending or []
    current_task = _archive_current_task(project)
    decisions = [e for e in entries if _archive_entry_kind(e) in {"decision", "meeting_conclusion", "rule"}]
    risks = [e for e in entries if _archive_entry_kind(e) in {"risk", "blocker", "conflict_reminder"}]
    important = [e for e in entries if _archive_entry_kind(e) in {"important_message", "meeting_conclusion"}]
    pending_items = [p for p in pending if isinstance(p, dict)]
    attention = []
    if pending_items:
        attention.append({"level": "pending", "label": "待确认", "text": f"{len(pending_items)} 个待确认项需要人工判断。"})
    if risks:
        attention.append({"level": "risk", "label": "风险", "text": f"{len(risks)} 条风险/冲突记录会影响后续执行。"})
    if artifacts:
        source_count = len({
            src.get("taskId") or src.get("agentId") or src.get("sourceType") or ""
            for artifact in artifacts
            for src in (artifact.get("sources") or [])
            if isinstance(src, dict)
        })
        attention.append({"level": "artifact", "label": "产物", "text": f"{len(artifacts)} 个产物" + (f"，来自 {source_count} 个来源。" if source_count else "。")})
    if current_task:
        attention.append({"level": "task", "label": "当前任务", "text": current_task.get("title") or "未命名任务"})
    sections = [
        {"key": "current_task", "label": "当前任务", "emptyText": "暂无明确当前任务", "items": [_archive_task_brief(current_task)] if current_task else []},
        {"key": "decisions", "label": "关键决策", "emptyText": "暂无关键决策", "items": [_archive_entry_brief(e) for e in decisions[:3]]},
        {"key": "risks", "label": "风险/冲突", "emptyText": "暂无风险或冲突记录", "items": [_archive_entry_brief(e) for e in risks[:3]]},
        {
            "key": "pending",
            "label": "待确认",
            "emptyText": "暂无待确认项",
            "items": [
                {
                    "id": item.get("id") or "",
                    "title": item.get("title") or "待确认项",
                    "summary": item.get("text") or "",
                    "kind": "pending",
                    "confidence": item.get("confidence") or ARCHIVE_PENDING,
                    "sources": item.get("sources") or [],
                }
                for item in pending_items[:3]
            ],
        },
        {"key": "artifacts", "label": "关键产物", "emptyText": "暂无关联产物", "items": [_archive_artifact_brief(a) for a in artifacts[:4]]},
        {"key": "important", "label": "重要消息/会议", "emptyText": "暂无重要消息或会议结论", "items": [_archive_entry_brief(e) for e in important[:3]]},
    ]
    return {
        "attention": attention[:4],
        "sections": sections,
        "footer": "这些索引由项目任务、产物、档案条目和待确认项实时派生；完整内容仍在下方上下文目录和产物浏览中查看。",
    }


def _archive_relevant_entries(entries, limit=8):
    priority = {
        ARCHIVE_CONFIRMED: 0,
        ARCHIVE_PENDING: 1,
        ARCHIVE_INFERENCE: 2,
    }
    items = list(entries or [])
    items.sort(key=lambda e: (priority.get(e.get("confidence"), 3), 1 if e.get("stale") else 0, e.get("updatedAt") or ""), reverse=False)
    return items[:limit]


def _archive_context_item(entry):
    authority = _archive_normalize_authority(entry)
    return {
        "id": entry.get("id"),
        "kind": _archive_entry_kind(entry),
        "title": entry.get("title") or entry.get("id") or "",
        "text": entry.get("text") or "",
        "confidence": entry.get("confidence") or ARCHIVE_INFERENCE,
        "authority": authority,
        "status": entry.get("status") or authority,
        "trustLevel": _archive_context_trust_level(authority),
        "stale": bool(entry.get("stale")),
        "staleReason": entry.get("staleReason") or "",
        "replacedBy": entry.get("replacedBy") or entry.get("supersededBy") or "",
        "replaces": entry.get("replaces") or "",
        "sourceComparison": entry.get("sourceComparison") or {},
        "pending": authority in {ARCHIVE_AUTH_PENDING_HUMAN, ARCHIVE_AUTH_DEFERRED} or entry.get("confidence") == ARCHIVE_PENDING or bool(entry.get("pendingConfirmationId")),
        "sources": entry.get("sources") or [],
    }


def _archive_context_trust_level(authority):
    if authority == ARCHIVE_AUTH_HUMAN:
        return "highest"
    if authority in {ARCHIVE_AUTH_SYSTEM, ARCHIVE_AUTH_SOURCE}:
        return "objective"
    if authority == ARCHIVE_AUTH_MANAGER:
        return "source_backed"
    if authority in {ARCHIVE_AUTH_PENDING_HUMAN, ARCHIVE_AUTH_DEFERRED}:
        return "unconfirmed"
    if authority == ARCHIVE_AUTH_REJECTED:
        return "rejected"
    return "inference"


def _archive_project_characteristics(project, entries, artifacts):
    description = str(project.get("description") or "").strip()
    background = description or f"项目名称：{project.get('title') or '未命名项目'}。业务背景未记录。"
    decisions = [e for e in entries or [] if _archive_entry_kind(e) in {"decision", "meeting_conclusion", "rule"}]
    risks = [e for e in entries or [] if _archive_entry_kind(e) in {"risk", "blocker", "conflict_reminder"}]
    artifact_names = [a.get("name") or a.get("path") for a in (artifacts or [])[:5]]
    return {
        "businessBackground": background,
        "goals": [description] if description else [],
        "confirmedRules": [e.get("text", "") for e in decisions if _archive_normalize_authority(e) == ARCHIVE_AUTH_HUMAN][:5],
        "decisionStyle": "优先依据已确认来源和项目档案；缺失或冲突内容进入待确认。",
        "userPreferences": [],
        "importantHistory": [e.get("text", "") for e in decisions[:5]],
        "risks": [e.get("text", "") for e in risks[:5]],
        "artifacts": [name for name in artifact_names if name],
        "boundary": "以下内容只是项目/任务补充上下文，不改写 AI 的全局身份、安全边界或通用工具规则。",
    }


def _archive_missing_context_reminders(project, entries):
    reminders = []
    if not str(project.get("description") or "").strip():
        reminders.append({"severity": "missing", "message": "项目描述未记录，AI 需要谨慎推断业务目标。", "proactive": False})
    if not any(_archive_entry_kind(e) == "rule" for e in entries or []):
        reminders.append({"severity": "missing", "message": "暂无已确认长期规则，执行时不要把推断当作规则。", "proactive": False})
    if any(e.get("stale") for e in entries or []):
        reminders.append({"severity": "stale", "message": "档案中存在 stale 条目，使用前需要确认是否仍有效。", "proactive": False})
    return reminders


def _archive_severe_conflict_reminders(entries, pending):
    reminders = []
    for item in pending or []:
        impact = str(item.get("impact") or "").lower()
        if impact in {"risk", "state", "project_status", "task", "task_conclusion", "risk_judgment"}:
            reminders.append({
                "severity": "severe_conflict",
                "message": item.get("text") or item.get("title") or "存在高影响待确认内容。",
                "proactive": True,
                "sources": item.get("sources") or [],
            })
    for entry in entries or []:
        if _archive_entry_kind(entry) == "conflict_reminder":
            reminders.append({
                "severity": "severe_conflict",
                "message": entry.get("text") or "存在冲突提醒。",
                "proactive": True,
                "sources": entry.get("sources") or [],
            })
    return reminders[:8]


def _archive_build_context_package(project, record=None, task=None, artifacts=None):
    record = record or _archive_room_derive_project(project)
    entries = record.get("entries") if isinstance(record.get("entries"), list) else []
    artifacts = artifacts if isinstance(artifacts, list) else []
    pending = record.get("pendingConfirmations") if isinstance(record.get("pendingConfirmations"), list) else []
    active_entries = [e for e in entries if _archive_normalize_authority(e) != ARCHIVE_AUTH_REJECTED and not e.get("stale")]
    relevant = [_archive_context_item(e) for e in _archive_relevant_entries(active_entries)]
    task_info = {}
    if isinstance(task, dict):
        task_info = {
            "id": task.get("id"),
            "title": task.get("title") or "",
            "description": task.get("description") or "",
            "status": task.get("status") or task.get("executionState") or "",
            "sources": [{"type": "task", "id": task.get("id"), "title": task.get("title", "")}],
        }
    characteristics = _archive_project_characteristics(project, entries, artifacts)
    reminders = _archive_missing_context_reminders(project, entries) + _archive_severe_conflict_reminders(entries, pending)
    conclusions = []
    if task_info:
        conclusions.append(f"当前任务：{task_info.get('title') or '未命名任务'}。")
    conclusions.extend([
        f"项目：{record.get('title') or project.get('title') or '未命名项目'}。",
        f"状态：{record.get('status') or project.get('status') or 'active'}；进度：{(record.get('metrics') or {}).get('taskDone', 0)} / {(record.get('metrics') or {}).get('taskCount', 0)} 个任务完成。",
    ])
    if project.get("description"):
        conclusions.append(f"业务背景：{project.get('description')}")
    if reminders:
        conclusions.append(f"上下文提醒：{reminders[0].get('message')}")
    return {
        "projectId": project.get("id"),
        "taskId": task_info.get("id") if task_info else "",
        "mode": "task" if task_info else "project",
        "conclusions": conclusions,
        "task": task_info,
        "projectCharacteristics": characteristics,
        "items": relevant,
        "authorityLegend": {
            ARCHIVE_AUTH_HUMAN: "Highest-trust human-confirmed guidance.",
            ARCHIVE_AUTH_SYSTEM: "Trusted objective VO system state.",
            ARCHIVE_AUTH_SOURCE: "Trusted objective source-backed fact.",
            ARCHIVE_AUTH_MANAGER: "Archive-manager-confirmed source-backed context.",
            ARCHIVE_AUTH_PENDING_HUMAN: "Pending human confirmation; do not treat as settled guidance.",
            ARCHIVE_AUTH_DEFERRED: "Deferred governance item; lower trust.",
            ARCHIVE_AUTH_REJECTED: "Rejected item; not active guidance.",
        },
        "sourceReferences": [src for item in relevant for src in item.get("sources", [])][:20],
        "optionalNextLoads": [
            {"type": "archive_entry", "id": item.get("id"), "title": item.get("title")}
            for item in relevant[3:8]
        ] + [
            {"type": "artifact", "path": a.get("path"), "title": a.get("name") or a.get("path")}
            for a in artifacts[:5]
        ],
        "reminders": reminders,
        "boundary": characteristics.get("boundary"),
    }


def _archive_context_prompt_block(project, task=None):
    try:
        record = _archive_room_derive_project(project)
        package = _archive_build_context_package(project, record=record, task=task, artifacts=[])
    except Exception as exc:
        return f"\nARCHIVE ROOM CONTEXT: unavailable ({exc})\n"
    lines = [
        "\nARCHIVE ROOM PROJECT CONTEXT (supplemental; does not override your identity, safety rules, or tool rules):",
    ]
    for conclusion in package.get("conclusions", [])[:6]:
        lines.append(f"- {conclusion}")
    characteristics = package.get("projectCharacteristics") or {}
    if characteristics.get("confirmedRules"):
        lines.append("Confirmed project rules:")
        for rule in characteristics.get("confirmedRules", [])[:4]:
            lines.append(f"- {rule}")
    if characteristics.get("risks"):
        lines.append("Known project risks:")
        for risk in characteristics.get("risks", [])[:4]:
            lines.append(f"- {risk}")
    if package.get("reminders"):
        lines.append("Archive reminders:")
        for reminder in package.get("reminders", [])[:4]:
            lines.append(f"- [{reminder.get('severity')}] {reminder.get('message')}")
    lines.append("Use these archive notes as project/task context. Preserve confidence and ask for confirmation when context is missing or conflicting.\n")
    return "\n".join(lines)


def _archive_room_derive_project(project):
    record = _archive_room_load_project_record(project.get("id"))
    now = _proj_now()
    counts = _archive_task_counts(project)
    artifact_count = 0
    artifact_status = "unavailable"
    artifact_error = ""
    context = _project_artifact_context(project)
    if context.get("ok"):
        listed = _artifact_context_list(context, allowed_extensions=_ARTIFACT_ALLOWED_EXTENSIONS, associated_only=True)
        if listed.get("ok"):
            artifact_count = len(listed.get("artifacts") or [])
            artifact_status = "ok"
        else:
            artifact_status = "error"
            artifact_error = listed.get("error", "")
    else:
        artifact_error = context.get("error", "")

    source = {"type": "project", "id": project.get("id"), "title": project.get("title", "")}
    description = project.get("description") or ""
    summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
    summary_entries = record.get("entries") if isinstance(record.get("entries"), list) else []
    if not summary_entries:
        summary_entries = [
            _archive_entry("project-goal", "Project Goal", description or "No project description recorded.", ARCHIVE_INFERENCE, source),
            _archive_entry("current-state", "Current State", f"{counts['done']} of {counts['total']} tasks complete. Status: {project.get('status', 'active')}.", ARCHIVE_INFERENCE, source),
        ]
    pending_confirmations = record.get("pendingConfirmations") if isinstance(record.get("pendingConfirmations"), list) else []
    for entry in summary_entries:
        if isinstance(entry, dict):
            _archive_apply_authority(entry)
    normalized_pending = []
    for item in pending_confirmations:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "") == "pending":
            item["status"] = ARCHIVE_AUTH_PENDING_HUMAN
        item["authority"] = _archive_normalize_authority(item, ARCHIVE_AUTH_PENDING_HUMAN)
        item.setdefault("confidence", ARCHIVE_PENDING)
        if item["authority"] in {ARCHIVE_AUTH_PENDING_HUMAN, ARCHIVE_AUTH_DEFERRED}:
            normalized_pending.append(item)
    pending_confirmations = _archive_sort_pending_confirmations(normalized_pending)
    active_pending_count = len([p for p in pending_confirmations if _archive_normalize_authority(p, ARCHIVE_AUTH_PENDING_HUMAN) == ARCHIVE_AUTH_PENDING_HUMAN])
    artifact_preview = []
    if context.get("ok"):
        listed_preview = _artifact_context_list(context, allowed_extensions=_ARTIFACT_ALLOWED_EXTENSIONS, associated_only=True)
        if listed_preview.get("ok"):
            artifact_preview = listed_preview.get("artifacts", [])
    source_types = _archive_source_types(summary_entries, artifact_preview, pending_confirmations)
    archive_introduction = _archive_archive_introduction(project, counts, summary_entries, artifact_preview, pending_confirmations)
    project_basic_info = _archive_project_basic_info(project, counts, artifact_count, active_pending_count, source_types)
    index_highlights = _archive_index_highlights(project, summary_entries, artifact_preview, pending_confirmations)
    content_map = _archive_content_presence(project, summary_entries, artifact_preview, pending_confirmations)
    usage_map = _archive_usage_map(project, counts, artifact_count, len(pending_confirmations))
    onboarding = record.get("onboardingPackage") if isinstance(record.get("onboardingPackage"), dict) else {}
    context_package = _archive_build_context_package(project, record={**record, "entries": summary_entries, "pendingConfirmations": pending_confirmations, "metrics": {
        "taskCount": counts["total"],
        "taskDone": counts["done"],
        "completionRate": counts["completionRate"],
        "riskCount": counts["riskCount"],
        "pendingConfirmationCount": active_pending_count,
        "activeAi": counts["activeAi"],
        "artifactCount": artifact_count,
    }, "title": project.get("title", ""), "status": project.get("status", "active")}, task=_archive_current_task(project), artifacts=artifact_preview)
    onboarding = {
        **onboarding,
        "title": f"AI 入场包：{project.get('title', 'project')}",
        "confidence": onboarding.get("confidence") or ARCHIVE_INFERENCE,
        "contextPackage": context_package,
        "copyText": "\n".join([
            f"项目：{project.get('title', '') or '未命名项目'}",
            f"状态：{project.get('status', 'active')}；进度：{counts['done']} / {counts['total']} 个任务完成",
            f"项目目标/背景：{description or '未记录，需要谨慎推断。'}",
            f"当前任务：{(_archive_current_task(project) or {}).get('title') or '暂无明确当前任务'}",
            f"风险/阻塞：{counts['riskCount']}",
            f"待确认：{active_pending_count}",
            f"产物：{artifact_count}",
            "项目特征：",
            f"- 决策风格：{context_package.get('projectCharacteristics', {}).get('decisionStyle', '')}",
            f"- 上下文边界：{context_package.get('boundary', '')}",
            "相关结论：",
            *[f"- {item}" for item in context_package.get("conclusions", [])[:6]],
            "可继续加载：",
            *[f"- {item.get('type')}: {item.get('title') or item.get('id') or item.get('path')}" for item in context_package.get("optionalNextLoads", [])[:8]],
        ]),
    }
    derived = {
        "projectId": project.get("id"),
        "title": project.get("title", ""),
        "description": description,
        "status": project.get("status", "active"),
        "updatedAt": project.get("updatedAt") or project.get("createdAt") or now,
        "archiveUpdatedAt": record.get("archiveUpdatedAt") or now,
        "metrics": {
            "taskCount": counts["total"],
            "taskDone": counts["done"],
            "completionRate": counts["completionRate"],
            "riskCount": counts["riskCount"],
            "pendingConfirmationCount": active_pending_count,
            "activeAi": counts["activeAi"],
            "artifactCount": artifact_count,
        },
        "artifactStatus": artifact_status,
        "artifactError": artifact_error,
        "archiveManager": _archive_manager_public_state(ensure=False),
        "archiveMaintenance": _archive_project_maintenance_meta(project, record),
        "inspections": record.get("inspections") if isinstance(record.get("inspections"), dict) else {},
        "pendingConfirmations": pending_confirmations,
        "processedGovernance": record.get("processedGovernance") if isinstance(record.get("processedGovernance"), list) else [],
        "automaticGovernanceNotices": (record.get("automaticGovernanceNotices") if isinstance(record.get("automaticGovernanceNotices"), list) else [])[-5:],
        "processedEventCount": len(record.get("processedEvents") or {}) if isinstance(record.get("processedEvents"), dict) else 0,
        "archiveIntroduction": archive_introduction,
        "projectBasicInfo": project_basic_info,
        "archiveIndexHighlights": index_highlights,
        "archiveContentMap": content_map,
        "archiveUsageMap": usage_map,
        "contextPackage": context_package,
        "summary": {
            "goal": summary.get("goal") or description,
            "currentState": summary.get("currentState") or f"{counts['done']} of {counts['total']} tasks complete.",
            "nextStep": summary.get("nextStep") or "",
        },
        "entries": summary_entries,
        "onboardingPackage": onboarding,
    }
    record.update(derived)
    _archive_room_save_project_record(project.get("id"), record)
    return record


def _archive_room_project_summary(record):
    metrics = record.get("metrics") or {}
    attention = int(metrics.get("riskCount") or 0) * 1000 + int(metrics.get("pendingConfirmationCount") or 0) * 100
    return {
        "id": record.get("projectId"),
        "title": record.get("title", ""),
        "description": record.get("description", ""),
        "status": record.get("status", "active"),
        "updatedAt": record.get("updatedAt", ""),
        "archiveUpdatedAt": record.get("archiveUpdatedAt", ""),
        "metrics": metrics,
        "artifactStatus": record.get("artifactStatus", "unavailable"),
        "artifactError": record.get("artifactError", ""),
        "archiveManager": record.get("archiveManager", {}),
        "archiveMaintenance": record.get("archiveMaintenance", {}),
        "inspections": record.get("inspections", {}),
        "automaticGovernanceNotices": (record.get("automaticGovernanceNotices") if isinstance(record.get("automaticGovernanceNotices"), list) else [])[-5:],
        "pendingConfirmationCount": len(record.get("pendingConfirmations") or []) if isinstance(record.get("pendingConfirmations"), list) else 0,
        "attentionScore": attention,
    }


def _handle_archive_room_overview():
    data = _load_projects()
    manager = _archive_manager_public_state(ensure=True)
    projects = []
    for project in data.get("projects", []) if isinstance(data, dict) else []:
        if not isinstance(project, dict) or project.get("template"):
            continue
        projects.append(_archive_room_project_summary(_archive_room_derive_project(project)))
    projects.sort(key=lambda p: (p.get("attentionScore") or 0, p.get("updatedAt") or ""), reverse=True)
    return {
        "ok": True,
        "archiveManager": manager,
        "projects": projects,
    }


def _handle_archive_room_audit_count():
    data = _load_projects()
    projects_data = [p for p in (data.get("projects", []) if isinstance(data, dict) else []) if isinstance(p, dict) and not p.get("template") and p.get("id")]
    try:
        state = _archive_manager_create_if_missing()
    except Exception as exc:
        state = _archive_manager_load_state()
        state["status"] = "error"
        state["label"] = "档案管理员不可用"
        state["lastError"] = str(exc)
        _archive_manager_append_activity(state, "audit_archive_count", "error", "档案数目检查失败", error=str(exc))
        try:
            _archive_manager_save_state(state)
        except Exception:
            pass
        return {"error": str(exc), "archiveManager": _archive_manager_public_state(ensure=False), "_status": 409}

    now = _proj_now()
    existing_ids = []
    missing_projects = []
    for project in projects_data:
        project_id = project.get("id")
        record_path = _archive_room_project_file(project_id)
        record = _archive_room_load_project_record(project_id)
        if os.path.exists(record_path) and record.get("projectId") == project_id:
            existing_ids.append(project_id)
        else:
            missing_projects.append(project)

    state["status"] = "working"
    state["label"] = "检查中"
    _archive_manager_append_activity(
        state,
        "audit_archive_count",
        "running",
        f"开始检查档案数目：项目 {len(projects_data)} 个，已有档案 {len(existing_ids)} 份",
    )
    _archive_manager_save_state(state)

    repaired = []
    for project in missing_projects:
        record = _archive_room_derive_project(project)
        record["archiveUpdatedAt"] = record.get("archiveUpdatedAt") or now
        record["managerMaintainedAt"] = now
        item = {
            "id": _proj_uuid(),
            "at": now,
            "managerAgentId": state.get("agentId") or ARCHIVE_MANAGER_AGENT_ID,
            "status": "ok",
            "eventType": "archive_count_repair",
            "triggerType": "audit_archive_count",
            "projectId": project.get("id"),
            "summary": "档案数目检查发现该项目缺少档案，已创建基础项目档案。",
            "output": {
                "status": "ok",
                "projectId": project.get("id"),
                "summary": "已创建基础项目档案。",
            },
        }
        _archive_append_project_maintenance(record, item)
        _archive_room_save_project_record(project.get("id"), record)
        repaired.append({"projectId": project.get("id"), "title": project.get("title", "")})

    status = "ok"
    message = f"档案数目检查完成：项目 {len(projects_data)} 个，已有档案 {len(existing_ids)} 份，补齐 {len(repaired)} 份。"
    state["status"] = "paused" if state.get("paused") else "idle"
    state["label"] = "已暂停" if state.get("paused") else "已接入"
    state["lastError"] = ""
    _archive_manager_append_activity(state, "audit_archive_count", status, message)
    _archive_manager_save_state(state)

    overview = _handle_archive_room_overview()
    return {
        "ok": True,
        "audit": {
            "projectCount": len(projects_data),
            "archiveCountBefore": len(existing_ids),
            "missingCount": len(missing_projects),
            "repairedCount": len(repaired),
            "repaired": repaired,
            "checkedAt": now,
            "message": message,
        },
        "archiveManager": _archive_manager_public_state(ensure=False),
        "projects": overview.get("projects", []),
    }


def _handle_archive_room_project(project_id):
    data = _load_projects()
    project = next((p for p in data.get("projects", []) if isinstance(p, dict) and p.get("id") == project_id), None)
    if not project:
        return {"error": "Project not found", "_status": 404}
    record = _archive_room_derive_project(project)
    artifacts = []
    context = _project_artifact_context(project)
    if context.get("ok"):
        listed = _artifact_context_list(context, allowed_extensions=_ARTIFACT_ALLOWED_EXTENSIONS, associated_only=True)
        if listed.get("ok"):
            artifacts = listed.get("artifacts", [])
    record["artifacts"] = artifacts
    return {"ok": True, "project": record}


def _handle_archive_room_context(project_id, query_string=""):
    data = _load_projects()
    project = next((p for p in data.get("projects", []) if isinstance(p, dict) and p.get("id") == project_id), None)
    if not project:
        return {"error": "Project not found", "_status": 404}
    params = urllib.parse.parse_qs(query_string or "")
    task_id = (params.get("taskId") or params.get("task") or [""])[0]
    task = None
    if task_id:
        task = next((t for t in _archive_tasks(project) if str(t.get("id") or "") == task_id), None)
        if not task:
            return {"error": "Task not found", "_status": 404}
    else:
        task = _archive_current_task(project)
    record = _archive_room_derive_project(project)
    artifacts = []
    context = _project_artifact_context(project)
    if context.get("ok"):
        listed = _artifact_context_list(context, allowed_extensions=_ARTIFACT_ALLOWED_EXTENSIONS, associated_only=True)
        if listed.get("ok"):
            artifacts = listed.get("artifacts", [])
    package = _archive_build_context_package(project, record=record, task=task, artifacts=artifacts)
    return {"ok": True, "projectId": project_id, "taskId": (task or {}).get("id") or "", "context": package}


def _handle_archive_governance_action(project_id, item_id, body):
    action = str((body or {}).get("action") or "").strip().lower()
    if action not in ARCHIVE_GOVERNANCE_ACTIONS:
        return {"error": "Unsupported governance action", "_status": 400}
    data = _load_projects()
    project = next((p for p in data.get("projects", []) if isinstance(p, dict) and p.get("id") == project_id), None)
    if not project:
        return {"error": "Project not found", "_status": 404}
    record = _archive_room_derive_project(project)
    pending = record.get("pendingConfirmations") if isinstance(record.get("pendingConfirmations"), list) else []
    idx = next((i for i, item in enumerate(pending) if isinstance(item, dict) and str(item.get("id") or "") == item_id), -1)
    if idx < 0:
        return {"error": "Pending confirmation not found", "_status": 404}
    item = pending[idx]
    now = _proj_now()
    actor = str((body or {}).get("actor") or "human").strip() or "human"
    reason = str((body or {}).get("reason") or "").strip()
    edited_text = str((body or {}).get("text") or (body or {}).get("editedText") or "").strip()
    original = json.loads(json.dumps(item, ensure_ascii=False))

    if action == "defer":
        item["status"] = ARCHIVE_AUTH_DEFERRED
        item["authority"] = ARCHIVE_AUTH_DEFERRED
        item["deferredAt"] = now
        item["deferredBy"] = actor
        if reason:
            item["deferReason"] = reason
        item["updatedAt"] = now
        pending[idx] = item
        record["pendingConfirmations"] = _archive_sort_pending_confirmations(pending)
        history_status = ARCHIVE_AUTH_DEFERRED
    else:
        pending.pop(idx)
        record["pendingConfirmations"] = _archive_sort_pending_confirmations(pending)
        history_status = ARCHIVE_AUTH_REJECTED if action == "reject" else ARCHIVE_AUTH_HUMAN

    confirmed_entry = None
    linked_entry_id = item.get("entryId") or ""
    if action in {"confirm", "edit_confirm"}:
        confirmed_text = edited_text if action == "edit_confirm" and edited_text else item.get("text", "")
        entry_id = f"human-confirmed-{item_id.replace('pending-', '')}"
        linked_entry_id = linked_entry_id or f"{item.get('kind') or 'event'}-{item_id.replace('pending-', '')}"
        source = (item.get("sources") or [None])[0]
        confirmed_entry = _archive_entry(entry_id, item.get("title") or "Human confirmed archive item", confirmed_text, ARCHIVE_CONFIRMED, source, stale=False)
        confirmed_entry.update({
            "kind": item.get("kind") or "human_confirmed",
            "authority": ARCHIVE_AUTH_HUMAN,
            "status": ARCHIVE_AUTH_HUMAN,
            "confirmedAt": now,
            "confirmedBy": actor,
            "confirmationReason": reason,
            "originalSuggestion": original,
            "updatedAt": now,
        })
        _archive_upsert_entry(record, confirmed_entry)
    elif action == "reject":
        linked_entry_id = linked_entry_id or f"{item.get('kind') or 'event'}-{item_id.replace('pending-', '')}"
        item["status"] = ARCHIVE_AUTH_REJECTED
        item["authority"] = ARCHIVE_AUTH_REJECTED
        item["rejectedAt"] = now
        item["rejectedBy"] = actor
        if reason:
            item["rejectReason"] = reason
    if action in {"confirm", "edit_confirm", "reject"} and linked_entry_id:
        for entry in record.get("entries") or []:
            if isinstance(entry, dict) and entry.get("id") == linked_entry_id:
                if action == "reject":
                    _archive_apply_authority(entry, ARCHIVE_AUTH_REJECTED)
                    entry["rejectedAt"] = now
                    entry["rejectedBy"] = actor
                    entry["rejectReason"] = reason
                else:
                    entry["supersededBy"] = (confirmed_entry or {}).get("id", "")
                    entry["status"] = "superseded_by_human_confirmed"
                entry["updatedAt"] = now
                break

    history_item = {
        "id": f"governance-{_proj_uuid()}",
        "pendingId": item_id,
        "action": action,
        "status": history_status,
        "actor": actor,
        "at": now,
        "reason": reason,
        "title": item.get("title") or "",
        "text": edited_text if action == "edit_confirm" and edited_text else item.get("text", ""),
        "originalSuggestion": original,
        "confirmedEntryId": (confirmed_entry or {}).get("id", ""),
        "sources": item.get("sources") or [],
    }
    _archive_add_governance_history(record, history_item)
    record["archiveUpdatedAt"] = now
    _archive_room_save_project_record(project_id, record)
    updated = _archive_room_derive_project(project)
    return {"ok": True, "action": action, "item": history_item, "project": updated}


_wrap_exports()
_hydrate()
