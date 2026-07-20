"""Database types that preserve formal decimal values across supported dialects."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import Numeric, String
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator, TypeEngine


class ExactDecimal(TypeDecorator[Decimal]):
    """NUMERIC on PostgreSQL and canonical decimal text on SQLite.

    SQLite NUMERIC affinity can silently coerce large decimal strings to binary
    floats. Formal ledger values therefore use text storage on SQLite.
    """

    impl = Numeric
    cache_ok = True

    def __init__(self, precision: int = 28, scale: int = 12) -> None:
        self.precision = precision
        self.scale = scale
        super().__init__()

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(self.precision + 3))
        return dialect.type_descriptor(
            Numeric(self.precision, self.scale, asdecimal=True)
        )

    def process_bind_param(
        self,
        value: Decimal | int | str | None,
        dialect: Dialect,
    ) -> Decimal | str | None:
        if value is None:
            return None
        if isinstance(value, float):
            raise TypeError("formal decimal columns reject binary float values")
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
        return format(decimal_value, "f") if dialect.name == "sqlite" else decimal_value

    def process_result_value(
        self,
        value: Decimal | str | int | None,
        _dialect: Dialect,
    ) -> Decimal | None:
        if value is None:
            return None
        return value if isinstance(value, Decimal) else Decimal(str(value))
