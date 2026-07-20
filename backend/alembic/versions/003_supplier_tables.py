"""Add supplier tables for Scope 3

Revision ID: 003
Revises: 002
Create Date: 2026-05-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("industry", sa.String(100), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("region", sa.String(50), nullable=True),
        sa.Column("share_token", sa.String(64), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "supplier_purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("amount_cny", sa.Float(), nullable=False),
        sa.Column("quantity_tonnes", sa.Float(), nullable=True),
        sa.Column("period_start", sa.String(7), nullable=False),
        sa.Column("period_end", sa.String(7), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "supplier_activity_data",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("scope", sa.String(10), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("fuel_type", sa.String(50), nullable=True),
        sa.Column("activity_quantity", sa.Float(), nullable=False),
        sa.Column("activity_unit", sa.String(20), nullable=False),
        sa.Column("co2_tonnes", sa.Float(), nullable=True),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default="supplier"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("supplier_activity_data")
    op.drop_table("supplier_purchases")
    op.drop_table("suppliers")
