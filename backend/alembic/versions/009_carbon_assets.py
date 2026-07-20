"""Add carbon asset management tables (T-21).

Revision ID: 009
Revises: 008
Create Date: 2026-05-13
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "carbon_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("enterprise_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("enterprises.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_type", sa.String(20), nullable=False),
        sa.Column("asset_subtype", sa.String(50), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("quantity_tco2", sa.Float, nullable=False, server_default="0"),
        sa.Column("unit_price_cny", sa.Float, nullable=True),
        sa.Column("total_value_cny", sa.Float, nullable=True),
        sa.Column("vintage_year", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("acquisition_date", sa.String(20), nullable=True),
        sa.Column("expiry_date", sa.String(20), nullable=True),
        sa.Column("ccer_methodology", sa.String(200), nullable=True),
        sa.Column("ccer_project_id", sa.String(100), nullable=True),
        sa.Column("registry", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "green_finance_products",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("product_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("institution", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("min_amount_cny", sa.Float, nullable=False, server_default="0"),
        sa.Column("interest_rate_pct", sa.Float, nullable=True),
        sa.Column("term_months", sa.Integer, nullable=True),
        sa.Column("collateral_type", sa.String(100), nullable=True),
        sa.Column("eligibility", sa.Text, nullable=True),
        sa.Column("contact", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
    )

    op.create_table(
        "compliance_strategies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("enterprise_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("enterprises.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("strategy_type", sa.String(30), nullable=False),
        sa.Column("allocated_quota", sa.Float, nullable=False),
        sa.Column("projected_emissions", sa.Float, nullable=False),
        sa.Column("held_assets", sa.Float, nullable=False, server_default="0"),
        sa.Column("surplus_deficit", sa.Float, nullable=False),
        sa.Column("recommended_action", sa.String(500), nullable=False),
        sa.Column("target_transaction_tco2", sa.Float, nullable=True),
        sa.Column("estimated_cost_cny", sa.Float, nullable=True),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("cea_price_cny", sa.Float, nullable=True),
        sa.Column("price_trend", sa.String(20), nullable=True),
        sa.Column("deadline", sa.String(20), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("compliance_strategies")
    op.drop_table("green_finance_products")
    op.drop_table("carbon_assets")
