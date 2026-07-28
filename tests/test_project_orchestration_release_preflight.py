#!/usr/bin/env python3
"""Tests for the read-only stage-pipeline release preflight."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from project_orchestration_release_preflight import build_report


def _write_project(root: Path, slug: str, *, project_id: str, title: str, execution_model: str | None, tasks: int = 0) -> Path:
    project_dir = root / "projects-md" / slug
    tasks_dir = project_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"id: {project_id}", f"title: {title}"]
    if execution_model is not None:
        lines.append(f"executionModel: {execution_model}")
    lines.extend(["---", "# Project", "Fixture"])
    (project_dir / "project.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for index in range(tasks):
        (tasks_dir / f"task-{index}.md").write_text(
            f"---\nid: task-{index}\ntitle: Task {index}\n---\n## Description\nFixture\n",
            encoding="utf-8",
        )
    return project_dir


def _snapshot_files(path: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for root, _, files in os.walk(path):
        for name in files:
            file_path = Path(root) / name
            result[str(file_path.relative_to(path))] = file_path.read_bytes()
    return result


def test_preflight_reports_exact_legacy_candidates_without_writing(tmp_path):
    legacy_dir = _write_project(tmp_path, "legacy", project_id="legacy-1", title="Legacy", execution_model=None, tasks=2)
    marked_dir = _write_project(
        tmp_path,
        "marked",
        project_id="marked-1",
        title="Marked",
        execution_model="stage_pipeline_v1",
        tasks=1,
    )
    unexpected_dir = _write_project(
        tmp_path,
        "unexpected",
        project_id="unexpected-1",
        title="Unexpected",
        execution_model="free_mode",
    )
    before = _snapshot_files(tmp_path)

    report = build_report(tmp_path, timestamp="20260725T000000Z")

    assert _snapshot_files(tmp_path) == before
    assert report["readOnly"] is True
    assert report["destructiveActionsPerformed"] == []
    assert report["backupCandidate"] == {
        "source": str(tmp_path.resolve()),
        "target": str(tmp_path.resolve().parent / f"{tmp_path.name}.backup-before-stage-pipeline-20260725T000000Z"),
        "actionRequired": "copy_status_dir_before_destructive_cleanup",
    }
    assert report["summary"] == {
        "canonicalProjectCount": 3,
        "legacyDeletionCandidateCount": 2,
        "readErrorCount": 0,
    }
    candidates = {item["id"]: item for item in report["legacyDeletionCandidates"]}
    assert set(candidates) == {"legacy-1", "unexpected-1"}
    assert candidates["legacy-1"]["projectDir"] == str(legacy_dir.resolve())
    assert candidates["legacy-1"]["projectFile"] == str((legacy_dir / "project.md").resolve())
    assert candidates["legacy-1"]["taskCount"] == 2
    assert candidates["legacy-1"]["reason"] == "missing_required_execution_model"
    assert candidates["unexpected-1"]["projectDir"] == str(unexpected_dir.resolve())
    assert candidates["unexpected-1"]["reason"] == "unexpected_execution_model"
    marked = next(item for item in report["projects"] if item["id"] == "marked-1")
    assert marked["projectDir"] == str(marked_dir.resolve())
    assert marked["executionModel"] == "stage_pipeline_v1"


def test_preflight_cli_outputs_json_and_remains_read_only(tmp_path):
    _write_project(tmp_path, "legacy", project_id="legacy-cli", title="Legacy CLI", execution_model=None)
    before = _snapshot_files(tmp_path)

    output = subprocess.check_output(
        [
            sys.executable,
            str(ROOT / "scripts" / "project_orchestration_release_preflight.py"),
            "--status-dir",
            str(tmp_path),
            "--timestamp",
            "20260725T010203Z",
        ],
        cwd=ROOT,
        text=True,
    )

    assert _snapshot_files(tmp_path) == before
    report = json.loads(output)
    assert report["summary"]["canonicalProjectCount"] == 1
    assert report["summary"]["legacyDeletionCandidateCount"] == 1
    assert report["legacyDeletionCandidates"][0]["id"] == "legacy-cli"
