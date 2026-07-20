"""Add AI OS core workflow and context tables.

Revision ID: 024
Revises: 023
Create Date: 2026-06-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_profiles",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("profile_key", sa.String(120), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("version", sa.String(40), nullable=False, server_default="v1"),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("capability_tags", sa.JSON(), nullable=True),
        sa.Column("model_preferences", sa.JSON(), nullable=True),
        sa.Column("tool_allowlist", sa.JSON(), nullable=True),
        sa.Column("input_contract", sa.JSON(), nullable=True),
        sa.Column("output_contract", sa.JSON(), nullable=True),
        sa.Column("guardrails", sa.JSON(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_profiles_tenant_id", "agent_profiles", ["tenant_id"])
    op.create_index("ix_agent_profiles_profile_key", "agent_profiles", ["profile_key"])

    op.create_table(
        "workflow_instances",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("enterprise_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=True),
        sa.Column("workflow_key", sa.String(160), nullable=False),
        sa.Column("workflow_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("phase", sa.String(80), nullable=False, server_default="data_collection"),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_step_key", sa.String(120), nullable=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_workflow_instances_tenant_id", "workflow_instances", ["tenant_id"])
    op.create_index("ix_workflow_instances_enterprise_id", "workflow_instances", ["enterprise_id"])
    op.create_index("ix_workflow_instances_workflow_key", "workflow_instances", ["workflow_key"])
    op.create_index("ix_workflow_instances_workflow_type", "workflow_instances", ["workflow_type"])

    op.create_table(
        "workflow_steps",
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("step_key", sa.String(120), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("agent_profile_key", sa.String(120), nullable=True),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="low"),
        sa.Column("inputs_json", sa.JSON(), nullable=True),
        sa.Column("outputs_json", sa.JSON(), nullable=True),
        sa.Column("checkpoints_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_workflow_steps_workflow_id", "workflow_steps", ["workflow_id"])
    op.create_index("ix_workflow_steps_tenant_id", "workflow_steps", ["tenant_id"])
    op.create_index("ix_workflow_steps_step_key", "workflow_steps", ["step_key"])
    op.create_index("ix_workflow_steps_agent_profile_key", "workflow_steps", ["agent_profile_key"])

    op.create_table(
        "ai_memories",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("enterprise_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=True),
        sa.Column("memory_type", sa.String(60), nullable=False),
        sa.Column("subject_key", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="tenant"),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("source_type", sa.String(80), nullable=True),
        sa.Column("source_ref", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_memories_tenant_id", "ai_memories", ["tenant_id"])
    op.create_index("ix_ai_memories_enterprise_id", "ai_memories", ["enterprise_id"])
    op.create_index("ix_ai_memories_memory_type", "ai_memories", ["memory_type"])
    op.create_index("ix_ai_memories_subject_key", "ai_memories", ["subject_key"])

    op.create_table(
        "context_pack_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_instances.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("agent_profile_key", sa.String(120), nullable=False),
        sa.Column("pack_key", sa.String(120), nullable=False),
        sa.Column("purpose", sa.String(120), nullable=False, server_default="agent_run"),
        sa.Column("input_snapshot", sa.JSON(), nullable=True),
        sa.Column("assembled_context", sa.JSON(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=True),
        sa.Column("policy_snapshot", sa.JSON(), nullable=True),
        sa.Column("token_estimate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_context_pack_records_tenant_id", "context_pack_records", ["tenant_id"])
    op.create_index("ix_context_pack_records_workflow_id", "context_pack_records", ["workflow_id"])
    op.create_index("ix_context_pack_records_agent_profile_key", "context_pack_records", ["agent_profile_key"])
    op.create_index("ix_context_pack_records_pack_key", "context_pack_records", ["pack_key"])


def downgrade() -> None:
    op.drop_index("ix_context_pack_records_pack_key", table_name="context_pack_records")
    op.drop_index("ix_context_pack_records_agent_profile_key", table_name="context_pack_records")
    op.drop_index("ix_context_pack_records_workflow_id", table_name="context_pack_records")
    op.drop_index("ix_context_pack_records_tenant_id", table_name="context_pack_records")
    op.drop_table("context_pack_records")

    op.drop_index("ix_ai_memories_subject_key", table_name="ai_memories")
    op.drop_index("ix_ai_memories_memory_type", table_name="ai_memories")
    op.drop_index("ix_ai_memories_enterprise_id", table_name="ai_memories")
    op.drop_index("ix_ai_memories_tenant_id", table_name="ai_memories")
    op.drop_table("ai_memories")

    op.drop_index("ix_workflow_steps_agent_profile_key", table_name="workflow_steps")
    op.drop_index("ix_workflow_steps_step_key", table_name="workflow_steps")
    op.drop_index("ix_workflow_steps_tenant_id", table_name="workflow_steps")
    op.drop_index("ix_workflow_steps_workflow_id", table_name="workflow_steps")
    op.drop_table("workflow_steps")

    op.drop_index("ix_workflow_instances_workflow_type", table_name="workflow_instances")
    op.drop_index("ix_workflow_instances_workflow_key", table_name="workflow_instances")
    op.drop_index("ix_workflow_instances_enterprise_id", table_name="workflow_instances")
    op.drop_index("ix_workflow_instances_tenant_id", table_name="workflow_instances")
    op.drop_table("workflow_instances")

    op.drop_index("ix_agent_profiles_profile_key", table_name="agent_profiles")
    op.drop_index("ix_agent_profiles_tenant_id", table_name="agent_profiles")
    op.drop_table("agent_profiles")
