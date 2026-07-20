"""Add tool trace and eval summary fields to agent run logs.

Revision ID: 016
Revises: 015
Create Date: 2026-05-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_run_logs", sa.Column("tool_calls", postgresql.JSON(), nullable=True))
    op.add_column("agent_run_logs", sa.Column("eval_summary", postgresql.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_run_logs", "eval_summary")
    op.drop_column("agent_run_logs", "tool_calls")
