"""Add formal CBAM installation, process, attribution, and SEE ledger tables.

Revision ID: 026
Revises: 025
Create Date: 2026-07-04
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_PREFIXES = {
    "cbam_installations": "cbam_inst",
    "cbam_production_processes": "cbam_proc",
    "cbam_products": "cbam_prod",
    "cbam_production_outputs": "cbam_out",
    "cbam_source_stream_attributions": "cbam_attr",
    "cbam_precursor_consumptions": "cbam_prec",
    "cbam_see_results": "cbam_see",
    "cbam_carbon_price_paid_evidence": "cbam_price",
}


def _decimal_type(precision: int = 28, scale: int = 12):
    return (
        sa.String(precision + 3)
        if op.get_bind().dialect.name == "sqlite"
        else sa.Numeric(precision, scale)
    )


def _ledger_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "derived_from",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("confirmed_by", sa.String(64), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supersedes_id", sa.Uuid(), nullable=True),
        sa.Column("superseded_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    ]


def _ledger_constraints(table_name: str) -> list[sa.Constraint]:
    prefix = TABLE_PREFIXES[table_name]
    return [
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            name=f"uq_{prefix}_id_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id", "tenant_id"],
            [f"{table_name}.id", f"{table_name}.tenant_id"],
            name=f"fk_{prefix}_supersedes_tenant",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_id", "tenant_id"],
            [f"{table_name}.id", f"{table_name}.tenant_id"],
            name=f"fk_{prefix}_superseded_by_tenant",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            "version",
            name=f"uq_{prefix}_idempotency_version",
        ),
        sa.UniqueConstraint(
            "supersedes_id",
            name=f"uq_{prefix}_supersedes",
        ),
        sa.UniqueConstraint(
            "superseded_by_id",
            name=f"uq_{prefix}_superseded_by",
        ),
        sa.CheckConstraint("version >= 1", name=f"ck_{prefix}_version"),
        sa.CheckConstraint(
            "supersedes_id IS NULL OR supersedes_id <> id",
            name=f"ck_{prefix}_not_self_supersedes",
        ),
        sa.CheckConstraint(
            "superseded_by_id IS NULL OR superseded_by_id <> id",
            name=f"ck_{prefix}_not_self_superseded",
        ),
    ]


def _create_ledger_table(
    table_name: str,
    *business_columns: sa.Column,
    extra_constraints: Sequence[sa.Constraint] = (),
) -> None:
    op.create_table(
        table_name,
        *_ledger_columns(),
        *business_columns,
        *_ledger_constraints(table_name),
        *extra_constraints,
    )
    op.create_index(f"ix_{TABLE_PREFIXES[table_name]}_tenant", table_name, ["tenant_id"])
    op.create_index(
        f"ix_{TABLE_PREFIXES[table_name]}_content_hash",
        table_name,
        ["content_hash"],
    )


def _create_postgres_triggers(table_name: str) -> None:
    prefix = TABLE_PREFIXES[table_name]
    lineage_checks = _postgres_lineage_checks(table_name)
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION zcy_{prefix}_guard_update() RETURNS trigger AS $$
            BEGIN
                IF (to_jsonb(NEW) - 'superseded_by_id' - 'updated_at')
                   IS DISTINCT FROM
                   (to_jsonb(OLD) - 'superseded_by_id' - 'updated_at') THEN
                    RAISE EXCEPTION 'confirmed ledger records are append-only';
                END IF;
                IF OLD.superseded_by_id IS NOT NULL
                   OR NEW.superseded_by_id IS NULL
                   OR NOT EXISTS (
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
            CREATE TRIGGER trg_{prefix}_guard_update
            BEFORE UPDATE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION zcy_{prefix}_guard_update();

            CREATE FUNCTION zcy_{prefix}_guard_delete() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION
                    'confirmed ledger records are append-only and cannot be deleted';
            END;
            $$ LANGUAGE plpgsql;
            CREATE TRIGGER trg_{prefix}_guard_delete
            BEFORE DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION zcy_{prefix}_guard_delete();

            CREATE FUNCTION zcy_{prefix}_guard_insert() RETURNS trigger AS $$
            DECLARE
                parent_tenant UUID;
                parent_version INTEGER;
                parent_successor UUID;
            BEGIN
                {lineage_checks}
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
            CREATE TRIGGER trg_{prefix}_guard_insert
            BEFORE INSERT ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION zcy_{prefix}_guard_insert();

            CREATE FUNCTION zcy_{prefix}_link_insert() RETURNS trigger AS $$
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
            CREATE TRIGGER trg_{prefix}_link_insert
            AFTER INSERT ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION zcy_{prefix}_link_insert();
            """
        )
    )


