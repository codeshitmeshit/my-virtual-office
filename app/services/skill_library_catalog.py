"""Atomic classification metadata for the local Skills Library.

Skill folders and ``SKILL.md`` remain the content source of truth.  This
repository owns only Virtual Office classification metadata and the latest
organization-run projection.
"""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, MutableMapping


CATALOG_FILENAME = ".vo-library-catalog.json"
CATALOG_SCHEMA_VERSION = 1
DEFAULT_CATEGORY_ID = "default"

SEEDED_CATEGORIES: tuple[dict[str, str], ...] = (
    {"id": DEFAULT_CATEGORY_ID, "name": "默认标签", "kind": "system"},
    {"id": "development-testing", "name": "开发与测试", "kind": "general"},
    {"id": "collaboration-docs", "name": "协作与文档", "kind": "general"},
    {"id": "project-process", "name": "项目与流程", "kind": "general"},
    {"id": "operations-diagnostics", "name": "运维与诊断", "kind": "general"},
    {"id": "knowledge-content", "name": "知识与内容", "kind": "general"},
)

_CATEGORY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_SKILL_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")
_MAX_CATEGORY_NAME = 80
_MAX_TAG_LENGTH = 48
_MAX_TAGS_PER_SKILL = 16
_REPOSITORY_LOCKS_GUARD = threading.Lock()
_REPOSITORY_LOCKS: dict[str, threading.RLock] = {}


class SkillLibraryCatalogError(ValueError):
    """Base error for invalid or unsafe catalog operations."""


class UnsafeSkillLibraryCatalogPath(SkillLibraryCatalogError):
    """Raised when the library or catalog target is a symbolic link."""


class CatalogRevisionConflict(SkillLibraryCatalogError):
    """Raised when an optimistic catalog mutation uses a stale revision."""

    def __init__(self, expected: int, actual: int):
        super().__init__(
            f"Skill Library catalog revision conflict: expected {expected}, actual {actual}"
        )
        self.expected = expected
        self.actual = actual
        self.code = "catalog_revision_conflict"


class ImmutableCategoryError(SkillLibraryCatalogError):
    """Raised when the immutable default category would be changed."""


def default_catalog() -> dict[str, Any]:
    """Return a new canonical empty catalog."""

    return {
        "schemaVersion": CATALOG_SCHEMA_VERSION,
        "revision": 0,
        "categories": copy.deepcopy(list(SEEDED_CATEGORIES)),
        "skills": {},
        "lastOrganization": None,
    }


def _clean_text(value: object, *, field: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise SkillLibraryCatalogError(f"{field} is required")
    if len(text) > limit:
        raise SkillLibraryCatalogError(f"{field} exceeds {limit} characters")
    if any(ord(char) < 32 for char in text) or "/" in text or "\\" in text:
        raise SkillLibraryCatalogError(f"{field} contains unsafe characters")
    if text in {".", ".."}:
        raise SkillLibraryCatalogError(f"{field} contains an unsafe path value")
    return text


def normalize_category_id(value: object) -> str:
    category_id = str(value or "").strip().lower()
    if not _CATEGORY_ID_RE.fullmatch(category_id):
        raise SkillLibraryCatalogError("category id must be a lowercase kebab-case id")
    return category_id


def normalize_skill_slug(value: object) -> str:
    slug = str(value or "").strip().lower()
    if not _SKILL_SLUG_RE.fullmatch(slug):
        raise SkillLibraryCatalogError("skill slug is invalid")
    return slug


def normalize_tags(values: object) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, (list, tuple)):
        raise SkillLibraryCatalogError("tags must be a list")
    if len(values) > _MAX_TAGS_PER_SKILL:
        raise SkillLibraryCatalogError(
            f"a skill may have at most {_MAX_TAGS_PER_SKILL} tags"
        )
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = _clean_text(value, field="tag", limit=_MAX_TAG_LENGTH)
        folded = tag.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        normalized.append(tag)
    return normalized


def _normalize_category(raw: object) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        raise SkillLibraryCatalogError("category must be an object")
    category_id = normalize_category_id(raw.get("id"))
    name = _clean_text(
        raw.get("name"), field="category name", limit=_MAX_CATEGORY_NAME
    )
    kind = str(raw.get("kind") or "ordinary").strip().lower()
    if kind not in {"system", "general", "ordinary"}:
        raise SkillLibraryCatalogError("category kind is invalid")
    if category_id == DEFAULT_CATEGORY_ID and (
        name != "默认标签" or kind != "system"
    ):
        raise ImmutableCategoryError("默认标签 cannot be renamed or retyped")
    return {"id": category_id, "name": name, "kind": kind}


