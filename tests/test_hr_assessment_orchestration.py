"""HR-only post-window assessment orchestration and sufficiency guards."""

import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_assessments import (
    HRAssessmentOrchestrator,
    HRAssessmentValidationError,
)
from services.hr_evidence import EvidenceCandidate, HREvidenceCollector, HREvidencePorts
from services.hr_reporting import HRReportingService
from services.hr_repository import HRRepository


NOW = datetime(2026, 7, 19, 10, tzinfo=timezone.utc)
LOCAL_DATE = "2026-07-19"


class FakeEvidencePort:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def _items(self, source, ai_id):
        return self.values.get((source, ai_id), ())

    def read_project_transitions(self, ai_id, _date):
        return self._items("projects", ai_id)

    def read_task_transitions(self, ai_id, _date):
        return self._items("tasks", ai_id)

    def read_meeting_contributions(self, ai_id, _date):
        return self._items("meetings", ai_id)

    def read_artifact_metadata(self, ai_id, _date):
        return self._items("artifacts", ai_id)

    def read_execution_results(self, ai_id, _date):
        return self._items("executions", ai_id)

    def read_blockers_and_waiting(self, ai_id, _date):
        return self._items("runtime", ai_id)


class FakeHR:
    def __init__(self, outputs):
        self.outputs = dict(outputs)
        self.calls = []

    def ask_hr(self, prompt, conversation_key, timeout_seconds):
        self.calls.append((prompt, conversation_key, timeout_seconds))
        ai_id = conversation_key.rsplit(":", 1)[-1]
        value = self.outputs[ai_id]
        if isinstance(value, Exception):
            raise value
        return value


def assessment(ai_id, *, sufficient=True, evidence=()):
    return json.dumps(
        {
            "schemaVersion": 1,
            "agentAiId": ai_id,
            "localDate": LOCAL_DATE,
            "principalContributions": ["完成任务"] if sufficient else [],
            "workload": "appropriate" if sufficient else "insufficient_information",
            "rationale": (
                "日报与任务记录互相印证。"
                if sufficient
                else "缺少足够的独立证据，不能推断工作量。"
            ),
            "evidenceReferences": list(evidence),
            "blockers": [],
            "strengths": ["交付清晰"] if sufficient else [],
            "improvements": ["继续补充可追踪产物"],
            "runtimeDiagnosis": "可用" if sufficient else "信息不足，运行态未知",
            "informationSufficiency": {
                "status": "sufficient" if sufficient else "insufficient",
                "explanation": "证据充分" if sufficient else "缺少日报或独立工作记录",
            },
            "hrAiId": "hr",
            "assessedAt": NOW.isoformat(),
        },
        ensure_ascii=False,
    )


@pytest.fixture
def setup(tmp_path):
    repository = HRRepository(tmp_path / "status", clock=lambda: NOW)
    repository.initialize()
    for ai_id in ("hr", "agent-1", "agent-2"):
        repository.upsert_agent(
            ai_id=ai_id,
            name=ai_id,
            agent_kind="system" if ai_id == "hr" else "project",
            status="active",
            availability="available",
            source="test",
        )
    reporting = HRReportingService(
        repository,
        clock=lambda: NOW,
        claim_token_factory=lambda request_id: f"claim:{request_id}",
    )
    opened = reporting.open_cycle(
        local_date=LOCAL_DATE,
        timezone_name="Asia/Shanghai",
        scheduled_at=datetime(2026, 7, 19, 9, tzinfo=timezone.utc),
        window_opens_at=datetime(2026, 7, 19, 9, tzinfo=timezone.utc),
        window_closes_at=NOW,
        eligible_ai_ids=("agent-1", "agent-2"),
    )
    reporting.submit_response(
        ai_id="agent-1",
        local_date=LOCAL_DATE,
        raw_response="完成任务 task-1",
        submitted_at=datetime(2026, 7, 19, 9, 30, tzinfo=timezone.utc),
    )
    return repository, reporting, opened


def collector(values=None):
    fake = FakeEvidencePort(values)
    return HREvidenceCollector(HREvidencePorts(fake, fake, fake, fake, fake, fake))


def task_evidence(ai_id="agent-1"):
    return {
        ("tasks", ai_id): [
            EvidenceCandidate(
                "task_transition",
                "task-1:event-2",
                "任务当天进入完成状态",
                LOCAL_DATE,
                {"taskId": "task-1", "toState": "completed"},
            )
        ]
    }


def reference():
    return {
        "evidenceType": "task_transition",
        "referenceId": "task-1:event-2",
        "rationale": "支持已完成任务的事实。",
    }


