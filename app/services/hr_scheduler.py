"""VO-local HR due-time calculation and today's-only cycle reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterable

from services.hr_config import HRConfig
from services.hr_reporting import HRReportingService, ReportingCycleResult
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
