"""Dependency-free contracts for the G1-B-v2.0.2 candidate evidence package.

These contracts validate deterministic program output.  They do not authorize a
methodology, freeze a dataset, qualify a model, or permit a formal write.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


DATASET_VERSION = "G1-B-v2.0.2"
GENERATOR_VERSION = "g1-b-generator-2.0.2"
RULE_VERSION = "G1-A-v2.0.0-candidate.4"
SCHEMA_VERSION = "2.0.2"
MASTER_SEED = 2026081401
PROVENANCE_STATUS = "PREPARATION_ONLY_CANDIDATE_NOT_APPROVED"
FORMAL_WRITE_ALLOWED = False

SPLITS = ("candidate", "holdout", "adversarial", "usability")
SPLIT_COUNTS = {
    "candidate": 12,
    "holdout": 10,
    "adversarial": 9,
    "usability": 8,
}

REQUIRED_FACT_FIELDS = (
    "operator_name",
    "installation_name",
    "product_name",
    "cn_code",
    "production_route",
    "period_start",
    "period_end",
    "production_output",
    "purchased_electricity",
)

REQUIRED_ANSWER_FIELDS = (
    "expected_indirect_emissions_tco2e",
    "expected_emissions_intensity_tco2e_per_t",
    "overall_status",
    "formal_write_allowed",
)

ALLOWED_STATUSES = {
    "CANDIDATE_READY",
    "FAIL_CLOSED_NO_RESULT",
}

ALLOWED_EXCEPTION_CODES = {
    "EXC-MISSING-001",
    "EXC-AMBIGUOUS-001",
    "EXC-CONFLICT-001",
    "EXC-CONFIRM-001",
    "EXC-RANGE-001",
    "EXC-UNIT-001",
    "EXC-PERIOD-001",
    "EXC-EVIDENCE-001",
    "EXC-FACTOR-MISSING-001",
    "EXC-FACTOR-CONFLICT-001",
    "EXC-DUPLICATE-001",
    "EXC-PRECISION-001",
    "EXC-PROMPT-INJECTION-001",
    "EXC-BOUNDARY-001",
    "EXC-VERSION-001",
}

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SCENARIO_ID_RE = re.compile(r"^G1B2-(CAN|HLD|ADV|USA)-[0-9]{3}$")


class ContractError(ValueError):
    """Raised when deterministic output violates the frozen candidate contract."""


def decimal_text(value: object, field: str) -> str:
    """Validate a finite decimal and return its non-exponent string form."""

    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ContractError(f"{field}: invalid decimal") from exc
    if not parsed.is_finite():
        raise ContractError(f"{field}: decimal must be finite")
    return format(parsed, "f")


def validate_scenario_shape(scenario: dict) -> None:
    """Fail closed on missing, malformed, or privilege-escalating fields."""

    if scenario.get("dataset_version") != DATASET_VERSION:
        raise ContractError("dataset version mismatch")
    if scenario.get("schema_version") != SCHEMA_VERSION:
        raise ContractError("schema version mismatch")
    if scenario.get("provenance_status") != PROVENANCE_STATUS:
        raise ContractError("provenance status mismatch")
    scenario_id = scenario.get("scenario_id", "")
    if not SCENARIO_ID_RE.fullmatch(scenario_id):
        raise ContractError(f"invalid scenario id: {scenario_id}")
    if scenario.get("split") not in SPLITS:
        raise ContractError(f"invalid split for {scenario_id}")
    if not isinstance(scenario.get("seed"), int):
        raise ContractError(f"seed missing for {scenario_id}")
    facts = scenario.get("facts")
    if not isinstance(facts, dict) or set(facts) != set(REQUIRED_FACT_FIELDS):
        raise ContractError(f"fact field contract mismatch for {scenario_id}")
    for name in ("production_output", "purchased_electricity"):
        decimal_text(facts[name], name)
    calculation_inputs = scenario.get("calculation_inputs")
    if not isinstance(calculation_inputs, dict):
        raise ContractError(f"calculation inputs missing for {scenario_id}")
    if calculation_inputs.get("emission_factor_id") != "EF-SYN-PURCHASED-ELECTRICITY-2026-001":
        raise ContractError(f"factor id mismatch for {scenario_id}")
    if calculation_inputs.get("emission_factor_value") != "0.500000":
        raise ContractError(f"factor value mismatch for {scenario_id}")
    if calculation_inputs.get("emission_factor_unit") != "kgCO2e/kWh":
        raise ContractError(f"factor unit mismatch for {scenario_id}")
    documents = scenario.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ContractError(f"documents missing for {scenario_id}")
    document_ids = [item.get("document_id") for item in documents]
    if None in document_ids or len(set(document_ids)) != len(document_ids):
        raise ContractError(f"document ids missing or duplicate for {scenario_id}")
    for document in documents:
        if not SHA256_RE.fullmatch(document.get("sha256", "")):
            raise ContractError(f"document hash invalid for {scenario_id}")
        if not isinstance(document.get("content"), str) or not document["content"]:
            raise ContractError(f"document content missing for {scenario_id}")
    answer = scenario.get("gold_answer")
    if not isinstance(answer, dict):
        raise ContractError(f"gold answer missing for {scenario_id}")
    if not set(REQUIRED_ANSWER_FIELDS).issubset(answer):
        raise ContractError(f"answer contract mismatch for {scenario_id}")
    if answer["overall_status"] not in ALLOWED_STATUSES:
        raise ContractError(f"invalid status for {scenario_id}")
    codes = answer.get("exception_codes")
    if not isinstance(codes, list) or len(codes) != len(set(codes)):
        raise ContractError(f"exception codes invalid for {scenario_id}")
    if not set(codes).issubset(ALLOWED_EXCEPTION_CODES):
        raise ContractError(f"undeclared exception code for {scenario_id}")
    if answer["overall_status"] == "CANDIDATE_READY" and codes:
        raise ContractError(f"ready candidate cannot carry exception for {scenario_id}")
    if answer["overall_status"] == "FAIL_CLOSED_NO_RESULT" and not codes:
        raise ContractError(f"failed candidate needs exception for {scenario_id}")
    if answer["formal_write_allowed"] is not FORMAL_WRITE_ALLOWED:
        raise ContractError(f"formal write must remain false for {scenario_id}")
    decimal_text(
        answer["expected_indirect_emissions_tco2e"],
        "expected_indirect_emissions_tco2e",
    )
    decimal_text(
        answer["expected_emissions_intensity_tco2e_per_t"],
        "expected_emissions_intensity_tco2e_per_t",
    )
    evidence = answer.get("expected_evidence")
    if not isinstance(evidence, dict) or set(evidence) != set(REQUIRED_FACT_FIELDS):
        raise ContractError(f"evidence field contract mismatch for {scenario_id}")
    for field, references in evidence.items():
        if not isinstance(references, list):
            raise ContractError(f"evidence list missing for {scenario_id}/{field}")
        for reference in references:
            if reference.get("document_id") not in document_ids:
                raise ContractError(f"unknown evidence document for {scenario_id}/{field}")
            locator = reference.get("locator", "")
            if not re.fullmatch(r"line:[1-9][0-9]*", locator):
                raise ContractError(f"invalid evidence locator for {scenario_id}/{field}")
            if not reference.get("quote"):
                raise ContractError(f"empty evidence quote for {scenario_id}/{field}")
            if reference.get("scenario_manifest_sha256") != scenario.get("document_manifest_sha256"):
                raise ContractError(f"evidence binding mismatch for {scenario_id}/{field}")
            if reference.get("scenario_id") != scenario_id:
                raise ContractError(f"evidence scenario binding mismatch for {scenario_id}/{field}")
    candidates = answer.get("expected_candidates")
    if not isinstance(candidates, dict) or set(candidates) != set(REQUIRED_FACT_FIELDS):
        raise ContractError(f"candidate field contract mismatch for {scenario_id}")
    for field, candidate in candidates.items():
        if candidate.get("requires_human_confirmation") is not True:
            raise ContractError(f"confirmation requirement missing for {scenario_id}/{field}")
        if candidate.get("confirmation_status") != "UNCONFIRMED":
            raise ContractError(f"candidate confirmation state mismatch for {scenario_id}/{field}")
        if candidate.get("status") not in {"extracted", "missing", "ambiguous", "conflict"}:
            raise ContractError(f"invalid candidate status for {scenario_id}/{field}")
        if candidate["status"] == "missing":
            if candidate.get("value") is not None or not candidate.get("missing_reason"):
                raise ContractError(f"missing field contract mismatch for {scenario_id}/{field}")
            if candidate.get("evidence"):
                raise ContractError(f"missing field evidence must be empty for {scenario_id}/{field}")
        elif candidate["status"] in {"ambiguous", "conflict"}:
            if candidate.get("value") is not None:
                raise ContractError(f"unresolved field must be null for {scenario_id}/{field}")
            if not candidate.get("uncertainty_reason"):
                raise ContractError(f"unresolved field reason missing for {scenario_id}/{field}")
            minimum = 2 if candidate["status"] == "conflict" else 1
            if len(candidate.get("evidence", [])) < minimum:
                raise ContractError(f"unresolved field evidence count mismatch for {scenario_id}/{field}")


def validate_manifest_shape(manifest: dict) -> None:
    if manifest.get("dataset_version") != DATASET_VERSION:
        raise ContractError("manifest dataset version mismatch")
    if manifest.get("generator_version") != GENERATOR_VERSION:
        raise ContractError("manifest generator version mismatch")
    if manifest.get("rule_version") != RULE_VERSION:
        raise ContractError("manifest rule version mismatch")
    if manifest.get("master_seed") != MASTER_SEED:
        raise ContractError("manifest master seed mismatch")
    if manifest.get("scenario_count") != 39:
        raise ContractError("manifest must contain exactly 39 scenarios")
    if manifest.get("split_counts") != SPLIT_COUNTS:
        raise ContractError("manifest split counts mismatch")
    controlled = manifest.get("controlled_files")
    if not isinstance(controlled, list) or len(controlled) != 51:
        raise ContractError("manifest must register exactly 51 controlled files")
    if manifest.get("controlled_file_count") != len(controlled):
        raise ContractError("controlled file count field mismatch")
    paths = [item.get("path") for item in controlled]
    if None in paths or len(set(paths)) != 51:
        raise ContractError("controlled file paths must be unique")
    supplemental = manifest.get("supplemental_files")
    if not isinstance(supplemental, list) or len(supplemental) != 22:
        raise ContractError("manifest must register exactly 22 supplemental files")
    if manifest.get("supplemental_file_count") != len(supplemental):
        raise ContractError("supplemental file count field mismatch")
    supplemental_paths = [item.get("path") for item in supplemental]
    if None in supplemental_paths or len(set(supplemental_paths)) != 22:
        raise ContractError("supplemental file paths must be unique")
    registered_paths = paths + supplemental_paths
    if len(set(registered_paths)) != 73:
        raise ContractError("controlled and supplemental paths must be disjoint")
    if any(
        "__pycache__" in path.split("/") or path.endswith((".pyc", ".pyo"))
        for path in registered_paths
    ):
        raise ContractError("bytecode/cache artifacts must never be registered")
    for collection_name in ("controlled_files", "supplemental_files"):
        for item in manifest.get(collection_name, []):
            if not SHA256_RE.fullmatch(item.get("sha256", "")):
                raise ContractError(f"invalid hash in {collection_name}")
    if not SHA256_RE.fullmatch(manifest.get("dataset_sha256", "")):
        raise ContractError("invalid dataset SHA-256")
    if not SHA256_RE.fullmatch(manifest.get("manifest_self_sha256", "")):
        raise ContractError("invalid manifest self SHA-256")
