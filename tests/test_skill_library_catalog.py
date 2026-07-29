from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.skill_library_catalog import (
    CATALOG_FILENAME,
    CatalogRevisionConflict,
    DEFAULT_CATEGORY_ID,
    ImmutableCategoryError,
    SEEDED_CATEGORIES,
    SkillLibraryCatalogError,
    SkillLibraryCatalogRepository,
    UnsafeSkillLibraryCatalogPath,
)


def repository(tmp_path: Path, **kwargs) -> SkillLibraryCatalogRepository:
    return SkillLibraryCatalogRepository(tmp_path / "skills-library", **kwargs)


def test_repositories_for_the_same_catalog_share_one_process_lock(tmp_path):
    first = repository(tmp_path)
    second = repository(tmp_path)

    assert first._lock is second._lock


def category_ids(catalog: dict) -> list[str]:
    return [item["id"] for item in catalog["categories"]]


def test_default_catalog_seeds_categories_without_writing(tmp_path):
    repo = repository(tmp_path)

    catalog = repo.load()

    assert catalog["schemaVersion"] == 1
    assert catalog["revision"] == 0
    assert catalog["categories"] == list(SEEDED_CATEGORIES)
    assert catalog["skills"] == {}
    assert catalog["lastOrganization"] is None
    assert not repo.path.exists()


def test_projection_defaults_missing_skills_and_ignores_stale_metadata(tmp_path):
    repo = repository(tmp_path)
    repo.set_skill_metadata(
        "stale-skill",
        "development-testing",
        valid_skill_names=["stale-skill"],
    )

    projected = repo.project(["fresh-skill"])

    assert projected["skills"] == {
        "fresh-skill": {"primaryCategoryId": DEFAULT_CATEGORY_ID, "tags": []}
    }
    # Read reconciliation must not mutate persisted metadata.
    assert "stale-skill" in repo.load()["skills"]


def test_skill_metadata_is_validated_deduplicated_and_revisioned(tmp_path):
    repo = repository(tmp_path)

    saved = repo.set_skill_metadata(
        "Dev_Debug",
        "development-testing",
        tags=["Diagnostics", "diagnostics", "CLI"],
        valid_skill_names=["dev_debug"],
    )

    assert saved["revision"] == 1
    assert saved["skills"]["dev_debug"] == {
        "primaryCategoryId": "development-testing",
        "tags": ["Diagnostics", "CLI"],
    }
    on_disk = json.loads(repo.path.read_text(encoding="utf-8"))
    assert on_disk == saved
    assert not list(repo.library_dir.glob(".vo-library-catalog.*.tmp"))


def test_unknown_categories_and_unsafe_values_are_rejected(tmp_path):
    repo = repository(tmp_path)

    with pytest.raises(SkillLibraryCatalogError, match="unknown primary category"):
        repo.set_skill_metadata("skill", "missing-category")
    with pytest.raises(SkillLibraryCatalogError, match="unsafe"):
        repo.put_category("unsafe", "../outside")
    with pytest.raises(SkillLibraryCatalogError, match="at most"):
        repo.set_skill_metadata(
            "skill",
            DEFAULT_CATEGORY_ID,
            tags=[f"tag-{index}" for index in range(17)],
        )
    assert not repo.path.exists()


def test_default_category_cannot_be_changed_deleted_or_merged(tmp_path):
    repo = repository(tmp_path)

    with pytest.raises(ImmutableCategoryError):
        repo.put_category(DEFAULT_CATEGORY_ID, "重命名", kind="system")
    with pytest.raises(ImmutableCategoryError):
        repo.delete_category(DEFAULT_CATEGORY_ID)
    with pytest.raises(ImmutableCategoryError):
        repo.merge_category(DEFAULT_CATEGORY_ID, "development-testing")

    assert repo.load()["categories"][0] == {
        "id": DEFAULT_CATEGORY_ID,
        "name": "默认标签",
        "kind": "system",
    }


