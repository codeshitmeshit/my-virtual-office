"""Strict structured schema for non-ranking HR performance assessments."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterable, Protocol

from services.hr_evidence import EvidenceBundle, HREvidenceCollector, SanitizedEvidence
from services.hr_repository import AssessmentRecord, HRRepository


class HRAssessmentValidationError(ValueError):
    code = "hr_assessment_validation_failed"


@dataclass(frozen=True, slots=True)
class AssessmentEvidenceReference:
    evidence_type: str
    reference_id: str
    rationale: str


@dataclass(frozen=True, slots=True)
class ParsedHRAssessment:
    agent_ai_id: str
    local_date: str
    principal_contributions: tuple[str, ...]
    workload: str
    workload_score: int
    rationale: str
    evidence_references: tuple[AssessmentEvidenceReference, ...]
    blockers: tuple[str, ...]
    strengths: tuple[str, ...]
    improvements: tuple[str, ...]
    runtime_diagnosis: str
    information_sufficiency: str
    information_sufficiency_status: str
    hr_ai_id: str
    assessed_at: str


class HRAssessmentConversationPort(Protocol):
    def ask_hr(
        self,
        prompt: str,
        conversation_key: str,
        timeout_seconds: float,
    ) -> str | None: ...


@dataclass(frozen=True, slots=True)
class AssessmentProcessingResult:
    ai_id: str
    local_date: str
    status: str
    assessment: AssessmentRecord | None
    error_code: str


class HRAssessmentParser:
    """Rejects unsupported assessment fields, scores, ranks, and unbounded output."""

    ROOT_KEYS = frozenset(
        {
            "schemaVersion",
            "agentAiId",
            "localDate",
            "principalContributions",
            "workload",
            "workloadScore",
            "rationale",
            "evidenceReferences",
            "blockers",
            "strengths",
            "improvements",
            "runtimeDiagnosis",
            "informationSufficiency",
            "hrAiId",
            "assessedAt",
        }
    )
    WORKLOADS = frozenset(
        {"low", "appropriate", "high", "overloaded", "insufficient_information"}
    )
    MAX_OUTPUT_CHARS = 50_000
    MAX_LIST_ITEMS = 50
    MAX_TEXT_CHARS = 2_000
    MAX_LONG_TEXT_CHARS = 8_000

    def __init__(self, *, hr_ai_id: str = "hr"):
        if not isinstance(hr_ai_id, str) or not hr_ai_id or any(
            character.isspace() for character in hr_ai_id
        ):
            raise HRAssessmentValidationError("hr_ai_id is invalid")
        self._hr_ai_id = hr_ai_id

    @staticmethod
    def _date(value: object) -> str:
        if not isinstance(value, str):
            raise HRAssessmentValidationError("localDate must use YYYY-MM-DD")
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError
        except ValueError as exc:
            raise HRAssessmentValidationError("localDate must use YYYY-MM-DD") from exc
        return value

    @classmethod
    def _text(cls, value: object, field: str, *, maximum: int | None = None) -> str:
        limit = cls.MAX_TEXT_CHARS if maximum is None else maximum
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise HRAssessmentValidationError(f"{field} is invalid")
        result = value.strip()
        if any(ord(character) < 32 and character not in "\n\r\t" for character in result):
            raise HRAssessmentValidationError(f"{field} is invalid")
        return result

    @classmethod
    def _text_list(cls, value: object, field: str) -> tuple[str, ...]:
        if not isinstance(value, list) or len(value) > cls.MAX_LIST_ITEMS:
            raise HRAssessmentValidationError(f"{field} must be a bounded list")
        result = tuple(cls._text(item, field) for item in value)
        if len(set(result)) != len(result):
            raise HRAssessmentValidationError(f"{field} contains duplicates")
        return result

    @classmethod
    def _evidence_references(
        cls, value: object
    ) -> tuple[AssessmentEvidenceReference, ...]:
        if not isinstance(value, list) or len(value) > 100:
            raise HRAssessmentValidationError("evidenceReferences must be a bounded list")
        result = []
        seen = set()
        for item in value:
            if not isinstance(item, dict) or set(item) != {
                "evidenceType",
                "referenceId",
                "rationale",
            }:
                raise HRAssessmentValidationError("evidenceReferences contains an invalid item")
            reference = AssessmentEvidenceReference(
                evidence_type=cls._text(item["evidenceType"], "evidenceType", maximum=64),
                reference_id=cls._text(item["referenceId"], "referenceId", maximum=256),
                rationale=cls._text(
                    item["rationale"],
                    "evidence rationale",
                    maximum=cls.MAX_TEXT_CHARS,
                ),
            )
            identity = (reference.evidence_type, reference.reference_id)
            if identity in seen:
                raise HRAssessmentValidationError("evidenceReferences contains duplicates")
            seen.add(identity)
            result.append(reference)
        return tuple(result)

    @staticmethod
    def _timestamp(value: object) -> str:
        if not isinstance(value, str):
            raise HRAssessmentValidationError("assessedAt must be an ISO timestamp")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise HRAssessmentValidationError("assessedAt must be an ISO timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise HRAssessmentValidationError("assessedAt must include a timezone")
        return parsed.astimezone(timezone.utc).isoformat()

    def parse(
        self,
        output: str,
        *,
        expected_ai_id: str,
        expected_local_date: str,
    ) -> ParsedHRAssessment:
        if not isinstance(output, str) or not output.strip():
            raise HRAssessmentValidationError("HR returned no assessment")
        if len(output) > self.MAX_OUTPUT_CHARS:
            raise HRAssessmentValidationError("HR assessment is too large")
        try:
            value = json.loads(output)
        except json.JSONDecodeError as exc:
            raise HRAssessmentValidationError("HR assessment is invalid JSON") from exc
        if not isinstance(value, dict) or set(value) != self.ROOT_KEYS:
            raise HRAssessmentValidationError("HR assessment has unsupported fields")
        if isinstance(value["schemaVersion"], bool) or value["schemaVersion"] != 1:
            raise HRAssessmentValidationError("unsupported assessment schema")
        local_date = self._date(value["localDate"])
        if local_date != self._date(expected_local_date):
            raise HRAssessmentValidationError("assessment date does not match")
        agent_ai_id = self._text(value["agentAiId"], "agentAiId", maximum=256)
        if agent_ai_id != expected_ai_id:
            raise HRAssessmentValidationError("assessment Agent does not match")
        hr_ai_id = self._text(value["hrAiId"], "hrAiId", maximum=256)
        if hr_ai_id != self._hr_ai_id:
            raise HRAssessmentValidationError("assessment HR identity does not match")
        workload = value["workload"]
        if not isinstance(workload, str) or workload not in self.WORKLOADS:
            raise HRAssessmentValidationError("assessment workload is unsupported")
        workload_score = value["workloadScore"]
        if (
            isinstance(workload_score, bool)
            or not isinstance(workload_score, int)
            or not 1 <= workload_score <= 10
        ):
            raise HRAssessmentValidationError("assessment workload score is unsupported")
        sufficiency = value["informationSufficiency"]
        if not isinstance(sufficiency, dict) or set(sufficiency) != {"status", "explanation"}:
            raise HRAssessmentValidationError("informationSufficiency is invalid")
        sufficiency_status = sufficiency["status"]
        if not isinstance(sufficiency_status, str) or sufficiency_status not in {
            "sufficient",
            "insufficient",
        }:
            raise HRAssessmentValidationError("information sufficiency status is unsupported")
        if (workload == "insufficient_information") != (sufficiency_status == "insufficient"):
            raise HRAssessmentValidationError("workload and information sufficiency conflict")
        evidence = self._evidence_references(value["evidenceReferences"])
        contributions = self._text_list(
            value["principalContributions"], "principalContributions"
        )
        if sufficiency_status == "sufficient" and (not evidence or not contributions):
            raise HRAssessmentValidationError(
                "sufficient assessment requires contributions and evidence"
            )
        return ParsedHRAssessment(
            agent_ai_id=agent_ai_id,
            local_date=local_date,
            principal_contributions=contributions,
            workload=workload,
            workload_score=workload_score,
            rationale=self._text(
                value["rationale"],
                "rationale",
                maximum=self.MAX_LONG_TEXT_CHARS,
            ),
            evidence_references=evidence,
            blockers=self._text_list(value["blockers"], "blockers"),
            strengths=self._text_list(value["strengths"], "strengths"),
            improvements=self._text_list(value["improvements"], "improvements"),
            runtime_diagnosis=self._text(
                value["runtimeDiagnosis"],
                "runtimeDiagnosis",
                maximum=4_000,
            ),
            information_sufficiency=self._text(
                sufficiency["explanation"],
                "information sufficiency explanation",
                maximum=4_000,
            ),
            information_sufficiency_status=sufficiency_status,
            hr_ai_id=hr_ai_id,
            assessed_at=self._timestamp(value["assessedAt"]),
        )


class HRAssessmentPolicy:
    """Rejects punitive automation, rankings, and numeric scoring in HR judgment."""

    FORBIDDEN = re.compile(
        r"(?:\b(?:scor(?:e|es|ed|ing)|rank(?:s|ed|ing)?|rating|leaderboard|"
        r"eliminat(?:e|ed|ion))\b|"
        r"\b(?:paus(?:e|ed)|delet(?:e|ed|ion)|terminat(?:e|ed|ion)|"
        r"remov(?:e|ed|al)|reassign(?:ed|ment)?)\b.{0,40}\bagent\b|"
        r"\bagent\b.{0,40}\b(?:paus(?:e|ed)|delet(?:e|ed|ion)|"
        r"terminat(?:e|ed|ion)|remov(?:e|ed|al)|reassign(?:ed|ment)?)\b|"
        r"评分|分数|排名|排行榜|淘汰|暂停.{0,20}Agent|删除.{0,20}Agent|重新分配)",
        re.IGNORECASE,
    )

    @classmethod
    def validate(cls, assessment: ParsedHRAssessment) -> ParsedHRAssessment:
        if not isinstance(assessment, ParsedHRAssessment):
            raise HRAssessmentValidationError("assessment policy input is invalid")
        texts = (
            *assessment.principal_contributions,
            assessment.rationale,
            *(item.rationale for item in assessment.evidence_references),
            *assessment.blockers,
            *assessment.strengths,
            *assessment.improvements,
            assessment.runtime_diagnosis,
            assessment.information_sufficiency,
        )
        if any(cls.FORBIDDEN.search(text) for text in texts):
            raise HRAssessmentValidationError(
                "assessment contains a punitive, ranking, or scoring directive"
            )
        return assessment


class HRAssessmentOrchestrator:
    """Allows HR alone to assess closed-cycle reports with bounded evidence."""

    def __init__(
        self,
        repository: HRRepository,
        evidence: HREvidenceCollector,
        hr: HRAssessmentConversationPort,
        *,
        parser: HRAssessmentParser | None = None,
        policy: HRAssessmentPolicy | None = None,
        hr_ai_id: str = "hr",
        timeout_seconds: float = 45.0,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        claim_token_factory: Callable[[str], str] = lambda _job_id: secrets.token_urlsafe(24),
        claim_lease_seconds: int = 90,
        retry_limit: int = 3,
    ):
        if not isinstance(repository, HRRepository):
            raise HRAssessmentValidationError("repository must be an HRRepository")
        if not isinstance(evidence, HREvidenceCollector):
            raise HRAssessmentValidationError("evidence collector is invalid")
        if not callable(getattr(hr, "ask_hr", None)):
            raise HRAssessmentValidationError("HR assessment port is invalid")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0.1 <= float(timeout_seconds) <= 300
        ):
            raise HRAssessmentValidationError("timeout_seconds must be between 0.1 and 300")
        if not callable(claim_token_factory):
            raise HRAssessmentValidationError("claim_token_factory is invalid")
        if (
            isinstance(claim_lease_seconds, bool)
            or not isinstance(claim_lease_seconds, int)
            or not 1 <= claim_lease_seconds <= 600
            or claim_lease_seconds <= float(timeout_seconds)
        ):
            raise HRAssessmentValidationError(
                "claim lease must exceed timeout and be at most 600 seconds"
            )
        if (
            isinstance(retry_limit, bool)
            or not isinstance(retry_limit, int)
            or not 0 <= retry_limit <= 10
        ):
            raise HRAssessmentValidationError("retry_limit must be between 0 and 10")
        self._repository = repository
        self._evidence = evidence
        self._hr = hr
        self._parser = parser or HRAssessmentParser(hr_ai_id=hr_ai_id)
        self._policy = policy or HRAssessmentPolicy()
        self._hr_ai_id = hr_ai_id
        self._timeout_seconds = float(timeout_seconds)
        self._clock = clock
        self._claim_token_factory = claim_token_factory
        self._claim_lease_seconds = claim_lease_seconds
        self._max_attempts = retry_limit + 1

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise HRAssessmentValidationError("assessment clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _source_group(item: SanitizedEvidence) -> str:
        if item.evidence_type in {"project_transition", "task_transition"}:
            return "work_tracking"
        if item.evidence_type in {"blocker", "waiting_state"}:
            return "runtime"
        return item.evidence_type

    @classmethod
    def _evidence_is_adequate(cls, report_has_raw: bool, bundle: EvidenceBundle) -> bool:
        groups = {cls._source_group(item) for item in bundle.items}
        if report_has_raw:
            groups.add("agent_report")
        return len(groups) >= 2

    @staticmethod
    def _evidence_payload(bundle: EvidenceBundle) -> list[dict[str, object]]:
        return [
            {
                "evidenceType": item.evidence_type,
                "referenceId": item.reference_id,
                "summary": item.summary,
                "evidenceDate": item.evidence_date,
                "metadata": item.metadata,
            }
            for item in bundle.items
        ]

    @classmethod
    def _evidence_version(cls, report_revision: int, bundle: EvidenceBundle) -> str:
        payload = {
            "reportRevision": report_revision,
            "items": cls._evidence_payload(bundle),
            "failures": [
                {"source": item.source, "errorCode": item.error_code}
                for item in bundle.failures
            ],
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    @classmethod
    def _prompt(cls, report, bundle: EvidenceBundle, *, adequate: bool) -> str:
        policy = (
            "Evidence is sufficient for a cautious workload conclusion."
            if adequate
            else "Evidence is insufficient. workload MUST be insufficient_information; "
            "informationSufficiency.status MUST be insufficient; principalContributions and "
            "strengths MUST be empty. Do not infer low work from non-submission or attendance."
        )
        schema = (
            "Return JSON only with exactly: schemaVersion, agentAiId, localDate, "
            "principalContributions, workload, workloadScore, rationale, evidenceReferences, blockers, "
            "strengths, improvements, runtimeDiagnosis, informationSufficiency, hrAiId, "
            "assessedAt. schemaVersion=1. Evidence reference items contain evidenceType, "
            "referenceId, rationale. informationSufficiency contains status and explanation. "
            "workloadScore MUST be an integer from 1 to 10 where 1 is minimal observable workload "
            "and 10 is extreme observable workload. Never output ranks, leaderboards, elimination, "
            "pause, delete, or reassign actions."
        )
        report_payload = {
            "submissionState": report.submission_state,
            "rawResponse": report.raw_response,
            "normalized": report.normalized,
            "requestedAt": report.requested_at,
            "windowClosedAt": report.window_closed_at,
            "submittedAt": report.submitted_at,
        }
        return (
            f"{schema}\n{policy}\nAgent AI ID: {report.ai_id}\nDate: {report.local_date}\n"
            f"Agent report: {json.dumps(report_payload, ensure_ascii=False)}\n"
            f"Allowed evidence: {json.dumps(cls._evidence_payload(bundle), ensure_ascii=False)}"
        )

    @staticmethod
    def _referenced_evidence(
        parsed: ParsedHRAssessment,
        bundle: EvidenceBundle,
    ) -> list[dict[str, object]]:
        available = {
            (item.evidence_type, item.reference_id): item for item in bundle.items
        }
        result = []
        for reference in parsed.evidence_references:
            item = available.get((reference.evidence_type, reference.reference_id))
            if item is None:
                raise HRAssessmentValidationError(
                    "assessment references unavailable evidence"
                )
            result.append(
                {
                    "evidence_type": item.evidence_type,
                    "reference_id": item.reference_id,
                    "summary": item.summary,
                    "evidence_date": item.evidence_date,
                    "metadata": {**item.metadata, "assessmentRationale": reference.rationale},
                }
            )
        return result

    def assess(
        self,
        ai_ids: Iterable[str],
        *,
        local_date: str,
        actor_ai_id: str,
        allow_open_cycle: bool = False,
        revision_reason: str = "",
    ) -> tuple[AssessmentProcessingResult, ...]:
        if actor_ai_id != self._hr_ai_id:
            raise HRAssessmentValidationError("only HR may create assessments")
        results = []
        for ai_id in tuple(ai_ids):
            if ai_id == self._hr_ai_id:
                results.append(
                    AssessmentProcessingResult(ai_id, local_date, "skipped_hr", None, "")
                )
                continue
            token = ""
            job = None
            try:
                report = self._repository.get_daily_report(ai_id, local_date)
                if report is None or report.cycle_id is None:
                    raise HRAssessmentValidationError("dated report does not exist")
                cycle = self._repository.get_daily_cycle(report.cycle_id)
                if cycle is None or (cycle.status != "closed" and not allow_open_cycle):
                    raise HRAssessmentValidationError("assessment cycle is not closed")
                bundle = self._evidence.collect(ai_id, local_date=local_date)
                adequate = self._evidence_is_adequate(report.raw_response is not None, bundle)
                evidence_version = self._evidence_version(report.revision, bundle)
                job = self._repository.ensure_assessment_job(
                    job_id=f"hr-assessment-job:{local_date}:{ai_id}",
                    ai_id=ai_id,
                    local_date=local_date,
                    evidence_version=evidence_version,
                    occurrence_key=f"hr-assessment:{local_date}:{ai_id}",
                )
                current = self._repository.get_current_assessment(ai_id, local_date)
                if current is not None and current.evidence_version == evidence_version:
                    self._repository.reconcile_assessment_job_complete(
                        job_id=job.id,
                        evidence_version=evidence_version,
                    )
                    results.append(
                        AssessmentProcessingResult(
                            ai_id, local_date, "already_complete", current, ""
                        )
                    )
                    continue
                if job.status in {"failed", "retry"} and job.attempt_count >= self._max_attempts:
                    self._repository.mark_assessment_job_exhausted(job.id)
                    results.append(
                        AssessmentProcessingResult(
                            ai_id, local_date, "retry_exhausted", current, ""
                        )
                    )
                    continue
                now = self._now()
                token = self._claim_token_factory(job.id)
                claim = self._repository.claim_assessment_job(
                    job_id=job.id,
                    claimed_by=self._hr_ai_id,
                    claim_token=token,
                    now=now.isoformat(),
                    claim_expires_at=(
                        now + timedelta(seconds=self._claim_lease_seconds)
                    ).isoformat(),
                )
                if claim is None:
                    results.append(
                        AssessmentProcessingResult(
                            ai_id, local_date, "claimed_elsewhere", None, ""
                        )
                    )
                    continue
                output = self._hr.ask_hr(
                    self._prompt(report, bundle, adequate=adequate),
                    f"hr:assessment:{local_date}:{ai_id}",
                    self._timeout_seconds,
                )
                parsed = self._parser.parse(
                    output,
                    expected_ai_id=ai_id,
                    expected_local_date=local_date,
                )
                parsed = self._policy.validate(parsed)
                if not adequate and (
                    parsed.workload != "insufficient_information"
                    or parsed.principal_contributions
                    or parsed.strengths
                ):
                    raise HRAssessmentValidationError(
                        "insufficient evidence cannot support a performance conclusion"
                    )
                evidence_rows = self._referenced_evidence(parsed, bundle)
                effective_revision_reason = revision_reason
                if current is not None:
                    normalized_submission = (
                        report.normalized.get("submission", {}).get("state")
                        if isinstance(report.normalized, dict)
                        else None
                    )
                    effective_revision_reason = effective_revision_reason or (
                        "late_report" if report.submission_state == "late_submitted"
                        or normalized_submission == "late_submitted" else "evidence_changed"
                    )
                assessment = self._repository.save_assessment(
                    assessment_id=(
                        f"hr-assessment:{local_date}:{ai_id}:"
                        f"{evidence_version.removeprefix('sha256:')[:16]}"
                    ),
                    ai_id=ai_id,
                    local_date=local_date,
                    status="complete",
                    workload=parsed.workload,
                    workload_score=parsed.workload_score,
                    principal_contributions=list(parsed.principal_contributions),
                    rationale=parsed.rationale,
                    blockers=list(parsed.blockers),
                    strengths=list(parsed.strengths),
                    improvements=list(parsed.improvements),
                    runtime_diagnosis=parsed.runtime_diagnosis,
                    information_sufficiency=parsed.information_sufficiency,
                    evidence_version=evidence_version,
                    hr_id=parsed.hr_ai_id,
                    evidence=evidence_rows,
                    revision_reason=effective_revision_reason,
                    expected_version=current.version if current is not None else 0,
                )
                self._repository.finish_assessment_job(
                    job_id=job.id,
                    claim_token=token,
                    status="complete",
                    finished_at=self._now().isoformat(),
                )
                results.append(
                    AssessmentProcessingResult(
                        ai_id, local_date, "complete", assessment, ""
                    )
                )
            except Exception as exc:
                error_code = str(getattr(exc, "code", "assessment_failed"))
                if token and job is not None:
                    try:
                        self._repository.finish_assessment_job(
                            job_id=job.id,
                            claim_token=token,
                            status="failed",
                            finished_at=self._now().isoformat(),
                            last_error=f"{error_code}:{exc.__class__.__name__}",
                        )
                    except Exception:
                        pass
                results.append(
                    AssessmentProcessingResult(
                        ai_id,
                        local_date,
                        "failed",
                        None,
                        error_code,
                    )
                )
        return tuple(results)
