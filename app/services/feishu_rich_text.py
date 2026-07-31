"""Extract plain text from Feishu rich-text message payloads."""

from __future__ import annotations

import json
from typing import Any


def _walk_text(value: Any, parts: list[str]) -> None:
    if isinstance(value, str):
        if value:
            parts.append(value)
        return
    if isinstance(value, list):
        for item in value:
            _walk_text(item, parts)
        return
    if not isinstance(value, dict):
        return
    tag = str(value.get("tag") or "").strip().lower()
    for key in ("text", "content", "name", "href"):
        item = value.get(key)
        if isinstance(item, str) and item:
            parts.append(item)
            if tag in {"at", "a"}:
                return
    for key in ("elements", "children", "content"):
        item = value.get(key)
        if isinstance(item, (list, dict)):
            _walk_text(item, parts)


def extract_feishu_rich_text(content: Any) -> str:
    """Return readable text from Feishu text/post content shapes."""

    value = content
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return ""
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return raw
    if isinstance(value, dict):
        direct = value.get("text") or value.get("content")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
    parts: list[str] = []
    if isinstance(value, dict) and isinstance(value.get("content"), list):
        for line in value.get("content") or []:
            line_parts: list[str] = []
            _walk_text(line, line_parts)
            if line_parts:
                parts.append("".join(line_parts).strip())
    else:
        _walk_text(value, parts)
    return "\n".join(part for part in parts if part).strip()


__all__ = ["extract_feishu_rich_text"]
