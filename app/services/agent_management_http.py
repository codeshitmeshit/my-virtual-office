"""Transport-neutral route delegation for human Agent configuration APIs."""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Mapping

from services.agent_management_confirmations import (
    AgentManagementConfirmationError,
    AgentManagementConfirmationService,
)
from services.agent_management_high_risk import AgentManagementHighRiskService
from services.agent_profile_configuration import ConfigurationActor
from services.agent_profile_mutations import AgentProfileMutationAPI
from services.agent_profile_store import (
    AgentProfileStore,
    AgentProfileStoreError,
    AgentProfileValidationError,
)


PROFILE_PREFIX = "/api/agent-management/profiles/"
PROFILE_MUTATION_PATH = "/api/agent-management/profile/mutate"
PROFILE_UNDO_PATH = "/api/agent-management/profile/undo"
CONFIRMATION_PATH = "/api/agent-management/confirmations"
COMMAND_PATH = "/api/agent-management/commands"
POST_PATHS = frozenset(
    {PROFILE_MUTATION_PATH, PROFILE_UNDO_PATH, CONFIRMATION_PATH, COMMAND_PATH}
)


@dataclass(frozen=True, slots=True)
class AgentManagementHTTPResponse:
    status: int
    payload: dict[str, object]


class AgentManagementHTTPRoutes:
    """Map authenticated-human requests onto focused application services."""

    def __init__(
        self,
        *,
        profiles: AgentProfileStore,
        mutations: AgentProfileMutationAPI,
        confirmations: AgentManagementConfirmationService,
        high_risk: AgentManagementHighRiskService | None = None,
    ):
        if not isinstance(profiles, AgentProfileStore):
            raise TypeError("profiles must be an AgentProfileStore")
        if not isinstance(mutations, AgentProfileMutationAPI):
            raise TypeError("mutations must be an AgentProfileMutationAPI")
        if not isinstance(confirmations, AgentManagementConfirmationService):
            raise TypeError(
                "confirmations must be an AgentManagementConfirmationService"
            )
        self._profiles = profiles
        self._mutations = mutations
        self._confirmations = confirmations
        self._high_risk = high_risk

    @staticmethod
    def handles(method: str, path: str) -> bool:
        normalized_method = str(method or "").upper()
        normalized_path = str(path or "").split("?", 1)[0]
        if normalized_method == "GET":
            return normalized_path.startswith(PROFILE_PREFIX)
        if normalized_method == "POST":
            return normalized_path in POST_PATHS
        return False

    @staticmethod
    def _profile_ai_id(path: str) -> str | None:
        encoded = str(path or "")[len(PROFILE_PREFIX) :].strip("/")
        if not encoded or "/" in encoded:
            return None
        return urllib.parse.unquote(encoded).strip() or None

    def get(self, path: str) -> AgentManagementHTTPResponse:
        ai_id = self._profile_ai_id(path)
        if ai_id is None:
            return AgentManagementHTTPResponse(
                404, {"ok": False, "code": "agent_profile_not_found"}
            )
        try:
            profile = self._profiles.get(ai_id)
        except (AgentProfileValidationError, AgentProfileStoreError):
            return AgentManagementHTTPResponse(
                400, {"ok": False, "code": "agent_profile_request_invalid"}
            )
        if profile is None:
            return AgentManagementHTTPResponse(
                404, {"ok": False, "code": "agent_profile_not_found"}
            )
        return AgentManagementHTTPResponse(
            200, {"ok": True, "profile": profile.to_dict()}
        )

    def post(self, path: str, body: object) -> AgentManagementHTTPResponse:
        actor = ConfigurationActor.human()
        if path == PROFILE_MUTATION_PATH:
            result = self._mutations.mutate(actor, body)
            return AgentManagementHTTPResponse(result.status, result.payload)
        if path == PROFILE_UNDO_PATH:
            result = self._mutations.undo(actor, body)
            return AgentManagementHTTPResponse(result.status, result.payload)
        if path == CONFIRMATION_PATH:
            return self._issue_confirmation(actor, body)
        if path == COMMAND_PATH:
            if self._high_risk is None:
                return AgentManagementHTTPResponse(
                    503, {"ok": False, "code": "agent_management_command_unavailable"}
                )
            result = self._high_risk.execute(actor, body)
            return AgentManagementHTTPResponse(result.status, result.payload)
        return AgentManagementHTTPResponse(
            404, {"ok": False, "code": "agent_management_route_not_found"}
        )

    def _issue_confirmation(
        self,
        actor: ConfigurationActor,
        body: object,
    ) -> AgentManagementHTTPResponse:
        required = {"targetAiId", "action", "before", "after", "revision"}
        if not isinstance(body, Mapping) or set(body) != required:
            return AgentManagementHTTPResponse(
                400,
                {
                    "ok": False,
                    "code": "agent_management_confirmation_invalid",
                },
            )
        try:
            challenge = self._confirmations.issue(
                actor,
                target_ai_id=body.get("targetAiId"),
                action=body.get("action"),
                before=body.get("before"),
                after=body.get("after"),
                revision=body.get("revision"),
            )
        except AgentManagementConfirmationError as exc:
            return AgentManagementHTTPResponse(
                400, {"ok": False, "code": exc.code}
            )
        except Exception:
            return AgentManagementHTTPResponse(
                500,
                {
                    "ok": False,
                    "code": "agent_management_confirmation_failed",
                },
            )
        return AgentManagementHTTPResponse(
            201, {"ok": True, "confirmation": challenge.to_dict()}
        )
