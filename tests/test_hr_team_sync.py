"""Manual HR team discovery and trusted-provider directory synchronization."""

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_command_status import HRCommandStatusTracker
from services.hr_directory import HRDirectoryService
from services.hr_repository import HRRepository
from services.hr_team_sync import (
    HRTeamSyncCommands,
    HRTeamSyncService,
    HRTeamSyncValidationError,
)


def test_manual_sync_force_refreshes_and_accepts_all_registered_provider_kinds(tmp_path):
    repository = HRRepository(tmp_path / "status")
    repository.initialize()
    refresh_flags = []
    service = HRTeamSyncService(
        HRDirectoryService(repository),
        lambda force: refresh_flags.append(force) or [
            {"id": "openclaw-agent", "name": "OpenClaw", "providerKind": "openclaw", "status": "busy"},
            {"statusKey": "codex-local", "name": "Codex", "providerKind": "codex"},
            {"id": "codex-local", "name": "Codex Updated", "providerKind": "codex"},
            {"id": "hermes-default", "name": "Hermes", "providerKind": "hermes"},
            {"name": "malformed"},
        ],
    )

    result = service.sync()

    assert refresh_flags == [True]
    assert result.discovered == 3
    assert result.created == ("codex-local", "hermes-default", "openclaw-agent")
    assert repository.get_agent("openclaw-agent").availability == "busy"
    assert repository.get_agent("codex-local").name == "Codex Updated"
    assert repository.get_agent("hermes-default").provider_kind == "hermes"
    assert all(
        repository.get_access_grant(ai_id) is None
        for ai_id in ("openclaw-agent", "codex-local", "hermes-default")
    )
    assert not hasattr(result, "grant_ready")


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
    service = HRTeamSyncService(HRDirectoryService(repository), lambda _force: [])

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
        def reconcile(self, _snapshots):
            raise AssertionError("invalid snapshot must not reach reconciliation")

    service = HRTeamSyncService(Coordinator(), lambda _force: [{"name": "missing id"}])
    with pytest.raises(HRTeamSyncValidationError, match="no valid Agent identity"):
        service.sync()
    assert repository.get_agent("existing").status == "active"


def test_team_sync_command_exposes_processing_then_terminal_state(tmp_path):
    repository = HRRepository(tmp_path / "status")
    repository.initialize()

    class Coordinator:
        def reconcile(self, _snapshots):
            from types import SimpleNamespace
            return SimpleNamespace(
                created=(), updated=(), reactivated=(), inactivated=(),
                unchanged=(), failures=(),
            )

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
