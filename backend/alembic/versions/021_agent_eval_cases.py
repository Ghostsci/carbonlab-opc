"""Add persisted dynamic eval cases.

Revision ID: 021
Revises: 020
Create Date: 2026-05-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_eval_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_name", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("input_data", postgresql.JSON(), nullable=False),
        sa.Column("expected_output_subset", postgresql.JSON(), nullable=True),
        sa.Column("expected_tool_sequence", postgresql.JSON(), nullable=True),
        sa.Column("expected_human_interventions", postgresql.JSON(), nullable=True),
        sa.Column(
            "source_candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_eval_candidates.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_eval_cases_tenant_id", "agent_eval_cases", ["tenant_id"])
    op.create_index("ix_agent_eval_cases_dataset_name", "agent_eval_cases", ["dataset_name"])
    op.create_index("ix_agent_eval_cases_agent_id", "agent_eval_cases", ["agent_id"])
    op.create_index("ix_agent_eval_cases_source_candidate_id", "agent_eval_cases", ["source_candidate_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_eval_cases_source_candidate_id", table_name="agent_eval_cases")
    op.drop_index("ix_agent_eval_cases_agent_id", table_name="agent_eval_cases")
    op.drop_index("ix_agent_eval_cases_dataset_name", table_name="agent_eval_cases")
    op.drop_index("ix_agent_eval_cases_tenant_id", table_name="agent_eval_cases")
    op.drop_table("agent_eval_cases")
