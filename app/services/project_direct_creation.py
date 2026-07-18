"""Atomic, conversation-confirmed project creation without persisted draft state."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from services.project_authoring_audit import sanitize_audit_text
from services.project_authoring_config import feature_disabled_error
from services.project_authoring_security import generate_request_secret, hash_request_secret
from services.project_authoring_store import GRANTS_KEY, IDEMPOTENCY_KEY, grant_public_view
from services.project_authoring_validation import validate_idempotency_key, validate_project_draft


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass
class DirectProjectCreationError(RuntimeError):
    code: str
    message: str
    status: int

    def __str__(self) -> str:
        return self.message

    def as_dict(self) -> dict[str, Any]:
        return {"ok": False, "code": self.code, "error": self.message, "_status": self.status}


@dataclass(frozen=True)
class DirectProjectCreationPorts:
    store: Any
    lookup_agent: Callable[[str], Any]
    is_excluded_agent: Callable[[str], bool]
    submission_enabled: Callable[[], bool]
    recurrence_enabled: Callable[[], bool]
    materialize_template: Callable[..., dict[str, Any]]
    materialize_recurrence: Callable[..., dict[str, Any]]
    build_project: Callable[..., dict[str, Any]]
    audit: Callable[..., dict[str, Any]]
    cleanup_workspace: Callable[[Mapping[str, Any], Callable | None], None]
    clock: Callable[[], datetime]
    new_id: Callable[[], str]
    new_secret: Callable[[], str] = generate_request_secret
    hash_secret: Callable[[str], str] = hash_request_secret


class DirectProjectCreationService:
    """Validate, prepare, and atomically commit one direct project creation."""

    def __init__(self, ports: DirectProjectCreationPorts) -> None:
        self.ports = ports

    def create(
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
        if not self.ports.submission_enabled():
            raise feature_disabled_error("authoring")
        agent_id = str(requesting_agent_id or "").strip()
        self._validate_requesting_agent(agent_id)
        key = validate_idempotency_key(idempotency_key)
        summary_digest = self._validate_confirmation(confirmation)
        normalized = validate_project_draft(
            project,
            idempotency_key=key,
            lookup_agent=self.ports.lookup_agent,
            is_excluded_agent=self.ports.is_excluded_agent,
            config=self.ports.store.config,
            reviewer_assignment_confirmed=True,
        )
        if (
            isinstance(normalized.get("recurrence"), Mapping)
            and normalized["recurrence"].get("enabled") is True
            and not self.ports.recurrence_enabled()
        ):
            raise feature_disabled_error("recurrence")
        digest_project = copy.deepcopy(normalized)
        digest_project.pop("validatedAt", None)
        payload_digest = _canonical_digest({
            "confirmationSummaryDigest": summary_digest,
            "project": digest_project,
        })
        record_key = f"direct-create:{agent_id}:{key}"
        existing = self._idempotent_result(
            self.ports.store.snapshot(), record_key=record_key, payload_digest=payload_digest,
        )
        if existing is not None:
            return existing

        creation_id = self.ports.new_id()
        project_id = f"project-{creation_id}"
        grant_secret = self.ports.new_secret()
        grant_secret_hash = self.ports.hash_secret(grant_secret)
        workspace: dict[str, Any] = {"ok": True, "managed": False, "created": False}
        try:
            if prepare_workspace is not None:
                prepared = prepare_workspace(normalized, creation_id, key)
                workspace = dict(prepared) if isinstance(prepared, Mapping) else {
                    "ok": False,
                    "error": "Workspace preparation returned an invalid result",
                }
            if not workspace.get("ok"):
                raise DirectProjectCreationError(
                    "workspace_preparation_failed",
                    sanitize_audit_text(workspace.get("error") or "Workspace preparation failed", limit=1000),
                    409,
                )
            result = self.ports.store.update(lambda root: self._commit(
                root,
                record_key=record_key,
                payload_digest=payload_digest,
                creation_id=creation_id,
                project_id=project_id,
                requesting_agent_id=agent_id,
                idempotency_key=key,
                summary_digest=summary_digest,
                approved=normalized,
                source=source,
                workspace=workspace,
                grant_secret_hash=grant_secret_hash,
            ))
            if result.get("created") is not True:
                self.ports.cleanup_workspace(workspace, cleanup_workspace)
                return result
            result["projectGrantSecret"] = grant_secret
            return result
        except Exception:
            self.ports.cleanup_workspace(workspace, cleanup_workspace)
            raise

    def _validate_requesting_agent(self, agent_id: str) -> None:
        if not agent_id or self.ports.lookup_agent(agent_id) is None:
            raise DirectProjectCreationError(
                "requesting_agent_not_found", "Requesting Agent was not found", 400,
            )
        if self.ports.is_excluded_agent(agent_id):
            raise DirectProjectCreationError(
                "requesting_agent_not_assignable", "Requesting Agent is not assignable", 400,
            )

    @staticmethod
    def _validate_confirmation(confirmation: Any) -> str:
        supplied = confirmation if isinstance(confirmation, Mapping) else {}
        if supplied.get("confirmed") is not True:
            raise DirectProjectCreationError(
                "project_confirmation_required",
                "Explicit conversational project confirmation is required",
                400,
            )
        digest = str(supplied.get("summaryDigest") or "").strip().lower()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise DirectProjectCreationError(
                "invalid_confirmation_summary_digest",
                "confirmation.summaryDigest must be a SHA-256 hex digest",
                400,
            )
        return digest

    def _idempotent_result(
        self,
        root: Mapping[str, Any],
        *,
        record_key: str,
        payload_digest: str,
    ) -> dict[str, Any] | None:
        record = root.get(IDEMPOTENCY_KEY, {}).get(record_key)
        if record is None:
            return None
        if not isinstance(record, Mapping) or record.get("payloadDigest") != payload_digest:
            raise DirectProjectCreationError(
                "project_creation_idempotency_conflict",
                "The project creation idempotency key was already used for different content",
                409,
            )
        project_id = str(record.get("projectId") or "")
        created = next(
            (
                item for item in root.get("projects", [])
                if isinstance(item, Mapping) and str(item.get("id") or "") == project_id
            ),
            None,
        )
        grant = root.get(GRANTS_KEY, {}).get(project_id)
        if created is None or not isinstance(grant, Mapping):
            raise DirectProjectCreationError(
                "created_project_result_missing",
                "The idempotent project creation result is incomplete",
                409,
            )
        return {
            "ok": True,
            "created": False,
            "project": copy.deepcopy(dict(created)),
            "grant": grant_public_view(grant),
        }

    def _commit(
        self,
        root: dict[str, Any],
        *,
        record_key: str,
        payload_digest: str,
        creation_id: str,
        project_id: str,
        requesting_agent_id: str,
        idempotency_key: str,
        summary_digest: str,
        approved: Mapping[str, Any],
        source: Mapping[str, Any] | None,
        workspace: Mapping[str, Any],
        grant_secret_hash: str,
    ) -> dict[str, Any]:
        existing = self._idempotent_result(
            root, record_key=record_key, payload_digest=payload_digest,
        )
        if existing is not None:
            return existing
        if any(str(item.get("id") or "") == project_id for item in root.get("projects", [])):
            raise DirectProjectCreationError(
                "project_id_conflict", "Created project id already exists", 409,
            )
        now = self.ports.clock().astimezone(timezone.utc).isoformat()
        direct_source = {"id": creation_id, "requestingAgentId": requesting_agent_id}
        template_ref = self.ports.materialize_template(
            root, creation_id, approved, now, requesting_agent_id,
        )
        recurrence_ref = self.ports.materialize_recurrence(
            root, creation_id, direct_source, approved, template_ref, now, requesting_agent_id,
        )
        created = self.ports.build_project(
            project_id=project_id,
            request=direct_source,
            approved=approved,
            workspace=workspace,
            template_ref=template_ref,
            recurrence_ref=recurrence_ref,
            now=now,
        )
        created.pop("authoringRequestId", None)
        created["authoringSource"] = {
            "kind": "conversation_confirmed_agent",
            "creationId": creation_id,
            "confirmationSummaryDigest": summary_digest,
            "surface": sanitize_audit_text((source or {}).get("surface") or "agent_http", limit=80),
        }
        created["activity"] = [{
            "type": "project_authored",
            "by": requesting_agent_id,
            "at": now,
            "detail": "Created after conversational confirmation",
        }]
        root.setdefault("projects", []).append(created)
        maintenance_mode = str(approved.get("agentMaintenanceMode") or "strict_confirmation")
        allowed_operations = ["status", "maintenance_request"]
        if maintenance_mode == "autonomous":
            allowed_operations.append("routine_task_update")
        grant = {
            "id": f"grant-{project_id}",
            "projectId": project_id,
            "creationId": creation_id,
            "requestingAgentId": requesting_agent_id,
            "secretHash": grant_secret_hash,
            "version": 1,
            "state": "active",
            "maintenanceMode": maintenance_mode,
            "allowedOperations": allowed_operations,
            "createdAt": now,
            "updatedAt": now,
            "audit": [self.ports.audit(
                "grant_activated", requesting_agent_id, "agent", now, "accepted",
                projectId=project_id,
            )],
        }
        root[GRANTS_KEY][project_id] = grant
        root[IDEMPOTENCY_KEY][record_key] = {
            "kind": "direct_project_creation",
            "creationId": creation_id,
            "requestingAgentId": requesting_agent_id,
            "idempotencyKey": idempotency_key,
            "payloadDigest": payload_digest,
            "projectId": project_id,
            "createdAt": now,
        }
        return {
            "ok": True,
            "created": True,
            "project": copy.deepcopy(created),
            "grant": grant_public_view(grant),
        }
