"""Project workflow service split from server.py.

The functions in this module intentionally keep their historical names because
server.py and project execution flows still expose them as compatibility entry
points. `_hydrate()` mirrors server globals so this mechanical split can stay
behavior-compatible while the service boundary firms up.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_DIR = os.environ.get("VO_STATUS_DIR") or os.path.join(APP_DIR, "status")

__all__ = [
    'WORKFLOW_STATE_FILE',
    'TASK_FILES_DIR',
    '_WORKFLOW_LOCK',
    '_WORKFLOW_STATE',
    '_wf_find_column',
    '_wf_get_backlog_col',
    '_wf_get_inprogress_col',
    '_wf_get_review_col',
    '_wf_get_done_col',
    '_wf_next_backlog_task',
    '_wf_get_active_task',
    '_wf_move_task',
    '_wf_update_task_field',
    '_wf_sync_project_workflow_meta',
    '_wf_write_task_file',
    '_wf_read_task_file',
    '_wf_safe_session_part',
    '_wf_task_session_key',
    '_wf_browser_exec_action_desc',
    '_wf_extract_session_activity',
    '_wf_format_activity_summary',
    '_wf_activity_tool_flags',
    '_wf_abort_task_session',
    '_wf_delete_session_via_gateway',
    '_wf_cleanup_task_sessions',
    '_wf_call_agent',
    '_extract_openclaw_text',
    '_wf_call_agent_ws',
    '_wf_call_agent_http',
    '_wf_call_agent_cli',
    '_wf_build_project_context',
    '_wf_build_task_prompt',
    '_wf_task_needs_visual_review',
    '_wf_build_review_prompt',
    '_wf_build_rework_prompt',
    '_wf_review_had_structured_match',
    '_wf_parse_review_response',
    '_wf_unfinished_checklist_items',
    '_wf_run_pipeline',
    '_wf_run_pipeline_inner',
    '_wf_persist_state',
    '_wf_update_shared_project_work',
    '_wf_load_persisted_state',
    '_wf_clear_persisted_state',
    '_codex_reasoning_events_to_chat_messages',
    '_wf_get_task_session_messages',
    '_wf_is_task_session_active',
    '_handle_workflow_chat',
    '_handle_workflow_start',
    '_handle_workflow_stop',
    '_handle_workflow_auto_mode',
    '_handle_workflow_status',
    '_wf_auto_resume_on_startup',
]


def _server_module():
    return sys.modules.get("server") or sys.modules.get("__main__")


def _hydrate():
    server = _server_module()
    if server is None or server is sys.modules.get(__name__):
        return
    exported = set(__all__)
    for key, value in vars(server).items():
        if key.startswith("__") or key in ('_server_module', '_hydrate', '_wrap_exports'):
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


def _project_execution_launch_thread(target, args=()):
    from server_services import projects
    projects._hydrate()
    return projects._project_execution_launch_thread(target, args)


# ─── PROJECT WORKFLOW ENGINE ──────────────────────────────────────────────────
# Background thread-based workflow: Backlog → In Progress → Review → Done
# Uses `openclaw agent` CLI or Gateway HTTP API to dispatch tasks and reviews to agents.
##############################################################################


# Global workflow state: { projectId: { "active": bool, "autoMode": bool, "currentTaskId": str, "phase": str, "thread": Thread, "stopFlag": Event } }
_WORKFLOW_STATE = {}
_WORKFLOW_LOCK = threading.Lock()

# Legacy task markdown files directory (kept for backward compatibility if present)
TASK_FILES_DIR = os.path.join(STATUS_DIR, "project-tasks")

def _wf_find_column(project, title_lower):
    """Find a column by title (case-insensitive). Tries exact match first, then contains."""
    cols = project.get("columns", [])
    # Exact match first
    for col in cols:
        if col.get("title", "").lower() == title_lower:
            return col
    # Fallback: column title contains the keyword (e.g. "Code Review" matches "review")
    for col in cols:
        if title_lower in col.get("title", "").lower():
            return col
    return None

def _wf_get_backlog_col(project):
    """Find the backlog/source column. Tries 'backlog' first, then common alternatives."""
    col = _wf_find_column(project, "backlog")
    if col:
        return col
    # Try common alternative names for the first/source column
    for alt in ("to do", "todo", "ideas", "reported"):
        col = _wf_find_column(project, alt)
        if col:
            return col
    # Last resort: use the first column by order
    cols = project.get("columns", [])
    if cols:
        sorted_cols = sorted(cols, key=lambda c: c.get("order", 0))
        return sorted_cols[0]
    return None

def _wf_get_inprogress_col(project):
    """Find the in-progress/work column. Tries common names, falls back to second column."""
    for name in ("in progress", "in_progress", "sprint", "creating", "writing", "working"):
        col = _wf_find_column(project, name)
        if col:
            return col
    # Fallback: second column by order (between backlog and review)
    cols = sorted(project.get("columns", []), key=lambda c: c.get("order", 0))
    if len(cols) >= 3:
        return cols[1]
    return None

def _wf_get_review_col(project):
    """Find the review column. Tries common names, falls back to second-to-last column."""
    for name in ("review", "code review", "qa", "editing", "testing"):
        col = _wf_find_column(project, name)
        if col:
            return col
    # Fallback: second-to-last column by order
    cols = sorted(project.get("columns", []), key=lambda c: c.get("order", 0))
    if len(cols) >= 3:
        return cols[-2]
    return None

def _wf_get_done_col(project):
    """Find the done/final column. Tries 'done' first, then common alternatives."""
    col = _wf_find_column(project, "done")
    if col:
        return col
    for alt in ("completed", "verified", "published", "fixed", "closed"):
        col = _wf_find_column(project, alt)
        if col:
            return col
    # Last resort: use the last column by order
    cols = project.get("columns", [])
    if cols:
        sorted_cols = sorted(cols, key=lambda c: c.get("order", 0))
        return sorted_cols[-1]
    return None

def _wf_next_backlog_task(project):
    """Get highest priority task from backlog column."""
    backlog = _wf_get_backlog_col(project)
    if not backlog:
        return None
    tasks = [t for t in project.get("tasks", []) if t.get("columnId") == backlog["id"]]
    if not tasks:
        return None
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    tasks.sort(key=lambda t: (priority_order.get(t.get("priority", "medium"), 2), t.get("order", 0)))
    return tasks[0]


def _wf_get_active_task(project):
    """Find a task currently in-progress or in review that still needs work.

    This prevents backlog tasks from jumping ahead of tasks that were sent
    back for rework after a failed review cycle.  Only assigned tasks are
    considered (unassigned ones can't be worked by the pipeline).
    """
    inprogress_col = _wf_get_inprogress_col(project)
    review_col = _wf_get_review_col(project)
    active_col_ids = set()
    if inprogress_col:
        active_col_ids.add(inprogress_col["id"])
    if review_col:
        active_col_ids.add(review_col["id"])
    if not active_col_ids:
        return None

    for t in project.get("tasks", []):
        if t.get("columnId") in active_col_ids and t.get("assignee"):
            return t
    return None

def _wf_move_task(project_id, task_id, target_col_id, by="workflow"):
    """Move a task to a target column and persist."""
    data = _load_projects()
    p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if not p:
        return None
    task = next((t for t in p["tasks"] if t["id"] == task_id), None)
    if not task:
        return None
    old_col = next((c["title"] for c in p.get("columns", []) if c["id"] == task.get("columnId")), "?")
    new_col = next((c["title"] for c in p.get("columns", []) if c["id"] == target_col_id), "?")
    task["columnId"] = target_col_id
    # Max order in target column
    col_tasks = [t for t in p["tasks"] if t.get("columnId") == target_col_id and t["id"] != task_id]
    task["order"] = max((t.get("order", 0) for t in col_tasks), default=-1) + 1
    task["updatedAt"] = _proj_now()
    p["updatedAt"] = _proj_now()
    # Handle done column — match common "final" column names
    done_cols = [c["id"] for c in p.get("columns", []) if c.get("title", "").lower() in ("done", "completed", "verified", "published", "fixed", "closed")]
    if target_col_id in done_cols and not task.get("completedAt"):
        task["completedAt"] = _proj_now()
        # Award points
        assignee = task.get("assignee")
        if assignee:
            pts = SCORE_TASK_COMPLETED
            pri = task.get("priority", "medium")
            if pri == "critical": pts += SCORE_CRITICAL_BONUS
            elif pri == "high": pts += SCORE_HIGH_BONUS
            elif pri == "medium": pts += SCORE_MEDIUM_BONUS
            chk = task.get("checklist", [])
            done_items = sum(1 for c in chk if c.get("done"))
            pts += done_items * SCORE_CHECKLIST_BONUS
            _award_points(assignee, pts, f"Completed: {task.get('title','')}")
    elif target_col_id not in done_cols:
        task["completedAt"] = None
    _log_activity(p, "task_moved", by, f"Moved '{task['title']}' from {old_col} to {new_col}", task_id)
    _save_projects(data)
    return task

def _wf_update_task_field(project_id, task_id, field, value):
    """Update a single field on a task and persist."""
    data = _load_projects()
    p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if not p:
        return None
    task = next((t for t in p["tasks"] if t["id"] == task_id), None)
    if not task:
        return None
    task[field] = value
    task["updatedAt"] = _proj_now()
    p["updatedAt"] = _proj_now()
    _save_projects(data)
    return task


def _wf_sync_project_workflow_meta(project_id, *, active=None, phase=None, current_task_id=None, active_agent=None):
    """Mirror live workflow metadata onto the project payload for UI consumers."""
    data = _load_projects()
    p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if not p:
        return None
    if active is not None:
        p["workflowActive"] = active
    if phase is not None:
        p["workflowPhase"] = phase
    if current_task_id is not None or current_task_id is None:
        p["activeTaskId"] = current_task_id
    if active_agent is not None or active_agent is None:
        p["activeAgent"] = active_agent
    p["updatedAt"] = _proj_now()
    _save_projects(data)
    return p

def _wf_write_task_file(project_id, task, status_text, review_results=None, work_log_entry=None):
    """Update canonical markdown-backed task state, preserving compatibility with workflow logging."""
    data = _load_projects()
    p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if not p:
        return
    live_task = next((t for t in p.get("tasks", []) if t.get("id") == task.get("id")), None)
    if not live_task:
        return
    if review_results is not None:
        live_task["reviewCheck"] = review_results
    if work_log_entry:
        comments = live_task.setdefault("comments", [])
        comments.append({
            "id": _proj_uuid(),
            "author": "workflow",
            "text": work_log_entry,
            "createdAt": _proj_now(),
        })
        if len(comments) > 200:
            live_task["comments"] = comments[-200:]
    live_task["updatedAt"] = _proj_now()
    p["updatedAt"] = _proj_now()
    _save_projects(data)


def _wf_read_task_file(project_id, task_id):
    """Read canonical task content from the markdown-backed store and render it into prompt-friendly markdown."""
    data = _load_projects()
    p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if not p:
        return None
    task = next((t for t in p.get("tasks", []) if t.get("id") == task_id), None)
    if not task:
        return None
    lines = [
        f"# Task: {task.get('title', 'Untitled')}",
        f"**Assignee:** {task.get('assignee', 'unassigned')} | **Priority:** {task.get('priority', 'medium')}",
        "",
        "## Description",
        task.get("description", "_No description_") or "_No description_",
        "",
        "## Checklist",
    ]
    checklist = task.get("checklist", [])
    if checklist:
        review_map = {item.get('text', ''): item.get('status', '') for item in (task.get('reviewCheck') or [])}
        for item in checklist:
            check = "x" if item.get("done") else " "
            suffix = f" — {review_map.get(item.get('text', ''), '')}" if review_map.get(item.get('text', '')) else ""
            lines.append(f"- [{check}] {item.get('text', '')}{suffix}")
    else:
        lines.append("- No checklist items")
    comments = task.get("comments", [])
    if comments:
        lines.extend(["", "## Work Log"])
        for comment in comments[-20:]:
            lines.append(f"### {comment.get('createdAt', '')} — {comment.get('author', 'user')}")
            lines.append(comment.get("text", ""))
            lines.append("")
    return "\n".join(lines).strip() + "\n"


# Track workflow sessions for cleanup: { project_id: { task_id: set(session_keys) } }
def _wf_safe_session_part(value, fallback="task", max_len=8):
    text = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip()).strip("-")
    text = (text or fallback)[:max_len].strip("-")
    return text or fallback[:max_len]


def _wf_task_session_key(agent_id, project_id, task_id):
    """Return a stable session key for a workflow task.

    All calls for the same task (work, review, rework) reuse one session.
    This means the agent keeps context across the full task lifecycle,
    prompt caching kicks in, and only ONE session is created per task.
    """
    agent_part = _wf_safe_session_part(agent_id, "agent", max_len=24)
    project_part = _wf_safe_session_part(project_id, "project")
    task_part = _wf_safe_session_part(task_id, "task")
    return f"agent-{agent_part}-openai-wf-{project_part}-{task_part}"


def _wf_browser_exec_action_desc(command):
    """Infer browser verification activity from exec-driven browser automation.

    This keeps workflow review validation compatible with environments where
    visual verification happens through a browser CLI (for example
    `agent-browser ...`) instead of the first-class `browser` tool.
    """
    if not command:
        return None
    cmd = command.strip()
    cmd_lower = cmd.lower()

    browser_markers = (
        "agent-browser ",
        " agent-browser",
        "agent-browser\n",
        "playwright ",
        " npx playwright",
    )
    if not any(marker in cmd_lower for marker in browser_markers):
        return None

    action_map = [
        (" screenshot", "screenshot"),
        (" snapshot", "snapshot"),
        (" open ", "open"),
        (" navigate ", "navigate"),
        (" click ", "click"),
        (" fill ", "fill"),
        (" type ", "type"),
        (" eval ", "eval"),
        (" close", "close"),
        (" wait ", "wait"),
    ]
    action = "browser-cli"
    for needle, label in action_map:
        if needle in cmd_lower:
            action = label
            break

    return f"{action} (exec)"


def _wf_extract_session_activity(agent_id, project_id, task_id):
    if _is_hermes_agent(agent_id):
        agent = _get_hermes_agent(agent_id) or {}
        profile = agent.get("profile") or agent.get("providerAgentId") or "default"
        messages = _load_hermes_history(profile)[-12:]
        return [{"type": "message", "summary": (m.get("text") or "")[:300], "ts": m.get("ts", 0)} for m in messages if m.get("text")]
    if _is_codex_agent(agent_id):
        messages = _load_comm_history(limit=24, conversation_id=task_id)
        return [{"type": "message", "summary": (m.get("text") or "")[:300], "ts": m.get("ts", 0)} for m in messages if m.get("text")]

    """Extract file activity and tool usage from a workflow task's session JSONL.

    Returns a dict with:
      files_read: list of file paths read
      files_edited: list of file paths edited/written
      files_written: list of file paths created/written
      exec_commands: list of commands run
      browser_actions: list of browser actions taken
      tool_call_count: total number of tool calls
    """
    home_path = VO_CONFIG.get("openclaw", {}).get("homePath", os.path.expanduser("~/.openclaw"))
    sessions_dir = os.path.join(home_path, "agents", agent_id, "sessions")
    sessions_json_path = os.path.join(sessions_dir, "sessions.json")
    session_key = _wf_task_session_key(agent_id, project_id, task_id)

    activity = {
        "files_read": [],
        "files_edited": [],
        "files_written": [],
        "exec_commands": [],
        "browser_actions": [],
        "tool_call_count": 0,
    }

    try:
        if not os.path.exists(sessions_json_path):
            return activity
        with open(sessions_json_path, "r") as f:
            sessions_data = json.load(f)
        session_info, _ = _openclaw_get_session_info(sessions_data, agent_id, session_key)
        if not session_info:
            return activity
        session_id = session_info.get("sessionId", "")
        jsonl_path = session_info.get("sessionFile") or (os.path.join(sessions_dir, f"{session_id}.jsonl") if session_id else "")
        if not os.path.exists(jsonl_path):
            return activity

        seen_files_read = set()
        seen_files_edit = set()
        seen_files_write = set()
        seen_browser_actions = set()

        with open(jsonl_path, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = entry.get("message", entry)
                content = msg.get("content", [])
                if not isinstance(content, list):
                    continue
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    if c.get("type") != "toolCall":
                        continue
                    activity["tool_call_count"] += 1
                    name = c.get("name", "")
                    args = c.get("arguments", {})
                    # Extract file path from various param names
                    fpath = args.get("path") or args.get("file") or args.get("filePath") or args.get("file_path") or ""

                    if name.lower() in ("read",):
                        if fpath and fpath not in seen_files_read:
                            seen_files_read.add(fpath)
                            activity["files_read"].append(fpath)
                    elif name.lower() in ("edit",):
                        if fpath and fpath not in seen_files_edit:
                            seen_files_edit.add(fpath)
                            activity["files_edited"].append(fpath)
                    elif name.lower() in ("write",):
                        if fpath and fpath not in seen_files_write:
                            seen_files_write.add(fpath)
                            activity["files_written"].append(fpath)
                    elif name.lower() == "exec":
                        cmd = args.get("command", "")
                        if cmd:
                            activity["exec_commands"].append(cmd[:200])
                            browser_desc = _wf_browser_exec_action_desc(cmd)
                            if browser_desc and browser_desc not in seen_browser_actions:
                                seen_browser_actions.add(browser_desc)
                                activity["browser_actions"].append(browser_desc)
                    elif name.lower() == "browser":
                        action = args.get("action", "")
                        url = args.get("url", "")
                        if action:
                            desc = action
                            if url:
                                desc += f" → {url}"
                            desc = desc[:200]
                            if desc not in seen_browser_actions:
                                seen_browser_actions.add(desc)
                                activity["browser_actions"].append(desc)
    except Exception as e:
        print(f"[WORKFLOW] Activity extraction error: {e}")

    return activity


def _wf_format_activity_summary(activity):
    """Format extracted session activity as markdown for the task file."""
    lines = []

    if isinstance(activity, list):
        if not activity:
            lines.append("No recent activity captured.")
            return "\n".join(lines)
        lines.append(f"**Recent messages:** {len(activity)}")
        for item in activity[:10]:
            if isinstance(item, dict):
                summary = str(item.get("summary") or item.get("text") or "").strip()
                kind = str(item.get("type") or "message")
            else:
                summary = str(item).strip()
                kind = "message"
            if summary:
                lines.append(f"  - {kind}: {summary[:300]}")
        if len(activity) > 10:
            lines.append(f"  - ... and {len(activity) - 10} more")
        return "\n".join(lines)

    if not isinstance(activity, dict):
        lines.append("No structured activity captured.")
        return "\n".join(lines)

    if activity["tool_call_count"] == 0:
        lines.append("⚠️ NO TOOL CALLS DETECTED — agent produced text only, no real changes made.")
        return "\n".join(lines)

    lines.append(f"**Tool calls:** {activity['tool_call_count']}")

    if activity["files_read"]:
        lines.append(f"\n**Files read ({len(activity['files_read'])}):**")
        for f in activity["files_read"]:
            lines.append(f"  - `{f}`")

    if activity["files_edited"]:
        lines.append(f"\n**Files edited ({len(activity['files_edited'])}):**")
        for f in activity["files_edited"]:
            lines.append(f"  - `{f}`")

    if activity["files_written"]:
        lines.append(f"\n**Files created/written ({len(activity['files_written'])}):**")
        for f in activity["files_written"]:
            lines.append(f"  - `{f}`")

    if activity["browser_actions"]:
        lines.append(f"\n**Browser verification ({len(activity['browser_actions'])}):**")
        for b in activity["browser_actions"]:
            lines.append(f"  - {b}")

    if activity["exec_commands"]:
        lines.append(f"\n**Commands run ({len(activity['exec_commands'])}):**")
        for cmd in activity["exec_commands"][:20]:  # cap at 20 to avoid huge logs
            lines.append(f"  - `{cmd}`")
    if len(activity["exec_commands"]) > 20:
        lines.append(f"  - ... and {len(activity['exec_commands']) - 20} more")

    return "\n".join(lines)


def _wf_activity_tool_flags(activity):
    """Return verification flags for activity dicts; message lists have no tools."""
    if isinstance(activity, list):
        has_messages = len(activity) > 0
        return {
            "tool_call_count": len(activity),
            "has_reads": has_messages,
            "has_exec": False,
            "has_browser": False,
        }
    if not isinstance(activity, dict):
        return {
            "tool_call_count": 0,
            "has_reads": False,
            "has_exec": False,
            "has_browser": False,
        }
    return {
        "tool_call_count": int(activity.get("tool_call_count") or 0),
        "has_reads": len(activity.get("files_read") or []) > 0,
        "has_exec": len(activity.get("exec_commands") or []) > 0,
        "has_browser": len(activity.get("browser_actions") or []) > 0,
    }


def _wf_abort_task_session(session_key):
    """Abort a running agent session via gateway chat.abort RPC.

    This immediately kills any in-flight LLM inference for the specific session,
    similar to clicking Stop in the VO chat. Only targets the given session key —
    does not affect the agent's main session or other workflow sessions.
    """
    import asyncio as _asyncio

    async def _do_abort():
        try:
            gw_url = VO_CONFIG["openclaw"]["gatewayUrl"]
            origin = f"http://127.0.0.1:{PORT}"
            token = _get_gateway_token()
            if not token:
                print(f"[WORKFLOW] No gateway token — skipping session abort for {session_key}")
                return False

            import websockets as _ws
            from websockets.asyncio.client import connect as _ws_connect

            async with _asyncio.timeout(15):
                ws = await _ws_connect(
                    gw_url,
                    max_size=1024 * 1024,
                    additional_headers={"Origin": origin},
                    close_timeout=3,
                )
                async with ws:
                    # Wait for challenge
                    raw = await _asyncio.wait_for(ws.recv(), timeout=5)
                    msg = json.loads(raw)
                    if msg.get("event") != "connect.challenge":
                        return False

                    # Authenticate
                    connect_msg = {
                        "type": "req",
                        "id": "wf-abort-1",
                        "method": "connect",
                        "params": {
                            "minProtocol": 4, "maxProtocol": 4,
                            "client": {"id": "vo-workflow", "version": "1.0", "platform": "server", "mode": "webchat"},
                            "role": "operator",
                            "scopes": ["operator.read", "operator.write"],
                            "caps": [], "commands": [], "permissions": {},
                            "auth": {"token": token}
                        }
                    }
                    await ws.send(json.dumps(connect_msg))
                    raw2 = await _asyncio.wait_for(ws.recv(), timeout=5)
                    res = json.loads(raw2)
                    if not res.get("ok"):
                        print(f"[WORKFLOW] Gateway auth failed for session abort: {res.get('error', {}).get('message', 'unknown')}")
                        return False

                    # Send chat.abort targeting ONLY this session key
                    abort_msg = {
                        "type": "req",
                        "id": "wf-abort-2",
                        "method": "chat.abort",
                        "params": {
                            "sessionKey": session_key
                        }
                    }
                    await ws.send(json.dumps(abort_msg))
                    raw3 = await _asyncio.wait_for(ws.recv(), timeout=5)
                    res3 = json.loads(raw3)
                    if res3.get("ok"):
                        print(f"[WORKFLOW] Gateway session aborted: {session_key}")
                        return True
                    else:
                        err = res3.get("error", {}).get("message", "unknown")
                        print(f"[WORKFLOW] Gateway session abort response: {err} (key={session_key})")
                        return False

        except Exception as e:
            print(f"[WORKFLOW] Gateway session abort failed for {session_key}: {e}")
            return False

    try:
        loop = _asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(_asyncio.run, _do_abort())
            return future.result(timeout=20)
    except RuntimeError:
        return _asyncio.run(_do_abort())


def _wf_delete_session_via_gateway(session_key):
    """Delete a session from the gateway's in-memory state via WebSocket RPC.

    File-level cleanup alone is not enough — the gateway keeps sessions in memory
    and will keep retrying (with "Continue where you left off") on stale sessions.
    This sends a sessions.delete RPC to properly terminate the session.
    """
    import asyncio as _asyncio

    async def _do_delete():
        try:
            gw_url = VO_CONFIG["openclaw"]["gatewayUrl"]
            origin = f"http://127.0.0.1:{PORT}"
            token = _get_gateway_token()
            if not token:
                print(f"[WORKFLOW] No gateway token — skipping session delete via gateway for {session_key}")
                return False

            import websockets as _ws
            from websockets.asyncio.client import connect as _ws_connect

            async with _asyncio.timeout(15):
                ws = await _ws_connect(
                    gw_url,
                    max_size=1024 * 1024,
                    additional_headers={"Origin": origin},
                    close_timeout=3,
                )
                async with ws:
                    # Wait for challenge
                    raw = await _asyncio.wait_for(ws.recv(), timeout=5)
                    msg = json.loads(raw)
                    if msg.get("event") != "connect.challenge":
                        return False

                    # Authenticate
                    connect_msg = {
                        "type": "req",
                        "id": "wf-cleanup-1",
                        "method": "connect",
                        "params": {
                            "minProtocol": 4, "maxProtocol": 4,
                            "client": {"id": "vo-workflow", "version": "1.0", "platform": "server", "mode": "webchat"},
                            "role": "operator",
                            "scopes": ["operator.read", "operator.write"],
                            "caps": [], "commands": [], "permissions": {},
                            "auth": {"token": token}
                        }
                    }
                    await ws.send(json.dumps(connect_msg))
                    raw2 = await _asyncio.wait_for(ws.recv(), timeout=5)
                    res = json.loads(raw2)
                    if not res.get("ok"):
                        print(f"[WORKFLOW] Gateway auth failed for session delete: {res.get('error', {}).get('message', 'unknown')}")
                        return False

                    # Send sessions.delete
                    delete_msg = {
                        "type": "req",
                        "id": "wf-cleanup-2",
                        "method": "sessions.delete",
                        "params": {
                            "key": session_key,
                            "deleteTranscript": True,
                            "emitLifecycleHooks": False
                        }
                    }
                    await ws.send(json.dumps(delete_msg))
                    raw3 = await _asyncio.wait_for(ws.recv(), timeout=5)
                    res3 = json.loads(raw3)
                    if res3.get("ok"):
                        print(f"[WORKFLOW] Gateway session deleted: {session_key}")
                        return True
                    else:
                        # Session may not exist in gateway memory — that's fine
                        err = res3.get("error", {}).get("message", "unknown")
                        print(f"[WORKFLOW] Gateway session delete response: {err} (key={session_key})")
                        return False

        except Exception as e:
            print(f"[WORKFLOW] Gateway session delete failed for {session_key}: {e}")
            return False

    # Run the async delete — handle both threaded and event-loop contexts
    try:
        loop = _asyncio.get_running_loop()
        # We're inside an async context — schedule as a task
        # Since workflow runs in a sync thread, this shouldn't happen,
        # but handle it gracefully
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(_asyncio.run, _do_delete())
            return future.result(timeout=20)
    except RuntimeError:
        # No running loop — safe to use asyncio.run
        return _asyncio.run(_do_delete())


def _wf_cleanup_task_sessions(agent_id, project_id, task_id):
    if _is_hermes_agent(agent_id):
        return

    """Delete the single session created for this workflow task.

    Two-phase cleanup:
    1. Tell the gateway to drop the session from memory (prevents retry loops)
    2. Delete session files from disk (cleanup storage)

    Phase 1 is critical — without it, the gateway keeps the session alive and
    fires "Continue where you left off" retries that loop forever.
    """
    session_key = _wf_task_session_key(agent_id, project_id, task_id)
    gateway_session_key = _openclaw_gateway_session_key(agent_id, session_key)

    # Phase 1: Delete from gateway's in-memory state
    _wf_delete_session_via_gateway(gateway_session_key)

    # Phase 2: Clean up session files on disk
    home_path = VO_CONFIG.get("openclaw", {}).get("homePath", os.path.expanduser("~/.openclaw"))
    sessions_dir = os.path.join(home_path, "agents", agent_id, "sessions")
    sessions_json_path = os.path.join(sessions_dir, "sessions.json")

    try:
        if not os.path.exists(sessions_json_path):
            return

        with open(sessions_json_path, "r") as f:
            sessions_data = json.load(f)

        session_info, stored_session_key = _openclaw_get_session_info(sessions_data, agent_id, session_key)
        if not session_info:
            return

        # Get session ID to delete the JSONL file
        session_id = session_info.get("sessionId", "")
        session_file = session_info.get("sessionFile", "")
        del sessions_data[stored_session_key]

        with open(sessions_json_path, "w") as f:
            json.dump(sessions_data, f)

        # Delete session JSONL and lock files
        cleanup_paths = []
        if session_file:
            cleanup_paths.extend([session_file, f"{session_file}.lock"])
        if session_id:
            cleanup_paths.extend([os.path.join(sessions_dir, f"{session_id}{ext}") for ext in [".jsonl", ".jsonl.lock", ".trajectory.jsonl", ".trajectory-path.json"]])
        for fpath in dict.fromkeys(cleanup_paths):
            if fpath and os.path.exists(fpath):
                os.remove(fpath)

        print(f"[WORKFLOW] Cleaned up session files for agent={agent_id} task={task_id[:8]}: {stored_session_key}")
    except Exception as e:
        print(f"[WORKFLOW] Session file cleanup error: {e}")


def _wf_call_agent(agent_id, message, timeout=600, project_id=None, task_id=None):
    """Call an agent and return its response text.

    All calls for the same task reuse ONE session key, so the agent keeps
    context across work → review → rework cycles, prompt caching works,
    and only one session exists per task (cleaned up when task is done).

    Strategy:
    1. Try the OpenClaw Gateway HTTP API (/v1/chat/completions) — synchronous,
       works when the gateway has openaiHttp enabled.
    2. Fall back to `openclaw agent` CLI — always available when OpenClaw is installed.

    Both are portable — no hardcoded paths or tokens. Config comes from vo-config.json.
    """
    if _is_hermes_agent(agent_id):
        result = _handle_hermes_chat({"agentId": agent_id, "message": message, "timeoutSec": timeout})
        if result.get("ok"):
            return result.get("reply", "")
        return f"[ERROR] Hermes agent failed: {result.get('error') or result.get('reply') or result}"
    if _is_codex_agent(agent_id):
        result = _handle_codex_chat({"agentId": agent_id, "message": message, "timeoutSec": timeout, "conversationId": task_id or ""})
        reply = result.get("reply", "")
        if result.get("ok"):
            return reply
        return f"[ERROR] Codex agent failed: {result.get('error') or reply or result}"

    # Use a stable session key per task — reused across all calls for this task
    session_key = None
    if project_id and task_id:
        session_key = _wf_task_session_key(agent_id, project_id, task_id)

    # Try gateway HTTP API first
    result = _wf_call_agent_http(agent_id, message, timeout, session_key=session_key)
    if result is not None and not str(result).startswith("[ERROR] Gateway returned HTTP 5"):
        return result

    # Some OpenClaw installs do not expose a healthy /v1/chat/completions
    # endpoint but the Control UI WebSocket chat path works. Use it before CLI
    # so Dockerized Virtual Office can still deliver cross-platform messages
    # without needing the host openclaw binary inside the container.
    ws_result = _wf_call_agent_ws(agent_id, message, timeout, session_key=session_key)
    if ws_result is not None:
        return ws_result

    # Fall back to CLI (also pass session key if available)
    return _wf_call_agent_cli(agent_id, message, timeout, session_key=session_key)


def _extract_openclaw_text(value):
    """Normalize OpenClaw message/content shapes into plain text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or item.get("message") or ""))
        return "".join(parts).strip()
    if isinstance(value, dict):
        return _extract_openclaw_text(value.get("text") or value.get("content") or value.get("message") or value.get("delta") or "")
    return str(value)


