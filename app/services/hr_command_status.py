"""Persistent status transitions for asynchronous HR management commands."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from services.hr_repository import HRActivityRecord, HRRepository


class HRCommandStatusTracker:
    """Represent one background command as a mutable, repository-backed activity."""

    def __init__(self, repository: HRRepository):
        if not isinstance(repository, HRRepository):
            raise TypeError("repository must be an HRRepository")
        self._repository = repository

    @staticmethod
    def _context(
        command_id: str,
        values: Mapping[str, object] | None = None,
        *,
        completed: bool = False,
    ) -> dict[str, object]:
        context = {"commandId": command_id, **dict(values or {})}
        if completed:
            context["completedAt"] = datetime.now(timezone.utc).isoformat()
        return context

    def accepted(
        self,
        command_id: str,
        action: str,
        *,
        context: Mapping[str, object] | None = None,
    ) -> HRActivityRecord:
        return self._repository.append_hr_activity(
            activity_id=command_id,
            ai_id=None,
            action=action,
            status="accepted",
            context=self._context(command_id, context),
            occurrence_key=f"hr-command:{command_id}",
        )

    def running(
        self,
        command_id: str,
        *,
        context: Mapping[str, object] | None = None,
    ) -> HRActivityRecord:
        return self._repository.transition_hr_command_activity(
            command_id,
            status="processing",
            context=self._context(command_id, context),
            expected_statuses=("accepted", "processing"),
        )

    def complete(
        self,
        command_id: str,
        *,
        message: str = "",
        context: Mapping[str, object] | None = None,
    ) -> HRActivityRecord:
        return self._repository.transition_hr_command_activity(
            command_id,
            status="complete",
            message=message,
            context=self._context(command_id, context, completed=True),
            expected_statuses=("accepted", "processing"),
        )

    def failed(
        self,
        command_id: str,
        code: str,
        *,
        context: Mapping[str, object] | None = None,
    ) -> HRActivityRecord:
        return self._repository.transition_hr_command_activity(
            command_id,
            status="failed",
            error=code,
            context=self._context(command_id, context, completed=True),
            expected_statuses=("accepted", "processing"),
        )

    def interrupt_active(self) -> int:
        """Close commands left active by a previous process before new work is accepted."""
        interrupted = 0
        for command in self._repository.list_active_hr_commands(limit=100):
            self.failed(
                command.id,
                "hr_command_interrupted",
                context={"previousStatus": command.status},
            )
            interrupted += 1
        return interrupted
