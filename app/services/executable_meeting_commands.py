"""Executable Meeting command orchestration with explicit persistence and domain hooks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from . import meeting_lifecycle


@dataclass(frozen=True)
class ExecutableMeetingPorts:
    lock: Any
    repository: Any
    clean_participants: Callable[[Any], list[str]]
    participant_error: Callable[[str], Mapping[str, Any] | None]
    participant_error_response: Callable[[list[str]], dict]
    project_ref: Callable[[str], dict]
    now: Callable[[], str]
    new_id: Callable[[], str]
    decision_window: Callable[[Any], int]
    resolution_policy: Callable[[Any], str]
    context_mode: Callable[[Any], str]
    context_budget: Callable[[Any], dict]
    preparing_timeout: Callable[[], int]
    rebuild_occupancy: Callable[..., Any]
    build_conflicts: Callable[..., Any]
    append_event: Callable[..., Any]
    complete_live_advisories: Callable[[str], Any]
    ensure_action_items: Callable[..., Any]
    release_timed_out: Callable[[dict], list[str]]
    project_history: Callable[..., dict]
    project_active: Callable[..., dict]
    busy_context: Callable[..., Any]
    advisory: Callable[..., Any]
    original_work_snapshot: Callable[..., Any]
    has_open_conflicts: Callable[..., Any]
    mark_preparing: Callable[..., Any]
    continue_decision: Callable[..., Any]
    resume_original_work: Callable[..., Any]
    award_points: Callable[..., Any]
    apply_project_result: Callable[[Mapping[str, Any]], Any]


class ExecutableMeetingCommands:
    def __init__(self, ports: ExecutableMeetingPorts):
        self.ports = ports

    def create(self, body: Mapping[str, Any]) -> dict:
        topic = str(body.get("topic") or "").strip()
        participants = self.ports.clean_participants(body.get("participants") or body.get("agents") or [])
        if not topic:
            return {"error": "Meeting topic is required", "_status": 400}
        if len(participants) < 2:
            return {"error": "Executable meeting requires at least 2 participants", "_status": 400}
        moderator = str(body.get("moderator") or body.get("moderatorId") or participants[0]).strip()
        try:
            meeting_lifecycle.validate_participant_eligibility(
                participants, moderator, participant_error=self.ports.participant_error,
            )
        except meeting_lifecycle.MeetingLifecycleError as error:
            if error.code == "archive_manager_not_meeting_participant":
                return self.ports.participant_error_response(error.details.get("participants") or [])
            return {"error": str(error), "_status": error.status}
        meeting_type = str(body.get("meetingType") or body.get("kind") or "discussion").strip() or "discussion"
        if meeting_type not in {"information", "discussion", "task"}:
            meeting_type = "discussion"
        try:
            max_rounds = max(1, min(20, int(body.get("maxRounds") or 2)))
        except (TypeError, ValueError):
            max_rounds = 2
        meeting_id = str(body.get("id") or self.ports.new_id())
        actor = {"type": "user", "id": str(body.get("createdBy") or body.get("organizer") or "user")}
        source = body.get("source") if isinstance(body.get("source"), dict) else {}
        project_ref = self.ports.project_ref(body.get("projectId") or source.get("projectId"))
        if not project_ref.get("ok"):
            return {
                "error": project_ref.get("error") or "Project not found",
                "code": project_ref.get("code", "project_not_found"), "_status": project_ref.get("_status", 404),
            }
        with self.ports.lock:
            def create_command(store):
                return meeting_lifecycle.create_command(
                    store,
                    {
                        "meetingId": meeting_id, "topic": topic, "participants": participants, "moderator": moderator,
                        "agenda": str(body.get("agenda") or topic).strip(), "purpose": str(body.get("purpose") or "").strip(),
                        "meetingType": meeting_type, "organizer": str(body.get("organizer") or participants[0]).strip(),
                        "createdBy": str(body.get("createdBy") or body.get("organizer") or "user").strip(),
                        "createdByType": str(body.get("createdByType") or ("agent" if body.get("createdByAgentId") else "user")).strip(),
                        "createdByAgentId": str(body.get("createdByAgentId") or "").strip(),
                        "projectId": project_ref["projectId"], "projectTitle": project_ref["projectTitle"], "maxRounds": max_rounds,
                        "decisionWindowSec": self.ports.decision_window(body.get("decisionWindowSec") or body.get("decisionWindowSeconds")),
                        "resolutionPolicy": self.ports.resolution_policy(body.get("resolutionPolicy") or body.get("arbitrationPolicy")),
                        "context": str(body.get("context") or body.get("initialContext") or "").strip(),
                        "contextMode": self.ports.context_mode(body.get("contextMode")),
                        "contextBudget": self.ports.context_budget(body.get("contextBudget")),
                        "source": source, "preparingTimeoutSec": self.ports.preparing_timeout(),
                        "now": self.ports.now(), "actor": actor,
                        "idempotencyKey": str(body.get("idempotencyKey") or "").strip(),
                        "allowConflicts": bool(body.get("allowConflicts") or body.get("conflictAware")),
                    },
                    meeting_lifecycle.CreateHooks(
                        rebuild_occupancy=self.ports.rebuild_occupancy,
                        build_conflicts=self.ports.build_conflicts,
                        append_event=self.ports.append_event,
                    ),
                )
            store, result = self.ports.repository.create_meeting(create_command)
            if not result.get("ok") or result.get("idempotent"):
                return result
            meeting = result["meeting"]
        if result.pop("conflicts", False):
            live_meeting = self.ports.complete_live_advisories(meeting_id)
            if live_meeting:
                meeting = live_meeting
        return {**result, "meeting": meeting}

    def detail(self, meeting_id: str) -> dict:
        with self.ports.lock:
            meeting = self.ports.repository.get_meeting(meeting_id)
            if not meeting:
                return {"error": "Executable meeting not found", "_status": 404}
            events = self.ports.repository.list_events(meeting_id)
            if meeting.get("stage") == "completed":
                store, _ = self.ports.repository.mutate_meeting(
                    meeting_id, lambda data: self.ports.ensure_action_items(data, data["meetings"][meeting_id]),
                )
                meeting = store["meetings"][meeting_id]
                projected = self.ports.project_history(meeting, events)
            else:
                projected = self.ports.project_active(meeting, events)
            return {"ok": True, "meeting": {**meeting, **projected}, "events": events}

    def conflict_action(self, meeting_id: str, body: Mapping[str, Any]) -> dict:
        hooks = meeting_lifecycle.ConflictHooks(
            append_event=self.ports.append_event, build_conflicts=self.ports.build_conflicts,
            busy_context=self.ports.busy_context, advisory=self.ports.advisory,
            original_work_snapshot=self.ports.original_work_snapshot,
            has_open_conflicts=self.ports.has_open_conflicts, mark_preparing=self.ports.mark_preparing,
            rebuild_occupancy=self.ports.rebuild_occupancy, participant_error=self.ports.participant_error,
            now=self.ports.now, new_id=self.ports.new_id,
        )
        with self.ports.lock:
            _, result = self.ports.repository.mutate_meeting(
                meeting_id, lambda store: meeting_lifecycle.conflict_action_command(store, meeting_id, body, hooks),
            )
        if result.pop("needsLiveAdvisory", False):
            live_meeting = self.ports.complete_live_advisories(meeting_id)
            if live_meeting:
                result["meeting"] = live_meeting
        return result

    def transition(self, meeting_id: str, body: Mapping[str, Any]) -> dict:
        hooks = meeting_lifecycle.TransitionHooks(
            append_event=self.ports.append_event, continue_decision=self.ports.continue_decision,
            mark_preparing=self.ports.mark_preparing, resume_original_work=self.ports.resume_original_work,
            ensure_action_items=self.ports.ensure_action_items, award_points=self.ports.award_points,
        )
        with self.ports.lock:
            store, result = self.ports.repository.mutate_meeting(
                meeting_id, lambda data: meeting_lifecycle.transition_command(data, meeting_id, body, hooks),
            )
            if not result.get("ok") or result.get("idempotent"):
                return result
        if result.pop("terminal", False):
            self.ports.apply_project_result(result["meeting"])
        with self.ports.lock:
            latest = self.ports.repository.get_meeting(meeting_id) or result["meeting"]
        return {**result, "meeting": latest}

    def intervention(self, meeting_id: str, body: Mapping[str, Any]) -> dict:
        return self._mutation(meeting_lifecycle.intervention_command, meeting_id, body)

    def agenda_change(self, meeting_id: str, body: Mapping[str, Any]) -> dict:
        return self._mutation(meeting_lifecycle.agenda_change_command, meeting_id, body)

    def _mutation(self, command, meeting_id, body):
        with self.ports.lock:
            _, result = self.ports.repository.mutate_meeting(
                meeting_id,
                lambda store: command(store, meeting_id, body, meeting_lifecycle.MutationHooks(append_event=self.ports.append_event)),
            )
            return result
