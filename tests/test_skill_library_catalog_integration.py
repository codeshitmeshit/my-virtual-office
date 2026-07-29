from __future__ import annotations

import json
import os
import sys
import base64
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")
os.environ.setdefault(
    "VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-skill-catalog-integration-test-")
)

from services.skill_library_catalog import (  # noqa: E402
    CATALOG_FILENAME,
    DEFAULT_CATEGORY_ID,
    SkillLibraryCatalogRepository,
)
from services.skill_library_catalog_integration import (  # noqa: E402
    compact_skill_catalog,
    enrich_skill_list,
    library_skill_names,
    record_skill_in_default,
)


def write_skill(library: Path, slug: str, content: str = "# Skill") -> Path:
    target = library / slug / "SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def test_external_skill_projects_to_default_without_persisting_catalog(tmp_path):
    library = tmp_path / "skills-library"
    skill_file = write_skill(library, "external-skill")
    original = {
        "name": "external-skill",
        "description": "Existing consumer field",
        "path": str(skill_file),
    }

    projected = enrich_skill_list(library, [original])

    assert projected["skills"][0] == {
        **original,
        "primaryCategoryId": DEFAULT_CATEGORY_ID,
        "primaryCategory": {
            "id": DEFAULT_CATEGORY_ID,
            "name": "默认标签",
            "kind": "system",
        },
        "tags": [],
    }
    assert projected["catalogRevision"] == 0
    assert projected["organization"] is None
    assert len(projected["categories"]) == 6
    assert not (library / CATALOG_FILENAME).exists()


def test_record_new_skill_defaults_but_existing_classification_is_preserved(tmp_path):
    library = tmp_path / "skills-library"
    write_skill(library, "new-skill")
    saved = record_skill_in_default(library, "new-skill")
    assert saved["skills"]["new-skill"]["primaryCategoryId"] == DEFAULT_CATEGORY_ID

    repository = SkillLibraryCatalogRepository(library)
    repository.set_skill_metadata(
        "new-skill",
        "development-testing",
        tags=["python"],
        valid_skill_names=["new-skill"],
    )
    # Updating skill content must not call record_skill_in_default. The
    # integration projection demonstrates that the prior metadata is retained.
    write_skill(library, "new-skill", "# Updated")
    projected = enrich_skill_list(
        library,
        [{"name": "new-skill", "description": "", "path": "unchanged"}],
    )
    assert projected["skills"][0]["primaryCategoryId"] == "development-testing"
    assert projected["skills"][0]["tags"] == ["python"]


def test_authorized_delete_compacts_stale_metadata(tmp_path):
    library = tmp_path / "skills-library"
    write_skill(library, "keep")
    removed = write_skill(library, "remove")
    repository = SkillLibraryCatalogRepository(library)
    repository.set_skill_metadata(
        "remove",
        "knowledge-content",
        valid_skill_names=["keep", "remove"],
    )

    removed.unlink()
    removed.parent.rmdir()
    compacted = compact_skill_catalog(library)

    assert "remove" not in compacted["skills"]
    assert repository.load()["skills"] == {}


def test_scan_ignores_invalid_non_skill_and_symlink_entries(tmp_path):
    library = tmp_path / "skills-library"
    write_skill(library, "valid_skill")
    (library / "notes").mkdir()
    (library / "notes" / "README.md").write_text("not a skill", encoding="utf-8")
    write_skill(library, "Unsafe Name")
    target = tmp_path / "outside"
    write_skill(target, "linked")
    (library / "linked").symlink_to(target / "linked", target_is_directory=True)

    assert library_skill_names(library) == ["valid_skill"]


def test_server_skill_crud_remains_compatible_and_updates_sidecar(tmp_path, monkeypatch):
    import server

    library_home = tmp_path / "openclaw"
    monkeypatch.setattr(
        server,
        "VO_CONFIG",
        {
            **server.VO_CONFIG,
            "openclaw": {
                **server.VO_CONFIG.get("openclaw", {}),
                "homePath": str(library_home),
            },
        },
    )
    monkeypatch.setattr(server, "_ensure_builtin_communication_skill", lambda: None)

    created = server._handle_skills_library_create(
        {"name": "Compat Skill", "content": "---\nname: compat-skill\n---\n# One"}
    )
    assert created["ok"] is True
    assert created["skill"] == "compat-skill"
    assert "catalogWarning" not in created

    listing = server._handle_skills_library_list()
    row = listing["skills"][0]
    assert {"name", "description", "path"} <= row.keys()
    assert row["primaryCategoryId"] == DEFAULT_CATEGORY_ID

    repository = SkillLibraryCatalogRepository(library_home / "skills-library")
    repository.set_skill_metadata(
        "compat-skill",
        "development-testing",
        valid_skill_names=["compat-skill"],
    )
    updated = server._handle_skills_library_create(
        {"name": "Compat Skill", "content": "---\nname: compat-skill\n---\n# Two"}
    )
    assert updated["ok"] is True
    assert (
        repository.load()["skills"]["compat-skill"]["primaryCategoryId"]
        == "development-testing"
    )

    deleted = server._handle_skills_library_delete("compat-skill")
    assert deleted == {"ok": True, "deleted": "compat-skill"}
    assert repository.load()["skills"] == {}
    sidecar = json.loads(
        (library_home / "skills-library" / CATALOG_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    assert sidecar["skills"] == {}


def test_server_import_and_save_from_agent_record_only_new_skills(
    tmp_path, monkeypatch
):
    import server

    library_home = tmp_path / "openclaw"
    monkeypatch.setattr(
        server,
        "VO_CONFIG",
        {
            **server.VO_CONFIG,
            "openclaw": {
                **server.VO_CONFIG.get("openclaw", {}),
                "homePath": str(library_home),
            },
        },
    )
    monkeypatch.setattr(
        server,
        "_handle_skill_list",
        lambda _agent_id: {
            "skills": [
                {
                    "name": "agent-skill",
                    "content": "---\nname: agent-skill\n---\n# Agent",
                }
            ]
        },
    )

    uploaded = server._handle_skills_library_upload(
        {
            "filename": "SKILL.md",
            "content": base64.b64encode(
                b"---\nname: imported-skill\n---\n# Imported"
            ).decode("ascii"),
        }
    )
    saved = server._handle_skills_library_save_from_agent(
        {"agentId": "archivist", "skill": "agent-skill"}
    )

    assert uploaded["ok"] is True
    assert saved["status"] == "created"
    repository = SkillLibraryCatalogRepository(library_home / "skills-library")
    assert repository.load()["skills"] == {
        "agent-skill": {"primaryCategoryId": DEFAULT_CATEGORY_ID, "tags": []},
        "imported-skill": {"primaryCategoryId": DEFAULT_CATEGORY_ID, "tags": []},
    }

    repository.set_skill_metadata(
        "agent-skill",
        "collaboration-docs",
        valid_skill_names=["agent-skill", "imported-skill"],
    )
    overwritten = server._handle_skills_library_save_from_agent(
        {"agentId": "archivist", "skill": "agent-skill", "overwrite": True}
    )
    assert overwritten["status"] == "identical"
    assert (
        repository.load()["skills"]["agent-skill"]["primaryCategoryId"]
        == "collaboration-docs"
    )
