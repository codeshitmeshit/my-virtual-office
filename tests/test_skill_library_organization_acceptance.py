"""Acceptance fixture for the Skills Library smart-organization workflow."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.archive_manager_coordinated_work import execute  # noqa: E402
from services.archive_manager_work_coordinator import (  # noqa: E402
    ArchiveManagerWorkCoordinator,
)
from services.skill_library_catalog import (  # noqa: E402
    DEFAULT_CATEGORY_ID,
    SkillLibraryCatalogRepository,
)
from services.skill_library_catalog_integration import (  # noqa: E402
    enrich_skill_list,
    library_skill_names,
)
from services.skill_library_organization_admin import (  # noqa: E402
    SkillLibraryOrganizationAdmin,
)
from services.skill_library_organization_runs import (  # noqa: E402
    SkillLibraryOrganizationService,
)
from services.skill_library_organization_runtime import (  # noqa: E402
    SkillLibraryOrganizationRuntime,
)


class ImmediateThread:
    def __init__(self, target):
        self.target = target

    def start(self):
        self.target()


class CapturedThread:
    def __init__(self, target):
        self.target = target

    def start(self):
        return None


def _write_skills(library: Path, count: int) -> list[str]:
    slugs = [f"acceptance-skill-{index:03d}" for index in range(count)]
    for slug in slugs:
        skill_file = library / slug / "SKILL.md"
        skill_file.parent.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(
            (
                "---\n"
                f"name: {slug}\n"
                f"description: Acceptance fixture for {slug}\n"
                "---\n"
                f"# {slug}\n"
                "Bounded acceptance content.\n"
            ),
            encoding="utf-8",
        )
    return slugs


def _prompt_slugs(prompt: str) -> list[str]:
    payload = prompt.split("<untrusted_skill_data>", 1)[1].split(
        "</untrusted_skill_data>", 1
    )[0]
    return [item["slug"] for item in json.loads(payload)]


def _manager_state(state: dict, coordinator: ArchiveManagerWorkCoordinator):
    return {
        "agentId": "archive-manager",
        "status": state["status"],
        "paused": False,
        "activeWork": coordinator.holder(),
    }


def _mark_working(state: dict, label: str) -> None:
    state.update({"status": "working", "label": label})


def _finalize(state: dict, failures: list, error: BaseException | None) -> None:
    failures.append(error)
    state.update({"status": "error" if error else "idle", "label": "已接入"})


def test_100_plus_skill_multi_batch_partial_repair_and_terminal_activity(
    tmp_path,
):
    library = tmp_path / "skills"
    slugs = _write_skills(library, 103)
    failed_slugs = set(slugs[-2:])
    batches: list[list[str]] = []
    activities: list[dict] = []
    finalizations: list[BaseException | None] = []
    state = {"status": "idle", "label": "已接入"}
    coordinator = ArchiveManagerWorkCoordinator()

    def classify(prompt, timeout):
        assert timeout == 45
        batch = _prompt_slugs(prompt)
        batches.append(batch)
        return json.dumps(
            {
                "results": [
                    (
                        {
                            "slug": slug,
                            "failureReason": "acceptance fixture needs owner review",
                        }
                        if slug in failed_slugs
                        else {
                            "slug": slug,
                            "categoryId": "development-testing",
                            "tags": ["acceptance"],
                        }
                    )
                    for slug in batch
                ]
            }
        )

    organizer = SkillLibraryOrganizationService(
        library,
        coordinator=coordinator,
        manager_state=lambda: _manager_state(state, coordinator),
        call_archive_manager=classify,
        mark_manager_working=lambda label: _mark_working(state, label),
        finalize_manager=lambda error: _finalize(
            state, finalizations, error
        ),
        append_terminal_activity=lambda summary: activities.append(dict(summary)),
        clock=iter(
            [
                "2026-07-30T10:00:00+00:00",
                "2026-07-30T10:06:00+00:00",
            ]
        ).__next__,
        run_id_factory=lambda: "acceptance-103",
        thread_factory=lambda target, _name: ImmediateThread(target),
        timeout_seconds=45,
    )

    organizer.start()

    assert [len(batch) for batch in batches] == [20, 20, 20, 20, 20, 3]
    assert [slug for batch in batches for slug in batch] == slugs
    terminal = organizer.repository.load()["lastOrganization"]
    assert terminal["status"] == "partial"
    assert terminal["totalCount"] == 103
    assert terminal["processedCount"] == 103
    assert terminal["assignedCount"] == 101
    assert terminal["failureCount"] == 2
    assert {item["slug"] for item in terminal["failures"]} == failed_slugs
    assert len(activities) == 1
    assert activities[0]["status"] == "partial"
    assert finalizations == [None]
    assert state["status"] == "idle"
    assert coordinator.holder() is None

    admin = SkillLibraryOrganizationAdmin(
        library,
        coordinator=coordinator,
        clock=lambda: "2026-07-30T10:07:00+00:00",
    )
    revision = organizer.repository.load()["revision"]
    for index, slug in enumerate(sorted(failed_slugs)):
        repaired = admin.correct_skill_category(
            slug,
            "knowledge-content",
            expected_revision=revision,
            tags=["owner-repaired"],
        )
        revision = repaired["catalogRevision"]
        assert repaired["organization"]["failureCount"] == 1 - index

    catalog = organizer.repository.project(slugs)
    assert catalog["lastOrganization"]["status"] == "resolved"
    assert all(
        metadata["primaryCategoryId"] != DEFAULT_CATEGORY_ID
        for metadata in catalog["skills"].values()
    )


def test_active_run_is_visible_and_blocks_other_archive_work(tmp_path):
    library = tmp_path / "skills"
    slugs = _write_skills(library, 1)
    coordinator = ArchiveManagerWorkCoordinator()
    state = {"status": "idle", "label": "已接入"}
    activities: list[dict] = []
    finalizations: list[BaseException | None] = []
    captured: list[CapturedThread] = []
    archive_calls: list[str] = []

    def classify(prompt, _timeout):
        return json.dumps(
            {
                "results": [
                    {
                        "slug": _prompt_slugs(prompt)[0],
                        "categoryId": "operations-diagnostics",
                        "tags": [],
                    }
                ]
            }
        )

    def thread_factory(target, _name):
        thread = CapturedThread(target)
        captured.append(thread)
        return thread

    organizer = SkillLibraryOrganizationService(
        library,
        coordinator=coordinator,
        manager_state=lambda: _manager_state(state, coordinator),
        call_archive_manager=classify,
        mark_manager_working=lambda label: _mark_working(state, label),
        finalize_manager=lambda error: _finalize(
            state, finalizations, error
        ),
        append_terminal_activity=lambda summary: activities.append(dict(summary)),
        clock=iter(
            [
                "2026-07-30T11:00:00+00:00",
                "2026-07-30T11:01:00+00:00",
            ]
        ).__next__,
        run_id_factory=lambda: "acceptance-visible",
        thread_factory=thread_factory,
    )
    admin = SkillLibraryOrganizationAdmin(library, coordinator=coordinator)
    runtime = SkillLibraryOrganizationRuntime(
        organizer=organizer,
        admin=admin,
        list_skills=lambda: enrich_skill_list(
            library,
            [{"name": slug, "description": slug} for slug in slugs],
        ),
        archive_manager_state=lambda: _manager_state(state, coordinator),
    )

    started = runtime.start_run()
    active = runtime.library_projection()
    blocked = execute(
        coordinator,
        kind="archive-count-audit",
        label="检查档案数目",
        metadata={"source": "archive-room"},
        operation=lambda: archive_calls.append("audit") or {"ok": True},
        finalize=lambda _error: None,
    )

    assert started["status"] == "running"
    assert active["organization"]["status"] == "running"
    assert active["archiveManager"]["status"] == "working"
    assert active["archiveManager"]["activeWork"]["kind"] == "skill-organization"
    assert blocked["code"] == "archive_manager_busy"
    assert blocked["_status"] == 409
    assert archive_calls == []
    assert activities == []

    captured[0].target()

    finished = runtime.library_projection()
    assert finished["organization"]["status"] == "completed"
    assert finished["archiveManager"]["status"] == "idle"
    assert finished["archiveManager"]["activeWork"] is None
    assert len(activities) == 1
    assert finalizations == [None]


def test_restart_recovery_keeps_interrupted_skills_in_default(tmp_path):
    library = tmp_path / "skills"
    slugs = _write_skills(library, 3)
    repository = SkillLibraryCatalogRepository(library)
    repository.update(
        lambda catalog: catalog.__setitem__(
            "lastOrganization",
            {
                "runId": "acceptance-interrupted",
                "status": "running",
                "startedAt": "2026-07-30T12:00:00+00:00",
                "completedAt": None,
                "targetSlugs": slugs,
                "totalCount": len(slugs),
                "processedCount": 0,
                "assignedCount": 0,
                "failureCount": 0,
                "failures": [],
                "dismissedAt": None,
            },
        ),
        valid_skill_names=library_skill_names(library),
    )
    activities: list[dict] = []
    coordinator = ArchiveManagerWorkCoordinator()
    recovered = SkillLibraryOrganizationAdmin(
        library,
        coordinator=coordinator,
        append_terminal_activity=lambda summary: activities.append(dict(summary)),
        clock=lambda: "2026-07-30T12:01:00+00:00",
    ).recover_interrupted_run()

    assert recovered["status"] == "failed"
    assert recovered["failureCount"] == 3
    assert {item["code"] for item in recovered["failures"]} == {
        "run_interrupted"
    }
    assert len(activities) == 1
    assert all(
        metadata["primaryCategoryId"] == DEFAULT_CATEGORY_ID
        for metadata in repository.project(slugs)["skills"].values()
    )
