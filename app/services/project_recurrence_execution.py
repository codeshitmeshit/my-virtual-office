"""Execution-mode contract for recurring project definitions and occurrences."""

from __future__ import annotations

import copy
from typing import Any, Mapping


CREATE_ONLY = "create_only"
CREATE_AND_EXECUTE = "create_and_execute"
RECURRENCE_EXECUTION_MODES = frozenset({CREATE_ONLY, CREATE_AND_EXECUTE})
PENDING = "pending"
STARTED = "started"
FAILED_RETRYABLE = "failed_retryable"
INTERVENTION_REQUIRED = "intervention_required"
EXECUTION_INTENT_STATES = frozenset({
    PENDING, STARTED, FAILED_RETRYABLE, INTERVENTION_REQUIRED,
})


def stored_recurrence_execution_mode(recurrence: Mapping[str, Any] | None) -> str:
    """Read durable intent, defaulting historical definitions to create-only."""

    value = recurrence.get("executionMode") if isinstance(recurrence, Mapping) else None
    return str(value) if value in RECURRENCE_EXECUTION_MODES else CREATE_ONLY


def new_occurrence_execution_intent(
    *, project_id: str, occurrence_id: str, timestamp: str,
) -> dict[str, Any]:
    """Create the durable pending intent committed with an occurrence Project."""

    return {
        "state": PENDING,
        "projectId": project_id,
        "occurrenceId": occurrence_id,
        "attempts": 0,
        "requestedAt": timestamp,
        "updatedAt": timestamp,
        "code": None,
        "history": [{"state": PENDING, "at": timestamp, "code": None}],
    }


def transition_occurrence_execution_intent(
    intent: Mapping[str, Any],
    *,
    state: str,
    timestamp: str,
    code: str | None = None,
    history_limit: int = 50,
) -> dict[str, Any]:
    """Return one bounded durable execution-intent state transition."""

    if state not in EXECUTION_INTENT_STATES:
        raise ValueError("unsupported occurrence execution-intent state")
    updated = copy.deepcopy(dict(intent))
    clean_code = str(code or "")[:100] or None
    attempts = int(updated.get("attempts") or 0)
    if state != PENDING:
        attempts += 1
    updated.update({
        "state": state,
        "attempts": attempts,
        "updatedAt": timestamp,
        "code": clean_code,
    })
    history = updated.get("history") if isinstance(updated.get("history"), list) else []
    history.append({"state": state, "at": timestamp, "code": clean_code})
    updated["history"] = history[-max(1, int(history_limit)):]
    return updated
