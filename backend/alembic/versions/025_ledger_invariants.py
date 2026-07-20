"""Add append-only ledger invariants to P0 activity and result records.

Revision ID: 025
Revises: 024
Create Date: 2026-07-03
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _canonical(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        normalized = (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )
        return normalized.isoformat()
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return str(value)


def _hash(value) -> str:
    payload = json.dumps(
        _canonical(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _add_ledger_columns(table_name: str, *, add_unit: bool = False) -> None:
    existing_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }
    with op.batch_alter_table(table_name) as batch:
        if "tenant_id" not in existing_columns:
            batch.add_column(sa.Column("tenant_id", sa.Uuid(), nullable=True))
        if "derived_from" not in existing_columns:
            batch.add_column(
                sa.Column(
                    "derived_from",
                    sa.JSON(),
                    nullable=True,
                    server_default=sa.text("'[]'"),
                )
            )
        if "content_hash" not in existing_columns:
            batch.add_column(sa.Column("content_hash", sa.String(64), nullable=True))
        if "idempotency_key" not in existing_columns:
            batch.add_column(sa.Column("idempotency_key", sa.String(64), nullable=True))
        if "version" not in existing_columns:
            batch.add_column(
                sa.Column("version", sa.Integer(), nullable=True, server_default="1")
            )
        if "confirmed_by" not in existing_columns:
            batch.add_column(sa.Column("confirmed_by", sa.String(64), nullable=True))
        if "confirmed_at" not in existing_columns:
            batch.add_column(
                sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True)
            )
        if "supersedes_id" not in existing_columns:
            batch.add_column(sa.Column("supersedes_id", sa.Uuid(), nullable=True))
        if "superseded_by_id" not in existing_columns:
            batch.add_column(sa.Column("superseded_by_id", sa.Uuid(), nullable=True))
        if add_unit and "unit" not in existing_columns:
            batch.add_column(sa.Column("unit", sa.String(64), nullable=True))


def _backfill_activity_data(connection) -> None:
    rows = connection.execute(
        sa.text(
            """
            SELECT ad.id, ad.emission_source_id, ad.period_start, ad.period_end,
                   ad.quantity, ad.unit, ad.data_source, ad.document_id, ad.notes,
                   e.tenant_id
            FROM activity_data ad
            JOIN emission_sources es ON es.id = ad.emission_source_id
            JOIN sites s ON s.id = es.site_id
            JOIN enterprises e ON e.id = s.enterprise_id
            """
        )
    ).mappings()
    now = datetime.now(timezone.utc)
    for row in rows:
        if row["tenant_id"] is None:
            raise RuntimeError(
                f"activity_data {row['id']} has no tenant owner; repair before migration 025"
            )
        derived_from = (
            [f"document:{row['document_id']}"] if row["document_id"] else []
        )
        payload = {
            "record_type": "activity_data",
            "legacy_id": row["id"],
            "tenant_id": row["tenant_id"],
            "emission_source_id": row["emission_source_id"],
            "period_start": row["period_start"],
            "period_end": row["period_end"],
            "quantity": Decimal(str(row["quantity"])).quantize(
                Decimal("0.000000000001")
            ),
            "unit": row["unit"],
            "data_source": row["data_source"],
            "document_id": row["document_id"],
            "notes": row["notes"],
        }
        connection.execute(
            sa.text(
                """
                UPDATE activity_data
                SET tenant_id = :tenant_id,
                    derived_from = :derived_from,
                    content_hash = :content_hash,
                    idempotency_key = :idempotency_key,
                    version = 1,
                    confirmed_by = 'migration:025',
                    confirmed_at = :confirmed_at
                WHERE id = :id
                """
            ),
            {
                "tenant_id": row["tenant_id"],
                "derived_from": json.dumps(derived_from),
                "content_hash": _hash(payload),
                "idempotency_key": _hash(
                    [
                        row["tenant_id"],
                        row["emission_source_id"],
                        row["period_start"],
                        row["period_end"],
                        row["document_id"] or row["id"],
                    ]
                ),
                "confirmed_at": now,
                "id": row["id"],
            },
        )


def _backfill_documents(connection) -> None:
    rows = connection.execute(
        sa.text(
            """
            SELECT id, tenant_id, enterprise_id, filename, mime_type,
                   size_bytes, storage_path, doc_type
            FROM documents
            """
        )
    ).mappings()
    for row in rows:
        if row["tenant_id"] is None:
            raise RuntimeError(
                f"document {row['id']} has no tenant owner; repair before migration 025"
            )
        legacy_hash = _hash(
            {
                "legacy_id": row["id"],
                "enterprise_id": row["enterprise_id"],
                "filename": row["filename"],
                "mime_type": row["mime_type"],
                "size_bytes": row["size_bytes"],
                "storage_path": row["storage_path"],
                "doc_type": row["doc_type"],
            }
        )
        connection.execute(
            sa.text(
                "UPDATE documents SET content_hash = :content_hash WHERE id = :id"
            ),
            {"content_hash": legacy_hash, "id": row["id"]},
        )


def _backfill_emission_results(connection) -> None:
    rows = connection.execute(
        sa.text(
            """
            SELECT er.id, er.emission_source_id, er.period_start, er.period_end,
                   er.scope, er.co2_tonnes, er.factor_id, er.activity_data_id,
                   er.audit_trail, e.tenant_id
            FROM emission_results er
            JOIN emission_sources es ON es.id = er.emission_source_id
            JOIN sites s ON s.id = es.site_id
            JOIN enterprises e ON e.id = s.enterprise_id
            """
        )
    ).mappings()
    now = datetime.now(timezone.utc)
    for row in rows:
        if row["tenant_id"] is None:
            raise RuntimeError(
                f"emission_result {row['id']} has no tenant owner; repair before migration 025"
            )
        derived_from = []
        if row["activity_data_id"]:
            derived_from.append(f"activity_data:{row['activity_data_id']}")
        if row["factor_id"]:
            derived_from.append(f"emission_factor:{row['factor_id']}")
        value = Decimal(str(row["co2_tonnes"])).quantize(
            Decimal("0.000000000001")
        )
        payload = {
            "record_type": "emission_result",
            "legacy_id": row["id"],
            "tenant_id": row["tenant_id"],
            "emission_source_id": row["emission_source_id"],
            "period_start": row["period_start"],
            "period_end": row["period_end"],
            "scope": row["scope"],
            "value": value,
            "unit": "tCO2",
            "factor_id": row["factor_id"],
            "activity_data_id": row["activity_data_id"],
            "audit_trail": row["audit_trail"],
        }
        connection.execute(
            sa.text(
                """
                UPDATE emission_results
                SET tenant_id = :tenant_id,
                    derived_from = :derived_from,
                    content_hash = :content_hash,
                    idempotency_key = :idempotency_key,
                    version = 1,
                    confirmed_by = 'migration:025',
                    confirmed_at = :confirmed_at,
                    unit = 'tCO2'
                WHERE id = :id
                """
            ),
            {
                "tenant_id": row["tenant_id"],
                "derived_from": json.dumps(derived_from),
                "content_hash": _hash(payload),
                "idempotency_key": _hash(
                    [
                        row["tenant_id"],
                        row["activity_data_id"] or row["emission_source_id"],
                        row["factor_id"],
                        "legacy:025",
                    ]
                ),
                "confirmed_at": now,
                "id": row["id"],
            },
        )


def _finalize_ledger_table(table_name: str) -> None:
    inspector = sa.inspect(op.get_bind())
    existing_indexes = {
        index["name"] for index in inspector.get_indexes(table_name)
    }
    tenant_fk_exists = any(
        foreign_key.get("referred_table") == "tenants"
        and foreign_key.get("constrained_columns") == ["tenant_id"]
        for foreign_key in inspector.get_foreign_keys(table_name)
    )
    with op.batch_alter_table(table_name) as batch:
        batch.alter_column("tenant_id", existing_type=sa.Uuid(), nullable=False)
        batch.alter_column("derived_from", existing_type=sa.JSON(), nullable=False)
        batch.alter_column(
            "content_hash", existing_type=sa.String(64), nullable=False
        )
        batch.alter_column(
            "idempotency_key", existing_type=sa.String(64), nullable=False
        )
        batch.alter_column("version", existing_type=sa.Integer(), nullable=False)
        batch.alter_column(
            "confirmed_by", existing_type=sa.String(64), nullable=False
        )
        batch.alter_column(
            "confirmed_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )
        if not tenant_fk_exists:
            batch.create_foreign_key(
                f"fk_{table_name}_tenant",
                "tenants",
                ["tenant_id"],
                ["id"],
            )
        batch.create_unique_constraint(
            f"uq_{table_name}_id_tenant",
            ["id", "tenant_id"],
        )
        batch.create_foreign_key(
            f"fk_{table_name}_supersedes_tenant",
            table_name,
            ["supersedes_id", "tenant_id"],
            ["id", "tenant_id"],
            deferrable=True,
            initially="DEFERRED",
        )
        batch.create_foreign_key(
            f"fk_{table_name}_superseded_by_tenant",
            table_name,
            ["superseded_by_id", "tenant_id"],
            ["id", "tenant_id"],
            deferrable=True,
            initially="DEFERRED",
        )
        batch.create_unique_constraint(
            f"uq_{table_name}_tenant_idempotency_version",
            ["tenant_id", "idempotency_key", "version"],
        )
        batch.create_unique_constraint(
            f"uq_{table_name}_supersedes",
            ["supersedes_id"],
        )
        batch.create_unique_constraint(
            f"uq_{table_name}_superseded_by",
            ["superseded_by_id"],
        )
        batch.create_check_constraint(
            f"ck_{table_name}_positive_version",
            "version >= 1",
        )
        batch.create_check_constraint(
            f"ck_{table_name}_not_self_supersedes",
            "supersedes_id IS NULL OR supersedes_id <> id",
        )
        batch.create_check_constraint(
            f"ck_{table_name}_not_self_superseded_by",
            "superseded_by_id IS NULL OR superseded_by_id <> id",
        )
        if f"ix_{table_name}_tenant_id" not in existing_indexes:
            batch.create_index(f"ix_{table_name}_tenant_id", ["tenant_id"])
        batch.create_index(f"ix_{table_name}_content_hash", ["content_hash"])


def _create_postgres_append_only_trigger(table_name: str) -> None:
    function_name = f"zcy_guard_{table_name}_append_only"
    trigger_name = f"trg_{table_name}_append_only"
    insert_function_name = f"zcy_guard_{table_name}_supersession_insert"
    insert_trigger_name = f"trg_{table_name}_supersession_insert"
    link_function_name = f"zcy_link_{table_name}_supersession"
    link_trigger_name = f"trg_{table_name}_supersession_link"
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {function_name}() RETURNS trigger AS $$
            BEGIN
                IF (to_jsonb(NEW) - 'superseded_by_id' - 'updated_at')
                   IS DISTINCT FROM
                   (to_jsonb(OLD) - 'superseded_by_id' - 'updated_at') THEN
                    RAISE EXCEPTION 'confirmed ledger records are append-only';
                END IF;
                IF OLD.superseded_by_id IS NOT NULL
                   OR NEW.superseded_by_id IS NULL THEN
                    RAISE EXCEPTION 'supersession pointer is one-way';
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM {table_name} successor
                    WHERE successor.id = NEW.superseded_by_id
                      AND successor.tenant_id = OLD.tenant_id
                      AND successor.supersedes_id = OLD.id
                      AND successor.version = OLD.version + 1
                ) THEN
                    RAISE EXCEPTION 'supersession link must be tenant-local and bidirectional';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            CREATE TRIGGER {trigger_name}
            BEFORE UPDATE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION {function_name}();

            CREATE FUNCTION {insert_function_name}() RETURNS trigger AS $$
            DECLARE
                parent_tenant UUID;
                parent_version INTEGER;
                parent_successor UUID;
            BEGIN
                IF NEW.superseded_by_id IS NOT NULL THEN
                    RAISE EXCEPTION 'new ledger versions cannot declare superseded_by_id';
                END IF;
                IF NEW.supersedes_id IS NULL THEN
                    IF NEW.version <> 1 THEN
                        RAISE EXCEPTION 'root ledger records must start at version 1';
                    END IF;
                    RETURN NEW;
                END IF;
                SELECT tenant_id, version, superseded_by_id
                INTO parent_tenant, parent_version, parent_successor
                FROM {table_name}
                WHERE id = NEW.supersedes_id;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'superseded ledger record does not exist';
                END IF;
                IF parent_tenant <> NEW.tenant_id THEN
                    RAISE EXCEPTION 'supersession cannot cross tenant boundaries';
                END IF;
                IF parent_successor IS NOT NULL THEN
                    RAISE EXCEPTION 'ledger record is already superseded';
                END IF;
                IF NEW.version <> parent_version + 1 THEN
                    RAISE EXCEPTION 'supersession version must be contiguous';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            CREATE TRIGGER {insert_trigger_name}
            BEFORE INSERT ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION {insert_function_name}();

            CREATE FUNCTION {link_function_name}() RETURNS trigger AS $$
            BEGIN
                IF NEW.supersedes_id IS NOT NULL THEN
                    UPDATE {table_name}
                    SET superseded_by_id = NEW.id
                    WHERE id = NEW.supersedes_id
                      AND tenant_id = NEW.tenant_id
                      AND superseded_by_id IS NULL;
                    IF NOT FOUND THEN
                        RAISE EXCEPTION 'failed to complete reverse supersession link';
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            CREATE TRIGGER {link_trigger_name}
            AFTER INSERT ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION {link_function_name}();
            """
        )
    )


