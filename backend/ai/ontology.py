"""Versioned, deliberately small ontology contract for the passport workflow.

The ontology is a semantic control plane, not an alternative source of truth.
Database constraints and the append-only formal ledger remain authoritative.
"""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any


ONTOLOGY_PATH = Path(__file__).with_name("ontology") / "carbon_passport_v0_1.json"
SUPPORTED_CORPORA = {"tenant_evidence", "public_methodology", "internal_sop"}


class OntologyContractError(RuntimeError):
    """Raised when the checked-in ontology contract is internally inconsistent."""


@lru_cache(maxsize=1)
def ontology_contract() -> dict[str, Any]:
    payload = json.loads(ONTOLOGY_PATH.read_text(encoding="utf-8"))
    required = {"ontology_id", "version", "classes", "relations", "field_mappings", "corpora", "invariants"}
    missing = sorted(required - payload.keys())
    if missing:
        raise OntologyContractError(f"ontology contract missing keys: {', '.join(missing)}")
    classes = payload["classes"]
    if not isinstance(classes, list) or len(classes) != len(set(classes)):
        raise OntologyContractError("ontology classes must be a unique list")
    class_names = set(classes)
    relation_names: set[str] = set()
    for relation in payload["relations"]:
        if relation.get("name") in relation_names:
            raise OntologyContractError("ontology relation names must be unique")
        relation_names.add(relation.get("name"))
        if relation.get("domain") not in class_names or relation.get("range") not in class_names:
            raise OntologyContractError(f"invalid ontology relation: {relation}")
    if set(payload["corpora"]) != SUPPORTED_CORPORA:
        raise OntologyContractError("ontology corpus policy does not match runtime corpus boundary")
    return payload


def ontology_version() -> str:
    payload = ontology_contract()
    return f"{payload['ontology_id']}-v{payload['version']}"


def canonical_field(field_name: str) -> str | None:
    normalized = field_name.strip().lower()
    for canonical, definition in ontology_contract()["field_mappings"].items():
        aliases = {str(alias).strip().lower() for alias in definition.get("aliases", [])}
        if normalized == canonical.lower() or normalized in aliases:
            return canonical
    return None


def concepts_for_field(field_name: str) -> list[str]:
    canonical = canonical_field(field_name)
    if canonical is None:
        return ["EvidenceChunk"]
    return list(ontology_contract()["field_mappings"][canonical].get("concepts", ["EvidenceChunk"]))


def role_allowed_corpora(role_id: str) -> set[str]:
    return {
        corpus
        for corpus, policy in ontology_contract()["corpora"].items()
        if role_id in policy.get("allowed_roles", [])
    }


def public_ontology_payload() -> dict[str, Any]:
    payload = ontology_contract()
    return {
        "ontology_id": payload["ontology_id"],
        "version": payload["version"],
        "runtime_version": ontology_version(),
        "status": payload["status"],
        "purpose": payload["purpose"],
        "classes": payload["classes"],
        "relations": payload["relations"],
        "field_mappings": payload["field_mappings"],
        "corpora": payload["corpora"],
        "invariants": payload["invariants"],
    }
