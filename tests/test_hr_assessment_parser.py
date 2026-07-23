"""Strict, non-ranking HR assessment schema validation."""

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_assessments import (
    HRAssessmentParser,
    HRAssessmentPolicy,
    HRAssessmentValidationError,
)


def payload(**overrides):
    result = {
        "schemaVersion": 1,
        "agentAiId": "agent-1",
        "localDate": "2026-07-19",
        "principalContributions": ["完成日报调度器并补齐并发测试"],
        "workload": "appropriate",
        "workloadScore": 6,
        "rationale": "实现和测试均有可追踪证据，工作量与当日目标匹配。",
        "evidenceReferences": [
            {
                "evidenceType": "task_transition",
                "referenceId": "task-1:event-2",
                "rationale": "任务在当天从执行进入完成。",
            }
        ],
        "blockers": ["开发机缺少真实 OpenClaw"],
        "strengths": ["并发边界测试完整"],
        "improvements": ["补充真实环境验收"],
        "runtimeDiagnosis": "Agent 可用；外部 Provider 环境尚未就绪。",
        "informationSufficiency": {
            "status": "sufficient",
            "explanation": "日报与任务状态能够互相印证。",
        },
        "hrAiId": "hr",
        "assessedAt": "2026-07-19T18:10:00+08:00",
    }
    result.update(overrides)
    return result


def parse(value):
    return HRAssessmentParser().parse(
        json.dumps(value, ensure_ascii=False),
        expected_ai_id="agent-1",
        expected_local_date="2026-07-19",
    )


def test_parses_complete_evidence_backed_assessment():
    result = parse(payload())
    assert result.agent_ai_id == "agent-1"
    assert result.local_date == "2026-07-19"
    assert result.workload == "appropriate"
    assert result.workload_score == 6
    assert result.principal_contributions == ("完成日报调度器并补齐并发测试",)
    assert result.evidence_references[0].reference_id == "task-1:event-2"
    assert result.blockers == ("开发机缺少真实 OpenClaw",)
    assert result.strengths == ("并发边界测试完整",)
    assert result.improvements == ("补充真实环境验收",)
    assert result.information_sufficiency_status == "sufficient"
    assert result.hr_ai_id == "hr"
    assert result.assessed_at == "2026-07-19T10:10:00+00:00"


@pytest.mark.parametrize("workload", ("low", "appropriate", "high", "overloaded"))
def test_all_supported_conclusive_workload_values(workload):
    assert parse(payload(workload=workload)).workload == workload


def test_insufficient_information_requires_explanation_without_invented_contribution():
    result = parse(
        payload(
            workload="insufficient_information",
            principalContributions=[],
            evidenceReferences=[],
            informationSufficiency={
                "status": "insufficient",
                "explanation": "缺少日报和可归属的任务结果，不能推断工作量。",
            },
        )
    )
    assert result.workload == "insufficient_information"
    assert result.principal_contributions == ()
    assert result.evidence_references == ()
    assert "不能推断" in result.information_sufficiency


@pytest.mark.parametrize("forbidden", ("score", "numericScore", "rank", "leaderboard"))
def test_unsupported_score_alias_and_rank_fields_are_rejected(forbidden):
    value = payload()
    value[forbidden] = 100
    with pytest.raises(HRAssessmentValidationError, match="unsupported fields"):
        parse(value)


@pytest.mark.parametrize(
    "overrides, message",
    (
        ({"workload": "medium"}, "workload"),
        ({"agentAiId": "agent-2"}, "Agent"),
        ({"localDate": "2026-07-18"}, "date"),
        ({"hrAiId": "agent-1"}, "HR identity"),
        ({"assessedAt": "2026-07-19T18:10:00"}, "timezone"),
        ({"schemaVersion": 2}, "schema"),
        ({"schemaVersion": True}, "schema"),
        ({"workload": ["low"]}, "workload"),
        ({"workloadScore": 0}, "workload score"),
        ({"workloadScore": 11}, "workload score"),
        ({"workloadScore": True}, "workload score"),
    ),
)
def test_identity_schema_workload_and_timestamp_are_enforced(overrides, message):
    with pytest.raises(HRAssessmentValidationError, match=message):
        parse(payload(**overrides))


@pytest.mark.parametrize(
    "workload, sufficiency",
    (
        ("low", {"status": "insufficient", "explanation": "missing"}),
        (
            "insufficient_information",
            {"status": "sufficient", "explanation": "enough"},
        ),
    ),
)
def test_workload_and_information_sufficiency_must_agree(workload, sufficiency):
    with pytest.raises(HRAssessmentValidationError, match="conflict"):
        parse(payload(workload=workload, informationSufficiency=sufficiency))


def test_sufficient_assessment_requires_contribution_and_evidence():
    with pytest.raises(HRAssessmentValidationError, match="requires"):
        parse(payload(principalContributions=[]))
    with pytest.raises(HRAssessmentValidationError, match="requires"):
        parse(payload(evidenceReferences=[]))


def test_duplicate_or_malformed_evidence_references_are_rejected():
    reference = payload()["evidenceReferences"][0]
    with pytest.raises(HRAssessmentValidationError, match="duplicates"):
        parse(payload(evidenceReferences=[reference, reference]))
    malformed = dict(reference)
    malformed["score"] = 1
    with pytest.raises(HRAssessmentValidationError, match="invalid item"):
        parse(payload(evidenceReferences=[malformed]))


def test_oversized_invalid_json_and_duplicate_list_items_are_rejected():
    parser = HRAssessmentParser()
    with pytest.raises(HRAssessmentValidationError, match="too large"):
        parser.parse(
            "x" * 50_001,
            expected_ai_id="agent-1",
            expected_local_date="2026-07-19",
        )
    with pytest.raises(HRAssessmentValidationError, match="invalid JSON"):
        parser.parse(
            "not-json",
            expected_ai_id="agent-1",
            expected_local_date="2026-07-19",
        )
    with pytest.raises(HRAssessmentValidationError, match="duplicates"):
        parse(payload(strengths=["same", "same"]))


def test_assessment_module_has_no_server_or_mutating_domain_dependency():
    source = (APP_DIR / "services" / "hr_assessments.py").read_text(encoding="utf-8")
    assert "import server" not in source
    assert "OfficeHandler" not in source
    assert "pause_agent" not in source
    assert "delete_agent" not in source


@pytest.mark.parametrize(
    "field, text",
    (
        ("rationale", "This Agent should be deleted."),
        ("improvements", ["Pause the Agent until further review."]),
        ("strengths", ["Performance score: 95"]),
        ("blockers", ["建议将该 Agent 淘汰"]),
        ("runtimeDiagnosis", "Agent 排名较低"),
    ),
)
def test_non_punitive_policy_rejects_actions_scores_and_ranks(field, text):
    parsed = parse(payload(**{field: text}))
    with pytest.raises(HRAssessmentValidationError, match="punitive"):
        HRAssessmentPolicy.validate(parsed)


def test_non_punitive_policy_allows_actionable_growth_feedback():
    parsed = parse(
        payload(
            improvements=["为并发测试补充真实环境覆盖"],
            principalContributions=["删除了产物目录中的过期临时文件"],
        )
    )
    assert HRAssessmentPolicy.validate(parsed) is parsed
