"""Composition for the automatic HR collection, normalization, and assessment cycle."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping, Protocol, Sequence

from services.hr_assessments import HRAssessmentOrchestrator
from services.hr_config import HRConfig
from services.hr_directory import HRDirectoryService, INELIGIBLE_AVAILABILITY
from services.hr_evidence import HREvidenceCollector, HREvidencePorts
from services.hr_manual_daily_sync import (
    CallableHRManualDailyConversation,
    EmptyHREvidencePort,
)
from services.hr_reporting import (
    HRDailyReportCollector,
    HRDailyReportNormalizer,
    HRReportingService,
)
from services.hr_repository import AgentRecord, HRRepository
from services.hr_scheduler import (
    HRReconciliationLoop,
    HRScheduler,
    HRWorkflowProcessor,
)
from services.hr_schedule_settings import HRScheduleSettingsService
from services.hr_team_sync import HRTeamSyncService


AUTOMATIC_DAILY_REPORT_MESSAGE = (
    "请提交你今天的日报。请准确说明今天完成的工作、相关项目或任务、产出物、"
    "遇到的阻塞以及需要的协助；不要虚构或补充未发生的工作。"
)


class HRLifecycleStatePort(Protocol):
    def public_state(self, *, ensure: bool = True) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class HRAutomaticReportingRuntime:
    loop: HRReconciliationLoop
    reporting: HRReportingService
    normalizer: HRDailyReportNormalizer
    assessments: HRAssessmentOrchestrator
    team_sync: HRTeamSyncService


def _all_agents(repository: HRRepository) -> tuple[AgentRecord, ...]:
    items: list[AgentRecord] = []
    cursor = None
    while True:
        page = repository.list_agents(limit=100, cursor=cursor)
        items.extend(page.items)
        if page.next_cursor is None:
            return tuple(items)
        cursor = page.next_cursor


def build_hr_automatic_reporting(
    repository: HRRepository,
    *,
    config: HRConfig,
    lifecycle: HRLifecycleStatePort,
    schedule_settings: HRScheduleSettingsService,
    roster_provider: Callable[[bool], Sequence[Mapping[str, object]]],
    conversation: CallableHRManualDailyConversation,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    interval_seconds: float = 30.0,
    on_error: Callable[[str], None] = lambda _code: None,
) -> HRAutomaticReportingRuntime:
    """Build one shared automatic pipeline without transport or server globals."""
    if not isinstance(schedule_settings, HRScheduleSettingsService):
        raise TypeError("schedule settings service is invalid")
    team_sync = HRTeamSyncService(HRDirectoryService(repository), roster_provider)
    lease_seconds = min(600, max(31, int(config.agent_timeout_seconds) + 30))
    reporting = HRReportingService(
        repository,
        clock=clock,
        claim_token_factory=lambda request_id: (
            f"hr-auto-{uuid.uuid4().hex}-{request_id}"
        ),
        claim_lease_seconds=lease_seconds,
    )
    evidence_port = EmptyHREvidencePort()
    evidence = HREvidenceCollector(
        HREvidencePorts(
            evidence_port,
            evidence_port,
            evidence_port,
            evidence_port,
            evidence_port,
            evidence_port,
        )
    )
    normalizer = HRDailyReportNormalizer(
        repository,
        conversation,
        clock=clock,
        timeout_seconds=config.agent_timeout_seconds,
    )
    assessments = HRAssessmentOrchestrator(
        repository,
        evidence,
        conversation,
        clock=clock,
        timeout_seconds=config.agent_timeout_seconds,
        claim_lease_seconds=lease_seconds,
        retry_limit=config.retry_limit,
    )
    collector = HRDailyReportCollector(
        repository,
        reporting,
        conversation,
        clock=clock,
        timeout_seconds=config.agent_timeout_seconds,
    )
    processor = HRWorkflowProcessor(
        config,
        repository,
        collector,
        normalizer,
        assessments,
        clock=clock,
    )

    def eligible_ai_ids() -> tuple[str, ...]:
        team_sync.sync()
        return tuple(
            agent.ai_id
            for agent in _all_agents(repository)
            if agent.ai_id != "hr"
            and agent.status == "active"
            and agent.availability not in INELIGIBLE_AVAILABILITY
        )

    def hr_available() -> bool:
        state = lifecycle.public_state(ensure=False)
        return str(state.get("status") or "").strip().lower() in {
            "idle",
            "working",
            "ready",
            "available",
        }

    scheduler = HRScheduler(
        config,
        repository,
        reporting,
        clock=clock,
        schedule_settings=schedule_settings.load,
    )
    loop = HRReconciliationLoop(
        scheduler,
        reporting,
        processor,
        eligible_ai_ids=eligible_ai_ids,
        hr_available=hr_available,
        report_message=AUTOMATIC_DAILY_REPORT_MESSAGE,
        clock=clock,
        interval_seconds=interval_seconds,
        on_error=on_error,
    )
    return HRAutomaticReportingRuntime(
        loop,
        reporting,
        normalizer,
        assessments,
        team_sync,
    )
