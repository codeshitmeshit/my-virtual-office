#!/usr/bin/env python3
"""Read-only preflight for the stage-pipeline Project Execution release."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from project_store import PROJECTS_DIRNAME, _parse_frontmatter  # noqa: E402


REQUIRED_EXECUTION_MODEL = "stage_pipeline_v1"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _project_task_count(project_dir: Path) -> int:
    tasks_dir = project_dir / "tasks"
    if not tasks_dir.is_dir():
        return 0
    return sum(1 for item in tasks_dir.iterdir() if item.is_file() and item.suffix == ".md")


def _read_project_meta(project_file: Path) -> dict[str, Any]:
    with project_file.open("r", encoding="utf-8") as handle:
        meta, _ = _parse_frontmatter(handle.read())
    return meta


def build_report(status_dir: str | os.PathLike[str], *, timestamp: str | None = None) -> dict[str, Any]:
    """Build a read-only report of canonical projects not marked for orchestration."""
    status_path = Path(status_dir).resolve()
    projects_dir = status_path / PROJECTS_DIRNAME
    timestamp = timestamp or _utc_timestamp()
    backup_target = status_path.parent / f"{status_path.name}.backup-before-stage-pipeline-{timestamp}"

    projects: list[dict[str, Any]] = []
    deletion_candidates: list[dict[str, Any]] = []
    read_errors: list[dict[str, str]] = []

    if projects_dir.is_dir():
        entries = sorted(item for item in projects_dir.iterdir() if item.is_dir())
        for project_dir in entries:
            project_file = project_dir / "project.md"
            if not project_file.is_file():
                continue
            try:
                meta = _read_project_meta(project_file)
            except Exception as exc:  # pragma: no cover - defensive report path
                read_errors.append({"path": str(project_file), "error": str(exc)})
                continue
            execution_model = str(meta.get("executionModel") or "")
            project = {
                "id": str(meta.get("id") or ""),
                "title": str(meta.get("title") or ""),
                "projectDir": str(project_dir),
                "projectFile": str(project_file),
                "executionModel": execution_model or None,
                "taskCount": _project_task_count(project_dir),
            }
            projects.append(project)
            if execution_model != REQUIRED_EXECUTION_MODEL:
                deletion_candidates.append({
                    **project,
                    "reason": "missing_required_execution_model" if not execution_model else "unexpected_execution_model",
                    "requiredExecutionModel": REQUIRED_EXECUTION_MODEL,
                })

    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "readOnly": True,
        "statusDir": str(status_path),
        "projectsDir": str(projects_dir),
        "requiredExecutionModel": REQUIRED_EXECUTION_MODEL,
        "backupCandidate": {
            "source": str(status_path),
            "target": str(backup_target),
            "actionRequired": "copy_status_dir_before_destructive_cleanup",
        },
        "summary": {
            "canonicalProjectCount": len(projects),
            "legacyDeletionCandidateCount": len(deletion_candidates),
            "readErrorCount": len(read_errors),
        },
        "projects": projects,
        "legacyDeletionCandidates": deletion_candidates,
        "readErrors": read_errors,
        "destructiveActionsPerformed": [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status-dir",
        default=os.environ.get("VO_STATUS_DIR") or str(ROOT / "data"),
        help="VO status directory containing projects-md/ (default: VO_STATUS_DIR or ./data)",
    )
    parser.add_argument(
        "--timestamp",
        default=None,
        help="Optional stable UTC timestamp for deterministic backup-candidate output.",
    )
    args = parser.parse_args(argv)
    report = build_report(args.status_dir, timestamp=args.timestamp)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