def test_hr_assesses_closed_cycle_from_report_and_independent_evidence(setup):
    repository, reporting, opened = setup
    reporting.close_cycle(opened.cycle.id, closed_at=NOW)
    hr = FakeHR({"agent-1": assessment("agent-1", evidence=(reference(),))})
    result = HRAssessmentOrchestrator(repository, collector(task_evidence()), hr).assess(
        ("agent-1",), local_date=LOCAL_DATE, actor_ai_id="hr"
    )
    assert result[0].status == "complete"
    stored = repository.get_current_assessment("agent-1", LOCAL_DATE)
    assert stored.workload == "appropriate"
    assert stored.hr_id == "hr"
    assert stored.evidence[0].reference_id == "task-1:event-2"
    assert stored.evidence[0].metadata["assessmentRationale"] == "支持已完成任务的事实。"
    assert hr.calls[0][1:] == ("hr:assessment:2026-07-19:agent-1", 45.0)
    assert "完成任务 task-1" in hr.calls[0][0]


def test_only_hr_can_mutate_assessments(setup):
    repository, reporting, opened = setup
    reporting.close_cycle(opened.cycle.id, closed_at=NOW)
    hr = FakeHR({"agent-1": assessment("agent-1", sufficient=False)})
    service = HRAssessmentOrchestrator(repository, collector(), hr)
    with pytest.raises(HRAssessmentValidationError, match="only HR"):
        service.assess(("agent-1",), local_date=LOCAL_DATE, actor_ai_id="agent-1")
    assert repository.get_current_assessment("agent-1", LOCAL_DATE) is None
    assert hr.calls == []


def test_hr_is_never_assessed_as_an_ordinary_agent(setup):
    repository, _reporting, _opened = setup
    hr = FakeHR({})
    result = HRAssessmentOrchestrator(repository, collector(), hr).assess(
        ("hr",), local_date=LOCAL_DATE, actor_ai_id="hr"
    )
    assert result[0].status == "skipped_hr"
    assert hr.calls == []
    assert repository.get_current_assessment("hr", LOCAL_DATE) is None


def test_assessment_cannot_run_before_cycle_closes(setup):
    repository, _reporting, _opened = setup
    hr = FakeHR({"agent-1": assessment("agent-1", evidence=(reference(),))})
    result = HRAssessmentOrchestrator(repository, collector(task_evidence()), hr).assess(
        ("agent-1",), local_date=LOCAL_DATE, actor_ai_id="hr"
    )
    assert result[0].status == "failed"
    assert result[0].error_code == HRAssessmentValidationError.code
    assert hr.calls == []


def test_non_submission_alone_forces_insufficient_information(setup):
    repository, reporting, opened = setup
    reporting.close_cycle(opened.cycle.id, closed_at=NOW)
    hr = FakeHR({"agent-2": assessment("agent-2", sufficient=False)})
    result = HRAssessmentOrchestrator(repository, collector(), hr).assess(
        ("agent-2",), local_date=LOCAL_DATE, actor_ai_id="hr"
    )
    assert result[0].status == "complete"
    stored = repository.get_current_assessment("agent-2", LOCAL_DATE)
    assert stored.workload == "insufficient_information"
    assert stored.principal_contributions == ()
    assert "MUST be insufficient_information" in hr.calls[0][0]


def test_meeting_record_alone_cannot_determine_performance(setup):
    repository, reporting, opened = setup
    reporting.close_cycle(opened.cycle.id, closed_at=NOW)
    meeting = {
        ("meetings", "agent-2"): [
            EvidenceCandidate(
                "meeting_contribution",
                "meeting-1:attendance",
                "参加会议",
                LOCAL_DATE,
                {"meetingId": "meeting-1", "contributionType": "attendance"},
            )
        ]
    }
    hr = FakeHR({"agent-2": assessment("agent-2", sufficient=False)})
    result = HRAssessmentOrchestrator(repository, collector(meeting), hr).assess(
        ("agent-2",), local_date=LOCAL_DATE, actor_ai_id="hr"
    )
    assert result[0].status == "complete"
    assert repository.get_current_assessment("agent-2", LOCAL_DATE).workload == (
        "insufficient_information"
    )


def test_hr_conclusion_is_rejected_when_evidence_is_inadequate(setup):
    repository, reporting, opened = setup
    reporting.close_cycle(opened.cycle.id, closed_at=NOW)
    hr = FakeHR({"agent-2": assessment("agent-2", sufficient=True, evidence=())})
    result = HRAssessmentOrchestrator(repository, collector(), hr).assess(
        ("agent-2",), local_date=LOCAL_DATE, actor_ai_id="hr"
    )
    assert result[0].status == "failed"
    assert repository.get_current_assessment("agent-2", LOCAL_DATE) is None


