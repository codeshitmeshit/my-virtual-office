"""Durable registration reconciler for independent recurring project instances."""

from __future__ import annotations

import copy
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from services.project_authoring_audit import build_audit_event, sanitize_audit_text
from services.project_authoring_config import is_recurrence_dispatch_paused, is_recurrence_enabled
from services.project_authoring_store import OUTBOX_KEY, RECURRENCES_KEY, ProjectAuthoringRootStore


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token() -> str:
    return str(uuid.uuid4())


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class RecurrenceRegistrationPorts:
    gateway: Callable[[str, dict[str, Any], int], dict[str, Any]]
    validate_schedule: Callable[[Any], str | None]
    extract_job_id: Callable[[dict[str, Any]], str]
    enabled: Callable[[], bool] = is_recurrence_enabled
    paused: Callable[[], bool] = is_recurrence_dispatch_paused
    clock: Callable[[], datetime] = _now
    new_token: Callable[[], str] = _token


class ProjectRecurrenceReconciler:
    """Claim bounded outbox batches and converge each recurrence to one Gateway job."""

    CLAIM_SECONDS = 300

    def __init__(self, store: ProjectAuthoringRootStore, ports: RecurrenceRegistrationPorts) -> None:
        self.store = store
        self.ports = ports

    def reconcile_once(self) -> dict[str, Any]:
        if not self.ports.enabled():
            return {"ok": True, "status": "disabled", "claimed": 0, "registered": 0, "failed": 0}
        if self.ports.paused():
            return {"ok": True, "status": "paused", "claimed": 0, "registered": 0, "failed": 0}
        claims = self._claim_batch()
        worker_count = min(self.store.config.outbox_worker_count, len(claims))
        if worker_count > 1:
            with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="project-recurrence") as executor:
                outcomes = list(executor.map(self._process_claim, claims))
        else:
            outcomes = [self._process_claim(claim) for claim in claims]
        registered = sum(outcome is True for outcome in outcomes)
        failed = len(outcomes) - registered
        return {
            "ok": True,
            "status": "ready",
            "claimed": len(claims),
            "registered": registered,
            "failed": failed,
        }

    def _claim_batch(self) -> list[dict[str, Any]]:
        now = self.ports.clock().astimezone(timezone.utc)
        token_prefix = self.ports.new_token()

        def claim(root: dict[str, Any]) -> list[dict[str, Any]]:
            selected = []
            for item in root[OUTBOX_KEY]:
                if len(selected) >= self.store.config.outbox_batch_size:
                    break
                if not isinstance(item, dict) or item.get("kind") != "register_project_template_instance":
                    continue
                state = str(item.get("state") or "pending")
                claim_expiry = _parse(item.get("claimExpiresAt"))
                stale_processing = state == "processing" and (claim_expiry is None or claim_expiry <= now)
                retry_due = state == "retry" and (_parse(item.get("nextAttemptAt")) or now) <= now
                if state != "pending" and not retry_due and not stale_processing:
                    continue
                attempts = int(item.get("attempts") or 0)
                if attempts >= self.store.config.outbox_max_attempts:
                    item.update({"state": "failed", "updatedAt": _iso(now)})
                    continue
                token = f"{token_prefix}:{len(selected) + 1}"
                item.update({
                    "state": "processing",
                    "attempts": attempts + 1,
                    "claimToken": token,
                    "claimedAt": _iso(now),
                    "claimExpiresAt": _iso(now + timedelta(seconds=self.CLAIM_SECONDS)),
                    "updatedAt": _iso(now),
                })
                selected.append({
                    "outboxId": item.get("id"),
                    "recurrenceId": item.get("recurrenceId"),
                    "claimToken": token,
                    "attempts": attempts + 1,
                })
            return selected

        return self.store.update(claim)

    def _process_claim(self, claim: Mapping[str, Any]) -> bool:
        recurrence_id = str(claim.get("recurrenceId") or "")
        root = self.store.snapshot()
        recurrence = root[RECURRENCES_KEY].get(recurrence_id)
        if not isinstance(recurrence, dict):
            self._finish_failure(claim, "recurrence_not_found", "Recurrence definition was not found", permanent=True)
            return False
        binding = recurrence.get("binding") if isinstance(recurrence.get("binding"), Mapping) else {}
        if recurrence.get("state") == "registered" and binding.get("cronJobId"):
            return self._finish_success(claim, recurrence, str(binding.get("cronJobId")), already_registered=True)
        schedule_error = self.ports.validate_schedule(recurrence.get("schedule"))
        if schedule_error:
            self._finish_failure(claim, "invalid_recurrence_schedule", schedule_error, permanent=True)
            return False
        job = self._gateway_job(recurrence)
        try:
            result = self.ports.gateway("cron.add", job, 30)
        except Exception as exc:
            self._finish_failure(claim, "gateway_request_failed", str(exc))
            return False
        if not isinstance(result, dict) or not result.get("ok"):
            error = result.get("error") if isinstance(result, Mapping) else "Invalid Gateway response"
            self._finish_failure(claim, "gateway_registration_failed", str(error or "Gateway registration failed"))
            return False
        cron_id = self.ports.extract_job_id(result)
        if not cron_id:
            self._finish_failure(claim, "gateway_job_id_missing", "Gateway created no identifiable cron job")
            return False
        try:
            completed = self._finish_success(claim, recurrence, cron_id)
        except Exception:
            self._remove_gateway_job(cron_id)
            raise
        if not completed:
            self._remove_gateway_job(cron_id)
        return completed

    def _finish_success(
        self,
        claim: Mapping[str, Any],
        recurrence: Mapping[str, Any],
        cron_id: str,
        *,
        already_registered: bool = False,
    ) -> bool:
        now = _iso(self.ports.clock())

        def finish(root: dict[str, Any]) -> bool:
            outbox = self._claimed_item(root, claim)
            current = root[RECURRENCES_KEY].get(str(claim.get("recurrenceId") or ""))
            if outbox is None or not isinstance(current, dict):
                return False
            binding = {
                "cronJobId": cron_id,
                "targetType": "projectTemplateInstance",
                "recurrenceId": current.get("id"),
                "templateId": current.get("templateId"),
                "templateVersion": current.get("templateVersion"),
                "requestingAgentId": current.get("requestingAgentId"),
                "schedule": copy.deepcopy(current.get("schedule")),
                "enabled": current.get("paused") is not True,
                "updatedAt": now,
            }
            current.update({
                "state": "registered",
                "gatewayCronId": cron_id,
                "binding": binding,
                "registeredAt": current.get("registeredAt") or now,
                "updatedAt": now,
            })
            current.setdefault("audit", []).append(build_audit_event(
                "recurrence_registered",
                "system:recurrence-reconciler",
                "system",
                now,
                "accepted",
                recurrenceId=current.get("id"),
                templateId=current.get("templateId"),
            ))
            current["audit"] = current["audit"][-self.store.config.audit_history_limit:]
            outbox.update({
                "state": "completed",
                "completedAt": now,
                "updatedAt": now,
                "result": {"cronJobId": cron_id, "alreadyRegistered": already_registered},
            })
            self._clear_claim(outbox)
            return True

        return bool(self.store.update(finish))

    def _finish_failure(
        self,
        claim: Mapping[str, Any],
        code: str,
        error: str,
        *,
        permanent: bool = False,
    ) -> None:
        now_dt = self.ports.clock().astimezone(timezone.utc)
        now = _iso(now_dt)
        attempts = int(claim.get("attempts") or 1)
        exhausted = attempts >= self.store.config.outbox_max_attempts
        terminal = permanent or exhausted
        delay = min(
            self.store.config.outbox_retry_max_seconds,
            self.store.config.outbox_retry_base_seconds * (2 ** max(0, attempts - 1)),
        )
        safe_error = sanitize_audit_text(error, limit=1000)

        def fail(root: dict[str, Any]) -> None:
            outbox = self._claimed_item(root, claim)
            if outbox is None:
                return
            outbox.update({
                "state": "failed" if terminal else "retry",
                "code": str(code or "recurrence_registration_failed"),
                "error": safe_error,
                "updatedAt": now,
            })
            if terminal:
                outbox["failedAt"] = now
                outbox.pop("nextAttemptAt", None)
            else:
                outbox["nextAttemptAt"] = _iso(now_dt + timedelta(seconds=delay))
            self._clear_claim(outbox)
            recurrence = root[RECURRENCES_KEY].get(str(claim.get("recurrenceId") or ""))
            if isinstance(recurrence, dict):
                recurrence.update({
                    "state": "intervention_required" if terminal else "registration_retry",
                    "lastError": {"code": code, "error": safe_error, "at": now},
                    "updatedAt": now,
                })
                recurrence.setdefault("audit", []).append(build_audit_event(
                    "recurrence_registration_failed",
                    "system:recurrence-reconciler",
                    "system",
                    now,
                    "failed",
                    recurrenceId=recurrence.get("id"),
                    templateId=recurrence.get("templateId"),
                    code=code,
                    error=safe_error,
                ))
                recurrence["audit"] = recurrence["audit"][-self.store.config.audit_history_limit:]

        self.store.update(fail)

    def _gateway_job(self, recurrence: Mapping[str, Any]) -> dict[str, Any]:
        recurrence_id = str(recurrence.get("id") or "")
        return {
            "name": f"VO recurring project {recurrence_id}",
            "schedule": copy.deepcopy(recurrence.get("schedule")),
            "payload": {
                "kind": "agentTurn",
                "message": (
                    "Create the due Virtual Office project-template instance for recurrence "
                    f"'{recurrence_id}'. Preserve the Gateway occurrence id when dispatching."
                ),
                "timeoutSeconds": 300,
            },
            "sessionTarget": "isolated",
            "enabled": recurrence.get("paused") is not True,
            "agentId": recurrence.get("requestingAgentId") or "main",
            "delivery": {"mode": "none"},
            "idempotencyKey": f"vo-project-recurrence:{recurrence_id}",
        }

    def _remove_gateway_job(self, cron_id: str) -> None:
        try:
            self.ports.gateway("cron.remove", {"id": cron_id}, 10)
        except Exception:
            pass

    @staticmethod
    def _clear_claim(item: dict[str, Any]) -> None:
        for field in ("claimToken", "claimedAt", "claimExpiresAt"):
            item.pop(field, None)

    @staticmethod
    def _claimed_item(root: Mapping[str, Any], claim: Mapping[str, Any]) -> dict[str, Any] | None:
        outbox_id = str(claim.get("outboxId") or "")
        token = str(claim.get("claimToken") or "")
        return next(
            (
                item for item in root.get(OUTBOX_KEY, [])
                if isinstance(item, dict)
                and str(item.get("id") or "") == outbox_id
                and str(item.get("claimToken") or "") == token
            ),
            None,
        )
