#!/usr/bin/env python3
"""Focused coverage for the Project Execution foundation."""

import os
import json
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
IMPORT_STATUS_DIR = tempfile.mkdtemp(prefix="vo-project-execution-import-")
os.environ["VO_STATUS_DIR"] = IMPORT_STATUS_DIR

import server
from feishu_notifications import build_feishu_card
from project_store import MarkdownProjectStore


AGENTS = [
    {"id": "executor", "statusKey": "executor", "providerAgentId": "executor", "providerKind": "openclaw", "name": "Executor"},
    {"id": "reviewer", "statusKey": "reviewer", "providerAgentId": "reviewer", "providerKind": "openclaw", "name": "Reviewer"},
    {"id": "alt-executor", "statusKey": "alt-executor", "providerAgentId": "alt-executor", "providerKind": "openclaw", "name": "Alt Executor"},
    {"id": "alt-reviewer", "statusKey": "alt-reviewer", "providerAgentId": "alt-reviewer", "providerKind": "openclaw", "name": "Alt Reviewer"},
    {"id": "hermes-executor", "statusKey": "hermes-executor", "providerAgentId": "hermes-executor", "providerKind": "hermes", "name": "Hermes Executor"},
    {"id": "codex-executor", "statusKey": "codex-executor", "providerAgentId": "codex-executor", "providerKind": "codex", "name": "Codex Executor"},
]


