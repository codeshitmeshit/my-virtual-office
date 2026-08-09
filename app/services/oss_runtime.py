"""OSS 活动配置的验证与原子运行时快照。"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol

from .oss_settings import (
    OssConnectionConfig,
    OssSettingsStore,
    OssSettingsValidationError,
    OssSettingsView,
)


_LOGGER = logging.getLogger(__name__)


class OssRuntimeError(RuntimeError):
    code = "oss_runtime_error"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class OssConfigurationUnavailable(OssRuntimeError):
    code = "oss_configuration_unavailable"


class OssConnectionValidator(Protocol):
    def probe_bucket(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ActiveOssContext:
    config: OssConnectionConfig
    provider: OssConnectionValidator
    revision: int


ProviderFactory = Callable[[OssConnectionConfig], OssConnectionValidator]


class OssRuntime:
    def __init__(self, store: OssSettingsStore, provider_factory: ProviderFactory):
        self._store = store
        self._provider_factory = provider_factory
        self._lock = threading.RLock()
        self._activation_lock = threading.Lock()
        self._active_snapshot: ActiveOssContext | None = None
        persisted = self._store.load_active()
        if persisted is not None:
            self._active_snapshot = ActiveOssContext(
                config=persisted,
                provider=self._provider_factory(persisted),
                revision=1,
            )

    def settings_view(self) -> OssSettingsView:
        with self._lock:
            snapshot = self._active_snapshot
        if snapshot is None:
            return OssSettingsView(
                endpoint="",
                bucket="",
                access_key_id="",
                configured=False,
                secret_configured=False,
            )
        return snapshot.config.to_settings_view()

    def active_context(self) -> ActiveOssContext:
        # 网络请求只持有完整快照引用，不持锁；旧长传输不会混入新配置字段。
        with self._lock:
            snapshot = self._active_snapshot
        if snapshot is None:
            raise OssConfigurationUnavailable(
                "Alibaba Cloud OSS is not configured",
                code="oss_configuration_unavailable",
            )
        return snapshot

    def test_and_activate(self, candidate: Mapping[str, object]) -> OssSettingsView:
        # 验证、落盘和内存交换必须串行，否则两个候选可能造成磁盘与内存最终值不一致。
        with self._activation_lock:
            return self._test_and_activate_locked(candidate)

    def _test_and_activate_locked(
        self, candidate: Mapping[str, object]
    ) -> OssSettingsView:
        if not isinstance(candidate, Mapping):
            raise OssSettingsValidationError("OSS settings payload is invalid")
        with self._lock:
            previous = self._active_snapshot
        submitted_secret = candidate.get("accessKeySecret")
        secret = str(submitted_secret or "").strip()
        if not secret and previous is not None:
            secret = previous.config.access_key_secret

        config = OssConnectionConfig.create(
            endpoint=candidate.get("endpoint"),
            bucket=candidate.get("bucket"),
            access_key_id=candidate.get("accessKeyId"),
            access_key_secret=secret,
        )
        provider = self._provider_factory(config)
        try:
            # 探测只读访问；失败时既不写文件，也不改变当前活动 context。
            provider.probe_bucket()
        except Exception as exc:
            code = str(getattr(exc, "code", "oss_connection_test_failed"))
            _LOGGER.warning("OSS connection validation failed code=%s", code)
            raise

        self._store.write_active(config)
        with self._lock:
            current_revision = self._active_snapshot.revision if self._active_snapshot else 0
            self._active_snapshot = ActiveOssContext(
                config=config,
                provider=provider,
                revision=current_revision + 1,
            )
            activated = self._active_snapshot
        _LOGGER.info("OSS settings activated revision=%s", activated.revision)
        return activated.config.to_settings_view()
