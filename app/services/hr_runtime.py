"""Focused dependency composition for Human Resources application APIs."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

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
) -> HRApplicationRuntime:
    """Build one repository authority shared by management and authenticated Agent APIs."""
    repository = HRRepository(status_dir)
    repository.initialize()
    observability = HRObservability()
    management = HRManagementAPI(
        repository,
        lifecycle,
        commands,
        HRReportingProjection(repository),
        observability,
        config,
    )
    routes = HRHTTPRoutes(
        management,
        HRAgentAuthenticator(repository),
        HRAgentAPI(repository, HRDirectoryQuery(repository)),
    )
    return HRApplicationRuntime(repository, observability, routes)
