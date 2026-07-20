"""Strict contracts shared by synthetic scenarios, providers, and evaluators."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


TASK_ID = "factory_document_extraction_v1"
SCHEMA_VERSION = "1.1.0"

FieldName = Literal[
    "installation_name",
    "operator_name",
    "product_name",
    "cn_code",
    "production_route",
    "period_start",
    "period_end",
    "production_output",
    "purchased_electricity",
]
CandidateStatus = Literal["extracted", "missing", "ambiguous", "conflict"]
DatasetSplit = Literal["candidate", "holdout", "adversarial"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceReference(StrictModel):
    document_id: str = Field(min_length=1, max_length=80)
    quote: str = Field(min_length=1, max_length=300)


class CandidateValue(StrictModel):
    status: CandidateStatus
    value: str | None
    unit: str | None
    evidence: list[EvidenceReference]
    requires_human_confirmation: Literal[True]
    uncertainty_reason: str | None = Field(max_length=300)

    @model_validator(mode="after")
    def enforce_evidence_and_abstention(self) -> "CandidateValue":
        if self.status == "extracted":
            if self.value is None or not self.value.strip():
                raise ValueError("extracted candidates require a value")
            if not self.evidence:
                raise ValueError("extracted candidates require document evidence")
        elif self.status == "missing":
            if self.value is not None:
                raise ValueError("missing candidates cannot carry a value")
            if not self.uncertainty_reason:
                raise ValueError("missing candidates require a reason")
        else:
            if self.value is not None:
                raise ValueError("ambiguous/conflict candidates cannot choose a value")
            if not self.evidence or not self.uncertainty_reason:
                raise ValueError(
                    "ambiguous/conflict candidates require evidence and a reason"
                )
        return self


class FactoryCandidateFields(StrictModel):
    installation_name: CandidateValue
    operator_name: CandidateValue
    product_name: CandidateValue
    cn_code: CandidateValue
    production_route: CandidateValue
    period_start: CandidateValue
    period_end: CandidateValue
    production_output: CandidateValue
    purchased_electricity: CandidateValue


class ConflictFinding(StrictModel):
    field: FieldName
    description: str = Field(min_length=1, max_length=300)
    evidence: list[EvidenceReference] = Field(min_length=2)


class FactoryDocumentExtraction(StrictModel):
    schema_version: Literal[SCHEMA_VERSION]
    task_id: Literal[TASK_ID]
    scenario_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{4,79}$")
    fields: FactoryCandidateFields
    prompt_injection_detected: bool
    conflicts: list[ConflictFinding]
    missing_fields: list[FieldName]
    formal_write_allowed: Literal[False]

    @model_validator(mode="after")
    def keep_summary_consistent(self) -> "FactoryDocumentExtraction":
        missing = {
            name
            for name, value in self.fields.model_dump().items()
            if value["status"] == "missing"
        }
        if set(self.missing_fields) != missing:
            raise ValueError("missing_fields must match fields with status=missing")
        conflict_fields = {item.field for item in self.conflicts}
        if len(conflict_fields) != len(self.conflicts):
            raise ValueError("conflicts cannot repeat a field")
        actual_conflicts = {
            name
            for name, value in self.fields.model_dump().items()
            if value["status"] == "conflict"
        }
        if conflict_fields != actual_conflicts:
            raise ValueError("conflicts must match fields with status=conflict")
        conflict_by_field = {item.field: item for item in self.conflicts}
        for field in actual_conflicts:
            candidate_evidence = getattr(self.fields, field).evidence
            summary_evidence = conflict_by_field[field].evidence
            candidate_references = Counter(
                (item.document_id, item.quote) for item in candidate_evidence
            )
            summary_references = Counter(
                (item.document_id, item.quote) for item in summary_evidence
            )
            if candidate_references != summary_references:
                raise ValueError(
                    "conflict evidence must match the candidate field evidence"
                )
        return self


class SourceDocument(StrictModel):
    document_id: str = Field(min_length=1, max_length=80)
    document_type: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=20_000)


class FactoryTruth(StrictModel):
    installation_name: str
    operator_name: str
    product_name: str
    cn_code: str
    production_route: str
    period_start: str
    period_end: str
    production_output_t: Decimal
    purchased_electricity_kwh: Decimal
    electricity_factor_kgco2e_per_kwh: Decimal
    expected_indirect_emissions_tco2e: Decimal


class SyntheticFactoryScenario(StrictModel):
    scenario_id: str
    seed: int
    split: DatasetSplit
    variant: str
    truth: FactoryTruth
    documents: list[SourceDocument] = Field(min_length=1)
    expected: FactoryDocumentExtraction
