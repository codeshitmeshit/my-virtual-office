"""Daily HR reporting cycle creation and durable request claim coordination."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Protocol

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


@dataclass(frozen=True, slots=True)
class DailyReportConversationRequest:
    sender_ai_id: str
    target_ai_id: str
    message: str
    conversation_key: str
    idempotency_key: str
    timeout_seconds: float


class HRDailyReportConversationPort(Protocol):
    def ask_agent_as_hr(self, request: DailyReportConversationRequest) -> str | None: ...


@dataclass(frozen=True, slots=True)
class ReportCollectionResult:
    request_id: str
    ai_id: str
    status: str
    conversation_key: str
    attempt_count: int
    error_code: str


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


class HRDailyReportCollector:
    """Performs visible, idempotent HR-to-Agent report conversations."""

    def __init__(
        self,
        repository: HRRepository,
        reporting: HRReportingService,
        conversation: HRDailyReportConversationPort,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        timeout_seconds: float = 30.0,
        hr_ai_id: str = "hr",
    ):
        if not isinstance(repository, HRRepository):
            raise HRReportingValidationError("repository must be an HRRepository")
        if not isinstance(reporting, HRReportingService):
            raise HRReportingValidationError("reporting service is invalid")
        if not callable(getattr(conversation, "ask_agent_as_hr", None)):
            raise HRReportingValidationError("conversation port is invalid")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0.1 <= float(timeout_seconds) <= 300
        ):
            raise HRReportingValidationError("timeout_seconds must be between 0.1 and 300")
        self._repository = repository
        self._reporting = reporting
        self._conversation = conversation
        self._clock = clock
        self._timeout_seconds = float(timeout_seconds)
        self._hr_ai_id = hr_ai_id

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise HRReportingValidationError("collector clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def process_requests(
        self,
        request_ids: Iterable[str],
        *,
        message: str,
        worker_id: str,
    ) -> tuple[ReportCollectionResult, ...]:
        if not isinstance(message, str) or not message.strip():
            raise HRReportingValidationError("daily report message must not be empty")
        message = message.strip()
        results = []
        for request_id in tuple(request_ids):
            token = ""
            request = None
            try:
                request = self._repository.get_report_request(request_id)
                if request is None:
                    raise HRReportingValidationError("report request does not exist")
                if request.status in {"submitted", "no_response", "skipped"}:
                    results.append(
                        ReportCollectionResult(
                            request.id,
                            request.ai_id,
                            "already_complete",
                            request.conversation_key,
                            request.attempt_count,
                            "",
                        )
                    )
                    continue
                claim = self._reporting.claim_request(request.id, worker_id=worker_id)
                if claim is None:
                    results.append(
                        ReportCollectionResult(
                            request.id,
                            request.ai_id,
                            "claimed_elsewhere",
                            request.conversation_key,
                            request.attempt_count,
                            "",
                        )
                    )
                    continue
                token = claim.claim_token
                response = self._conversation.ask_agent_as_hr(
                    DailyReportConversationRequest(
                        sender_ai_id=self._hr_ai_id,
                        target_ai_id=claim.ai_id,
                        message=message,
                        conversation_key=claim.conversation_key,
                        idempotency_key=claim.occurrence_key,
                        timeout_seconds=self._timeout_seconds,
                    )
                )
                if response is not None and not isinstance(response, str):
                    raise TypeError("conversation response must be text or None")
                finished, _ = self._repository.record_report_response(
                    request_id=claim.id,
                    claim_token=token,
                    finished_at=self._now().isoformat(),
                    raw_response=response,
                )
                results.append(
                    ReportCollectionResult(
                        finished.id,
                        finished.ai_id,
                        "submitted" if finished.status == "submitted" else "no_response",
                        finished.conversation_key,
                        finished.attempt_count,
                        "",
                    )
                )
            except Exception as exc:
                error_code = (
                    "conversation_timeout"
                    if isinstance(exc, TimeoutError)
                    else getattr(exc, "code", "conversation_failed")
                )
                attempts = request.attempt_count if request is not None else 0
                if token and request is not None:
                    try:
                        failed = self._repository.finish_report_request(
                            request_id=request.id,
                            claim_token=token,
                            status="retry",
                            finished_at=self._now().isoformat(),
                            last_error=f"{error_code}:{exc.__class__.__name__}",
                        )
                        attempts = failed.attempt_count
                    except Exception:
                        pass
                results.append(
                    ReportCollectionResult(
                        str(request_id),
                        request.ai_id if request is not None else "",
                        "timeout" if error_code == "conversation_timeout" else "failed",
                        request.conversation_key if request is not None else "",
                        attempts,
                        str(error_code),
                    )
                )
        return tuple(results)
