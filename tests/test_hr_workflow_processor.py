"""Bounded durable report/assessment workers, retries, and dual-loop fencing."""

import json
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_assessments import HRAssessmentOrchestrator
from services.hr_config import HRConfig
from services.hr_evidence import HREvidenceCollector, HREvidencePorts
from services.hr_reporting import HRDailyReportCollector, HRReportingService
from services.hr_repository import HRRepository
from services.hr_scheduler import (
    HRLoopRuntime,
    HRManualCommands,
    HRReconciliationLoop,
    HRScheduler,
    HRWorkflowProcessor,
)


NOW = datetime(2026, 7, 19, 10, tzinfo=timezone.utc)
LOCAL_DATE = "2026-07-19"
MESSAGE = "请提交今日日报。"


class EmptyEvidence:
    def read_project_transitions(self, *_args):
        return ()

    def read_task_transitions(self, *_args):
        return ()

    def read_meeting_contributions(self, *_args):
        return ()

    def read_artifact_metadata(self, *_args):
        return ()

    def read_execution_results(self, *_args):
        return ()

    def read_blockers_and_waiting(self, *_args):
        return ()


class Conversation:
    def __init__(self, outcome=None):
        self.outcome = outcome
        self.calls = []

    def ask_agent_as_hr(self, request):
        self.calls.append(request)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome if self.outcome is not None else f"{request.target_ai_id} done"


class AssessmentHR:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def ask_hr(self, _prompt, conversation_key, _timeout):
        self.calls.append(conversation_key)
        if self.fail:
            raise RuntimeError("provider secret")
        ai_id = conversation_key.rsplit(":", 1)[-1]
        return json.dumps(
            {
                "schemaVersion": 1,
                "agentAiId": ai_id,
                "localDate": LOCAL_DATE,
                "principalContributions": [],
                "workload": "insufficient_information",
                "rationale": "证据不足，不能推断工作量。",
                "evidenceReferences": [],
                "blockers": [],
                "strengths": [],
                "improvements": ["补充可追踪信息"],
                "runtimeDiagnosis": "信息不足",
                "informationSufficiency": {
                    "status": "insufficient",
                    "explanation": "只有单一或缺失来源",
                },
                "hrAiId": "hr",
                "assessedAt": NOW.isoformat(),
            },
            ensure_ascii=False,
        )


def make_config(*, enabled=True, workers=2, retries=1):
    return HRConfig.from_env(
        {
            "VO_HR_ENABLED": "1" if enabled else "0",
            "VO_HR_SCHEDULER_ENABLED": "1",
            "VO_HR_MAX_WORKERS": str(workers),
            "VO_HR_RETRY_LIMIT": str(retries),
        }
    )


def setup(tmp_path, *, agent_count=4, conversation=None, assessment_hr=None, config=None):
    cfg = config or make_config()
    repository = HRRepository(tmp_path / "status", clock=lambda: NOW)
    repository.initialize()
    agent_ids = tuple(f"agent-{index}" for index in range(1, agent_count + 1))
    for ai_id in ("hr", *agent_ids):
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
        claim_lease_seconds=120,
    )
    opened = reporting.open_cycle(
        local_date=LOCAL_DATE,
        timezone_name="UTC",
        scheduled_at=NOW,
        window_opens_at=NOW,
        window_closes_at=NOW + timedelta(hours=2),
        eligible_ai_ids=agent_ids,
    )
    conversation = conversation or Conversation()
    reports = HRDailyReportCollector(
        repository,
        reporting,
        conversation,
        clock=lambda: NOW,
        timeout_seconds=1,
    )
    empty = EmptyEvidence()
    evidence = HREvidenceCollector(
        HREvidencePorts(empty, empty, empty, empty, empty, empty)
    )
    assessment_hr = assessment_hr or AssessmentHR()
    assessments = HRAssessmentOrchestrator(
        repository,
        evidence,
        assessment_hr,
        clock=lambda: NOW,
        claim_token_factory=lambda job_id: f"claim:{job_id}",
        timeout_seconds=1,
        claim_lease_seconds=30,
        retry_limit=cfg.retry_limit,
    )
    processor = HRWorkflowProcessor(
        cfg,
        repository,
        reports,
        assessments,
        clock=lambda: NOW,
        queue_capacity=cfg.max_workers,
    )
    return repository, reporting, opened, conversation, assessment_hr, processor


def test_report_queue_is_bounded_and_drains_across_ticks(tmp_path):
    repository, _reporting, opened, conversation, _hr, processor = setup(tmp_path)
    first = processor.process_reports(opened.cycle.id, message=MESSAGE)
    assert first.accepted == 2
    assert first.deferred == 2
    assert len(conversation.calls) == 2
    second = processor.process_reports(opened.cycle.id, message=MESSAGE)
    assert second.accepted == 2
    assert second.deferred == 0
    assert len(conversation.calls) == 4
    assert all(
        repository.get_daily_report(ai_id, LOCAL_DATE).raw_response is not None
        for ai_id in opened.cycle.roster_snapshot
    )


