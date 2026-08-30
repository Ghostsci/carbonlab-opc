"""Durable execution records for governed digital employees."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    DDL,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class AgentRunEventImmutableError(RuntimeError):
    """Raised when an append-only execution event is mutated or deleted."""


class AgentRunImmutableError(RuntimeError):
    """Raised when a terminal execution record is mutated or deleted."""


TERMINAL_AGENT_RUN_STATUSES = frozenset({"completed", "failed", "cancelled"})


class AgentRunLog(Base):
    """One concrete execution of a governed employee against a business task."""

    __tablename__ = "agent_run_logs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'waiting_human', 'completed', 'failed', 'cancelled')",
            name="ck_agent_run_logs_status",
        ),
        CheckConstraint("attempt_number >= 1", name="ck_agent_run_logs_attempt"),
        CheckConstraint(
            "skill_sha256 IS NULL OR length(skill_sha256) = 64",
            name="ck_agent_run_logs_skill_hash",
        ),
        UniqueConstraint(
            "run_id",
            "tenant_id",
            "enterprise_id",
            name="uq_agent_run_logs_run_scope",
        ),
        ForeignKeyConstraint(
            ["enterprise_id", "tenant_id"],
            ["enterprises.id", "enterprises.tenant_id"],
            name="fk_agent_run_logs_enterprise_tenant",
        ),
        ForeignKeyConstraint(
            ["source_file_id", "tenant_id", "enterprise_id"],
            ["documents.id", "documents.tenant_id", "documents.enterprise_id"],
            name="fk_agent_run_logs_source_file_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("tenants.id"),
        nullable=True,
        index=True,
    )
    enterprise_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("enterprises.id"),
        nullable=True,
        index=True,
    )
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("workflow_instances.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    workflow_step_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("workflow_steps.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    trigger: Mapped[str | None] = mapped_column(String(20), nullable=True)
    trigger_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    status_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    skill_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    skill_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    skill_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    redaction_version: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="trace-redaction-v1",
        server_default="trace-redaction-v1",
    )
    node_path: Mapped[list | None] = mapped_column(JSON, nullable=True)
    llm_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    human_intervention: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    final_action: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    input_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    eval_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cost_cny: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    execution_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    events: Mapped[list["AgentRunEvent"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AgentRunEvent.sequence",
    )


class AgentRunEvent(Base):
    """Append-only, hash-linked public trace event for one execution."""

    __tablename__ = "agent_run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_agent_run_events_run_sequence"),
        CheckConstraint("sequence >= 1", name="ck_agent_run_events_sequence"),
        CheckConstraint(
            "status IN ('info', 'running', 'success', 'warning', 'blocked', 'error')",
            name="ck_agent_run_events_status",
        ),
        CheckConstraint("length(event_sha256) = 64", name="ck_agent_run_events_hash"),
        CheckConstraint(
            "prev_event_sha256 IS NULL OR length(prev_event_sha256) = 64",
            name="ck_agent_run_events_prev_hash",
        ),
        ForeignKeyConstraint(
            ["run_id", "tenant_id", "enterprise_id"],
            [
                "agent_run_logs.run_id",
                "agent_run_logs.tenant_id",
                "agent_run_logs.enterprise_id",
            ],
            name="fk_agent_run_events_run_scope",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("enterprises.id"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    payload_json: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    evidence_refs: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    prev_event_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    run: Mapped[AgentRunLog] = relationship(back_populates="events")


@event.listens_for(AgentRunEvent, "before_update")
@event.listens_for(AgentRunEvent, "before_delete")
def _guard_agent_run_event_immutability(_mapper, _connection, _target) -> None:
    raise AgentRunEventImmutableError(
        "agent run events are append-only and cannot be changed or deleted"
    )


@event.listens_for(AgentRunLog, "before_update")
def _guard_terminal_agent_run_update(_mapper, _connection, target: AgentRunLog) -> None:
    state = inspect(target)
    status_history = state.attrs.status.history
    previous_status = (
        status_history.deleted[0]
        if status_history.deleted
        else target.status
    )
    if previous_status in TERMINAL_AGENT_RUN_STATUSES:
        raise AgentRunImmutableError(
            "terminal agent runs are immutable and cannot be changed"
        )


@event.listens_for(AgentRunLog, "before_delete")
def _guard_agent_run_delete(_mapper, _connection, _target) -> None:
    raise AgentRunImmutableError("agent runs are audit records and cannot be deleted")


event.listen(
    AgentRunLog.__table__,
    "after_create",
    DDL(
        """
        CREATE TRIGGER IF NOT EXISTS trg_agent_run_logs_scope_insert
        BEFORE INSERT ON agent_run_logs
        WHEN (
            NEW.enterprise_id IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM enterprises
                WHERE enterprises.id = NEW.enterprise_id
                  AND enterprises.tenant_id = NEW.tenant_id
            )
        ) OR (
            NEW.source_file_id IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM documents
                WHERE documents.id = NEW.source_file_id
                  AND documents.tenant_id = NEW.tenant_id
                  AND documents.enterprise_id = NEW.enterprise_id
            )
        )
        BEGIN
            SELECT RAISE(ABORT, 'agent run tenant lineage violated');
        END
        """
    ).execute_if(dialect="sqlite"),
)
event.listen(
    AgentRunLog.__table__,
    "after_create",
    DDL(
        """
        CREATE TRIGGER IF NOT EXISTS trg_agent_run_logs_scope_update
        BEFORE UPDATE OF tenant_id, enterprise_id, source_file_id ON agent_run_logs
        WHEN (
            NEW.enterprise_id IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM enterprises
                WHERE enterprises.id = NEW.enterprise_id
                  AND enterprises.tenant_id = NEW.tenant_id
            )
        ) OR (
            NEW.source_file_id IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM documents
                WHERE documents.id = NEW.source_file_id
                  AND documents.tenant_id = NEW.tenant_id
                  AND documents.enterprise_id = NEW.enterprise_id
            )
        )
        BEGIN
            SELECT RAISE(ABORT, 'agent run tenant lineage violated');
        END
        """
    ).execute_if(dialect="sqlite"),
)
event.listen(
    AgentRunLog.__table__,
    "after_create",
    DDL(
        """
        CREATE TRIGGER IF NOT EXISTS trg_agent_run_logs_terminal_no_update
        BEFORE UPDATE ON agent_run_logs
        WHEN OLD.status IN ('completed', 'failed', 'cancelled')
        BEGIN
            SELECT RAISE(ABORT, 'terminal agent runs are immutable');
        END
        """
    ).execute_if(dialect="sqlite"),
)
event.listen(
    AgentRunLog.__table__,
    "after_create",
    DDL(
        """
        CREATE TRIGGER IF NOT EXISTS trg_agent_run_logs_no_delete
        BEFORE DELETE ON agent_run_logs
        BEGIN
            SELECT RAISE(ABORT, 'agent runs are audit records');
        END
        """
    ).execute_if(dialect="sqlite"),
)


event.listen(
    AgentRunEvent.__table__,
    "after_create",
    DDL(
        """
        CREATE TRIGGER IF NOT EXISTS trg_agent_run_events_scope_insert
        BEFORE INSERT ON agent_run_events
        WHEN NOT EXISTS (
            SELECT 1 FROM agent_run_logs
            WHERE agent_run_logs.run_id = NEW.run_id
              AND agent_run_logs.tenant_id = NEW.tenant_id
              AND agent_run_logs.enterprise_id = NEW.enterprise_id
              AND agent_run_logs.status NOT IN ('completed', 'failed', 'cancelled')
        )
        BEGIN
            SELECT RAISE(ABORT, 'agent run event lineage or lifecycle violated');
        END
        """
    ).execute_if(dialect="sqlite"),
)
event.listen(
    AgentRunEvent.__table__,
    "after_create",
    DDL(
        """
        CREATE TRIGGER IF NOT EXISTS trg_agent_run_events_no_update
        BEFORE UPDATE ON agent_run_events
        BEGIN
            SELECT RAISE(ABORT, 'agent run events are append-only');
        END
        """
    ).execute_if(dialect="sqlite"),
)
event.listen(
    AgentRunEvent.__table__,
    "after_create",
    DDL(
        """
        CREATE TRIGGER IF NOT EXISTS trg_agent_run_events_no_delete
        BEFORE DELETE ON agent_run_events
        BEGIN
            SELECT RAISE(ABORT, 'agent run events are append-only');
        END
        """
    ).execute_if(dialect="sqlite"),
)
