"""阿里云 OSS 设置的私有持久化边界。"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit, urlunsplit


SCHEMA_VERSION = 1
SETTINGS_FILENAME = "oss-settings.json"
_REGION_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
_LOGGER = logging.getLogger(__name__)


class OssSettingsError(RuntimeError):
    """不携带候选配置内容的 OSS 设置错误。"""

    code = "oss_settings_unavailable"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class OssSettingsValidationError(OssSettingsError, ValueError):
    code = "oss_settings_invalid"


def _required_text(
    value: object,
    field_name: str,
    *,
    maximum: int,
    code: str = "oss_settings_invalid",
) -> str:
    text = str(value or "").strip()
    if not text or len(text) > maximum:
        raise OssSettingsValidationError(
            f"OSS setting {field_name} is missing or invalid",
            code=code,
        )
    return text


def _normalize_endpoint(value: object) -> str:
    endpoint = _required_text(
        value,
        "endpoint",
        maximum=2048,
        code="oss_endpoint_invalid",
    )
    if "://" not in endpoint:
        endpoint = f"https://{endpoint}"
    try:
        parsed = urlsplit(endpoint)
        hostname = parsed.hostname
    except ValueError as exc:
        raise OssSettingsValidationError(
            "OSS setting endpoint is invalid",
            code="oss_endpoint_invalid",
        ) from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise OssSettingsValidationError(
            "OSS setting endpoint must be an HTTP(S) service endpoint without credentials or query data",
            code="oss_endpoint_invalid",
        )
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _derive_region_from_endpoint(endpoint: str) -> str:
    """只从地域明确的阿里云标准域名推导 Region，绝不回退或猜测。"""

    hostname = (urlsplit(endpoint).hostname or "").lower()
    suffix = ".aliyuncs.com"
    region = ""
    if hostname.startswith("oss-") and hostname.endswith(suffix):
        label = hostname[len("oss-") : -len(suffix)]
        if label.endswith("-internal"):
            label = label[: -len("-internal")]
        if not label.startswith("accelerate"):
            region = label
    else:
        dual_stack_suffix = ".oss.aliyuncs.com"
        if hostname.endswith(dual_stack_suffix):
            region = hostname[: -len(dual_stack_suffix)]
    if not region or not _REGION_RE.fullmatch(region):
        raise OssSettingsValidationError(
            "OSS region cannot be derived from endpoint",
            code="oss_region_unresolved",
        )
    return region


@dataclass(frozen=True, slots=True)
class OssSettingsView:
    endpoint: str
    bucket: str
    access_key_id: str = field(repr=False)
    configured: bool = True
    secret_configured: bool = True

    def to_dict(self) -> dict[str, object]:
        """浏览器投影有意不定义 secret 字段，避免调用方误回传持久化密钥。"""

        return {
            "endpoint": self.endpoint,
            "bucket": self.bucket,
            "accessKeyId": self.access_key_id,
            "configured": self.configured,
            "secretConfigured": self.secret_configured,
        }


@dataclass(frozen=True, slots=True)
class OssConnectionConfig:
    endpoint: str
    region: str
    bucket: str
    access_key_id: str = field(repr=False)
    access_key_secret: str = field(repr=False)

    @classmethod
    def create(
        cls,
        *,
        endpoint: object,
        bucket: object,
        access_key_id: object,
        access_key_secret: object,
    ) -> "OssConnectionConfig":
        normalized_endpoint = _normalize_endpoint(endpoint)
        normalized_region = _derive_region_from_endpoint(normalized_endpoint)
        normalized_bucket = _required_text(
            bucket,
            "bucket",
            maximum=63,
            code="oss_bucket_invalid",
        ).lower()
        if not _BUCKET_RE.fullmatch(normalized_bucket):
            raise OssSettingsValidationError(
                "OSS setting bucket is invalid",
                code="oss_bucket_invalid",
            )
        return cls(
            endpoint=normalized_endpoint,
            region=normalized_region,
            bucket=normalized_bucket,
            access_key_id=_required_text(
                access_key_id,
                "accessKeyId",
                maximum=256,
                code="oss_access_key_id_invalid",
            ),
            access_key_secret=_required_text(
                access_key_secret,
                "accessKeySecret",
                maximum=1024,
                code="oss_access_key_secret_invalid",
            ),
        )

    def to_settings_view(self) -> OssSettingsView:
        return OssSettingsView(
            endpoint=self.endpoint,
            bucket=self.bucket,
            access_key_id=self.access_key_id,
            configured=True,
            secret_configured=bool(self.access_key_secret),
        )

    def _to_persisted_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "endpoint": self.endpoint,
            "bucket": self.bucket,
            "accessKeyId": self.access_key_id,
            "accessKeySecret": self.access_key_secret,
            "activatedAt": datetime.now(timezone.utc).isoformat(),
        }


class OssSettingsStore:
    """只使用构造时注入的数据目录；绝不读取 OSS 环境变量或通用 VO 配置。"""

    def __init__(
        self,
        data_dir: str | Path,
        *,
        replace: Callable[[str | bytes | os.PathLike, str | bytes | os.PathLike], None]
        = os.replace,
    ):
        self.path = Path(data_dir) / SETTINGS_FILENAME
        self._replace = replace
        self._lock = threading.RLock()

    def load_active(self) -> OssConnectionConfig | None:
        with self._lock:
            try:
                raw = self.path.read_text(encoding="utf-8")
            except FileNotFoundError:
                return None
            except OSError as exc:
                _LOGGER.warning("OSS settings load failed code=oss_settings_unavailable")
                raise OssSettingsError("OSS settings are unavailable") from exc

            try:
                payload = json.loads(raw)
                if not isinstance(payload, dict) or payload.get("schemaVersion") != SCHEMA_VERSION:
                    raise ValueError("unsupported settings schema")
                return OssConnectionConfig.create(
                    endpoint=payload.get("endpoint"),
                    bucket=payload.get("bucket"),
                    access_key_id=payload.get("accessKeyId"),
                    access_key_secret=payload.get("accessKeySecret"),
                )
            except (json.JSONDecodeError, OssSettingsValidationError, ValueError, TypeError) as exc:
                # 损坏文件可能含有真实凭证，日志和异常都只保留稳定错误类别。
                _LOGGER.warning("OSS settings load failed code=oss_settings_invalid")
                raise OssSettingsError(
                    "OSS settings are invalid", code="oss_settings_invalid"
                ) from exc

    def write_active(self, config: OssConnectionConfig) -> None:
        if not isinstance(config, OssConnectionConfig):
            raise OssSettingsValidationError("OSS settings value is invalid")
        content = json.dumps(
            config._to_persisted_dict(), ensure_ascii=False, indent=2
        ) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path: Path | None = None
            try:
                fd, temporary_name = tempfile.mkstemp(
                    prefix=f".{self.path.name}.", dir=self.path.parent
                )
                temporary_path = Path(temporary_name)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                # 凭证文件在 rename 前后都保持当前账户独占，避免短暂放宽权限。
                os.chmod(temporary_path, 0o600)
                self._replace(temporary_path, self.path)
            except OSError as exc:
                _LOGGER.warning("OSS settings write failed code=oss_settings_unavailable")
                raise OssSettingsError("OSS settings could not be saved") from exc
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
