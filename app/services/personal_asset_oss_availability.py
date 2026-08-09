"""Safe, lazy projection of the VO OSS runtime availability."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from .oss_runtime import OssConfigurationUnavailable


class PersonalAssetOssAvailability:
    """Lazily verifies the active OSS context and read-only bucket access."""

    def __init__(
        self,
        context_provider: Callable[[], object],
        *,
        now: Callable[[], datetime] | None = None,
    ):
        self._context_provider = context_provider
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _checked_at(self) -> str:
        value = self._now()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def check(self) -> dict[str, str]:
        checked_at = self._checked_at()
        try:
            context = self._context_provider()
            provider = getattr(context, "provider", None)
            probe_bucket = getattr(provider, "probe_bucket", None)
            if not callable(probe_bucket):
                raise RuntimeError("OSS runtime provider cannot probe the bucket")
            probe_bucket()
        except OssConfigurationUnavailable:
            return {
                "status": "unconfigured",
                "checkedAt": checked_at,
                "code": "oss_configuration_unavailable",
            }
        except Exception:
            return {
                "status": "unavailable",
                "checkedAt": checked_at,
                "code": "oss_runtime_unavailable",
            }
        return {"status": "available", "checkedAt": checked_at}
