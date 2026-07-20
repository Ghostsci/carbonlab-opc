"""Add missing AI-native governance and verification workbench tables.

Revision ID: 015
Revises: 014
Create Date: 2026-05-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_run_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False, unique=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trigger", sa.String(20), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("node_path", postgresql.JSON(), nullable=True),
        sa.Column("llm_calls", postgresql.JSON(), nullable=True),
        sa.Column("human_intervention", postgresql.JSON(), nullable=True),
        sa.Column("final_action", postgresql.JSON(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("total_cost_cny", sa.Numeric(10, 4), nullable=True),
        sa.Column("execution_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_agent_run_logs_agent_id", "agent_run_logs", ["agent_id"])
    op.create_index("ix_agent_run_logs_tenant_id", "agent_run_logs", ["tenant_id"])

    op.create_table(
        "agent_monthly_costs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("total_cost_cny", sa.Numeric(10, 4), nullable=True),
        sa.Column("run_count", sa.Integer(), nullable=True),
        sa.Column("avg_tokens_per_run", sa.Integer(), nullable=True),
        sa.Column("degradation_count", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_monthly_costs_agent_id", "agent_monthly_costs", ["agent_id"])

    op.create_table(
        "nl_query_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("sql_generated", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("execution_ms", sa.Integer(), nullable=True),
        sa.Column("chart_type", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_nl_query_logs_tenant_id", "nl_query_logs", ["tenant_id"])

    op.create_table(
        "regulation_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("regulation_name", sa.String(500), nullable=False),
        sa.Column("jurisdiction", sa.String(50), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("change_type", sa.String(50), nullable=False),
        sa.Column("structured_diff", postgresql.JSON(), nullable=False),
        sa.Column("affected_industries", postgresql.JSON(), nullable=True),
        sa.Column("affected_customer_ids", postgresql.JSON(), nullable=True),
        sa.Column("action_required", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("summary_zh", sa.Text(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "verification_workbench_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cbam_report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enterprise_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("priority", sa.String(10), nullable=True),
        sa.Column("report_pdf_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_verification_workbench_tasks_cbam_report_id",
        "verification_workbench_tasks",
        ["cbam_report_id"],
    )
    op.create_index(
        "ix_verification_workbench_tasks_enterprise_id",
        "verification_workbench_tasks",
        ["enterprise_id"],
    )

    op.create_table(
        "verification_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("verification_workbench_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("finding_type", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(10), nullable=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence_ref", sa.String(255), nullable=True),
        sa.Column("suggested_action", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_verification_findings_task_id", "verification_findings", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_verification_findings_task_id", table_name="verification_findings")
    op.drop_table("verification_findings")
    op.drop_index("ix_verification_workbench_tasks_enterprise_id", table_name="verification_workbench_tasks")
    op.drop_index("ix_verification_workbench_tasks_cbam_report_id", table_name="verification_workbench_tasks")
    op.drop_table("verification_workbench_tasks")
    op.drop_table("regulation_changes")
    op.drop_index("ix_nl_query_logs_tenant_id", table_name="nl_query_logs")
    op.drop_table("nl_query_logs")
    op.drop_index("ix_agent_monthly_costs_agent_id", table_name="agent_monthly_costs")
    op.drop_table("agent_monthly_costs")
    op.drop_index("ix_agent_run_logs_tenant_id", table_name="agent_run_logs")
    op.drop_index("ix_agent_run_logs_agent_id", table_name="agent_run_logs")
    op.drop_table("agent_run_logs")
