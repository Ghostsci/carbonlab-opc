"""Add agent input snapshots and eval candidate queue.

Revision ID: 020
Revises: 019
Create Date: 2026-05-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_run_logs", sa.Column("input_snapshot", postgresql.JSON(), nullable=True))
    op.create_table(
        "agent_eval_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("feedback_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_feedback.id"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("input_snapshot", postgresql.JSON(), nullable=True),
        sa.Column("expected_output", postgresql.JSON(), nullable=False),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_eval_candidates_feedback_id", "agent_eval_candidates", ["feedback_id"])
    op.create_index("ix_agent_eval_candidates_tenant_id", "agent_eval_candidates", ["tenant_id"])
    op.create_index("ix_agent_eval_candidates_run_id", "agent_eval_candidates", ["run_id"])
    op.create_index("ix_agent_eval_candidates_agent_id", "agent_eval_candidates", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_eval_candidates_agent_id", table_name="agent_eval_candidates")
    op.drop_index("ix_agent_eval_candidates_run_id", table_name="agent_eval_candidates")
    op.drop_index("ix_agent_eval_candidates_tenant_id", table_name="agent_eval_candidates")
    op.drop_index("ix_agent_eval_candidates_feedback_id", table_name="agent_eval_candidates")
    op.drop_table("agent_eval_candidates")
    op.drop_column("agent_run_logs", "input_snapshot")
