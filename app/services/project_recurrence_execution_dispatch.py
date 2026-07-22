"""Post-commit reconciliation of durable recurring Project execution intents."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from services.project_authoring_audit import sanitize_audit_text
from services.project_authoring_store import RECURRENCES_KEY
from services.project_recurrence_execution import (
    FAILED_RETRYABLE,
    INTERVENTION_REQUIRED,
    PENDING,
    STARTED,
    transition_occurrence_execution_intent,
)


_INTERVENTION_CODES = frozenset({
    "agent_not_found", "agent_not_assignable", "executor_missing",
    "executable_agent_required", "project_execution_disabled", "project_not_found",
    "workspace_not_ready", "workspace_required",
})
_ALREADY_STARTED_CODES = frozenset({
    "already_active", "already_completed", "project_already_active",
    "project_execution_active", "project_execution_completed",
})


def _parse_timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _already_satisfied(project: Mapping[str, Any]) -> str | None:
    if str(project.get("status") or "").lower() in {"completed", "done", "archived"}:
        return "already_completed"
    if project.get("projectExecutionFlowActive") is True or project.get("workflowActive") is True:
        return "already_active"
    for task in project.get("tasks") or []:
        if isinstance(task, Mapping) and (
            task.get("activeAttemptId")
            or task.get("executionState") in {"executing", "reviewing", "awaiting_acceptance"}
        ):
            return "already_active"
    return None


class RecurrenceExecutionDispatcher:
    """Claim, launch, and durably finalize one automatic-execution intent."""

    def __init__(
        self,
        *,
        store,
        start_project: Callable[[str, Mapping[str, Any]], Mapping[str, Any]] | None,
        clock: Callable[[], datetime],
        new_id: Callable[[], str],
        observe: Callable[..., None] | None = None,
    ) -> None:
        self.store = store
        self.start_project = start_project
        self.clock = clock
        self.new_id = new_id
        self.observe = observe

    def reconcile(self, recurrence_id: str, occurrence_id: str) -> dict[str, Any]:
        now_dt = self.clock().astimezone(timezone.utc)
        now = now_dt.isoformat()
        outcome: dict[str, Any] = {}

        def claim(root: dict[str, Any]) -> None:
            recurrence = root.get(RECURRENCES_KEY, {}).get(recurrence_id)
            record = (recurrence.get("occurrences") or {}).get(occurrence_id) if isinstance(recurrence, dict) else None
            intent = record.get("executionIntent") if isinstance(record, dict) else None
            if not isinstance(intent, dict):
                outcome.update({"state": "not_requested"})
                return
            if self.start_project is None:
                outcome.update({"state": PENDING, "code": "start_port_unavailable"})
                return
            if intent.get("state") in {STARTED, INTERVENTION_REQUIRED}:
                outcome.update({"state": intent.get("state"), "code": intent.get("code")})
                return
            project_id = str(intent.get("projectId") or record.get("projectId") or "")
            project = next(
                (item for item in root.get("projects", []) if item.get("id") == project_id), None,
            )
            if not isinstance(project, dict):
                record["executionIntent"] = transition_occurrence_execution_intent(
                    intent, state=INTERVENTION_REQUIRED, timestamp=now,
                    code="project_not_found", history_limit=self.store.config.recurrence_history_limit,
                )
                outcome.update({"state": INTERVENTION_REQUIRED, "code": "project_not_found"})
                return
            satisfied = _already_satisfied(project)
            if satisfied:
                record["executionIntent"] = transition_occurrence_execution_intent(
                    intent, state=STARTED, timestamp=now, code=satisfied,
                    history_limit=self.store.config.recurrence_history_limit,
                )
                outcome.update({"state": STARTED, "code": satisfied})
                return
            expires_at = _parse_timestamp(intent.get("claimExpiresAt"))
            if intent.get("claimToken") and expires_at and expires_at > now_dt:
                outcome.update({"state": "in_progress", "code": "launch_claimed"})
                return
            token = f"recurrence-execution-{self.new_id()}"
            intent.update({
                "claimToken": token,
                "claimOwner": "project-recurrence-execution",
                "claimExpiresAt": (
                    now_dt + timedelta(seconds=self.store.config.occurrence_claim_seconds)
                ).isoformat(),
                "updatedAt": now,
            })
            outcome.update({
                "state": "owned", "claimToken": token, "projectId": project_id,
                "startMode": project.get("projectExecutionStartMode") or "continuous",
            })

        self.store.update(claim)
        if outcome.get("state") != "owned":
            if outcome.get("state") != "not_requested":
                self._observe(outcome.get("state") or "unknown", outcome.get("code") or "")
            return copy.deepcopy(outcome)

        self._observe("requested", "")
        try:
            result = self.start_project(str(outcome["projectId"]), {
                "mode": outcome["startMode"],
                "by": "system:project-recurrence",
                "flowReason": "recurrence_automatic_execution",
                "occurrenceId": occurrence_id,
            })
            response = dict(result) if isinstance(result, Mapping) else {}
            raw_response_code = str(response.get("code") or "")[:100]
            response_code = sanitize_audit_text(raw_response_code, limit=100)
            if response.get("ok") is True or raw_response_code in _ALREADY_STARTED_CODES:
                state, code = STARTED, response_code or "started"
            else:
                code = response_code or "project_execution_start_failed"
                status = int(response.get("_status") or 500)
                state = INTERVENTION_REQUIRED if raw_response_code in _INTERVENTION_CODES or 400 <= status < 500 else FAILED_RETRYABLE
        except Exception:
            state, code = FAILED_RETRYABLE, "project_execution_start_exception"

        finalized: dict[str, Any] = {"state": state, "code": code}

        def finish(root: dict[str, Any]) -> None:
            recurrence = root.get(RECURRENCES_KEY, {}).get(recurrence_id)
            record = (recurrence.get("occurrences") or {}).get(occurrence_id) if isinstance(recurrence, dict) else None
            intent = record.get("executionIntent") if isinstance(record, dict) else None
            if not isinstance(intent, dict) or intent.get("claimToken") != outcome.get("claimToken"):
                finalized.update({"state": "claim_lost", "code": "execution_claim_lost"})
                return
            transitioned = transition_occurrence_execution_intent(
                intent, state=state, timestamp=self.clock().astimezone(timezone.utc).isoformat(),
                code=code, history_limit=self.store.config.recurrence_history_limit,
            )
            for field in ("claimToken", "claimOwner", "claimExpiresAt"):
                transitioned.pop(field, None)
            record["executionIntent"] = transitioned
            recurrence["lastExecutionStatus"] = state
            recurrence["updatedAt"] = transitioned["updatedAt"]

        self.store.update(finish)
        self._observe(finalized["state"], finalized["code"])
        return copy.deepcopy(finalized)

    def _observe(self, state: str, code: str) -> None:
        if self.observe is None:
            return
        self.observe(
            "recurrence.execution.start",
            status=state,
            duration_ms=0,
            code=str(code or "")[:100],
            intervention=state == INTERVENTION_REQUIRED,
        )
