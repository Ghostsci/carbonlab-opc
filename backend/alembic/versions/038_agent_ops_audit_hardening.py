"""Harden AgentOps scope lineage and terminal audit immutability.

Revision ID: 038
Revises: 037
Create Date: 2026-08-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "038"
down_revision: Union[str, None] = "037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ENTERPRISE_SCOPE_UNIQUE = "uq_enterprises_id_tenant"
DOCUMENT_SCOPE_UNIQUE = "uq_documents_id_tenant_enterprise"
RUN_SCOPE_UNIQUE = "uq_agent_run_logs_run_scope"
RUN_ENTERPRISE_SCOPE_FK = "fk_agent_run_logs_enterprise_tenant"
RUN_DOCUMENT_SCOPE_FK = "fk_agent_run_logs_source_file_scope"
EVENT_RUN_SCOPE_FK = "fk_agent_run_events_run_scope"


def _preflight() -> None:
    bind = op.get_bind()
    invalid_run_enterprises = bind.execute(
        sa.text(
            "SELECT count(*) FROM agent_run_logs r "
            "WHERE r.enterprise_id IS NOT NULL AND NOT EXISTS ("
            "SELECT 1 FROM enterprises e "
            "WHERE e.id = r.enterprise_id AND e.tenant_id = r.tenant_id)"
        )
    ).scalar_one()
    invalid_run_documents = bind.execute(
        sa.text(
            "SELECT count(*) FROM agent_run_logs r "
            "WHERE r.source_file_id IS NOT NULL AND NOT EXISTS ("
            "SELECT 1 FROM documents d WHERE d.id = r.source_file_id "
            "AND d.tenant_id = r.tenant_id AND d.enterprise_id = r.enterprise_id)"
        )
    ).scalar_one()
    invalid_events = bind.execute(
        sa.text(
            "SELECT count(*) FROM agent_run_events e WHERE NOT EXISTS ("
            "SELECT 1 FROM agent_run_logs r WHERE r.run_id = e.run_id "
            "AND r.tenant_id = e.tenant_id AND r.enterprise_id = e.enterprise_id)"
        )
    ).scalar_one()
    if invalid_run_enterprises or invalid_run_documents or invalid_events:
        raise RuntimeError(
            "038 AgentOps lineage preflight failed: "
            f"invalid_run_enterprises={invalid_run_enterprises}, "
            f"invalid_run_documents={invalid_run_documents}, "
            f"invalid_events={invalid_events}"
        )


def _upgrade_sqlite() -> None:
    # SQLite cannot add composite foreign keys without rebuilding live tables.
    # Equivalent insert/update guards keep legacy test and development databases
    # safe, while fresh databases also receive the model-level constraints.
    op.create_index(
        ENTERPRISE_SCOPE_UNIQUE,
        "enterprises",
        ["id", "tenant_id"],
        unique=True,
    )
    op.create_index(
        DOCUMENT_SCOPE_UNIQUE,
        "documents",
        ["id", "tenant_id", "enterprise_id"],
        unique=True,
    )
    op.create_index(
        RUN_SCOPE_UNIQUE,
        "agent_run_logs",
        ["run_id", "tenant_id", "enterprise_id"],
        unique=True,
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_agent_run_logs_scope_insert
            BEFORE INSERT ON agent_run_logs
            WHEN (
                NEW.enterprise_id IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM enterprises
                    WHERE id = NEW.enterprise_id AND tenant_id = NEW.tenant_id
                )
            ) OR (
                NEW.source_file_id IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM documents
                    WHERE id = NEW.source_file_id
                      AND tenant_id = NEW.tenant_id
                      AND enterprise_id = NEW.enterprise_id
                )
            )
            BEGIN
                SELECT RAISE(ABORT, 'agent run tenant lineage violated');
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_agent_run_logs_scope_update
            BEFORE UPDATE OF tenant_id, enterprise_id, source_file_id ON agent_run_logs
            WHEN (
                NEW.enterprise_id IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM enterprises
                    WHERE id = NEW.enterprise_id AND tenant_id = NEW.tenant_id
                )
            ) OR (
                NEW.source_file_id IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM documents
                    WHERE id = NEW.source_file_id
                      AND tenant_id = NEW.tenant_id
                      AND enterprise_id = NEW.enterprise_id
                )
            )
            BEGIN
                SELECT RAISE(ABORT, 'agent run tenant lineage violated');
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_agent_run_logs_terminal_no_update
            BEFORE UPDATE ON agent_run_logs
            WHEN OLD.status IN ('completed', 'failed', 'cancelled')
            BEGIN
                SELECT RAISE(ABORT, 'terminal agent runs are immutable');
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_agent_run_logs_no_delete
            BEFORE DELETE ON agent_run_logs
            BEGIN
                SELECT RAISE(ABORT, 'agent runs are audit records');
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_agent_run_events_scope_insert
            BEFORE INSERT ON agent_run_events
            WHEN NOT EXISTS (
                SELECT 1 FROM agent_run_logs
                WHERE run_id = NEW.run_id
                  AND tenant_id = NEW.tenant_id
                  AND enterprise_id = NEW.enterprise_id
                  AND status NOT IN ('completed', 'failed', 'cancelled')
            )
            BEGIN
                SELECT RAISE(ABORT, 'agent run event lineage or lifecycle violated');
            END
            """
        )
    )


