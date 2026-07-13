"""Provider-neutral bounded approval ownership and fenced resolution."""

from __future__ import annotations

import copy
import threading
import time
import uuid
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .provider_events import sanitize_payload


SUPPORTED_DECISIONS = frozenset({"once", "session", "always", "deny"})


@dataclass(frozen=True)
class TrustedApprovalContext:
    provider_kind: str
    agent_id: str
    profile: str = ""
    session_id: str = ""
    run_id: str = ""
    conversation_id: str = ""
    actor_id: str = ""
    source: str = "server"

    def normalized(self) -> "TrustedApprovalContext":
        provider = str(self.provider_kind or "").strip().lower()[:80]
        agent = str(self.agent_id or "").strip()[:160]
        if not provider or not agent:
            raise ValueError("trusted approval context requires provider_kind and agent_id")
        return TrustedApprovalContext(
            provider,
            agent,
            str(self.profile or "").strip()[:160],
            str(self.session_id or "").strip()[:240],
            str(self.run_id or "").strip()[:240],
            str(self.conversation_id or "").strip()[:240],
            str(self.actor_id or "").strip()[:160],
            str(self.source or "server").strip()[:80],
        )


@dataclass(frozen=True)
class ApprovalRegistration:
    record: dict[str, Any]
    created: bool
    notification_intent: dict[str, Any] | None


@dataclass(frozen=True)
class ApprovalClaim:
    claimed: bool
    replay: bool
    busy: bool
    decision_token: str
    record: dict[str, Any] | None
    outcome: dict[str, Any] | None


