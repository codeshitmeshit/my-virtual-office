import io
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.oss_runtime import ActiveOssContext, OssConfigurationUnavailable  # noqa: E402
from services.oss_settings import OssConnectionConfig  # noqa: E402
from services.oss_storage import (  # noqa: E402
    ObjectRef,
    OssStorageError,
    OssStorageService,
    ProviderObjectMetadata,
    ProviderObjectPage,
)


def runtime_config():
    return OssConnectionConfig.create(
        endpoint="https://oss-cn-hangzhou.aliyuncs.com",
        bucket="vo-materials",
        access_key_id="LTAI-test",
        access_key_secret="secret-sentinel",
    )


class FakeProvider:
    def __init__(self):
        self.objects = {}
        self.download_calls = 0
        self.calls = []
        self.failure = None

    def _fail(self):
        if self.failure:
            failure = self.failure
            self.failure = None
            raise failure

    def upload_from(self, key, reader, *, content_type=None):
        self.calls.append(("upload", key))
        self._fail()
        chunks = []
        while True:
            chunk = reader.read(7)
            if not chunk:
                break
            chunks.append(chunk)
        content = b"".join(chunks)
        metadata = ProviderObjectMetadata(
            key=key,
            size=len(content),
            content_type=content_type,
            etag=f"etag-{len(content)}",
            last_modified=datetime.now(timezone.utc),
        )
        self.objects[key] = (content, metadata)
        return metadata

    def download_to(self, key, sink, *, chunk_size):
        self.calls.append(("download", key))
        self._fail()
        self.download_calls += 1
        if key not in self.objects:
            raise OssStorageError("Object not found", code="oss_not_found")
        content, metadata = self.objects[key]
        for offset in range(0, len(content), min(chunk_size, 5)):
            sink.write(content[offset : offset + min(chunk_size, 5)])
        return metadata

    def head(self, key):
        self.calls.append(("head", key))
        self._fail()
        if key not in self.objects:
            raise OssStorageError("Object not found", code="oss_not_found")
        return self.objects[key][1]

    def exists(self, key):
        self.calls.append(("exists", key))
        self._fail()
        return key in self.objects

    def delete(self, key):
        self.calls.append(("delete", key))
        self._fail()
        self.objects.pop(key, None)

    def list(self, prefix, *, continuation_token=None, limit=100):
        self.calls.append(("list", prefix))
        self._fail()
        keys = sorted(key for key in self.objects if key.startswith(prefix))
        offset = int(continuation_token or 0)
        selected = keys[offset : offset + limit]
        next_token = str(offset + limit) if offset + limit < len(keys) else None
        items = [replace(self.objects[key][1], content_type=None) for key in selected]
        return ProviderObjectPage(items=tuple(items), next_token=next_token)


def service(provider=None):
    provider = provider or FakeProvider()
    context = ActiveOssContext(runtime_config(), provider, 1)
    return OssStorageService(lambda: context, transfer_buffer_size=8), provider


def test_save_is_internal_and_restore_occurs_only_when_explicitly_requested():
    storage, provider = service()

    saved = storage.save("meeting", "notes/周会.md", io.BytesIO(b"hello world"), content_type="text/markdown")

    assert provider.download_calls == 0
    serialized = json.dumps(saved.to_dict(), ensure_ascii=False)
    assert "http" not in serialized
    assert "vo-materials" not in serialized
    assert "vo/v1/" not in serialized
    assert saved.content_type == "text/markdown"

    sink = io.BytesIO()
    restored = storage.restore_to("meeting", saved.ref, sink)
    assert sink.getvalue() == b"hello world"
    assert restored.ref == saved.ref
    assert provider.download_calls == 1


