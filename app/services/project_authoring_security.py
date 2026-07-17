"""Opaque request-secret generation and verification for Agent authoring APIs."""

from __future__ import annotations

import hashlib
import hmac
import secrets


HASH_PREFIX = "sha256:"


def generate_request_secret() -> str:
    return secrets.token_urlsafe(32)


def hash_request_secret(secret: str) -> str:
    value = str(secret or "")
    if not value:
        raise ValueError("Request secret is required")
    return HASH_PREFIX + hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_request_secret(secret: str, stored_hash: str) -> bool:
    supplied = str(secret or "")
    expected = str(stored_hash or "")
    if not supplied or not expected.startswith(HASH_PREFIX):
        return False
    return hmac.compare_digest(hash_request_secret(supplied), expected)
