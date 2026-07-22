"""Validation for Agent-authored HR daily report responses."""

from __future__ import annotations

import json
from typing import Any


class HRDailyReportContractError(ValueError):
    code = "daily_report_contract_invalid"


REQUIRED_KEYS = frozenset(
    {
        "schemaVersion",
        "agentAiId",
        "localDate",
        "completedWork",
        "relatedProjectsOrTasks",
        "artifacts",
        "blockers",
        "requestedHelp",
        "selfAssessment",
    }
)


def _string_list(value: Any, field: str) -> None:
    if not isinstance(value, list):
        raise HRDailyReportContractError(f"{field} must be an array")
    for item in value:
        if not isinstance(item, str):
            raise HRDailyReportContractError(f"{field} items must be strings")


def _object_list(value: Any, field: str, keys: frozenset[str]) -> None:
    if not isinstance(value, list):
        raise HRDailyReportContractError(f"{field} must be an array")
    for item in value:
        if not isinstance(item, dict) or set(item) != keys:
            raise HRDailyReportContractError(f"{field} items must match the template")
        if any(not isinstance(item[key], str) for key in keys):
            raise HRDailyReportContractError(f"{field} item values must be strings")


def validate_daily_report_response(raw_response: str, *, ai_id: str, local_date: str) -> str:
    """Return the original JSON text if it satisfies the daily-report contract."""
    if not isinstance(raw_response, str) or not raw_response.strip():
        raise HRDailyReportContractError("daily report response is empty")
    text = raw_response.strip()
    if text.startswith("```") or text.endswith("```"):
        raise HRDailyReportContractError("daily report response must not use Markdown fences")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HRDailyReportContractError("daily report response must be valid JSON") from exc
    if not isinstance(value, dict) or set(value) != REQUIRED_KEYS:
        raise HRDailyReportContractError("daily report response has unsupported fields")
    if value["schemaVersion"] != 1:
        raise HRDailyReportContractError("daily report schemaVersion must be 1")
    if value["agentAiId"] != ai_id or value["localDate"] != local_date:
        raise HRDailyReportContractError("daily report identity does not match request")
    _string_list(value["completedWork"], "completedWork")
    _object_list(
        value["relatedProjectsOrTasks"],
        "relatedProjectsOrTasks",
        frozenset({"type", "id", "title"}),
    )
    _object_list(value["artifacts"], "artifacts", frozenset({"id", "name", "type"}))
    _string_list(value["blockers"], "blockers")
    _string_list(value["requestedHelp"], "requestedHelp")
    if not isinstance(value["selfAssessment"], str):
        raise HRDailyReportContractError("selfAssessment must be a string")
    return text
