"""Durable kind-based dispatcher for resolved human decisions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Protocol

from .human_decision_chat_continuation import ContinuationDispatchResult
from .human_decisions import HumanDecisionContinuationClaim, HumanDecisionStore


class ContinuationAdapter(Protocol):
    def dispatch(self, claim: HumanDecisionContinuationClaim) -> ContinuationDispatchResult: ...


class HumanDecisionContinuationDispatcher:
    def __init__(self, *, store: HumanDecisionStore, adapters: Mapping[str, ContinuationAdapter]):
        self.store = store
        self._adapters = dict(adapters)

    def queue(self, decision_id: str) -> dict[str, Any]:
        return self.store.queue_continuation(decision_id)

    @staticmethod
    def _time(value: str | None) -> datetime:
        if value:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        return datetime.now(timezone.utc)

    def process_due(self, *, now: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        current = self._time(now)
        claims = self.store.claim_due_continuations(now=current.isoformat(), limit=limit)
        events: list[dict[str, Any]] = []
        for claim in claims:
            adapter = self._adapters.get(claim.kind)
            if adapter is None:
                result = ContinuationDispatchResult("failed", "continuation_adapter_missing")
            else:
                try:
                    result = adapter.dispatch(claim)
                except Exception:
                    result = ContinuationDispatchResult("dispatch_uncertain", "adapter_exception")
            outcome = str(result.outcome or "")
            category = str(result.error_category or "")[:80]
            if outcome == "dispatched":
                self.store.complete_continuation(claim.decision_id, claim_token=claim.claim_token)
                status = "completed"
            elif outcome == "not_dispatched_retryable":
                if claim.attempts >= 3:
                    self.store.fail_continuation(
                        claim.decision_id, claim_token=claim.claim_token,
                        error_category=category or "retry_exhausted",
                    )
                    status = "failed"
                else:
                    self.store.retry_continuation(
                        claim.decision_id,
                        claim_token=claim.claim_token,
                        error_category=category or "temporarily_unavailable",
                        next_attempt_at=(current + timedelta(seconds=30 * claim.attempts)).isoformat(),
                    )
                    status = "retry_wait"
            elif outcome == "failed":
                self.store.fail_continuation(
                    claim.decision_id, claim_token=claim.claim_token,
                    error_category=category or "dispatch_failed",
                )
                status = "failed"
            else:
                self.store.mark_continuation_uncertain(
                    claim.decision_id, claim_token=claim.claim_token,
                    error_category=category or "dispatch_uncertain",
                )
                status = "uncertain"
            events.append({"decisionId": claim.decision_id, "status": status, "attempts": claim.attempts})
        return events


__all__ = ["ContinuationAdapter", "HumanDecisionContinuationDispatcher"]
