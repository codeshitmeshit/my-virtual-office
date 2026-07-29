from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.archive_manager_work_coordinator import (  # noqa: E402
    ArchiveManagerBusyError,
    ArchiveManagerWorkCoordinator,
)
from services.skill_library_catalog import (  # noqa: E402
    CatalogRevisionConflict,
    DEFAULT_CATEGORY_ID,
    SkillLibraryCatalogRepository,
)
from services.skill_library_organization_admin import (  # noqa: E402
    SkillLibraryOrganizationAdmin,
    SkillOrganizationMutationError,
)


def write_skills(library: Path, *slugs: str) -> None:
    for slug in slugs:
        target = library / slug / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"---\nname: {slug}\n---\n# {slug}", encoding="utf-8")


def seed_organization(
    library: Path,
    *,
    status: str,
    targets=("alpha", "beta"),
    failures=None,
) -> SkillLibraryCatalogRepository:
    repository = SkillLibraryCatalogRepository(library)
    failures = (
        failures
        if failures is not None
        else [
            {"slug": slug, "code": "failed", "reason": "needs correction"}
            for slug in targets
        ]
    )
    repository.update(
        lambda catalog: catalog.__setitem__(
            "lastOrganization",
            {
                "runId": "run-1",
                "status": status,
                "startedAt": "2026-07-30T10:00:00+00:00",
                "completedAt": (
                    None if status == "running" else "2026-07-30T10:01:00+00:00"
                ),
                "targetSlugs": list(targets),
                "totalCount": len(targets),
                "processedCount": 0 if status == "running" else len(targets),
                "assignedCount": 0,
                "failureCount": len(failures),
                "failures": failures,
                "dismissedAt": None,
            },
        ),
        valid_skill_names=targets,
    )
    return repository


def admin(
    library: Path,
    coordinator=None,
    activities=None,
    finalizations=None,
) -> SkillLibraryOrganizationAdmin:
    activities = activities if activities is not None else []
    finalizations = finalizations if finalizations is not None else []
    return SkillLibraryOrganizationAdmin(
        library,
        coordinator=coordinator or ArchiveManagerWorkCoordinator(),
        append_terminal_activity=lambda summary: activities.append(dict(summary)),
        finalize_manager=finalizations.append,
        clock=lambda: "2026-07-30T11:00:00+00:00",
    )


def test_restart_recovery_finalizes_running_run_once_without_moving_skills(
    tmp_path,
):
    library = tmp_path / "skills"
    write_skills(library, "alpha", "beta")
    repository = seed_organization(library, status="running")
    activities: list[dict] = []
    finalizations: list[BaseException | None] = []
    mutations = admin(
        library,
        activities=activities,
        finalizations=finalizations,
    )

    recovered = mutations.recover_interrupted_run()

    assert recovered["status"] == "failed"
    assert recovered["failureCount"] == 2
    assert {item["code"] for item in recovered["failures"]} == {
        "run_interrupted"
    }
    projected = repository.project(["alpha", "beta"])
    assert all(
        metadata["primaryCategoryId"] == DEFAULT_CATEGORY_ID
        for metadata in projected["skills"].values()
    )
    assert len(activities) == 1
    assert finalizations == [None]
    assert mutations.recover_interrupted_run() is None
    assert len(activities) == 1


def test_recovery_refuses_to_touch_persisted_run_while_live_holder_exists(
    tmp_path,
):
    library = tmp_path / "skills"
    write_skills(library, "alpha")
    repository = seed_organization(
        library, status="running", targets=("alpha",)
    )
    coordinator = ArchiveManagerWorkCoordinator()
    lease = coordinator.acquire("skill-organization")
    mutations = admin(library, coordinator=coordinator)

    with pytest.raises(ArchiveManagerBusyError):
        mutations.recover_interrupted_run()

    assert repository.load()["lastOrganization"]["status"] == "running"
    coordinator.release(lease)


def test_recovery_revision_race_does_not_overwrite_newer_result(tmp_path, monkeypatch):
    library = tmp_path / "skills"
    write_skills(library, "alpha")
    repository = seed_organization(
        library, status="running", targets=("alpha",)
    )
    mutations = admin(library)
    original_update = mutations.repository.update
    raced = False

    def update_with_race(mutation, **kwargs):
        nonlocal raced
        if not raced and kwargs.get("expected_revision") is not None:
            raced = True
            repository.update(
                lambda catalog: catalog["lastOrganization"].update(
                    {
                        "status": "completed",
                        "failureCount": 0,
                        "failures": [],
                    }
                ),
                valid_skill_names=["alpha"],
            )
        return original_update(mutation, **kwargs)

    monkeypatch.setattr(mutations.repository, "update", update_with_race)

    assert mutations.recover_interrupted_run() is None
    assert repository.load()["lastOrganization"]["status"] == "completed"


def test_terminal_marker_dismissal_persists_and_running_marker_is_protected(
    tmp_path,
):
    library = tmp_path / "skills"
    write_skills(library, "alpha")
    repository = seed_organization(
        library, status="partial", targets=("alpha",)
    )
    mutations = admin(library)

    dismissed = mutations.dismiss_marker()

    assert dismissed["organization"]["dismissedAt"] == (
        "2026-07-30T11:00:00+00:00"
    )
    assert repository.load()["lastOrganization"]["dismissedAt"] is not None

    repository.update(
        lambda catalog: catalog["lastOrganization"].update(
            {"status": "running", "dismissedAt": None}
        ),
        valid_skill_names=["alpha"],
    )
    with pytest.raises(SkillOrganizationMutationError) as caught:
        mutations.dismiss_marker()
    assert caught.value.code == "organization_running"


def test_single_skill_correction_decrements_failures_and_resolves_final_one(
    tmp_path,
):
    library = tmp_path / "skills"
    write_skills(library, "alpha", "beta")
    repository = seed_organization(library, status="partial")
    mutations = admin(library)
    initial_revision = repository.load()["revision"]

    first = mutations.correct_skill_category(
        "alpha",
        "development-testing",
        expected_revision=initial_revision,
        tags=["manual"],
    )

    assert first["organization"]["failureCount"] == 1
    assert first["organization"]["status"] == "partial"
    assert first["metadata"] == {
        "primaryCategoryId": "development-testing",
        "tags": ["manual"],
    }
    assert set(first["metadata"]) == {"primaryCategoryId", "tags"}

    with pytest.raises(CatalogRevisionConflict):
        mutations.correct_skill_category(
            "beta",
            "knowledge-content",
            expected_revision=initial_revision,
        )

    final = mutations.correct_skill_category(
        "beta",
        "knowledge-content",
        expected_revision=first["catalogRevision"],
    )
    assert final["organization"]["failureCount"] == 0
    assert final["organization"]["failures"] == []
    assert final["organization"]["status"] == "resolved"
    assert final["organization"]["resolvedAt"] == "2026-07-30T11:00:00+00:00"


def test_manual_correction_is_disabled_during_live_skill_organization(tmp_path):
    library = tmp_path / "skills"
    write_skills(library, "alpha")
    repository = seed_organization(
        library, status="running", targets=("alpha",)
    )
    coordinator = ArchiveManagerWorkCoordinator()
    lease = coordinator.acquire("skill-organization")
    mutations = admin(library, coordinator=coordinator)

    with pytest.raises(SkillOrganizationMutationError) as caught:
        mutations.correct_skill_category(
            "alpha",
            "development-testing",
            expected_revision=repository.load()["revision"],
        )

    assert caught.value.code == "organization_running"
    coordinator.release(lease)
