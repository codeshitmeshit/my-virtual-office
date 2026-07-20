"""Trusted identity boundary for loopback Human Resources Agent APIs.

Virtual Office treats internal Agent interactions as trusted.  The caller
declares its stable AI ID, and this boundary verifies only that the request is
an originless loopback HR request for a currently active directory Agent.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from services.hr_repository import HRRepository, HRRepositoryError


HR_AGENT_ACTION = "human-resources"


class HRAgentAuthenticationError(PermissionError):
    """A disclosure-safe identity denial with a stable machine code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class HRAgentAuthRequest:
    remote_host: str
    origin: str | None
    action: str | None
    ai_id: str | None


@dataclass(frozen=True, slots=True)
class AuthenticatedHRAgent:
    ai_id: str
    name: str
    provider_kind: str


class HRAgentAuthenticator:
    """Accept a trusted VO Agent identity after directory and source checks."""

    def __init__(self, repository: HRRepository):
        if not isinstance(repository, HRRepository):
            raise TypeError("repository must be an HRRepository")
        self._repository = repository

    @staticmethod
    def _require_loopback(remote_host: str) -> None:
        value = str(remote_host or "").strip()
        if value.startswith("[") and value.endswith("]"):
            value = value[1:-1]
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise HRAgentAuthenticationError(
                "hr_agent_loopback_required", "Human Resources Agent API requires loopback"
            ) from exc
        if not address.is_loopback:
            raise HRAgentAuthenticationError(
                "hr_agent_loopback_required", "Human Resources Agent API requires loopback"
            )

    def authenticate(self, request: HRAgentAuthRequest) -> AuthenticatedHRAgent:
        if not isinstance(request, HRAgentAuthRequest):
            raise TypeError("request must be an HRAgentAuthRequest")
        self._require_loopback(request.remote_host)
        if request.origin is not None:
            raise HRAgentAuthenticationError(
                "hr_agent_browser_origin_forbidden", "Browser-originated HR Agent access is forbidden"
            )
        if request.action != HR_AGENT_ACTION:
            raise HRAgentAuthenticationError(
                "hr_agent_action_required", "The Human Resources Agent action header is required"
            )
        ai_id = request.ai_id.strip() if isinstance(request.ai_id, str) else ""
        if not ai_id or len(ai_id) > 256 or any(ord(character) < 33 for character in ai_id):
            raise HRAgentAuthenticationError(
                "hr_agent_identity_required", "A valid Human Resources Agent identity is required"
            )
        try:
            agent = self._repository.get_agent(ai_id)
        except HRRepositoryError as exc:
            raise HRAgentAuthenticationError(
                "hr_agent_unknown", "The requesting Agent is not registered"
            ) from exc
        if agent is None:
            raise HRAgentAuthenticationError(
                "hr_agent_unknown", "The requesting Agent is not registered"
            )
        if agent.status != "active":
            raise HRAgentAuthenticationError(
                "hr_agent_inactive", "The requesting Agent is not active"
            )
        return AuthenticatedHRAgent(
            ai_id=agent.ai_id,
            name=agent.name,
            provider_kind=agent.provider_kind,
        )
