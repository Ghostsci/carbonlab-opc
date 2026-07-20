"""Add product LCA and EPD report tables (T-19).

Revision ID: 004
Revises: 003
Create Date: 2026-05-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_lca",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("enterprise_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("enterprises.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("sku", sa.String(100), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("declared_unit", sa.String(50), nullable=False, server_default="1 tonne"),
        sa.Column("annual_output", sa.Float(), nullable=False),
        sa.Column("annual_revenue_cny", sa.Float(), nullable=True),
        sa.Column("production_hours", sa.Float(), nullable=True),
        sa.Column("total_co2_tonnes", sa.Float(), nullable=True),
        sa.Column("co2_per_unit", sa.Float(), nullable=True),
        sa.Column("allocation_method", sa.String(50), nullable=True),
        sa.Column("industry_avg_co2_per_unit", sa.Float(), nullable=True),
        sa.Column("benchmark_source", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "product_stages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("product_lca_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("product_lca.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("stage_order", sa.Integer(), nullable=False),
        sa.Column("stage_name", sa.String(50), nullable=False),
        sa.Column("stage_label", sa.String(50), nullable=False),
        sa.Column("activity_description", sa.String(500), nullable=False),
        sa.Column("co2_tonnes", sa.Float(), nullable=False, server_default="0"),
        sa.Column("co2_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_factor", sa.String(500), nullable=True),
    )

    op.create_table(
        "product_emissions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("product_lca_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("product_lca.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("emission_result_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("emission_results.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("allocation_method", sa.String(50), nullable=False),
        sa.Column("allocation_ratio", sa.Float(), nullable=False),
        sa.Column("co2_tonnes", sa.Float(), nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
    )

    op.create_table(
        "epd_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_lca_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("product_lca.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("epd_version", sa.String(20), nullable=False, server_default="2026-v1"),
        sa.Column("program_operator", sa.String(200), nullable=False, server_default="CarbonLab EPD Programme"),
        sa.Column("pcr_reference", sa.String(200), nullable=False, server_default="ISO 14067:2018"),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("gwp_total", sa.Float(), nullable=False),
        sa.Column("gwp_biogenic", sa.Float(), nullable=True),
        sa.Column("gwp_luluc", sa.Float(), nullable=True),
        sa.Column("stage_results", sa.Text(), nullable=True),
        sa.Column("materials", sa.Text(), nullable=True),
        sa.Column("hazardous_substances", sa.String(500), nullable=True),
        sa.Column("use_scenario", sa.Text(), nullable=True),
        sa.Column("disposal_scenario", sa.Text(), nullable=True),
        sa.Column("third_party_verified", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("verifier_name", sa.String(200), nullable=True),
        sa.Column("report_html", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("epd_reports")
    op.drop_table("product_emissions")
    op.drop_table("product_stages")
    op.drop_table("product_lca")
