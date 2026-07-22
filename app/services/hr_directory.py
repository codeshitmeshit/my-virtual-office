"""HR-owned roster reconciliation without transport or provider coupling."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Protocol, Sequence

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
    emoji: str = ""
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


class HRConversationPort(Protocol):
    def ask_agent_as_hr(
        self,
        target_ai_id: str,
        message: str,
        conversation_key: str,
        timeout_seconds: float,
    ) -> str | None: ...


class HRSummarizationPort(Protocol):
    def ask_hr(
        self,
        prompt: str,
        conversation_key: str,
        timeout_seconds: float,
    ) -> str | None: ...


@dataclass(frozen=True, slots=True)
class IntroductionProcessingResult:
    ai_id: str
    status: str
    conversation_key: str
    attempt_count: int
    error_code: str


@dataclass(frozen=True, slots=True)
class IntroductionSummaryResult:
    ai_id: str
    status: str
    version: int
    conversation_key: str
    error_code: str


@dataclass(frozen=True, slots=True)
class SafeDirectoryEntry:
    name: str
    introduction: str
    ai_id: str
    availability: str
    readiness: str


@dataclass(frozen=True, slots=True)
class SafeDirectoryPage:
    items: tuple[SafeDirectoryEntry, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class _MergedObservation:
    ai_id: str
    name: str
    emoji: str
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
        emoji = next(
            (
                item.emoji.strip()
                for item in (*active, *(item for _, item in ordered))
                if item.emoji.strip()
            ),
            "",
        )
        sources = "+".join(sorted({source for source, _ in observations}))
        return _MergedObservation(
            ai_id=ai_id,
            name=preferred.name.strip(),
            emoji=emoji,
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
                    emoji=merged.emoji,
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
                        emoji=before.emoji,
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


class HRIntroductionWorkflow:
    """Claims and performs HR-to-Agent introduction requests with failure isolation."""

    def __init__(
        self,
        repository: HRRepository,
        conversation: HRConversationPort,
        *,
        hr_ai_id: str = "hr",
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        claim_token_factory: Callable[[str], str],
        timeout_seconds: float = 30.0,
        claim_lease_seconds: int = 60,
    ):
        if not isinstance(repository, HRRepository):
            raise HRDirectoryValidationError("repository must be an HRRepository")
        if not callable(getattr(conversation, "ask_agent_as_hr", None)):
            raise HRDirectoryValidationError("conversation port is invalid")
        if not callable(claim_token_factory):
            raise HRDirectoryValidationError("claim_token_factory is required")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
            raise HRDirectoryValidationError("timeout_seconds must be numeric")
        if not 0.1 <= float(timeout_seconds) <= 300:
            raise HRDirectoryValidationError("timeout_seconds must be between 0.1 and 300")
        if (
            isinstance(claim_lease_seconds, bool)
            or not isinstance(claim_lease_seconds, int)
            or not 1 <= claim_lease_seconds <= 600
        ):
            raise HRDirectoryValidationError("claim_lease_seconds must be between 1 and 600")
        if claim_lease_seconds <= float(timeout_seconds):
            raise HRDirectoryValidationError("claim lease must be longer than conversation timeout")
        self._repository = repository
        self._conversation = conversation
        self._hr_ai_id = hr_ai_id
        self._clock = clock
        self._claim_token_factory = claim_token_factory
        self._timeout_seconds = float(timeout_seconds)
        self._claim_lease_seconds = claim_lease_seconds

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise HRDirectoryValidationError("introduction clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _keys(ai_id: str) -> tuple[str, str]:
        return (
            f"hr:introduction-request:{ai_id}:initial",
            f"hr:introduction-conversation:{ai_id}:initial",
        )

    def process(
        self,
        ai_ids: Iterable[str],
        *,
        message: str,
    ) -> tuple[IntroductionProcessingResult, ...]:
        if not isinstance(message, str) or not message.strip():
            raise HRDirectoryValidationError("introduction message must not be empty")
        message = message.strip()
        results = []
        for ai_id in tuple(ai_ids):
            occurrence_key, conversation_key = self._keys(ai_id)
            if ai_id == self._hr_ai_id:
                results.append(
                    IntroductionProcessingResult(ai_id, "skipped_hr", conversation_key, 0, "")
                )
                continue
            token = ""
            try:
                request = self._repository.ensure_introduction_request(
                    ai_id=ai_id,
                    occurrence_key=occurrence_key,
                    conversation_key=conversation_key,
                    actor_id=self._hr_ai_id,
                )
                if request.state in {"response_received", "published", "clarification_pending"}:
                    results.append(
                        IntroductionProcessingResult(
                            ai_id,
                            "already_complete",
                            conversation_key,
                            request.attempt_count,
                            "",
                        )
                    )
                    continue
                now = self._now()
                token = self._claim_token_factory(ai_id)
                claim = self._repository.claim_introduction_request(
                    ai_id=ai_id,
                    claimed_by=self._hr_ai_id,
                    claim_token=token,
                    now=now.isoformat(),
                    claim_expires_at=(
                        now + timedelta(seconds=self._claim_lease_seconds)
                    ).isoformat(),
                )
                if claim is None:
                    results.append(
                        IntroductionProcessingResult(
                            ai_id,
                            "claimed_elsewhere",
                            conversation_key,
                            request.attempt_count,
                            "",
                        )
                    )
                    continue
                response = self._conversation.ask_agent_as_hr(
                    ai_id,
                    message,
                    conversation_key,
                    self._timeout_seconds,
                )
                if response is not None and not isinstance(response, str):
                    raise TypeError("conversation response must be text or None")
                raw_response = response if response is not None and response.strip() else None
                finished = self._repository.finish_introduction_request(
                    ai_id=ai_id,
                    claim_token=token,
                    finished_at=self._now().isoformat(),
                    raw_response=raw_response,
                )
                results.append(
                    IntroductionProcessingResult(
                        ai_id,
                        "response_received" if raw_response is not None else "no_response",
                        conversation_key,
                        finished.attempt_count,
                        "",
                    )
                )
            except Exception as exc:
                error_code = getattr(exc, "code", "hr_introduction_conversation_failed")
                if token:
                    try:
                        failed = self._repository.finish_introduction_request(
                            ai_id=ai_id,
                            claim_token=token,
                            finished_at=self._now().isoformat(),
                            raw_response=None,
                            error=f"conversation_failed:{exc.__class__.__name__}",
                        )
                        attempts = failed.attempt_count
                    except Exception:
                        attempts = 0
                else:
                    attempts = 0
                results.append(
                    IntroductionProcessingResult(
                        ai_id,
                        "failed",
                        conversation_key,
                        attempts,
                        str(error_code),
                    )
                )
        return tuple(results)


class HRIntroductionSummarizer:
    """Validates HR structured summaries before versioned publication."""

    def __init__(
        self,
        repository: HRRepository,
        hr: HRSummarizationPort,
        *,
        hr_ai_id: str = "hr",
        timeout_seconds: float = 30.0,
    ):
        if not isinstance(repository, HRRepository):
            raise HRDirectoryValidationError("repository must be an HRRepository")
        if not callable(getattr(hr, "ask_hr", None)):
            raise HRDirectoryValidationError("HR summarization port is invalid")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0.1 <= float(timeout_seconds) <= 300
        ):
            raise HRDirectoryValidationError("timeout_seconds must be between 0.1 and 300")
        self._repository = repository
        self._hr = hr
        self._hr_ai_id = hr_ai_id
        self._timeout_seconds = float(timeout_seconds)

    @staticmethod
    def _conversation_key(ai_id: str, version: int, raw_response: str) -> str:
        fingerprint = hashlib.sha256(raw_response.encode("utf-8")).hexdigest()[:16]
        return f"hr:introduction-summary:{ai_id}:v{version}:{fingerprint}"

    @staticmethod
    def _prompt(ai_id: str, raw_response: str, previous_introduction: str) -> str:
        previous = previous_introduction or "(none)"
        return (
            "Return only JSON with keys schemaVersion, introduction, supportingEvidence, "
            "materialConflict, clarificationQuestion. schemaVersion must be 1. "
            "supportingEvidence must contain exact excerpts from the Agent response. "
            "Do not invent responsibilities. If the response materially conflicts with the "
            "previous introduction, set materialConflict=true, keep introduction empty, and "
            "provide one neutral clarificationQuestion.\n"
            f"Agent AI ID: {ai_id}\n"
            f"Previous introduction: {previous}\n"
            f"Agent response:\n{raw_response}"
        )

    @staticmethod
    def _validate_output(payload: str, raw_response: str, *, has_previous: bool) -> dict[str, object]:
        if not isinstance(payload, str) or not payload.strip():
            raise HRDirectoryValidationError("HR returned no structured introduction")
        if len(payload) > 20_000:
            raise HRDirectoryValidationError("HR structured introduction is too large")
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise HRDirectoryValidationError("HR structured introduction is malformed JSON") from exc
        expected_keys = {
            "schemaVersion",
            "introduction",
            "supportingEvidence",
            "materialConflict",
            "clarificationQuestion",
        }
        if not isinstance(value, dict) or set(value) != expected_keys:
            raise HRDirectoryValidationError("HR structured introduction has an invalid schema")
        if value["schemaVersion"] != 1 or isinstance(value["schemaVersion"], bool):
            raise HRDirectoryValidationError("HR introduction schema version is unsupported")
        introduction = value["introduction"]
        evidence = value["supportingEvidence"]
        conflict = value["materialConflict"]
        question = value["clarificationQuestion"]
        if not isinstance(introduction, str) or len(introduction.strip()) > 1_000:
            raise HRDirectoryValidationError("HR introduction text is invalid")
        if (
            not isinstance(evidence, list)
            or not 1 <= len(evidence) <= 10
            or any(
                not isinstance(item, str)
                or not item.strip()
                or len(item) > 500
                or item not in raw_response
                for item in evidence
            )
        ):
            raise HRDirectoryValidationError("HR introduction lacks supported evidence")
        if not isinstance(conflict, bool) or not isinstance(question, str):
            raise HRDirectoryValidationError("HR conflict fields are invalid")
        if conflict:
            if not has_previous or introduction.strip() or not question.strip() or len(question) > 1_000:
                raise HRDirectoryValidationError("HR clarification result is invalid")
        elif not introduction.strip() or question.strip():
            raise HRDirectoryValidationError("HR publication result is invalid")
        return value

    def summarize(
        self,
        ai_id: str,
        *,
        expected_version: int,
        raw_response: str | None = None,
    ) -> IntroductionSummaryResult:
        current = self._repository.get_current_introduction(ai_id)
        if current is None:
            return IntroductionSummaryResult(ai_id, "missing_response", 0, "", "hr_introduction_missing")
        if current.version != expected_version:
            return IntroductionSummaryResult(
                ai_id,
                "failed",
                current.version,
                "",
                "hr_introduction_version_conflict",
            )
        if current.state == "published" and raw_response is None:
            return IntroductionSummaryResult(ai_id, "already_published", current.version, "", "")
        if current.state == "clarification_pending" and raw_response is None:
            return IntroductionSummaryResult(
                ai_id,
                "awaiting_clarification",
                current.version,
                "",
                "",
            )
        candidate = raw_response if raw_response is not None else current.raw_response
        if not isinstance(candidate, str) or not candidate.strip():
            return IntroductionSummaryResult(
                ai_id,
                "missing_response",
                current.version,
                "",
                "hr_introduction_missing",
            )
        if current.state == "published" and candidate == current.raw_response:
            return IntroductionSummaryResult(ai_id, "already_published", current.version, "", "")
        key = self._conversation_key(ai_id, current.version, candidate)
        try:
            payload = self._hr.ask_hr(
                self._prompt(ai_id, candidate, current.introduction),
                key,
                self._timeout_seconds,
            )
            value = self._validate_output(
                payload,
                candidate,
                has_previous=bool(current.introduction),
            )
            conflict = bool(value["materialConflict"])
            saved = self._repository.save_introduction(
                ai_id=ai_id,
                state="clarification_pending" if conflict else "published",
                raw_response=candidate,
                introduction=current.introduction if conflict else str(value["introduction"]).strip(),
                source="hr-structured-summary",
                actor_id=self._hr_ai_id,
                clarification_question=(
                    str(value["clarificationQuestion"]).strip() if conflict else ""
                ),
                expected_version=current.version,
            )
            return IntroductionSummaryResult(
                ai_id,
                "clarification_pending" if conflict else "published",
                saved.version,
                key,
                "",
            )
        except HRRepositoryError as exc:
            return IntroductionSummaryResult(ai_id, "failed", current.version, key, exc.code)
        except Exception:
            return IntroductionSummaryResult(
                ai_id,
                "failed",
                current.version,
                key,
                "hr_introduction_summary_invalid",
            )


class HRDirectoryQuery:
    """Builds the allowlisted Agent-facing directory projection."""

    READINESS = frozenset(
        {
            "pending",
            "awaiting_hr_summary",
            "clarification_pending",
            "ready",
            "failed",
        }
    )

    def __init__(self, repository: HRRepository):
        if not isinstance(repository, HRRepository):
            raise HRDirectoryValidationError("repository must be an HRRepository")
        self._repository = repository

    @staticmethod
    def _readiness(state: str | None) -> str:
        return {
            None: "pending",
            "introduction_pending": "pending",
            "response_received": "awaiting_hr_summary",
            "clarification_pending": "clarification_pending",
            "published": "ready",
            "failed": "failed",
        }.get(state, "pending")

    @staticmethod
    def _availability(agent: AgentRecord) -> str:
        return agent.availability if agent.status == "active" else "unavailable"

    @staticmethod
    def _encode_offset(offset: int) -> str:
        payload = json.dumps([offset], separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_offset(cursor: str | None) -> int:
        if cursor is None:
            return 0
        if not isinstance(cursor, str) or not cursor or len(cursor) > 256:
            raise HRDirectoryValidationError("directory cursor is invalid")
        try:
            padding = "=" * (-len(cursor) % 4)
            payload = base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
            decoded = json.loads(payload.decode("utf-8"))
        except (binascii.Error, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise HRDirectoryValidationError("directory cursor is invalid") from exc
        if (
            not isinstance(decoded, list)
            or len(decoded) != 1
            or isinstance(decoded[0], bool)
            or not isinstance(decoded[0], int)
            or not 0 <= decoded[0] <= 1_000_000
        ):
            raise HRDirectoryValidationError("directory cursor is invalid")
        return decoded[0]

    def _entries(self) -> tuple[SafeDirectoryEntry, ...]:
        entries = []
        for agent in HRDirectoryService._all_agents(self._repository):
            introduction = self._repository.get_current_introduction(agent.ai_id)
            entries.append(
                SafeDirectoryEntry(
                    name=agent.name,
                    introduction=introduction.introduction if introduction is not None else "",
                    ai_id=agent.ai_id,
                    availability=self._availability(agent),
                    readiness=self._readiness(
                        introduction.state if introduction is not None else None
                    ),
                )
            )
        return tuple(sorted(entries, key=lambda item: item.ai_id))

    def get(self, ai_id: str) -> SafeDirectoryEntry | None:
        if not isinstance(ai_id, str) or not ai_id.strip():
            raise HRDirectoryValidationError("ai_id must not be empty")
        agent = self._repository.get_agent(ai_id)
        if agent is None:
            return None
        introduction = self._repository.get_current_introduction(ai_id)
        return SafeDirectoryEntry(
            name=agent.name,
            introduction=introduction.introduction if introduction is not None else "",
            ai_id=agent.ai_id,
            availability=self._availability(agent),
            readiness=self._readiness(
                introduction.state if introduction is not None else None
            ),
        )

    def list(
        self,
        *,
        availability: str | None = None,
        readiness: str | None = None,
        query: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> SafeDirectoryPage:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise HRDirectoryValidationError("limit must be between 1 and 100")
        if availability is not None and (
            not isinstance(availability, str) or not availability.strip()
        ):
            raise HRDirectoryValidationError("availability filter is invalid")
        if readiness is not None and readiness not in self.READINESS:
            raise HRDirectoryValidationError("readiness filter is invalid")
        if query is not None and (
            not isinstance(query, str) or not query.strip() or len(query.strip()) > 200
        ):
            raise HRDirectoryValidationError("directory query is invalid")
        offset = self._decode_offset(cursor)
        needle = query.strip().casefold() if query is not None else None
        filtered = []
        for item in self._entries():
            if availability is not None and item.availability != availability:
                continue
            if readiness is not None and item.readiness != readiness:
                continue
            if needle is not None and not any(
                needle in value.casefold()
                for value in (item.ai_id, item.name, item.introduction)
            ):
                continue
            filtered.append(item)
        items = tuple(filtered[offset : offset + limit])
        next_offset = offset + len(items)
        next_cursor = self._encode_offset(next_offset) if next_offset < len(filtered) else None
        return SafeDirectoryPage(items=items, next_cursor=next_cursor)
