#!/usr/bin/env python3
"""Focused tests for the project-scoped repository commit coordinator."""

import copy
import os
import sys
import threading
import time
import ast
import tempfile

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services.project_repository import (
    ProjectAlreadyExistsError,
    ProjectConflictError,
    ProjectNotFoundError,
    ProjectRepository,
)
from project_store import MarkdownProjectStore


class MemoryStore:
    def __init__(self):
        self.data = {
            "projects": [
                {"id": "p1", "title": "One", "activity": [], "scheduledCronHistory": [{"id": "history"}]},
                {"id": "p2", "title": "Two", "activity": []},
            ],
            "templates": [],
        }
        self.lock = threading.Lock()
        self.loads = 0
        self.saves = 0

    def load(self):
        with self.lock:
            self.loads += 1
            return copy.deepcopy(self.data)

    def save(self, value):
        with self.lock:
            self.saves += 1
            self.data = copy.deepcopy(value)


def repository(store=None, repair=None):
    store = store or MemoryStore()
    return store, ProjectRepository(load_projects=store.load, save_projects=store.save, repair_projects=repair)


def test_update_commits_result_and_preserves_latest_cron_history():
    store, repo = repository()
    result = repo.update("p1", lambda project: project.update({"title": "Changed", "scheduledCronHistory": []}) or "ok")
    assert result == "ok"
    assert repo.get("p1")["title"] == "Changed"
    assert repo.get("p1")["scheduledCronHistory"] == [{"id": "history"}]
    assert store.saves == 1
    assert repo.active_lock_entries == 0


