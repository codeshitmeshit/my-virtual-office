"""Thread-safe project mutation boundary independent of HTTP and server globals."""

from __future__ import annotations

import copy
import threading
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator, MutableMapping, TypeVar


T = TypeVar("T")
ProjectData = dict[str, Any]
ProjectMutator = Callable[[ProjectData], T]
RootMutator = Callable[[ProjectData], T]


class ProjectNotFoundError(KeyError):
    """Raised when an atomic project mutation targets an unknown project."""


class ProjectAlreadyExistsError(ValueError):
    """Raised when a create operation would duplicate a project id."""


class ProjectConflictError(RuntimeError):
    """Raised instead of overwriting a field changed after a legacy snapshot."""


@dataclass
class _LockEntry:
    lock: threading.RLock
    references: int = 0


class ProjectRepository:
    """Coordinate in-process project reads and full-store commits.

    Project locks serialize validation and mutation for one project. The short
    store commit lock protects the shared full-project snapshot used by the
    Markdown store. External work must happen outside calls to ``update``.
    """

    def __init__(
        self,
        *,
        load_projects: Callable[[], ProjectData],
        save_projects: Callable[[ProjectData], None],
        repair_projects: Callable[[ProjectData], ProjectData] | None = None,
        delete_project: Callable[[str], bool] | None = None,
        cache_namespace: Callable[[], Any] | None = None,
    ) -> None:
        self._load_projects = load_projects
        self._save_projects = save_projects
        self._repair_projects = repair_projects or (lambda data: data)
        self._delete_project = delete_project
        self._cache_namespace = cache_namespace or (lambda: None)
        self._cache_guard = threading.RLock()
        self._cached_namespace: Any = object()
        self._cached_data: ProjectData | None = None
        self._registry_guard = threading.Lock()
        self._project_locks: dict[str, _LockEntry] = {}
        self._store_commit_lock = threading.Lock()

    def load_all(self) -> ProjectData:
        """Return a repaired snapshot without exposing repository internals."""
        return self._load_repaired()

    def get(self, project_id: str) -> ProjectData | None:
        self._validate_project_id(project_id)
        namespace = self._cache_namespace()
        with self._cache_guard:
            self._ensure_cache_locked(namespace)
            project = self._find_project(self._cached_data or {}, project_id)
            return copy.deepcopy(project) if project is not None else None

    def update(self, project_id: str, mutator: ProjectMutator[T]) -> T:
        """Atomically mutate and commit one project in the current process."""
        self._validate_project_id(project_id)
        with self._project_lock(project_id):
            current = self.get(project_id)
            if current is None:
                raise ProjectNotFoundError(project_id)
            changed = copy.deepcopy(current)
            result = mutator(changed)
            with self._store_commit_lock:
                namespace = self._cache_namespace()
                with self._cache_guard:
                    self._ensure_cache_locked(namespace)
                    coherent = self._cached_data or {"projects": [], "templates": []}
                    latest_current = self._find_project(coherent, project_id)
                    if latest_current is None:
                        raise ProjectNotFoundError(project_id)
                    merged = self._merge_value(current, changed, latest_current)
                    self._preserve_cron_history(latest_current, merged)
                    latest = dict(coherent)
                    latest["projects"] = list(coherent.get("projects", []))
                    self._replace_project(latest, project_id, merged)
                    self._save_coherent(latest)
            return result

    def update_from_snapshot(
        self,
        project_id: str,
        snapshot_project: ProjectData,
        mutator: ProjectMutator[T],
    ) -> T:
        """Reuse a validated project snapshot when it is still the latest version."""
        self._validate_project_id(project_id)
        with self._project_lock(project_id):
            namespace = self._cache_namespace()
            with self._cache_guard:
                self._ensure_cache_locked(namespace)
                coherent_current = self._find_project(self._cached_data or {}, project_id)
                if coherent_current is None:
                    raise ProjectNotFoundError(project_id)
                current = snapshot_project if coherent_current == snapshot_project else copy.deepcopy(coherent_current)
            changed = copy.deepcopy(current)
            result = mutator(changed)
            with self._store_commit_lock:
                with self._cache_guard:
                    self._ensure_cache_locked(self._cache_namespace())
                    coherent = self._cached_data or {"projects": [], "templates": []}
                    latest_current = self._find_project(coherent, project_id)
                    if latest_current is None:
                        raise ProjectNotFoundError(project_id)
                    merged = self._merge_value(current, changed, latest_current)
                    self._preserve_cron_history(latest_current, merged)
                    latest = dict(coherent)
                    latest["projects"] = list(coherent.get("projects", []))
                    self._replace_project(latest, project_id, merged)
                    self._save_coherent(latest)
            return result

    def create(self, project: ProjectData) -> ProjectData:
        """Create a project without accepting a caller-owned full snapshot."""
        project_id = str(project.get("id") or "").strip()
        self._validate_project_id(project_id)
        with self._project_lock(project_id):
            with self._store_commit_lock:
                latest = self._load_repaired()
                if self._find_project(latest, project_id) is not None:
                    raise ProjectAlreadyExistsError(project_id)
                created = copy.deepcopy(project)
                latest.setdefault("projects", []).append(created)
                self._save_coherent(latest)
                return copy.deepcopy(created)

    def delete(self, project_id: str) -> bool:
        """Delete one project through the same coordinated full-store commit."""
        self._validate_project_id(project_id)
        with self._project_lock(project_id):
            with self._store_commit_lock:
                if self._delete_project is not None:
                    deleted = self._delete_project(project_id)
                    if deleted:
                        with self._cache_guard:
                            self._cached_data = None
                    return deleted
                latest = self._load_repaired()
                projects = latest.setdefault("projects", [])
                remaining = [item for item in projects if item.get("id") != project_id]
                if len(remaining) == len(projects):
                    return False
                latest["projects"] = remaining
                self._save_coherent(latest)
                return True

    def commit_snapshot(self, changed: ProjectData, baseline: ProjectData | None = None) -> ProjectData:
        """Three-way merge a legacy load-modify-save snapshot into latest data."""
        if baseline is None:
            raise ValueError("baseline is required for coordinated snapshot commits")
        clean_changed = {key: value for key, value in changed.items() if key != "__vo_repository_base__"}
        clean_baseline = {key: value for key, value in baseline.items() if key != "__vo_repository_base__"}
        affected_ids = self._affected_project_ids(clean_baseline, clean_changed)
        with ExitStack() as stack:
            for project_id in affected_ids:
                stack.enter_context(self._project_lock(project_id))
            with self._store_commit_lock:
                latest = self._load_repaired()
                merged = self._merge_value(clean_baseline, clean_changed, latest, reject_conflicts=True)
                self._save_coherent(merged)
                return merged

    def commit_snapshot_if(
        self,
        project_id: str,
        changed: ProjectData,
        baseline: ProjectData,
        predicate: Callable[[ProjectData], bool],
    ) -> ProjectData | None:
        """Commit a legacy result only if latest target state still matches its token."""
        self._validate_project_id(project_id)
        clean_changed = {key: value for key, value in changed.items() if key != "__vo_repository_base__"}
        clean_baseline = {key: value for key, value in baseline.items() if key != "__vo_repository_base__"}
        with self._project_lock(project_id):
            with self._store_commit_lock:
                latest = self._load_repaired()
                latest_project = self._find_project(latest, project_id)
                if latest_project is None or not predicate(copy.deepcopy(latest_project)):
                    return None
                merged = self._merge_value(clean_baseline, clean_changed, latest, reject_conflicts=True)
                self._save_coherent(merged)
                return merged

    def commit_project_if(
        self,
        project_id: str,
        changed_project: ProjectData,
        baseline_project: ProjectData,
        predicate: Callable[[ProjectData], bool],
    ) -> ProjectData | None:
        """Conditionally merge one project without copying a full caller snapshot."""
        self._validate_project_id(project_id)
        with self._project_lock(project_id):
            with self._store_commit_lock:
                namespace = self._cache_namespace()
                with self._cache_guard:
                    self._ensure_cache_locked(namespace)
                    coherent = self._cached_data or {"projects": [], "templates": []}
                    latest_project = self._find_project(coherent, project_id)
                    if latest_project is None or not predicate(copy.deepcopy(latest_project)):
                        return None
                    merged_project = self._merge_value(
                        baseline_project,
                        changed_project,
                        latest_project,
                        reject_conflicts=True,
                        prefer_changed_keys=frozenset({"updatedAt"}),
                    )
                    self._preserve_cron_history(latest_project, merged_project)
                    latest = dict(coherent)
                    latest["projects"] = list(coherent.get("projects", []))
                    self._replace_project(latest, project_id, merged_project)
                    self._save_coherent(latest)
                    return copy.deepcopy(merged_project)

    def update_root(self, mutator: RootMutator[T]) -> T:
        """Mutate root collections such as templates under the commit lock."""
        with self._store_commit_lock:
            latest = self._load_repaired()
            result = mutator(latest)
            self._save_coherent(latest)
            return result

    @property
    def active_lock_entries(self) -> int:
        """Expose registry size for deterministic leak tests and diagnostics."""
        with self._registry_guard:
            return len(self._project_locks)

    @contextmanager
    def _project_lock(self, project_id: str) -> Iterator[None]:
        with self._registry_guard:
            entry = self._project_locks.get(project_id)
            if entry is None:
                entry = _LockEntry(lock=threading.RLock())
                self._project_locks[project_id] = entry
            entry.references += 1
        entry.lock.acquire()
        try:
            yield
        finally:
            entry.lock.release()
            with self._registry_guard:
                entry.references -= 1
                if entry.references == 0 and self._project_locks.get(project_id) is entry:
                    del self._project_locks[project_id]

    def _load_repaired(self) -> ProjectData:
        namespace = self._cache_namespace()
        with self._cache_guard:
            self._ensure_cache_locked(namespace)
            return copy.deepcopy(self._cached_data)

    def _ensure_cache_locked(self, namespace: Any) -> None:
        if self._cached_data is not None and namespace == self._cached_namespace:
            return
        data = self._load_projects()
        repaired = self._repair_projects(data)
        self._cached_namespace = namespace
        self._cached_data = repaired if repaired is not None else data

    def _save_coherent(self, data: ProjectData) -> None:
        self._save_projects(data)
        with self._cache_guard:
            repaired = self._repair_projects(data)
            self._cached_namespace = self._cache_namespace()
            self._cached_data = repaired if repaired is not None else data

    @staticmethod
    def _validate_project_id(project_id: str) -> None:
        if not project_id or len(project_id) > 256 or project_id.strip() != project_id or any(ord(char) < 32 or char in "/\\" for char in project_id):
            raise ProjectNotFoundError(project_id)

    @staticmethod
    def _find_project(data: MutableMapping[str, Any], project_id: str) -> ProjectData | None:
        return next(
            (item for item in data.get("projects", []) if isinstance(item, dict) and item.get("id") == project_id),
            None,
        )

    @staticmethod
    def _replace_project(data: ProjectData, project_id: str, changed: ProjectData) -> None:
        projects = data.setdefault("projects", [])
        for index, item in enumerate(projects):
            if item.get("id") == project_id:
                projects[index] = copy.deepcopy(changed)
                return
        raise ProjectNotFoundError(project_id)

    @staticmethod
    def _preserve_cron_history(latest: ProjectData, changed: ProjectData) -> None:
        existing_history = latest.get("scheduledCronHistory")
        changed_history = changed.get("scheduledCronHistory")
        if isinstance(existing_history, list) and existing_history and not changed_history:
            changed["scheduledCronHistory"] = copy.deepcopy(existing_history)

    @classmethod
    def _preserve_all_cron_history(cls, latest: ProjectData, changed: ProjectData) -> None:
        latest_by_id = {item.get("id"): item for item in latest.get("projects", []) if isinstance(item, dict)}
        for project in changed.get("projects", []):
            previous = latest_by_id.get(project.get("id")) if isinstance(project, dict) else None
            if previous is not None:
                cls._preserve_cron_history(previous, project)

    @classmethod
    def _merge_value(
        cls,
        baseline: Any,
        changed: Any,
        latest: Any,
        *,
        reject_conflicts: bool = False,
        prefer_changed_keys: frozenset[str] = frozenset(),
    ) -> Any:
        if changed == baseline:
            return copy.deepcopy(latest)
        if latest == baseline:
            return copy.deepcopy(changed)
        if isinstance(baseline, dict) and isinstance(changed, dict) and isinstance(latest, dict):
            merged = copy.deepcopy(latest)
            for key in baseline.keys() - changed.keys():
                if reject_conflicts and key in latest and latest[key] != baseline[key]:
                    raise ProjectConflictError("Project state changed before a legacy field deletion")
                merged.pop(key, None)
            for key, value in changed.items():
                if key not in baseline:
                    merged[key] = copy.deepcopy(value)
                elif key in prefer_changed_keys and value != baseline[key]:
                    latest_value = latest.get(key)
                    if isinstance(value, str) and isinstance(latest_value, str):
                        merged[key] = max(value, latest_value)
                    else:
                        merged[key] = copy.deepcopy(value)
                else:
                    merged[key] = cls._merge_value(
                        baseline[key], value, latest.get(key),
                        reject_conflicts=reject_conflicts,
                        prefer_changed_keys=prefer_changed_keys,
                    )
            return merged
        if isinstance(baseline, list) and isinstance(changed, list) and isinstance(latest, list):
            if cls._has_stable_ids(baseline, changed, latest):
                return cls._merge_entity_list(
                    baseline, changed, latest,
                    reject_conflicts=reject_conflicts,
                    prefer_changed_keys=prefer_changed_keys,
                )
            if changed[: len(baseline)] == baseline:
                additions = changed[len(baseline):]
                return copy.deepcopy(latest + [item for item in additions if item not in latest])
        if reject_conflicts and latest != baseline and changed != latest:
            raise ProjectConflictError("Project state changed after the legacy writer snapshot")
        return copy.deepcopy(changed)

    @staticmethod
    def _has_stable_ids(*values: list[Any]) -> bool:
        items = [item for value in values for item in value]
        return bool(items) and all(isinstance(item, dict) and item.get("id") for item in items)

    @classmethod
    def _merge_entity_list(
        cls,
        baseline: list[Any],
        changed: list[Any],
        latest: list[Any],
        *,
        reject_conflicts: bool = False,
        prefer_changed_keys: frozenset[str] = frozenset(),
    ) -> list[Any]:
        latest = copy.deepcopy(latest)
        baseline_ids = {item["id"] for item in baseline}
        latest_ids = {item["id"] for item in latest}
        for baseline_item in baseline:
            if baseline_item["id"] in latest_ids:
                continue
            baseline_content = {key: value for key, value in baseline_item.items() if key != "id"}
            match = next(
                (
                    item for item in latest
                    if item["id"] not in baseline_ids
                    and {key: value for key, value in item.items() if key != "id"} == baseline_content
                ),
                None,
            )
            if match is not None:
                latest_ids.discard(match["id"])
                match["id"] = baseline_item["id"]
                latest_ids.add(match["id"])
        baseline_by_id = {item["id"]: item for item in baseline}
        changed_by_id = {item["id"]: item for item in changed}
        latest_by_id = {item["id"]: item for item in latest}
        removed = baseline_by_id.keys() - changed_by_id.keys()
        if reject_conflicts:
            for item_id in removed:
                if item_id in latest_by_id and latest_by_id[item_id] != baseline_by_id[item_id]:
                    raise ProjectConflictError("Project state changed before a legacy entity deletion")
        result = [copy.deepcopy(item) for item in latest if item["id"] not in removed]
        positions = {item["id"]: index for index, item in enumerate(result)}
        for item in changed:
            item_id = item["id"]
            if item_id not in baseline_by_id:
                if item_id not in positions:
                    positions[item_id] = len(result)
                    result.append(copy.deepcopy(item))
                continue
            if item_id not in latest_by_id:
                if item != baseline_by_id[item_id]:
                    positions[item_id] = len(result)
                    result.append(copy.deepcopy(item))
                continue
            merged = cls._merge_value(
                baseline_by_id[item_id], item, latest_by_id[item_id],
                reject_conflicts=reject_conflicts,
                prefer_changed_keys=prefer_changed_keys,
            )
            if item_id in positions:
                result[positions[item_id]] = merged
            else:
                positions[item_id] = len(result)
                result.append(merged)
        return result

    @staticmethod
    def _affected_project_ids(baseline: ProjectData | None, changed: ProjectData) -> list[str]:
        changed_map = {item.get("id"): item for item in changed.get("projects", []) if isinstance(item, dict) and item.get("id")}
        if baseline is None:
            return sorted(changed_map)
        baseline_map = {item.get("id"): item for item in baseline.get("projects", []) if isinstance(item, dict) and item.get("id")}
        return sorted(
            project_id for project_id in baseline_map.keys() | changed_map.keys()
            if baseline_map.get(project_id) != changed_map.get(project_id)
        )