def test_unknown_evidence_reference_is_rejected(setup):
    repository, reporting, opened = setup
    reporting.close_cycle(opened.cycle.id, closed_at=NOW)
    unknown = dict(reference(), referenceId="task-unknown")
    hr = FakeHR({"agent-1": assessment("agent-1", evidence=(unknown,))})
    result = HRAssessmentOrchestrator(repository, collector(task_evidence()), hr).assess(
        ("agent-1",), local_date=LOCAL_DATE, actor_ai_id="hr"
    )
    assert result[0].status == "failed"
    assert repository.get_current_assessment("agent-1", LOCAL_DATE) is None


def test_one_agent_hr_failure_does_not_block_another(setup):
    repository, reporting, opened = setup
    reporting.close_cycle(opened.cycle.id, closed_at=NOW)
    hr = FakeHR(
        {
            "agent-1": RuntimeError("provider secret"),
            "agent-2": assessment("agent-2", sufficient=False),
        }
    )
    results = HRAssessmentOrchestrator(repository, collector(task_evidence()), hr).assess(
        ("agent-1", "agent-2"), local_date=LOCAL_DATE, actor_ai_id="hr"
    )
    assert [item.status for item in results] == ["failed", "complete"]
    assert "secret" not in results[0].error_code
    assert repository.get_current_assessment("agent-2", LOCAL_DATE) is not None


def test_same_evidence_retry_is_idempotent_and_skips_second_hr_call(setup):
    repository, reporting, opened = setup
    reporting.close_cycle(opened.cycle.id, closed_at=NOW)
    hr = FakeHR({"agent-1": assessment("agent-1", evidence=(reference(),))})
    service = HRAssessmentOrchestrator(repository, collector(task_evidence()), hr)
    first = service.assess(("agent-1",), local_date=LOCAL_DATE, actor_ai_id="hr")
    second = service.assess(("agent-1",), local_date=LOCAL_DATE, actor_ai_id="hr")
    assert first[0].status == "complete"
    assert second[0].status == "already_complete"
    assert second[0].assessment == first[0].assessment
    assert len(hr.calls) == 1
    assert len(repository.list_assessments(ai_id="agent-1").items) == 1
    assert repository.get_assessment_job("agent-1", LOCAL_DATE).status == "complete"


def test_failed_job_is_visible_and_retryable_without_provider_error_leak(setup):
    repository, reporting, opened = setup
    reporting.close_cycle(opened.cycle.id, closed_at=NOW)
    failed = HRAssessmentOrchestrator(
        repository,
        collector(task_evidence()),
        FakeHR({"agent-1": RuntimeError("provider secret envelope")}),
    ).assess(("agent-1",), local_date=LOCAL_DATE, actor_ai_id="hr")
    assert failed[0].status == "failed"
    job = repository.get_assessment_job("agent-1", LOCAL_DATE)
    assert job.status == "failed"
    assert job.last_error == "assessment_failed:RuntimeError"
    assert "secret" not in job.last_error
    retried = HRAssessmentOrchestrator(
        repository,
        collector(task_evidence()),
        FakeHR({"agent-1": assessment("agent-1", evidence=(reference(),))}),
    ).assess(("agent-1",), local_date=LOCAL_DATE, actor_ai_id="hr")
    assert retried[0].status == "complete"
    assert repository.get_assessment_job("agent-1", LOCAL_DATE).attempt_count == 2


def test_late_report_creates_new_current_version_with_revision_reason(setup):
    repository, reporting, opened = setup
    reporting.close_cycle(opened.cycle.id, closed_at=NOW)
    first = HRAssessmentOrchestrator(
        repository,
        collector(),
        FakeHR({"agent-2": assessment("agent-2", sufficient=False)}),
    ).assess(("agent-2",), local_date=LOCAL_DATE, actor_ai_id="hr")
    assert first[0].assessment.version == 1
    reporting.submit_response(
        ai_id="agent-2",
        local_date=LOCAL_DATE,
        raw_response="迟交：完成 task-1",
        submitted_at=datetime(2026, 7, 19, 11, tzinfo=timezone.utc),
    )
    second = HRAssessmentOrchestrator(
        repository,
        collector(task_evidence("agent-2")),
        FakeHR({"agent-2": assessment("agent-2", evidence=(reference(),))}),
    ).assess(("agent-2",), local_date=LOCAL_DATE, actor_ai_id="hr")
    assert second[0].status == "complete"
    assert second[0].assessment.version == 2
    assert second[0].assessment.revision_reason == "late_report"
    history = repository.list_assessments(ai_id="agent-2").items
    assert [item.version for item in history] == [2, 1]
    assert [item.is_current for item in history] == [True, False]


