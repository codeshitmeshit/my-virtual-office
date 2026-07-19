"""Selected, management-triggered daily-report correction and reassessment."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

from services.hr_assessments import HRAssessmentOrchestrator
from services.hr_directory import INELIGIBLE_AVAILABILITY
from services.hr_reporting import (
    DailyReportConversationRequest,
    HRDailyReportNormalizer,
    HRReportingService,
)
from services.hr_repository import AgentRecord, HRRepository


DAILY_REPORT_REQUEST_MESSAGE = (
    "请重新提交你今天的日报。请准确说明今天完成的工作、相关项目或任务、产出物、"
    "遇到的阻塞以及需要的协助；不要虚构或补充未发生的工作。"
)


class HRManualDailySyncValidationError(ValueError):
    code = "hr_manual_daily_sync_validation_failed"


@dataclass(frozen=True, slots=True)
class HRManualDailySyncItem:
    ai_id: str
    status: str
    error_code: str = ""


@dataclass(frozen=True, slots=True)
class HRManualDailySyncResult:
    local_date: str
    requested: int
    updated: int
    assessed: int
    no_response: int
    failed: int
    items: tuple[HRManualDailySyncItem, ...]


@dataclass(frozen=True, slots=True)
class HRManualDailySyncReceipt:
    command_id: str
    command: str
    accepted: bool


class CallableHRManualDailyConversation:
    """Injected office conversation adapter shared by collection and HR reasoning."""

    def __init__(
        self,
        ask_agent: Callable[[str, str, str, float], str | None],
        ask_hr: Callable[[str, str, float], str | None],
    ):
        if not callable(ask_agent) or not callable(ask_hr):
            raise HRManualDailySyncValidationError("conversation callbacks are required")
        self._ask_agent = ask_agent
        self._ask_hr = ask_hr

    def ask_agent_as_hr(self, request: DailyReportConversationRequest) -> str | None:
        return self._ask_agent(
            request.target_ai_id,
            request.message,
            request.conversation_key,
            request.timeout_seconds,
        )

    def ask_hr(self, prompt: str, conversation_key: str, timeout_seconds: float) -> str | None:
        return self._ask_hr(prompt, conversation_key, timeout_seconds)


class EmptyHREvidencePort:
    """Production-safe fallback until domain evidence adapters are installed."""

    def read_project_transitions(self, _ai_id: str, _local_date: str): return ()
    def read_task_transitions(self, _ai_id: str, _local_date: str): return ()
    def read_meeting_contributions(self, _ai_id: str, _local_date: str): return ()
    def read_artifact_metadata(self, _ai_id: str, _local_date: str): return ()
    def read_execution_results(self, _ai_id: str, _local_date: str): return ()
    def read_blockers_and_waiting(self, _ai_id: str, _local_date: str): return ()


class HRManualDailySyncService:
    """Refresh selected reports and immediately replace their current assessments."""

    MAX_SELECTION = 100

    def __init__(
        self,
        repository: HRRepository,
        reporting: HRReportingService,
        normalizer: HRDailyReportNormalizer,
        assessments: HRAssessmentOrchestrator,
        conversation: CallableHRManualDailyConversation,
        *,
        timezone_name: str,
        submission_window_minutes: int,
        max_workers: int,
        timeout_seconds: float,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ):
        if not isinstance(repository, HRRepository):
            raise HRManualDailySyncValidationError("repository must be an HRRepository")
        if not isinstance(reporting, HRReportingService):
            raise HRManualDailySyncValidationError("reporting service is invalid")
        if not isinstance(normalizer, HRDailyReportNormalizer):
            raise HRManualDailySyncValidationError("normalizer is invalid")
        if not isinstance(assessments, HRAssessmentOrchestrator):
            raise HRManualDailySyncValidationError("assessment service is invalid")
        if not isinstance(conversation, CallableHRManualDailyConversation):
            raise HRManualDailySyncValidationError("conversation adapter is invalid")
        try:
            self._timezone = ZoneInfo(timezone_name)
        except Exception as exc:
            raise HRManualDailySyncValidationError("timezone_name is invalid") from exc
        if not 1 <= max_workers <= 16 or not 1 <= submission_window_minutes <= 1440:
            raise HRManualDailySyncValidationError("manual daily sync limits are invalid")
        self._repository = repository
        self._reporting = reporting
        self._normalizer = normalizer
        self._assessments = assessments
        self._conversation = conversation
        self._timezone_name = timezone_name
        self._submission_window_minutes = submission_window_minutes
        self._max_workers = max_workers
        self._timeout_seconds = float(timeout_seconds)
        self._clock = clock
        self._new_id = new_id

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise HRManualDailySyncValidationError("clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def _all_agents(self) -> tuple[AgentRecord, ...]:
        items: list[AgentRecord] = []
        cursor = None
        while True:
            page = self._repository.list_agents(limit=100, cursor=cursor)
            items.extend(page.items)
            if page.next_cursor is None:
                return tuple(items)
            cursor = page.next_cursor

    @staticmethod
    def _available(agent: AgentRecord) -> bool:
        return agent.ai_id != "hr" and agent.status == "active" and agent.availability not in INELIGIBLE_AVAILABILITY

    def _selection(self, ai_ids: Iterable[str]) -> tuple[str, ...]:
        values = tuple(ai_ids)
        if not values or len(values) > self.MAX_SELECTION:
            raise HRManualDailySyncValidationError("agentIds must select between 1 and 100 Agents")
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise HRManualDailySyncValidationError("agentIds contains an invalid AI ID")
        normalized = tuple(value.strip() for value in values)
        if len(set(normalized)) != len(normalized):
            raise HRManualDailySyncValidationError("agentIds contains duplicates")
        available = {agent.ai_id for agent in self._all_agents() if self._available(agent)}
        if any(ai_id not in available for ai_id in normalized):
            raise HRManualDailySyncValidationError("agentIds contains an unavailable Agent")
        return normalized

    def _ensure_cycle(self, local_date: str, now: datetime, selected: tuple[str, ...]) -> None:
        cycle = self._repository.get_daily_cycle(f"hr-cycle:{local_date}")
        if cycle is None:
            roster = tuple(agent.ai_id for agent in self._all_agents() if self._available(agent))
            opened = self._reporting.open_cycle(
                local_date=local_date,
                timezone_name=self._timezone_name,
                scheduled_at=now,
                window_opens_at=now,
                window_closes_at=now + timedelta(minutes=self._submission_window_minutes),
                eligible_ai_ids=roster,
            )
            cycle = opened.cycle
        for ai_id in selected:
            if self._repository.get_daily_report(ai_id, local_date) is None:
                self._repository.save_daily_report(
                    report_id=f"hr-daily-report:{local_date}:{ai_id}",
                    cycle_id=cycle.id,
                    ai_id=ai_id,
                    local_date=local_date,
                    submission_state="waiting",
                    raw_response=None,
                    normalized=None,
                    expected_revision=0,
                )

    def _sync_one(self, ai_id: str, *, local_date: str, command_id: str) -> HRManualDailySyncItem:
        try:
            response = self._conversation.ask_agent_as_hr(
                DailyReportConversationRequest(
                    sender_ai_id="hr",
                    target_ai_id=ai_id,
                    message=DAILY_REPORT_REQUEST_MESSAGE,
                    conversation_key=f"hr:manual-daily-report:{local_date}:{ai_id}:{command_id}",
                    idempotency_key=f"hr-manual-daily:{command_id}:{ai_id}",
                    timeout_seconds=self._timeout_seconds,
                )
            )
            if response is None or not str(response).strip():
                return HRManualDailySyncItem(ai_id, "no_response")
            self._repository.replace_daily_report_response(
                ai_id=ai_id,
                local_date=local_date,
                raw_response=str(response),
                submitted_at=self._now().isoformat(),
            )
            normalized = self._normalizer.normalize((ai_id,), local_date=local_date)[0]
            if normalized.status != "normalized":
                return HRManualDailySyncItem(ai_id, "normalization_failed", normalized.error_code)
            assessed = self._assessments.assess(
                (ai_id,),
                local_date=local_date,
                actor_ai_id="hr",
                allow_open_cycle=True,
                revision_reason="manual_daily_sync",
            )[0]
            if assessed.status not in {"complete", "already_complete"}:
                return HRManualDailySyncItem(ai_id, "assessment_failed", assessed.error_code)
            return HRManualDailySyncItem(ai_id, "complete")
        except Exception as exc:
            return HRManualDailySyncItem(ai_id, "failed", str(getattr(exc, "code", "hr_manual_daily_sync_failed")))

    def synchronize(self, ai_ids: Iterable[str], *, command_id: str) -> HRManualDailySyncResult:
        selected = self._selection(ai_ids)
        now = self._now()
        local_date = now.astimezone(self._timezone).date().isoformat()
        self._ensure_cycle(local_date, now, selected)
        items: list[HRManualDailySyncItem] = []
        with ThreadPoolExecutor(max_workers=min(self._max_workers, len(selected)), thread_name_prefix="hr-daily-sync") as executor:
            futures = {executor.submit(self._sync_one, ai_id, local_date=local_date, command_id=command_id): ai_id for ai_id in selected}
            for future in as_completed(futures):
                items.append(future.result())
        items.sort(key=lambda item: item.ai_id)
        return HRManualDailySyncResult(
            local_date,
            len(selected),
            sum(item.status in {"complete", "assessment_failed", "normalization_failed"} for item in items),
            sum(item.status == "complete" for item in items),
            sum(item.status == "no_response" for item in items),
            sum(item.status not in {"complete", "no_response"} for item in items),
            tuple(items),
        )

    def record_activity(self, command_id: str, result: HRManualDailySyncResult) -> None:
        self._repository.append_hr_activity(
            activity_id=self._new_id(), ai_id=None, action="manual_daily_sync",
            status="failed" if result.failed else "complete",
            message=f"requested={result.requested}, updated={result.updated}, assessed={result.assessed}",
            context={"localDate": result.local_date, "requested": result.requested, "updated": result.updated, "assessed": result.assessed, "noResponse": result.no_response, "failed": result.failed},
            occurrence_key=f"hr-manual-daily-sync:{command_id}:complete",
        )

    def record_failure(self, command_id: str, exc: Exception) -> None:
        self._repository.append_hr_activity(
            activity_id=self._new_id(),
            ai_id=None,
            action="manual_daily_sync",
            status="failed",
            error=str(getattr(exc, "code", "hr_manual_daily_sync_failed")),
            occurrence_key=f"hr-manual-daily-sync:{command_id}:failed",
        )


class HRManualDailySyncCommands:
    """Single-flight asynchronous command boundary for HTTP callers."""

    def __init__(self, service: HRManualDailySyncService, *, submit: Callable[[Callable[[], None]], bool] | None = None, new_id: Callable[[], str] = lambda: uuid.uuid4().hex):
        self._service = service
        self._submit = submit or self._thread_submit
        self._new_id = new_id
        self._lock = threading.Lock()
        self._running = False

    @staticmethod
    def _thread_submit(callback: Callable[[], None]) -> bool:
        threading.Thread(target=callback, daemon=True, name="hr-manual-daily-sync").start()
        return True

    def run(self, ai_ids: Iterable[str]) -> HRManualDailySyncReceipt:
        selected = self._service._selection(ai_ids)
        command_id = self._new_id()
        with self._lock:
            if self._running:
                return HRManualDailySyncReceipt(command_id, "manual_daily_sync", False)
            self._running = True

        def execute() -> None:
            try:
                result = self._service.synchronize(selected, command_id=command_id)
                self._service.record_activity(command_id, result)
            except Exception as exc:
                try:
                    self._service.record_failure(command_id, exc)
                except Exception:
                    pass
            finally:
                with self._lock:
                    self._running = False

        try:
            accepted = bool(self._submit(execute))
        except Exception:
            accepted = False
        if not accepted:
            with self._lock:
                self._running = False
        return HRManualDailySyncReceipt(command_id, "manual_daily_sync", accepted)
