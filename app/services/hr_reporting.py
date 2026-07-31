"""Daily HR reporting cycle creation and durable request claim coordination."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Protocol

from services.hr_prompt_documents import daily_report_request_document
from services.hr_repository import (
    DailyCycleRecord,
    DailyReportRecord,
    HRRepository,
    HRRepositoryConflictError,
    ReportRequestPage,
    ReportRequestRecord,
)
from services.hr_daily_report_response_filter import reportable_daily_response


class HRReportingValidationError(ValueError):
    code = "hr_reporting_validation_failed"


def daily_report_request_message(base_message: str, *, ai_id: str, local_date: str) -> str:
    """Build the provider-neutral preferred JSON contract with a text fallback."""
    if not isinstance(base_message, str) or not base_message.strip():
        raise HRReportingValidationError("daily report message must not be empty")
    return daily_report_request_document(
        base_message.strip(),
        ai_id=ai_id,
        local_date=local_date,
    )


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

    def close_cycle(
        self,
        cycle_id: str,
        *,
        closed_at: datetime | None = None,
    ) -> ReportingCycleResult:
        effective = self._now() if closed_at is None else closed_at
        if (
            not isinstance(effective, datetime)
            or effective.tzinfo is None
            or effective.utcoffset() is None
        ):
            raise HRReportingValidationError("closed_at must be timezone-aware")
        cycle, reports = self._repository.close_daily_cycle(
            cycle_id,
            closed_at=effective.astimezone(timezone.utc).isoformat(),
        )
        request_items = []
        cursor = None
        while True:
            page = self._repository.list_report_requests(cycle.id, limit=100, cursor=cursor)
            request_items.extend(page.items)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        return ReportingCycleResult(cycle, tuple(request_items), reports)

    def submit_response(
        self,
        *,
        ai_id: str,
        local_date: str,
        raw_response: str,
        submitted_at: datetime | None = None,
    ) -> DailyReportRecord:
        effective = self._now() if submitted_at is None else submitted_at
        if (
            not isinstance(effective, datetime)
            or effective.tzinfo is None
            or effective.utcoffset() is None
        ):
            raise HRReportingValidationError("submitted_at must be timezone-aware")
        return self._repository.submit_daily_report_response(
            ai_id=ai_id,
            local_date=local_date,
            raw_response=raw_response,
            submitted_at=effective.astimezone(timezone.utc).isoformat(),
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
                cycle = self._repository.get_daily_cycle(claim.cycle_id)
                if cycle is None:
                    raise HRReportingValidationError("daily report cycle does not exist")
                response = self._conversation.ask_agent_as_hr(
                    DailyReportConversationRequest(
                        sender_ai_id=self._hr_ai_id,
                        target_ai_id=claim.ai_id,
                        message=daily_report_request_message(
                            message,
                            ai_id=claim.ai_id,
                            local_date=cycle.local_date,
                        ),
                        conversation_key=claim.conversation_key,
                        idempotency_key=claim.occurrence_key,
                        timeout_seconds=self._timeout_seconds,
                    )
                )
                if response is not None and not isinstance(response, str):
                    raise TypeError("conversation response must be text or None")
                response = reportable_daily_response(response)
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


@dataclass(frozen=True, slots=True)
class AgentReportPublicStatus:
    ai_id: str
    local_date: str
    status: str
    requested_at: str | None
    window_closed_at: str | None
    submitted_at: str | None


@dataclass(frozen=True, slots=True)
class AgentReportManagementStatus:
    public: AgentReportPublicStatus
    request_status: str
    attempt_count: int
    last_error: str
    raw_response: str | None


@dataclass(frozen=True, slots=True)
class CycleStatusProjection:
    cycle_id: str
    local_date: str
    status: str
    total: int
    counts: dict[str, int]
    items: tuple[AgentReportPublicStatus | AgentReportManagementStatus, ...]
    next_cursor: str | None


class HRReportingProjection:
    """Builds non-leaking public and full management reporting status views."""

    STATUSES = (
        "waiting",
        "submitted",
        "late",
        "not_submitted",
        "skipped",
        "complete",
        "failed",
    )

    def __init__(self, repository: HRRepository):
        if not isinstance(repository, HRRepository):
            raise HRReportingValidationError("repository must be an HRRepository")
        self._repository = repository

    @staticmethod
    def _status(
        request: ReportRequestRecord,
        report: DailyReportRecord,
        *,
        assessment_complete: bool = False,
    ) -> str:
        if assessment_complete or report.submission_state == "complete":
            return "complete"
        if report.submission_state == "skipped" or request.status == "skipped":
            return "skipped"
        if report.raw_response is not None:
            if (
                report.submission_state == "late_submitted"
                or report.window_closed_at is not None
                and report.submitted_at is not None
                and report.submitted_at > report.window_closed_at
            ):
                return "late"
            return "submitted"
        if report.submission_state == "not_submitted":
            return "not_submitted"
        if request.status in {"failed", "retry"} or report.submission_state == "failed":
            return "failed"
        return "waiting"

    def _item(
        self,
        request: ReportRequestRecord,
        report: DailyReportRecord,
        *,
        management: bool,
        assessment_complete: bool = False,
    ) -> AgentReportPublicStatus | AgentReportManagementStatus:
        public = AgentReportPublicStatus(
            ai_id=request.ai_id,
            local_date=report.local_date,
            status=self._status(
                request,
                report,
                assessment_complete=assessment_complete,
            ),
            requested_at=report.requested_at or request.requested_at,
            window_closed_at=report.window_closed_at,
            submitted_at=report.submitted_at,
        )
        if not management:
            return public
        return AgentReportManagementStatus(
            public=public,
            request_status=request.status,
            attempt_count=request.attempt_count,
            last_error=request.last_error,
            raw_response=report.raw_response,
        )

    def project_cycle(
        self,
        cycle_id: str,
        *,
        management: bool = False,
        limit: int = 50,
        cursor: str | None = None,
    ) -> CycleStatusProjection:
        cycle = self._repository.get_daily_cycle(cycle_id)
        if cycle is None:
            raise HRReportingValidationError("daily cycle does not exist")
        selected = self._repository.list_report_requests(
            cycle.id,
            limit=limit,
            cursor=cursor,
        )
        selected_ids = {item.id for item in selected.items}
        selected_projections = {}
        counts = {status: 0 for status in self.STATUSES}
        total = 0
        scan_cursor = None
        while True:
            page = self._repository.list_report_requests(
                cycle.id,
                limit=100,
                cursor=scan_cursor,
            )
            for request in page.items:
                report = self._repository.get_daily_report(request.ai_id, cycle.local_date)
                if report is None:
                    raise HRReportingValidationError("daily report placeholder is missing")
                assessment_complete = (
                    self._repository.get_current_assessment(request.ai_id, cycle.local_date)
                    is not None
                )
                status = self._status(
                    request,
                    report,
                    assessment_complete=assessment_complete,
                )
                counts[status] += 1
                total += 1
                if request.id in selected_ids:
                    selected_projections[request.id] = self._item(
                        request,
                        report,
                        management=management,
                        assessment_complete=assessment_complete,
                    )
            if page.next_cursor is None:
                break
            scan_cursor = page.next_cursor
        items = tuple(selected_projections[item.id] for item in selected.items)
        terminal = counts["not_submitted"] + counts["skipped"] + counts["complete"]
        if total == terminal and cycle.status == "closed":
            cycle_status = "complete"
        elif cycle.status == "closed":
            cycle_status = "processing"
        else:
            cycle_status = cycle.status
        return CycleStatusProjection(
            cycle_id=cycle.id,
            local_date=cycle.local_date,
            status=cycle_status,
            total=total,
            counts=counts,
            items=items,
            next_cursor=selected.next_cursor,
        )
