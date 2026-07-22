"""File-backed daily-report assessment trigger queue."""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from hashlib import sha256
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from services.hr_assessments import HRAssessmentOrchestrator
from services.hr_repository import DailyReportRecord, HRRepository
from services.periodic_timer import PeriodicTimer


class HRDailyReportAssessmentQueueError(ValueError):
    code = "hr_daily_report_assessment_queue_failed"


@dataclass(frozen=True, slots=True)
class HRDailyReportAssessmentQueueTick:
    scanned: int
    accepted: int
    failed: int


def _safe_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return segment.strip("._") or "unknown"


class HRDailyReportLogSink:
    """Persists one latest JSON report log per Agent/date for the queue watcher."""

    def __init__(self, log_dir: str | os.PathLike[str]):
        self.log_dir = Path(log_dir).absolute()

    def path_for(self, *, ai_id: str, local_date: str) -> Path:
        return self.log_dir / f"{_safe_segment(local_date)}__{_safe_segment(ai_id)}.json"

    def write(self, report: DailyReportRecord) -> Path | None:
        if not isinstance(report, DailyReportRecord):
            raise HRDailyReportAssessmentQueueError("daily report record is invalid")
        if report.raw_response is None:
            return None
        self.log_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": 1,
            "reportId": report.id,
            "cycleId": report.cycle_id,
            "agentAiId": report.ai_id,
            "localDate": report.local_date,
            "submissionState": report.submission_state,
            "revision": report.revision,
            "submittedAt": report.submitted_at,
            "updatedAt": report.updated_at,
            "rawResponse": report.raw_response,
        }
        path = self.path_for(ai_id=report.ai_id, local_date=report.local_date)
        content = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        if path.exists():
            try:
                if path.read_text(encoding="utf-8") == content:
                    return path
            except Exception:
                pass
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
        return path


class HRDailyReportAssessmentQueue:
    """Polls report-log files and sends changed reports into HR assessment jobs."""

    def __init__(
        self,
        repository: HRRepository,
        assessments: HRAssessmentOrchestrator,
        log_dir: str | os.PathLike[str],
        *,
        interval_seconds: float = 5.0,
        max_per_tick: int = 4,
        on_error: Callable[[str], None] = lambda _code: None,
    ):
        if not isinstance(repository, HRRepository):
            raise HRDailyReportAssessmentQueueError("repository must be an HRRepository")
        if not isinstance(assessments, HRAssessmentOrchestrator):
            raise HRDailyReportAssessmentQueueError("assessment orchestrator is invalid")
        if (
            isinstance(max_per_tick, bool)
            or not isinstance(max_per_tick, int)
            or not 1 <= max_per_tick <= 100
        ):
            raise HRDailyReportAssessmentQueueError("max_per_tick must be between 1 and 100")
        self._repository = repository
        self._assessments = assessments
        self._sink = HRDailyReportLogSink(log_dir)
        self._state_path = self._sink.log_dir / ".assessment-queue-state.json"
        self._max_per_tick = max_per_tick
        self._on_error = on_error
        self._tick_lock = threading.Lock()
        self._timer = PeriodicTimer(
            self.tick,
            interval_seconds=interval_seconds,
            name="hr-daily-report-assessment-queue",
            on_error=lambda exc: self._on_error(
                str(getattr(exc, "code", "hr_daily_report_assessment_queue_failed"))
            ),
        )

    @property
    def sink(self) -> HRDailyReportLogSink:
        return self._sink

    def seed_from_repository(self) -> int:
        written = 0
        cursor = None
        while True:
            page = self._repository.list_daily_reports(limit=100, cursor=cursor)
            for report in page.items:
                if report.raw_response is not None and self._sink.write(report) is not None:
                    written += 1
            if page.next_cursor is None:
                return written
            cursor = page.next_cursor

    def _load_state(self) -> dict[str, dict[str, str]]:
        try:
            value = json.loads(self._state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(value, dict):
            return {}
        state: dict[str, dict[str, str]] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not isinstance(item, dict):
                continue
            state[key] = {
                str(field): str(item.get(field) or "")
                for field in ("digest", "status", "processedAt", "errorCode")
            }
        return state

    def _save_state(self, state: dict[str, dict[str, str]]) -> None:
        self._sink.log_dir.mkdir(parents=True, exist_ok=True)
        content = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True)
        temporary = self._state_path.with_name(
            f".{self._state_path.name}.{uuid.uuid4().hex}.tmp"
        )
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, self._state_path)

    def _payloads(self) -> tuple[dict[str, object], ...]:
        self._sink.log_dir.mkdir(parents=True, exist_ok=True)
        payloads = []
        for path in sorted(
            self._sink.log_dir.glob("*.json"),
            key=lambda item: (item.stat().st_mtime, item.name),
        ):
            try:
                content = path.read_text(encoding="utf-8")
                value = json.loads(content)
            except Exception:
                continue
            if isinstance(value, dict):
                value = dict(value)
                value["_queueStateKey"] = path.name
                value["_queueDigest"] = sha256(content.encode("utf-8")).hexdigest()
                payloads.append(value)
        return tuple(payloads)

    def tick(self) -> HRDailyReportAssessmentQueueTick:
        if not self._tick_lock.acquire(blocking=False):
            return HRDailyReportAssessmentQueueTick(0, 0, 0)
        try:
            self.seed_from_repository()
            state = self._load_state()
            accepted = 0
            failed = 0
            scanned = 0
            for payload in self._payloads():
                if accepted >= self._max_per_tick:
                    break
                scanned += 1
                state_key = str(payload.get("_queueStateKey") or "")
                digest = str(payload.get("_queueDigest") or "")
                prior = state.get(state_key, {})
                if (
                    state_key
                    and digest
                    and prior.get("digest") == digest
                    and prior.get("status") in {"complete", "already_complete", "exhausted"}
                ):
                    continue
                ai_id = str(payload.get("agentAiId") or "").strip()
                local_date = str(payload.get("localDate") or "").strip()
                cycle_id = str(payload.get("cycleId") or "").strip() or None
                if not ai_id or not local_date:
                    failed += 1
                    continue
                job = self._repository.get_assessment_job(ai_id, local_date)
                if job is not None and job.status == "failed":
                    self._repository.reopen_failed_assessment_job(ai_id, local_date)
                results = self._assessments.assess(
                    (ai_id,),
                    local_date=local_date,
                    actor_ai_id="hr",
                    cycle_id=cycle_id,
                    allow_open_cycle=True,
                    revision_reason="daily_report_log_updated",
                )
                accepted += 1
                status = results[0].status if results else "unknown"
                error_code = results[0].error_code if results else ""
                if status == "retry_exhausted":
                    status = "exhausted"
                if state_key and digest:
                    state[state_key] = {
                        "digest": digest,
                        "status": status,
                        "processedAt": datetime.now(timezone.utc).isoformat(),
                        "errorCode": error_code,
                    }
                if results and results[0].status == "failed":
                    failed += 1
            self._save_state(state)
            return HRDailyReportAssessmentQueueTick(scanned, accepted, failed)
        finally:
            self._tick_lock.release()

    def start(self) -> bool:
        self.seed_from_repository()
        return self._timer.start()

    def stop(self, timeout_seconds: float = 5.0) -> None:
        self._timer.stop(timeout_seconds)
