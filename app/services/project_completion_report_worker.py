"""Persistent worker for project completion-report generation and delivery."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime
import threading
from typing import Any, Callable, Mapping

from .periodic_timer import PeriodicTimer
from .project_completion_report_delivery import CompletionReportDeliveryError
from .project_completion_report_generation import CompletionReportGenerationError
from .project_completion_report_storage import CompletionReportStorageError
from .project_completion_reporting import (
    CompletionReportStateError,
    begin_completion_report_delivery,
    claim_due_completion_report,
    fail_completion_report_attempt,
    finish_completion_report_delivery,
    finish_completion_report_generation,
)
from .project_repository import ProjectNotFoundError, ProjectRepository


@dataclass(frozen=True, slots=True)
class CompletionReportWorkerPorts:
    repository: ProjectRepository
    now: Callable[[], str]
    new_token: Callable[[], str]
    collect: Callable[[Mapping[str, Any]], Mapping[str, Any]]
    generate: Callable[[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]
    store: Callable[[Mapping[str, Any], dict[str, Any], str], Mapping[str, Any]]
    deliver: Callable[[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _find_occurrence(project: Mapping[str, Any], occurrence_id: str) -> dict[str, Any] | None:
    orchestration = project.get("orchestration") if isinstance(project.get("orchestration"), Mapping) else {}
    for item in orchestration.get("completionReports") or []:
        if isinstance(item, dict) and item.get("occurrenceId") == occurrence_id:
            return item
    return None


class ProjectCompletionReportWorker:
    def __init__(
        self,
        ports: CompletionReportWorkerPorts,
        *,
        interval_seconds: float = 15,
        batch_size: int = 10,
        timer_factory: Callable[..., Any] = PeriodicTimer,
    ) -> None:
        self._ports = ports
        self._interval_seconds = interval_seconds
        self._batch_size = max(1, min(int(batch_size), 100))
        self._timer_factory = timer_factory
        self._timer = None
        self._run_lock = threading.Lock()

    def start(self) -> bool:
        if self._timer is not None:
            return False
        self._timer = self._timer_factory(
            self.run_once,
            interval_seconds=self._interval_seconds,
            name="project-completion-report-worker",
            on_error=lambda _exc: None,
        )
        return bool(self._timer.start())

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()

    def wake(self) -> None:
        threading.Thread(
            target=self.run_once,
            daemon=True,
            name="project-completion-report-wakeup",
        ).start()

    def run_once(self) -> dict[str, int]:
        if not self._run_lock.acquire(blocking=False):
            return {"selected": 0, "delivered": 0, "failed": 0, "skipped": 1}
        try:
            candidates = self._due_candidates()[: self._batch_size]
            result = {"selected": len(candidates), "delivered": 0, "failed": 0, "skipped": 0}
            for project_id, occurrence_id in candidates:
                token = str(self._ports.new_token() or "").strip()
                if not token:
                    result["skipped"] += 1
                    continue
                try:
                    claim = self._ports.repository.update(
                        project_id,
                        lambda project, oid=occurrence_id, value=token: claim_due_completion_report(
                            project,
                            occurrence_id=oid,
                            now=self._ports.now(),
                            token=value,
                        ),
                    )
                except (ProjectNotFoundError, CompletionReportStateError):
                    result["skipped"] += 1
                    continue
                if not claim.get("claimed"):
                    result["skipped"] += 1
                    continue
                if self._process_claim(
                    project_id,
                    occurrence_id,
                    token,
                    resume_delivery=bool(claim.get("resumeDelivery")),
                ):
                    result["delivered"] += 1
                else:
                    result["failed"] += 1
            return result
        finally:
            self._run_lock.release()

    def _due_candidates(self) -> list[tuple[str, str]]:
        now = _parse_time(self._ports.now())
        candidates: list[tuple[str, str]] = []
        for project in self._ports.repository.load_all().get("projects") or []:
            if not isinstance(project, Mapping):
                continue
            project_id = str(project.get("id") or "").strip()
            orchestration = project.get("orchestration") if isinstance(project.get("orchestration"), Mapping) else {}
            for occurrence in orchestration.get("completionReports") or []:
                if not isinstance(occurrence, Mapping):
                    continue
                state = str(occurrence.get("state") or "")
                if state not in {"pending", "retry", "generating", "ready", "delivering"}:
                    continue
                due = _parse_time(occurrence.get("nextAttemptAt"))
                claim = occurrence.get("claim") if isinstance(occurrence.get("claim"), Mapping) else {}
                expires = _parse_time(claim.get("expiresAt"))
                if due and now and due > now:
                    continue
                if claim and expires and now and expires > now:
                    continue
                occurrence_id = str(occurrence.get("occurrenceId") or "").strip()
                if project_id and occurrence_id:
                    candidates.append((project_id, occurrence_id))
        return candidates

    def _process_claim(
        self,
        project_id: str,
        occurrence_id: str,
        token: str,
        *,
        resume_delivery: bool,
    ) -> bool:
        delivery_started = False
        try:
            project = self._ports.repository.get(project_id)
            if project is None:
                raise ProjectNotFoundError(project_id)
            occurrence = _find_occurrence(project, occurrence_id)
            if occurrence is None:
                raise CompletionReportStateError("completion_report_not_found", "Occurrence not found")
            if resume_delivery:
                self._ports.repository.update(
                    project_id,
                    lambda latest: begin_completion_report_delivery(
                        latest,
                        occurrence_id=occurrence_id,
                        token=token,
                        now=self._ports.now(),
                    ),
                )
            else:
                collected = self._ports.collect(project)
                generated = self._ports.generate(project, occurrence, collected)
                storage = self._ports.store(project, occurrence, str(generated.get("markdown") or ""))

                def persist_generation(latest: dict[str, Any]) -> None:
                    finish_completion_report_generation(
                        latest,
                        occurrence_id=occurrence_id,
                        token=token,
                        now=self._ports.now(),
                        reporting_agent_id=str(generated.get("reportingAgentId") or ""),
                        markdown_path=str(storage.get("markdownPath") or ""),
                        digest=str(storage.get("digest") or ""),
                        report=generated.get("report") if isinstance(generated.get("report"), Mapping) else {},
                    )
                    begin_completion_report_delivery(
                        latest,
                        occurrence_id=occurrence_id,
                        token=token,
                        now=self._ports.now(),
                    )

                self._ports.repository.update(project_id, persist_generation)
            delivery_started = True
            project = self._ports.repository.get(project_id)
            occurrence = _find_occurrence(project or {}, occurrence_id)
            if project is None or occurrence is None:
                raise ProjectNotFoundError(project_id)
            report = occurrence.get("generatedReport") if isinstance(occurrence.get("generatedReport"), Mapping) else {}
            delivery = self._ports.deliver(project, occurrence, report)
            if not delivery.get("ok"):
                status = str(delivery.get("status") or "delivery_failed")
                code_value = delivery.get("code")
                recoverable = status == "feishu_error" and (
                    str(code_value) == "429" or (str(code_value).isdigit() and int(str(code_value)) >= 500)
                )
                outcome_unknown = status in {"network_error", "timeout", "delivery_timeout"}
                self._fail(
                    project_id,
                    occurrence_id,
                    token,
                    code="delivery_outcome_unknown" if outcome_unknown else status,
                    error=str(delivery.get("error") or delivery.get("message") or status),
                    recoverable=recoverable,
                    outcome_unknown=outcome_unknown,
                )
                return False
            self._ports.repository.update(
                project_id,
                lambda latest: finish_completion_report_delivery(
                    latest,
                    occurrence_id=occurrence_id,
                    token=token,
                    now=self._ports.now(),
                    message_id=str(delivery.get("messageId") or ""),
                ),
            )
            return True
        except (CompletionReportGenerationError, CompletionReportDeliveryError) as exc:
            self._fail(
                project_id,
                occurrence_id,
                token,
                code=exc.code,
                error=str(exc),
                recoverable=exc.recoverable,
                outcome_unknown=delivery_started,
            )
        except CompletionReportStorageError as exc:
            self._fail(
                project_id,
                occurrence_id,
                token,
                code="completion_report_storage_failed",
                error=str(exc),
                recoverable=False,
                outcome_unknown=False,
            )
        except Exception as exc:
            self._fail(
                project_id,
                occurrence_id,
                token,
                code="delivery_outcome_unknown" if delivery_started else "completion_report_processing_failed",
                error=str(exc),
                recoverable=not delivery_started,
                outcome_unknown=delivery_started,
            )
        return False

    def _fail(
        self,
        project_id: str,
        occurrence_id: str,
        token: str,
        *,
        code: str,
        error: str,
        recoverable: bool,
        outcome_unknown: bool,
    ) -> None:
        try:
            self._ports.repository.update(
                project_id,
                lambda project: fail_completion_report_attempt(
                    project,
                    occurrence_id=occurrence_id,
                    token=token,
                    now=self._ports.now(),
                    code=code,
                    error=error,
                    recoverable=recoverable,
                    outcome_unknown=outcome_unknown,
                ),
            )
        except (ProjectNotFoundError, CompletionReportStateError):
            return
