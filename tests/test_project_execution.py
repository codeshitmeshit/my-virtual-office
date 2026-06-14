#!/usr/bin/env python3
"""Focused coverage for the Project Execution foundation."""

import os
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
    task = server._handle_task_create(project["id"], {"title": "Implement fixture", "columnId": project["columns"][0]["id"]})["task"]
    return project, task


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
        assert loaded["defaultReviewerAgentId"] == "reviewer"
        assert loaded["workflowPhase"] == "executing"
        assert loaded["activeTaskId"] == "t1"
        assert loaded["tasks"][0]["executionState"] == "backlog"
        assert loaded["tasks"][0]["attempts"] == []


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
            server._save_projects(data)

            listed = server._handle_project_artifacts_list(project["id"])
            assert listed["ok"] is True
            by_path = {a["path"]: a for a in listed["artifacts"]}
            assert set(by_path) == {"docs/artifact.md", "docs/manual.md", "other/artifact.md"}
            source = by_path["docs/artifact.md"]["sources"][0]
            assert source["taskId"] == later_task["id"]
            assert source["taskTitle"] == later_task["title"]
            assert source["agentId"] == "hermes-executor"
            assert source["providerKind"] == "hermes"
            assert source["attemptId"] == "attempt-2"
            assert by_path["docs/artifact.md"]["sources"][1]["taskId"] == task["id"]
            assert len(by_path["docs/artifact.md"]["sources"]) == 2
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
            reorder_blocked = server._handle_tasks_reorder(project["id"], {"updates": [{"id": selected["id"], "columnId": done_col, "order": 0}]})
            assert reorder_blocked["_status"] == 409
        finally:
            server._project_execution_call_executor = old_call
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


def test_dirty_confirmation_is_single_use():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
        with open(os.path.join(workspace, "dirty.txt"), "w", encoding="utf-8") as f:
            f.write("one\n")
        old = with_store(status_dir)
        old_call = server._project_execution_call_executor
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "pytest: 1 passed", "modifiedFiles": [],
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
            assert repeated["_status"] == 409
            assert repeated["code"] == "dirty_worktree_confirmation_already_used"
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
        finally:
            server._project_execution_call_executor = old_call
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
            release["done"] = True

            def blocked():
                current = server._handle_project_get(project["id"])["project"]
                task = current["tasks"][0]
                return task if task.get("executionState") == "blocked" else None

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
            assert "could not be resumed" in status["task"]["blockedReason"]
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
        }
        server._project_execution_call_reviewer = lambda reviewer, prompt, review_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": '{"status":"pass"}',
        }
        try:
            project, task = create_project_execution_project(workspace)
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


def test_reviewer_needs_more_work_auto_reworks_and_rechecks_to_user_acceptance():
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
            return {"ok": True, "status": "completed", "reply": f"done {len(executor_prompts)}", "modifiedFiles": [f"file{len(executor_prompts)}.txt"]}

        def reviewer_call(reviewer, prompt, review_id, project_id=None, task_id=None, timeout=600):
            return {"ok": True, "status": "completed", "reply": reviews.pop(0)}

        server._project_execution_call_executor = executor_call
        server._project_execution_call_reviewer = reviewer_call
        try:
            project, task = create_project_execution_project(workspace)
            task = complete_project_task_execution(project["id"], task["id"])
            started = server._handle_project_execution_review_start(project["id"], task["id"], {"attemptId": task["evidence"]["attemptId"]})
            assert started["ok"] is True

            def awaiting_acceptance():
                current = server._handle_project_get(project["id"])["project"]
                task = current["tasks"][0]
                return task if task.get("executionState") == "awaiting_user_acceptance" else None

            task = wait_for(awaiting_acceptance)
            assert task["reworkCount"] == 1
            assert len(task["attempts"]) == 2
            assert len(task["reviewHistory"]) == 2
            assert task["reviewResult"]["status"] == "pass"
            assert "missing edge case" in executor_prompts[1]
            assert task["completedAt"] is None
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
            return {"ok": True, "status": "completed", "reply": f"done {executor_count['value']}", "modifiedFiles": []}

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
        }
        server._project_execution_call_reviewer = lambda reviewer, prompt, review_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": '{"status":"pass","summary":"ready","rationale":"evidence is sufficient","items":[]}',
        }
        try:
            project, task = create_project_execution_project(workspace)
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


def test_acceptance_reject_and_mark_blocked_require_feedback_and_invalidate_pass():
    with tempfile.TemporaryDirectory() as status_dir, tempfile.TemporaryDirectory() as workspace:
        old = with_store(status_dir)
        old_executor = server._project_execution_call_executor
        old_reviewer = server._project_execution_call_reviewer
        server._project_execution_call_executor = lambda executor, prompt, workspace, attempt_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": "pytest: 1 passed", "modifiedFiles": [],
        }
        server._project_execution_call_reviewer = lambda reviewer, prompt, review_id, project_id=None, task_id=None, timeout=600: {
            "ok": True, "status": "completed", "reply": '{"status":"pass","summary":"ready","rationale":"ok","items":[]}',
        }
        try:
            project, task = create_project_execution_project(workspace)
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
            assert rejected["task"]["executionState"] == "backlog"
            assert rejected["task"]["reviewResult"] == {}
            assert rejected["task"]["reworkFeedback"] == "missing edge case"
            accept_old = server._handle_project_execution_acceptance(project["id"], task["id"], {
                "action": "accept", "attemptId": task["reviewResult"]["attemptId"],
            })
            assert accept_old["_status"] == 409
        finally:
            server._project_execution_call_executor = old_executor
            server._project_execution_call_reviewer = old_reviewer
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
    test_workspace_validation_and_dirty_fingerprint()
    test_workspace_validation_rejects_files_and_outside_allowed_roots()
    test_artifact_core_lists_markdown_only_and_reads_safely()
    test_project_artifacts_include_phase7_source_records()
    test_project_artifacts_reject_disabled_or_missing_workspace_projects()
    test_project_artifacts_real_acceptance_review_scenario()
    test_project_execution_project_create_rejects_invalid_workspace()
    test_roles_must_be_independent()
    test_task_role_overrides_project_defaults()
    test_provider_matrix_routes_execution_with_workspace_and_provider_ref()
    test_selected_task_executes_and_stops_at_execution_complete()
    test_dirty_confirmation_is_bound_to_current_fingerprint()
    test_dirty_confirmation_is_single_use()
    test_start_rejects_when_another_task_is_reviewing()
    test_execution_failure_blocks_with_redacted_bounded_evidence()
    test_cancel_active_execution_blocks_and_preserves_evidence()
    test_status_reconciles_stale_active_execution_after_restart()
    test_reviewer_provider_matrix_receives_read_only_evidence_packet()
    test_malformed_reviewer_result_blocks_instead_of_passing()
    test_reviewer_needs_more_work_auto_reworks_and_rechecks_to_user_acceptance()
    test_reviewer_needs_more_work_blocks_after_three_rework_cycles()
    test_independent_review_pass_waits_for_user_acceptance_then_done()
    test_acceptance_reject_and_mark_blocked_require_feedback_and_invalidate_pass()
    test_legacy_review_check_cannot_update_project_execution_project()
    print("ok")
