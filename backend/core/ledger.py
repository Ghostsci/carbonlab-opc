"""Deterministic primitives for append-only environmental ledger records."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
import hashlib
import json
from typing import Any
import uuid


FORMAL_VALUE_ORIGINS = frozenset(
    {
        "human_confirmed",
        "erp_signed",
        "meter_signed",
        "migration_verified",
    }
)


class LedgerError(ValueError):
    """Base error for invalid formal ledger operations."""


class UnconfirmedValueError(LedgerError):
    """Raised when an unconfirmed or LLM-origin value reaches the ledger."""


LEDGER_QUANTUM = Decimal("0.000000000001")


def ledger_decimal(value: Decimal | int | str) -> Decimal:
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        return Decimal(str(value)).quantize(LEDGER_QUANTUM)


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        normalized = (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )
        return normalized.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise LedgerError(f"unsupported canonical ledger value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        _json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def idempotency_hash(*parts: Any) -> str:
    return content_hash(list(parts))


def require_confirmed_origin(origin: str | None) -> str:
    normalized = str(origin or "").strip().lower()
    if normalized not in FORMAL_VALUE_ORIGINS:
        raise UnconfirmedValueError(
            "formal numeric values require a human-confirmed or signed origin"
        )
    return normalized