def _wf_call_agent_ws(agent_id, message, timeout, session_key=None):
    """Call an OpenClaw agent through the gateway WebSocket chat path.

    This mirrors the live Virtual Office chat client. It is intentionally a
    fallback for product deployments where the HTTP OpenAI-compatible endpoint
    is unavailable/unhealthy and the openclaw CLI is not present in the Docker
    container.
    """
    token = _get_gateway_token()
    if not token:
        return None
    session_key = session_key or f"agent:{agent_id}:main"
    gw_url = VO_CONFIG.get("openclaw", {}).get("gatewayUrl", "ws://127.0.0.1:18789")
    origin = f"http://127.0.0.1:{PORT}"

    async def _call():
        async with ws_connect(
            gw_url,
            max_size=1024 * 1024,
            additional_headers={"Origin": origin},
            close_timeout=3,
        ) as ws:
            # Challenge
            await asyncio.wait_for(ws.recv(), timeout=5)
            connect_id = f"vo-ws-connect-{uuid.uuid4()}"
            await ws.send(json.dumps({
                "type": "req",
                "id": connect_id,
                "method": "connect",
                "params": {
                    "minProtocol": 4,
                    "maxProtocol": 4,
                    "client": {"id": "openclaw-control-ui", "version": _get_openclaw_version(), "platform": "web", "mode": "webchat"},
                    "role": "operator",
                    "scopes": ["operator.read", "operator.write", "operator.admin"],
                    "caps": ["tool-events"],
                    "commands": [],
                    "permissions": {},
                    "auth": {"token": token},
                    "locale": "en-US",
                    "userAgent": "virtual-office-server/1.0",
                },
            }))
            # Wait for connect response, ignoring snapshot/events.
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                msg = json.loads(raw)
                if msg.get("id") == connect_id:
                    if not msg.get("ok"):
                        return f"[ERROR] Gateway WS connect failed: {msg.get('error', {}).get('message', 'unknown')}"
                    break

            send_id = f"vo-ws-send-{uuid.uuid4()}"
            await ws.send(json.dumps({
                "type": "req",
                "id": send_id,
                "method": "chat.send",
                "params": {
                    "sessionKey": session_key,
                    "message": message,
                    "idempotencyKey": f"vo-a2a-{uuid.uuid4()}",
                },
            }))
            run_id = None
            final_seen = False
            deadline = time.time() + timeout
            while time.time() < deadline:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(30, max(1, deadline - time.time())))
                msg = json.loads(raw)
                if msg.get("id") == send_id:
                    if not msg.get("ok"):
                        return f"[ERROR] Gateway WS chat.send failed: {msg.get('error', {}).get('message', 'unknown')}"
                    payload = msg.get("payload") or {}
                    run_id = payload.get("runId")
                elif msg.get("event") == "chat":
                    payload = msg.get("payload") or {}
                    if payload.get("sessionKey") == session_key and payload.get("state") in ("final", "done"):
                        text = _extract_openclaw_text(payload.get("text") or payload.get("content") or payload.get("message") or payload.get("delta"))
                        if text:
                            return text
                        final_seen = True
                        break
                    if run_id and payload.get("runId") == run_id and payload.get("state") in ("final", "done"):
                        text = _extract_openclaw_text(payload.get("text") or payload.get("content") or payload.get("message") or payload.get("delta"))
                        if text:
                            return text
                        final_seen = True
                        break
                elif msg.get("event") == "session.message":
                    payload = msg.get("payload") or {}
                    m = payload.get("message") if isinstance(payload.get("message"), dict) else payload
                    if m.get("role") == "assistant" and (payload.get("sessionKey") in (None, session_key) or (run_id and payload.get("runId") == run_id)):
                        text = _extract_openclaw_text(m.get("content") or m.get("text") or m)
                        if text:
                            return text

            # Some gateway versions send final without text; fetch recent history.
            hist_id = f"vo-ws-history-{uuid.uuid4()}"
            await ws.send(json.dumps({"type": "req", "id": hist_id, "method": "chat.history", "params": {"sessionKey": session_key, "limit": 12}}))
            while time.time() < deadline + 10:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                msg = json.loads(raw)
                if msg.get("id") != hist_id:
                    continue
                if not msg.get("ok"):
                    return "[DELIVERED] Message delivered to OpenClaw agent; history fetch failed."
                payload = msg.get("payload") or {}
                messages = payload.get("messages") or payload.get("items") or payload.get("history") or []
                if isinstance(messages, dict):
                    messages = messages.get("messages") or messages.get("items") or []
                for item in reversed(messages):
                    role = item.get("role") or item.get("senderKind")
                    text = _extract_openclaw_text(item.get("text") or item.get("content") or item.get("message") or item)
                    if role == "assistant" and text:
                        return text
                return "[DELIVERED] Message delivered to OpenClaw agent."
            return "[DELIVERED] Message delivered to OpenClaw agent." if final_seen else None

    try:
        return asyncio.run(_call())
    except Exception as e:
        print(f"[WORKFLOW] Gateway WS agent call failed: {e}")
        return None


