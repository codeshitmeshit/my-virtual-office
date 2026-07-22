"""Project-authoring orchestration delegating persisted shapes to materializers."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from services.project_authoring_config import (
    feature_disabled_error,
    is_authoring_enabled,
    is_recurrence_dispatch_paused,
    is_recurrence_enabled,
)
from services.project_authoring_store import (
    GRANTS_KEY,
    IDEMPOTENCY_KEY,
    OUTBOX_KEY,
    RECURRENCES_KEY,
    REQUESTS_KEY,
    TEMPLATES_KEY,
    ProjectAuthoringRootStore,
    agent_request_view,
    grant_public_view,
    management_request_view,
)
from services.project_authoring_validation import validate_idempotency_key, validate_project_draft
from services.project_authoring_workspace import prepared_execution_workspace_error
from services.project_materialization import (
    apply_authoring_overlay,
    materialize_columns,
    materialize_project_base,
    materialize_task_base,
)
from services.project_authoring_security import verify_request_secret
from services.project_direct_creation import (
    DirectProjectCreationPorts,
    DirectProjectCreationService,
)
from services.project_authoring_audit import build_audit_event, sanitize_audit_text
from services.project_templates import (
    ProjectTemplateError,
    adapt_legacy_template,
    append_template_version,
    resolve_template_version,
)
from services.project_template_materialization import (
    materialize_versioned_template_instance,
)
from services.project_recurrence_execution import (
    CREATE_AND_EXECUTE,
    new_occurrence_execution_intent,
    stored_recurrence_execution_mode,
)
from services.project_recurrence_materialization import (
    materialize_recurrence_occurrence_project,
)
from services.project_recurrence_execution_dispatch import RecurrenceExecutionDispatcher
from services.project_actors import (
    ActorReferenceError,
    legacy_task_role_fields,
    task_actor_references,
    validate_task_actor_references,
)


EDITABLE_STATES = frozenset({"pending", "failed"})
PROTECTED_MAINTENANCE_OPERATIONS = frozenset({
    "update_project",
    "update_task",
    "create_task",
    "delete_task",
    "reassign_roles",
    "update_recurrence",
    "archive_project",
    "workspace_change",
    "maintenance_mode_change",
})
AUTONOMOUS_ROUTINE_FIELDS = frozenset({
    "executionState", "description", "checklist", "evidence", "dueDate",
})
OCCURRENCE_ACTOR_INTERVENTION_CODES = frozenset({
    "actor_required", "actor_id_required", "agent_actor_required", "agent_not_assignable",
    "agent_not_found", "invalid_actor_reference", "unsupported_actor_type", "unsupported_user_actor",
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass
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
        recurrence_enabled: Callable[[], bool] = is_recurrence_enabled,
        recurrence_paused: Callable[[], bool] = is_recurrence_dispatch_paused,
        clock: Callable[[], datetime] = _now,
        new_id: Callable[[], str] = _new_id,
        new_secret: Callable[[], str] | None = None,
        hash_secret: Callable[[str], str] | None = None,
        start_project: Callable[[str, Mapping[str, Any]], Mapping[str, Any]] | None = None,
        observe_operation: Callable[..., None] | None = None,
    ) -> None:
        self.store = store
        self.lookup_agent = lookup_agent
        self.is_excluded_agent = is_excluded_agent
        self.submission_enabled = submission_enabled
        self.recurrence_enabled = recurrence_enabled
        self.recurrence_paused = recurrence_paused
        self.clock = clock
        self.new_id = new_id
        self.recurrence_execution = RecurrenceExecutionDispatcher(
            store=store,
            start_project=start_project,
            clock=clock,
            new_id=new_id,
            observe=observe_operation,
        )
        direct_ports = DirectProjectCreationPorts(
            store=store,
            lookup_agent=lookup_agent,
            is_excluded_agent=is_excluded_agent,
            submission_enabled=submission_enabled,
            recurrence_enabled=recurrence_enabled,
            materialize_template=self._materialize_template,
            materialize_recurrence=self._materialize_recurrence,
            build_project=self._build_project,
            audit=self._audit,
            cleanup_workspace=self._cleanup_prepared_workspace,
            clock=clock,
            new_id=new_id,
            **({"new_secret": new_secret} if new_secret is not None else {}),
            **({"hash_secret": hash_secret} if hash_secret is not None else {}),
        )
        self.direct_creation = DirectProjectCreationService(direct_ports)

    def create_confirmed_project(
        self,
        project: Any,
        *,
        requesting_agent_id: str,
        idempotency_key: Any,
        confirmation: Any,
        source: Mapping[str, Any] | None = None,
        prepare_workspace: Callable[[Mapping[str, Any], str, str], Mapping[str, Any]] | None = None,
        cleanup_workspace: Callable[[Mapping[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        return self.direct_creation.create(
            project,
            requesting_agent_id=requesting_agent_id,
            idempotency_key=idempotency_key,
            confirmation=confirmation,
            source=source,
            prepare_workspace=prepare_workspace,
            cleanup_workspace=cleanup_workspace,
        )

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
                "audit": [self._audit(
                    "draft_submitted", agent_id, "agent", now, "accepted", requestId=request_id,
                )],
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

    def authenticate_agent_status(
        self,
        request_id: str,
        *,
        requesting_agent_id: str,
        request_secret: str,
    ) -> dict[str, Any]:
        request = self._get_raw(request_id)
        agent_id = str(requesting_agent_id or "").strip()
        if (
            str(request.get("requestingAgentId") or "") != agent_id
            or not verify_request_secret(request_secret, request.get("requestSecretHash"))
        ):
            raise ProjectAuthoringCommandError(
                "invalid_project_authoring_secret",
                "Project authoring request authentication failed",
                403,
                request_id,
            )
        view = agent_request_view(request, requesting_agent_id=agent_id)
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
                "error": sanitize_audit_text(error or "Project materialization failed", limit=2000),
                "updatedAt": now,
            })
            self._append_audit(request, "materialization_failed", actor, "system", now, "failed")
            return management_request_view(request)

        return self.store.update(fail)

    def confirm_and_materialize(
        self,
        request_id: str,
        *,
        expected_revision: int,
        confirmation_key: Any,
        actor: str = "user",
        prepare_workspace: Callable[[Mapping[str, Any], str, str], Mapping[str, Any]] | None = None,
        cleanup_workspace: Callable[[Mapping[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        """Prepare external workspace state, then atomically commit the complete aggregate."""
        key = validate_idempotency_key(confirmation_key)
        existing = self._get_raw(request_id)
        if existing.get("state") == "confirmed" and existing.get("confirmationKey") == key:
            return self._materialization_result(existing)
        started = self.begin_confirmation(
            request_id,
            expected_revision=expected_revision,
            confirmation_key=key,
            actor=actor,
        )
        materializing_revision = int(started.get("revision") or 0)
        approved = copy.deepcopy(started.get("approvedSnapshot") or {})
        workspace: dict[str, Any] = {"ok": True, "managed": False, "created": False}
        try:
            execution_enabled = approved.get("projectExecutionEnabled") is True
            if execution_enabled and prepare_workspace is None:
                failed = self._fail_materialization(
                    request_id,
                    materializing_revision,
                    "workspace_preparation_required",
                    "Execution-enabled project creation requires workspace preparation",
                )
                return {
                    "ok": False,
                    "request": failed,
                    "code": failed.get("code"),
                    "error": failed.get("error"),
                    "_status": 409,
                }
            if execution_enabled and prepare_workspace is not None:
                prepared = prepare_workspace(approved, request_id, key)
                workspace = dict(prepared) if isinstance(prepared, Mapping) else {
                    "ok": False, "error": "Workspace preparation returned an invalid result",
                }
            workspace_error = (
                prepared_execution_workspace_error(workspace)
                if execution_enabled
                else None
            )
            if workspace_error:
                self._cleanup_prepared_workspace(workspace, cleanup_workspace)
                failed = self._fail_materialization(
                    request_id,
                    materializing_revision,
                    "workspace_preparation_failed",
                    workspace_error,
                )
                return {
                    "ok": False,
                    "request": failed,
                    "code": failed.get("code"),
                    "error": failed.get("error"),
                    "_status": 409,
                }

            committed = self.store.update(
                lambda root: self._commit_materialization(
                    root,
                    request_id=request_id,
                    expected_revision=materializing_revision,
                    confirmation_key=key,
                    actor=actor,
                    workspace=workspace,
                )
            )
            return committed
        except Exception as exc:
            self._cleanup_prepared_workspace(workspace, cleanup_workspace)
            if isinstance(exc, ProjectAuthoringCommandError) and exc.code == "request_revision_conflict":
                latest = self._get_raw(request_id)
                if latest.get("state") == "confirmed" and latest.get("confirmationKey") == key:
                    return self._materialization_result(latest)
            failure = self._fail_materialization(
                request_id,
                materializing_revision,
                getattr(exc, "code", "materialization_failed"),
                str(exc) or "Project materialization failed",
                raise_on_conflict=False,
            )
            if failure.get("state") == "failed":
                return {"ok": False, "request": failure, "code": failure.get("code"), "error": failure.get("error"), "_status": 409}
            raise

    def _commit_materialization(
        self,
        root: dict[str, Any],
        *,
        request_id: str,
        expected_revision: int,
        confirmation_key: str,
        actor: str,
        workspace: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = root[REQUESTS_KEY].get(request_id)
        if not isinstance(request, dict):
            raise self._not_found(request_id)
        confirmation_record_key = f"confirmation:{request_id}:{confirmation_key}"
        existing_confirmation = root[IDEMPOTENCY_KEY].get(confirmation_record_key)
        existing_project_id = (
            existing_confirmation.get("projectId")
            if isinstance(existing_confirmation, dict)
            else existing_confirmation
        )
        if existing_project_id:
            project = next(
                (item for item in root.get("projects", []) if item.get("id") == existing_project_id),
                None,
            )
            if project is not None:
                request.update({"state": "confirmed", "projectId": existing_project_id})
                return {"ok": True, "created": False, "project": copy.deepcopy(project), "request": management_request_view(request)}
        request = self._require_mutable(
            root, request_id, expected_revision, {"materializing"},
        )
        if request.get("confirmationKey") != confirmation_key:
            raise ProjectAuthoringCommandError(
                "confirmation_key_conflict", "A different confirmation is already active", 409, request_id,
            )
        approved = validate_project_draft(
            request.get("approvedSnapshot"),
            idempotency_key=request.get("idempotencyKey"),
            lookup_agent=self.lookup_agent,
            is_excluded_agent=self.is_excluded_agent,
            config=self.store.config,
            reviewer_assignment_confirmed=True,
        )
        now = self._timestamp()
        project_id = f"project-{request_id}"
        if any(item.get("id") == project_id for item in root.get("projects", [])):
            raise ProjectAuthoringCommandError(
                "project_id_conflict", "Materialized project id already exists", 409, request_id,
            )
        template_ref = self._materialize_template(root, request_id, approved, now, actor)
        recurrence_ref = self._materialize_recurrence(
            root, request_id, request, approved, template_ref, now, actor,
        )
        project = self._build_project(
            project_id=project_id,
            request=request,
            approved=approved,
            workspace=workspace,
            template_ref=template_ref,
            recurrence_ref=recurrence_ref,
            now=now,
        )
        root.setdefault("projects", []).append(project)
        maintenance_mode = str(approved.get("agentMaintenanceMode") or "strict_confirmation")
        allowed_operations = ["status", "maintenance_request"]
        if maintenance_mode == "autonomous":
            allowed_operations.append("routine_task_update")
        root[GRANTS_KEY][project_id] = {
            "id": f"grant-{project_id}",
            "projectId": project_id,
            "requestId": request_id,
            "requestingAgentId": request.get("requestingAgentId"),
            "secretHash": request.get("requestSecretHash"),
            "version": 1,
            "state": "active",
            "maintenanceMode": maintenance_mode,
            "allowedOperations": allowed_operations,
            "createdAt": now,
            "updatedAt": now,
            "audit": [self._audit(
                "grant_activated", actor, "management", now, "accepted",
                requestId=request_id, projectId=project_id,
            )],
        }
        request.update({
            "state": "confirmed",
            "revision": int(request.get("revision") or 0) + 1,
            "projectId": project_id,
            "confirmedBy": actor,
            "confirmedAt": now,
            "terminalAt": now,
            "updatedAt": now,
            "approvedSnapshot": copy.deepcopy(approved),
        })
        request.pop("code", None)
        request.pop("error", None)
        self._append_audit(request, "project_materialized", actor, "management", now, "accepted")
        root[IDEMPOTENCY_KEY][confirmation_record_key] = {
            "requestId": request_id,
            "projectId": project_id,
            "confirmationKey": confirmation_key,
            "createdAt": now,
        }
        return {
            "ok": True,
            "created": True,
            "project": copy.deepcopy(project),
            "request": management_request_view(request),
        }

    def authenticate_project_grant(
        self,
        project_id: str,
        *,
        requesting_agent_id: str,
        grant_secret: str,
        required_operation: str | None = None,
    ) -> dict[str, Any]:
        root = self.store.snapshot()
        grant = root[GRANTS_KEY].get(str(project_id or ""))
        agent_id = str(requesting_agent_id or "").strip()
        self._validate_grant_record(
            grant,
            project_id=project_id,
            requesting_agent_id=agent_id,
            grant_secret=grant_secret,
            required_operation=required_operation,
        )
        return grant_public_view(grant)

    def instantiate_template(
        self,
        template_id: str,
        version: int,
        *,
        idempotency_key: Any,
        overrides: Mapping[str, Any] | None = None,
        actor: str = "user",
        prepare_workspace: Callable[[Mapping[str, Any], str, str], Mapping[str, Any]] | None = None,
        cleanup_workspace: Callable[[Mapping[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        """Create one independent project from one immutable template version."""
        key = validate_idempotency_key(idempotency_key)
        clean_template_id = str(template_id or "").strip()
        try:
            version_number = int(version)
        except (TypeError, ValueError):
            version_number = 0
        if not clean_template_id or version_number < 1:
            raise ProjectAuthoringCommandError(
                "invalid_template_reference", "Template id and positive version are required", 400,
            )
        scoped_key = f"template-instantiation:{clean_template_id}:{version_number}:{key}"
        root = self.store.snapshot()
        existing = root[IDEMPOTENCY_KEY].get(scoped_key)
        existing_project_id = existing.get("projectId") if isinstance(existing, Mapping) else existing
        if existing_project_id:
            project = next(
                (item for item in root.get("projects", []) if item.get("id") == existing_project_id),
                None,
            )
            if project is not None:
                return {"ok": True, "created": False, "project": copy.deepcopy(project)}

        template = self._resolve_template_record(root, clean_template_id, version_number)
        snapshot = copy.deepcopy(template.get("snapshot") or {})
        self._validate_template_snapshot_actors(snapshot)
        configuration = self._template_instantiation_configuration(snapshot, overrides)
        project_id = f"project-template-{self.new_id()}"
        workspace: dict[str, Any] = {"ok": True, "managed": False, "created": False}
        try:
            execution = configuration.get("executionSettings") or {}
            if execution.get("projectExecutionEnabled") is True:
                if prepare_workspace is None:
                    raise ProjectAuthoringCommandError(
                        "workspace_preparation_required",
                        "Execution-enabled template instances require workspace preparation",
                        409,
                    )
                prepared = prepare_workspace(configuration, project_id, key)
                workspace = dict(prepared) if isinstance(prepared, Mapping) else {
                    "ok": False, "error": "Workspace preparation returned an invalid result",
                }
                if not workspace.get("ok"):
                    raise ProjectAuthoringCommandError(
                        str(workspace.get("code") or "workspace_preparation_failed"),
                        str(workspace.get("error") or "Workspace preparation failed"),
                        409,
                    )

            def commit(current: dict[str, Any]) -> dict[str, Any]:
                existing = current[IDEMPOTENCY_KEY].get(scoped_key)
                existing_id = existing.get("projectId") if isinstance(existing, Mapping) else existing
                if existing_id:
                    project = next(
                        (item for item in current.get("projects", []) if item.get("id") == existing_id),
                        None,
                    )
                    if project is not None:
                        return {"ok": True, "created": False, "project": copy.deepcopy(project)}
                latest = self._resolve_template_record(current, clean_template_id, version_number)
                if latest.get("snapshotDigest") != template.get("snapshotDigest"):
                    raise ProjectAuthoringCommandError(
                        "template_version_changed", "Template version changed during instantiation", 409,
                    )
                current_snapshot = copy.deepcopy(latest.get("snapshot") or {})
                self._validate_template_snapshot_actors(current_snapshot)
                if any(item.get("id") == project_id for item in current.get("projects", [])):
                    raise ProjectAuthoringCommandError(
                        "project_id_conflict", "Generated project id already exists", 409,
                    )
                now = self._timestamp()
                project = materialize_versioned_template_instance(
                    project_id=project_id,
                    template_id=clean_template_id,
                    version=version_number,
                    configuration=configuration,
                    workspace=workspace,
                    actor=actor,
                    timestamp=now,
                )
                current.setdefault("projects", []).append(project)
                current[IDEMPOTENCY_KEY][scoped_key] = {
                    "projectId": project_id,
                    "templateId": clean_template_id,
                    "templateVersion": version_number,
                    "idempotencyKey": key,
                    "createdAt": now,
                }
                return {"ok": True, "created": True, "project": copy.deepcopy(project)}

            result = self.store.update(commit)
            if not result.get("created"):
                self._cleanup_prepared_workspace(workspace, cleanup_workspace)
            return result
        except Exception:
            self._cleanup_prepared_workspace(workspace, cleanup_workspace)
            raise

    def materialize_recurrence_occurrence(
        self,
        recurrence_id: str,
        occurrence_id: str,
        *,
        prepare_workspace: Callable[[Mapping[str, Any], str, str], Mapping[str, Any]] | None = None,
        cleanup_workspace: Callable[[Mapping[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        """Claim and atomically materialize one independent recurrence occurrence."""
        if not self.recurrence_enabled():
            raise ProjectAuthoringCommandError(
                "project_recurrence_disabled", "Recurring project dispatch is disabled", 503,
            )
        if self.recurrence_paused():
            raise ProjectAuthoringCommandError(
                "project_recurrence_dispatch_paused", "Recurring project dispatch is paused", 503,
            )
        clean_recurrence_id = str(recurrence_id or "").strip()
        clean_occurrence_id = str(occurrence_id or "").strip()
        if not clean_recurrence_id or not clean_occurrence_id or len(clean_occurrence_id) > 300:
            raise ProjectAuthoringCommandError(
                "invalid_occurrence_reference", "Recurrence id and bounded occurrence id are required", 400,
            )
        claim_token = ""
        now_dt = self.clock().astimezone(timezone.utc)
        now = now_dt.isoformat()
        outcome: dict[str, Any] = {}

        def claim(root: dict[str, Any]) -> None:
            nonlocal claim_token
            recurrence = root[RECURRENCES_KEY].get(clean_recurrence_id)
            if not isinstance(recurrence, dict):
                raise ProjectAuthoringCommandError(
                    "recurrence_not_found", "Recurring project definition was not found", 404,
                )
            if recurrence.get("paused") is True:
                raise ProjectAuthoringCommandError(
                    "recurrence_paused", "Recurring project definition is paused", 409,
                )
            existing_project = self._find_occurrence_project(
                root.get("projects") or [], clean_recurrence_id, clean_occurrence_id,
            )
            if existing_project is not None:
                outcome.update({"status": "created", "project": copy.deepcopy(existing_project)})
                return
            occurrences = recurrence.setdefault("occurrences", {})
            record = occurrences.get(clean_occurrence_id)
            if isinstance(record, dict) and record.get("state") == "intervention_required":
                outcome.update({
                    "status": "intervention_required",
                    "code": record.get("code"),
                    "error": record.get("error"),
                })
                return
            if isinstance(record, dict) and record.get("state") == "created" and record.get("projectId"):
                project = next(
                    (item for item in root.get("projects", []) if item.get("id") == record.get("projectId")),
                    None,
                )
                if project is not None:
                    outcome.update({"status": "created", "project": copy.deepcopy(project)})
                    return
            expires_at = self._parse_timestamp(record.get("claimExpiresAt")) if isinstance(record, dict) else None
            if (
                isinstance(record, dict)
                and record.get("state") == "claimed"
                and expires_at is not None
                and expires_at > now_dt
            ):
                outcome.update({
                    "status": "claimed",
                    "claimExpiresAt": record.get("claimExpiresAt"),
                })
                return
            attempts = int(record.get("attempts") or 0) + 1 if isinstance(record, dict) else 1
            claim_token = f"occurrence-claim-{self.new_id()}"
            occurrences[clean_occurrence_id] = {
                "occurrenceId": clean_occurrence_id,
                "executionMode": stored_recurrence_execution_mode(recurrence),
                "state": "claimed",
                "claimToken": claim_token,
                "claimOwner": "project-recurrence-dispatch",
                "claimedAt": now,
                "claimExpiresAt": (
                    now_dt + timedelta(seconds=self.store.config.occurrence_claim_seconds)
                ).isoformat(),
                "attempts": attempts,
                "updatedAt": now,
            }
            self._append_occurrence_history(
                recurrence,
                clean_occurrence_id,
                "claimed",
                now,
                {"attempt": attempts},
            )
            outcome.update({"status": "owned", "attempts": attempts})

        self.store.update(claim)
        if outcome.get("status") == "created":
            result = {"ok": True, "created": False, "status": "created", "project": outcome["project"]}
            return self._with_reconciled_occurrence_execution(
                result, clean_recurrence_id, clean_occurrence_id,
            )
        if outcome.get("status") == "claimed":
            return {
                "ok": True,
                "created": False,
                "status": "in_progress",
                "claimExpiresAt": outcome.get("claimExpiresAt"),
                "_status": 202,
            }
        if outcome.get("status") == "intervention_required":
            return {
                "ok": False,
                "created": False,
                "status": "intervention_required",
                "code": outcome.get("code"),
                "error": outcome.get("error"),
                "_status": 409,
            }

        workspace: dict[str, Any] = {"ok": True, "managed": False, "created": False}
        try:
            initial_root = self.store.snapshot()
            recurrence = initial_root[RECURRENCES_KEY].get(clean_recurrence_id) or {}
            template_id = str(recurrence.get("templateId") or "")
            template_version = int(recurrence.get("templateVersion") or 0)
            template = self._resolve_template_record(initial_root, template_id, template_version)
            snapshot = copy.deepcopy(template.get("snapshot") or {})
            self._validate_template_snapshot_actors(snapshot)
            configuration = self._template_instantiation_configuration(snapshot, None)
            suffix = hashlib.sha256(clean_occurrence_id.encode()).hexdigest()[:16]
            project_id = f"project-{clean_recurrence_id}-{suffix}"
            execution = configuration.get("executionSettings") or {}
            if execution.get("projectExecutionEnabled") is True:
                if prepare_workspace is None:
                    raise ProjectAuthoringCommandError(
                        "workspace_preparation_required",
                        "Execution-enabled recurring instances require workspace preparation",
                        409,
                    )
                prepared = prepare_workspace(configuration, project_id, clean_occurrence_id)
                workspace = dict(prepared) if isinstance(prepared, Mapping) else {
                    "ok": False, "error": "Workspace preparation returned an invalid result",
                }
                if not workspace.get("ok"):
                    raise ProjectAuthoringCommandError(
                        str(workspace.get("code") or "workspace_preparation_failed"),
                        str(workspace.get("error") or "Workspace preparation failed"),
                        409,
                    )

            def commit(root: dict[str, Any]) -> dict[str, Any]:
                current = root[RECURRENCES_KEY].get(clean_recurrence_id)
                record = (current.get("occurrences") or {}).get(clean_occurrence_id) if isinstance(current, dict) else None
                if not isinstance(current, dict) or not isinstance(record, dict):
                    raise ProjectAuthoringCommandError(
                        "occurrence_claim_lost", "Recurring project occurrence claim was lost", 409,
                    )
                existing = self._find_occurrence_project(
                    root.get("projects") or [], clean_recurrence_id, clean_occurrence_id,
                )
                if existing is not None:
                    record.update({"state": "created", "projectId": existing.get("id"), "updatedAt": self._timestamp()})
                    return {"ok": True, "created": False, "status": "created", "project": copy.deepcopy(existing)}
                if record.get("claimToken") != claim_token or record.get("state") != "claimed":
                    raise ProjectAuthoringCommandError(
                        "occurrence_claim_lost", "Recurring project occurrence claim is owned by another worker", 409,
                    )
                latest = self._resolve_template_record(root, template_id, template_version)
                if latest.get("snapshotDigest") != template.get("snapshotDigest"):
                    raise ProjectAuthoringCommandError(
                        "template_version_changed", "Recurring project template version changed", 409,
                    )
                latest_snapshot = copy.deepcopy(latest.get("snapshot") or {})
                self._validate_template_snapshot_actors(latest_snapshot)
                committed_at = self._timestamp()
                project = materialize_recurrence_occurrence_project(
                    project_id=project_id,
                    template_id=template_id,
                    template_version=template_version,
                    recurrence_id=clean_recurrence_id,
                    occurrence_id=clean_occurrence_id,
                    configuration=configuration,
                    workspace=workspace,
                    actor=current.get("requestingAgentId") or "project-recurrence",
                    timestamp=committed_at,
                )
                root.setdefault("projects", []).append(project)
                record.update({
                    "state": "created",
                    "projectId": project_id,
                    "createdAt": committed_at,
                    "updatedAt": committed_at,
                })
                execution_mode = stored_recurrence_execution_mode(current)
                record["executionMode"] = execution_mode
                if execution_mode == CREATE_AND_EXECUTE:
                    record["executionIntent"] = new_occurrence_execution_intent(
                        project_id=project_id,
                        occurrence_id=clean_occurrence_id,
                        timestamp=committed_at,
                    )
                for field in ("claimToken", "claimOwner", "claimExpiresAt"):
                    record.pop(field, None)
                current.update({
                    "lastOccurrenceId": clean_occurrence_id,
                    "lastProjectId": project_id,
                    "lastStatus": "created",
                    "updatedAt": committed_at,
                })
                self._append_occurrence_history(
                    current,
                    clean_occurrence_id,
                    "created",
                    committed_at,
                    {"projectId": project_id},
                )
                self._prune_occurrences(current)
                return {"ok": True, "created": True, "status": "created", "project": copy.deepcopy(project)}

            result = self.store.update(commit)
            if not result.get("created"):
                self._cleanup_prepared_workspace(workspace, cleanup_workspace)
            return self._with_reconciled_occurrence_execution(
                result, clean_recurrence_id, clean_occurrence_id,
            )
        except Exception as exc:
            self._cleanup_prepared_workspace(workspace, cleanup_workspace)
            self._record_occurrence_failure(
                clean_recurrence_id,
                clean_occurrence_id,
                claim_token,
                exc,
            )
            raise

    def _with_reconciled_occurrence_execution(
        self,
        result: dict[str, Any],
        recurrence_id: str,
        occurrence_id: str,
    ) -> dict[str, Any]:
        execution = self.recurrence_execution.reconcile(recurrence_id, occurrence_id)
        if execution.get("state") not in {None, "not_requested"}:
            result = {**result, "automaticExecution": execution}
        return result

    def authenticate_recurrence_dispatch(
        self,
        recurrence_id: str,
        *,
        requesting_agent_id: str,
        grant_secret: str,
    ) -> dict[str, Any]:
        root = self.store.snapshot()
        recurrence = root[RECURRENCES_KEY].get(str(recurrence_id or ""))
        agent_id = str(requesting_agent_id or "").strip()
        source_project_id = recurrence.get("sourceProjectId") if isinstance(recurrence, dict) else ""
        if not isinstance(recurrence, dict) or recurrence.get("requestingAgentId") != agent_id or not source_project_id:
            raise ProjectAuthoringCommandError(
                "recurrence_not_found", "Recurring project definition was not found", 404,
            )
        self._validate_grant_record(
            root[GRANTS_KEY].get(source_project_id),
            project_id=source_project_id,
            requesting_agent_id=agent_id,
            grant_secret=grant_secret,
            required_operation="status",
        )
        return {
            "id": recurrence.get("id"),
            "sourceProjectId": source_project_id,
            "requestingAgentId": agent_id,
            "state": recurrence.get("state"),
            "paused": recurrence.get("paused") is True,
        }

    def create_maintenance_request(
        self,
        project_id: str,
        mutation: Any,
        *,
        requesting_agent_id: str,
        grant_secret: str,
        idempotency_key: Any,
    ) -> dict[str, Any]:
        key = validate_idempotency_key(idempotency_key)
        now = self._timestamp()
        maintenance_id = f"maintenance-{self.new_id()}"
        outcome: dict[str, Any] = {}

        def create(root: dict[str, Any]) -> None:
            project = next((item for item in root.get("projects", []) if item.get("id") == project_id), None)
            if project is None:
                raise ProjectAuthoringCommandError("project_not_found", "Project not found", 404)
            grant = root[GRANTS_KEY].get(project_id)
            self._validate_grant_record(
                grant,
                project_id=project_id,
                requesting_agent_id=requesting_agent_id,
                grant_secret=grant_secret,
                required_operation="maintenance_request",
            )
            scoped_key = f"{requesting_agent_id}:{key}"
            existing_id = grant["maintenanceIdempotency"].get(scoped_key)
            existing = grant["maintenanceRequests"].get(str(existing_id or ""))
            if isinstance(existing, dict):
                outcome.update({"created": False, "request": copy.deepcopy(existing)})
                return
            normalized = self._normalize_maintenance_mutation(mutation)
            request = {
                "id": maintenance_id,
                "projectId": project_id,
                "requestingAgentId": requesting_agent_id,
                "idempotencyKey": key,
                "state": "pending",
                "revision": 1,
                "mutation": copy.deepcopy(normalized),
                "createdAt": now,
                "updatedAt": now,
                "audit": [self._audit(
                    "maintenance_requested", requesting_agent_id, "agent", now, "accepted",
                    projectId=project_id, maintenanceRequestId=maintenance_id,
                )],
                "history": [],
            }
            grant["maintenanceRequests"][maintenance_id] = request
            grant["maintenanceIdempotency"][scoped_key] = maintenance_id
            grant["updatedAt"] = now
            outcome.update({"created": True, "request": copy.deepcopy(request)})

        self.store.update(create)
        return {
            "ok": True,
            "created": outcome["created"],
            "request": management_request_view(outcome["request"]),
        }

    @staticmethod
    def _validate_confirmed_maintenance_confirmation(confirmation: Any) -> str:
        if not isinstance(confirmation, Mapping) or confirmation.get("confirmed") is not True:
            raise ProjectAuthoringCommandError(
                "maintenance_confirmation_required",
                "Confirmed maintenance requires confirmation.confirmed=true",
                400,
            )
        summary_text = str(confirmation.get("summaryText") or "")
        if not summary_text.strip():
            raise ProjectAuthoringCommandError(
                "maintenance_summary_text_required",
                "Confirmed maintenance requires confirmation.summaryText",
                400,
            )
        summary_digest = str(confirmation.get("summaryDigest") or "").strip().lower()
        if len(summary_digest) != 64 or any(ch not in "0123456789abcdef" for ch in summary_digest):
            raise ProjectAuthoringCommandError(
                "maintenance_summary_digest_invalid",
                "Confirmed maintenance requires a SHA-256 summaryDigest",
                400,
            )
        if _text_digest(summary_text) != summary_digest:
            raise ProjectAuthoringCommandError(
                "maintenance_summary_digest_mismatch",
                "Confirmed maintenance summaryDigest does not match summaryText",
                400,
            )
        required_markers = (
            "我准备修改这个 VO 项目，请确认：",
            "项目 ID：",
            "修改内容：",
            "请确认是否按以上方案修改真实项目。",
        )
        missing = [marker for marker in required_markers if marker not in summary_text]
        if missing:
            raise ProjectAuthoringCommandError(
                "maintenance_summary_template_required",
                "Confirmed maintenance summaryText must use the required maintenance confirmation template",
                400,
            )
        return summary_digest

    def apply_confirmed_maintenance(
        self,
        project_id: str,
        mutation: Any,
        *,
        requesting_agent_id: str,
        idempotency_key: Any,
        confirmation: Any,
    ) -> dict[str, Any]:
        agent_id = str(requesting_agent_id or "").strip()
        self._validate_requesting_agent(agent_id)
        key = validate_idempotency_key(idempotency_key)
        summary_digest = self._validate_confirmed_maintenance_confirmation(confirmation)
        normalized = self._normalize_maintenance_mutation(mutation)
        payload_digest = _canonical_digest({
            "confirmationSummaryDigest": summary_digest,
            "mutation": normalized,
            "projectId": str(project_id or ""),
        })
        scoped_key = f"confirmed-maintenance:{agent_id}:{project_id}:{key}"
        now = self._timestamp()

        def apply(root: dict[str, Any]) -> dict[str, Any]:
            existing = root[IDEMPOTENCY_KEY].get(scoped_key)
            if isinstance(existing, Mapping):
                if existing.get("payloadDigest") != payload_digest:
                    raise ProjectAuthoringCommandError(
                        "maintenance_idempotency_conflict",
                        "Maintenance idempotency key was already used for different confirmed content",
                        409,
                    )
                project = next(
                    (item for item in root.get("projects", []) if item.get("id") == existing.get("projectId")),
                    None,
                )
                return {
                    "ok": True,
                    "created": False,
                    "project": copy.deepcopy(project) if isinstance(project, dict) else None,
                    "mutation": copy.deepcopy(existing.get("mutation") or normalized),
                    "confirmationSummaryDigest": existing.get("confirmationSummaryDigest"),
                }
            project = next((item for item in root.get("projects", []) if item.get("id") == project_id), None)
            if project is None:
                raise ProjectAuthoringCommandError("project_not_found", "Project not found", 404)
            grant = root[GRANTS_KEY].get(project_id)
            persisted_grant = isinstance(grant, dict)
            if not isinstance(grant, dict):
                grant = {
                    "id": f"grant-{project_id}",
                    "projectId": project_id,
                    "requestingAgentId": agent_id,
                    "state": "active",
                    "maintenanceMode": project.get("agentMaintenanceMode") or "strict_confirmation",
                    "allowedOperations": ["status", "maintenance_request"],
                    "createdAt": now,
                    "updatedAt": now,
                    "audit": [],
                    "maintenanceRequests": {},
                    "maintenanceIdempotency": {},
                    "autonomousIdempotency": {},
                }
            self._apply_maintenance_mutation(root, project, grant, normalized, now)
            project["updatedAt"] = now
            if persisted_grant:
                grant["updatedAt"] = now
                self._append_grant_audit(
                    grant,
                    "confirmed_maintenance_applied",
                    agent_id,
                    now,
                )
            project.setdefault("maintenanceHistory", []).append({
                "id": f"confirmed-maintenance-{self.new_id()}",
                "type": "confirmed_agent_maintenance",
                "requestingAgentId": agent_id,
                "operation": normalized.get("operation"),
                "confirmationSummaryDigest": summary_digest,
                "createdAt": now,
            })
            project["maintenanceHistory"] = project["maintenanceHistory"][-self.store.config.audit_history_limit:]
            result = {
                "ok": True,
                "created": True,
                "project": copy.deepcopy(project),
                "mutation": copy.deepcopy(normalized),
                "confirmationSummaryDigest": summary_digest,
            }
            root[IDEMPOTENCY_KEY][scoped_key] = {
                "projectId": project_id,
                "requestingAgentId": agent_id,
                "idempotencyKey": key,
                "payloadDigest": payload_digest,
                "mutation": copy.deepcopy(normalized),
                "confirmationSummaryDigest": summary_digest,
                "createdAt": now,
            }
            return result

        return self.store.update(apply)

    def confirm_maintenance_request(
        self,
        project_id: str,
        maintenance_id: str,
        *,
        expected_revision: int,
        actor: str = "user",
    ) -> dict[str, Any]:
        now = self._timestamp()

        def confirm(root: dict[str, Any]) -> dict[str, Any]:
            project = next((item for item in root.get("projects", []) if item.get("id") == project_id), None)
            grant = root[GRANTS_KEY].get(project_id)
            if project is None or not isinstance(grant, dict):
                raise ProjectAuthoringCommandError("project_not_found", "Project not found", 404)
            request = (grant.get("maintenanceRequests") or {}).get(maintenance_id)
            if not isinstance(request, dict):
                raise ProjectAuthoringCommandError(
                    "maintenance_request_not_found", "Maintenance request not found", 404,
                )
            if request.get("state") == "confirmed":
                return {"project": copy.deepcopy(project), "request": management_request_view(request)}
            actual = int(request.get("revision") or 0)
            if actual != int(expected_revision):
                raise ProjectAuthoringCommandError(
                    "maintenance_revision_conflict", "Maintenance request revision changed", 409,
                    maintenance_id, int(expected_revision), actual,
                )
            if request.get("state") not in {"pending", "failed"}:
                raise ProjectAuthoringCommandError(
                    "invalid_maintenance_state", "Maintenance request cannot be confirmed", 409,
                )
            self._apply_maintenance_mutation(root, project, grant, request["mutation"], now)
            request.update({
                "state": "confirmed",
                "revision": actual + 1,
                "confirmedAt": now,
                "confirmedBy": actor,
                "updatedAt": now,
            })
            request.setdefault("audit", []).append(
                self._audit(
                    "maintenance_confirmed", actor, "management", now, "accepted",
                    projectId=project_id, maintenanceRequestId=maintenance_id,
                )
            )
            request["audit"] = request["audit"][-self.store.config.audit_history_limit:]
            project["updatedAt"] = now
            grant["updatedAt"] = now
            self._append_grant_audit(
                grant, "maintenance_applied", actor, now,
                maintenanceRequestId=maintenance_id,
            )
            return {"project": copy.deepcopy(project), "request": management_request_view(request)}

        try:
            result = self.store.update(confirm)
        except Exception as exc:
            self._record_maintenance_failure(
                project_id, maintenance_id, exc, actor=actor,
            )
            raise
        return {"ok": True, **result}

    def reject_maintenance_request(
        self,
        project_id: str,
        maintenance_id: str,
        *,
        expected_revision: int,
        reason: Any,
        actor: str = "user",
    ) -> dict[str, Any]:
        rejection_reason = str(reason or "").strip()
        if not rejection_reason:
            raise ProjectAuthoringCommandError(
                "rejection_reason_required", "A rejection reason is required", 400,
            )
        now = self._timestamp()

        def reject(root: dict[str, Any]) -> dict[str, Any]:
            grant = root[GRANTS_KEY].get(project_id)
            request = (grant.get("maintenanceRequests") or {}).get(maintenance_id) if isinstance(grant, dict) else None
            if not isinstance(request, dict):
                raise ProjectAuthoringCommandError(
                    "maintenance_request_not_found", "Maintenance request not found", 404,
                )
            if request.get("state") == "rejected":
                return management_request_view(request)
            actual = int(request.get("revision") or 0)
            if actual != int(expected_revision) or request.get("state") not in {"pending", "failed"}:
                raise ProjectAuthoringCommandError(
                    "maintenance_revision_conflict", "Maintenance request changed", 409,
                    maintenance_id, int(expected_revision), actual,
                )
            request.update({
                "state": "rejected",
                "revision": actual + 1,
                "rejectionReason": rejection_reason,
                "rejectedAt": now,
                "rejectedBy": actor,
                "updatedAt": now,
            })
            request.setdefault("audit", []).append(
                self._audit(
                    "maintenance_rejected", actor, "management", now, "accepted",
                    projectId=project_id, maintenanceRequestId=maintenance_id,
                )
            )
            return management_request_view(request)

        return {"ok": True, "request": self.store.update(reject)}

    def apply_autonomous_routine_update(
        self,
        project_id: str,
        task_id: str,
        changes: Any,
        *,
        requesting_agent_id: str,
        grant_secret: str,
        idempotency_key: Any,
    ) -> dict[str, Any]:
        key = validate_idempotency_key(idempotency_key)
        now = self._timestamp()
        scoped_key = f"{requesting_agent_id}:{key}"

        def apply(root: dict[str, Any]) -> dict[str, Any]:
            project = next((item for item in root.get("projects", []) if item.get("id") == project_id), None)
            grant = root[GRANTS_KEY].get(project_id)
            if project is None:
                raise ProjectAuthoringCommandError("project_not_found", "Project not found", 404)
            self._validate_grant_record(
                grant,
                project_id=project_id,
                requesting_agent_id=requesting_agent_id,
                grant_secret=grant_secret,
                required_operation="routine_task_update",
            )
            if project.get("agentMaintenanceMode") != "autonomous" or grant.get("maintenanceMode") != "autonomous":
                raise ProjectAuthoringCommandError(
                    "autonomous_maintenance_disabled", "Project autonomous maintenance is disabled", 403,
                )
            existing = grant["autonomousIdempotency"].get(scoped_key)
            if isinstance(existing, dict):
                return {"created": False, **copy.deepcopy(existing.get("result") or {})}
            if not isinstance(changes, Mapping) or not changes:
                raise ProjectAuthoringCommandError(
                    "routine_update_changes_required", "Routine update requires changes", 400,
                )
            unknown = set(changes) - AUTONOMOUS_ROUTINE_FIELDS
            if unknown:
                raise ProjectAuthoringCommandError(
                    "autonomous_field_not_allowed",
                    f"Autonomous update fields are not allowed: {', '.join(sorted(unknown))}",
                    403,
                )
            task = self._maintenance_task(project, task_id)
            actors = task_actor_references(task)
            assigned_agent_ids = {
                actor.get("id") for actor in (actors.get("responsible"), actors.get("executor"))
                if isinstance(actor, dict) and actor.get("type") == "agent"
            }
            if requesting_agent_id not in assigned_agent_ids:
                raise ProjectAuthoringCommandError(
                    "agent_not_assigned_to_task", "Agent is not assigned to this task", 403,
                )
            for field, value in changes.items():
                task[field] = copy.deepcopy(value)
            task["updatedAt"] = now
            history = task.setdefault("maintenanceHistory", [])
            history.append({
                "actor": requesting_agent_id,
                "source": "autonomous_grant",
                "changedFields": sorted(changes),
                "at": now,
            })
            task["maintenanceHistory"] = history[-self.store.config.audit_history_limit:]
            project["updatedAt"] = now
            self._append_grant_audit(
                grant, "autonomous_routine_update", requesting_agent_id, now,
                taskId=task_id, changedFields=sorted(changes),
            )
            result = {
                "task": copy.deepcopy(task),
                "changedFields": sorted(changes),
                "updatedAt": now,
            }
            grant["autonomousIdempotency"][scoped_key] = {
                "taskId": task_id,
                "createdAt": now,
                "result": copy.deepcopy(result),
            }
            return {"created": True, **result}

        result = self.store.update(apply)
        return {"ok": True, **result}

    def revoke_project_grant(self, project_id: str, *, actor: str = "user") -> dict[str, Any]:
        now = self._timestamp()

        def revoke(root: dict[str, Any]) -> dict[str, Any]:
            grant = root[GRANTS_KEY].get(project_id)
            if not isinstance(grant, dict):
                raise ProjectAuthoringCommandError(
                    "project_grant_not_found", "Project grant not found", 404,
                )
            if grant.get("state") != "revoked":
                grant.update({
                    "state": "revoked",
                    "secretHash": "",
                    "version": int(grant.get("version") or 0) + 1,
                    "revokedAt": now,
                    "revokedBy": actor,
                    "updatedAt": now,
                })
                self._append_grant_audit(grant, "grant_revoked", actor, now)
            return grant_public_view(grant)

        return self.store.update(revoke)

    def rotate_project_grant(
        self,
        project_id: str,
        *,
        secret_hash: str,
        actor: str = "user",
    ) -> dict[str, Any]:
        now = self._timestamp()

        def rotate(root: dict[str, Any]) -> dict[str, Any]:
            grant = root[GRANTS_KEY].get(project_id)
            if not isinstance(grant, dict):
                raise ProjectAuthoringCommandError(
                    "project_grant_not_found", "Project grant not found", 404,
                )
            grant.update({
                "state": "active",
                "secretHash": str(secret_hash or ""),
                "version": int(grant.get("version") or 0) + 1,
                "rotatedAt": now,
                "rotatedBy": actor,
                "updatedAt": now,
            })
            grant.pop("revokedAt", None)
            grant.pop("revokedBy", None)
            self._append_grant_audit(grant, "grant_rotated", actor, now)
            return grant_public_view(grant)

        return self.store.update(rotate)

    def _materialize_template(
        self,
        root: dict[str, Any],
        request_id: str,
        approved: Mapping[str, Any],
        now: str,
        actor: str,
    ) -> dict[str, Any]:
        template = approved.get("template") if isinstance(approved.get("template"), Mapping) else {}
        mode = template.get("mode")
        if mode == "none":
            return {}
        if mode == "reference":
            template_id = str(template.get("templateId") or "")
            version = int(template.get("version") or 0)
            try:
                resolve_template_version(
                    root[TEMPLATES_KEY], root.get("templates") or [], template_id, version,
                )
            except ProjectTemplateError as exc:
                raise ProjectAuthoringCommandError(
                    exc.code, str(exc), 409, request_id,
                ) from exc
            return {"id": template_id, "version": version}

        template_id = str(template.get("templateId") or f"template-{request_id}")
        versions = root[TEMPLATES_KEY].setdefault(template_id, [])
        legacy = next(
            (
                item for item in (root.get("templates") or [])
                if isinstance(item, Mapping) and str(item.get("id") or "") == template_id
            ),
            None,
        )
        if legacy is not None and not versions:
            versions.append(adapt_legacy_template(legacy))
        version = append_template_version(
            versions,
            template_id=template_id,
            name=template.get("name") or approved.get("title"),
            draft=approved,
            created_at=now,
            created_by=actor,
            source_request_id=request_id,
        )
        summaries = root.setdefault("templates", [])
        summary = next(
            (
                item for item in summaries
                if isinstance(item, dict) and str(item.get("id") or "") == template_id
            ),
            None,
        )
        if summary is None:
            summaries.append({
                "id": template_id,
                "title": version["name"],
                "description": approved.get("description") or "",
                "version": version["version"],
            })
        else:
            summary["version"] = version["version"]
        return {"id": template_id, "version": version["version"]}

    def _record_occurrence_failure(
        self,
        recurrence_id: str,
        occurrence_id: str,
        claim_token: str,
        error: Exception,
    ) -> None:
        now = self._timestamp()
        code = str(getattr(error, "code", "occurrence_materialization_failed"))
        safe_error = sanitize_audit_text(error, limit=1000)
        actor_intervention = code in OCCURRENCE_ACTOR_INTERVENTION_CODES

        def fail(root: dict[str, Any]) -> None:
            recurrence = root[RECURRENCES_KEY].get(recurrence_id)
            record = (recurrence.get("occurrences") or {}).get(occurrence_id) if isinstance(recurrence, dict) else None
            if not isinstance(recurrence, dict) or not isinstance(record, dict):
                return
            if record.get("claimToken") != claim_token or record.get("state") != "claimed":
                return
            record.update({
                "state": "intervention_required" if actor_intervention else "failed",
                "retryable": not actor_intervention,
                "code": code,
                "error": safe_error,
                "failedAt": now,
                "updatedAt": now,
            })
            for field in ("claimToken", "claimOwner", "claimExpiresAt"):
                record.pop(field, None)
            recurrence.update({
                "lastOccurrenceId": occurrence_id,
                "lastStatus": "intervention_required" if actor_intervention else "failed",
                "lastError": {"code": code, "error": safe_error, "at": now},
                "updatedAt": now,
            })
            if actor_intervention:
                recurrence.setdefault("interventionAlerts", []).append({
                    "type": "invalid_template_actor",
                    "occurrenceId": occurrence_id,
                    "code": code,
                    "error": safe_error,
                    "createdAt": now,
                    "resolved": False,
                })
                recurrence["interventionAlerts"] = recurrence["interventionAlerts"][
                    -self.store.config.recurrence_history_limit:
                ]
            self._append_occurrence_history(
                recurrence,
                occurrence_id,
                "intervention_required" if actor_intervention else "failed",
                now,
                {"code": code, "error": safe_error},
            )
            self._prune_occurrences(recurrence)

        try:
            self.store.update(fail)
        except Exception:
            pass

    def _append_occurrence_history(
        self,
        recurrence: dict[str, Any],
        occurrence_id: str,
        status: str,
        at: str,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        recurrence.setdefault("occurrenceHistory", []).append({
            "occurrenceId": occurrence_id,
            "status": status,
            "at": at,
            **copy.deepcopy(dict(detail or {})),
        })
        recurrence["occurrenceHistory"] = recurrence["occurrenceHistory"][-self.store.config.recurrence_history_limit:]

    def _prune_occurrences(self, recurrence: dict[str, Any]) -> None:
        occurrences = recurrence.get("occurrences")
        if not isinstance(occurrences, dict) or len(occurrences) <= self.store.config.recurrence_history_limit:
            return
        removable = sorted(
            (
                (str(record.get("updatedAt") or ""), occurrence_id)
                for occurrence_id, record in occurrences.items()
                if isinstance(record, dict) and record.get("state") in {"created", "failed"}
            ),
        )
        for _updated_at, occurrence_id in removable:
            if len(occurrences) <= self.store.config.recurrence_history_limit:
                break
            occurrences.pop(occurrence_id, None)

    @staticmethod
    def _find_occurrence_project(
        projects: list[Any], recurrence_id: str, occurrence_id: str,
    ) -> dict[str, Any] | None:
        return next(
            (
                project for project in projects
                if isinstance(project, dict)
                and isinstance(project.get("recurrenceRef"), Mapping)
                and project["recurrenceRef"].get("id") == recurrence_id
                and project["recurrenceRef"].get("occurrenceId") == occurrence_id
            ),
            None,
        )

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _resolve_template_record(
        root: Mapping[str, Any], template_id: str, version: int,
    ) -> dict[str, Any]:
        try:
            return resolve_template_version(
                root.get(TEMPLATES_KEY) or {}, root.get("templates") or [], template_id, version,
            )
        except ProjectTemplateError as exc:
            raise ProjectAuthoringCommandError(exc.code, str(exc), 404) from exc

    def _validate_template_snapshot_actors(self, snapshot: Mapping[str, Any]) -> None:
        tasks = snapshot.get("tasks") if isinstance(snapshot.get("tasks"), list) else []
        if not tasks:
            raise ProjectAuthoringCommandError(
                "template_tasks_required", "Template version has no task blueprints", 409,
            )
        for index, task in enumerate(tasks):
            if not isinstance(task, Mapping):
                raise ProjectAuthoringCommandError(
                    "invalid_template_task", f"Template task {index + 1} is invalid", 409,
                )
            try:
                validate_task_actor_references(
                    task,
                    lookup_agent=self.lookup_agent,
                    is_excluded_agent=self.is_excluded_agent,
                )
            except ActorReferenceError as exc:
                raise ProjectAuthoringCommandError(
                    exc.code, f"Template task {index + 1}: {exc.message}", 409,
                ) from exc

    @staticmethod
    def _template_instantiation_configuration(
        snapshot: Mapping[str, Any], overrides: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        result = copy.deepcopy(dict(snapshot))
        allowed = {"title", "description", "priority", "dueDate", "tags", "branch", "longTermProject"}
        supplied = dict(overrides or {})
        unknown = set(supplied) - allowed
        if unknown:
            raise ProjectAuthoringCommandError(
                "template_override_not_allowed",
                f"Template instance overrides are not allowed: {', '.join(sorted(unknown))}",
                400,
            )
        for field, value in supplied.items():
            result[field] = copy.deepcopy(value)
        title = str(result.get("title") or "").strip()
        if not title or len(title) > 200:
            raise ProjectAuthoringCommandError(
                "invalid_project_title", "Template instance title is required and must not exceed 200 characters", 400,
            )
        result["title"] = title
        return result

    @staticmethod
    def _build_template_instance_project(
        *,
        project_id: str,
        template_id: str,
        version: int,
        configuration: Mapping[str, Any],
        workspace: Mapping[str, Any],
        actor: str,
        now: str,
    ) -> dict[str, Any]:
        columns = copy.deepcopy(configuration.get("columns") or [])
        default_column = columns[0].get("id") if columns else None
        tasks = []
        for index, blueprint in enumerate(configuration.get("tasks") or []):
            task = copy.deepcopy(blueprint)
            actors = task_actor_references(task)
            raw_order = task.get("order")
            task.update({
                "id": f"{project_id}-task-{index + 1}",
                "columnId": task.get("columnId") or default_column,
                "order": index if raw_order is None else int(raw_order),
                **legacy_task_role_fields(actors),
                "executionState": "backlog",
                "activeAttemptId": None,
                "attempts": [],
                "createdAt": now,
                "updatedAt": now,
                "completedAt": None,
            })
            tasks.append(task)
        execution = configuration.get("executionSettings") if isinstance(
            configuration.get("executionSettings"), Mapping,
        ) else {}
        project = {
            "id": project_id,
            "title": configuration.get("title"),
            "description": configuration.get("description") or "",
            "projectType": "one_time",
            "status": "active",
            "priority": configuration.get("priority") or "medium",
            "dueDate": configuration.get("dueDate"),
            "tags": copy.deepcopy(configuration.get("tags") or []),
            "branch": configuration.get("branch") or "",
            "longTermProject": configuration.get("longTermProject") is True,
            "columns": columns,
            "tasks": tasks,
            "activity": [{
                "type": "project_instantiated_from_template",
                "by": actor,
                "at": now,
                "detail": f"Created from template {template_id} version {version}",
            }],
            "createdAt": now,
            "updatedAt": now,
            "createdBy": actor,
            "agentMaintenanceMode": configuration.get("agentMaintenanceMode") or "strict_confirmation",
            "authoringSource": {
                "kind": "manual_template_instance",
                "templateId": template_id,
                "templateVersion": version,
            },
            "templateRef": {"id": template_id, "version": version},
            "recurrenceRef": {},
            "projectExecutionEnabled": execution.get("projectExecutionEnabled") is True,
            "projectExecutionStartMode": execution.get("projectExecutionStartMode") or "continuous",
            "executionPolicy": copy.deepcopy(execution.get("executionPolicy") or {"maxActiveTasks": 1}),
            "defaultExecutorAgentId": execution.get("defaultExecutorAgentId"),
            "defaultReviewerAgentId": execution.get("defaultReviewerAgentId"),
            "projectExecutionFlowActive": False,
            "workflowActive": False,
            "workflowPhase": "idle",
            "activeTaskId": None,
            "activeAgent": None,
        }
        if workspace.get("workspacePath"):
            project.update({
                "workspacePath": workspace.get("workspacePath"),
                "workspaceKind": workspace.get("workspaceKind") or "directory",
                "workspaceManagedBy": workspace.get("workspaceManagedBy"),
                "workspaceCreatedAt": workspace.get("workspaceCreatedAt"),
                "workspaceStatus": copy.deepcopy(workspace.get("workspaceStatus") or {
                    "ok": True, "path": workspace.get("workspacePath"),
                }),
            })
        return project

    def _materialize_recurrence(
        self,
        root: dict[str, Any],
        request_id: str,
        request: Mapping[str, Any],
        approved: Mapping[str, Any],
        template_ref: Mapping[str, Any],
        now: str,
        actor: str,
    ) -> dict[str, Any]:
        recurrence = approved.get("recurrence") if isinstance(approved.get("recurrence"), Mapping) else {}
        if recurrence.get("enabled") is not True:
            return {}
        if not template_ref:
            raise ProjectAuthoringCommandError(
                "recurrence_template_required", "Recurring projects require a materialized template version", 409, request_id,
            )
        recurrence_id = f"recurrence-{request_id}"
        if recurrence_id in root[RECURRENCES_KEY]:
            raise ProjectAuthoringCommandError(
                "recurrence_id_conflict", "Recurrence already exists for another confirmation", 409, request_id,
            )
        record = {
            "id": recurrence_id,
            "targetType": "projectTemplateInstance",
            "templateId": template_ref.get("id"),
            "templateVersion": template_ref.get("version"),
            "schedule": copy.deepcopy(recurrence.get("schedule")),
            "paused": recurrence.get("paused") is True,
            "executionMode": stored_recurrence_execution_mode(recurrence),
            "state": "pending_registration",
            "requestingAgentId": request.get("requestingAgentId"),
            "sourceRequestId": request_id,
            "sourceProjectId": f"project-{request_id}",
            "createdAt": now,
            "createdBy": actor,
            "audit": [],
            "occurrenceHistory": [],
        }
        root[RECURRENCES_KEY][recurrence_id] = record
        root[OUTBOX_KEY].append({
            "id": f"outbox-{recurrence_id}",
            "kind": "register_project_template_instance",
            "recurrenceId": recurrence_id,
            "state": "pending",
            "attempts": 0,
            "createdAt": now,
            "updatedAt": now,
        })
        return {"id": recurrence_id}

    @staticmethod
    def _build_project(
        *,
        project_id: str,
        request: Mapping[str, Any],
        approved: Mapping[str, Any],
        workspace: Mapping[str, Any],
        template_ref: Mapping[str, Any],
        recurrence_ref: Mapping[str, Any],
        now: str,
    ) -> dict[str, Any]:
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
            if source_column in column_map:
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

    def _fail_materialization(
        self,
        request_id: str,
        expected_revision: int,
        code: str,
        error: str,
        *,
        raise_on_conflict: bool = True,
    ) -> dict[str, Any]:
        try:
            return self.mark_materialization_failed(
                request_id,
                expected_revision=expected_revision,
                code=str(code or "materialization_failed"),
                error=error,
            )
        except Exception:
            if raise_on_conflict:
                raise
            return {"state": "unknown", "code": code, "error": error}

    @staticmethod
    def _cleanup_prepared_workspace(
        workspace: Mapping[str, Any],
        cleanup_workspace: Callable[[Mapping[str, Any]], Any] | None,
    ) -> None:
        if cleanup_workspace is None:
            return
        if (
            workspace.get("workspaceManagedBy") != "system"
            or workspace.get("createdInAttempt") is not True
        ):
            return
        try:
            cleanup_workspace(workspace)
        except Exception:
            pass

    def _materialization_result(self, request: Mapping[str, Any]) -> dict[str, Any]:
        project_id = str(request.get("projectId") or "")
        project = next(
            (item for item in self.store.snapshot().get("projects", []) if item.get("id") == project_id),
            None,
        )
        if project is None:
            raise ProjectAuthoringCommandError(
                "materialized_project_missing", "Confirmed request project was not found", 409,
                str(request.get("id") or ""),
            )
        return {
            "ok": True,
            "created": False,
            "project": copy.deepcopy(project),
            "request": management_request_view(request),
        }

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
    def _audit(
        action: str,
        actor: str,
        source: str,
        at: str,
        result: str,
        **context: Any,
    ) -> dict[str, Any]:
        return build_audit_event(action, actor, source, at, result, **context)

    def _append_audit(self, request: dict[str, Any], action: str, actor: str, source: str, at: str, result: str) -> None:
        request.setdefault("audit", []).append(self._audit(
            action,
            actor,
            source,
            at,
            result,
            requestId=request.get("id"),
            projectId=request.get("projectId"),
        ))
        request["audit"] = request["audit"][-self.store.config.audit_history_limit:]

    def _append_grant_audit(
        self,
        grant: dict[str, Any],
        action: str,
        actor: str,
        at: str,
        **context: Any,
    ) -> None:
        grant.setdefault("audit", []).append(self._audit(
            action,
            actor,
            "management",
            at,
            "accepted",
            projectId=grant.get("projectId"),
            requestId=grant.get("requestId"),
            **context,
        ))
        grant["audit"] = grant["audit"][-self.store.config.audit_history_limit:]

    def _record_maintenance_failure(
        self,
        project_id: str,
        maintenance_id: str,
        error: Exception,
        *,
        actor: str,
    ) -> None:
        now = self._timestamp()

        def record(root: dict[str, Any]) -> None:
            grant = root[GRANTS_KEY].get(project_id)
            request = (grant.get("maintenanceRequests") or {}).get(maintenance_id) if isinstance(grant, dict) else None
            if not isinstance(request, dict):
                return
            code = str(getattr(error, "code", "maintenance_apply_failed"))
            safe_error = sanitize_audit_text(error, limit=1000)
            request.setdefault("audit", []).append(self._audit(
                "maintenance_apply_failed",
                actor,
                "management",
                now,
                "failed",
                projectId=project_id,
                maintenanceRequestId=maintenance_id,
                code=code,
                error=safe_error,
            ))
            request["audit"] = request["audit"][-self.store.config.audit_history_limit:]
            request["lastFailure"] = {"code": code, "error": safe_error, "at": now}
            request["updatedAt"] = now

        try:
            self.store.update(record)
        except Exception:
            pass

    @staticmethod
    def _validate_grant_record(
        grant: Any,
        *,
        project_id: str,
        requesting_agent_id: str,
        grant_secret: str,
        required_operation: str | None,
    ) -> None:
        allowed = grant.get("allowedOperations") if isinstance(grant, dict) else []
        if (
            not isinstance(grant, dict)
            or grant.get("state") != "active"
            or grant.get("projectId") != project_id
            or grant.get("requestingAgentId") != str(requesting_agent_id or "").strip()
            or not verify_request_secret(grant_secret, grant.get("secretHash"))
            or (required_operation and required_operation not in (allowed or []))
        ):
            raise ProjectAuthoringCommandError(
                "invalid_project_grant", "Project grant authentication failed", 403,
            )

    @staticmethod
    def _normalize_maintenance_mutation(mutation: Any) -> dict[str, Any]:
        if not isinstance(mutation, Mapping):
            raise ProjectAuthoringCommandError(
                "invalid_maintenance_mutation", "Maintenance mutation must be an object", 400,
            )
        operation = str(mutation.get("operation") or "").strip()
        if operation not in PROTECTED_MAINTENANCE_OPERATIONS:
            raise ProjectAuthoringCommandError(
                "unsupported_maintenance_operation", "Maintenance operation is not supported", 400,
            )
        normalized = copy.deepcopy(dict(mutation))
        normalized["operation"] = operation
        if operation in {"update_task", "delete_task", "reassign_roles"}:
            task_id = str(mutation.get("taskId") or "").strip()
            if not task_id:
                raise ProjectAuthoringCommandError(
                    "maintenance_task_required", "Maintenance operation requires taskId", 400,
                )
            normalized["taskId"] = task_id
        if operation in {"update_project", "update_task", "reassign_roles", "workspace_change", "maintenance_mode_change"}:
            if not isinstance(mutation.get("changes"), Mapping):
                raise ProjectAuthoringCommandError(
                    "maintenance_changes_required", "Maintenance operation requires changes", 400,
                )
            normalized["changes"] = copy.deepcopy(dict(mutation["changes"]))
        if operation == "create_task" and not isinstance(mutation.get("task"), Mapping):
            raise ProjectAuthoringCommandError(
                "maintenance_task_required", "create_task requires a task object", 400,
            )
        if operation == "update_recurrence" and not isinstance(mutation.get("changes"), Mapping):
            raise ProjectAuthoringCommandError(
                "maintenance_changes_required", "update_recurrence requires changes", 400,
            )
        return normalized

    def _apply_maintenance_mutation(
        self,
        root: dict[str, Any],
        project: dict[str, Any],
        grant: dict[str, Any],
        mutation: Mapping[str, Any],
        now: str,
    ) -> None:
        operation = mutation["operation"]
        if operation == "update_project":
            allowed = {"title", "description", "priority", "dueDate", "tags", "longTermProject", "projectType"}
            self._apply_allowed_changes(project, mutation["changes"], allowed)
            if "projectType" in mutation["changes"]:
                project_type = str(project.get("projectType") or "")
                if project_type not in {"one_time", "reusable", "recurring"}:
                    raise ProjectAuthoringCommandError(
                        "invalid_project_type", "projectType must be one_time, reusable, or recurring", 400,
                    )
            return
        if operation in {"update_task", "reassign_roles"}:
            task = self._maintenance_task(project, mutation["taskId"])
            allowed = (
                {"title", "description", "priority", "dueDate", "checklist", "evidence", "executionState"}
                if operation == "update_task"
                else {"responsibleActor", "executorActor", "reviewerActor", "reviewerRecommendation"}
            )
            self._apply_allowed_changes(task, mutation["changes"], allowed)
            if operation == "reassign_roles":
                actors = self._validate_maintenance_task_actors(task)
                task.update({
                    "responsibleActor": actors["responsible"],
                    "executorActor": actors["executor"],
                    "reviewerActor": actors["reviewer"],
                    **legacy_task_role_fields(actors),
                })
            task["updatedAt"] = now
            return
        if operation == "create_task":
            task_configuration = copy.deepcopy(dict(mutation["task"]))
            if not str(task_configuration.get("title") or "").strip():
                raise ProjectAuthoringCommandError(
                    "maintenance_task_title_required", "Created task requires a title", 400,
                )
            actors = self._validate_maintenance_task_actors(task_configuration)
            task_configuration.update({
                "responsibleActor": actors["responsible"],
                "executorActor": actors["executor"],
                "reviewerActor": actors["reviewer"],
                **legacy_task_role_fields(actors),
            })
            task_id = str(task_configuration.get("id") or f"task-{self.new_id()}")
            if any(item.get("id") == task_id for item in project.get("tasks", [])):
                raise ProjectAuthoringCommandError(
                    "maintenance_task_id_conflict", "Created task id already exists", 409,
                )
            task = materialize_task_base(
                task_configuration,
                columns=project.get("columns") or [],
                task_id=task_id,
                timestamp=now,
                existing_tasks=project.get("tasks") or [],
                new_id=lambda: task_id,
                now=lambda: now,
            )
            project.setdefault("tasks", []).append(task)
            return
        if operation == "delete_task":
            before = len(project.get("tasks", []))
            project["tasks"] = [item for item in project.get("tasks", []) if item.get("id") != mutation["taskId"]]
            if len(project["tasks"]) == before:
                raise ProjectAuthoringCommandError("task_not_found", "Task not found", 404)
            return
        if operation == "archive_project":
            project["status"] = "archived"
            return
        if operation == "workspace_change":
            allowed = {"workspacePath", "workspaceKind", "workspaceStatus", "projectExecutionEnabled"}
            self._apply_allowed_changes(project, mutation["changes"], allowed)
            return
        if operation == "maintenance_mode_change":
            mode = str(mutation["changes"].get("agentMaintenanceMode") or "")
            if mode not in {"strict_confirmation", "autonomous"}:
                raise ProjectAuthoringCommandError(
                    "invalid_maintenance_mode", "Maintenance mode is invalid", 400,
                )
            project["agentMaintenanceMode"] = mode
            grant["maintenanceMode"] = mode
            grant["allowedOperations"] = ["status", "maintenance_request"] + (
                ["routine_task_update"] if mode == "autonomous" else []
            )
            return
        if operation == "update_recurrence":
            allowed = {"schedule", "paused"}
            recurrence = copy.deepcopy(project.get("recurrence") if isinstance(project.get("recurrence"), Mapping) else {})
            recurrence.setdefault("enabled", True)
            self._apply_allowed_changes(recurrence, mutation["changes"], allowed)
            if "schedule" in recurrence:
                schedule = recurrence.get("schedule")
                if not isinstance(schedule, Mapping):
                    raise ProjectAuthoringCommandError("invalid_recurrence_schedule", "Project recurrence schedule is invalid", 400)
                kind = str(schedule.get("kind") or "").strip()
                if kind == "cron":
                    expr = str(schedule.get("expr") or "").strip()
                    if len(expr.split()) < 5 or len(expr.split()) > 7:
                        raise ProjectAuthoringCommandError("invalid_recurrence_schedule", "Cron schedule requires a 5-7 field expr", 400)
                elif kind == "every":
                    try:
                        every_ms = int(schedule.get("everyMs") or 0)
                    except (TypeError, ValueError):
                        every_ms = 0
                    if every_ms < 60000:
                        raise ProjectAuthoringCommandError("invalid_recurrence_schedule", "Recurring schedule everyMs must be at least 60000", 400)
                else:
                    raise ProjectAuthoringCommandError("invalid_recurrence_schedule", "Project recurrence schedule kind must be cron or every", 400)
            recurrence["enabled"] = True
            recurrence["updatedAt"] = now
            project["recurrence"] = recurrence
            project["projectType"] = "recurring"
            return
        raise ProjectAuthoringCommandError(
            "unsupported_maintenance_operation", "Maintenance operation is not supported", 400,
        )

    @staticmethod
    def _apply_allowed_changes(target: dict[str, Any], changes: Mapping[str, Any], allowed: set[str]) -> None:
        unknown = set(changes) - allowed
        if unknown:
            raise ProjectAuthoringCommandError(
                "protected_maintenance_field",
                f"Maintenance fields are not allowed: {', '.join(sorted(unknown))}",
                400,
            )
        for key, value in changes.items():
            target[key] = copy.deepcopy(value)

    @staticmethod
    def _maintenance_task(project: Mapping[str, Any], task_id: str) -> dict[str, Any]:
        task = next((item for item in project.get("tasks", []) if item.get("id") == task_id), None)
        if not isinstance(task, dict):
            raise ProjectAuthoringCommandError("task_not_found", "Task not found", 404)
        return task

    def _validate_maintenance_task_actors(self, task: Mapping[str, Any]) -> dict[str, Any]:
        try:
            return validate_task_actor_references(
                task,
                lookup_agent=self.lookup_agent,
                is_excluded_agent=self.is_excluded_agent,
            )
        except ActorReferenceError as exc:
            raise ProjectAuthoringCommandError(exc.code, exc.message, 400) from exc

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