def wait_for(predicate, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("timed out")


def with_store(status_dir):
    old = (server.STATUS_DIR, server.PROJECT_STORE, server.get_roster)
    server.STATUS_DIR = status_dir
    server.PROJECT_STORE = MarkdownProjectStore(status_dir)
    server.get_roster = lambda: AGENTS
    return old


def restore_store(old):
    server.STATUS_DIR, server.PROJECT_STORE, server.get_roster = old


def restore_attrs(pairs):
    for owner, name, value in pairs:
        setattr(owner, name, value)


def fake_feishu_sender(calls):
    def _send(intent, **kwargs):
        calls.append({"intent": intent, "kwargs": kwargs})
        return {
            "ok": True,
            "status": "sent",
            "channel": "test",
            "record": {"id": intent.get("id"), "type": intent.get("type"), "title": intent.get("title")},
        }
    return _send


def create_project_execution_project(workspace):
    project = server._handle_project_create({
        "title": "Project Execution Test",
        "projectExecutionEnabled": True,
        "workspacePath": workspace,
        "defaultExecutorAgentId": "executor",
        "defaultReviewerAgentId": "reviewer",
    })["project"]
    validation = server._handle_project_execution_workspace_validate(project["id"], {"workspacePath": workspace})
    assert validation["ok"] is True
    task = server._handle_task_create(project["id"], {
        "title": "Implement fixture",
        "columnId": project["columns"][0]["id"],
        "assignee": "executor",
        "executorAgentId": "executor",
    })["task"]
    return project, task


def col_id(project, title):
    return next(c["id"] for c in project["columns"] if c["title"] == title)


def test_project_store_round_trip_and_legacy_defaults():
    with tempfile.TemporaryDirectory() as status_dir:
        store = MarkdownProjectStore(status_dir)
        store.save_all({"projects": [{
            "id": "p1", "title": "P1", "columns": [], "tasks": [{"id": "t1", "title": "T1", "completedAt": None}],
            "projectExecutionEnabled": True, "workspacePath": "/tmp/work", "workspaceKind": "directory",
            "workspaceStatus": {"ok": True}, "defaultExecutorAgentId": "executor", "defaultReviewerAgentId": "reviewer",
            "workflowActive": True, "workflowPhase": "executing", "activeTaskId": "t1", "activeAgent": "executor",
        }]})
        loaded = store.load_all()["projects"][0]
        assert loaded["workspacePath"] == "/tmp/work"
        assert loaded["workspaceManagedBy"] is None
        assert loaded["defaultReviewerAgentId"] == "reviewer"
        assert loaded["workflowPhase"] == "executing"
        assert loaded["activeTaskId"] == "t1"
        assert loaded["tasks"][0]["executionState"] == "backlog"
        assert loaded["tasks"][0]["attempts"] == []


def test_workflow_chat_reads_project_execution_codex_attempt_reasoning():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        old_activity = server._get_codex_activity
        try:
            project = server._handle_project_create({
                "title": "Codex Chat Project",
                "projectExecutionEnabled": True,
                "workspacePath": status_dir,
                "defaultExecutorAgentId": "codex-executor",
                "defaultReviewerAgentId": "reviewer",
            })["project"]
            task = server._handle_task_create(project["id"], {"title": "Show reasoning", "columnId": project["columns"][0]["id"]})["task"]
            project = server._handle_project_get(project["id"])["project"]
            task = next(t for t in project["tasks"] if t["id"] == task["id"])
            attempt_id = "attempt-chat-1"
            task["activeAttemptId"] = attempt_id
            task["executorAgentId"] = "codex-executor"
            task["attempts"] = [{"id": attempt_id, "status": "executing", "executor": {"id": "codex-executor", "providerKind": "codex"}}]
            project.update({"workflowActive": True, "workflowPhase": "executing", "activeTaskId": task["id"], "activeAgent": "codex-executor"})
            server._save_projects({"projects": [project]})

            calls = []
            def fake_activity(agent_id, conversation_id, after=0):
                calls.append((agent_id, conversation_id, after))
                return [{
                    "id": "evt-1",
                    "type": "reasoning",
                    "text": "I am planning the active backlog task.",
                    "status": "running",
                    "ts": 123,
                    "operationId": "op-1",
                }]

            server._get_codex_activity = fake_activity
            result = server._handle_workflow_chat(project["id"])
            assert result["agent"] == "codex-executor"
            assert result["taskId"] == task["id"]
            assert calls == [("codex-executor", attempt_id, 0)]
            assert result["messages"][0]["thinking"] == "I am planning the active backlog task."
        finally:
            server._get_codex_activity = old_activity
            restore_store(old)


def test_openclaw_workflow_chat_reads_gateway_prefixed_session_file():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as openclaw_home:
        old = with_store(status_dir)
        old_config = server.VO_CONFIG
        try:
            project = server._handle_project_create({
                "title": "OpenClaw Chat Project",
                "projectExecutionEnabled": True,
                "workspacePath": status_dir,
                "defaultExecutorAgentId": "executor",
                "defaultReviewerAgentId": "reviewer",
            })["project"]
            task = server._handle_task_create(project["id"], {"title": "Show transcript", "columnId": project["columns"][0]["id"]})["task"]
            project = server._handle_project_get(project["id"])["project"]
            task = next(t for t in project["tasks"] if t["id"] == task["id"])
            project.update({"workflowActive": True, "workflowPhase": "executing", "activeTaskId": task["id"], "activeAgent": "executor"})
            task.update({"activeAttemptId": "attempt-openclaw", "executorAgentId": "executor"})
            server._save_projects({"projects": [project]})

            sessions_dir = os.path.join(openclaw_home, "agents", "executor", "sessions")
            os.makedirs(sessions_dir, exist_ok=True)
            session_file = os.path.join(sessions_dir, "session-1.jsonl")
            session_key = server._wf_task_session_key("executor", project["id"], "attempt-openclaw")
            with open(os.path.join(sessions_dir, "sessions.json"), "w", encoding="utf-8") as f:
                json.dump({f"agent:executor:{session_key}": {"sessionId": "ignored", "sessionFile": session_file, "status": "running"}}, f)
            with open(session_file, "w", encoding="utf-8") as f:
                f.write(json.dumps({"message": {"role": "assistant", "content": [{"type": "text", "text": "OpenClaw transcript visible"}], "timestamp": 456}}) + "\n")

            server.VO_CONFIG = {**server.VO_CONFIG, "openclaw": {**server.VO_CONFIG.get("openclaw", {}), "homePath": openclaw_home}}
            result = server._handle_workflow_chat(project["id"])
            assert result["messages"][0]["text"] == "OpenClaw transcript visible"
            assert result["sessionActive"] is True
        finally:
            server.VO_CONFIG = old_config
            restore_store(old)


def test_workflow_chat_reads_project_execution_hermes_attempt_history_only():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            project = server._handle_project_create({
                "title": "Hermes Chat Project",
                "projectExecutionEnabled": True,
                "workspacePath": status_dir,
                "defaultExecutorAgentId": "hermes-executor",
                "defaultReviewerAgentId": "reviewer",
            })["project"]
            task = server._handle_task_create(project["id"], {"title": "Show Hermes reasoning", "columnId": project["columns"][0]["id"]})["task"]
            project = server._handle_project_get(project["id"])["project"]
            task = next(t for t in project["tasks"] if t["id"] == task["id"])
            attempt_id = "attempt-hermes-1"
            task["activeAttemptId"] = attempt_id
            task["executorAgentId"] = "hermes-executor"
            task["attempts"] = [{"id": attempt_id, "status": "executing", "executor": {"id": "hermes-executor", "providerKind": "hermes"}}]
            project.update({"workflowActive": True, "workflowPhase": "executing", "activeTaskId": task["id"], "activeAgent": "hermes-executor"})
            server._save_projects({"projects": [project]})

            server._save_hermes_history("hermes-executor", [{"role": "assistant", "text": "old global thought", "ts": 1}])
            server._save_hermes_history("hermes-executor", [{"role": "assistant", "text": "current project thought", "ts": 2}], attempt_id)

            result = server._handle_workflow_chat(project["id"])
            texts = [m.get("text") for m in result["messages"]]
            assert result["agent"] == "hermes-executor"
            assert "current project thought" in texts
            assert "old global thought" not in texts
        finally:
            restore_store(old)


def test_project_execution_hermes_call_uses_attempt_conversation_id():
    calls = []
    old_handle = server._handle_hermes_chat
    try:
        def fake_hermes_chat(body):
            calls.append(body)
            return {"ok": True, "reply": "done", "conversationId": body.get("conversationId")}

        server._handle_hermes_chat = fake_hermes_chat
        result = server._project_execution_call_executor(
            {"id": "hermes-executor", "providerKind": "hermes"},
            "prompt",
            "/tmp/workspace",
            "attempt-hermes-call",
            project_id="project-1",
            task_id="task-1",
        )
        assert result["ok"] is True
        assert calls[0]["conversationId"] == "attempt-hermes-call"
    finally:
        server._handle_hermes_chat = old_handle


def test_project_execution_openclaw_executor_uses_attempt_session_id():
    calls = []
    old_call = server._wf_call_agent
    try:
        def fake_call(agent_id, message, timeout=600, project_id=None, task_id=None):
            calls.append({"agentId": agent_id, "projectId": project_id, "taskId": task_id})
            return "done"

        server._wf_call_agent = fake_call
        result = server._project_execution_call_executor(
            {"id": "executor", "providerKind": "openclaw"},
            "prompt",
            "/tmp/workspace",
            "attempt-openclaw-call",
            project_id="project-1",
            task_id="task-1",
        )
        assert result["ok"] is True
        assert calls == [{"agentId": "executor", "projectId": "project-1", "taskId": "attempt-openclaw-call"}]
    finally:
        server._wf_call_agent = old_call


def test_project_execution_openclaw_reviewer_uses_review_session_id():
    calls = []
    old_call = server._wf_call_agent
    try:
        def fake_call(agent_id, message, timeout=600, project_id=None, task_id=None):
            calls.append({"agentId": agent_id, "projectId": project_id, "taskId": task_id})
            return '{"status":"pass","summary":"ok","rationale":"verified","items":[]}'

        server._wf_call_agent = fake_call
        result = server._project_execution_call_reviewer(
            {"id": "reviewer", "providerKind": "openclaw"},
            "prompt",
            "review-openclaw-call",
            project_id="project-1",
            task_id="task-1",
        )
        assert result["ok"] is True
        assert calls == [{"agentId": "reviewer", "projectId": "project-1", "taskId": "review-openclaw-call"}]
    finally:
        server._wf_call_agent = old_call


def test_project_create_auto_workspace_and_store_round_trip():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        old_auto_root = os.environ.get("VO_AUTO_PROJECT_WORKSPACE_ROOT")
        auto_root = os.path.join(status_dir, "auto-root")
        os.environ["VO_AUTO_PROJECT_WORKSPACE_ROOT"] = auto_root
        try:
            created = server._handle_project_create({
                "title": "Demo Project",
                "projectExecutionEnabled": True,
                "defaultExecutorAgentId": "executor",
                "defaultReviewerAgentId": "reviewer",
            })
            assert created["ok"] is True
            project = created["project"]
            assert project["projectExecutionEnabled"] is True
            assert project["workspaceManagedBy"] == "system"
            assert project["workspaceCreatedAt"]
            assert project["workspaceStatus"]["ok"] is True
            assert project["workspaceKind"] == "directory"
            assert os.path.isdir(project["workspacePath"])
            assert os.path.realpath(project["workspacePath"]).startswith(os.path.realpath(auto_root) + os.sep)
            assert os.path.basename(project["workspacePath"]).startswith("demo-project-")
            assert os.path.basename(project["workspacePath"]).split("-")[-1].isdigit()

            loaded = server._load_projects()["projects"][0]
            assert loaded["workspacePath"] == project["workspacePath"]
            assert loaded["workspaceManagedBy"] == "system"
            assert loaded["workspaceCreatedAt"] == project["workspaceCreatedAt"]
        finally:
            if old_auto_root is None:
                os.environ.pop("VO_AUTO_PROJECT_WORKSPACE_ROOT", None)
            else:
                os.environ["VO_AUTO_PROJECT_WORKSPACE_ROOT"] = old_auto_root
            restore_store(old)


def test_project_create_normal_and_manual_workspace_provenance():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        try:
            normal = server._handle_project_create({"title": "Normal Project", "projectExecutionEnabled": False})
            assert normal["ok"] is True
            assert normal["project"]["projectExecutionEnabled"] is False
            assert normal["project"]["workspacePath"] is None
            assert normal["project"]["workspaceManagedBy"] is None

            manual = server._handle_project_create({
                "title": "Manual Project",
                "projectExecutionEnabled": True,
                "workspacePath": workspace,
            })
            assert manual["ok"] is True
            assert manual["project"]["projectExecutionEnabled"] is True
            assert manual["project"]["workspacePath"] == os.path.realpath(workspace)
            assert manual["project"]["workspaceManagedBy"] == "user"
        finally:
            restore_store(old)


def test_project_from_template_auto_workspace_matches_project_create():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        old_auto_root = os.environ.get("VO_AUTO_PROJECT_WORKSPACE_ROOT")
        os.environ["VO_AUTO_PROJECT_WORKSPACE_ROOT"] = os.path.join(status_dir, "auto-root")
        try:
            created = server._handle_project_from_template({
                "templateId": "tpl-software",
                "title": "Template Project",
                "projectExecutionEnabled": True,
            })
            assert created["ok"] is True
            project = created["project"]
            assert project["projectExecutionEnabled"] is True
            assert project["workspaceManagedBy"] == "system"
            assert os.path.isdir(project["workspacePath"])
            assert os.path.basename(project["workspacePath"]).startswith("template-project-")

            normal = server._handle_project_from_template({
                "templateId": "tpl-software",
                "title": "Template Normal",
                "projectExecutionEnabled": False,
            })
            assert normal["ok"] is True
            assert normal["project"]["projectExecutionEnabled"] is False
            assert normal["project"]["workspacePath"] is None
        finally:
            if old_auto_root is None:
                os.environ.pop("VO_AUTO_PROJECT_WORKSPACE_ROOT", None)
            else:
                os.environ["VO_AUTO_PROJECT_WORKSPACE_ROOT"] = old_auto_root
            restore_store(old)


def test_project_delete_auto_workspace_keep_or_delete_and_never_delete_user_workspace():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as user_workspace:
        old = with_store(status_dir)
        old_auto_root = os.environ.get("VO_AUTO_PROJECT_WORKSPACE_ROOT")
        os.environ["VO_AUTO_PROJECT_WORKSPACE_ROOT"] = os.path.join(status_dir, "auto-root")
        try:
            keep = server._handle_project_create({"title": "Keep Workspace", "projectExecutionEnabled": True})["project"]
            keep_path = keep["workspacePath"]
            kept = server._handle_project_delete(keep["id"], delete_workspace=False)
            assert kept["ok"] is True
            assert kept["workspaceDeleted"] is False
            assert os.path.isdir(keep_path)

            remove = server._handle_project_create({"title": "Remove Workspace", "projectExecutionEnabled": True})["project"]
            remove_path = remove["workspacePath"]
            removed = server._handle_project_delete(remove["id"], delete_workspace=True)
            assert removed["ok"] is True
            assert removed["workspaceDeleted"] is True
            assert not os.path.exists(remove_path)

            user = server._handle_project_create({
                "title": "User Workspace",
                "projectExecutionEnabled": True,
                "workspacePath": user_workspace,
            })["project"]
            user_deleted = server._handle_project_delete(user["id"], delete_workspace=True)
            assert user_deleted["ok"] is True
            assert user_deleted["workspaceDeleted"] is False
            assert "workspaceDeleteError" in user_deleted
            assert os.path.isdir(user_workspace)
        finally:
            if old_auto_root is None:
                os.environ.pop("VO_AUTO_PROJECT_WORKSPACE_ROOT", None)
            else:
                os.environ["VO_AUTO_PROJECT_WORKSPACE_ROOT"] = old_auto_root
            restore_store(old)


def test_auto_workspace_create_failure_does_not_create_project():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        old_auto_root = os.environ.get("VO_AUTO_PROJECT_WORKSPACE_ROOT")
        blocker = os.path.join(status_dir, "not-a-dir")
        with open(blocker, "w", encoding="utf-8") as f:
            f.write("x\n")
        os.environ["VO_AUTO_PROJECT_WORKSPACE_ROOT"] = blocker
        try:
            result = server._handle_project_create({"title": "Cannot Create Workspace", "projectExecutionEnabled": True})
            assert result["_status"] == 400
            assert result["code"] == "workspace_root_create_failed"
            assert server._load_projects()["projects"] == []
        finally:
            if old_auto_root is None:
                os.environ.pop("VO_AUTO_PROJECT_WORKSPACE_ROOT", None)
            else:
                os.environ["VO_AUTO_PROJECT_WORKSPACE_ROOT"] = old_auto_root
            restore_store(old)


def test_workspace_validation_and_dirty_fingerprint():
    with tempfile.TemporaryDirectory() as workspace:
        assert server._project_execution_validate_workspace(workspace)["kind"] == "directory"
        subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
        with open(os.path.join(workspace, "tracked.txt"), "w", encoding="utf-8") as f:
            f.write("dirty\n")
        snapshot = server._project_execution_git_snapshot(workspace)
        assert snapshot["kind"] == "git"
        assert snapshot["dirty"] is True
        assert snapshot["fingerprint"]
        assert "tracked.txt" in snapshot["files"]
        assert server._project_execution_validate_workspace(os.path.join(workspace, "missing"))["ok"] is False


def test_workspace_validation_rejects_files_and_outside_allowed_roots():
    old_roots = os.environ.get("VO_PROJECT_ROOTS")
    with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as outside:
        file_path = os.path.join(allowed, "not-a-dir.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("x\n")
        assert server._project_execution_validate_workspace(file_path)["code"] == "workspace_not_directory"

        os.environ["VO_PROJECT_ROOTS"] = allowed
        assert server._project_execution_validate_workspace(allowed)["ok"] is True
        escaped_link = os.path.join(allowed, "escaped")
        os.symlink(outside, escaped_link)
        escaped = server._project_execution_validate_workspace(escaped_link)
        assert escaped["ok"] is False
        assert escaped["code"] == "workspace_outside_roots"
    if old_roots is None:
        os.environ.pop("VO_PROJECT_ROOTS", None)
    else:
        os.environ["VO_PROJECT_ROOTS"] = old_roots


def test_artifact_core_lists_markdown_only_and_reads_safely():
    with tempfile.TemporaryDirectory() as workspace:
        os.makedirs(os.path.join(workspace, "docs"), exist_ok=True)
        os.makedirs(os.path.join(workspace, "node_modules", "pkg"), exist_ok=True)
        with open(os.path.join(workspace, "docs", "guide.md"), "w", encoding="utf-8") as f:
            f.write("# Guide\n\nhello")
        with open(os.path.join(workspace, "docs", "data.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        with open(os.path.join(workspace, "docs", "large.markdown"), "w", encoding="utf-8") as f:
            f.write("x" * (server._ARTIFACT_MAX_READ_BYTES + 20))
        with open(os.path.join(workspace, "node_modules", "pkg", "README.md"), "w", encoding="utf-8") as f:
            f.write("# Dependency")

        context = {"root": workspace, "sourcesByPath": {}}
        listed = server._artifact_context_list(context)
        assert listed["ok"] is True
        assert {a["path"] for a in listed["artifacts"]} == {"docs/guide.md", "docs/large.markdown"}
        assert all(a["unassociated"] is True for a in listed["artifacts"])

        read = server._artifact_context_read(context, "docs/guide.md")
        assert read["ok"] is True
        assert read["artifact"]["content"].startswith("# Guide")
        large = server._artifact_context_read(context, "docs/large.markdown")
        assert large["ok"] is True
        assert large["artifact"]["truncated"] is True
        assert len(large["artifact"]["content"]) == server._ARTIFACT_MAX_READ_BYTES
        assert server._artifact_context_read(context, "docs/data.json")["_status"] == 415
        assert server._artifact_context_read(context, "../outside.md")["_status"] == 400

        outside = tempfile.NamedTemporaryFile(delete=False, suffix=".md")
        outside.close()
        try:
            os.symlink(outside.name, os.path.join(workspace, "docs", "escape.md"))
            assert server._artifact_context_read(context, "docs/escape.md")["_status"] == 403
        finally:
            os.unlink(outside.name)


def test_project_artifacts_include_phase7_source_records():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        try:
            os.makedirs(os.path.join(workspace, "docs"), exist_ok=True)
            os.makedirs(os.path.join(workspace, "other"), exist_ok=True)
            with open(os.path.join(workspace, "docs", "artifact.md"), "w", encoding="utf-8") as f:
                f.write("# Artifact")
            with open(os.path.join(workspace, "docs", "manual.md"), "w", encoding="utf-8") as f:
                f.write("# Manual")
            with open(os.path.join(workspace, "docs", "hermes-summary.md"), "w", encoding="utf-8") as f:
                f.write("# Hermes Summary")
            with open(os.path.join(workspace, "other", "artifact.md"), "w", encoding="utf-8") as f:
                f.write("# Other")
            project, task = create_project_execution_project(workspace)
            data = server._load_projects()
            project = data["projects"][0]
            task = project["tasks"][0]
            later_task = server._handle_task_create(project["id"], {"title": "Refresh fixture", "columnId": project["columns"][0]["id"]})["task"]
            data = server._load_projects()
            project = data["projects"][0]
            task = project["tasks"][0]
            later_task = project["tasks"][1]
            task["evidence"] = {
                "attemptId": "attempt-1",
                "changedFiles": ["docs/artifact.md", "docs/not-shown.json"],
                "capturedAt": "2026-06-11T00:00:00+00:00",
                "providerRef": {"providerKind": "codex", "agentId": "codex-executor"},
            }
            task["attempts"] = [{
                "id": "attempt-1",
                "executor": {"id": "codex-executor", "providerKind": "codex"},
                "evidence": task["evidence"],
            }]
            later_task["evidence"] = {
                "attemptId": "attempt-2",
                "changedFiles": ["docs/artifact.md"],
                "capturedAt": "2026-06-12T00:00:00+00:00",
                "providerRef": {"providerKind": "hermes", "agentId": "hermes-executor"},
            }
            later_task["attempts"] = [{
                "id": "attempt-2",
                "executor": {"id": "hermes-executor", "providerKind": "hermes"},
                "evidence": later_task["evidence"],
            }, {
                "id": "attempt-3",
                "executor": {"id": "hermes-executor", "providerKind": "hermes"},
                "evidence": {
                    "attemptId": "attempt-3",
                    "changedFiles": [],
                    "capturedAt": "2026-06-13T00:00:00+00:00",
                    "executorSummary": f"review diff a/{workspace}/docs/hermes-summary.md -> b/{workspace}/docs/hermes-summary.md",
                    "providerRef": {"providerKind": "hermes", "agentId": "hermes-executor"},
                },
            }]
            server._save_projects(data)

            listed = server._handle_project_artifacts_list(project["id"])
            assert listed["ok"] is True
            by_path = {a["path"]: a for a in listed["artifacts"]}
            assert set(by_path) == {"docs/artifact.md", "docs/hermes-summary.md", "docs/manual.md", "other/artifact.md"}
            source = by_path["docs/artifact.md"]["sources"][0]
            assert source["taskId"] == later_task["id"]
            assert source["taskTitle"] == later_task["title"]
            assert source["agentId"] == "hermes-executor"
            assert source["providerKind"] == "hermes"
            assert source["attemptId"] == "attempt-2"
            assert by_path["docs/artifact.md"]["sources"][1]["taskId"] == task["id"]
            assert len(by_path["docs/artifact.md"]["sources"]) == 2
            hermes_summary_source = by_path["docs/hermes-summary.md"]["sources"][0]
            assert hermes_summary_source["taskId"] == later_task["id"]
            assert hermes_summary_source["agentId"] == "hermes-executor"
            assert hermes_summary_source["providerKind"] == "hermes"
            assert hermes_summary_source["attemptId"] == "attempt-3"
            assert by_path["docs/manual.md"]["unassociated"] is True
            assert by_path["other/artifact.md"]["unassociated"] is True

            read = server._handle_project_artifact_read(project["id"], "path=docs%2Fartifact.md")
            assert read["ok"] is True
            assert read["artifact"]["content"] == "# Artifact"
        finally:
            restore_store(old)


def test_project_artifacts_reject_disabled_or_missing_workspace_projects():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        try:
            project, _ = create_project_execution_project(workspace)
            listed = server._handle_project_artifacts_list(project["id"])
            assert listed["ok"] is True
            assert listed["artifacts"] == []
            assert listed["truncated"] is False

            project = server._handle_project_create({"title": "Plain Project"})["project"]
            listed = server._handle_project_artifacts_list(project["id"])
            assert listed["_status"] == 409
            assert "Project Execution workspace" in listed["error"]
        finally:
            restore_store(old)


def test_project_artifacts_real_acceptance_review_scenario():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        try:
            for rel in ["requirements", "docs", "node_modules/pkg", "reports"]:
                os.makedirs(os.path.join(workspace, rel), exist_ok=True)
            with open(os.path.join(workspace, "requirements", "acceptance.md"), "w", encoding="utf-8") as f:
                f.write("# Acceptance Notes\n\n- CHK-001 pass\n- CHK-017 source visible\n\n<script>alert('x')</script>\n")
            with open(os.path.join(workspace, "docs", "handoff.markdown"), "w", encoding="utf-8") as f:
                f.write("# Handoff\n\nReviewer requested one follow-up and it was fixed.\n")
            with open(os.path.join(workspace, "docs", "manual.md"), "w", encoding="utf-8") as f:
                f.write("# Manual Note\n\nCreated outside Project Execution evidence.\n")
            with open(os.path.join(workspace, "node_modules", "pkg", "README.md"), "w", encoding="utf-8") as f:
                f.write("# Dependency README")
            with open(os.path.join(workspace, "reports", "raw-result.json"), "w", encoding="utf-8") as f:
                f.write("{}")

            project, acceptance_task = create_project_execution_project(workspace)
            acceptance_task_id = acceptance_task["id"]
            handoff_task = server._handle_task_create(project["id"], {"title": "Address review feedback", "columnId": project["columns"][0]["id"]})["task"]
            handoff_task_id = handoff_task["id"]
            data = server._load_projects()
            project = data["projects"][0]
            acceptance_task = next(task for task in project["tasks"] if task["id"] == acceptance_task_id)
            handoff_task = next(task for task in project["tasks"] if task["id"] == handoff_task_id)
            acceptance_task["title"] = "Write acceptance notes"
            acceptance_task["evidence"] = {
                "attemptId": "attempt-acceptance",
                "changedFiles": [os.path.join(workspace, "requirements", "acceptance.md"), "reports/raw-result.json"],
                "capturedAt": "2026-06-15T02:00:00+00:00",
                "providerRef": {"providerKind": "openclaw", "agentId": "executor"},
            }
            acceptance_task["attempts"] = [{
                "id": "attempt-acceptance",
                "executor": {"id": "executor", "providerKind": "openclaw"},
                "evidence": acceptance_task["evidence"],
            }]
            acceptance_task["reviewResult"] = {
                "status": "pass",
                "changedFiles": ["requirements/acceptance.md"],
                "reviewerAgentId": "reviewer",
                "providerKind": "openclaw",
            }
            handoff_task["evidence"] = {
                "attemptId": "attempt-handoff",
                "changedFiles": ["docs/handoff.markdown"],
                "capturedAt": "2026-06-15T03:00:00+00:00",
                "providerRef": {"providerKind": "codex", "agentId": "codex-executor"},
            }
            handoff_task["attempts"] = [{
                "id": "attempt-handoff",
                "executor": {"id": "codex-executor", "providerKind": "codex"},
                "evidence": handoff_task["evidence"],
            }]
            server._save_projects(data)

            listed = server._handle_project_artifacts_list(project["id"])
            assert listed["ok"] is True
            by_path = {a["path"]: a for a in listed["artifacts"]}
            assert set(by_path) == {"requirements/acceptance.md", "docs/handoff.markdown", "docs/manual.md"}
            assert "node_modules/pkg/README.md" not in by_path
            assert "reports/raw-result.json" not in by_path

            acceptance_source = by_path["requirements/acceptance.md"]["sources"][0]
            assert acceptance_source["taskTitle"] == "Write acceptance notes"
            assert acceptance_source["agentId"] == "executor"
            assert acceptance_source["providerKind"] == "openclaw"
            assert acceptance_source["attemptId"] == "attempt-acceptance"
            assert acceptance_source["capturedAt"] == "2026-06-15T02:00:00+00:00"
            assert acceptance_source["agentId"] != "reviewer"

            handoff_source = by_path["docs/handoff.markdown"]["sources"][0]
            assert handoff_source["taskTitle"] == "Address review feedback"
            assert handoff_source["agentId"] == "codex-executor"
            assert handoff_source["providerKind"] == "codex"
            assert by_path["docs/manual.md"]["unassociated"] is True

            read = server._handle_project_artifact_read(project["id"], "path=requirements%2Facceptance.md")
            assert read["ok"] is True
            assert read["artifact"]["content"].startswith("# Acceptance Notes")
            assert "<script>alert('x')</script>" in read["artifact"]["content"]
        finally:
            restore_store(old)


def test_project_execution_project_create_rejects_invalid_workspace():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            result = server._handle_project_create({
                "title": "Invalid Workspace",
                "projectExecutionEnabled": True,
                "workspacePath": os.path.join(status_dir, "missing"),
                "defaultExecutorAgentId": "executor",
                "defaultReviewerAgentId": "reviewer",
            })
            assert result["_status"] == 400
            assert result["code"] == "workspace_missing"
            assert server._load_projects()["projects"] == []
        finally:
            restore_store(old)


def test_roles_must_be_independent():
    old_roster = server.get_roster
    server.get_roster = lambda: AGENTS
    try:
        project = {"defaultExecutorAgentId": "executor", "defaultReviewerAgentId": "reviewer"}
        assert server._project_execution_resolve_roles(project, {})["ok"] is True
        project["defaultReviewerAgentId"] = "executor"
        result = server._project_execution_resolve_roles(project, {})
        assert result["ok"] is False
        assert result["code"] == "reviewer_not_independent"
    finally:
        server.get_roster = old_roster


def test_task_role_overrides_project_defaults():
    old_roster = server.get_roster
    server.get_roster = lambda: AGENTS
    try:
        project = {"defaultExecutorAgentId": "executor", "defaultReviewerAgentId": "reviewer"}
        task = {"executorAgentId": "alt-executor", "reviewerAgentId": "alt-reviewer"}
        roles = server._project_execution_resolve_roles(project, task)
        assert roles["ok"] is True
        assert roles["executor"]["id"] == "alt-executor"
        assert roles["reviewer"]["id"] == "alt-reviewer"
    finally:
        server.get_roster = old_roster


def test_project_execution_prompt_requires_checklist_lifecycle_and_meeting_context():
    project = {"title": "Daily Report", "description": "Publish a daily report."}
    task = {"title": "日报", "description": "整理日报内容", "checklist": []}
    attempt = {"id": "attempt-1"}
    prompt = server._project_execution_build_prompt(project, task, attempt, "/tmp/workspace")
    assert "Write the task/deliverable acceptance criteria into the task checklist" in prompt
    assert "not a meeting action-item queue" in prompt
    assert "vo-operating-guidelines" in prompt
    assert "Do not confirm or reject meetings yourself" in prompt
    assert "POST /api/projects/{projectId}/tasks/{taskId}/meeting-requests" in prompt
    assert "proactively request a meeting" in prompt
    assert "Do not put those meeting action items or risks into the checklist" in prompt
    assert "Mark completed checklist items done" in prompt
    assert "continue working until it is complete" in prompt
    assert "checklistUpdates" in prompt
    assert "meetingDiscussionPoints" in prompt
    assert "FINAL RESPONSE FORMAT (strict)" in prompt
    assert "Do not print raw JSON outside the fenced json block" in prompt
    assert "tests must be an array of short strings only" in prompt


def test_project_execution_test_evidence_does_not_render_full_json_reply():
    reply = json.dumps({
        "finalAssistantVisibleText": "执行完成；测试 / 校验全部通过。",
        "checklistUpdates": [{"id": "1", "text": "完成日报", "done": True, "evidence": "已验证"}],
        "tests": ["pytest: 3 passed", {"name": "final structural check", "status": "PASS", "raw": "x" * 1000}],
    }, ensure_ascii=False)
    evidence = server._project_execution_test_evidence({"ok": True, "status": "completed", "reply": reply})
    assert evidence == ["pytest: 3 passed", "final structural check · PASS"]
    assert all("finalAssistantVisibleText" not in item for item in evidence)
    assert all(len(item) <= server._PROJECT_EXECUTION_MAX_EVIDENCE_LINE + len("...[truncated]") for item in evidence)


def test_project_execution_applies_verified_checklist_updates_from_executor():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_call = server._project_execution_call_executor
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True,
            "status": "completed",
            "reply": json.dumps({
                "summary": "implemented",
                "checklistUpdates": [
                    {"id": "c1", "text": "Run tests", "done": True, "evidence": "pytest passed"},
                    {"id": "c2", "text": "Write docs", "done": False, "evidence": "not touched"},
                ],
            }),
            "modifiedFiles": ["result.txt"],
        }
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_task_update(project["id"], task["id"], {
                "checklist": [
                    {"id": "c1", "text": "Run tests", "done": False},
                    {"id": "c2", "text": "Write docs", "done": False},
                    {"id": "m1", "text": "Meeting action", "done": False, "source": "meeting_action_item"},
                ]
            })
            started = server._handle_project_execution_start(project["id"], task["id"], {})
            assert started["ok"] is True

            def completed():
                current = server._handle_project_get(project["id"])["project"]
                current_task = next(t for t in current["tasks"] if t["id"] == task["id"])
                return current_task if current_task.get("executionState") == "execution_complete" else None

            done = wait_for(completed)
            by_id = {item["id"]: item for item in done["checklist"]}
            assert by_id["c1"]["done"] is True
            assert by_id["c1"]["completedBy"] == "executor"
            assert by_id["c1"]["completionEvidence"] == "pytest passed"
            assert by_id["c2"]["done"] is False
            assert by_id["m1"]["done"] is False
            evidence_by_id = {item["id"]: item for item in done["evidence"]["checklist"]}
            assert evidence_by_id["c1"]["done"] is True
            assert "m1" not in evidence_by_id
            assert done["evidence"]["checklistUpdated"] is True
        finally:
            server._project_execution_call_executor = old_call
            restore_store(old)


def test_project_execution_creates_checklist_items_from_executor_updates_when_empty():
    task = {"checklist": []}
    result = {
        "reply": json.dumps({
            "checklistUpdates": [
                {"id": "main-artifact", "text": "完成主要产物", "done": True, "evidence": "artifact exists"},
                {"id": "verify", "text": "完成验证", "done": False, "evidence": "not run"},
            ]
        })
    }
    changed = server._project_execution_apply_checklist_updates(task, result)
    by_id = {item["id"]: item for item in task["checklist"]}
    assert changed is True
    assert by_id["main-artifact"]["text"] == "完成主要产物"
    assert by_id["main-artifact"]["done"] is True
    assert by_id["main-artifact"]["completedBy"] == "executor"
    assert by_id["verify"]["done"] is False
    assert by_id["verify"]["source"] == "project_execution_acceptance"


def test_project_execution_matches_summarized_checklist_update_conservatively():
    long_requirement = (
        "满足任务描述要求：使用cosh-tech-daily 进行每日日报信息获取，如果有信息源不肯定的话，可以联系codex开个高优会议，"
        "请他帮忙确认，获取完信息之后请联系hermes和codex召开一个高优日报汇总会议看看大家对这个日报有什么提议和需要修改的地方，"
        "进行最后信息准确性的确认。在会议中如果达成发布结论，只有少数问题的话，可以在修改之后直接发布，不需要重新召开会议了。"
        "完成了之后生成一个日报的项目产物，名字是year_month_day/daily.md"
    )
    task = {
        "checklist": [
            {"id": "c-main", "text": "完成任务要求的主要产物：日报", "done": False},
            {"id": "c-long", "text": long_requirement, "done": False},
            {"id": "c-risk", "text": "记录执行结果、关键变更和剩余风险", "done": False},
        ]
    }
    result = {
        "reply": json.dumps({
            "checklistUpdates": [
                {
                    "id": "task-description-satisfied",
                    "text": "满足任务描述要求：使用 cosh-tech-daily 获取信息、处理不确定来源、召开 Hermes/Codex 汇总确认会议、修改后发布 year_month_day/daily.md",
                    "done": True,
                    "evidence": "日报、会议上下文和发布快照均已验证。",
                }
            ]
        })
    }
    changed = server._project_execution_apply_checklist_updates(task, result)
    by_id = {item["id"]: item for item in task["checklist"]}
    assert changed is True
    assert by_id["c-long"]["done"] is True
    assert by_id["c-long"]["completedBy"] == "executor"
    assert by_id["c-long"]["completionEvidence"] == "日报、会议上下文和发布快照均已验证。"
    assert by_id["c-main"]["done"] is False
    assert by_id["c-risk"]["done"] is False


def test_project_execution_does_not_apply_ambiguous_fuzzy_checklist_update():
    task = {
        "checklist": [
            {"id": "c1", "text": "满足任务描述要求：生成日报草稿并记录来源", "done": False},
            {"id": "c2", "text": "满足任务描述要求：生成日报终稿并记录来源", "done": False},
        ]
    }
    result = {
        "reply": json.dumps({
            "checklistUpdates": [
                {"id": "unknown", "text": "满足任务描述要求：生成日报并记录来源", "done": True}
            ]
        })
    }
    changed = server._project_execution_apply_checklist_updates(task, result)
    assert changed is False
    assert all(item["done"] is False for item in task["checklist"])


def test_project_execution_pipeline_restart_clears_execution_context():
    project = {
        "columns": [
            {"id": "todo", "name": "待办", "order": 0, "type": "todo"},
            {"id": "done", "name": "完成", "order": 1, "type": "done"},
        ],
        "tasks": [
            {
                "id": "t1",
                "title": "日报",
                "columnId": "done",
                "order": 0,
                "executionState": "done",
                "completedAt": "2026-06-24T00:00:00+00:00",
                "activeAttemptId": "attempt-1",
                "checklist": [
                    {"id": "c1", "text": "完成日报", "done": True, "completedAt": "2026-06-24T00:00:00+00:00", "completedBy": "executor", "completionEvidence": "done"},
                ],
                "meetingActionItems": [{"id": "a1", "title": "修订风险表述", "status": "pending"}],
                "meetingDecisionHistory": [{"id": "d1", "decision": "可以发布"}],
                "meetingDiscussionPoints": [{"id": "p1", "kind": "risk", "text": "链接有不确定性"}],
                "meetingRecords": [{"id": "r1", "meetingId": "m1", "outcome": "approved", "decision": "可以发布"}],
                "meetingBlocker": {"requestId": "req-1", "meetingId": "m1", "status": "resolved_continue"},
                "comments": [{"id": "comment-1", "author": "user", "text": "人工评论保留"}],
            }
        ],
    }
    result = server._project_execution_reset_project_tasks_for_restart(project, actor="test")
    task = project["tasks"][0]
    assert result["ok"] is True
    assert result["resetTaskCount"] == 1
    assert task["columnId"] == "todo"
    assert task["executionState"] == "backlog"
    assert task["completedAt"] is None
    assert task["checklist"] == []
    assert task["meetingActionItems"] == []
    assert task["meetingDecisionHistory"] == []
    assert task["meetingDiscussionPoints"] == []
    assert task["meetingRecords"] == []
    assert task["meetingBlocker"] == {}
    assert task["meetingBlockerHistory"][0]["requestId"] == "req-1"
    assert task["meetingBlockerHistory"][0]["resetReason"] == "project pipeline restart"
    assert task["comments"] == [{"id": "comment-1", "author": "user", "text": "人工评论保留"}]


def test_project_execution_manual_restart_clears_stale_meeting_bindings():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "restarted", "modifiedFiles": [],
            "checklistUpdates": [{"id": "c1", "text": "Complete implementation", "done": True}],
        }
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_task_update(project["id"], task["id"], {
                "checklist": [{"id": "c1", "text": "Complete implementation", "done": True, "completedAt": "2026-06-24T00:00:00+00:00"}],
                "meetingActionItems": [{"id": "a1", "title": "old action", "status": "pending"}],
                "meetingDecisionHistory": [{"id": "d1", "decision": "old decision"}],
                "meetingDiscussionPoints": [{"id": "p1", "kind": "risk", "text": "old risk"}],
                "meetingRecords": [{"id": "r1", "meetingId": "m1", "outcome": "approved"}],
            })
            data, stored_project = server._project_find(project["id"])
            stored_task = stored_project["tasks"][0]
            stored_task["meetingBlocker"] = {"requestId": "req-1", "meetingId": "m1", "status": "resolved_continue"}
            server._save_projects(data)

            started = server._handle_project_execution_start(project["id"], task["id"], {"resetExecutionContext": True})
            assert started["ok"] is True
            current = server._handle_project_get(project["id"])["project"]["tasks"][0]
            latest_attempt = current["attempts"][-1]
            assert latest_attempt["meetingActionPhase"] is False
            assert current["meetingActionItems"] == []
            assert current["meetingDecisionHistory"] == []
            assert current["meetingDiscussionPoints"] == []
            assert current["meetingRecords"] == []
            assert current["meetingBlocker"] == {}
            assert current["checklist"] == []
            assert current["meetingBlockerHistory"][0]["resetReason"] == "manual task restart"
        finally:
            server._project_execution_call_executor = old_executor
            restore_store(old)


def test_project_execution_meeting_result_records_discussion_points_not_comments():
    project = {"tasks": []}
    task = {"id": "task-1", "executorAgentId": "executor", "comments": [], "meetingActionItems": [], "meetingDecisionHistory": []}
    meeting = {"id": "meeting-1"}
    result = {
        "decision": "可以发布，但要保守描述。",
        "summary": "会议确认日报可发布。",
        "risks": ["部分链接可能不可达"],
        "actionItems": [],
    }
    applied = server._project_execution_apply_meeting_output_to_task(project, task, meeting, result, "request-1")
    assert applied["risks"] == 1
    assert task["comments"] == []
    assert len(task["meetingDiscussionPoints"]) == 2
    assert len(task["meetingRecords"]) == 1
    record = task["meetingRecords"][0]
    assert record["meetingId"] == "meeting-1"
    assert record["requestId"] == "request-1"
    assert record["outcome"] == "approved"
    assert record["decision"] == "可以发布，但要保守描述。"
    assert record["summary"] == "会议确认日报可发布。"
    assert record["risks"] == ["部分链接可能不可达"]
    by_kind = {item["kind"]: item for item in task["meetingDiscussionPoints"]}
    assert by_kind["decision"]["text"] == "可以发布，但要保守描述。"
    assert by_kind["risk"]["text"] == "部分链接可能不可达"

    repeated = server._project_execution_apply_meeting_output_to_task(project, task, meeting, result, "request-1")
    assert repeated["meetingRecordChanged"] is False
    assert len(task["meetingRecords"]) == 1


def test_project_execution_applies_executor_meeting_discussion_points():
    task = {"meetingDiscussionPoints": []}
    result = {
        "reply": json.dumps({
            "meetingDiscussionPoints": [
                {"kind": "decision", "title": "会议结论", "text": "同意发布", "meetingId": "m1", "requestId": "r1"},
                {"kind": "risk", "text": "链接存在波动", "meetingId": "m1"},
            ]
        })
    }
    changed = server._project_execution_apply_meeting_discussion_points(task, result)
    assert changed is True
    assert len(task["meetingDiscussionPoints"]) == 2
    by_kind = {item["kind"]: item for item in task["meetingDiscussionPoints"]}
    assert by_kind["decision"]["text"] == "同意发布"
    assert by_kind["decision"]["requestId"] == "r1"
    assert by_kind["risk"]["title"] == "风险"


def test_project_execution_assignee_defaults_executor_on_update():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        try:
            project = server._handle_project_create({
                "title": "Project Execution Test",
                "projectExecutionEnabled": True,
                "workspacePath": workspace,
                "defaultExecutorAgentId": "executor",
                "defaultReviewerAgentId": "reviewer",
            })["project"]
            task = server._handle_task_create(project["id"], {"title": "Implement fixture", "columnId": project["columns"][0]["id"]})["task"]
            assert task["assignee"] is None
            assert task["executorAgentId"] is None

            updated = server._handle_task_update(project["id"], task["id"], {"assignee": "executor"})["task"]
            assert updated["assignee"] == "executor"
            assert updated["executorAgentId"] == "executor"

            updated = server._handle_task_update(project["id"], task["id"], {"assignee": "alt-executor"})["task"]
            assert updated["assignee"] == "alt-executor"
            assert updated["executorAgentId"] == "executor"

            updated = server._handle_task_update(project["id"], task["id"], {"executorAgentId": "executor"})["task"]
            assert updated["assignee"] == "alt-executor"
            assert updated["executorAgentId"] == "executor"

            explicit = server._handle_task_update(project["id"], task["id"], {"executorAgentId": "reviewer"})["task"]
            assert explicit["assignee"] == "alt-executor"
            assert explicit["executorAgentId"] == "reviewer"
            explicit = server._handle_task_update(project["id"], task["id"], {"assignee": "alt-executor", "executorAgentId": "reviewer"})["task"]
            assert explicit["assignee"] == "alt-executor"
            assert explicit["executorAgentId"] == "reviewer"

            preserved = server._handle_task_update(project["id"], task["id"], {"assignee": "executor"})["task"]
            assert preserved["assignee"] == "executor"
            assert preserved["executorAgentId"] == "reviewer"
        finally:
            restore_store(old)


def test_provider_matrix_routes_execution_with_workspace_and_provider_ref():
    calls = []
    originals = [
        (server, "_wf_call_agent", server._wf_call_agent),
        (server, "_handle_hermes_chat", server._handle_hermes_chat),
        (server, "_handle_codex_chat", server._handle_codex_chat),
    ]

    def openclaw_call(agent_id, prompt, timeout=600, project_id=None, task_id=None):
        calls.append(("openclaw", agent_id, prompt, None))
        return "openclaw done\npytest: 1 passed"

    def hermes_call(body):
        calls.append(("hermes", body.get("agentId"), body.get("message"), None))
        return {"ok": True, "status": "completed", "reply": "hermes done", "modifiedFiles": ["hermes.txt"]}

    def codex_call(body):
        calls.append(("codex", body.get("agentId"), body.get("message"), body.get("workspace")))
        return {"ok": True, "status": "completed", "reply": "codex done", "modifiedFiles": ["codex.txt"]}

    server._wf_call_agent = openclaw_call
    server._handle_hermes_chat = hermes_call
    server._handle_codex_chat = codex_call
    try:
        for provider, agent_id in [("openclaw", "executor"), ("hermes", "hermes-executor"), ("codex", "codex-executor")]:
            with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
                old = with_store(status_dir)
                try:
                    project, task = create_project_execution_project(workspace)
                    server._handle_task_update(project["id"], task["id"], {"executorAgentId": agent_id})
                    task = complete_project_task_execution(project["id"], task["id"])
                    assert task["evidence"]["providerRef"]["providerKind"] == provider
                    assert task["evidence"]["providerRef"]["agentId"] == agent_id
                finally:
                    restore_store(old)
        assert any(call[0] == "codex" and call[3] for call in calls)
        assert any(call[0] == "openclaw" and "WORKSPACE:" in call[2] for call in calls)
        assert any(call[0] == "hermes" and "WORKSPACE:" in call[2] for call in calls)
    finally:
        restore_attrs(originals)


def test_selected_task_executes_and_stops_at_execution_complete():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_call = server._project_execution_call_executor
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "implemented\npytest: 3 passed", "modifiedFiles": ["result.txt"],
        }
        try:
            project, selected = create_project_execution_project(workspace)
            other = server._handle_task_create(project["id"], {"title": "Do not run", "columnId": project["columns"][0]["id"]})["task"]
            started = server._handle_project_execution_start(project["id"], selected["id"], {})
            assert started["ok"] is True

            def completed():
                current = server._handle_project_get(project["id"])["project"]
                task = next(t for t in current["tasks"] if t["id"] == selected["id"])
                return task if task.get("executionState") == "execution_complete" else None

            task = wait_for(completed)
            current = server._handle_project_get(project["id"])["project"]
            task = next(t for t in current["tasks"] if t["id"] == selected["id"])
            assert task["columnId"] == col_id(current, "Review")
            assert task["completedAt"] is None
            assert "implemented" in task["evidence"]["executorSummary"]
            assert task["evidence"]["changedFiles"] == ["result.txt"]
            assert task["evidence"]["testResults"] == ["pytest: 3 passed"]
            assert task["evidence"]["checklist"] == []
            untouched = next(t for t in server._handle_project_get(project["id"])["project"]["tasks"] if t["id"] == other["id"])
            assert untouched["executionState"] == "backlog"

            done_col = next(c["id"] for c in project["columns"] if c["title"] == "Done")
            blocked = server._handle_task_update(project["id"], selected["id"], {"columnId": done_col})
            assert blocked["_status"] == 409
            in_progress_col = next(c["id"] for c in project["columns"] if c["title"] == "In Progress")
            state_locked = server._handle_task_update(project["id"], selected["id"], {"columnId": in_progress_col})
            assert state_locked["_status"] == 409
            assert state_locked["code"] == "project_execution_column_locked"
            reorder_blocked = server._handle_tasks_reorder(project["id"], {"updates": [{"id": selected["id"], "columnId": done_col, "order": 0}]})
            assert reorder_blocked["_status"] == 409
            reorder_state_locked = server._handle_tasks_reorder(project["id"], {"updates": [{"id": selected["id"], "columnId": in_progress_col, "order": 0}]})
            assert reorder_state_locked["_status"] == 409
            assert reorder_state_locked["code"] == "project_execution_column_locked"
        finally:
            server._project_execution_call_executor = old_call
            restore_store(old)

def test_project_execution_transition_syncs_state_columns():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        try:
            project, task = create_project_execution_project(workspace)
            server._project_execution_transition(project, task, "executing", "test", "start", "attempt-1")
            assert task["columnId"] == col_id(project, "In Progress")
            assert task["completedAt"] is None
            server._project_execution_transition(project, task, "execution_complete", "test", "done", "attempt-1")
            assert task["columnId"] == col_id(project, "Review")
            server._project_execution_transition(project, task, "reviewing", "test", "review", "attempt-1")
            assert task["columnId"] == col_id(project, "Review")
            server._project_execution_transition(project, task, "awaiting_user_acceptance", "test", "accept", "attempt-1")
            assert task["columnId"] == col_id(project, "Review")
            task["checklist"] = [{"id": "c1", "text": "Done criteria", "done": True}]
            result = server._project_execution_mark_done(project, task, "test", "done", "attempt-1")
            assert result["ok"] is True
            assert task["columnId"] == col_id(project, "Done")
            assert task["completedAt"]
        finally:
            restore_store(old)


def test_project_execution_mark_done_rejects_incomplete_checklist():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        try:
            project, task = create_project_execution_project(workspace)
            task["checklist"] = [
                {"id": "c1", "text": "Already done", "done": True},
                {"id": "c2", "text": "Still pending", "done": False},
            ]

            result = server._project_execution_mark_done(project, task, "test", "done", "attempt-1")

            assert result["_status"] == 409
            assert result["code"] == "checklist_incomplete"
            assert result["unfinishedChecklist"] == [{"id": "c2", "text": "Still pending"}]
            assert task.get("executionState") != "done"
            assert task.get("completedAt") is None
            assert task["columnId"] != col_id(project, "Done")
        finally:
            restore_store(old)


def test_project_execution_mark_done_rejects_empty_checklist():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        try:
            project, task = create_project_execution_project(workspace)
            task["checklist"] = []

            result = server._project_execution_mark_done(project, task, "test", "done", "attempt-1")

            assert result["_status"] == 409
            assert result["code"] == "checklist_empty"
            assert task.get("executionState") != "done"
            assert task.get("completedAt") is None
        finally:
            restore_store(old)


def test_project_execution_mark_done_allows_explicit_empty_checklist_skip():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        try:
            project, task = create_project_execution_project(workspace)
            task["checklist"] = []

            result = server._project_execution_mark_done(
                project,
                task,
                "user",
                "accepted without checklist",
                "attempt-1",
                allow_empty_checklist=True,
            )

            assert result["ok"] is True
            assert task.get("executionState") == "done"
            assert task.get("completedAt")
            assert task["columnId"] == col_id(project, "Done")
            assert task["acceptanceHistory"][-1]["action"] == "skip_empty_checklist"
            assert task["acceptanceHistory"][-1]["attemptId"] == "attempt-1"
        finally:
            restore_store(old)


def test_project_execution_checklist_completion_after_review_marks_done_without_user_acceptance():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        try:
            project, task = create_project_execution_project(workspace)
            project["projectExecutionStartMode"] = "single"
            task["requiresUserAcceptance"] = False
            task["executionState"] = "backlog"
            task["reviewResult"] = {"status": "pass", "attemptId": "attempt-1"}
            task["attempts"] = [{"id": "attempt-1", "status": "review_passed", "requiresUserAcceptance": False}]
            task["checklist"] = [{"id": "c1", "text": "Verified output", "done": False}]
            server._save_projects({"projects": [project], "templates": []})

            updated = server._handle_task_update(project["id"], task["id"], {
                "checklist": [{"id": "c1", "text": "Verified output", "done": True}],
            })

            assert updated["ok"] is True
            current = server._handle_project_get(project["id"])["project"]
            done_task = next(t for t in current["tasks"] if t["id"] == task["id"])
            assert done_task["executionState"] == "done"
            assert done_task["columnId"] == col_id(current, "Done")
            assert done_task["completedAt"]
            assert current["projectExecutionFlowStopReason"] == "checklist_completed"
        finally:
            restore_store(old)


def test_project_execution_checklist_completion_does_not_bypass_user_acceptance():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        try:
            project, task = create_project_execution_project(workspace)
            task["requiresUserAcceptance"] = True
            task["executionState"] = "awaiting_user_acceptance"
            task["reviewResult"] = {"status": "pass", "attemptId": "attempt-1"}
            task["attempts"] = [{"id": "attempt-1", "status": "review_passed", "requiresUserAcceptance": True}]
            task["checklist"] = [{"id": "c1", "text": "Verified output", "done": False}]
            task["columnId"] = col_id(project, "Review")
            server._save_projects({"projects": [project], "templates": []})

            updated = server._handle_task_update(project["id"], task["id"], {
                "checklist": [{"id": "c1", "text": "Verified output", "done": True}],
            })

            assert updated["ok"] is True
            current = server._handle_project_get(project["id"])["project"]
            current_task = next(t for t in current["tasks"] if t["id"] == task["id"])
            assert current_task["executionState"] == "awaiting_user_acceptance"
            assert current_task["columnId"] == col_id(current, "Review")
            assert current_task.get("completedAt") is None
        finally:
            restore_store(old)


def test_project_execution_openclaw_delivered_only_is_not_completed():
    old_call = server._wf_call_agent
    server._wf_call_agent = lambda *args, **kwargs: "[DELIVERED] Message delivered to OpenClaw agent."
    try:
        result = server._project_execution_call_executor(
            {"id": "executor", "providerKind": "openclaw"},
            "prompt",
            "/tmp/workspace",
            "attempt-1",
        )
        assert result["ok"] is False
        assert result["status"] == "execution_pending_result"
        assert "no final execution result" in result["error"]
    finally:
        server._wf_call_agent = old_call


def test_project_execution_auto_pass_continues_when_checklist_incomplete():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        old_reviewer = server._project_execution_call_reviewer
        calls = {"executor": 0}

        def fake_executor(executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600):
            calls["executor"] += 1
            if calls["executor"] == 1:
                return {"ok": True, "status": "completed", "reply": "implemented", "modifiedFiles": []}
            time.sleep(0.25)
            return {
                "ok": True,
                "status": "completed",
                "reply": "completed missing checklist item",
                "modifiedFiles": [],
                "checklistUpdates": [{"id": "c2", "text": "Still pending", "done": True}],
            }

        server._project_execution_call_executor = fake_executor
        server._project_execution_call_reviewer = lambda reviewer, prompt, review_id, project_id=None, task_id=None, timeout=600: {
            "ok": True,
            "status": "completed",
            "reply": '{"status":"pass","summary":"ready","rationale":"review passed","items":[]}',
        }
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_task_update(project["id"], task["id"], {
                "requiresUserAcceptance": False,
                "checklist": [
                    {"id": "c1", "text": "Already done", "done": True},
                    {"id": "c2", "text": "Still pending", "done": False},
                ],
            })
            task = complete_project_task_execution(project["id"], task["id"])
            review_started = server._handle_project_execution_review_start(project["id"], task["id"], {"attemptId": task["evidence"]["attemptId"]})
            assert review_started["ok"] is True

            reworking = wait_for(lambda: server._handle_project_get(project["id"])["project"]["tasks"][0]
                                 if server._handle_project_get(project["id"])["project"]["tasks"][0].get("executionState") == "reworking"
                                 else None)
            assert reworking.get("blockedReason") in (None, "")
            assert "Still pending" in reworking.get("reworkFeedback", "")
            assert calls["executor"] >= 2
        finally:
            server._project_execution_call_executor = old_executor
            server._project_execution_call_reviewer = old_reviewer
            restore_store(old)

def test_project_load_repairs_stale_acceptance_state_when_user_acceptance_disabled():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        try:
            project, task = create_project_execution_project(workspace)
            task["requiresUserAcceptance"] = False
            task["executionState"] = "awaiting_user_acceptance"
            task["completedAt"] = None
            task["reviewResult"] = {"status": "skipped", "attemptId": "attempt-1"}
            task["attempts"] = [{"id": "attempt-1", "status": "review_skipped_waiting_acceptance"}]
            task["checklist"] = [{"id": "c1", "text": "Verified output", "done": True}]
            task["columnId"] = col_id(project, "Review")
            project["workflowPhase"] = "awaiting_user_acceptance"
            project["projectExecutionFlowStopReason"] = "awaiting_user_acceptance"
            server._save_projects({"projects": [project], "templates": []})

            current = server._handle_project_get(project["id"])["project"]
            repaired = next(t for t in current["tasks"] if t["id"] == task["id"])
            assert repaired["executionState"] == "done"
            assert repaired["columnId"] == col_id(current, "Done")
            assert repaired["completedAt"]
            assert repaired["attempts"][0]["status"] == "execution_complete"
            assert current["projectExecutionFlowStopReason"] is None
        finally:
            restore_store(old)


def test_project_load_repairs_stale_backlog_after_review_and_completed_checklist():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        try:
            project, task = create_project_execution_project(workspace)
            task["requiresUserAcceptance"] = False
            task["executionState"] = "backlog"
            task["completedAt"] = None
            task["reviewResult"] = {"status": "pass", "attemptId": "attempt-1"}
            task["attempts"] = [{"id": "attempt-1", "status": "review_passed", "requiresUserAcceptance": False}]
            task["checklist"] = [{"id": "c1", "text": "Verified output", "done": True}]
            task["columnId"] = col_id(project, "Backlog")
            server._save_projects({"projects": [project], "templates": []})

            current = server._handle_project_get(project["id"])["project"]
            repaired = next(t for t in current["tasks"] if t["id"] == task["id"])
            assert repaired["executionState"] == "done"
            assert repaired["columnId"] == col_id(current, "Done")
            assert repaired["completedAt"]
        finally:
            restore_store(old)


def test_normal_project_can_move_task_to_done_without_project_execution_restriction():
    with tempfile.TemporaryDirectory() as status_dir:
        old = with_store(status_dir)
        try:
            project = server._handle_project_create({"title": "Normal Project", "projectExecutionEnabled": False})["project"]
            backlog_col = project["columns"][0]["id"]
            done_col = col_id(project, "Done")
            task = server._handle_task_create(project["id"], {"title": "Manual task", "columnId": backlog_col})["task"]
            moved = server._handle_task_update(project["id"], task["id"], {"columnId": done_col})
            assert moved["ok"] is True
            assert moved["task"]["columnId"] == done_col
            assert moved["task"]["completedAt"]
        finally:
            restore_store(old)


def test_project_level_start_selects_first_eligible_and_auto_reviews_to_done_by_default():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        old_reviewer = server._project_execution_call_reviewer
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "implemented", "modifiedFiles": [],
            "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
        }
        server._project_execution_call_reviewer = lambda reviewer, prompt, review_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": '{"status":"pass","summary":"ready","rationale":"ok","items":[]}',
        }
        try:
            project, first = create_project_execution_project(workspace)
            second = server._handle_task_create(project["id"], {"title": "Second", "columnId": project["columns"][0]["id"]})["task"]
            started = server._handle_project_execution_project_start(project["id"], {"mode": "single"})
            assert started["ok"] is True
            assert started["taskId"] == first["id"]
            assert started["startMode"] == "single"
            assert started["requiresUserAcceptance"] is False

            def done():
                current = server._handle_project_get(project["id"])["project"]
                task = next(t for t in current["tasks"] if t["id"] == first["id"])
                return task if task.get("executionState") == "done" else None

            task = wait_for(done)
            assert task["reviewResult"]["status"] == "pass"
            assert task["columnId"] == col_id(server._handle_project_get(project["id"])["project"], "Done")
            current = server._handle_project_get(project["id"])["project"]
            untouched = next(t for t in current["tasks"] if t["id"] == second["id"])
            assert untouched["executionState"] == "backlog"
            assert current["projectExecutionStartMode"] == "single"
            assert current["projectExecutionFlowActive"] is False
        finally:
            server._project_execution_call_executor = old_executor
            server._project_execution_call_reviewer = old_reviewer
            restore_store(old)


