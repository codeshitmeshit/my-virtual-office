"""Corruption-safe root collection access for project authoring."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from services.project_authoring_config import (
    DEFAULT_CONFIG,
    ProjectAuthoringConfig,
    outbox_capacity_error,
    maintenance_capacity_error,
    pending_capacity_error,
)


REQUESTS_KEY = "projectAuthoringRequests"
IDEMPOTENCY_KEY = "projectAuthoringIdempotency"
GRANTS_KEY = "projectAuthoringGrants"
TEMPLATES_KEY = "projectTemplateVersions"
RECURRENCES_KEY = "projectRecurrences"
OUTBOX_KEY = "projectAuthoringOutbox"

MAP_COLLECTION_KEYS = (
    REQUESTS_KEY,
    IDEMPOTENCY_KEY,
    GRANTS_KEY,
    TEMPLATES_KEY,
    RECURRENCES_KEY,
)
TERMINAL_REQUEST_STATES = frozenset({"confirmed", "rejected", "expired"})
OPEN_REQUEST_STATES = frozenset({"pending", "materializing", "failed"})
SENSITIVE_KEYS = frozenset({
    "requestsecret",
    "requestsecrethash",
    "secrethash",
    "grantsecrethash",
    "managementtoken",
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _scrub_secrets(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _scrub_secrets(item)
            for key, item in value.items()
            if str(key).replace("_", "").lower() not in SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [_scrub_secrets(item) for item in value]
    return copy.deepcopy(value)


def management_request_view(request: Mapping[str, Any]) -> dict[str, Any]:
    """Return full review data without any credential or credential hash."""
    return _scrub_secrets(request)


def grant_public_view(grant: Mapping[str, Any]) -> dict[str, Any]:
    """Expose grant policy and lifecycle without its bearer-secret hash."""
    return _scrub_secrets(grant)


def agent_request_view(
    request: Mapping[str, Any],
    *,
    requesting_agent_id: str,
) -> dict[str, Any] | None:
    """Return only caller-owned status/result fields for an Agent endpoint."""
    if str(request.get("requestingAgentId") or "") != str(requesting_agent_id or ""):
        return None
    allowed = (
        "id", "requestId", "state", "revision", "createdAt", "updatedAt",
        "expiresAt", "terminalAt", "projectId", "code", "error", "result",
        "summary", "tombstone", "retention",
    )
    return _scrub_secrets({key: request[key] for key in allowed if key in request})


class ProjectAuthoringRootStore:
    """Serialize authoring root mutations through the repository commit lock."""

    def __init__(
        self,
        repository,
        *,
        config: ProjectAuthoringConfig = DEFAULT_CONFIG,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.repository = repository
        self.config = config
        self.clock = clock

    def snapshot(self) -> dict[str, Any]:
        captured: dict[str, Any] = {}

        def normalize(root: dict[str, Any]) -> None:
            self._repair_root(root)
            captured.update(copy.deepcopy(root))

        self.repository.update_root(normalize)
        return captured

    def update(self, mutator: Callable[[dict[str, Any]], Any]) -> Any:
        def apply(root: dict[str, Any]) -> Any:
            self._repair_root(root)
            result = mutator(root)
            self._repair_root(root)
            self._enforce_capacities(root)
            return result

        return self.repository.update_root(apply)

    def compact_terminal_requests(self, *, now: datetime | None = None) -> int:
        compacted_at = now or self.clock()
        cutoff = compacted_at - timedelta(days=self.config.terminal_retention_days)

        def compact(root: dict[str, Any]) -> int:
            changed = 0
            requests = root[REQUESTS_KEY]
            for request_id, request in list(requests.items()):
                if request.get("tombstone") is True:
                    continue
                state = str(request.get("state") or "")
                terminal_at = _parse_time(
                    request.get("terminalAt") or request.get("updatedAt") or request.get("createdAt")
                )
                if state not in TERMINAL_REQUEST_STATES or terminal_at is None or terminal_at > cutoff:
                    continue
                tombstone = {
                    "id": str(request.get("id") or request_id),
                    "requestId": str(request.get("requestId") or request_id),
                    "requestingAgentId": str(request.get("requestingAgentId") or ""),
                    "state": state,
                    "revision": int(request.get("revision") or 0),
                    "createdAt": request.get("createdAt"),
                    "updatedAt": request.get("updatedAt"),
                    "terminalAt": request.get("terminalAt") or request.get("updatedAt"),
                    "projectId": request.get("projectId"),
                    "code": request.get("code"),
                    "result": _scrub_secrets(request.get("result")),
                    "tombstone": True,
                    "retention": {
                        "terminalRetentionDays": self.config.terminal_retention_days,
                        "compactedAt": _iso(compacted_at),
                    },
                }
                requests[request_id] = {key: value for key, value in tombstone.items() if value is not None}
                changed += 1
            return changed

        return self.update(compact)

    def _repair_root(self, root: dict[str, Any]) -> None:
        for key in MAP_COLLECTION_KEYS:
            if not isinstance(root.get(key), dict):
                root[key] = {}
        if not isinstance(root.get(OUTBOX_KEY), list):
            root[OUTBOX_KEY] = []

        root[REQUESTS_KEY] = self._repair_record_map(
            root[REQUESTS_KEY], history_fields=("audit", "history"),
            history_limit=self.config.audit_history_limit,
        )
        root[GRANTS_KEY] = self._repair_record_map(
            root[GRANTS_KEY], history_fields=("audit",),
            history_limit=self.config.audit_history_limit,
        )
        for grant in root[GRANTS_KEY].values():
            maintenance = grant.get("maintenanceRequests")
            grant["maintenanceRequests"] = self._repair_record_map(
                maintenance if isinstance(maintenance, dict) else {},
                history_fields=("audit", "history"),
                history_limit=self.config.audit_history_limit,
            )
            idempotency = grant.get("maintenanceIdempotency")
            grant["maintenanceIdempotency"] = {
                str(key): str(value)
                for key, value in (idempotency.items() if isinstance(idempotency, dict) else [])
                if str(key).strip() and str(value).strip()
            }
            autonomous_idempotency = grant.get("autonomousIdempotency")
            grant["autonomousIdempotency"] = {
                str(key): copy.deepcopy(value)
                for key, value in (autonomous_idempotency.items() if isinstance(autonomous_idempotency, dict) else [])
                if str(key).strip() and isinstance(value, dict)
            }
        root[RECURRENCES_KEY] = self._repair_record_map(
            root[RECURRENCES_KEY], history_fields=("audit",),
            history_limit=self.config.audit_history_limit,
            occurrence_limit=self.config.recurrence_history_limit,
        )
        root[TEMPLATES_KEY] = self._repair_template_versions(root[TEMPLATES_KEY])
        root[IDEMPOTENCY_KEY] = {
            str(key): copy.deepcopy(value)
            for key, value in root[IDEMPOTENCY_KEY].items()
            if str(key).strip() and isinstance(value, (str, dict))
        }
        root[OUTBOX_KEY] = [
            copy.deepcopy(item) for item in root[OUTBOX_KEY] if isinstance(item, dict)
        ]

    def _enforce_capacities(self, root: dict[str, Any]) -> None:
        open_requests = [
            request for request in root[REQUESTS_KEY].values()
            if str(request.get("state") or "pending") in OPEN_REQUEST_STATES
        ]
        if len(open_requests) > self.config.max_pending_global:
            raise pending_capacity_error("global")
        per_agent: dict[str, int] = {}
        for request in open_requests:
            agent_id = str(request.get("requestingAgentId") or "")
            per_agent[agent_id] = per_agent.get(agent_id, 0) + 1
        if any(count > self.config.max_pending_per_agent for count in per_agent.values()):
            raise pending_capacity_error("agent")
        if len(root[OUTBOX_KEY]) > self.config.outbox_capacity:
            raise outbox_capacity_error()
        for grant in root[GRANTS_KEY].values():
            requests = grant.get("maintenanceRequests") or {}
            open_count = sum(
                1 for request in requests.values()
                if str(request.get("state") or "pending") in {"pending", "applying", "failed"}
            )
            if open_count > self.config.max_maintenance_requests_per_project:
                raise maintenance_capacity_error()

    def _repair_record_map(
        self,
        records: Mapping[Any, Any],
        *,
        history_fields: tuple[str, ...],
        history_limit: int,
        occurrence_limit: int | None = None,
    ) -> dict[str, dict[str, Any]]:
        repaired: dict[str, dict[str, Any]] = {}
        for key, value in records.items():
            record_id = str(key).strip()
            if not record_id or not isinstance(value, dict):
                continue
            record = copy.deepcopy(value)
            record.setdefault("id", record_id)
            for field in history_fields:
                history = record.get(field)
                record[field] = (
                    [copy.deepcopy(item) for item in history if isinstance(item, dict)][-history_limit:]
                    if isinstance(history, list) else []
                )
            if occurrence_limit is not None:
                history = record.get("occurrenceHistory")
                record["occurrenceHistory"] = (
                    [copy.deepcopy(item) for item in history if isinstance(item, dict)][-occurrence_limit:]
                    if isinstance(history, list) else []
                )
            repaired[record_id] = record
        return repaired

    @staticmethod
    def _repair_template_versions(templates: Mapping[Any, Any]) -> dict[str, list[dict[str, Any]]]:
        repaired: dict[str, list[dict[str, Any]]] = {}
        for key, versions in templates.items():
            template_id = str(key).strip()
            if not template_id or not isinstance(versions, list):
                continue
            valid = [copy.deepcopy(version) for version in versions if isinstance(version, dict)]
            if valid:
                repaired[template_id] = valid
        return repaired
