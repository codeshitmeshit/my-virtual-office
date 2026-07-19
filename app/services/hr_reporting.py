"""Daily HR reporting cycle creation and durable request claim coordination."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable

from services.hr_repository import (
    DailyCycleRecord,
    DailyReportRecord,
    HRRepository,
    HRRepositoryConflictError,
    ReportRequestPage,
    ReportRequestRecord,
)


class HRReportingValidationError(ValueError):
    code = "hr_reporting_validation_failed"


@dataclass(frozen=True, slots=True)
class ReportingCycleResult:
    cycle: DailyCycleRecord
    requests: tuple[ReportRequestRecord, ...]
    reports: tuple[DailyReportRecord, ...]


class HRReportingService:
    """Creates one dated cycle and one durable request/report per eligible Agent."""

    def __init__(
        self,
        repository: HRRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        claim_token_factory: Callable[[str], str],
        claim_lease_seconds: int = 120,
        hr_ai_id: str = "hr",
    ):
        if not isinstance(repository, HRRepository):
            raise HRReportingValidationError("repository must be an HRRepository")
        if not callable(claim_token_factory):
            raise HRReportingValidationError("claim_token_factory is required")
        if (
            isinstance(claim_lease_seconds, bool)
            or not isinstance(claim_lease_seconds, int)
            or not 1 <= claim_lease_seconds <= 1_800
        ):
            raise HRReportingValidationError("claim_lease_seconds must be between 1 and 1800")
        self._repository = repository
        self._clock = clock
        self._claim_token_factory = claim_token_factory
        self._claim_lease_seconds = claim_lease_seconds
        self._hr_ai_id = hr_ai_id

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise HRReportingValidationError("reporting clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _cycle_id(local_date: str) -> str:
        return f"hr-cycle:{local_date}"

    @staticmethod
    def _request_id(local_date: str, ai_id: str) -> str:
        return f"hr-report-request:{local_date}:{ai_id}"

    @staticmethod
    def _report_id(local_date: str, ai_id: str) -> str:
        return f"hr-daily-report:{local_date}:{ai_id}"

    def open_cycle(
        self,
        *,
        local_date: str,
        timezone_name: str,
        scheduled_at: datetime,
        window_opens_at: datetime,
        window_closes_at: datetime,
        eligible_ai_ids: Iterable[str],
    ) -> ReportingCycleResult:
        timestamps = (scheduled_at, window_opens_at, window_closes_at)
        if any(
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
            for value in timestamps
        ):
            raise HRReportingValidationError("cycle timestamps must be timezone-aware")
        candidates = tuple(eligible_ai_ids)
        if any(not isinstance(ai_id, str) or not ai_id for ai_id in candidates):
            raise HRReportingValidationError("eligible AI IDs are invalid")
        roster = tuple(sorted(set(candidates) - {self._hr_ai_id}))
        cycle_id = self._cycle_id(local_date)
        cycle = self._repository.get_daily_cycle(cycle_id)
        if cycle is None:
            try:
                cycle = self._repository.ensure_daily_cycle(
                    cycle_id=cycle_id,
                    local_date=local_date,
                    timezone_name=timezone_name,
                    scheduled_at=scheduled_at.isoformat(),
                    window_opens_at=window_opens_at.isoformat(),
                    window_closes_at=window_closes_at.isoformat(),
                    status="open",
                    roster_snapshot=roster,
                    occurrence_key=f"hr-daily-cycle:{local_date}",
                )
            except HRRepositoryConflictError:
                cycle = self._repository.get_daily_cycle(cycle_id)
                if cycle is None:
                    raise
        roster = cycle.roster_snapshot
        requests = []
        reports = []
        for ai_id in roster:
            request = self._repository.ensure_report_request(
                request_id=self._request_id(local_date, ai_id),
                cycle_id=cycle.id,
                ai_id=ai_id,
                occurrence_key=f"hr-daily-request:{local_date}:{ai_id}",
                conversation_key=f"hr:daily-report:{local_date}:{ai_id}",
            )
            requests.append(request)
            report_id = self._report_id(local_date, ai_id)
            try:
                report = self._repository.save_daily_report(
                    report_id=report_id,
                    cycle_id=cycle.id,
                    ai_id=ai_id,
                    local_date=local_date,
                    submission_state="waiting",
                    raw_response=None,
                    normalized=None,
                    expected_revision=0,
                )
            except HRRepositoryConflictError:
                report = self._repository.get_daily_report(ai_id, local_date)
                if report is None or report.id != report_id:
                    raise
            reports.append(report)
        return ReportingCycleResult(cycle, tuple(requests), tuple(reports))

    def claim_request(self, request_id: str, *, worker_id: str) -> ReportRequestRecord | None:
        now = self._now()
        token = self._claim_token_factory(request_id)
        return self._repository.claim_report_request(
            request_id=request_id,
            claimed_by=worker_id,
            claim_token=token,
            now=now.isoformat(),
            claim_expires_at=(now + timedelta(seconds=self._claim_lease_seconds)).isoformat(),
        )

    def list_requests(
        self,
        cycle_id: str,
        *,
        status: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> ReportRequestPage:
        return self._repository.list_report_requests(
            cycle_id,
            status=status,
            limit=limit,
            cursor=cursor,
        )
