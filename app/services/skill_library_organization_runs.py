"""Asynchronous Skills Library organization using the archive manager."""

from __future__ import annotations

import copy
import hashlib
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, Sequence

from services.archive_manager_work_coordinator import (
    ArchiveManagerBusyError,
    ArchiveManagerWorkCoordinator,
    ArchiveManagerWorkLease,
)
from services.skill_library_catalog import (
    DEFAULT_CATEGORY_ID,
    SkillLibraryCatalogRepository,
)
from services.skill_library_catalog_integration import library_skill_names
from services.skill_library_organization import (
    MAX_BATCH_SIZE,
    OrganizationContractError,
    build_classification_prompt,
    parse_classification_reply,
    summarize_skill,
)


class SkillOrganizationStartError(RuntimeError):
    """Stable precondition failure raised before an organization run starts."""

    def __init__(self, code: str, message: str, *, status: int = 409):
        self.code = code
        self.status = status
        super().__init__(message)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_thread_factory(target: Callable[[], None], name: str) -> threading.Thread:
    return threading.Thread(target=target, name=name, daemon=True)


def _safe_category_id(name: str, existing: Mapping[str, str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:48]
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:10]
    if not base:
        base = f"category-{digest}"
    candidate = base
    if candidate == DEFAULT_CATEGORY_ID:
        candidate = f"category-{digest}"
    if candidate in existing and existing[candidate] != name:
        candidate = f"{base[:52]}-{digest}"
    return candidate[:63]


