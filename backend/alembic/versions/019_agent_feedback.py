"""Add human feedback table for agent outputs.

Revision ID: 019
Revises: 018
Create Date: 2026-05-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("agent_run_logs.run_id"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("feedback_type", sa.String(20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("corrected_output", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_feedback_run_id", "agent_feedback", ["run_id"])
    op.create_index("ix_agent_feedback_tenant_id", "agent_feedback", ["tenant_id"])
    op.create_index("ix_agent_feedback_user_id", "agent_feedback", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_feedback_user_id", table_name="agent_feedback")
    op.drop_index("ix_agent_feedback_tenant_id", table_name="agent_feedback")
    op.drop_index("ix_agent_feedback_run_id", table_name="agent_feedback")
    op.drop_table("agent_feedback")
