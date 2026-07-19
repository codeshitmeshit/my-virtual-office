"""Generic managed-skill registry behavior independent of server.py."""

import hashlib
import json
import sys
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services import managed_skills
from services.managed_skills import (
    MANAGED_SKILL_MARKER,
    ManagedSkillDefinition,
    seed_managed_skill_library,
    sync_managed_skill_to_workspace,
)


def content(name, body="canonical"):
    return f"---\nname: {name}\ndescription: test skill\n---\n\n# Skill\n\n{body}\n"


def definition(name="managed-one", body="canonical", **kwargs):
    return ManagedSkillDefinition(name, lambda: content(name, body), **kwargs)


def agent(workspace, provider="openclaw"):
    return {"id": "agent-1", "providerKind": provider, "workspace": str(workspace)}


def test_definition_validates_name_loader_provider_and_declared_identity():
    with pytest.raises(ValueError, match="name"):
        definition("bad/name")
    with pytest.raises(ValueError, match="provider"):
        ManagedSkillDefinition("valid", lambda: content("valid"), frozenset())
    with pytest.raises(ValueError, match="declare name"):
        ManagedSkillDefinition("expected", lambda: content("other")).content()


def test_library_seed_is_generic_atomic_and_idempotent(tmp_path):
    library = tmp_path / "library"
    definitions = (definition("managed-one", "one"), definition("managed-two", "two"))
    first = seed_managed_skill_library(library, definitions)
    assert set(first.paths) == {"managed-one", "managed-two"}
    assert first.conflicts == ()
    first_path = Path(first.paths["managed-one"])
    assert first_path.read_text() == content("managed-one", "one")
    before = first_path.stat().st_mtime_ns
    second = seed_managed_skill_library(library, definitions)
    assert second.paths == first.paths
    assert first_path.stat().st_mtime_ns == before
    assert not list(library.rglob("*.tmp-*"))


def test_library_removes_only_exact_verified_legacy_directory(tmp_path):
    known = "known legacy"
    skill = definition(
        legacy_names=("legacy-one",),
        legacy_content_validator=lambda value: value == known,
    )
    library = tmp_path / "library"
    legacy = library / "legacy-one"
    legacy.mkdir(parents=True)
    (legacy / "SKILL.md").write_text(known)
    assert seed_managed_skill_library(library, (skill,)).conflicts == ()
    assert not legacy.exists()

    legacy.mkdir()
    (legacy / "SKILL.md").write_text(known)
    (legacy / "notes.txt").write_text("user data")
    result = seed_managed_skill_library(library, (skill,))
    assert result.conflicts == ("legacy-one",)
    assert (legacy / "notes.txt").read_text() == "user data"


def test_workspace_install_writes_owned_hash_marker_and_noops(tmp_path):
    workspace = tmp_path / "workspaces" / "agent-1"
    workspace.mkdir(parents=True)
    skill = definition()
    first = sync_managed_skill_to_workspace(
        skill,
        agent(workspace),
        workspace_base=tmp_path / "workspaces",
    )
    assert first["status"] == "updated"
    skill_path = workspace / "skills" / skill.name / "SKILL.md"
    marker_path = skill_path.parent / MANAGED_SKILL_MARKER
    marker = json.loads(marker_path.read_text())
    assert marker == {
        "managedBy": "virtual-office",
        "sha256": hashlib.sha256(content(skill.name).encode()).hexdigest(),
        "skill": skill.name,
    }
    before = (skill_path.stat().st_mtime_ns, marker_path.stat().st_mtime_ns)
    second = sync_managed_skill_to_workspace(
        skill,
        agent(workspace),
        workspace_base=tmp_path / "workspaces",
    )
    assert second["status"] == "ready"
    assert (skill_path.stat().st_mtime_ns, marker_path.stat().st_mtime_ns) == before


def test_workspace_install_preserves_unowned_conflict_and_repairs_owned_copy(tmp_path):
    workspace = tmp_path / "workspaces" / "agent-1"
    skill_path = workspace / "skills" / "managed-one" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text("user-owned")
    skill = definition()
    conflict = sync_managed_skill_to_workspace(
        skill,
        agent(workspace),
        workspace_base=tmp_path / "workspaces",
    )
    assert conflict == {"ready": False, "status": "conflict", "updated": False}
    assert skill_path.read_text() == "user-owned"

    marker = {"managedBy": "virtual-office", "skill": skill.name, "sha256": "old"}
    (skill_path.parent / MANAGED_SKILL_MARKER).write_text(json.dumps(marker))
    repaired = sync_managed_skill_to_workspace(
        skill,
        agent(workspace),
        workspace_base=tmp_path / "workspaces",
    )
    assert repaired["status"] == "updated"
    assert skill_path.read_text() == content(skill.name)


