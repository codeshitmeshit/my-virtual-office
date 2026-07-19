"""Directory-to-skill/grant readiness wiring and per-Agent isolation."""

import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_directory import (
    HRDirectoryQuery,
    HRDirectoryService,
    RosterObservation,
    RosterSourceSnapshot,
)
from services.hr_repository import HRRepository
from services.hr_skill_publisher import (
    HRDirectoryEnablementCoordinator,
    HRGrantManager,
    HRSkillPublisher,
)


NOW = datetime(2026, 7, 19, 9, tzinfo=timezone.utc)


def observation(ai_id, *, kind="project", status="active", availability="available"):
    return RosterObservation(
        ai_id=ai_id,
        name=ai_id,
        agent_kind=kind,
        provider_kind="openclaw",
        status=status,
        availability=availability,
    )


def setup(tmp_path):
    repository = HRRepository(tmp_path / "status", clock=lambda: NOW)
    repository.initialize()
    base = tmp_path / "workspaces"
    canonical = tmp_path / "canonical" / "SKILL.md"
    canonical.parent.mkdir()
    canonical.write_text(
        "---\nname: vo-agent-directory\ndescription: safe\n---\n\n# Directory\n"
    )
    publisher = HRSkillPublisher(workspace_base=base, canonical_skill_path=canonical)
    grants = HRGrantManager(
        repository,
        workspace_base=base,
        secret_factory=lambda ai_id: f"grant_{ai_id}_abcdefghijklmnopqrstuvwxyz123456",
        key_id_factory=lambda ai_id: f"key-{ai_id}",
        clock=lambda: NOW,
    )
    coordinator = HRDirectoryEnablementCoordinator(
        repository,
        HRDirectoryService(repository),
        publisher,
        grants,
    )
    return repository, base, coordinator, publisher, grants


def workspace_agent(base, ai_id, provider="openclaw"):
    workspace = base / ai_id
    workspace.mkdir(parents=True, exist_ok=True)
    return {"id": ai_id, "providerKind": provider, "workspace": str(workspace)}


def test_reconciliation_persists_readiness_and_isolates_conflict_and_unsupported_provider(tmp_path):
    repository, base, coordinator, _publisher, _grants = setup(tmp_path)
    payloads = {
        "hr": workspace_agent(base, "hr"),
        "good": workspace_agent(base, "good"),
        "conflict": workspace_agent(base, "conflict"),
        "codex": workspace_agent(base, "codex", provider="codex"),
    }
    conflict_skill = base / "conflict" / "skills" / "vo-agent-directory" / "SKILL.md"
    conflict_skill.parent.mkdir(parents=True)
    conflict_skill.write_text("user-owned conflict")
    snapshot = RosterSourceSnapshot(
        "provider",
        (
            observation("hr", kind="system"),
            observation("good"),
            observation("conflict"),
            observation("codex"),
        ),
    )
    result = coordinator.reconcile((snapshot,), payloads)
    readiness = {item.ai_id: item for item in result.enablements}

    assert {item.agent.ai_id for item in result.directory.agents} == {
        "hr",
        "good",
        "conflict",
        "codex",
    }
    assert readiness["good"].skill.ready and readiness["good"].grant.ready
    assert readiness["conflict"].skill.state == "conflict"
    assert readiness["conflict"].grant.ready is False
    assert readiness["codex"].skill.state == "unsupported_provider"
    assert readiness["hr"].grant.state == "not_required"
    assert all(item.persisted for item in readiness.values())

    directory_states = {item.agent.ai_id: item for item in result.directory.agents}
    assert directory_states["conflict"].report_eligible is True
    assert directory_states["codex"].report_eligible is True
    assert repository.get_access_grant("conflict") is None
    assert repository.get_access_grant("codex") is None
    assert repository.get_access_grant("good").status == "active"
    assert conflict_skill.read_text() == "user-owned conflict"


