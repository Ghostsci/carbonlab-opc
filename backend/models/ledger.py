"""Shared columns and constraints for append-only formal ledger records."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    Uuid,
    event,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class LedgerRecordMixin:
    """Inline provenance, idempotency, confirmation, and version-chain fields."""

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    derived_from: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confirmed_by: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    @declared_attr
    def supersedes_id(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(
            Uuid,
            nullable=True,
        )

    @declared_attr
    def superseded_by_id(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(
            Uuid,
            nullable=True,
        )

    @declared_attr.directive
    def __table_args__(cls):
        table_name = cls.__tablename__
        return (
            UniqueConstraint(
                "id",
                "tenant_id",
                name=f"uq_{table_name}_id_tenant",
            ),
            ForeignKeyConstraint(
                ["supersedes_id", "tenant_id"],
                [f"{table_name}.id", f"{table_name}.tenant_id"],
                name=f"fk_{table_name}_supersedes_tenant",
                deferrable=True,
                initially="DEFERRED",
            ),
            ForeignKeyConstraint(
                ["superseded_by_id", "tenant_id"],
                [f"{table_name}.id", f"{table_name}.tenant_id"],
                name=f"fk_{table_name}_superseded_by_tenant",
                deferrable=True,
                initially="DEFERRED",
            ),
            UniqueConstraint(
                "tenant_id",
                "idempotency_key",
                "version",
                name=f"uq_{table_name}_tenant_idempotency_version",
            ),
            UniqueConstraint(
                "supersedes_id",
                name=f"uq_{table_name}_supersedes",
            ),
            UniqueConstraint(
                "superseded_by_id",
                name=f"uq_{table_name}_superseded_by",
            ),
            CheckConstraint(
                "version >= 1",
                name=f"ck_{table_name}_positive_version",
            ),
            CheckConstraint(
                "supersedes_id IS NULL OR supersedes_id <> id",
                name=f"ck_{table_name}_not_self_supersedes",
            ),
            CheckConstraint(
                "superseded_by_id IS NULL OR superseded_by_id <> id",
                name=f"ck_{table_name}_not_self_superseded_by",
            ),
        )


class LedgerImmutableError(RuntimeError):
    """Raised when confirmed ledger content is mutated in place."""


class LedgerIntegrityError(RuntimeError):
    """Raised when a version chain is cross-tenant, discontinuous, or one-sided."""


def _load_chain_record(connection, target, record_id):
    table = target.__table__
    return connection.execute(
        select(
            table.c.id,
            table.c.tenant_id,
            table.c.version,
            table.c.supersedes_id,
            table.c.superseded_by_id,
        ).where(table.c.id == record_id)
    ).mappings().first()


@event.listens_for(LedgerRecordMixin, "before_insert", propagate=True)
def _validate_superseding_record(_mapper, connection, target) -> None:
    if target.superseded_by_id is not None:
        raise LedgerIntegrityError(
            "new ledger versions cannot declare superseded_by_id"
        )
    if target.supersedes_id is None:
        if target.version != 1:
            raise LedgerIntegrityError("root ledger records must start at version 1")
        return
    parent = _load_chain_record(connection, target, target.supersedes_id)
    if parent is None:
        raise LedgerIntegrityError("superseded ledger record does not exist")
    if parent["tenant_id"] != target.tenant_id:
        raise LedgerIntegrityError("supersession cannot cross tenant boundaries")
    if parent["superseded_by_id"] is not None:
        raise LedgerIntegrityError("ledger record is already superseded")
    if target.version != parent["version"] + 1:
        raise LedgerIntegrityError("supersession version must be contiguous")


@event.listens_for(LedgerRecordMixin, "after_insert", propagate=True)
def _complete_reverse_supersession(_mapper, connection, target) -> None:
    if target.supersedes_id is None:
        return
    parent = _load_chain_record(connection, target, target.supersedes_id)
    if parent is not None and parent["superseded_by_id"] == target.id:
        return
    if parent is None or parent["superseded_by_id"] is not None:
        raise LedgerIntegrityError("failed to complete reverse supersession link")
    table = target.__table__
    result = connection.execute(
        update(table)
        .where(
            table.c.id == target.supersedes_id,
            table.c.tenant_id == target.tenant_id,
            table.c.superseded_by_id.is_(None),
        )
        .values(superseded_by_id=target.id)
    )
    if result.rowcount != 1:
        raise LedgerIntegrityError("failed to complete reverse supersession link")


@event.listens_for(LedgerRecordMixin, "before_update", propagate=True)
def _guard_confirmed_ledger_update(_mapper, connection, target) -> None:
    state = inspect(target)
    changed = {
        attribute.key
        for attribute in state.mapper.column_attrs
        if state.attrs[attribute.key].history.has_changes()
    }
    changed.discard("updated_at")
    if not changed:
        return
    if changed == {"superseded_by_id"}:
        history = state.attrs.superseded_by_id.history
        old_value = history.deleted[0] if history.deleted else None
        new_value = history.added[0] if history.added else None
        if old_value is None and new_value is not None:
            successor = _load_chain_record(connection, target, new_value)
            if (
                successor is not None
                and successor["tenant_id"] == target.tenant_id
                and successor["supersedes_id"] == target.id
                and successor["version"] == target.version + 1
            ):
                return
            raise LedgerIntegrityError(
                "superseded_by_id must reference the matching next tenant version"
            )
    raise LedgerImmutableError(
        "confirmed ledger records are append-only; create a superseding version"
    )


@event.listens_for(LedgerRecordMixin, "before_delete", propagate=True)
def _guard_confirmed_ledger_delete(_mapper, _connection, _target) -> None:
    raise LedgerImmutableError(
        "confirmed ledger records are append-only and cannot be deleted"
    )
