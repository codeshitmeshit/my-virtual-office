"""Validation helpers for Agent-authored HR daily report responses."""

from __future__ import annotations


_OPENCLAW_DELIVERY_RECEIPT_PREFIX = "[DELIVERED] Message delivered to OpenClaw agent"


def reportable_daily_response(response: str | None) -> str | None:
    """Return a persistable daily-report response, or None for transport receipts."""
    if response is None:
        return None
    text = str(response).strip()
    if not text:
        return None
    if text.startswith(_OPENCLAW_DELIVERY_RECEIPT_PREFIX):
        return None
    return response
