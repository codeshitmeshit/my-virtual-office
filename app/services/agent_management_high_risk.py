"""Confirmed high-risk Agent Management command application service."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable, Mapping

from services.agent_management_confirmations import (
    AgentManagementConfirmationError,
    AgentManagementConfirmationService,
)
from services.agent_profile_configuration import ActorKind, ConfigurationActor
from services.agent_profile_store import AgentProfileStore, AgentProfileStoreError


@dataclass(frozen=True, slots=True)
class AgentManagementCommandResult:
    status: int
    payload: dict[str, object]


class AgentManagementHighRiskService:
    """Consume a payload-bound challenge before invoking an injected executor."""

    def __init__(
        self,
        *,
        profiles: AgentProfileStore,
        confirmations: AgentManagementConfirmationService,
        executor: Callable[[str, str, object, object], Mapping[str, object]],
    ):
        if not isinstance(profiles, AgentProfileStore):
            raise TypeError("profiles must be an AgentProfileStore")
        if not isinstance(confirmations, AgentManagementConfirmationService):
            raise TypeError("confirmations must be an AgentManagementConfirmationService")
        if not callable(executor):
            raise TypeError("executor must be callable")
        self._profiles = profiles
        self._confirmations = confirmations
        self._executor = executor

    def execute(
        self,
        actor: ConfigurationActor,
        body: object,
    ) -> AgentManagementCommandResult:
        if not isinstance(actor, ConfigurationActor) or actor.kind is not ActorKind.HUMAN:
            return AgentManagementCommandResult(
                403, {"ok": False, "code": "agent_management_command_denied"}
            )
        if not isinstance(body, Mapping):
            return AgentManagementCommandResult(
                400, {"ok": False, "code": "agent_management_confirmation_invalid"}
            )
        required = {
            "challengeToken",
            "targetAiId",
            "action",
            "before",
            "after",
            "revision",
        }
        if set(body) != required:
            return AgentManagementCommandResult(
                400, {"ok": False, "code": "agent_management_confirmation_invalid"}
            )
        target = str(body.get("targetAiId") or "").strip()
        try:
            profile = self._profiles.get(target)
            current_revision = profile.revision if profile is not None else 0
            confirmed = self._confirmations.consume(
                actor,
                body,
                current_revision=current_revision,
            )
            raw = dict(
                self._executor(
                    confirmed.action,
                    confirmed.target_ai_id,
                    copy.deepcopy(body.get("before")),
                    copy.deepcopy(body.get("after")),
                )
            )
            status = int(raw.pop("_status", 200))
            if raw.get("ok") is not True and status < 400:
                status = 500
            return AgentManagementCommandResult(status, raw)
        except AgentManagementConfirmationError as exc:
            status = 403 if "denied" in exc.code else (
                409 if "conflict" in exc.code else (
                    410 if "expired" in exc.code else 400
                )
            )
            return AgentManagementCommandResult(
                status, {"ok": False, "code": exc.code}
            )
        except AgentProfileStoreError:
            return AgentManagementCommandResult(
                503, {"ok": False, "code": "agent_profile_store_unavailable"}
            )
        except Exception:
            return AgentManagementCommandResult(
                500, {"ok": False, "code": "agent_management_command_failed"}
            )
