"""Route parsing and error normalization for Human Resources HTTP APIs."""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from services.hr_agent_api import HRAgentAPI, HRAgentServiceResult
from services.hr_agent_auth import (
    HRAgentAuthenticationError,
    HRAgentAuthenticator,
    HRAgentAuthRequest,
)
from services.hr_api import HRManagementAPI, HRServiceResult


MANAGEMENT_PREFIX = "/api/human-resources"
AGENT_PREFIX = "/api/agent-human-resources"


class HRHTTPValidationError(ValueError):
    code = "hr_http_validation_failed"


@dataclass(frozen=True, slots=True)
class HRHTTPResponse:
    status: int
    payload: dict[str, Any]


class HRHTTPRoutes:
    """Maps normalized HTTP inputs onto transport-free HR application services."""

    def __init__(
        self,
        management: HRManagementAPI,
        authenticator: HRAgentAuthenticator,
        agents: HRAgentAPI,
    ):
        if not isinstance(management, HRManagementAPI):
            raise HRHTTPValidationError("management API is invalid")
        if not isinstance(authenticator, HRAgentAuthenticator):
            raise HRHTTPValidationError("Agent authenticator is invalid")
        if not isinstance(agents, HRAgentAPI):
            raise HRHTTPValidationError("Agent API is invalid")
        self._management = management
        self._authenticator = authenticator
        self._agents = agents

    @staticmethod
    def handles(path: str) -> bool:
        return path == MANAGEMENT_PREFIX or path.startswith(
            f"{MANAGEMENT_PREFIX}/"
        ) or path == AGENT_PREFIX or path.startswith(f"{AGENT_PREFIX}/")

    @staticmethod
    def is_management(path: str) -> bool:
        return path == MANAGEMENT_PREFIX or path.startswith(f"{MANAGEMENT_PREFIX}/")

    @staticmethod
    def _value(
        query: Mapping[str, Sequence[str]],
        name: str,
        *,
        default: str | None = None,
    ) -> str | None:
        values = query.get(name)
        if values is None:
            return default
        if isinstance(values, (str, bytes)) or len(values) != 1:
            raise HRHTTPValidationError(f"query parameter {name} must occur once")
        value = values[0]
        if not isinstance(value, str):
            raise HRHTTPValidationError(f"query parameter {name} is invalid")
        return value

    @classmethod
    def _integer(
        cls,
        query: Mapping[str, Sequence[str]],
        name: str,
        *,
        default: int,
    ) -> int:
        value = cls._value(query, name)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError as exc:
            raise HRHTTPValidationError(f"query parameter {name} must be an integer") from exc

    @staticmethod
    def _segment(value: str) -> str:
        decoded = urllib.parse.unquote(value)
        if not decoded or "/" in decoded or "\\" in decoded or len(decoded) > 256:
            raise HRHTTPValidationError("route identifier is invalid")
        return decoded

    @staticmethod
    def _response(result: HRServiceResult | HRAgentServiceResult) -> HRHTTPResponse:
        return HRHTTPResponse(result.status, result.payload)

    @staticmethod
    def _validation_error(exc: Exception) -> HRHTTPResponse:
        return HRHTTPResponse(
            400,
            {"ok": False, "code": str(getattr(exc, "code", HRHTTPValidationError.code))},
        )

    def management_get(
        self,
        path: str,
        query: Mapping[str, Sequence[str]],
    ) -> HRHTTPResponse:
        try:
            if path == f"{MANAGEMENT_PREFIX}/overview":
                result = self._management.overview()
            elif path == f"{MANAGEMENT_PREFIX}/access-log":
                result = self._management.access_log(
                    target_ai_id=self._value(query, "targetAiId"),
                    viewer_ai_id=self._value(query, "viewerAiId"),
                    limit=self._integer(query, "limit", default=50),
                    cursor=self._value(query, "cursor"),
                )
            elif path == f"{MANAGEMENT_PREFIX}/health":
                result = self._management.health()
            elif path == f"{MANAGEMENT_PREFIX}/export":
                table = self._value(query, "table")
                if table is None:
                    raise HRHTTPValidationError("query parameter table is required")
                result = self._management.export(
                    table,
                    limit=self._integer(query, "limit", default=50),
                    cursor=self._value(query, "cursor"),
                    max_bytes=self._integer(query, "maxBytes", default=256_000),
                )
            elif path.startswith(f"{MANAGEMENT_PREFIX}/agents/"):
                ai_id = self._segment(path.removeprefix(f"{MANAGEMENT_PREFIX}/agents/"))
                result = self._management.agent_detail(
                    ai_id,
                    report_limit=self._integer(query, "reportLimit", default=20),
                    report_cursor=self._value(query, "reportCursor"),
                    assessment_limit=self._integer(query, "assessmentLimit", default=20),
                    assessment_cursor=self._value(query, "assessmentCursor"),
                    access_limit=self._integer(query, "accessLimit", default=20),
                    access_cursor=self._value(query, "accessCursor"),
                )
            else:
                return HRHTTPResponse(404, {"ok": False, "code": "hr_route_not_found"})
            return self._response(result)
        except HRHTTPValidationError as exc:
            return self._validation_error(exc)
        except Exception as exc:
            return self._response(self._management.safe_error(exc))

    def management_post(
        self,
        path: str,
        body: object,
        *,
        body_bytes: int,
    ) -> HRHTTPResponse:
        try:
            lifecycle_prefix = f"{MANAGEMENT_PREFIX}/hr/"
            cycle_prefix = f"{MANAGEMENT_PREFIX}/cycles/"
            if path == f"{MANAGEMENT_PREFIX}/directory/sync":
                result = self._management.directory_sync_command(body, body_bytes=body_bytes)
            elif path.startswith(lifecycle_prefix):
                action = self._segment(path.removeprefix(lifecycle_prefix))
                result = self._management.lifecycle_command(action, body, body_bytes=body_bytes)
            elif path.startswith(cycle_prefix):
                action = self._segment(path.removeprefix(cycle_prefix))
                result = self._management.cycle_command(action, body, body_bytes=body_bytes)
            else:
                return HRHTTPResponse(404, {"ok": False, "code": "hr_route_not_found"})
            return self._response(result)
        except HRHTTPValidationError as exc:
            return self._validation_error(exc)
        except Exception as exc:
            return self._response(self._management.safe_error(exc))

    def agent_get(
        self,
        path: str,
        query: Mapping[str, Sequence[str]],
        request: HRAgentAuthRequest,
        *,
        occurrence_key: str,
    ) -> HRHTTPResponse:
        try:
            identity = self._authenticator.authenticate(request)
            if path == f"{AGENT_PREFIX}/directory":
                result = self._agents.directory(
                    identity,
                    availability=self._value(query, "availability"),
                    readiness=self._value(query, "readiness"),
                    query=self._value(query, "query"),
                    limit=self._integer(query, "limit", default=50),
                    cursor=self._value(query, "cursor"),
                )
            elif path == f"{AGENT_PREFIX}/access-log/self":
                result = self._agents.self_access_log(
                    identity,
                    limit=self._integer(query, "limit", default=50),
                    cursor=self._value(query, "cursor"),
                )
            elif path.startswith(f"{AGENT_PREFIX}/agents/"):
                ai_id = self._segment(path.removeprefix(f"{AGENT_PREFIX}/agents/"))
                result = self._agents.agent_detail(
                    identity,
                    ai_id,
                    occurrence_key=occurrence_key,
                )
            else:
                return HRHTTPResponse(404, {"ok": False, "code": "hr_route_not_found"})
            return self._response(result)
        except HRAgentAuthenticationError as exc:
            return HRHTTPResponse(403, {"ok": False, "code": exc.code})
        except HRHTTPValidationError as exc:
            return self._validation_error(exc)
        except ValueError as exc:
            return self._validation_error(exc)
        except Exception as exc:
            return self._response(self._agents.safe_error(exc))