def test_reviewer_pass_uses_attempt_acceptance_snapshot():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        old_reviewer = server._project_execution_call_reviewer

        def executor_call(executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600):
            server._handle_task_update(project_id, task_id, {"requiresUserAcceptance": True})
            return {
                "ok": True,
                "status": "completed",
                "reply": "implemented",
                "modifiedFiles": [],
                "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
            }

        server._project_execution_call_executor = executor_call
        server._project_execution_call_reviewer = lambda reviewer, prompt, review_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": '{"status":"pass","summary":"ready","rationale":"ok","items":[]}',
        }
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_task_update(project["id"], task["id"], {"requiresUserAcceptance": False})
            started = server._handle_project_execution_project_start(project["id"], {"mode": "single"})
            assert started["ok"] is True

            current_task = wait_for(lambda: server._handle_project_get(project["id"])["project"]["tasks"][0]
                                    if server._handle_project_get(project["id"])["project"]["tasks"][0].get("executionState") == "done"
                                    else None)
            assert current_task["requiresUserAcceptance"] is True
            assert current_task["attempts"][-1]["requiresUserAcceptance"] is False
            assert current_task["reviewResult"]["status"] == "pass"
        finally:
            server._project_execution_call_executor = old_executor
            server._project_execution_call_reviewer = old_reviewer
            restore_store(old)


