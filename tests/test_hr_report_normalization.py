"""Strict HR-owned normalization of immutable Agent daily-report claims."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_reporting import HRDailyReportNormalizer, HRReportingService
from services.hr_repository import HRRepository


NOW = datetime(2026, 7, 19, 2, tzinfo=timezone.utc)


class FakeHR:
    def __init__(self, outputs=None):
        self.outputs = dict(outputs or {})
        self.calls = []

    def ask_hr(self, prompt, conversation_key, timeout_seconds):
        self.calls.append((prompt, conversation_key, timeout_seconds))
        ai_id = conversation_key.rsplit(":", 1)[-1]
        output = self.outputs.get(ai_id)
        if isinstance(output, Exception):
            raise output
        return output


def normalized_payload(ai_id, *, extra=None):
    result = {
        "schemaVersion": 1,
        "localDate": "2026-07-19",
        "agentAiId": ai_id,
        "completedWork": ["完成日报结构设计"],
        "relatedProjectsOrTasks": [
            {"type": "task", "id": "task-1", "title": "日报归一化"}
        ],
        "artifacts": [{"id": "artifact-1", "name": "方案", "type": "document"}],
        "blockers": ["等待接口确认"],
        "requestedHelp": ["请 HR 协调接口评审"],
        "submission": {
            "state": "submitted",
            "requestedAt": "2026-07-19T02:00:00+00:00",
            "submittedAt": "2026-07-19T02:00:00+00:00",
        },
    }
    if extra:
        result.update(extra)
    return result


@pytest.fixture
def repository(tmp_path):
    result = HRRepository(tmp_path / "status", clock=lambda: NOW)
    result.initialize()
    for ai_id in ("hr", "agent-1", "agent-2"):
        result.upsert_agent(
            ai_id=ai_id,
            name=ai_id,
            agent_kind="system" if ai_id == "hr" else "project",
            status="active",
            availability="available",
            source="test",
        )
    reporting = HRReportingService(
        result,
        clock=lambda: NOW,
        claim_token_factory=lambda request_id: f"claim:{request_id}",
    )
    opened = reporting.open_cycle(
        local_date="2026-07-19",
        timezone_name="Asia/Shanghai",
        scheduled_at=NOW,
        window_opens_at=NOW,
        window_closes_at=datetime(2026, 7, 19, 10, tzinfo=timezone.utc),
        eligible_ai_ids=("agent-1", "agent-2"),
    )
    for ai_id in ("agent-1", "agent-2"):
        report = result.get_daily_report(ai_id, "2026-07-19")
        result.save_daily_report(
            report_id=report.id,
            cycle_id=opened.cycle.id,
            ai_id=ai_id,
            local_date="2026-07-19",
            submission_state="submitted",
            raw_response=f"{ai_id} 原始日报",
            normalized=None,
            requested_at=NOW.isoformat(),
            submitted_at=NOW.isoformat(),
            expected_revision=report.revision,
        )
    return result


def normalizer(repository, hr):
    return HRDailyReportNormalizer(
        repository,
        hr,
        clock=lambda: NOW,
        timeout_seconds=15,
    )


def test_hr_normalization_persists_strict_structure_and_identity(repository):
    hr = FakeHR({"agent-1": json.dumps(normalized_payload("agent-1"))})
    result = normalizer(repository, hr).normalize(
        ("agent-1",), local_date="2026-07-19"
    )
    assert result[0].status == "normalized"
    stored = repository.get_daily_report("agent-1", "2026-07-19")
    assert stored.submission_state == "normalized"
    assert stored.raw_response == "agent-1 原始日报"
    assert stored.normalizer_id == "hr"
    assert stored.normalized["completedWork"] == ["完成日报结构设计"]
    assert stored.normalized["relatedProjectsOrTasks"][0]["id"] == "task-1"
    assert stored.normalized_at == NOW.isoformat()
    assert hr.calls[0][1:] == ("hr:daily-report-normalize:2026-07-19:agent-1", 15.0)
    assert "agent-1 原始日报" in hr.calls[0][0]


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value.update({"unsupported": "field"}),
        lambda value: value.update({"schemaVersion": True}),
        lambda value: value.update({"agentAiId": "agent-2"}),
        lambda value: value.update({"completedWork": [""]}),
        lambda value: value.update(
            {"relatedProjectsOrTasks": [{"type": "task", "id": "task-1"}]}
        ),
        lambda value: value["submission"].update({"state": "late_submitted"}),
    ),
)
def test_invalid_structure_retains_raw_and_marks_retryable_failure(repository, mutate):
    payload = normalized_payload("agent-1")
    mutate(payload)
    result = normalizer(repository, FakeHR({"agent-1": json.dumps(payload)})).normalize(
        ("agent-1",), local_date="2026-07-19"
    )
    assert result[0].status == "failed"
    stored = repository.get_daily_report("agent-1", "2026-07-19")
    assert stored.submission_state == "normalization_failed"
    assert stored.raw_response == "agent-1 原始日报"
    assert stored.normalized is None
    assert stored.normalizer_id == ""


def test_oversized_or_non_json_output_is_rejected_without_raw_loss(repository):
    first = normalizer(repository, FakeHR({"agent-1": "x" * 40_001})).normalize(
        ("agent-1",), local_date="2026-07-19"
    )
    assert first[0].status == "failed"
    retry = normalizer(repository, FakeHR({"agent-1": "not-json"})).normalize(
        ("agent-1",), local_date="2026-07-19"
    )
    assert retry[0].status == "failed"
    assert repository.get_daily_report("agent-1", "2026-07-19").raw_response == (
        "agent-1 原始日报"
    )


def test_one_hr_failure_does_not_block_other_agent(repository):
    hr = FakeHR(
        {
            "agent-1": RuntimeError("provider envelope secret"),
            "agent-2": json.dumps(normalized_payload("agent-2")),
        }
    )
    results = normalizer(repository, hr).normalize(
        ("agent-1", "agent-2"), local_date="2026-07-19"
    )
    assert [item.status for item in results] == ["failed", "normalized"]
    assert repository.get_daily_report("agent-1", "2026-07-19").normalized is None
    assert repository.get_daily_report("agent-2", "2026-07-19").normalized is not None
    assert "secret" not in results[0].error_code


def test_missing_raw_is_neutral_and_does_not_call_hr(repository):
    report = repository.get_daily_report("agent-1", "2026-07-19")
    # A third eligible Agent is unnecessary: this verifies lookup absence is neutral.
    hr = FakeHR()
    result = normalizer(repository, hr).normalize(
        ("unknown-agent",), local_date="2026-07-19"
    )
    assert report.raw_response is not None
    assert result[0].status == "no_raw_report"
    assert hr.calls == []


def test_success_is_idempotent_and_does_not_ask_hr_twice(repository):
    hr = FakeHR({"agent-1": json.dumps(normalized_payload("agent-1"))})
    service = normalizer(repository, hr)
    service.normalize(("agent-1",), local_date="2026-07-19")
    second = service.normalize(("agent-1",), local_date="2026-07-19")
    assert second[0].status == "already_normalized"
    assert len(hr.calls) == 1


def test_normalization_retry_keeps_original_submission_metadata(repository):
    failed = normalizer(repository, FakeHR({"agent-1": "bad-json"})).normalize(
        ("agent-1",), local_date="2026-07-19"
    )
    assert failed[0].status == "failed"
    hr = FakeHR({"agent-1": json.dumps(normalized_payload("agent-1"))})
    retried = normalizer(repository, hr).normalize(
        ("agent-1",), local_date="2026-07-19"
    )
    assert retried[0].status == "normalized"
    stored = repository.get_daily_report("agent-1", "2026-07-19")
    assert stored.normalized["submission"]["state"] == "submitted"
    assert '"state": "submitted"' in hr.calls[0][0]
