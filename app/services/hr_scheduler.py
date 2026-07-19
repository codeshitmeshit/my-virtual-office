"""VO-local HR due-time calculation and today's-only cycle reconciliation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import threading
import uuid
from typing import Callable, Iterable

from services.hr_config import HRConfig
from services.hr_assessments import AssessmentProcessingResult, HRAssessmentOrchestrator
from services.hr_reporting import (
    HRDailyReportCollector,
    HRReportingService,
    ReportCollectionResult,
    ReportingCycleResult,
)
from services.hr_repository import DailyCycleRecord, HRRepository
from services.hr_command_status import HRCommandStatusTracker


class HRSchedulerValidationError(ValueError):
    code = "hr_scheduler_validation_failed"


@dataclass(frozen=True, slots=True)
class DailyScheduleWindow:
    local_date: str
    timezone_name: str
    scheduled_at: datetime
    window_opens_at: datetime
    window_closes_at: datetime
    dst_adjusted: bool


@dataclass(frozen=True, slots=True)
class SchedulerReconciliation:
    action: str
    window: DailyScheduleWindow | None
    cycle: DailyCycleRecord | None
    opened: ReportingCycleResult | None


@dataclass(frozen=True, slots=True)
class WorkflowProcessingSummary:
    status: str
    accepted: int
    deferred: int
    exhausted: int
    results: tuple[ReportCollectionResult | AssessmentProcessingResult, ...]


@dataclass(frozen=True, slots=True)
class ReconciliationTickResult:
    schedule: SchedulerReconciliation | None
    reports: WorkflowProcessingSummary | None
    assessments: WorkflowProcessingSummary | None


@dataclass(frozen=True, slots=True)
class HRCommandReceipt:
    command_id: str
    command: str
    accepted: bool


class HRDueTimeCalculator:
    """Resolves one real instant for a configured local wall time and date."""

    def __init__(self, config: HRConfig):
        if not isinstance(config, HRConfig):
            raise HRSchedulerValidationError("HR config is invalid")
        self._config = config

    def _valid_instants(self, naive: datetime) -> tuple[datetime, ...]:
        zone = self._config.timezone
        instants = []
        for fold in (0, 1):
            candidate = naive.replace(tzinfo=zone, fold=fold)
            utc = candidate.astimezone(timezone.utc)
            round_trip = utc.astimezone(zone)
            if (
                round_trip.replace(tzinfo=None) == naive
                and round_trip.fold == fold
                and utc not in instants
            ):
                instants.append(utc)
        return tuple(sorted(instants))

    def window_for_date(self, local_date: date) -> DailyScheduleWindow:
        if not isinstance(local_date, date) or isinstance(local_date, datetime):
            raise HRSchedulerValidationError("local_date must be a date")
        naive = datetime.combine(local_date, self._config.daily_time)
        instants = self._valid_instants(naive)
        adjusted = False
        if not instants:
            adjusted = True
            for minutes in range(1, 181):
                instants = self._valid_instants(naive + timedelta(minutes=minutes))
                if instants:
                    break
        if not instants:
            raise HRSchedulerValidationError("daily time could not be resolved in timezone")
        scheduled = instants[0]
        return DailyScheduleWindow(
            local_date=local_date.isoformat(),
            timezone_name=self._config.timezone_name,
            scheduled_at=scheduled,
            window_opens_at=scheduled,
            window_closes_at=scheduled
            + timedelta(minutes=self._config.submission_window_minutes),
            dst_adjusted=adjusted,
        )

    def window_at(self, now: datetime) -> DailyScheduleWindow:
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise HRSchedulerValidationError("scheduler clock must be timezone-aware")
        local_date = now.astimezone(self._config.timezone).date()
        return self.window_for_date(local_date)


class HRScheduler:
    """Reconciles today's durable cycle without historical backfill or provider work."""

    def __init__(
        self,
        config: HRConfig,
        repository: HRRepository,
        reporting: HRReportingService,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        if not isinstance(config, HRConfig):
            raise HRSchedulerValidationError("HR config is invalid")
        if not isinstance(repository, HRRepository):
            raise HRSchedulerValidationError("repository must be an HRRepository")
        if not isinstance(reporting, HRReportingService):
            raise HRSchedulerValidationError("reporting service is invalid")
        self._config = config
        self._repository = repository
        self._reporting = reporting
        self._clock = clock
        self._calculator = HRDueTimeCalculator(config)

    @property
    def mutations_enabled(self) -> bool:
        return self._config.enabled

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise HRSchedulerValidationError("scheduler clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def reconcile(
        self,
        eligible_ai_ids: Iterable[str],
        *,
        hr_available: bool = True,
        manual: bool = False,
    ) -> SchedulerReconciliation:
        if not isinstance(hr_available, bool) or not isinstance(manual, bool):
            raise HRSchedulerValidationError("scheduler flags must be boolean")
        if not self._config.enabled:
            return SchedulerReconciliation("disabled", None, None, None)
        if not manual and not self._config.scheduler_enabled:
            return SchedulerReconciliation("scheduler_disabled", None, None, None)
        now = self._now()
        window = self._calculator.window_at(now)
        cycle_id = f"hr-cycle:{window.local_date}"
        existing = self._repository.get_daily_cycle(cycle_id)
        if existing is not None:
            action = "recover_open" if existing.status == "open" else "already_closed"
            return SchedulerReconciliation(action, window, existing, None)
        if not manual and now < window.scheduled_at:
            return SchedulerReconciliation("not_due", window, None, None)
        if not hr_available:
            return SchedulerReconciliation("hr_unavailable", window, None, None)
        opened = self._reporting.open_cycle(
            local_date=window.local_date,
            timezone_name=window.timezone_name,
            scheduled_at=window.scheduled_at,
            window_opens_at=window.window_opens_at,
            window_closes_at=window.window_closes_at,
            eligible_ai_ids=eligible_ai_ids,
        )
        action = "opened_late" if now >= window.window_closes_at else "opened"
        return SchedulerReconciliation(action, window, opened.cycle, opened)


class HRWorkflowProcessor:
    """Runs durable claimed work in a bounded pool with per-tick backpressure."""

    def __init__(
        self,
        config: HRConfig,
        repository: HRRepository,
        reports: HRDailyReportCollector,
        assessments: HRAssessmentOrchestrator,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        active: Callable[[], bool] | None = None,
        queue_capacity: int | None = None,
    ):
        if not isinstance(config, HRConfig):
            raise HRSchedulerValidationError("HR config is invalid")
        if not isinstance(repository, HRRepository):
            raise HRSchedulerValidationError("repository must be an HRRepository")
        if not isinstance(reports, HRDailyReportCollector):
            raise HRSchedulerValidationError("report collector is invalid")
        if not isinstance(assessments, HRAssessmentOrchestrator):
            raise HRSchedulerValidationError("assessment orchestrator is invalid")
        capacity = config.max_workers * 4 if queue_capacity is None else queue_capacity
        if (
            isinstance(capacity, bool)
            or not isinstance(capacity, int)
            or not config.max_workers <= capacity <= 1_000
        ):
            raise HRSchedulerValidationError(
                "queue_capacity must cover workers and be at most 1000"
            )
        self._config = config
        self._repository = repository
        self._reports = reports
        self._assessments = assessments
        self._clock = clock
        self._active = active or (lambda: config.scheduler_active)
        self._queue_capacity = capacity

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise HRSchedulerValidationError("workflow clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def _all_requests(self, cycle_id: str):
        items = []
        cursor = None
        while True:
            page = self._repository.list_report_requests(
                cycle_id,
                limit=100,
                cursor=cursor,
            )
            items.extend(page.items)
            if page.next_cursor is None:
                return tuple(items)
            cursor = page.next_cursor

    def get_cycle(self, cycle_id: str) -> DailyCycleRecord | None:
        return self._repository.get_daily_cycle(cycle_id)

    def process_reports(
        self,
        cycle_id: str,
        *,
        message: str,
    ) -> WorkflowProcessingSummary:
        if not self._active():
            return WorkflowProcessingSummary("disabled", 0, 0, 0, ())
        now = self._now()
        max_attempts = self._config.retry_limit + 1
        candidates = []
        exhausted = 0
        for request in self._all_requests(cycle_id):
            retryable = request.status in {"pending", "retry", "failed"}
            expired = (
                request.status == "claimed"
                and request.claim_expires_at is not None
                and request.claim_expires_at <= now.isoformat()
            )
            if not (retryable or expired):
                continue
            if request.attempt_count >= max_attempts:
                self._repository.mark_report_request_exhausted(
                    request.id,
                    exhausted_at=now.isoformat(),
                )
                exhausted += 1
                continue
            candidates.append(request)
        accepted = candidates[: self._queue_capacity]
        deferred = len(candidates) - len(accepted)
        if not accepted:
            return WorkflowProcessingSummary("idle", 0, deferred, exhausted, ())
        results = []
        with ThreadPoolExecutor(
            max_workers=min(self._config.max_workers, len(accepted)),
            thread_name_prefix="hr-report",
        ) as executor:
            futures = {
                executor.submit(
                    self._reports.process_requests,
                    (request.id,),
                    message=message,
                    worker_id=f"hr-report-worker-{index}",
                ): request.id
                for index, request in enumerate(accepted)
            }
            for future in as_completed(futures):
                results.extend(future.result())
        results.sort(key=lambda item: item.request_id)
        return WorkflowProcessingSummary(
            "processed",
            len(accepted),
            deferred,
            exhausted,
            tuple(results),
        )

    def process_assessments(
        self,
        cycle_id: str,
    ) -> WorkflowProcessingSummary:
        if not self._active():
            return WorkflowProcessingSummary("disabled", 0, 0, 0, ())
        cycle = self._repository.get_daily_cycle(cycle_id)
        if cycle is None:
            raise HRSchedulerValidationError("daily cycle does not exist")
        if cycle.status != "closed":
            raise HRSchedulerValidationError("assessment cycle is not closed")
        ranked = []
        for ai_id in cycle.roster_snapshot:
            job = self._repository.get_assessment_job(ai_id, cycle.local_date)
            priority = 1 if job is not None and job.status == "complete" else 0
            ranked.append((priority, job.updated_at if job is not None else "", ai_id))
        candidates = [item[2] for item in sorted(ranked)]
        accepted = candidates[: self._queue_capacity]
        deferred = len(candidates) - len(accepted)
        if not accepted:
            return WorkflowProcessingSummary("idle", 0, deferred, 0, ())
        results = []
        with ThreadPoolExecutor(
            max_workers=min(self._config.max_workers, len(accepted)),
            thread_name_prefix="hr-assessment",
        ) as executor:
            futures = {
                executor.submit(
                    self._assessments.assess,
                    (ai_id,),
                    local_date=cycle.local_date,
                    actor_ai_id="hr",
                ): ai_id
                for ai_id in accepted
            }
            for future in as_completed(futures):
                results.extend(future.result())
        results.sort(key=lambda item: item.ai_id)
        exhausted = sum(item.status == "retry_exhausted" for item in results)
        return WorkflowProcessingSummary(
            "processed",
            len(accepted),
            deferred,
            exhausted,
            tuple(results),
        )


class HRReconciliationLoop:
    """Background-only coordinator shared by startup and manual commands."""

    def __init__(
        self,
        scheduler: HRScheduler,
        reporting: HRReportingService,
        processor: HRWorkflowProcessor,
        *,
        eligible_ai_ids: Callable[[], Iterable[str]],
        hr_available: Callable[[], bool],
        report_message: str,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        interval_seconds: float = 30.0,
        on_error: Callable[[str], None] = lambda _code: None,
    ):
        if not isinstance(scheduler, HRScheduler):
            raise HRSchedulerValidationError("scheduler is invalid")
        if not isinstance(reporting, HRReportingService):
            raise HRSchedulerValidationError("reporting service is invalid")
        if not isinstance(processor, HRWorkflowProcessor):
            raise HRSchedulerValidationError("workflow processor is invalid")
        if not callable(eligible_ai_ids) or not callable(hr_available):
            raise HRSchedulerValidationError("reconciliation providers are invalid")
        if not isinstance(report_message, str) or not report_message.strip():
            raise HRSchedulerValidationError("report_message must not be empty")
        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, (int, float))
            or not 1 <= float(interval_seconds) <= 3_600
        ):
            raise HRSchedulerValidationError("interval_seconds must be between 1 and 3600")
        self._scheduler = scheduler
        self._reporting = reporting
        self._processor = processor
        self._eligible_ai_ids = eligible_ai_ids
        self._hr_available = hr_available
        self._report_message = report_message.strip()
        self._clock = clock
        self._interval_seconds = float(interval_seconds)
        self._on_error = on_error
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise HRSchedulerValidationError("loop clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def tick(self, *, manual: bool = False) -> ReconciliationTickResult:
        schedule = self._scheduler.reconcile(
            self._eligible_ai_ids(),
            hr_available=self._hr_available(),
            manual=manual,
        )
        cycle = schedule.cycle
        if cycle is None or schedule.window is None:
            return ReconciliationTickResult(schedule, None, None)
        if cycle.status == "closed":
            assessments = self._processor.process_assessments(cycle.id)
            return ReconciliationTickResult(schedule, None, assessments)
        if self._now() >= schedule.window.window_closes_at:
            self._reporting.close_cycle(cycle.id, closed_at=self._now())
            assessments = self._processor.process_assessments(cycle.id)
            return ReconciliationTickResult(schedule, None, assessments)
        reports = self._processor.process_reports(cycle.id, message=self._report_message)
        return ReconciliationTickResult(schedule, reports, None)

    def close_and_assess(self, cycle_id: str) -> ReconciliationTickResult:
        if not self._scheduler.mutations_enabled:
            raise HRSchedulerValidationError("Human Resources is disabled")
        self._reporting.close_cycle(cycle_id, closed_at=self._now())
        assessments = self._processor.process_assessments(cycle_id)
        return ReconciliationTickResult(None, None, assessments)

    def retry(self, cycle_id: str) -> ReconciliationTickResult:
        if not self._scheduler.mutations_enabled:
            raise HRSchedulerValidationError("Human Resources is disabled")
        cycle = self._processor.get_cycle(cycle_id)
        if cycle is None:
            raise HRSchedulerValidationError("daily cycle does not exist")
        if cycle.status == "closed":
            assessments = self._processor.process_assessments(cycle_id)
            return ReconciliationTickResult(None, None, assessments)
        reports = self._processor.process_reports(cycle_id, message=self._report_message)
        return ReconciliationTickResult(None, reports, None)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:
                try:
                    self._on_error(
                        str(getattr(exc, "code", "hr_reconciliation_failed"))
                    )
                except Exception:
                    pass
            self._stop.wait(self._interval_seconds)

    def start(self) -> bool:
        with self._start_lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
                name="hr-reconciliation",
            )
            self._thread.start()
            return True

    def stop(self, timeout_seconds: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.0, float(timeout_seconds)))


