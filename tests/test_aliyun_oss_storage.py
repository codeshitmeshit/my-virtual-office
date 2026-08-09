import io
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.aliyun_oss_storage import AliyunOssProvider, build_client  # noqa: E402
from services.oss_settings import OssConnectionConfig  # noqa: E402
from services.oss_storage import OssStorageError  # noqa: E402


def config():
    return OssConnectionConfig.create(
        endpoint="https://oss-cn-hangzhou.aliyuncs.com",
        bucket="vo-materials",
        access_key_id="LTAI-static",
        access_key_secret="static-secret",
    )


class Request:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeServiceError(Exception):
    def __init__(self, *, status_code=500, code="InternalError", request_id="request-1"):
        super().__init__("provider detail must stay private")
        self.status_code = status_code
        self.code = code
        self.request_id = request_id


class FakeOperationError(Exception):
    def __init__(self, error):
        super().__init__("operation failed")
        self._error = error

    def unwrap(self):
        return self._error


class FakeBody:
    def __init__(self, content):
        self.content = content
        self.closed = False
        self.block_sizes = []

    def iter_bytes(self, **kwargs):
        block_size = kwargs["block_size"]
        self.block_sizes.append(block_size)
        for offset in range(0, len(self.content), block_size):
            yield self.content[offset : offset + block_size]

    def close(self):
        self.closed = True


class FakeUploader:
    def __init__(self, client):
        self.client = client

    def upload_from(self, request, reader):
        chunks = []
        while True:
            chunk = reader.read(4)
            if not chunk:
                break
            chunks.append(chunk)
        self.client.uploads.append((request, b"".join(chunks)))
        return SimpleNamespace(etag="upload-etag")


class FakeClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self.requests = []
        self.uploads = []
        self.body = FakeBody(b"download-content")
        self.failure = None

    def _maybe_fail(self):
        if self.failure:
            failure = self.failure
            self.failure = None
            raise failure

    def uploader(self, **kwargs):
        self.requests.append(("uploader", kwargs))
        return FakeUploader(self)

    def head_object(self, request):
        self._maybe_fail()
        self.requests.append(("head", request))
        return SimpleNamespace(
            content_length=16,
            content_type="text/plain",
            etag="head-etag",
            last_modified=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    def get_object(self, request):
        self._maybe_fail()
        self.requests.append(("get", request))
        return SimpleNamespace(
            content_length=len(self.body.content),
            content_type="application/octet-stream",
            etag="get-etag",
            last_modified=None,
            body=self.body,
        )

    def delete_object(self, request):
        self._maybe_fail()
        self.requests.append(("delete", request))
        return SimpleNamespace()

    def list_objects_v2(self, request):
        self._maybe_fail()
        self.requests.append(("list", request))
        return SimpleNamespace(
            contents=[
                SimpleNamespace(
                    key=request.prefix + "YQ",
                    size=1,
                    etag="etag-a",
                    last_modified=None,
                )
            ],
            next_continuation_token="next-provider-token",
        )


class FakeSdk:
    def __init__(self):
        self.static_credentials = []
        self.environment_provider_calls = 0
        outer = self

        class StaticCredentialsProvider:
            def __init__(self, *, access_key_id, access_key_secret):
                outer.static_credentials.append((access_key_id, access_key_secret))

        class EnvironmentVariableCredentialsProvider:
            def __init__(self):
                outer.environment_provider_calls += 1

        self.credentials = SimpleNamespace(
            StaticCredentialsProvider=StaticCredentialsProvider,
            EnvironmentVariableCredentialsProvider=EnvironmentVariableCredentialsProvider,
        )
        self.config = SimpleNamespace(load_default=lambda: SimpleNamespace())
        self.clients = []

        def client_factory(cfg):
            client = FakeClient(cfg)
            self.clients.append(client)
            return client

        self.Client = client_factory
        self.PutObjectRequest = Request
        self.GetObjectRequest = Request
        self.HeadObjectRequest = Request
        self.DeleteObjectRequest = Request
        self.ListObjectsV2Request = Request
        self.exceptions = SimpleNamespace(
            ServiceError=FakeServiceError,
            OperationError=FakeOperationError,
        )


def provider():
    sdk = FakeSdk()
    return AliyunOssProvider(config(), sdk=sdk), sdk, sdk.clients[0]


def test_build_client_uses_only_explicit_static_credentials(monkeypatch):
    monkeypatch.setenv("OSS_ACCESS_KEY_ID", "environment-id")
    monkeypatch.setenv("OSS_ACCESS_KEY_SECRET", "environment-secret")
    sdk = FakeSdk()

    client = build_client(config(), sdk=sdk)

    assert sdk.static_credentials == [("LTAI-static", "static-secret")]
    assert sdk.environment_provider_calls == 0
    assert client.cfg.credentials_provider is not None
    assert client.cfg.region == "cn-hangzhou"
    assert client.cfg.endpoint == "https://oss-cn-hangzhou.aliyuncs.com"


def test_probe_is_read_only_and_limited_to_vo_root():
    value, _sdk, client = provider()

    value.probe_bucket()

    assert len(client.requests) == 1
    operation, request = client.requests[0]
    assert operation == "list"
    assert request.bucket == "vo-materials"
    assert request.prefix == "vo/v1/"
    assert request.max_keys == 1


def test_upload_uses_uploader_stream_and_returns_head_metadata():
    value, _sdk, client = provider()

    result = value.upload_from("vo/v1/caller/object", io.BytesIO(b"stream-body"), content_type="text/plain")

    request, content = client.uploads[0]
    assert request.bucket == "vo-materials"
    assert request.key == "vo/v1/caller/object"
    assert request.content_type == "text/plain"
    assert content == b"stream-body"
    assert result.size == 16
    assert result.content_type == "text/plain"
    assert any(operation == "head" for operation, _ in client.requests)


def test_download_iterates_with_bounded_blocks_and_always_closes_body():
    value, _sdk, client = provider()
    sink = io.BytesIO()

    result = value.download_to("vo/v1/caller/object", sink, chunk_size=5)

    assert sink.getvalue() == b"download-content"
    assert client.body.block_sizes == [5]
    assert client.body.closed is True
    assert result.size == len(b"download-content")


def test_list_maps_provider_metadata_and_continuation_token():
    value, _sdk, client = provider()

    page = value.list("vo/v1/caller/", continuation_token="current", limit=25)

    operation, request = client.requests[-1]
    assert operation == "list"
    assert request.continuation_token == "current"
    assert request.max_keys == 25
    assert page.items[0].content_type is None
    assert page.next_token == "next-provider-token"


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (FakeServiceError(status_code=404, code="NoSuchKey"), "oss_not_found"),
        (FakeServiceError(status_code=403, code="AccessDenied"), "oss_authentication_failed"),
        (FakeOperationError(TimeoutError("timeout")), "oss_connectivity_failed"),
        (FakeServiceError(status_code=500), "oss_provider_operation_failed"),
    ],
)
def test_sdk_errors_are_normalized_without_raw_provider_message(failure, expected_code):
    value, _sdk, client = provider()
    client.failure = failure

    with pytest.raises(OssStorageError) as error:
        value.head("vo/v1/caller/object")

    assert error.value.code == expected_code
    assert error.value.request_id in {"", "request-1"}
    assert "provider detail" not in str(error.value)
