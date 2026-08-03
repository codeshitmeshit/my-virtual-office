"""Durable authority for VO human decision requests.

The store owns validation and state transitions. Transport, Feishu delivery and
dashboard projection stay outside this module so every execution surface writes
the same authority without importing the legacy server entry point.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


JsonDict = dict[str, Any]
_PATH_LOCKS: dict[str, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()
_OPTION_IDS = ("A", "B", "C", "D")
_SOURCE_TYPES = {"task", "meeting", "chat"}
_RISKS = {"low", "medium", "high"}
_URGENCIES = {"normal", "urgent", "critical"}
_REMINDER_INTERVALS = {"critical": timedelta(minutes=15), "urgent": timedelta(hours=1), "normal": timedelta(hours=8)}


class HumanDecisionError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class HumanDecisionContinuationClaim:
    decision_id: str
    claim_token: str
    kind: str
    agent_id: str
    binding: JsonDict
    attempts: int
    decision: JsonDict

    @property
    def conversation_id(self) -> str:
        return str(self.binding.get("conversationId") or "")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _text(value: Any, limit: int, *, required: bool = False, field: str = "value") -> str:
    result = str(value or "").strip()
    if required and not result:
        raise HumanDecisionError("missing_field", f"{field} is required")
    return result[:limit]


def _lock_for(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


class HumanDecisionStore:
    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self._lock = _lock_for(self.path)

    def _empty(self) -> JsonDict:
        return {"revision": 0, "decisions": [], "idempotency": {}}

    def _load(self) -> JsonDict:
        if not self.path.exists():
            return self._empty()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HumanDecisionError("state_unavailable", f"Decision state unavailable: {exc}", 500) from exc
        if not isinstance(data, dict) or not isinstance(data.get("decisions"), list):
            raise HumanDecisionError("state_invalid", "Decision state is invalid", 500)
        data.setdefault("revision", 0)
        data.setdefault("idempotency", {})
        return data

    def _save(self, data: JsonDict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, sort_keys=True, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self.path)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    @staticmethod
    def _public(decision: JsonDict) -> JsonDict:
        projected = copy.deepcopy(decision)
        projected.pop("_deliveries", None)
        continuation = projected.pop("_continuation", None)
        if isinstance(continuation, dict):
            projected["continuation"] = {
                "status": str(continuation.get("status") or ""),
                "attempts": int(continuation.get("attempts") or 0),
                "updatedAt": str(continuation.get("updatedAt") or ""),
                "errorCategory": str(continuation.get("errorCategory") or ""),
            }
        return projected

    @staticmethod
    def _find(data: JsonDict, decision_id: str) -> JsonDict:
        for decision in data["decisions"]:
            if isinstance(decision, dict) and decision.get("id") == decision_id:
                return decision
        raise HumanDecisionError("decision_not_found", "Decision request not found", 404)

    def snapshot(self) -> JsonDict:
        with self._lock:
            data = self._load()
            return {
                "revision": int(data.get("revision") or 0),
                "generatedAt": _now_iso(),
                "decisions": [self._public(item) for item in data["decisions"] if isinstance(item, dict)],
            }

    def create(self, payload: JsonDict) -> JsonDict:
        if not isinstance(payload, dict):
            raise HumanDecisionError("invalid_request", "Decision request must be an object")
        with self._lock:
            data = self._load()
            key = _text(payload.get("idempotencyKey"), 240)
            existing_id = (data.get("idempotency") or {}).get(key) if key else None
            if existing_id:
                return {"created": False, "decision": self._public(self._find(data, existing_id)), "revision": data["revision"]}

            source_input = payload.get("source") if isinstance(payload.get("source"), dict) else {}
            source_type = _text(source_input.get("type"), 20, required=True, field="source.type")
            if source_type not in _SOURCE_TYPES:
                raise HumanDecisionError("invalid_source", "source.type must be task, meeting, or chat")
            source = {
                "type": source_type,
                "id": _text(source_input.get("id"), 240, required=True, field="source.id"),
                "label": _text(source_input.get("label"), 240, required=True, field="source.label"),
            }
            project_source_id = _text(source_input.get("projectId"), 240)
            if source_type == "task" and project_source_id:
                source["projectId"] = project_source_id

            raw_options = payload.get("options")
            if not isinstance(raw_options, list) or len(raw_options) != 4:
                raise HumanDecisionError("invalid_options", "Exactly A, B, C, and D options are required")
            options = []
            for raw in raw_options:
                item = raw if isinstance(raw, dict) else {}
                options.append({
                    "id": _text(item.get("id"), 1),
                    "label": _text(item.get("label"), 400, required=True, field="option.label"),
                    "impact": _text(item.get("impact"), 1000, required=True, field="option.impact"),
                })
            if tuple(item["id"] for item in options) != _OPTION_IDS:
                raise HumanDecisionError("invalid_options", "Options must be ordered A, B, C, and D")

            recommendation_input = payload.get("recommendation") if isinstance(payload.get("recommendation"), dict) else {}
            recommendation_id = _text(recommendation_input.get("optionId"), 1)
            if recommendation_id not in _OPTION_IDS:
                raise HumanDecisionError("invalid_recommendation", "recommendation.optionId must reference A, B, C, or D")
            risk = _text(payload.get("risk") or "medium", 20).lower()
            urgency = _text(payload.get("urgency") or "normal", 20).lower()
            if risk not in _RISKS:
                raise HumanDecisionError("invalid_risk", "risk must be low, medium, or high")
            if urgency not in _URGENCIES:
                raise HumanDecisionError("invalid_urgency", "urgency must be normal, urgent, or critical")

            detail_input = payload.get("taskDetail") if isinstance(payload.get("taskDetail"), dict) else {}
            completed = detail_input.get("completed") if isinstance(detail_input.get("completed"), list) else []
            now = _now_iso()
            next_reminder_at = _text(payload.get("nextReminderAt"), 80)
            if not next_reminder_at:
                next_reminder_at = (
                    (_parse_time(now) or datetime.now(timezone.utc))
                    + _REMINDER_INTERVALS.get(urgency, _REMINDER_INTERVALS["normal"])
                ).isoformat()
            decision: JsonDict = {
                "id": _text(payload.get("id"), 120) or f"decision-{uuid.uuid4().hex}",
                "status": "pending",
                "createdAt": now,
                "source": source,
                "title": _text(payload.get("title"), 240, required=True, field="title"),
                "situation": _text(payload.get("situation"), 4000, required=True, field="situation"),
                "reason": _text(payload.get("reason"), 3000, required=True, field="reason"),
                "risk": risk,
                "urgency": urgency,
                "nearTimeout": bool(payload.get("nearTimeout")),
                "deadlineAt": _text(payload.get("deadlineAt"), 80),
                "timeoutConsequence": _text(payload.get("timeoutConsequence"), 2000),
                "options": options,
                "recommendation": {
                    "optionId": recommendation_id,
                    "reason": _text(recommendation_input.get("reason"), 2000, required=True, field="recommendation.reason"),
                },
                "reminder": {"count": 0, "limit": 3, "nextAt": next_reminder_at},
                "taskDetail": {
                    "summary": _text(detail_input.get("summary"), 3000),
                    "completed": [_text(item, 500) for item in completed[:20] if _text(item, 500)],
                    "blocked": _text(detail_input.get("blocked"), 2000),
                    "context": _text(detail_input.get("context"), 4000),
                    "nextStep": _text(detail_input.get("nextStep"), 2000),
                },
                "resolution": None,
                "execution": {"started": False, "impact": ""},
                "sync": {"feishuStatus": "pending", "application": ""},
                "_deliveries": [],
            }
            data["decisions"].append(decision)
            data["revision"] = int(data.get("revision") or 0) + 1
            if key:
                data.setdefault("idempotency", {})[key] = decision["id"]
            self._save(data)
            return {"created": True, "decision": self._public(decision), "revision": data["revision"]}

    def resolve(
        self,
        decision_id: str,
        *,
        option_id: str | None = None,
        custom_answer: str | None = None,
        channel: str = "local",
        actor: JsonDict | None = None,
    ) -> JsonDict:
        custom = _text(custom_answer, 4000)
        selected_id = _text(option_id, 1)
        with self._lock:
            data = self._load()
            decision = self._find(data, decision_id)
            options = {item["id"]: item for item in decision.get("options") or [] if isinstance(item, dict)}
            if not custom and selected_id not in options:
                raise HumanDecisionError("invalid_option", "Select A, B, C, or D, or provide a custom answer")
            if custom and selected_id and selected_id not in options:
                raise HumanDecisionError("invalid_option", "optionId must be A, B, C, or D")
            effective_option_id = None if custom else selected_id
            answer = custom or options[selected_id]["label"]
            normalized_channel = _text(channel, 20) or "local"
            normalized_actor = copy.deepcopy(actor) if isinstance(actor, dict) else {}
            existing = decision.get("resolution") if isinstance(decision.get("resolution"), dict) else None
            if decision.get("status") != "pending":
                if existing and existing.get("answer") == answer and existing.get("optionId") == effective_option_id and existing.get("channel") == normalized_channel:
                    return {"idempotent": True, "decision": self._public(decision), "revision": data["revision"]}
                raise HumanDecisionError("decision_conflict", "Decision was already resolved with a different answer", 409)
            decision["status"] = "resolved"
            decision["resolution"] = {
                "answer": answer,
                "optionId": effective_option_id,
                "channel": normalized_channel,
                "resolvedAt": _now_iso(),
                "nextAction": _text((decision.get("taskDetail") or {}).get("nextStep"), 2000),
                "actor": normalized_actor,
            }
            data["revision"] += 1
            self._save(data)
            return {"idempotent": False, "decision": self._public(decision), "revision": data["revision"]}

    def reopen(self, decision_id: str) -> JsonDict:
        with self._lock:
            data = self._load()
            decision = self._find(data, decision_id)
            if (decision.get("execution") or {}).get("started"):
                raise HumanDecisionError("execution_started", "Decision cannot be reopened after execution starts", 409)
            if decision.get("status") == "pending":
                return {"idempotent": True, "decision": self._public(decision), "revision": data["revision"]}
            decision["status"] = "pending"
            decision["resolution"] = None
            data["revision"] += 1
            self._save(data)
            return {"idempotent": False, "decision": self._public(decision), "revision": data["revision"]}

    def mark_execution_started(self, decision_id: str, *, impact: str = "") -> JsonDict:
        with self._lock:
            data = self._load()
            decision = self._find(data, decision_id)
            if decision.get("status") == "pending" or not isinstance(decision.get("resolution"), dict):
                raise HumanDecisionError("decision_pending", "Execution cannot start before the decision is resolved", 409)
            if (decision.get("execution") or {}).get("started"):
                return {"idempotent": True, "decision": self._public(decision), "revision": data["revision"]}
            decision["status"] = "locked"
            decision["execution"] = {"started": True, "impact": _text(impact, 2000)}
            data["revision"] += 1
            self._save(data)
            return {"idempotent": False, "decision": self._public(decision), "revision": data["revision"]}

    def record_delivery(self, decision_id: str, *, application: str, result: JsonDict) -> JsonDict:
        with self._lock:
            data = self._load()
            decision = self._find(data, decision_id)
            record = {
                "application": _text(application, 40),
                "ok": bool(result.get("ok")),
                "status": _text(result.get("status"), 80),
                "messageId": _text(result.get("messageId"), 300),
                "recordedAt": _now_iso(),
            }
            decision.setdefault("_deliveries", []).append(record)
            decision["sync"] = {
                "feishuStatus": record["status"] or ("sent" if record["ok"] else "failed"),
                "application": record["application"],
            }
            data["revision"] += 1
            self._save(data)
            return {"decision": self._public(decision), "revision": data["revision"]}

    def delivery_records(self, decision_id: str) -> list[JsonDict]:
        with self._lock:
            decision = self._find(self._load(), decision_id)
            return copy.deepcopy(decision.get("_deliveries") or [])

    def bind_continuation(
        self,
        decision_id: str,
        *,
        kind: str,
        agent_id: str,
        binding: JsonDict,
    ) -> JsonDict:
        agent = _text(agent_id, 160, required=True, field="agent_id")
        normalized_kind = _text(kind, 20, required=True, field="kind").lower()
        if normalized_kind not in _SOURCE_TYPES:
            raise HumanDecisionError("continuation_binding_invalid", "Unsupported continuation kind", 409)
        raw_binding = binding if isinstance(binding, dict) else {}
        allowed_keys = {
            "chat": ("conversationId",),
            "meeting": ("meetingId", "meetingVersion", "resumeStage"),
            "task": ("projectId", "taskId", "attemptId", "runId", "mode", "sessionKey"),
        }[normalized_kind]
        normalized_binding = {
            key: _text(raw_binding.get(key), 300)
            for key in allowed_keys
            if _text(raw_binding.get(key), 300)
        }
        with self._lock:
            data = self._load()
            decision = self._find(data, decision_id)
            source = decision.get("source") if isinstance(decision.get("source"), dict) else {}
            matches = source.get("type") == normalized_kind
            if normalized_kind == "chat":
                matches = matches and source.get("id") == normalized_binding.get("conversationId")
            elif normalized_kind == "meeting":
                matches = matches and source.get("id") == normalized_binding.get("meetingId")
            else:
                matches = (
                    matches
                    and source.get("id") == normalized_binding.get("taskId")
                    and source.get("projectId") == normalized_binding.get("projectId")
                    and bool(normalized_binding.get("attemptId") or normalized_binding.get("sessionKey"))
                )
            if not matches:
                raise HumanDecisionError(
                    "continuation_binding_invalid",
                    "Continuation binding must match the decision source",
                    409,
                )
            existing = decision.get("_continuation")
            if isinstance(existing, dict):
                existing_binding = existing.get("binding") if isinstance(existing.get("binding"), dict) else {
                    "conversationId": existing.get("conversationId")
                }
                if (
                    existing.get("kind") != normalized_kind
                    or existing.get("agentId") != agent
                    or existing_binding != normalized_binding
                ):
                    raise HumanDecisionError(
                        "continuation_binding_conflict",
                        "Decision is already bound to another continuation",
                        409,
                    )
                return self._public(decision)
            decision["_continuation"] = {
                "kind": normalized_kind,
                "agentId": agent,
                "binding": normalized_binding,
                "status": "waiting",
                "attempts": 0,
                "nextAttemptAt": "",
                "claimToken": "",
                "leaseExpiresAt": "",
                "updatedAt": _now_iso(),
                "errorCategory": "",
            }
            data["revision"] += 1
            self._save(data)
            return self._public(decision)

    def bind_chat_continuation(
        self,
        decision_id: str,
        *,
        agent_id: str,
        conversation_id: str,
    ) -> JsonDict:
        result = self.bind_continuation(
            decision_id,
            kind="chat",
            agent_id=agent_id,
            binding={"conversationId": conversation_id},
        )
        # Preserve the on-disk legacy aliases while older installations migrate.
        with self._lock:
            data = self._load()
            decision = self._find(data, decision_id)
            continuation = decision.get("_continuation")
            if isinstance(continuation, dict):
                continuation["conversationId"] = str(conversation_id)
                self._save(data)
        return result

    def queue_continuation(self, decision_id: str) -> JsonDict:
        with self._lock:
            data = self._load()
            decision = self._find(data, decision_id)
            continuation = decision.get("_continuation")
            if not isinstance(continuation, dict):
                return {"queued": False, "decision": self._public(decision), "revision": data["revision"]}
            if decision.get("status") not in {"resolved", "locked"}:
                raise HumanDecisionError(
                    "continuation_decision_pending",
                    "Chat continuation cannot be queued before resolution",
                    409,
                )
            if continuation.get("status") != "waiting":
                return {"queued": False, "decision": self._public(decision), "revision": data["revision"]}
            continuation.update({
                "status": "queued",
                "nextAttemptAt": "",
                "claimToken": "",
                "leaseExpiresAt": "",
                "updatedAt": _now_iso(),
                "errorCategory": "",
            })
            data["revision"] += 1
            self._save(data)
            return {"queued": True, "decision": self._public(decision), "revision": data["revision"]}

    def queue_chat_continuation(self, decision_id: str) -> JsonDict:
        return self.queue_continuation(decision_id)

    def claim_due_continuations(
        self,
        *,
        now: str | None = None,
        limit: int = 10,
        lease_seconds: int = 60,
        kinds: set[str] | None = None,
    ) -> list[HumanDecisionContinuationClaim]:
        current = _parse_time(now) if now else datetime.now(timezone.utc)
        if current is None:
            raise HumanDecisionError("invalid_time", "now must be an ISO-8601 timestamp")
        claims: list[HumanDecisionContinuationClaim] = []
        changed = False
        with self._lock:
            data = self._load()
            for decision in data["decisions"]:
                if not isinstance(decision, dict):
                    continue
                continuation = decision.get("_continuation")
                if not isinstance(continuation, dict):
                    continue
                continuation_kind = str(continuation.get("kind") or "chat")
                if kinds is not None and continuation_kind not in kinds:
                    continue
                status = str(continuation.get("status") or "")
                if status == "running":
                    lease = _parse_time(continuation.get("leaseExpiresAt"))
                    if lease is not None and lease <= current:
                        continuation.update({
                            "status": "uncertain",
                            "claimToken": "",
                            "leaseExpiresAt": "",
                            "updatedAt": current.isoformat(),
                            "errorCategory": "lease_expired",
                        })
                        data["revision"] += 1
                        changed = True
                    continue
                recover_waiting = (
                    status == "waiting"
                    and decision.get("status") in {"resolved", "locked"}
                    and isinstance(decision.get("resolution"), dict)
                )
                if status not in {"queued", "retry_wait"} and not recover_waiting:
                    continue
                next_attempt = _parse_time(continuation.get("nextAttemptAt"))
                if status == "retry_wait" and next_attempt is not None and next_attempt > current:
                    continue
                token = uuid.uuid4().hex
                attempts = int(continuation.get("attempts") or 0) + 1
                continuation.update({
                    "status": "running",
                    "attempts": attempts,
                    "claimToken": token,
                    "leaseExpiresAt": (current + timedelta(seconds=max(1, int(lease_seconds)))).isoformat(),
                    "updatedAt": current.isoformat(),
                    "errorCategory": "",
                })
                data["revision"] += 1
                changed = True
                claims.append(HumanDecisionContinuationClaim(
                    decision_id=str(decision.get("id") or ""),
                    claim_token=token,
                    kind=continuation_kind,
                    agent_id=str(continuation.get("agentId") or ""),
                    binding=copy.deepcopy(
                        continuation.get("binding")
                        if isinstance(continuation.get("binding"), dict)
                        else {"conversationId": continuation.get("conversationId") or ""}
                    ),
                    attempts=attempts,
                    decision=self._public(decision),
                ))
                if len(claims) >= max(1, int(limit)):
                    break
            if changed:
                self._save(data)
        return claims

    def claim_due_chat_continuations(self, **kwargs: Any) -> list[HumanDecisionContinuationClaim]:
        return self.claim_due_continuations(**kwargs, kinds={"chat"})

    def _transition_running_continuation(
        self,
        decision_id: str,
        *,
        claim_token: str,
        status: str,
        error_category: str = "",
        next_attempt_at: str = "",
    ) -> JsonDict:
        with self._lock:
            data = self._load()
            decision = self._find(data, decision_id)
            continuation = decision.get("_continuation")
            if (
                not isinstance(continuation, dict)
                or continuation.get("status") != "running"
                or continuation.get("claimToken") != str(claim_token or "")
            ):
                return {"updated": False, "decision": self._public(decision), "revision": data["revision"]}
            continuation.update({
                "status": status,
                "nextAttemptAt": next_attempt_at,
                "claimToken": "",
                "leaseExpiresAt": "",
                "updatedAt": _now_iso(),
                "errorCategory": _text(error_category, 80),
            })
            data["revision"] += 1
            self._save(data)
            return {"updated": True, "decision": self._public(decision), "revision": data["revision"]}

    def complete_continuation(self, decision_id: str, *, claim_token: str) -> JsonDict:
        return self._transition_running_continuation(decision_id, claim_token=claim_token, status="completed")

    def retry_continuation(self, decision_id: str, *, claim_token: str, error_category: str, next_attempt_at: str) -> JsonDict:
        parsed = _parse_time(next_attempt_at)
        if parsed is None:
            raise HumanDecisionError("invalid_time", "next_attempt_at must be an ISO-8601 timestamp")
        return self._transition_running_continuation(
            decision_id, claim_token=claim_token, status="retry_wait",
            error_category=error_category, next_attempt_at=parsed.isoformat(),
        )

    def fail_continuation(self, decision_id: str, *, claim_token: str, error_category: str) -> JsonDict:
        return self._transition_running_continuation(
            decision_id, claim_token=claim_token, status="failed", error_category=error_category,
        )

    def mark_continuation_uncertain(self, decision_id: str, *, claim_token: str, error_category: str) -> JsonDict:
        return self._transition_running_continuation(
            decision_id, claim_token=claim_token, status="uncertain", error_category=error_category,
        )

    def complete_chat_continuation(self, decision_id: str, *, claim_token: str) -> JsonDict:
        return self.complete_continuation(decision_id, claim_token=claim_token)

    def retry_chat_continuation(
        self,
        decision_id: str,
        *,
        claim_token: str,
        error_category: str,
        next_attempt_at: str,
    ) -> JsonDict:
        return self.retry_continuation(
            decision_id, claim_token=claim_token, error_category=error_category, next_attempt_at=next_attempt_at,
        )

    def fail_chat_continuation(
        self,
        decision_id: str,
        *,
        claim_token: str,
        error_category: str,
    ) -> JsonDict:
        return self.fail_continuation(decision_id, claim_token=claim_token, error_category=error_category)

    def mark_chat_continuation_uncertain(
        self,
        decision_id: str,
        *,
        claim_token: str,
        error_category: str,
    ) -> JsonDict:
        return self.mark_continuation_uncertain(decision_id, claim_token=claim_token, error_category=error_category)

    def process_due(self, now: str | None = None) -> list[JsonDict]:
        """Advance due reminders and apply the bounded timeout policy atomically."""
        current = _parse_time(now) if now else datetime.now(timezone.utc)
        if current is None:
            raise HumanDecisionError("invalid_time", "now must be an ISO-8601 timestamp")
        events: list[JsonDict] = []
        with self._lock:
            data = self._load()
            for decision in data["decisions"]:
                if not isinstance(decision, dict) or decision.get("status") != "pending":
                    continue
                reminder = decision.get("reminder") if isinstance(decision.get("reminder"), dict) else {}
                count = max(0, min(int(reminder.get("count") or 0), 3))
                due_at = _parse_time(reminder.get("nextAt"))
                if due_at is None or due_at > current:
                    continue
                reminder["limit"] = 3
                if count < 3:
                    count += 1
                    reminder["count"] = count
                    interval = _REMINDER_INTERVALS.get(decision.get("urgency"), _REMINDER_INTERVALS["normal"])
                    reminder["nextAt"] = (current + interval).isoformat()
                    decision["nearTimeout"] = count >= 2
                    kind = "reminder"
                else:
                    reminder["nextAt"] = ""
                    decision["nearTimeout"] = True
                    if decision.get("risk") == "low":
                        recommended_id = str((decision.get("recommendation") or {}).get("optionId") or "")
                        option = next(
                            (item for item in decision.get("options") or [] if isinstance(item, dict) and item.get("id") == recommended_id),
                            None,
                        )
                        if option:
                            decision["status"] = "resolved"
                            decision["resolution"] = {
                                "answer": str(option.get("label") or ""),
                                "optionId": recommended_id,
                                "channel": "timeout",
                                "resolvedAt": current.isoformat(),
                                "nextAction": _text((decision.get("taskDetail") or {}).get("nextStep"), 2000),
                                "actor": {"id": "vo:timeout"},
                            }
                            kind = "timeout_resolved"
                    if decision.get("status") == "pending":
                        kind = "timeout_waiting"
                data["revision"] += 1
                events.append({"kind": kind, "decision": self._public(decision), "revision": data["revision"]})
            if events:
                self._save(data)
        return events
