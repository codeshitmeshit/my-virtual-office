import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
import weakref
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from services.project_actors import task_actor_references

PROJECTS_DIRNAME = "projects-md"
LEGACY_PROJECTS_FILENAME = "projects.json"
ROOT_METADATA_FILENAME = "projects-root.json"
ROOT_METADATA_DEFAULTS = {
    "templates": [],
    "projectAuthoringRequests": {},
    "projectAuthoringIdempotency": {},
    "projectAuthoringGrants": {},
    "projectTemplateVersions": {},
    "projectRecurrences": {},
    "projectAuthoringOutbox": [],
}
COMPLEX_JSON_FIELDS = {
    "columns_json", "templates_json", "reviewCheck_json", "lastReviewCheck_json",
    "checklist_json", "tags_json", "attachments_json", "workspaceStatus_json",
    "executionPolicy_json", "executionDirtyConfirmations_json", "attempts_json",
    "evidence_json", "reviewResult_json", "reviewHistory_json",
    "acceptanceHistory_json", "stateHistory_json", "source_json",
    "meetingBlocker_json", "meetingBlockerHistory_json",
    "meetingActionItems_json", "meetingDecisionHistory_json", "meetingDiscussionPoints_json", "meetingRecords_json",
    "scheduledCronHistory_json", "archiveMaintenance_json", "feishuNotifications_json",
    "authoringSource_json", "templateRef_json", "recurrenceRef_json",
    "responsibleActor_json", "executorActor_json", "reviewerActor_json",
    "reviewerRecommendation_json",
    "maintenanceHistory_json",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _slugify(value: str, fallback: str = "item") -> str:
    s = (value or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or fallback


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "":
        return '""'
    if re.match(r"^[A-Za-z0-9_.:/@# +\-]+$", text) and text.lower() not in {"true", "false", "null"}:
        return text
    return json.dumps(text, ensure_ascii=False)


def _dump_frontmatter(data: Dict[str, Any]) -> str:
    lines: List[str] = ["---"]
    for key, value in data.items():
        if key in COMPLEX_JSON_FIELDS:
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False, separators=(',', ':'))}")
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


def _parse_scalar(text: str) -> Any:
    text = text.strip()
    if text in ("null", "~"):
        return None
    if text == "true":
        return True
    if text == "false":
        return False
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in inner.split(",")]
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        try:
            return json.loads(text)
        except Exception:
            return text[1:-1]
    if re.fullmatch(r"-?\d+", text):
        try:
            return int(text)
        except Exception:
            pass
    if re.fullmatch(r"-?\d+\.\d+", text):
        try:
            return float(text)
        except Exception:
            pass
    return text


def _parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 5 :]
    lines = raw.splitlines()
    result: Dict[str, Any] = {}
    for line in lines:
        if not line.strip() or ":" not in line:
            continue
        key, rest = line.split(":", 1)
        key = key.strip()
        rest = rest.strip()
        if key in COMPLEX_JSON_FIELDS:
            try:
                result[key] = json.loads(rest) if rest else None
            except Exception:
                result[key] = None
        else:
            result[key] = _parse_scalar(rest)
    return result, body.lstrip("\n")


def _atomic_write(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o666)
    except Exception:
        pass