def test_changed_evidence_creates_revision_and_retains_evidence_links(setup):
    repository, reporting, opened = setup
    reporting.close_cycle(opened.cycle.id, closed_at=NOW)
    first_service = HRAssessmentOrchestrator(
        repository,
        collector(task_evidence()),
        FakeHR({"agent-1": assessment("agent-1", evidence=(reference(),))}),
    )
    first_service.assess(("agent-1",), local_date=LOCAL_DATE, actor_ai_id="hr")
    changed = task_evidence()
    changed[("artifacts", "agent-1")] = [
        EvidenceCandidate(
            "artifact",
            "artifact-2",
            "新增验收报告",
            LOCAL_DATE,
            {"artifactId": "artifact-2", "artifactType": "document"},
        )
    ]
    second = HRAssessmentOrchestrator(
        repository,
        collector(changed),
        FakeHR({"agent-1": assessment("agent-1", evidence=(reference(),))}),
    ).assess(("agent-1",), local_date=LOCAL_DATE, actor_ai_id="hr")
    assert second[0].assessment.version == 2
    assert second[0].assessment.revision_reason == "evidence_changed"
    assert second[0].assessment.evidence[0].reference_id == "task-1:event-2"
    assert second[0].assessment.evidence_version != (
        repository.list_assessments(ai_id="agent-1").items[1].evidence_version
    )


def test_concurrent_evaluation_has_one_claim_one_hr_call_and_one_version(setup):
    repository, reporting, opened = setup
    reporting.close_cycle(opened.cycle.id, closed_at=NOW)
    entered = threading.Event()
    release = threading.Event()

    class BlockingHR(FakeHR):
        def ask_hr(self, *args):
            self.calls.append(args)
            entered.set()
            assert release.wait(timeout=5)
            return assessment("agent-1", evidence=(reference(),))

    hr = BlockingHR({})
    first_service = HRAssessmentOrchestrator(repository, collector(task_evidence()), hr)
    second_service = HRAssessmentOrchestrator(repository, collector(task_evidence()), hr)
    first_results = []
    thread = threading.Thread(
        target=lambda: first_results.extend(
            first_service.assess(("agent-1",), local_date=LOCAL_DATE, actor_ai_id="hr")
        )
    )
    thread.start()
    assert entered.wait(timeout=5)
    second = second_service.assess(
        ("agent-1",), local_date=LOCAL_DATE, actor_ai_id="hr"
    )
    release.set()
    thread.join(timeout=5)
    assert first_results[0].status == "complete"
    assert second[0].status == "claimed_elsewhere"
    assert len(hr.calls) == 1
    assert len(repository.list_assessments(ai_id="agent-1").items) == 1


def test_low_assessment_does_not_change_agent_or_existing_project_score(setup):
    repository, reporting, opened = setup
    reporting.close_cycle(opened.cycle.id, closed_at=NOW)
    score_path = repository.status_dir / "project-scores.json"
    original_score = b'{"agents":{"agent-1":{"score":88,"completed":4}}}'
    score_path.write_bytes(original_score)
    before_agent = repository.get_agent("agent-1")
    output = json.loads(assessment("agent-1", evidence=(reference(),)))
    output["workload"] = "low"
    output["rationale"] = "现有日报与任务记录显示当日工作量较低，建议检查任务供给。"
    result = HRAssessmentOrchestrator(
        repository,
        collector(task_evidence()),
        FakeHR({"agent-1": json.dumps(output, ensure_ascii=False)}),
    ).assess(("agent-1",), local_date=LOCAL_DATE, actor_ai_id="hr")
    assert result[0].status == "complete"
    assert result[0].assessment.workload == "low"
    assert repository.get_agent("agent-1") == before_agent
    assert score_path.read_bytes() == original_score


def test_punitive_hr_output_is_failed_without_side_effects(setup):
    repository, reporting, opened = setup
    reporting.close_cycle(opened.cycle.id, closed_at=NOW)
    before_agent = repository.get_agent("agent-1")
    output = json.loads(assessment("agent-1", evidence=(reference(),)))
    output["improvements"] = ["Pause the Agent and reassign its project."]
    result = HRAssessmentOrchestrator(
        repository,
        collector(task_evidence()),
        FakeHR({"agent-1": json.dumps(output)}),
    ).assess(("agent-1",), local_date=LOCAL_DATE, actor_ai_id="hr")
    assert result[0].status == "failed"
    assert repository.get_current_assessment("agent-1", LOCAL_DATE) is None
    assert repository.get_assessment_job("agent-1", LOCAL_DATE).status == "failed"
    assert repository.get_agent("agent-1") == before_agent