def test_one_stalled_agent_does_not_prevent_other_worker_from_finishing(tmp_path):
    entered = threading.Event()
    release = threading.Event()
    neighbor_finished = threading.Event()

    class OneStallConversation(Conversation):
        def ask_agent_as_hr(self, request):
            self.calls.append(request)
            if request.target_ai_id == "agent-1":
                entered.set()
                assert release.wait(timeout=5)
            else:
                neighbor_finished.set()
            return f"{request.target_ai_id} done"

    conversation = OneStallConversation()
    _repository, _reporting, opened, _conversation, _hr, processor = setup(
        tmp_path, agent_count=2, conversation=conversation
    )
    results = []
    thread = threading.Thread(
        target=lambda: results.append(
            processor.process_reports(opened.cycle.id, message=MESSAGE)
        )
    )
    thread.start()
    assert entered.wait(timeout=5)
    assert neighbor_finished.wait(timeout=5)
    release.set()
    thread.join(timeout=5)
    assert len(results[0].results) == 2


def test_dual_report_loops_make_one_effective_provider_call(tmp_path):
    entered = threading.Event()
    release = threading.Event()

    class BlockingConversation(Conversation):
        def ask_agent_as_hr(self, request):
            self.calls.append(request)
            entered.set()
            assert release.wait(timeout=5)
            return "done"

    conversation = BlockingConversation()
    repository, reporting, opened, _conversation, assessment_hr, first = setup(
        tmp_path, agent_count=1, conversation=conversation
    )
    reports = HRDailyReportCollector(
        repository, reporting, conversation, clock=lambda: NOW, timeout_seconds=1
    )
    second = HRWorkflowProcessor(
        make_config(),
        repository,
        reports,
        first._assessments,
        clock=lambda: NOW,
        queue_capacity=2,
    )
    first_results = []
    thread = threading.Thread(
        target=lambda: first_results.append(
            first.process_reports(opened.cycle.id, message=MESSAGE)
        )
    )
    thread.start()
    assert entered.wait(timeout=5)
    competing = second.process_reports(opened.cycle.id, message=MESSAGE)
    release.set()
    thread.join(timeout=5)
    assert len(conversation.calls) == 1
    assert competing.status == "idle"
    assert competing.accepted == 0
    assert assessment_hr.calls == []


def test_expired_claim_is_recovered_after_restart(tmp_path):
    repository, reporting, opened, conversation, _hr, processor = setup(
        tmp_path, agent_count=1
    )
    request = opened.requests[0]
    repository.claim_report_request(
        request_id=request.id,
        claimed_by="dead-worker",
        claim_token="dead-claim",
        now=(NOW - timedelta(minutes=2)).isoformat(),
        claim_expires_at=(NOW - timedelta(minutes=1)).isoformat(),
    )
    result = processor.process_reports(opened.cycle.id, message=MESSAGE)
    assert result.results[0].status == "submitted"
    assert len(conversation.calls) == 1
    assert repository.get_report_request(request.id).attempt_count == 2


def test_report_retry_limit_becomes_visible_and_stops_provider_calls(tmp_path):
    timeout = Conversation(TimeoutError("provider secret"))
    repository, _reporting, opened, conversation, _hr, processor = setup(
        tmp_path,
        agent_count=1,
        conversation=timeout,
        config=make_config(retries=1),
    )
    assert processor.process_reports(opened.cycle.id, message=MESSAGE).results[0].status == (
        "timeout"
    )
    assert processor.process_reports(opened.cycle.id, message=MESSAGE).results[0].status == (
        "timeout"
    )
    exhausted = processor.process_reports(opened.cycle.id, message=MESSAGE)
    assert exhausted.exhausted == 1
    assert len(conversation.calls) == 2
    stored = repository.get_report_request(opened.requests[0].id)
    assert stored.status == "failed"
    assert stored.last_error == "retry_limit_exhausted"


def test_feature_disable_stops_new_claims_without_hiding_data(tmp_path):
    active = [False]
    repository, _reporting, opened, conversation, _hr, base = setup(
        tmp_path, agent_count=1
    )
    processor = HRWorkflowProcessor(
        make_config(),
        repository,
        base._reports,
        base._assessments,
        clock=lambda: NOW,
        active=lambda: active[0],
        queue_capacity=2,
    )
    disabled = processor.process_reports(opened.cycle.id, message=MESSAGE)
    assert disabled.status == "disabled"
    assert conversation.calls == []
    assert repository.get_report_request(opened.requests[0].id).status == "pending"
    active[0] = True
    assert processor.process_reports(opened.cycle.id, message=MESSAGE).accepted == 1


