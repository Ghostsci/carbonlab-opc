"""Add authoritative RuleRecord and enforce K2 rule references.

Revision ID: 027
Revises: 026
Create Date: 2026-07-04
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _postgres_triggers() -> None:
    op.execute(
        sa.text(
            """
            CREATE FUNCTION zcy_validate_precursor_rule_record() RETURNS trigger AS $$
            DECLARE rule_id UUID;
            BEGIN
                IF NEW.source_kind <> 'rule_default' THEN RETURN NEW; END IF;
                rule_id := split_part(NEW.source_see_ref, ':', 2)::uuid;
                IF NOT EXISTS (
                    SELECT 1 FROM rule_records rule
                    WHERE rule.id = rule_id
                      AND rule.tenant_id = NEW.tenant_id
                      AND rule.rule_kind = 'precursor_default'
                      AND rule.status = 'approved'
                      AND rule.publisher IN (
                          'European Commission',
                          'European Parliament and Council'
                      )
                      AND rule.jurisdiction = 'EU'
                      AND rule.document_number LIKE 'EU-%'
                      AND rule.source_url LIKE 'https://%'
                      AND rule.vintage <= EXTRACT(YEAR FROM NEW.period_start)
                      AND rule.valid_from <= NEW.period_start
                      AND (rule.valid_to IS NULL OR rule.valid_to >= NEW.period_end)
                ) THEN
                    RAISE EXCEPTION 'approved rule record not found or not applicable';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            CREATE TRIGGER trg_cbam_prec_rule_record
            BEFORE INSERT ON cbam_precursor_consumptions
            FOR EACH ROW EXECUTE FUNCTION zcy_validate_precursor_rule_record();

            CREATE FUNCTION zcy_validate_see_rule_record() RETURNS trigger AS $$
            DECLARE rule_id UUID;
            BEGIN
                rule_id := split_part(NEW.methodology_ref, ':', 2)::uuid;
                IF NOT EXISTS (
                    SELECT 1 FROM rule_records rule
                    WHERE rule.id = rule_id
                      AND rule.tenant_id = NEW.tenant_id
                      AND rule.rule_kind = 'cbam_methodology'
                      AND rule.status = 'approved'
                      AND rule.publisher IN (
                          'European Commission',
                          'European Parliament and Council'
                      )
                      AND rule.jurisdiction = 'EU'
                      AND rule.document_number LIKE 'EU-%'
                      AND rule.source_url LIKE 'https://%'
                      AND rule.vintage <= EXTRACT(YEAR FROM NEW.period_start)
                      AND rule.valid_from <= NEW.period_start
                      AND (rule.valid_to IS NULL OR rule.valid_to >= NEW.period_end)
                ) THEN
                    RAISE EXCEPTION 'approved rule record not found or not applicable';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            CREATE TRIGGER trg_cbam_see_rule_record
            BEFORE INSERT ON cbam_see_results
            FOR EACH ROW EXECUTE FUNCTION zcy_validate_see_rule_record();
            """
        )
    )


def _sqlite_triggers() -> None:
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_cbam_prec_rule_record
            BEFORE INSERT ON cbam_precursor_consumptions
            FOR EACH ROW
            WHEN NEW.source_kind = 'rule_default'
             AND NOT EXISTS (
                SELECT 1 FROM rule_records rule
                WHERE rule.id =
                      replace(substr(NEW.source_see_ref, 13), '-', '')
                  AND rule.tenant_id = NEW.tenant_id
                  AND rule.rule_kind = 'precursor_default'
                  AND rule.status = 'approved'
                  AND rule.publisher IN (
                      'European Commission',
                      'European Parliament and Council'
                  )
                  AND rule.jurisdiction = 'EU'
                  AND rule.document_number LIKE 'EU-%'
                  AND rule.source_url LIKE 'https://%'
                  AND rule.vintage <= CAST(substr(NEW.period_start, 1, 4) AS INTEGER)
                  AND rule.valid_from <= NEW.period_start
                  AND (rule.valid_to IS NULL OR rule.valid_to >= NEW.period_end)
             )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'approved rule record not found or not applicable'
                );
            END;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_cbam_see_rule_record
            BEFORE INSERT ON cbam_see_results
            FOR EACH ROW
            WHEN NOT EXISTS (
                SELECT 1 FROM rule_records rule
                WHERE rule.id =
                      replace(substr(NEW.methodology_ref, 13), '-', '')
                  AND rule.tenant_id = NEW.tenant_id
                  AND rule.rule_kind = 'cbam_methodology'
                  AND rule.status = 'approved'
                  AND rule.publisher IN (
                      'European Commission',
                      'European Parliament and Council'
                  )
                  AND rule.jurisdiction = 'EU'
                  AND rule.document_number LIKE 'EU-%'
                  AND rule.source_url LIKE 'https://%'
                  AND rule.vintage <= CAST(substr(NEW.period_start, 1, 4) AS INTEGER)
                  AND rule.valid_from <= NEW.period_start
                  AND (rule.valid_to IS NULL OR rule.valid_to >= NEW.period_end)
             )
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'approved rule record not found or not applicable'
                );
            END;
            """
        )
    )


