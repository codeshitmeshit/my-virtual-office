"""Reconcile Skills Library files with Virtual Office classification metadata.

The directory tree remains the source of truth for skill existence. Reads only
project catalog metadata over that tree; authorized skill mutations may compact
stale metadata while recording newly-created skills in ``默认标签``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from services.skill_library_catalog import (
    DEFAULT_CATEGORY_ID,
    SkillLibraryCatalogRepository,
    normalize_skill_slug,
)


def library_skill_names(library_dir: str | os.PathLike[str]) -> list[str]:
    """Return safe, normalized skill folders that contain a regular SKILL.md."""

    root = Path(library_dir)
    try:
        entries = list(root.iterdir())
    except (FileNotFoundError, NotADirectoryError, OSError):
        return []

    names: list[str] = []
    for entry in entries:
        if entry.is_symlink() or not entry.is_dir():
            continue
        skill_file = entry / "SKILL.md"
        if skill_file.is_symlink() or not skill_file.is_file():
            continue
        try:
            slug = normalize_skill_slug(entry.name)
        except ValueError:
            continue
        names.append(slug)
    return sorted(set(names))


def enrich_skill_list(
    library_dir: str | os.PathLike[str],
    skills: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Add classification fields without changing existing skill-list fields."""

    skill_rows = [dict(skill) for skill in skills]
    names = library_skill_names(library_dir)
    catalog = SkillLibraryCatalogRepository(library_dir).project(names)
    categories = catalog["categories"]
    category_by_id = {category["id"]: category for category in categories}

    for skill in skill_rows:
        try:
            slug = normalize_skill_slug(skill.get("name"))
        except ValueError:
            slug = ""
        metadata = catalog["skills"].get(
            slug,
            {"primaryCategoryId": DEFAULT_CATEGORY_ID, "tags": []},
        )
        category_id = metadata["primaryCategoryId"]
        skill["primaryCategoryId"] = category_id
        skill["primaryCategory"] = dict(category_by_id[category_id])
        skill["tags"] = list(metadata.get("tags") or [])

    return {
        "skills": skill_rows,
        "categories": categories,
        "catalogRevision": catalog["revision"],
        "organization": catalog.get("lastOrganization"),
    }


def record_skill_in_default(
    library_dir: str | os.PathLike[str],
    slug: str,
    *,
    valid_skill_names: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Record a new skill in the default category and compact stale entries."""

    valid = (
        list(valid_skill_names)
        if valid_skill_names is not None
        else library_skill_names(library_dir)
    )
    return SkillLibraryCatalogRepository(library_dir).set_skill_metadata(
        slug,
        DEFAULT_CATEGORY_ID,
        tags=[],
        valid_skill_names=valid,
    )


def compact_skill_catalog(
    library_dir: str | os.PathLike[str],
    *,
    valid_skill_names: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Remove metadata for missing skills as part of an authorized write."""

    valid = (
        list(valid_skill_names)
        if valid_skill_names is not None
        else library_skill_names(library_dir)
    )
    repository = SkillLibraryCatalogRepository(library_dir)
    return repository.update(lambda _catalog: None, valid_skill_names=valid)