def _wf_call_agent_http(agent_id, message, timeout, session_key=None):
    """Try calling agent via gateway /v1/chat/completions. Returns None if not available.
    If session_key is provided, uses it for session routing (enables cleanup later)."""

    gateway_http = VO_CONFIG.get("openclaw", {}).get("gatewayHttp", "http://127.0.0.1:18789")
    token = _get_gateway_token()
    if not token:
        return None

    url = f"{gateway_http}/v1/chat/completions"
    payload = json.dumps({
        "model": f"openclaw/{agent_id}",
        "messages": [{"role": "user", "content": message}],
    })
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    if session_key:
        headers["x-openclaw-session-key"] = session_key

    try:
        req = urllib.request.Request(url, data=payload.encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout + 30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "application/json" not in content_type:
                # Gateway returned HTML (endpoint not enabled) — fall back to CLI
                return None
            data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                return msg.get("content", "")
            return data.get("reply", data.get("text", str(data)))
    except urllib.error.HTTPError as e:
        if e.code in (404, 405):
            # Endpoint not available — fall back to CLI
            return None
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        return f"[ERROR] Gateway returned HTTP {e.code}: {body}"
    except Exception:
        return None  # Fall back to CLI


def _wf_call_agent_cli(agent_id, message, timeout, session_key=None):
    """Call agent via `openclaw agent` CLI — always available when OpenClaw is installed."""

    openclaw_bin = shutil.which("openclaw")
    if not openclaw_bin:
        return "[ERROR] openclaw CLI not found in PATH"

    cmd = [openclaw_bin, "agent", "--agent", agent_id, "--message", message, "--timeout", str(timeout), "--json"]
    if session_key:
        cmd.extend(["--session-id", session_key])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 60)
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                return data.get("reply", data.get("text", result.stdout))
            except json.JSONDecodeError:
                return result.stdout.strip()
        else:
            return f"[ERROR] Agent returned code {result.returncode}: {result.stderr.strip()[:500]}"
    except subprocess.TimeoutExpired:
        return "[ERROR] Agent call timed out"
    except Exception as e:
        return f"[ERROR] Agent call failed: {str(e)}"

