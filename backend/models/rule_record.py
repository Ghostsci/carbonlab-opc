"""Authoritative, versioned rule metadata used by formal calculations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.base import TimestampMixin, UUIDMixin
from backend.models.ledger import LedgerImmutableError


class RuleRecord(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "rule_records"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    rule_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    publisher: Mapped[str] = mapped_column(String(255), nullable=False)
    document_number: Mapped[str] = mapped_column(String(128), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(32), nullable=False)
    vintage: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "rule_kind",
            "document_number",
            "vintage",
            name="uq_rule_record_authority_version",
        ),
        CheckConstraint(
            "rule_kind IN ('cbam_methodology', 'precursor_default')",
            name="ck_rule_record_kind",
        ),
        CheckConstraint(
            "length(trim(title)) > 0 "
            "AND length(trim(publisher)) > 0 "
            "AND length(trim(document_number)) > 0 "
            "AND length(trim(jurisdiction)) > 0",
            name="ck_rule_record_authority_metadata",
        ),
        CheckConstraint(
            "publisher IN ('European Commission', "
            "'European Parliament and Council')",
            name="ck_rule_record_trusted_publisher",
        ),
        CheckConstraint(
            "jurisdiction = 'EU' AND document_number LIKE 'EU-%'",
            name="ck_rule_record_document_identity",
        ),
        CheckConstraint(
            "source_url LIKE 'https://%'",
            name="ck_rule_record_https_source",
        ),
        CheckConstraint("vintage >= 1900", name="ck_rule_record_vintage"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from < valid_to",
            name="ck_rule_record_valid_period",
        ),
        CheckConstraint(
            "status IN ('approved', 'withdrawn', 'superseded')",
            name="ck_rule_record_status",
        ),
        CheckConstraint(
            "length(content_hash) = 64",
            name="ck_rule_record_content_hash",
        ),
    )


@event.listens_for(RuleRecord, "before_update")
@event.listens_for(RuleRecord, "before_delete")
def _guard_rule_record_immutability(_mapper, _connection, target) -> None:
    raise LedgerImmutableError(
        "rule records are immutable; create a new vintage"
    )
