"""Formal CBAM installation, process, attribution, and SEE ledger objects."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, String, Uuid, event, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.core.db_types import ExactDecimal
from backend.database import Base
from backend.models.base import TimestampMixin, UUIDMixin
from backend.models.ledger import LedgerIntegrityError, LedgerRecordMixin


class Installation(Base, UUIDMixin, TimestampMixin, LedgerRecordMixin):
    __tablename__ = "cbam_installations"

    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("enterprises.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    operator_name: Mapped[str] = mapped_column(String(255), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    unlocode: Mapped[str | None] = mapped_column(String(5))


class ProductionProcess(Base, UUIDMixin, TimestampMixin, LedgerRecordMixin):
    __tablename__ = "cbam_production_processes"

    installation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("cbam_installations.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    aggregate_goods_category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    production_route: Mapped[str] = mapped_column(String(32), nullable=False)


class CBAMProduct(Base, UUIDMixin, TimestampMixin, LedgerRecordMixin):
    """K2 formal product definition; legacy report `Product` remains a DTO."""

    __tablename__ = "cbam_products"

    process_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("cbam_production_processes.id"),
        nullable=False,
        index=True,
    )
    cn_code: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class ProductionOutput(Base, UUIDMixin, TimestampMixin, LedgerRecordMixin):
    __tablename__ = "cbam_production_outputs"

    process_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("cbam_production_processes.id"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("cbam_products.id"),
        nullable=False,
        index=True,
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(ExactDecimal(28, 12), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)


class SourceStreamAttribution(
    Base,
    UUIDMixin,
    TimestampMixin,
    LedgerRecordMixin,
):
    __tablename__ = "cbam_source_stream_attributions"

    process_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("cbam_production_processes.id"),
        nullable=False,
        index=True,
    )
    source_ref: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    share: Mapped[Decimal] = mapped_column(ExactDecimal(18, 12), nullable=False)
    method: Mapped[str] = mapped_column(String(64), nullable=False)


class PrecursorConsumption(Base, UUIDMixin, TimestampMixin, LedgerRecordMixin):
    __tablename__ = "cbam_precursor_consumptions"

    process_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("cbam_production_processes.id"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("cbam_products.id"),
        nullable=False,
        index=True,
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    precursor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(ExactDecimal(28, 12), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_see_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    specific_emissions: Mapped[Decimal] = mapped_column(
        ExactDecimal(28, 12),
        nullable=False,
    )
    specific_unit: Mapped[str] = mapped_column(String(64), nullable=False)
    data_quality: Mapped[str] = mapped_column(String(32), nullable=False)


class SEEResult(Base, UUIDMixin, TimestampMixin, LedgerRecordMixin):
    __tablename__ = "cbam_see_results"

    process_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("cbam_production_processes.id"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("cbam_products.id"),
        nullable=False,
        index=True,
    )
    production_output_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("cbam_production_outputs.id"),
        nullable=False,
        index=True,
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    direct_emissions: Mapped[Decimal] = mapped_column(
        ExactDecimal(28, 12),
        nullable=False,
    )
    indirect_emissions: Mapped[Decimal] = mapped_column(
        ExactDecimal(28, 12),
        nullable=False,
    )
    precursor_emissions: Mapped[Decimal] = mapped_column(
        ExactDecimal(28, 12),
        nullable=False,
    )
    total_emissions: Mapped[Decimal] = mapped_column(
        ExactDecimal(28, 12),
        nullable=False,
    )
    emissions_unit: Mapped[str] = mapped_column(String(64), nullable=False)
    specific_emissions: Mapped[Decimal] = mapped_column(
        ExactDecimal(28, 12),
        nullable=False,
    )
    specific_unit: Mapped[str] = mapped_column(String(64), nullable=False)
    data_quality: Mapped[str] = mapped_column(String(32), nullable=False)
    methodology_ref: Mapped[str] = mapped_column(String(128), nullable=False)


class CarbonPricePaidEvidence(
    Base,
    UUIDMixin,
    TimestampMixin,
    LedgerRecordMixin,
):
    __tablename__ = "cbam_carbon_price_paid_evidence"

    installation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("cbam_installations.id"),
        nullable=False,
        index=True,
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    scheme: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(ExactDecimal(28, 12), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    covered_emissions: Mapped[Decimal] = mapped_column(
        ExactDecimal(28, 12),
        nullable=False,
    )
    emissions_unit: Mapped[str] = mapped_column(String(64), nullable=False)
    price_per_tonne: Mapped[Decimal] = mapped_column(
        ExactDecimal(28, 12),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("documents.id"),
    )


def _assert_tenant_parent(connection, target, table_name: str, record_id) -> None:
    table = target.__table__.metadata.tables[table_name]
    owner = connection.execute(
        select(table.c.tenant_id).where(table.c.id == record_id)
    ).scalar_one_or_none()
    if owner != target.tenant_id:
        raise LedgerIntegrityError(
            f"tenant lineage violation: {table_name} parent is missing or foreign"
        )


def _assert_ref_tenant(
    connection,
    target,
    value: str,
    *,
    prefix: str,
    table_name: str,
) -> None:
    ref_prefix, separator, identifier = value.partition(":")
    if separator != ":" or ref_prefix != prefix:
        raise LedgerIntegrityError(f"tenant lineage violation: invalid {prefix} reference")
    try:
        record_id = uuid.UUID(identifier)
    except ValueError as exc:
        raise LedgerIntegrityError(
            f"tenant lineage violation: invalid {prefix} reference"
        ) from exc
    _assert_tenant_parent(connection, target, table_name, record_id)


def _domain_decimal(value, label: str) -> Decimal:
    if isinstance(value, float):
        raise LedgerIntegrityError(f"{label} rejects binary float values")
    try:
        return value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise LedgerIntegrityError(f"{label} must be an exact decimal") from exc


def _assert_period(target, label: str) -> None:
    if target.period_start >= target.period_end:
        raise LedgerIntegrityError(f"{label} period_start must precede period_end")


def _validate_output_domain(target: ProductionOutput) -> None:
    _assert_period(target, "production output")
    if _domain_decimal(target.quantity, "production output quantity") <= 0:
        raise LedgerIntegrityError("production output quantity must be positive")
    if target.unit != "t":
        raise LedgerIntegrityError("production output unit must be canonical mass unit t")


def _validate_precursor_domain(target: PrecursorConsumption) -> None:
    _assert_period(target, "precursor")
    if _domain_decimal(target.quantity, "precursor quantity") <= 0:
        raise LedgerIntegrityError("precursor quantity must be positive")
    if target.unit != "t":
        raise LedgerIntegrityError("precursor unit must be canonical mass unit t")
    if _domain_decimal(target.specific_emissions, "precursor emissions") < 0:
        raise LedgerIntegrityError("precursor specific emissions cannot be negative")
    if target.specific_unit != "tCO2e/t":
        raise LedgerIntegrityError(
            "precursor specific unit must be canonical tCO2e/t"
        )
    prefixes = {
        "self_produced_see": "see_result:",
        "supplier_see": "supplier_see:",
        "rule_default": "rule_record:",
    }
    prefix = prefixes.get(target.source_kind)
    if prefix is None:
        raise LedgerIntegrityError("precursor source_kind is not allowed")
    if not target.source_see_ref.startswith(prefix):
        raise LedgerIntegrityError(
            "precursor source reference does not match source_kind"
        )
    if target.source_kind == "supplier_see" and target.data_quality not in {
        "supplier_verified",
        "supplier_declared",
    }:
        raise LedgerIntegrityError("precursor supplier data quality is invalid")
    if target.source_kind == "rule_default" and target.data_quality != "rule_default":
        raise LedgerIntegrityError("precursor rule default data quality is invalid")


def _validate_see_domain(connection, target: SEEResult) -> None:
    _assert_period(target, "SEE")
    direct = _domain_decimal(target.direct_emissions, "SEE direct emissions")
    indirect = _domain_decimal(target.indirect_emissions, "SEE indirect emissions")
    precursor = _domain_decimal(target.precursor_emissions, "SEE precursor emissions")
    total = _domain_decimal(target.total_emissions, "SEE total emissions")
    specific = _domain_decimal(target.specific_emissions, "SEE specific emissions")
    if min(direct, indirect, precursor, total, specific) < 0:
        raise LedgerIntegrityError("SEE emissions cannot be negative")
    if total != direct + indirect + precursor:
        raise LedgerIntegrityError("SEE total must equal its emission components")
    if target.emissions_unit != "tCO2e" or target.specific_unit != "tCO2e/t":
        raise LedgerIntegrityError("SEE units must be canonical tCO2e and tCO2e/t")
    if target.data_quality not in {
        "not_applicable",
        "supplier_verified",
        "supplier_declared",
        "rule_default",
    }:
        raise LedgerIntegrityError("SEE data quality is not allowed")
    if not target.methodology_ref.startswith("rule_record:"):
        raise LedgerIntegrityError("SEE methodology must reference a rule_record")
    references = set(target.derived_from or ())
    if f"production_output:{target.production_output_id}" not in references:
        raise LedgerIntegrityError("SEE provenance must include its production output")
    if target.methodology_ref not in references:
        raise LedgerIntegrityError("SEE provenance must include its methodology")
    attribution_refs = [
        reference for reference in references if reference.startswith("attribution:")
    ]
    if not attribution_refs:
        raise LedgerIntegrityError("SEE provenance must include an attribution")
    attribution_table = target.__table__.metadata.tables[
        "cbam_source_stream_attributions"
    ]
    for reference in attribution_refs:
        try:
            attribution_id = uuid.UUID(reference.removeprefix("attribution:"))
        except ValueError as exc:
            raise LedgerIntegrityError(
                "SEE provenance contains an invalid attribution reference"
            ) from exc
        valid = connection.execute(
            select(attribution_table.c.id).where(
                attribution_table.c.id == attribution_id,
                attribution_table.c.tenant_id == target.tenant_id,
                attribution_table.c.process_id == target.process_id,
                attribution_table.c.period_start == target.period_start,
                attribution_table.c.period_end == target.period_end,
            )
        ).scalar_one_or_none()
        if valid is None:
            raise LedgerIntegrityError(
                "SEE provenance attribution is missing or outside its formal boundary"
            )


def _validate_price_evidence_domain(target: CarbonPricePaidEvidence) -> None:
    _assert_period(target, "carbon price evidence")
    amount = _domain_decimal(target.amount_paid, "carbon price amount")
    covered = _domain_decimal(target.covered_emissions, "carbon price emissions")
    price = _domain_decimal(target.price_per_tonne, "carbon price per tonne")
    if min(amount, covered, price) < 0:
        raise LedgerIntegrityError("carbon price values cannot be negative")
    if target.emissions_unit != "tCO2e":
        raise LedgerIntegrityError("carbon price emissions unit must be tCO2e")
    if (
        len(target.currency) != 3
        or target.currency != target.currency.upper()
        or not target.currency.isalpha()
    ):
        raise LedgerIntegrityError("carbon price currency must be three uppercase letters")


def _assert_rule_record(
    connection,
    target,
    reference: str,
    *,
    expected_kind: str,
) -> None:
    prefix, separator, identifier = reference.partition(":")
    if prefix != "rule_record" or separator != ":":
        raise LedgerIntegrityError("formal rule reference must use rule_record:<uuid>")
    try:
        rule_id = uuid.UUID(identifier)
    except ValueError as exc:
        raise LedgerIntegrityError(
            "formal rule reference must contain a valid UUID"
        ) from exc
    table = target.__table__.metadata.tables["rule_records"]
    valid = connection.execute(
        select(table.c.id).where(
            table.c.id == rule_id,
            table.c.tenant_id == target.tenant_id,
            table.c.rule_kind == expected_kind,
            table.c.status == "approved",
            table.c.publisher.in_(
                ("European Commission", "European Parliament and Council")
            ),
            table.c.jurisdiction == "EU",
            table.c.document_number.like("EU-%"),
            table.c.source_url.like("https://%"),
            table.c.vintage <= target.period_start.year,
            table.c.valid_from <= target.period_start,
            (table.c.valid_to.is_(None) | (table.c.valid_to >= target.period_end)),
        )
    ).scalar_one_or_none()
    if valid is None:
        raise LedgerIntegrityError(
            "approved rule record is missing, foreign, wrong-kind, or out of period"
        )


@event.listens_for(Installation, "before_insert")
def _installation_tenant_lineage(_mapper, connection, target) -> None:
    _assert_tenant_parent(connection, target, "enterprises", target.enterprise_id)


@event.listens_for(ProductionProcess, "before_insert")
def _process_tenant_lineage(_mapper, connection, target) -> None:
    _assert_tenant_parent(
        connection,
        target,
        "cbam_installations",
        target.installation_id,
    )


@event.listens_for(CBAMProduct, "before_insert")
def _product_tenant_lineage(_mapper, connection, target) -> None:
    _assert_tenant_parent(
        connection,
        target,
        "cbam_production_processes",
        target.process_id,
    )


@event.listens_for(ProductionOutput, "before_insert")
def _output_tenant_lineage(_mapper, connection, target) -> None:
    _validate_output_domain(target)
    _assert_tenant_parent(
        connection,
        target,
        "cbam_production_processes",
        target.process_id,
    )
    _assert_tenant_parent(connection, target, "cbam_products", target.product_id)


@event.listens_for(SourceStreamAttribution, "before_insert")
def _attribution_tenant_lineage(_mapper, connection, target) -> None:
    _assert_tenant_parent(
        connection,
        target,
        "cbam_production_processes",
        target.process_id,
    )
    _assert_ref_tenant(
        connection,
        target,
        target.source_ref,
        prefix="emission_result",
        table_name="emission_results",
    )


@event.listens_for(PrecursorConsumption, "before_insert")
def _precursor_tenant_lineage(_mapper, connection, target) -> None:
    _validate_precursor_domain(target)
    _assert_tenant_parent(
        connection,
        target,
        "cbam_production_processes",
        target.process_id,
    )
    _assert_tenant_parent(connection, target, "cbam_products", target.product_id)
    if target.source_kind == "self_produced_see":
        _assert_ref_tenant(
            connection,
            target,
            target.source_see_ref,
            prefix="see_result",
            table_name="cbam_see_results",
        )
    elif target.source_kind == "rule_default":
        _assert_rule_record(
            connection,
            target,
            target.source_see_ref,
            expected_kind="precursor_default",
        )


@event.listens_for(SEEResult, "before_insert")
def _see_tenant_lineage(_mapper, connection, target) -> None:
    _validate_see_domain(connection, target)
    _assert_rule_record(
        connection,
        target,
        target.methodology_ref,
        expected_kind="cbam_methodology",
    )
    _assert_tenant_parent(
        connection,
        target,
        "cbam_production_processes",
        target.process_id,
    )
    _assert_tenant_parent(connection, target, "cbam_products", target.product_id)
    _assert_tenant_parent(
        connection,
        target,
        "cbam_production_outputs",
        target.production_output_id,
    )


@event.listens_for(CarbonPricePaidEvidence, "before_insert")
def _price_evidence_tenant_lineage(_mapper, connection, target) -> None:
    _validate_price_evidence_domain(target)
    _assert_tenant_parent(
        connection,
        target,
        "cbam_installations",
        target.installation_id,
    )
    if target.document_id is not None:
        _assert_tenant_parent(connection, target, "documents", target.document_id)


@event.listens_for(Session, "before_flush")
def _validate_formal_attribution_batches(session, _flush_context, _instances) -> None:
    pending = [
        record
        for record in session.new
        if isinstance(record, SourceStreamAttribution)
    ]
    if not pending:
        return
    groups = {
        (
            record.tenant_id,
            record.source_ref,
            record.period_start,
            record.period_end,
        )
        for record in pending
    }
    superseded_ids = {
        record.supersedes_id
        for record in pending
        if record.supersedes_id is not None
    }
    for tenant_id, source_ref, period_start, period_end in groups:
        existing = (
            session.query(SourceStreamAttribution)
            .filter(
                SourceStreamAttribution.tenant_id == tenant_id,
                SourceStreamAttribution.source_ref == source_ref,
                SourceStreamAttribution.period_start == period_start,
                SourceStreamAttribution.period_end == period_end,
                SourceStreamAttribution.superseded_by_id.is_(None),
            )
            .all()
        )
        total = sum(
            (
                record.share
                for record in existing
                if record.id not in superseded_ids
            ),
            Decimal("0"),
        )
        total += sum(
            (
                record.share
                for record in pending
                if (
                    record.tenant_id,
                    record.source_ref,
                    record.period_start,
                    record.period_end,
                )
                == (tenant_id, source_ref, period_start, period_end)
            ),
            Decimal("0"),
        )
        if total != Decimal("1"):
            raise LedgerIntegrityError(
                f"formal attribution shares must total exactly 1.00; received {total}"
            )
