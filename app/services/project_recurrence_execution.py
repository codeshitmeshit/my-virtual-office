"""Execution-mode contract for recurring project definitions and occurrences."""

from __future__ import annotations

from typing import Any, Mapping


CREATE_ONLY = "create_only"
CREATE_AND_EXECUTE = "create_and_execute"
RECURRENCE_EXECUTION_MODES = frozenset({CREATE_ONLY, CREATE_AND_EXECUTE})


def stored_recurrence_execution_mode(recurrence: Mapping[str, Any] | None) -> str:
    """Read durable intent, defaulting historical definitions to create-only."""

    value = recurrence.get("executionMode") if isinstance(recurrence, Mapping) else None
    return str(value) if value in RECURRENCE_EXECUTION_MODES else CREATE_ONLY
