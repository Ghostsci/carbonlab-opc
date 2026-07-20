"""Persist and replay deterministic CBAM specific embedded emissions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.ledger import content_hash, idempotency_hash, ledger_decimal
from backend.core.quantity import Quantity
from backend.models.cbam_ledger import (
    CBAMProduct,
    PrecursorConsumption,
    ProductionOutput,
    ProductionProcess,
    SEEResult,
    SourceStreamAttribution,
)
from backend.models.emission_result import EmissionResult
from backend.models.ledger import LedgerIntegrityError
from backend.services.cbam_aggregation import (
    AttributionShare,
    AttributedEmission,
    PrecursorInput,
    SEEBreakdown,
    calculate_see,
    validate_attribution_totals,
)
from backend.services.rule_records import resolve_rule_record


@dataclass(frozen=True, slots=True)
class _SEEInputs:
    output: ProductionOutput
    attributions: tuple[SourceStreamAttribution, ...]
    precursors: tuple[PrecursorConsumption, ...]
    breakdown: SEEBreakdown


def calculate_and_persist_see(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    process_id: uuid.UUID,
    product_id: uuid.UUID,
    production_output_id: uuid.UUID,
    methodology_ref: str,
    confirmed_by: str,
) -> SEEResult:
    process = _tenant_record(db, ProductionProcess, tenant_id, process_id, "process")
    product = _tenant_record(db, CBAMProduct, tenant_id, product_id, "product")
    output = _tenant_record(
        db,
        ProductionOutput,
        tenant_id,
        production_output_id,
        "production output",
    )
    resolve_rule_record(
        db,
        tenant_id=tenant_id,
        reference=methodology_ref,
        expected_kind="cbam_methodology",
        period_start=output.period_start,
        period_end=output.period_end,
    )
    if product.process_id != process.id:
        raise ValueError("product does not belong to process")
    if output.process_id != process.id or output.product_id != product.id:
        raise ValueError("production output does not belong to process/product")

    inputs = _load_current_inputs(
        db,
        tenant_id=tenant_id,
        process=process,
        product=product,
        output=output,
    )
    return _append_see_result(
        db,
        tenant_id=tenant_id,
        process=process,
        product=product,
        inputs=inputs,
        methodology_ref=methodology_ref,
        confirmed_by=confirmed_by,
    )


def replay_see_result(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    see_result_id: uuid.UUID,
) -> dict:
    stored = (
        db.query(SEEResult)
        .filter(SEEResult.id == see_result_id, SEEResult.tenant_id == tenant_id)
        .first()
    )
    if stored is None:
        raise LookupError("SEE result not found for tenant")
    output_ids = _derived_ids(stored.derived_from, "production_output")
    attribution_ids = _derived_ids(stored.derived_from, "attribution")
    precursor_ids = _derived_ids(stored.derived_from, "precursor")
    if len(output_ids) != 1:
        return {"match": False, "reason": "invalid_output_provenance"}
    output = _tenant_record(
        db,
        ProductionOutput,
        tenant_id,
        output_ids[0],
        "production output",
    )
    attributions = _records_by_ids(
        db,
        SourceStreamAttribution,
        tenant_id,
        attribution_ids,
    )
    precursors = _records_by_ids(
        db,
        PrecursorConsumption,
        tenant_id,
        precursor_ids,
    )
    breakdown = _calculate_from_records(
        db,
        tenant_id=tenant_id,
        output=output,
        attributions=attributions,
        precursors=precursors,
    )
    payload = _see_payload(
        tenant_id=tenant_id,
        process_id=stored.process_id,
        product_id=stored.product_id,
        output=output,
        breakdown=breakdown,
        methodology_ref=stored.methodology_ref,
        derived_from=stored.derived_from,
    )
    expected_hash = content_hash(payload)
    expected = _breakdown_values(breakdown)
    actual = {
        "direct": ledger_decimal(stored.direct_emissions),
        "indirect": ledger_decimal(stored.indirect_emissions),
        "precursor": ledger_decimal(stored.precursor_emissions),
        "total": ledger_decimal(stored.total_emissions),
        "specific": ledger_decimal(stored.specific_emissions),
    }
    matches = (
        actual == expected
        and stored.emissions_unit == "tCO2e"
        and stored.specific_unit == "tCO2e/t"
        and stored.content_hash == expected_hash
    )
    return {
        "match": matches,
        "reason": None if matches else "replay_mismatch",
        "content_hash_match": stored.content_hash == expected_hash,
        "stored": {key: format(value, "f") for key, value in actual.items()},
        "recomputed": {key: format(value, "f") for key, value in expected.items()},
    }


def _load_current_inputs(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    process: ProductionProcess,
    product: CBAMProduct,
    output: ProductionOutput,
) -> _SEEInputs:
    attributions = tuple(
        db.query(SourceStreamAttribution)
        .filter(
            SourceStreamAttribution.tenant_id == tenant_id,
            SourceStreamAttribution.process_id == process.id,
            SourceStreamAttribution.period_start == output.period_start,
            SourceStreamAttribution.period_end == output.period_end,
            SourceStreamAttribution.superseded_by_id.is_(None),
        )
        .order_by(SourceStreamAttribution.id)
        .all()
    )
    if not attributions:
        raise ValueError("no source-stream attributions for process and period")
    for source_ref in {item.source_ref for item in attributions}:
        source_attributions = (
            db.query(SourceStreamAttribution)
            .filter(
                SourceStreamAttribution.tenant_id == tenant_id,
                SourceStreamAttribution.source_ref == source_ref,
                SourceStreamAttribution.period_start == output.period_start,
                SourceStreamAttribution.period_end == output.period_end,
                SourceStreamAttribution.superseded_by_id.is_(None),
            )
            .all()
        )
        validate_attribution_totals(
            [
                AttributionShare(
                    source_ref=item.source_ref,
                    process_ref=f"production_process:{item.process_id}",
                    share=item.share,
                )
                for item in source_attributions
            ]
        )

    precursors = tuple(
        db.query(PrecursorConsumption)
        .filter(
            PrecursorConsumption.tenant_id == tenant_id,
            PrecursorConsumption.process_id == process.id,
            PrecursorConsumption.product_id == product.id,
            PrecursorConsumption.period_start == output.period_start,
            PrecursorConsumption.period_end == output.period_end,
            PrecursorConsumption.superseded_by_id.is_(None),
        )
        .order_by(PrecursorConsumption.id)
        .all()
    )
    breakdown = _calculate_from_records(
        db,
        tenant_id=tenant_id,
        output=output,
        attributions=attributions,
        precursors=precursors,
    )
    return _SEEInputs(output, attributions, precursors, breakdown)


def _calculate_from_records(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    output: ProductionOutput,
    attributions: Sequence[SourceStreamAttribution],
    precursors: Sequence[PrecursorConsumption],
) -> SEEBreakdown:
    attributed_emissions: list[AttributedEmission] = []
    for attribution in attributions:
        result_id = _parse_ref(attribution.source_ref, "emission_result")
        result = (
            db.query(EmissionResult)
            .filter(
                EmissionResult.id == result_id,
                EmissionResult.tenant_id == tenant_id,
            )
            .first()
        )
        if result is None:
            raise ValueError("attribution references missing or foreign-tenant result")
        if (
            result.period_start != output.period_start
            or result.period_end != output.period_end
        ):
            raise ValueError("attribution result period does not match production output")
        if result.scope == "scope_1":
            category = "direct"
        elif result.scope == "scope_2":
            category = "indirect"
        else:
            raise ValueError(f"unsupported CBAM emission scope: {result.scope}")
        allocated = (
            Quantity.of(result.co2_tonnes, result.unit)
            * Quantity.of(attribution.share, "1")
        ).convert_to("tCO2e")
        attributed_emissions.append(
            AttributedEmission(
                source_ref=attribution.source_ref,
                category=category,
                emissions=allocated,
            )
        )
    precursor_inputs = [
        PrecursorInput(
            source_ref=item.source_see_ref,
            consumption=Quantity.of(item.quantity, item.unit),
            specific_embedded_emissions=Quantity.of(
                item.specific_emissions,
                item.specific_unit,
            ),
            data_quality=item.data_quality,
        )
        for item in precursors
    ]
    return calculate_see(
        production_output=Quantity.of(output.quantity, output.unit),
        attributed_emissions=attributed_emissions,
        precursors=precursor_inputs,
    )


def _append_see_result(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    process: ProductionProcess,
    product: CBAMProduct,
    inputs: _SEEInputs,
    methodology_ref: str,
    confirmed_by: str,
) -> SEEResult:
    attribution_ids = [item.id for item in inputs.attributions]
    precursor_ids = [item.id for item in inputs.precursors]
    key = idempotency_hash(
        tenant_id,
        process.id,
        product.id,
        inputs.output.id,
        sorted(str(item) for item in attribution_ids),
        sorted(str(item) for item in precursor_ids),
        methodology_ref,
    )
    derived_from = [
        f"production_output:{inputs.output.id}",
        *(f"attribution:{item}" for item in attribution_ids),
        *(f"precursor:{item}" for item in precursor_ids),
        methodology_ref,
    ]
    payload = _see_payload(
        tenant_id=tenant_id,
        process_id=process.id,
        product_id=product.id,
        output=inputs.output,
        breakdown=inputs.breakdown,
        methodology_ref=methodology_ref,
        derived_from=derived_from,
    )
    record_hash = content_hash(payload)
    values = _breakdown_values(inputs.breakdown)

    for _attempt in range(5):
        existing = (
            db.query(SEEResult)
            .filter(
                SEEResult.tenant_id == tenant_id,
                SEEResult.idempotency_key == key,
            )
            .order_by(SEEResult.version.desc())
            .first()
        )
        if existing and existing.content_hash == record_hash:
            return existing
        previous = (
            db.query(SEEResult)
            .filter(
                SEEResult.tenant_id == tenant_id,
                SEEResult.process_id == process.id,
                SEEResult.product_id == product.id,
                SEEResult.period_start == inputs.output.period_start,
                SEEResult.period_end == inputs.output.period_end,
                SEEResult.superseded_by_id.is_(None),
            )
            .order_by(SEEResult.version.desc())
            .first()
        )
        result = SEEResult(
            tenant_id=tenant_id,
            process_id=process.id,
            product_id=product.id,
            production_output_id=inputs.output.id,
            period_start=inputs.output.period_start,
            period_end=inputs.output.period_end,
            direct_emissions=values["direct"],
            indirect_emissions=values["indirect"],
            precursor_emissions=values["precursor"],
            total_emissions=values["total"],
            emissions_unit="tCO2e",
            specific_emissions=values["specific"],
            specific_unit="tCO2e/t",
            data_quality=inputs.breakdown.data_quality,
            methodology_ref=methodology_ref,
            derived_from=derived_from,
            content_hash=record_hash,
            idempotency_key=key,
            version=(previous.version + 1) if previous else 1,
            supersedes_id=previous.id if previous else None,
            superseded_by_id=None,
            confirmed_by=confirmed_by,
            confirmed_at=datetime.now(timezone.utc),
        )
        try:
            with db.begin_nested():
                db.add(result)
                db.flush()
        except (IntegrityError, LedgerIntegrityError) as exc:
            db.expire_all()
            winner = (
                db.query(SEEResult)
                .filter(
                    SEEResult.tenant_id == tenant_id,
                    SEEResult.idempotency_key == key,
                )
                .order_by(SEEResult.version.desc())
                .first()
            )
            if winner is None:
                raise exc
            if winner.content_hash == record_hash:
                return winner
            continue
        if previous:
            db.expire(previous, ["superseded_by_id"])
        return result
    raise RuntimeError("SEE ledger write did not converge after concurrent retries")


def _see_payload(
    *,
    tenant_id: uuid.UUID,
    process_id: uuid.UUID,
    product_id: uuid.UUID,
    output: ProductionOutput,
    breakdown: SEEBreakdown,
    methodology_ref: str,
    derived_from: Sequence[str],
) -> dict:
    values = _breakdown_values(breakdown)
    return {
        "record_type": "cbam_see_result",
        "tenant_id": tenant_id,
        "process_id": process_id,
        "product_id": product_id,
        "production_output_id": output.id,
        "period_start": output.period_start,
        "period_end": output.period_end,
        **values,
        "emissions_unit": "tCO2e",
        "specific_unit": "tCO2e/t",
        "data_quality": breakdown.data_quality,
        "methodology_ref": methodology_ref,
        "derived_from": list(derived_from),
    }


def _breakdown_values(breakdown: SEEBreakdown) -> dict:
    return {
        "direct": ledger_decimal(breakdown.direct.convert_to("tCO2e").value),
        "indirect": ledger_decimal(breakdown.indirect.convert_to("tCO2e").value),
        "precursor": ledger_decimal(breakdown.precursor.convert_to("tCO2e").value),
        "total": ledger_decimal(breakdown.total.convert_to("tCO2e").value),
        "specific": ledger_decimal(
            breakdown.specific.convert_to("tCO2e/t").value
        ),
    }


def _tenant_record(db: Session, model, tenant_id, record_id, label):
    record = (
        db.query(model)
        .filter(model.id == record_id, model.tenant_id == tenant_id)
        .first()
    )
    if record is None:
        raise LookupError(f"{label} not found for tenant")
    return record


def _parse_ref(value: str, expected_type: str) -> uuid.UUID:
    prefix, separator, identifier = value.partition(":")
    if separator != ":" or prefix != expected_type:
        raise ValueError(f"expected {expected_type} reference")
    try:
        return uuid.UUID(identifier)
    except ValueError as exc:
        raise ValueError(f"invalid {expected_type} reference") from exc


def _derived_ids(values: Sequence[str], prefix: str) -> list[uuid.UUID]:
    return [_parse_ref(value, prefix) for value in values if value.startswith(f"{prefix}:")]


def _records_by_ids(db: Session, model, tenant_id, ids: Sequence[uuid.UUID]):
    if not ids:
        return ()
    records = (
        db.query(model)
        .filter(model.tenant_id == tenant_id, model.id.in_(ids))
        .all()
    )
    by_id = {record.id: record for record in records}
    if len(by_id) != len(set(ids)):
        raise ValueError("SEE provenance references missing or foreign-tenant records")
    return tuple(by_id[record_id] for record_id in ids)
