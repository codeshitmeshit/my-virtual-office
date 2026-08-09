import json
import os
import stat
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.oss_settings import (  # noqa: E402
    OssConnectionConfig,
    OssSettingsError,
    OssSettingsStore,
    OssSettingsValidationError,
)
from services.oss_runtime import (  # noqa: E402
    OssConfigurationUnavailable,
    OssRuntime,
)


SECRET = "oss-secret-sentinel-never-expose"


def config(**overrides):
    values = {
        "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
        "bucket": "vo-materials",
        "access_key_id": "LTAI-example",
        "access_key_secret": SECRET,
    }
    values.update(overrides)
    return OssConnectionConfig.create(**values)


def test_settings_view_and_repr_never_expose_secret():
    value = config()

    view = value.to_settings_view()

    assert view.to_dict() == {
        "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
        "bucket": "vo-materials",
        "accessKeyId": "LTAI-example",
        "configured": True,
        "secretConfigured": True,
    }
    assert SECRET not in repr(value)
    assert SECRET not in repr(view)
    assert SECRET not in json.dumps(view.to_dict())


def test_private_store_round_trips_and_uses_owner_only_permissions(tmp_path):
    store = OssSettingsStore(tmp_path)

    store.write_active(config())
    loaded = OssSettingsStore(tmp_path).load_active()

    assert loaded == config()
    assert store.path == tmp_path / "oss-settings.json"
    assert stat.S_IMODE(os.stat(store.path).st_mode) == 0o600
    persisted = json.loads(store.path.read_text(encoding="utf-8"))
    assert persisted["schemaVersion"] == 1
    assert persisted["accessKeySecret"] == SECRET
    assert "region" not in persisted


@pytest.mark.parametrize(
    ("endpoint", "expected_region"),
    [
        ("https://oss-cn-hangzhou.aliyuncs.com", "cn-hangzhou"),
        ("https://oss-cn-shanghai-internal.aliyuncs.com", "cn-shanghai"),
        ("https://cn-beijing.oss.aliyuncs.com", "cn-beijing"),
    ],
)
def test_region_is_derived_from_supported_standard_endpoint(endpoint, expected_region):
    assert config(endpoint=endpoint).region == expected_region


def test_endpoint_without_scheme_defaults_to_https():
    value = config(endpoint="oss-cn-beijing.aliyuncs.com")

    assert value.endpoint == "https://oss-cn-beijing.aliyuncs.com"
    assert value.region == "cn-beijing"


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"endpoint": "ftp://oss-cn-beijing.aliyuncs.com"}, "oss_endpoint_invalid"),
        ({"bucket": "INVALID_BUCKET"}, "oss_bucket_invalid"),
        ({"access_key_id": " "}, "oss_access_key_id_invalid"),
        ({"access_key_secret": " "}, "oss_access_key_secret_invalid"),
    ],
)
def test_invalid_setting_reports_its_field(overrides, expected_code):
    with pytest.raises(OssSettingsValidationError) as error:
        config(**overrides)

    assert error.value.code == expected_code
    assert SECRET not in str(error.value)


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://oss-accelerate.aliyuncs.com",
        "https://objects.example.com",
    ],
)
def test_endpoint_without_deterministic_region_is_rejected(endpoint):
    with pytest.raises(OssSettingsValidationError) as error:
        config(endpoint=endpoint)

    assert error.value.code == "oss_region_unresolved"


def test_loading_legacy_region_ignores_it_and_rederives_from_endpoint(tmp_path):
    store = OssSettingsStore(tmp_path)
    store.path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "endpoint": "https://oss-cn-shanghai.aliyuncs.com",
                "region": "cn-hangzhou",
                "bucket": "vo-materials",
                "accessKeyId": "LTAI-example",
                "accessKeySecret": SECRET,
            }
        ),
        encoding="utf-8",
    )

    assert store.load_active().region == "cn-shanghai"


def test_oss_like_environment_variables_never_create_or_override_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("OSS_ENDPOINT", "https://attacker.invalid")
    monkeypatch.setenv("OSS_ACCESS_KEY_ID", "from-environment")
    monkeypatch.setenv("OSS_ACCESS_KEY_SECRET", "environment-secret")
    monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "also-environment")

    empty = OssSettingsStore(tmp_path)
    assert empty.load_active() is None

    empty.write_active(config())
    loaded = OssSettingsStore(tmp_path).load_active()
    assert loaded == config()
    assert "environment" not in repr(loaded)
    assert loaded.endpoint != "https://attacker.invalid"


def test_invalid_fields_are_rejected_without_echoing_secret():
    with pytest.raises(OssSettingsValidationError) as error:
        config(endpoint=" ")

    assert error.value.code == "oss_endpoint_invalid"
    assert SECRET not in str(error.value)


def test_corrupt_state_fails_safely_without_logging_file_content(tmp_path, caplog):
    path = tmp_path / "oss-settings.json"
    path.write_text('{"accessKeySecret":"' + SECRET + '"', encoding="utf-8")

    with pytest.raises(OssSettingsError) as error:
        OssSettingsStore(tmp_path).load_active()

    assert error.value.code == "oss_settings_invalid"
    assert SECRET not in str(error.value)
    assert SECRET not in caplog.text


