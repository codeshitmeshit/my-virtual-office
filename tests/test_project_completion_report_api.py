#!/usr/bin/env python3
"""Query and manual-resend contracts for project completion reports."""

from __future__ import annotations

import copy
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.project_completion_report_api import completion_report_summaries, resend_completion_report
from services.project_repository import ProjectRepository


class _Store:
    def __init__(self, projects):
        self.data = {"projects": copy.deepcopy(projects), "templates": []}

    def load(self):
        return copy.deepcopy(self.data)

    def save(self, data):
        self.data = copy.deepcopy(data)


def _repository(projects):
    store = _Store(projects)
    return ProjectRepository(load_projects=store.load, save_projects=store.save), store


def _occurrence(occurrence_id, version, state, **values):
    return {
        "occurrenceId": occurrence_id,
        "version": version,
        "runId": f"r{version}",
        "state": state,
        "visibleStatus": "delivered" if state == "delivered" else ("failed" if state == "failed" else "pending"),
        "completedAt": f"2026-08-0{version}T00:00:00+00:00",
        "attemptCount": values.pop("attemptCount", 1),
        "claim": {"token": "private-token"},
        "attempts": [{"claimToken": "private-token"}],
        "generatedReport": {"secret": "internal"},
        **values,
    }


def test_query_returns_newest_first_sanitized_visible_states():
    project = {
        "orchestration": {"completionReports": [
            _occurrence("o1", 1, "delivered", deliveredAt="2026-08-01T01:00:00+00:00", reportMarkdownPath="v1.md"),
            _occurrence("o2", 2, "retry", nextAttemptAt="2026-08-02T01:00:00+00:00"),
            _occurrence("o3", 3, "failed", lastError={
                "code": "send_failed",
                "message": "api_key=super-secret delivery failed",
                "at": "2026-08-03T01:00:00+00:00",
            }),
        ]},
    }

    result = completion_report_summaries(project)

    assert [item["version"] for item in result] == [3, 2, 1]
    assert [item["status"] for item in result] == ["failed", "pending", "delivered"]
    assert result[0]["canResend"] is True
    assert "super-secret" not in result[0]["lastError"]["message"]
    assert result[1]["canResend"] is False
    assert result[2]["deliveredAt"] == "2026-08-01T01:00:00+00:00"
    forbidden = {"claim", "attempts", "generatedReport", "reportingAgentId", "reportDigest", "messageId"}
    assert forbidden.isdisjoint(result[0])


def test_resend_rejects_owner_violation_overrides_missing_and_processing_occurrences():
    project = {"id": "p1", "orchestration": {"completionReports": [_occurrence("o1", 1, "generating")]}}
    repository, _store = _repository([project])

    forbidden = resend_completion_report(
        "p1", "o1", {}, repository=repository, now=lambda: "2026-08-03T00:00:00+00:00",
        owner_authorized=False, wake=lambda: None,
    )
    override = resend_completion_report(
        "p1", "o1", {"recipient": "someone-else"}, repository=repository,
        now=lambda: "2026-08-03T00:00:00+00:00", owner_authorized=True, wake=lambda: None,
    )
    processing = resend_completion_report(
        "p1", "o1", {}, repository=repository, now=lambda: "2026-08-03T00:00:00+00:00",
        owner_authorized=True, wake=lambda: None,
    )
    missing_occurrence = resend_completion_report(
        "p1", "missing", {}, repository=repository, now=lambda: "2026-08-03T00:00:00+00:00",
        owner_authorized=True, wake=lambda: None,
    )
    missing_project = resend_completion_report(
        "missing", "o1", {}, repository=repository, now=lambda: "2026-08-03T00:00:00+00:00",
        owner_authorized=True, wake=lambda: None,
    )

    assert (forbidden.status, forbidden.payload["code"]) == (403, "completion_report_resend_forbidden")
    assert (override.status, override.payload["code"]) == (400, "completion_report_resend_overrides_forbidden")
    assert (processing.status, processing.payload["code"]) == (409, "completion_report_not_failed")
    assert (missing_occurrence.status, missing_occurrence.payload["code"]) == (404, "completion_report_not_found")
    assert (missing_project.status, missing_project.payload["code"]) == (404, "project_not_found")


def test_failed_occurrence_is_reset_in_place_and_wakes_worker_once():
    project = {"id": "p1", "orchestration": {"completionReports": [
        _occurrence("o1", 4, "failed", attemptCount=3, lastError={"code": "failed", "message": "no"})
    ]}}
    repository, store = _repository([project])
    wakes = []

    result = resend_completion_report(
        "p1", "o1", {}, repository=repository, now=lambda: "2026-08-03T00:00:00+00:00",
        owner_authorized=True, wake=lambda: wakes.append(True),
    )

    saved = store.data["projects"][0]["orchestration"]["completionReports"][0]
    assert result.status == 200
    assert result.payload["report"]["version"] == 4
    assert result.payload["report"]["status"] == "pending"
    assert saved["occurrenceId"] == "o1"
    assert saved["attemptCount"] == 0
    assert saved["nextAttemptMode"] == "manual"
    assert wakes == [True]
