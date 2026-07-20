"""Manual discovery and reconciliation of the HR Agent team directory."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, Sequence

from services.hr_directory import (
    DirectoryReconciliationResult,
    HRDirectoryService,
    RosterObservation,
    RosterSourceSnapshot,
)
from services.hr_repository import HRRepository
from services.hr_command_status import HRCommandStatusTracker
from services.system_agent_roles import HR_ROLE


class HRTeamSyncValidationError(ValueError):
    code = "hr_team_sync_validation_failed"


class HRDirectoryCoordinatorPort(Protocol):
    def reconcile(
        self,
        snapshots: tuple[RosterSourceSnapshot, ...],
    ) -> DirectoryReconciliationResult: ...


@dataclass(frozen=True, slots=True)
class HRTeamSyncResult:
    discovered: int
    created: tuple[str, ...]
    updated: tuple[str, ...]
    reactivated: tuple[str, ...]
    inactivated: tuple[str, ...]
    unchanged: tuple[str, ...]
    failed: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HRTeamSyncReceipt:
    command_id: str
    command: str
    accepted: bool


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
        is_hr = (
            HR_ROLE.matches_identity(ai_id)
            or HR_ROLE.matches_identity(agent.get("name"))
            or str(agent.get("systemRole") or agent.get("system_role") or "").strip()
            == HR_ROLE.role_key
        )
        name = HR_ROLE.display_name if is_hr else (str(agent.get("name") or ai_id).strip() or ai_id)
        provider_kind = str(agent.get("providerKind") or "openclaw").strip() or "openclaw"
        explicit_kind = str(agent.get("agentKind") or "").strip().lower()
        if explicit_kind in {"system", "project", "external", "synthetic"}:
            agent_kind = explicit_kind
        elif is_hr or ai_id == "archive-manager":
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
            observations: dict[str, RosterObservation] = {}
            for raw in roster:
                if not isinstance(raw, Mapping):
                    continue
                observation = self._observation(raw)
                if observation is None:
                    continue
                observations[observation.ai_id] = observation
            if roster and not observations:
                raise HRTeamSyncValidationError("roster snapshot contains no valid Agent identity")
            result = self._coordinator.reconcile(
                (RosterSourceSnapshot("vo-roster", tuple(observations.values())),)
            )
            failed = tuple(item.ai_id for item in result.failures)
            return HRTeamSyncResult(
                discovered=len(observations),
                created=result.created,
                updated=result.updated,
                reactivated=result.reactivated,
                inactivated=result.inactivated,
                unchanged=result.unchanged,
                failed=tuple(dict.fromkeys(failed)),
            )


class HRTeamSyncCommands:
    """Queue one roster synchronization and expose its durable execution state."""

    def __init__(
        self,
        service: HRTeamSyncService,
        tracker: HRCommandStatusTracker,
        *,
        submit: Callable[[Callable[[], None]], bool] | None = None,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ):
        if not isinstance(service, HRTeamSyncService):
            raise HRTeamSyncValidationError("team sync service is invalid")
        if not isinstance(tracker, HRCommandStatusTracker):
            raise HRTeamSyncValidationError("command status tracker is invalid")
        self._service = service
        self._tracker = tracker
        self._submit = submit or self._thread_submit
        self._new_id = new_id
        self._lock = threading.Lock()
        self._running = False

    @staticmethod
    def _thread_submit(callback: Callable[[], None]) -> bool:
        threading.Thread(target=callback, daemon=True, name="hr-team-sync").start()
        return True

    def sync(self) -> HRTeamSyncReceipt:
        command_id = self._new_id()
        with self._lock:
            if self._running:
                return HRTeamSyncReceipt(command_id, "sync", False)
            self._running = True
        try:
            self._tracker.accepted(command_id, "sync")
        except Exception:
            with self._lock:
                self._running = False
            raise

        def execute() -> None:
            try:
                self._tracker.running(command_id)
                result = self._service.sync()
                context = {
                    "discovered": result.discovered,
                    "created": len(result.created),
                    "updated": len(result.updated),
                    "reactivated": len(result.reactivated),
                    "inactivated": len(result.inactivated),
                    "failed": len(result.failed),
                }
                if result.failed:
                    self._tracker.failed(
                        command_id, "hr_team_sync_partial_failure", context=context
                    )
                else:
                    self._tracker.complete(
                        command_id,
                        message=f"discovered={result.discovered}, failed=0",
                        context=context,
                    )
            except Exception as exc:
                try:
                    self._tracker.failed(
                        command_id,
                        str(getattr(exc, "code", "hr_team_sync_failed")),
                    )
                except Exception:
                    pass
            finally:
                with self._lock:
                    self._running = False

        try:
            accepted = bool(self._submit(execute))
        except Exception:
            accepted = False
        if not accepted:
            try:
                self._tracker.failed(command_id, "hr_command_not_accepted")
            finally:
                with self._lock:
                    self._running = False
        return HRTeamSyncReceipt(command_id, "sync", accepted)


def build_hr_team_sync(
    repository: HRRepository,
    *,
    roster_provider: Callable[[bool], Sequence[Mapping[str, object]]],
) -> HRTeamSyncCommands:
    service = HRTeamSyncService(HRDirectoryService(repository), roster_provider)
    return HRTeamSyncCommands(service, HRCommandStatusTracker(repository))
