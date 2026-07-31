"""Helpers for strict HR structured-output extraction and diagnostics."""

from __future__ import annotations

import json
from dataclasses import dataclass

from services import business_prompt_bridge


MAX_DIAGNOSTIC_OUTPUT = 700


@dataclass(frozen=True, slots=True)
class HRStructuredOutputPayload:
    json_text: str
    raw_output_excerpt: str
    repaired: bool = False


def compact_diagnostic_text(value: object, *, limit: int = MAX_DIAGNOSTIC_OUTPUT) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.replace("\x00", "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _json_object_end(text: str, start: int) -> int | None:
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def extract_json_object_text(payload: object) -> HRStructuredOutputPayload:
    if not isinstance(payload, str) or not payload.strip():
        raise ValueError("HR returned no structured output")
    raw = payload.strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, dict):
        return HRStructuredOutputPayload(raw, compact_diagnostic_text(payload))

    for start, char in enumerate(raw):
        if char != "{":
            continue
        end = _json_object_end(raw, start)
        if end is None:
            continue
        candidate = raw[start:end]
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return HRStructuredOutputPayload(
                candidate,
                compact_diagnostic_text(payload),
                repaired=True,
            )
    raise ValueError("HR structured output does not contain a JSON object")


def render_repair_prompt(
    *,
    ai_id: str,
    raw_response: str,
    invalid_output: object,
    validation_error: str,
) -> str:
    return business_prompt_bridge.render_business_prompt(
        {
            "domain": "hr.introduction_summary_repair",
            "operation": "repair",
            "locale": "zh-CN",
            "root": "hr_introduction_summary_repair_prompt",
            "target": {"agentAiId": ai_id},
            "sections": [
                {"name": "role", "value": "Human Resources structured-output repair worker.", "trusted": True},
                {"name": "task", "value": "Repair the previous HR introduction summary response into the exact required JSON object.", "trusted": True},
                {
                    "name": "rules",
                    "trusted": True,
                    "value": [
                        "Return only one JSON object. Do not wrap it in Markdown.",
                        "Use exactly these keys: schemaVersion, introduction, supportingEvidence, materialConflict, clarificationQuestion.",
                        "schemaVersion must be 1.",
                        "supportingEvidence must contain exact substrings copied from the Agent response.",
                        "Do not invent responsibilities or capabilities.",
                        "If there is no material conflict, introduction must be non-empty and clarificationQuestion must be empty.",
                    ],
                },
                {"name": "agent", "value": {"ai_id": ai_id}},
                {"name": "validation_error", "value": validation_error},
                {"name": "agent_response", "value": raw_response},
                {"name": "invalid_output", "value": invalid_output},
            ],
            "output": {
                "schema": {
                    "schemaVersion": 1,
                    "introduction": "string",
                    "supportingEvidence": ["exact excerpts from the Agent response"],
                    "materialConflict": "boolean",
                    "clarificationQuestion": "string",
                },
                "format": "Return JSON only.",
            },
        },
    )
