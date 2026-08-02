"""Pure state transitions for project completion-report occurrences."""

from __future__ import annotations

from typing import Any, Mapping


COMPLETION_REPORT_SCHEMA_VERSION = 1


def stage_completion_report_occurrence(
    project: dict[str, Any],
    *,
    run_id: str | None,
    completed_at: str,
) -> dict[str, Any]:
    """Stage one idempotent pending report for a successful final-stage run."""

    clean_run_id = str(run_id or "").strip()
    if not clean_run_id:
        raise ValueError("run_id is required")

    orchestration = project.setdefault("orchestration", {})
    if not isinstance(orchestration, dict):
        orchestration = {}
        project["orchestration"] = orchestration
    orchestration["completedAt"] = orchestration.get("completedAt") or completed_at
    reports = orchestration.get("completionReports")
    if not isinstance(reports, list):
        reports = []
        orchestration["completionReports"] = reports

    occurrence_id = f"stage-run:{clean_run_id}"
    for item in reports:
        if isinstance(item, Mapping) and item.get("occurrenceId") == occurrence_id:
            return {"created": False, "status": "existing", "occurrence": item}

    if project.get("feishuCompletionReportEnabled", True) is False:
        return {"created": False, "status": "skipped_disabled", "occurrence": None}

    versions = [
        int(item.get("version") or 0)
        for item in reports
        if isinstance(item, Mapping)
        and isinstance(item.get("version"), int)
        and not isinstance(item.get("version"), bool)
    ]
    occurrence = {
        "schemaVersion": COMPLETION_REPORT_SCHEMA_VERSION,
        "occurrenceId": occurrence_id,
        "version": max(versions, default=0) + 1,
        "runId": clean_run_id,
        "completedAt": completed_at,
        "state": "pending",
        "visibleStatus": "pending",
        "reportingAgentId": "",
        "reportMarkdownPath": "",
        "reportDigest": "",
        "attemptCount": 0,
        "nextAttemptAt": None,
        "lastError": None,
        "messageId": None,
        "claim": None,
        "attempts": [],
    }
    reports.append(occurrence)
    return {"created": True, "status": "pending", "occurrence": occurrence}
