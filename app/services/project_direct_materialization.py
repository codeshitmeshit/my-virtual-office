"""Canonical projection for one conversation-confirmed direct Project."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from services.project_materialization import (
    apply_authoring_overlay,
    materialize_columns,
    materialize_project_base,
    materialize_task_base,
)


def materialize_direct_project(
    *,
    project_id: str,
    request: Mapping[str, Any],
    approved: Mapping[str, Any],
    workspace: Mapping[str, Any],
    template_ref: Mapping[str, Any],
    recurrence_ref: Mapping[str, Any],
    now: str,
) -> dict[str, Any]:
    """Build a direct Project without authorization or persistence effects."""

    column_sequence = {"value": 0}

    def new_column_id() -> str:
        column_sequence["value"] += 1
        return f"{project_id}-column-{column_sequence['value']}"

    columns, column_map = materialize_columns(
        approved.get("columns"), new_id=new_column_id,
    )
    tasks = []
    for index, item in enumerate(approved.get("tasks") or []):
        task_configuration = copy.deepcopy(dict(item))
        source_column = task_configuration.get("columnId")
        if isinstance(source_column, (str, int)) and source_column in column_map:
            task_configuration["columnId"] = column_map[source_column]
        raw_order = task_configuration.get("order")
        tasks.append(materialize_task_base(
            task_configuration,
            columns=columns,
            task_id=str(
                task_configuration.get("id") or f"{project_id}-task-{index + 1}"
            ),
            timestamp=now,
            order=index if raw_order is None else int(raw_order),
            new_id=lambda: f"{project_id}-task-{index + 1}",
            now=lambda: now,
        ))
    created_by = str(request.get("requestingAgentId") or "").strip()
    maintenance_enabled = (
        bool(approved["archiveMaintenanceEnabled"])
        if "archiveMaintenanceEnabled" in approved
        else True
    )
    project = materialize_project_base(
        {**approved, "createdBy": created_by},
        columns=columns,
        tasks=tasks,
        workspace=workspace,
        project_id=project_id,
        timestamp=now,
        new_id=lambda: project_id,
        now=lambda: now,
        archive_maintenance_enabled=maintenance_enabled,
        archive_maintenance_explicit="archiveMaintenanceEnabled" in approved,
        archive_maintenance_updated_by=created_by,
    )
    return apply_authoring_overlay(
        project,
        actor=created_by,
        request_id=str(request.get("id") or ""),
        timestamp=now,
        maintenance_mode=str(
            approved.get("agentMaintenanceMode") or "strict_confirmation"
        ),
        template_ref=template_ref,
        recurrence_ref=recurrence_ref,
    )
