"""Configuration and stable capacity errors for Agent-managed VO projects."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


Environment = Mapping[str, str]

AUTHORING_FEATURE_ENV = "VO_AGENT_PROJECT_AUTHORING_ENABLED"
RECURRENCE_FEATURE_ENV = "VO_PROJECT_INSTANCE_RECURRENCE_ENABLED"
RECURRENCE_PAUSE_ENV = "VO_PROJECT_INSTANCE_RECURRENCE_DISPATCH_PAUSED"


def _env_bool(environ: Environment, name: str, default: bool = False) -> bool:
    raw = environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _bounded_int(
    environ: Environment,
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(str(environ.get(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def is_authoring_enabled(environ: Environment | None = None) -> bool:
    """Read the rollout switch at action time so disabling takes effect immediately."""
    return _env_bool(environ if environ is not None else os.environ, AUTHORING_FEATURE_ENV, False)


def is_recurrence_enabled(environ: Environment | None = None) -> bool:
    """Read the recurrence-registration/dispatch switch at action time."""
    return _env_bool(environ if environ is not None else os.environ, RECURRENCE_FEATURE_ENV, False)


def is_recurrence_dispatch_paused(environ: Environment | None = None) -> bool:
    """Allow operations to pause dispatch while retaining durable intents."""
    return _env_bool(environ if environ is not None else os.environ, RECURRENCE_PAUSE_ENV, False)


@dataclass(frozen=True)
class ProjectAuthoringConfig:
    body_limit_bytes: int
    max_initial_tasks: int
    max_pending_per_agent: int
    max_pending_global: int
    max_maintenance_requests_per_project: int
    audit_history_limit: int
    recurrence_history_limit: int
    terminal_retention_days: int
    outbox_capacity: int
    outbox_worker_count: int
    outbox_batch_size: int
    outbox_retry_base_seconds: int
    outbox_retry_max_seconds: int
    outbox_max_attempts: int

    @classmethod
    def from_env(cls, environ: Environment | None = None) -> "ProjectAuthoringConfig":
        env = environ if environ is not None else os.environ
        retry_base = _bounded_int(
            env, "VO_PROJECT_AUTHORING_OUTBOX_RETRY_BASE_SECONDS", 2,
            minimum=1, maximum=3600,
        )
        retry_max = _bounded_int(
            env, "VO_PROJECT_AUTHORING_OUTBOX_RETRY_MAX_SECONDS", 300,
            minimum=retry_base, maximum=86400,
        )
        return cls(
            body_limit_bytes=_bounded_int(
                env, "VO_PROJECT_AUTHORING_BODY_LIMIT_BYTES", 64 * 1024,
                minimum=1024, maximum=1024 * 1024,
            ),
            max_initial_tasks=_bounded_int(
                env, "VO_PROJECT_AUTHORING_MAX_INITIAL_TASKS", 100,
                minimum=1, maximum=1000,
            ),
            max_pending_per_agent=_bounded_int(
                env, "VO_PROJECT_AUTHORING_MAX_PENDING_PER_AGENT", 20,
                minimum=1, maximum=500,
            ),
            max_pending_global=_bounded_int(
                env, "VO_PROJECT_AUTHORING_MAX_PENDING_GLOBAL", 500,
                minimum=1, maximum=10000,
            ),
            max_maintenance_requests_per_project=_bounded_int(
                env, "VO_PROJECT_AUTHORING_MAX_MAINTENANCE_PER_PROJECT", 20,
                minimum=1, maximum=500,
            ),
            audit_history_limit=_bounded_int(
                env, "VO_PROJECT_AUTHORING_AUDIT_HISTORY_LIMIT", 100,
                minimum=10, maximum=1000,
            ),
            recurrence_history_limit=_bounded_int(
                env, "VO_PROJECT_AUTHORING_RECURRENCE_HISTORY_LIMIT", 100,
                minimum=10, maximum=1000,
            ),
            terminal_retention_days=_bounded_int(
                env, "VO_PROJECT_AUTHORING_TERMINAL_RETENTION_DAYS", 30,
                minimum=1, maximum=3650,
            ),
            outbox_capacity=_bounded_int(
                env, "VO_PROJECT_AUTHORING_OUTBOX_CAPACITY", 1000,
                minimum=1, maximum=100000,
            ),
            outbox_worker_count=_bounded_int(
                env, "VO_PROJECT_AUTHORING_OUTBOX_WORKERS", 2,
                minimum=1, maximum=32,
            ),
            outbox_batch_size=_bounded_int(
                env, "VO_PROJECT_AUTHORING_OUTBOX_BATCH_SIZE", 20,
                minimum=1, maximum=500,
            ),
            outbox_retry_base_seconds=retry_base,
            outbox_retry_max_seconds=retry_max,
            outbox_max_attempts=_bounded_int(
                env, "VO_PROJECT_AUTHORING_OUTBOX_MAX_ATTEMPTS", 10,
                minimum=1, maximum=100,
            ),
        )


DEFAULT_CONFIG = ProjectAuthoringConfig.from_env()


@dataclass
class ProjectAuthoringCapacityError(RuntimeError):
    code: str
    message: str
    status: int
    retryable: bool = True
    scope: str = ""

    def __str__(self) -> str:
        return self.message

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "ok": False,
            "code": self.code,
            "error": self.message,
            "retryable": self.retryable,
            "_status": self.status,
        }
        if self.scope:
            payload["scope"] = self.scope
        return payload


def pending_capacity_error(scope: str) -> ProjectAuthoringCapacityError:
    normalized = "agent" if scope == "agent" else "global"
    return ProjectAuthoringCapacityError(
        code="project_authoring_pending_limit",
        message=f"Project authoring pending request capacity reached for {normalized} scope",
        status=429,
        scope=normalized,
    )


def outbox_capacity_error() -> ProjectAuthoringCapacityError:
    return ProjectAuthoringCapacityError(
        code="project_authoring_outbox_full",
        message="Project authoring recurrence outbox capacity reached",
        status=503,
        scope="outbox",
    )


def maintenance_capacity_error() -> ProjectAuthoringCapacityError:
    return ProjectAuthoringCapacityError(
        code="project_maintenance_pending_limit",
        message="Project maintenance pending request capacity reached",
        status=429,
        scope="project",
    )


def feature_disabled_error(feature: str) -> ProjectAuthoringCapacityError:
    normalized = "recurrence" if feature == "recurrence" else "authoring"
    return ProjectAuthoringCapacityError(
        code=f"project_{normalized}_disabled",
        message=f"Project {normalized} is disabled",
        status=503,
        retryable=False,
        scope=normalized,
    )
