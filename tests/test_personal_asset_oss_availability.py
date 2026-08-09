import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.oss_runtime import OssConfigurationUnavailable  # noqa: E402
from services.personal_asset_oss_availability import (  # noqa: E402
    PersonalAssetOssAvailability,
)
from services.personal_asset_oss_availability_http import (  # noqa: E402
    OSS_AVAILABILITY_PATH,
    PersonalAssetOssAvailabilityHTTP,
)


NOW = datetime(2026, 8, 9, 10, 30, tzinfo=timezone.utc)


def test_available_projection_only_exposes_status_and_checked_at():
    calls = []
    context = SimpleNamespace(provider=SimpleNamespace(probe_bucket=lambda: calls.append("probe")))
    availability = PersonalAssetOssAvailability(lambda: context, now=lambda: NOW)

    result = availability.check()

    assert result == {"status": "available", "checkedAt": "2026-08-09T10:30:00Z"}
    assert calls == ["probe"]
    assert "context" not in str(result).lower()


def test_unconfigured_projection_uses_stable_code_without_configuration_details():
    def unavailable():
        raise OssConfigurationUnavailable(
            "endpoint and bucket are missing",
            code="oss_configuration_unavailable",
        )

    result = PersonalAssetOssAvailability(unavailable, now=lambda: NOW).check()

    assert result == {
        "status": "unconfigured",
        "checkedAt": "2026-08-09T10:30:00Z",
        "code": "oss_configuration_unavailable",
    }
    assert "endpoint" not in str(result).lower()
    assert "bucket" not in str(result).lower()


def test_unexpected_runtime_failure_is_sanitized_and_does_not_escape():
    def broken():
        raise RuntimeError("secret=do-not-return")

    result = PersonalAssetOssAvailability(broken, now=lambda: NOW).check()

    assert result == {
        "status": "unavailable",
        "checkedAt": "2026-08-09T10:30:00Z",
        "code": "oss_runtime_unavailable",
    }
    assert "secret" not in str(result).lower()


def test_bucket_probe_failure_is_reported_as_unavailable_without_provider_details():
    def broken_probe():
        raise RuntimeError("endpoint=private.example secret=do-not-return")

    context = SimpleNamespace(
        provider=SimpleNamespace(probe_bucket=broken_probe)
    )

    result = PersonalAssetOssAvailability(
        lambda: context, now=lambda: NOW
    ).check()

    assert result == {
        "status": "unavailable",
        "checkedAt": "2026-08-09T10:30:00Z",
        "code": "oss_runtime_unavailable",
    }
    assert "private.example" not in str(result)
    assert "secret" not in str(result).lower()


def test_http_get_is_narrow_and_never_returns_provider_configuration():
    context = SimpleNamespace(
        provider=SimpleNamespace(probe_bucket=lambda: None)
    )
    http = PersonalAssetOssAvailabilityHTTP(
        PersonalAssetOssAvailability(lambda: context, now=lambda: NOW)
    )

    response = http.get(OSS_AVAILABILITY_PATH)
    unknown = http.get("/api/personal-assets/sync/availability-extra")

    assert http.handles_get(OSS_AVAILABILITY_PATH)
    assert not http.handles_get("/api/personal-assets/sync/availability-extra")
    assert response.status == 200
    assert response.payload == {
        "ok": True,
        "availability": {
            "status": "available",
            "checkedAt": "2026-08-09T10:30:00Z",
        },
    }
    assert unknown.status == 404