def _create_sqlite_append_only_trigger(
    table_name: str,
    immutable_columns: tuple[str, ...],
) -> None:
    trigger_name = f"trg_{table_name}_append_only"
    immutable_change = "\n                OR ".join(
        f"NEW.{column} IS NOT OLD.{column}" for column in immutable_columns
    )
    statements = (
        f"""
            CREATE TRIGGER trg_{table_name}_supersession_insert
            BEFORE INSERT ON {table_name}
            FOR EACH ROW
            BEGIN
                SELECT CASE
                    WHEN NEW.superseded_by_id IS NOT NULL
                    THEN RAISE(ABORT, 'new ledger versions cannot declare superseded_by_id')
                    WHEN NEW.supersedes_id IS NULL AND NEW.version <> 1
                    THEN RAISE(ABORT, 'root ledger records must start at version 1')
                    WHEN NEW.supersedes_id IS NOT NULL AND NOT EXISTS (
                        SELECT 1 FROM {table_name} parent
                        WHERE parent.id = NEW.supersedes_id
                    )
                    THEN RAISE(ABORT, 'superseded ledger record does not exist')
                    WHEN NEW.supersedes_id IS NOT NULL AND NOT EXISTS (
                        SELECT 1 FROM {table_name} parent
                        WHERE parent.id = NEW.supersedes_id
                          AND parent.tenant_id = NEW.tenant_id
                    )
                    THEN RAISE(ABORT, 'supersession cannot cross tenant boundaries')
                    WHEN NEW.supersedes_id IS NOT NULL AND EXISTS (
                        SELECT 1 FROM {table_name} parent
                        WHERE parent.id = NEW.supersedes_id
                          AND parent.superseded_by_id IS NOT NULL
                    )
                    THEN RAISE(ABORT, 'ledger record is already superseded')
                    WHEN NEW.supersedes_id IS NOT NULL AND NOT EXISTS (
                        SELECT 1 FROM {table_name} parent
                        WHERE parent.id = NEW.supersedes_id
                          AND NEW.version = parent.version + 1
                    )
                    THEN RAISE(ABORT, 'supersession version must be contiguous')
                END;
            END;
        """,
        f"""
            CREATE TRIGGER {trigger_name}
            BEFORE UPDATE ON {table_name}
            FOR EACH ROW
            WHEN {immutable_change}
                 OR OLD.superseded_by_id IS NOT NULL
                 OR NEW.superseded_by_id IS NULL
                 OR NOT EXISTS (
                    SELECT 1 FROM {table_name} successor
                    WHERE successor.id = NEW.superseded_by_id
                      AND successor.tenant_id = OLD.tenant_id
                      AND successor.supersedes_id = OLD.id
                      AND successor.version = OLD.version + 1
                 )
            BEGIN
                SELECT RAISE(ABORT, 'confirmed ledger records are append-only');
            END;
        """,
        f"""
            CREATE TRIGGER trg_{table_name}_supersession_link
            AFTER INSERT ON {table_name}
            FOR EACH ROW
            WHEN NEW.supersedes_id IS NOT NULL
            BEGIN
                UPDATE {table_name}
                SET superseded_by_id = NEW.id
                WHERE id = NEW.supersedes_id
                  AND tenant_id = NEW.tenant_id
                  AND superseded_by_id IS NULL;
            END;
        """,
    )
    for statement in statements:
        op.execute(sa.text(statement))


