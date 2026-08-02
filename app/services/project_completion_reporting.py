"""Pure state transitions for project completion-report occurrences."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping


COMPLETION_REPORT_SCHEMA_VERSION = 1
MAX_AUTOMATIC_ATTEMPTS = 3
MAX_ATTEMPT_HISTORY = 20
RETRY_DELAYS_SECONDS = (30, 120)


class CompletionReportStateError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _occurrence(project: Mapping[str, Any], occurrence_id: str) -> dict[str, Any]:
    orchestration = project.get("orchestration") if isinstance(project.get("orchestration"), Mapping) else {}
    for item in orchestration.get("completionReports") or []:
        if isinstance(item, dict) and item.get("occurrenceId") == occurrence_id:
            return item
    raise CompletionReportStateError(
        "completion_report_not_found", "Completion report occurrence was not found"
    )


def _owned(occurrence: dict[str, Any], token: str) -> None:
    claim = occurrence.get("claim") if isinstance(occurrence.get("claim"), Mapping) else {}
    if not token or claim.get("token") != token:
        raise CompletionReportStateError(
            "completion_report_claim_lost", "Completion report claim is no longer owned"
        )


def _attempt(occurrence: dict[str, Any], token: str) -> dict[str, Any] | None:
    for item in reversed(occurrence.get("attempts") or []):
        if isinstance(item, dict) and item.get("claimToken") == token:
            return item
    return None


def _append_attempt(occurrence: dict[str, Any], attempt: dict[str, Any]) -> None:
    attempts = occurrence.get("attempts")
    if not isinstance(attempts, list):
        attempts = []
        occurrence["attempts"] = attempts
    attempts.append(attempt)
    del attempts[:-MAX_ATTEMPT_HISTORY]


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


def claim_due_completion_report(
    project: dict[str, Any],
    *,
    occurrence_id: str,
    now: str,
    token: str,
    claim_ttl_seconds: int = 60,
) -> dict[str, Any]:
    occurrence = _occurrence(project, occurrence_id)
    current_time = _parse_time(now)
    if current_time is None:
        raise CompletionReportStateError("completion_report_invalid_time", "A valid claim time is required")
    current_claim = occurrence.get("claim") if isinstance(occurrence.get("claim"), Mapping) else {}
    expires_at = _parse_time(current_claim.get("expiresAt"))
    if current_claim and expires_at and expires_at > current_time:
        return {"claimed": False, "status": "in_progress", "occurrence": None}
    if current_claim and occurrence.get("state") == "delivering":
        occurrence.update({
            "state": "failed",
            "visibleStatus": "failed",
            "claim": None,
            "nextAttemptAt": None,
            "lastError": {
                "code": "delivery_outcome_unknown",
                "message": "The previous delivery result is unknown",
                "at": now,
            },
        })
        return {"claimed": False, "status": "delivery_outcome_unknown", "occurrence": None}
    if occurrence.get("state") in {"delivered", "failed"}:
        return {"claimed": False, "status": str(occurrence.get("state")), "occurrence": None}
    due = _parse_time(occurrence.get("nextAttemptAt"))
    if due and due > current_time:
        return {"claimed": False, "status": "not_due", "occurrence": None}
    attempts = int(occurrence.get("attemptCount") or 0)
    if attempts >= MAX_AUTOMATIC_ATTEMPTS:
        occurrence.update({"state": "failed", "visibleStatus": "failed", "nextAttemptAt": None, "claim": None})
        return {"claimed": False, "status": "attempts_exhausted", "occurrence": None}
    mode = str(occurrence.pop("nextAttemptMode", "automatic") or "automatic")
    resume_delivery = bool(
        occurrence.get("reportMarkdownPath")
        and isinstance(occurrence.get("generatedReport"), Mapping)
    )
    occurrence.update({
        "state": "ready" if resume_delivery else "generating",
        "visibleStatus": "pending",
        "attemptCount": attempts + 1,
        "nextAttemptAt": None,
        "claim": {
            "token": token,
            "claimedAt": now,
            "expiresAt": _iso(current_time + timedelta(seconds=max(1, claim_ttl_seconds))),
        },
    })
    _append_attempt(occurrence, {
        "attempt": attempts + 1,
        "mode": mode,
        "phase": "delivery" if resume_delivery else "generation",
        "status": "processing",
        "startedAt": now,
        "claimToken": token,
    })
    return {
        "claimed": True,
        "status": "ready" if resume_delivery else "generating",
        "resumeDelivery": resume_delivery,
        "occurrence": occurrence,
    }


def finish_completion_report_generation(
    project: dict[str, Any],
    *,
    occurrence_id: str,
    token: str,
    now: str,
    reporting_agent_id: str,
    markdown_path: str,
    digest: str,
    report: Mapping[str, Any],
) -> dict[str, Any]:
    occurrence = _occurrence(project, occurrence_id)
    _owned(occurrence, token)
    occurrence.update({
        "state": "ready",
        "visibleStatus": "pending",
        "reportingAgentId": reporting_agent_id,
        "reportMarkdownPath": markdown_path,
        "reportDigest": digest,
        "generatedReport": dict(report),
        "generatedAt": now,
    })
    attempt = _attempt(occurrence, token)
    if attempt:
        attempt.update({"phase": "generation", "status": "generated", "generatedAt": now})
    return occurrence


def begin_completion_report_delivery(
    project: dict[str, Any], *, occurrence_id: str, token: str, now: str
) -> dict[str, Any]:
    occurrence = _occurrence(project, occurrence_id)
    _owned(occurrence, token)
    occurrence.update({"state": "delivering", "visibleStatus": "pending", "deliveryStartedAt": now})
    attempt = _attempt(occurrence, token)
    if attempt:
        attempt.update({"phase": "delivery", "status": "processing", "deliveryStartedAt": now})
    return occurrence


def finish_completion_report_delivery(
    project: dict[str, Any],
    *,
    occurrence_id: str,
    token: str,
    now: str,
    message_id: str,
) -> dict[str, Any]:
    occurrence = _occurrence(project, occurrence_id)
    _owned(occurrence, token)
    occurrence.update({
        "state": "delivered",
        "visibleStatus": "delivered",
        "deliveredAt": now,
        "messageId": message_id,
        "lastError": None,
        "nextAttemptAt": None,
        "claim": None,
    })
    attempt = _attempt(occurrence, token)
    if attempt:
        attempt.update({"phase": "delivery", "status": "delivered", "completedAt": now})
        attempt.pop("claimToken", None)
    return occurrence


def fail_completion_report_attempt(
    project: dict[str, Any],
    *,
    occurrence_id: str,
    token: str,
    now: str,
    code: str,
    error: str,
    recoverable: bool,
    outcome_unknown: bool = False,
) -> dict[str, Any]:
    occurrence = _occurrence(project, occurrence_id)
    _owned(occurrence, token)
    attempts = int(occurrence.get("attemptCount") or 0)
    terminal = outcome_unknown or not recoverable or attempts >= MAX_AUTOMATIC_ATTEMPTS
    next_attempt_at = None
    if not terminal:
        current_time = _parse_time(now)
        if current_time is None:
            raise CompletionReportStateError("completion_report_invalid_time", "A valid failure time is required")
        delay = RETRY_DELAYS_SECONDS[min(attempts - 1, len(RETRY_DELAYS_SECONDS) - 1)]
        next_attempt_at = _iso(current_time + timedelta(seconds=delay))
    occurrence.update({
        "state": "failed" if terminal else "retry",
        "visibleStatus": "failed" if terminal else "pending",
        "nextAttemptAt": next_attempt_at,
        "lastError": {"code": code, "message": str(error)[:1000], "at": now},
        "claim": None,
    })
    attempt = _attempt(occurrence, token)
    if attempt:
        attempt.update({"status": "failed", "completedAt": now, "errorCode": code})
        attempt.pop("claimToken", None)
    return occurrence


def request_manual_resend(
    project: dict[str, Any],
    *,
    occurrence_id: str,
    now: str,
    owner_authorized: bool,
) -> dict[str, Any]:
    if not owner_authorized:
        raise CompletionReportStateError(
            "completion_report_resend_forbidden", "Only the project owner can resend a report"
        )
    occurrence = _occurrence(project, occurrence_id)
    if occurrence.get("state") != "failed":
        raise CompletionReportStateError(
            "completion_report_not_failed", "Only a failed completion report can be resent"
        )
    occurrence.update({
        "state": "pending",
        "visibleStatus": "pending",
        "attemptCount": 0,
        "nextAttemptAt": None,
        "lastError": None,
        "claim": None,
        "nextAttemptMode": "manual",
    })
    _append_attempt(occurrence, {
        "mode": "manual_resend_requested",
        "status": "pending",
        "requestedAt": now,
    })
    return occurrence
