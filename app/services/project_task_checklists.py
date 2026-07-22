"""Task checklist defaults for compact project-authoring drafts."""

from __future__ import annotations

import copy
import re
from typing import Any, Mapping


_CRITERIA_PATTERNS = (
    re.compile(r"(?:验收标准|验收条件|完成标准)\s*[：:]\s*(.+)", re.I),
    re.compile(r"(?:acceptance criteria|acceptance standard|done criteria)\s*[：:]\s*(.+)", re.I),
)


def normalize_task_checklist(task: Mapping[str, Any], *, index: int) -> list[dict[str, Any]]:
    """Return an explicit checklist, deriving one from acceptance text when absent."""
    existing = task.get("checklist")
    if isinstance(existing, list) and existing:
        return [_normalize_existing_item(item, item_index) for item_index, item in enumerate(existing)]

    criterion = _extract_acceptance_criterion(str(task.get("description") or ""))
    if not criterion:
        criterion = f"Complete the task deliverable for {str(task.get('title') or 'this task').strip() or 'this task'}."
    return [{
        "id": f"acceptance-{index + 1}",
        "text": criterion,
        "done": False,
        "source": "project_authoring_acceptance",
    }]


def _normalize_existing_item(item: Any, index: int) -> dict[str, Any]:
    if isinstance(item, Mapping):
        normalized = copy.deepcopy(dict(item))
        normalized["id"] = str(normalized.get("id") or f"acceptance-{index + 1}")
        normalized["text"] = str(normalized.get("text") or normalized.get("title") or "").strip()
        normalized["done"] = normalized.get("done") is True
        if not normalized["text"]:
            normalized["text"] = f"Complete acceptance item {index + 1}."
        return normalized
    return {
        "id": f"acceptance-{index + 1}",
        "text": str(item or "").strip() or f"Complete acceptance item {index + 1}.",
        "done": False,
        "source": "project_authoring_acceptance",
    }


def _extract_acceptance_criterion(description: str) -> str:
    lines = [line.strip() for line in description.splitlines()]
    for line in lines:
        if not line:
            continue
        for pattern in _CRITERIA_PATTERNS:
            match = pattern.search(line)
            if match:
                return _clean_criterion(match.group(1))
    return ""


def _clean_criterion(value: str) -> str:
    text = re.sub(r"^[\-*\d.\s]+", "", value.strip())
    return text.rstrip("。.;；") + ("。" if _contains_cjk(text) else ".")


def _contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", value))