def _wf_build_project_context(project, task):
    """Build project and task metadata context string."""
    lines = []
    proj_title = project.get("title") or project.get("name") or "Untitled Project"
    proj_desc = project.get("description", "")
    proj_tags = project.get("tags", [])
    task_tags = task.get("tags", [])
    task_priority = task.get("priority", "medium")
    task_assignee = task.get("assignee", "unassigned")

    lines.append(f"PROJECT: {proj_title}")
    if proj_desc:
        lines.append(f"PROJECT DESCRIPTION: {proj_desc}")
    if proj_tags:
        lines.append(f"PROJECT TAGS: {', '.join(proj_tags)}")
    if task_tags:
        lines.append(f"TASK TAGS: {', '.join(task_tags)}")
    lines.append(f"PRIORITY: {task_priority}")
    lines.append(f"ASSIGNED TO: {task_assignee}")
    return "\n".join(lines)


def _wf_build_task_prompt(task, task_file_content=None, project=None):
    """Build the autonomous work prompt for an agent."""
    project_context = ""
    if project:
        project_context = _wf_build_project_context(project, task) + "\n\n"

    checklist_text = ""
    acceptance_checklist = _project_execution_acceptance_checklist(task)
    if acceptance_checklist:
        checklist_text = "\n\nChecklist (you must complete ALL items):\n"
        for i, item in enumerate(acceptance_checklist, 1):
            status = "✅ DONE" if item.get("done") else "⬜ TODO"
            checklist_text += f"  {i}. [{status}] {item.get('text', '')}\n"

    previous_work = ""
    if task_file_content:
        previous_work = f"\n\n--- PREVIOUS WORK LOG ---\n{task_file_content}\n--- END PREVIOUS WORK LOG ---\n\nContinue from where you left off. Do NOT redo work that was already completed."

    return f"""You have been assigned a task. Complete it fully on your own. Do NOT ask for clarification, followups, or user input.

{project_context}TASK: {task.get('title', 'Untitled')}

DESCRIPTION:
{task.get('description', 'No description provided.')}
{checklist_text}
{previous_work}

EXPECTED WORKFLOW:
1. First read the task and determine what content or deliverable must be produced. Write the task/deliverable acceptance criteria into the task checklist. The checklist is only for deliverable acceptance criteria, not a meeting action-item queue. If the task checklist is empty, include the created acceptance criteria in checklistUpdates and, when possible, persist them with PUT /api/projects/{{projectId}}/tasks/{{taskId}}.
2. Execute the task. For any Virtual Office operation, first use the vo-operating-guidelines skill to detect the VO environment, choose the correct VO skill, and follow its boundaries. If you discover an issue that requires alignment, use vo-operating-guidelines to decide whether a formal AI meeting is appropriate; when it is, proactively request a meeting with POST /api/projects/{{projectId}}/tasks/{{taskId}}/meeting-requests. Do not confirm or reject meetings yourself. Add the corresponding action items and discussion points as meeting/task context. Do not put those meeting action items or risks into the checklist or comments.
3. Before finishing, inspect whether every checklist item is complete. Mark completed checklist items done; if any item is unfinished, continue working until it is complete.

MANDATORY RULES — VIOLATIONS WILL FAIL REVIEW:
1. You MUST use tools (read, edit, exec, browser) to make REAL changes to actual files. Text-only responses WILL BE REJECTED.
2. Read the relevant source files FIRST to understand the codebase before making changes.
3. Use the edit tool to modify files. Use exec to run commands, test, or verify.
4. After making changes, verify them yourself — run the app, check the output, confirm it works.
5. In your final response include checklistUpdates as JSON: an array of {{id, text, done, evidence}}. Set done=true only for checklist items you actually verified as complete. Include meetingDiscussionPoints as JSON when there are meeting conclusions, risks, or discussion notes for the task.
5. Use the browser tool to visually verify UI changes on the running app/site if applicable.
6. In your final report, list EVERY file you modified and what you changed.

A reviewer will independently verify your work by reading the actual files and browsing the app. If no real file changes are found, ALL items will be marked DID_NOT_PASS.

WARNING: Do NOT run 'docker restart' on this app's container — it will kill the workflow pipeline managing this task. If you need to reload server changes, the app live-mounts /app so file edits take effect on the next HTTP request for static files. For server.py changes that need a process reload, note what needs restarting in your report and the reviewer will handle it."""

def _wf_task_needs_visual_review(task):
    """Heuristic: determine whether a task should require browser-based review."""
    parts = [
        task.get("title", "") or "",
        task.get("description", "") or "",
    ]
    for item in task.get("checklist") or []:
        parts.append(item.get("text", "") or "")
    hay = "\n".join(parts).lower()

    visual_terms = [
        "ui", "ux", "browser", "page", "screen", "visual", "visually",
        "frontend", "front-end", "layout", "render", "display", "button",
        "form", "modal", "panel", "dashboard", "site", "web app", "webapp",
        "css", "html", "screenshot", "snapshot", "click", "navigation",
        "animation", "canvas", "view", "viewer", "interactive"
    ]
    non_visual_terms = [
        "docs", "documentation", "audit", "analysis", "implementation map",
        "review evidence", "write-up", "writeup", "readme", "markdown"
    ]

    has_visual = any(term in hay for term in visual_terms)
    has_non_visual = any(term in hay for term in non_visual_terms)
    return has_visual and not has_non_visual


def _wf_build_review_prompt(task, task_file_content=None, project=None):
    """Build the self-review prompt for an agent."""
    project_context = ""
    if project:
        project_context = _wf_build_project_context(project, task) + "\n\n"

    items_text = ""
    acceptance_checklist = _project_execution_acceptance_checklist(task)
    if acceptance_checklist:
        for i, item in enumerate(acceptance_checklist, 1):
            items_text += f"  {i}. {item.get('text', '')}\n"

    needs_visual_review = _wf_task_needs_visual_review(task)
    visual_steps = """
3. Use the browser tool to load the running app/site and visually confirm UI changes are working. Take snapshots.
4. If you open any browser/session for review, you MUST close it before finishing your review response. Do not leave browser instances running after review.
5. If you cannot find real file changes for an item, mark it DID_NOT_PASS regardless of what was claimed earlier.""" if needs_visual_review else """
3. Use the browser tool only if the task has a real visual/UI surface that can be meaningfully checked in a running app or site.
4. If you open any browser/session for review, you MUST close it before finishing your review response.
5. If you cannot find real file changes or real deliverables for an item, mark it DID_NOT_PASS regardless of what was claimed earlier."""

    pass_line = "- PASS — verified in the actual files AND confirmed working in the browser/app" if needs_visual_review else "- PASS — verified in the actual files and supported by real verification steps (for example read/exec, and browser if applicable)"
    critical_line = "CRITICAL: You MUST use tools (read, exec, browser) during this review. A text-only review with no tool calls will be considered invalid." if needs_visual_review else "CRITICAL: You MUST use tools during this review. Use read and/or exec for non-visual tasks, and use browser only when the task is visually reviewable. A text-only review with no tool calls will be considered invalid."

    return f"""{project_context}Review your completed work on: {task.get('title', 'Untitled')}

You must INDEPENDENTLY VERIFY each checklist item. Do NOT trust your previous claims — verify by actually checking.

MANDATORY REVIEW STEPS:
1. Use the read tool to open the actual source files that were supposed to be modified. Confirm the changes exist in the code.
2. Use exec to run any tests, linters, or verification commands.
{visual_steps}

For EACH checklist item, respond with one of these statuses:
{pass_line}
- NEEDS_MORE_WORK — partially implemented but has issues you can identify in the code
- DID_NOT_PASS — no real changes found in files, or changes don't work
- REQUIRES_USER_REVIEW — ONLY if the item truly cannot be judged by an agent after using tools, such as a subjective product/design decision, required human sign-off, unavailable external system access that only the user can provide, or a genuinely destructive/approval-gated action. Do NOT use REQUIRES_USER_REVIEW for ordinary coding uncertainty, incomplete implementation, missing evidence, failed verification, or because one item previously needed rework. In those cases you MUST use NEEDS_MORE_WORK or DID_NOT_PASS.

If you can read the code, run tests, inspect outputs, or otherwise verify the implementation yourself, you MUST make your own judgment and use PASS, NEEDS_MORE_WORK, or DID_NOT_PASS.

Respond in this EXACT format (one line per item, after your verification):
REVIEW_ITEM_1: <status>
REVIEW_ITEM_2: <status>
...

Checklist items to review:
{items_text}

{critical_line}"""

