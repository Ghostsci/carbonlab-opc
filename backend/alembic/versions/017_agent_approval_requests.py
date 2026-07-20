"""Add durable approval queue for high-risk agent actions.

Revision ID: 017
Revises: 016
Create Date: 2026-05-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("agent_run_logs.run_id"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("tool_name", sa.String(150), nullable=False),
        sa.Column("arguments", postgresql.JSON(), nullable=False),
        sa.Column("resume_payload", postgresql.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resumed_run_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_approval_requests_run_id", "agent_approval_requests", ["run_id"])
    op.create_index("ix_agent_approval_requests_tenant_id", "agent_approval_requests", ["tenant_id"])
    op.create_index("ix_agent_approval_requests_agent_id", "agent_approval_requests", ["agent_id"])
    op.create_index("ix_agent_approval_requests_tool_name", "agent_approval_requests", ["tool_name"])


def downgrade() -> None:
    op.drop_index("ix_agent_approval_requests_tool_name", table_name="agent_approval_requests")
    op.drop_index("ix_agent_approval_requests_agent_id", table_name="agent_approval_requests")
    op.drop_index("ix_agent_approval_requests_tenant_id", table_name="agent_approval_requests")
    op.drop_index("ix_agent_approval_requests_run_id", table_name="agent_approval_requests")
    op.drop_table("agent_approval_requests")
