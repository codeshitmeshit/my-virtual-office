"""Durable, bounded state for routing Codex approvals through Feishu."""

from __future__ import annotations

import copy
import concurrent.futures
import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .provider_events import sanitize_payload

try:  # app/server.py imports services as a top-level package.
    from feishu_notifications import redact_sensitive
except ImportError:  # Tests may import through app.services.
    from app.feishu_notifications import redact_sensitive


SCHEMA = "vo.codex-feishu-approval-routes/v1"
ACTIVE_STATES = frozenset({"pending", "delivering", "delivered", "resolving"})
TERMINAL_STATES = frozenset({"resolved", "failed", "expired"})
DECISIONS = frozenset({"approve", "cancel"})
ELIGIBLE_KINDS = frozenset({"command", "file_change", "permissions"})
KIND_LABELS = {
    "command": "命令执行",
    "file_change": "文件变更",
    "permissions": "权限申请",
}


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
        return self._claim(route_id, decision, actor_ids=actor_ids, trusted_system=False)

    def claim_system(self, route_id: str, decision: str = "cancel") -> RouteClaim:
        """Claim a route for a fail-closed server decision, bypassing user identity only."""
        return self._claim(route_id, decision, actor_ids=None, trusted_system=True)

    def _claim(
        self,
        route_id: str,
        decision: str,
        *,
        actor_ids: Mapping[str, Any] | None,
        trusted_system: bool,
    ) -> RouteClaim:
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
            if not trusted_system and (not trusted_actors or not presented or trusted_actors.isdisjoint(presented)):
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

    def commit(
        self,
        route_id: str,
        token: str,
        outcome: Mapping[str, Any],
        *,
        terminal_status: str = "resolved",
    ) -> RouteClaim:
        if terminal_status not in {"resolved", "failed"}:
            raise ValueError("claim commit status must be resolved or failed")
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
                "status": terminal_status,
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


class BoundedApprovalDeliveryExecutor:
    """Bounded delivery pool with a hard deadline and one failure closure."""

    def __init__(self, *, max_workers: int = 2, max_queue: int = 16, deadline_sec: float = 12.0) -> None:
        self.max_workers = max(1, min(int(max_workers), 16))
        self.max_queue = max(0, min(int(max_queue), 256))
        self.deadline_sec = max(0.05, min(float(deadline_sec), 60.0))
        self._slots = threading.BoundedSemaphore(self.max_workers + self.max_queue)
        self._pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="codex-feishu-approval",
        )
        self._lock = threading.Lock()
        self._closed = False

    def submit(
        self,
        delivery: Callable[[], Mapping[str, Any]],
        on_failure: Callable[[str, Mapping[str, Any] | None], None],
    ) -> bool:
        with self._lock:
            if self._closed:
                return False
        if not self._slots.acquire(blocking=False):
            return False
        outcome_lock = threading.Lock()
        finished = {"value": False}

        def fail_once(reason: str, result: Mapping[str, Any] | None = None) -> None:
            with outcome_lock:
                if finished["value"]:
                    return
                finished["value"] = True
            on_failure(reason, result)

        timer = threading.Timer(self.deadline_sec, fail_once, args=("deadline", None))
        timer.daemon = True
        timer.start()

        def run() -> None:
            try:
                result = delivery()
                if not isinstance(result, Mapping) or not result.get("ok"):
                    fail_once("undeliverable", result if isinstance(result, Mapping) else None)
                else:
                    with outcome_lock:
                        finished["value"] = True
            except Exception as exc:
                fail_once("delivery_error", {"errorCategory": type(exc).__name__[:80]})
            finally:
                timer.cancel()
                self._slots.release()

        try:
            self._pool.submit(run)
        except RuntimeError:
            timer.cancel()
            self._slots.release()
            return False
        return True

    def shutdown(self, *, wait: bool = False) -> None:
        with self._lock:
            self._closed = True
        self._pool.shutdown(wait=wait, cancel_futures=True)


