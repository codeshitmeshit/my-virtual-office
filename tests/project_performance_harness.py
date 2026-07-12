#!/usr/bin/env python3
"""Deterministic Project Execution baseline harness.

The harness measures application-level operation counts with an in-memory
project store. Wall-clock values are secondary evidence; load/save/external
call counts are the stable performance contract.
"""

import argparse
import copy
import json
import os
import statistics
import sys
import tempfile
import threading
import time
from contextlib import contextmanager


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-perf-import-"))

import server


SCALES = {
    "small": (5, 10),
    "medium": (50, 50),
    "large": (200, 100),
}


class MemoryProjects:
    def __init__(self, data):
        self.data = copy.deepcopy(data)
        self.counts = {"load": 0, "save": 0}

    def load(self):
        self.counts["load"] += 1
        return copy.deepcopy(self.data)

    def save(self, value):
        self.counts["save"] += 1
        self.data = copy.deepcopy(value)


class NoopThread:
    def __init__(self, *args, **kwargs):
        self.target = kwargs.get("target") or (args[0] if args else None)

    def start(self):
        return None


def _task(project_index, task_index):
    return {
        "id": f"task-{project_index}-{task_index}",
        "title": f"Task {project_index}-{task_index}",
        "description": "benchmark fixture",
        "columnId": f"backlog-{project_index}",
        "order": task_index,
        "priority": "medium",
        "assignee": "executor",
        "executorAgentId": "executor",
        "reviewerAgentId": "reviewer",
        "executionState": "backlog",
        "requiresUserAcceptance": True,
        "checklist": [{"id": "check-1", "text": "verified", "done": True, "source": "user"}],
        "attempts": [],
        "comments": [],
        "stateHistory": [],
    }


def fixture(scale):
    project_count, task_count = SCALES[scale]
    projects = []
    for p_index in range(project_count):
        projects.append({
            "id": f"project-{p_index}",
            "title": f"Project {p_index}",
            "status": "active",
            "projectExecutionEnabled": True,
            "workspacePath": "/tmp/vo-perf-workspace",
            "workspaceKind": "directory",
            "workspaceStatus": {"ok": True},
            "defaultExecutorAgentId": "executor",
            "defaultReviewerAgentId": "reviewer",
            "projectExecutionStartMode": "single",
            "projectExecutionFlowActive": False,
            "workflowActive": False,
            "workflowPhase": "idle",
            "activeTaskId": None,
            "activeAgent": None,
            "executionPolicy": {"maxActiveTasks": 1},
            "executionDirtyConfirmations": [],
            "columns": [
                {"id": f"backlog-{p_index}", "title": "Backlog", "order": 0},
                {"id": f"progress-{p_index}", "title": "In Progress", "order": 1},
                {"id": f"review-{p_index}", "title": "Review", "order": 2},
                {"id": f"done-{p_index}", "title": "Done", "order": 3},
            ],
            "tasks": [_task(p_index, t_index) for t_index in range(task_count)],
            "activity": [],
            "scheduledCronHistory": [],
            "updatedAt": "before",
        })
    return {"projects": projects, "templates": []}


@contextmanager
def patched(**values):
    originals = {}
    try:
        for name, value in values.items():
            originals[name] = getattr(server, name)
            setattr(server, name, value)
        yield
    finally:
        for name, value in originals.items():
            setattr(server, name, value)


def _roles():
    return [
        {"id": "executor", "statusKey": "executor", "providerKind": "codex", "providerAgentId": "executor", "name": "Executor"},
        {"id": "reviewer", "statusKey": "reviewer", "providerKind": "codex", "providerAgentId": "reviewer", "name": "Reviewer"},
    ]


def _common(scale):
    memory = MemoryProjects(fixture(scale))
    external = {"provider": 0, "notification": 0, "gateway": 0, "git_scan": 0}

    def snapshot(_workspace):
        external["git_scan"] += 1
        return {"dirty": False, "files": [], "fingerprint": "", "truncated": False}

    return memory, external, {
        "_load_projects": memory.load,
        "_save_projects": memory.save,
        "get_roster": _roles,
        "_project_execution_validate_workspace": lambda path: {"ok": True, "path": path, "kind": "directory"},
        "_project_execution_git_snapshot": snapshot,
        "_send_feishu_workflow_notification": lambda *args, **kwargs: external.__setitem__("notification", external["notification"] + 1) or {"ok": True},
    }


def scenario_start_prepare(scale):
    memory, external, patches = _common(scale)
    original_thread = server.threading.Thread
    server.threading.Thread = NoopThread
    try:
        with patched(**patches):
            result = server._handle_project_execution_start("project-0", "task-0-0", {})
            assert result.get("ok"), result
    finally:
        server.threading.Thread = original_thread
        server._PROJECT_EXECUTION_CANCEL_FLAGS.clear()
    return memory.counts, external


