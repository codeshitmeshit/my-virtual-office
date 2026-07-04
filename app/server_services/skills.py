"""Agent skills and skills-library service split from server.py."""

import sys

AGENT_PLATFORM_COMM_SKILL_NAME = "AgentPlatform-to-AgentPlatform_Communications"

__all__ = ['AGENT_PLATFORM_COMM_SKILL_NAME', '_agent_platform_comm_skill_content', '_vo_presence_skill_content', '_vo_browser_skill_content', '_vo_meetings_skill_content', '_vo_projects_skill_content', '_builtin_office_skill_contents', '_ensure_builtin_communication_skill', '_handle_skill_list', '_extract_skill_description', '_handle_skill_write', '_get_skills_library_dir', '_parse_skill_frontmatter', '_skill_library_slug', '_handle_skills_library_list', '_handle_skills_library_get', '_handle_skills_library_create', '_handle_skills_library_save_from_agent', '_parse_cli_json', '_openclaw_skill_workshop_cli', '_skill_workshop_rpc', '_skill_workshop_agent_targets', '_normalize_skill_workshop_proposal', '_handle_skill_workshop_list', '_handle_skill_workshop_inspect', '_handle_skill_workshop_action', '_handle_skills_library_delete', '_handle_skills_library_apply', '_handle_skills_library_upload', '_handle_skill_delete']


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


def _agent_platform_comm_skill_content():
    office_url = f"http://127.0.0.1:{PORT}"
    return '''---
name: AgentPlatform-to-AgentPlatform_Communications
description: "Talk to agents on OpenClaw, Hermes, or other Virtual Office-connected platforms through the office communication layer."
---

# AgentPlatform-to-AgentPlatform Communications

Use this when you need to send a message, question, handoff, or task note to another agent in My Virtual Office, including agents from other platforms.

## Rule

Do **not** bypass the office with a direct CLI/private channel when the conversation should be visible to the office. Send through the Virtual Office communication endpoint so the interaction is logged for later chat bubbles, review, and cross-platform history.

## Endpoint

Default local endpoint:

```bash
POST {office_url}/api/agent-platform-communications/send
```

If Virtual Office runs elsewhere, use that office base URL.

## Message format

```json
{
  "fromAgentId": "<your office agent id>",
  "toAgentId": "<target office agent id>",
  "message": "<clear message to the target agent>",
  "conversationId": "<optional stable thread id>",
  "metadata": {"topic": "optional"}
}
```

Office agent IDs look like:

- `main`, `dev-cody`, `pq-m-moe` for OpenClaw agents
- `hermes-default` or `hermes-<profile>` for Hermes agents

## Curl example

```bash
curl -sS -X POST {office_url}/api/agent-platform-communications/send \
  -H 'Content-Type: application/json' \
  -d '{
    "fromAgentId":"main",
    "toAgentId":"hermes-default",
    "message":"Hi Hermes, can you review this idea and reply with your take?"
  }'
```

## Response

The response contains the target agent reply and office log IDs:

```json
{
  "ok": true,
  "conversationId": "...",
  "messageId": "...",
  "replyMessageId": "...",
  "reply": "..."
}
```

## Safety

- Keep private data minimal.
- Do not request config, credential, network, or infrastructure changes unless the office owner explicitly approved them.
- Use a clear `conversationId` when continuing the same topic.
- If the endpoint fails, report the error instead of silently using an offscreen private channel.
'''.replace("{office_url}", office_url)


def _vo_presence_skill_content():
    office_url = f"http://127.0.0.1:{PORT}"
    return '''---
name: VirtualOffice-Presence-and-Status
description: "Update and inspect Virtual Office presence states such as working, idle, break, and meeting."
---

# VirtualOffice Presence and Status

Use this to make the office show what you are doing.

## Set working

```bash
curl -sS -X POST {office_url}/api/presence/YOUR_AGENT_ID \
  -H 'Content-Type: application/json' \
  -d '{"state":"working","task":"short task description"}'
```

## Set idle

```bash
curl -sS -X POST {office_url}/api/presence/YOUR_AGENT_ID \
  -H 'Content-Type: application/json' \
  -d '{"state":"idle"}'
```

## Read presence

```bash
curl -sS {office_url}/api/presence
curl -sS {office_url}/status
```

## Rules

- Set `working` before visible work.
- Keep task text short.
- Set `idle` when done.
- Do not fake another agent's status unless you are the office broker handling that agent's task.
'''.replace("{office_url}", office_url)