def _normalize_last_organization(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise SkillLibraryCatalogError("lastOrganization must be an object or null")
    # The organization service owns field-level semantics.  The repository
    # guarantees JSON-safe detached data and prevents catalog-shape injection.
    try:
        detached = json.loads(json.dumps(dict(raw), ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise SkillLibraryCatalogError("lastOrganization must be JSON serializable") from exc
    if not isinstance(detached, dict):
        raise SkillLibraryCatalogError("lastOrganization must be an object")
    return detached


def normalize_catalog(raw: object) -> dict[str, Any]:
    """Validate and return a detached canonical catalog."""

    if not isinstance(raw, Mapping):
        raise SkillLibraryCatalogError("catalog must be an object")
    schema_version = raw.get("schemaVersion", CATALOG_SCHEMA_VERSION)
    if schema_version != CATALOG_SCHEMA_VERSION:
        raise SkillLibraryCatalogError(
            f"unsupported catalog schema version: {schema_version}"
        )
    try:
        revision = int(raw.get("revision", 0))
    except (TypeError, ValueError) as exc:
        raise SkillLibraryCatalogError("catalog revision must be an integer") from exc
    if revision < 0:
        raise SkillLibraryCatalogError("catalog revision must not be negative")

    categories_by_id: dict[str, dict[str, str]] = {}
    for seeded in SEEDED_CATEGORIES:
        normalized = _normalize_category(seeded)
        categories_by_id[normalized["id"]] = normalized
    for raw_category in raw.get("categories") or []:
        normalized = _normalize_category(raw_category)
        category_id = normalized["id"]
        existing = categories_by_id.get(category_id)
        if category_id == DEFAULT_CATEGORY_ID and existing != normalized:
            raise ImmutableCategoryError("默认标签 cannot be changed")
        categories_by_id[category_id] = normalized

    skills: dict[str, dict[str, Any]] = {}
    raw_skills = raw.get("skills") or {}
    if not isinstance(raw_skills, Mapping):
        raise SkillLibraryCatalogError("skills must be an object")
    for raw_slug, raw_metadata in raw_skills.items():
        slug = normalize_skill_slug(raw_slug)
        if not isinstance(raw_metadata, Mapping):
            raise SkillLibraryCatalogError(f"metadata for {slug} must be an object")
        category_id = normalize_category_id(
            raw_metadata.get("primaryCategoryId") or DEFAULT_CATEGORY_ID
        )
        if category_id not in categories_by_id:
            raise SkillLibraryCatalogError(
                f"skill {slug} references unknown category {category_id}"
            )
        skills[slug] = {
            "primaryCategoryId": category_id,
            "tags": normalize_tags(raw_metadata.get("tags")),
        }

    return {
        "schemaVersion": CATALOG_SCHEMA_VERSION,
        "revision": revision,
        "categories": list(categories_by_id.values()),
        "skills": skills,
        "lastOrganization": _normalize_last_organization(
            raw.get("lastOrganization")
        ),
    }


class SkillLibraryCatalogRepository:
    """Serialize and atomically persist Skills Library classification metadata."""

    def __init__(
        self,
        library_dir: str | os.PathLike[str],
        *,
        replace: Callable[[str, str], object] = os.replace,
        fsync: Callable[[int], object] = os.fsync,
    ):
        self.library_dir = Path(library_dir).absolute()
        self.path = self.library_dir / CATALOG_FILENAME
        self._replace = replace
        self._fsync = fsync
        lock_key = str(self.path)
        with _REPOSITORY_LOCKS_GUARD:
            self._lock = _REPOSITORY_LOCKS.setdefault(
                lock_key, threading.RLock()
            )

    def _assert_safe_target(self) -> None:
        if self.library_dir.is_symlink():
            raise UnsafeSkillLibraryCatalogPath(
                "skills library directory must not be a symbolic link"
            )
        if self.path.is_symlink():
            raise UnsafeSkillLibraryCatalogPath(
                "skills library catalog must not be a symbolic link"
            )

    def load(self) -> dict[str, Any]:
        """Load a valid catalog or recover to canonical defaults.

        Invalid JSON and invalid catalog shapes are treated as recoverable read
        corruption.  No file is overwritten until a later authorized write.
        Unsafe symbolic-link targets are never recovered silently.
        """

        with self._lock:
            self._assert_safe_target()
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                return normalize_catalog(raw)
            except FileNotFoundError:
                return default_catalog()
            except (
                json.JSONDecodeError,
                OSError,
                SkillLibraryCatalogError,
                TypeError,
                ValueError,
            ):
                return default_catalog()

    def project(self, skill_names: Iterable[object]) -> dict[str, Any]:
        """Return a non-persisted projection reconciled with on-disk skills."""

        with self._lock:
            catalog = self.load()
            valid_slugs = {normalize_skill_slug(name) for name in skill_names}
            projected_skills: dict[str, dict[str, Any]] = {}
            for slug in sorted(valid_slugs):
                metadata = (catalog.get("skills") or {}).get(slug)
                projected_skills[slug] = copy.deepcopy(
                    metadata
                    or {"primaryCategoryId": DEFAULT_CATEGORY_ID, "tags": []}
                )
            catalog["skills"] = projected_skills
            return catalog

    def _write(self, catalog: Mapping[str, Any]) -> None:
        self._assert_safe_target()
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self._assert_safe_target()
        descriptor = -1
        temporary = ""
        try:
            descriptor, temporary = tempfile.mkstemp(
                prefix=".vo-library-catalog.",
                suffix=".tmp",
                dir=self.library_dir,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                descriptor = -1
                json.dump(dict(catalog), output, ensure_ascii=False, indent=2)
                output.write("\n")
                output.flush()
                self._fsync(output.fileno())
            os.chmod(temporary, 0o666, follow_symlinks=False)
            self._assert_safe_target()
            self._replace(temporary, str(self.path))
            temporary = ""
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    @staticmethod
    def _check_revision(catalog: Mapping[str, Any], expected: int | None) -> None:
        if expected is None:
            return
        actual = int(catalog.get("revision") or 0)
        if int(expected) != actual:
            raise CatalogRevisionConflict(int(expected), actual)

    def update(
        self,
        mutation: Callable[[MutableMapping[str, Any]], object],
        *,
        expected_revision: int | None = None,
        valid_skill_names: Iterable[object] | None = None,
    ) -> dict[str, Any]:
        """Apply one validated mutation and atomically increment the revision."""

        with self._lock:
            current = self.load()
            self._check_revision(current, expected_revision)
            candidate: MutableMapping[str, Any] = copy.deepcopy(current)
            mutation(candidate)
            if valid_skill_names is not None:
                valid = {
                    normalize_skill_slug(name) for name in valid_skill_names
                }
                candidate["skills"] = {
                    slug: metadata
                    for slug, metadata in (candidate.get("skills") or {}).items()
                    if slug in valid
                }
            normalized = normalize_catalog(candidate)
            normalized["revision"] = int(current.get("revision") or 0) + 1
            self._write(normalized)
            return copy.deepcopy(normalized)

    def put_category(
        self,
        category_id: object,
        name: object,
        *,
        kind: str = "ordinary",
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        normalized = _normalize_category(
            {"id": category_id, "name": name, "kind": kind}
        )

        def mutation(catalog: MutableMapping[str, Any]) -> None:
            categories = list(catalog.get("categories") or [])
            for index, category in enumerate(categories):
                if category.get("id") != normalized["id"]:
                    continue
                if normalized["id"] == DEFAULT_CATEGORY_ID and category != normalized:
                    raise ImmutableCategoryError("默认标签 cannot be changed")
                categories[index] = normalized
                break
            else:
                categories.append(normalized)
            catalog["categories"] = categories

        return self.update(mutation, expected_revision=expected_revision)

    def delete_category(
        self, category_id: object, *, expected_revision: int | None = None
    ) -> dict[str, Any]:
        normalized_id = normalize_category_id(category_id)
        if normalized_id == DEFAULT_CATEGORY_ID:
            raise ImmutableCategoryError("默认标签 cannot be deleted")

        def mutation(catalog: MutableMapping[str, Any]) -> None:
            categories = list(catalog.get("categories") or [])
            if not any(category.get("id") == normalized_id for category in categories):
                raise SkillLibraryCatalogError("category not found")
            catalog["categories"] = [
                category
                for category in categories
                if category.get("id") != normalized_id
            ]
            for metadata in (catalog.get("skills") or {}).values():
                if metadata.get("primaryCategoryId") == normalized_id:
                    metadata["primaryCategoryId"] = DEFAULT_CATEGORY_ID

        return self.update(mutation, expected_revision=expected_revision)

    def merge_category(
        self,
        source_category_id: object,
        target_category_id: object,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        source = normalize_category_id(source_category_id)
        target = normalize_category_id(target_category_id)
        if source == DEFAULT_CATEGORY_ID:
            raise ImmutableCategoryError("默认标签 cannot be merged")
        if source == target:
            raise SkillLibraryCatalogError("source and target categories must differ")

        def mutation(catalog: MutableMapping[str, Any]) -> None:
            category_ids = {
                category.get("id") for category in catalog.get("categories") or []
            }
            if source not in category_ids or target not in category_ids:
                raise SkillLibraryCatalogError("source or target category not found")
            for metadata in (catalog.get("skills") or {}).values():
                if metadata.get("primaryCategoryId") == source:
                    metadata["primaryCategoryId"] = target
            catalog["categories"] = [
                category
                for category in catalog.get("categories") or []
                if category.get("id") != source
            ]

        return self.update(mutation, expected_revision=expected_revision)

    def set_skill_metadata(
        self,
        skill_slug: object,
        primary_category_id: object,
        *,
        tags: object = None,
        expected_revision: int | None = None,
        valid_skill_names: Iterable[object] | None = None,
    ) -> dict[str, Any]:
        slug = normalize_skill_slug(skill_slug)
        category_id = normalize_category_id(primary_category_id)
        normalized_tags = normalize_tags(tags)

        def mutation(catalog: MutableMapping[str, Any]) -> None:
            category_ids = {
                category.get("id") for category in catalog.get("categories") or []
            }
            if category_id not in category_ids:
                raise SkillLibraryCatalogError(
                    f"unknown primary category: {category_id}"
                )
            catalog.setdefault("skills", {})[slug] = {
                "primaryCategoryId": category_id,
                "tags": normalized_tags,
            }

        return self.update(
            mutation,
            expected_revision=expected_revision,
            valid_skill_names=valid_skill_names,
        )
