from decimal import Decimal, localcontext

import pytest

import backend.core.quantity as quantity_module
from backend.core.quantity import BasisError, DimensionalityError, Quantity, QuantityError


def test_ten_thousand_kwh_normalizes_without_float_loss() -> None:
    quantity = Quantity.of("63.26", "万kWh")

    normalized = quantity.convert_to("kWh")

    assert normalized.value == Decimal("632600")
    assert normalized.unit == "kWh"


def test_mwh_converts_to_kwh_exactly() -> None:
    assert Quantity.of("1.25", "MWh").convert_to("kWh").value == Decimal("1250")


def test_tonnes_convert_to_kilograms_exactly() -> None:
    assert Quantity.of("2.75", "t").convert_to("kg").value == Decimal("2750")


def test_tce_uses_statutory_energy_equivalent() -> None:
    assert Quantity.of("1", "tce").convert_to("GJ").value == Decimal("29.307")


def test_addition_converts_compatible_units_without_mutating_operands() -> None:
    left = Quantity.of("1", "MWh")
    right = Quantity.of("250", "kWh")

    total = left + right

    assert total == Quantity.of("1.25", "MWh")
    assert left == Quantity.of("1", "MWh")
    with pytest.raises(DimensionalityError):
        _ = left + Quantity.of("1", "kg")


def test_activity_times_compatible_factor_reduces_to_emissions() -> None:
    activity = Quantity.of("632600", "kWh")
    factor = Quantity.of("0.55", "kgCO2e/kWh")

    result = (activity * factor).convert_to("tCO2e")

    assert result.value == Decimal("347.930")


def test_co2_and_co2e_are_distinct_dimensions() -> None:
    with pytest.raises(DimensionalityError):
        Quantity.of("1", "tCO2").convert_to("tCO2e")


def test_normal_and_actual_cubic_metres_require_contextual_conversion() -> None:
    with pytest.raises(DimensionalityError):
        Quantity.of("100", "Nm3").convert_to("m3")


def test_heating_value_requires_and_preserves_ncv_or_hcv_basis() -> None:
    with pytest.raises(BasisError):
        Quantity.heating_value("35.8", "MJ/Nm3", basis=None)

    ncv = Quantity.heating_value("35.8", "MJ/Nm3", basis="NCV")
    hcv = Quantity.heating_value("39.6", "MJ/Nm3", basis="HCV")

    assert ncv.basis == "NCV"
    with pytest.raises(BasisError):
        _ = ncv + hcv


def test_binary_float_is_rejected_at_formal_quantity_interface() -> None:
    with pytest.raises(QuantityError, match="Decimal"):
        Quantity.of(0.1, "kWh")  # type: ignore[arg-type]


def test_subtraction_uses_left_operand_unit() -> None:
    result = Quantity.of("1", "MWh") - Quantity.of("250", "kWh")

    assert result == Quantity.of("0.75", "MWh")


def test_division_produces_convertible_compound_dimension() -> None:
    intensity = Quantity.of("1000", "kgCO2e") / Quantity.of("2", "t")

    assert intensity.convert_to("kgCO2e/t").value == Decimal("500")


def test_factor_with_wrong_denominator_cannot_masquerade_as_emissions() -> None:
    incompatible = Quantity.of("632600", "kWh") * Quantity.of(
        "0.55",
        "kgCO2e/kg",
    )

    with pytest.raises(DimensionalityError):
        incompatible.convert_to("tCO2e")


def test_formal_arithmetic_is_independent_of_ambient_decimal_precision() -> None:
    with localcontext() as ambient:
        ambient.prec = 6
        result = (
            Quantity.of("632600", "kWh")
            * Quantity.of("0.550012345678", "kgCO2e/kWh")
        ).convert_to("tCO2e")

    assert result.value == Decimal("347.9378098759028")


def test_malformed_unit_expression_is_rejected() -> None:
    with pytest.raises(QuantityError, match="invalid unit expression"):
        Quantity.of("1", "kWh/")


def test_common_ocr_unit_glyphs_are_normalized_at_the_interface() -> None:
    assert Quantity.of("1", "tCO₂e").convert_to("kgCO2e").value == Decimal("1000")
    assert Quantity.of("1", "Nm³").convert_to("Nm3").value == Decimal("1")


def test_kg_per_tonne_normalizes_as_dimensionless_ratio() -> None:
    assert Quantity.of("1000", "kg/t").convert_to("1").value == Decimal("1")


def test_quantity_of_cannot_bypass_heating_value_basis() -> None:
    with pytest.raises(BasisError, match="NCV or HCV"):
        Quantity.of("35.8", "MJ/Nm3")


def test_public_decimal_context_mutation_cannot_change_formal_result() -> None:
    shared_context = getattr(quantity_module, "FORMAL_DECIMAL_CONTEXT", None)
    original_precision = shared_context.prec if shared_context is not None else None
    if shared_context is not None:
        shared_context.prec = 6
    try:
        result = (
            Quantity.of("632600", "kWh")
            * Quantity.of("0.550012345678", "kgCO2e/kWh")
        ).convert_to("tCO2e")
    finally:
        if shared_context is not None:
            shared_context.prec = original_precision

    assert result.value == Decimal("347.9378098759028")


def test_division_by_compound_unit_preserves_denominator_grouping() -> None:
    result = Quantity.of("100", "kgCO2e") / Quantity.of("2", "kg/t")

    assert result.convert_to("tCO2e").value == Decimal("50")


def test_compound_arithmetic_result_can_be_reconstructed_from_value_and_unit() -> None:
    result = Quantity.of("100", "kgCO2e") / Quantity.of("2", "kg/t")

    replayed = Quantity.of(str(result.value), result.unit, basis=result.basis)

    assert replayed.convert_to("tCO2e").value == Decimal("50")