def _vo_browser_skill_content():
    office_url = f"http://127.0.0.1:{PORT}"
    return '''---
name: VirtualOffice-Browser-Control
description: "Use the Virtual Office browser panel/status surface safely instead of direct Kasm/CDP credentials."
---

# VirtualOffice Browser Control

Use this when you need the shared Virtual Office browser/Kasm panel.

## Current safe read endpoints

```bash
curl -sS {office_url}/browser-status
curl -sS {office_url}/browser-tabs
curl -sS {office_url}/browser-controller
```

## Rules

- Treat the Virtual Office browser as a shared visible resource.
- Do not use raw Kasm/CDP credentials directly unless the office/browser adapter explicitly gives you a safe action endpoint.
- Announce/request browser use through presence or AgentPlatform communications so the office owner can see who is using it.
- If another agent/user controls the browser, wait or ask instead of fighting for control.

## Current limitation

This skill documents the shared browser surface. A provider-neutral browser action endpoint is planned next; until then, agents outside OpenClaw should not bypass the office to control Kasm directly.
'''.replace("{office_url}", office_url)


def _vo_meetings_skill_content():
    office_url = f"http://127.0.0.1:{PORT}"
    return '''---
name: VirtualOffice-Meetings
description: "Create, inspect, and end visible Virtual Office meetings with summaries and action items."
---

# VirtualOffice Meetings

Use meetings when multiple agents coordinate.

## Read meetings

```bash
curl -sS {office_url}/api/meetings/active
curl -sS {office_url}/api/meetings/history
```

## Create meeting

```bash
curl -sS -X POST {office_url}/api/meetings/create \
  -H 'Content-Type: application/json' \
  -d '{"topic":"Topic","purpose":"Why we are meeting","kind":"discussion","organizer":"YOUR_AGENT_ID","participants":["YOUR_AGENT_ID","OTHER_AGENT_ID"]}'
```

## End meeting

```bash
curl -sS -X POST {office_url}/api/meetings/end \
  -H 'Content-Type: application/json' \
  -d '{"id":"MEETING_ID","endedBy":"YOUR_AGENT_ID","summary":"What happened","resolution":"Decision/outcome","actionItems":["Next step"]}'
```

## Rules

- Always end meetings with a useful summary.
- Do not silently create meetings for casual one-off messages; use AgentPlatform communications for that.
- Do not invite system archive manager agents such as `archive-manager`; they are not normal meeting participants.
'''.replace("{office_url}", office_url)


def _vo_projects_skill_content():
    office_url = f"http://127.0.0.1:{PORT}"
    return '''---
name: VirtualOffice-Projects-and-Tasks
description: "Inspect and work with Virtual Office projects, tasks, workflow status, and agent scores."
---

# VirtualOffice Projects and Tasks

Use this to inspect visible project/task state.

## Read projects

```bash
curl -sS {office_url}/api/projects
curl -sS {office_url}/api/projects/PROJECT_ID
curl -sS {office_url}/api/projects/PROJECT_ID/workflow/status
```

## Read scores

```bash
curl -sS {office_url}/api/projects/scores
```

## Create a task

```bash
curl -sS -X POST {office_url}/api/projects/PROJECT_ID/tasks \
  -H 'Content-Type: application/json' \
  -d '{"title":"Task title","description":"Task details","assignee":"AGENT_ID"}'
```

## Rules

- Prefer project/task endpoints for durable work instead of private chat when the work belongs on a board.
- Keep task titles short and descriptions concrete.
- Do not delete or reorder project data unless explicitly asked.
'''.replace("{office_url}", office_url)


