"""Dependency construction for the Agent Management application boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services.agent_management_confirmations import (
    AgentManagementConfirmationService,
)
from services.agent_management_http import AgentManagementHTTPRoutes
from services.agent_profile_configuration import AgentProfileConfigurationService
from services.agent_profile_mutations import AgentProfileMutationAPI
from services.agent_profile_store import AgentProfileStore


@dataclass(frozen=True, slots=True)
class AgentManagementRuntime:
    routes: AgentManagementHTTPRoutes
    profiles: AgentProfileStore
    mutations: AgentProfileMutationAPI
    confirmations: AgentManagementConfirmationService


def build_agent_management_runtime(
    *,
    status_dir: str | Path,
) -> AgentManagementRuntime:
    root = Path(status_dir)
    profiles = AgentProfileStore(
        root / "agent-management" / "profiles.json",
        legacy_office_config_path=root / "office-config.json",
    )
    configuration = AgentProfileConfigurationService(profiles)
    mutations = AgentProfileMutationAPI(configuration, profiles)
    confirmations = AgentManagementConfirmationService()
    routes = AgentManagementHTTPRoutes(
        profiles=profiles,
        mutations=mutations,
        confirmations=confirmations,
    )
    return AgentManagementRuntime(
        routes=routes,
        profiles=profiles,
        mutations=mutations,
        confirmations=confirmations,
    )
