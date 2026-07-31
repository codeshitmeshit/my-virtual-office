"""Deterministic summaries for structured Agent self-introduction responses."""

from __future__ import annotations

import json

from services.hr_structured_output import extract_json_object_text


def _string_list(value: object, *, limit: int = 3) -> list[str]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            continue
        items.append(" ".join(item.split()))
        if len(items) >= limit:
            break
    return items


def summarize_structured_agent_introduction(raw_response: str) -> str:
    """Build a concise introduction from the Agent's own structured response."""
    try:
        payload = extract_json_object_text(raw_response)
        value = json.loads(payload.json_text)
    except Exception:
        return ""
    if not isinstance(value, dict):
        return ""
    if value.get("schemaVersion") != 1 or not isinstance(value.get("agentAiId"), str):
        return ""
    identity = value.get("identity")
    if not isinstance(identity, str) or not identity.strip():
        return ""
    responsibilities = _string_list(value.get("responsibilities"))
    strengths = _string_list(value.get("strengths"), limit=2)
    scenarios = _string_list(value.get("collaborationScenarios"), limit=2)

    parts = [" ".join(identity.split())]
    if responsibilities:
        parts.append("主要职责：" + "；".join(responsibilities) + "。")
    if strengths:
        parts.append("擅长：" + "；".join(strengths) + "。")
    if scenarios:
        parts.append("适合协作场景：" + "；".join(scenarios) + "。")
    summary = "".join(parts).strip()
    if len(summary) <= 1_000:
        return summary
    return summary[:997].rstrip() + "..."