def test_different_project_barrier_updates_preserve_both_commits():
    store, repo = repository()
    barrier = threading.Barrier(2)
    errors = []

    def update(project_id, title):
        try:
            def mutate(project):
                barrier.wait(timeout=2)
                project["title"] = title

            repo.update(project_id, mutate)
        except BaseException as exc:  # surfaced below with both thread outcomes
            errors.append(exc)

    threads = [
        threading.Thread(target=update, args=("p1", "One changed")),
        threading.Thread(target=update, args=("p2", "Two changed")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    assert errors == []
    assert repo.get("p1")["title"] == "One changed"
    assert repo.get("p2")["title"] == "Two changed"
    assert repo.active_lock_entries == 0


def test_same_project_updates_are_serialized_and_observe_latest_state():
    _, repo = repository()
    first_entered = threading.Event()
    release_first = threading.Event()
    observations = []

    def first_mutator(project):
        first_entered.set()
        assert release_first.wait(timeout=2)
        project["activity"].append("first")

    first = threading.Thread(target=lambda: repo.update("p1", first_mutator))
    second = threading.Thread(
        target=lambda: repo.update("p1", lambda project: observations.append(list(project["activity"])) or project["activity"].append("second"))
    )
    first.start()
    assert first_entered.wait(timeout=1)
    second.start()
    time.sleep(0.05)
    assert observations == []
    release_first.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert observations == [["first"]]
    assert repo.get("p1")["activity"] == ["first", "second"]


def test_create_delete_root_update_and_errors_do_not_leak_locks():
    _, repo = repository()
    assert repo.create({"id": "p3", "title": "Three"})["id"] == "p3"
    with pytest.raises(ProjectAlreadyExistsError):
        repo.create({"id": "p3", "title": "Duplicate"})
    assert repo.delete("p3") is True
    assert repo.delete("p3") is False
    repo.update_root(lambda data: data.setdefault("templates", []).append({"id": "template-1"}))
    assert repo.load_all()["templates"] == [{"id": "template-1"}]
    with pytest.raises(ProjectNotFoundError):
        repo.update("missing", lambda project: None)
    with pytest.raises(ProjectNotFoundError):
        repo.update("../invalid", lambda project: None)
    assert repo.active_lock_entries == 0


def test_repair_hook_runs_for_reads_and_commits():
    calls = []

    def repair(data):
        calls.append(True)
        data["repaired"] = True
        return data

    _, repo = repository(repair=repair)
    assert repo.load_all()["repaired"] is True
    repo.update("p1", lambda project: project.update({"title": "Repaired"}))
    assert len(calls) >= 1


def test_coherent_snapshot_avoids_redundant_store_reads_and_namespace_invalidates():
    state, repo = repository()
    loads = []
    namespace = ["store-a"]

    def load():
        loads.append(namespace[0])
        return copy.deepcopy(state.data)

    cached = ProjectRepository(
        load_projects=load,
        save_projects=state.save,
        cache_namespace=lambda: namespace[0],
    )
    assert cached.get("p1")["title"] == "One"
    assert cached.get("p1")["title"] == "One"
    cached.update("p1", lambda project: project.update({"title": "Cached"}))
    assert cached.get("p1")["title"] == "Cached"
    assert loads == ["store-a"]

    namespace[0] = "store-b"
    assert cached.get("p1")["title"] == "Cached"
    assert loads == ["store-a", "store-b"]


def test_markdown_revision_invalidates_cache_after_external_file_edit():
    with tempfile.TemporaryDirectory() as status_dir:
        store = MarkdownProjectStore(
            status_dir,
            watch_external_changes=True,
            watch_interval=0.1,
            full_revision_interval=0.2,
        )
        store.save_all({"projects": [{"id": "p1", "title": "One", "tasks": [], "activity": []}], "templates": []})
        repo = ProjectRepository(
            load_projects=store.load_all,
            save_projects=store.save_all,
            cache_namespace=lambda: (store, store.revision()),
        )
        assert repo.get("p1")["title"] == "One"
        project_md = next(
            os.path.join(store.projects_dir, entry, "project.md")
            for entry in os.listdir(store.projects_dir)
        )
        with open(project_md, encoding="utf-8") as source_file:
            source = source_file.read()
        with open(project_md, "w", encoding="utf-8") as output_file:
            output_file.write(source.replace("title: One", "title: Two"))

        deadline = time.time() + 2
        while repo.get("p1")["title"] != "Two" and time.time() < deadline:
            time.sleep(0.02)
        assert repo.get("p1")["title"] == "Two"
        repo.update("p1", lambda project: project.update({"priority": "high"}))
        assert store.get_project("p1")["title"] == "Two"


def test_legacy_snapshots_merge_different_projects_and_same_project_fields():
    _, repo = repository()
    original = repo.load_all()
    legacy = copy.deepcopy(original)
    execution = copy.deepcopy(original)
    legacy["projects"][0]["activity"].append({"id": "activity-1", "type": "legacy"})
    execution["projects"][0]["workflowPhase"] = "executing"
    execution["projects"][1]["title"] = "Two changed"

    repo.commit_snapshot(legacy, original)
    repo.commit_snapshot(execution, original)

    assert repo.get("p1")["activity"] == [{"id": "activity-1", "type": "legacy"}]
    assert repo.get("p1")["workflowPhase"] == "executing"
    assert repo.get("p2")["title"] == "Two changed"


def test_legacy_snapshot_waits_for_project_update_and_rejects_same_field_conflict():
    _, repo = repository()
    legacy = repo.load_all(); legacy["projects"][0]["title"] = "legacy title"
    entered = threading.Event(); release = threading.Event(); errors = []

    def command_mutator(project):
        entered.set(); assert release.wait(timeout=2); project["title"] = "command title"

    command = threading.Thread(target=lambda: repo.update("p1", command_mutator))
    stale = threading.Thread(target=lambda: _capture_error(errors, lambda: repo.commit_snapshot(legacy, {"projects": [{"id": "p1", "title": "One", "activity": [], "scheduledCronHistory": [{"id": "history"}]}, {"id": "p2", "title": "Two", "activity": []}], "templates": []})))
    command.start(); assert entered.wait(timeout=1); stale.start(); time.sleep(0.05); assert errors == []
    release.set(); command.join(timeout=2); stale.join(timeout=2)
    assert len(errors) == 1 and isinstance(errors[0], ProjectConflictError)
    assert repo.get("p1")["title"] == "command title"


def test_legacy_snapshot_waits_then_merges_non_conflicting_comment_with_execution_state():
    _, repo = repository()
    baseline = repo.load_all(); legacy = copy.deepcopy(baseline)
    legacy["projects"][0]["activity"].append({"id": "comment-1", "detail": "comment"})
    entered = threading.Event(); release = threading.Event(); errors = []
    def command_mutator(project):
        entered.set(); assert release.wait(timeout=2); project["workflowPhase"] = "execution_complete"
    command = threading.Thread(target=lambda: repo.update("p1", command_mutator))
    stale = threading.Thread(target=lambda: _capture_error(errors, lambda: repo.commit_snapshot(legacy, baseline)))
    command.start(); assert entered.wait(timeout=1); stale.start(); release.set(); command.join(timeout=2); stale.join(timeout=2)
    assert errors == []
    assert repo.get("p1")["workflowPhase"] == "execution_complete"
    assert repo.get("p1")["activity"] == [{"id": "comment-1", "detail": "comment"}]


def test_stale_snapshot_cannot_delete_a_concurrently_updated_field():
    _, repo = repository()
    baseline = repo.load_all()
    changed = copy.deepcopy(baseline)
    del changed["projects"][0]["scheduledCronHistory"]
    repo.update("p1", lambda project: project["scheduledCronHistory"].append({"id": "new-history"}))

    with pytest.raises(ProjectConflictError):
        repo.commit_snapshot(changed, baseline)

    assert repo.get("p1")["scheduledCronHistory"][-1] == {"id": "new-history"}


def test_stale_snapshots_cannot_add_the_same_field_with_different_values():
    _, repo = repository()
    baseline = repo.load_all()
    first = copy.deepcopy(baseline)
    second = copy.deepcopy(baseline)
    first["projects"][0]["workflowPhase"] = "executing"
    second["projects"][0]["workflowPhase"] = "done"

    repo.commit_snapshot(first, baseline)
    with pytest.raises(ProjectConflictError, match="legacy field addition"):
        repo.commit_snapshot(second, baseline)

    assert repo.get("p1")["workflowPhase"] == "executing"


def test_stale_snapshots_may_add_the_same_field_with_the_same_value():
    _, repo = repository()
    baseline = repo.load_all()
    first = copy.deepcopy(baseline)
    second = copy.deepcopy(baseline)
    first["projects"][0]["workflowPhase"] = "executing"
    second["projects"][0]["workflowPhase"] = "executing"

    repo.commit_snapshot(first, baseline)
    repo.commit_snapshot(second, baseline)

    assert repo.get("p1")["workflowPhase"] == "executing"


def test_stale_snapshot_cannot_delete_a_concurrently_updated_entity():
    _, repo = repository()
    baseline = repo.load_all()
    changed = copy.deepcopy(baseline)
    changed["projects"] = [project for project in changed["projects"] if project["id"] != "p1"]
    repo.update("p1", lambda project: project.update({"workflowPhase": "execution_complete"}))

    with pytest.raises(ProjectConflictError):
        repo.commit_snapshot(changed, baseline)

    assert repo.get("p1")["workflowPhase"] == "execution_complete"


def test_stale_snapshots_cannot_add_same_entity_id_with_different_values():
    _, repo = repository()
    baseline = repo.load_all()
    first = copy.deepcopy(baseline)
    second = copy.deepcopy(baseline)
    first["projects"].append({"id": "p3", "title": "first", "activity": []})
    second["projects"].append({"id": "p3", "title": "second", "activity": []})

    repo.commit_snapshot(first, baseline)
    with pytest.raises(ProjectConflictError, match="legacy entity addition"):
        repo.commit_snapshot(second, baseline)

    assert repo.get("p3")["title"] == "first"


def test_stale_snapshot_cannot_revive_concurrently_deleted_entity():
    _, repo = repository()
    baseline = repo.load_all()
    changed = copy.deepcopy(baseline)
    changed["projects"][0]["title"] = "legacy update"
    repo.delete("p1")

    with pytest.raises(ProjectConflictError, match="legacy entity update"):
        repo.commit_snapshot(changed, baseline)

    assert repo.get("p1") is None


def test_conditional_snapshot_commit_discards_stale_attempt_result():
    _, repo = repository()
    repo.update("p1", lambda project: project.update({"activeAttemptId": "a1"}))
    baseline = repo.load_all()
    completed = copy.deepcopy(baseline)
    completed["projects"][0]["activeAttemptId"] = None
    completed["projects"][0]["workflowPhase"] = "execution_complete"
    repo.update("p1", lambda project: project.update({"activeAttemptId": "a2", "workflowPhase": "executing"}))

    committed = repo.commit_snapshot_if(
        "p1", completed, baseline,
        lambda project: project.get("activeAttemptId") == "a1",
    )

    assert committed is None
    assert repo.get("p1")["activeAttemptId"] == "a2"
    assert repo.get("p1")["workflowPhase"] == "executing"


def test_conditional_project_commit_preserves_other_projects_and_checks_token():
    _, repo = repository()
    baseline = repo.get("p1")
    changed = copy.deepcopy(baseline)
    changed["workflowPhase"] = "execution_complete"
    repo.update("p2", lambda project: project.update({"title": "Concurrent project"}))

    committed = repo.commit_project_if(
        "p1", changed, baseline,
        lambda project: project.get("title") == "One",
    )
    assert committed["workflowPhase"] == "execution_complete"
    assert repo.get("p2")["title"] == "Concurrent project"

    stale = copy.deepcopy(committed)
    stale["workflowPhase"] = "done"
    repo.update("p1", lambda project: project.update({"activeAttemptId": "replacement"}))
    assert repo.commit_project_if(
        "p1", stale, committed,
        lambda project: project.get("activeAttemptId") in (None, ""),
    ) is None
    assert repo.get("p1")["activeAttemptId"] == "replacement"


def test_conditional_project_commit_merges_concurrent_comment_despite_updated_at():
    _, repo = repository()
    repo.update("p1", lambda project: project.update({
        "updatedAt": "2026-01-01T00:00:00+00:00",
        "tasks": [{
            "id": "t1", "title": "Task", "activeAttemptId": "a1",
            "updatedAt": "2026-01-01T00:00:00+00:00", "comments": [],
            "attempts": [{"id": "a1", "status": "executing"}],
        }],
    }))
    baseline = repo.get("p1")
    completed = copy.deepcopy(baseline)
    completed["updatedAt"] = "2026-01-01T00:00:02+00:00"
    completed["tasks"][0].update({
        "activeAttemptId": None,
        "updatedAt": "2026-01-01T00:00:02+00:00",
        "evidence": {"providerStatus": "completed"},
    })

    def add_comment(project):
        project["updatedAt"] = "2026-01-01T00:00:01+00:00"
        task = project["tasks"][0]
        task["updatedAt"] = "2026-01-01T00:00:01+00:00"
        task["comments"].append({"id": "comment-1", "text": "keep me"})

    repo.update("p1", add_comment)
    committed = repo.commit_project_if(
        "p1", completed, baseline,
        lambda project: project["tasks"][0].get("activeAttemptId") == "a1",
    )

    assert committed["tasks"][0]["comments"] == [{"id": "comment-1", "text": "keep me"}]
    assert committed["tasks"][0]["evidence"]["providerStatus"] == "completed"
    assert committed["tasks"][0]["updatedAt"] == "2026-01-01T00:00:02+00:00"


def _capture_error(errors, callback):
    try:
        callback()
    except BaseException as exc:
        errors.append(exc)


def test_repository_module_has_no_server_or_http_dependency():
    path = os.path.join(APP_DIR, "services", "project_repository.py")
    with open(path, encoding="utf-8") as source_file:
        source = source_file.read()
    assert "import server" not in source
    assert "OfficeHandler" not in source
    assert "http.server" not in source


def test_server_project_store_writes_are_confined_to_repository_wiring():
    path = os.path.join(APP_DIR, "server.py")
    with open(path, encoding="utf-8") as source_file:
        source = source_file.read()
    tree = ast.parse(source)
    direct_calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner = node.func.value
        if isinstance(owner, ast.Name) and owner.id == "PROJECT_STORE" and node.func.attr in {"save_all", "delete_project"}:
            direct_calls.append((node.func.attr, node.lineno))
    assert [name for name, _ in direct_calls] == ["save_all", "delete_project"]
    save_function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_save_projects")
    save_source = ast.get_source_segment(source, save_function)
    assert "_PROJECT_REPOSITORY.commit_snapshot" in save_source
    assert "PROJECT_STORE.save_all" not in save_source