def test_workspace_legacy_conflict_preserves_auxiliary_data(tmp_path):
    workspace = tmp_path / "workspaces" / "agent-1"
    legacy = workspace / "skills" / "legacy-one"
    legacy.mkdir(parents=True)
    (legacy / "SKILL.md").write_text("known")
    (legacy / "notes.txt").write_text("keep")
    skill = definition(
        legacy_names=("legacy-one",),
        legacy_content_validator=lambda value: value == "known",
    )
    result = sync_managed_skill_to_workspace(
        skill,
        agent(workspace),
        workspace_base=tmp_path / "workspaces",
    )
    assert result["status"] == "legacy_conflict"
    assert (legacy / "notes.txt").read_text() == "keep"


@pytest.mark.parametrize("link_target", ("skills", "skill", "marker", "legacy"))
def test_workspace_install_rejects_every_managed_symlink_boundary(tmp_path, link_target):
    base = tmp_path / "workspaces"
    workspace = base / "agent-1"
    outside = tmp_path / "outside"
    workspace.mkdir(parents=True)
    outside.mkdir()
    skills = workspace / "skills"
    skill_dir = skills / "managed-one"
    marker = skill_dir / MANAGED_SKILL_MARKER
    legacy = skills / "legacy-one"
    if link_target == "skills":
        skills.symlink_to(outside, target_is_directory=True)
    else:
        skills.mkdir()
        if link_target == "skill":
            skill_dir.symlink_to(outside, target_is_directory=True)
        elif link_target == "marker":
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(content("managed-one"))
            marker.symlink_to(outside / "marker.json")
        else:
            legacy.symlink_to(outside, target_is_directory=True)
    skill = definition(
        legacy_names=("legacy-one",),
        legacy_content_validator=lambda _value: True,
    )
    result = sync_managed_skill_to_workspace(skill, agent(workspace), workspace_base=base)
    assert result == {"ready": False, "status": "path_rejected", "updated": False}
    assert list(outside.iterdir()) == []


def test_provider_and_workspace_boundaries_are_explicit(tmp_path):
    base = tmp_path / "workspaces"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    skill = definition()
    assert sync_managed_skill_to_workspace(
        skill, agent(outside), workspace_base=base
    )["status"] == "path_rejected"
    assert sync_managed_skill_to_workspace(
        skill, agent(base / "missing"), workspace_base=base
    )["status"] == "workspace_missing"
    assert sync_managed_skill_to_workspace(
        skill, agent(outside, "codex"), workspace_base=base
    )["status"] == "not_applicable"


def test_atomic_replace_failure_keeps_previous_managed_content(tmp_path, monkeypatch):
    base = tmp_path / "workspaces"
    workspace = base / "agent-1"
    workspace.mkdir(parents=True)
    original = definition(body="version one")
    sync_managed_skill_to_workspace(original, agent(workspace), workspace_base=base)
    skill_path = workspace / "skills" / original.name / "SKILL.md"
    before = skill_path.read_text()

    monkeypatch.setattr(
        managed_skills.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("injected")),
    )
    with pytest.raises(OSError, match="injected"):
        sync_managed_skill_to_workspace(
            definition(body="version two"),
            agent(workspace),
            workspace_base=base,
        )
    assert skill_path.read_text() == before
    assert not list(skill_path.parent.glob("*.tmp-*"))


def test_concurrent_installers_converge_on_one_valid_copy(tmp_path):
    base = tmp_path / "workspaces"
    workspace = base / "agent-1"
    workspace.mkdir(parents=True)
    skill = definition()
    barrier = threading.Barrier(3)
    results = []

    def install():
        barrier.wait()
        results.append(sync_managed_skill_to_workspace(skill, agent(workspace), workspace_base=base))

    threads = [threading.Thread(target=install) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)
    assert sorted(item["status"] for item in results) == ["ready", "updated"]
    assert (workspace / "skills" / skill.name / "SKILL.md").read_text() == content(skill.name)


def test_managed_skill_module_has_no_server_dependency():
    source = (APP_DIR / "services" / "managed_skills.py").read_text(encoding="utf-8")
    assert "import server" not in source
    assert "OfficeHandler" not in source