def _atomic_write_private(path: str, content: str):
    """Atomically write root metadata that may contain credential hashes."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


class MarkdownProjectStore:
    def __init__(
        self,
        status_dir: str,
        *,
        watch_external_changes: bool = False,
        watch_interval: float = 0.5,
        full_revision_interval: float = 5.0,
    ):
        self.status_dir = status_dir
        self.projects_dir = os.path.join(status_dir, PROJECTS_DIRNAME)
        self.legacy_json = os.path.join(status_dir, LEGACY_PROJECTS_FILENAME)
        self.root_metadata = os.path.join(status_dir, ROOT_METADATA_FILENAME)
        self.lock = threading.Lock()
        self._revision_lock = threading.Lock()
        self._revision_generation = 0
        self._revision_signature = ""
        self._revision_quick_signature = ""
        self._last_full_revision_poll = 0.0
        self._watch_interval = max(0.1, float(watch_interval))
        self._full_revision_interval = max(self._watch_interval, float(full_revision_interval))
        os.makedirs(self.projects_dir, exist_ok=True)
        if watch_external_changes:
            self.poll_external_revision()
            self._revision_quick_signature = self._quick_revision_signature()
            threading.Thread(
                target=self._watch_revision_loop,
                args=(weakref.ref(self), self._watch_interval),
                daemon=True,
                name="project-markdown-revision",
            ).start()

    def now(self) -> str:
        return _now_iso()

    def new_id(self) -> str:
        return _new_id()

    def revision(self) -> int:
        """Return the O(1) generation maintained by writes and the file watcher."""
        with self._revision_lock:
            return self._revision_generation

    def poll_external_revision(self) -> dict[str, Any]:
        """Scan Markdown metadata once; the background watcher calls this off-path."""
        digest = hashlib.blake2b(digest_size=16)
        files_scanned = 0
        for root, dirs, files in os.walk(self.projects_dir):
            dirs.sort()
            files.sort()
            for name in files:
                path = os.path.join(root, name)
                try:
                    stat = os.stat(path, follow_symlinks=False)
                except OSError:
                    continue
                files_scanned += 1
                relative = os.path.relpath(path, self.projects_dir)
                digest.update(relative.encode("utf-8", errors="surrogateescape"))
                digest.update(f":{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}".encode())
        if os.path.isfile(self.legacy_json):
            try:
                stat = os.stat(self.legacy_json, follow_symlinks=False)
                digest.update(f"legacy:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}".encode())
                files_scanned += 1
            except OSError:
                pass
        if os.path.isfile(self.root_metadata):
            try:
                stat = os.stat(self.root_metadata, follow_symlinks=False)
                digest.update(f"root:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}".encode())
                files_scanned += 1
            except OSError:
                pass
        signature = digest.hexdigest()
        with self._revision_lock:
            changed = bool(self._revision_signature and signature != self._revision_signature)
            if changed:
                self._revision_generation += 1
            self._revision_signature = signature
            self._last_full_revision_poll = time.monotonic()
            generation = self._revision_generation
        return {"generation": generation, "changed": changed, "filesScanned": files_scanned}

    def _quick_revision_signature(self) -> str:
        """Fingerprint project/task directories without stat-ing every task file."""
        digest = hashlib.blake2b(digest_size=12)
        try:
            with os.scandir(self.projects_dir) as scan:
                entries = sorted(scan, key=lambda item: item.name)
        except OSError:
            return ""
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            try:
                stat = entry.stat(follow_symlinks=False)
                digest.update(f"{entry.name}:{stat.st_mtime_ns}".encode())
                tasks_dir = os.path.join(entry.path, "tasks")
                task_stat = os.stat(tasks_dir, follow_symlinks=False)
                digest.update(f":{task_stat.st_mtime_ns}".encode())
            except OSError:
                continue
        try:
            stat = os.stat(self.root_metadata, follow_symlinks=False)
            digest.update(f"root:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}".encode())
        except OSError:
            pass
        return digest.hexdigest()

    def _watcher_poll(self) -> None:
        quick = self._quick_revision_signature()
        with self._revision_lock:
            quick_changed = bool(self._revision_quick_signature and quick != self._revision_quick_signature)
            self._revision_quick_signature = quick
            full_due = time.monotonic() - self._last_full_revision_poll >= self._full_revision_interval
        if quick_changed or full_due:
            self.poll_external_revision()

    @staticmethod
    def _watch_revision_loop(store_ref, interval):
        while True:
            time.sleep(interval)
            store = store_ref()
            if store is None:
                return
            try:
                store._watcher_poll()
            except Exception:
                pass
            finally:
                del store

    def _mark_written(self) -> None:
        with self._revision_lock:
            self._revision_generation += 1

    def load_all(self) -> Dict[str, Any]:
        with self.lock:
            self._migrate_legacy_if_needed()
            projects = self._read_all_projects()
            root = self._read_root_metadata(repair=True)
            derived_templates: List[Dict[str, Any]] = []
            for p in projects:
                if p.get("template"):
                    derived_templates.append({
                        "id": p.get("id"),
                        "title": p.get("title", ""),
                        "description": p.get("description", ""),
                        "columns": [{"title": c.get("title"), "color": c.get("color", "#6c757d")} for c in p.get("columns", [])],
                        "taskTemplates": [
                            {
                                "title": t.get("title", ""),
                                "columnIndex": next((i for i, c in enumerate(p.get("columns", [])) if c.get("id") == t.get("columnId")), 0),
                                "priority": t.get("priority", "medium"),
                                "tags": t.get("tags", []),
                                "description": t.get("description", ""),
                            }
                            for t in p.get("tasks", [])
                        ],
                    })
            templates = copy.deepcopy(root["templates"])
            known_template_ids = {item.get("id") for item in templates if isinstance(item, dict)}
            templates.extend(item for item in derived_templates if item.get("id") not in known_template_ids)
            root["projects"] = projects
            root["templates"] = templates
            return root

    def save_all(self, data: Dict[str, Any]):
        with self.lock:
            self._rewrite_from_dict(data)
            self._mark_written()

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        data = self.load_all()
        for p in data.get("projects", []):
            if p.get("id") == project_id:
                return p
        return None

    def delete_project(self, project_id: str) -> bool:
        with self.lock:
            deleted = False
            self._migrate_legacy_if_needed()
            for entry in os.listdir(self.projects_dir):
                project_dir = os.path.join(self.projects_dir, entry)
                project_md = os.path.join(project_dir, "project.md")
                if not os.path.isfile(project_md):
                    continue
                with open(project_md, encoding="utf-8") as project_file:
                    meta, _ = _parse_frontmatter(project_file.read())
                if meta.get("id") == project_id:
                    shutil.rmtree(project_dir, ignore_errors=True)
                    deleted = True
                    break

            legacy = {"projects": [], "templates": []}
            if os.path.isfile(self.legacy_json):
                try:
                    with open(self.legacy_json, "r", encoding="utf-8") as f:
                        legacy = json.load(f)
                except Exception:
                    legacy = {"projects": [], "templates": []}

            before_projects = len(legacy.get("projects", []))
            before_templates = len(legacy.get("templates", []))
            legacy["projects"] = [p for p in legacy.get("projects", []) if p.get("id") != project_id]
            legacy["templates"] = [t for t in legacy.get("templates", []) if t.get("id") != project_id]
            if len(legacy["projects"]) != before_projects or len(legacy["templates"]) != before_templates:
                _atomic_write(self.legacy_json, json.dumps(legacy, ensure_ascii=False, indent=2) + "\n")
                deleted = True

            root = self._read_root_metadata(repair=False)
            root_templates = root.get("templates", [])
            remaining_templates = [
                template for template in root_templates
                if not isinstance(template, dict) or template.get("id") != project_id
            ]
            if len(remaining_templates) != len(root_templates):
                root["templates"] = remaining_templates
                self._write_root_metadata(root)
                deleted = True
            if deleted:
                self._mark_written()

            task_dir = os.path.join(self.status_dir, "project-tasks", project_id)
            if os.path.isdir(task_dir):
                shutil.rmtree(task_dir, ignore_errors=True)
                deleted = True

            md_dir = os.path.join(self.projects_dir, _slugify(project_id, fallback=project_id))
            if os.path.isdir(md_dir):
                shutil.rmtree(md_dir, ignore_errors=True)

            return deleted

    def _migrate_legacy_if_needed(self):
        with os.scandir(self.projects_dir) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False) and os.path.isfile(os.path.join(entry.path, "project.md")):
                    return
        if not os.path.isfile(self.legacy_json):
            return
        try:
            with open(self.legacy_json, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        existing_root = self._read_root_metadata(repair=False)
        for key in ROOT_METADATA_DEFAULTS:
            if key not in data or data.get(key) in (None, [], {}):
                data[key] = existing_root[key]
        self._rewrite_from_dict(data)

    def _rewrite_from_dict(self, data: Dict[str, Any]):
        shutil.rmtree(self.projects_dir, ignore_errors=True)
        os.makedirs(self.projects_dir, exist_ok=True)
        for project in data.get("projects", []):
            self._write_project(project)
        self._write_root_metadata(data)

    def _read_root_metadata(self, *, repair: bool) -> Dict[str, Any]:
        raw: Any = {}
        damaged = False
        if os.path.isfile(self.root_metadata):
            try:
                with open(self.root_metadata, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception:
                raw = {}
                damaged = True
        if not isinstance(raw, dict):
            raw = {}
            damaged = True

        normalized: Dict[str, Any] = {}
        for key, default in ROOT_METADATA_DEFAULTS.items():
            value = raw.get(key, copy.deepcopy(default))
            if not isinstance(value, type(default)):
                value = copy.deepcopy(default)
                damaged = True
            normalized[key] = copy.deepcopy(value)
        if set(raw) - set(ROOT_METADATA_DEFAULTS):
            damaged = True
        if os.path.isfile(self.root_metadata):
            try:
                if os.stat(self.root_metadata, follow_symlinks=False).st_mode & 0o777 != 0o600:
                    damaged = True
            except OSError:
                damaged = True
        if repair and (damaged or not os.path.isfile(self.root_metadata)):
            self._write_root_metadata(normalized)
        return normalized

    def _write_root_metadata(self, data: Dict[str, Any]) -> None:
        bounded: Dict[str, Any] = {}
        for key, default in ROOT_METADATA_DEFAULTS.items():
            value = data.get(key, copy.deepcopy(default))
            bounded[key] = copy.deepcopy(value) if isinstance(value, type(default)) else copy.deepcopy(default)
        _atomic_write_private(
            self.root_metadata,
            json.dumps(bounded, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )

    def _project_dir(self, project: Dict[str, Any]) -> str:
        slug = _slugify(project.get("title", "project"))
        pid = str(project.get("id") or self.new_id())
        suffix = f"{_slugify(pid)[:8]}-{hashlib.sha256(pid.encode()).hexdigest()[:10]}"
        return os.path.join(self.projects_dir, f"{slug}--{suffix}")

    def _write_project(self, project: Dict[str, Any]):
        project = copy.deepcopy(project)
        project_dir = self._project_dir(project)
        tasks_dir = os.path.join(project_dir, "tasks")
        os.makedirs(tasks_dir, exist_ok=True)
        tasks = project.pop("tasks", [])
        activity = project.pop("activity", [])
        meta = {
            "id": project.get("id"),
            "title": project.get("title", ""),
            "projectType": project.get("projectType", "one_time"),
            "status": project.get("status", "active"),
            "priority": project.get("priority", "medium"),
            "createdAt": project.get("createdAt"),
            "updatedAt": project.get("updatedAt"),
            "dueDate": project.get("dueDate"),
            "createdBy": project.get("createdBy", "user"),
            "tags_json": project.get("tags", []),
            "branch": project.get("branch", ""),
            "longTermProject": project.get("longTermProject", False),
            "highPriorityAiMeetingAutoApprove": project.get("highPriorityAiMeetingAutoApprove", False),
            "archiveMaintenanceEnabled": project.get("archiveMaintenanceEnabled"),
            "archiveMaintenance_json": project.get("archiveMaintenance", {}),
            "projectExecutionEnabled": project.get("projectExecutionEnabled", False),
            "workspacePath": project.get("workspacePath"),
            "workspaceKind": project.get("workspaceKind"),
            "workspaceStatus_json": project.get("workspaceStatus", {}),
            "workspaceManagedBy": project.get("workspaceManagedBy"),
            "workspaceCreatedAt": project.get("workspaceCreatedAt"),
            "defaultExecutorAgentId": project.get("defaultExecutorAgentId"),
            "defaultReviewerAgentId": project.get("defaultReviewerAgentId"),
            "projectExecutionStartMode": project.get("projectExecutionStartMode", "continuous"),
            "projectExecutionFlowActive": project.get("projectExecutionFlowActive", False),
            "projectExecutionFlowStopReason": project.get("projectExecutionFlowStopReason"),
            "scheduledCronPaused": project.get("scheduledCronPaused", False),
            "scheduledCronHistory_json": project.get("scheduledCronHistory", []),
            "executionPolicy_json": project.get("executionPolicy", {"maxActiveTasks": 1}),
            "executionDirtyConfirmations_json": project.get("executionDirtyConfirmations", []),
            "feishuNotifications_json": project.get("feishuNotifications", {}),
            "workflowActive": project.get("workflowActive", False),
            "workflowPhase": project.get("workflowPhase", "idle"),
            "activeTaskId": project.get("activeTaskId"),
            "activeAgent": project.get("activeAgent"),
            "autoMode": project.get("autoMode", False),
            "template": project.get("template", False),
            "columns_json": project.get("columns", []),
            "templates_json": project.get("templates", []),
            "agentMaintenanceMode": project.get("agentMaintenanceMode", "strict_confirmation"),
            "authoringAgentId": project.get("authoringAgentId"),
            "authoringRequestId": project.get("authoringRequestId"),
            "authoringSource_json": project.get("authoringSource", {}),
            "templateRef_json": project.get("templateRef", {}),
            "recurrenceRef_json": project.get("recurrenceRef", {}),
        }
        body_lines = [
            "# Project",
            project.get("description", "") or "_No description_",
            "",
            "## Activity",
        ]
        if activity:
            for item in activity[-200:]:
                detail = item.get("detail", "")
                by = item.get("by", "user")
                at = item.get("at", "")
                body_lines.append(f"- [{at}] ({by}) {detail}")
        else:
            body_lines.append("- No activity yet")
        _atomic_write(os.path.join(project_dir, "project.md"), _dump_frontmatter(meta) + "\n" + "\n".join(body_lines) + "\n")
        for task in tasks:
            self._write_task_file(tasks_dir, task)

    def _write_task_file(self, tasks_dir: str, task: Dict[str, Any]):
        task = copy.deepcopy(task)
        try:
            actors = task_actor_references(task)
        except ValueError:
            actors = {}
        task_id = str(task.get("id") or self.new_id())
        title_slug = _slugify(task.get("title", "task"))
        suffix = f"{_slugify(task_id)[:8]}-{hashlib.sha256(task_id.encode()).hexdigest()[:10]}"
        path = os.path.join(tasks_dir, f"{title_slug}--{suffix}.md")
        comments = task.pop("comments", [])
        attachments = task.pop("attachments", [])
        review_check = task.pop("reviewCheck", None)
        last_review_check = task.pop("lastReviewCheck", None)
        meta = {
            "id": task_id,
            "title": task.get("title", ""),
            "columnId": task.get("columnId"),
            "order": task.get("order", 0),
            "priority": task.get("priority", "medium"),
            "assignee": task.get("assignee"),
            "assigneeBranch": task.get("assigneeBranch"),
            "executorAgentId": task.get("executorAgentId"),
            "reviewerAgentId": task.get("reviewerAgentId"),
            "responsibleActor_json": task.get("responsibleActor", actors.get("responsible")),
            "executorActor_json": task.get("executorActor", actors.get("executor")),
            "reviewerActor_json": task.get("reviewerActor", actors.get("reviewer")),
            "reviewerRecommendation_json": task.get("reviewerRecommendation", {}),
            "maintenanceHistory_json": task.get("maintenanceHistory", []),
            "requiresUserAcceptance": task.get("requiresUserAcceptance", True),
            "allowReviewerlessExecution": task.get("allowReviewerlessExecution", False),
            "scheduledRepeatEnabled": task.get("scheduledRepeatEnabled", False),
            "executionState": task.get("executionState", "done" if task.get("completedAt") else "backlog"),
            "activeAttemptId": task.get("activeAttemptId"),
            "attempts_json": task.get("attempts", []),
            "evidence_json": task.get("evidence", {}),
            "reviewResult_json": task.get("reviewResult", {}),
            "reviewHistory_json": task.get("reviewHistory", []),
            "acceptanceHistory_json": task.get("acceptanceHistory", []),
            "meetingBlocker_json": task.get("meetingBlocker", {}),
            "meetingBlockerHistory_json": task.get("meetingBlockerHistory", []),
            "meetingActionItems_json": task.get("meetingActionItems", []),
            "meetingDecisionHistory_json": task.get("meetingDecisionHistory", []),
            "meetingDiscussionPoints_json": task.get("meetingDiscussionPoints", []),
            "meetingRecords_json": task.get("meetingRecords", []),
            "feishuNotifications_json": task.get("feishuNotifications", {}),
            "reworkCount": task.get("reworkCount", 0),
            "stateHistory_json": task.get("stateHistory", []),
            "blockedReason": task.get("blockedReason"),
            "reworkFeedback": task.get("reworkFeedback"),
            "lastError": task.get("lastError"),
            "dueDate": task.get("dueDate"),
            "tags_json": task.get("tags", []),
            "checklist_json": task.get("checklist", []),
            "attachments_json": attachments,
            "reviewCheck_json": review_check or [],
            "lastReviewCheck_json": last_review_check or [],
            "createdAt": task.get("createdAt"),
            "updatedAt": task.get("updatedAt"),
            "completedAt": task.get("completedAt"),
            "source_json": task.get("source", {}),
        }
        body_lines = [
            "## Description",
            task.get("description", "") or "_No description_",
            "",
            "## Comments",
        ]
        if comments:
            for comment in comments:
                body_lines.append(f"### {comment.get('author', 'user')} — {comment.get('createdAt', '')}")
                body_lines.append(comment.get("text", ""))
                body_lines.append("")
        else:
            body_lines.append("No comments yet")
        body_lines.extend(["", "## Attachments"])
        if attachments:
            for att in attachments:
                body_lines.append(f"- {att}")
        else:
            body_lines.append("No attachments")
        if review_check:
            body_lines.extend(["", "## Review Check"])
            for item in review_check:
                body_lines.append(f"- {item.get('status', 'pending')}: {item.get('text', '')}")
        if last_review_check:
            body_lines.extend(["", "## Last Review Check"])
            for item in last_review_check:
                body_lines.append(f"- {item.get('status', 'pending')}: {item.get('text', '')}")
        _atomic_write(path, _dump_frontmatter(meta) + "\n" + "\n".join(body_lines).rstrip() + "\n")

    def _read_all_projects(self) -> List[Dict[str, Any]]:
        projects: List[Dict[str, Any]] = []
        for entry in sorted(os.listdir(self.projects_dir)):
            project_dir = os.path.join(self.projects_dir, entry)
            project_md = os.path.join(project_dir, "project.md")
            if not os.path.isfile(project_md):
                continue
            try:
                projects.append(self._read_project_dir(project_dir))
            except Exception:
                continue
        return projects

    def _read_project_dir(self, project_dir: str) -> Dict[str, Any]:
        with open(os.path.join(project_dir, "project.md"), "r", encoding="utf-8") as f:
            meta, body = _parse_frontmatter(f.read())
        project = {
            "id": meta.get("id") or self.new_id(),
            "title": meta.get("title", ""),
            "projectType": meta.get("projectType", "one_time"),
            "description": self._extract_section(body, "Project"),
            "status": meta.get("status", "active"),
            "priority": meta.get("priority", "medium"),
            "createdAt": meta.get("createdAt") or self.now(),
            "updatedAt": meta.get("updatedAt") or self.now(),
            "dueDate": meta.get("dueDate"),
            "createdBy": meta.get("createdBy", "user"),
            "tags": meta.get("tags_json", []),
            "branch": meta.get("branch", ""),
            "longTermProject": meta.get("longTermProject", False),
            "highPriorityAiMeetingAutoApprove": meta.get("highPriorityAiMeetingAutoApprove", False),
            "archiveMaintenanceEnabled": meta.get("archiveMaintenanceEnabled"),
            "archiveMaintenance": meta.get("archiveMaintenance_json", {}),
            "projectExecutionEnabled": meta.get("projectExecutionEnabled", False),
            "workspacePath": meta.get("workspacePath"),
            "workspaceKind": meta.get("workspaceKind"),
            "workspaceStatus": meta.get("workspaceStatus_json", {}),
            "workspaceManagedBy": meta.get("workspaceManagedBy"),
            "workspaceCreatedAt": meta.get("workspaceCreatedAt"),
            "defaultExecutorAgentId": meta.get("defaultExecutorAgentId"),
            "defaultReviewerAgentId": meta.get("defaultReviewerAgentId"),
            "projectExecutionStartMode": meta.get("projectExecutionStartMode", "continuous"),
            "projectExecutionFlowActive": meta.get("projectExecutionFlowActive", False),
            "projectExecutionFlowStopReason": meta.get("projectExecutionFlowStopReason"),
            "scheduledCronPaused": meta.get("scheduledCronPaused", False),
            "scheduledCronHistory": meta.get("scheduledCronHistory_json", []),
            "executionPolicy": meta.get("executionPolicy_json", {"maxActiveTasks": 1}),
            "executionDirtyConfirmations": meta.get("executionDirtyConfirmations_json", []),
            "feishuNotifications": meta.get("feishuNotifications_json", {}),
            "columns": meta.get("columns_json", []),
            "workflowActive": meta.get("workflowActive", False),
            "workflowPhase": meta.get("workflowPhase", "idle"),
            "activeTaskId": meta.get("activeTaskId"),
            "activeAgent": meta.get("activeAgent"),
            "autoMode": meta.get("autoMode", False),
            "template": meta.get("template", False),
            "templates": meta.get("templates_json", []),
            "agentMaintenanceMode": meta.get("agentMaintenanceMode", "strict_confirmation"),
            "authoringAgentId": meta.get("authoringAgentId"),
            "authoringRequestId": meta.get("authoringRequestId"),
            "authoringSource": meta.get("authoringSource_json", {}),
            "templateRef": meta.get("templateRef_json", {}),
            "recurrenceRef": meta.get("recurrenceRef_json", {}),
            "activity": self._parse_activity(self._extract_section(body, "Activity")),
            "tasks": [],
        }
        tasks_dir = os.path.join(project_dir, "tasks")
        if os.path.isdir(tasks_dir):
            for name in sorted(os.listdir(tasks_dir)):
                if not name.endswith(".md"):
                    continue
                task = self._read_task_file(os.path.join(tasks_dir, name))
                if task:
                    project["tasks"].append(task)
        return project

    def _read_task_file(self, path: str) -> Optional[Dict[str, Any]]:
        with open(path, "r", encoding="utf-8") as f:
            meta, body = _parse_frontmatter(f.read())
        description = self._extract_section(body, "Description")
        comments = self._parse_comments(self._extract_section(body, "Comments"))
        task = {
            "id": meta.get("id") or self.new_id(),
            "title": meta.get("title", ""),
            "description": description if description and description != "_No description_" else "",
            "columnId": meta.get("columnId"),
            "order": meta.get("order", 0),
            "priority": meta.get("priority", "medium"),
            "assignee": meta.get("assignee"),
            "assigneeBranch": meta.get("assigneeBranch"),
            "executorAgentId": meta.get("executorAgentId") or meta.get("assignee"),
            "reviewerAgentId": meta.get("reviewerAgentId"),
            "responsibleActor": meta.get("responsibleActor_json"),
            "executorActor": meta.get("executorActor_json"),
            "reviewerActor": meta.get("reviewerActor_json"),
            "reviewerRecommendation": meta.get("reviewerRecommendation_json", {}),
            "maintenanceHistory": meta.get("maintenanceHistory_json", []),
            "requiresUserAcceptance": meta.get("requiresUserAcceptance", True),
            "allowReviewerlessExecution": meta.get("allowReviewerlessExecution", False),
            "scheduledRepeatEnabled": meta.get("scheduledRepeatEnabled", False),
            "executionState": meta.get("executionState") or ("done" if meta.get("completedAt") else "backlog"),
            "activeAttemptId": meta.get("activeAttemptId"),
            "attempts": meta.get("attempts_json", []),
            "evidence": meta.get("evidence_json", {}),
            "reviewResult": meta.get("reviewResult_json", {}),
            "reviewHistory": meta.get("reviewHistory_json", []),
            "acceptanceHistory": meta.get("acceptanceHistory_json", []),
            "meetingBlocker": meta.get("meetingBlocker_json", {}),
            "meetingBlockerHistory": meta.get("meetingBlockerHistory_json", []),
            "meetingActionItems": meta.get("meetingActionItems_json", []),
            "meetingDecisionHistory": meta.get("meetingDecisionHistory_json", []),
            "meetingDiscussionPoints": meta.get("meetingDiscussionPoints_json", []),
            "meetingRecords": meta.get("meetingRecords_json", []),
            "feishuNotifications": meta.get("feishuNotifications_json", {}),
            "reworkCount": meta.get("reworkCount", 0),
            "stateHistory": meta.get("stateHistory_json", []),
            "blockedReason": meta.get("blockedReason"),
            "reworkFeedback": meta.get("reworkFeedback"),
            "lastError": meta.get("lastError"),
            "dueDate": meta.get("dueDate"),
            "tags": meta.get("tags_json", []),
            "checklist": meta.get("checklist_json", []),
            "comments": comments,
            "attachments": meta.get("attachments_json", []),
            "createdAt": meta.get("createdAt") or self.now(),
            "updatedAt": meta.get("updatedAt") or self.now(),
            "completedAt": meta.get("completedAt"),
            "source": meta.get("source_json", {}),
        }
        review_check = meta.get("reviewCheck_json", [])
        if review_check:
            task["reviewCheck"] = review_check
        last_review_check = meta.get("lastReviewCheck_json", [])
        if last_review_check:
            task["lastReviewCheck"] = last_review_check
        try:
            actors = task_actor_references(task)
        except ValueError:
            actors = {}
        if task.get("responsibleActor") is None:
            task["responsibleActor"] = actors.get("responsible")
        if task.get("executorActor") is None:
            task["executorActor"] = actors.get("executor")
        if task.get("reviewerActor") is None:
            task["reviewerActor"] = actors.get("reviewer")
        return task

    def _extract_section(self, body: str, heading: str) -> str:
        if not body:
            return ""
        lines = body.splitlines()
        target_level = None
        collecting = False
        buf: List[str] = []
        for line in lines:
            match = re.match(r"^(#+)\s+(.*)$", line.strip())
            if match and match.group(2) == heading:
                target_level = len(match.group(1))
                collecting = True
                continue
            if collecting and match and (target_level == 1 or len(match.group(1)) <= (target_level or 1)):
                break
            if collecting:
                buf.append(line)
        return "\n".join(buf).strip()

    def _parse_checklist(self, text: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for line in text.splitlines():
            m = re.match(r"- \[(.| )\] (.*)", line.strip())
            if m:
                items.append({"text": m.group(2).strip(), "done": m.group(1).lower() == "x"})
        return items

    def _parse_comments(self, text: str) -> List[Dict[str, Any]]:
        comments: List[Dict[str, Any]] = []
        if not text or text.strip() == "No comments yet":
            return comments
        parts = re.split(r"^### ", text, flags=re.M)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            first_line, *rest = part.splitlines()
            if " — " in first_line:
                author, created_at = first_line.split(" — ", 1)
            else:
                author, created_at = first_line, ""
            comments.append({"id": self.new_id(), "author": author.strip(), "createdAt": created_at.strip(), "text": "\n".join(rest).strip()})
        return comments

    def _parse_attachments(self, text: str) -> List[str]:
        items: List[str] = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("- "):
                items.append(line[2:].strip())
        return items

    def _parse_review_check(self, text: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("- "):
                continue
            body = line[2:]
            if ": " in body:
                status, label = body.split(": ", 1)
                items.append({"id": self.new_id(), "status": status.strip(), "text": label.strip()})
        return items

    def _parse_activity(self, text: str) -> List[Dict[str, Any]]:
        activity: List[Dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            m = re.match(r"- \[(.*?)\] \((.*?)\) (.*)", line)
            if m:
                activity.append({"type": "activity", "at": m.group(1), "by": m.group(2), "detail": m.group(3)})
        return activity
