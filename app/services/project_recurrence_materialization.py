"""Canonical projection for one claimed recurring project occurrence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.project_materialization import apply_recurrence_overlay
from services.project_template_materialization import materialize_template_project_base


def materialize_recurrence_occurrence_project(
    *,
    project_id: str,
    template_id: str,
    template_version: int,
    recurrence_id: str,
    occurrence_id: str,
    configuration: Mapping[str, Any],
    workspace: Mapping[str, Any],
    actor: str,
    timestamp: str,
) -> dict[str, Any]:
    """Build a deterministic occurrence Project without claim or persistence effects."""

    project = materialize_template_project_base(
        project_id=project_id,
        configuration=configuration,
        workspace=workspace,
        actor=actor,
        timestamp=timestamp,
    )
    return apply_recurrence_overlay(
        project,
        actor=actor,
        timestamp=timestamp,
        template_id=template_id,
        template_version=template_version,
        recurrence_id=recurrence_id,
        occurrence_id=occurrence_id,
    )
