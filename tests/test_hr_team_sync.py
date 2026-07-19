"""Manual HR team discovery and directory enablement."""

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_directory import HRDirectoryService
from services.hr_agent_grants import HRGrantManager
from services.hr_directory_enablement import HRDirectoryEnablementCoordinator
from services.hr_repository import HRRepository
from services.hr_command_status import HRCommandStatusTracker
from services.hr_team_sync import (
    HRTeamSyncCommands,
    HRTeamSyncService,
    HRTeamSyncValidationError,
)


def test_manual_sync_force_refreshes_roster_and_persists_new_agents(tmp_path):
    repository = HRRepository(tmp_path / "status")
    repository.initialize()
    workspace_base = tmp_path / "workspaces"
    workspace = workspace_base / "new-agent"
    workspace.mkdir(parents=True)
    coordinator = HRDirectoryEnablementCoordinator(
        repository,
        HRDirectoryService(repository),
        HRGrantManager(
            repository,
            workspace_base=workspace_base,
            secret_factory=lambda ai_id: f"secret-{ai_id}-abcdefghijklmnopqrstuvwxyz123456",
            key_id_factory=lambda ai_id: f"key-{ai_id}",
        ),
    )
    refresh_flags = []
    service = HRTeamSyncService(
        coordinator,
        lambda force: refresh_flags.append(force) or [
            {
                "id": "new-agent",
                "name": "New Agent",
                "providerKind": "openclaw",
                "workspace": str(workspace),
                "status": "busy",
            },
            {"statusKey": "codex-local", "name": "Codex", "providerKind": "codex"},
            {"id": "codex-local", "name": "Codex Updated", "providerKind": "codex"},
            {"name": "malformed"},
        ],
    )

    result = service.sync()

    assert refresh_flags == [True]
    assert result.discovered == 2
    assert result.created == ("codex-local", "new-agent")
    assert result.grant_ready == 1
    assert repository.get_agent("new-agent").availability == "busy"
    assert repository.get_agent("new-agent").skill_readiness == "ready"
    assert repository.get_agent("codex-local").skill_readiness == "ready"
    assert repository.get_agent("codex-local").grant_readiness == "unsupported_provider"
    assert repository.get_agent("codex-local").name == "Codex Updated"
    assert repository.get_access_grant("new-agent").status == "active"
    assert not (workspace / "skills" / "vo-agent-directory").exists()


def test_hr_identity_name_is_always_canonical_uppercase():
    observation = HRTeamSyncService._observation(
        {"id": "provider-hr-legacy", "name": "Hr", "providerKind": "openclaw"}
    )
    assert observation is not None
    assert observation.name == "HR"
    assert observation.agent_kind == "system"


def test_manual_sync_marks_agents_missing_from_authoritative_roster_unreachable(tmp_path):
    repository = HRRepository(tmp_path / "status")
    repository.initialize()
    repository.upsert_agent(
        ai_id="old-agent", name="Old", agent_kind="project", provider_kind="openclaw",
        status="active", availability="available", source="vo-roster",
    )
    workspace_base = tmp_path / "workspaces"
    workspace_base.mkdir()
    service = HRTeamSyncService(
        HRDirectoryEnablementCoordinator(
            repository,
            HRDirectoryService(repository),
            HRGrantManager(
                repository,
                workspace_base=workspace_base,
                secret_factory=lambda _ai_id: "abcdefghijklmnopqrstuvwxyz1234567890",
                key_id_factory=lambda _ai_id: "key",
            ),
        ),
        lambda _force: [],
    )

    result = service.sync()

    assert result.inactivated == ("old-agent",)
    assert repository.get_agent("old-agent").status == "unreachable"


def test_malformed_nonempty_snapshot_fails_without_inactivating_existing_directory(tmp_path):
    repository = HRRepository(tmp_path / "status")
    repository.initialize()
    repository.upsert_agent(
        ai_id="existing", name="Existing", agent_kind="project", provider_kind="openclaw",
        status="active", availability="available", source="vo-roster",
    )

    class Coordinator:
        def reconcile(self, _snapshots, _payloads):
            raise AssertionError("invalid snapshot must not reach reconciliation")

    service = HRTeamSyncService(Coordinator(), lambda _force: [{"name": "missing id"}])
    with pytest.raises(HRTeamSyncValidationError, match="no valid Agent identity"):
        service.sync()
    assert repository.get_agent("existing").status == "active"


def test_team_sync_command_exposes_processing_then_terminal_state(tmp_path):
    repository = HRRepository(tmp_path / "status")
    repository.initialize()

    class Coordinator:
        def reconcile(self, _snapshots, _payloads):
            from types import SimpleNamespace
            directory = SimpleNamespace(
                created=(), updated=(), reactivated=(), inactivated=(),
                unchanged=(), failures=(),
            )
            return SimpleNamespace(directory=directory, enablements=())

    callbacks = []
    commands = HRTeamSyncCommands(
        HRTeamSyncService(Coordinator(), lambda _force: []),
        HRCommandStatusTracker(repository),
        submit=lambda callback: callbacks.append(callback) or True,
        new_id=iter(("sync-1", "sync-2")).__next__,
    )

    assert commands.sync().accepted is True
    assert commands.sync().accepted is False
    assert repository.list_active_hr_commands()[0].status == "accepted"
    callbacks.pop()()
    assert repository.list_active_hr_commands() == ()
    activity = repository.list_hr_activity().items[0]
    assert activity.action == "sync"
    assert activity.status == "complete"
