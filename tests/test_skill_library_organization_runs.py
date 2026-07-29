from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.archive_manager_work_coordinator import (  # noqa: E402
    ArchiveManagerWorkCoordinator,
)
from services.skill_library_catalog import (  # noqa: E402
    DEFAULT_CATEGORY_ID,
    SkillLibraryCatalogRepository,
)
from services.skill_library_organization_runs import (  # noqa: E402
    SkillLibraryOrganizationService,
    SkillOrganizationStartError,
)


class ImmediateThread:
    def __init__(self, target):
        self.target = target

    def start(self):
        self.target()


def immediate_thread_factory(target, _name):
    return ImmediateThread(target)


def write_skills(library: Path, count: int) -> list[str]:
    slugs = [f"skill-{index:02d}" for index in range(count)]
    for slug in slugs:
        target = library / slug / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            f"---\nname: {slug}\ndescription: Test {slug}\n---\n# {slug}\nBody",
            encoding="utf-8",
        )
    return slugs


def prompt_slugs(prompt: str) -> list[str]:
    payload = prompt.split("<untrusted_skill_data>", 1)[1].split(
        "</untrusted_skill_data>", 1
    )[0]
    return [item["slug"] for item in json.loads(payload)]


def service(
    library: Path,
    caller,
    *,
    manager=None,
    coordinator=None,
    activities=None,
    finalizations=None,
    thread_factory=immediate_thread_factory,
):
    timestamps = iter(
        [
            "2026-07-30T10:00:00+00:00",
            "2026-07-30T10:01:00+00:00",
            "2026-07-30T10:02:00+00:00",
        ]
    )
    activities = activities if activities is not None else []
    finalizations = finalizations if finalizations is not None else []
    return SkillLibraryOrganizationService(
        library,
        coordinator=coordinator or ArchiveManagerWorkCoordinator(),
        manager_state=lambda: manager
        or {"agentId": "archive-manager", "status": "idle", "paused": False},
        call_archive_manager=caller,
        mark_manager_working=lambda label: None,
        finalize_manager=finalizations.append,
        append_terminal_activity=lambda summary: activities.append(dict(summary)),
        clock=lambda: next(timestamps),
        run_id_factory=lambda: "run-1",
        thread_factory=thread_factory,
        timeout_seconds=30,
    )


def test_complete_run_processes_batches_sequentially_and_creates_category(tmp_path):
    library = tmp_path / "skills"
    slugs = write_skills(library, 21)
    calls: list[list[str]] = []
    active = 0
    max_active = 0

    def caller(prompt, timeout):
        nonlocal active, max_active
        assert timeout == 30
        active += 1
        max_active = max(max_active, active)
        batch = prompt_slugs(prompt)
        calls.append(batch)
        results = []
        for index, slug in enumerate(batch):
            if slug == slugs[0]:
                results.append(
                    {
                        "slug": slug,
                        "newCategoryName": "设计与体验",
                        "tags": ["visual"],
                    }
                )
            else:
                results.append(
                    {
                        "slug": slug,
                        "categoryId": "development-testing",
                        "tags": [],
                    }
                )
        active -= 1
        return json.dumps({"results": results}, ensure_ascii=False)

    activities: list[dict] = []
    finalizations: list[BaseException | None] = []
    organizer = service(
        library,
        caller,
        activities=activities,
        finalizations=finalizations,
    )

    started = organizer.start()

    assert started["status"] == "running"
    assert [len(batch) for batch in calls] == [20, 1]
    assert max_active == 1
    catalog = organizer.repository.load()
    terminal = catalog["lastOrganization"]
    assert terminal["status"] == "completed"
    assert terminal["assignedCount"] == 21
    assert terminal["failureCount"] == 0
    custom = next(
        category
        for category in catalog["categories"]
        if category["name"] == "设计与体验"
    )
    assert custom["kind"] == "ordinary"
    assert catalog["skills"][slugs[0]] == {
        "primaryCategoryId": custom["id"],
        "tags": ["visual"],
    }
    assert len(activities) == 1
    assert activities[0]["status"] == "completed"
    assert finalizations == [None]
    assert "undo" not in terminal


def test_partial_run_keeps_failures_in_default_and_applies_success(tmp_path):
    library = tmp_path / "skills"
    slugs = write_skills(library, 2)

    def caller(prompt, _timeout):
        batch = prompt_slugs(prompt)
        return json.dumps(
            {
                "results": [
                    {
                        "slug": batch[0],
                        "categoryId": "knowledge-content",
                        "tags": ["reference"],
                    },
                    {
                        "slug": batch[1],
                        "categoryId": "missing-category",
                    },
                ]
            }
        )

    organizer = service(library, caller)
    organizer.start()
    catalog = organizer.repository.load()

    assert catalog["lastOrganization"]["status"] == "partial"
    assert catalog["lastOrganization"]["failureCount"] == 1
    assert catalog["lastOrganization"]["failures"][0]["slug"] == slugs[1]
    assert (
        catalog["skills"][slugs[0]]["primaryCategoryId"] == "knowledge-content"
    )
    projected = organizer.repository.project(slugs)
    assert projected["skills"][slugs[1]]["primaryCategoryId"] == DEFAULT_CATEGORY_ID


