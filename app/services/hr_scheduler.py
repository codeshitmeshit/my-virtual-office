"""VO-local HR due-time calculation and today's-only cycle reconciliation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
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
