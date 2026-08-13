"""Meeting-request application workflow with explicit infrastructure ports."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from . import meeting_requests


Result = dict[str, Any]


@dataclass(frozen=True)
class MeetingRequestPorts:
    repository: Any
    find_project_task: Callable[[str, str], tuple[dict | None, dict | None]]
    context_candidates: Callable[[dict, dict], list[dict]]
    request_hooks: Callable[[], meeting_requests.RequestHooks]
    participant_error: Callable[[list[str]], Result]
    block_project: Callable[[str, str, Mapping[str, Any], str], Result]
    update_blocker: Callable[..., Result]
    record_reconciliation: Callable[[str, str, Mapping[str, Any], Mapping[str, Any]], Any]
    reconcile_project: Callable[[str], Result]
    auto_confirm_reason: Callable[[Mapping[str, Any], Any], str]
    send_notification: Callable[..., Result]
    project_ref: Callable[[str], Result]
    preparing_timeout: Callable[[], int]
    decision_window: Callable[[], int]
    context_budget: Callable[[Any], dict]
    new_id: Callable[[], str]
    log_auto_confirm: Callable[[Mapping[str, Any], Mapping[str, Any], str], Any]
    approved_details: Callable[[Mapping[str, Any]], list]
    meeting_open_url: Callable[[str], str]
    run_meeting: Callable[[str, Mapping[str, Any]], Result]
    now: Callable[[], str]
    task_comment: Callable[[str, str, Mapping[str, Any]], Any]
    notification_details: Callable[[Mapping[str, Any]], list]


class MeetingRequestWorkflow:
    def __init__(self, ports: MeetingRequestPorts):
        self.ports = ports

    def create(self, project_id: str, task_id: str, body: Mapping[str, Any]) -> Result:
        project, task = self.ports.find_project_task(project_id, task_id)
        if not project:
            return meeting_requests.error("Project not found", 404, "project_not_found")
        if not task:
            return meeting_requests.error("Task not found", 404, "task_not_found")
        candidates = self.ports.context_candidates(project, task)
        _, result = self.ports.repository.create_request(
            lambda data: meeting_requests.create_command(
                data, project, task, body, candidates, self.ports.request_hooks(),
            )
        )
        if not result.get("ok"):
            if result.get("code") == "archive_manager_not_meeting_participant":
                return self.ports.participant_error(result.get("participants") or [])
            return result
        request = result["request"]
        created = bool(result.pop("created", False))
        if result.get("idempotent") or not created:
            reconciliation = self.ports.reconcile_project(request.get("id"))
            if reconciliation.get("attempted"):
                result["projectReconciliation"] = reconciliation
            return result
        blocked = self.ports.block_project(
            project_id, task_id, request, "AI meeting requested; waiting for meeting resolution.",
        )
        if not blocked.get("ok"):
            self.ports.record_reconciliation(
                request["id"], "project_block_create", blocked,
                {"projectId": project_id, "taskId": task_id},
            )
            return blocked
        auto_reason = self.ports.auto_confirm_reason(project, request.get("urgency"))
        if auto_reason:
            requested = request.get("requestedContext") if isinstance(request.get("requestedContext"), dict) else {}
            auto = self.confirm(request["id"], {
                "confirmedBy": f"agent:{request.get('requestingAgentId') or ''}",
                "autoConfirmed": True,
                "autoConfirmReason": auto_reason,
                "selectedContextIds": requested.get("selectedContextIds") or body.get("selectedContextIds") or body.get("contextIds") or [],
                "supplementalContext": requested.get("supplementalContext") if "supplementalContext" in requested else body.get("supplementalContext") or "",
                "idempotencyKey": f"meeting-request-auto:{request['id']}",
            })
            if auto.get("ok"):
                auto["autoConfirmed"] = True
                return auto
            return {
                "ok": True, "request": request, "autoConfirmError": auto,
                "notification": self.ports.send_notification(request, "pending"),
            }
        return {"ok": True, "request": request, "notification": self.ports.send_notification(request, "pending")}

    def list(self, *, status: str = "", project_id: str = "", task_id: str = "") -> Result:
        values = self.ports.repository.list_requests()
        return meeting_requests.list_command(
            {"requests": {str(value.get("id")): value for value in values}},
            status=status, project_id=project_id, task_id=task_id,
        )

    def detail(self, request_id: str) -> Result:
        request = self.ports.repository.get_request(request_id)
        return meeting_requests.detail_command({"requests": {request_id: request} if request else {}}, request_id)

    def confirm(self, request_id: str, body: Mapping[str, Any]) -> Result:
        request = self.ports.repository.get_request(request_id)
        if not request:
            return meeting_requests.error("Meeting request not found", 404, "request_not_found")
        source = request.get("source") if isinstance(request.get("source"), dict) else {}
        project_ref = self.ports.project_ref(str(body.get("projectId") or source.get("projectId") or ""))
        if not project_ref.get("ok"):
            return meeting_requests.error(
                project_ref.get("error") or "Project not found", project_ref.get("_status", 404),
                project_ref.get("code", "project_not_found"),
            )
        defaults = {
            "meetingId": self.ports.new_id(),
            "preparingTimeoutSec": self.ports.preparing_timeout(),
            "decisionWindowSec": self.ports.decision_window(),
            "contextBudget": self.ports.context_budget(None),
            "allowConflicts": False,
        }
        _, result = self.ports.repository.mutate_request_with_meetings(
            request_id,
            lambda data: meeting_requests.confirm_command(
                data, request_id, body, project_title=project_ref.get("projectTitle") or "",
                lifecycle_defaults=defaults, hooks=self.ports.request_hooks(),
            )
        )
        if not result.get("ok"):
            if result.get("code") == "archive_manager_not_meeting_participant":
                return self.ports.participant_error(result.get("participants") or [])
            return result
        request = result.get("request") or {}
        meeting = result.get("meeting")
        if result.get("idempotent"):
            reconciliation = self.ports.reconcile_project(request_id)
            if reconciliation.get("attempted"):
                result["projectReconciliation"] = reconciliation
            return result
        project_update = self.ports.update_blocker(
            source.get("projectId"), source.get("taskId"), request_id,
            status="confirmed", meetingId=result.get("meetingId"), awaitingUserDecision=False,
        )
        if not project_update.get("ok"):
            self.ports.record_reconciliation(
                request_id, "project_confirm", project_update,
                {"projectId": source.get("projectId"), "taskId": source.get("taskId"), "meetingId": result.get("meetingId")},
            )
        if body.get("autoConfirmed") and meeting:
            self.ports.log_auto_confirm(request, meeting, body.get("autoConfirmReason"))
        notification = self.ports.send_notification(
            request, "approved", summary=f"会议申请已同意，会议 ID：{result.get('meetingId')}",
            details=self.ports.approved_details(request),
            actions=[{"category": "jump", "text": "查看会议", "url": self.ports.meeting_open_url(result.get("meetingId"))}],
        )
        if body.get("autoConfirmed") and meeting:
            auto_run = self.ports.run_meeting(meeting["id"], {
                "action": "auto_start", "actorId": request.get("requestingAgentId") or "agent", "actorType": "agent",
            })
            summary = {
                "attempted": True, "startedAt": self.ports.now(),
                "ok": bool(auto_run.get("ok")) if isinstance(auto_run, dict) else False,
                "stage": ((auto_run or {}).get("meeting") or {}).get("stage") if isinstance(auto_run, dict) else "",
                "error": (auto_run or {}).get("error") if isinstance(auto_run, dict) else "Auto run failed",
            }
            def record_auto_run(data):
                current = data.get("requests", {}).get(request_id)
                if current:
                    current.setdefault("conversion", {})["autoRun"] = copy.deepcopy(summary)
                    current["updatedAt"] = self.ports.now()
                return meeting_requests.public_request(current)
            _, current_request = self.ports.repository.mutate_request(request_id, record_auto_run)
            result["request"] = current_request
            result["autoRun"] = summary
            if isinstance(auto_run, dict) and auto_run.get("meeting"):
                result["meeting"] = auto_run["meeting"]
        result["notification"] = notification
        if not project_update.get("ok"):
            result["projectReconciliationPending"] = True
        return result

    def reject(self, request_id: str, body: Mapping[str, Any]) -> Result:
        _, result = self.ports.repository.mutate_request(
            request_id,
            lambda data: meeting_requests.reject_command(data, request_id, body, self.ports.request_hooks())
        )
        if not result.get("ok"):
            return result
        if result.get("idempotent"):
            reconciliation = self.ports.reconcile_project(request_id)
            if reconciliation.get("attempted"):
                result["projectReconciliation"] = reconciliation
            return result
        request = result["request"]
        source = request.get("source") or {}
        reason = str(body.get("reason") or "").strip()
        project_update = self.ports.update_blocker(
            source.get("projectId"), source.get("taskId"), request_id,
            status="rejected", rejectionReason=reason, awaitingUserDecision=True,
        )
        if not project_update.get("ok"):
            self.ports.record_reconciliation(
                request_id, "project_reject", project_update,
                {"projectId": source.get("projectId"), "taskId": source.get("taskId"), "reason": reason},
            )
            result["projectReconciliationPending"] = True
        self.ports.task_comment(source.get("projectId", ""), source.get("taskId", ""), {
            "author": "meeting-request", "text": f"AI meeting request rejected: {reason}",
        })
        result["notification"] = self.ports.send_notification(
            request, "rejected", summary=f"会议申请已拒绝：{reason}", actions=[],
            details=self.ports.notification_details(request) + [("拒绝原因", reason)],
        )
        return result
