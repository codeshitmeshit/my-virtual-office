"""Durable, bounded state for routing Codex approvals through Feishu."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .provider_events import sanitize_payload


SCHEMA = "vo.codex-feishu-approval-routes/v1"
ACTIVE_STATES = frozenset({"pending", "delivering", "delivered", "resolving"})
TERMINAL_STATES = frozenset({"resolved", "failed", "expired"})
DECISIONS = frozenset({"approve", "cancel"})


@dataclass(frozen=True)
class RouteClaim:
    claimed: bool
    replay: bool
    busy: bool
    stale: bool
    unauthorized: bool
    token: str
    record: dict[str, Any] | None
    outcome: dict[str, Any] | None


class CodexFeishuApprovalRouteStore:
    """Atomic JSON repository with a durable decision fence.

    The store deliberately persists a claim before a provider continuation is
    called. A resolving claim loaded after process restart is expired instead
    of retried, preserving the at-most-once safety boundary.
    """

    def __init__(
        self,
        path: str,
        *,
        max_records: int = 2000,
        retention_ms: int = 24 * 60 * 60 * 1000,
        claim_lease_ms: int = 30_000,
        max_deliveries: int = 8,
        clock_ms: Callable[[], int] | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        self.path = os.path.abspath(path)
        self.max_records = max(1, int(max_records))
        self.retention_ms = max(1, int(retention_ms))
        self.claim_lease_ms = max(1, int(claim_lease_ms))
        self.max_deliveries = max(1, int(max_deliveries))
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self._token_factory = token_factory or (lambda: uuid.uuid4().hex)
        self._lock = threading.RLock()
        self._records: dict[str, dict[str, Any]] = {}
        self._load_and_reconcile()

    @staticmethod
    def _public(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(record, Mapping):
            return None
        return copy.deepcopy({key: value for key, value in record.items() if key != "claimToken"})

    @staticmethod
    def _bounded(value: Mapping[str, Any] | None) -> dict[str, Any]:
        cleaned = sanitize_payload(dict(value or {}))
        return cleaned if isinstance(cleaned, dict) else {}

    @staticmethod
    def _route_id(record: Mapping[str, Any]) -> str:
        return str(record.get("routeId") or record.get("route_id") or record.get("id") or "").strip()[:240]

    @staticmethod
    def _actor_ids(record: Mapping[str, Any]) -> set[str]:
        actor = record.get("actorIds") if isinstance(record.get("actorIds"), Mapping) else {}
        return {str(value).strip() for value in actor.values() if str(value or "").strip()}

    def register(self, record: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
        cleaned = self._bounded(record)
        route_id = self._route_id(cleaned)
        approval_id = str(cleaned.get("approvalId") or cleaned.get("approval_id") or "").strip()[:240]
        if not route_id or not approval_id:
            raise ValueError("routeId and approvalId are required")
        now = self._clock_ms()
        with self._lock:
            self._prune_locked(now)
            existing = self._records.get(route_id)
            if existing:
                if str(existing.get("approvalId") or "") != approval_id:
                    raise ValueError("routeId is already linked to another approval")
                return self._public(existing) or {}, False
            self._make_capacity_locked(now)
            stored = {
                **cleaned,
                "id": route_id,
                "routeId": route_id,
                "approvalId": approval_id,
                "status": "pending",
                "decision": "",
                "claimToken": "",
                "claimExpiresAt": 0,
                "outcome": None,
                "deliveries": [],
                "createdAt": int(cleaned.get("createdAt") or now),
                "updatedAt": now,
                "expiresAt": int(cleaned.get("expiresAt") or now + self.retention_ms),
            }
            self._records[route_id] = stored
            self._write_locked(now)
            return self._public(stored) or {}, True

    def get(self, route_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._prune_and_write_locked(self._clock_ms())
            return self._public(self._records.get(str(route_id or "").strip()))

    def begin_delivery(self, route_id: str) -> dict[str, Any] | None:
        now = self._clock_ms()
        with self._lock:
            current = self._records.get(str(route_id or "").strip())
            if not current or current.get("status") not in {"pending", "delivering"}:
                return self._public(current)
            current.update({"status": "delivering", "updatedAt": now})
            self._write_locked(now)
            return self._public(current)

    def record_delivery(self, route_id: str, delivery: Mapping[str, Any]) -> dict[str, Any] | None:
        cleaned = self._bounded(delivery)
        allowed = {
            "attemptId", "application", "channel", "messageId", "receiveIdType",
            "status", "ok", "ambiguous", "errorCategory", "createdAt", "updatedAt",
        }
        safe = {key: value for key, value in cleaned.items() if key in allowed}
        now = self._clock_ms()
        safe.setdefault("createdAt", now)
        with self._lock:
            current = self._records.get(str(route_id or "").strip())
            if not current or current.get("status") in TERMINAL_STATES:
                return self._public(current)
            deliveries = list(current.get("deliveries") or [])
            attempt_id = str(safe.get("attemptId") or "").strip()
            if attempt_id and any(str(item.get("attemptId") or "") == attempt_id for item in deliveries if isinstance(item, dict)):
                return self._public(current)
            deliveries.append(safe)
            current["deliveries"] = deliveries[-self.max_deliveries :]
            delivered = bool(safe.get("ok")) and str(safe.get("status") or "") in {"sent", "delivered"}
            current.update({"status": "delivered" if delivered else "delivering", "updatedAt": now})
            self._write_locked(now)
            return self._public(current)

    def claim(self, route_id: str, decision: str, actor_ids: Mapping[str, Any] | None = None) -> RouteClaim:
        route_id = str(route_id or "").strip()
        decision = str(decision or "").strip().lower()
        if decision not in DECISIONS:
            raise ValueError("unsupported Codex Feishu approval decision")
        now = self._clock_ms()
        with self._lock:
            self._prune_locked(now)
            current = self._records.get(route_id)
            if not current:
                return RouteClaim(False, False, False, True, False, "", None, None)
            trusted_actors = self._actor_ids(current)
            presented = {str(value).strip() for value in (actor_ids or {}).values() if str(value or "").strip()}
            if not trusted_actors or not presented or trusted_actors.isdisjoint(presented):
                return RouteClaim(False, False, False, False, True, "", self._public(current), None)
            status = str(current.get("status") or "")
            if status == "resolved":
                return RouteClaim(False, True, False, False, False, "", self._public(current), copy.deepcopy(current.get("outcome")))
            if status in {"failed", "expired"}:
                return RouteClaim(False, False, False, True, False, "", self._public(current), copy.deepcopy(current.get("outcome")))
            if status == "resolving":
                return RouteClaim(False, False, True, False, False, "", self._public(current), None)
            token = self._token_factory()
            current.update({
                "status": "resolving",
                "decision": decision,
                "claimToken": token,
                "claimExpiresAt": now + self.claim_lease_ms,
                "updatedAt": now,
            })
            self._write_locked(now)
            return RouteClaim(True, False, False, False, False, token, self._public(current), None)

    def commit(self, route_id: str, token: str, outcome: Mapping[str, Any]) -> RouteClaim:
        route_id = str(route_id or "").strip()
        now = self._clock_ms()
        cleaned = self._bounded(outcome)
        with self._lock:
            current = self._records.get(route_id)
            if not current:
                return RouteClaim(False, False, False, True, False, "", None, None)
            if current.get("status") == "resolved":
                return RouteClaim(False, True, False, False, False, "", self._public(current), copy.deepcopy(current.get("outcome")))
            if current.get("status") != "resolving" or not token or current.get("claimToken") != token:
                return RouteClaim(False, False, current.get("status") == "resolving", current.get("status") in TERMINAL_STATES, False, "", self._public(current), copy.deepcopy(current.get("outcome")))
            current.update({
                "status": "resolved",
                "claimToken": "",
                "claimExpiresAt": 0,
                "outcome": cleaned,
                "resolvedAt": now,
                "updatedAt": now,
            })
            self._write_locked(now)
            return RouteClaim(True, False, False, False, False, "", self._public(current), copy.deepcopy(cleaned))

    def fail(self, route_id: str, outcome: Mapping[str, Any], *, status: str = "failed") -> dict[str, Any] | None:
        if status not in {"failed", "expired"}:
            raise ValueError("terminal route status must be failed or expired")
        now = self._clock_ms()
        with self._lock:
            current = self._records.get(str(route_id or "").strip())
            if not current or current.get("status") == "resolved":
                return self._public(current)
            if current.get("status") == "resolving":
                return self._public(current)
            current.update({
                "status": status,
                "claimToken": "",
                "claimExpiresAt": 0,
                "outcome": self._bounded(outcome),
                "resolvedAt": now,
                "updatedAt": now,
            })
            self._write_locked(now)
            return self._public(current)

    def reconcile_startup(self) -> int:
        """Expire uncertain in-flight decisions without retrying the provider."""
        now = self._clock_ms()
        changed = 0
        with self._lock:
            for current in self._records.values():
                if current.get("status") != "resolving":
                    continue
                current.update({
                    "status": "expired",
                    "claimToken": "",
                    "claimExpiresAt": 0,
                    "outcome": {"ok": False, "status": "resolved_unknown", "reason": "startup_reconciliation"},
                    "resolvedAt": now,
                    "updatedAt": now,
                })
                changed += 1
            changed += self._prune_locked(now)
            if changed:
                self._write_locked(now)
        return changed

    def stats(self) -> dict[str, int]:
        with self._lock:
            counts = {state: 0 for state in (*ACTIVE_STATES, *TERMINAL_STATES)}
            for record in self._records.values():
                status = str(record.get("status") or "")
                counts[status] = counts.get(status, 0) + 1
            return {"records": len(self._records), **counts}

    def _load_and_reconcile(self) -> None:
        with self._lock:
            try:
                if os.path.islink(self.path):
                    raise OSError("approval route store must not be a symlink")
                with open(self.path, "r", encoding="utf-8") as stream:
                    payload = json.load(stream)
            except FileNotFoundError:
                return
            if not isinstance(payload, dict) or payload.get("schema") != SCHEMA or not isinstance(payload.get("records"), dict):
                raise ValueError("invalid Codex Feishu approval route store")
            self._records = {
                str(key): value for key, value in payload["records"].items()
                if isinstance(value, dict) and str(key) == self._route_id(value)
            }
        self.reconcile_startup()

    def _prune_and_write_locked(self, now: int) -> None:
        if self._prune_locked(now):
            self._write_locked(now)

    def _prune_locked(self, now: int) -> int:
        changed = 0
        for current in self._records.values():
            if current.get("status") in ACTIVE_STATES and int(current.get("expiresAt") or 0) <= now:
                current.update({
                    "status": "expired",
                    "claimToken": "",
                    "claimExpiresAt": 0,
                    "outcome": {"ok": False, "status": "expired", "reason": "retention_deadline"},
                    "resolvedAt": now,
                    "updatedAt": now,
                })
                changed += 1
        removable = [
            route_id for route_id, current in self._records.items()
            if current.get("status") in TERMINAL_STATES
            and now - int(current.get("resolvedAt") or current.get("updatedAt") or now) >= self.retention_ms
        ]
        for route_id in removable:
            self._records.pop(route_id, None)
            changed += 1
        return changed

    def _make_capacity_locked(self, now: int) -> None:
        if len(self._records) < self.max_records:
            return
        terminal = sorted(
            (
                (int(record.get("resolvedAt") or record.get("updatedAt") or now), route_id)
                for route_id, record in self._records.items()
                if record.get("status") in TERMINAL_STATES
            )
        )
        while len(self._records) >= self.max_records and terminal:
            _, route_id = terminal.pop(0)
            self._records.pop(route_id, None)
        if len(self._records) >= self.max_records:
            raise OverflowError("Codex Feishu approval route capacity is full")

    def _write_locked(self, now: int) -> None:
        directory = os.path.dirname(self.path)
        os.makedirs(directory, mode=0o700, exist_ok=True)
        if os.path.islink(self.path):
            raise OSError("approval route store must not be a symlink")
        fd, temporary = tempfile.mkstemp(prefix=".codex-feishu-approvals-", suffix=".tmp", dir=directory)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"schema": SCHEMA, "updatedAt": now, "records": self._records}, stream, ensure_ascii=False, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
