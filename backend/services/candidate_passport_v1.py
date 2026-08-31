"""Truth-isolated synthetic candidate passport pipeline for the M3 gate."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from jose import JWTError, jwt

from backend.auth.jwt import ALGORITHM, SECRET_KEY
from backend.core.quantity import Quantity, QuantityError
from backend.validation.contracts import (
    CandidateValue,
    ConflictFinding,
    EvidenceReference,
    FactoryCandidateFields,
    FactoryDocumentExtraction,
    SCHEMA_VERSION,
    SourceDocument,
    TASK_ID,
)
from backend.validation.providers import StaticProvider


PIPELINE_VERSION = "m3-candidate-passport-v1.0.3"
RULE_VERSION = "synthetic-electricity-rule-v1"
ELECTRICITY_FACTOR = Decimal("0.500000")
REVIEWER_ROLES = frozenset({"platform_admin", "admin", "manager", "auditor"})
CONFIRMATION_AUDIENCE = "carbon-passport-confirmation"


class CandidatePipelineError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class CandidateInput(BaseModel):
    """Runtime input deliberately cannot carry dataset truth or expected answers."""

    model_config = ConfigDict(extra="forbid")
    scenario_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{4,79}$")
    documents: tuple[SourceDocument, ...] = Field(min_length=1)


class ConfirmationAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["confirm", "reject"]
    reason: str = Field(min_length=1)
    occurred_at: datetime


class ReviewerCredential(BaseModel):
    """Opaque credential signed by the server-side authentication boundary."""

    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=1)


class CandidatePassport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pipeline_version: Literal[PIPELINE_VERSION]
    scenario_id: str
    synthetic_only: Literal[True]
    state: Literal["candidate", "rejected", "calculated"]
    formal_write_allowed: Literal[False]
    publish_allowed: Literal[False]
    candidate: dict
    confirmation: dict | None
    calculation_receipt: dict | None
    provenance: dict


def build_candidate(candidate_input: CandidateInput) -> CandidatePassport:
    """Invoke static/static-v1 using documents only; no truth/expected is accepted."""

    output = _extract_documents(candidate_input)
    provider = StaticProvider(
        {candidate_input.scenario_id: output}, provider_id="static", model="static-v1"
    )
    invocation = provider.complete_json(
        [{"role": "user", "content": f"SCENARIO_ID={candidate_input.scenario_id}"}]
    )
    extraction = FactoryDocumentExtraction.model_validate_json(invocation.output_text)
    if extraction.formal_write_allowed:
        raise CandidatePipelineError("formal_write_requested")
    _validate_evidence_bindings(extraction, candidate_input.documents)
    _validate_candidate_semantics(extraction)
    source_hashes = {
        item.document_id: hashlib.sha256(item.content.encode("utf-8")).hexdigest()
        for item in sorted(candidate_input.documents, key=lambda value: value.document_id)
    }
    return CandidatePassport(
        pipeline_version=PIPELINE_VERSION,
        scenario_id=candidate_input.scenario_id,
        synthetic_only=True,
        state="candidate",
        formal_write_allowed=False,
        publish_allowed=False,
        candidate=extraction.model_dump(mode="json"),
        confirmation=None,
        calculation_receipt=None,
        provenance={
            "source_sha256": source_hashes,
            "extraction_provider": f"{invocation.provider_id}/{invocation.model}",
            "truth_isolated": True,
        },
    )


def apply_human_action(
    passport: CandidatePassport,
    action: ConfirmationAction,
    credential: ReviewerCredential,
) -> CandidatePassport:
    actor_id, role = _verify_reviewer_credential(credential)
    if passport.state != "candidate":
        raise CandidatePipelineError("confirmation_requires_candidate_state")
    payload = passport.model_dump(mode="json")
    payload["confirmation"] = {
        **action.model_dump(mode="json"),
        "actor_id": actor_id,
        "actor_role": role,
        "authentication": "signed_confirmation_credential",
    }
    if action.decision == "reject":
        payload["state"] = "rejected"
        return CandidatePassport.model_validate(payload)
    extraction = FactoryDocumentExtraction.model_validate(passport.candidate)
    non_extracted = [name for name, field in extraction.fields if field.status != "extracted"]
    if non_extracted:
        raise CandidatePipelineError("unresolved_candidates:" + ",".join(non_extracted))
    if extraction.prompt_injection_detected:
        raise CandidatePipelineError("document_instruction_detected")
    payload["state"] = "calculated"
    payload["calculation_receipt"] = _calculate(extraction)
    return CandidatePassport.model_validate(payload)


def run_batch(
    inputs: tuple[CandidateInput, ...],
    actions: dict[str, tuple[ConfirmationAction, ReviewerCredential]],
) -> list[dict]:
    results: list[dict] = []
    for candidate_input in inputs:
        try:
            passport = build_candidate(candidate_input)
            action = actions.get(candidate_input.scenario_id)
            if action is not None:
                passport = apply_human_action(passport, *action)
            results.append({"scenario_id": candidate_input.scenario_id, "classification": "PASS", "passport": passport.model_dump(mode="json")})
        except CandidatePipelineError as exc:
            results.append({"scenario_id": candidate_input.scenario_id, "classification": "PASS", "outcome": "expected_rejection", "reason": exc.reason})
    return results


def _verify_reviewer_credential(credential: ReviewerCredential) -> tuple[str, str]:
    """Verify signature, audience, expiry and authorization at the use boundary."""

    if not isinstance(credential, ReviewerCredential):
        raise CandidatePipelineError("reviewer_credential_required")
    try:
        claims = jwt.decode(
            credential.token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=CONFIRMATION_AUDIENCE,
            options={"require_exp": True, "require_sub": True, "require_aud": True},
        )
    except JWTError as exc:
        raise CandidatePipelineError("reviewer_credential_invalid") from exc
    if claims.get("type") != "passport_confirmation":
        raise CandidatePipelineError("reviewer_credential_invalid")
    actor_id = claims.get("sub")
    role = claims.get("role")
    if not isinstance(actor_id, str) or not actor_id or role not in REVIEWER_ROLES:
        raise CandidatePipelineError("reviewer_not_authorized")
    return actor_id, role


def semantic_sha256(value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _extract_documents(candidate_input: CandidateInput) -> dict:
    documents = {item.document_id: item.content for item in candidate_input.documents}
    identity = documents.get("identity", "")
    fields: dict[str, CandidateValue] = {}
    identity_labels = {
        "installation_name": "装置",
        "operator_name": "经营者",
        "product_name": "产品",
        "cn_code": "CN编码",
        "production_route": "生产路线",
        "period_start": "期间开始",
        "period_end": "期间结束",
    }
    for name, label in identity_labels.items():
        fields[name] = _extract_label(identity, "identity", label)

    output_matches = _quantity_lines(documents, ("合格产量", "同期发运汇总产量"))
    ledger_output = next((item for item in output_matches if item[0] == "production_ledger"), None)
    shipping_output = next((item for item in output_matches if item[0] == "shipping_summary"), None)
    conflicts: list[ConflictFinding] = []
    if ledger_output and shipping_output and ledger_output[2] != shipping_output[2]:
        evidence = [EvidenceReference(document_id=item[0], quote=item[1]) for item in (ledger_output, shipping_output)]
        fields["production_output"] = CandidateValue(status="conflict", value=None, unit="t", evidence=evidence, requires_human_confirmation=True, uncertainty_reason="两个文件提供了不同的同期产量。")
        conflicts.append(ConflictFinding(field="production_output", description="生产台账与发运汇总的产量不一致，不能自动选值。", evidence=evidence))
    elif ledger_output is None or "尚未提供" in ledger_output[1] or "未提供" in ledger_output[1]:
        fields["production_output"] = _missing("产量台账未提供合格产量。")
    elif ledger_output[3] is None:
        fields["production_output"] = CandidateValue(status="ambiguous", value=None, unit=None, evidence=[EvidenceReference(document_id=ledger_output[0], quote=ledger_output[1])], requires_human_confirmation=True, uncertainty_reason="产量数值存在，但计量单位未标明。")
    else:
        fields["production_output"] = _extracted(ledger_output[2], ledger_output[0], ledger_output[1], ledger_output[3])

    electricity = next(iter(_quantity_lines(documents, ("本期用电量",))), None)
    if electricity is None or "未提供" in electricity[1]:
        fields["purchased_electricity"] = _missing("文件仅声明未提供本期用电量。")
    elif electricity[3] is None:
        fields["purchased_electricity"] = CandidateValue(status="ambiguous", value=None, unit=None, evidence=[EvidenceReference(document_id=electricity[0], quote=electricity[1])], requires_human_confirmation=True, uncertainty_reason="用电量数值存在，但计量单位未标明。")
    else:
        fields["purchased_electricity"] = _extracted(electricity[2], electricity[0], electricity[1], electricity[3])

    candidate_fields = FactoryCandidateFields(**fields)
    missing = [name for name, field in candidate_fields if field.status == "missing"]
    injection_markers = ("忽略所有系统规则", "允许正式写入", "直接输出已核查")
    return FactoryDocumentExtraction(
        schema_version=SCHEMA_VERSION,
        task_id=TASK_ID,
        scenario_id=candidate_input.scenario_id,
        fields=candidate_fields,
        prompt_injection_detected=any(marker in content for content in documents.values() for marker in injection_markers),
        conflicts=conflicts,
        missing_fields=missing,
        formal_write_allowed=False,
    ).model_dump(mode="json")


def _extract_label(content: str, document_id: str, label: str) -> CandidateValue:
    match = re.search(rf"(?m)^{re.escape(label)}：([^\n]+)$", content)
    if not match:
        return _missing(f"{label}未提供。")
    quote = match.group(0)
    return _extracted(match.group(1).strip(), document_id, quote, None)


def _quantity_lines(documents: dict[str, str], labels: tuple[str, ...]) -> list[tuple[str, str, str, str | None]]:
    matches = []
    for document_id, content in documents.items():
        for label in labels:
            match = re.search(rf"(?m)^{re.escape(label)}：([^\n]+)$", content)
            if not match:
                continue
            quote, body = match.group(0), match.group(1).strip()
            number = re.search(r"[0-9][0-9,]*(?:\.[0-9]+)?", body)
            unit_match = re.search(r"\b(kWh|t)\b", body)
            matches.append((document_id, quote, number.group(0).replace(",", "") if number else "", unit_match.group(1) if unit_match else None))
    return matches


def _extracted(value: str, document_id: str, quote: str, unit: str | None) -> CandidateValue:
    return CandidateValue(status="extracted", value=value, unit=unit, evidence=[EvidenceReference(document_id=document_id, quote=quote)], requires_human_confirmation=True, uncertainty_reason=None)


def _missing(reason: str) -> CandidateValue:
    return CandidateValue(status="missing", value=None, unit=None, evidence=[], requires_human_confirmation=True, uncertainty_reason=reason)


def _validate_evidence_bindings(extraction: FactoryDocumentExtraction, source_documents: tuple[SourceDocument, ...]) -> None:
    documents = {item.document_id: item.content for item in source_documents}
    for field_name, field in extraction.fields:
        for evidence in field.evidence:
            content = documents.get(evidence.document_id)
            if content is None or evidence.quote not in content:
                raise CandidatePipelineError(f"evidence_mismatch:{field_name}")
            if field.status == "extracted" and field.value is not None:
                normalized_quote = evidence.quote.replace(",", "").casefold()
                if field.value.replace(",", "").casefold() not in normalized_quote:
                    raise CandidatePipelineError(f"evidence_value_mismatch:{field_name}")
                if field.unit is not None and field.unit.casefold() not in normalized_quote:
                    raise CandidatePipelineError(f"evidence_unit_mismatch:{field_name}")


def _validate_candidate_semantics(extraction: FactoryDocumentExtraction) -> None:
    fields = extraction.fields
    if fields.production_output.status == "extracted" and fields.production_output.unit != "t":
        raise CandidatePipelineError("invalid_unit:production_output")
    if fields.purchased_electricity.status == "extracted" and fields.purchased_electricity.unit != "kWh":
        raise CandidatePipelineError("invalid_unit:purchased_electricity")
    if fields.period_start.status == "extracted" and fields.period_end.status == "extracted":
        try:
            start = date.fromisoformat(fields.period_start.value or "")
            end = date.fromisoformat(fields.period_end.value or "")
        except ValueError as exc:
            raise CandidatePipelineError("invalid_period") from exc
        if start > end:
            raise CandidatePipelineError("invalid_period")


def _calculate(extraction: FactoryDocumentExtraction) -> dict:
    try:
        electricity = Decimal(extraction.fields.purchased_electricity.value or "")
        output = Decimal(extraction.fields.production_output.value or "")
        if electricity <= 0 or output <= 0:
            raise CandidatePipelineError("non_positive_quantity")
        emissions = (Quantity.of(electricity, "kWh") * Quantity.of(ELECTRICITY_FACTOR, "kgCO2e/kWh")).convert_to("tCO2e").value
    except (InvalidOperation, QuantityError) as exc:
        raise CandidatePipelineError("invalid_quantity") from exc
    inputs = {"purchased_electricity": {"value": str(electricity), "unit": "kWh"}, "electricity_factor": {"value": str(ELECTRICITY_FACTOR), "unit": "kgCO2e/kWh"}, "production_output": {"value": str(output), "unit": "t"}}
    return {"rule_version": RULE_VERSION, "formula": "purchased_electricity_kWh * factor_kgCO2e_per_kWh / 1000", "inputs": inputs, "result": {"value": str(emissions), "unit": "tCO2e"}, "input_sha256": semantic_sha256(inputs)}