class HRManualCommands:
    """Queues manual actions so HTTP callers never wait for provider workflows."""

    def __init__(
        self,
        loop: HRReconciliationLoop,
        *,
        submit: Callable[[Callable[[], object]], bool] | None = None,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
        on_error: Callable[[str, str], None] = lambda _command_id, _code: None,
        tracker: HRCommandStatusTracker | None = None,
    ):
        if not isinstance(loop, HRReconciliationLoop):
            raise HRSchedulerValidationError("reconciliation loop is invalid")
        self._loop = loop
        self._submit = submit or self._thread_submit
        self._new_id = new_id
        self._on_error = on_error
        self._tracker = tracker

    @staticmethod
    def _thread_submit(callback: Callable[[], object]) -> bool:
        threading.Thread(
            target=callback,
            daemon=True,
            name="hr-manual-command",
        ).start()
        return True

    def _enqueue(self, command: str, callback: Callable[[], object]) -> HRCommandReceipt:
        command_id = self._new_id()
        if not isinstance(command_id, str) or not command_id.strip():
            raise HRSchedulerValidationError("manual command ID is invalid")
        tracker = getattr(self, "_tracker", None)
        if tracker is not None:
            tracker.accepted(command_id, command)

        def guarded() -> None:
            try:
                if tracker is not None:
                    tracker.running(command_id)
                callback()
                if tracker is not None:
                    tracker.complete(command_id)
            except Exception as exc:
                code = str(getattr(exc, "code", "hr_manual_command_failed"))
                if tracker is not None:
                    try:
                        tracker.failed(command_id, code)
                    except Exception:
                        pass
                self._on_error(
                    command_id,
                    code,
                )

        try:
            accepted = bool(self._submit(guarded))
        except Exception:
            accepted = False
        if not accepted and tracker is not None:
            tracker.failed(command_id, "hr_command_not_accepted")
        return HRCommandReceipt(command_id, command, accepted)

    def run(self) -> HRCommandReceipt:
        return self._enqueue("run", lambda: self._loop.tick(manual=True))

    def close(self, cycle_id: str) -> HRCommandReceipt:
        return self._enqueue(
            "close",
            lambda: self._loop.close_and_assess(cycle_id),
        )

    def retry(self, cycle_id: str) -> HRCommandReceipt:
        return self._enqueue("retry", lambda: self._loop.retry(cycle_id))


class HRLoopRuntime:
    """Explicit startup wiring holder; construction remains outside the legacy entry point."""

    def __init__(self):
        self._lock = threading.Lock()
        self._loop: HRReconciliationLoop | None = None

    def install(self, loop: HRReconciliationLoop) -> None:
        if not isinstance(loop, HRReconciliationLoop):
            raise HRSchedulerValidationError("reconciliation loop is invalid")
        with self._lock:
            self._loop = loop

    def start(self) -> bool:
        with self._lock:
            loop = self._loop
        return loop.start() if loop is not None else False

    def stop(self) -> None:
        with self._lock:
            loop = self._loop
        if loop is not None:
            loop.stop()
