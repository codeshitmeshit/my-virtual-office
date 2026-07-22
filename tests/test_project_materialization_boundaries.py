#!/usr/bin/env python3
"""Static inventory for Project/Task creation authorities during convergence."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


@dataclass(frozen=True, order=True)
class MaterializationSite:
    path: str
    symbol: str
    kind: str


CURRENT_MATERIALIZATION_BUILDERS = frozenset({
    MaterializationSite("app/office.py", "proj_cmd", "project"),
    MaterializationSite("app/office.py", "proj_cmd", "task"),
    MaterializationSite(
        "app/services/project_authoring.py",
        "ProjectAuthoringService._apply_maintenance_mutation",
        "task",
    ),
    MaterializationSite(
        "app/services/project_authoring.py",
        "ProjectAuthoringService._build_project",
        "project",
    ),
    MaterializationSite(
        "app/services/project_authoring.py",
        "ProjectAuthoringService._build_project",
        "task",
    ),
    MaterializationSite(
        "app/services/project_authoring.py",
        "ProjectAuthoringService._build_template_instance_project",
        "project",
    ),
    MaterializationSite(
        "app/services/project_authoring.py",
        "ProjectAuthoringService._build_template_instance_project",
        "task",
    ),
})

# Task 7.1 replaces CURRENT_MATERIALIZATION_BUILDERS with this final boundary.
FINAL_MATERIALIZATION_BOUNDARY = frozenset({
    MaterializationSite(
        "app/services/project_materialization.py", "materialize_project_base", "project",
    ),
    MaterializationSite(
        "app/services/project_materialization.py", "materialize_task_base", "task",
    ),
})

NON_BUILDER_INVENTORY = {
    MaterializationSite("app/project_store.py", "MarkdownProjectStore._read_project_dir", "project"): "reader",
    MaterializationSite("app/project_store.py", "MarkdownProjectStore._read_task_file", "task"): "reader",
    MaterializationSite("app/project_store.py", "MarkdownProjectStore._write_task_file", "task"): "serializer",
    MaterializationSite("app/services/project_templates.py", "build_template_snapshot", "project"): "blueprint",
    MaterializationSite("app/services/project_repository.py", "ProjectRepository.create", "project"): "persistence_sink",
    MaterializationSite("app/services/project_direct_creation.py", "DirectProjectCreationService._commit", "project"): "persistence_sink",
    MaterializationSite("app/services/project_authoring.py", "ProjectAuthoringService._commit_materialization", "project"): "persistence_sink",
}

PROJECT_LITERAL_MARKERS = frozenset({"id", "title", "columns", "tasks", "activity"})
TASK_LITERAL_MARKERS = frozenset({"id", "title", "columnId", "order"})
TASK_UPDATE_MARKERS = frozenset({"id", "columnId", "order", "executionState"})


def _literal_keys(node: ast.Dict) -> set[str]:
    return {
        key.value
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }


def _owned_nodes(function: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterable[ast.AST]:
    """Walk one function body without attributing nested functions to its owner."""

    pending = list(function.body)
    while pending:
        node = pending.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        pending.extend(ast.iter_child_nodes(node))


def _function_symbol(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    parents: dict[ast.AST, ast.AST],
) -> str:
    names = [function.name]
    owner = parents.get(function)
    while owner is not None:
        if isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(owner.name)
        owner = parents.get(owner)
    return ".".join(reversed(names))


def _contains_maintenance_task_builder(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if function.name != "_apply_maintenance_mutation":
        return False
    nodes = tuple(_owned_nodes(function))
    has_create_task_branch = any(
        isinstance(node, ast.Compare)
        and any(
            isinstance(part, ast.Constant) and part.value == "create_task"
            for part in (node.left, *node.comparators)
        )
        for node in nodes
    )
    has_task_append = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "append"
        and isinstance(node.func.value, ast.Call)
        and isinstance(node.func.value.func, ast.Attribute)
        and node.func.value.func.attr == "setdefault"
        and bool(node.func.value.args)
        and isinstance(node.func.value.args[0], ast.Constant)
        and node.func.value.args[0].value == "tasks"
        for node in nodes
    )
    return has_create_task_branch and has_task_append


def discover_materialization_candidates() -> set[MaterializationSite]:
    discovered: set[MaterializationSite] = set()
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        relative = path.relative_to(ROOT).as_posix()
        for function in (
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            symbol = _function_symbol(function, parents)
            project_builder = False
            task_builder = _contains_maintenance_task_builder(function)
            for node in _owned_nodes(function):
                if isinstance(node, ast.Dict):
                    keys = _literal_keys(node)
                    project_builder = project_builder or PROJECT_LITERAL_MARKERS <= keys
                    task_builder = task_builder or TASK_LITERAL_MARKERS <= keys
                elif (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "update"
                    and node.args
                    and isinstance(node.args[0], ast.Dict)
                ):
                    task_builder = task_builder or TASK_UPDATE_MARKERS <= _literal_keys(node.args[0])
            if project_builder:
                discovered.add(MaterializationSite(relative, symbol, "project"))
            if task_builder:
                discovered.add(MaterializationSite(relative, symbol, "task"))
    return discovered


def test_current_creation_builder_inventory_is_complete_and_explicit():
    candidates = discover_materialization_candidates()
    excluded = set(NON_BUILDER_INVENTORY)
    builders = candidates - excluded

    assert builders == set(CURRENT_MATERIALIZATION_BUILDERS) | (
        builders & set(FINAL_MATERIALIZATION_BOUNDARY)
    )
    assert set(CURRENT_MATERIALIZATION_BUILDERS) <= builders
    assert set(CURRENT_MATERIALIZATION_BUILDERS).isdisjoint(excluded)


def test_inventory_classifies_non_builders_and_defines_final_boundary():
    assert set(NON_BUILDER_INVENTORY.values()) == {
        "reader", "serializer", "blueprint", "persistence_sink",
    }
    assert FINAL_MATERIALIZATION_BOUNDARY == {
        MaterializationSite(
            "app/services/project_materialization.py", "materialize_project_base", "project",
        ),
        MaterializationSite(
            "app/services/project_materialization.py", "materialize_task_base", "task",
        ),
    }
    assert set(CURRENT_MATERIALIZATION_BUILDERS).isdisjoint(FINAL_MATERIALIZATION_BOUNDARY)
