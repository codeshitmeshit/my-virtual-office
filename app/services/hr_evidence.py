"""Bounded, read-only evidence ports and sanitization for HR assessment."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date
from itertools import islice
from typing import Iterable, Protocol


class HREvidenceValidationError(ValueError):
    code = "hr_evidence_validation_failed"


@dataclass(frozen=True, slots=True)
class EvidenceCandidate:
    evidence_type: str
    reference_id: str
    summary: str
    evidence_date: str | None
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class SanitizedEvidence:
    evidence_type: str
    reference_id: str
    summary: str
    evidence_date: str | None
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class EvidenceSourceFailure:
    source: str
    error_code: str


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    ai_id: str
    local_date: str
    items: tuple[SanitizedEvidence, ...]
    failures: tuple[EvidenceSourceFailure, ...]
    truncated_sources: tuple[str, ...]


class ProjectEvidencePort(Protocol):
    def read_project_transitions(
        self, ai_id: str, local_date: str
    ) -> Iterable[EvidenceCandidate]: ...


class TaskEvidencePort(Protocol):
    def read_task_transitions(
        self, ai_id: str, local_date: str
    ) -> Iterable[EvidenceCandidate]: ...


class MeetingEvidencePort(Protocol):
    def read_meeting_contributions(
        self, ai_id: str, local_date: str
    ) -> Iterable[EvidenceCandidate]: ...


class ArtifactEvidencePort(Protocol):
    def read_artifact_metadata(
        self, ai_id: str, local_date: str
    ) -> Iterable[EvidenceCandidate]: ...


class ExecutionEvidencePort(Protocol):
    def read_execution_results(
        self, ai_id: str, local_date: str
    ) -> Iterable[EvidenceCandidate]: ...


class RuntimeEvidencePort(Protocol):
    def read_blockers_and_waiting(
        self, ai_id: str, local_date: str
    ) -> Iterable[EvidenceCandidate]: ...


@dataclass(frozen=True, slots=True)
class HREvidencePorts:
    projects: ProjectEvidencePort
    tasks: TaskEvidencePort
    meetings: MeetingEvidencePort
    artifacts: ArtifactEvidencePort
    executions: ExecutionEvidencePort
    runtime: RuntimeEvidencePort


class HREvidenceCollector:
    """Reads each source independently and emits only bounded allowlisted evidence."""

    SOURCE_METHODS = (
        ("projects", "read_project_transitions"),
        ("tasks", "read_task_transitions"),
        ("meetings", "read_meeting_contributions"),
        ("artifacts", "read_artifact_metadata"),
        ("executions", "read_execution_results"),
        ("runtime", "read_blockers_and_waiting"),
    )
    SOURCE_TYPES = {
        "projects": frozenset({"project_transition"}),
        "tasks": frozenset({"task_transition"}),
        "meetings": frozenset({"meeting_contribution"}),
        "artifacts": frozenset({"artifact"}),
        "executions": frozenset({"execution_result"}),
        "runtime": frozenset({"blocker", "waiting_state"}),
    }
    METADATA_KEYS = {
        "project_transition": frozenset(
            {"projectId", "fromState", "toState", "transitionType"}
        ),
        "task_transition": frozenset(
            {"projectId", "taskId", "fromState", "toState", "resultState"}
        ),
        "meeting_contribution": frozenset(
            {"meetingId", "agendaItemId", "contributionType"}
        ),
        "artifact": frozenset({"artifactId", "artifactType", "projectId", "taskId"}),
        "execution_result": frozenset(
            {"executionId", "projectId", "taskId", "resultState", "attempt"}
        ),
        "blocker": frozenset({"projectId", "taskId", "blockerType", "state"}),
        "waiting_state": frozenset({"projectId", "taskId", "waitingOn", "state"}),
    }
    SENSITIVE_KEY = re.compile(
        r"(?:token|secret|password|credential|authorization|cookie|transcript|raw|content)",
        re.IGNORECASE,
    )
    SENSITIVE_VALUE = re.compile(
        r"(?:bearer\s+\S+|(?:token|secret|password|credential|authorization)\s*[:=]\s*\S+)",
        re.IGNORECASE,
    )
    MAX_SUMMARY_CHARS = 500
    MAX_REFERENCE_CHARS = 256

    def __init__(self, ports: HREvidencePorts, *, per_source_cap: int = 20):
        if not isinstance(ports, HREvidencePorts):
            raise HREvidenceValidationError("evidence ports are required")
        if (
            isinstance(per_source_cap, bool)
            or not isinstance(per_source_cap, int)
            or not 1 <= per_source_cap <= 100
        ):
            raise HREvidenceValidationError("per_source_cap must be between 1 and 100")
        for source, method in self.SOURCE_METHODS:
            if not callable(getattr(getattr(ports, source), method, None)):
                raise HREvidenceValidationError(f"{source} evidence port is invalid")
        self._ports = ports
        self._per_source_cap = per_source_cap

    @staticmethod
    def _local_date(value: object) -> str:
        if not isinstance(value, str):
            raise HREvidenceValidationError("local_date must use YYYY-MM-DD")
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError
        except ValueError as exc:
            raise HREvidenceValidationError("local_date must use YYYY-MM-DD") from exc
        return value

    @classmethod
    def _safe_text(cls, value: object, field: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise HREvidenceValidationError(f"{field} is invalid")
        text = value.strip()
        if any(ord(character) < 32 and character not in "\n\r\t" for character in text):
            raise HREvidenceValidationError(f"{field} is invalid")
        return cls.SENSITIVE_VALUE.sub("[redacted]", text)

    @classmethod
    def _sanitize_metadata(cls, candidate: EvidenceCandidate) -> dict[str, object]:
        if not isinstance(candidate.metadata, dict):
            raise HREvidenceValidationError("evidence metadata must be an object")
        allowed = cls.METADATA_KEYS[candidate.evidence_type]
        result = {}
        for key, value in candidate.metadata.items():
            if not isinstance(key, str) or cls.SENSITIVE_KEY.search(key) or key not in allowed:
                continue
            if isinstance(value, bool) or value is None:
                result[key] = value
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                if math.isfinite(value):
                    result[key] = value
            elif isinstance(value, str):
                result[key] = cls._safe_text(value, f"metadata.{key}", 256)
        return result

    @classmethod
    def _sanitize(cls, source: str, candidate: object) -> SanitizedEvidence:
        if not isinstance(candidate, EvidenceCandidate):
            raise HREvidenceValidationError("evidence source returned an invalid item")
        if candidate.evidence_type not in cls.SOURCE_TYPES[source]:
            raise HREvidenceValidationError("evidence type does not match its source")
        evidence_date = (
            cls._local_date(candidate.evidence_date)
            if candidate.evidence_date is not None
            else None
        )
        return SanitizedEvidence(
            evidence_type=candidate.evidence_type,
            reference_id=cls._safe_text(
                candidate.reference_id,
                "reference_id",
                cls.MAX_REFERENCE_CHARS,
            ),
            summary=cls._safe_text(candidate.summary, "summary", cls.MAX_SUMMARY_CHARS),
            evidence_date=evidence_date,
            metadata=cls._sanitize_metadata(candidate),
        )

    def collect(self, ai_id: str, *, local_date: str) -> EvidenceBundle:
        if not isinstance(ai_id, str) or not ai_id or any(character.isspace() for character in ai_id):
            raise HREvidenceValidationError("ai_id is invalid")
        local_date = self._local_date(local_date)
        items = []
        failures = []
        truncated = []
        seen = set()
        for source, method_name in self.SOURCE_METHODS:
            port = getattr(self._ports, source)
            try:
                candidates = tuple(
                    islice(
                        getattr(port, method_name)(ai_id, local_date),
                        self._per_source_cap + 1,
                    )
                )
                if len(candidates) > self._per_source_cap:
                    truncated.append(source)
                for candidate in candidates[: self._per_source_cap]:
                    sanitized = self._sanitize(source, candidate)
                    if (
                        sanitized.evidence_date is not None
                        and sanitized.evidence_date != local_date
                    ):
                        raise HREvidenceValidationError(
                            "evidence date does not match requested date"
                        )
                    identity = (sanitized.evidence_type, sanitized.reference_id)
                    if identity not in seen:
                        items.append(sanitized)
                        seen.add(identity)
            except Exception as exc:
                failures.append(
                    EvidenceSourceFailure(
                        source,
                        str(getattr(exc, "code", "evidence_source_failed")),
                    )
                )
        items.sort(key=lambda item: (item.evidence_date or "", item.evidence_type, item.reference_id))
        return EvidenceBundle(
            ai_id=ai_id,
            local_date=local_date,
            items=tuple(items),
            failures=tuple(failures),
            truncated_sources=tuple(truncated),
        )