def upgrade() -> None:
    op.create_table(
        "rule_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("rule_kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("publisher", sa.String(255), nullable=False),
        sa.Column("document_number", sa.String(128), nullable=False),
        sa.Column("jurisdiction", sa.String(32), nullable=False),
        sa.Column("vintage", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("approved_by", sa.String(64), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.UniqueConstraint(
            "tenant_id",
            "rule_kind",
            "document_number",
            "vintage",
            name="uq_rule_record_authority_version",
        ),
        sa.CheckConstraint(
            "rule_kind IN ('cbam_methodology', 'precursor_default')",
            name="ck_rule_record_kind",
        ),
        sa.CheckConstraint(
            "length(trim(title)) > 0 "
            "AND length(trim(publisher)) > 0 "
            "AND length(trim(document_number)) > 0 "
            "AND length(trim(jurisdiction)) > 0",
            name="ck_rule_record_authority_metadata",
        ),
        sa.CheckConstraint(
            "publisher IN ('European Commission', "
            "'European Parliament and Council')",
            name="ck_rule_record_trusted_publisher",
        ),
        sa.CheckConstraint(
            "jurisdiction = 'EU' AND document_number LIKE 'EU-%'",
            name="ck_rule_record_document_identity",
        ),
        sa.CheckConstraint(
            "source_url LIKE 'https://%'",
            name="ck_rule_record_https_source",
        ),
        sa.CheckConstraint("vintage >= 1900", name="ck_rule_record_vintage"),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from < valid_to",
            name="ck_rule_record_valid_period",
        ),
        sa.CheckConstraint(
            "status IN ('approved', 'withdrawn', 'superseded')",
            name="ck_rule_record_status",
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_rule_record_content_hash",
        ),
    )
    op.create_index("ix_rule_records_tenant_id", "rule_records", ["tenant_id"])
    op.create_index("ix_rule_records_rule_kind", "rule_records", ["rule_kind"])
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        _postgres_triggers()
    elif dialect == "sqlite":
        _sqlite_triggers()


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        for table, trigger, function in (
            (
                "cbam_precursor_consumptions",
                "trg_cbam_prec_rule_record",
                "zcy_validate_precursor_rule_record",
            ),
            (
                "cbam_see_results",
                "trg_cbam_see_rule_record",
                "zcy_validate_see_rule_record",
            ),
        ):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger} ON {table}"))
            op.execute(sa.text(f"DROP FUNCTION IF EXISTS {function}()"))
    elif dialect == "sqlite":
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_cbam_prec_rule_record"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_cbam_see_rule_record"))
    op.drop_index("ix_rule_records_rule_kind", table_name="rule_records")
    op.drop_index("ix_rule_records_tenant_id", table_name="rule_records")
    op.drop_table("rule_records")
