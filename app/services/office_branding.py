"""Validation helpers for user-configurable office browser branding."""

from __future__ import annotations

import base64
import binascii
import copy
import re
from collections.abc import Mapping


DEFAULT_OFFICE_NAME = "Virtual Office"
MAX_OFFICE_NAME_LENGTH = 80
MAX_ICON_BYTES = 32 * 1024
_ICON_DATA_URL = re.compile(
    r"^data:(image/(?:png|jpeg|webp|x-icon|vnd\.microsoft\.icon));base64,([A-Za-z0-9+/=]+)$",
    re.IGNORECASE,
)


def normalize_office_name(value: object) -> str:
    name = str(value or "").strip()
    if not name:
        return DEFAULT_OFFICE_NAME
    if len(name) > MAX_OFFICE_NAME_LENGTH:
        raise ValueError(f"Office name must be at most {MAX_OFFICE_NAME_LENGTH} characters")
    return name


def normalize_icon_data_url(value: object) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("Office icon must be an image data URL")
    match = _ICON_DATA_URL.fullmatch(value.strip())
    if not match:
        raise ValueError("Office icon must be a PNG, JPG, WebP, or ICO image")
    try:
        decoded = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Office icon contains invalid image data") from exc
    if not decoded:
        raise ValueError("Office icon cannot be empty")
    if len(decoded) > MAX_ICON_BYTES:
        raise ValueError(f"Office icon must be at most {MAX_ICON_BYTES // 1024} KB after processing")
    mime = match.group(1).lower()
    return f"data:{mime};base64,{match.group(2)}"


def normalize_office_patch(value: object) -> dict:
    """Validate branding fields while preserving unrelated office settings."""
    if not isinstance(value, Mapping):
        raise ValueError("Office settings must be an object")
    normalized = copy.deepcopy(dict(value))
    if "name" in normalized:
        normalized["name"] = normalize_office_name(normalized.get("name"))
    if "iconDataUrl" in normalized:
        normalized["iconDataUrl"] = normalize_icon_data_url(normalized.get("iconDataUrl"))
    return normalized


def safe_icon_data_url(value: object) -> str | None:
    """Ignore an invalid legacy icon instead of preventing server startup."""
    try:
        return normalize_icon_data_url(value)
    except ValueError:
        return None
