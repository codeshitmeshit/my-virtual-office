"""Default board-shape helpers for projects created from compact drafts."""

from __future__ import annotations

import copy
from typing import Any, Mapping


DEFAULT_PROJECT_COLUMNS: tuple[dict[str, Any], ...] = (
    {"id": "backlog", "title": "Backlog", "color": "#6c757d", "order": 0},
    {"id": "in-progress", "title": "In Progress", "color": "#ffc107", "order": 1},
    {"id": "review", "title": "Review", "color": "#fd7e14", "order": 2},
    {"id": "done", "title": "Done", "color": "#198754", "order": 3},
)


def default_project_columns() -> list[dict[str, Any]]:
    return copy.deepcopy(list(DEFAULT_PROJECT_COLUMNS))


def normalize_compact_project_columns(columns: Any) -> list[dict[str, Any]]:
    """Expand missing or single-column AI drafts to the standard project board."""
    supplied = [copy.deepcopy(dict(column)) for column in columns or [] if isinstance(column, Mapping)]
    if len(supplied) > 1:
        return _normalize_order(supplied)

    defaults = default_project_columns()
    if not supplied:
        return defaults

    first = supplied[0]
    defaults[0].update({key: value for key, value in first.items() if value is not None and key != "order"})
    defaults[0].setdefault("id", "backlog")
    defaults[0].setdefault("title", "Backlog")
    return _normalize_order(defaults)


def _normalize_order(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for index, column in enumerate(columns):
        column.setdefault("id", f"column-{index + 1}")
        column.setdefault("title", f"Column {index + 1}")
        column.setdefault("color", DEFAULT_PROJECT_COLUMNS[min(index, len(DEFAULT_PROJECT_COLUMNS) - 1)]["color"])
        column["order"] = index if column.get("order") is None else column.get("order")
    return columns