def _wf_build_rework_prompt(task, failed_items, task_file_content=None, project=None):
    """Build a rework prompt for failed review items."""
    # project context not repeated in rework — agent already has it from the same session
    items_text = ""
    for i, item in enumerate(failed_items, 1):
        items_text += f"  {i}. {item.get('text', '')} — Status: {item.get('reviewStatus', 'needs_more_work')}\n"

    previous_work = ""
    if task_file_content:
        previous_work = f"\n\n--- PREVIOUS WORK LOG ---\n{task_file_content}\n--- END PREVIOUS WORK LOG ---"

    return f"""These items need more work on: {task.get('title', 'Untitled')}

The following checklist items did NOT pass review. Fix them yourself. Do not ask for help.

Items that need work:
{items_text}
{previous_work}

MANDATORY RULES:
1. You MUST use tools (read, edit, exec, browser) to make REAL changes to actual files.
2. Read the relevant files first, then use edit to fix the issues.
3. After fixing, verify your changes work — use exec to test and browser to visually confirm UI changes.
4. If you open any browser/session during rework or verification, you MUST close it before finishing your response. Do not leave browser instances running.
5. Only fix the items listed above. Do NOT redo work that already passed.
6. In your report, list EVERY file you modified and what you changed.

A reviewer will independently verify your fixes by reading the actual files and browsing the app."""

def _wf_review_had_structured_match(review_results):
    """Check if any review results came from structured line parsing (not defaults/fallbacks).

    Returns True if at least one result was explicitly parsed from a structured
    review line (marked with _parsed=True) or from a freeform-positive fallback.
    Returns False if all results came from the default needs_more_work fill-in
    (marked with _default=True) — indicating the parser couldn't understand the response.
    """
    for r in review_results:
        if r.get("_parsed") or r.get("_fallback"):
            return True
    return False


def _wf_parse_review_response(response_text, checklist, review_cycle=0):
    """Parse the agent's review response into structured results.

    Handles formats like:
      REVIEW_ITEM_1: PASS
      REVIEW_ITEM_2: NEEDS_MORE_WORK
    Or:
      1. PASS
      Item 3: DID_NOT_PASS
    Or freeform lines containing status keywords.

    Important: checks longer status strings first to avoid "PASS" matching "DID_NOT_PASS".

    Fallback behavior for freeform/unstructured responses:
    - If no structured review lines matched, performs sentiment analysis on the full text.
    - If sentiment is positive (pass keywords, no fail keywords), treats as all-pass.
    - If review_cycle >= 3 and all checklist items are marked done, auto-passes.
    """
    results = []
    lines = response_text.strip().split("\n")

    # Ordered longest-first to prevent "pass" from matching "did_not_pass"
    status_patterns = [
        ("requires_user_review", "requires_user_review"),
        ("requires user review", "requires_user_review"),
        ("needs_more_work", "needs_more_work"),
        ("needs more work", "needs_more_work"),
        ("did_not_pass", "did_not_pass"),
        ("did not pass", "did_not_pass"),
        ("pass", "pass"),
    ]

    item_idx = 0
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped or item_idx >= len(checklist):
            continue

        line_lower = line_stripped.lower()

        # Skip lines that don't look like review items (pure prose, headers, etc.)
        # Accept lines with REVIEW_ITEM_, numbered items, or containing a status keyword
        is_review_line = (
            "review_item" in line_lower
            or re.match(r'^\d+[\.\):\s]', line_stripped)
            or "item " in line_lower
        )

        matched_status = None
        for pattern, status_val in status_patterns:
            if pattern in line_lower:
                matched_status = status_val
                break

        if matched_status and (is_review_line or item_idx == 0 or len(checklist) == 1):
            results.append({
                "id": checklist[item_idx].get("id"),
                "text": checklist[item_idx].get("text", ""),
                "status": matched_status,
                "_parsed": True,
            })
            item_idx += 1
        elif matched_status and not is_review_line:
            # Heuristic: if we're already matching items and this line has a status,
            # it's probably a continuation
            if len(results) > 0:
                results.append({
                    "id": checklist[item_idx].get("id"),
                    "text": checklist[item_idx].get("text", ""),
                    "status": matched_status,
                    "_parsed": True,
                })
                item_idx += 1

    # --- Freeform fallback: if no structured lines matched at all ---
    if not results:
        response_lower = response_text.lower()

        # Positive sentiment keywords (agent says everything is good)
        positive_keywords = [
            "all items verified", "all items are done", "all items pass",
            "everything looks good", "everything is working", "all checks pass",
            "all tasks completed", "all completed", "all done", "looks great",
            "fully implemented", "all requirements met", "verified and working",
            "all items look good", "no issues found", "nothing to fix",
            "approved", "lgtm", "ship it",
        ]
        # Negative sentiment keywords (agent says something is wrong)
        negative_keywords = [
            "needs work", "needs more work", "did not pass", "not working",
            "failed", "missing", "incomplete", "broken", "issues found",
            "not implemented", "needs fix", "needs rework", "does not work",
            "errors", "bugs found", "not done", "partially done",
        ]

        # Count occurrences of positive vs negative keywords in the response.
        # This gives a quantitative signal: if positive_count > 0 and
        # negative_count == 0, the agent is clearly approving.
        positive_count = sum(1 for kw in positive_keywords if kw in response_lower)
        negative_count = sum(1 for kw in negative_keywords if kw in response_lower)

        if negative_count > 0:
            # Negative keywords found — don't auto-pass, fall through to defaults.
            # The agent explicitly flagged issues; treat as needs_more_work.
            pass
        else:
            # No structured lines AND zero negative keywords → treat as all-pass.
            # This covers: (a) positive sentiment ("all items verified"), and
            # (b) neutral/ambiguous text with no negatives ("code looks ready").
            # The spec says: empty results = all-pass, not all-fail.
            if positive_count > 0:
                fallback_reason = "freeform_positive_sentiment"
            else:
                fallback_reason = "freeform_no_negatives"
            for i, item in enumerate(checklist):
                results.append({
                    "id": item.get("id"),
                    "text": item.get("text", ""),
                    "status": "pass",
                    "_fallback": fallback_reason,
                    "_positive_count": positive_count,
                    "_negative_count": negative_count,
                })
            return results

        # Cycle-based fallback: if review_cycle >= 3 and all checklist items
        # are already marked done in the project data, auto-pass even with negatives
        if review_cycle >= 3:
            all_checklist_done = all(item.get("done", False) for item in checklist)
            if all_checklist_done:
                for i, item in enumerate(checklist):
                    results.append({
                        "id": item.get("id"),
                        "text": item.get("text", ""),
                        "status": "pass",
                        "_fallback": "cycle_3_checklist_done",
                    })
                return results

    # If parsing failed or incomplete, default remaining to needs_more_work
    for i in range(len(results), len(checklist)):
        results.append({
            "id": checklist[i].get("id"),
            "text": checklist[i].get("text", ""),
            "status": "needs_more_work",
            "_default": True,
        })

    return results

def _wf_unfinished_checklist_items(checklist):
    return [
        item for item in (checklist or [])
        if isinstance(item, dict) and item.get("done") is not True
    ]

def _wf_run_pipeline(project_id, single_task=False):
    """Main workflow pipeline — runs in a background thread."""
    with _WORKFLOW_LOCK:
        wf = _WORKFLOW_STATE.get(project_id)
        if not wf:
            return

    stop_flag = wf["stopFlag"]

    try:
      _wf_run_pipeline_inner(project_id, single_task, wf, stop_flag)
    except Exception as e:
        print(f"[WORKFLOW ERROR] Pipeline crashed for {project_id}: {e}")
        traceback.print_exc()
    finally:
        # Always clean up state
        with _WORKFLOW_LOCK:
            if project_id in _WORKFLOW_STATE:
                _WORKFLOW_STATE[project_id]["active"] = False
                _WORKFLOW_STATE[project_id]["thread"] = None
        _wf_persist_state(project_id)
        _wf_clear_persisted_state(project_id)