def test_ordinary_category_merge_and_delete_rehome_skills(tmp_path):
    repo = repository(tmp_path)
    first = repo.put_category("custom-one", "定制一")
    second = repo.put_category(
        "custom-two", "定制二", expected_revision=first["revision"]
    )
    assigned = repo.set_skill_metadata(
        "skill-a",
        "custom-one",
        expected_revision=second["revision"],
        valid_skill_names=["skill-a", "skill-b"],
    )

    merged = repo.merge_category(
        "custom-one",
        "custom-two",
        expected_revision=assigned["revision"],
    )
    assert merged["skills"]["skill-a"]["primaryCategoryId"] == "custom-two"
    assert "custom-one" not in category_ids(merged)

    assigned_again = repo.set_skill_metadata(
        "skill-b",
        "custom-two",
        expected_revision=merged["revision"],
        valid_skill_names=["skill-a", "skill-b"],
    )
    deleted = repo.delete_category(
        "custom-two", expected_revision=assigned_again["revision"]
    )
    assert deleted["skills"]["skill-a"]["primaryCategoryId"] == DEFAULT_CATEGORY_ID
    assert deleted["skills"]["skill-b"]["primaryCategoryId"] == DEFAULT_CATEGORY_ID


def test_stale_revision_is_rejected_without_writing(tmp_path):
    repo = repository(tmp_path)
    saved = repo.put_category("custom", "定制")
    before = repo.path.read_bytes()

    with pytest.raises(CatalogRevisionConflict) as raised:
        repo.put_category("other", "其他", expected_revision=0)

    assert raised.value.expected == 0
    assert raised.value.actual == saved["revision"]
    assert raised.value.code == "catalog_revision_conflict"
    assert repo.path.read_bytes() == before


@pytest.mark.parametrize(
    "content",
    [
        "{not-json",
        json.dumps({"schemaVersion": 99}),
        json.dumps({"skills": []}),
        json.dumps(
            {
                "schemaVersion": 1,
                "categories": [
                    {"id": DEFAULT_CATEGORY_ID, "name": "renamed", "kind": "system"}
                ],
            }
        ),
    ],
)
def test_corrupt_catalog_recovers_to_defaults_without_overwrite(tmp_path, content):
    repo = repository(tmp_path)
    repo.library_dir.mkdir(parents=True)
    repo.path.write_text(content, encoding="utf-8")

    recovered = repo.load()

    assert recovered["revision"] == 0
    assert recovered["categories"] == list(SEEDED_CATEGORIES)
    assert repo.path.read_text(encoding="utf-8") == content


def test_symlinked_library_or_catalog_is_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_library = tmp_path / "linked-library"
    linked_library.symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafeSkillLibraryCatalogPath):
        SkillLibraryCatalogRepository(linked_library).load()

    repo = repository(tmp_path)
    repo.library_dir.mkdir(parents=True)
    outside_file = tmp_path / "outside.json"
    outside_file.write_text("outside", encoding="utf-8")
    repo.path.symlink_to(outside_file)

    with pytest.raises(UnsafeSkillLibraryCatalogPath):
        repo.load()
    assert outside_file.read_text(encoding="utf-8") == "outside"


def test_atomic_replace_failure_preserves_previous_catalog_and_cleans_temp(tmp_path):
    stable = repository(tmp_path)
    stable.put_category("stable", "稳定")
    before = stable.path.read_bytes()

    def fail_replace(_source: str, _target: str):
        raise OSError("replace failed")

    failing = SkillLibraryCatalogRepository(
        stable.library_dir,
        replace=fail_replace,
    )
    with pytest.raises(OSError, match="replace failed"):
        failing.put_category("never-written", "不会写入")

    assert stable.path.read_bytes() == before
    assert not list(stable.library_dir.glob(".vo-library-catalog.*.tmp"))


def test_catalog_permissions_are_host_editable_after_atomic_write(tmp_path):
    repo = repository(tmp_path)
    repo.put_category("custom", "定制")

    assert os.stat(repo.path).st_mode & 0o777 == 0o666
    assert repo.path.name == CATALOG_FILENAME