def upgrade() -> None:
    connection = op.get_bind()
    formal_decimal_type = (
        sa.String(31)
        if connection.dialect.name == "sqlite"
        else sa.Numeric(28, 12)
    )
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("content_hash", sa.String(64), nullable=True))
    _backfill_documents(connection)
    with op.batch_alter_table("documents") as batch:
        batch.alter_column(
            "tenant_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )
        batch.alter_column(
            "content_hash",
            existing_type=sa.String(64),
            nullable=False,
        )
        batch.create_unique_constraint(
            "uq_documents_tenant_content_hash",
            ["tenant_id", "content_hash"],
        )
        batch.create_index("ix_documents_content_hash", ["content_hash"])

    _add_ledger_columns("activity_data")
    _add_ledger_columns("emission_results", add_unit=True)
    _backfill_activity_data(connection)
    _backfill_emission_results(connection)

    with op.batch_alter_table("activity_data") as batch:
        batch.alter_column(
            "quantity",
            existing_type=sa.Float(),
            type_=formal_decimal_type,
            existing_nullable=False,
        )
        batch.alter_column(
            "unit",
            existing_type=sa.String(20),
            type_=sa.String(64),
            existing_nullable=False,
        )
    with op.batch_alter_table("emission_results") as batch:
        batch.alter_column(
            "co2_tonnes",
            existing_type=sa.Float(),
            type_=formal_decimal_type,
            existing_nullable=False,
        )
        batch.alter_column("unit", existing_type=sa.String(64), nullable=False)

    _finalize_ledger_table("activity_data")
    _finalize_ledger_table("emission_results")

    if connection.dialect.name == "postgresql":
        _create_postgres_append_only_trigger("activity_data")
        _create_postgres_append_only_trigger("emission_results")
    elif connection.dialect.name == "sqlite":
        _create_sqlite_append_only_trigger(
            "activity_data",
            (
                "id",
                "emission_source_id",
                "period_start",
                "period_end",
                "quantity",
                "unit",
                "data_source",
                "document_id",
                "notes",
                "tenant_id",
                "derived_from",
                "content_hash",
                "idempotency_key",
                "version",
                "confirmed_by",
                "confirmed_at",
                "supersedes_id",
            ),
        )
        _create_sqlite_append_only_trigger(
            "emission_results",
            (
                "id",
                "emission_source_id",
                "period_start",
                "period_end",
                "scope",
                "co2_tonnes",
                "unit",
                "uncertainty_pct",
                "confidence_95_low",
                "confidence_95_high",
                "factor_id",
                "activity_data_id",
                "audit_trail",
                "created_at",
                "tenant_id",
                "derived_from",
                "content_hash",
                "idempotency_key",
                "version",
                "confirmed_by",
                "confirmed_at",
                "supersedes_id",
            ),
        )


def downgrade() -> None:
    connection = op.get_bind()
    formal_decimal_type = (
        sa.String(31)
        if connection.dialect.name == "sqlite"
        else sa.Numeric(28, 12)
    )
    if connection.dialect.name == "postgresql":
        for table_name in ("emission_results", "activity_data"):
            op.execute(
                sa.text(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name}")
            )
            op.execute(
                sa.text(
                    f"DROP TRIGGER IF EXISTS trg_{table_name}_supersession_link "
                    f"ON {table_name}"
                )
            )
            op.execute(
                sa.text(
                    f"DROP TRIGGER IF EXISTS trg_{table_name}_supersession_insert "
                    f"ON {table_name}"
                )
            )
            op.execute(
                sa.text(
                    f"DROP FUNCTION IF EXISTS zcy_guard_{table_name}_append_only()"
                )
            )
            op.execute(
                sa.text(
                    f"DROP FUNCTION IF EXISTS zcy_link_{table_name}_supersession()"
                )
            )
            op.execute(
                sa.text(
                    f"DROP FUNCTION IF EXISTS "
                    f"zcy_guard_{table_name}_supersession_insert()"
                )
            )
    elif connection.dialect.name == "sqlite":
        for table_name in ("emission_results", "activity_data"):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only"))
            op.execute(
                sa.text(
                    f"DROP TRIGGER IF EXISTS trg_{table_name}_supersession_link"
                )
            )
            op.execute(
                sa.text(
                    f"DROP TRIGGER IF EXISTS trg_{table_name}_supersession_insert"
                )
            )

    for table_name in ("emission_results", "activity_data"):
        with op.batch_alter_table(table_name) as batch:
            batch.drop_index(f"ix_{table_name}_content_hash")
            batch.drop_index(f"ix_{table_name}_tenant_id")
            batch.drop_constraint(
                f"ck_{table_name}_not_self_superseded_by",
                type_="check",
            )
            batch.drop_constraint(
                f"ck_{table_name}_not_self_supersedes",
                type_="check",
            )
            batch.drop_constraint(
                f"ck_{table_name}_positive_version",
                type_="check",
            )
            batch.drop_constraint(
                f"uq_{table_name}_superseded_by",
                type_="unique",
            )
            batch.drop_constraint(
                f"uq_{table_name}_supersedes",
                type_="unique",
            )
            batch.drop_constraint(
                f"uq_{table_name}_tenant_idempotency_version",
                type_="unique",
            )
            batch.drop_constraint(
                f"uq_{table_name}_id_tenant",
                type_="unique",
            )
            batch.drop_constraint(
                f"fk_{table_name}_superseded_by_tenant",
                type_="foreignkey",
            )
            batch.drop_constraint(
                f"fk_{table_name}_supersedes_tenant",
                type_="foreignkey",
            )
            batch.drop_constraint(
                f"fk_{table_name}_tenant",
                type_="foreignkey",
            )

    with op.batch_alter_table("emission_results") as batch:
        batch.alter_column(
            "co2_tonnes",
            existing_type=formal_decimal_type,
            type_=sa.Float(),
            existing_nullable=False,
        )
        batch.drop_column("unit")
    with op.batch_alter_table("activity_data") as batch:
        batch.alter_column(
            "quantity",
            existing_type=formal_decimal_type,
            type_=sa.Float(),
            existing_nullable=False,
        )
        batch.alter_column(
            "unit",
            existing_type=sa.String(64),
            type_=sa.String(20),
            existing_nullable=False,
        )

    for table_name in ("emission_results", "activity_data"):
        with op.batch_alter_table(table_name) as batch:
            for column_name in (
                "superseded_by_id",
                "supersedes_id",
                "confirmed_at",
                "confirmed_by",
                "version",
                "idempotency_key",
                "content_hash",
                "derived_from",
                "tenant_id",
            ):
                batch.drop_column(column_name)

    with op.batch_alter_table("documents") as batch:
        batch.drop_index("ix_documents_content_hash")
        batch.drop_constraint(
            "uq_documents_tenant_content_hash",
            type_="unique",
        )
        batch.alter_column(
            "tenant_id",
            existing_type=sa.Uuid(),
            nullable=True,
        )
        batch.drop_column("content_hash")