def _wf_run_pipeline_inner(project_id, single_task, wf, stop_flag):
    """Inner pipeline logic — wrapped by _wf_run_pipeline for error safety."""
    while not stop_flag.is_set():
        # Load fresh project data
        data = _load_projects()
        project = next((x for x in data["projects"] if x["id"] == project_id), None)
        if not project:
            break

        # Check for an active task (in-progress or review) before pulling from backlog.
        # This prevents backlog tasks from jumping ahead of tasks sent back for rework.
        active_task = _wf_get_active_task(project)
        if active_task:
            # There's already a task being worked on — do NOT pull from backlog.
            # The pipeline should not start a new task while one is still active.
            with _WORKFLOW_LOCK:
                wf["phase"] = "blocked_by_active_task"
                wf["error"] = f"Task '{active_task.get('title', '')}' is still in progress. Backlog tasks will not start until it is fully done or moved to backlog/done."
                wf["currentTaskId"] = active_task["id"]
                wf["active"] = False
            _wf_sync_project_workflow_meta(project_id, active=False, phase="blocked_by_active_task", current_task_id=active_task["id"], active_agent=active_task.get("assignee"))
            _wf_persist_state(project_id)
            break

        # Find next backlog task
        task = _wf_next_backlog_task(project)
        if not task:
            # No more backlog tasks
            with _WORKFLOW_LOCK:
                wf["phase"] = "idle"
                wf["currentTaskId"] = None
                wf["active"] = False
            _wf_sync_project_workflow_meta(project_id, active=False, phase="idle", current_task_id=None, active_agent=None)
            break

        task_id = task["id"]
        assignee = task.get("assignee")
        if not assignee:
            # Skip unassigned tasks
            with _WORKFLOW_LOCK:
                wf["phase"] = "error"
                wf["error"] = "Please assign an agent to all tasks"
                wf["active"] = False
            break

        with _WORKFLOW_LOCK:
            wf["currentTaskId"] = task_id
            wf["phase"] = "dispatching"
            wf["error"] = None
        _wf_sync_project_workflow_meta(project_id, active=True, phase="dispatching", current_task_id=task_id, active_agent=assignee)
        _wf_persist_state(project_id)

        if stop_flag.is_set():
            break

        # Step 1: Move straight to In Progress
        inprogress_col = _wf_get_inprogress_col(project)
        if not inprogress_col:
            with _WORKFLOW_LOCK:
                wf["phase"] = "error"
                wf["error"] = "No 'In Progress' column found"
                wf["active"] = False
            break

        _wf_move_task(project_id, task_id, inprogress_col["id"], by="workflow")
        _wf_write_task_file(project_id, task, "in_progress", work_log_entry="Sent to agent for work")

        with _WORKFLOW_LOCK:
            wf["phase"] = "in_progress"
        _wf_persist_state(project_id)

        if stop_flag.is_set():
            break

        # Clean up any stale session from a previous run of this task.
        # Without this, the gateway may still hold an old session in memory
        # and fire "Continue where you left off" instead of the actual task prompt.
        _wf_cleanup_task_sessions(assignee, project_id, task_id)

        task_file = _wf_read_task_file(project_id, task_id)
        prompt = _wf_build_task_prompt(task, task_file, project=project)
        agent_response = _wf_call_agent(assignee, prompt, project_id=project_id, task_id=task_id)

        if stop_flag.is_set():
            break

        # Update task file with agent response + file activity
        work_activity = _wf_extract_session_activity(assignee, project_id, task_id)
        work_activity_text = _wf_format_activity_summary(work_activity)
        _wf_write_task_file(project_id, task, "in_progress", work_log_entry=f"Agent response:\n{agent_response[:2000]}\n\n**Activity:**\n{work_activity_text}")

        # Step 3: Move to Review
        review_col = _wf_get_review_col(project)
        if not review_col:
            with _WORKFLOW_LOCK:
                wf["phase"] = "error"
                wf["error"] = "No 'Review' column found"
                wf["active"] = False
            break

        _wf_move_task(project_id, task_id, review_col["id"], by="workflow")

        # Review loop
        max_review_cycles = 5
        review_cycle = 0
        task_done = False
        wf["_parseFailCount"] = 0  # Track consecutive parse failures for safety cap
        wf["_reworkCount"] = 0     # Track total consecutive rework cycles for safety cap

        while review_cycle < max_review_cycles and not stop_flag.is_set():
            review_cycle += 1
            with _WORKFLOW_LOCK:
                wf["phase"] = "reviewing"
                wf["reviewCycle"] = review_cycle
            _wf_sync_project_workflow_meta(project_id, active=True, phase="reviewing", current_task_id=task_id, active_agent=assignee)
            _wf_persist_state(project_id)

            # Reload task for fresh checklist
            data = _load_projects()
            project = next((x for x in data["projects"] if x["id"] == project_id), None)
            if not project:
                break
            task = next((t for t in project["tasks"] if t["id"] == task_id), None)
            if not task:
                break

            checklist = _project_execution_acceptance_checklist(task)
            if not checklist:
                _wf_write_task_file(
                    project_id,
                    task,
                    "review",
                    review_results=[{
                        "id": "acceptance-checklist",
                        "text": "Create task acceptance checklist items before completion.",
                        "status": "needs_more_work",
                        "reviewStatus": "needs_more_work",
                        "reason": "Acceptance checklist is empty.",
                    }],
                    work_log_entry="❌ Review: REJECTED — acceptance checklist is empty."
                )
                wf["_reworkCount"] = wf.get("_reworkCount", 0) + 1
                task_done = False
                break

            task_file = _wf_read_task_file(project_id, task_id)
            review_prompt = _wf_build_review_prompt(task, task_file, project=project)
            review_response = _wf_call_agent(assignee, review_prompt, project_id=project_id, task_id=task_id)

            if stop_flag.is_set():
                break

            # Parse review results (pass review_cycle for freeform fallback logic)
            review_results = _wf_parse_review_response(review_response, checklist, review_cycle=review_cycle)

            # Save review results to task
            _wf_update_task_field(project_id, task_id, "reviewCheck", review_results)
            review_activity = _wf_extract_session_activity(assignee, project_id, task_id)
            review_activity_text = _wf_format_activity_summary(review_activity)
            _wf_write_task_file(project_id, task, "review", review_results=review_results, work_log_entry=f"Review cycle {review_cycle}:\n{review_response[:2000]}\n\n**Review verification activity:**\n{review_activity_text}")

            # ── TOOL-CALL VERIFICATION ──────────────────────────────
            # A valid review MUST include actual tool usage to verify the work.
            # For visual/UI tasks, browser review is strongly expected.
            # For non-visual tasks, read/exec verification is enough.
            # Exception: cycle >= 4 with all checklist done bypasses this
            # to prevent infinite loops when the agent refuses to use tools.
            review_flags = _wf_activity_tool_flags(review_activity)
            review_tool_count = review_flags["tool_call_count"]
            review_has_reads = review_flags["has_reads"]
            review_has_exec = review_flags["has_exec"]
            review_has_browser = review_flags["has_browser"]
            task_needs_visual_review = _wf_task_needs_visual_review(task)
            review_verified = review_has_reads or review_has_exec or review_has_browser
            review_visual_verified = review_has_browser if task_needs_visual_review else True

            # Track whether the original parse had structured matches (before
            # tool-verification may override the result). This is used by the
            # safety cap below to detect repeated parse failures even when
            # freeform-fallback temporarily marks everything as pass.
            original_had_structured = _wf_review_had_structured_match(review_results)

            # Check results
            all_pass = all(r.get("status") == "pass" for r in review_results)
            needs_user = any(r.get("status") == "requires_user_review" for r in review_results)
            failed_items = [r for r in review_results if r.get("status") in ("needs_more_work", "did_not_pass")]

            # Reject reviews that claim all-pass without required verification.
            if all_pass and (not review_verified or not review_visual_verified):
                all_checklist_done = all(item.get("done", False) for item in checklist)
                if review_cycle >= 4 and all_checklist_done:
                    _wf_write_task_file(project_id, task, "review",
                        work_log_entry=f"⚠️ Review cycle {review_cycle}: accepted without full verification (all checklist items done, cycle limit reached)")
                else:
                    all_pass = False
                    failed_items = review_results
                    reason = "used no tools (read/exec/browser) to verify"
                    if review_verified and not review_visual_verified:
                        reason = "did not use browser verification for a visually reviewable task"
                    _wf_write_task_file(project_id, task, "review",
                        work_log_entry=f"❌ Review cycle {review_cycle}: REJECTED — agent claimed PASS but {reason}. {review_tool_count} total tool calls.")

            if all_pass:
                unfinished_items = _wf_unfinished_checklist_items(checklist)
                if unfinished_items:
                    all_pass = False
                    failed_items = [
                        {
                            "id": item.get("id"),
                            "text": item.get("text", ""),
                            "status": "needs_more_work",
                            "reviewStatus": "needs_more_work",
                            "reason": "Checklist item is still unchecked.",
                        }
                        for item in unfinished_items
                    ]
                    _wf_write_task_file(
                        project_id,
                        task,
                        "review",
                        review_results=failed_items,
                        work_log_entry=f"❌ Review cycle {review_cycle}: REJECTED — {len(unfinished_items)} checklist item(s) are still unchecked."
                    )
                else:
                    wf["_reworkCount"] = 0
                    wf["_parseFailCount"] = 0
                    task_done = True
                    break

            if needs_user:
                # Pause workflow — user must intervene
                with _WORKFLOW_LOCK:
                    wf["phase"] = "awaiting_user_review"
                    wf["error"] = "Task requires user review for some items"
                _wf_sync_project_workflow_meta(project_id, active=True, phase="awaiting_user_review", current_task_id=task_id, active_agent=assignee)
                _wf_persist_state(project_id)
                _wf_write_task_file(project_id, task, "review", review_results=review_results, work_log_entry="Workflow paused — requires user review")
                # Wait until user resolves or stop
                while not stop_flag.is_set():
                    time.sleep(5)
                    # Check if user resolved review items
                    data = _load_projects()
                    project = next((x for x in data["projects"] if x["id"] == project_id), None)
                    if not project:
                        break
                    task = next((t for t in project["tasks"] if t["id"] == task_id), None)
                    if not task:
                        break
                    current_review = task.get("reviewCheck", [])
                    still_needs_user = any(r.get("status") == "requires_user_review" for r in current_review)
                    if not still_needs_user:
                        # User resolved — check if all pass now
                        all_resolved_pass = all(r.get("status") == "pass" for r in current_review)
                        if all_resolved_pass:
                            task_done = True
                            break
                        else:
                            # Some items still need work — continue review loop
                            failed_items = [r for r in current_review if r.get("status") in ("needs_more_work", "did_not_pass")]
                            break
                if task_done or stop_flag.is_set():
                    break

            if failed_items and not stop_flag.is_set():
                # Safety cap: track consecutive rework cycles where the parser
                # couldn't extract structured review lines. Uses original_had_structured
                # (computed BEFORE tool-verification may override all_pass→failed)
                # so that freeform-positive responses that get rejected by tool-check
                # still count as parse failures.
                if not original_had_structured:
                    parse_fail_count = wf.get("_parseFailCount", 0) + 1
                    wf["_parseFailCount"] = parse_fail_count
                else:
                    wf["_parseFailCount"] = 0
                    parse_fail_count = 0

                # Also track total consecutive rework cycles (regardless of parse
                # success) to catch loops where the agent keeps failing for any reason.
                rework_count = wf.get("_reworkCount", 0) + 1
                wf["_reworkCount"] = rework_count

                # Escalate at 3 consecutive parse failures OR 3 total reworks with
                # the same pattern (prevents loops from any cause, not just parse).
                should_escalate = parse_fail_count >= 3 or rework_count >= 3
                if should_escalate:
                    reason_parts = []
                    if parse_fail_count >= 3:
                        reason_parts.append(f"parser failed to match structured output for {parse_fail_count} consecutive cycles")
                    if rework_count >= 3:
                        reason_parts.append(f"task has been reworked {rework_count} consecutive times")
                    reason = "; ".join(reason_parts)

                    with _WORKFLOW_LOCK:
                        wf["phase"] = "awaiting_human_intervention"
                        wf["error"] = (
                            f"Review loop safety cap triggered: {reason}. "
                            f"The reviewing agent may be responding with freeform text "
                            f"or the task may be stuck. Please review manually."
                        )
                    _wf_sync_project_workflow_meta(project_id, active=True, phase="awaiting_human_intervention", current_task_id=task_id, active_agent=assignee)
                    _wf_persist_state(project_id)
                    _wf_write_task_file(
                        project_id, task, "review",
                        review_results=review_results,
                        work_log_entry=f"⚠️ Escalated to user — {reason}. Last response:\n{review_response[:1000]}"
                    )
                    break

                # Move back to In Progress for rework
                with _WORKFLOW_LOCK:
                    wf["phase"] = "reworking"
                _wf_update_task_field(project_id, task_id, "lastReviewCheck", review_results)
                _wf_sync_project_workflow_meta(project_id, active=True, phase="reworking", current_task_id=task_id, active_agent=assignee)
                _wf_persist_state(project_id)

                # Clear stale reviewCheck so next cycle starts clean
                _wf_update_task_field(project_id, task_id, "reviewCheck", [])

                _wf_move_task(project_id, task_id, inprogress_col["id"], by="workflow")
                _wf_write_task_file(project_id, task, "in_progress", work_log_entry=f"Back to In Progress — {len(failed_items)} items need rework")

                task_file = _wf_read_task_file(project_id, task_id)
                rework_prompt = _wf_build_rework_prompt(task, failed_items, task_file)
                rework_response = _wf_call_agent(assignee, rework_prompt, project_id=project_id, task_id=task_id)

                if stop_flag.is_set():
                    break

                rework_activity = _wf_extract_session_activity(assignee, project_id, task_id)
                rework_activity_text = _wf_format_activity_summary(rework_activity)
                _wf_write_task_file(project_id, task, "in_progress", work_log_entry=f"Rework response:\n{rework_response[:2000]}\n\n**Rework activity:**\n{rework_activity_text}")

                # Move back to Review
                _wf_move_task(project_id, task_id, review_col["id"], by="workflow")

        # End of review loop
        if stop_flag.is_set():
            break

        if task_done:
            # Extract session activity BEFORE cleanup (needs the session files)
            activity = _wf_extract_session_activity(assignee, project_id, task_id)
            activity_summary = _wf_format_activity_summary(activity)

            # Move to Done
            done_col = _wf_get_done_col(project)
            if done_col:
                _wf_move_task(project_id, task_id, done_col["id"], by="workflow")

                # Write completion with activity summary
                completion_entry = f"Task completed — all review checks passed\n\n### Task Completion Summary\n{activity_summary}"
                _wf_write_task_file(project_id, task, "done", work_log_entry=completion_entry)

            # Clean up workflow sessions for this task (AFTER activity extraction)
            _wf_cleanup_task_sessions(assignee, project_id, task_id)

            with _WORKFLOW_LOCK:
                wf["phase"] = "task_done"
                wf["currentTaskId"] = None
            _wf_sync_project_workflow_meta(project_id, active=(not single_task), phase="task_done", current_task_id=None, active_agent=None)
            _wf_persist_state(project_id)

            if single_task:
                # Auto Mode OFF — stop after one task
                with _WORKFLOW_LOCK:
                    wf["active"] = False
                break
            else:
                # Auto Mode ON — continue to next task
                time.sleep(2)  # Brief pause between tasks
                continue
        else:
            # Task did NOT pass review after max cycles — do NOT pull next backlog task.
            # Keep this task in progress and pause for human intervention.
            _wf_move_task(project_id, task_id, inprogress_col["id"], by="workflow")
            _wf_write_task_file(project_id, task, "in_progress",
                work_log_entry=f"Review failed after {max_review_cycles} cycles — paused for human intervention. Backlog tasks will NOT proceed until this task passes or is manually resolved.")

            with _WORKFLOW_LOCK:
                wf["phase"] = "awaiting_human_intervention"
                wf["error"] = f"Task '{task.get('title', '')}' failed review after {max_review_cycles} cycles. Resolve manually or retry."
            _wf_sync_project_workflow_meta(project_id, active=True, phase="awaiting_human_intervention", current_task_id=task_id, active_agent=assignee)
            _wf_persist_state(project_id)

            # Wait until human resolves (moves task to done/backlog, or restarts workflow)
            while not stop_flag.is_set():
                time.sleep(5)
                # Check if task was manually moved to done or back to backlog
                data = _load_projects()
                project = next((x for x in data["projects"] if x["id"] == project_id), None)
                if not project:
                    break
                task = next((t for t in project["tasks"] if t["id"] == task_id), None)
                if not task:
                    break
                done_col = _wf_get_done_col(project)
                backlog_col = _wf_get_backlog_col(project)
                current_col = task.get("columnId")
                if done_col and current_col == done_col["id"]:
                    # Human moved to done — clean up and continue
                    _wf_cleanup_task_sessions(assignee, project_id, task_id)
                    break
                if backlog_col and current_col == backlog_col["id"]:
                    # Human moved back to backlog — skip this task
                    _wf_cleanup_task_sessions(assignee, project_id, task_id)
                    break

            if stop_flag.is_set():
                break

            # If single_task mode, stop; otherwise loop will re-check backlog
            if single_task:
                with _WORKFLOW_LOCK:
                    wf["active"] = False
                break
            else:
                time.sleep(2)
                continue

    # Pipeline ended (cleanup handled by wrapper in _wf_run_pipeline)


