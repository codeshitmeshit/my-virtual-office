"""HR-owned roster reconciliation without transport or provider coupling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from services.hr_repository import AgentRecord, HRRepository, HRRepositoryError


INELIGIBLE_AVAILABILITY = frozenset(
    {"unavailable", "offline", "disabled", "deleted", "unreachable"}
)
KIND_PRIORITY = {"system": 4, "project": 3, "external": 2, "synthetic": 1}
STATUS_PRIORITY = {"deleted": 4, "disabled": 3, "offline": 2, "unreachable": 1}


class HRDirectoryValidationError(ValueError):
    code = "hr_directory_validation_failed"


@dataclass(frozen=True, slots=True)
class RosterObservation:
    ai_id: str
    name: str
    agent_kind: str
    availability: str
    status: str = "active"
    provider_kind: str = ""
    priority: int = 0

    def __post_init__(self) -> None:
        for field in ("ai_id", "name", "agent_kind", "availability", "status"):
            if not isinstance(getattr(self, field), str) or not getattr(self, field).strip():
                raise HRDirectoryValidationError(f"{field} must not be empty")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise HRDirectoryValidationError("priority must be an integer")


@dataclass(frozen=True, slots=True)
class RosterSourceSnapshot:
    source: str
    agents: tuple[RosterObservation, ...] = ()
    available: bool = True
    error: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source.strip():
            raise HRDirectoryValidationError("source must not be empty")
        if self.available and self.error:
            raise HRDirectoryValidationError("available roster source cannot contain an error")
        if not self.available and self.agents:
            raise HRDirectoryValidationError("unavailable roster source cannot contain observations")
        if not self.available and not self.error.strip():
            raise HRDirectoryValidationError("unavailable roster source requires an error")


@dataclass(frozen=True, slots=True)
class DirectoryAgentState:
    agent: AgentRecord
    report_eligible: bool
    assessment_eligible: bool


@dataclass(frozen=True, slots=True)
class DirectoryFailure:
    ai_id: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class DirectorySourceFailure:
    source: str
    error: str


@dataclass(frozen=True, slots=True)
class DirectoryReconciliationResult:
    agents: tuple[DirectoryAgentState, ...]
    created: tuple[str, ...]
    updated: tuple[str, ...]
    reactivated: tuple[str, ...]
    inactivated: tuple[str, ...]
    unchanged: tuple[str, ...]
    source_errors: tuple[str, ...]
    source_failures: tuple[DirectorySourceFailure, ...]
    failures: tuple[DirectoryFailure, ...]
    authoritative_absence: bool


@dataclass(frozen=True, slots=True)
class _MergedObservation:
    ai_id: str
    name: str
    agent_kind: str
    provider_kind: str
    status: str
    availability: str
    source: str


class HRDirectoryService:
    """Reconciles complete source snapshots into the stable HR Agent directory."""

    def __init__(self, repository: HRRepository, *, hr_ai_id: str = "hr"):
        if not isinstance(repository, HRRepository):
            raise HRDirectoryValidationError("repository must be an HRRepository")
        if not isinstance(hr_ai_id, str) or not hr_ai_id.strip():
            raise HRDirectoryValidationError("hr_ai_id must not be empty")
        self._repository = repository
        self._hr_ai_id = hr_ai_id

    @staticmethod
    def _all_agents(repository: HRRepository) -> tuple[AgentRecord, ...]:
        agents: list[AgentRecord] = []
        cursor = None
        while True:
            page = repository.list_agents(limit=100, cursor=cursor)
            agents.extend(page.items)
            if page.next_cursor is None:
                return tuple(agents)
            cursor = page.next_cursor

    @staticmethod
    def _merge(ai_id: str, observations: Sequence[tuple[str, RosterObservation]]) -> _MergedObservation:
        ordered = sorted(observations, key=lambda item: (-item[1].priority, item[0]))
        active = [item for _, item in ordered if item.status == "active"]
        preferred = active[0] if active else ordered[0][1]
        if active:
            status = "active"
        else:
            status = max(
                (item.status for _, item in ordered),
                key=lambda value: STATUS_PRIORITY.get(value, 0),
            )
        available = [
            item.availability
            for item in active
            if item.availability not in INELIGIBLE_AVAILABILITY
        ]
        availability = (
            available[0]
            if available
            else (active[0].availability if active else ordered[0][1].availability)
        )
        agent_kind = max(
            (item.agent_kind for _, item in ordered),
            key=lambda value: KIND_PRIORITY.get(value, 0),
        )
        provider_kind = next(
            (
                item.provider_kind
                for item in (*active, *(item for _, item in ordered))
                if item.provider_kind
            ),
            "",
        )
        sources = "+".join(sorted({source for source, _ in observations}))
        return _MergedObservation(
            ai_id=ai_id,
            name=preferred.name.strip(),
            agent_kind=agent_kind,
            provider_kind=provider_kind,
            status=status,
            availability=availability,
            source=sources,
        )

    def _state(self, agent: AgentRecord) -> DirectoryAgentState:
        eligible = self._eligible(agent)
        return DirectoryAgentState(
            agent=agent,
            report_eligible=eligible,
            assessment_eligible=eligible,
        )

    def _eligible(self, agent: AgentRecord) -> bool:
        return (
            agent.ai_id != self._hr_ai_id
            and agent.status == "active"
            and agent.availability not in INELIGIBLE_AVAILABILITY
        )

    def reconcile(
        self,
        snapshots: Iterable[RosterSourceSnapshot],
    ) -> DirectoryReconciliationResult:
        snapshots = tuple(snapshots)
        if not snapshots:
            raise HRDirectoryValidationError("at least one roster source is required")
        source_names = [snapshot.source.strip() for snapshot in snapshots]
        if len(set(source_names)) != len(source_names):
            raise HRDirectoryValidationError("roster source names must be unique")

        current = {agent.ai_id: agent for agent in self._all_agents(self._repository)}
        grouped: dict[str, list[tuple[str, RosterObservation]]] = {}
        source_errors = []
        source_failures = []
        for snapshot in snapshots:
            if not snapshot.available:
                source_errors.append(snapshot.source)
                source_failures.append(
                    DirectorySourceFailure(snapshot.source, snapshot.error.strip())
                )
                continue
            seen_in_source = set()
            for observation in snapshot.agents:
                if observation.ai_id in seen_in_source:
                    raise HRDirectoryValidationError(
                        f"source {snapshot.source} contains duplicate AI ID {observation.ai_id}"
                    )
                seen_in_source.add(observation.ai_id)
                grouped.setdefault(observation.ai_id, []).append((snapshot.source, observation))

        created: list[str] = []
        updated: list[str] = []
        reactivated: list[str] = []
        inactivated: list[str] = []
        unchanged: list[str] = []
        failures: list[DirectoryFailure] = []
        for ai_id in sorted(grouped):
            merged = self._merge(ai_id, grouped[ai_id])
            before = current.get(ai_id)
            try:
                after = self._repository.upsert_agent(
                    ai_id=merged.ai_id,
                    name=merged.name,
                    agent_kind=merged.agent_kind,
                    provider_kind=merged.provider_kind,
                    status=merged.status,
                    availability=merged.availability,
                    source=merged.source,
                    expected_revision=before.revision if before is not None else 0,
                )
            except HRRepositoryError as exc:
                failures.append(DirectoryFailure(ai_id, exc.code, str(exc)))
                continue
            current[ai_id] = after
            if before is None:
                created.append(ai_id)
            elif after.revision == before.revision:
                unchanged.append(ai_id)
            else:
                updated.append(ai_id)
                if not self._eligible(before) and self._eligible(after):
                    reactivated.append(ai_id)
                elif self._eligible(before) and not self._eligible(after):
                    inactivated.append(ai_id)

        authoritative_absence = not source_errors
        if authoritative_absence:
            supplied_sources = set(source_names)
            absent = sorted(
                ai_id
                for ai_id, agent in current.items()
                if ai_id not in grouped
                and ai_id != self._hr_ai_id
                and set(agent.discovery_source.split("+")) <= supplied_sources
            )
            for ai_id in absent:
                before = current[ai_id]
                if before.status == "unreachable" and before.availability == "unavailable":
                    unchanged.append(ai_id)
                    continue
                try:
                    after = self._repository.upsert_agent(
                        ai_id=before.ai_id,
                        name=before.name,
                        agent_kind=before.agent_kind,
                        provider_kind=before.provider_kind,
                        status="unreachable",
                        availability="unavailable",
                        source=before.discovery_source,
                        expected_revision=before.revision,
                    )
                except HRRepositoryError as exc:
                    failures.append(DirectoryFailure(ai_id, exc.code, str(exc)))
                    continue
                current[ai_id] = after
                updated.append(ai_id)
                if self._eligible(before):
                    inactivated.append(ai_id)

        final_agents = tuple(self._state(agent) for agent in self._all_agents(self._repository))
        return DirectoryReconciliationResult(
            agents=final_agents,
            created=tuple(created),
            updated=tuple(updated),
            reactivated=tuple(reactivated),
            inactivated=tuple(inactivated),
            unchanged=tuple(sorted(set(unchanged))),
            source_errors=tuple(sorted(source_errors)),
            source_failures=tuple(sorted(source_failures, key=lambda item: item.source)),
            failures=tuple(failures),
            authoritative_absence=authoritative_absence,
        )
