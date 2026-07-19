"""Per-Agent HR grant issuance, secure delivery, rotation, and revocation."""

import hashlib
import json
import stat
import sys
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_repository import HRRepository, HRRepositoryError
from services.hr_skill_publisher import HRGrantManager, HRSkillPublisher


NOW = datetime(2026, 7, 19, 9, tzinfo=timezone.utc)


class Factory:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = []

    def __call__(self, ai_id):
        self.calls.append(ai_id)
        return next(self.values)


@pytest.fixture
def setup_grants(tmp_path):
    repository = HRRepository(tmp_path / "status", clock=lambda: NOW)
    repository.initialize()
    repository.upsert_agent(
        ai_id="agent-1",
        name="Agent 1",
        agent_kind="project",
        status="active",
        availability="available",
        source="test",
    )
    workspace_base = tmp_path / "workspaces"
    workspace = workspace_base / "agent-1"
    workspace.mkdir(parents=True)
    canonical = tmp_path / "canonical" / "SKILL.md"
    canonical.parent.mkdir()
    canonical.write_text(
        "---\nname: vo-agent-directory\ndescription: safe\n---\n\n# Directory\n"
    )
    publisher = HRSkillPublisher(
        workspace_base=workspace_base,
        canonical_skill_path=canonical,
    )
    assert publisher.publish(
        {"id": "agent-1", "providerKind": "openclaw", "workspace": str(workspace)}
    ).ready
    return repository, workspace_base, workspace, canonical


def agent(workspace, provider="openclaw"):
    return {"id": "agent-1", "providerKind": provider, "workspace": str(workspace)}


def manager(repository, base, secrets, keys):
    secret_factory = Factory(secrets)
    key_factory = Factory(keys)
    result = HRGrantManager(
        repository,
        workspace_base=base,
        secret_factory=secret_factory,
        key_id_factory=key_factory,
        clock=lambda: NOW,
    )
    return result, secret_factory, key_factory


def delivery_paths(workspace):
    secret = workspace / ".vo" / "credentials" / "human-resources" / "grant"
    reference = workspace / "skills" / "vo-agent-directory" / ".vo-hr-grant-ref.json"
    return secret, reference