WORKFLOW_STATE_FILE = os.path.join(STATUS_DIR, "workflow-state.json")

def _wf_persist_state(project_id):
    """Persist workflow state to disk so it survives page refreshes and container restarts."""
    with _WORKFLOW_LOCK:
        wf = _WORKFLOW_STATE.get(project_id, {})
    state_data = {}
    try:
        if os.path.isfile(WORKFLOW_STATE_FILE):
            with open(WORKFLOW_STATE_FILE, "r") as f:
                state_data = json.load(f)
    except Exception:
        state_data = {}
    state_data[project_id] = {
        "active": wf.get("active", False),
        "autoMode": wf.get("autoMode", False),
        "currentTaskId": wf.get("currentTaskId"),
        "currentAssignee": wf.get("currentAssignee"),
        "currentTaskTitle": wf.get("currentTaskTitle"),
        "phase": wf.get("phase", "idle"),
        "error": wf.get("error"),
        "reviewCycle": wf.get("reviewCycle", 0),
    }
    try:
        os.makedirs(os.path.dirname(WORKFLOW_STATE_FILE), exist_ok=True)
        with open(WORKFLOW_STATE_FILE, "w") as f:
            json.dump(state_data, f, indent=2)
    except Exception:
        pass
    # Also write shared project-work signal file so other VO instances
    # can show project work indicators.
    # This file lives in ~/.openclaw/shared/ which is mounted by all VOs.
    _wf_update_shared_project_work()


def _wf_update_shared_project_work():
    """Write active project-work data to a shared file readable by all VO instances.
    Maps agent IDs to their active project task info."""
    active_phases = ("in_progress", "dispatching", "reviewing", "rework")
    shared = {}
    with _WORKFLOW_LOCK:
        for pid, wf in _WORKFLOW_STATE.items():
            if not wf.get("active") or wf.get("phase") not in active_phases:
                continue
            agent_id = wf.get("currentAssignee")
            if not agent_id:
                continue
            shared[agent_id] = {
                "projectId": pid,
                "taskId": wf.get("currentTaskId", ""),
                "taskTitle": wf.get("currentTaskTitle", ""),
                "phase": wf.get("phase", ""),
                "updatedAt": int(time.time() * 1000),
            }
    try:
        shared_path = os.path.join(WORKSPACE_BASE, "shared", "project-work.json")
        os.makedirs(os.path.dirname(shared_path), exist_ok=True)
        with open(shared_path, "w") as f:
            json.dump(shared, f)
    except Exception:
        pass


def _wf_load_persisted_state(project_id):
    """Load persisted workflow state from disk."""
    try:
        if os.path.isfile(WORKFLOW_STATE_FILE):
            with open(WORKFLOW_STATE_FILE, "r") as f:
                state_data = json.load(f)
            return state_data.get(project_id, {})
    except Exception:
        pass
    return {}

def _wf_clear_persisted_state(project_id):
    """Clear persisted state when workflow ends."""
    try:
        if os.path.isfile(WORKFLOW_STATE_FILE):
            with open(WORKFLOW_STATE_FILE, "r") as f:
                state_data = json.load(f)
            state_data.pop(project_id, None)
            with open(WORKFLOW_STATE_FILE, "w") as f:
                json.dump(state_data, f, indent=2)
    except Exception:
        pass




def _codex_reasoning_events_to_chat_messages(events, agent_id, max_messages=50):
    states = {}
    ordered = []
    for event in events:
        if event.get("type") != "reasoning":
            continue
        key = f"{event.get('operationId') or event.get('turnId') or event.get('threadId') or 'turn'}:{event.get('itemId') or 'reasoning'}"
        state = states.get(key)
        if not state:
            state = {"text": "", "ids": set(), "lastTs": 0, "status": "running"}
            states[key] = state
            ordered.append((key, state))
        event_id = event.get("id")
        if event_id and event_id in state["ids"]:
            continue
        if event_id:
            state["ids"].add(event_id)
        incoming = _provider_visible_thinking("codex", {**event, "thinking": event.get("text") or event.get("output") or ""})
        if not incoming:
            continue
        if event.get("replace") and incoming.strip():
            state["text"] = incoming
        else:
            if event.get("boundary") and state["text"].strip() and not state["text"].endswith("\n\n"):
                state["text"] += "\n\n"
            state["text"] += incoming
        state["lastTs"] = max(int(event.get("ts") or 0), int(state.get("lastTs") or 0))
        state["status"] = event.get("status") or state.get("status") or "running"

    messages = []
    for _, state in ordered:
        text = state.get("text", "").strip()
        if not text:
            continue
        messages.append({
            "role": "assistant",
            "text": "",
            "thinking": text,
            "reasoningStatus": state.get("status") or "running",
            "ts": state.get("lastTs") or 0,
            "epochMs": state.get("lastTs") or 0,
            "fromAgentId": agent_id,
            "source": "codex-activity",
        })
    return messages[-max_messages:]


def _wf_get_task_session_messages(agent_id, project_id, task_id, max_messages=50, conversation_id=None):
    if _is_hermes_agent(agent_id):
        agent = _get_hermes_agent(agent_id) or {}
        profile = agent.get("profile") or agent.get("providerAgentId") or "default"
        return _load_hermes_history(profile, conversation_id)[-max_messages:]
    if _is_codex_agent(agent_id):
        messages = []
        codex_conversation_id = conversation_id or task_id
        for event in _load_comm_history(limit=max_messages, conversation_id=codex_conversation_id):
            msg = _comm_event_to_chat_message(event, agent_id)
            if msg:
                messages.append(msg)
        messages.extend(_codex_reasoning_events_to_chat_messages(
            _get_codex_activity(agent_id, codex_conversation_id, 0),
            agent_id,
            max_messages=max_messages,
        ))
        messages.sort(key=lambda m: int(m.get("epochMs") or m.get("ts") or 0))
        return messages[-max_messages:]

    """Read messages from the task-specific workflow session JSONL only."""
    session_key = _wf_task_session_key(agent_id, project_id, task_id)
    home_path = VO_CONFIG.get("openclaw", {}).get("homePath", os.path.expanduser("~/.openclaw"))
    sessions_dir = os.path.join(home_path, "agents", agent_id, "sessions")
    sessions_json_path = os.path.join(sessions_dir, "sessions.json")

    try:
        with open(sessions_json_path, "r") as f:
            sessions_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    session_info, _ = _openclaw_get_session_info(sessions_data, agent_id, session_key)
    if not session_info:
        return []

    session_id = session_info.get("sessionId", "")
    jsonl_path = session_info.get("sessionFile") or (os.path.join(sessions_dir, f"{session_id}.jsonl") if session_id else "")
    if not os.path.exists(jsonl_path):
        return []

    messages = []
    try:
        # Read tail of file — use a larger buffer to handle long lines (tool results
        # can be 100KB+). Read last 256KB to ensure we capture multiple complete lines.
        TAIL_BYTES = 256 * 1024
        with open(jsonl_path, "rb") as fb:
            fb.seek(0, 2)
            fsize = fb.tell()
            start = max(0, fsize - TAIL_BYTES)
            fb.seek(start)
            tail_data = fb.read().decode("utf-8", errors="replace")
        if start > 0:
            nl = tail_data.find("\n")
            if nl >= 0:
                tail_data = tail_data[nl + 1:]
        for line in tail_data.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = entry.get("message", entry)
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue
            content = msg.get("content", [])
            text = ""
            tool_info = []
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                for c in content:
                    if isinstance(c, dict):
                        if c.get("type") == "text":
                            text += c.get("text", "")
                        elif c.get("type") == "toolCall":
                            name = c.get("name", "?")
                            args = c.get("arguments", {})
                            # Build a human-readable summary instead of bare tool name
                            summary = name
                            if isinstance(args, dict):
                                if name in ("read", "Read") and (args.get("file") or args.get("path") or args.get("file_path")):
                                    fpath = args.get("file") or args.get("path") or args.get("file_path") or ""
                                    summary = f"Reading {fpath.split('/')[-1] if '/' in fpath else fpath}"
                                elif name in ("edit", "Edit"):
                                    fpath = args.get("file") or args.get("path") or args.get("file_path") or ""
                                    summary = f"Editing {fpath.split('/')[-1] if '/' in fpath else fpath}"
                                elif name in ("write", "Write"):
                                    fpath = args.get("file") or args.get("path") or args.get("file_path") or ""
                                    summary = f"Writing {fpath.split('/')[-1] if '/' in fpath else fpath}"
                                elif name == "exec":
                                    cmd = args.get("command", "")
                                    summary = f"Running: {cmd[:80]}" if cmd else "exec"
                                elif name == "web_search":
                                    query = args.get("query", "")
                                    summary = f"Searching: {query[:60]}" if query else "web_search"
                                elif name == "web_fetch":
                                    url = args.get("url", "")
                                    summary = f"Fetching: {url[:60]}" if url else "web_fetch"
                                elif name == "browser":
                                    action = args.get("action", "")
                                    summary = f"Browser: {action}" if action else "browser"
                                elif name == "sessions_send":
                                    target = args.get("sessionKey") or args.get("label") or ""
                                    summary = f"Messaging: {target[:40]}" if target else "sessions_send"
                            tool_info.append({"name": summary, "args_preview": ""})
                        elif c.get("type") == "toolResult":
                            pass  # skip tool results for chat display
            if text or tool_info:
                m = {"role": role, "timestamp": msg.get("timestamp", entry.get("timestamp", 0))}
                if text:
                    m["text"] = text[:2000]
                if tool_info:
                    m["tools"] = tool_info[:5]  # cap tool display
                messages.append(m)
        messages = messages[-max_messages:]
    except Exception:
        pass
    return messages


def _wf_is_task_session_active(agent_id, project_id, task_id):
    if _is_hermes_agent(agent_id) or _is_codex_agent(agent_id):
        return False

    """Check if the task-specific workflow session is still actively running."""
    session_key = _wf_task_session_key(agent_id, project_id, task_id)
    home_path = VO_CONFIG.get("openclaw", {}).get("homePath", os.path.expanduser("~/.openclaw"))
    sessions_dir = os.path.join(home_path, "agents", agent_id, "sessions")
    sessions_json_path = os.path.join(sessions_dir, "sessions.json")

    try:
        with open(sessions_json_path, "r") as f:
            sessions_data = json.load(f)
        session_info, _ = _openclaw_get_session_info(sessions_data, agent_id, session_key)
        status = session_info.get("status", "")
        return status == "running"
    except Exception:
        return False