def _upgrade_postgresql() -> None:
    op.create_unique_constraint(
        ENTERPRISE_SCOPE_UNIQUE,
        "enterprises",
        ["id", "tenant_id"],
    )
    op.create_unique_constraint(
        DOCUMENT_SCOPE_UNIQUE,
        "documents",
        ["id", "tenant_id", "enterprise_id"],
    )
    op.create_unique_constraint(
        RUN_SCOPE_UNIQUE,
        "agent_run_logs",
        ["run_id", "tenant_id", "enterprise_id"],
    )
    op.create_foreign_key(
        RUN_ENTERPRISE_SCOPE_FK,
        "agent_run_logs",
        "enterprises",
        ["enterprise_id", "tenant_id"],
        ["id", "tenant_id"],
    )
    op.create_foreign_key(
        RUN_DOCUMENT_SCOPE_FK,
        "agent_run_logs",
        "documents",
        ["source_file_id", "tenant_id", "enterprise_id"],
        ["id", "tenant_id", "enterprise_id"],
    )
    op.create_foreign_key(
        EVENT_RUN_SCOPE_FK,
        "agent_run_events",
        "agent_run_logs",
        ["run_id", "tenant_id", "enterprise_id"],
        ["run_id", "tenant_id", "enterprise_id"],
        ondelete="RESTRICT",
    )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION public.zcy_guard_agent_run_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'agent runs are audit records and cannot be deleted'
                        USING ERRCODE = '23514';
                END IF;
                IF OLD.status IN ('completed', 'failed', 'cancelled') THEN
                    RAISE EXCEPTION 'terminal agent runs are immutable'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END
            $$
            """
        )
    )
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_agent_run_logs_immutable ON agent_run_logs"))
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_agent_run_logs_immutable "
            "BEFORE UPDATE OR DELETE ON agent_run_logs "
            "FOR EACH ROW EXECUTE FUNCTION public.zcy_guard_agent_run_mutation()"
        )
    )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION public.zcy_guard_agent_run_event_insert()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM agent_run_logs r
                    WHERE r.run_id = NEW.run_id
                      AND r.tenant_id = NEW.tenant_id
                      AND r.enterprise_id = NEW.enterprise_id
                      AND r.status NOT IN ('completed', 'failed', 'cancelled')
                ) THEN
                    RAISE EXCEPTION 'agent run event lineage or lifecycle violated'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END
            $$
            """
        )
    )
    op.execute(
        sa.text("DROP TRIGGER IF EXISTS trg_agent_run_events_scope_insert ON agent_run_events")
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_agent_run_events_scope_insert "
            "BEFORE INSERT ON agent_run_events "
            "FOR EACH ROW EXECUTE FUNCTION public.zcy_guard_agent_run_event_insert()"
        )
    )


def upgrade() -> None:
    _preflight()
    if op.get_bind().dialect.name == "sqlite":
        _upgrade_sqlite()
    else:
        _upgrade_postgresql()


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        for trigger in (
            "trg_agent_run_events_scope_insert",
            "trg_agent_run_logs_no_delete",
            "trg_agent_run_logs_terminal_no_update",
            "trg_agent_run_logs_scope_update",
            "trg_agent_run_logs_scope_insert",
        ):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger}"))
        op.drop_index(RUN_SCOPE_UNIQUE, table_name="agent_run_logs")
        op.drop_index(DOCUMENT_SCOPE_UNIQUE, table_name="documents")
        op.drop_index(ENTERPRISE_SCOPE_UNIQUE, table_name="enterprises")
        return

    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_agent_run_events_scope_insert ON agent_run_events"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS public.zcy_guard_agent_run_event_insert()"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_agent_run_logs_immutable ON agent_run_logs"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS public.zcy_guard_agent_run_mutation()"))
    op.drop_constraint(EVENT_RUN_SCOPE_FK, "agent_run_events", type_="foreignkey")
    op.drop_constraint(RUN_DOCUMENT_SCOPE_FK, "agent_run_logs", type_="foreignkey")
    op.drop_constraint(RUN_ENTERPRISE_SCOPE_FK, "agent_run_logs", type_="foreignkey")
    op.drop_constraint(RUN_SCOPE_UNIQUE, "agent_run_logs", type_="unique")
    op.drop_constraint(DOCUMENT_SCOPE_UNIQUE, "documents", type_="unique")
    op.drop_constraint(ENTERPRISE_SCOPE_UNIQUE, "enterprises", type_="unique")
