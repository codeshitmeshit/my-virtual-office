#!/usr/bin/env python3
"""Request-secret hashing and authenticated Agent status coverage."""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services.project_authoring_security import (
    generate_request_secret,
    hash_request_secret,
    verify_request_secret,
)


def test_request_secret_is_random_hashed_and_constant_contract_verifiable():
    first = generate_request_secret()
    second = generate_request_secret()
    stored = hash_request_secret(first)

    assert first != second
    assert len(first) >= 32
    assert stored.startswith("sha256:")
    assert first not in stored
    assert verify_request_secret(first, stored) is True
    assert verify_request_secret(second, stored) is False
    assert verify_request_secret("", stored) is False
    assert verify_request_secret(first, "plaintext") is False