def _handle_workflow_chat(project_id):
    """GET /api/projects/{id}/workflow/chat — get the active workflow agent's session messages.

    ONLY reads from the task-specific workflow session (wf-<project>-<task>),
    never from the agent's main session or other sessions.
    """
    with _WORKFLOW_LOCK:
        wf = _WORKFLOW_STATE.get(project_id, {})

    # Also check persisted state if in-memory is empty
    persisted = _wf_load_persisted_state(project_id)
    current_task_id = wf.get("currentTaskId") or persisted.get("currentTaskId")
    phase = wf.get("phase") or persisted.get("phase", "idle")

    # Find the assigned agent — check current task or find any in-progress/review task
    data = _load_projects()
    p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if not p:
        return {"ok": True, "messages": [], "agent": None}

    project_execution_active = _project_execution_enabled(p) and p.get("workflowActive") and p.get("activeTaskId")
    agent_key = p.get("activeAgent") if project_execution_active else None
    task_id = p.get("activeTaskId") if project_execution_active else current_task_id
    conversation_id = None

    # First try the tracked current task
    if task_id:
        task = next((t for t in p["tasks"] if t["id"] == task_id), None)
        if task:
            if project_execution_active:
                phase = p.get("workflowPhase") or phase
                conversation_id = task.get("activeAttemptId")
                if phase == "reviewing":
                    agent_key = agent_key or task.get("reviewerAgentId")
                else:
                    agent_key = agent_key or task.get("executorAgentId")
            agent_key = agent_key or task.get("assignee")

    # If no tracked task, find the most recently active task (in progress or review)
    if not agent_key:
        ip_cols = [c["id"] for c in p.get("columns", []) if c.get("title", "").lower() in ("in progress", "review", "to do")]
        active_tasks = [t for t in p.get("tasks", []) if t.get("columnId") in ip_cols]
        if active_tasks:
            active_tasks.sort(key=lambda t: t.get("updatedAt", ""), reverse=True)
            task_id = active_tasks[0]["id"]
            agent_key = active_tasks[0].get("assignee")

    if not agent_key or not task_id:
        return {"ok": True, "messages": [], "agent": None, "phase": phase}

    # Read ONLY from the execution-scoped session. Project Execution uses the
    # active attempt/review id for OpenClaw sessions so repeat triggers do not
    # continue a prior run's transcript.
    session_task_id = conversation_id if (project_execution_active and conversation_id and not (_is_hermes_agent(agent_key) or _is_codex_agent(agent_key))) else task_id
    msgs = _wf_get_task_session_messages(agent_key, project_id, session_task_id, conversation_id=conversation_id)

    # Check if the workflow session is still actively running
    session_active = _wf_is_task_session_active(agent_key, project_id, session_task_id)

    return {
        "ok": True,
        "messages": msgs,
        "agent": agent_key,
        "taskId": task_id,
        "phase": phase,
        "sessionActive": session_active,
    }

def _handle_workflow_start(project_id, body=None):
    """POST /api/projects/{id}/workflow/start — start the workflow pipeline."""
    body = body or {}
    data = _load_projects()
    p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if not p:
        return {"error": "Project not found", "_status": 404}

    with _WORKFLOW_LOCK:
        wf = _WORKFLOW_STATE.get(project_id)
        if wf and wf.get("active"):
            return {"error": "Workflow already running for this project", "_status": 409}

        auto_mode = body.get("autoMode", False)
        stop_flag = threading.Event()
        wf = {
            "active": True,
            "autoMode": auto_mode,
            "currentTaskId": None,
            "phase": "starting",
            "error": None,
            "reviewCycle": 0,
            "stopFlag": stop_flag,
            "thread": None,
        }
        _WORKFLOW_STATE[project_id] = wf

    # Update project workflow settings
    p["workflowActive"] = True
    p["workflowPhase"] = "starting"
    p["activeTaskId"] = None
    p["activeAgent"] = None
    p["autoMode"] = auto_mode
    p["updatedAt"] = _proj_now()
    _save_projects(data)
    _log_activity(p, "workflow_started", "user", f"Workflow started (autoMode: {auto_mode})")

    _wf_persist_state(project_id)

    # Launch background thread
    single_task = not auto_mode
    t = _project_execution_launch_thread(_wf_run_pipeline, (project_id, single_task))
    with _WORKFLOW_LOCK:
        wf["thread"] = t

    return {"ok": True, "status": "started", "autoMode": auto_mode}

def _handle_workflow_stop(project_id):
    """POST /api/projects/{id}/workflow/stop — stop the workflow."""
    current_task_id = None
    with _WORKFLOW_LOCK:
        wf = _WORKFLOW_STATE.get(project_id)
        if not wf or not wf.get("active"):
            return {"ok": True, "status": "already_stopped"}
        current_task_id = wf.get("currentTaskId")
        wf["stopFlag"].set()
        wf["active"] = False
        wf["phase"] = "stopped"
        wf["currentTaskId"] = None

    _wf_persist_state(project_id)
    _wf_clear_persisted_state(project_id)

    # Update project
    data = _load_projects()
    p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if p:
        p["workflowActive"] = False
        p["workflowPhase"] = "stopped"
        p["activeTaskId"] = None
        p["activeAgent"] = None
        p["updatedAt"] = _proj_now()
        _save_projects(data)
        _log_activity(p, "workflow_stopped", "user", "Workflow stopped by user")

    # Abort the running agent session for the active task, then clean up.
    # This sends chat.abort to the gateway which immediately kills any in-flight
    # LLM inference — only targets this specific task session, not the agent's
    # main session or other workflow sessions.
    if current_task_id and p:
        task = next((t for t in p.get("tasks", []) if t["id"] == current_task_id), None)
        if task and task.get("assignee"):
            session_key = _wf_task_session_key(task["assignee"], project_id, current_task_id)
            _wf_abort_task_session(session_key)
            _wf_cleanup_task_sessions(task["assignee"], project_id, current_task_id)

    return {"ok": True, "status": "stopped"}

def _handle_workflow_auto_mode(project_id, body):
    """PUT /api/projects/{id}/workflow/auto-mode — toggle auto mode."""
    auto_mode = body.get("autoMode", False)
    data = _load_projects()
    p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if not p:
        return {"error": "Project not found", "_status": 404}
    p["autoMode"] = auto_mode
    p["updatedAt"] = _proj_now()
    _save_projects(data)

    with _WORKFLOW_LOCK:
        wf = _WORKFLOW_STATE.get(project_id)
        if wf:
            wf["autoMode"] = auto_mode

    return {"ok": True, "autoMode": auto_mode}

def _handle_workflow_status(project_id):
    """GET /api/projects/{id}/workflow/status — get workflow state."""
    data = _load_projects()
    p = next((x for x in data["projects"] if x["id"] == project_id), None)
    if not p:
        return {"error": "Project not found", "_status": 404}

    with _WORKFLOW_LOCK:
        wf = _WORKFLOW_STATE.get(project_id, {})
        # Detect stale state: persisted says active but thread is dead
        thread = wf.get("thread")
        thread_alive = thread is not None and thread.is_alive() if thread else False

    # Merge with persisted state (for page refresh resilience)
    persisted = _wf_load_persisted_state(project_id)
    in_memory_active = wf.get("active", False)
    persisted_active = persisted.get("active", False)

    # If persisted says active but no thread is running, it's stale — clean up
    if persisted_active and not in_memory_active and not thread_alive:
        _wf_clear_persisted_state(project_id)
        persisted_active = False
        persisted["phase"] = persisted.get("phase", "idle")
        # If the phase was a working phase, mark it as stalled
        if persisted.get("phase") in ("in_progress", "reviewing", "reworking", "dispatching"):
            persisted["phase"] = "stalled"

    active = in_memory_active or persisted_active
    phase = wf.get("phase") or persisted.get("phase", "idle")
    current_task = wf.get("currentTaskId") or persisted.get("currentTaskId")
    error = wf.get("error") or persisted.get("error")
    review_cycle = wf.get("reviewCycle", 0) or persisted.get("reviewCycle", 0)

    # Check if the task-specific session is still actively running in OpenClaw
    # This catches cases where the workflow thread is mid-API-call (active=True in session)
    # but the in-memory state hasn't been updated yet
    session_active = False
    if current_task and not active and phase != "stopped":
        # Find the assignee for the current task
        task = next((t for t in p.get("tasks", []) if t["id"] == current_task), None)
        if task and task.get("assignee"):
            session_active = _wf_is_task_session_active(task["assignee"], project_id, current_task)
            if session_active:
                # Session is running but workflow state says inactive — the thread
                # is mid-API-call. Report as active so UI shows progress.
                active = True
                if phase in ("idle", "stalled", "blocked_by_active_task"):
                    phase = "working"

    return {
        "ok": True,
        "active": active,
        "autoMode": p.get("autoMode", False),
        "currentTaskId": current_task,
        "activeAgent": next((t.get("assignee") for t in p.get("tasks", []) if t.get("id") == current_task), None) if current_task else None,
        "phase": phase,
        "error": error,
        "reviewCycle": review_cycle,
        "sessionActive": session_active,
    }


def _wf_auto_resume_on_startup():
    """Check for workflows that were interrupted by a container restart and resume them.

    Looks for tasks stuck in 'In Progress' or 'Review' columns that have an active
    or done workflow session, indicating the pipeline was mid-execution when killed.
    """
    time.sleep(3)  # Let the server fully start first

    try:
        data = _load_projects()
        for p in data.get("projects", []):
            project_id = p["id"]
            # Find tasks in active columns
            ip_cols = [c["id"] for c in p.get("columns", []) if c.get("title", "").lower() in ("in progress", "review")]
            stuck_tasks = [t for t in p.get("tasks", []) if t.get("columnId") in ip_cols and t.get("assignee")]

            for task in stuck_tasks:
                task_id = task["id"]
                assignee = task["assignee"]
                session_key = _wf_task_session_key(assignee, project_id, task_id)

                # Check if there's a workflow session for this task
                home_path = VO_CONFIG.get("openclaw", {}).get("homePath", os.path.expanduser("~/.openclaw"))
                sessions_json_path = os.path.join(home_path, "agents", assignee, "sessions", "sessions.json")
                try:
                    with open(sessions_json_path, "r") as f:
                        sessions_data = json.load(f)
                    session_info, stored_session_key = _openclaw_get_session_info(sessions_data, assignee, session_key)
                    if session_info:
                        session_status = session_info.get("status", "")
                        if session_status in ("done", "running", "failed"):
                            print(f"[WORKFLOW AUTO-RESUME] Found interrupted task: '{task.get('title', '?')}' (project={project_id[:8]}, session={session_status}, key={stored_session_key})")
                            # Resume the workflow for this project
                            with _WORKFLOW_LOCK:
                                if project_id not in _WORKFLOW_STATE or not _WORKFLOW_STATE.get(project_id, {}).get("active"):
                                    auto_mode = p.get("autoMode", False)
                                    stop_flag = threading.Event()
                                    wf = {
                                        "active": True,
                                        "autoMode": auto_mode,
                                        "currentTaskId": task_id,
                                        "phase": "resuming",
                                        "error": None,
                                        "reviewCycle": 0,
                                        "stopFlag": stop_flag,
                                        "thread": None,
                                    }
                                    _WORKFLOW_STATE[project_id] = wf
                                    t = threading.Thread(target=_wf_run_pipeline, args=(project_id, not auto_mode), daemon=True)
                                    wf["thread"] = t
                                    t.start()
                                    print(f"[WORKFLOW AUTO-RESUME] Resumed pipeline for project {project_id[:8]} (autoMode={auto_mode})")
                            break  # One resume per project
                except (FileNotFoundError, json.JSONDecodeError):
                    pass
    except Exception as e:
        print(f"[WORKFLOW AUTO-RESUME] Error: {e}")


_wrap_exports()
_hydrate()