def test_safe_directory_projects_persisted_enablement_without_sensitive_grant_data(tmp_path):
    repository, base, coordinator, _publisher, _grants = setup(tmp_path)
    payloads = {
        "good": workspace_agent(base, "good"),
        "conflict": workspace_agent(base, "conflict"),
        "codex": workspace_agent(base, "codex", provider="codex"),
    }
    conflict_skill = base / "conflict" / "skills" / "vo-agent-directory" / "SKILL.md"
    conflict_skill.parent.mkdir(parents=True)
    conflict_skill.write_text("user-owned")
    coordinator.reconcile(
        (
            RosterSourceSnapshot(
                "provider",
                (observation("good"), observation("conflict"), observation("codex")),
            ),
        ),
        payloads,
    )
    for ai_id in payloads:
        repository.save_introduction(
            ai_id=ai_id,
            state="published",
            raw_response=f"private raw {ai_id}",
            introduction=f"Public {ai_id}",
            source="hr",
            actor_id="hr",
            expected_version=0,
        )
    projected = {item.ai_id: item for item in HRDirectoryQuery(repository).list().items}
    assert projected["good"].readiness == "ready"
    assert projected["conflict"].readiness == "skill_conflict"
    assert projected["codex"].readiness == "unsupported_provider"
    text = repr(projected)
    assert "grant_good" not in text
    assert repository.get_access_grant("good").secret_digest not in text


def test_inactive_reconciliation_revokes_existing_grant_without_blocking_directory(tmp_path):
    repository, base, coordinator, _publisher, _grants = setup(tmp_path)
    payload = workspace_agent(base, "agent-1")
    active = RosterSourceSnapshot("provider", (observation("agent-1"),))
    coordinator.reconcile((active,), {"agent-1": payload})
    assert repository.get_access_grant("agent-1").status == "active"

    inactive = RosterSourceSnapshot(
        "provider",
        (observation("agent-1", status="deleted", availability="unavailable"),),
    )
    result = coordinator.reconcile((inactive,), {"agent-1": payload})
    state = result.directory.agents[0]
    enablement = result.enablements[0]
    assert state.agent.status == "deleted"
    assert state.report_eligible is False
    assert enablement.grant.state == "revoked"
    assert repository.get_access_grant("agent-1").status == "revoked"


def test_one_publisher_exception_does_not_block_other_agent_or_directory(tmp_path):
    repository, base, _coordinator, publisher, grants = setup(tmp_path)
    good_payload = workspace_agent(base, "good")
    bad_payload = workspace_agent(base, "bad")

    class FailingPublisher:
        def publish(self, payload):
            if payload["id"] == "bad":
                raise RuntimeError("injected")
            return publisher.publish(payload)

    coordinator = HRDirectoryEnablementCoordinator(
        repository,
        HRDirectoryService(repository),
        FailingPublisher(),
        grants,
    )
    result = coordinator.reconcile(
        (RosterSourceSnapshot("provider", (observation("bad"), observation("good"))),),
        {"bad": bad_payload, "good": good_payload},
    )
    readiness = {item.ai_id: item for item in result.enablements}
    assert readiness["bad"].skill.state == "failed"
    assert readiness["good"].skill.ready is True
    assert readiness["good"].grant.ready is True
    assert repository.get_agent("bad") is not None
    assert repository.get_agent("good") is not None
    assert next(
        item for item in result.directory.agents if item.agent.ai_id == "bad"
    ).report_eligible is True


def test_one_grant_exception_and_malformed_payload_are_isolated(tmp_path):
    repository, base, _coordinator, publisher, grants = setup(tmp_path)
    good_payload = workspace_agent(base, "good")
    bad_payload = workspace_agent(base, "bad")

    class FailingGrants:
        def reconcile(self, payload, *, eligible):
            if payload["id"] == "bad":
                raise RuntimeError("injected")
            return grants.reconcile(payload, eligible=eligible)

    coordinator = HRDirectoryEnablementCoordinator(
        repository,
        HRDirectoryService(repository),
        publisher,
        FailingGrants(),
    )
    result = coordinator.reconcile(
        (
            RosterSourceSnapshot(
                "provider",
                (observation("bad"), observation("good"), observation("malformed")),
            ),
        ),
        {"bad": bad_payload, "good": good_payload, "malformed": "not-a-mapping"},
    )
    readiness = {item.ai_id: item for item in result.enablements}
    assert readiness["bad"].grant.state == "failed"
    assert readiness["good"].grant.ready is True
    assert readiness["malformed"].skill.ready is False
    assert all(repository.get_agent(ai_id) is not None for ai_id in readiness)