def test_project_level_start_skips_done_columns_and_reports_no_eligible_task():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_send = server.send_feishu_notification
        feishu_calls = []
        server.send_feishu_notification = fake_feishu_sender(feishu_calls)
        try:
            empty = server._handle_project_create({
                "title": "Empty",
                "projectExecutionEnabled": True,
                "workspacePath": workspace,
                "defaultExecutorAgentId": "executor",
                "defaultReviewerAgentId": "reviewer",
            })["project"]
            no_task = server._handle_project_execution_project_start(empty["id"], {"mode": "continuous"})
            assert no_task["_status"] == 409
            assert no_task["code"] == "no_eligible_task"
            assert not [c for c in feishu_calls if c["intent"]["target"] == "feishu-project-execution-complete"]

            project, task = create_project_execution_project(workspace)
            done_col = next(c for c in project["columns"] if c["title"] == "Done")
            data = server._load_projects()
            current = data["projects"][-1]
            current["tasks"][0]["columnId"] = done_col["id"]
            current["tasks"][0]["executionState"] = "done"
            current["tasks"][0]["completedAt"] = server._proj_now()
            server._save_projects(data)
            no_eligible = server._handle_project_execution_project_start(project["id"], {"mode": "continuous"})
            assert no_eligible["_status"] == 409
            assert no_eligible["code"] == "no_eligible_task"
            complete_calls = [c for c in feishu_calls if c["intent"]["target"] == "feishu-project-execution-complete"]
            assert len(complete_calls) == 1
            assert complete_calls[0]["intent"]["type"] == "notification"
            repeated = server._handle_project_execution_project_start(project["id"], {"mode": "continuous"})
            assert repeated["code"] == "no_eligible_task"
            assert len([c for c in feishu_calls if c["intent"]["target"] == "feishu-project-execution-complete"]) == 1
        finally:
            server.send_feishu_notification = old_send
            restore_store(old)