def scenario_provider_completion(scale):
    memory, external, patches = _common(scale)
    project = memory.data["projects"][0]
    task = project["tasks"][0]
    attempt_id = "attempt-1"
    task["attempts"] = [{
        "id": attempt_id,
        "status": "executing",
        "workspacePath": project["workspacePath"],
        "executor": {"id": "executor", "providerKind": "codex"},
        "baseline": {"dirty": False, "files": []},
        "autoReviewAfterExecution": False,
    }]
    task["activeAttemptId"] = attempt_id
    task["executionState"] = "executing"
    project.update({"workflowActive": True, "workflowPhase": "executing", "activeTaskId": task["id"], "activeAgent": "executor"})

    def executor(*args, **kwargs):
        external["provider"] += 1
        return {"ok": True, "status": "completed", "reply": "done", "modifiedFiles": [], "testResults": []}

    patches["_project_execution_call_executor"] = executor
    patches["_send_project_execution_intervention_notification"] = lambda *args, **kwargs: None
    with patched(**patches):
        server._PROJECT_EXECUTION_CANCEL_FLAGS[attempt_id] = threading.Event()
        server._project_execution_run_attempt("project-0", task["id"], attempt_id, server._PROJECT_EXECUTION_CANCEL_FLAGS[attempt_id])
    server._PROJECT_EXECUTION_CANCEL_FLAGS.clear()
    return memory.counts, external


def scenario_review_start(scale):
    memory, external, patches = _common(scale)
    project = memory.data["projects"][0]
    task = project["tasks"][0]
    task["executionState"] = "execution_complete"
    task["attempts"] = [{"id": "attempt-1", "status": "execution_complete", "evidence": {"executorSummary": "done"}}]
    original_thread = server.threading.Thread
    server.threading.Thread = NoopThread
    try:
        with patched(**patches):
            result = server._handle_project_execution_review_start("project-0", task["id"], {"attemptId": "attempt-1"})
            assert result.get("ok"), result
    finally:
        server.threading.Thread = original_thread
        server._PROJECT_EXECUTION_REVIEW_FLAGS.clear()
    return memory.counts, external


def scenario_acceptance(scale):
    memory, external, patches = _common(scale)
    project = memory.data["projects"][0]
    task = project["tasks"][0]
    task["executionState"] = "awaiting_user_acceptance"
    task["reviewResult"] = {"id": "review-1", "attemptId": "attempt-1", "status": "pass"}
    task["attempts"] = [{"id": "attempt-1", "status": "review_passed", "requiresUserAcceptance": True}]
    with patched(**patches):
        result = server._handle_project_execution_acceptance(
            "project-0", task["id"], {"action": "accept", "attemptId": "attempt-1"}
        )
        assert result.get("ok"), result
    return memory.counts, external


def scenario_cron_dispatch(scale):
    memory, external, patches = _common(scale)
    project = memory.data["projects"][0]
    project["status"] = "archived"
    binding = {"id": "cron-1", "projectId": "project-0", "targetType": "projectWorkflow", "name": "Benchmark"}
    patches["_load_project_cron_bindings"] = lambda: {"bindings": {"cron-1": binding}}
    patches["_project_cron_update_binding_status"] = lambda *args, **kwargs: None
    patches["_gateway_rpc_call"] = lambda *args, **kwargs: external.__setitem__("gateway", external["gateway"] + 1) or {"ok": True}
    with patched(**patches):
        result = server._handle_project_scheduled_cron_dispatch("project-0", "cron-1", source="benchmark")
        assert result.get("status") == "skipped", result
    return memory.counts, external


SCENARIOS = {
    "start_prepare": scenario_start_prepare,
    "provider_completion": scenario_provider_completion,
    "review_start": scenario_review_start,
    "acceptance": scenario_acceptance,
    "cron_dispatch": scenario_cron_dispatch,
}


def measure(scale, warmups, runs):
    results = {}
    for name, scenario in SCENARIOS.items():
        for _ in range(warmups):
            scenario(scale)
        durations = []
        samples = []
        for _ in range(runs):
            started = time.perf_counter_ns()
            store_counts, external_counts = scenario(scale)
            durations.append((time.perf_counter_ns() - started) / 1_000_000)
            samples.append({**store_counts, **external_counts})
        ordered = sorted(durations)
        p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))
        results[name] = {
            "median_ms": round(statistics.median(durations), 3),
            "p95_ms": round(ordered[p95_index], 3),
            "counts": samples[0],
            "counts_stable": all(item == samples[0] for item in samples),
        }
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scales", default="small,medium,large")
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--output")
    parser.add_argument("--revision-label", default=None, help="Explicit SHA/label for the measured code")
    args = parser.parse_args()
    actual_head = os.popen("git rev-parse HEAD").read().strip()
    report = {
        "revision_label": args.revision_label or actual_head,
        "measured_head": actual_head,
        "warmups": args.warmups,
        "runs": args.runs,
        "fixtures": {name: {"projects": value[0], "tasks_per_project": value[1]} for name, value in SCALES.items()},
        "scales": {scale: measure(scale, args.warmups, args.runs) for scale in args.scales.split(",")},
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as output:
            output.write(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
