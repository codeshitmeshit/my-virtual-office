"""Explicit application runtime for Skills Library organization routes."""

from __future__ import annotations

import copy
from typing import Any, Callable, Mapping

from services.skill_library_catalog_integration import library_skill_names
from services.skill_library_organization_admin import (
    SkillLibraryOrganizationAdmin,
)
from services.skill_library_organization_runs import (
    SkillLibraryOrganizationService,
    SkillOrganizationStartError,
)


def _public_organization(value: object) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    allowed = (
        "runId",
        "status",
        "startedAt",
        "completedAt",
        "interruptedAt",
        "resolvedAt",
        "totalCount",
        "processedCount",
        "assignedCount",
        "failureCount",
        "dismissedAt",
    )
    result = {key: copy.deepcopy(value.get(key)) for key in allowed if key in value}
    result["failures"] = [
        {
            "slug": str(item.get("slug") or ""),
            "code": str(item.get("code") or "classification_failed"),
            "reason": str(item.get("reason") or "归类失败"),
        }
        for item in value.get("failures") or []
        if isinstance(item, Mapping) and item.get("slug")
    ]
    return result


class SkillLibraryOrganizationRuntime:
    """Compose organization domain services with transport-facing projections."""

    def __init__(
        self,
        *,
        organizer: SkillLibraryOrganizationService,
        admin: SkillLibraryOrganizationAdmin,
        list_skills: Callable[[], Mapping[str, Any]],
        archive_manager_state: Callable[[], Mapping[str, Any]],
        organization_enabled: Callable[[], bool] = lambda: True,
    ):
        self.organizer = organizer
        self.admin = admin
        self.list_skills = list_skills
        self.archive_manager_state = archive_manager_state
        self.organization_enabled = organization_enabled

    def library_projection(self) -> dict[str, Any]:
        response = dict(self.list_skills() or {})
        catalog = self.organizer.repository.project(
            library_skill_names(self.organizer.library_dir)
        )
        response.setdefault("categories", copy.deepcopy(catalog["categories"]))
        response.setdefault("catalogRevision", catalog["revision"])
        organization = response.get("organization", catalog.get("lastOrganization"))
        response["organization"] = _public_organization(organization)
        response["archiveManager"] = copy.deepcopy(
            dict(self.archive_manager_state() or {})
        )
        response["organizationEnabled"] = bool(self.organization_enabled())
        return response

    def start_run(self) -> dict[str, Any]:
        if not self.organization_enabled():
            raise SkillOrganizationStartError(
                "skill_organization_disabled",
                "Skill Library organization is disabled",
                status=404,
            )
        result = self.organizer.start()
        return {"ok": True, **result, "_status": 202}

    def dismiss(self) -> dict[str, Any]:
        return self.admin.dismiss_marker()

    def correct_skill(self, slug: str, body: Mapping[str, Any]) -> dict[str, Any]:
        return self.admin.correct_skill_category(
            slug,
            body.get("categoryId"),
            expected_revision=body.get("expectedRevision"),
            tags=body.get("tags") if "tags" in body else None,
        )

    def recover_interrupted_run(self) -> dict[str, Any] | None:
        return self.admin.recover_interrupted_run()
