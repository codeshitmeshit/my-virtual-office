#!/usr/bin/env python3
"""Tests for the stage-pipeline release rehearsal command."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _write_legacy_project(status_dir: Path, slug: str, project_id: str, title: str) -> None:
    project_dir = status_dir / "projects-md" / slug
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.md").write_text(
        "\n".join([
            "---",
            f"id: {project_id}",
            f"title: {title}",
            "projectType: one_time",
            "status: active",
            "---",
            "# Project",
            "Legacy fixture",
        ])
        + "\n",
        encoding="utf-8",
    )


def test_release_rehearsal_cli_smokes_deploy_and_project_store_rollback(tmp_path):
    status_dir = tmp_path / "status"
    backup_dir = tmp_path / "backup"
    (status_dir / "projects-md").mkdir(parents=True)
    for index in range(3):
        _write_legacy_project(
            backup_dir,
            f"legacy-{index}",
            f"legacy-{index}",
            f"Legacy {index}",
        )

    output = subprocess.check_output(
        [
            sys.executable,
            str(ROOT / "scripts" / "project_orchestration_release_rehearsal.py"),
            "--status-dir",
            str(status_dir),
            "--backup-dir",
            str(backup_dir),
        ],
        cwd=ROOT,
        text=True,
    )

    report = json.loads(output)
    assert report["ok"] is True
    assert report["readOnlyToRealStatusDir"] is True
    assert report["preMutationPreflight"]["legacyDeletionCandidateCount"] == 0
    assert report["coordinatedActivation"]["ok"] is True
    assert report["newProjectSmoke"]["executionModel"] == "stage_pipeline_v1"
    assert report["newProjectSmoke"]["stages"] == [1, 2]
    assert report["serviceStop"]["ok"] is True
    assert report["previousCodeRestore"]["ok"] is True
    assert report["projectStoreRestore"]["postRestorePreflight"]["legacyDeletionCandidateCount"] == 3
    assert not list((status_dir / "projects-md").iterdir())
