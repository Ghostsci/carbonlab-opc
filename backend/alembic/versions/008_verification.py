"""Add verification platform tables (T-22).

Revision ID: 008
Revises: 007
Create Date: 2026-05-13
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "verification_bodies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("accreditation_number", sa.String(50), nullable=False, unique=True),
        sa.Column("accreditation_scope", sa.String(500), nullable=False),
        sa.Column("country", sa.String(100), nullable=False),
        sa.Column("contact_email", sa.String(200), nullable=False),
        sa.Column("contact_phone", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "verifiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("body_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verification_bodies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(200), nullable=False, unique=True),
        sa.Column("qualification", sa.String(200), nullable=False),
        sa.Column("years_experience", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "verification_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("enterprise_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("enterprises.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("body_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verification_bodies.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("lead_verifier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verifiers.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("scope", sa.String(200), nullable=False),
        sa.Column("reporting_period", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("access_token", sa.String(100), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "verification_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verification_tasks.id", ondelete="CASCADE"), nullable=False, unique=True, index=True),
        sa.Column("opinion", sa.String(50), nullable=False),
        sa.Column("is_limited_assurance", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("verified_co2_tonnes", sa.Float(), nullable=False),
        sa.Column("enterprise_reported_co2_tonnes", sa.Float(), nullable=False),
        sa.Column("materiality_threshold_pct", sa.Float(), nullable=False, server_default="5.0"),
        sa.Column("discrepancy_pct", sa.Float(), nullable=True),
        sa.Column("findings_json", sa.Text(), nullable=True),
        sa.Column("verifier_signature", sa.String(200), nullable=True),
        sa.Column("signed_at", sa.String(30), nullable=True),
        sa.Column("bjgem_format", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("verification_reports")
    op.drop_table("verification_tasks")
    op.drop_table("verifiers")
    op.drop_table("verification_bodies")
