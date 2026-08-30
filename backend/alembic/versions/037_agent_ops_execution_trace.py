"""Add governed digital employee task runs and immutable execution events.

Revision ID: 037
Revises: 036
Create Date: 2026-08-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "037"
down_revision: Union[str, None] = "036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _enable_postgres_controls() -> None:
    for table in ("agent_run_logs", "agent_run_events"):
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}"))
        op.execute(
            sa.text(
                f"CREATE POLICY tenant_isolation_{table} ON {table} "
                "USING (tenant_id::text = current_setting('app.current_tenant_id', true)) "
                "WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))"
            )
        )

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION public.zcy_prevent_agent_run_event_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'agent run events are append-only'
                    USING ERRCODE = '23514';
            END
            $$
            """
        )
    )
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_agent_run_events_immutable ON agent_run_events"))
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_agent_run_events_immutable "
            "BEFORE UPDATE OR DELETE ON agent_run_events "
            "FOR EACH ROW EXECUTE FUNCTION public.zcy_prevent_agent_run_event_mutation()"
        )
    )


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    with op.batch_alter_table("agent_run_logs") as batch:
        batch.add_column(sa.Column("enterprise_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("workflow_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("workflow_step_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("source_file_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("parent_run_id", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(sa.Column("trigger_ref", sa.String(255), nullable=True))
        batch.add_column(sa.Column("status_reason", sa.String(255), nullable=True))
        batch.add_column(sa.Column("skill_id", sa.String(100), nullable=True))
        batch.add_column(sa.Column("skill_version", sa.String(40), nullable=True))
        batch.add_column(sa.Column("skill_sha256", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column(
                "redaction_version",
                sa.String(40),
                nullable=False,
                server_default="trace-redaction-v1",
            )
        )
        batch.add_column(sa.Column("output_snapshot", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("summary", sa.String(1000), nullable=True))
        batch.create_foreign_key(
            "fk_agent_run_logs_enterprise",
            "enterprises",
            ["enterprise_id"],
            ["id"],
        )
        batch.create_foreign_key(
            "fk_agent_run_logs_workflow",
            "workflow_instances",
            ["workflow_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_agent_run_logs_workflow_step",
            "workflow_steps",
            ["workflow_step_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_agent_run_logs_source_file",
            "documents",
            ["source_file_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.execute(
        sa.text(
            "UPDATE agent_run_logs SET status='completed' "
            "WHERE status IS NULL OR status NOT IN "
            "('queued', 'running', 'waiting_human', 'completed', 'failed', 'cancelled')"
        )
    )
    with op.batch_alter_table("agent_run_logs") as batch:
        batch.alter_column(
            "status",
            existing_type=sa.String(20),
            nullable=False,
            server_default="completed",
        )
        batch.create_check_constraint(
            "ck_agent_run_logs_status",
            "status IN ('queued', 'running', 'waiting_human', 'completed', 'failed', 'cancelled')",
        )
        batch.create_check_constraint(
            "ck_agent_run_logs_attempt",
            "attempt_number >= 1",
        )
        batch.create_check_constraint(
            "ck_agent_run_logs_skill_hash",
            "skill_sha256 IS NULL OR length(skill_sha256) = 64",
        )
    op.create_index("ix_agent_run_logs_enterprise_id", "agent_run_logs", ["enterprise_id"])
    op.create_index("ix_agent_run_logs_workflow_id", "agent_run_logs", ["workflow_id"])
    op.create_index("ix_agent_run_logs_workflow_step_id", "agent_run_logs", ["workflow_step_id"])
    op.create_index("ix_agent_run_logs_source_file_id", "agent_run_logs", ["source_file_id"])
    op.create_index("ix_agent_run_logs_parent_run_id", "agent_run_logs", ["parent_run_id"])

    json_object_default = sa.text("'{}'::json") if dialect == "postgresql" else sa.text("'{}'")
    json_list_default = sa.text("'[]'::json") if dialect == "postgresql" else sa.text("'[]'")
    op.create_table(
        "agent_run_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("enterprise_id", sa.Uuid(), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column(
            "run_id",
            sa.String(64),
            sa.ForeignKey("agent_run_logs.run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.String(1000), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=json_object_default),
        sa.Column("evidence_refs", sa.JSON(), nullable=False, server_default=json_list_default),
        sa.Column("prev_event_sha256", sa.String(64), nullable=True),
        sa.Column("event_sha256", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("run_id", "sequence", name="uq_agent_run_events_run_sequence"),
        sa.CheckConstraint("sequence >= 1", name="ck_agent_run_events_sequence"),
        sa.CheckConstraint(
            "status IN ('info', 'running', 'success', 'warning', 'blocked', 'error')",
            name="ck_agent_run_events_status",
        ),
        sa.CheckConstraint("length(event_sha256) = 64", name="ck_agent_run_events_hash"),
        sa.CheckConstraint(
            "prev_event_sha256 IS NULL OR length(prev_event_sha256) = 64",
            name="ck_agent_run_events_prev_hash",
        ),
    )
    op.create_index("ix_agent_run_events_tenant_id", "agent_run_events", ["tenant_id"])
    op.create_index("ix_agent_run_events_enterprise_id", "agent_run_events", ["enterprise_id"])
    op.create_index("ix_agent_run_events_run_id", "agent_run_events", ["run_id"])
    op.create_index("ix_agent_run_events_event_type", "agent_run_events", ["event_type"])

    if dialect == "postgresql":
        _enable_postgres_controls()


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_agent_run_events_immutable ON agent_run_events"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS public.zcy_prevent_agent_run_event_mutation()"))
        for table in ("agent_run_events", "agent_run_logs"):
            op.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}"))
            op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    op.drop_index("ix_agent_run_events_event_type", table_name="agent_run_events")
    op.drop_index("ix_agent_run_events_run_id", table_name="agent_run_events")
    op.drop_index("ix_agent_run_events_enterprise_id", table_name="agent_run_events")
    op.drop_index("ix_agent_run_events_tenant_id", table_name="agent_run_events")
    op.drop_table("agent_run_events")

    op.drop_index("ix_agent_run_logs_parent_run_id", table_name="agent_run_logs")
    op.drop_index("ix_agent_run_logs_source_file_id", table_name="agent_run_logs")
    op.drop_index("ix_agent_run_logs_workflow_step_id", table_name="agent_run_logs")
    op.drop_index("ix_agent_run_logs_workflow_id", table_name="agent_run_logs")
    op.drop_index("ix_agent_run_logs_enterprise_id", table_name="agent_run_logs")
    with op.batch_alter_table("agent_run_logs") as batch:
        batch.drop_constraint("ck_agent_run_logs_skill_hash", type_="check")
        batch.drop_constraint("ck_agent_run_logs_attempt", type_="check")
        batch.drop_constraint("ck_agent_run_logs_status", type_="check")
        batch.drop_constraint("fk_agent_run_logs_source_file", type_="foreignkey")
        batch.drop_constraint("fk_agent_run_logs_workflow_step", type_="foreignkey")
        batch.drop_constraint("fk_agent_run_logs_workflow", type_="foreignkey")
        batch.drop_constraint("fk_agent_run_logs_enterprise", type_="foreignkey")
        for column in (
            "summary",
            "output_snapshot",
            "redaction_version",
            "skill_sha256",
            "skill_version",
            "skill_id",
            "status_reason",
            "trigger_ref",
            "attempt_number",
            "parent_run_id",
            "source_file_id",
            "workflow_step_id",
            "workflow_id",
            "enterprise_id",
        ):
            batch.drop_column(column)
