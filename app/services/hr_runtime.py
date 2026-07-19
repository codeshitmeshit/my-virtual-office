"""Focused dependency composition for Human Resources application APIs."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from services.hr_agent_api import HRAgentAPI
from services.hr_agent_auth import HRAgentAuthenticator
from services.hr_api import HRLifecyclePort, HRManagementAPI, HRManualCommandsPort
from services.hr_config import HRConfig
from services.hr_directory import HRDirectoryQuery
from services.hr_information_completion import (
    CallableHRInformationConversation,
    HRInformationCompletionCommands,
    HRInformationCompletionService,
)
from services.hr_assessments import HRAssessmentOrchestrator
from services.hr_evidence import HREvidenceCollector, HREvidencePorts
from services.hr_manual_daily_sync import (
    CallableHRManualDailyConversation,
    EmptyHREvidencePort,
    HRManualDailySyncCommands,
    HRManualDailySyncService,
)
from services.hr_http import HRHTTPRoutes
from services.hr_observability import HRObservability
from services.hr_reporting import HRDailyReportNormalizer, HRReportingProjection, HRReportingService
from services.hr_repository import HRRepository
from services.hr_scheduler import HRCommandReceipt, HRManualCommands, HRReconciliationLoop
from services.hr_team_sync import build_hr_team_sync


class HRCommandRouter:
    """Keeps HTTP command wiring stable while the scheduler loop is installed lazily."""

    def __init__(self):
        self._lock = threading.Lock()
        self._commands: HRManualCommandsPort | None = None

    def install(self, commands: HRManualCommandsPort) -> None:
        if not all(
            callable(getattr(commands, method, None))
            for method in ("run", "close", "retry")
        ):
            raise TypeError("HR manual commands are invalid")
        with self._lock:
            self._commands = commands

    def install_loop(self, loop: HRReconciliationLoop) -> None:
        self.install(HRManualCommands(loop))

    def _call(self, action: str, cycle_id: str | None = None) -> HRCommandReceipt:
        with self._lock:
            commands = self._commands
        if commands is None:
            return HRCommandReceipt(uuid.uuid4().hex, action, False)
        method = getattr(commands, action)
        return method() if cycle_id is None else method(cycle_id)

    def run(self) -> HRCommandReceipt:
        return self._call("run")

    def close(self, cycle_id: str) -> HRCommandReceipt:
        return self._call("close", cycle_id)

    def retry(self, cycle_id: str) -> HRCommandReceipt:
        return self._call("retry", cycle_id)


@dataclass(frozen=True, slots=True)
class HRApplicationRuntime:
    repository: HRRepository
    observability: HRObservability
    routes: HRHTTPRoutes


def build_hr_application_runtime(
    *,
    status_dir: str | Path,
    lifecycle: HRLifecyclePort,
    config: HRConfig,
    commands: HRManualCommandsPort,
    roster_provider: Callable[[bool], Sequence[Mapping[str, object]]] | None = None,
    workspace_base: str | Path | None = None,
    information_conversation: CallableHRInformationConversation | None = None,
    daily_conversation: CallableHRManualDailyConversation | None = None,
) -> HRApplicationRuntime:
    """Build one repository authority shared by management and authenticated Agent APIs."""
    repository = HRRepository(status_dir)
    repository.initialize()
    observability = HRObservability()
    directory_sync = None
    if roster_provider is not None:
        if workspace_base is None:
            raise ValueError("workspace_base is required for roster sync")
        directory_sync = build_hr_team_sync(
            repository,
            roster_provider=roster_provider,
            workspace_base=workspace_base,
        )
    information_completion = None
    if information_conversation is not None:
        information_completion = HRInformationCompletionCommands(
            HRInformationCompletionService(
                repository,
                information_conversation,
                max_workers=config.max_workers,
                timeout_seconds=config.agent_timeout_seconds,
            )
        )
    manual_daily_sync = None
    if daily_conversation is not None:
        reporting = HRReportingService(
            repository,
            claim_token_factory=lambda request_id: f"hr-manual-{uuid.uuid4().hex}-{request_id}",
            claim_lease_seconds=min(600, max(31, int(config.agent_timeout_seconds) + 30)),
        )
        evidence_port = EmptyHREvidencePort()
        evidence = HREvidenceCollector(
            HREvidencePorts(
                evidence_port, evidence_port, evidence_port,
                evidence_port, evidence_port, evidence_port,
            )
        )
        normalizer = HRDailyReportNormalizer(
            repository, daily_conversation, timeout_seconds=config.agent_timeout_seconds,
        )
        assessments = HRAssessmentOrchestrator(
            repository,
            evidence,
            daily_conversation,
            timeout_seconds=config.agent_timeout_seconds,
            claim_lease_seconds=min(600, max(31, int(config.agent_timeout_seconds) + 30)),
        )
        manual_daily_sync = HRManualDailySyncCommands(
            HRManualDailySyncService(
                repository,
                reporting,
                normalizer,
                assessments,
                daily_conversation,
                timezone_name=config.timezone_name,
                submission_window_minutes=config.submission_window_minutes,
                max_workers=config.max_workers,
                timeout_seconds=config.agent_timeout_seconds,
            )
        )
    management = HRManagementAPI(
        repository,
        lifecycle,
        commands,
        HRReportingProjection(repository),
        observability,
        config,
        directory_sync=directory_sync,
        information_completion=information_completion,
        manual_daily_sync=manual_daily_sync,
    )
    routes = HRHTTPRoutes(
        management,
        HRAgentAuthenticator(repository),
        HRAgentAPI(repository, HRDirectoryQuery(repository)),
    )
    return HRApplicationRuntime(repository, observability, routes)
