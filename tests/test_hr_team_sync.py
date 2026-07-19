"""Manual HR team discovery and directory enablement."""

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_directory import HRDirectoryService
from services.hr_repository import HRRepository
from services.hr_skill_publisher import HRDirectoryEnablementCoordinator, HRGrantManager, HRSkillPublisher
from services.hr_team_sync import HRTeamSyncService, HRTeamSyncValidationError


def test_manual_sync_force_refreshes_roster_and_persists_new_agents(tmp_path):
    repository = HRRepository(tmp_path / "status")
    repository.initialize()
    workspace_base = tmp_path / "workspaces"
    workspace = workspace_base / "new-agent"
    workspace.mkdir(parents=True)
    canonical = tmp_path / "canonical" / "SKILL.md"
    canonical.parent.mkdir()
    canonical.write_text("---\nname: vo-agent-directory\ndescription: safe\n---\n")
    coordinator = HRDirectoryEnablementCoordinator(
        repository,
        HRDirectoryService(repository),
        HRSkillPublisher(workspace_base=workspace_base, canonical_skill_path=canonical),
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
    assert result.skill_ready == 1
    assert result.grant_ready == 1
    assert repository.get_agent("new-agent").availability == "busy"
    assert repository.get_agent("new-agent").skill_readiness == "updated"
    assert repository.get_agent("codex-local").skill_readiness == "unsupported_provider"
    assert repository.get_agent("codex-local").name == "Codex Updated"
    assert repository.get_access_grant("new-agent").status == "active"


def test_manual_sync_marks_agents_missing_from_authoritative_roster_unreachable(tmp_path):
    repository = HRRepository(tmp_path / "status")
    repository.initialize()
    repository.upsert_agent(
        ai_id="old-agent", name="Old", agent_kind="project", provider_kind="openclaw",
        status="active", availability="available", source="vo-roster",
    )
    workspace_base = tmp_path / "workspaces"
    workspace_base.mkdir()
    canonical = tmp_path / "canonical" / "SKILL.md"
    canonical.parent.mkdir()
    canonical.write_text("---\nname: vo-agent-directory\ndescription: safe\n---\n")
    service = HRTeamSyncService(
        HRDirectoryEnablementCoordinator(
            repository,
            HRDirectoryService(repository),
            HRSkillPublisher(workspace_base=workspace_base, canonical_skill_path=canonical),
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
