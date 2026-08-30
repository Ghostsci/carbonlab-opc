"""Repair and enforce tenant lineage for sites and emission sources.

Revision ID: 035
Revises: 034
Create Date: 2026-08-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "035"
down_revision: Union[str, None] = "034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SITE_TENANT_UNIQUE = "uq_sites_id_tenant"
SOURCE_SITE_TENANT_FK = "fk_emission_sources_site_tenant"


def _backfill_tenant_lineage() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE sites SET tenant_id = ("
            "SELECT enterprises.tenant_id FROM enterprises "
            "WHERE enterprises.id = sites.enterprise_id"
            ") WHERE tenant_id IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE emission_sources SET tenant_id = ("
            "SELECT sites.tenant_id FROM sites "
            "WHERE sites.id = emission_sources.site_id"
            ") WHERE tenant_id IS NULL"
        )
    )


def _preflight() -> None:
    bind = op.get_bind()
    invalid_sites = bind.execute(
        sa.text(
            "SELECT count(*) FROM sites s "
            "LEFT JOIN enterprises e ON e.id = s.enterprise_id "
            "WHERE s.tenant_id IS NULL OR e.id IS NULL "
            "OR e.tenant_id IS NULL OR s.tenant_id <> e.tenant_id"
        )
    ).scalar_one()
    invalid_sources = bind.execute(
        sa.text(
            "SELECT count(*) FROM emission_sources es "
            "LEFT JOIN sites s ON s.id = es.site_id "
            "WHERE es.tenant_id IS NULL OR s.id IS NULL "
            "OR s.tenant_id IS NULL OR es.tenant_id <> s.tenant_id"
        )
    ).scalar_one()
    if invalid_sites or invalid_sources:
        raise RuntimeError(
            "035 tenant-lineage preflight failed: "
            f"invalid_sites={invalid_sites}, invalid_emission_sources={invalid_sources}"
        )


def _foreign_key_name(
    table_name: str,
    constrained_columns: list[str],
    referred_table: str,
) -> str | None:
    for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys(table_name):
        if (
            foreign_key.get("constrained_columns") == constrained_columns
            and foreign_key.get("referred_table") == referred_table
        ):
            return foreign_key.get("name")
    return None


def _upgrade_sqlite() -> None:
    with op.batch_alter_table("sites") as batch:
        batch.alter_column("tenant_id", existing_type=sa.Uuid(), nullable=False)
        batch.create_unique_constraint(SITE_TENANT_UNIQUE, ["id", "tenant_id"])
    with op.batch_alter_table("emission_sources") as batch:
        batch.alter_column("tenant_id", existing_type=sa.Uuid(), nullable=False)
    op.execute(
        sa.text(
            """
            CREATE TRIGGER IF NOT EXISTS trg_emission_sources_tenant_insert
            BEFORE INSERT ON emission_sources
            WHEN NOT EXISTS (
                SELECT 1 FROM sites
                WHERE sites.id = NEW.site_id AND sites.tenant_id = NEW.tenant_id
            )
            BEGIN
                SELECT RAISE(ABORT, 'emission source tenant lineage violated');
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER IF NOT EXISTS trg_emission_sources_tenant_update
            BEFORE UPDATE OF site_id, tenant_id ON emission_sources
            WHEN NOT EXISTS (
                SELECT 1 FROM sites
                WHERE sites.id = NEW.site_id AND sites.tenant_id = NEW.tenant_id
            )
            BEGIN
                SELECT RAISE(ABORT, 'emission source tenant lineage violated');
            END
            """
        )
    )


def _upgrade_postgresql() -> None:
    op.alter_column(
        "sites",
        "tenant_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.alter_column(
        "emission_sources",
        "tenant_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.create_unique_constraint(SITE_TENANT_UNIQUE, "sites", ["id", "tenant_id"])
    legacy_site_fk = _foreign_key_name("emission_sources", ["site_id"], "sites")
    if legacy_site_fk:
        op.drop_constraint(legacy_site_fk, "emission_sources", type_="foreignkey")
    op.create_foreign_key(
        SOURCE_SITE_TENANT_FK,
        "emission_sources",
        "sites",
        ["site_id", "tenant_id"],
        ["id", "tenant_id"],
    )


def upgrade() -> None:
    _backfill_tenant_lineage()
    _preflight()
    if op.get_bind().dialect.name == "sqlite":
        _upgrade_sqlite()
    else:
        _upgrade_postgresql()


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            sa.text("DROP TRIGGER IF EXISTS trg_emission_sources_tenant_update")
        )
        op.execute(
            sa.text("DROP TRIGGER IF EXISTS trg_emission_sources_tenant_insert")
        )
        with op.batch_alter_table("emission_sources") as batch:
            batch.alter_column("tenant_id", existing_type=sa.Uuid(), nullable=True)
        with op.batch_alter_table("sites") as batch:
            batch.drop_constraint(SITE_TENANT_UNIQUE, type_="unique")
            batch.alter_column("tenant_id", existing_type=sa.Uuid(), nullable=True)
        return

    op.drop_constraint(SOURCE_SITE_TENANT_FK, "emission_sources", type_="foreignkey")
    op.create_foreign_key(
        "emission_sources_site_id_fkey",
        "emission_sources",
        "sites",
        ["site_id"],
        ["id"],
    )
    op.drop_constraint(SITE_TENANT_UNIQUE, "sites", type_="unique")
    op.alter_column(
        "emission_sources",
        "tenant_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.alter_column(
        "sites",
        "tenant_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
