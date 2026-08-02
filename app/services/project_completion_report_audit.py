"""Bounded redacted audit log for project completion-report delivery routing."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any, Callable, Mapping


AUDIT_FILENAME = "project-completion-report-delivery.jsonl"
MAX_AUDIT_RECORDS = 1000
_LOCK = threading.Lock()
_FIELDS = (
    "projectId",
    "occurrenceId",
    "primaryStatus",
    "primaryCode",
    "fallbackDecision",
    "fallbackStatus",
    "fallbackCode",
    "finalChannel",
    "messageId",
)
_LIMITS = {
    "projectId": 160,
    "occurrenceId": 200,
    "primaryStatus": 120,
    "primaryCode": 120,
    "fallbackDecision": 80,
    "fallbackStatus": 120,
    "fallbackCode": 120,
    "finalChannel": 80,
    "messageId": 300,
}


def append_completion_report_delivery_audit(
    status_dir: str | Path,
    event: Mapping[str, Any],
    *,
    now: Callable[[], str] | None = None,
) -> None:
    record = {"at": (now or (lambda: datetime.now(timezone.utc).isoformat()))()}
    for field in _FIELDS:
        record[field] = str(event.get(field) or "").strip()[: _LIMITS[field]]
    path = Path(status_dir) / AUDIT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with _LOCK:
        existing = []
        if path.exists():
            try:
                existing = path.read_text(encoding="utf-8").splitlines()[-(MAX_AUDIT_RECORDS - 1):]
            except OSError:
                existing = []
        existing.append(encoded)
        path.write_text("\n".join(existing) + "\n", encoding="utf-8")
