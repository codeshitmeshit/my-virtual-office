"""Focused dependency wiring for the project completion-report worker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .project_completion_report_artifacts import collect_completion_report_artifacts
from .project_completion_report_delivery import deliver_completion_report
from .project_completion_report_generation import generate_completion_report
from .project_completion_report_storage import write_completion_report
from .project_completion_report_worker import (
    CompletionReportWorkerPorts,
    ProjectCompletionReportWorker,
)
from .project_repository import ProjectRepository


@dataclass(frozen=True, slots=True)
class CompletionReportRuntimeDependencies:
    reporting_agent_id: Callable[[], str]
    artifact_context: Callable[[Mapping[str, Any]], Mapping[str, Any]]
    read_artifact: Callable[..., Mapping[str, Any]]
    generate_agent: Callable[..., Mapping[str, Any]]
    notification_app_config: Callable[[], Mapping[str, Any]]
    send_notification: Callable[..., dict[str, Any]]
    project_url: Callable[[str], str]
    now: Callable[[], str]
    new_token: Callable[[], str]


def build_completion_report_worker(
    repository: ProjectRepository,
    dependencies: CompletionReportRuntimeDependencies,
    *,
    interval_seconds: float = 15,
    batch_size: int = 10,
) -> ProjectCompletionReportWorker:
    """Compose the worker without coupling its domain modules to the server."""

    def collect(project: Mapping[str, Any]) -> Mapping[str, Any]:
        context = dependencies.artifact_context(project)

        def read(path: str, **options: Any) -> Mapping[str, Any]:
            if not context.get("ok"):
                return {
                    "ok": False,
                    "error": str(context.get("error") or "Artifact context is unavailable"),
                }
            return dependencies.read_artifact(context, path, **options)

        return collect_completion_report_artifacts(project, read_artifact=read)

    def generate(
        project: Mapping[str, Any],
        occurrence: Mapping[str, Any],
        collected: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return generate_completion_report(
            project,
            occurrence,
            artifacts=collected.get("artifacts") or [],
            omissions=collected.get("omissions") or [],
            reporting_agent_id=dependencies.reporting_agent_id(),
            generate=dependencies.generate_agent,
        )

    def deliver(
        project: Mapping[str, Any],
        occurrence: Mapping[str, Any],
        report: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return deliver_completion_report(
            project,
            occurrence,
            report,
            app_config=dependencies.notification_app_config(),
            send_notification=dependencies.send_notification,
            project_url=dependencies.project_url(str(project.get("id") or "")),
        )

    return ProjectCompletionReportWorker(
        CompletionReportWorkerPorts(
            repository=repository,
            now=dependencies.now,
            new_token=dependencies.new_token,
            collect=collect,
            generate=generate,
            store=write_completion_report,
            deliver=deliver,
        ),
        interval_seconds=interval_seconds,
        batch_size=batch_size,
    )
