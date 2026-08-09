"""受现有管理令牌边界保护的 OSS 设置 HTTP 适配。"""

from __future__ import annotations

import re
from typing import Callable

from services.oss_settings import OssSettingsError, OssSettingsValidationError
from services.oss_storage import OssStorageError

from .http import JsonBodyError, read_json, send_json


GET_PATH = "/api/settings/oss"
ACTIVATE_PATH = "/api/settings/oss/test-and-activate"
MAX_BODY_BYTES = 64 * 1024
_runtime_provider: Callable[[], object] | None = None
_SAFE_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def configure_runtime(provider: Callable[[], object]) -> None:
    global _runtime_provider
    _runtime_provider = provider


def _runtime():
    if _runtime_provider is None:
        raise RuntimeError("OSS settings runtime is not configured")
    return _runtime_provider()


def _error(exc: BaseException) -> dict[str, object]:
    if isinstance(exc, OssSettingsValidationError):
        messages = {
            "oss_endpoint_invalid": "OSS Endpoint must be a valid HTTP(S) address",
            "oss_region_unresolved": "OSS region cannot be derived from endpoint",
            "oss_bucket_invalid": "OSS Bucket name is invalid",
            "oss_access_key_id_invalid": "OSS AccessKey ID is missing or invalid",
            "oss_access_key_secret_invalid": "OSS AccessKey Secret is missing or invalid",
            "oss_settings_invalid": "OSS settings are invalid",
        }
        safe_code = exc.code if exc.code in messages else "oss_settings_invalid"
        return {
            "ok": False,
            "code": safe_code,
            "error": messages[safe_code],
            "_status": 400,
        }
    if isinstance(exc, OssStorageError):
        statuses = {
            "oss_authentication_failed": 400,
            "oss_bucket_inaccessible": 400,
            "oss_connectivity_failed": 503,
            "oss_dependency_unavailable": 503,
            "oss_provider_operation_failed": 502,
        }
        safe_code = exc.code if exc.code in statuses else "oss_provider_operation_failed"
        status = statuses[safe_code]
        messages = {
            "oss_authentication_failed": "OSS authentication or authorization failed",
            "oss_bucket_inaccessible": "OSS bucket is missing or inaccessible",
            "oss_connectivity_failed": "Alibaba Cloud OSS is unreachable",
            "oss_dependency_unavailable": "Alibaba Cloud OSS SDK V2 is unavailable",
            "oss_provider_operation_failed": "Alibaba Cloud OSS validation failed",
        }
        payload: dict[str, object] = {
            "ok": False,
            "code": safe_code,
            "error": messages.get(safe_code, "Alibaba Cloud OSS validation failed"),
            "_status": status,
        }
        request_id = str(exc.request_id or "")
        if _SAFE_REQUEST_ID_RE.fullmatch(request_id):
            payload["requestId"] = request_id
        return payload
    if isinstance(exc, OssSettingsError):
        return {
            "ok": False,
            "code": exc.code,
            "error": "OSS settings are unavailable",
            "_status": 500,
        }
    return {
        "ok": False,
        "code": "oss_settings_failed",
        "error": "OSS settings operation failed",
        "_status": 500,
    }


def handle_get(handler, parsed_url) -> bool:
    if parsed_url.path != GET_PATH:
        return False
    try:
        view = _runtime().settings_view()
        return send_json(handler, {"ok": True, "settings": view.to_dict()})
    except Exception as exc:
        return send_json(handler, _error(exc))


def handle_post(handler, parsed_url) -> bool:
    if parsed_url.path != ACTIVATE_PATH:
        return False
    try:
        body = read_json(handler, max_bytes=MAX_BODY_BYTES)
        if not isinstance(body, dict):
            raise OssSettingsValidationError("OSS settings payload is invalid")
        view = _runtime().test_and_activate(body)
        return send_json(handler, {"ok": True, "settings": view.to_dict()})
    except JsonBodyError:
        return send_json(
            handler,
            {
                "ok": False,
                "code": "invalid_json",
                "error": "Request body must be valid JSON",
                "_status": 400,
            },
        )
    except Exception as exc:
        # route 只序列化稳定错误字段，绝不回显 candidate 或原始 provider 异常。
        return send_json(handler, _error(exc))


def handle_put(handler, parsed_url) -> bool:
    return False


def handle_delete(handler, parsed_url) -> bool:
    return False