def test_project_pipeline_restart_requires_every_task_to_allow_retriggering():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "restarted", "modifiedFiles": [],
        }
        try:
            project, first = create_project_execution_project(workspace)
            second = server._handle_task_create(project["id"], {"title": "Second", "columnId": project["columns"][0]["id"]})["task"]
            done_col = next(c for c in project["columns"] if c["title"].lower() == "done")
            data, stored = server._project_find(project["id"])
            for task in stored["tasks"]:
                task["columnId"] = done_col["id"]
                task["completedAt"] = server._proj_now()
                task["executionState"] = "done"
                task["scheduledRepeatEnabled"] = task["id"] == first["id"]
            server._save_projects(data)

            blocked = server._handle_project_execution_project_start(project["id"], {"mode": "continuous", "restartPipeline": True})
            assert blocked["_status"] == 409
            assert blocked["code"] == "project_restart_requires_all_tasks_repeatable"

            data, stored = server._project_find(project["id"])
            for task in stored["tasks"]:
                task["scheduledRepeatEnabled"] = True
            server._save_projects(data)

            restarted = server._handle_project_execution_project_start(project["id"], {"mode": "continuous", "restartPipeline": True})
            assert restarted["ok"] is True
            assert restarted["restartPipeline"] is True
            assert restarted["resetTaskCount"] == 2
            assert restarted["taskId"] == first["id"]

            current = server._handle_project_get(project["id"])["project"]
            backlog_col = next(c for c in current["columns"] if c["title"].lower() == "backlog")
            current_first = next(t for t in current["tasks"] if t["id"] == first["id"])
            current_second = next(t for t in current["tasks"] if t["id"] == second["id"])
            assert current_first["executionState"] == "executing"
            assert current_first["completedAt"] is None
            assert current_second["executionState"] == "backlog"
            assert current_second["completedAt"] is None
            assert current_second["columnId"] == backlog_col["id"]
        finally:
            server._project_execution_call_executor = old_executor
            restore_store(old)


def test_project_level_start_persists_reviewer_skip_confirmation_for_toolbar_state():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_project_update(project["id"], {"defaultReviewerAgentId": None})
            server._handle_task_update(project["id"], task["id"], {"reviewerAgentId": None})
            result = server._handle_project_execution_project_start(project["id"], {"mode": "continuous"})
            assert result["_status"] == 409
            assert result["confirmationRequired"] is True
            assert result["code"] == "reviewer_skip_confirmation_required"
            current = server._handle_project_get(project["id"])["project"]
            assert current["workflowActive"] is False
            assert current["workflowPhase"] == "reviewer_skip_confirmation_required"
            assert current["projectExecutionFlowStopReason"] == "reviewer_skip_confirmation_required"
        finally:
            restore_store(old)


def test_missing_reviewer_skip_completes_by_default_after_explicit_confirmation():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "implemented without reviewer", "modifiedFiles": [],
            "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
        }
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_project_update(project["id"], {"defaultReviewerAgentId": None})
            server._handle_task_update(project["id"], task["id"], {"reviewerAgentId": None})
            first = server._handle_project_execution_project_start(project["id"], {"mode": "continuous"})
            assert first["_status"] == 409
            assert first["confirmationRequired"] is True
            assert first["code"] == "reviewer_skip_confirmation_required"
            assert first["selectedTask"]["id"] == task["id"]

            confirmed = server._handle_project_execution_project_start(project["id"], {"mode": "continuous", "skipReviewConfirmed": True})
            assert confirmed["ok"] is True

            def done():
                current = server._handle_project_get(project["id"])["project"]
                task = current["tasks"][0]
                return task if task.get("executionState") == "done" else None

            task = wait_for(done)
            assert task["reviewResult"]["status"] == "skipped"
            assert "skipped" in task["reviewResult"]["summary"].lower()
            assert task["completedAt"]
            assert task["columnId"] == col_id(server._handle_project_get(project["id"])["project"], "Done")
        finally:
            server._project_execution_call_executor = old_executor
            restore_store(old)


def test_task_can_allow_missing_reviewer_without_confirmation_and_complete_by_default():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "implemented without reviewer confirmation", "modifiedFiles": [],
            "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
        }
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_project_update(project["id"], {"defaultReviewerAgentId": None})
            server._handle_task_update(project["id"], task["id"], {
                "reviewerAgentId": None,
                "allowReviewerlessExecution": True,
            })

            started = server._handle_project_execution_project_start(project["id"], {"mode": "continuous"})
            assert started["ok"] is True
            assert started.get("confirmationRequired") is None

            def done():
                current = server._handle_project_get(project["id"])["project"]
                task = current["tasks"][0]
                return task if task.get("executionState") == "done" else None

            task = wait_for(done)
            latest = task["attempts"][-1]
            assert latest["skipReview"] is True
            assert latest["skipReviewReason"] == "reviewer_missing"
            assert task["reviewResult"]["status"] == "skipped"
            assert task["allowReviewerlessExecution"] is True
            assert task["columnId"] == col_id(server._handle_project_get(project["id"])["project"], "Done")
        finally:
            server._project_execution_call_executor = old_executor
            restore_store(old)


def test_skip_review_completion_uses_attempt_acceptance_snapshot():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor

        def executor_call(executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600):
            server._handle_task_update(project_id, task_id, {"requiresUserAcceptance": True})
            return {
                "ok": True,
                "status": "completed",
                "reply": "implemented",
                "modifiedFiles": [],
                "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
            }

        server._project_execution_call_executor = executor_call
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_project_update(project["id"], {"defaultReviewerAgentId": None})
            server._handle_task_update(project["id"], task["id"], {
                "reviewerAgentId": None,
                "requiresUserAcceptance": False,
                "allowReviewerlessExecution": True,
            })
            started = server._handle_project_execution_start(project["id"], task["id"], {})
            assert started["ok"] is True

            current_task = wait_for(lambda: server._handle_project_get(project["id"])["project"]["tasks"][0]
                                    if server._handle_project_get(project["id"])["project"]["tasks"][0].get("executionState") == "done"
                                    else None)
            assert current_task["requiresUserAcceptance"] is True
            assert current_task["attempts"][-1]["requiresUserAcceptance"] is False
            assert current_task["reviewResult"]["status"] == "skipped"
        finally:
            server._project_execution_call_executor = old_executor
            restore_store(old)


def test_skipped_review_waits_for_acceptance_when_required():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "implemented without reviewer", "modifiedFiles": [],
            "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
        }
        try:
            project, task = create_project_execution_project(workspace)
            done_col = next(c["id"] for c in project["columns"] if c["title"] == "Done")
            server._handle_project_update(project["id"], {"defaultReviewerAgentId": None})
            server._handle_task_update(project["id"], task["id"], {"reviewerAgentId": None, "requiresUserAcceptance": True})
            first = server._handle_project_execution_project_start(project["id"], {"mode": "single"})
            assert first["code"] == "reviewer_skip_confirmation_required"
            confirmed = server._handle_project_execution_project_start(project["id"], {"mode": "single", "skipReviewConfirmed": True})
            assert confirmed["ok"] is True

            task = wait_for(lambda: server._handle_project_get(project["id"])["project"]["tasks"][0]
                            if server._handle_project_get(project["id"])["project"]["tasks"][0].get("executionState") == "awaiting_user_acceptance"
                            else None)
            assert task["reviewResult"]["status"] == "skipped"
            assert task["columnId"] == col_id(server._handle_project_get(project["id"])["project"], "Review")
            accepted = server._handle_project_execution_acceptance(project["id"], task["id"], {
                "action": "accept",
                "attemptId": task["reviewResult"]["attemptId"],
            })
            assert accepted["ok"] is True
            assert accepted["task"]["executionState"] == "done"
            assert accepted["task"]["columnId"] == done_col
            assert accepted["task"]["completedAt"]
        finally:
            server._project_execution_call_executor = old_executor
            restore_store(old)


