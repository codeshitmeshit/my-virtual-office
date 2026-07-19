"""Feature-gated startup reconciliation for the global HR system Agent."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Mapping

from .hr_lifecycle import HRLifecycleAdapter, hr_public_state


HR_FEATURE_ENV = "VO_HR_ENABLED"
Environment = Mapping[str, str]


def is_hr_enabled(environ: Environment | None = None) -> bool:
    env = environ if environ is not None else os.environ
    raw = env.get(HR_FEATURE_ENV)
    if raw is None or str(raw).strip() == "":
        return True
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "enabled"}


@dataclass(frozen=True, slots=True)
class HRBootstrapResult:
    enabled: bool
    attempted: bool
    state: Mapping[str, object] | None = None
    error: str = ""


class HRBootstrap:
    """Lazily construct HR dependencies only after the feature gate passes."""

    def __init__(
        self,
        adapter_factory: Callable[[], HRLifecycleAdapter],
        *,
        enabled: Callable[[], bool] = is_hr_enabled,
    ):
        self._adapter_factory = adapter_factory
        self._enabled = enabled

    def reconcile_startup(self) -> HRBootstrapResult:
        if not self._enabled():
            return HRBootstrapResult(enabled=False, attempted=False)
        try:
            state = self._adapter_factory().reconcile()
            return HRBootstrapResult(
                enabled=True,
                attempted=True,
                state=hr_public_state(state),
                error=state.last_error,
            )
        except Exception as exc:
            return HRBootstrapResult(
                enabled=True,
                attempted=True,
                error=str(exc).strip() or exc.__class__.__name__,
            )
