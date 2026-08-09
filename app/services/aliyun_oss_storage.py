"""阿里云 OSS Python SDK V2 的唯一适配边界。"""

from __future__ import annotations

from typing import BinaryIO

from .oss_settings import OssConnectionConfig
from .oss_storage import (
    OBJECT_ROOT,
    OssStorageError,
    ProviderObjectMetadata,
    ProviderObjectPage,
)


def _load_sdk():
    try:
        import alibabacloud_oss_v2 as oss
    except ImportError as exc:
        raise OssStorageError(
            "Alibaba Cloud OSS SDK V2 is not installed",
            code="oss_dependency_unavailable",
        ) from exc
    return oss


def build_client(config: OssConnectionConfig, *, sdk=None):
    """显式注入应用设置凭证，禁止落入 SDK 环境变量凭证链。"""

    sdk = sdk or _load_sdk()
    credentials = sdk.credentials.StaticCredentialsProvider(
        access_key_id=config.access_key_id,
        access_key_secret=config.access_key_secret,
    )
    client_config = sdk.config.load_default()
    client_config.credentials_provider = credentials
    client_config.region = config.region
    client_config.endpoint = config.endpoint
    return sdk.Client(client_config)


def _classified_error(sdk, exc: Exception) -> OssStorageError:
    service_error = getattr(getattr(sdk, "exceptions", object()), "ServiceError", ())
    operation_error = getattr(getattr(sdk, "exceptions", object()), "OperationError", ())
    if service_error and isinstance(exc, service_error):
        status = int(getattr(exc, "status_code", 0) or 0)
        provider_code = str(getattr(exc, "code", "") or "")
        request_id = str(getattr(exc, "request_id", "") or "")
        if status == 404 or provider_code in {"NoSuchKey", "NoSuchObject"}:
            return OssStorageError(
                "OSS object was not found",
                code="oss_not_found",
                request_id=request_id,
            )
        if status in {401, 403} or provider_code in {
            "AccessDenied",
            "InvalidAccessKeyId",
            "SignatureDoesNotMatch",
            "SecurityTokenExpired",
        }:
            return OssStorageError(
                "OSS authentication or authorization failed",
                code="oss_authentication_failed",
                request_id=request_id,
            )
        return OssStorageError(
            "Alibaba Cloud OSS operation failed",
            code="oss_provider_operation_failed",
            request_id=request_id,
        )
    if operation_error and isinstance(exc, operation_error):
        try:
            underlying = exc.unwrap()
        except Exception:
            underlying = None
        if isinstance(underlying, (TimeoutError, ConnectionError, OSError)):
            return OssStorageError(
                "Alibaba Cloud OSS is unreachable",
                code="oss_connectivity_failed",
            )
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return OssStorageError(
            "Alibaba Cloud OSS is unreachable", code="oss_connectivity_failed"
        )
    return OssStorageError(
        "Alibaba Cloud OSS operation failed",
        code="oss_provider_operation_failed",
    )


class AliyunOssProvider:
    def __init__(self, config: OssConnectionConfig, *, sdk=None, client=None):
        self._sdk = sdk or _load_sdk()
        self._bucket = config.bucket
        self._client = client or build_client(config, sdk=self._sdk)

    def _call(self, callback):
        try:
            return callback()
        except OssStorageError:
            raise
        except Exception as exc:
            # 原始 SDK 异常可能包含请求目标或响应细节，只向上返回稳定安全字段。
            raise _classified_error(self._sdk, exc) from exc

    def probe_bucket(self) -> None:
        try:
            self._call(
                lambda: self._client.list_objects_v2(
                    self._sdk.ListObjectsV2Request(
                        bucket=self._bucket,
                        prefix=OBJECT_ROOT,
                        max_keys=1,
                    )
                )
            )
        except OssStorageError as exc:
            if exc.code == "oss_not_found":
                raise OssStorageError(
                    "OSS bucket is missing or inaccessible",
                    code="oss_bucket_inaccessible",
                    request_id=exc.request_id,
                ) from exc
            raise

    def upload_from(
        self, key: str, reader: BinaryIO, *, content_type: str | None = None
    ) -> ProviderObjectMetadata:
        request = self._sdk.PutObjectRequest(
            bucket=self._bucket,
            key=key,
            content_type=content_type,
        )
        # SDK Uploader 负责 multipart 与有界 part buffer，VO 不设置对象总大小上限。
        self._call(lambda: self._client.uploader().upload_from(request, reader))
        return self.head(key)

    def download_to(
        self, key: str, sink: BinaryIO, *, chunk_size: int
    ) -> ProviderObjectMetadata:
        response = self._call(
            lambda: self._client.get_object(
                self._sdk.GetObjectRequest(bucket=self._bucket, key=key)
            )
        )
        body = getattr(response, "body", None)
        if body is None:
            raise OssStorageError(
                "Alibaba Cloud OSS returned an empty response body",
                code="oss_provider_operation_failed",
            )
        try:
            for chunk in body.iter_bytes(block_size=chunk_size):
                if chunk:
                    self._write_all(sink, chunk)
        except OssStorageError:
            raise
        except Exception as exc:
            raise _classified_error(self._sdk, exc) from exc
        finally:
            # 无论 sink 或网络迭代是否失败，都必须释放 HTTP response body。
            body.close()
        return ProviderObjectMetadata(
            key=key,
            size=int(getattr(response, "content_length", 0) or 0),
            content_type=getattr(response, "content_type", None),
            etag=getattr(response, "etag", None),
            last_modified=getattr(response, "last_modified", None),
        )

    @staticmethod
    def _write_all(sink: BinaryIO, chunk: bytes) -> None:
        remaining = memoryview(chunk)
        while remaining:
            written = sink.write(remaining)
            if written is None:
                return
            if written <= 0:
                raise OssStorageError(
                    "Restore sink did not accept data",
                    code="oss_provider_operation_failed",
                )
            remaining = remaining[written:]

    def head(self, key: str) -> ProviderObjectMetadata:
        response = self._call(
            lambda: self._client.head_object(
                self._sdk.HeadObjectRequest(bucket=self._bucket, key=key)
            )
        )
        return ProviderObjectMetadata(
            key=key,
            size=int(getattr(response, "content_length", 0) or 0),
            content_type=getattr(response, "content_type", None),
            etag=getattr(response, "etag", None),
            last_modified=getattr(response, "last_modified", None),
        )

    def exists(self, key: str) -> bool:
        try:
            self.head(key)
            return True
        except OssStorageError as exc:
            if exc.code == "oss_not_found":
                return False
            raise

    def delete(self, key: str) -> None:
        self._call(
            lambda: self._client.delete_object(
                self._sdk.DeleteObjectRequest(bucket=self._bucket, key=key)
            )
        )

    def list(
        self,
        prefix: str,
        *,
        continuation_token: str | None = None,
        limit: int = 100,
    ) -> ProviderObjectPage:
        response = self._call(
            lambda: self._client.list_objects_v2(
                self._sdk.ListObjectsV2Request(
                    bucket=self._bucket,
                    prefix=prefix,
                    continuation_token=continuation_token,
                    max_keys=limit,
                )
            )
        )
        items = tuple(
            ProviderObjectMetadata(
                key=str(getattr(item, "key", "") or ""),
                size=int(getattr(item, "size", 0) or 0),
                content_type=None,
                etag=getattr(item, "etag", None),
                last_modified=getattr(item, "last_modified", None),
            )
            for item in (getattr(response, "contents", None) or ())
        )
        return ProviderObjectPage(
            items=items,
            next_token=getattr(response, "next_continuation_token", None),
        )
