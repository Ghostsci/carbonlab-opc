"""Governed K2 writes for production output, precursors, and cost demos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from typing import Callable
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.ledger import (
    content_hash,
    idempotency_hash,
    ledger_decimal,
    require_confirmed_origin,
)
from backend.core.quantity import Quantity
from backend.models.cbam_ledger import (
    CBAMProduct,
    PrecursorConsumption,
    ProductionOutput,
    ProductionProcess,
    SEEResult,
)
from backend.models.ledger import LedgerIntegrityError
from backend.services.rule_records import resolve_rule_record


@dataclass(frozen=True, slots=True)
class CertificateCost:
    gross: Decimal
    deduction: Decimal
    net: Decimal
    currency: str


def persist_production_output(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    process_id: uuid.UUID,
    product_id: uuid.UUID,
    period_start: datetime,
    period_end: datetime,
    quantity: Decimal | int | str,
    unit: str,
    value_origin: str,
    confirmed_by: str,
) -> ProductionOutput:
    process, product = _process_product(db, tenant_id, process_id, product_id)
    _validate_period(period_start, period_end)
    require_confirmed_origin(value_origin)
    normalized = Quantity.of(quantity, unit).convert_to("t")
    if normalized.value <= 0:
        raise ValueError("production output must be greater than zero")
    value = ledger_decimal(normalized.value)
    key = idempotency_hash(
        tenant_id,
        process.id,
        product.id,
        period_start,
        period_end,
    )
    payload = {
        "record_type": "production_output",
        "tenant_id": tenant_id,
        "process_id": process.id,
        "product_id": product.id,
        "period_start": period_start,
        "period_end": period_end,
        "quantity": value,
        "unit": "t",
        "value_origin": value_origin,
    }
    record_hash = content_hash(payload)
    derived_from = [
        f"production_process:{process.id}",
        f"cbam_product:{product.id}",
    ]

    def previous_query():
        return (
            db.query(ProductionOutput)
            .filter(
                ProductionOutput.tenant_id == tenant_id,
                ProductionOutput.process_id == process.id,
                ProductionOutput.product_id == product.id,
                ProductionOutput.period_start == period_start,
                ProductionOutput.period_end == period_end,
                ProductionOutput.superseded_by_id.is_(None),
            )
            .order_by(ProductionOutput.version.desc())
            .first()
        )

    def build(previous):
        return ProductionOutput(
            tenant_id=tenant_id,
            process_id=process.id,
            product_id=product.id,
            period_start=period_start,
            period_end=period_end,
            quantity=value,
            unit="t",
            derived_from=derived_from,
            content_hash=record_hash,
            idempotency_key=key,
            version=(previous.version + 1) if previous else 1,
            supersedes_id=previous.id if previous else None,
            superseded_by_id=None,
            confirmed_by=confirmed_by,
            confirmed_at=datetime.now(timezone.utc),
        )

    return _append_idempotent(
        db,
        model=ProductionOutput,
        tenant_id=tenant_id,
        key=key,
        record_hash=record_hash,
        previous_query=previous_query,
        build=build,
        label="production output",
    )


def persist_precursor_consumption(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    process_id: uuid.UUID,
    product_id: uuid.UUID,
    period_start: datetime,
    period_end: datetime,
    precursor_name: str,
    quantity: Decimal | int | str,
    unit: str,
    source_kind: str,
    source_see_ref: str,
    specific_emissions: Decimal | int | str | None,
    specific_unit: str | None,
    value_origin: str,
    confirmed_by: str,
) -> PrecursorConsumption:
    process, product = _process_product(db, tenant_id, process_id, product_id)
    _validate_period(period_start, period_end)
    require_confirmed_origin(value_origin)
    consumption = Quantity.of(quantity, unit).convert_to("t")
    if consumption.value <= 0:
        raise ValueError("precursor consumption must be greater than zero")

    if source_kind == "self_produced_see":
        see_id = _parse_ref(source_see_ref, "see_result")
        source_see = (
            db.query(SEEResult)
            .filter(SEEResult.id == see_id, SEEResult.tenant_id == tenant_id)
            .first()
        )
        if source_see is None:
            raise ValueError("self-produced SEE reference not found for tenant")
        specific = Quantity.of(
            source_see.specific_emissions,
            source_see.specific_unit,
        ).convert_to("tCO2e/t")
        data_quality = source_see.data_quality
    else:
        if specific_emissions is None or not specific_unit:
            raise ValueError("precursor specific emissions are required")
        specific = Quantity.of(
            specific_emissions,
            specific_unit,
        ).convert_to("tCO2e/t")
        if specific.value < 0:
            raise ValueError("precursor specific emissions cannot be negative")
        if source_kind == "supplier_see":
            if not source_see_ref.startswith("supplier_see:"):
                raise ValueError("supplier SEE requires supplier_see reference")
            data_quality = "supplier_verified"
        elif source_kind == "rule_default":
            resolve_rule_record(
                db,
                tenant_id=tenant_id,
                reference=source_see_ref,
                expected_kind="precursor_default",
                period_start=period_start,
                period_end=period_end,
            )
            data_quality = "rule_default"
        else:
            raise ValueError(f"unsupported precursor source kind: {source_kind}")

    consumption_value = ledger_decimal(consumption.value)
    specific_value = ledger_decimal(specific.value)
    key = idempotency_hash(
        tenant_id,
        process.id,
        product.id,
        period_start,
        period_end,
        precursor_name,
        source_kind,
        source_see_ref,
    )
    payload = {
        "record_type": "precursor_consumption",
        "tenant_id": tenant_id,
        "process_id": process.id,
        "product_id": product.id,
        "period_start": period_start,
        "period_end": period_end,
        "precursor_name": precursor_name,
        "quantity": consumption_value,
        "unit": "t",
        "source_kind": source_kind,
        "source_see_ref": source_see_ref,
        "specific_emissions": specific_value,
        "specific_unit": "tCO2e/t",
        "data_quality": data_quality,
        "value_origin": value_origin,
    }
    record_hash = content_hash(payload)
    derived_from = [
        f"production_process:{process.id}",
        f"cbam_product:{product.id}",
        source_see_ref,
    ]

    def previous_query():
        return (
            db.query(PrecursorConsumption)
            .filter(
                PrecursorConsumption.tenant_id == tenant_id,
                PrecursorConsumption.process_id == process.id,
                PrecursorConsumption.product_id == product.id,
                PrecursorConsumption.period_start == period_start,
                PrecursorConsumption.period_end == period_end,
                PrecursorConsumption.precursor_name == precursor_name,
                PrecursorConsumption.superseded_by_id.is_(None),
            )
            .order_by(PrecursorConsumption.version.desc())
            .first()
        )

    def build(previous):
        return PrecursorConsumption(
            tenant_id=tenant_id,
            process_id=process.id,
            product_id=product.id,
            period_start=period_start,
            period_end=period_end,
            precursor_name=precursor_name,
            quantity=consumption_value,
            unit="t",
            source_kind=source_kind,
            source_see_ref=source_see_ref,
            specific_emissions=specific_value,
            specific_unit="tCO2e/t",
            data_quality=data_quality,
            derived_from=derived_from,
            content_hash=record_hash,
            idempotency_key=key,
            version=(previous.version + 1) if previous else 1,
            supersedes_id=previous.id if previous else None,
            superseded_by_id=None,
            confirmed_by=confirmed_by,
            confirmed_at=datetime.now(timezone.utc),
        )

    return _append_idempotent(
        db,
        model=PrecursorConsumption,
        tenant_id=tenant_id,
        key=key,
        record_hash=record_hash,
        previous_query=previous_query,
        build=build,
        label="precursor consumption",
    )


def calculate_certificate_cost(
    *,
    embedded_emissions: Quantity,
    certificate_price_per_tonne: Decimal | int | str,
    currency: str,
    eligible_carbon_price_paid: Decimal | int | str = "0",
) -> CertificateCost:
    emissions = embedded_emissions.convert_to("tCO2e")
    if emissions.value < 0:
        raise ValueError("embedded emissions cannot be negative")
    price = _decimal_input(certificate_price_per_tonne)
    deduction = _decimal_input(eligible_carbon_price_paid)
    if price < 0 or deduction < 0:
        raise ValueError("certificate price and deduction cannot be negative")
    normalized_currency = currency.strip().upper()
    if len(normalized_currency) != 3:
        raise ValueError("currency must be a three-letter code")
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        gross = (emissions.value * price).quantize(Decimal("0.01"))
        paid = deduction.quantize(Decimal("0.01"))
        net = max(Decimal("0"), gross - paid).quantize(Decimal("0.01"))
    return CertificateCost(
        gross=gross,
        deduction=paid,
        net=net,
        currency=normalized_currency,
    )


def _append_idempotent(
    db: Session,
    *,
    model,
    tenant_id: uuid.UUID,
    key: str,
    record_hash: str,
    previous_query: Callable,
    build: Callable,
    label: str,
):
    for _attempt in range(5):
        existing = (
            db.query(model)
            .filter(model.tenant_id == tenant_id, model.idempotency_key == key)
            .order_by(model.version.desc())
            .first()
        )
        if existing and existing.content_hash == record_hash:
            return existing
        previous = previous_query()
        record = build(previous)
        try:
            with db.begin_nested():
                db.add(record)
                db.flush()
        except (IntegrityError, LedgerIntegrityError) as exc:
            db.expire_all()
            winner = (
                db.query(model)
                .filter(model.tenant_id == tenant_id, model.idempotency_key == key)
                .order_by(model.version.desc())
                .first()
            )
            if winner is None:
                raise exc
            if winner.content_hash == record_hash:
                return winner
            continue
        if previous:
            db.expire(previous, ["superseded_by_id"])
        return record
    raise RuntimeError(f"{label} ledger write did not converge")


def _process_product(db, tenant_id, process_id, product_id):
    process = (
        db.query(ProductionProcess)
        .filter(
            ProductionProcess.id == process_id,
            ProductionProcess.tenant_id == tenant_id,
        )
        .first()
    )
    product = (
        db.query(CBAMProduct)
        .filter(CBAMProduct.id == product_id, CBAMProduct.tenant_id == tenant_id)
        .first()
    )
    if process is None or product is None:
        raise LookupError("process or product not found for tenant")
    if product.process_id != process.id:
        raise ValueError("product does not belong to process")
    return process, product


def _validate_period(start: datetime, end: datetime) -> None:
    if end < start:
        raise ValueError("period_end must not precede period_start")


def _parse_ref(value: str, expected_prefix: str) -> uuid.UUID:
    prefix, separator, identifier = value.partition(":")
    if separator != ":" or prefix != expected_prefix:
        raise ValueError(f"expected {expected_prefix} reference")
    try:
        return uuid.UUID(identifier)
    except ValueError as exc:
        raise ValueError(f"invalid {expected_prefix} reference") from exc


def _decimal_input(value: Decimal | int | str) -> Decimal:
    if isinstance(value, bool | float):
        raise TypeError("formal cost calculation rejects binary float values")
    parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    if not parsed.is_finite():
        raise ValueError("cost input must be finite")
    return parsed