def test_issue_stores_only_digest_and_delivers_secret_via_secure_reference(setup_grants):
    repository, base, workspace, canonical = setup_grants
    raw_secret = "grant_value_abcdefghijklmnopqrstuvwxyz123456"
    service, secret_factory, key_factory = manager(
        repository, base, [raw_secret], ["key-1"]
    )
    skill_before = canonical.read_text()
    result = service.reconcile(agent(workspace), eligible=True)
    assert result.ready is True
    assert result.state == "issued"
    assert result.key_id == "key-1"
    assert secret_factory.calls == key_factory.calls == ["agent-1"]

    stored = repository.get_access_grant("agent-1")
    assert stored.secret_digest == hashlib.sha256(raw_secret.encode()).hexdigest()
    secret_path, reference_path = delivery_paths(workspace)
    assert secret_path.read_text() == raw_secret
    assert json.loads(reference_path.read_text()) == {
        "grantFile": ".vo/credentials/human-resources/grant",
        "keyId": "key-1",
        "schemaVersion": 1,
    }
    assert stat.S_IMODE(secret_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(reference_path.stat().st_mode) == 0o600
    assert raw_secret not in reference_path.read_text()
    assert raw_secret not in repr(asdict(result))
    assert stored.secret_digest not in repr(asdict(result))
    assert canonical.read_text() == skill_before


def test_valid_existing_delivery_is_ready_without_regeneration(setup_grants):
    repository, base, workspace, _canonical = setup_grants
    first, _, _ = manager(
        repository,
        base,
        ["first_secret_abcdefghijklmnopqrstuvwxyz"],
        ["key-1"],
    )
    first.reconcile(agent(workspace), eligible=True)
    restarted, secrets, keys = manager(
        repository,
        base,
        ["must_not_be_generated_abcdefghijklmnop"],
        ["must-not-be-generated"],
    )
    result = restarted.reconcile(agent(workspace), eligible=True)
    assert result.state == "ready"
    assert result.key_id == "key-1"
    assert secrets.calls == keys.calls == []


def test_force_rotation_replaces_delivery_and_repository_digest(setup_grants):
    repository, base, workspace, _canonical = setup_grants
    service, _, _ = manager(
        repository,
        base,
        [
            "first_secret_abcdefghijklmnopqrstuvwxyz",
            "second_secret_abcdefghijklmnopqrstuvwxyz",
        ],
        ["key-1", "key-2"],
    )
    service.reconcile(agent(workspace), eligible=True)
    rotated = service.reconcile(agent(workspace), eligible=True, force_rotate=True)
    assert rotated.state == "rotated"
    assert rotated.key_id == "key-2"
    stored = repository.get_access_grant("agent-1")
    assert stored.key_id == "key-2"
    assert stored.secret_digest == hashlib.sha256(
        b"second_secret_abcdefghijklmnopqrstuvwxyz"
    ).hexdigest()
    assert delivery_paths(workspace)[0].read_text().startswith("second_secret")
    assert "key-2" in delivery_paths(workspace)[1].read_text()


def test_ineligibility_revokes_grant_and_removes_delivery(setup_grants):
    repository, base, workspace, _canonical = setup_grants
    service, _, _ = manager(
        repository,
        base,
        ["active_secret_abcdefghijklmnopqrstuvwxyz"],
        ["key-1"],
    )
    service.reconcile(agent(workspace), eligible=True)
    result = service.reconcile(agent(workspace), eligible=False)
    assert result.ready is False
    assert result.state == "revoked"
    assert result.key_id == ""
    assert repository.get_access_grant("agent-1").status == "revoked"
    assert all(not path.exists() for path in delivery_paths(workspace))


def test_provider_becoming_unsupported_revokes_and_cleans_existing_grant(setup_grants):
    repository, base, workspace, _canonical = setup_grants
    service, _, _ = manager(
        repository,
        base,
        ["active_secret_abcdefghijklmnopqrstuvwxyz"],
        ["key-1"],
    )
    service.reconcile(agent(workspace), eligible=True)
    result = service.reconcile(agent(workspace, "codex"), eligible=True)
    assert result.state == "unsupported_provider"
    assert result.error_code == "hr_grant_unsupported_provider"
    assert repository.get_access_grant("agent-1").status == "revoked"
    assert all(not path.exists() for path in delivery_paths(workspace))


def test_revocation_reports_when_delivery_cleanup_cannot_be_verified(setup_grants, tmp_path):
    repository, base, workspace, _canonical = setup_grants
    service, _, _ = manager(
        repository,
        base,
        ["active_secret_abcdefghijklmnopqrstuvwxyz"],
        ["key-1"],
    )
    service.reconcile(agent(workspace), eligible=True)
    result = service.reconcile(agent(tmp_path / "outside"), eligible=False)
    assert result.state == "revoked_cleanup_unverified"
    assert result.error_code == "hr_grant_revoked_cleanup_unverified"
    assert repository.get_access_grant("agent-1").status == "revoked"


def test_missing_or_unmanaged_skill_disables_delivery_without_generating_secret(tmp_path):
    repository = HRRepository(tmp_path / "status", clock=lambda: NOW)
    repository.initialize()
    repository.upsert_agent(
        ai_id="agent-1",
        name="Agent 1",
        agent_kind="project",
        status="active",
        availability="available",
        source="test",
    )
    base = tmp_path / "workspaces"
    workspace = base / "agent-1"
    workspace.mkdir(parents=True)
    service, secrets, keys = manager(
        repository,
        base,
        ["must_not_be_used_abcdefghijklmnopqrstuvwxyz"],
        ["key-unused"],
    )
    assert service.reconcile(agent(workspace), eligible=True).state == "delivery_unsupported"
    user_skill = workspace / "skills" / "vo-agent-directory" / "SKILL.md"
    user_skill.parent.mkdir(parents=True)
    user_skill.write_text("user-owned")
    assert service.reconcile(agent(workspace), eligible=True).state == "delivery_unsupported"
    assert secrets.calls == keys.calls == []
    assert repository.get_access_grant("agent-1") is None


def test_symlinked_credential_path_fails_before_secret_generation(setup_grants, tmp_path):
    repository, base, workspace, _canonical = setup_grants
    outside = tmp_path / "outside"
    outside.mkdir()
    credential_root = workspace / ".vo"
    credential_root.symlink_to(outside, target_is_directory=True)
    service, secrets, keys = manager(
        repository,
        base,
        ["must_not_be_used_abcdefghijklmnopqrstuvwxyz"],
        ["key-unused"],
    )
    result = service.reconcile(agent(workspace), eligible=True)
    assert result.state == "delivery_unsupported"
    assert secrets.calls == keys.calls == []
    assert list(outside.iterdir()) == []


def test_repository_failure_removes_new_raw_delivery(setup_grants, monkeypatch):
    repository, base, workspace, _canonical = setup_grants
    service, _, _ = manager(
        repository,
        base,
        ["new_secret_abcdefghijklmnopqrstuvwxyz"],
        ["key-1"],
    )
    monkeypatch.setattr(
        repository,
        "rotate_access_grant",
        lambda **_kwargs: (_ for _ in ()).throw(HRRepositoryError("injected")),
    )
    result = service.reconcile(agent(workspace), eligible=True)
    assert result.state == "delivery_failed"
    assert all(not path.exists() for path in delivery_paths(workspace))


def test_invalid_factory_output_never_reaches_workspace_or_repository(setup_grants):
    repository, base, workspace, _canonical = setup_grants
    service, _, _ = manager(repository, base, ["short"], ["key-1"])
    result = service.reconcile(agent(workspace), eligible=True)
    assert result.state == "generation_failed"
    assert repository.get_access_grant("agent-1") is None
    assert all(not path.exists() for path in delivery_paths(workspace))


def test_concurrent_reconciliation_converges_without_duplicate_rotation(setup_grants):
    repository, base, workspace, _canonical = setup_grants
    first, first_secrets, _ = manager(
        repository,
        base,
        ["first_secret_abcdefghijklmnopqrstuvwxyz"],
        ["key-1"],
    )
    second, second_secrets, _ = manager(
        repository,
        base,
        ["second_secret_abcdefghijklmnopqrstuvwxyz"],
        ["key-2"],
    )
    barrier = threading.Barrier(3)
    results = []

    def reconcile(service):
        barrier.wait()
        results.append(service.reconcile(agent(workspace), eligible=True))

    threads = [threading.Thread(target=reconcile, args=(service,)) for service in (first, second)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)
    assert sorted(item.state for item in results) == ["issued", "ready"]
    assert len(first_secrets.calls) + len(second_secrets.calls) == 1
    stored = repository.get_access_grant("agent-1")
    raw = delivery_paths(workspace)[0].read_text()
    assert hashlib.sha256(raw.encode()).hexdigest() == stored.secret_digest