@pytest.mark.parametrize(
    ("exception", "expected_code"),
    [
        (RuntimeError("bad reply"), "archive_manager_invalid_response"),
        (TimeoutError("slow"), "archive_manager_timeout"),
    ],
)
def test_total_failure_and_timeout_leave_every_skill_in_default(
    tmp_path, exception, expected_code
):
    library = tmp_path / "skills"
    slugs = write_skills(library, 3)

    def caller(_prompt, _timeout):
        raise exception

    activities: list[dict] = []
    organizer = service(library, caller, activities=activities)
    organizer.start()
    catalog = organizer.repository.load()
    terminal = catalog["lastOrganization"]

    assert terminal["status"] == "failed"
    assert terminal["assignedCount"] == 0
    assert terminal["failureCount"] == 3
    assert {failure["code"] for failure in terminal["failures"]} == {
        expected_code
    }
    projected = organizer.repository.project(slugs)
    assert all(
        projected["skills"][slug]["primaryCategoryId"] == DEFAULT_CATEGORY_ID
        for slug in slugs
    )
    assert len(activities) == 1


@pytest.mark.parametrize(
    ("manager", "code"),
    [
        (
            {"agentId": "", "status": "missing", "paused": False},
            "archive_manager_unavailable",
        ),
        (
            {"agentId": "archive-manager", "status": "paused", "paused": True},
            "archive_manager_paused",
        ),
    ],
)
def test_unavailable_or_paused_manager_is_rejected_before_mutation(
    tmp_path, manager, code
):
    library = tmp_path / "skills"
    write_skills(library, 1)
    organizer = service(library, lambda *_args: None, manager=manager)

    with pytest.raises(SkillOrganizationStartError) as caught:
        organizer.start()

    assert caught.value.code == code
    assert not organizer.repository.path.exists()
    assert organizer.coordinator.holder() is None


def test_empty_default_category_is_rejected_and_lease_is_released(tmp_path):
    library = tmp_path / "skills"
    slugs = write_skills(library, 1)
    repository = SkillLibraryCatalogRepository(library)
    repository.set_skill_metadata(
        slugs[0],
        "project-process",
        valid_skill_names=slugs,
    )
    coordinator = ArchiveManagerWorkCoordinator()
    organizer = service(
        library,
        lambda *_args: None,
        coordinator=coordinator,
    )

    with pytest.raises(SkillOrganizationStartError) as caught:
        organizer.start()

    assert caught.value.code == "default_category_empty"
    assert coordinator.holder() is None
    assert repository.load()["lastOrganization"] is None


def test_real_background_worker_returns_running_before_completion(tmp_path):
    library = tmp_path / "skills"
    slugs = write_skills(library, 1)
    entered = threading.Event()
    release = threading.Event()
    completed = threading.Event()
    activities: list[dict] = []

    def caller(prompt, _timeout):
        entered.set()
        assert release.wait(timeout=2)
        return json.dumps(
            {
                "results": [
                    {
                        "slug": prompt_slugs(prompt)[0],
                        "categoryId": "operations-diagnostics",
                    }
                ]
            }
        )

    def activity(summary):
        activities.append(dict(summary))
        completed.set()

    coordinator = ArchiveManagerWorkCoordinator()
    organizer = SkillLibraryOrganizationService(
        library,
        coordinator=coordinator,
        manager_state=lambda: {
            "agentId": "archive-manager",
            "status": "idle",
            "paused": False,
        },
        call_archive_manager=caller,
        append_terminal_activity=activity,
        run_id_factory=lambda: "async-run",
    )

    started = organizer.start()
    assert started["status"] == "running"
    assert entered.wait(timeout=1)
    assert organizer.repository.load()["lastOrganization"]["status"] == "running"
    assert coordinator.holder()["kind"] == "skill-organization"

    release.set()
    assert completed.wait(timeout=2)
    assert organizer.repository.load()["lastOrganization"]["status"] == "completed"
    assert (
        organizer.repository.load()["skills"][slugs[0]]["primaryCategoryId"]
        == "operations-diagnostics"
    )
    assert coordinator.holder() is None


def test_worker_start_failure_is_terminal_and_releases_manager(tmp_path):
    library = tmp_path / "skills"
    write_skills(library, 1)
    activities: list[dict] = []
    finalizations: list[BaseException | None] = []
    coordinator = ArchiveManagerWorkCoordinator()

    class FailingThread:
        def start(self):
            raise RuntimeError("thread unavailable")

    organizer = service(
        library,
        lambda *_args: None,
        coordinator=coordinator,
        activities=activities,
        finalizations=finalizations,
        thread_factory=lambda _target, _name: FailingThread(),
    )

    with pytest.raises(RuntimeError, match="thread unavailable"):
        organizer.start()

    terminal = organizer.repository.load()["lastOrganization"]
    assert terminal["status"] == "failed"
    assert terminal["failureCount"] == 1
    assert len(activities) == 1
    assert str(finalizations[0]) == "thread unavailable"
    assert coordinator.holder() is None
