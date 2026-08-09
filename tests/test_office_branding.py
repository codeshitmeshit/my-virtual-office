import base64
import copy
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.office_branding import (  # noqa: E402
    MAX_ICON_BYTES,
    normalize_icon_data_url,
    normalize_office_name,
    normalize_office_patch,
    safe_icon_data_url,
)
from server_services import config_runtime  # noqa: E402


def test_office_name_defaults_trims_and_limits():
    assert normalize_office_name("  Studio  ") == "Studio"
    assert normalize_office_name("") == "Virtual Office"
    try:
        normalize_office_name("x" * 81)
    except ValueError as exc:
        assert "80" in str(exc)
    else:
        raise AssertionError("long office names must be rejected")


def test_icon_data_url_accepts_supported_small_images():
    payload = base64.b64encode(b"small-png-bytes").decode()
    value = f"data:image/png;base64,{payload}"
    assert normalize_icon_data_url(value) == value
    assert normalize_office_patch({"name": "HQ", "iconDataUrl": value, "port": 8090}) == {
        "name": "HQ",
        "iconDataUrl": value,
        "port": 8090,
    }


def test_icon_data_url_rejects_unsupported_invalid_and_large_values():
    invalid_values = [
        "https://example.com/icon.png",
        "data:image/svg+xml;base64,PHN2Zz4=",
        "data:image/png;base64,not-valid!",
        "data:image/png;base64," + base64.b64encode(b"x" * (MAX_ICON_BYTES + 1)).decode(),
    ]
    for value in invalid_values:
        try:
            normalize_icon_data_url(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid icon must be rejected: {value[:40]}")
        assert safe_icon_data_url(value) is None


def test_setup_persistence_rejects_invalid_branding_before_disk_write():
    config_runtime.copy = copy
    result = config_runtime._persist_setup_payload({
        "office": {"name": "HQ", "iconDataUrl": "data:image/svg+xml;base64,PHN2Zz4="},
    })
    assert result == {
        "ok": False,
        "error": "Office icon must be a PNG, JPG, WebP, or ICO image",
        "code": "invalid_office_branding",
        "_status": 400,
    }


if __name__ == "__main__":
    test_office_name_defaults_trims_and_limits()
    test_icon_data_url_accepts_supported_small_images()
    test_icon_data_url_rejects_unsupported_invalid_and_large_values()
    test_setup_persistence_rejects_invalid_branding_before_disk_write()
    print("office branding validation ok")
