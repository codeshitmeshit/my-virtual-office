"""Canonical projection for one immutable versioned-template instance."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from itertools import count
from typing import Any

from services.project_actors import legacy_task_role_fields, task_actor_references
from services.project_board_defaults import normalize_compact_project_columns
from services.project_task_checklists import normalize_task_checklist
from services.project_materialization import (
    apply_template_overlay,
    materialize_columns,
    materialize_project_base,
    materialize_task_base,
)


def materialize_template_project_base(
    *,
    project_id: str,
    configuration: Mapping[str, Any],
    workspace: Mapping[str, Any],
    actor: str,
    timestamp: str,
) -> dict[str, Any]:
    """Materialize the canonical base shared by immutable template instances."""

    column_sequence = count(1)
    columns, column_map = materialize_columns(
        normalize_compact_project_columns(configuration.get("columns")),
        new_id=lambda: f"{project_id}-column-{next(column_sequence)}",
    )
    tasks = []
    for index, blueprint in enumerate(configuration.get("tasks") or []):
        task_configuration = copy.deepcopy(dict(blueprint))
        task_configuration["checklist"] = normalize_task_checklist(
            task_configuration, index=index,
        )
        source_column = task_configuration.get("columnId")
        if isinstance(source_column, (str, int)) and source_column in column_map:
            task_configuration["columnId"] = column_map[source_column]
        task_configuration.update(
            legacy_task_role_fields(task_actor_references(task_configuration))
        )
        raw_order = task_configuration.get("order")
        tasks.append(materialize_task_base(
            task_configuration,
            columns=columns,
            task_id=f"{project_id}-task-{index + 1}",
            timestamp=timestamp,
            order=index if raw_order is None else int(raw_order),
            new_id=lambda: f"{project_id}-task-{index + 1}",
            now=lambda: timestamp,
        ))

    execution = configuration.get("executionSettings")
    execution_settings = dict(execution) if isinstance(execution, Mapping) else {}
    project = materialize_project_base(
        {
            **configuration,
            **execution_settings,
            "projectType": "one_time",
            "createdBy": actor,
        },
        columns=columns,
        tasks=tasks,
        workspace=workspace,
        project_id=project_id,
        timestamp=timestamp,
        new_id=lambda: project_id,
        now=lambda: timestamp,
        archive_maintenance_enabled=True,
        archive_maintenance_explicit=False,
        archive_maintenance_updated_by=actor,
    )
    project["agentMaintenanceMode"] = (
        configuration.get("agentMaintenanceMode") or "strict_confirmation"
    )
    return project


def materialize_versioned_template_instance(
    *,
    project_id: str,
    template_id: str,
    version: int,
    configuration: Mapping[str, Any],
    workspace: Mapping[str, Any],
    actor: str,
    timestamp: str,
) -> dict[str, Any]:
    """Materialize one version-pinned template instance without persistence effects."""

    project = materialize_template_project_base(
        project_id=project_id,
        configuration=configuration,
        workspace=workspace,
        actor=actor,
        timestamp=timestamp,
    )
    return apply_template_overlay(
        project,
        actor=actor,
        timestamp=timestamp,
        template_id=template_id,
        template_version=version,
    )
