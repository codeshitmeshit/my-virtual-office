from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_CLAUDE_CODE_ENABLED", "0")
os.environ.setdefault(
    "VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-skill-org-flag-")
)

import server  # noqa: E402
from services import skill_library_organization_config  # noqa: E402
from services.skill_library_catalog import (  # noqa: E402
    CATALOG_FILENAME,
    SkillLibraryCatalogRepository,
)
from services.skill_library_organization_runs import (  # noqa: E402
    SkillOrganizationStartError,
)
from services.skill_library_organization_runtime import (  # noqa: E402
    SkillLibraryOrganizationRuntime,
)


class Organizer:
    def __init__(self, library):
        self.library_dir = library
        self.repository = SkillLibraryCatalogRepository(library)
        self.starts = 0

    def start(self):
        self.starts += 1
        return {"runId": "run-1", "status": "running"}


def runtime(library, enabled):
    organizer = Organizer(library)
    composed = SkillLibraryOrganizationRuntime(
        organizer=organizer,
        admin=object(),
        list_skills=lambda: {"skills": []},
        archive_manager_state=lambda: {"status": "idle"},
        organization_enabled=lambda: enabled,
    )
    return organizer, composed


@pytest.mark.parametrize(
    ("value", "enabled"),
    [
        (None, False),
        ("", False),
        ("0", False),
        ("false", False),
        ("1", True),
        ("TRUE", True),
        ("yes", True),
        ("enabled", True),
    ],
)
def test_rollout_environment_parsing(value, enabled):
    environment = {}
    if value is not None:
        environment[skill_library_organization_config.ENV_NAME] = value
    assert skill_library_organization_config.is_enabled(environment) is enabled


def test_disabled_runtime_rejects_only_new_run_start(tmp_path):
    organizer, composed = runtime(tmp_path / "skills", False)

    projection = composed.library_projection()
    with pytest.raises(SkillOrganizationStartError) as caught:
        composed.start_run()

    assert projection["organizationEnabled"] is False
    assert caught.value.code == "skill_organization_disabled"
    assert caught.value.status == 404
    assert organizer.starts == 0


def test_enabled_runtime_starts_normally(tmp_path):
    organizer, composed = runtime(tmp_path / "skills", True)

    started = composed.start_run()

    assert started["ok"] is True
    assert started["runId"] == "run-1"
    assert started["_status"] == 202
    assert organizer.starts == 1


def test_disabled_read_is_rollback_compatible_and_does_not_rewrite_sidecar(
    tmp_path,
):
    library = tmp_path / "skills"
    target = library / "alpha" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Alpha", encoding="utf-8")
    repository = SkillLibraryCatalogRepository(library)
    repository.set_skill_metadata(
        "alpha",
        "knowledge-content",
        tags=["reference"],
        valid_skill_names=["alpha"],
    )
    repository.update(
        lambda catalog: catalog.__setitem__(
            "lastOrganization",
            {
                "runId": "old-run",
                "status": "completed",
                "assignedCount": 1,
                "failureCount": 0,
                "failures": [],
            },
        ),
        valid_skill_names=["alpha"],
    )
    sidecar = library / CATALOG_FILENAME
    before = sidecar.read_bytes()
    _organizer, composed = runtime(library, False)

    projection = composed.library_projection()

    assert projection["organizationEnabled"] is False
    assert projection["organization"]["runId"] == "old-run"
    assert sidecar.read_bytes() == before
    assert json.loads(before)["skills"]["alpha"]["primaryCategoryId"] == (
        "knowledge-content"
    )


def test_disabled_flag_does_not_block_existing_skill_crud(tmp_path, monkeypatch):
    home = tmp_path / "openclaw"
    monkeypatch.setenv(
        skill_library_organization_config.ENV_NAME,
        "0",
    )
    monkeypatch.setattr(
        server,
        "VO_CONFIG",
        {
            **server.VO_CONFIG,
            "openclaw": {
                **server.VO_CONFIG.get("openclaw", {}),
                "homePath": str(home),
            },
        },
    )
    monkeypatch.setattr(server, "_ensure_builtin_communication_skill", lambda: None)

    created = server._handle_skills_library_create(
        {"name": "rollback-skill", "content": "# Rollback"}
    )
    listing = server._handle_skills_library_list()
    deleted = server._handle_skills_library_delete("rollback-skill")

    assert created["ok"] is True
    assert [skill["name"] for skill in listing["skills"]] == ["rollback-skill"]
    assert deleted["ok"] is True