class ProviderApprovalService:
    def __init__(
        self,
        *,
        max_pending: int = 1000,
        max_per_scope: int = 100,
        max_resolved: int = 2000,
        retention_ms: int = 24 * 60 * 60 * 1000,
        claim_lease_ms: int = 30_000,
        clock_ms: Callable[[], int] | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        self.max_pending = max(1, int(max_pending))
        self.max_per_scope = max(1, int(max_per_scope))
        self.max_resolved = max(1, int(max_resolved))
        self.retention_ms = max(1, int(retention_ms))
        self.claim_lease_ms = max(1, int(claim_lease_ms))
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self._token_factory = token_factory or (lambda: uuid.uuid4().hex)
        self._lock = threading.RLock()
        self._records: dict[str, dict[str, Any]] = {}
        self._queues: dict[tuple[str, str, str, str], deque[str]] = {}
        self._pending_order: OrderedDict[str, None] = OrderedDict()
        self._resolved_order: OrderedDict[str, None] = OrderedDict()

    @staticmethod
    def _scope(context: TrustedApprovalContext) -> tuple[str, str, str, str]:
        return (context.provider_kind, context.agent_id, context.profile, context.session_id)

    @staticmethod
    def _public(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(record, Mapping):
            return None
        hidden = {"decisionToken", "claimExpiresAt", "notificationIntent"}
        return copy.deepcopy({key: value for key, value in record.items() if key not in hidden})

    @staticmethod
    def _bounded(record: Mapping[str, Any]) -> dict[str, Any]:
        cleaned = sanitize_payload(dict(record))
        return cleaned if isinstance(cleaned, dict) else {}

    def register(
        self,
        context: TrustedApprovalContext,
        record: Mapping[str, Any],
        *,
        notification_intent: Mapping[str, Any] | None = None,
    ) -> ApprovalRegistration:
        context = context.normalized()
        cleaned = self._bounded(record)
        approval_id = str(cleaned.get("approval_id") or cleaned.get("approvalId") or cleaned.get("id") or "").strip()[:240]
        if not approval_id:
            raise ValueError("approval id is required")
        now = self._clock_ms()
        with self._lock:
            self._prune_locked(now)
            existing = self._records.get(approval_id)
            if existing:
                if not self._matches(existing, context, include_run=True):
                    raise ValueError("approval id is already linked to another provider run")
                return ApprovalRegistration(self._public(existing) or {}, False, copy.deepcopy(existing.get("notificationIntent")))
            stored = {
                **cleaned,
                "id": approval_id,
                "approval_id": approval_id,
                "providerKind": context.provider_kind,
                "agentId": context.agent_id,
                "profile": context.profile,
                "session_id": context.session_id,
                "runId": context.run_id,
                "conversationId": context.conversation_id,
                "status": "pending",
                "queuedAt": int(cleaned.get("queuedAt") or now),
                "updatedAt": now,
                "decision": "",
                "decisionToken": "",
                "claimExpiresAt": 0,
                "outcome": None,
                "notificationIntent": self._bounded(notification_intent or {}) if notification_intent else None,
            }
            scope = self._scope(context)
            queue = self._queues.setdefault(scope, deque())
            while len(queue) >= self.max_per_scope:
                self._evict_pending_locked(queue[0], "scope_capacity")
            while len(self._pending_order) >= self.max_pending:
                self._evict_pending_locked(next(iter(self._pending_order)), "global_capacity")
            self._records[approval_id] = stored
            self._queues.setdefault(scope, deque()).append(approval_id)
            self._pending_order[approval_id] = None
            return ApprovalRegistration(self._public(stored) or {}, True, copy.deepcopy(stored.get("notificationIntent")))

    def update(self, approval_id: str, updates: Mapping[str, Any]) -> dict[str, Any] | None:
        cleaned = self._bounded(updates)
        immutable = {"id", "approval_id", "providerKind", "agentId", "profile", "session_id", "runId", "conversationId", "status", "decision", "outcome", "queuedAt", "resolvedAt"}
        cleaned = {key: value for key, value in cleaned.items() if key not in immutable}
        with self._lock:
            current = self._records.get(str(approval_id or ""))
            if not current:
                return None
            current.update(cleaned)
            current["updatedAt"] = self._clock_ms()
            return self._public(current)

    def pending(self, context: TrustedApprovalContext) -> dict[str, Any]:
        context = context.normalized()
        with self._lock:
            self._prune_locked(self._clock_ms())
            candidates = [
                self._scope(context),
                (context.provider_kind, context.agent_id, context.profile, ""),
            ]
            ids: list[str] = []
            for scope in dict.fromkeys(candidates):
                ids.extend(self._queues.get(scope, ()))
            if not ids:
                ids = [
                    approval_id for approval_id in self._pending_order
                    if self._matches(self._records.get(approval_id) or {}, context, include_run=False)
                ]
            records = [self._public(self._records.get(approval_id)) for approval_id in ids]
            records = [item for item in records if item and item.get("status") == "pending"]
            return {"ok": True, "pending": records[0] if records else None, "pending_count": len(records), "session_id": context.session_id or (records[0].get("session_id", "") if records else "")}

    def claim(self, context: TrustedApprovalContext, approval_id: str, decision: str) -> ApprovalClaim:
        context = context.normalized()
        approval_id = str(approval_id or "").strip()
        decision = str(decision or "").strip().lower()
        if decision not in SUPPORTED_DECISIONS:
            raise ValueError("unsupported approval decision")
        now = self._clock_ms()
        with self._lock:
            self._prune_locked(now)
            current = self._records.get(approval_id)
            if not current or not self._matches(current, context, include_run=True):
                return ApprovalClaim(False, False, False, "", None, None)
            if current.get("status") == "resolved":
                return ApprovalClaim(False, True, False, "", self._public(current), copy.deepcopy(current.get("outcome")))
            if current.get("status") == "resolving" and int(current.get("claimExpiresAt") or 0) > now:
                return ApprovalClaim(False, False, True, "", self._public(current), None)
            token = self._token_factory()
            current.update({"status": "resolving", "decision": decision, "decisionToken": token, "claimExpiresAt": now + self.claim_lease_ms, "updatedAt": now})
            return ApprovalClaim(True, False, False, token, self._public(current), None)

    def commit(self, approval_id: str, decision_token: str, outcome: Mapping[str, Any]) -> ApprovalClaim:
        cleaned = self._bounded(outcome)
        now = self._clock_ms()
        with self._lock:
            current = self._records.get(str(approval_id or ""))
            if not current or current.get("status") != "resolving" or current.get("decisionToken") != str(decision_token or ""):
                return ApprovalClaim(False, False, False, "", self._public(current), copy.deepcopy((current or {}).get("outcome")))
            current.update({"status": "resolved", "resolvedAt": now, "updatedAt": now, "outcome": cleaned, "claimExpiresAt": 0})
            self._remove_from_queue_locked(current)
            self._pending_order.pop(str(approval_id), None)
            self._resolved_order[str(approval_id)] = None
            while len(self._resolved_order) > self.max_resolved:
                old_id, _ = self._resolved_order.popitem(last=False)
                self._records.pop(old_id, None)
            return ApprovalClaim(True, False, False, "", self._public(current), copy.deepcopy(cleaned))

    def resolve(
        self,
        context: TrustedApprovalContext,
        approval_id: str,
        decision: str,
        continuation: Callable[[dict[str, Any], str], Mapping[str, Any]],
    ) -> ApprovalClaim:
        claim = self.claim(context, approval_id, decision)
        if not claim.claimed:
            return claim
        try:
            outcome = continuation(copy.deepcopy(claim.record or {}), decision)
            normalized = dict(outcome) if isinstance(outcome, Mapping) else {"ok": False, "status": "invalid_outcome", "error": "approval continuation returned an invalid result"}
        except BaseException as exc:
            normalized = {"ok": False, "status": "continuation_failed", "error": str(exc)[:512], "errorCategory": type(exc).__name__[:80]}
        return self.commit(approval_id, claim.decision_token, normalized)

    def cancel_run(self, context: TrustedApprovalContext, outcome: Mapping[str, Any] | None = None) -> int:
        """Fence pending approvals for a provider run after cancellation wins."""
        context = context.normalized()
        if not context.run_id:
            return 0
        with self._lock:
            approval_ids = [
                approval_id for approval_id in self._pending_order
                if str((self._records.get(approval_id) or {}).get("providerKind") or "") == context.provider_kind
                and str((self._records.get(approval_id) or {}).get("agentId") or "") == context.agent_id
                and (not context.profile or str((self._records.get(approval_id) or {}).get("profile") or "") == context.profile)
                and str((self._records.get(approval_id) or {}).get("runId") or "") == context.run_id
            ]
        resolved = 0
        compatible = dict(outcome or {"ok": True, "status": "cancelled"})
        compatible.setdefault("status", "cancelled")
        for approval_id in approval_ids:
            with self._lock:
                current = self._records.get(approval_id) or {}
                linked_context = TrustedApprovalContext(
                    context.provider_kind,
                    context.agent_id,
                    str(current.get("profile") or context.profile),
                    str(current.get("session_id") or ""),
                    context.run_id,
                    str(current.get("conversationId") or context.conversation_id),
                    context.actor_id,
                    context.source,
                )
            claim = self.claim(linked_context, approval_id, "deny")
            if claim.claimed and self.commit(approval_id, claim.decision_token, compatible).claimed:
                resolved += 1
        return resolved

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            self._queues.clear()
            self._pending_order.clear()
            self._resolved_order.clear()

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"pending": len(self._pending_order), "resolved": len(self._resolved_order), "records": len(self._records), "scopes": len(self._queues)}

    @staticmethod
    def _matches(record: Mapping[str, Any], context: TrustedApprovalContext, *, include_run: bool) -> bool:
        pairs = (
            ("providerKind", context.provider_kind),
            ("agentId", context.agent_id),
            ("profile", context.profile),
            ("session_id", context.session_id),
        )
        for key, expected in pairs:
            actual = str(record.get(key) or "")
            if include_run and key == "session_id" and actual and not expected:
                return False
            if expected and actual and actual != expected:
                return False
        if include_run:
            actual_run = str(record.get("runId") or "")
            if actual_run and not context.run_id:
                return False
            if context.run_id and actual_run != context.run_id:
                return False
        return True

    def _remove_from_queue_locked(self, record: Mapping[str, Any]) -> None:
        scope = (str(record.get("providerKind") or ""), str(record.get("agentId") or ""), str(record.get("profile") or ""), str(record.get("session_id") or ""))
        queue = self._queues.get(scope)
        if queue:
            try:
                queue.remove(str(record.get("id") or ""))
            except ValueError:
                pass
            if not queue:
                self._queues.pop(scope, None)

    def _evict_pending_locked(self, approval_id: str, reason: str) -> None:
        current = self._records.pop(str(approval_id or ""), None)
        self._pending_order.pop(str(approval_id or ""), None)
        if current:
            self._remove_from_queue_locked(current)

    def _prune_locked(self, now: int) -> None:
        for approval_id in list(self._resolved_order):
            current = self._records.get(approval_id)
            if not current or now - int(current.get("resolvedAt") or current.get("updatedAt") or 0) > self.retention_ms:
                self._resolved_order.pop(approval_id, None)
                self._records.pop(approval_id, None)
        for approval_id in list(self._pending_order):
            current = self._records.get(approval_id)
            if current and current.get("status") == "resolving" and int(current.get("claimExpiresAt") or 0) <= now:
                current.update({"status": "pending", "decisionToken": "", "claimExpiresAt": 0, "updatedAt": now})
