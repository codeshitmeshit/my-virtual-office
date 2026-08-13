"""Retryable Project-side reconciliation for Meeting requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class ReconciliationPorts:
    repository: Any
    now: Callable[[], str]
    summarize: Callable[[Any, int], str]
    block_project: Callable[..., dict]
    update_blocker: Callable[..., dict]
    apply_meeting_result: Callable[..., dict]


class MeetingRequestReconciliation:
    def __init__(self, ports: ReconciliationPorts):
        self.ports = ports

    def record(self, request_id: str, operation: str, failure: Mapping[str, Any], context=None) -> bool:
        def mutate(data):
            request = data.get("requests", {}).get(request_id)
            if not isinstance(request, dict):
                return False
            entries = request.setdefault("reconciliation", [])
            key = f"{request_id}:{operation}"
            entry = {
                "key": key, "operation": operation, "status": "pending",
                "error": self.ports.summarize((failure or {}).get("error") or "Project update failed", 500),
                "context": {name: value for name, value in (context or {}).items() if value not in (None, "")},
                "updatedAt": self.ports.now(),
            }
            existing = next((item for item in entries if item.get("key") == key), None)
            if existing:
                existing.update(entry)
            else:
                entries.append(entry)
            request["reconciliation"] = entries[-20:]
            request["updatedAt"] = entry["updatedAt"]
            return True
        return bool(self.ports.repository.mutate_request(request_id, mutate)[1])

    def reconcile(self, request_id: str) -> dict:
        request = self.ports.repository.get_request(request_id)
        if not isinstance(request, dict):
            return {"ok": False, "error": "Meeting request not found", "_status": 404}
        pending = [item for item in request.get("reconciliation", []) if item.get("status") == "pending"]
        results = []
        for entry in pending:
            outcome = self._retry(request_id, request, entry)
            results.append({"key": entry.get("key"), "operation": entry.get("operation"), "ok": bool(outcome.get("ok"))})
            if outcome.get("ok"):
                self._resolve(request_id, entry.get("key"))
        return {"ok": all(item["ok"] for item in results), "attempted": len(results), "results": results}

    def _retry(self, request_id: str, request: Mapping[str, Any], entry: Mapping[str, Any]) -> dict:
        context = entry.get("context") if isinstance(entry.get("context"), dict) else {}
        operation = entry.get("operation")
        if operation == "project_block_create":
            return self.ports.block_project(
                context.get("projectId"), context.get("taskId"), request,
                "AI meeting requested; waiting for meeting resolution.",
            )
        if operation == "project_confirm":
            return self.ports.update_blocker(
                context.get("projectId"), context.get("taskId"), request_id,
                status="confirmed", meetingId=context.get("meetingId"), awaitingUserDecision=False,
            )
        if operation == "project_reject":
            return self.ports.update_blocker(
                context.get("projectId"), context.get("taskId"), request_id,
                status="rejected", rejectionReason=context.get("reason"), awaitingUserDecision=True,
            )
        if operation == "project_meeting_result":
            meeting = self.ports.repository.get_meeting(context.get("meetingId"))
            return self.ports.apply_meeting_result(meeting, _record_reconciliation=False) if meeting else {
                "ok": False, "error": "Meeting not found", "_status": 404,
            }
        return {"ok": False, "error": "Unsupported reconciliation operation", "_status": 400}

    def _resolve(self, request_id: str, key: str) -> None:
        def resolve(data):
            current = data.get("requests", {}).get(request_id)
            for item in current.get("reconciliation", []) if isinstance(current, dict) else []:
                if item.get("key") == key:
                    item["status"] = "resolved"
                    item["resolvedAt"] = self.ports.now()
                    item["updatedAt"] = item["resolvedAt"]
            return True
        self.ports.repository.mutate_request(request_id, resolve)
