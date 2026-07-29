"""Recovery and owner mutations for Skills Library organization."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping

from services.archive_manager_work_coordinator import (
    ArchiveManagerBusyError,
    ArchiveManagerWorkCoordinator,
)
from services.skill_library_catalog import (
    CatalogRevisionConflict,
    DEFAULT_CATEGORY_ID,
    SkillLibraryCatalogRepository,
    normalize_category_id,
    normalize_skill_slug,
    normalize_tags,
)
from services.skill_library_catalog_integration import library_skill_names


class SkillOrganizationMutationError(ValueError):
    """Stable validation or precondition error for owner mutations."""

    def __init__(self, code: str, message: str, *, status: int = 400):
        self.code = code
        self.status = status
        super().__init__(message)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SkillLibraryOrganizationAdmin:
    """Own restart recovery, marker dismissal, and single-skill correction."""

    def __init__(
        self,
        library_dir: str | Path,
        *,
        coordinator: ArchiveManagerWorkCoordinator,
        finalize_manager: Callable[[BaseException | None], None] = lambda _error: None,
        append_terminal_activity: Callable[[Mapping[str, Any]], None] = (
            lambda _summary: None
        ),
        clock: Callable[[], str] = _utc_now,
    ):
        self.library_dir = Path(library_dir)
        self.repository = SkillLibraryCatalogRepository(self.library_dir)
        self.coordinator = coordinator
        self.finalize_manager = finalize_manager
        self.append_terminal_activity = append_terminal_activity
        self.clock = clock

    @staticmethod
    def _failure(slug: str) -> dict[str, str]:
        return {
            "slug": slug,
            "code": "run_interrupted",
            "reason": "Virtual Office 重启导致本次整理中断",
        }

    def recover_interrupted_run(self) -> dict[str, Any] | None:
        """Finalize one persisted running run when no live process owns it."""

        catalog = self.repository.load()
        current = catalog.get("lastOrganization")
        if not isinstance(current, dict) or current.get("status") != "running":
            return None
        recovered: dict[str, Any] | None = None

        def recover(stale: Mapping[str, Any]) -> None:
            nonlocal recovered
            run_id = stale.get("runId")
            valid_names = library_skill_names(self.library_dir)
            projected = self.repository.project(valid_names)
            target_slugs = [
                normalize_skill_slug(slug)
                for slug in stale.get("targetSlugs") or []
            ]
            if not target_slugs:
                target_slugs = [
                    slug
                    for slug, metadata in projected["skills"].items()
                    if metadata.get("primaryCategoryId") == DEFAULT_CATEGORY_ID
                ]
            failed_slugs = [
                slug
                for slug in target_slugs
                if slug in projected["skills"]
                and projected["skills"][slug].get("primaryCategoryId")
                == DEFAULT_CATEGORY_ID
            ]

            def mutation(candidate: MutableMapping[str, Any]) -> None:
                nonlocal recovered
                latest = candidate.get("lastOrganization")
                if (
                    not isinstance(latest, dict)
                    or latest.get("runId") != run_id
                    or latest.get("status") != "running"
                ):
                    return
                recovered = {
                    **latest,
                    "status": "failed",
                    "completedAt": str(self.clock()),
                    "interruptedAt": str(self.clock()),
                    "assignedCount": 0,
                    "failureCount": len(failed_slugs),
                    "failures": [self._failure(slug) for slug in failed_slugs],
                    "dismissedAt": None,
                }
                candidate["lastOrganization"] = recovered

            self.repository.update(
                mutation,
                expected_revision=catalog["revision"],
                valid_skill_names=valid_names,
            )

        try:
            self.coordinator.reconcile_stale_start(
                [current],
                is_stale=lambda item: item.get("status") == "running",
                recover=recover,
            )
        except CatalogRevisionConflict:
            return None
        if recovered is None:
            return None
        try:
            self.append_terminal_activity(copy.deepcopy(recovered))
        finally:
            self.finalize_manager(None)
        return copy.deepcopy(recovered)

    def dismiss_marker(self) -> dict[str, Any]:
        """Persist dismissal of the latest terminal marker."""

        dismissed: dict[str, Any] | None = None

        def mutation(catalog: MutableMapping[str, Any]) -> None:
            nonlocal dismissed
            current = catalog.get("lastOrganization")
            if not isinstance(current, dict):
                raise SkillOrganizationMutationError(
                    "organization_result_missing",
                    "No organization result is available",
                    status=404,
                )
            if current.get("status") == "running":
                raise SkillOrganizationMutationError(
                    "organization_running",
                    "Running organization cannot be dismissed",
                    status=409,
                )
            current["dismissedAt"] = str(self.clock())
            dismissed = copy.deepcopy(current)

        saved = self.repository.update(
            mutation, valid_skill_names=library_skill_names(self.library_dir)
        )
        return {
            "ok": True,
            "catalogRevision": saved["revision"],
            "organization": dismissed,
        }

    def correct_skill_category(
        self,
        slug: object,
        category_id: object,
        *,
        expected_revision: int | None,
        tags: object = None,
    ) -> dict[str, Any]:
        """Move exactly one skill with optimistic revision protection."""

        if expected_revision is None:
            raise SkillOrganizationMutationError(
                "catalog_revision_required",
                "catalog revision is required",
            )
        active = self.coordinator.holder()
        if active and active.get("kind") == "skill-organization":
            raise SkillOrganizationMutationError(
                "organization_running",
                "Category changes are disabled during skill organization",
                status=409,
            )
        normalized_slug = normalize_skill_slug(slug)
        normalized_category = normalize_category_id(category_id)
        valid_names = library_skill_names(self.library_dir)
        if normalized_slug not in set(valid_names):
            raise SkillOrganizationMutationError(
                "skill_not_found", "Skill was not found", status=404
            )
        normalized_tags = normalize_tags(tags) if tags is not None else None
        moved: dict[str, Any] = {}

        def mutation(catalog: MutableMapping[str, Any]) -> None:
            nonlocal moved
            category_ids = {
                category.get("id") for category in catalog.get("categories") or []
            }
            if normalized_category not in category_ids:
                raise SkillOrganizationMutationError(
                    "category_not_found", "Category was not found", status=404
                )
            existing = (catalog.get("skills") or {}).get(
                normalized_slug,
                {"primaryCategoryId": DEFAULT_CATEGORY_ID, "tags": []},
            )
            metadata = {
                "primaryCategoryId": normalized_category,
                "tags": (
                    list(normalized_tags)
                    if normalized_tags is not None
                    else list(existing.get("tags") or [])
                ),
            }
            catalog.setdefault("skills", {})[normalized_slug] = metadata
            current = catalog.get("lastOrganization")
            if (
                isinstance(current, dict)
                and normalized_category != DEFAULT_CATEGORY_ID
            ):
                failures = [
                    failure
                    for failure in current.get("failures") or []
                    if failure.get("slug") != normalized_slug
                ]
                if len(failures) != len(current.get("failures") or []):
                    current["failures"] = failures
                    current["failureCount"] = len(failures)
                    if not failures:
                        current["status"] = "resolved"
                        current["resolvedAt"] = str(self.clock())
            moved = copy.deepcopy(metadata)

        saved = self.repository.update(
            mutation,
            expected_revision=int(expected_revision),
            valid_skill_names=valid_names,
        )
        return {
            "ok": True,
            "skill": normalized_slug,
            "metadata": moved,
            "catalogRevision": saved["revision"],
            "organization": copy.deepcopy(saved.get("lastOrganization")),
        }
