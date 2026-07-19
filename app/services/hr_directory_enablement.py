"""HR directory reconciliation with independent Agent API grant readiness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from services.hr_agent_grants import HRGrantManager, HRGrantReadiness
from services.hr_directory import (
    DirectoryReconciliationResult,
    HRDirectoryService,
    RosterSourceSnapshot,
)
from services.hr_repository import HRRepository, HRRepositoryError


class HRDirectoryEnablementError(RuntimeError):
    code = "hr_directory_enablement_failed"


@dataclass(frozen=True, slots=True)
class HREnablementReadiness:
    ai_id: str
    grant: HRGrantReadiness
    persisted: bool
    error_code: str


@dataclass(frozen=True, slots=True)
class HRDirectoryEnablementResult:
    directory: DirectoryReconciliationResult
    enablements: tuple[HREnablementReadiness, ...]


class HRDirectoryEnablementCoordinator:
    """Commit directory state, then isolate per-Agent API grant refresh."""

    def __init__(
        self,
        repository: HRRepository,
        directory: HRDirectoryService,
        grants: HRGrantManager,
        *,
        hr_ai_id: str = "hr",
    ):
        self._repository = repository
        self._directory = directory
        self._grants = grants
        self._hr_ai_id = hr_ai_id

    def reconcile(
        self,
        snapshots: tuple[RosterSourceSnapshot, ...],
        provider_agents: Mapping[str, Mapping[str, object]],
    ) -> HRDirectoryEnablementResult:
        directory_result = self._directory.reconcile(snapshots)
        enablements = []
        for state in directory_result.agents:
            ai_id = state.agent.ai_id
            raw_payload = provider_agents.get(ai_id)
            payload = dict(raw_payload) if isinstance(raw_payload, Mapping) else {}
            payload.setdefault("id", ai_id)
            if ai_id == self._hr_ai_id:
                grant = HRGrantReadiness(ai_id, True, "not_required", "", "")
            else:
                try:
                    grant = self._grants.reconcile(payload, eligible=state.report_eligible)
                except Exception:
                    grant = HRGrantReadiness(
                        ai_id,
                        False,
                        "failed",
                        "",
                        "hr_grant_refresh_failed",
                    )
            persisted = False
            error_code = ""
            try:
                current = self._repository.get_agent(ai_id)
                if current is None:
                    raise HRDirectoryEnablementError("directory Agent disappeared")
                self._repository.update_agent_enablement(
                    ai_id=ai_id,
                    # Kept for schema compatibility. The skill is a VO built-in and
                    # no longer has per-Agent installation readiness.
                    skill_readiness="ready",
                    grant_readiness=grant.state,
                    expected_revision=current.revision,
                )
                persisted = True
            except (HRRepositoryError, HRDirectoryEnablementError) as exc:
                error_code = getattr(exc, "code", "hr_enablement_persist_failed")
            enablements.append(
                HREnablementReadiness(
                    ai_id=ai_id,
                    grant=grant,
                    persisted=persisted,
                    error_code=str(error_code),
                )
            )
        return HRDirectoryEnablementResult(directory_result, tuple(enablements))
