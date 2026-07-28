#!/usr/bin/env python3
"""Non-destructive release and rollback rehearsal for stage-pipeline projects."""

from __future__ import annotations

import argparse
import json
import os
import py_compile
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from project_store import MarkdownProjectStore  # noqa: E402
from project_orchestration_release_preflight import build_report  # noqa: E402
from services.project_orchestration import (  # noqa: E402
    EXECUTION_MODEL_STAGE_PIPELINE_V1,
    default_orchestration_state,
    default_skip_state,
    validate_stage_invariants,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _load_projects(status_dir: Path) -> list[dict[str, Any]]:
    return list(MarkdownProjectStore(str(status_dir)).load_all().get("projects") or [])


def _invariant_report(status_dir: Path) -> dict[str, Any]:
    projects = _load_projects(status_dir)
    checked: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for project in projects:
        if project.get("executionModel") != EXECUTION_MODEL_STAGE_PIPELINE_V1:
            continue
        result = validate_stage_invariants(project)
        project_issues = [
            {
                "code": issue.code,
                "message": issue.message,
                "taskId": issue.task_id,
                "stage": issue.stage,
            }
            for issue in result.issues
        ]
        checked.append({
            "id": project.get("id"),
            "title": project.get("title"),
            "ok": result.ok,
            "stages": list(result.stages),
            "issueCount": len(project_issues),
        })
        issues.extend({"projectId": project.get("id"), **issue} for issue in project_issues)
    return {
        "projectCount": len(projects),
        "markedProjectCount": len(checked),
        "ok": not issues,
        "checked": checked,
        "issues": issues,
    }


def _task(task_id: str, title: str, stage: int, *, executor: str) -> dict[str, Any]:
    return {
        "id": task_id,
        "title": title,
        "description": f"Release rehearsal task {title}",
        "columnId": "backlog",
        "order": stage,
        "executionStage": stage,
        "stageRunId": None,
        "orchestrationSkip": default_skip_state(),
        "executionState": "pending",
        "activeAttemptId": None,
        "attempts": [],
        "checklist": [{"id": f"{task_id}-check", "text": "Complete", "done": False}],
        "responsibleActor": {"type": "agent", "id": "owner"},
        "executorActor": {"type": "agent", "id": executor},
        "reviewerRecommendation": {"recommended": False, "triggers": []},
        "requiresUserAcceptance": True,
        "allowReviewerlessExecution": False,
        "createdAt": "2026-07-27T00:00:00+00:00",
        "updatedAt": "2026-07-27T00:00:00+00:00",
    }


def _smoke_project() -> dict[str, Any]:
    return {
        "id": "release-rehearsal-project",
        "title": "Release Rehearsal Project",
        "description": "Temporary project written only inside the release rehearsal sandbox.",
        "projectType": "one_time",
        "status": "active",
        "priority": "medium",
        "createdAt": "2026-07-27T00:00:00+00:00",
        "updatedAt": "2026-07-27T00:00:00+00:00",
        "createdBy": "release-rehearsal",
        "tags": [],
        "branch": "",
        "longTermProject": False,
        "highPriorityAiMeetingAutoApprove": False,
        "archiveMaintenanceEnabled": False,
        "archiveMaintenance": {"enabled": False, "explicit": False},
        "projectExecutionEnabled": True,
        "workspacePath": str(ROOT),
        "workspaceKind": "local",
        "workspaceStatus": {},
        "workspaceManagedBy": "user",
        "workspaceCreatedAt": None,
        "defaultExecutorAgentId": "executor-a",
        "defaultReviewerAgentId": None,
        "executionModel": EXECUTION_MODEL_STAGE_PIPELINE_V1,
        "orchestration": default_orchestration_state(),
        "scheduledCronPaused": False,
        "executionDirtyConfirmations": [],
        "columns": [{"id": "backlog", "title": "Backlog", "color": "#6c757d", "order": 0}],
        "tasks": [
            _task("task-a", "Stage A1", 1, executor="executor-a"),
            _task("task-b", "Stage A2", 1, executor="executor-b"),
            _task("task-c", "Stage B", 2, executor="executor-c"),
        ],
        "activity": [],
        "template": False,
    }


def _new_project_smoke(status_dir: Path) -> dict[str, Any]:
    store = MarkdownProjectStore(str(status_dir))
    data = store.load_all()
    project = _smoke_project()
    data["projects"] = list(data.get("projects") or []) + [project]
    store.save_all(data)
    reloaded = next(
        item for item in MarkdownProjectStore(str(status_dir)).load_all().get("projects") or []
        if item.get("id") == project["id"]
    )
    invariant = validate_stage_invariants(reloaded)
    forbidden = [
        key for key in (
            "projectExecutionStartMode",
            "projectExecutionFlowActive",
            "projectExecutionFlowStopReason",
            "workflowActive",
            "workflowPhase",
            "activeTaskId",
            "activeAgent",
            "autoMode",
            "executionPolicy",
        )
        if key in reloaded
    ]
    task_forbidden = [
        task.get("id")
        for task in reloaded.get("tasks") or []
        if isinstance(task, dict) and "executionOrder" in task
    ]
    return {
        "ok": invariant.ok and not forbidden and not task_forbidden,
        "projectId": reloaded.get("id"),
        "executionModel": reloaded.get("executionModel"),
        "orchestrationState": (reloaded.get("orchestration") or {}).get("state"),
        "stages": list(invariant.stages),
        "taskCount": len(reloaded.get("tasks") or []),
        "forbiddenProjectFields": forbidden,
        "tasksWithExecutionOrder": task_forbidden,
        "issues": [issue.code for issue in invariant.issues],
    }


def _compile_report() -> dict[str, Any]:
    files = [
        ROOT / "app/server.py",
        ROOT / "app/services/project_orchestration.py",
        ROOT / "app/services/project_orchestration_commands.py",
        ROOT / "app/services/project_stage_dispatch.py",
        ROOT / "app/services/project_orchestration_recovery.py",
    ]
    results = []
    for path in files:
        try:
            py_compile.compile(str(path), doraise=True)
            results.append({"path": str(path), "ok": True})
        except py_compile.PyCompileError as exc:
            results.append({"path": str(path), "ok": False, "error": str(exc)})
    return {"ok": all(item["ok"] for item in results), "files": results}


def _frontend_activation_report() -> dict[str, Any]:
    index = (ROOT / "app/index.html").read_text(encoding="utf-8")
    required = [
        "project-orchestration.css",
        "project-orchestration-api.js",
        "project-orchestration.js",
    ]
    return {
        "ok": all(item in index for item in required),
        "requiredAssets": required,
        "presentAssets": [item for item in required if item in index],
    }


def _service_stop_rehearsal(work_dir: Path) -> dict[str, Any]:
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(work_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}/"
    healthy = False
    try:
        for _ in range(30):
            try:
                with urllib.request.urlopen(url, timeout=0.2) as response:
                    healthy = response.status == 200
                if healthy:
                    break
            except OSError:
                time.sleep(0.1)
        process.terminate()
        try:
            process.wait(timeout=5)
            stopped = True
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
            stopped = True
        refused = False
        try:
            urllib.request.urlopen(url, timeout=0.2)
        except OSError:
            refused = True
        return {
            "ok": healthy and stopped and refused,
            "startedHealthy": healthy,
            "stopped": stopped,
            "postStopConnectionRefused": refused,
            "port": port,
        }
    finally:
        if process.poll() is None:
            process.kill()


def rehearse(status_dir: Path, backup_dir: Path, previous_code_ref: str, keep_work_dir: bool) -> dict[str, Any]:
    status_dir = status_dir.resolve()
    backup_dir = backup_dir.resolve()
    release_code_ref = _git("rev-parse", "HEAD")
    rollback_code_ref = _git("rev-parse", previous_code_ref)
    temp_root = Path(tempfile.mkdtemp(prefix="vo-stage-pipeline-release-rehearsal-"))
    deploy_status = temp_root / "deploy-status"
    rollback_status = temp_root / "rollback-status"
    try:
        shutil.copytree(status_dir, deploy_status, symlinks=True)
        pre_mutation = build_report(deploy_status, timestamp="20260727TrehearsalZ")
        invariant_before = _invariant_report(deploy_status)
        compile_check = _compile_report()
        frontend_check = _frontend_activation_report()
        smoke = _new_project_smoke(deploy_status)
        invariant_after_smoke = _invariant_report(deploy_status)
        service_stop = _service_stop_rehearsal(temp_root)
        shutil.copytree(backup_dir, rollback_status, symlinks=True)
        rollback_preflight = build_report(rollback_status, timestamp="20260727TrollbackZ")
        rollback_invariant = _invariant_report(rollback_status)
        report = {
            "schemaVersion": 1,
            "generatedAt": _utc_now(),
            "readOnlyToRealStatusDir": True,
            "statusDir": str(status_dir),
            "backupDir": str(backup_dir),
            "workDir": str(temp_root),
            "releaseCodeRef": release_code_ref,
            "rollbackCodeRef": rollback_code_ref,
            "preMutationPreflight": pre_mutation["summary"],
            "preMutationInvariant": invariant_before,
            "coordinatedActivation": {
                "backendCompile": compile_check,
                "frontendAssets": frontend_check,
                "ok": compile_check["ok"] and frontend_check["ok"],
            },
            "newProjectSmoke": smoke,
            "postSmokeInvariant": invariant_after_smoke,
            "serviceStop": service_stop,
            "previousCodeRestore": {
                "requestedRef": previous_code_ref,
                "resolvedRef": rollback_code_ref,
                "ok": bool(rollback_code_ref),
            },
            "projectStoreRestore": {
                "sourceBackup": str(backup_dir),
                "restoredSandbox": str(rollback_status),
                "postRestorePreflight": rollback_preflight["summary"],
                "postRestoreInvariant": rollback_invariant,
                "ok": rollback_preflight["summary"]["legacyDeletionCandidateCount"] == 3,
            },
        }
        report["ok"] = (
            report["preMutationPreflight"]["legacyDeletionCandidateCount"] == 0
            and invariant_before["ok"]
            and report["coordinatedActivation"]["ok"]
            and smoke["ok"]
            and invariant_after_smoke["ok"]
            and service_stop["ok"]
            and report["previousCodeRestore"]["ok"]
            and report["projectStoreRestore"]["ok"]
        )
        return report
    finally:
        if not keep_work_dir:
            shutil.rmtree(temp_root, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status-dir", default=os.environ.get("VO_STATUS_DIR") or str(ROOT / "data"))
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--previous-code-ref", default="HEAD^")
    parser.add_argument("--keep-work-dir", action="store_true")
    args = parser.parse_args(argv)
    report = rehearse(Path(args.status_dir), Path(args.backup_dir), args.previous_code_ref, args.keep_work_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
