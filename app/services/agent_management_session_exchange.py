"""Same-origin browser exchange policy for Agent Management launch codes."""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping

from services.agent_management_sessions import (
    AgentManagementLaunchCodeExpiredError,
    AgentManagementLaunchCodeUnavailableError,
    AgentManagementSessionCapacityError,
    AgentManagementSessionService,
)


SESSION_COOKIE_NAME = "vo_agent_management_session"
SESSION_COOKIE_PATH = "/api/agent-management/browser"
SESSION_REDIRECT_LOCATION = "/#agent-management"


@dataclass(frozen=True, slots=True)
class AgentManagementExchangeRequest:
    code: str | None
    host: str | None
    origin: str | None
    referer: str | None
    fetch_site: str | None
    secure: bool = False


@dataclass(frozen=True, slots=True)
class AgentManagementExchangeResponse:
    status: int
    headers: Mapping[str, str]
    payload: dict[str, object] | None = None

    def body(self) -> bytes:
        if self.payload is None:
            return b""
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


class AgentManagementSessionExchangeService:
    """Exchange one launch code without exposing the browser session to JS."""

    def __init__(
        self,
        sessions: AgentManagementSessionService,
        *,
        now: Callable[[], datetime] | None = None,
    ):
        if not isinstance(sessions, AgentManagementSessionService):
            raise TypeError("sessions must be an AgentManagementSessionService")
        self._sessions = sessions
        self._now = now or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _base_headers() -> dict[str, str]:
        return {
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        }

    @staticmethod
    def _authority(value: str | None) -> str:
        return str(value or "").strip().lower()

    @classmethod
    def _url_matches_host(cls, value: str | None, host: str) -> bool:
        if value is None:
            return True
        raw = str(value).strip()
        if not raw or raw == "null":
            return False
        try:
            parsed = urllib.parse.urlsplit(raw)
        except ValueError:
            return False
        return (
            parsed.scheme in {"http", "https"}
            and cls._authority(parsed.netloc) == host
        )

    @classmethod
    def _same_origin(cls, request: AgentManagementExchangeRequest) -> bool:
        host = cls._authority(request.host)
        if not host:
            return False
        fetch_site = str(request.fetch_site or "").strip().lower()
        if fetch_site and fetch_site not in {"same-origin", "none"}:
            return False
        return cls._url_matches_host(
            request.origin, host
        ) and cls._url_matches_host(request.referer, host)

    def _error(self, status: int, code: str) -> AgentManagementExchangeResponse:
        headers = self._base_headers()
        headers["Content-Type"] = "application/json"
        return AgentManagementExchangeResponse(
            status,
            headers,
            {"ok": False, "code": code},
        )

    def exchange(
        self, request: AgentManagementExchangeRequest
    ) -> AgentManagementExchangeResponse:
        if not isinstance(request, AgentManagementExchangeRequest):
            raise TypeError("request must be an AgentManagementExchangeRequest")
        if not self._same_origin(request):
            return self._error(403, "agent_management_exchange_origin_forbidden")
        code = request.code
        if not isinstance(code, str) or not 32 <= len(code) <= 512:
            return self._error(400, "agent_management_launch_code_invalid")
        try:
            session = self._sessions.exchange_launch_code(code)
        except AgentManagementLaunchCodeExpiredError:
            return self._error(410, "agent_management_launch_code_expired")
        except AgentManagementLaunchCodeUnavailableError:
            return self._error(410, "agent_management_launch_code_unavailable")
        except AgentManagementSessionCapacityError:
            return self._error(429, "agent_management_session_capacity")
        now = self._now()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise RuntimeError("exchange clock must be timezone-aware")
        max_age = max(
            1,
            int(
                (
                    session.absolute_expires_at
                    - now.astimezone(timezone.utc)
                ).total_seconds()
            ),
        )
        cookie = (
            f"{SESSION_COOKIE_NAME}={session.token}; "
            f"Path={SESSION_COOKIE_PATH}; Max-Age={max_age}; "
            "HttpOnly; SameSite=Strict"
        )
        if request.secure:
            cookie += "; Secure"
        headers = self._base_headers()
        headers.update(
            {
                "Location": SESSION_REDIRECT_LOCATION,
                "Set-Cookie": cookie,
            }
        )
        return AgentManagementExchangeResponse(303, headers)


def build_agent_management_session_exchange(
    sessions: AgentManagementSessionService,
) -> AgentManagementSessionExchangeService:
    return AgentManagementSessionExchangeService(sessions)
