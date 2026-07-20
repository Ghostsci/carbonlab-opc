"""Resolution boundary for authoritative rule references."""

from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy.orm import Session

from backend.models.rule_record import RuleRecord


TRUSTED_CBAM_PUBLISHERS = {
    "European Commission",
    "European Parliament and Council",
}


def parse_rule_ref(reference: str) -> uuid.UUID:
    prefix, separator, identifier = reference.partition(":")
    if prefix != "rule_record" or separator != ":":
        raise ValueError("rule record reference must use rule_record:<uuid>")
    try:
        return uuid.UUID(identifier)
    except ValueError as exc:
        raise ValueError("rule record reference must contain a valid UUID") from exc


def resolve_rule_record(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    reference: str,
    expected_kind: str,
    period_start: datetime,
    period_end: datetime,
) -> RuleRecord:
    rule_id = parse_rule_ref(reference)
    rule = (
        db.query(RuleRecord)
        .filter(
            RuleRecord.id == rule_id,
            RuleRecord.tenant_id == tenant_id,
            RuleRecord.rule_kind == expected_kind,
            RuleRecord.status == "approved",
            RuleRecord.valid_from <= period_start,
        )
        .first()
    )
    if rule is None or (rule.valid_to is not None and rule.valid_to < period_end):
        raise ValueError(
            "approved rule record not found for tenant, kind, and reporting period"
        )
    if not all(
        (
            rule.publisher.strip(),
            rule.document_number.strip(),
            rule.jurisdiction.strip(),
            rule.source_url.strip(),
            rule.content_hash.strip(),
        )
    ):
        raise ValueError("rule record authority metadata is incomplete")
    if (
        rule.publisher not in TRUSTED_CBAM_PUBLISHERS
        or rule.jurisdiction != "EU"
        or not rule.document_number.startswith("EU-")
        or not rule.source_url.startswith("https://")
        or rule.vintage > period_start.year
    ):
        raise ValueError("rule record authority, document, or vintage is invalid")
    return rule
