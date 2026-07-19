"""Manual discovery and reconciliation of the HR Agent team directory."""

from __future__ import annotations

import secrets
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence

from services.hr_directory import HRDirectoryService, RosterObservation, RosterSourceSnapshot
from services.hr_repository import HRRepository
from services.hr_skill_publisher import (
    HRDirectoryEnablementCoordinator,
    HRDirectoryEnablementResult,
    HRGrantManager,
    HRSkillPublisher,
    repository_directory_skill_path,
)


class HRTeamSyncValidationError(ValueError):
    code = "hr_team_sync_validation_failed"


class HRDirectoryCoordinatorPort(Protocol):
    def reconcile(
        self,
        snapshots: tuple[RosterSourceSnapshot, ...],
        provider_agents: Mapping[str, Mapping[str, object]],
    ) -> HRDirectoryEnablementResult: ...


@dataclass(frozen=True, slots=True)
class HRTeamSyncResult:
    discovered: int
    created: tuple[str, ...]
    updated: tuple[str, ...]
    reactivated: tuple[str, ...]
    inactivated: tuple[str, ...]
    unchanged: tuple[str, ...]
    failed: tuple[str, ...]
    skill_ready: int
    grant_ready: int


class HRTeamSyncService:
    """Force-refresh the VO roster, then persist directory enablement per Agent."""

    def __init__(
        self,
        coordinator: HRDirectoryCoordinatorPort,
        roster_provider: Callable[[bool], Sequence[Mapping[str, object]]],
    ):
        if not callable(getattr(coordinator, "reconcile", None)):
            raise HRTeamSyncValidationError("coordinator is invalid")
        if not callable(roster_provider):
            raise HRTeamSyncValidationError("roster provider is invalid")
        self._coordinator = coordinator
        self._roster_provider = roster_provider
        self._lock = threading.Lock()

    @staticmethod
    def _identity(agent: Mapping[str, object]) -> str:
        return str(agent.get("id") or agent.get("statusKey") or agent.get("agentId") or "").strip()

    @classmethod
    def _observation(cls, agent: Mapping[str, object]) -> RosterObservation | None:
        ai_id = cls._identity(agent)
        if not ai_id:
            return None
        name = str(agent.get("name") or ai_id).strip() or ai_id
        provider_kind = str(agent.get("providerKind") or "openclaw").strip() or "openclaw"
        explicit_kind = str(agent.get("agentKind") or "").strip().lower()
        if explicit_kind in {"system", "project", "external", "synthetic"}:
            agent_kind = explicit_kind
        elif ai_id in {"hr", "archive-manager"}:
            agent_kind = "system"
        elif str(agent.get("providerType") or "").strip() == "gateway-platform":
            agent_kind = "synthetic"
        else:
            agent_kind = "project"
        raw_status = str(agent.get("status") or "").strip().lower()
        if raw_status in {"deleted", "disabled"}:
            status = raw_status
            availability = "unavailable"
        else:
            status = "active"
            availability = str(agent.get("availability") or agent.get("presence") or "").strip().lower()
            if not availability and raw_status in {
                "available", "busy", "offline", "unavailable", "unreachable"
            }:
                availability = raw_status
            availability = availability or "available"
        return RosterObservation(
            ai_id=ai_id,
            name=name,
            agent_kind=agent_kind,
            provider_kind=provider_kind,
            status=status,
            availability=availability,
        )

    def sync(self) -> HRTeamSyncResult:
        with self._lock:
            roster = self._roster_provider(True)
            if isinstance(roster, (str, bytes)) or not isinstance(roster, Sequence):
                raise HRTeamSyncValidationError("roster provider returned an invalid snapshot")
            payloads: dict[str, Mapping[str, object]] = {}
            observations: dict[str, RosterObservation] = {}
            for raw in roster:
                if not isinstance(raw, Mapping):
                    continue
                observation = self._observation(raw)
                if observation is None:
                    continue
                payloads[observation.ai_id] = raw
                observations[observation.ai_id] = observation
            if roster and not observations:
                raise HRTeamSyncValidationError("roster snapshot contains no valid Agent identity")
            result = self._coordinator.reconcile(
                (RosterSourceSnapshot("vo-roster", tuple(observations.values())),), payloads
            )
            failed = tuple(item.ai_id for item in result.directory.failures)
            failed += tuple(item.ai_id for item in result.enablements if not item.persisted)
            return HRTeamSyncResult(
                discovered=len(observations),
                created=result.directory.created,
                updated=result.directory.updated,
                reactivated=result.directory.reactivated,
                inactivated=result.directory.inactivated,
                unchanged=result.directory.unchanged,
                failed=tuple(dict.fromkeys(failed)),
                skill_ready=sum(1 for item in result.enablements if item.skill.ready),
                grant_ready=sum(1 for item in result.enablements if item.grant.ready),
            )


def build_hr_team_sync(
    repository: HRRepository,
    *,
    roster_provider: Callable[[bool], Sequence[Mapping[str, object]]],
    workspace_base: str | Path,
    repository_root: str | Path,
) -> HRTeamSyncService:
    coordinator = HRDirectoryEnablementCoordinator(
        repository,
        HRDirectoryService(repository),
        HRSkillPublisher(
            workspace_base=workspace_base,
            canonical_skill_path=repository_directory_skill_path(repository_root),
        ),
        HRGrantManager(
            repository,
            workspace_base=workspace_base,
            secret_factory=lambda _ai_id: secrets.token_urlsafe(32),
            key_id_factory=lambda _ai_id: uuid.uuid4().hex,
        ),
    )
    return HRTeamSyncService(coordinator, roster_provider)
