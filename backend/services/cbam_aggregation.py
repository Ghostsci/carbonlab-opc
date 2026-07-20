"""Deterministic CBAM installation/process aggregation primitives."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Sequence

from backend.core.quantity import Quantity


EmissionCategory = Literal["direct", "indirect"]


@dataclass(frozen=True, slots=True)
class AttributionShare:
    source_ref: str
    process_ref: str
    share: Decimal

    def __post_init__(self) -> None:
        if isinstance(self.share, float):
            raise TypeError("formal attribution shares reject binary float values")
        share = self.share if isinstance(self.share, Decimal) else Decimal(str(self.share))
        if share <= 0 or share > 1:
            raise ValueError("attribution share must be greater than 0 and at most 1")
        object.__setattr__(self, "share", share)


@dataclass(frozen=True, slots=True)
class AttributedEmission:
    source_ref: str
    category: EmissionCategory
    emissions: Quantity


@dataclass(frozen=True, slots=True)
class PrecursorInput:
    source_ref: str
    consumption: Quantity
    specific_embedded_emissions: Quantity
    data_quality: str


@dataclass(frozen=True, slots=True)
class SEEBreakdown:
    direct: Quantity
    indirect: Quantity
    precursor: Quantity
    total: Quantity
    specific: Quantity
    data_quality: str
    audit_refs: tuple[str, ...]


def validate_attribution_totals(attributions: Sequence[AttributionShare]) -> None:
    totals: dict[str, Decimal] = {}
    for attribution in attributions:
        totals[attribution.source_ref] = (
            totals.get(attribution.source_ref, Decimal("0")) + attribution.share
        )
    for source_ref, total in totals.items():
        if total != Decimal("1"):
            raise ValueError(
                f"attribution shares for {source_ref} must total exactly 1.00; "
                f"received {total}"
            )


def calculate_see(
    *,
    production_output: Quantity,
    attributed_emissions: Sequence[AttributedEmission],
    precursors: Sequence[PrecursorInput],
) -> SEEBreakdown:
    output = production_output.convert_to("t")
    if output.value <= 0:
        raise ValueError("production output must be greater than zero")

    direct = Quantity.of("0", "tCO2e")
    indirect = Quantity.of("0", "tCO2e")
    audit_refs: list[str] = []
    for item in attributed_emissions:
        emissions = item.emissions.convert_to("tCO2e")
        if emissions.value < 0:
            raise ValueError("attributed emissions cannot be negative")
        if item.category == "direct":
            direct = direct + emissions
        elif item.category == "indirect":
            indirect = indirect + emissions
        else:
            raise ValueError(f"unsupported CBAM emission category: {item.category}")
        audit_refs.append(item.source_ref)

    precursor_total = Quantity.of("0", "tCO2e")
    quality_labels: list[str] = []
    for item in precursors:
        consumption = item.consumption.convert_to("t")
        if consumption.value < 0:
            raise ValueError("precursor consumption cannot be negative")
        embedded = (
            consumption * item.specific_embedded_emissions
        ).convert_to("tCO2e")
        precursor_total = precursor_total + embedded
        quality_labels.append(item.data_quality)
        audit_refs.append(item.source_ref)

    total = direct + indirect + precursor_total
    specific = (total / output).convert_to("tCO2e/t")
    return SEEBreakdown(
        direct=direct,
        indirect=indirect,
        precursor=precursor_total,
        total=total,
        specific=specific,
        data_quality=_aggregate_data_quality(quality_labels),
        audit_refs=tuple(audit_refs),
    )


def _aggregate_data_quality(labels: Sequence[str]) -> str:
    if not labels:
        return "not_applicable"
    rank = {
        "supplier_verified": 0,
        "supplier_declared": 1,
        "rule_default": 2,
    }
    unknown = [label for label in labels if label not in rank]
    if unknown:
        raise ValueError(f"unsupported precursor data quality: {unknown[0]}")
    return max(labels, key=rank.__getitem__)
