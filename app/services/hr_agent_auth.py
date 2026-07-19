"""Authentication boundary for loopback Human Resources Agent APIs."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from services.hr_repository import HRRepository, HRRepositoryError


HR_AGENT_ACTION = "human-resources"
_DUMMY_DIGEST = hashlib.sha256(b"vo-hr-missing-grant").hexdigest()


class HRAgentAuthenticationError(PermissionError):
    """A disclosure-safe authentication denial with a stable machine code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class HRAgentAuthRequest:
    remote_host: str
    origin: str | None
    action: str | None
    ai_id: str | None
    authorization: str | None


@dataclass(frozen=True, slots=True)
class AuthenticatedHRAgent:
    ai_id: str
    name: str
    provider_kind: str
    key_id: str


class HRAgentAuthenticator:
    """Binds one originless loopback request to one active Agent grant."""

    def __init__(
        self,
        repository: HRRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        supported_provider_kinds: frozenset[str] = frozenset({"openclaw"}),
    ):
        if not isinstance(repository, HRRepository):
            raise TypeError("repository must be an HRRepository")
        providers = frozenset(str(value).strip() for value in supported_provider_kinds)
        if not providers or "" in providers:
            raise ValueError("supported_provider_kinds must not be empty")
        self._repository = repository
        self._clock = clock
        self._supported_provider_kinds = providers

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

    @staticmethod
    def _bearer_secret(authorization: str | None) -> str:
        if not isinstance(authorization, str) or len(authorization) > 4_096:
            raise HRAgentAuthenticationError(
                "hr_agent_bearer_required", "A valid Human Resources bearer grant is required"
            )
        scheme, separator, secret = authorization.partition(" ")
        if (
            not separator
            or scheme.lower() != "bearer"
            or len(secret) < 32
            or any(character.isspace() for character in secret)
        ):
            raise HRAgentAuthenticationError(
                "hr_agent_bearer_required", "A valid Human Resources bearer grant is required"
            )
        return secret

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("Human Resources authentication clock must be timezone-aware")
        return value.astimezone(timezone.utc)

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
        ai_id = request.ai_id if isinstance(request.ai_id, str) else ""
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
        if agent.provider_kind not in self._supported_provider_kinds:
            raise HRAgentAuthenticationError(
                "hr_agent_provider_unsupported", "The requesting Agent provider is unsupported"
            )

        secret = self._bearer_secret(request.authorization)
        grant = self._repository.get_access_grant(agent.ai_id)
        presented_digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        expected_digest = grant.secret_digest if grant is not None else _DUMMY_DIGEST
        digest_matches = hmac.compare_digest(presented_digest, expected_digest)
        if grant is None:
            raise HRAgentAuthenticationError(
                "hr_agent_grant_missing", "The requesting Agent has no Human Resources grant"
            )
        if not digest_matches:
            raise HRAgentAuthenticationError(
                "hr_agent_grant_mismatch", "The Human Resources grant does not match the Agent"
            )
        if grant.status != "active":
            raise HRAgentAuthenticationError(
                "hr_agent_grant_revoked", "The Human Resources grant is revoked"
            )
        if grant.expires_at is None or datetime.fromisoformat(grant.expires_at) <= self._now():
            raise HRAgentAuthenticationError(
                "hr_agent_grant_expired", "The Human Resources grant is expired"
            )
        return AuthenticatedHRAgent(
            ai_id=agent.ai_id,
            name=agent.name,
            provider_kind=agent.provider_kind,
            key_id=grant.key_id,
        )
