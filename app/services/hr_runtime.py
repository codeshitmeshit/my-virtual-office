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
from services.hr_http import HRHTTPRoutes
from services.hr_observability import HRObservability
from services.hr_reporting import HRReportingProjection
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
    repository_root: str | Path | None = None,
) -> HRApplicationRuntime:
    """Build one repository authority shared by management and authenticated Agent APIs."""
    repository = HRRepository(status_dir)
    repository.initialize()
    observability = HRObservability()
    directory_sync = None
    if roster_provider is not None:
        if workspace_base is None or repository_root is None:
            raise ValueError("workspace_base and repository_root are required for roster sync")
        directory_sync = build_hr_team_sync(
            repository,
            roster_provider=roster_provider,
            workspace_base=workspace_base,
            repository_root=repository_root,
        )
    management = HRManagementAPI(
        repository,
        lifecycle,
        commands,
        HRReportingProjection(repository),
        observability,
        config,
        directory_sync=directory_sync,
    )
    routes = HRHTTPRoutes(
        management,
        HRAgentAuthenticator(repository),
        HRAgentAPI(repository, HRDirectoryQuery(repository)),
    )
    return HRApplicationRuntime(repository, observability, routes)