def test_scopes_can_reuse_object_id_but_cannot_use_each_others_reference():
    storage, provider = service()
    first = storage.save("integration-a", "same", io.BytesIO(b"a"))
    second = storage.save("integration-b", "same", io.BytesIO(b"b"))
    calls_before = len(provider.calls)

    with pytest.raises(OssStorageError) as error:
        storage.metadata("integration-b", first.ref)

    assert error.value.code == "oss_scope_mismatch"
    assert len(provider.calls) == calls_before
    sink = io.BytesIO()
    storage.restore_to("integration-b", second.ref, sink)
    assert sink.getvalue() == b"b"


def test_overwrite_delete_exists_and_not_found_have_deterministic_semantics():
    storage, _provider = service()
    original = storage.save("assets", "report", io.BytesIO(b"old"))
    replacement = storage.save("assets", "report", io.BytesIO(b"new content"))

    assert original.ref == replacement.ref
    sink = io.BytesIO()
    storage.restore_to("assets", replacement.ref, sink)
    assert sink.getvalue() == b"new content"
    assert storage.exists("assets", replacement.ref) is True

    storage.delete("assets", replacement.ref)
    assert storage.exists("assets", replacement.ref) is False
    with pytest.raises(OssStorageError) as error:
        storage.restore_to("assets", replacement.ref, io.BytesIO())
    assert error.value.code == "oss_not_found"


def test_list_is_scope_limited_paginated_and_content_type_is_optional():
    storage, _provider = service()
    for object_id in ("a", "b", "c"):
        storage.save("one", object_id, io.BytesIO(object_id.encode()), content_type="text/plain")
    storage.save("two", "hidden", io.BytesIO(b"hidden"))

    first_page = storage.list("one", limit=2)
    second_page = storage.list("one", limit=2, continuation_token=first_page.next_token)

    assert [item.ref.object_id for item in first_page.items] == ["a", "b"]
    assert [item.ref.object_id for item in second_page.items] == ["c"]
    assert all(item.content_type is None for item in first_page.items + second_page.items)
    assert first_page.next_token
    with pytest.raises(OssStorageError) as error:
        storage.list("two", continuation_token=first_page.next_token)
    assert error.value.code == "oss_scope_mismatch"


def test_large_stream_uses_bounded_reads_and_writes():
    storage, _provider = service()

    class BoundedReader(io.BytesIO):
        def read(self, size=-1):
            assert 0 < size <= 8
            return super().read(size)

    class BoundedSink(io.BytesIO):
        def write(self, value):
            assert len(value) <= 8
            return super().write(value)

    content = b"0123456789" * 100
    saved = storage.save("large", "blob", BoundedReader(content))
    sink = BoundedSink()
    storage.restore_to("large", saved.ref, sink)
    assert sink.getvalue() == content


def test_provider_failure_is_categorized_without_secret_or_content():
    storage, provider = service()
    provider.failure = RuntimeError("provider leaked secret-sentinel and full-content")

    with pytest.raises(OssStorageError) as error:
        storage.save("safe", "object", io.BytesIO(b"full-content"))

    assert error.value.code == "oss_provider_operation_failed"
    assert "secret-sentinel" not in str(error.value)
    assert "full-content" not in str(error.value)


def test_missing_runtime_configuration_sends_no_provider_request():
    def unavailable():
        raise OssConfigurationUnavailable("not configured")

    storage = OssStorageService(unavailable)
    with pytest.raises(OssStorageError) as error:
        storage.save("integration", "object", io.BytesIO(b"data"))
    assert error.value.code == "oss_configuration_unavailable"


def test_invalid_and_oversized_identifiers_are_rejected_before_provider():
    storage, provider = service()
    for integration_id, object_id in (("", "a"), ("a", ""), ("a", "x" * 2000)):
        with pytest.raises(OssStorageError) as error:
            storage.save(integration_id, object_id, io.BytesIO(b"data"))
        assert error.value.code == "oss_invalid_identifier"
    assert provider.calls == []


def test_object_reference_round_trip_is_stable_and_scope_bound():
    ref = ObjectRef.for_scope("integration", "folder/对象.txt")
    restored = ObjectRef.parse(ref.to_string())
    assert restored == ref
    assert "integration" not in ref.to_string()
