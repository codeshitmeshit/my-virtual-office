"""个人资产 Agent API 的可信本地身份边界。"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass


PERSONAL_ASSET_AGENT_ACTION = "personal-assets"


class PersonalAssetAgentAuthenticationError(PermissionError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class PersonalAssetAgentAuthRequest:
    remote_host: str
    origin: str | None
    action: str | None
    ai_id: str | None


@dataclass(frozen=True, slots=True)
class AuthenticatedPersonalAssetAgent:
    ai_id: str
    name: str
    provider_kind: str


class PersonalAssetAgentAuthenticator:
    def authenticate(
        self, request: PersonalAssetAgentAuthRequest
    ) -> AuthenticatedPersonalAssetAgent:
        if not isinstance(request, PersonalAssetAgentAuthRequest):
            raise TypeError("request must be a PersonalAssetAgentAuthRequest")
        host = str(request.remote_host or "").strip().strip("[]")
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            raise PersonalAssetAgentAuthenticationError(
                "personal_asset_agent_loopback_required",
                "Personal asset Agent API requires loopback",
            ) from exc
        if not address.is_loopback:
            raise PersonalAssetAgentAuthenticationError(
                "personal_asset_agent_loopback_required",
                "Personal asset Agent API requires loopback",
            )
        if request.origin is not None:
            raise PersonalAssetAgentAuthenticationError(
                "personal_asset_agent_browser_origin_forbidden",
                "Browser-originated personal asset Agent access is forbidden",
            )
        if request.action != PERSONAL_ASSET_AGENT_ACTION:
            raise PersonalAssetAgentAuthenticationError(
                "personal_asset_agent_action_required",
                "X-VO-Agent-Action: personal-assets is required",
            )
        ai_id = request.ai_id.strip() if isinstance(request.ai_id, str) else ""
        if not ai_id or len(ai_id) > 256 or any(ord(character) < 33 for character in ai_id):
            raise PersonalAssetAgentAuthenticationError(
                "personal_asset_agent_identity_required", "A valid Agent identity is required"
            )
        # Personal Assets belongs to the owner, not to HR governance. Any named local
        # VO Agent may maintain it; identity is retained only for audit/idempotency.
        return AuthenticatedPersonalAssetAgent(ai_id, ai_id, "vo-runtime")
