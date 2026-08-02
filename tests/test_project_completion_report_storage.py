#!/usr/bin/env python3
"""Safe storage contracts for versioned Feishu completion reports."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.project_completion_report_storage import (
    CompletionReportStorageError,
    write_completion_report,
)


def test_write_completion_report_creates_versioned_sidecar_and_metadata(tmp_path):
    project = {"workspacePath": str(tmp_path)}
    occurrence = {"occurrenceId": "stage-run:run-1", "version": 1}
    markdown = "# Report\n\nDone.\n"

    result = write_completion_report(project, occurrence, markdown)

    assert result == {
        "markdownPath": ".vo/project-completion-reports/v1-stage-run-run-1/FEISHU_COMPLETION_REPORT.md",
        "digest": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "created": True,
    }
    assert (tmp_path / result["markdownPath"]).read_text(encoding="utf-8") == markdown
    assert occurrence["reportMarkdownPath"] == result["markdownPath"]
    assert occurrence["reportDigest"] == result["digest"]


def test_write_completion_report_is_idempotent_but_does_not_overwrite_a_version(tmp_path):
    project = {"workspacePath": str(tmp_path)}
    occurrence = {"occurrenceId": "stage-run:run-1", "version": 1}

    first = write_completion_report(project, occurrence, "stable")
    repeated = write_completion_report(project, occurrence, "stable")

    assert first["created"] is True
    assert repeated["created"] is False
    with pytest.raises(CompletionReportStorageError, match="already exists with different content"):
        write_completion_report(project, occurrence, "replacement")
    assert (tmp_path / first["markdownPath"]).read_text(encoding="utf-8") == "stable"


def test_write_completion_report_keeps_hostile_occurrence_id_inside_workspace(tmp_path):
    project = {"workspacePath": str(tmp_path)}
    occurrence = {"occurrenceId": "../../outside", "version": 2}

    result = write_completion_report(project, occurrence, "safe")

    destination = (tmp_path / result["markdownPath"]).resolve()
    assert destination.is_relative_to(tmp_path.resolve())
    assert ".." not in result["markdownPath"]


def test_write_completion_report_requires_workspace_and_valid_version(tmp_path):
    with pytest.raises(CompletionReportStorageError, match="workspacePath is required"):
        write_completion_report({}, {"occurrenceId": "run", "version": 1}, "report")
    with pytest.raises(CompletionReportStorageError, match="version must be a positive integer"):
        write_completion_report(
            {"workspacePath": str(tmp_path)},
            {"occurrenceId": "run", "version": 0},
            "report",
        )
