"""Project-authoring request commands; no project materialization occurs here."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from services.project_authoring_config import feature_disabled_error, is_authoring_enabled
from services.project_authoring_store import (
    IDEMPOTENCY_KEY,
    REQUESTS_KEY,
    ProjectAuthoringRootStore,
    agent_request_view,
    management_request_view,
)
from services.project_authoring_validation import validate_idempotency_key, validate_project_draft


EDITABLE_STATES = frozenset({"pending", "failed"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ProjectAuthoringCommandError(RuntimeError):
    code: str
    message: str
    status: int
    request_id: str = ""
    expected_revision: int | None = None
    actual_revision: int | None = None

    def __str__(self) -> str:
        return self.message

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "ok": False,
            "code": self.code,
            "error": self.message,
            "_status": self.status,
        }
        if self.request_id:
            result["requestId"] = self.request_id
        if self.expected_revision is not None:
            result["expectedRevision"] = self.expected_revision
        if self.actual_revision is not None:
            result["actualRevision"] = self.actual_revision
        return result


class ProjectAuthoringService:
    def __init__(
        self,
        store: ProjectAuthoringRootStore,
        *,
        lookup_agent,
        is_excluded_agent,
        submission_enabled: Callable[[], bool] = is_authoring_enabled,
        clock: Callable[[], datetime] = _now,
        new_id: Callable[[], str] = _new_id,
    ) -> None:
        self.store = store
        self.lookup_agent = lookup_agent
        self.is_excluded_agent = is_excluded_agent
        self.submission_enabled = submission_enabled
        self.clock = clock
        self.new_id = new_id

    def create_pending(
        self,
        draft: Any,
        *,
        requesting_agent_id: str,
        idempotency_key: Any,
        request_secret_hash: str,
        source: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.submission_enabled():
            raise feature_disabled_error("authoring")
        agent_id = str(requesting_agent_id or "").strip()
        self._validate_requesting_agent(agent_id)
        key = validate_idempotency_key(idempotency_key)
        scoped_key = f"{agent_id}:{key}"
        existing = self._idempotent_request(scoped_key)
        if existing is not None:
            return {
                "ok": True,
                "created": False,
                "request": agent_request_view(existing, requesting_agent_id=agent_id),
            }
        normalized = validate_project_draft(
            draft,
            idempotency_key=key,
            lookup_agent=self.lookup_agent,
            is_excluded_agent=self.is_excluded_agent,
            config=self.store.config,
            reviewer_assignment_confirmed=False,
        )
        now = self._timestamp()
        request_id = self.new_id()
        outcome: dict[str, Any] = {}

        def create(root: dict[str, Any]) -> None:
            existing_record = root[IDEMPOTENCY_KEY].get(scoped_key)
            existing_id = (
                existing_record.get("requestId") if isinstance(existing_record, dict)
                else existing_record
            )
            existing = root[REQUESTS_KEY].get(str(existing_id or ""))
            if isinstance(existing, dict):
                outcome.update({"created": False, "request": copy.deepcopy(existing)})
                return
            request = {
                "id": request_id,
                "requestId": request_id,
                "requestingAgentId": agent_id,
                "idempotencyKey": key,
                "draftDigest": _canonical_digest(normalized),
                "state": "pending",
                "revision": 1,
                "originalDraft": copy.deepcopy(normalized),
                "workingDraft": copy.deepcopy(normalized),
                "requestSecretHash": str(request_secret_hash or ""),
                "source": copy.deepcopy(dict(source or {})),
                "createdAt": now,
                "updatedAt": now,
                "audit": [self._audit("draft_submitted", agent_id, "agent", now, "accepted")],
                "history": [],
                "approvalHistory": [],
            }
            root[REQUESTS_KEY][request_id] = request
            root[IDEMPOTENCY_KEY][scoped_key] = {
                "requestId": request_id,
                "requestingAgentId": agent_id,
                "createdAt": now,
            }
            outcome.update({"created": True, "request": copy.deepcopy(request)})

        self.store.update(create)
        return {
            "ok": True,
            "created": outcome["created"],
            "request": agent_request_view(outcome["request"], requesting_agent_id=agent_id),
        }

    def get_management(self, request_id: str) -> dict[str, Any]:
        request = self._get_raw(request_id)
        return management_request_view(request)

    def get_agent_status(self, request_id: str, *, requesting_agent_id: str) -> dict[str, Any]:
        request = self._get_raw(request_id)
        view = agent_request_view(request, requesting_agent_id=requesting_agent_id)
        if view is None:
            raise self._not_found(request_id)
        return view

    def list_management(
        self,
        *,
        states: set[str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        root = self.store.snapshot()
        selected = [
            request for request in root[REQUESTS_KEY].values()
            if not states or str(request.get("state") or "") in states
        ]
        selected.sort(key=lambda item: (str(item.get("updatedAt") or ""), str(item.get("id") or "")), reverse=True)
        return [self._summary(request) for request in selected[: max(1, min(int(limit), 100))]]

    def edit_pending(
        self,
        request_id: str,
        draft: Any,
        *,
        expected_revision: int,
        actor: str = "user",
    ) -> dict[str, Any]:
        existing = self._get_raw(request_id)
        normalized = validate_project_draft(
            draft,
            idempotency_key=existing.get("idempotencyKey"),
            lookup_agent=self.lookup_agent,
            is_excluded_agent=self.is_excluded_agent,
            config=self.store.config,
            reviewer_assignment_confirmed=True,
        )
        now = self._timestamp()

        def edit(root: dict[str, Any]) -> dict[str, Any]:
            request = self._require_mutable(root, request_id, expected_revision, EDITABLE_STATES)
            previous = copy.deepcopy(request.get("workingDraft"))
            request.setdefault("history", []).append({
                "revision": request.get("revision"),
                "draft": previous,
                "changedAt": now,
                "changedBy": actor,
            })
            request["workingDraft"] = copy.deepcopy(normalized)
            request["draftDigest"] = _canonical_digest(normalized)
            request["state"] = "pending"
            request["revision"] = int(request.get("revision") or 0) + 1
            request["updatedAt"] = now
            request.pop("error", None)
            request.pop("code", None)
            self._append_audit(request, "draft_edited", actor, "management", now, "accepted")
            return management_request_view(request)

        return self.store.update(edit)

    def reject_pending(
        self,
        request_id: str,
        *,
        expected_revision: int,
        reason: Any,
        actor: str = "user",
    ) -> dict[str, Any]:
        rejection_reason = str(reason or "").strip()
        if not rejection_reason:
            raise ProjectAuthoringCommandError(
                "rejection_reason_required", "A rejection reason is required", 400, request_id,
            )
        now = self._timestamp()

        def reject(root: dict[str, Any]) -> dict[str, Any]:
            request = root[REQUESTS_KEY].get(request_id)
            if not isinstance(request, dict):
                raise self._not_found(request_id)
            if request.get("state") == "rejected":
                return management_request_view(request)
            request = self._require_mutable(root, request_id, expected_revision, EDITABLE_STATES)
            request.update({
                "state": "rejected",
                "revision": int(request.get("revision") or 0) + 1,
                "rejectionReason": rejection_reason,
                "rejectedBy": actor,
                "terminalAt": now,
                "updatedAt": now,
            })
            self._append_audit(request, "draft_rejected", actor, "management", now, "accepted")
            return management_request_view(request)

        return self.store.update(reject)

    def begin_confirmation(
        self,
        request_id: str,
        *,
        expected_revision: int,
        confirmation_key: Any,
        actor: str = "user",
    ) -> dict[str, Any]:
        key = validate_idempotency_key(confirmation_key)
        now = self._timestamp()

        def begin(root: dict[str, Any]) -> dict[str, Any]:
            request = root[REQUESTS_KEY].get(request_id)
            if not isinstance(request, dict):
                raise self._not_found(request_id)
            if request.get("state") == "materializing" and request.get("confirmationKey") == key:
                return management_request_view(request)
            request = self._require_mutable(root, request_id, expected_revision, EDITABLE_STATES)
            approved = validate_project_draft(
                request.get("workingDraft"),
                idempotency_key=request.get("idempotencyKey"),
                lookup_agent=self.lookup_agent,
                is_excluded_agent=self.is_excluded_agent,
                config=self.store.config,
                reviewer_assignment_confirmed=True,
            )
            approved_record = {
                "revision": int(request.get("revision") or 0),
                "snapshot": copy.deepcopy(approved),
                "approvedAt": now,
                "approvedBy": actor,
                "confirmationKey": key,
            }
            request.setdefault("approvalHistory", []).append(approved_record)
            request["approvalHistory"] = request["approvalHistory"][-self.store.config.audit_history_limit:]
            request.update({
                "state": "materializing",
                "revision": int(request.get("revision") or 0) + 1,
                "approvedSnapshot": copy.deepcopy(approved),
                "approvedBy": actor,
                "approvedAt": now,
                "confirmationKey": key,
                "updatedAt": now,
            })
            self._append_audit(request, "confirmation_started", actor, "management", now, "accepted")
            return management_request_view(request)

        return self.store.update(begin)

    def mark_materialization_failed(
        self,
        request_id: str,
        *,
        expected_revision: int,
        code: str,
        error: str,
        actor: str = "system",
    ) -> dict[str, Any]:
        now = self._timestamp()

        def fail(root: dict[str, Any]) -> dict[str, Any]:
            request = self._require_mutable(root, request_id, expected_revision, {"materializing"})
            request.update({
                "state": "failed",
                "revision": int(request.get("revision") or 0) + 1,
                "code": str(code or "materialization_failed"),
                "error": str(error or "Project materialization failed")[:2000],
                "updatedAt": now,
            })
            self._append_audit(request, "materialization_failed", actor, "system", now, "failed")
            return management_request_view(request)

        return self.store.update(fail)

    def _get_raw(self, request_id: str) -> dict[str, Any]:
        request = self.store.snapshot()[REQUESTS_KEY].get(str(request_id or ""))
        if not isinstance(request, dict):
            raise self._not_found(request_id)
        return request

    def _idempotent_request(self, scoped_key: str) -> dict[str, Any] | None:
        root = self.store.snapshot()
        record = root[IDEMPOTENCY_KEY].get(scoped_key)
        request_id = record.get("requestId") if isinstance(record, dict) else record
        request = root[REQUESTS_KEY].get(str(request_id or ""))
        return request if isinstance(request, dict) else None

    def _require_mutable(
        self,
        root: dict[str, Any],
        request_id: str,
        expected_revision: int,
        states: set[str] | frozenset[str],
    ) -> dict[str, Any]:
        request = root[REQUESTS_KEY].get(request_id)
        if not isinstance(request, dict):
            raise self._not_found(request_id)
        actual = int(request.get("revision") or 0)
        if actual != int(expected_revision):
            raise ProjectAuthoringCommandError(
                "request_revision_conflict", "Project authoring request revision changed", 409,
                request_id, int(expected_revision), actual,
            )
        if str(request.get("state") or "") not in states:
            raise ProjectAuthoringCommandError(
                "invalid_request_state",
                f"Request state {request.get('state')} does not allow this action",
                409,
                request_id,
            )
        return request

    def _validate_requesting_agent(self, agent_id: str) -> None:
        if not agent_id or self.lookup_agent(agent_id) is None:
            raise ProjectAuthoringCommandError(
                "requesting_agent_not_found", "Requesting Agent was not found", 400,
            )
        if self.is_excluded_agent(agent_id):
            raise ProjectAuthoringCommandError(
                "requesting_agent_not_assignable", "Requesting Agent is not assignable", 400,
            )

    def _timestamp(self) -> str:
        return self.clock().astimezone(timezone.utc).isoformat()

    @staticmethod
    def _audit(action: str, actor: str, source: str, at: str, result: str) -> dict[str, Any]:
        return {"action": action, "actor": actor, "source": source, "at": at, "result": result}

    def _append_audit(self, request: dict[str, Any], action: str, actor: str, source: str, at: str, result: str) -> None:
        request.setdefault("audit", []).append(self._audit(action, actor, source, at, result))
        request["audit"] = request["audit"][-self.store.config.audit_history_limit:]

    @staticmethod
    def _summary(request: Mapping[str, Any]) -> dict[str, Any]:
        draft = request.get("workingDraft") if isinstance(request.get("workingDraft"), Mapping) else {}
        return management_request_view({
            "id": request.get("id"),
            "requestId": request.get("requestId"),
            "requestingAgentId": request.get("requestingAgentId"),
            "state": request.get("state"),
            "revision": request.get("revision"),
            "title": draft.get("title"),
            "projectType": draft.get("projectType"),
            "taskCount": len(draft.get("tasks") or []),
            "projectId": request.get("projectId"),
            "createdAt": request.get("createdAt"),
            "updatedAt": request.get("updatedAt"),
            "tombstone": request.get("tombstone") is True,
        })

    @staticmethod
    def _not_found(request_id: str) -> ProjectAuthoringCommandError:
        return ProjectAuthoringCommandError(
            "project_authoring_request_not_found", "Project authoring request not found", 404,
            str(request_id or ""),
        )
