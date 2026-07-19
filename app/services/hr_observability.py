"""Bounded HR metrics, rate-limited safe logs, and non-sensitive health snapshots."""

from __future__ import annotations

import math
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping


class HRObservabilityValidationError(ValueError):
    code = "hr_observability_validation_failed"


@dataclass(frozen=True, slots=True)
class DurationSnapshot:
    count: int
    total_seconds: float
    max_seconds: float


@dataclass(frozen=True, slots=True)
class HRMetricsSnapshot:
    counters: dict[str, int]
    gauges: dict[str, float]
    durations: dict[str, DurationSnapshot]


@dataclass(frozen=True, slots=True)
class HRHealthSnapshot:
    status: str
    feature_enabled: bool
    scheduler_enabled: bool
    repository_status: str
    repository_code: str
    schema_version: int | None
    integrity: str
    foreign_key_violations: int
    metrics: HRMetricsSnapshot


class HRObservability:
    """In-memory process telemetry with a deliberately narrow disclosure surface."""

    DOMAINS = frozenset(
        {"lifecycle", "directory", "report", "assessment", "query", "skill"}
    )
    METRIC_PATTERN = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){1,3}\Z")
    SAFE_VALUE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}\Z")
    SENSITIVE_VALUE_PATTERN = re.compile(
        r"(?:bearer|token|secret|password|credential|authorization|provider.?envelope)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        logger: Callable[[Mapping[str, object]], None] = lambda _event: None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        log_rate_limit_seconds: float = 30.0,
    ):
        if not callable(logger) or not callable(clock):
            raise HRObservabilityValidationError("logger and clock must be callable")
        if (
            isinstance(log_rate_limit_seconds, bool)
            or not isinstance(log_rate_limit_seconds, (int, float))
            or not 0 <= float(log_rate_limit_seconds) <= 3_600
        ):
            raise HRObservabilityValidationError(
                "log_rate_limit_seconds must be between 0 and 3600"
            )
        self._logger = logger
        self._clock = clock
        self._log_rate_limit_seconds = float(log_rate_limit_seconds)
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}
        self._gauges: dict[str, float] = {}
        self._durations: dict[str, list[float | int]] = {}
        self._last_log: dict[tuple[str, str, str], datetime] = {}

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise HRObservabilityValidationError("observability clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    @classmethod
    def _metric(cls, metric: str) -> str:
        if not isinstance(metric, str) or cls.METRIC_PATTERN.fullmatch(metric) is None:
            raise HRObservabilityValidationError("metric name is invalid")
        if metric.split(".", 1)[0] not in cls.DOMAINS:
            raise HRObservabilityValidationError("metric domain is unsupported")
        if cls.SENSITIVE_VALUE_PATTERN.search(metric):
            raise HRObservabilityValidationError("metric name contains a sensitive term")
        return metric

    @staticmethod
    def _finite(value: object, field: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise HRObservabilityValidationError(f"{field} must be numeric")
        result = float(value)
        if not math.isfinite(result) or result < 0:
            raise HRObservabilityValidationError(f"{field} must be finite and non-negative")
        return result

    def increment(self, metric: str, amount: int = 1) -> None:
        metric = self._metric(metric)
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 1:
            raise HRObservabilityValidationError("counter amount must be a positive integer")
        with self._lock:
            self._counters[metric] = self._counters.get(metric, 0) + amount

    def gauge(self, metric: str, value: float) -> None:
        metric = self._metric(metric)
        value = self._finite(value, "gauge value")
        with self._lock:
            self._gauges[metric] = value

    def observe_duration(self, metric: str, seconds: float) -> None:
        metric = self._metric(metric)
        seconds = self._finite(seconds, "duration")
        with self._lock:
            current = self._durations.setdefault(metric, [0, 0.0, 0.0])
            current[0] = int(current[0]) + 1
            current[1] = float(current[1]) + seconds
            current[2] = max(float(current[2]), seconds)

    @classmethod
    def _safe_value(cls, value: object) -> str:
        if not isinstance(value, str):
            return ""
        stripped = value.strip()
        return (
            stripped
            if cls.SAFE_VALUE_PATTERN.fullmatch(stripped)
            and cls.SENSITIVE_VALUE_PATTERN.search(stripped) is None
            else ""
        )

    def event(
        self,
        event: str,
        *,
        status: str,
        code: str = "",
        ai_id: str = "",
        cycle_id: str = "",
        duration_seconds: float | None = None,
    ) -> bool:
        event = self._metric(event)
        status = self._safe_value(status) or "invalid_status"
        code = self._safe_value(code) or ("ok" if status in {"ok", "complete"} else "invalid_code")
        ai_id = self._safe_value(ai_id)
        cycle_id = self._safe_value(cycle_id)
        duration = (
            self._finite(duration_seconds, "duration")
            if duration_seconds is not None
            else None
        )
        now = self._now()
        key = (event, status, code)
        with self._lock:
            previous = self._last_log.get(key)
            if (
                previous is not None
                and (now - previous).total_seconds() < self._log_rate_limit_seconds
            ):
                suppressed = f"{event}.suppressed"
                self._counters[suppressed] = self._counters.get(suppressed, 0) + 1
                return False
            self._last_log[key] = now
        payload: dict[str, object] = {
            "event": event,
            "status": status,
            "code": code,
            "at": now.isoformat(),
        }
        if ai_id:
            payload["aiId"] = ai_id
        if cycle_id:
            payload["cycleId"] = cycle_id
        if duration is not None:
            payload["durationSeconds"] = duration
        try:
            self._logger(payload)
            return True
        except Exception:
            with self._lock:
                failed = f"{event}.log_failures"
                self._counters[failed] = self._counters.get(failed, 0) + 1
            return False

    def metrics(self) -> HRMetricsSnapshot:
        with self._lock:
            return HRMetricsSnapshot(
                counters=dict(self._counters),
                gauges=dict(self._gauges),
                durations={
                    metric: DurationSnapshot(
                        count=int(value[0]),
                        total_seconds=float(value[1]),
                        max_seconds=float(value[2]),
                    )
                    for metric, value in self._durations.items()
                },
            )

    def health(
        self,
        repository: object,
        *,
        feature_enabled: bool,
        scheduler_enabled: bool,
    ) -> HRHealthSnapshot:
        if not isinstance(feature_enabled, bool) or not isinstance(scheduler_enabled, bool):
            raise HRObservabilityValidationError("health switches must be boolean")

        def field(name: str, default: object) -> object:
            if isinstance(repository, Mapping):
                return repository.get(name, default)
            return getattr(repository, name, default)

        repository_status = self._safe_value(field("status", "unknown")) or "unknown"
        repository_code = self._safe_value(field("code", "unknown")) or "unknown"
        schema_version = field("schema_version", None)
        if isinstance(schema_version, bool) or not isinstance(schema_version, (int, type(None))):
            schema_version = None
        integrity = self._safe_value(field("integrity", "unknown")) or "unknown"
        violations = field("foreign_key_violations", 0)
        if isinstance(violations, bool) or not isinstance(violations, int) or violations < 0:
            violations = 0
        healthy = repository_status in {"ok", "ready"} and integrity == "ok" and violations == 0
        return HRHealthSnapshot(
            status="ok" if healthy else "degraded",
            feature_enabled=feature_enabled,
            scheduler_enabled=scheduler_enabled,
            repository_status=repository_status,
            repository_code=repository_code,
            schema_version=schema_version,
            integrity=integrity,
            foreign_key_violations=violations,
            metrics=self.metrics(),
        )
