"""Helpers for normalizing Agent-provided self-introduction payloads."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StructuredIntroduction:
    text: str


def _strip_json_fence(value: str) -> str:
    raw = value.strip()
    if not raw.startswith("```"):
        return raw
    lines = raw.splitlines()
    if not lines:
        return raw
    first = lines[0].strip().lower()
    if first not in {"```", "```json"} or lines[-1].strip() != "```":
        return raw
    return "\n".join(lines[1:-1]).strip()


def parse_structured_introduction(raw_response: str) -> StructuredIntroduction | None:
    """Return a readable introduction when the Agent already sent the requested JSON."""

    if not isinstance(raw_response, str) or not raw_response.strip():
        return None
    try:
        payload = json.loads(_strip_json_fence(raw_response))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
        return None
    identity = _string(payload.get("identity"))
    responsibilities = _strings(payload.get("responsibilities"))
    strengths = _strings(payload.get("strengths"))
    scenarios = _strings(payload.get("collaborationScenarios"))
    if not identity and not responsibilities and not strengths and not scenarios:
        return None
    parts = []
    if identity:
        parts.append(identity)
    if responsibilities:
        parts.append("主要职责：" + "；".join(responsibilities))
    if strengths:
        parts.append("擅长：" + "；".join(strengths))
    if scenarios:
        parts.append("适合协作场景：" + "；".join(scenarios))
    text = " ".join(parts).strip()
    if not text or len(text) > 1_000:
        return None
    return StructuredIntroduction(text=text)


def _string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    items = []
    for item in value:
        if isinstance(item, str) and item.strip():
            items.append(item.strip())
    return tuple(items[:10])
