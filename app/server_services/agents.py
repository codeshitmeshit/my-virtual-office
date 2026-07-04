"""Agent workspace, platform, and lifecycle service split from server.py."""

import sys

__all__ = ['_handle_agents_list', '_safe_agent_workspace_key', '_load_agent_workspaces', '_save_agent_workspaces', '_find_agent_record', '_agent_workspace_abs_path', '_safe_workspace_relpath', '_resolve_workspace_file', '_read_workspace_text_file', '_save_workspace_text_file', '_delete_workspace_text_file', '_workspace_file_summaries', '_agent_skill_summaries', '_agent_project_tasks', '_agent_recent_activity', '_agent_score_info', '_office_config_agent_override', '_update_office_config_agent', '_get_agent_workspace_payload', '_handle_agent_workspace_update', '_handle_agent_platforms', '_comm_log_path', '_office_agent_lookup', '_office_agent_ref', '_append_comm_event', '_rewrite_comm_events', '_comm_event_progress_marker', '_upsert_comm_progress_event', '_remove_comm_progress_events', '_append_codex_progress_comm_event', '_load_comm_history', '_is_a2a_envelope_text', '_dedupe_visible_comm_history', '_comm_event_to_chat_message', '_merge_comm_events_into_agent_chat', '_handle_agent_platform_comm_send', '_handle_agent_platform_comm_history', '_sanitize_agent_id', '_remove_openclaw_agent_paths', '_run_async_blocking', '_gateway_rpc_call_async', '_gateway_rpc_call', '_agent_template_files', '_default_openclaw_agent_model', '_handle_agent_create', '_handle_hermes_agent_create', '_handle_codex_agent_create', '_handle_claude_code_agent_create', '_write_template', '_signal_gateway_reload', '_handle_agent_delete']


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


def _safe_agent_workspace_key(agent_key):
    return re.sub(r"[^a-zA-Z0-9_.:-]+", "-", str(agent_key or "").strip())[:120]