class CodexFeishuApprovalCoordinator:
    """Build and route Codex approval cards through the common notifier."""

    def __init__(
        self,
        store: CodexFeishuApprovalRouteStore,
        *,
        send_notification: Callable[..., Mapping[str, Any]],
        status_dir: str = "",
        attempt_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self._send_notification = send_notification
        self.status_dir = str(status_dir or "")
        self._attempt_id_factory = attempt_id_factory or (lambda: uuid.uuid4().hex)

    @staticmethod
    def freeze_origin(context: Mapping[str, Any]) -> dict[str, Any]:
        context = context if isinstance(context, Mapping) else {}
        surface = str(context.get("sourceSurface") or "").strip().lower()
        if str(context.get("sourceApp") or "").strip().lower() != "feishu" or surface not in {"feishu-dm", "feishu-group"}:
            raise ValueError("Codex approval is not from a trusted Feishu turn")
        actor = context.get("sourceActor") if isinstance(context.get("sourceActor"), Mapping) else {}
        actor_ids = {
            key: str(actor.get(key) or "").strip()[:256]
            for key in ("openId", "userId", "unionId")
            if str(actor.get(key) or "").strip()
        }
        chat_id = str(context.get("feishuChatId") or "").strip()[:300]
        source_message_id = str(context.get("sourceMessageId") or "").strip()[:300]
        if not actor_ids or not chat_id or not source_message_id:
            raise ValueError("trusted Feishu origin requires actor, chat, and source message identity")
        return {
            "sourceApp": "feishu",
            "sourceSurface": surface,
            "sourceMessageId": source_message_id,
            "feishuChatId": chat_id,
            "actorIds": actor_ids,
            "actorName": str(actor.get("name") or context.get("fromDisplayName") or "Feishu User").strip()[:160],
        }

    @staticmethod
    def _summary(approval: Mapping[str, Any]) -> str:
        raw = str(
            approval.get("command")
            or approval.get("description")
            or approval.get("title")
            or "Codex 请求执行受保护操作"
        ).strip()
        cleaned = sanitize_payload({"summary": redact_sensitive(raw[:1800])}).get("summary")
        return str(cleaned or "Codex 请求执行受保护操作")[:1200]

    @staticmethod
    def _kind(approval: Mapping[str, Any]) -> str:
        raw = str(approval.get("kind") or "").strip().lower().replace("-", "_")
        aliases = {"filechange": "file_change", "file": "file_change", "permission": "permissions"}
        return aliases.get(raw, raw)

    @staticmethod
    def _route_id(approval: Mapping[str, Any], context: Mapping[str, Any], origin: Mapping[str, Any]) -> str:
        approval_id = str(approval.get("approval_id") or approval.get("approvalId") or approval.get("id") or "").strip()
        seed = "|".join((
            str(context.get("agentId") or approval.get("agentId") or ""),
            str(context.get("conversationId") or ""),
            str(approval.get("threadId") or approval.get("session_id") or ""),
            str(approval.get("turnId") or approval.get("runId") or ""),
            approval_id,
            str(origin.get("sourceMessageId") or ""),
        ))
        return "codex-feishu-approval-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]

    @classmethod
    def intent_for(cls, record: Mapping[str, Any], *, state: str = "pending", include_actions: bool = True) -> dict[str, Any]:
        kind = str(record.get("kind") or "")
        route_id = str(record.get("routeId") or "")
        actions = []
        if include_actions:
            actions = [
                {
                    "category": "confirm",
                    "text": "允许一次",
                    "value": {"action": "codex_approval_once", "route_id": route_id, "version": 1},
                },
                {
                    "category": "cancel",
                    "text": "取消",
                    "value": {"action": "codex_approval_cancel", "route_id": route_id, "version": 1},
                },
            ]
        return {
            "id": route_id,
            "type": "application_form",
            "title": "Codex 操作待审批",
            "summary": str(record.get("summary") or "Codex 请求执行受保护操作")[:1200],
            "state": state,
            "multi_participant": False,
            "related": {
                "type": "codex_approval",
                "id": route_id,
                "title": KIND_LABELS.get(kind, "受保护操作"),
            },
            "details": [
                ("Agent", str(record.get("agentId") or "Codex")[:160]),
                ("类型", KIND_LABELS.get(kind, kind or "受保护操作")),
            ],
            "actions": actions,
            "target": "feishu-codex-approval",
        }

    def register(self, approval: Mapping[str, Any], context: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
        approval = approval if isinstance(approval, Mapping) else {}
        context = context if isinstance(context, Mapping) else {}
        kind = self._kind(approval)
        if kind not in ELIGIBLE_KINDS:
            raise ValueError(f"unsupported Codex approval kind: {kind or '<empty>'}")
        approval_id = str(approval.get("approval_id") or approval.get("approvalId") or approval.get("id") or "").strip()[:240]
        if not approval_id:
            raise ValueError("Codex approval identity is required")
        origin = self.freeze_origin(context)
        route_id = self._route_id(approval, context, origin)
        record = {
            "routeId": route_id,
            "approvalId": approval_id,
            "providerKind": "codex",
            "profile": str(approval.get("profile") or context.get("profile") or "")[:160],
            "agentId": str(context.get("agentId") or approval.get("agentId") or "codex-local")[:160],
            "conversationId": str(context.get("conversationId") or "")[:240],
            "threadId": str(approval.get("threadId") or approval.get("session_id") or "")[:240],
            "turnId": str(approval.get("turnId") or approval.get("runId") or "")[:240],
            "kind": kind,
            "summary": self._summary(approval),
            **origin,
        }
        record["intent"] = self.intent_for(record)
        return self.store.register(record)

    @staticmethod
    def _notification_target(record: Mapping[str, Any], notification_config: Mapping[str, Any], chat_config: Mapping[str, Any]) -> tuple[str, str]:
        actor = record.get("actorIds") if isinstance(record.get("actorIds"), Mapping) else {}
        if actor.get("unionId"):
            return "union_id", str(actor["unionId"])
        if actor.get("userId"):
            return "user_id", str(actor["userId"])
        same_identity_domain = (
            str(notification_config.get("appId") or "").strip()
            and str(notification_config.get("appId") or "").strip() == str(chat_config.get("appId") or "").strip()
        )
        if same_identity_domain and actor.get("openId"):
            return "open_id", str(actor["openId"])
        return "", ""

    @staticmethod
    def _configured(config: Mapping[str, Any]) -> bool:
        return bool(config.get("appId") and config.get("appSecret"))

    def _attempt(
        self,
        record: Mapping[str, Any],
        *,
        application: str,
        app_config: Mapping[str, Any],
        receive_id_type: str,
        receive_id: str,
    ) -> dict[str, Any]:
        attempt_id = self._attempt_id_factory()
        result = dict(self._send_notification(
            record.get("intent") or self.intent_for(record),
            webhook_url=None,
            app_config={
                "appId": app_config.get("appId") or "",
                "appSecret": app_config.get("appSecret") or "",
                "receiveIdType": receive_id_type,
                "receiveId": receive_id,
            },
            status_dir=self.status_dir or None,
        ))
        sent = bool(result.get("ok")) and result.get("status") == "sent" and bool(result.get("messageId"))
        ambiguous = str(result.get("status") or "") in {"network_error", "timeout", "send_timeout"}
        delivery = {
            "attemptId": attempt_id,
            "application": application,
            "channel": result.get("channel") or "app",
            "messageId": result.get("messageId") or "",
            "receiveIdType": receive_id_type,
            "status": "sent" if sent else str(result.get("status") or "failed"),
            "ok": sent,
            "ambiguous": ambiguous,
            "errorCategory": result.get("errorCategory") or result.get("code") or "",
        }
        self.store.record_delivery(str(record.get("routeId") or ""), delivery)
        return {"application": application, "attemptId": attempt_id, "sent": sent, "ambiguous": ambiguous, "result": result}

    def deliver(
        self,
        route_id: str,
        *,
        notification_config: Mapping[str, Any] | None = None,
        chat_config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = self.store.begin_delivery(route_id)
        if not record or record.get("status") in TERMINAL_STATES:
            return {"ok": False, "status": "route_unavailable", "routeId": route_id, "attempts": []}
        notification_config = notification_config or {}
        chat_config = chat_config or {}
        attempts = []
        if self._configured(notification_config):
            receive_type, receive_id = self._notification_target(record, notification_config, chat_config)
            if receive_type and receive_id:
                primary = self._attempt(
                    record,
                    application="notification",
                    app_config=notification_config,
                    receive_id_type=receive_type,
                    receive_id=receive_id,
                )
                attempts.append(primary)
                if primary["sent"]:
                    return {"ok": True, "status": "sent", "routeId": route_id, "application": "notification", "attempts": attempts}
            else:
                attempts.append({"application": "notification", "sent": False, "ambiguous": False, "status": "unroutable_identity"})
        if self._configured(chat_config) and record.get("feishuChatId"):
            fallback = self._attempt(
                record,
                application="chat",
                app_config=chat_config,
                receive_id_type="chat_id",
                receive_id=str(record.get("feishuChatId") or ""),
            )
            attempts.append(fallback)
            if fallback["sent"]:
                return {"ok": True, "status": "sent", "routeId": route_id, "application": "chat", "attempts": attempts}
        return {"ok": False, "status": "undeliverable", "routeId": route_id, "attempts": attempts}
