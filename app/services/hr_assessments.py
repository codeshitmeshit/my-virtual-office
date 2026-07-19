"""Strict structured schema for non-ranking HR performance assessments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone


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


class HRAssessmentParser:
    """Rejects unsupported assessment fields, scores, ranks, and unbounded output."""

    ROOT_KEYS = frozenset(
        {
            "schemaVersion",
            "agentAiId",
            "localDate",
            "principalContributions",
            "workload",
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