def _load_agent_workspaces():
    try:
        with open(AGENT_WORKSPACES_FILE, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_agent_workspaces(data):
    os.makedirs(os.path.dirname(AGENT_WORKSPACES_FILE), exist_ok=True)
    with open(AGENT_WORKSPACES_FILE, "w") as f:
        json.dump(data, f, indent=2)
    try:
        os.chmod(AGENT_WORKSPACES_FILE, 0o666)
    except OSError:
        pass


def _find_agent_record(agent_key):
    needle = str(agent_key or "")
    for agent in get_roster():
        values = (
            agent.get("id"),
            agent.get("statusKey"),
            agent.get("providerAgentId"),
            agent.get("profile"),
        )
        if needle in values:
            return agent
    return None


_WORKSPACE_TEXT_EXTS = {
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".env",
    ".py", ".js", ".css", ".html", ".sh", ".csv", ".log",
}
_WORKSPACE_FILE_LIMIT = 256 * 1024


def _agent_workspace_abs_path(agent_key, agent):
    if agent.get("providerKind", "openclaw") != "openclaw":
        return None
    if agent.get("providerKind") in {"codex", "claude-code"}:
        ws = agent.get("workspace") or agent.get("home") or AGENT_WORKSPACES.get(agent_key) or AGENT_WORKSPACES.get(agent.get("statusKey"))
        return os.path.abspath(ws) if ws else None
    ws_dir = AGENT_WORKSPACES.get(agent_key) or AGENT_WORKSPACES.get(agent.get("statusKey"))
    if not ws_dir:
        return None
    return os.path.abspath(os.path.join(WORKSPACE_BASE, ws_dir))


def _safe_workspace_relpath(raw_path):
    rel = str(raw_path or "").replace("\\", "/").strip()
    rel = rel.lstrip("/")
    if not rel or rel in (".", "..") or "\x00" in rel:
        return ""
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return ""
    return "/".join(parts)


def _resolve_workspace_file(agent_key, agent, raw_path, allow_new=False):
    root = _agent_workspace_abs_path(agent_key, agent)
    if not root:
        return None, "", "Workspace files are not available for this platform"
    rel = _safe_workspace_relpath(raw_path)
    if not rel:
        return None, "", "File path required"
    ext = os.path.splitext(rel)[1].lower()
    if ext not in _WORKSPACE_TEXT_EXTS:
        return None, "", "Only text workspace files can be edited"
    full = os.path.abspath(os.path.join(root, rel))
    if full != root and not full.startswith(root + os.sep):
        return None, "", "File must stay inside the agent workspace"
    if not allow_new and not os.path.isfile(full):
        return None, "", "File not found"
    return full, rel, ""


def _read_workspace_text_file(agent_key, agent, relpath):
    full, rel, err = _resolve_workspace_file(agent_key, agent, relpath)
    if err:
        return {"error": err, "_status": 400}
    size = os.path.getsize(full)
    if size > _WORKSPACE_FILE_LIMIT:
        return {"error": "File is too large for dashboard editing", "_status": 413}
    with open(full, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    return {
        "ok": True,
        "file": {
            "name": os.path.basename(rel),
            "path": rel,
            "kind": "workspace",
            "size": size,
            "modified": datetime.fromtimestamp(os.path.getmtime(full), timezone.utc).isoformat(),
            "content": content,
        },
    }


def _save_workspace_text_file(agent_key, agent, relpath, content, create=False):
    full, rel, err = _resolve_workspace_file(agent_key, agent, relpath, allow_new=create)
    if err:
        return {"error": err, "_status": 400}
    text = str(content or "")
    if len(text.encode("utf-8")) > _WORKSPACE_FILE_LIMIT:
        return {"error": "File content is too large", "_status": 413}
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(text)
    return {"ok": True, "saved": rel}


def _delete_workspace_text_file(agent_key, agent, relpath):
    full, rel, err = _resolve_workspace_file(agent_key, agent, relpath)
    if err:
        return {"error": err, "_status": 400}
    os.remove(full)
    return {"ok": True, "deleted": rel}


def _workspace_file_summaries(agent_key, agent):
    provider_kind = agent.get("providerKind", "openclaw")
    if provider_kind == "hermes":
        profile = agent.get("profile") or agent.get("providerAgentId") or "default"
        hist_path = _hermes_history_path(profile)
        files = []
        if os.path.exists(hist_path):
            files.append({
                "name": f"Hermes chat history ({profile})",
                "kind": "history",
                "size": os.path.getsize(hist_path),
                "modified": datetime.fromtimestamp(os.path.getmtime(hist_path), timezone.utc).isoformat(),
            })
        return files
    if provider_kind != "openclaw":
        return []

    ws_path = _agent_workspace_abs_path(agent_key, agent)
    if not ws_path:
        return []
    files = []
    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv"}
    preferred = {"AGENTS.md": -90, "IDENTITY.md": -89, "SOUL.md": -88, "USER.md": -87, "HEARTBEAT.md": -86, "MEMORY.md": -85, "TOOLS.md": -84}
    for root, dirs, names in os.walk(ws_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".cache")]
        depth = os.path.relpath(root, ws_path).count(os.sep)
        if depth > 3:
            dirs[:] = []
        for fname in names:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in _WORKSPACE_TEXT_EXTS:
                continue
            fpath = os.path.join(root, fname)
            try:
                size = os.path.getsize(fpath)
                rel = os.path.relpath(fpath, ws_path).replace(os.sep, "/")
                if size > _WORKSPACE_FILE_LIMIT:
                    kind = "large-text"
                elif rel.startswith("memory/"):
                    kind = "daily-note"
                elif rel.startswith("notes/"):
                    kind = "note-file"
                else:
                    kind = "workspace"
                files.append({
                    "name": fname,
                    "path": rel,
                    "kind": kind,
                    "size": size,
                    "modified": datetime.fromtimestamp(os.path.getmtime(fpath), timezone.utc).isoformat(),
                    "_rank": preferred.get(rel, 0),
                })
            except OSError:
                pass
    files.sort(key=lambda f: (f.pop("_rank", 0), f.get("path", "")))
    return files[:120]


def _agent_skill_summaries(agent_key, agent):
    if agent.get("providerKind", "openclaw") != "openclaw":
        return []
    result = _handle_skill_list(agent_key)
    return [
        {
            "name": s.get("name", ""),
            "type": s.get("type", ""),
            "description": s.get("description", ""),
            "content": s.get("content", ""),
        }
        for s in result.get("skills", [])[:40]
    ]


def _agent_project_tasks(agent):
    aliases = {
        str(agent.get("id") or ""),
        str(agent.get("statusKey") or ""),
        str(agent.get("providerAgentId") or ""),
    }
    aliases.discard("")
    data = _load_projects()
    items = []
    for project in data.get("projects", []):
        columns = {c.get("id"): c.get("title", "") for c in project.get("columns", [])}
        for task in project.get("tasks", []):
            assignee = str(task.get("assignee") or "")
            executor = str(task.get("executorAgentId") or "")
            reviewer = str(task.get("reviewerAgentId") or "")
            if not aliases.intersection({assignee, executor, reviewer}):
                continue
            blocker = task.get("meetingBlocker") if isinstance(task.get("meetingBlocker"), dict) else {}
            attempts = task.get("attempts") if isinstance(task.get("attempts"), list) else []
            active_attempt = next((a for a in attempts if isinstance(a, dict) and a.get("id") == task.get("activeAttemptId")), None)
            items.append({
                "projectId": project.get("id", ""),
                "projectTitle": project.get("title", ""),
                "projectStatus": project.get("status", "active"),
                "projectExecutionEnabled": bool(project.get("projectExecutionEnabled")),
                "projectWorkflowPhase": project.get("workflowPhase") or "",
                "projectExecutionFlowActive": bool(project.get("projectExecutionFlowActive")),
                "projectExecutionFlowStopReason": project.get("projectExecutionFlowStopReason") or "",
                "taskId": task.get("id", ""),
                "id": task.get("id", ""),
                "title": task.get("title", ""),
                "description": task.get("description", ""),
                "priority": task.get("priority", "medium"),
                "column": columns.get(task.get("columnId"), ""),
                "columnId": task.get("columnId", ""),
                "executionState": task.get("executionState") or ("done" if task.get("completedAt") else "backlog"),
                "activeAttemptId": task.get("activeAttemptId") or "",
                "activeAttemptStatus": (active_attempt or {}).get("status", ""),
                "assignee": assignee,
                "executorAgentId": executor,
                "reviewerAgentId": reviewer,
                "role": "executor" if executor in aliases else ("reviewer" if reviewer in aliases else "assignee"),
                "completed": bool(task.get("completedAt")),
                "completedAt": task.get("completedAt") or "",
                "dueDate": task.get("dueDate") or "",
                "blockedReason": task.get("blockedReason") or "",
                "lastError": task.get("lastError") or "",
                "meetingBlocker": {
                    "requestId": blocker.get("requestId") or "",
                    "meetingId": blocker.get("meetingId") or "",
                    "status": blocker.get("status") or "",
                    "awaitingUserDecision": bool(blocker.get("awaitingUserDecision")),
                    "outcome": blocker.get("outcome") or "",
                    "reason": blocker.get("reason") or "",
                } if blocker else {},
                "meetingRecordCount": len(task.get("meetingRecords") if isinstance(task.get("meetingRecords"), list) else []),
                "meetingActionItemCount": len(task.get("meetingActionItems") if isinstance(task.get("meetingActionItems"), list) else []),
                "scheduledRepeatEnabled": task.get("scheduledRepeatEnabled") is True,
                "updatedAt": task.get("updatedAt") or project.get("updatedAt", ""),
                "readOnly": True,
            })
    items.sort(key=lambda x: x.get("updatedAt") or "", reverse=True)
    return items[:25]


def _agent_recent_activity(agent_key, agent):
    if agent.get("providerKind") == "hermes":
        profile = agent.get("profile") or agent.get("providerAgentId") or "default"
        messages = _load_hermes_history(profile)[-80:]
    elif agent.get("providerKind") == "codex":
        messages = []
        for event in _load_comm_history(limit=160, agent_id=agent_key):
            msg = _comm_event_to_chat_message(event, agent_key)
            if msg:
                messages.append(msg)
    else:
        messages = get_agent_messages(agent_key, max_messages=80)
    return messages[-80:] if isinstance(messages, list) else []


def _agent_score_info(agent_key):
    try:
        data = _load_scores()
        return data.get("agents", {}).get(agent_key, {"score": 0, "completed": 0, "streak": 0, "history": []})
    except Exception:
        return {"score": 0, "completed": 0, "streak": 0, "history": []}


def _office_config_agent_override(agent_key):
    path = os.path.join(STATUS_DIR, "office-config.json")
    try:
        with open(path, "r") as f:
            cfg = json.load(f)
    except Exception:
        return {}
    for item in cfg.get("agents", []) or []:
        if agent_key in (item.get("id"), item.get("statusKey")):
            return item
    return {}


def _update_office_config_agent(agent_key, patch):
    path = os.path.join(STATUS_DIR, "office-config.json")
    try:
        with open(path, "r") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    agents = cfg.setdefault("agents", [])
    item = None
    for candidate in agents:
        if agent_key in (candidate.get("id"), candidate.get("statusKey")):
            item = candidate
            break
    if item is None:
        item = {"id": agent_key, "statusKey": agent_key}
        agents.append(item)
    for key, value in patch.items():
        if value is not None:
            item[key] = value
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
    try:
        os.chmod(path, 0o666)
    except OSError:
        pass
    return item


def _get_agent_workspace_payload(agent_key):
    refresh_agent_maps()
    agent = _find_agent_record(agent_key)
    if not agent:
        return {"error": f"Unknown agent: {agent_key}", "_status": 404}

    key = agent.get("statusKey") or agent.get("id") or agent_key
    store_key = _safe_agent_workspace_key(key)
    store = _load_agent_workspaces()
    workspace = store.setdefault(store_key, {})
    workspace.setdefault("bulletin", [])
    workspace.setdefault("tasks", [])
    workspace.setdefault("notes", [])
    workspace.setdefault("settings", {})
    workspace.setdefault("updatedAt", "")

    presence = _get_normalized_presence_state().get(key, {"state": "idle", "task": "", "updated": 0})
    override = _office_config_agent_override(key)
    payload_agent = {
        "id": agent.get("id", key),
        "statusKey": key,
        "providerKind": agent.get("providerKind", "openclaw"),
        "providerType": agent.get("providerType", "runtime"),
        "providerAgentId": agent.get("providerAgentId", agent.get("id", key)),
        "profile": agent.get("profile", ""),
        "name": override.get("name") or agent.get("name", key),
        "displayName": override.get("displayName") or override.get("name") or agent.get("name", key),
        "emoji": override.get("emoji") or agent.get("emoji", "🤖"),
        "role": override.get("role") or agent.get("role", ""),
        "branch": override.get("branch") or agent.get("branch", ""),
        "color": override.get("color", ""),
        "model": agent.get("model", ""),
        "provider": agent.get("provider", ""),
        "lastActiveAt": agent.get("lastActiveAt", 0),
    }
    heartbeat = ""
    if agent.get("providerKind", "openclaw") == "openclaw":
        hb = _resolve_workspace_file(key, agent, "HEARTBEAT.md", allow_new=True)[0]
        if hb and os.path.isfile(hb):
            try:
                with open(hb, "r", encoding="utf-8", errors="replace") as f:
                    heartbeat = f.read()
            except OSError:
                heartbeat = ""
    return {
        "ok": True,
        "agent": payload_agent,
        "presence": presence,
        "workspace": workspace,
        "files": _workspace_file_summaries(key, agent),
        "skills": _agent_skill_summaries(key, agent),
        "skillLibrary": _handle_skills_library_list().get("skills", []),
        "projectTasks": _agent_project_tasks(agent),
        "activity": _agent_recent_activity(key, agent),
        "score": _agent_score_info(key),
        "settings": {
            "heartbeatContent": heartbeat,
            "heartbeatApplicable": agent.get("providerKind", "openclaw") == "openclaw",
            "cronApplicable": agent.get("providerKind", "openclaw") == "openclaw",
            "filesApplicable": agent.get("providerKind", "openclaw") == "openclaw",
            "agentSkillsApplicable": agent.get("providerKind", "openclaw") == "openclaw",
            "skillLibraryApplicable": True,
            "modelEditable": agent.get("providerKind", "openclaw") == "openclaw",
        },
    }


def _handle_agent_workspace_update(agent_key, body):
    payload = _get_agent_workspace_payload(agent_key)
    if not payload.get("ok"):
        return payload
    key = payload["agent"]["statusKey"]
    store_key = _safe_agent_workspace_key(key)
    store = _load_agent_workspaces()
    workspace = store.setdefault(store_key, {"bulletin": [], "tasks": [], "notes": [], "settings": {}})
    workspace.setdefault("bulletin", [])
    workspace.setdefault("tasks", [])
    workspace.setdefault("notes", [])
    workspace.setdefault("settings", {})
    action = (body.get("action") or "").strip()
    now = datetime.now(timezone.utc).isoformat()
    actor = (body.get("actor") or "user").strip()[:80] or "user"
    agent = payload["agent"]

    if action == "addBulletin":
        text = (body.get("text") or "").strip()
        if not text:
            return {"error": "Bulletin text required", "_status": 400}
        workspace.setdefault("bulletin", []).insert(0, {
            "id": str(uuid.uuid4()),
            "text": text[:5000],
            "createdAt": now,
            "createdBy": actor,
            "pinned": bool(body.get("pinned", False)),
        })
        workspace["bulletin"] = workspace["bulletin"][:100]
    elif action == "deleteBulletin":
        item_id = str(body.get("id") or "")
        workspace["bulletin"] = [x for x in workspace.get("bulletin", []) if x.get("id") != item_id]
    elif action == "updateBulletin":
        item_id = str(body.get("id") or "")
        text = (body.get("text") or "").strip()
        for note in workspace.get("bulletin", []):
            if note.get("id") == item_id:
                note["text"] = text[:5000]
                note["updatedAt"] = now
                note["pinned"] = bool(body.get("pinned", note.get("pinned", False)))
                break
    elif action == "addTask":
        text = (body.get("text") or "").strip()
        if not text:
            return {"error": "Task text required", "_status": 400}
        workspace.setdefault("tasks", []).append({
            "id": str(uuid.uuid4()),
            "text": text[:1000],
            "detail": (body.get("detail") or "").strip()[:5000],
            "done": False,
            "status": "queued",
            "priority": (body.get("priority") or "normal").strip()[:40],
            "createdAt": now,
            "createdBy": actor,
            "due": (body.get("due") or "").strip()[:80],
        })
        workspace["tasks"] = workspace["tasks"][:100]
        if not workspace.get("activeTaskId") and workspace.get("settings", {}).get("taskMode") == "single":
            workspace["activeTaskId"] = workspace["tasks"][-1]["id"]
            workspace["tasks"][-1]["status"] = "active"
    elif action == "updateTask":
        item_id = str(body.get("id") or "")
        for task in workspace.get("tasks", []):
            if task.get("id") == item_id:
                task["text"] = (body.get("text") or task.get("text") or "").strip()[:1000]
                task["detail"] = (body.get("detail") or task.get("detail") or "").strip()[:5000]
                task["due"] = (body.get("due") or "").strip()[:80]
                task["priority"] = (body.get("priority") or task.get("priority") or "normal").strip()[:40]
                task["updatedAt"] = now
                break
    elif action == "toggleTask":
        item_id = str(body.get("id") or "")
        for task in workspace.get("tasks", []):
            if task.get("id") == item_id:
                task["done"] = not bool(task.get("done"))
                task["status"] = "done" if task["done"] else "queued"
                task["updatedAt"] = now
                break
    elif action == "startTask":
        item_id = str(body.get("id") or "")
        workspace["activeTaskId"] = item_id
        for task in workspace.get("tasks", []):
            if task.get("done"):
                task["status"] = "done"
            elif task.get("id") == item_id:
                task["status"] = "active"
                task["startedAt"] = now
            elif task.get("status") == "active":
                task["status"] = "queued"
    elif action == "completeTask":
        item_id = str(body.get("id") or workspace.get("activeTaskId") or "")
        for task in workspace.get("tasks", []):
            if task.get("id") == item_id:
                task["done"] = True
                task["status"] = "done"
                task["completedAt"] = now
                task["updatedAt"] = now
                break
        if workspace.get("activeTaskId") == item_id:
            workspace["activeTaskId"] = ""
        if workspace.get("settings", {}).get("taskMode") == "auto":
            for task in workspace.get("tasks", []):
                if not task.get("done"):
                    workspace["activeTaskId"] = task.get("id")
                    task["status"] = "active"
                    task["startedAt"] = now
                    break
    elif action == "deleteTask":
        item_id = str(body.get("id") or "")
        workspace["tasks"] = [x for x in workspace.get("tasks", []) if x.get("id") != item_id]
        if workspace.get("activeTaskId") == item_id:
            workspace["activeTaskId"] = ""
    elif action == "setTaskMode":
        mode = (body.get("mode") or "manual").strip()
        if mode not in ("manual", "single", "auto"):
            return {"error": "Invalid task mode", "_status": 400}
        workspace.setdefault("settings", {})["taskMode"] = mode
    elif action == "addNote":
        title = (body.get("title") or "Untitled note").strip()[:160]
        workspace.setdefault("notes", []).insert(0, {
            "id": str(uuid.uuid4()),
            "title": title or "Untitled note",
            "content": str(body.get("content") or "")[:50000],
            "folder": (body.get("folder") or "General").strip()[:120] or "General",
            "kind": (body.get("kind") or "note").strip()[:40],
            "tags": [str(x).strip()[:40] for x in body.get("tags", []) if str(x).strip()][:12],
            "createdAt": now,
            "updatedAt": now,
            "createdBy": actor,
        })
        workspace["notes"] = workspace["notes"][:300]
    elif action == "updateNote":
        item_id = str(body.get("id") or "")
        for note in workspace.get("notes", []):
            if note.get("id") == item_id:
                note["title"] = (body.get("title") or note.get("title") or "Untitled note").strip()[:160]
                note["content"] = str(body.get("content") or "")[:50000]
                note["folder"] = (body.get("folder") or "General").strip()[:120] or "General"
                note["kind"] = (body.get("kind") or note.get("kind") or "note").strip()[:40]
                note["tags"] = [str(x).strip()[:40] for x in body.get("tags", []) if str(x).strip()][:12]
                note["updatedAt"] = now
                break
    elif action == "deleteNote":
        item_id = str(body.get("id") or "")
        workspace["notes"] = [x for x in workspace.get("notes", []) if x.get("id") != item_id]
    elif action == "readFile":
        return _read_workspace_text_file(key, _find_agent_record(key), body.get("path") or "")
    elif action == "saveFile":
        result = _save_workspace_text_file(key, _find_agent_record(key), body.get("path") or "", body.get("content") or "", create=False)
        if not result.get("ok"):
            return result
    elif action == "createFile":
        result = _save_workspace_text_file(key, _find_agent_record(key), body.get("path") or "", body.get("content") or "", create=True)
        if not result.get("ok"):
            return result
    elif action == "deleteFile":
        result = _delete_workspace_text_file(key, _find_agent_record(key), body.get("path") or "")
        if not result.get("ok"):
            return result
    elif action == "saveAgentSkill":
        if payload["agent"].get("providerKind") != "openclaw":
            return {"error": "Workspace skills are OpenClaw-only for this platform", "_status": 400}
        name = (body.get("name") or "").strip()
        content = str(body.get("content") or "")
        if not content:
            content = f"---\nname: {name or 'new-skill'}\ndescription: \"Agent workflow skill.\"\n---\n\n# {name or 'New Skill'}\n\nUse this skill when...\n"
        result = _handle_skill_write(key, name, {"name": name, "content": content})
        if not result.get("ok"):
            return result
    elif action == "deleteAgentSkill":
        if payload["agent"].get("providerKind") != "openclaw":
            return {"error": "Workspace skills are OpenClaw-only for this platform", "_status": 400}
        result = _handle_skill_delete(key, (body.get("name") or "").strip())
        if not result.get("ok"):
            return result
    elif action == "saveLibrarySkill":
        content = str(body.get("content") or "")
        name = (body.get("name") or "").strip()
        if not content:
            content = f"---\nname: {name or 'new-library-skill'}\ndescription: \"Reusable Virtual Office skill.\"\n---\n\n# {name or 'New Library Skill'}\n\nUse this skill when...\n"
        result = _handle_skills_library_create({"name": name, "content": content})
        if not result.get("ok"):
            return result
    elif action == "applyLibrarySkill":
        if payload["agent"].get("providerKind") != "openclaw":
            return {"error": "Workspace skills are OpenClaw-only for this platform", "_status": 400}
        result = _handle_skills_library_apply({
            "skill": (body.get("name") or "").strip(),
            "agentId": key,
            "overwrite": bool(body.get("overwrite", True)),
        })
        if not result.get("ok") and not result.get("exists"):
            return result
    elif action == "saveAgentSkillToLibrary":
        if payload["agent"].get("providerKind") != "openclaw":
            return {"error": "Workspace skills are OpenClaw-only for this platform", "_status": 400}
        result = _handle_skills_library_save_from_agent({
            "skill": (body.get("name") or "").strip(),
            "agentId": key,
            "overwrite": bool(body.get("overwrite", False)),
        })
        if not result.get("ok"):
            return result
    elif action == "updateSettings":
        settings = workspace.setdefault("settings", {})
        for field in ("taskMode", "heartbeatMinutes", "cronEnabled", "displayName", "branch", "leaderboardPoints"):
            if field in body:
                settings[field] = body.get(field)
        if "leaderboardPoints" in body:
            try:
                scores = _load_scores()
                score_entry = scores.setdefault("agents", {}).setdefault(key, {"score": 0, "completed": 0, "streak": 0, "history": []})
                score_entry["score"] = int(body.get("leaderboardPoints") or 0)
                _save_scores(scores)
            except Exception:
                pass
        if "heartbeatContent" in body:
            if payload["agent"].get("providerKind") != "openclaw":
                return {"error": "Heartbeats are OpenClaw-only for this platform", "_status": 400}
            result = _save_workspace_text_file(key, _find_agent_record(key), "HEARTBEAT.md", body.get("heartbeatContent") or "", create=True)
            if not result.get("ok"):
                return result
        patch = {}
        for field in ("name", "displayName", "role", "branch", "emoji", "color"):
            if field in body:
                patch[field] = str(body.get(field) or "").strip()
        if patch:
            _update_office_config_agent(key, patch)
    else:
        return {"error": f"Unknown action: {action}", "_status": 400}

    workspace["updatedAt"] = now
    store[store_key] = workspace
    _save_agent_workspaces(store)
    return _get_agent_workspace_payload(key)


def _handle_agent_platforms():
    """Return agent platforms available to the New Agent workflow."""
    hermes_cfg = VO_CONFIG.get("hermes", {})
    hermes_status = HermesProvider(
        home_path=hermes_cfg.get("homePath"),
        binary=hermes_cfg.get("binary"),
        enabled=hermes_cfg.get("enabled", True),
    ).test()
    codex_status = _handle_codex_test()
    claude_code_status = _handle_claude_code_test()
    return {
        "ok": True,
        "platforms": [
            {
                "id": "openclaw",
                "label": "OpenClaw",
                "description": "Native OpenClaw workspace agent",
                "providerType": "runtime",
                "available": True,
                "create": True,
                "delete": True,
            },
            {
                "id": "hermes",
                "label": "Hermes",
                "description": "Hermes profile-backed agent",
                "providerType": "runtime",
                "available": bool(hermes_status.get("ok")),
                "create": bool(hermes_status.get("ok")),
                "delete": bool(hermes_status.get("ok")),
                "error": "" if hermes_status.get("ok") else hermes_status.get("error", "Hermes is not available"),
            },
            {
                "id": "codex",
                "label": "Codex",
                "description": "Codex app-server bridge and native agent workspaces",
                "available": bool(codex_status.get("ok")),
                "create": bool(codex_status.get("ok")),
                "delete": bool(codex_status.get("ok")),
                "error": "" if codex_status.get("ok") else codex_status.get("error", "Codex harness is disabled"),
            },
            {
                "id": "claude-code",
                "label": "Claude Code",
                "description": "Claude Code CLI and native subagent workspaces",
                "available": bool(claude_code_status.get("ok")),
                "create": bool(claude_code_status.get("ok")),
                "delete": bool(claude_code_status.get("ok")),
                "error": "" if claude_code_status.get("ok") else claude_code_status.get("error", "Claude Code provider is disabled"),
            },
        ],
    }


# ─── AGENT PLATFORM COMMUNICATION LAYER ─────────────────────────

def _comm_log_path():
    return os.path.join(STATUS_DIR, "agent-platform-communications.jsonl")


def _office_agent_lookup(agent_id_or_key):
    needle = str(agent_id_or_key or "").strip()
    for agent in get_roster():
        aliases = {
            str(agent.get("id") or ""),
            str(agent.get("statusKey") or ""),
            str(agent.get("providerAgentId") or ""),
        }
        if needle in aliases:
            return agent
    return None


def _office_agent_ref(agent_id_or_key):
    agent = _office_agent_lookup(agent_id_or_key)
    if agent:
        return {
            "id": agent.get("statusKey") or agent.get("id"),
            "nativeId": agent.get("providerAgentId") or agent.get("id"),
            "providerKind": agent.get("providerKind", "openclaw"),
            "name": agent.get("name") or agent.get("id"),
            "emoji": agent.get("emoji") or "",
        }
    return {
        "id": str(agent_id_or_key or ""),
        "nativeId": str(agent_id_or_key or ""),
        "providerKind": "unknown",
        "name": str(agent_id_or_key or ""),
        "emoji": "",
    }


def _append_comm_event(event):
    event = dict(event)
    if "text" in event:
        event["text"] = _extract_openclaw_text(event.get("text"))
    event.setdefault("ts", int(time.time() * 1000))
    event.setdefault("id", str(uuid.uuid4()))
    event.setdefault("schema", "vo.agent-platform-communication.v1")
    path = _comm_log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        try:
            os.chmod(path, 0o666)
        except OSError:
            pass
    except OSError as e:
        print(f"[COMM] Failed to append communication event: {e}")
    return event


def _rewrite_comm_events(events):
    path = _comm_log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w") as f:
            for event in events or []:
                if isinstance(event, dict):
                    f.write(json.dumps(event, ensure_ascii=False) + "\n")
        os.replace(tmp_path, path)
        try:
            os.chmod(path, 0o666)
        except OSError:
            pass
    except OSError as e:
        print(f"[COMM] Failed to rewrite communication history: {e}")


def _comm_event_progress_marker(event):
    metadata = event.get("metadata") if isinstance(event, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    return metadata.get("ephemeral") or event.get("ephemeral"), metadata.get("progressId") or event.get("progressId")


def _upsert_comm_progress_event(event, ephemeral, progress_id):
    event = dict(event)
    if "text" in event:
        event["text"] = _extract_openclaw_text(event.get("text"))
    event.setdefault("ts", int(time.time() * 1000))
    event.setdefault("id", str(uuid.uuid4()))
    event.setdefault("schema", "vo.agent-platform-communication.v1")
    conversation_id = event.get("conversationId") or ""
    events = _load_comm_history(limit=1000)
    kept = []
    for item in events:
        item_ephemeral, item_progress_id = _comm_event_progress_marker(item)
        if (
            item.get("conversationId") == conversation_id
            and item_ephemeral == ephemeral
            and item_progress_id == progress_id
        ):
            continue
        kept.append(item)
    kept.append(event)
    _rewrite_comm_events(kept)
    return event


def _remove_comm_progress_events(ephemeral, progress_id=None, conversation_id=None):
    events = _load_comm_history(limit=1000)
    kept = []
    for item in events:
        item_ephemeral, item_progress_id = _comm_event_progress_marker(item)
        if item_ephemeral != ephemeral:
            kept.append(item)
            continue
        if progress_id and item_progress_id != progress_id:
            kept.append(item)
            continue
        if conversation_id and item.get("conversationId") != conversation_id:
            kept.append(item)
            continue
    _rewrite_comm_events(kept)


def _append_codex_progress_comm_event(agent, agent_id, conversation_id, progress_id, run_state):
    if not conversation_id or not progress_id:
        return None
    run_state = run_state if isinstance(run_state, dict) else {}
    progress_message = _provider_progress_message(
        "codex",
        agent_id,
        progress_id,
        run_state,
        conversation_id,
        "Waiting for Codex run events.",
    )
    status = progress_message.get("status") or run_state.get("status") or "running"
    event_text = f"Codex progress: {status}"
    return _upsert_comm_progress_event({
        "type": "operation",
        "operation": "provider_progress",
        "direction": "progress",
        "conversationId": conversation_id,
        "from": _office_agent_ref(agent_id),
        "to": {"id": "user", "providerKind": "human", "name": "User"},
        "text": event_text,
        "metadata": {
            "providerKind": "codex",
            "ephemeral": "codex-progress",
            "progressId": progress_id,
            "progress": progress_message,
        },
        "visibleInOffice": False,
    }, "codex-progress", progress_id)


def _load_comm_history(limit=200, conversation_id=None, agent_id=None):
    path = _comm_log_path()
    events = []
    try:
        with open(path, "r") as f:
            for line in f:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if conversation_id and event.get("conversationId") != conversation_id:
                    continue
                if agent_id:
                    src = (event.get("from") or {}).get("id")
                    dst = (event.get("to") or {}).get("id")
                    if agent_id not in (src, dst):
                        continue
                events.append(event)
    except FileNotFoundError:
        pass
    except OSError as e:
        print(f"[COMM] Failed to load communication history: {e}")
    return events[-max(1, min(int(limit or 200), 1000)):]


def _is_a2a_envelope_text(text):
    value = str(text or "")
    return value.startswith("[A2A ") and "Message from " in value and "Reply directly to the sender" in value


def _dedupe_visible_comm_history(events):
    deduped = []
    seen = set()
    for event in events or []:
        if _is_a2a_envelope_text(event.get("text") if isinstance(event, dict) else ""):
            continue
        event_id = event.get("id") or ""
        if event_id:
            key = ("id", event_id)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(event)
            continue
        direction = event.get("direction") or ""
        key = (
            event.get("conversationId") or "",
            direction,
            (event.get("from") or {}).get("id") or "",
            (event.get("to") or {}).get("id") or "",
            event.get("text") or "",
            "" if direction == "reply" else event.get("inReplyTo") or "",
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)
    return deduped


def _comm_event_to_chat_message(event, agent_key):
    """Convert a communication event into the existing bubble message shape."""
    from_ref = event.get("from") or {}
    to_ref = event.get("to") or {}
    from_id = from_ref.get("id", "")
    to_id = to_ref.get("id", "")
    text = _extract_openclaw_text(event.get("text", ""))
    if not text:
        return None
    from_label = (from_ref.get("name") or from_id or "Agent").strip()
    to_label = (to_ref.get("name") or to_id or "Agent").strip()
    # For an agent's own outgoing message, show it like assistant speech.
    # Incoming messages keep role=user so the bubble renderer prefixes sender.
    role = "assistant" if from_id == agent_key else "user"
    return {
        "role": role,
        "text": text,
        "ts": event.get("ts", 0),
        "epochMs": event.get("ts", 0),
        "from": from_label,
        "fromAgentId": from_id,
        "to": to_label,
        "toAgentId": to_id,
        "conversationId": event.get("conversationId", ""),
        "source": "agent-platform-communications",
        "commEventId": event.get("id", ""),
    }


def _merge_comm_events_into_agent_chat(result, per_agent_limit=500):
    """Merge visible cross-platform comm events into /agent-chat payload.

    Chat bubbles are supposed to show the latest real agent conversation,
    regardless of whether it came from an OpenClaw transcript, Hermes history,
    or the office-mediated cross-platform communication layer.
    """
    events = _load_comm_history(limit=1000)
    if not events:
        return result
    valid_keys = set(AGENT_SESSION_IDS.keys()) | {a.get("statusKey") or a.get("id") for a in get_roster()}
    for event in events:
        if not event.get("visibleInOffice", True):
            continue
        refs = [event.get("from") or {}, event.get("to") or {}]
        for ref in refs:
            agent_key = ref.get("id")
            if not agent_key or agent_key not in valid_keys:
                continue
            msg = _comm_event_to_chat_message(event, agent_key)
            if not msg:
                continue
            result.setdefault(agent_key, []).append(msg)

    # Sort/dedupe/trim so each bubble follows true recency.
    for agent_key, msgs in list(result.items()):
        seen = set()
        cleaned = []
        for msg in msgs:
            msg_text = _extract_openclaw_text(msg.get("text"))
            if not msg_text and not msg.get("media") and not msg.get("tools"):
                continue
            if msg.get("text") != msg_text:
                msg = dict(msg)
                msg["text"] = msg_text
            tool_sig = ""
            if msg.get("tools"):
                tool_sig = json.dumps([
                    {
                        "id": t.get("id"),
                        "name": t.get("name"),
                        "status": t.get("status"),
                    }
                    for t in (msg.get("tools") or [])
                    if isinstance(t, dict)
                ], sort_keys=True)
            unique = msg.get("commEventId") or (msg.get("role"), msg_text, tool_sig, msg.get("epochMs") or msg.get("ts") or msg.get("time"))
            if str(unique) in seen:
                continue
            seen.add(str(unique))
            cleaned.append(msg)
        cleaned.sort(key=lambda m: int(m.get("epochMs") or m.get("ts") or 0))
        # Provider calls may also write their own local history (Hermes does).
        # Prefer the communication-layer copy because it preserves from/to
        # context needed for visible cross-platform bubbles.
        comm_signatures = set()
        for msg in cleaned:
            if msg.get("source") == "agent-platform-communications":
                ts = int(msg.get("epochMs") or msg.get("ts") or 0)
                comm_signatures.add((msg.get("role"), _extract_openclaw_text(msg.get("text")), ts // 5000))
        if comm_signatures:
            filtered = []
            for msg in cleaned:
                if msg.get("source") == "agent-platform-communications":
                    filtered.append(msg)
                    continue
                raw_text = _extract_openclaw_text(msg.get("text"))
                if raw_text.lstrip().startswith("[A2A ") or "via My Virtual Office AgentPlatform-to-AgentPlatform Communications" in raw_text:
                    continue
                ts = int(msg.get("epochMs") or msg.get("ts") or 0)
                msg_text = _extract_openclaw_text(msg.get("text"))
                sigs = [(msg.get("role"), msg_text, ts // 5000), (msg.get("role"), msg_text, (ts // 5000) - 1), (msg.get("role"), msg_text, (ts // 5000) + 1)]
                if any(sig in comm_signatures for sig in sigs):
                    continue
                filtered.append(msg)
            cleaned = filtered
        result[agent_key] = cleaned[-per_agent_limit:]
    return result


def _handle_agent_platform_comm_send(body):
    """Send a visible office-mediated message between provider agents.

    The sender/target may be OpenClaw, Hermes, or future provider agents. The
    actual provider routing uses the existing agent-call abstraction, while the
    office owns the cross-platform log that future chat bubbles can render.
    """
    from_type = str(body.get("fromType") or body.get("senderType") or "agent").strip().lower()
    from_agent_id = (body.get("fromAgentId") or body.get("from") or "").strip()
    to_agent_id = (body.get("toAgentId") or body.get("to") or "").strip()
    message = (body.get("message") or body.get("text") or "").strip()
    is_human_source = from_type in {"human", "user", "chat", "ui"}
    if not from_agent_id and not is_human_source:
        return {"ok": False, "error": "fromAgentId is required", "_status": 400}
    if not to_agent_id:
        return {"ok": False, "error": "toAgentId is required", "_status": 400}
    if not message:
        return {"ok": False, "error": "message is required", "_status": 400}

    to_agent = _office_agent_lookup(to_agent_id)
    if not to_agent:
        return {"ok": False, "error": f"Target agent '{to_agent_id}' not found", "_status": 404}
    archive_guard = _archive_manager_chat_guard(to_agent_id, message)

    source_app = str(body.get("sourceApp") or body.get("app") or "virtual-office").strip() or "virtual-office"
    source_surface = str(body.get("sourceSurface") or body.get("surface") or "agent-platform").strip() or "agent-platform"
    source_label = str(body.get("sourceLabel") or "").strip()
    if is_human_source:
        display_name = str(body.get("fromDisplayName") or body.get("displayName") or body.get("fromName") or "User").strip() or "User"
        from_ref = {
            "id": str(body.get("fromId") or body.get("fromUserId") or "user").strip() or "user",
            "nativeId": str(body.get("fromId") or body.get("fromUserId") or "user").strip() or "user",
            "providerKind": "human",
            "providerType": "chat-window",
            "name": display_name,
            "emoji": "",
            "sourceApp": source_app,
            "sourceSurface": source_surface,
            "sourceLabel": source_label,
        }
    else:
        from_ref = _office_agent_ref(from_agent_id)
    to_ref = _office_agent_ref(to_agent_id)
    conversation_id = (body.get("conversationId") or body.get("threadId") or f"{from_ref['id']}__{to_ref['id']}").strip()
    metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    metadata = dict(metadata)
    metadata.setdefault("sourceApp", source_app)
    metadata.setdefault("sourceSurface", source_surface)
    if source_label:
        metadata.setdefault("sourceLabel", source_label)
    timeout = int(body.get("timeoutSec") or body.get("timeout") or 600)

    inbound = _append_comm_event({
        "type": "message",
        "direction": "request",
        "conversationId": conversation_id,
        "from": from_ref,
        "to": to_ref,
        "text": message,
        "metadata": metadata,
        "visibleInOffice": True,
    })
    if archive_guard:
        outbound = _append_comm_event({
            "type": "message",
            "direction": "reply",
            "conversationId": conversation_id,
            "from": to_ref,
            "to": from_ref,
            "text": archive_guard["reply"],
            "inReplyTo": inbound["id"],
            "metadata": metadata,
            "visibleInOffice": True,
            "ok": True,
        })
        return {
            "ok": True,
            "conversationId": conversation_id,
            "messageId": inbound["id"],
            "replyMessageId": outbound["id"],
            "from": from_ref,
            "to": to_ref,
            "reply": archive_guard["reply"],
            "status": archive_guard["status"],
            "modifiedFiles": [],
            "needsHumanIntervention": False,
            "activeConversationId": "",
            "activeStatus": "",
        }

    provider_prefixes = {
        "openclaw": "OpenClaw",
        "hermes": "Hermes",
        "codex": "Codex",
        "claude-code": "Claude Code",
    }
    if is_human_source:
        sender_label = from_ref.get("name") or "User"
        pretty_surface = source_label or ("Virtual Office Chat" if source_app == "virtual-office" and source_surface in {"chat-window", "chat"} else f"{source_app.replace('-', ' ').title()} {source_surface.replace('-', ' ').title()}".strip())
        envelope_source = pretty_surface
    else:
        provider_label = provider_prefixes.get(str(from_ref.get("providerKind") or "").lower(), str(from_ref.get("providerKind") or "Agent").replace("-", " ").title())
        base_name = f"{from_ref.get('name') or from_ref['id']} {from_ref.get('emoji') or ''}".strip()
        sender_label = f"{provider_label}: {base_name}" if provider_label else base_name
        envelope_source = "My Virtual Office AgentPlatform-to-AgentPlatform Communications"
    target_prompt = (
        f"[A2A from={from_ref['id']} name={json.dumps(sender_label)} to={to_ref['id']} isUser={'true' if is_human_source else 'false'} sourceApp={json.dumps(source_app)} sourceSurface={json.dumps(source_surface)}]\n"
        f"Message from {sender_label} via {envelope_source}.\n\n"
        f"{message}\n\n"
        "Reply directly to the sender. Keep the reply concise unless detail is needed."
    )

    gateway_presence.set_manual_override(to_ref["id"], "working", f"Replying to {sender_label}")
    provider_result = None
    try:
        if str(to_ref.get("providerKind") or "").lower() == "codex":
            provider_result = _handle_codex_chat({
                "agentId": to_ref["id"],
                "message": target_prompt,
                "timeoutSec": timeout,
                "conversationId": conversation_id,
                "fromType": "human" if is_human_source else "agent",
            })
            reply = provider_result.get("reply") or provider_result.get("error") or ""
            ok = bool(provider_result.get("ok"))
        elif str(to_ref.get("providerKind") or "").lower() == "claude-code":
            provider_result = _handle_claude_code_chat({
                "agentId": to_ref["id"],
                "message": target_prompt,
                "timeoutSec": timeout,
                "conversationId": conversation_id,
                "fromType": "human" if is_human_source else "agent",
            })
            reply = provider_result.get("reply") or provider_result.get("error") or ""
            ok = bool(provider_result.get("ok"))
        else:
            reply = _wf_call_agent(to_ref["id"], target_prompt, timeout=timeout, project_id="agent-platform-communications", task_id=conversation_id)
            ok = not str(reply or "").startswith("[ERROR]")
    except Exception as e:
        reply = f"[ERROR] {e}"
        ok = False
    finally:
        gateway_presence.set_manual_override(to_ref["id"], "idle", "")

    outbound_metadata = dict(metadata)
    if provider_result:
        outbound_metadata["codex"] = {
            "status": provider_result.get("status"),
            "errorCode": provider_result.get("errorCode"),
            "threadId": provider_result.get("threadId"),
            "turnId": provider_result.get("turnId"),
            "modifiedFiles": provider_result.get("modifiedFiles") or [],
            "needsHumanIntervention": bool(provider_result.get("needsHumanIntervention")),
            "durationMs": provider_result.get("durationMs"),
        }
    outbound = _append_comm_event({
        "type": "message",
        "direction": "reply",
        "conversationId": conversation_id,
        "from": to_ref,
        "to": from_ref,
        "text": reply,
        "inReplyTo": inbound["id"],
        "metadata": outbound_metadata,
        "visibleInOffice": True,
        "ok": ok,
    })

    return {
        "ok": ok,
        "conversationId": conversation_id,
        "messageId": inbound["id"],
        "replyMessageId": outbound["id"],
        "from": from_ref,
        "to": to_ref,
        "reply": reply,
        "status": provider_result.get("status") if provider_result else ("completed" if ok else "execution_failed"),
        "modifiedFiles": provider_result.get("modifiedFiles") if provider_result else [],
        "needsHumanIntervention": bool(provider_result and provider_result.get("needsHumanIntervention")),
        "activeConversationId": provider_result.get("activeConversationId", "") if provider_result else "",
        "activeStatus": provider_result.get("activeStatus", "") if provider_result else "",
    }


def _handle_agent_platform_comm_history(query):
    limit = int((query.get("limit") or [200])[0] or 200)
    conversation_id = (query.get("conversationId") or query.get("threadId") or [None])[0]
    agent_id = (query.get("agentId") or [None])[0]
    return {"ok": True, "events": _load_comm_history(limit=limit, conversation_id=conversation_id, agent_id=agent_id)}


def _sanitize_agent_id(name):
    """Convert a display name into a safe agent ID."""
    s = name.lower().strip()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s]+', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s or f"agent-{int(time.time())}"

def _remove_openclaw_agent_paths(agent_id):
    """Remove local OpenClaw agent/workspace leftovers after Gateway deletion."""
    safe_id = _sanitize_agent_id(agent_id)
    if safe_id != agent_id:
        raise ValueError("Unsafe agent ID")

    base = os.path.realpath(WORKSPACE_BASE)
    targets = [
        os.path.join(base, "agents", safe_id),
        os.path.join(base, f"workspace-{safe_id}"),
    ]
    for target in targets:
        real_target = os.path.realpath(target)
        if not (real_target == base or real_target.startswith(base + os.sep)):
            raise ValueError(f"Refusing to remove path outside OpenClaw home: {target}")
        try:
            if os.path.islink(target) or os.path.isfile(target):
                os.remove(target)
            elif os.path.isdir(target):
                shutil.rmtree(target)
        except FileNotFoundError:
            pass

def _run_async_blocking(coro, timeout=30):
    """Run an async Gateway helper from either sync or async server code."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result(timeout=timeout)

async def _gateway_rpc_call_async(method, params=None, timeout=20):
    """Call an OpenClaw Gateway RPC as the Virtual Office server."""
    token = _get_gateway_token()
    if not token:
        return {"ok": False, "error": "Gateway token is not configured"}
    gw_url = VO_CONFIG.get("openclaw", {}).get("gatewayUrl", "ws://127.0.0.1:18789")
    origin = f"http://127.0.0.1:{PORT}"
    async with ws_connect(
        gw_url,
        max_size=1024 * 1024,
        additional_headers={"Origin": origin},
        close_timeout=3,
    ) as ws:
        await asyncio.wait_for(ws.recv(), timeout=5)
        connect_id = f"vo-agent-admin-connect-{uuid.uuid4()}"
        await ws.send(json.dumps({
            "type": "req",
            "id": connect_id,
            "method": "connect",
            "params": {
                "minProtocol": 4,
                "maxProtocol": 4,
                "client": {"id": "openclaw-control-ui", "version": _get_openclaw_version(), "platform": "server", "mode": "webchat"},
                "role": "operator",
                "scopes": ["operator.read", "operator.write", "operator.admin"],
                "caps": [],
                "commands": [],
                "permissions": {},
                "auth": {"token": token},
                "locale": "en-US",
                "userAgent": "virtual-office-server/agent-admin",
            },
        }))
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            if msg.get("id") == connect_id:
                if not msg.get("ok"):
                    return {"ok": False, "error": msg.get("error", {}).get("message", "Gateway connect failed")}
                break

        req_id = f"vo-agent-admin-{uuid.uuid4()}"
        await ws.send(json.dumps({
            "type": "req",
            "id": req_id,
            "method": method,
            "params": params or {},
        }))
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=min(10, max(1, deadline - time.time()))))
            if msg.get("id") != req_id:
                continue
            if not msg.get("ok"):
                return {"ok": False, "error": msg.get("error", {}).get("message", f"{method} failed")}
            payload = msg.get("payload")
            if isinstance(payload, dict):
                payload.setdefault("ok", True)
                return payload
            return {"ok": True, "payload": payload}
    return {"ok": False, "error": f"{method} timed out"}

def _gateway_rpc_call(method, params=None, timeout=20):
    try:
        return _run_async_blocking(_gateway_rpc_call_async(method, params=params, timeout=timeout), timeout=timeout + 10)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def _agent_template_files(name, role, emoji, agent_kind="OpenClaw"):
    """Return non-secret bootstrap files for a newly-created agent workspace."""
    return {
        "IDENTITY.md": f"""# IDENTITY.md

- **Name:** {name}
- **Creature:** {role} — {agent_kind} agent
- **Vibe:** Helpful, efficient, ready to work
- **Emoji:** {emoji}
""",
        "SOUL.md": f"""# SOUL.md — {name}

You are **{name}** {emoji} — {role}.

## Style
- Be helpful and direct
- Follow your AGENTS.md workflow strictly
- Keep work visible through Virtual Office when possible
""",
        "USER.md": """# USER.md

- **Name:** (set by your owner)
- **Timezone:** (set by your owner)
- **Notes:** Prefers direct, clear communication.
""",
        "AGENTS.md": f"""# {name} {emoji} — {role}

## Role
{role}

## Core Rules
- Follow instructions carefully
- Log your work in memory/YYYY-MM-DD.md when useful
- Complete the full loop: working → work → report → idle

## Communication
- Use Virtual Office communication tools when talking to other office agents
- Your text reply IS your response — write it directly

## Memory
- Daily logs: `memory/YYYY-MM-DD.md`
- Long-term: `MEMORY.md`
""",
        "HEARTBEAT.md": """# HEARTBEAT.md

# Add periodic tasks below. If nothing needs attention, reply HEARTBEAT_OK.
""",
        "MEMORY.md": f"# MEMORY.md - {name}\n\n_No memories yet._\n",
        "TOOLS.md": f"# TOOLS.md — {name}\n\n_Add tool-specific notes here._\n",
    }

def _default_openclaw_agent_model():
    """Prefer the running main agent's model over stale global defaults."""
    result = _gateway_rpc_call("agents.list", {}, timeout=10)
    if not result.get("ok"):
        return ""
    for agent in result.get("agents", []):
        if agent.get("id") == "main":
            model = agent.get("model")
            if isinstance(model, dict):
                return str(model.get("primary") or "")
            if isinstance(model, str):
                return model
    return ""

def _handle_agent_create(body):
    """Create a new agent from the VO app."""
    name = (body.get("name") or "").strip()
    if not name:
        return {"error": "Agent name is required", "_status": 400}

    platform = (body.get("agentPlatform") or body.get("platform") or body.get("providerKind") or "openclaw").strip().lower()
    if platform in {"hermes", "hermes-agent"}:
        return _handle_hermes_agent_create(body, name)
    if platform in {"codex", "codex-agent"}:
        return _handle_codex_agent_create(body, name)
    if platform in {"claude-code", "claude_code", "claude-code-agent"}:
        return _handle_claude_code_agent_create(body, name)
    if platform not in {"openclaw", "openclaw-agent"}:
        return {"error": f"Unsupported agent platform '{platform}'", "_status": 400}

    agent_id = _sanitize_agent_id(body.get("id") or name)
    emoji = body.get("emoji", "🤖")
    role = body.get("role", "AI assistant")
    model = body.get("model", "")
    workspace_dir = os.path.join(WORKSPACE_BASE, f"workspace-{agent_id}")

    try:
        create_params = {"name": name, "workspace": workspace_dir, "emoji": emoji}
        selected_model = model or _default_openclaw_agent_model()
        if selected_model:
            create_params["model"] = selected_model
        result = _gateway_rpc_call("agents.create", create_params, timeout=30)
        if not result.get("ok"):
            status = 409 if "already exists" in str(result.get("error", "")).lower() else 500
            return {"error": result.get("error", "OpenClaw agent creation failed"), "_status": status}

        agent_id = result.get("agentId") or agent_id
        for filename, content in _agent_template_files(name, role, emoji, "OpenClaw").items():
            file_result = _gateway_rpc_call("agents.files.set", {"agentId": agent_id, "name": filename, "content": content}, timeout=20)
            if not file_result.get("ok"):
                return {"error": f"Agent created but failed to write {filename}: {file_result.get('error', 'unknown error')}", "_status": 500}

        # Refresh discovery
        global _discovered_at
        _discovered_at = 0
        refresh_agent_maps()

        return {
            "ok": True,
            "agentId": agent_id,
            "name": name,
            "workspace": workspace_dir,
            "message": f"Agent '{name}' ({agent_id}) created successfully"
        }

    except Exception as e:
        traceback.print_exc()
        return {"error": str(e), "_status": 500}

def _handle_hermes_agent_create(body, name):
    emoji = body.get("emoji", "⚕️")
    role = body.get("role", "Hermes Agent")
    model = body.get("model", "")
    profile = body.get("id") or body.get("profile") or _sanitize_agent_id(name)
    provider = HermesProvider(
        home_path=VO_CONFIG.get("hermes", {}).get("homePath"),
        binary=VO_CONFIG.get("hermes", {}).get("binary"),
        enabled=VO_CONFIG.get("hermes", {}).get("enabled", True),
        timeout_sec=VO_CONFIG.get("hermes", {}).get("timeoutSec", 600),
    )
    result = provider.create_agent(name=name, role=role, model=model, emoji=emoji, profile=profile)
    if not result.get("ok"):
        return {"error": result.get("error", "Hermes agent creation failed"), "_status": 500}
    global _discovered_at
    _discovered_at = 0
    refresh_agent_maps()
    return {
        "ok": True,
        "agentId": result.get("agentId"),
        "providerKind": "hermes",
        "providerAgentId": result.get("profile"),
        "profile": result.get("profile"),
        "name": name,
        "workspace": result.get("workspace"),
        "message": result.get("message", f"Hermes agent '{name}' created successfully"),
    }


def _handle_codex_agent_create(body, name):
    emoji = body.get("emoji", "🤖")
    role = body.get("role", "Codex Agent")
    prompt = body.get("prompt") or body.get("systemPrompt") or body.get("instructions") or role
    model = body.get("model") or VO_CONFIG.get("codex", {}).get("model", "")
    profile = body.get("id") or body.get("profile") or _sanitize_agent_id(name)
    creation_mode = body.get("codexCreationMode") or body.get("creationMode") or body.get("agentDirectoryMode") or "standard"
    custom_directory = body.get("codexCustomDirectory") or body.get("customDirectory") or body.get("agentDirectory") or ""
    result = _codex_provider_from_config().create_agent(
        name=name,
        role=role,
        model=model,
        emoji=emoji,
        profile=profile,
        prompt=prompt,
        creation_mode=creation_mode,
        custom_directory=custom_directory,
    )
    if not result.get("ok"):
        return {"error": result.get("error", "Codex agent creation failed"), "_status": 500}
    global _discovered_at
    _discovered_at = 0
    refresh_agent_maps()
    return {
        "ok": True,
        "agentId": result.get("agentId"),
        "providerKind": "codex",
        "providerType": "app-server-bridge",
        "providerAgentId": result.get("profile"),
        "profile": result.get("profile"),
        "name": name,
        "workspace": result.get("workspace"),
        "creationMode": result.get("creationMode"),
        "nativeAgentPath": result.get("nativeAgentPath"),
        "message": result.get("message", f"Codex agent '{name}' created successfully"),
    }


def _handle_claude_code_agent_create(body, name):
    emoji = body.get("emoji", "🤖")
    role = body.get("role", "Claude Code Agent")
    prompt = body.get("prompt") or body.get("systemPrompt") or body.get("instructions") or role
    model = body.get("model") or VO_CONFIG.get("claudeCode", {}).get("model", "")
    profile = body.get("id") or body.get("profile") or _sanitize_agent_id(name)
    creation_mode = body.get("claudeCodeCreationMode") or body.get("creationMode") or body.get("agentDirectoryMode") or "standard"
    custom_directory = body.get("claudeCodeCustomDirectory") or body.get("customDirectory") or body.get("agentDirectory") or ""
    result = _claude_code_provider_from_config().create_agent(
        name=name,
        role=role,
        model=model,
        emoji=emoji,
        profile=profile,
        prompt=prompt,
        creation_mode=creation_mode,
        custom_directory=custom_directory,
    )
    if not result.get("ok"):
        return {"error": result.get("error", "Claude Code agent creation failed"), "_status": 500}
    global _discovered_at
    _discovered_at = 0
    refresh_agent_maps()
    return {
        "ok": True,
        "agentId": result.get("agentId"),
        "providerKind": "claude-code",
        "providerType": "harness",
        "providerAgentId": result.get("profile"),
        "profile": result.get("profile"),
        "name": name,
        "workspace": result.get("workspace"),
        "creationMode": result.get("creationMode"),
        "nativeAgentPath": result.get("nativeAgentPath"),
        "message": result.get("message", f"Claude Code agent '{name}' created successfully"),
    }


def _write_template(workspace_dir, filename, content):
    """Write a template file to a workspace."""
    with open(os.path.join(workspace_dir, filename), "w") as f:
        f.write(content)


def _signal_gateway_reload():
    """Send SIGUSR1 to the OpenClaw gateway process to reload config."""
    try:
        # Find gateway PID from proc
        for pid_dir in os.listdir("/proc"):
            if not pid_dir.isdigit():
                continue
            try:
                with open(f"/proc/{pid_dir}/cmdline", "r") as f:
                    cmdline = f.read()
                if "openclaw" in cmdline and "gateway" in cmdline:
                    os.kill(int(pid_dir), signal.SIGUSR1)
                    return True
            except (PermissionError, FileNotFoundError, ProcessLookupError):
                continue
        # Fallback: try common PID file locations
        for pidfile in ["/tmp/openclaw-gateway.pid", os.path.join(WORKSPACE_BASE, "gateway.pid")]:
            if os.path.exists(pidfile):
                with open(pidfile) as f:
                    pid = int(f.read().strip())
                os.kill(pid, signal.SIGUSR1)
                return True
    except Exception as e:
        print(f"⚠️  Could not signal gateway reload: {e}")
    return False


def _handle_agent_delete(body):
    """Delete an agent from its backing platform."""
    agent_id = (body.get("id") or "").strip()
    if not agent_id:
        return {"error": "Agent ID is required", "_status": 400}

    # Safety: never delete the main agent
    if agent_id == "main":
        return {"error": "Cannot delete the main agent", "_status": 403}
    if _is_archive_manager_agent(agent_id):
        return {"error": "档案管理员是系统角色，不能删除；可以在档案室暂停。", "code": "archive_manager_cannot_delete", "_status": 403}

    try:
        agent = _office_agent_lookup(agent_id)
        provider_kind = (agent or {}).get("providerKind", "openclaw")
        if provider_kind == "codex" or agent_id.startswith("codex-"):
            profile = (agent or {}).get("providerAgentId") or agent_id.replace("codex-", "", 1)
            result = _codex_provider_from_config().delete_agent(profile)
            if not result.get("ok"):
                return {"error": result.get("error", "Codex agent delete failed"), "_status": 500}
        elif provider_kind == "claude-code" or agent_id.startswith("claude-code-"):
            profile = (agent or {}).get("providerAgentId") or agent_id.replace("claude-code-", "", 1)
            result = _claude_code_provider_from_config().delete_agent(profile)
            if not result.get("ok"):
                return {"error": result.get("error", "Claude Code agent delete failed"), "_status": 500}
            try:
                os.remove(_claude_code_history_path(profile))
            except FileNotFoundError:
                pass
            except OSError as e:
                print(f"[CLAUDE-CODE] Failed to remove VO history for deleted profile {profile}: {e}")
        elif provider_kind == "hermes" or agent_id.startswith("hermes-"):
            profile = (agent or {}).get("providerAgentId") or agent_id.replace("hermes-", "", 1)
            provider = HermesProvider(
                home_path=VO_CONFIG.get("hermes", {}).get("homePath"),
                binary=VO_CONFIG.get("hermes", {}).get("binary"),
                enabled=VO_CONFIG.get("hermes", {}).get("enabled", True),
                timeout_sec=VO_CONFIG.get("hermes", {}).get("timeoutSec", 600),
            )
            result = provider.delete_agent(profile)
            if not result.get("ok"):
                return {"error": result.get("error", "Hermes agent delete failed"), "_status": 500}
            try:
                os.remove(_hermes_history_path(profile))
            except FileNotFoundError:
                pass
            except OSError as e:
                print(f"[HERMES] Failed to remove VO history for deleted profile {profile}: {e}")
        elif provider_kind == "codex" or agent_id.startswith("codex-"):
            profile = (agent or {}).get("providerAgentId") or agent_id.replace("codex-", "", 1)
            result = _codex_provider().delete_agent(profile)
            if not result.get("ok"):
                return {"error": result.get("error", "Codex agent delete failed"), "_status": 500}
            try:
                os.remove(_codex_history_path(profile))
            except FileNotFoundError:
                pass
            except OSError as e:
                print(f"[CODEX] Failed to remove VO history for deleted profile {profile}: {e}")
        elif provider_kind == "claude-code" or agent_id.startswith("claude-code-"):
            profile = (agent or {}).get("providerAgentId") or agent_id.replace("claude-code-", "", 1)
            result = _claude_code_provider().delete_agent(profile)
            if not result.get("ok"):
                return {"error": result.get("error", "Claude Code agent delete failed"), "_status": 500}
            try:
                os.remove(_claude_code_history_path(profile))
            except FileNotFoundError:
                pass
            except OSError as e:
                print(f"[CLAUDE_CODE] Failed to remove VO history for deleted profile {profile}: {e}")
        else:
            result = _gateway_rpc_call("agents.delete", {"agentId": agent_id, "deleteFiles": True}, timeout=30)
            if not result.get("ok"):
                status = 404 if "not found" in str(result.get("error", "")).lower() else 500
                return {"error": result.get("error", "OpenClaw agent delete failed"), "_status": status}
            _remove_openclaw_agent_paths(agent_id)

        # Refresh discovery
        global _discovered_at
        _discovered_at = 0
        refresh_agent_maps()

        return {
            "ok": True,
            "agentId": agent_id,
            "message": f"Agent '{agent_id}' deleted successfully"
        }

    except Exception as e:
        traceback.print_exc()
        return {"error": str(e), "_status": 500}




def _handle_agents_list():
    refresh_agent_maps()
    _oc_overrides, _oc_branches = _load_office_agent_overrides()
    roster = []
    for a in get_roster():
        oc = _office_agent_override_for(a, _oc_overrides)
        provider_kind = a.get("providerKind", "openclaw")
        branch_id = oc.get("branch", "")
        branch_name = _oc_branches.get(branch_id, "") if branch_id else ""
        if not branch_name:
            branch_name = provider_kind.title() if provider_kind != "openclaw" else "Unassigned"
        agent_payload = {
            "id": a["id"],
            "statusKey": a["statusKey"],
            "providerKind": provider_kind,
            "providerType": a.get("providerType", "runtime"),
            "providerAgentId": a.get("providerAgentId", a["id"]),
            "profile": a.get("profile") or a.get("providerAgentId") or "",
            "name": oc.get("name") or a["name"],
            "emoji": oc.get("emoji") or a["emoji"],
            "role": a.get("role", ""),
            "model": a.get("model", ""),
            "provider": a.get("provider", ""),
            "lastActiveAt": a.get("lastActiveAt", 0),
            "branch": branch_name,
        }
        agent_payload.update(_agent_archive_manager_meta(a.get("statusKey") or a.get("id")))
        roster.append(agent_payload)
    return {"agents": _apply_agent_limit_balanced(roster)}

_wrap_exports()
_hydrate()
