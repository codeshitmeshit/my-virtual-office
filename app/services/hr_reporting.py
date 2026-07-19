"""Daily HR reporting cycle creation and durable request claim coordination."""

from __future__ import annotations

import json
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


class HRReportNormalizationPort(Protocol):
    def ask_hr(
        self,
        prompt: str,
        conversation_key: str,
        timeout_seconds: float,
    ) -> str | None: ...


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


@dataclass(frozen=True, slots=True)
class ReportNormalizationResult:
    ai_id: str
    local_date: str
    status: str
    error_code: str


class HRDailyReportNormalizer:
    """Asks HR for bounded structured normalization of Agent-authored claims."""

    MAX_OUTPUT_CHARS = 40_000
    MAX_LIST_ITEMS = 50
    MAX_TEXT_CHARS = 1_000
    ROOT_KEYS = frozenset(
        {
            "schemaVersion",
            "localDate",
            "agentAiId",
            "completedWork",
            "relatedProjectsOrTasks",
            "artifacts",
            "blockers",
            "requestedHelp",
            "submission",
        }
    )

    def __init__(
        self,
        repository: HRRepository,
        hr: HRReportNormalizationPort,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        timeout_seconds: float = 30.0,
        hr_ai_id: str = "hr",
    ):
        if not isinstance(repository, HRRepository):
            raise HRReportingValidationError("repository must be an HRRepository")
        if not callable(getattr(hr, "ask_hr", None)):
            raise HRReportingValidationError("HR normalization port is invalid")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0.1 <= float(timeout_seconds) <= 300
        ):
            raise HRReportingValidationError("timeout_seconds must be between 0.1 and 300")
        self._repository = repository
        self._hr = hr
        self._clock = clock
        self._timeout_seconds = float(timeout_seconds)
        self._hr_ai_id = hr_ai_id

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise HRReportingValidationError("normalization clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    @classmethod
    def _string_list(cls, value: object, field: str) -> list[str]:
        if not isinstance(value, list) or len(value) > cls.MAX_LIST_ITEMS:
            raise HRReportingValidationError(f"{field} must be a bounded list")
        if any(
            not isinstance(item, str)
            or not item.strip()
            or len(item) > cls.MAX_TEXT_CHARS
            for item in value
        ):
            raise HRReportingValidationError(f"{field} contains invalid text")
        return [item.strip() for item in value]

    @classmethod
    def _object_list(
        cls,
        value: object,
        field: str,
        keys: frozenset[str],
    ) -> list[dict[str, str]]:
        if not isinstance(value, list) or len(value) > cls.MAX_LIST_ITEMS:
            raise HRReportingValidationError(f"{field} must be a bounded list")
        normalized = []
        for item in value:
            if not isinstance(item, dict) or set(item) != keys:
                raise HRReportingValidationError(f"{field} contains an invalid object")
            if any(
                not isinstance(item[key], str)
                or not item[key].strip()
                or len(item[key]) > cls.MAX_TEXT_CHARS
                for key in keys
            ):
                raise HRReportingValidationError(f"{field} contains invalid text")
            normalized.append({key: item[key].strip() for key in sorted(keys)})
        return normalized

    @staticmethod
    def _claim_submission_state(report: DailyReportRecord) -> str:
        if report.submitted_at is None:
            return report.submission_state
        if (
            report.window_closed_at is not None
            and report.submitted_at > report.window_closed_at
        ):
            return "late_submitted"
        return "submitted"

    @classmethod
    def _parse(cls, output: str, report: DailyReportRecord) -> dict[str, object]:
        if not isinstance(output, str) or not output.strip():
            raise HRReportingValidationError("HR returned no normalized report")
        if len(output) > cls.MAX_OUTPUT_CHARS:
            raise HRReportingValidationError("HR normalized report is too large")
        try:
            value = json.loads(output)
        except json.JSONDecodeError as exc:
            raise HRReportingValidationError("HR normalized report is invalid JSON") from exc
        if not isinstance(value, dict) or set(value) != cls.ROOT_KEYS:
            raise HRReportingValidationError("HR normalized report has unsupported fields")
        if value["schemaVersion"] != 1:
            raise HRReportingValidationError("unsupported normalized report schema")
        if value["localDate"] != report.local_date or value["agentAiId"] != report.ai_id:
            raise HRReportingValidationError("normalized report identity does not match")
        submission = value["submission"]
        if not isinstance(submission, dict) or set(submission) != {
            "state",
            "requestedAt",
            "submittedAt",
        }:
            raise HRReportingValidationError("submission metadata is invalid")
        expected_submission = {
            "state": cls._claim_submission_state(report),
            "requestedAt": report.requested_at,
            "submittedAt": report.submitted_at,
        }
        if submission != expected_submission:
            raise HRReportingValidationError("submission metadata does not match")
        return {
            "schemaVersion": 1,
            "localDate": report.local_date,
            "agentAiId": report.ai_id,
            "completedWork": cls._string_list(value["completedWork"], "completedWork"),
            "relatedProjectsOrTasks": cls._object_list(
                value["relatedProjectsOrTasks"],
                "relatedProjectsOrTasks",
                frozenset({"type", "id", "title"}),
            ),
            "artifacts": cls._object_list(
                value["artifacts"],
                "artifacts",
                frozenset({"id", "name", "type"}),
            ),
            "blockers": cls._string_list(value["blockers"], "blockers"),
            "requestedHelp": cls._string_list(value["requestedHelp"], "requestedHelp"),
            "submission": expected_submission,
        }

    @staticmethod
    def _prompt(report: DailyReportRecord) -> str:
        submission = {
            "state": HRDailyReportNormalizer._claim_submission_state(report),
            "requestedAt": report.requested_at,
            "submittedAt": report.submitted_at,
        }
        return (
            "Normalize the Agent's daily report. Return JSON only with exactly these keys: "
            "schemaVersion, localDate, agentAiId, completedWork, "
            "relatedProjectsOrTasks, artifacts, blockers, requestedHelp, submission. "
            "schemaVersion must be 1. relatedProjectsOrTasks items require type, id, title; "
            "artifacts items require id, name, type. submission requires state, requestedAt, "
            "submittedAt and must copy the supplied metadata exactly. Do not invent work.\n"
            f"localDate: {report.local_date}\nAgent AI ID: {report.ai_id}\n"
            f"submission: {json.dumps(submission, ensure_ascii=False)}\n"
            f"Agent raw response:\n{report.raw_response}"
        )

    def normalize(
        self,
        ai_ids: Iterable[str],
        *,
        local_date: str,
    ) -> tuple[ReportNormalizationResult, ...]:
        results = []
        for ai_id in tuple(ai_ids):
            report = None
            try:
                report = self._repository.get_daily_report(ai_id, local_date)
                if report is None or report.raw_response is None:
                    results.append(
                        ReportNormalizationResult(ai_id, local_date, "no_raw_report", "")
                    )
                    continue
                if report.normalized is not None:
                    results.append(
                        ReportNormalizationResult(ai_id, local_date, "already_normalized", "")
                    )
                    continue
                output = self._hr.ask_hr(
                    self._prompt(report),
                    f"hr:daily-report-normalize:{local_date}:{ai_id}",
                    self._timeout_seconds,
                )
                normalized = self._parse(output, report)
                self._repository.save_daily_report(
                    report_id=report.id,
                    cycle_id=report.cycle_id,
                    ai_id=report.ai_id,
                    local_date=report.local_date,
                    submission_state="normalized",
                    raw_response=report.raw_response,
                    normalized=normalized,
                    normalizer_id=self._hr_ai_id,
                    requested_at=report.requested_at,
                    window_closed_at=report.window_closed_at,
                    submitted_at=report.submitted_at,
                    normalized_at=self._now().isoformat(),
                    expected_revision=report.revision,
                )
                results.append(ReportNormalizationResult(ai_id, local_date, "normalized", ""))
            except Exception as exc:
                error_code = getattr(exc, "code", "normalization_failed")
                if report is not None and report.raw_response is not None:
                    try:
                        self._repository.save_daily_report(
                            report_id=report.id,
                            cycle_id=report.cycle_id,
                            ai_id=report.ai_id,
                            local_date=report.local_date,
                            submission_state="normalization_failed",
                            raw_response=report.raw_response,
                            normalized=None,
                            requested_at=report.requested_at,
                            window_closed_at=report.window_closed_at,
                            submitted_at=report.submitted_at,
                            expected_revision=report.revision,
                        )
                    except Exception:
                        pass
                results.append(
                    ReportNormalizationResult(ai_id, local_date, "failed", str(error_code))
                )
        return tuple(results)