def _create_sqlite_triggers(table_name: str) -> None:
    prefix = TABLE_PREFIXES[table_name]
    immutable_columns = [
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
        if column["name"] not in {"superseded_by_id", "updated_at"}
    ]
    immutable_change = "\n                OR ".join(
        f"NEW.{column} IS NOT OLD.{column}" for column in immutable_columns
    )
    lineage_cases = _sqlite_lineage_cases(table_name)
    statements = (
        f"""
        CREATE TRIGGER trg_{prefix}_guard_insert
        BEFORE INSERT ON {table_name}
        FOR EACH ROW
        BEGIN
            SELECT CASE
                {lineage_cases}
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
        CREATE TRIGGER trg_{prefix}_guard_update
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
        CREATE TRIGGER trg_{prefix}_link_insert
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
        f"""
        CREATE TRIGGER trg_{prefix}_guard_delete
        BEFORE DELETE ON {table_name}
        FOR EACH ROW
        BEGIN
            SELECT RAISE(
                ABORT,
                'confirmed ledger records are append-only and cannot be deleted'
            );
        END;
        """,
    )
    for statement in statements:
        op.execute(sa.text(statement))


def _create_postgres_attribution_total_trigger() -> None:
    op.execute(
        sa.text(
            """
            CREATE FUNCTION zcy_cbam_attr_total_check() RETURNS trigger AS $$
            DECLARE
                target_tenant UUID;
                target_source TEXT;
                target_start TIMESTAMPTZ;
                target_end TIMESTAMPTZ;
                total_share NUMERIC;
            BEGIN
                target_tenant := COALESCE(NEW.tenant_id, OLD.tenant_id);
                target_source := COALESCE(NEW.source_ref, OLD.source_ref);
                target_start := COALESCE(NEW.period_start, OLD.period_start);
                target_end := COALESCE(NEW.period_end, OLD.period_end);
                SELECT COALESCE(SUM(share), 0)
                INTO total_share
                FROM cbam_source_stream_attributions
                WHERE tenant_id = target_tenant
                  AND source_ref = target_source
                  AND period_start = target_start
                  AND period_end = target_end
                  AND superseded_by_id IS NULL;
                IF total_share <> 1 THEN
                    RAISE EXCEPTION
                        'formal attribution shares must total exactly 1.00; received %',
                        total_share;
                END IF;
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
            CREATE CONSTRAINT TRIGGER trg_cbam_attr_total_check
            AFTER INSERT OR UPDATE OR DELETE
            ON cbam_source_stream_attributions
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION zcy_cbam_attr_total_check();
            """
        )
    )


def _postgres_lineage_checks(table_name: str) -> str:
    checks = {
        "cbam_installations": """
            IF NOT EXISTS (
                SELECT 1 FROM enterprises parent
                WHERE parent.id = NEW.enterprise_id
                  AND parent.tenant_id = NEW.tenant_id
            ) THEN RAISE EXCEPTION 'tenant lineage violation'; END IF;
        """,
        "cbam_production_processes": """
            IF NOT EXISTS (
                SELECT 1 FROM cbam_installations parent
                WHERE parent.id = NEW.installation_id
                  AND parent.tenant_id = NEW.tenant_id
            ) THEN RAISE EXCEPTION 'tenant lineage violation'; END IF;
        """,
        "cbam_products": """
            IF NOT EXISTS (
                SELECT 1 FROM cbam_production_processes parent
                WHERE parent.id = NEW.process_id
                  AND parent.tenant_id = NEW.tenant_id
            ) THEN RAISE EXCEPTION 'tenant lineage violation'; END IF;
        """,
        "cbam_production_outputs": """
            IF NOT EXISTS (
                SELECT 1 FROM cbam_production_processes parent
                WHERE parent.id = NEW.process_id
                  AND parent.tenant_id = NEW.tenant_id
            ) OR NOT EXISTS (
                SELECT 1 FROM cbam_products parent
                WHERE parent.id = NEW.product_id
                  AND parent.tenant_id = NEW.tenant_id
            ) THEN RAISE EXCEPTION 'tenant lineage violation'; END IF;
        """,
        "cbam_source_stream_attributions": """
            IF NOT EXISTS (
                SELECT 1 FROM cbam_production_processes parent
                WHERE parent.id = NEW.process_id
                  AND parent.tenant_id = NEW.tenant_id
            ) OR split_part(NEW.source_ref, ':', 1) <> 'emission_result'
              OR NOT EXISTS (
                SELECT 1 FROM emission_results parent
                WHERE parent.id = split_part(NEW.source_ref, ':', 2)::uuid
                  AND parent.tenant_id = NEW.tenant_id
            ) THEN RAISE EXCEPTION 'tenant lineage violation'; END IF;
        """,
        "cbam_precursor_consumptions": """
            IF NOT EXISTS (
                SELECT 1 FROM cbam_production_processes parent
                WHERE parent.id = NEW.process_id
                  AND parent.tenant_id = NEW.tenant_id
            ) OR NOT EXISTS (
                SELECT 1 FROM cbam_products parent
                WHERE parent.id = NEW.product_id
                  AND parent.tenant_id = NEW.tenant_id
            ) OR (
                NEW.source_kind = 'self_produced_see'
                AND (
                    split_part(NEW.source_see_ref, ':', 1) <> 'see_result'
                    OR NOT EXISTS (
                        SELECT 1 FROM cbam_see_results parent
                        WHERE parent.id =
                              split_part(NEW.source_see_ref, ':', 2)::uuid
                          AND parent.tenant_id = NEW.tenant_id
                    )
                )
            ) THEN RAISE EXCEPTION 'tenant lineage violation'; END IF;
        """,
        "cbam_see_results": """
            IF NOT EXISTS (
                SELECT 1 FROM cbam_production_processes parent
                WHERE parent.id = NEW.process_id
                  AND parent.tenant_id = NEW.tenant_id
            ) OR NOT EXISTS (
                SELECT 1 FROM cbam_products parent
                WHERE parent.id = NEW.product_id
                  AND parent.tenant_id = NEW.tenant_id
            ) OR NOT EXISTS (
                SELECT 1 FROM cbam_production_outputs parent
                WHERE parent.id = NEW.production_output_id
                  AND parent.tenant_id = NEW.tenant_id
            ) OR NOT EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(NEW.derived_from::jsonb) ref(value)
                WHERE ref.value =
                      'production_output:' || NEW.production_output_id::text
            ) OR NOT EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(NEW.derived_from::jsonb) ref(value)
                WHERE ref.value = NEW.methodology_ref
            ) OR NOT EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(NEW.derived_from::jsonb) ref(value)
                JOIN cbam_source_stream_attributions attribution
                  ON attribution.id =
                     split_part(ref.value, ':', 2)::uuid
                 AND attribution.tenant_id = NEW.tenant_id
                 AND attribution.process_id = NEW.process_id
                 AND attribution.period_start = NEW.period_start
                 AND attribution.period_end = NEW.period_end
                WHERE ref.value LIKE 'attribution:%'
            ) THEN RAISE EXCEPTION 'tenant lineage or formal provenance violation'; END IF;
        """,
        "cbam_carbon_price_paid_evidence": """
            IF NOT EXISTS (
                SELECT 1 FROM cbam_installations parent
                WHERE parent.id = NEW.installation_id
                  AND parent.tenant_id = NEW.tenant_id
            ) OR (
                NEW.document_id IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM documents parent
                    WHERE parent.id = NEW.document_id
                      AND parent.tenant_id = NEW.tenant_id
                )
            ) THEN RAISE EXCEPTION 'tenant lineage violation'; END IF;
        """,
    }
    return checks[table_name]


def _sqlite_lineage_cases(table_name: str) -> str:
    checks = {
        "cbam_installations": """
            WHEN NOT EXISTS (
                SELECT 1 FROM enterprises parent
                WHERE parent.id = NEW.enterprise_id
                  AND parent.tenant_id = NEW.tenant_id
            ) THEN RAISE(ABORT, 'tenant lineage violation')
        """,
        "cbam_production_processes": """
            WHEN NOT EXISTS (
                SELECT 1 FROM cbam_installations parent
                WHERE parent.id = NEW.installation_id
                  AND parent.tenant_id = NEW.tenant_id
            ) THEN RAISE(ABORT, 'tenant lineage violation')
        """,
        "cbam_products": """
            WHEN NOT EXISTS (
                SELECT 1 FROM cbam_production_processes parent
                WHERE parent.id = NEW.process_id
                  AND parent.tenant_id = NEW.tenant_id
            ) THEN RAISE(ABORT, 'tenant lineage violation')
        """,
        "cbam_production_outputs": """
            WHEN NOT EXISTS (
                SELECT 1 FROM cbam_production_processes parent
                WHERE parent.id = NEW.process_id
                  AND parent.tenant_id = NEW.tenant_id
            ) OR NOT EXISTS (
                SELECT 1 FROM cbam_products parent
                WHERE parent.id = NEW.product_id
                  AND parent.tenant_id = NEW.tenant_id
            ) THEN RAISE(ABORT, 'tenant lineage violation')
        """,
        "cbam_source_stream_attributions": """
            WHEN NOT EXISTS (
                SELECT 1 FROM cbam_production_processes parent
                WHERE parent.id = NEW.process_id
                  AND parent.tenant_id = NEW.tenant_id
            ) OR NEW.source_ref NOT LIKE 'emission_result:%'
              OR NOT EXISTS (
                SELECT 1 FROM emission_results parent
                WHERE parent.id =
                      replace(substr(NEW.source_ref, 17), '-', '')
                  AND parent.tenant_id = NEW.tenant_id
            ) THEN RAISE(ABORT, 'tenant lineage violation')
        """,
        "cbam_precursor_consumptions": """
            WHEN NOT EXISTS (
                SELECT 1 FROM cbam_production_processes parent
                WHERE parent.id = NEW.process_id
                  AND parent.tenant_id = NEW.tenant_id
            ) OR NOT EXISTS (
                SELECT 1 FROM cbam_products parent
                WHERE parent.id = NEW.product_id
                  AND parent.tenant_id = NEW.tenant_id
            ) OR (
                NEW.source_kind = 'self_produced_see'
                AND (
                    NEW.source_see_ref NOT LIKE 'see_result:%'
                    OR NOT EXISTS (
                        SELECT 1 FROM cbam_see_results parent
                        WHERE parent.id =
                              replace(substr(NEW.source_see_ref, 12), '-', '')
                          AND parent.tenant_id = NEW.tenant_id
                    )
                )
            ) THEN RAISE(ABORT, 'tenant lineage violation')
        """,
        "cbam_see_results": """
            WHEN NOT EXISTS (
                SELECT 1 FROM cbam_production_processes parent
                WHERE parent.id = NEW.process_id
                  AND parent.tenant_id = NEW.tenant_id
            ) OR NOT EXISTS (
                SELECT 1 FROM cbam_products parent
                WHERE parent.id = NEW.product_id
                  AND parent.tenant_id = NEW.tenant_id
            ) OR NOT EXISTS (
                SELECT 1 FROM cbam_production_outputs parent
                WHERE parent.id = NEW.production_output_id
                  AND parent.tenant_id = NEW.tenant_id
            ) OR NOT EXISTS (
                SELECT 1 FROM json_each(NEW.derived_from) ref
                WHERE ref.value =
                      'production_output:' || replace(NEW.production_output_id, '-', '')
                   OR ref.value =
                      'production_output:' || NEW.production_output_id
            ) OR NOT EXISTS (
                SELECT 1 FROM json_each(NEW.derived_from) ref
                WHERE ref.value = NEW.methodology_ref
            ) OR NOT EXISTS (
                SELECT 1 FROM json_each(NEW.derived_from) ref
                JOIN cbam_source_stream_attributions attribution
                  ON attribution.id =
                     replace(substr(ref.value, 13), '-', '')
                 AND attribution.tenant_id = NEW.tenant_id
                 AND attribution.process_id = NEW.process_id
                 AND attribution.period_start = NEW.period_start
                 AND attribution.period_end = NEW.period_end
                WHERE ref.value LIKE 'attribution:%'
            ) THEN RAISE(ABORT, 'tenant lineage or formal provenance violation')
        """,
        "cbam_carbon_price_paid_evidence": """
            WHEN NOT EXISTS (
                SELECT 1 FROM cbam_installations parent
                WHERE parent.id = NEW.installation_id
                  AND parent.tenant_id = NEW.tenant_id
            ) OR (
                NEW.document_id IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM documents parent
                    WHERE parent.id = NEW.document_id
                      AND parent.tenant_id = NEW.tenant_id
                )
            ) THEN RAISE(ABORT, 'tenant lineage violation')
        """,
    }
    return checks[table_name]


def upgrade() -> None:
    decimal_type = _decimal_type()
    share_type = _decimal_type(18, 12)
    _create_ledger_table(
        "cbam_installations",
        sa.Column(
            "enterprise_id",
            sa.Uuid(),
            sa.ForeignKey("enterprises.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("operator_name", sa.String(255), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("unlocode", sa.String(5), nullable=True),
    )
    _create_ledger_table(
        "cbam_production_processes",
        sa.Column(
            "installation_id",
            sa.Uuid(),
            sa.ForeignKey("cbam_installations.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("aggregate_goods_category", sa.String(64), nullable=False),
        sa.Column("production_route", sa.String(32), nullable=False),
    )
    _create_ledger_table(
        "cbam_products",
        sa.Column(
            "process_id",
            sa.Uuid(),
            sa.ForeignKey("cbam_production_processes.id"),
            nullable=False,
        ),
        sa.Column("cn_code", sa.String(8), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        extra_constraints=(
            sa.CheckConstraint(
                "length(cn_code) = 8",
                name="ck_cbam_prod_cn_code_length",
            ),
        ),
    )
    _create_ledger_table(
        "cbam_production_outputs",
        sa.Column(
            "process_id",
            sa.Uuid(),
            sa.ForeignKey("cbam_production_processes.id"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("cbam_products.id"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quantity", decimal_type, nullable=False),
        sa.Column("unit", sa.String(64), nullable=False),
        extra_constraints=(
            sa.CheckConstraint(
                "CAST(quantity AS NUMERIC) > 0",
                name="ck_cbam_out_positive_quantity",
            ),
            sa.CheckConstraint(
                "unit = 't'",
                name="ck_cbam_out_canonical_unit",
            ),
            sa.CheckConstraint(
                "period_start < period_end",
                name="ck_cbam_out_valid_period",
            ),
        ),
    )
    _create_ledger_table(
        "cbam_source_stream_attributions",
        sa.Column(
            "process_id",
            sa.Uuid(),
            sa.ForeignKey("cbam_production_processes.id"),
            nullable=False,
        ),
        sa.Column("source_ref", sa.String(128), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("share", share_type, nullable=False),
        sa.Column("method", sa.String(64), nullable=False),
        extra_constraints=(
            sa.CheckConstraint(
                "CAST(share AS NUMERIC) > 0 AND CAST(share AS NUMERIC) <= 1",
                name="ck_cbam_attr_share_range",
            ),
            sa.CheckConstraint(
                "period_start < period_end",
                name="ck_cbam_attr_valid_period",
            ),
        ),
    )
    _create_ledger_table(
        "cbam_precursor_consumptions",
        sa.Column(
            "process_id",
            sa.Uuid(),
            sa.ForeignKey("cbam_production_processes.id"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("cbam_products.id"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("precursor_name", sa.String(255), nullable=False),
        sa.Column("quantity", decimal_type, nullable=False),
        sa.Column("unit", sa.String(64), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("source_see_ref", sa.String(128), nullable=False),
        sa.Column("specific_emissions", decimal_type, nullable=False),
        sa.Column("specific_unit", sa.String(64), nullable=False),
        sa.Column("data_quality", sa.String(32), nullable=False),
        extra_constraints=(
            sa.CheckConstraint(
                "CAST(quantity AS NUMERIC) > 0",
                name="ck_cbam_prec_positive_quantity",
            ),
            sa.CheckConstraint(
                "unit = 't'",
                name="ck_cbam_prec_canonical_unit",
            ),
            sa.CheckConstraint(
                "CAST(specific_emissions AS NUMERIC) >= 0",
                name="ck_cbam_prec_nonnegative_see",
            ),
            sa.CheckConstraint(
                "specific_unit = 'tCO2e/t'",
                name="ck_cbam_prec_canonical_see_unit",
            ),
            sa.CheckConstraint(
                "source_kind IN ('self_produced_see', 'supplier_see', 'rule_default')",
                name="ck_cbam_prec_source_kind",
            ),
            sa.CheckConstraint(
                "(source_kind = 'self_produced_see' AND source_see_ref LIKE 'see_result:%') "
                "OR (source_kind = 'supplier_see' AND source_see_ref LIKE 'supplier_see:%') "
                "OR (source_kind = 'rule_default' AND source_see_ref LIKE 'rule_record:%')",
                name="ck_cbam_prec_source_ref",
            ),
            sa.CheckConstraint(
                "period_start < period_end",
                name="ck_cbam_prec_valid_period",
            ),
        ),
    )
    _create_ledger_table(
        "cbam_see_results",
        sa.Column(
            "process_id",
            sa.Uuid(),
            sa.ForeignKey("cbam_production_processes.id"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("cbam_products.id"),
            nullable=False,
        ),
        sa.Column(
            "production_output_id",
            sa.Uuid(),
            sa.ForeignKey("cbam_production_outputs.id"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("direct_emissions", decimal_type, nullable=False),
        sa.Column("indirect_emissions", decimal_type, nullable=False),
        sa.Column("precursor_emissions", decimal_type, nullable=False),
        sa.Column("total_emissions", decimal_type, nullable=False),
        sa.Column("emissions_unit", sa.String(64), nullable=False),
        sa.Column("specific_emissions", decimal_type, nullable=False),
        sa.Column("specific_unit", sa.String(64), nullable=False),
        sa.Column("data_quality", sa.String(32), nullable=False),
        sa.Column("methodology_ref", sa.String(128), nullable=False),
        extra_constraints=(
            sa.CheckConstraint(
                "CAST(direct_emissions AS NUMERIC) >= 0 "
                "AND CAST(indirect_emissions AS NUMERIC) >= 0 "
                "AND CAST(precursor_emissions AS NUMERIC) >= 0 "
                "AND CAST(total_emissions AS NUMERIC) >= 0 "
                "AND CAST(specific_emissions AS NUMERIC) >= 0",
                name="ck_cbam_see_nonnegative",
            ),
            sa.CheckConstraint(
                "CAST(total_emissions AS NUMERIC) = "
                "CAST(direct_emissions AS NUMERIC) "
                "+ CAST(indirect_emissions AS NUMERIC) "
                "+ CAST(precursor_emissions AS NUMERIC)",
                name="ck_cbam_see_component_total",
            ),
            sa.CheckConstraint(
                "emissions_unit = 'tCO2e' AND specific_unit = 'tCO2e/t'",
                name="ck_cbam_see_canonical_units",
            ),
            sa.CheckConstraint(
                "data_quality IN ('not_applicable', 'supplier_verified', "
                "'supplier_declared', 'rule_default')",
                name="ck_cbam_see_data_quality",
            ),
            sa.CheckConstraint(
                "methodology_ref LIKE 'rule_record:%'",
                name="ck_cbam_see_methodology_ref",
            ),
            sa.CheckConstraint(
                "period_start < period_end",
                name="ck_cbam_see_valid_period",
            ),
        ),
    )
    _create_ledger_table(
        "cbam_carbon_price_paid_evidence",
        sa.Column(
            "installation_id",
            sa.Uuid(),
            sa.ForeignKey("cbam_installations.id"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheme", sa.String(32), nullable=False),
        sa.Column("amount_paid", decimal_type, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("covered_emissions", decimal_type, nullable=False),
        sa.Column("emissions_unit", sa.String(64), nullable=False),
        sa.Column("price_per_tonne", decimal_type, nullable=False),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id"),
            nullable=True,
        ),
        extra_constraints=(
            sa.CheckConstraint(
                "CAST(amount_paid AS NUMERIC) >= 0 "
                "AND CAST(covered_emissions AS NUMERIC) >= 0 "
                "AND CAST(price_per_tonne AS NUMERIC) >= 0",
                name="ck_cbam_price_nonnegative",
            ),
            sa.CheckConstraint(
                "emissions_unit = 'tCO2e'",
                name="ck_cbam_price_canonical_unit",
            ),
            sa.CheckConstraint(
                "length(currency) = 3 AND currency = upper(currency)",
                name="ck_cbam_price_currency",
            ),
            sa.CheckConstraint(
                "period_start < period_end",
                name="ck_cbam_price_valid_period",
            ),
        ),
    )

    connection = op.get_bind()
    for table_name in TABLE_PREFIXES:
        if connection.dialect.name == "postgresql":
            _create_postgres_triggers(table_name)
        elif connection.dialect.name == "sqlite":
            _create_sqlite_triggers(table_name)
    if connection.dialect.name == "postgresql":
        _create_postgres_attribution_total_trigger()


def downgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS trg_cbam_attr_total_check "
                "ON cbam_source_stream_attributions"
            )
        )
        op.execute(
            sa.text("DROP FUNCTION IF EXISTS zcy_cbam_attr_total_check()")
        )
    for table_name, prefix in reversed(tuple(TABLE_PREFIXES.items())):
        if connection.dialect.name == "postgresql":
            for trigger in (
                "link_insert",
                "guard_insert",
                "guard_update",
                "guard_delete",
            ):
                op.execute(
                    sa.text(
                        f"DROP TRIGGER IF EXISTS trg_{prefix}_{trigger} "
                        f"ON {table_name}"
                    )
                )
                op.execute(
                    sa.text(
                        f"DROP FUNCTION IF EXISTS zcy_{prefix}_{trigger}()"
                    )
                )
        elif connection.dialect.name == "sqlite":
            for trigger in (
                "link_insert",
                "guard_insert",
                "guard_update",
                "guard_delete",
            ):
                op.execute(
                    sa.text(f"DROP TRIGGER IF EXISTS trg_{prefix}_{trigger}")
                )
        op.drop_table(table_name)