def test_project_start_preserves_dirty_confirmation_after_reviewer_skip_confirmation():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
        with open(os.path.join(workspace, "dirty.txt"), "w", encoding="utf-8") as f:
            f.write("dirty\n")
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "implemented without reviewer", "modifiedFiles": [],
            "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
        }
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_project_update(project["id"], {"defaultReviewerAgentId": None})
            server._handle_task_update(project["id"], task["id"], {"reviewerAgentId": None})

            reviewer_confirm = server._handle_project_execution_project_start(project["id"], {"mode": "continuous"})
            assert reviewer_confirm["_status"] == 409
            assert reviewer_confirm["code"] == "reviewer_skip_confirmation_required"

            dirty_confirm = server._handle_project_execution_project_start(project["id"], {"mode": "continuous", "skipReviewConfirmed": True})
            assert dirty_confirm["_status"] == 409
            assert dirty_confirm["code"] == "dirty_worktree_confirmation_required"
            assert dirty_confirm["dirtyFingerprint"]

            started = server._handle_project_execution_project_start(project["id"], {
                "mode": "continuous",
                "skipReviewConfirmed": True,
                "dirtyFingerprint": dirty_confirm["dirtyFingerprint"],
            })
            assert started["ok"] is True
            assert started["taskId"] == task["id"]

            current_task = wait_for(lambda: server._handle_project_get(project["id"])["project"]["tasks"][0]
                                    if server._handle_project_get(project["id"])["project"]["tasks"][0].get("executionState") == "done"
                                    else None)
            assert current_task["reviewResult"]["status"] == "skipped"
        finally:
            server._project_execution_call_executor = old_executor
            restore_store(old)


def test_direct_task_start_supports_reviewer_skip_and_dirty_confirmation_chain():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
        with open(os.path.join(workspace, "dirty.txt"), "w", encoding="utf-8") as f:
            f.write("dirty\n")
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "implemented without reviewer", "modifiedFiles": [],
            "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
        }
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_project_update(project["id"], {"defaultReviewerAgentId": None})
            server._handle_task_update(project["id"], task["id"], {"reviewerAgentId": None})

            reviewer_confirm = server._handle_project_execution_start(project["id"], task["id"], {})
            assert reviewer_confirm["_status"] == 409
            assert reviewer_confirm["code"] == "reviewer_skip_confirmation_required"

            dirty_confirm = server._handle_project_execution_start(project["id"], task["id"], {"skipReviewConfirmed": True})
            assert dirty_confirm["_status"] == 409
            assert dirty_confirm["code"] == "dirty_worktree_confirmation_required"

            started = server._handle_project_execution_start(project["id"], task["id"], {
                "skipReviewConfirmed": True,
                "dirtyFingerprint": dirty_confirm["dirtyFingerprint"],
            })
            assert started["ok"] is True
            assert started["startMode"] == "single"

            current_task = wait_for(lambda: server._handle_project_get(project["id"])["project"]["tasks"][0]
                                    if server._handle_project_get(project["id"])["project"]["tasks"][0].get("executionState") == "done"
                                    else None)
            assert current_task["reviewResult"]["status"] == "skipped"
        finally:
            server._project_execution_call_executor = old_executor
            restore_store(old)


def test_direct_task_start_requires_explicit_executor_agent():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_project_update(project["id"], {"defaultExecutorAgentId": None, "defaultReviewerAgentId": None})
            server._handle_task_update(project["id"], task["id"], {
                "assignee": None,
                "executorAgentId": None,
                "reviewerAgentId": None,
                "allowReviewerlessExecution": True,
            })

            started = server._handle_project_execution_start(project["id"], task["id"], {"skipReviewConfirmed": True})
            assert started["_status"] == 409
            assert started["code"] == "executor_required"
            current_task = server._handle_project_get(project["id"])["project"]["tasks"][0]
            assert current_task["executionState"] == "backlog"
            assert current_task.get("activeAttemptId") in (None, "")
            assert current_task.get("executorAgentId") in (None, "")
            assert current_task.get("assignee") in (None, "")
        finally:
            restore_store(old)


def test_continuous_flow_auto_continues_when_task_does_not_require_acceptance():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        old_reviewer = server._project_execution_call_reviewer
        calls = []

        def executor_call(executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600):
            calls.append(("execute", task_id))
            return {
                "ok": True,
                "status": "completed",
                "reply": "implemented",
                "modifiedFiles": [],
                "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
            }

        server._project_execution_call_executor = executor_call
        server._project_execution_call_reviewer = lambda reviewer, prompt, review_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": '{"status":"pass","summary":"ready","rationale":"ok","items":[]}',
        }
        try:
            project, first = create_project_execution_project(workspace)
            server._handle_task_update(project["id"], first["id"], {"requiresUserAcceptance": False})
            second = server._handle_task_create(project["id"], {"title": "Second", "columnId": project["columns"][0]["id"], "requiresUserAcceptance": True})["task"]
            started = server._handle_project_execution_project_start(project["id"], {"mode": "continuous"})
            assert started["ok"] is True

            def second_awaiting():
                current = server._handle_project_get(project["id"])["project"]
                first_task = next(t for t in current["tasks"] if t["id"] == first["id"])
                second_task = next(t for t in current["tasks"] if t["id"] == second["id"])
                if first_task.get("executionState") == "done" and second_task.get("executionState") == "awaiting_user_acceptance":
                    return current, first_task, second_task
                return None

            current, first_task, second_task = wait_for(second_awaiting, timeout=8)
            assert first_task["completedAt"]
            assert second_task["reviewResult"]["status"] == "pass"
            assert [call[1] for call in calls] == [first["id"], second["id"]]
            assert current["projectExecutionFlowStopReason"] == "awaiting_user_acceptance"
        finally:
            server._project_execution_call_executor = old_executor
            server._project_execution_call_reviewer = old_reviewer
            restore_store(old)


def test_direct_task_start_does_not_enable_continuous_flow_even_when_project_default_is_continuous():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "implemented", "modifiedFiles": [],
            "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
        }
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_project_update(project["id"], {"projectExecutionStartMode": "continuous"})
            started = server._handle_project_execution_start(project["id"], task["id"], {})
            assert started["ok"] is True
            assert started["startMode"] == "single"
            wait_for(lambda: server._handle_project_get(project["id"])["project"]["tasks"][0].get("executionState") == "execution_complete")
            current = server._handle_project_get(project["id"])["project"]
            assert current["projectExecutionStartMode"] == "continuous"
            assert current["projectExecutionFlowActive"] is False
        finally:
            server._project_execution_call_executor = old_executor
            restore_store(old)


def test_direct_task_start_respects_repeat_trigger_setting_for_done_tasks():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "retriggered", "modifiedFiles": [],
        }
        try:
            project, task = create_project_execution_project(workspace)
            done_col = next(c for c in project["columns"] if c["title"].lower() == "done")
            data, stored = server._project_find(project["id"])
            stored_task = next(t for t in stored["tasks"] if t["id"] == task["id"])
            stored_task["columnId"] = done_col["id"]
            stored_task["completedAt"] = server._proj_now()
            stored_task["executionState"] = "done"
            stored_task["scheduledRepeatEnabled"] = False
            server._save_projects(data)

            blocked = server._handle_project_execution_start(project["id"], task["id"], {})
            assert blocked["_status"] == 409
            assert blocked["code"] == "task_completed_repeat_disabled"

            data, stored = server._project_find(project["id"])
            stored_task = next(t for t in stored["tasks"] if t["id"] == task["id"])
            stored_task["scheduledRepeatEnabled"] = True
            server._save_projects(data)
            started = server._handle_project_execution_start(project["id"], task["id"], {})
            assert started["ok"] is True
            assert started["reopenedCompletedTask"] is True

            current = server._handle_project_get(project["id"])["project"]["tasks"][0]
            inprogress_col = next(c for c in project["columns"] if c["title"].lower() == "in progress")
            assert current["completedAt"] is None
            assert current["columnId"] == inprogress_col["id"]
            assert current["executionState"] == "executing"
        finally:
            server._project_execution_call_executor = old_executor
            restore_store(old)


def test_dirty_confirmation_is_bound_to_current_fingerprint():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
        with open(os.path.join(workspace, "dirty.txt"), "w", encoding="utf-8") as f:
            f.write("one\n")
        old = with_store(status_dir)
        try:
            project, task = create_project_execution_project(workspace)
            first = server._handle_project_execution_start(project["id"], task["id"], {})
            assert first["confirmationRequired"] is True
            stale = first["dirtyFingerprint"]
            with open(os.path.join(workspace, "dirty.txt"), "a", encoding="utf-8") as f:
                f.write("two\n")
            second = server._handle_project_execution_start(project["id"], task["id"], {"dirtyFingerprint": stale})
            assert second["confirmationRequired"] is True
            assert second["dirtyFingerprint"] != stale
        finally:
            restore_store(old)


def test_dirty_confirmation_can_be_reconfirmed_for_same_fingerprint():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
        with open(os.path.join(workspace, "dirty.txt"), "w", encoding="utf-8") as f:
            f.write("one\n")
        old = with_store(status_dir)
        old_call = server._project_execution_call_executor
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "pytest: 1 passed", "modifiedFiles": [],
            "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
        }
        try:
            project, task = create_project_execution_project(workspace)
            first = server._handle_project_execution_start(project["id"], task["id"], {})
            assert first["confirmationRequired"] is True
            confirmed = server._handle_project_execution_start(project["id"], task["id"], {"dirtyFingerprint": first["dirtyFingerprint"]})
            assert confirmed["ok"] is True
            wait_for(lambda: server._handle_project_get(project["id"])["project"]["tasks"][0].get("executionState") == "execution_complete")
            second_task = server._handle_task_create(project["id"], {"title": "Second", "columnId": project["columns"][0]["id"]})["task"]
            repeated = server._handle_project_execution_start(project["id"], second_task["id"], {"dirtyFingerprint": first["dirtyFingerprint"]})
            assert repeated["ok"] is True
            assert repeated["taskId"] == second_task["id"]
        finally:
            server._project_execution_call_executor = old_call
            restore_store(old)


def test_start_rejects_when_another_task_is_reviewing():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        try:
            project, task = create_project_execution_project(workspace)
            second = server._handle_task_create(project["id"], {"title": "Second", "columnId": project["columns"][0]["id"]})["task"]
            data = server._load_projects()
            current = data["projects"][0]
            current["tasks"][0]["executionState"] = "reviewing"
            current["tasks"][0]["activeAttemptId"] = "review-id"
            current["workflowActive"] = True
            current["workflowPhase"] = "reviewing"
            current["activeTaskId"] = task["id"]
            server._save_projects(data)

            result = server._handle_project_execution_start(project["id"], second["id"], {})
            assert result["_status"] == 409
            assert result["activeTaskId"] == task["id"]
        finally:
            restore_store(old)


def test_execution_failure_blocks_with_redacted_bounded_evidence():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_call = server._project_execution_call_executor
        old_send = server.send_feishu_notification
        feishu_calls = []
        server.send_feishu_notification = fake_feishu_sender(feishu_calls)
        secret = "api_key=SECRET_VALUE"
        long_reply = "x" * (server._PROJECT_EXECUTION_MAX_TEXT + 50)
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": False,
            "status": "execution_failed",
            "reply": long_reply + "\n" + secret,
            "error": "password=hunter2",
            "tests": ["pytest failed", "access_token=SHOULD_HIDE"],
            "modifiedFiles": ["partial.txt"],
        }
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_task_update(project["id"], task["id"], {"checklist": [{"text": "Run tests", "done": False}]})
            started = server._handle_project_execution_start(project["id"], task["id"], {})
            assert started["ok"] is True

            def blocked():
                current = server._handle_project_get(project["id"])["project"]
                task = current["tasks"][0]
                return task if task.get("executionState") == "blocked" else None

            task = wait_for(blocked)
            evidence = task["evidence"]
            assert evidence["providerStatus"] == "execution_failed"
            assert evidence["changedFiles"] == ["partial.txt"]
            assert evidence["checklist"] == [{"text": "Run tests", "done": False}]
            assert "SECRET_VALUE" not in evidence["executorSummary"]
            assert "hunter2" not in evidence["error"]
            assert "SHOULD_HIDE" not in "\n".join(evidence["testResults"])
            assert "...[truncated]" in evidence["executorSummary"]
            intervention_calls = [c for c in feishu_calls if c["intent"]["target"] == "feishu-project-execution-intervention"]
            assert len(intervention_calls) == 1
            assert intervention_calls[0]["intent"]["type"] == "error"
            assert "hunter2" not in json.dumps(intervention_calls[0]["intent"], ensure_ascii=False)
            project = server._handle_project_get(project["id"])["project"]
            duplicate = server._send_project_execution_intervention_notification(
                project, project["tasks"][0], project["tasks"][0]["blockedReason"], evidence["attemptId"], kind="error"
            )
            assert duplicate["status"] == "skipped_duplicate"
            assert len([c for c in feishu_calls if c["intent"]["target"] == "feishu-project-execution-intervention"]) == 1
        finally:
            server.send_feishu_notification = old_send
            server._project_execution_call_executor = old_call
            restore_store(old)


def test_transient_gateway_timeout_retries_once_before_blocking():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_call = server._project_execution_call_executor
        old_sleep = server.time.sleep
        old_send = server.send_feishu_notification
        feishu_calls = []
        server.send_feishu_notification = fake_feishu_sender(feishu_calls)
        calls = {"executor": 0}

        def flaky_executor(executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600):
            calls["executor"] += 1
            if calls["executor"] == 1:
                return {
                    "ok": False,
                    "status": "execution_failed",
                    "error": "[ERROR] Agent returned code 1: GatewayClientRequestError: FailoverError: LLM request timed out.",
                    "modifiedFiles": [],
                }
            return {"ok": True, "status": "completed", "reply": "completed after retry", "modifiedFiles": []}

        server._project_execution_call_executor = flaky_executor
        server.time.sleep = lambda seconds: None
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_task_update(project["id"], task["id"], {"checklist": [{"text": "Run tests", "done": False}]})
            started = server._handle_project_execution_start(project["id"], task["id"], {})
            assert started["ok"] is True

            current_task = wait_for(lambda: server._handle_project_get(project["id"])["project"]["tasks"][0]
                                    if server._handle_project_get(project["id"])["project"]["tasks"][0].get("executionState") == "execution_complete" else None)
            assert calls["executor"] == 2
            assert current_task.get("executionState") == "execution_complete"
            assert current_task.get("blockedReason") in (None, "")
            attempts = current_task.get("attempts") or []
            assert attempts[0]["status"] == "retry_scheduled"
            assert attempts[0]["retryReason"] in {"llm request timed out", "gatewayclientrequesterror", "failovererror", "timed out", "timeout"}
            assert attempts[1]["transientRetry"] is True
            assert attempts[1]["retryFromAttemptId"] == attempts[0]["id"]
            assert not [c for c in feishu_calls if c["intent"]["target"] == "feishu-project-execution-intervention"]
        finally:
            server.send_feishu_notification = old_send
            server.time.sleep = old_sleep
            server._project_execution_call_executor = old_call
            restore_store(old)


