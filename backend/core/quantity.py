"""Dimension-safe decimal quantities for formal environmental calculations."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
import re
from types import MappingProxyType
from typing import Mapping


_UNIT_GLYPH_TRANSLATION: Mapping[str | int, str | int | None] = MappingProxyType(
    str.maketrans({"₂": "2", "³": "3", "·": "*", "×": "*"})
)


def _formal_context():
    """Return a fresh context so callers cannot mutate formal arithmetic globally."""
    return localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN))


class QuantityError(ValueError):
    """Base error for invalid quantity operations."""


class UnknownUnitError(QuantityError):
    """Raised when a unit is not registered."""


class DimensionalityError(QuantityError):
    """Raised when an operation combines incompatible dimensions."""


class BasisError(QuantityError):
    """Raised when quantities use missing or incompatible methodological bases."""


@dataclass(frozen=True, slots=True)
class UnitDefinition:
    symbol: str
    dimensions: tuple[tuple[str, int], ...]
    canonical_factor: Decimal


def _dimensions(**powers: int) -> tuple[tuple[str, int], ...]:
    return tuple(sorted((name, power) for name, power in powers.items() if power))


def _combine_dimensions(
    left: tuple[tuple[str, int], ...],
    right: tuple[tuple[str, int], ...],
    *,
    right_sign: int,
) -> tuple[tuple[str, int], ...]:
    powers = dict(left)
    for name, exponent in right:
        powers[name] = powers.get(name, 0) + right_sign * exponent
    return _dimensions(**powers)


_HEATING_VALUE_DIMENSIONS = frozenset(
    {
        _dimensions(energy=1, mass=-1),
        _dimensions(energy=1, actual_volume=-1),
        _dimensions(energy=1, normal_volume=-1),
    }
)

CANONICAL_UNIT_BY_DIMENSION: Mapping[str, str] = MappingProxyType(
    {
        "energy": "J",
        "mass": "kg",
        "co2_mass": "kgCO2",
        "co2e_mass": "kgCO2e",
        "actual_volume": "m3",
        "normal_volume": "Nm3",
    }
)


def _canonical_unit(dimensions: tuple[tuple[str, int], ...]) -> str:
    numerator: list[str] = []
    denominator: list[str] = []
    for name, exponent in dimensions:
        try:
            symbol = CANONICAL_UNIT_BY_DIMENSION[name]
        except KeyError as exc:
            raise DimensionalityError(f"no canonical unit for dimension: {name}") from exc
        target = numerator if exponent > 0 else denominator
        target.extend([symbol] * abs(exponent))
    expression = "*".join(numerator) if numerator else "1"
    if denominator:
        expression += "".join(f"/{symbol}" for symbol in denominator)
    return expression


UNIT_DEFINITIONS: Mapping[str, UnitDefinition] = MappingProxyType(
    {
        "1": UnitDefinition("1", _dimensions(), Decimal("1")),
        "J": UnitDefinition("J", _dimensions(energy=1), Decimal("1")),
        "kWh": UnitDefinition("kWh", _dimensions(energy=1), Decimal("3600000")),
        "MWh": UnitDefinition("MWh", _dimensions(energy=1), Decimal("3600000000")),
        "万kWh": UnitDefinition("万kWh", _dimensions(energy=1), Decimal("36000000000")),
        "GJ": UnitDefinition("GJ", _dimensions(energy=1), Decimal("1000000000")),
        "MJ": UnitDefinition("MJ", _dimensions(energy=1), Decimal("1000000")),
        "tce": UnitDefinition("tce", _dimensions(energy=1), Decimal("29307000000")),
        "kg": UnitDefinition("kg", _dimensions(mass=1), Decimal("1")),
        "t": UnitDefinition("t", _dimensions(mass=1), Decimal("1000")),
        "kgCO2": UnitDefinition("kgCO2", _dimensions(co2_mass=1), Decimal("1")),
        "tCO2": UnitDefinition("tCO2", _dimensions(co2_mass=1), Decimal("1000")),
        "kgCO2e": UnitDefinition("kgCO2e", _dimensions(co2e_mass=1), Decimal("1")),
        "tCO2e": UnitDefinition("tCO2e", _dimensions(co2e_mass=1), Decimal("1000")),
        "m3": UnitDefinition("m3", _dimensions(actual_volume=1), Decimal("1")),
        "Nm3": UnitDefinition("Nm3", _dimensions(normal_volume=1), Decimal("1")),
    }
)


def _resolve_unit(expression: str) -> UnitDefinition:
    normalized = expression.translate(_UNIT_GLYPH_TRANSLATION).replace(" ", "")
    tokens = [token for token in re.split(r"([*/])", normalized) if token]
    if (
        not tokens
        or len(tokens) % 2 == 0
        or any(token in {"*", "/"} for token in tokens[::2])
        or any(token not in {"*", "/"} for token in tokens[1::2])
    ):
        raise UnknownUnitError(f"invalid unit expression: {expression}")

    powers: dict[str, int] = {}
    factor = Decimal("1")
    operation = "*"
    with _formal_context():
        for token in tokens:
            if token in {"*", "/"}:
                operation = token
                continue
            definition = UNIT_DEFINITIONS.get(token)
            if definition is None:
                raise UnknownUnitError(f"unknown unit: {token}")
            sign = 1 if operation == "*" else -1
            factor = (
                factor * definition.canonical_factor
                if sign == 1
                else factor / definition.canonical_factor
            )
            for name, exponent in definition.dimensions:
                powers[name] = powers.get(name, 0) + sign * exponent
            operation = "*"
    return UnitDefinition(normalized, _dimensions(**powers), factor)


def _decimal(value: Decimal | int | str) -> Decimal:
    if isinstance(value, bool | float):
        raise QuantityError("formal quantities require Decimal, int, or decimal string")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise QuantityError(f"invalid decimal quantity: {value!r}") from exc
    if not parsed.is_finite():
        raise QuantityError("quantity must be finite")
    return parsed


@dataclass(frozen=True, slots=True)
class Quantity:
    value: Decimal
    unit: str
    basis: str | None = None
    _dimensions: tuple[tuple[str, int], ...] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _canonical_factor: Decimal = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _decimal(self.value))
        if self.basis is not None:
            normalized_basis = self.basis.strip().upper()
            if not normalized_basis:
                raise BasisError("basis cannot be blank")
            object.__setattr__(self, "basis", normalized_basis)
        definition = _resolve_unit(self.unit)
        self._validate_basis_for_dimensions(definition.dimensions, self.basis)
        object.__setattr__(self, "_dimensions", definition.dimensions)
        object.__setattr__(self, "_canonical_factor", definition.canonical_factor)

    @classmethod
    def _from_operation(
        cls,
        *,
        value: Decimal,
        unit: str,
        basis: str | None,
        dimensions: tuple[tuple[str, int], ...],
        canonical_factor: Decimal,
    ) -> "Quantity":
        cls._validate_basis_for_dimensions(dimensions, basis)
        instance = object.__new__(cls)
        object.__setattr__(instance, "value", _decimal(value))
        object.__setattr__(instance, "unit", unit)
        object.__setattr__(instance, "basis", basis)
        object.__setattr__(instance, "_dimensions", dimensions)
        object.__setattr__(instance, "_canonical_factor", canonical_factor)
        return instance

    @staticmethod
    def _validate_basis_for_dimensions(
        dimensions: tuple[tuple[str, int], ...],
        basis: str | None,
    ) -> None:
        if dimensions in _HEATING_VALUE_DIMENSIONS and basis not in {"NCV", "HCV"}:
            raise BasisError(
                "heating value quantities require an explicit NCV or HCV basis"
            )

    @classmethod
    def of(
        cls,
        value: Decimal | int | str,
        unit: str,
        *,
        basis: str | None = None,
    ) -> "Quantity":
        return cls(_decimal(value), unit, basis)

    @classmethod
    def heating_value(
        cls,
        value: Decimal | int | str,
        unit: str,
        *,
        basis: str | None,
    ) -> "Quantity":
        normalized_basis = basis.strip().upper() if basis else None
        if normalized_basis not in {"NCV", "HCV"}:
            raise BasisError("heating value basis must be explicitly NCV or HCV")
        dimensions = _resolve_unit(unit).dimensions
        if dimensions not in _HEATING_VALUE_DIMENSIONS:
            raise DimensionalityError(
                "heating value must have energy per mass or volume dimensions"
            )
        return cls.of(value, unit, basis=normalized_basis)

    def convert_to(self, unit: str) -> "Quantity":
        target = _resolve_unit(unit)
        if self._dimensions != target.dimensions:
            raise DimensionalityError(
                f"cannot convert {self.unit} to incompatible unit {unit}"
            )
        with _formal_context():
            canonical_value = self.value * self._canonical_factor
            converted_value = canonical_value / target.canonical_factor
        return Quantity(converted_value, target.symbol, self.basis)

    def __add__(self, other: object) -> "Quantity":
        if not isinstance(other, Quantity):
            return NotImplemented
        self._require_compatible_basis(other)
        self._require_compatible_dimensions(other)
        with _formal_context():
            converted_value = (
                other.value * other._canonical_factor / self._canonical_factor
            )
            value = self.value + converted_value
        return self._from_operation(
            value=value,
            unit=self.unit,
            basis=self.basis,
            dimensions=self._dimensions,
            canonical_factor=self._canonical_factor,
        )

    def __sub__(self, other: object) -> "Quantity":
        if not isinstance(other, Quantity):
            return NotImplemented
        self._require_compatible_basis(other)
        self._require_compatible_dimensions(other)
        with _formal_context():
            converted_value = (
                other.value * other._canonical_factor / self._canonical_factor
            )
            value = self.value - converted_value
        return self._from_operation(
            value=value,
            unit=self.unit,
            basis=self.basis,
            dimensions=self._dimensions,
            canonical_factor=self._canonical_factor,
        )

    def __mul__(self, other: object) -> "Quantity":
        if not isinstance(other, Quantity):
            return NotImplemented
        self._require_compatible_basis(other, allow_missing=True)
        dimensions = _combine_dimensions(
            self._dimensions,
            other._dimensions,
            right_sign=1,
        )
        with _formal_context():
            value = (
                self.value
                * self._canonical_factor
                * other.value
                * other._canonical_factor
            )
        return self._from_operation(
            value=value,
            unit=_canonical_unit(dimensions),
            basis=self.basis or other.basis,
            dimensions=dimensions,
            canonical_factor=Decimal("1"),
        )

    def __truediv__(self, other: object) -> "Quantity":
        if not isinstance(other, Quantity):
            return NotImplemented
        if other.value == 0:
            raise ZeroDivisionError("cannot divide by a zero quantity")
        self._require_compatible_basis(other, allow_missing=True)
        dimensions = _combine_dimensions(
            self._dimensions,
            other._dimensions,
            right_sign=-1,
        )
        with _formal_context():
            numerator = self.value * self._canonical_factor
            denominator = other.value * other._canonical_factor
            value = numerator / denominator
        return self._from_operation(
            value=value,
            unit=_canonical_unit(dimensions),
            basis=self.basis or other.basis,
            dimensions=dimensions,
            canonical_factor=Decimal("1"),
        )

    def _require_compatible_dimensions(self, other: "Quantity") -> None:
        if self._dimensions != other._dimensions:
            raise DimensionalityError(
                f"incompatible dimensions: {self.unit} and {other.unit}"
            )

    def _require_compatible_basis(
        self,
        other: "Quantity",
        *,
        allow_missing: bool = False,
    ) -> None:
        if self.basis == other.basis:
            return
        if allow_missing and (self.basis is None or other.basis is None):
            return
        raise BasisError(
            f"incompatible bases: {self.basis or 'unspecified'} and "
            f"{other.basis or 'unspecified'}"
        )
