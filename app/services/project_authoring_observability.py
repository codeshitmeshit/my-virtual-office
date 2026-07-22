"""Bounded, credential-safe observability for project authoring and recurrence."""

from __future__ import annotations

import copy
import json
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from services.project_authoring_audit import sanitize_audit_text
from services.project_authoring_store import OUTBOX_KEY, RECURRENCES_KEY


def _parse_timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class ProjectAuthoringObservability:
    """Keep process-local metrics and derive durable queue health from root state."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        emit: Callable[[str], None] | None = None,
        log_interval_seconds: int = 60,
        alert_limit: int = 100,
    ) -> None:
        self.clock = clock
        self.emit = emit
        self.log_interval_seconds = max(1, int(log_interval_seconds))
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._durations: dict[str, dict[str, int]] = {}
        self._last_log: dict[str, float] = {}
        self._alerts: deque[dict[str, Any]] = deque(maxlen=max(10, int(alert_limit)))

    def observe(
        self,
        operation: str,
        *,
        status: str,
        duration_ms: int,
        code: str = "",
        intervention: bool = False,
    ) -> None:
        safe_operation = sanitize_audit_text(operation, limit=120) or "unknown"
        safe_status = sanitize_audit_text(status, limit=40) or "unknown"
        safe_code = sanitize_audit_text(code, limit=120)
        elapsed = max(0, int(duration_ms))
        with self._lock:
            self._counters["operations.total"] += 1
            self._counters[f"operations.{safe_status}"] += 1
            self._counters[f"operation.{safe_operation}.{safe_status}"] += 1
            timing = self._durations.setdefault(safe_operation, {"count": 0, "totalMs": 0, "maxMs": 0})
            timing["count"] += 1
            timing["totalMs"] += elapsed
            timing["maxMs"] = max(timing["maxMs"], elapsed)
            if intervention:
                self._counters["interventions.total"] += 1
                self._alerts.append({
                    "type": "operation_intervention",
                    "operation": safe_operation,
                    "code": safe_code or "intervention_required",
                    "at": datetime.fromtimestamp(self.clock(), timezone.utc).isoformat(),
                })
        quiet_statuses = {
            "success", "requested", "started", "already_active", "already_completed",
            "in_progress", "pending", "not_requested",
        }
        if safe_status not in quiet_statuses or intervention:
            self._emit_rate_limited(safe_operation, safe_status, safe_code, elapsed)

    def snapshot(
        self,
        root: Mapping[str, Any],
        *,
        authoring_enabled: bool,
        recurrence_enabled: bool,
        recurrence_paused: bool,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        outbox = root.get(OUTBOX_KEY) if isinstance(root.get(OUTBOX_KEY), list) else []
        recurrences = root.get(RECURRENCES_KEY) if isinstance(root.get(RECURRENCES_KEY), Mapping) else {}

        queued = [item for item in outbox if isinstance(item, Mapping) and item.get("state") in {"pending", "processing", "retry"}]
        intervention_recurrences = [
            item for item in recurrences.values()
            if isinstance(item, Mapping) and item.get("state") == "intervention_required"
        ]
        outbox_age = self._oldest_age_seconds(queued, current, "createdAt")
        durable_alerts = []
        for recurrence in intervention_recurrences[-20:]:
            last_error = recurrence.get("lastError") if isinstance(recurrence.get("lastError"), Mapping) else {}
            durable_alerts.append({
                "type": "recurrence_intervention",
                "recurrenceId": sanitize_audit_text(recurrence.get("id"), limit=160),
                "code": sanitize_audit_text(last_error.get("code"), limit=120) or "intervention_required",
                "at": sanitize_audit_text(last_error.get("at") or recurrence.get("updatedAt"), limit=80),
            })

        if intervention_recurrences:
            health = "intervention_required"
        elif outbox_age >= 900:
            health = "degraded"
        elif not authoring_enabled:
            health = "disabled"
        elif recurrence_enabled and recurrence_paused:
            health = "paused"
        else:
            health = "healthy"

        with self._lock:
            counters = dict(self._counters)
            durations = copy.deepcopy(self._durations)
            transient_alerts = list(self._alerts)
        duration_views = {
            operation: {
                **values,
                "averageMs": round(values["totalMs"] / values["count"], 2) if values["count"] else 0,
            }
            for operation, values in durations.items()
        }
        return {
            "ok": health not in {"degraded", "intervention_required"},
            "status": health,
            "features": {
                "authoring": "enabled" if authoring_enabled else "disabled",
                "recurrence": "paused" if recurrence_enabled and recurrence_paused else (
                    "enabled" if recurrence_enabled else "disabled"
                ),
            },
            "queues": {
                "recurrenceOutbox": len(queued),
                "oldestRecurrenceOutboxAgeSeconds": outbox_age,
            },
            "counters": counters,
            "durations": duration_views,
            "interventionAlerts": (durable_alerts + transient_alerts)[-100:],
        }

    def _emit_rate_limited(self, operation: str, status: str, code: str, duration_ms: int) -> None:
        if self.emit is None:
            return
        key = f"{operation}:{status}:{code}"
        now = self.clock()
        with self._lock:
            last = self._last_log.get(key)
            if last is not None and now - last < self.log_interval_seconds:
                self._counters["logs.suppressed"] += 1
                return
            self._last_log[key] = now
            self._counters["logs.emitted"] += 1
        self.emit(json.dumps({
            "type": "project_authoring_operation",
            "operation": operation,
            "status": status,
            "code": code,
            "durationMs": duration_ms,
        }, ensure_ascii=False, sort_keys=True))

    @staticmethod
    def _oldest_age_seconds(items: list[Mapping[str, Any]], now: datetime, field: str) -> int:
        timestamps = [parsed for item in items if (parsed := _parse_timestamp(item.get(field))) is not None]
        if not timestamps:
            return 0
        return max(0, int((now - min(timestamps)).total_seconds()))