def test_feishu_start_failure_notification_dedupes_after_persisted_reload():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_send = server.send_feishu_notification
        feishu_calls = []
        server.send_feishu_notification = fake_feishu_sender(feishu_calls)
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_task_update(project["id"], task["id"], {"executorAgentId": "missing-agent"})
            first = server._handle_project_execution_start(project["id"], task["id"], {})
            assert first["_status"] == 409
            assert len([c for c in feishu_calls if c["intent"]["target"] == "feishu-project-execution-intervention"]) == 1

            # Reload through the markdown store to prove task-level dedupe markers persist.
            second = server._handle_project_execution_start(project["id"], task["id"], {})
            assert second["_status"] == 409
            assert len([c for c in feishu_calls if c["intent"]["target"] == "feishu-project-execution-intervention"]) == 1
        finally:
            server.send_feishu_notification = old_send
            restore_store(old)


def test_cancel_active_execution_blocks_and_preserves_evidence():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_call = server._project_execution_call_executor
        release = {"done": False}

        def slow_executor(executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600):
            deadline = time.time() + 2
            while not release["done"] and time.time() < deadline:
                time.sleep(0.02)
            return {"ok": False, "status": "cancelled", "reply": "cancelled after partial work", "modifiedFiles": ["partial.txt"]}

        server._project_execution_call_executor = slow_executor
        try:
            project, task = create_project_execution_project(workspace)
            started = server._handle_project_execution_start(project["id"], task["id"], {})
            assert started["ok"] is True
            cancelling = server._handle_project_execution_cancel(project["id"], task["id"], {"attemptId": started["attemptId"]})
            assert cancelling["ok"] is True
            assert cancelling["status"] == "blocked"
            assert cancelling["task"]["executionState"] == "blocked"
            assert cancelling["task"]["activeAttemptId"] is None
            assert "stopped by user" in cancelling["task"]["blockedReason"]
            release["done"] = True

            def blocked():
                current = server._handle_project_get(project["id"])["project"]
                task = current["tasks"][0]
                return task if task.get("executionState") == "blocked" and task.get("evidence") else None

            task = wait_for(blocked)
            assert "cancelled" in task["blockedReason"].lower()
            assert task["evidence"]["providerStatus"] == "cancelled"
            assert task["evidence"]["changedFiles"] == ["partial.txt"]
        finally:
            server._project_execution_call_executor = old_call
            restore_store(old)


def test_status_reconciles_stale_active_execution_after_restart():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        try:
            project, task = create_project_execution_project(workspace)
            data = server._load_projects()
            current = data["projects"][0]
            current["tasks"][0]["executionState"] = "executing"
            current["tasks"][0]["activeAttemptId"] = "stale-attempt"
            current["workflowActive"] = True
            current["workflowPhase"] = "executing"
            current["activeTaskId"] = task["id"]
            server._save_projects(data)

            status = server._handle_project_execution_status(project["id"], task["id"])
            assert status["ok"] is True
            assert status["phase"] == "blocked"
            assert status["task"]["executionState"] == "blocked"
            assert status["task"]["blockedReason"] == "previous_execution_not_resumable"
        finally:
            restore_store(old)


def test_load_repairs_done_task_with_stale_blocked_project_state():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        try:
            project, task = create_project_execution_project(workspace)
            done_col = next(c["id"] for c in project["columns"] if c["title"] == "Done")
            data = server._load_projects()
            current = data["projects"][0]
            current["workflowActive"] = False
            current["workflowPhase"] = "blocked"
            current["activeTaskId"] = task["id"]
            current["projectExecutionFlowActive"] = False
            current["projectExecutionFlowStopReason"] = "previous_execution_not_resumable"
            current["tasks"][0].update({
                "executionState": "done",
                "completedAt": "2026-06-26T00:00:00+00:00",
                "columnId": done_col,
                "activeAttemptId": "stale-attempt",
                "blockedReason": "previous_execution_not_resumable",
                "lastError": "previous_execution_not_resumable",
            })
            server._save_projects(data)

            repaired = server._handle_project_get(project["id"])["project"]
            repaired_task = repaired["tasks"][0]
            assert repaired["workflowPhase"] == "done"
            assert repaired["activeTaskId"] is None
            assert repaired["projectExecutionFlowStopReason"] is None
            assert repaired_task["executionState"] == "done"
            assert repaired_task["activeAttemptId"] is None
            assert repaired_task["blockedReason"] is None
            assert repaired_task["lastError"] is None
        finally:
            restore_store(old)


def complete_project_task_execution(project_id, task_id):
    started = server._handle_project_execution_start(project_id, task_id, {})
    assert started["ok"] is True

    def completed():
        current = server._handle_project_get(project_id)["project"]
        task = next(t for t in current["tasks"] if t["id"] == task_id)
        return task if task.get("executionState") == "execution_complete" else None

    return wait_for(completed)


def review_project_execution_task(project_id, task_id):
    task = server._handle_project_get(project_id)["project"]["tasks"][0]
    attempt_id = task["evidence"]["attemptId"]
    started = server._handle_project_execution_review_start(project_id, task_id, {"attemptId": attempt_id})
    assert started["ok"] is True

    def reviewed():
        current = server._handle_project_get(project_id)["project"]
        task = next(t for t in current["tasks"] if t["id"] == task_id)
        return task if task.get("executionState") == "awaiting_user_acceptance" else None

    return wait_for(reviewed)


def test_reviewer_provider_matrix_receives_read_only_evidence_packet():
    calls = []
    originals = [
        (server, "_wf_call_agent", server._wf_call_agent),
        (server, "_handle_hermes_chat", server._handle_hermes_chat),
        (server, "_handle_codex_chat", server._handle_codex_chat),
    ]

    def review_reply():
        return '{"status":"pass","summary":"ready","rationale":"evidence ok","items":[]}'

    def openclaw_call(agent_id, prompt, timeout=600, project_id=None, task_id=None):
        calls.append(("openclaw", agent_id, prompt, None))
        return review_reply()

    def hermes_call(body):
        calls.append(("hermes", body.get("agentId"), body.get("message"), body.get("workspace")))
        return {"ok": True, "status": "completed", "reply": review_reply()}

    def codex_call(body):
        calls.append(("codex", body.get("agentId"), body.get("message"), body.get("workspace")))
        return {"ok": True, "status": "completed", "reply": review_reply()}

    server._wf_call_agent = openclaw_call
    server._handle_hermes_chat = hermes_call
    server._handle_codex_chat = codex_call
    try:
        attempt = {"id": "a1", "evidence": {"executorSummary": "implemented", "changedFiles": ["x.py"], "testResults": ["pytest passed"]}}
        project = {"title": "P", "description": "", "workspacePath": "/tmp/should-not-be-sent"}
        task = {"title": "T", "description": "", "checklist": [{"text": "done", "done": True}]}
        prompt = server._project_execution_build_review_prompt(project, task, attempt)
        for provider, reviewer in [
            ("openclaw", {"id": "reviewer", "providerKind": "openclaw"}),
            ("hermes", {"id": "hermes-executor", "providerKind": "hermes"}),
            ("codex", {"id": "codex-executor", "providerKind": "codex"}),
        ]:
            result = server._project_execution_call_reviewer(reviewer, prompt, f"review-{provider}", project_id="p", task_id="t")
            assert result["ok"] is True
        assert {call[0] for call in calls} == {"openclaw", "hermes", "codex"}
        assert all("EXECUTOR SUMMARY" in call[2] for call in calls)
        assert all("/tmp/should-not-be-sent" not in call[2] for call in calls)
        assert all(call[3] in (None, "") for call in calls)
    finally:
        restore_attrs(originals)


def test_malformed_reviewer_result_blocks_instead_of_passing():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        old_reviewer = server._project_execution_call_reviewer
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "implemented", "modifiedFiles": [],
            "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
        }
        server._project_execution_call_reviewer = lambda reviewer, prompt, review_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": '{"status":"pass"}',
        }
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_task_update(project["id"], task["id"], {"requiresUserAcceptance": True})
            task = complete_project_task_execution(project["id"], task["id"])
            started = server._handle_project_execution_review_start(project["id"], task["id"], {"attemptId": task["evidence"]["attemptId"]})
            assert started["ok"] is True

            def blocked():
                current = server._handle_project_get(project["id"])["project"]
                task = current["tasks"][0]
                return task if task.get("executionState") == "blocked" else None

            task = wait_for(blocked)
            assert task["reviewResult"]["status"] == "blocked"
            assert task["completedAt"] is None
        finally:
            server._project_execution_call_executor = old_executor
            server._project_execution_call_reviewer = old_reviewer
            restore_store(old)


def test_reviewer_needs_more_work_auto_reworks_and_rechecks_to_done_by_default():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        old_reviewer = server._project_execution_call_reviewer
        executor_prompts = []
        reviews = [
            '{"status":"needs_more_work","summary":"missing edge case","rationale":"add coverage","items":[{"text":"add test"}]}',
            '{"status":"pass","summary":"ready","rationale":"rework fixed it","items":[]}',
        ]

        def executor_call(executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600):
            executor_prompts.append(prompt)
            return {
                "ok": True,
                "status": "completed",
                "reply": f"done {len(executor_prompts)}",
                "modifiedFiles": [f"file{len(executor_prompts)}.txt"],
                "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
            }

        def reviewer_call(reviewer, prompt, review_id, project_id=None, task_id=None, timeout=600):
            return {"ok": True, "status": "completed", "reply": reviews.pop(0)}

        server._project_execution_call_executor = executor_call
        server._project_execution_call_reviewer = reviewer_call
        try:
            project, task = create_project_execution_project(workspace)
            task = complete_project_task_execution(project["id"], task["id"])
            started = server._handle_project_execution_review_start(project["id"], task["id"], {"attemptId": task["evidence"]["attemptId"]})
            assert started["ok"] is True

            def done():
                current = server._handle_project_get(project["id"])["project"]
                task = current["tasks"][0]
                return task if task.get("executionState") == "done" else None

            task = wait_for(done)
            assert task["reworkCount"] == 1
            assert len(task["attempts"]) == 2
            assert len(task["reviewHistory"]) == 2
            assert task["reviewResult"]["status"] == "pass"
            assert "missing edge case" in executor_prompts[1]
            assert task["completedAt"]
            assert task["columnId"] == col_id(server._handle_project_get(project["id"])["project"], "Done")
        finally:
            server._project_execution_call_executor = old_executor
            server._project_execution_call_reviewer = old_reviewer
            restore_store(old)


def test_reviewer_needs_more_work_blocks_after_three_rework_cycles():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        old_reviewer = server._project_execution_call_reviewer
        executor_count = {"value": 0}

        def executor_call(executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600):
            executor_count["value"] += 1
            return {
                "ok": True,
                "status": "completed",
                "reply": f"done {executor_count['value']}",
                "modifiedFiles": [],
                "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
            }

        def reviewer_call(reviewer, prompt, review_id, project_id=None, task_id=None, timeout=600):
            return {"ok": True, "status": "completed", "reply": '{"status":"needs_more_work","summary":"still failing","rationale":"not fixed","items":[]}'}

        server._project_execution_call_executor = executor_call
        server._project_execution_call_reviewer = reviewer_call
        try:
            project, task = create_project_execution_project(workspace)
            task = complete_project_task_execution(project["id"], task["id"])
            started = server._handle_project_execution_review_start(project["id"], task["id"], {"attemptId": task["evidence"]["attemptId"]})
            assert started["ok"] is True

            def blocked_after_reworks():
                current = server._handle_project_get(project["id"])["project"]
                task = current["tasks"][0]
                return task if task.get("executionState") == "blocked" and int(task.get("reworkCount") or 0) == 3 else None

            task = wait_for(blocked_after_reworks)
            assert executor_count["value"] == 4
            assert len(task["attempts"]) == 4
            assert len(task["reviewHistory"]) == 4
            assert "three rework cycles" in task["blockedReason"]
        finally:
            server._project_execution_call_executor = old_executor
            server._project_execution_call_reviewer = old_reviewer
            restore_store(old)


def test_independent_review_pass_waits_for_user_acceptance_then_done():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        old_reviewer = server._project_execution_call_reviewer
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "implemented\npytest: 2 passed", "modifiedFiles": ["result.txt"],
            "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
        }
        server._project_execution_call_reviewer = lambda reviewer, prompt, review_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": '{"status":"pass","summary":"ready","rationale":"evidence is sufficient","items":[]}',
        }
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_task_update(project["id"], task["id"], {"requiresUserAcceptance": True})
            task = complete_project_task_execution(project["id"], task["id"])
            done_col = next(c["id"] for c in project["columns"] if c["title"] == "Done")
            assert task["columnId"] != done_col
            task = review_project_execution_task(project["id"], task["id"])
            assert task["reviewResult"]["status"] == "pass"
            assert task["completedAt"] is None
            assert task["columnId"] != done_col

            stale = server._handle_project_execution_acceptance(project["id"], task["id"], {"action": "accept", "attemptId": "wrong"})
            assert stale["_status"] == 409
            accepted = server._handle_project_execution_acceptance(project["id"], task["id"], {"action": "accept", "attemptId": task["reviewResult"]["attemptId"]})
            assert accepted["ok"] is True
            assert accepted["task"]["executionState"] == "done"
            assert accepted["task"]["columnId"] == done_col
            assert accepted["task"]["completedAt"]
        finally:
            server._project_execution_call_executor = old_executor
            server._project_execution_call_reviewer = old_reviewer
            restore_store(old)