def _builtin_office_skill_contents():
    return {
        AGENT_PLATFORM_COMM_SKILL_NAME: _agent_platform_comm_skill_content(),
        "VirtualOffice-Presence-and-Status": _vo_presence_skill_content(),
        "VirtualOffice-Browser-Control": _vo_browser_skill_content(),
        "VirtualOffice-Meetings": _vo_meetings_skill_content(),
        "VirtualOffice-Projects-and-Tasks": _vo_projects_skill_content(),
    }


def _ensure_builtin_communication_skill():
    """Seed built-in Virtual Office agent tool skills into the library."""
    try:
        lib_dir = _get_skills_library_dir()
        first_path = ""
        for skill_name, content in _builtin_office_skill_contents().items():
            skill_dir = os.path.join(lib_dir, skill_name)
            skill_file = os.path.join(skill_dir, "SKILL.md")
            os.makedirs(skill_dir, exist_ok=True)
            old = ""
            if os.path.isfile(skill_file):
                with open(skill_file, "r") as f:
                    old = f.read()
            if old != content:
                with open(skill_file, "w") as f:
                    f.write(content)
            if skill_name == AGENT_PLATFORM_COMM_SKILL_NAME:
                first_path = skill_file
        return first_path
    except Exception as e:
        print(f"[SKILLS] Failed to seed built-in office skills: {e}")
        return ""


def _handle_skill_list(agent_key):
    """List skills for an agent."""
    refresh_agent_maps()
    ws_dir = AGENT_WORKSPACES.get(agent_key)
    if not ws_dir:
        return {"error": "Agent not found", "_status": 404}
    ws_path = os.path.join(WORKSPACE_BASE, ws_dir)
    skills_dir = os.path.join(ws_path, "skills")
    if not os.path.isdir(skills_dir):
        return {"skills": []}
    skills = []
    for entry in sorted(os.listdir(skills_dir)):
        skill_path = os.path.join(skills_dir, entry)
        # Skill can be a folder with SKILL.md or a single .md file
        if os.path.isdir(skill_path):
            skill_md = os.path.join(skill_path, "SKILL.md")
            if os.path.exists(skill_md):
                desc = _extract_skill_description(skill_md)
                try:
                    with open(skill_md, "r") as f:
                        content = f.read()
                except Exception:
                    content = ""
                skills.append({"name": entry, "type": "folder", "description": desc, "content": content})
        elif entry.endswith(".md"):
            desc = _extract_skill_description(skill_path)
            try:
                with open(skill_path, "r") as f:
                    content = f.read()
            except Exception:
                content = ""
            skills.append({"name": entry.replace(".md", ""), "type": "file", "description": desc, "content": content})
    return {"skills": skills}


def _extract_skill_description(filepath):
    """Extract first meaningful line from a skill file as description."""
    try:
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("---") and not line.startswith("name:"):
                    return line[:200]
    except Exception:
        pass
    return ""


def _handle_skill_write(agent_key, skill_name, body):
    """Create or update a skill for an agent."""
    refresh_agent_maps()
    ws_dir = AGENT_WORKSPACES.get(agent_key)
    if not ws_dir:
        return {"error": "Agent not found", "_status": 404}
    ws_path = os.path.join(WORKSPACE_BASE, ws_dir)
    skills_dir = os.path.join(ws_path, "skills")
    os.makedirs(skills_dir, exist_ok=True)

    name = body.get("name", skill_name or "").strip()
    content = body.get("content", "")
    if not name:
        return {"error": "Skill name is required", "_status": 400}

    # Sanitize name
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '-', name).strip('-')
    if not safe_name:
        return {"error": "Invalid skill name", "_status": 400}

    # Create skill as a folder with SKILL.md
    skill_dir = os.path.join(skills_dir, safe_name)
    os.makedirs(skill_dir, exist_ok=True)
    skill_file = os.path.join(skill_dir, "SKILL.md")

    if not content:
        content = f"# {name}\n\n_Describe this skill's instructions here._\n"

    with open(skill_file, "w") as f:
        f.write(content)

    return {"ok": True, "skill": safe_name, "path": skill_file}