def test_failed_atomic_replace_preserves_previous_active_file(tmp_path):
    store = OssSettingsStore(tmp_path)
    store.write_active(config())
    before = store.path.read_bytes()

    def fail_replace(_source, _target):
        raise OSError("replace unavailable")

    failing = OssSettingsStore(tmp_path, replace=fail_replace)
    with pytest.raises(OssSettingsError) as error:
        failing.write_active(config(bucket="replacement"))

    assert error.value.code == "oss_settings_unavailable"
    assert store.path.read_bytes() == before
    assert SECRET not in str(error.value)


class FakeProvider:
    def __init__(self, value, *, failure=None):
        self.config = value
        self.failure = failure
        self.probes = 0

    def probe_bucket(self):
        self.probes += 1
        if self.failure:
            raise self.failure


class RecordingFactory:
    def __init__(self):
        self.providers = []
        self.next_failure = None

    def __call__(self, value):
        provider = FakeProvider(value, failure=self.next_failure)
        self.next_failure = None
        self.providers.append(provider)
        return provider


def candidate(**overrides):
    values = {
        "endpoint": "https://oss-cn-hangzhou.aliyuncs.com",
        "bucket": "vo-materials",
        "accessKeyId": "LTAI-example",
        "accessKeySecret": SECRET,
    }
    values.update(overrides)
    return values


def test_runtime_requires_an_active_validated_configuration_without_provider_call(tmp_path):
    factory = RecordingFactory()
    runtime = OssRuntime(OssSettingsStore(tmp_path), factory)

    assert runtime.settings_view().to_dict() == {
        "endpoint": "",
        "bucket": "",
        "accessKeyId": "",
        "configured": False,
        "secretConfigured": False,
    }
    with pytest.raises(OssConfigurationUnavailable) as error:
        runtime.active_context()
    assert error.value.code == "oss_configuration_unavailable"
    assert factory.providers == []


def test_successful_test_persists_then_activates_complete_context(tmp_path):
    factory = RecordingFactory()
    store = OssSettingsStore(tmp_path)
    runtime = OssRuntime(store, factory)

    view = runtime.test_and_activate(candidate())
    context = runtime.active_context()

    assert factory.providers[0].probes == 1
    assert context.provider is factory.providers[0]
    assert context.config == config()
    assert context.revision == 1
    assert view.secret_configured is True
    assert SECRET not in repr(view)
    assert OssSettingsStore(tmp_path).load_active() == config()


def test_unresolved_region_fails_before_provider_factory_is_called(tmp_path):
    factory = RecordingFactory()
    runtime = OssRuntime(OssSettingsStore(tmp_path), factory)

    with pytest.raises(OssSettingsValidationError) as error:
        runtime.test_and_activate(candidate(endpoint="https://oss-accelerate.aliyuncs.com"))

    assert error.value.code == "oss_region_unresolved"
    assert factory.providers == []


def test_failed_replacement_preserves_old_file_and_active_context(tmp_path, caplog):
    factory = RecordingFactory()
    store = OssSettingsStore(tmp_path)
    runtime = OssRuntime(store, factory)
    runtime.test_and_activate(candidate())
    before = runtime.active_context()
    persisted_before = store.path.read_bytes()
    factory.next_failure = RuntimeError("provider rejected " + SECRET)

    with pytest.raises(RuntimeError):
        runtime.test_and_activate(candidate(bucket="replacement"))

    assert runtime.active_context() is before
    assert store.path.read_bytes() == persisted_before
    assert SECRET not in caplog.text


def test_blank_secret_keeps_active_secret_and_non_blank_replaces_it(tmp_path):
    factory = RecordingFactory()
    runtime = OssRuntime(OssSettingsStore(tmp_path), factory)
    runtime.test_and_activate(candidate())

    runtime.test_and_activate(candidate(bucket="second-bucket", accessKeySecret=""))
    retained = runtime.active_context()
    assert retained.config.access_key_secret == SECRET
    assert retained.config.bucket == "second-bucket"

    runtime.test_and_activate(candidate(accessKeySecret="replacement-secret"))
    replaced = runtime.active_context()
    assert replaced.config.access_key_secret == "replacement-secret"
    assert replaced.revision == 3


def test_existing_operation_keeps_old_context_while_new_operations_get_replacement(tmp_path):
    factory = RecordingFactory()
    runtime = OssRuntime(OssSettingsStore(tmp_path), factory)
    runtime.test_and_activate(candidate())
    existing_operation = runtime.active_context()

    runtime.test_and_activate(
        candidate(
            endpoint="https://oss-cn-shanghai.aliyuncs.com",
            bucket="replacement-bucket",
        )
    )
    new_operation = runtime.active_context()

    assert (
        existing_operation.config.endpoint,
        existing_operation.config.region,
        existing_operation.config.bucket,
    ) == (
        "https://oss-cn-hangzhou.aliyuncs.com",
        "cn-hangzhou",
        "vo-materials",
    )
    assert (
        new_operation.config.endpoint,
        new_operation.config.region,
        new_operation.config.bucket,
    ) == (
        "https://oss-cn-shanghai.aliyuncs.com",
        "cn-shanghai",
        "replacement-bucket",
    )


def test_runtime_restart_restores_active_context_without_retesting_bucket(tmp_path):
    store = OssSettingsStore(tmp_path)
    store.write_active(config())
    factory = RecordingFactory()

    runtime = OssRuntime(store, factory)

    assert runtime.active_context().config == config()
    assert runtime.active_context().revision == 1
    assert len(factory.providers) == 1
    assert factory.providers[0].probes == 0
