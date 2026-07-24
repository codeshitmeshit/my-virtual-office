"""Trusted loopback boundary for minting Agent Management launch codes."""

from __future__ import annotations

import ipaddress
import urllib.parse
from dataclasses import dataclass

from services.agent_management_sessions import (
    AgentManagementSessionCapacityError,
    AgentManagementSessionService,
)
from services.hr_repository import HRRepository, HRRepositoryError


AGENT_MANAGEMENT_ACTION = "agent-management"
SESSION_MINT_PATH = "/api/agent-management/sessions"
SESSION_EXCHANGE_PATH = "/agent-management/exchange"


@dataclass(frozen=True, slots=True)
class AgentManagementMintRequest:
    remote_host: str
    origin: str | None
    action: str | None
    ai_id: str | None


@dataclass(frozen=True, slots=True)
class AgentManagementMintResponse:
    status: int
    payload: dict[str, object]


class AgentManagementSessionMintService:
    """Authenticate a self-declared active Agent and issue one launch code."""

    def __init__(
        self,
        repository: HRRepository,
        sessions: AgentManagementSessionService,
    ):
        if not isinstance(repository, HRRepository):
            raise TypeError("repository must be an HRRepository")
        if not isinstance(sessions, AgentManagementSessionService):
            raise TypeError("sessions must be an AgentManagementSessionService")
        self._repository = repository
        self.sessions = sessions

    @staticmethod
    def _loopback(remote_host: str) -> bool:
        value = str(remote_host or "").strip()
        if value.startswith("[") and value.endswith("]"):
            value = value[1:-1]
        try:
            return ipaddress.ip_address(value).is_loopback
        except ValueError:
            return False

    @staticmethod
    def _denied(status: int, code: str) -> AgentManagementMintResponse:
        return AgentManagementMintResponse(
            status,
            {"ok": False, "code": code},
        )

    def mint(
        self, request: AgentManagementMintRequest
    ) -> AgentManagementMintResponse:
        if not isinstance(request, AgentManagementMintRequest):
            raise TypeError("request must be an AgentManagementMintRequest")
        if not self._loopback(request.remote_host):
            return self._denied(
                403, "agent_management_loopback_required"
            )
        if request.origin is not None:
            return self._denied(
                403, "agent_management_browser_origin_forbidden"
            )
        if request.action != AGENT_MANAGEMENT_ACTION:
            return self._denied(
                400, "agent_management_action_required"
            )
        ai_id = request.ai_id.strip() if isinstance(request.ai_id, str) else ""
        if (
            not ai_id
            or len(ai_id) > 256
            or "/" in ai_id
            or "\\" in ai_id
            or any(ord(character) < 33 for character in ai_id)
        ):
            return self._denied(
                400, "agent_management_identity_required"
            )
        try:
            agent = self._repository.get_agent(ai_id)
        except HRRepositoryError:
            return self._denied(503, "agent_management_directory_unavailable")
        if agent is None:
            return self._denied(403, "agent_management_agent_unknown")
        if agent.status != "active":
            return self._denied(403, "agent_management_agent_inactive")
        try:
            launch = self.sessions.issue_launch_code(agent.ai_id)
        except AgentManagementSessionCapacityError:
            return self._denied(429, "agent_management_launch_rate_limited")
        launch_url = (
            SESSION_EXCHANGE_PATH
            + "?code="
            + urllib.parse.quote(launch.code, safe="")
        )
        return AgentManagementMintResponse(
            201,
            {
                "ok": True,
                "aiId": launch.ai_id,
                "launchCode": launch.code,
                "launchUrl": launch_url,
                "expiresAt": launch.expires_at.isoformat(),
            },
        )


def build_agent_management_session_mint(
    repository: HRRepository,
) -> AgentManagementSessionMintService:
    return AgentManagementSessionMintService(
        repository,
        AgentManagementSessionService(),
    )