def test_assessment_queue_backpressure_and_failure_retry_limit(tmp_path):
    failing_hr = AssessmentHR(fail=True)
    repository, reporting, opened, _conversation, _hr, processor = setup(
        tmp_path,
        agent_count=3,
        assessment_hr=failing_hr,
        config=make_config(retries=1),
    )
    reporting.close_cycle(opened.cycle.id, closed_at=NOW)
    first = processor.process_assessments(opened.cycle.id)
    assert first.accepted == 2
    assert first.deferred == 1
    second = processor.process_assessments(opened.cycle.id)
    assert second.accepted == 2
    assert any(item.status == "failed" for item in second.results)
    third = processor.process_assessments(opened.cycle.id)
    assert third.exhausted >= 1
    assert any(
        repository.get_assessment_job(ai_id, LOCAL_DATE).last_error
        == "retry_limit_exhausted"
        for ai_id in opened.cycle.roster_snapshot
    )
    assert all(
        repository.get_assessment_job(ai_id, LOCAL_DATE) is not None
        for ai_id in opened.cycle.roster_snapshot
    )


def make_loop(repository, reporting, processor, opened, *, config=None):
    cfg = config or make_config()
    scheduler = HRScheduler(cfg, repository, reporting, clock=lambda: NOW)
    return HRReconciliationLoop(
        scheduler,
        reporting,
        processor,
        eligible_ai_ids=lambda: opened.cycle.roster_snapshot,
        hr_available=lambda: True,
        report_message=MESSAGE,
        clock=lambda: NOW,
        interval_seconds=1,
    )


def test_loop_tick_reuses_scheduler_and_processor_paths(tmp_path):
    repository, reporting, opened, conversation, _hr, processor = setup(
        tmp_path, agent_count=2
    )
    loop = make_loop(repository, reporting, processor, opened)
    result = loop.tick()
    assert result.schedule.action == "recover_open"
    assert result.reports.accepted == 2
    assert result.assessments is None
    assert len(conversation.calls) == 2
    closed = loop.close_and_assess(opened.cycle.id)
    assert closed.assessments.accepted == 2
    assert repository.get_daily_cycle(opened.cycle.id).status == "closed"
    retried = loop.retry(opened.cycle.id)
    assert retried.assessments is not None


def test_manual_commands_enqueue_without_running_provider_on_caller_thread(tmp_path):
    repository, reporting, opened, conversation, _hr, processor = setup(
        tmp_path, agent_count=1
    )
    loop = make_loop(repository, reporting, processor, opened)
    callbacks = []
    commands = HRManualCommands(
        loop,
        submit=lambda callback: callbacks.append(callback) is None,
        new_id=lambda: "command-1",
    )
    receipt = commands.run()
    assert receipt.command_id == "command-1"
    assert receipt.command == "run"
    assert receipt.accepted is True
    assert conversation.calls == []
    assert repository.get_report_request(opened.requests[0].id).status == "pending"
    callbacks[0]()
    assert len(conversation.calls) == 1


def test_default_manual_submit_returns_while_background_callback_is_blocked(tmp_path):
    repository, reporting, opened, _conversation, _hr, processor = setup(
        tmp_path, agent_count=1
    )
    loop = make_loop(repository, reporting, processor, opened)
    entered = threading.Event()
    release = threading.Event()

    def blocking_tick(*, manual=False):
        assert manual is True
        entered.set()
        assert release.wait(timeout=5)

    loop.tick = blocking_tick
    receipt = HRManualCommands(loop, new_id=lambda: "async-command").run()
    assert receipt.accepted is True
    assert entered.wait(timeout=5)
    release.set()


def test_manual_background_failure_is_reported_as_safe_code(tmp_path):
    repository, reporting, opened, _conversation, _hr, processor = setup(
        tmp_path, agent_count=1
    )
    loop = make_loop(repository, reporting, processor, opened)
    callbacks = []
    errors = []
    commands = HRManualCommands(
        loop,
        submit=lambda callback: callbacks.append(callback) is None,
        new_id=lambda: "bad-close",
        on_error=lambda command_id, code: errors.append((command_id, code)),
    )
    assert commands.close("missing-cycle").accepted is True
    callbacks[0]()
    assert errors == [("bad-close", "hr_repository_not_found")]


def test_startup_runtime_is_explicit_idempotent_and_stoppable(tmp_path):
    repository, reporting, opened, _conversation, _hr, processor = setup(
        tmp_path, agent_count=1
    )
    disabled = make_config(enabled=False)
    loop = make_loop(repository, reporting, processor, opened, config=disabled)
    runtime = HRLoopRuntime()
    assert runtime.start() is False
    runtime.install(loop)
    assert runtime.start() is True
    assert runtime.start() is False
    runtime.stop()


def test_server_startup_wiring_is_thin_and_does_not_run_whole_cycle_inline():
    source = (APP_DIR / "server.py").read_text(encoding="utf-8")
    assert "target=_hr_scheduler_start_on_startup" in source
    startup = source[source.index("def _hr_scheduler_start_on_startup"):]
    startup = startup[: startup.index("\n\ndef ", 10)]
    assert "process_reports" not in startup
    assert "process_assessments" not in startup
    assert "ask_agent_as_hr" not in startup