class SkillLibraryOrganizationService:
    """Own organization-run preconditions, execution, and terminal persistence."""

    def __init__(
        self,
        library_dir: str | Path,
        *,
        coordinator: ArchiveManagerWorkCoordinator,
        manager_state: Callable[[], Mapping[str, Any]],
        call_archive_manager: Callable[[str, int], object],
        mark_manager_working: Callable[[str], None] = lambda _label: None,
        finalize_manager: Callable[[BaseException | None], None] = lambda _error: None,
        append_terminal_activity: Callable[[Mapping[str, Any]], None] = (
            lambda _summary: None
        ),
        clock: Callable[[], str] = _utc_now,
        run_id_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
        thread_factory: Callable[
            [Callable[[], None], str], Any
        ] = _default_thread_factory,
        timeout_seconds: int = 600,
    ):
        self.library_dir = Path(library_dir)
        self.repository = SkillLibraryCatalogRepository(self.library_dir)
        self.coordinator = coordinator
        self.manager_state = manager_state
        self.call_archive_manager = call_archive_manager
        self.mark_manager_working = mark_manager_working
        self.finalize_manager = finalize_manager
        self.append_terminal_activity = append_terminal_activity
        self.clock = clock
        self.run_id_factory = run_id_factory
        self.thread_factory = thread_factory
        self.timeout_seconds = max(1, min(int(timeout_seconds), 600))

    def _manager_precondition(self) -> Mapping[str, Any]:
        state = dict(self.manager_state() or {})
        if state.get("paused") or state.get("status") == "paused":
            raise SkillOrganizationStartError(
                "archive_manager_paused", "Archive manager is paused"
            )
        status = str(state.get("status") or "missing")
        if status in {"missing", "error", "offline", "unavailable"} or not state.get(
            "agentId"
        ):
            raise SkillOrganizationStartError(
                "archive_manager_unavailable", "Archive manager is unavailable"
            )
        if status == "working":
            raise SkillOrganizationStartError(
                "archive_manager_busy", "Archive manager is busy"
            )
        return state

    def _snapshot_default_skills(self) -> tuple[list[str], dict[str, Any]]:
        names = library_skill_names(self.library_dir)
        catalog = self.repository.project(names)
        slugs = [
            slug
            for slug, metadata in catalog["skills"].items()
            if metadata.get("primaryCategoryId") == DEFAULT_CATEGORY_ID
        ]
        return sorted(slugs), catalog

    def start(self) -> dict[str, Any]:
        """Persist and dispatch one run, returning before background completion."""

        self._manager_precondition()
        try:
            lease = self.coordinator.acquire(
                "skill-organization",
                label="整理技能库",
                metadata={"source": "skills-library"},
            )
        except ArchiveManagerBusyError as exc:
            raise SkillOrganizationStartError(
                exc.code, "Archive manager is busy"
            ) from exc

        marked_working = False
        persisted_run: tuple[str, Sequence[str]] | None = None
        try:
            slugs, catalog = self._snapshot_default_skills()
            if not slugs:
                raise SkillOrganizationStartError(
                    "default_category_empty",
                    "No skills in 默认标签 need organization",
                    status=422,
                )
            run_id = str(self.run_id_factory())
            started_at = str(self.clock())
            running = {
                "runId": run_id,
                "status": "running",
                "startedAt": started_at,
                "completedAt": None,
                "totalCount": len(slugs),
                "processedCount": 0,
                "assignedCount": 0,
                "failureCount": 0,
                "failures": [],
                "targetSlugs": list(slugs),
                "dismissedAt": None,
            }
            self.mark_manager_working("整理技能库")
            marked_working = True
            self.repository.update(
                lambda candidate: candidate.__setitem__(
                    "lastOrganization", copy.deepcopy(running)
                ),
                expected_revision=catalog["revision"],
                valid_skill_names=library_skill_names(self.library_dir),
            )
            persisted_run = (run_id, slugs)
            worker = self.thread_factory(
                lambda: self._run_worker(lease, slugs, run_id),
                f"skill-library-organization-{run_id}",
            )
            worker.start()
            return copy.deepcopy(running)
        except BaseException as exc:
            if persisted_run is not None:
                failed = self._catastrophic_terminal(*persisted_run)
                try:
                    self.append_terminal_activity(copy.deepcopy(failed))
                except Exception:
                    pass
            try:
                if marked_working:
                    self.finalize_manager(exc)
            finally:
                self.coordinator.release(lease)
            raise

    @staticmethod
    def _batch_failure(slug: str, code: str, reason: str) -> dict[str, str]:
        return {"slug": slug, "code": code, "reason": reason}

    def _progress(self, run_id: str, processed: int, failures: int) -> None:
        def mutation(catalog: MutableMapping[str, Any]) -> None:
            current = catalog.get("lastOrganization")
            if not isinstance(current, dict) or current.get("runId") != run_id:
                raise RuntimeError("organization run was replaced")
            current["processedCount"] = processed
            current["failureCount"] = failures

        self.repository.update(
            mutation, valid_skill_names=library_skill_names(self.library_dir)
        )

    def _execute(
        self, slugs: Sequence[str], run_id: str
    ) -> dict[str, Any]:
        projected = self.repository.project(library_skill_names(self.library_dir))
        prompt_categories = projected["categories"]
        summaries: list[dict[str, str]] = []
        failures: dict[str, dict[str, str]] = {}
        for slug in slugs:
            try:
                summaries.append(summarize_skill(self.library_dir, slug))
            except OrganizationContractError:
                failures[slug] = self._batch_failure(
                    slug, "skill_unreadable", "无法读取该 Skill 的安全摘要"
                )

        assignments: dict[str, dict[str, Any]] = {}
        processed = len(failures)
        for index in range(0, len(summaries), MAX_BATCH_SIZE):
            batch = summaries[index : index + MAX_BATCH_SIZE]
            batch_slugs = [item["slug"] for item in batch]
            try:
                prompt = build_classification_prompt(batch, prompt_categories)
                reply = self.call_archive_manager(prompt, self.timeout_seconds)
                parsed = parse_classification_reply(
                    reply,
                    expected_slugs=batch_slugs,
                    categories=prompt_categories,
                )
                for assignment in parsed.assignments:
                    assignments[assignment["slug"]] = dict(assignment)
                for failure in parsed.failures:
                    failures[failure["slug"]] = dict(failure)
            except TimeoutError:
                for slug in batch_slugs:
                    failures[slug] = self._batch_failure(
                        slug, "archive_manager_timeout", "档案管理员归类超时"
                    )
            except Exception:
                for slug in batch_slugs:
                    failures[slug] = self._batch_failure(
                        slug,
                        "archive_manager_invalid_response",
                        "档案管理员未返回有效归类结果",
                    )
            processed += len(batch_slugs)
            self._progress(run_id, processed, len(failures))

        return self._commit_terminal(run_id, slugs, assignments, failures)

    def _commit_terminal(
        self,
        run_id: str,
        snapshot_slugs: Sequence[str],
        assignments: Mapping[str, Mapping[str, Any]],
        failures: Mapping[str, Mapping[str, str]],
    ) -> dict[str, Any]:
        terminal: dict[str, Any] = {}
        valid_names = library_skill_names(self.library_dir)
        valid_set = set(valid_names)

        def mutation(catalog: MutableMapping[str, Any]) -> None:
            nonlocal terminal
            current = catalog.get("lastOrganization")
            if not isinstance(current, dict) or current.get("runId") != run_id:
                raise RuntimeError("organization run was replaced")
            categories = list(catalog.get("categories") or [])
            category_names = {
                str(category.get("name") or "").casefold(): category["id"]
                for category in categories
            }
            category_ids = {
                category["id"]: str(category.get("name") or "")
                for category in categories
            }
            final_failures = {
                slug: dict(failure) for slug, failure in failures.items()
            }
            assigned_count = 0
            skill_metadata = catalog.setdefault("skills", {})

            for slug in snapshot_slugs:
                assignment = assignments.get(slug)
                if assignment is None or slug in final_failures:
                    continue
                metadata = skill_metadata.get(
                    slug, {"primaryCategoryId": DEFAULT_CATEGORY_ID, "tags": []}
                )
                if (
                    slug not in valid_set
                    or metadata.get("primaryCategoryId") != DEFAULT_CATEGORY_ID
                ):
                    final_failures[slug] = self._batch_failure(
                        slug,
                        "skill_changed",
                        "Skill 在整理期间已被删除或移动",
                    )
                    continue
                category_id = assignment.get("categoryId")
                if not category_id:
                    category_name = str(assignment.get("newCategoryName") or "")
                    category_id = category_names.get(category_name.casefold())
                    if not category_id:
                        category_id = _safe_category_id(category_name, category_ids)
                        categories.append(
                            {
                                "id": category_id,
                                "name": category_name,
                                "kind": "ordinary",
                            }
                        )
                        category_ids[category_id] = category_name
                        category_names[category_name.casefold()] = category_id
                if category_id not in category_ids:
                    final_failures[slug] = self._batch_failure(
                        slug,
                        "category_changed",
                        "目标分类在整理期间已不可用",
                    )
                    continue
                skill_metadata[slug] = {
                    "primaryCategoryId": category_id,
                    "tags": list(assignment.get("tags") or []),
                }
                assigned_count += 1

            ordered_failures = [
                final_failures[slug]
                for slug in snapshot_slugs
                if slug in final_failures
            ]
            if assigned_count == 0:
                status = "failed"
            elif ordered_failures:
                status = "partial"
            else:
                status = "completed"
            terminal = {
                **current,
                "status": status,
                "completedAt": str(self.clock()),
                "processedCount": len(snapshot_slugs),
                "assignedCount": assigned_count,
                "failureCount": len(ordered_failures),
                "failures": ordered_failures,
                "dismissedAt": None,
            }
            catalog["categories"] = categories
            catalog["skills"] = skill_metadata
            catalog["lastOrganization"] = terminal

        self.repository.update(mutation, valid_skill_names=valid_names)
        return copy.deepcopy(terminal)

    def _catastrophic_terminal(
        self, run_id: str, slugs: Sequence[str]
    ) -> dict[str, Any]:
        failures = {
            slug: self._batch_failure(
                slug, "organization_internal_error", "技能库整理未能完成"
            )
            for slug in slugs
        }
        try:
            return self._commit_terminal(run_id, slugs, {}, failures)
        except Exception:
            return {
                "runId": run_id,
                "status": "failed",
                "completedAt": str(self.clock()),
                "totalCount": len(slugs),
                "processedCount": len(slugs),
                "assignedCount": 0,
                "failureCount": len(slugs),
                "failures": list(failures.values()),
                "dismissedAt": None,
            }

    def _run_worker(
        self,
        lease: ArchiveManagerWorkLease,
        slugs: Sequence[str],
        run_id: str,
    ) -> None:
        failure: BaseException | None = None
        try:
            summary = self._execute(slugs, run_id)
        except BaseException as exc:
            failure = exc
            summary = self._catastrophic_terminal(run_id, slugs)
        try:
            self.append_terminal_activity(copy.deepcopy(summary))
        finally:
            try:
                self.finalize_manager(failure)
            finally:
                self.coordinator.release(lease)