def test_feishu_acceptance_notification_and_card_actions():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        old_reviewer = server._project_execution_call_reviewer
        old_send = server.send_feishu_notification
        feishu_calls = []
        server.send_feishu_notification = fake_feishu_sender(feishu_calls)
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "implemented", "modifiedFiles": [],
            "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
        }
        server._project_execution_call_reviewer = lambda reviewer, prompt, review_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": '{"status":"pass","summary":"ready","rationale":"ok","items":[]}',
        }
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_task_update(project["id"], task["id"], {"requiresUserAcceptance": True})
            task = complete_project_task_execution(project["id"], task["id"])
            task = review_project_execution_task(project["id"], task["id"])
            assert len(feishu_calls) == 1
            intent = feishu_calls[0]["intent"]
            assert intent["type"] == "application_form"
            assert intent["target"] == "feishu-project-execution-acceptance"
            assert intent["inputs"][0]["name"] == "feedback"
            assert intent["actions"][0]["value"]["action"] == "project_execution_accept"
            assert intent["actions"][1]["value"]["action"] == "project_execution_rework"
            assert intent["actions"][2]["url"].startswith("http://")
            assert "/#projects?projectId=" in intent["actions"][2]["url"]
            rendered = build_feishu_card(intent)
            rendered_elements = rendered["card"]["body"]["elements"]
            form = next(element for element in rendered_elements if element["tag"] == "form")
            feedback_input = next(element for element in form["elements"] if element["tag"] == "input")
            button_row = next(element for element in form["elements"] if element["tag"] == "column_set")
            buttons = [column["elements"][0] for column in button_row["columns"]]
            accept_button = next(button for button in buttons if button["text"]["content"] == "接受")
            rework_button = next(button for button in buttons if button["text"]["content"] == "要求返工")
            jump_button = next(button for button in buttons if button["text"]["content"] == "打开任务")
            assert rendered["card"]["schema"] == "2.0"
            assert feedback_input["name"] == "feedback"
            assert [button["text"]["content"] for button in buttons] == ["接受", "要求返工", "打开任务"]
            assert rework_button["text"]["content"] == "要求返工"
            assert rework_button["form_action_type"] == "submit"
            assert rework_button["behaviors"][0]["value"]["action"] == "project_execution_rework"
            assert accept_button["behaviors"][0]["value"]["action"] == "project_execution_accept"
            assert jump_button["behaviors"][0]["type"] == "open_url"

            duplicate = server._send_project_execution_acceptance_notification(
                server._handle_project_get(project["id"])["project"],
                task,
                task["reviewResult"]["attemptId"],
            )
            assert duplicate["status"] == "skipped_duplicate"
            assert len(feishu_calls) == 1

            stale = server._handle_feishu_card_action({
                "event": {"operator": {"open_id": "ou_demo"}, "action": {"value": {
                    "action": "project_execution_accept",
                    "project_id": project["id"],
                    "task_id": task["id"],
                    "attempt_id": "wrong",
                }}}
            })
            assert stale["ok"] is False
            assert stale["outcome"]["businessStatus"] == "project_execution_action_failed"

            accepted = server._handle_feishu_card_action({
                "event": {"operator": {"open_id": "ou_demo"}, "action": {"value": {
                    "action": "project_execution_accept",
                    "project_id": project["id"],
                    "task_id": task["id"],
                    "attempt_id": task["reviewResult"]["attemptId"],
                }}}
            })
            assert accepted["ok"] is True
            assert accepted["outcome"]["businessStatus"] == "done"
            current = server._handle_project_get(project["id"])["project"]["tasks"][0]
            assert current["executionState"] == "done"
        finally:
            server.send_feishu_notification = old_send
            server._project_execution_call_executor = old_executor
            server._project_execution_call_reviewer = old_reviewer
            restore_store(old)


def test_feishu_acceptance_rework_uses_default_feedback():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        old_reviewer = server._project_execution_call_reviewer
        old_send = server.send_feishu_notification
        feishu_calls = []
        server.send_feishu_notification = fake_feishu_sender(feishu_calls)
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "implemented", "modifiedFiles": [],
            "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
        }
        server._project_execution_call_reviewer = lambda reviewer, prompt, review_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": '{"status":"pass","summary":"ready","rationale":"ok","items":[]}',
        }
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_task_update(project["id"], task["id"], {"requiresUserAcceptance": True})
            task = complete_project_task_execution(project["id"], task["id"])
            task = review_project_execution_task(project["id"], task["id"])
            result = server._handle_feishu_card_action({
                "event": {"operator": {"open_id": "ou_demo"}, "action": {"value": {
                    "action": "project_execution_rework",
                    "project_id": project["id"],
                    "task_id": task["id"],
                    "attempt_id": task["reviewResult"]["attemptId"],
                }}}
            })
            assert result["ok"] is True
            assert result["outcome"]["businessStatus"] == "reworking"
            current = server._handle_project_get(project["id"])["project"]["tasks"][0]
            assert current["executionState"] == "reworking"
            assert current["reworkFeedback"] == server._PROJECT_EXECUTION_FEISHU_REWORK_FEEDBACK
        finally:
            server.send_feishu_notification = old_send
            server._project_execution_call_executor = old_executor
            server._project_execution_call_reviewer = old_reviewer
            restore_store(old)


def test_feishu_acceptance_rework_uses_card_feedback_input():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        old_reviewer = server._project_execution_call_reviewer
        old_send = server.send_feishu_notification
        feishu_calls = []
        server.send_feishu_notification = fake_feishu_sender(feishu_calls)
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "implemented", "modifiedFiles": [],
            "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
        }
        server._project_execution_call_reviewer = lambda reviewer, prompt, review_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": '{"status":"pass","summary":"ready","rationale":"ok","items":[]}',
        }
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_task_update(project["id"], task["id"], {"requiresUserAcceptance": True})
            task = complete_project_task_execution(project["id"], task["id"])
            task = review_project_execution_task(project["id"], task["id"])
            result = server._handle_feishu_card_action({
                "event": {"operator": {"open_id": "ou_demo"}, "action": {
                    "value": {
                        "action": "project_execution_rework",
                        "project_id": project["id"],
                        "task_id": task["id"],
                        "attempt_id": task["reviewResult"]["attemptId"],
                    },
                    "form_value": {"feedback": "请补充 README 的验收说明"},
                }}
            })
            assert result["ok"] is True
            assert result["outcome"]["businessStatus"] == "reworking"
            current = server._handle_project_get(project["id"])["project"]["tasks"][0]
            assert current["executionState"] == "reworking"
            assert current["reworkFeedback"] == "请补充 README 的验收说明"
        finally:
            server.send_feishu_notification = old_send
            server._project_execution_call_executor = old_executor
            server._project_execution_call_reviewer = old_reviewer
            restore_store(old)


def test_acceptance_reject_and_mark_blocked_require_feedback_and_invalidate_pass():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        old_reviewer = server._project_execution_call_reviewer
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "pytest: 1 passed", "modifiedFiles": [],
            "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
        }
        server._project_execution_call_reviewer = lambda reviewer, prompt, review_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": '{"status":"pass","summary":"ready","rationale":"ok","items":[]}',
        }
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_task_update(project["id"], task["id"], {"requiresUserAcceptance": True})
            task = complete_project_task_execution(project["id"], task["id"])
            task = review_project_execution_task(project["id"], task["id"])
            no_feedback = server._handle_project_execution_acceptance(project["id"], task["id"], {
                "action": "reject_and_rework", "attemptId": task["reviewResult"]["attemptId"], "feedback": "",
            })
            assert no_feedback["_status"] == 400
            rejected = server._handle_project_execution_acceptance(project["id"], task["id"], {
                "action": "reject_and_rework", "attemptId": task["reviewResult"]["attemptId"], "feedback": "missing edge case",
            })
            assert rejected["ok"] is True
            assert rejected["task"]["executionState"] == "reworking"
            assert rejected["task"]["reviewResult"] == {}
            assert rejected["task"]["reworkFeedback"] == "missing edge case"
            assert rejected["task"]["activeAttemptId"] == rejected["attemptId"]
            accept_old = server._handle_project_execution_acceptance(project["id"], task["id"], {
                "action": "accept", "attemptId": task["reviewResult"]["attemptId"],
            })
            assert accept_old["_status"] == 409
        finally:
            server._project_execution_call_executor = old_executor
            server._project_execution_call_reviewer = old_reviewer
            restore_store(old)


def test_acceptance_reject_can_rework_skipped_review_result():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "implemented without reviewer", "modifiedFiles": [],
        }
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_project_update(project["id"], {"defaultReviewerAgentId": None})
            server._handle_task_update(project["id"], task["id"], {
                "reviewerAgentId": None,
                "requiresUserAcceptance": True,
                "allowReviewerlessExecution": True,
            })
            started = server._handle_project_execution_start(project["id"], task["id"], {})
            assert started["ok"] is True

            task = wait_for(lambda: server._handle_project_get(project["id"])["project"]["tasks"][0]
                            if server._handle_project_get(project["id"])["project"]["tasks"][0].get("executionState") == "awaiting_user_acceptance"
                            else None)
            assert task["reviewResult"]["status"] == "skipped"
            rejected = server._handle_project_execution_acceptance(project["id"], task["id"], {
                "action": "reject_and_rework",
                "attemptId": task["reviewResult"]["attemptId"],
                "feedback": "需要补充真实数据",
            })
            assert rejected["ok"] is True
            assert rejected["task"]["executionState"] == "reworking"
            assert rejected["task"]["reviewResult"] == {}
            assert rejected["task"]["reworkFeedback"] == "需要补充真实数据"
            assert rejected["task"]["activeAttemptId"] == rejected["attemptId"]
        finally:
            server._project_execution_call_executor = old_executor
            restore_store(old)


def test_acceptance_reject_starts_rework_execution_before_returning_to_review():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        calls = []

        def executor_call(executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600):
            calls.append(attempt_id)
            return {
                "ok": True,
                "status": "completed",
                "reply": "implemented",
                "modifiedFiles": [],
                "checklistUpdates": [{"id": "done", "text": "Complete implementation", "done": True}],
            }

        server._project_execution_call_executor = executor_call
        try:
            project, task = create_project_execution_project(workspace)
            server._handle_project_update(project["id"], {"defaultReviewerAgentId": None})
            server._handle_task_update(project["id"], task["id"], {
                "reviewerAgentId": None,
                "requiresUserAcceptance": True,
                "allowReviewerlessExecution": True,
            })
            started = server._handle_project_execution_start(project["id"], task["id"], {})
            assert started["ok"] is True
            task = wait_for(lambda: server._handle_project_get(project["id"])["project"]["tasks"][0]
                            if server._handle_project_get(project["id"])["project"]["tasks"][0].get("executionState") == "awaiting_user_acceptance"
                            else None)

            rejected = server._handle_project_execution_acceptance(project["id"], task["id"], {
                "action": "reject_and_rework",
                "attemptId": task["reviewResult"]["attemptId"],
                "feedback": "重新执行",
            })
            assert rejected["status"] == "reworking"
            assert calls[-1] == started["attemptId"]

            reworked = wait_for(lambda: server._handle_project_get(project["id"])["project"]["tasks"][0]
                                if len(calls) >= 2 and server._handle_project_get(project["id"])["project"]["tasks"][0].get("executionState") == "awaiting_user_acceptance"
                                else None)
            assert calls[-1] == rejected["attemptId"]
            assert reworked["reviewResult"]["status"] == "skipped"
            assert reworked["activeAttemptId"] is None
            assert reworked["attempts"][-1]["id"] == rejected["attemptId"]
        finally:
            server._project_execution_call_executor = old_executor
            restore_store(old)


def test_legacy_review_check_cannot_update_project_execution_project():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        try:
            project, task = create_project_execution_project(workspace)
            result = server._handle_review_check_update(project["id"], task["id"], {"reviewCheck": [{"text": "force", "status": "pass"}]})
            assert result["_status"] == 409
        finally:
            restore_store(old)


if __name__ == "__main__":
    test_project_store_round_trip_and_legacy_defaults()
    test_workflow_chat_reads_project_execution_codex_attempt_reasoning()
    test_openclaw_workflow_chat_reads_gateway_prefixed_session_file()
    test_workflow_chat_reads_project_execution_hermes_attempt_history_only()
    test_project_execution_hermes_call_uses_attempt_conversation_id()
    test_project_execution_openclaw_executor_uses_attempt_session_id()
    test_project_execution_openclaw_reviewer_uses_review_session_id()
    test_project_create_auto_workspace_and_store_round_trip()
    test_project_create_normal_and_manual_workspace_provenance()
    test_project_from_template_auto_workspace_matches_project_create()
    test_project_delete_auto_workspace_keep_or_delete_and_never_delete_user_workspace()
    test_auto_workspace_create_failure_does_not_create_project()
    test_workspace_validation_and_dirty_fingerprint()
    test_workspace_validation_rejects_files_and_outside_allowed_roots()
    test_artifact_core_lists_markdown_only_and_reads_safely()
    test_project_artifacts_include_phase7_source_records()
    test_project_artifacts_reject_disabled_or_missing_workspace_projects()
    test_project_artifacts_real_acceptance_review_scenario()
    test_project_execution_project_create_rejects_invalid_workspace()
    test_roles_must_be_independent()
    test_task_role_overrides_project_defaults()
    test_project_execution_prompt_requires_checklist_lifecycle_and_meeting_context()
    test_project_execution_applies_verified_checklist_updates_from_executor()
    test_project_execution_creates_checklist_items_from_executor_updates_when_empty()
    test_project_execution_matches_summarized_checklist_update_conservatively()
    test_project_execution_does_not_apply_ambiguous_fuzzy_checklist_update()
    test_project_execution_pipeline_restart_clears_execution_context()
    test_project_execution_manual_restart_clears_stale_meeting_bindings()
    test_project_execution_meeting_result_records_discussion_points_not_comments()
    test_project_execution_applies_executor_meeting_discussion_points()
    test_project_execution_assignee_defaults_executor_on_update()
    test_provider_matrix_routes_execution_with_workspace_and_provider_ref()
    test_selected_task_executes_and_stops_at_execution_complete()
    test_project_execution_transition_syncs_state_columns()
    test_normal_project_can_move_task_to_done_without_project_execution_restriction()
    test_project_level_start_selects_first_eligible_and_auto_reviews_to_done_by_default()
    test_reviewer_pass_uses_attempt_acceptance_snapshot()
    test_project_level_start_skips_done_columns_and_reports_no_eligible_task()
    test_project_pipeline_restart_requires_every_task_to_allow_retriggering()
    test_project_level_start_persists_reviewer_skip_confirmation_for_toolbar_state()
    test_missing_reviewer_skip_completes_by_default_after_explicit_confirmation()
    test_task_can_allow_missing_reviewer_without_confirmation_and_complete_by_default()
    test_skip_review_completion_uses_attempt_acceptance_snapshot()
    test_skipped_review_waits_for_acceptance_when_required()
    test_project_start_preserves_dirty_confirmation_after_reviewer_skip_confirmation()
    test_direct_task_start_supports_reviewer_skip_and_dirty_confirmation_chain()
    test_direct_task_start_requires_explicit_executor_agent()
    test_continuous_flow_auto_continues_when_task_does_not_require_acceptance()
    test_direct_task_start_does_not_enable_continuous_flow_even_when_project_default_is_continuous()
    test_direct_task_start_respects_repeat_trigger_setting_for_done_tasks()
    test_dirty_confirmation_is_bound_to_current_fingerprint()
    test_dirty_confirmation_can_be_reconfirmed_for_same_fingerprint()
    test_start_rejects_when_another_task_is_reviewing()
    test_execution_failure_blocks_with_redacted_bounded_evidence()
    test_cancel_active_execution_blocks_and_preserves_evidence()
    test_feishu_start_failure_notification_dedupes_after_persisted_reload()
    test_status_reconciles_stale_active_execution_after_restart()
    test_reviewer_provider_matrix_receives_read_only_evidence_packet()
    test_malformed_reviewer_result_blocks_instead_of_passing()
    test_reviewer_needs_more_work_auto_reworks_and_rechecks_to_done_by_default()
    test_reviewer_needs_more_work_blocks_after_three_rework_cycles()
    test_independent_review_pass_waits_for_user_acceptance_then_done()
    test_feishu_acceptance_notification_and_card_actions()
    test_feishu_acceptance_rework_uses_default_feedback()
    test_feishu_acceptance_rework_uses_card_feedback_input()
    test_acceptance_reject_and_mark_blocked_require_feedback_and_invalidate_pass()
    test_acceptance_reject_can_rework_skipped_review_result()
    test_acceptance_reject_starts_rework_execution_before_returning_to_review()
    test_legacy_review_check_cannot_update_project_execution_project()
    print("ok")