# ─── SKILLS LIBRARY HANDLERS ─────────────────────────────────────

def _get_skills_library_dir():
    """Return path to the central skills library (master copies, not agent-specific)."""
    home = VO_CONFIG.get("openclaw", {}).get("homePath", os.path.expanduser("~/.openclaw"))
    d = os.path.join(home, "skills-library")
    os.makedirs(d, exist_ok=True)
    return d


def _parse_skill_frontmatter(content):
    """Parse YAML-like frontmatter from SKILL.md content."""
    name = ""
    description = ""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                line = line.strip()
                if line.startswith("name:"):
                    name = line[5:].strip().strip("'\"")
                elif line.startswith("description:"):
                    description = line[12:].strip().strip("'\"")
    return name, description


def _skill_library_slug(name):
    """Return the normalized folder name used by the central skill library."""
    return re.sub(r'[^a-zA-Z0-9_-]', '-', (name or "").strip()).strip('-').lower()


def _handle_skills_library_list():
    """GET /api/skills-library — list all library skills."""
    _ensure_builtin_communication_skill()
    lib_dir = _get_skills_library_dir()
    skills = []
    for entry in sorted(os.listdir(lib_dir)):
        skill_dir = os.path.join(lib_dir, entry)
        if not os.path.isdir(skill_dir):
            continue
        skill_md = os.path.join(skill_dir, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue
        try:
            with open(skill_md, "r") as f:
                content = f.read()
        except Exception:
            content = ""
        name, description = _parse_skill_frontmatter(content)
        if not name:
            name = entry
        if not description:
            description = _extract_skill_description(skill_md)
        skills.append({"name": entry, "description": description, "path": skill_md})
    return {"skills": skills}


def _handle_skills_library_get(skill_name):
    """GET /api/skills-library/<name> — read a specific library skill."""
    if skill_name == AGENT_PLATFORM_COMM_SKILL_NAME:
        _ensure_builtin_communication_skill()
    lib_dir = _get_skills_library_dir()
    skill_md = os.path.join(lib_dir, skill_name, "SKILL.md")
    if not os.path.isfile(skill_md):
        return {"error": f"Skill '{skill_name}' not found in library", "_status": 404}
    try:
        with open(skill_md, "r") as f:
            content = f.read()
    except Exception as e:
        return {"error": str(e), "_status": 500}
    name, description = _parse_skill_frontmatter(content)
    if not name:
        name = skill_name
    return {"name": name, "description": description, "content": content}


def _handle_skills_library_create(body):
    """POST /api/skills-library — create or update a library skill."""
    name = body.get("name", "").strip()
    content = body.get("content", "")
    if not name:
        return {"error": "name is required", "_status": 400}
    slug = _skill_library_slug(name)
    if not slug:
        return {"error": "Invalid skill name", "_status": 400}
    lib_dir = _get_skills_library_dir()
    skill_dir = os.path.join(lib_dir, slug)
    os.makedirs(skill_dir, exist_ok=True)
    skill_file = os.path.join(skill_dir, "SKILL.md")
    if not content:
        content = f"---\nname: {slug}\ndescription: \n---\n\n# {name}\n\n_Describe this skill here._\n"
    with open(skill_file, "w") as f:
        f.write(content)
    parsed_name, description = _parse_skill_frontmatter(content)
    return {"ok": True, "skill": slug, "name": parsed_name or slug, "description": description, "path": skill_file}


def _handle_skills_library_save_from_agent(body):
    """Copy an agent workspace skill into the central skills library."""
    agent_id = (body.get("agentId") or "").strip()
    skill_name = (body.get("skill") or body.get("name") or "").strip()
    overwrite = bool(body.get("overwrite", False))
    if not agent_id:
        return {"error": "agentId is required", "_status": 400}
    if not skill_name:
        return {"error": "skill is required", "_status": 400}

    skill = None
    result = _handle_skill_list(agent_id)
    if not result.get("skills") and result.get("error"):
        return result
    for item in result.get("skills", []):
        if item.get("name") == skill_name:
            skill = item
            break
    if not skill:
        return {"error": f"Skill '{skill_name}' not found on agent '{agent_id}'", "_status": 404}

    content = skill.get("content") or ""
    slug = _skill_library_slug(skill_name)
    if not slug:
        return {"error": "Invalid skill name", "_status": 400}

    lib_dir = _get_skills_library_dir()
    skill_dir = os.path.join(lib_dir, slug)
    skill_file = os.path.join(skill_dir, "SKILL.md")
    existed = os.path.isfile(skill_file)
    if existed:
        try:
            with open(skill_file, "r") as f:
                existing = f.read()
        except Exception:
            existing = ""
        if existing == content:
            return {
                "ok": True,
                "status": "identical",
                "exists": True,
                "different": False,
                "skill": slug,
                "message": "Skill already exists in the Skill Library.",
            }
        if not overwrite:
            return {
                "ok": False,
                "status": "exists_different",
                "exists": True,
                "different": True,
                "skill": slug,
                "message": "Skill already exists in the Skill Library.",
            }

    os.makedirs(skill_dir, exist_ok=True)
    with open(skill_file, "w") as f:
        f.write(content)
    parsed_name, description = _parse_skill_frontmatter(content)
    return {
        "ok": True,
        "status": "updated" if existed else "created",
        "skill": slug,
        "name": parsed_name or slug,
        "description": description,
        "path": skill_file,
    }


def _parse_cli_json(stdout, stderr=""):
    """Parse JSON from OpenClaw CLI output that may include warning lines first."""
    text = (stdout or "").strip()
    if not text:
        text = (stderr or "").strip()
    for idx, ch in enumerate(text):
        if ch not in "[{":
            continue
        try:
            data, _ = json.JSONDecoder().raw_decode(text[idx:])
            return data
        except json.JSONDecodeError:
            continue
    return None


def _openclaw_skill_workshop_cli(agent_id, args, timeout=25):
    """Run an OpenClaw Skill Workshop CLI command for one agent workspace."""
    openclaw_bin = shutil.which("openclaw")
    if not openclaw_bin:
        return {"ok": False, "error": "openclaw CLI not found", "_status": 500}
    cmd = [openclaw_bin, "skills"]
    if agent_id:
        cmd.extend(["--agent", agent_id])
    cmd.append("workshop")
    cmd.extend(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Skill Workshop command timed out", "_status": 504, "agentId": agent_id}
    except Exception as e:
        return {"ok": False, "error": str(e), "_status": 500, "agentId": agent_id}
    data = _parse_cli_json(result.stdout, result.stderr)
    if result.returncode != 0:
        return {
            "ok": False,
            "error": (result.stderr or result.stdout or "Skill Workshop command failed").strip()[:1000],
            "code": result.returncode,
            "_status": 500,
            "agentId": agent_id,
            "data": data,
        }
    if isinstance(data, dict):
        data.setdefault("ok", True)
        data.setdefault("agentId", agent_id)
        return data
    return {"ok": True, "agentId": agent_id, "result": data}


def _skill_workshop_rpc(method, agent_id, params=None, timeout=25):
    payload = dict(params or {})
    if agent_id:
        payload["agentId"] = agent_id
    result = _gateway_rpc_call(method, payload, timeout=timeout)
    if isinstance(result, dict):
        result.setdefault("agentId", agent_id)
    return result


def _skill_workshop_agent_targets(agent_id=""):
    refresh_agent_maps()
    roster = get_roster()
    targets = []
    for agent in roster:
        key = agent.get("statusKey") or agent.get("key") or agent.get("id")
        if not key:
            continue
        if agent_id and key != agent_id and agent.get("id") != agent_id:
            continue
        if agent.get("providerKind", "openclaw") != "openclaw":
            continue
        targets.append({
            "id": key,
            "name": agent.get("name") or key,
            "emoji": agent.get("emoji") or "",
        })
    if agent_id and not targets:
        targets.append({"id": agent_id, "name": agent_id, "emoji": ""})
    return targets


def _normalize_skill_workshop_proposal(proposal, agent):
    if not isinstance(proposal, dict):
        return {}
    item = dict(proposal)
    proposal_id = item.get("id") or item.get("proposalId") or item.get("proposal_id")
    item["id"] = proposal_id or ""
    item["agentId"] = agent.get("id")
    item["agentName"] = agent.get("name")
    item["agentEmoji"] = agent.get("emoji", "")
    return item


def _handle_skill_workshop_list(qs):
    agent_id = ""
    if isinstance(qs, dict):
        values = qs.get("agentId") or qs.get("agent") or []
        if values:
            agent_id = str(values[0]).strip()
    targets = _skill_workshop_agent_targets(agent_id)
    proposals = []
    errors = []

    def load_target(agent):
        result = _skill_workshop_rpc("skills.proposals.list", agent["id"], {}, timeout=25)
        return agent, result

    # Keep the UI responsive when aggregating across many agents.
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(load_target, agent) for agent in targets]
        for future in concurrent.futures.as_completed(futures):
            agent, result = future.result()
            if not result.get("ok"):
                errors.append({"agentId": agent["id"], "agentName": agent["name"], "error": result.get("error", "Failed")})
                continue
            for proposal in result.get("proposals", []) or []:
                normalized = _normalize_skill_workshop_proposal(proposal, agent)
                if normalized:
                    proposals.append(normalized)
    proposals.sort(key=lambda p: str(p.get("updatedAt") or p.get("createdAt") or ""), reverse=True)
    return {"ok": True, "proposals": proposals, "errors": errors, "agents": targets}


def _handle_skill_workshop_inspect(qs):
    proposal_id = ""
    agent_id = ""
    if isinstance(qs, dict):
        proposal_id = str((qs.get("proposalId") or qs.get("id") or [""])[0]).strip()
        agent_id = str((qs.get("agentId") or qs.get("agent") or [""])[0]).strip()
    if not proposal_id:
        return {"error": "proposalId is required", "_status": 400}
    if not agent_id:
        return {"error": "agentId is required", "_status": 400}
    result = _skill_workshop_rpc("skills.proposals.inspect", agent_id, {"proposalId": proposal_id}, timeout=25)
    result.setdefault("proposalId", proposal_id)
    result.setdefault("agentId", agent_id)
    return result


def _handle_skill_workshop_action(body):
    action = (body.get("action") or "").strip()
    proposal_id = (body.get("proposalId") or body.get("id") or "").strip()
    agent_id = (body.get("agentId") or "").strip()
    if action not in ("apply", "reject", "quarantine", "revise"):
        return {"error": "Invalid Skill Workshop action", "_status": 400}
    if not proposal_id:
        return {"error": "proposalId is required", "_status": 400}
    if not agent_id:
        return {"error": "agentId is required", "_status": 400}

    method = {
        "apply": "skills.proposals.apply",
        "reject": "skills.proposals.reject",
        "quarantine": "skills.proposals.quarantine",
        "revise": "skills.proposals.revise",
    }[action]
    params = {"proposalId": proposal_id}
    if action in ("reject", "quarantine", "apply"):
        reason = (body.get("reason") or "").strip()
        if reason:
            params["reason"] = reason
    if action == "revise":
        proposal_content = body.get("proposalContent") or body.get("content") or ""
        if not proposal_content:
            return {"error": "proposalContent is required for revise", "_status": 400}
        params["content"] = str(proposal_content)
        for key in ("description", "goal", "evidence"):
            value = (body.get(key) or "").strip()
            if value:
                params[key] = value
    return _skill_workshop_rpc(method, agent_id, params, timeout=35)


def _handle_skills_library_delete(skill_name):
    """DELETE /api/skills-library/<name> — delete a library skill."""
    lib_dir = _get_skills_library_dir()
    skill_dir = os.path.join(lib_dir, skill_name)
    if not os.path.isdir(skill_dir):
        return {"error": f"Skill '{skill_name}' not found in library", "_status": 404}
    shutil.rmtree(skill_dir)
    return {"ok": True, "deleted": skill_name}


def _handle_skills_library_apply(body):
    """POST /api/skills-library/apply — copy library skill to agent workspace."""
    skill_name = body.get("skill", "").strip()
    agent_id = body.get("agentId", "").strip()
    overwrite = body.get("overwrite", False)
    if not skill_name:
        return {"error": "skill name is required", "_status": 400}
    if not agent_id:
        return {"error": "agentId is required", "_status": 400}
    # Check library skill exists
    lib_dir = _get_skills_library_dir()
    src_file = os.path.join(lib_dir, skill_name, "SKILL.md")
    if not os.path.isfile(src_file):
        return {"error": f"Skill '{skill_name}' not found in library", "_status": 404}
    # Find agent workspace
    refresh_agent_maps()
    ws_dir = AGENT_WORKSPACES.get(agent_id)
    if not ws_dir:
        return {"error": f"Agent '{agent_id}' not found", "_status": 404}
    ws_path = os.path.join(WORKSPACE_BASE, ws_dir)
    dest_dir = os.path.join(ws_path, "skills", skill_name)
    dest_file = os.path.join(dest_dir, "SKILL.md")
    if os.path.isfile(dest_file) and not overwrite:
        return {"ok": False, "warning": f"Agent '{agent_id}' already has skill '{skill_name}'. Set overwrite=true to replace.", "exists": True}
    os.makedirs(dest_dir, exist_ok=True)
    shutil.copy2(src_file, dest_file)
    return {"ok": True, "skill": skill_name, "agentId": agent_id, "path": dest_file, "overwritten": os.path.isfile(dest_file) and overwrite}


def _handle_skills_library_upload(body):
    """POST /api/skills-library/upload — upload a SKILL.md to library."""
    filename = body.get("filename", "").strip()
    content_b64 = body.get("content", "")
    if not content_b64:
        return {"error": "content is required (base64)", "_status": 400}
    try:
        content = base64.b64decode(content_b64).decode("utf-8")
    except Exception:
        content = content_b64  # allow plain text too
    # Extract name from frontmatter or filename
    name, description = _parse_skill_frontmatter(content)
    if not name and filename:
        name = filename.replace(".md", "").replace("SKILL", "").strip("-_ ")
    if not name:
        name = "uploaded-skill"
    slug = re.sub(r'[^a-zA-Z0-9_-]', '-', name).strip('-').lower()
    if not slug:
        slug = "uploaded-skill"
    lib_dir = _get_skills_library_dir()
    skill_dir = os.path.join(lib_dir, slug)
    os.makedirs(skill_dir, exist_ok=True)
    with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
        f.write(content)
    return {"ok": True, "skill": slug, "name": name, "description": description}


def _handle_skill_delete(agent_key, skill_name):
    """Delete a skill from an agent."""
    refresh_agent_maps()
    ws_dir = AGENT_WORKSPACES.get(agent_key)
    if not ws_dir:
        return {"error": "Agent not found", "_status": 404}
    ws_path = os.path.join(WORKSPACE_BASE, ws_dir)
    skills_dir = os.path.join(ws_path, "skills")

    if not skill_name:
        return {"error": "Skill name is required", "_status": 400}

    # Try folder first, then file
    skill_folder = os.path.join(skills_dir, skill_name)
    skill_file = os.path.join(skills_dir, f"{skill_name}.md")

    if os.path.isdir(skill_folder):
        shutil.rmtree(skill_folder)
        return {"ok": True, "deleted": skill_name}
    elif os.path.isfile(skill_file):
        os.remove(skill_file)
        return {"ok": True, "deleted": skill_name}
    else:
        return {"error": f"Skill '{skill_name}' not found", "_status": 404}



_wrap_exports()
_hydrate()
