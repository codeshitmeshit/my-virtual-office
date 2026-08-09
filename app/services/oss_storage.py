"""面向 VO 后端集成的调用方隔离对象存储边界。"""

from __future__ import annotations

import base64
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO, Callable, Protocol

from .oss_runtime import ActiveOssContext, OssConfigurationUnavailable


OBJECT_ROOT = "vo/v1/"
MAX_OSS_KEY_BYTES = 1023
DEFAULT_TRANSFER_BUFFER_SIZE = 1024 * 1024
_LOGGER = logging.getLogger(__name__)


class OssStorageError(RuntimeError):
    code = "oss_provider_operation_failed"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        request_id: str = "",
    ):
        super().__init__(message)
        if code:
            self.code = code
        self.request_id = str(request_id or "")


def _b64encode(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _b64decode(value: str) -> str:
    try:
        padded = value + "=" * (-len(value) % 4)
        return base64.b64decode(padded, altchars=b"-_", validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise OssStorageError(
            "Object reference is invalid", code="oss_invalid_identifier"
        ) from exc


def _scope_fingerprint(integration_id: str) -> str:
    return hashlib.sha256(integration_id.encode("utf-8")).hexdigest()[:32]


def _validated_identifier(value: object, name: str, *, maximum: int = 2048) -> str:
    text = str(value or "").strip()
    if not text or len(text.encode("utf-8")) > maximum or "\x00" in text:
        raise OssStorageError(
            f"{name} is invalid", code="oss_invalid_identifier"
        )
    return text


@dataclass(frozen=True, slots=True)
class ObjectRef:
    object_id: str
    scope_fingerprint: str

    @classmethod
    def for_scope(cls, integration_id: str, object_id: str) -> "ObjectRef":
        integration = _validated_identifier(integration_id, "integration_id", maximum=256)
        logical_id = _validated_identifier(object_id, "object_id")
        return cls(
            object_id=logical_id,
            scope_fingerprint=_scope_fingerprint(integration),
        )

    @classmethod
    def parse(cls, value: str) -> "ObjectRef":
        parts = str(value or "").split(":")
        if len(parts) != 4 or parts[:2] != ["oss", "v1"] or len(parts[2]) != 32:
            raise OssStorageError(
                "Object reference is invalid", code="oss_invalid_identifier"
            )
        object_id = _validated_identifier(_b64decode(parts[3]), "object_id")
        return cls(object_id=object_id, scope_fingerprint=parts[2])

    def to_string(self) -> str:
        return f"oss:v1:{self.scope_fingerprint}:{_b64encode(self.object_id)}"


@dataclass(frozen=True, slots=True)
class ProviderObjectMetadata:
    key: str
    size: int
    content_type: str | None = None
    etag: str | None = None
    last_modified: datetime | str | None = None


@dataclass(frozen=True, slots=True)
class ProviderObjectPage:
    items: tuple[ProviderObjectMetadata, ...]
    next_token: str | None = None


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    ref: ObjectRef
    size: int
    content_type: str | None = None
    etag: str | None = None
    last_modified: datetime | str | None = None

    def to_dict(self) -> dict[str, object]:
        modified = self.last_modified
        if isinstance(modified, datetime):
            modified = modified.isoformat()
        return {
            "objectRef": self.ref.to_string(),
            "objectId": self.ref.object_id,
            "size": self.size,
            "contentType": self.content_type,
            "etag": self.etag,
            "lastModified": modified,
        }


@dataclass(frozen=True, slots=True)
class ObjectPage:
    items: tuple[ObjectMetadata, ...]
    next_token: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "items": [item.to_dict() for item in self.items],
            "nextToken": self.next_token,
        }


class OssObjectProvider(Protocol):
    def upload_from(
        self, key: str, reader: BinaryIO, *, content_type: str | None = None
    ) -> ProviderObjectMetadata: ...

    def download_to(
        self, key: str, sink: BinaryIO, *, chunk_size: int
    ) -> ProviderObjectMetadata: ...

    def head(self, key: str) -> ProviderObjectMetadata: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...

    def list(
        self, prefix: str, *, continuation_token: str | None = None, limit: int = 100
    ) -> ProviderObjectPage: ...


class OssStorageService:
    def __init__(
        self,
        context_provider: Callable[[], ActiveOssContext],
        *,
        transfer_buffer_size: int = DEFAULT_TRANSFER_BUFFER_SIZE,
    ):
        if transfer_buffer_size <= 0:
            raise ValueError("transfer_buffer_size must be positive")
        self._context_provider = context_provider
        self._transfer_buffer_size = transfer_buffer_size

    def _context(self) -> ActiveOssContext:
        try:
            return self._context_provider()
        except OssConfigurationUnavailable as exc:
            raise OssStorageError(
                "Alibaba Cloud OSS is not configured",
                code="oss_configuration_unavailable",
            ) from exc

    def _scope(self, integration_id: str) -> tuple[str, str]:
        integration = _validated_identifier(integration_id, "integration_id", maximum=256)
        fingerprint = _scope_fingerprint(integration)
        return f"{OBJECT_ROOT}{_b64encode(integration)}/", fingerprint

    def _key_for_object(self, integration_id: str, object_id: str) -> tuple[str, ObjectRef]:
        prefix, fingerprint = self._scope(integration_id)
        logical_id = _validated_identifier(object_id, "object_id")
        key = prefix + _b64encode(logical_id)
        if len(key.encode("utf-8")) > MAX_OSS_KEY_BYTES:
            raise OssStorageError(
                "object_id is too long", code="oss_invalid_identifier"
            )
        return key, ObjectRef(logical_id, fingerprint)

    def _key_for_ref(self, integration_id: str, value: ObjectRef | str) -> tuple[str, ObjectRef]:
        ref = ObjectRef.parse(value) if isinstance(value, str) else value
        if not isinstance(ref, ObjectRef):
            raise OssStorageError(
                "Object reference is invalid", code="oss_invalid_identifier"
            )
        prefix, fingerprint = self._scope(integration_id)
        if ref.scope_fingerprint != fingerprint:
            # fingerprint 校验提供明确拒绝；实际 key 仍始终由当前 integration prefix 构造。
            raise OssStorageError(
                "Object reference belongs to another integration",
                code="oss_scope_mismatch",
            )
        key = prefix + _b64encode(_validated_identifier(ref.object_id, "object_id"))
        if len(key.encode("utf-8")) > MAX_OSS_KEY_BYTES:
            raise OssStorageError(
                "object_id is too long", code="oss_invalid_identifier"
            )
        return key, ref

    def _provider_call(self, action: str, fingerprint: str, callback):
        try:
            return callback()
        except OssStorageError as exc:
            _LOGGER.warning(
                "OSS operation failed action=%s scope=%s code=%s request_id=%s",
                action,
                fingerprint,
                exc.code,
                exc.request_id,
            )
            raise
        except Exception as exc:
            _LOGGER.warning(
                "OSS operation failed action=%s scope=%s code=oss_provider_operation_failed",
                action,
                fingerprint,
            )
            raise OssStorageError(
                "Alibaba Cloud OSS operation failed",
                code="oss_provider_operation_failed",
            ) from exc

    def _metadata_for(
        self, expected_key: str, ref: ObjectRef, provider_value: ProviderObjectMetadata
    ) -> ObjectMetadata:
        if provider_value.key != expected_key:
            raise OssStorageError(
                "Alibaba Cloud OSS returned an invalid object result",
                code="oss_provider_operation_failed",
            )
        return ObjectMetadata(
            ref=ref,
            size=int(provider_value.size),
            content_type=provider_value.content_type,
            etag=provider_value.etag,
            last_modified=provider_value.last_modified,
        )

    def save(
        self,
        integration_id: str,
        object_id: str,
        reader: BinaryIO,
        *,
        content_type: str | None = None,
    ) -> ObjectMetadata:
        if not callable(getattr(reader, "read", None)):
            raise OssStorageError("reader is invalid", code="oss_invalid_identifier")
        key, ref = self._key_for_object(integration_id, object_id)
        context = self._context()
        value = self._provider_call(
            "save",
            ref.scope_fingerprint,
            lambda: context.provider.upload_from(key, reader, content_type=content_type),
        )
        return self._metadata_for(key, ref, value)

    def restore_to(
        self,
        integration_id: str,
        ref: ObjectRef | str,
        sink: BinaryIO,
    ) -> ObjectMetadata:
        if not callable(getattr(sink, "write", None)):
            raise OssStorageError("sink is invalid", code="oss_invalid_identifier")
        key, checked_ref = self._key_for_ref(integration_id, ref)
        context = self._context()
        value = self._provider_call(
            "restore",
            checked_ref.scope_fingerprint,
            lambda: context.provider.download_to(
                key, sink, chunk_size=self._transfer_buffer_size
            ),
        )
        return self._metadata_for(key, checked_ref, value)

    def exists(self, integration_id: str, ref: ObjectRef | str) -> bool:
        key, checked_ref = self._key_for_ref(integration_id, ref)
        context = self._context()
        return bool(
            self._provider_call(
                "exists",
                checked_ref.scope_fingerprint,
                lambda: context.provider.exists(key),
            )
        )

    def metadata(self, integration_id: str, ref: ObjectRef | str) -> ObjectMetadata:
        key, checked_ref = self._key_for_ref(integration_id, ref)
        context = self._context()
        value = self._provider_call(
            "metadata",
            checked_ref.scope_fingerprint,
            lambda: context.provider.head(key),
        )
        return self._metadata_for(key, checked_ref, value)

    def delete(self, integration_id: str, ref: ObjectRef | str) -> None:
        key, checked_ref = self._key_for_ref(integration_id, ref)
        context = self._context()
        self._provider_call(
            "delete",
            checked_ref.scope_fingerprint,
            lambda: context.provider.delete(key),
        )

    def list(
        self,
        integration_id: str,
        *,
        continuation_token: str | None = None,
        limit: int = 100,
    ) -> ObjectPage:
        if not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise OssStorageError("list limit is invalid", code="oss_invalid_identifier")
        prefix, fingerprint = self._scope(integration_id)
        provider_token = self._decode_page_token(continuation_token, fingerprint)
        context = self._context()
        page = self._provider_call(
            "list",
            fingerprint,
            lambda: context.provider.list(
                prefix, continuation_token=provider_token, limit=limit
            ),
        )
        items: list[ObjectMetadata] = []
        for provider_item in page.items:
            if not provider_item.key.startswith(prefix):
                raise OssStorageError(
                    "Alibaba Cloud OSS returned an object outside the integration scope",
                    code="oss_provider_operation_failed",
                )
            encoded_id = provider_item.key[len(prefix) :]
            if not encoded_id or "/" in encoded_id:
                raise OssStorageError(
                    "Alibaba Cloud OSS returned an invalid object key",
                    code="oss_provider_operation_failed",
                )
            ref = ObjectRef(_b64decode(encoded_id), fingerprint)
            items.append(self._metadata_for(provider_item.key, ref, provider_item))
        next_token = (
            self._encode_page_token(page.next_token, fingerprint)
            if page.next_token
            else None
        )
        # ListObjectsV2 不提供 content type；不追加逐对象 HEAD，避免目录规模放大。
        return ObjectPage(items=tuple(items), next_token=next_token)

    @staticmethod
    def _encode_page_token(provider_token: str, fingerprint: str) -> str:
        return f"oss-page:v1:{fingerprint}:{_b64encode(str(provider_token))}"

    @staticmethod
    def _decode_page_token(token: str | None, fingerprint: str) -> str | None:
        if not token:
            return None
        parts = str(token).split(":")
        if len(parts) != 4 or parts[:2] != ["oss-page", "v1"]:
            raise OssStorageError(
                "Continuation token is invalid", code="oss_invalid_identifier"
            )
        if parts[2] != fingerprint:
            raise OssStorageError(
                "Continuation token belongs to another integration",
                code="oss_scope_mismatch",
            )
        return _b64decode(parts[3])
