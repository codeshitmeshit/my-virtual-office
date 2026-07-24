"""Transport-independent Human Resources management queries and commands."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Protocol

from services.hr_config import HRConfig
from services.hr_governance import HRCaller, HRDisclosurePolicy
from services.hr_observability import HRObservability
from services.hr_reporting import HRReportingProjection
from services.hr_repository import HRRepository, HRRepositoryError
from services.hr_scheduler import HRCommandReceipt, HRDueTimeCalculator
from services.hr_schedule_settings import (
    HRScheduleSettingsService,
    HRScheduleSettingsValidationError,
)


class HRAPIValidationError(ValueError):
    code = "hr_api_validation_failed"


class HRAPIDisabledError(RuntimeError):
    code = "hr_disabled"


@dataclass(frozen=True, slots=True)
class HRServiceResult:
    status: int
    payload: dict[str, Any]


class HRLifecyclePort(Protocol):
    def public_state(self, *, ensure: bool = True) -> Mapping[str, object]: ...

    def pause(self) -> object: ...

    def resume(self) -> object: ...


class HRManualCommandsPort(Protocol):
    def run(self) -> HRCommandReceipt: ...

    def close(self, cycle_id: str) -> HRCommandReceipt: ...

    def retry(self, cycle_id: str) -> HRCommandReceipt: ...


class HRDirectorySyncPort(Protocol):
    def sync(self) -> object: ...


class HRInformationCompletionPort(Protocol):
    def complete(self) -> object: ...


class HRManualDailySyncPort(Protocol):
    def run(self, ai_ids: tuple[str, ...]) -> object: ...


def _json_safe(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            _camel(field.name): _json_safe(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _json_safe(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


class HRManagementAPI:
    """Application boundary for management-token-authenticated HR routes."""

    MAX_BODY_BYTES = 64 * 1024

    def __init__(
        self,
        repository: HRRepository,
        lifecycle: HRLifecyclePort,
        commands: HRManualCommandsPort,
        reporting: HRReportingProjection,
        observability: HRObservability,
        config: HRConfig,
        *,
        schedule_settings: HRScheduleSettingsService | None = None,
        directory_sync: HRDirectorySyncPort | None = None,
        information_completion: HRInformationCompletionPort | None = None,
        manual_daily_sync: HRManualDailySyncPort | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        if not isinstance(repository, HRRepository):
            raise HRAPIValidationError("repository must be an HRRepository")
        if not all(
            callable(getattr(lifecycle, method, None))
            for method in ("public_state", "pause", "resume")
        ):
            raise HRAPIValidationError("lifecycle port is invalid")
        if not all(
            callable(getattr(commands, method, None))
            for method in ("run", "close", "retry")
        ):
            raise HRAPIValidationError("manual commands are invalid")
        if not isinstance(reporting, HRReportingProjection):
            raise HRAPIValidationError("reporting projection is invalid")
        if not isinstance(observability, HRObservability):
            raise HRAPIValidationError("observability is invalid")
        if not isinstance(config, HRConfig):
            raise HRAPIValidationError("HR config is invalid")
        if schedule_settings is not None and not isinstance(
            schedule_settings, HRScheduleSettingsService
        ):
            raise HRAPIValidationError("HR schedule settings are invalid")
        if directory_sync is not None and not callable(getattr(directory_sync, "sync", None)):
            raise HRAPIValidationError("directory sync port is invalid")
        if information_completion is not None and not callable(
            getattr(information_completion, "complete", None)
        ):
            raise HRAPIValidationError("information completion port is invalid")
        if manual_daily_sync is not None and not callable(getattr(manual_daily_sync, "run", None)):
            raise HRAPIValidationError("manual daily sync port is invalid")
        self._repository = repository
        self._lifecycle = lifecycle
        self._commands = commands
        self._reporting = reporting
        self._observability = observability
        self._config = config
        self._schedule_settings = schedule_settings or HRScheduleSettingsService(repository)
        self._directory_sync = directory_sync
        self._information_completion = information_completion
        self._manual_daily_sync = manual_daily_sync
        self._clock = clock

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise HRAPIValidationError("API clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def _effective_schedule_settings(self):
        settings = self._schedule_settings.load()
        if self._config.scheduler_enabled:
            return settings
        return replace(settings, enabled=False)

    @staticmethod
    def _limit(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
            raise HRAPIValidationError("limit must be between 1 and 100")
        return value

    @classmethod
    def _body(cls, body: object, body_bytes: int) -> Mapping[str, object]:
        if (
            isinstance(body_bytes, bool)
            or not isinstance(body_bytes, int)
            or body_bytes < 0
        ):
            raise HRAPIValidationError("body size is invalid")
        if body_bytes > cls.MAX_BODY_BYTES:
            raise HRAPIValidationError("request body is too large")
        if not isinstance(body, Mapping):
            raise HRAPIValidationError("request body must be an object")
        return body

    def _report_schedule(
        self,
        *,
        local_date: date,
        cycle_exists: bool,
        now: datetime,
    ) -> dict[str, object]:
        settings = self._effective_schedule_settings()
        effective_config = replace(
            self._config,
            scheduler_enabled=settings.enabled,
            daily_time=settings.daily_time,
        )
        calculator = HRDueTimeCalculator(effective_config)
        today = calculator.window_for_date(local_date)
        enabled = effective_config.scheduler_active
        if cycle_exists:
            window = calculator.window_for_date(local_date + timedelta(days=1))
            state = "scheduled" if enabled else "disabled"
        elif now < today.scheduled_at:
            window = today
            state = "scheduled" if enabled else "disabled"
        elif enabled:
            window = today
            state = "due"
        else:
            window = calculator.window_for_date(local_date + timedelta(days=1))
            state = "disabled"
        local_scheduled = window.scheduled_at.astimezone(effective_config.timezone)
        return {
            "enabled": enabled,
            "state": state,
            "nextAt": window.scheduled_at.isoformat(),
            "nextLocalAt": local_scheduled.isoformat(),
            "timezone": effective_config.timezone_name,
            "dailyTime": settings.daily_time_text,
        }

    def overview(self) -> HRServiceResult:
        self._observability.increment("query.requests_total")
        agents = []
        cursor = None
        while True:
            page = self._repository.list_agents(limit=100, cursor=cursor)
            agents.extend(page.items)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        counts: dict[str, int] = {}
        for agent in agents:
            key = agent.availability if agent.status == "active" else "unavailable"
            counts[key] = counts.get(key, 0) + 1
        now = self._now()
        local_day = now.astimezone(self._config.timezone).date()
        local_date = local_day.isoformat()
        cycle = self._repository.get_daily_cycle(f"hr-cycle:{local_date}")
        cycle_payload = (
            _json_safe(self._reporting.project_cycle(cycle.id, management=False, limit=100))
            if cycle is not None
            else None
        )
        activity = self._repository.list_hr_activity(limit=20)
        return HRServiceResult(
            200,
            {
                "ok": True,
                "hr": dict(self._lifecycle.public_state(ensure=False)),
                "agentTotal": len(agents),
                "availabilityCounts": counts,
                "localDate": local_date,
                "reportSchedule": self._report_schedule(
                    local_date=local_day,
                    cycle_exists=cycle is not None,
                    now=now,
                ),
                "cycle": cycle_payload,
                "activeCommands": _json_safe(
                    self._repository.list_active_hr_commands(limit=20)
                ),
                "recentActivity": _json_safe(activity.items),
            },
        )

    def agent_detail(
        self,
        ai_id: str,
        *,
        report_limit: int = 20,
        report_cursor: str | None = None,
        assessment_limit: int = 20,
        assessment_cursor: str | None = None,
        access_limit: int = 20,
        access_cursor: str | None = None,
    ) -> HRServiceResult:
        self._observability.increment("query.requests_total")
        report_limit = self._limit(report_limit)
        assessment_limit = self._limit(assessment_limit)
        access_limit = self._limit(access_limit)
        agent = self._repository.get_agent(ai_id)
        if agent is None:
            return HRServiceResult(404, {"ok": False, "code": "hr_agent_not_found"})
        introduction = self._repository.get_current_introduction(ai_id)
        reports = self._repository.list_daily_reports(
            ai_id=ai_id,
            limit=report_limit,
            cursor=report_cursor,
        )
        assessments = self._repository.list_assessments(
            ai_id=ai_id,
            limit=assessment_limit,
            cursor=assessment_cursor,
        )
        identity_history = self._repository.list_identity_history(ai_id, limit=20)
        access_history = self._repository.list_access_log(
            target_ai_id=ai_id,
            limit=access_limit,
            cursor=access_cursor,
        )
        latest_assessment = assessments.items[0] if assessments.items else None
        latest_report = reports.items[0] if reports.items else None
        normalized = latest_report.normalized if latest_report is not None else None
        record = {
            "aiId": agent.ai_id,
            "name": agent.name,
            "emoji": agent.emoji,
            "introduction": introduction.introduction if introduction else "",
            "availability": agent.availability if agent.status == "active" else "unavailable",
            "status": agent.status,
            "agentKind": agent.agent_kind,
            "providerKind": agent.provider_kind,
            "introductionProvenance": (
                {
                    "source": introduction.source,
                    "actorId": introduction.actor_id,
                    "version": introduction.version,
                }
                if introduction
                else None
            ),
            "identityHistory": _json_safe(identity_history.items),
            "publicWorkSummary": (
                normalized.get("completedWork", []) if isinstance(normalized, dict) else []
            ),
            "workload": latest_assessment.workload if latest_assessment else "insufficient_information",
            "reports": _json_safe(reports.items),
            "assessments": _json_safe(assessments.items),
            "evidence": _json_safe(latest_assessment.evidence if latest_assessment else ()),
            "improvements": list(latest_assessment.improvements) if latest_assessment else [],
            "workflowState": latest_report.submission_state if latest_report else "not_due",
            "hrContactState": introduction.state if introduction else "introduction_pending",
            "accessHistory": _json_safe(access_history.items),
            "createdAt": agent.created_at,
            "updatedAt": agent.updated_at,
        }
        projected = HRDisclosurePolicy.project(
            record,
            caller=HRCaller.human(),
            target_ai_id=ai_id,
            requested_scope="full",
        )
        projected["reportNextCursor"] = reports.next_cursor
        projected["assessmentNextCursor"] = assessments.next_cursor
        projected["identityNextCursor"] = identity_history.next_cursor
        projected["accessNextCursor"] = access_history.next_cursor
        return HRServiceResult(200, {"ok": True, "agent": projected})

    def access_log(
        self,
        *,
        target_ai_id: str | None = None,
        viewer_ai_id: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> HRServiceResult:
        self._observability.increment("query.requests_total")
        page = self._repository.list_access_log(
            target_ai_id=target_ai_id,
            viewer_ai_id=viewer_ai_id,
            limit=self._limit(limit),
            cursor=cursor,
        )
        return HRServiceResult(
            200,
            {"ok": True, "items": _json_safe(page.items), "nextCursor": page.next_cursor},
        )

    def health(self) -> HRServiceResult:
        self._observability.increment("query.requests_total")
        snapshot = self._observability.health(
            self._repository.management_health(),
            feature_enabled=self._config.enabled,
            scheduler_enabled=self._effective_schedule_settings().enabled,
        )
        return HRServiceResult(200, {"ok": True, "health": _json_safe(snapshot)})

    def export(
        self,
        table: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
        max_bytes: int = 256_000,
    ) -> HRServiceResult:
        self._observability.increment("query.requests_total")
        page = self._repository.management_export(
            table,
            limit=self._limit(limit),
            cursor=cursor,
            max_bytes=max_bytes,
        )
        return HRServiceResult(200, {"ok": True, "export": _json_safe(page)})

    def lifecycle_command(
        self,
        action: str,
        body: object,
        *,
        body_bytes: int,
    ) -> HRServiceResult:
        if not self._config.enabled:
            raise HRAPIDisabledError("Human Resources mutations are disabled")
        payload = self._body(body, body_bytes)
        if payload:
            raise HRAPIValidationError("lifecycle command body must be empty")
        if action not in {"pause", "resume"}:
            raise HRAPIValidationError("unsupported lifecycle action")
        state = self._lifecycle.pause() if action == "pause" else self._lifecycle.resume()
        return HRServiceResult(200, {"ok": True, "hr": _json_safe(state)})

    def schedule_command(self, body: object, *, body_bytes: int) -> HRServiceResult:
        if not self._config.enabled:
            raise HRAPIDisabledError("Human Resources mutations are disabled")
        payload = self._body(body, body_bytes)
        settings = self._schedule_settings.update(payload)
        return HRServiceResult(
            200,
            {
                "ok": True,
                "schedule": {
                    "enabled": settings.enabled,
                    "dailyTime": settings.daily_time_text,
                    "timezone": self._config.timezone_name,
                },
            },
        )

    def cycle_command(
        self,
        action: str,
        body: object,
        *,
        body_bytes: int,
    ) -> HRServiceResult:
        if not self._config.enabled:
            raise HRAPIDisabledError("Human Resources mutations are disabled")
        payload = self._body(body, body_bytes)
        if action == "run":
            if payload:
                raise HRAPIValidationError("run command body must be empty")
            receipt = self._commands.run()
        elif action in {"close", "retry"}:
            if set(payload) != {"cycleId"}:
                raise HRAPIValidationError(f"{action} command requires only cycleId")
            cycle_id = payload.get("cycleId")
            if not isinstance(cycle_id, str) or not cycle_id.strip():
                raise HRAPIValidationError("cycleId is invalid")
            receipt = (
                self._commands.close(cycle_id)
                if action == "close"
                else self._commands.retry(cycle_id)
            )
        else:
            raise HRAPIValidationError("unsupported cycle action")
        return HRServiceResult(
            202 if receipt.accepted else 503,
            {"ok": receipt.accepted, "command": _json_safe(receipt)},
        )

    def directory_sync_command(self, body: object, *, body_bytes: int) -> HRServiceResult:
        if not self._config.enabled:
            raise HRAPIDisabledError("Human Resources mutations are disabled")
        payload = self._body(body, body_bytes)
        if payload:
            raise HRAPIValidationError("directory sync command body must be empty")
        if self._directory_sync is None:
            return HRServiceResult(503, {"ok": False, "code": "hr_directory_sync_unavailable"})
        self._observability.increment("directory.sync_requests_total")
        receipt = self._directory_sync.sync()
        accepted = bool(getattr(receipt, "accepted", False))
        return HRServiceResult(
            202 if accepted else 409,
            {
                "ok": accepted,
                **({} if accepted else {"code": "hr_directory_sync_running"}),
                "command": _json_safe(receipt),
            },
        )

    def information_completion_command(
        self,
        body: object,
        *,
        body_bytes: int,
    ) -> HRServiceResult:
        if not self._config.enabled:
            raise HRAPIDisabledError("Human Resources mutations are disabled")
        payload = self._body(body, body_bytes)
        if payload:
            raise HRAPIValidationError("information completion command body must be empty")
        if self._information_completion is None:
            return HRServiceResult(
                503,
                {"ok": False, "code": "hr_information_completion_unavailable"},
            )
        lifecycle = self._lifecycle.public_state(ensure=False)
        lifecycle_status = str(lifecycle.get("status") or "").strip().lower()
        if bool(lifecycle.get("paused")) or lifecycle_status not in {
            "idle",
            "ready",
            "available",
            "working",
        }:
            return HRServiceResult(
                409,
                {"ok": False, "code": "hr_information_completion_hr_unavailable"},
            )
        receipt = self._information_completion.complete()
        accepted = bool(getattr(receipt, "accepted", False))
        return HRServiceResult(
            202 if accepted else 409,
            {
                "ok": accepted,
                **(
                    {}
                    if accepted
                    else {"code": "hr_information_completion_running"}
                ),
                "command": _json_safe(receipt),
            },
        )

    def manual_daily_sync_command(self, body: object, *, body_bytes: int) -> HRServiceResult:
        if not self._config.enabled:
            raise HRAPIDisabledError("Human Resources mutations are disabled")
        payload = self._body(body, body_bytes)
        if set(payload) != {"agentIds"}:
            raise HRAPIValidationError("manual daily sync requires only agentIds")
        agent_ids = payload.get("agentIds")
        if not isinstance(agent_ids, list):
            raise HRAPIValidationError("agentIds must be a list")
        lifecycle = self._lifecycle.public_state(ensure=False)
        lifecycle_status = str(lifecycle.get("status") or "").strip().lower()
        if bool(lifecycle.get("paused")) or lifecycle_status not in {"idle", "ready", "available", "working"}:
            return HRServiceResult(409, {"ok": False, "code": "hr_manual_daily_sync_hr_unavailable"})
        if self._manual_daily_sync is None:
            return HRServiceResult(503, {"ok": False, "code": "hr_manual_daily_sync_unavailable"})
        try:
            receipt = self._manual_daily_sync.run(tuple(agent_ids))
        except Exception as exc:
            if getattr(exc, "code", "") == "hr_manual_daily_sync_validation_failed":
                return HRServiceResult(
                    400,
                    {"ok": False, "code": "hr_manual_daily_sync_validation_failed"},
                )
            raise
        accepted = bool(getattr(receipt, "accepted", False))
        return HRServiceResult(
            202 if accepted else 409,
            {"ok": accepted, **({} if accepted else {"code": "hr_manual_daily_sync_running"}), "command": _json_safe(receipt)},
        )

    @staticmethod
    def safe_error(exc: Exception) -> HRServiceResult:
        if isinstance(exc, HRAPIDisabledError):
            return HRServiceResult(503, {"ok": False, "code": exc.code})
        if isinstance(exc, HRAPIValidationError):
            status = 413 if "too large" in str(exc) else 400
            return HRServiceResult(status, {"ok": False, "code": exc.code, "error": str(exc)})
        if isinstance(exc, HRScheduleSettingsValidationError):
            return HRServiceResult(400, {"ok": False, "code": exc.code})
        if isinstance(exc, HRRepositoryError):
            return HRServiceResult(409, {"ok": False, "code": exc.code})
        return HRServiceResult(500, {"ok": False, "code": "hr_internal_error"})
