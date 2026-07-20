"""Transport-independent queries for trusted Human Resources Agent identities."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from services.hr_agent_auth import AuthenticatedHRAgent
from services.hr_directory import HRDirectoryQuery
from services.hr_governance import HRCaller, HRDisclosurePolicy, HRGovernanceError
from services.hr_repository import HRRepository, HRRepositoryError


class HRAgentAPIValidationError(ValueError):
    code = "hr_agent_api_validation_failed"


class HRAgentAuditError(RuntimeError):
    code = "hr_audit_unavailable"


@dataclass(frozen=True, slots=True)
class HRAgentServiceResult:
    status: int
    payload: dict[str, Any]


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def _json_safe(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {_camel(field.name): _json_safe(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_safe(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


class HRAgentAPI:
    """Returns governed directory, detail, and self-audit projections."""

    def __init__(
        self,
        repository: HRRepository,
        directory: HRDirectoryQuery,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        if not isinstance(repository, HRRepository):
            raise HRAgentAPIValidationError("repository must be an HRRepository")
        if not isinstance(directory, HRDirectoryQuery):
            raise HRAgentAPIValidationError("directory must be an HRDirectoryQuery")
        self._repository = repository
        self._directory = directory
        self._clock = clock

    @staticmethod
    def _caller(identity: AuthenticatedHRAgent) -> HRCaller:
        if not isinstance(identity, AuthenticatedHRAgent):
            raise HRAgentAPIValidationError("authenticated Agent identity is required")
        return HRCaller.agent(identity.ai_id)

    @staticmethod
    def _limit(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
            raise HRAgentAPIValidationError("limit must be between 1 and 100")
        return value

    @staticmethod
    def _occurrence_key(value: str) -> str:
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 256
            or any(character.isspace() or ord(character) < 33 for character in value)
        ):
            raise HRAgentAPIValidationError("request occurrence key is invalid")
        return value

    def _now(self) -> str:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise HRAgentAPIValidationError("API clock must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()

    def directory(
        self,
        identity: AuthenticatedHRAgent,
        *,
        availability: str | None = None,
        readiness: str | None = None,
        query: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> HRAgentServiceResult:
        self._caller(identity)
        page = self._directory.list(
            availability=availability,
            readiness=readiness,
            query=query,
            limit=self._limit(limit),
            cursor=cursor,
        )
        return HRAgentServiceResult(
            200,
            {"ok": True, "items": _json_safe(page.items), "nextCursor": page.next_cursor},
        )

    def _agent_record(self, ai_id: str, *, include_self_fields: bool) -> dict[str, object] | None:
        agent = self._repository.get_agent(ai_id)
        if agent is None:
            return None
        introduction = self._repository.get_current_introduction(ai_id)
        reports = self._repository.list_daily_reports(ai_id=ai_id, limit=20)
        assessments = self._repository.list_assessments(ai_id=ai_id, limit=20)
        latest_report = reports.items[0] if reports.items else None
        latest_assessment = assessments.items[0] if assessments.items else None
        normalized = latest_report.normalized if latest_report is not None else None
        record: dict[str, object] = {
            "aiId": agent.ai_id,
            "name": agent.name,
            "introduction": introduction.introduction if introduction else "",
            "availability": agent.availability if agent.status == "active" else "unavailable",
            "publicWorkSummary": (
                normalized.get("completedWork", []) if isinstance(normalized, dict) else []
            ),
            "workload": (
                latest_assessment.workload
                if latest_assessment is not None
                else "insufficient_information"
            ),
        }
        if include_self_fields:
            access_page = self._repository.list_access_log(target_ai_id=ai_id, limit=100)
            record.update(
                {
                    "reports": _json_safe(reports.items),
                    "assessments": _json_safe(assessments.items),
                    "improvements": (
                        list(latest_assessment.improvements) if latest_assessment else []
                    ),
                    "workflowState": (
                        latest_report.submission_state if latest_report else "not_due"
                    ),
                    "hrContactState": (
                        introduction.state if introduction else "introduction_pending"
                    ),
                    "accessHistory": _json_safe(access_page.items),
                }
            )
        return record

    def agent_detail(
        self,
        identity: AuthenticatedHRAgent,
        target_ai_id: str,
        *,
        occurrence_key: str,
    ) -> HRAgentServiceResult:
        caller = self._caller(identity)
        is_self = caller.ai_id == target_ai_id
        record = self._agent_record(target_ai_id, include_self_fields=is_self)
        if record is None:
            return HRAgentServiceResult(404, {"ok": False, "code": "hr_agent_not_found"})
        projected = HRDisclosurePolicy.project(
            record,
            caller=caller,
            target_ai_id=target_ai_id,
            requested_scope="self" if is_self else "public",
        )
        if not is_self:
            occurrence_key = self._occurrence_key(occurrence_key)
            digest = hashlib.sha256(
                f"{occurrence_key}\0{caller.ai_id}\0{target_ai_id}".encode("utf-8")
            ).hexdigest()
            try:
                self._repository.record_successful_access(
                    access_id=f"hr-access:{digest}",
                    viewer_ai_id=caller.ai_id,
                    target_ai_id=target_ai_id,
                    viewed_at=self._now(),
                    scope="public_work_summary",
                    request_source="agent-human-resources-api",
                    occurrence_key=occurrence_key,
                )
            except HRRepositoryError as exc:
                raise HRAgentAuditError("cross-Agent disclosure audit could not be committed") from exc
        return HRAgentServiceResult(200, {"ok": True, "agent": projected})

    def self_access_log(
        self,
        identity: AuthenticatedHRAgent,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> HRAgentServiceResult:
        caller = self._caller(identity)
        page = self._repository.list_access_log(
            target_ai_id=caller.ai_id,
            limit=self._limit(limit),
            cursor=cursor,
        )
        records = tuple(_json_safe(item) for item in page.items)
        projected = HRDisclosurePolicy.project_access_log(
            records,
            caller=caller,
            target_ai_id=caller.ai_id,
        )
        return HRAgentServiceResult(
            200,
            {"ok": True, "items": list(projected), "nextCursor": page.next_cursor},
        )

    @staticmethod
    def safe_error(exc: Exception) -> HRAgentServiceResult:
        if isinstance(exc, HRAgentAPIValidationError):
            return HRAgentServiceResult(400, {"ok": False, "code": exc.code})
        if isinstance(exc, HRGovernanceError):
            return HRAgentServiceResult(403, {"ok": False, "code": exc.code})
        if isinstance(exc, HRAgentAuditError):
            return HRAgentServiceResult(503, {"ok": False, "code": exc.code})
        if isinstance(exc, HRRepositoryError):
            return HRAgentServiceResult(503, {"ok": False, "code": "hr_repository_unavailable"})
        return HRAgentServiceResult(500, {"ok": False, "code": "hr_internal_error"})
