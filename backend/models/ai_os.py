"""AI-native operating system models.

These tables capture the durable state that sits above individual agent runs:
agent identity/contracts, workflow state, reusable memory, and assembled context
packs.  They intentionally do not store prompts or raw model responses unless a
caller explicitly places redacted snapshots into JSON fields.
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from backend.models.enterprise import Enterprise
    from backend.models.tenant import Tenant
    from backend.models.user import User


class AgentProfile(Base, UUIDMixin, TimestampMixin):
    """Governed identity and contract for one AI agent persona/version."""

    __tablename__ = "agent_profiles"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=True, index=True
    )
    profile_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="v1")
    role: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="active | paused | archived",
    )
    capability_tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    model_preferences: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tool_allowlist: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    input_contract: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_contract: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    guardrails: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )


class WorkflowInstance(Base, UUIDMixin, TimestampMixin):
    """Tenant-local business workflow state visible to users and agents."""

    __tablename__ = "workflow_instances"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=False, index=True
    )
    enterprise_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("enterprises.id"), nullable=True, index=True
    )
    workflow_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    workflow_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="active",
        comment="draft | active | blocked | review | completed | archived",
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="medium",
        comment="low | medium | high | critical",
    )
    phase: Mapped[str] = mapped_column(String(80), nullable=False, default="data_collection")
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_step_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    steps: Mapped[list["WorkflowStep"]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="WorkflowStep.sort_order",
    )


class WorkflowStep(Base, UUIDMixin, TimestampMixin):
    """One auditable step inside a workflow instance."""

    __tablename__ = "workflow_steps"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=False, index=True
    )
    step_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        comment="pending | in_progress | blocked | review | completed | skipped",
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    agent_profile_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default="low")
    inputs_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    outputs_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    checkpoints_json: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workflow: Mapped["WorkflowInstance"] = relationship(back_populates="steps")


class AIMemory(Base, UUIDMixin, TimestampMixin):
    """Tenant memory for facts, corrections, preferences, and audit learnings."""

    __tablename__ = "ai_memories"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=True, index=True
    )
    enterprise_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("enterprises.id"), nullable=True, index=True
    )
    memory_type: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        index=True,
        comment="fact | correction | preference | risk | decision | eval_learning",
    )
    subject_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="tenant",
        comment="global | tenant | enterprise | private",
    )
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    source_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        comment="active | superseded | archived",
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ContextPackRecord(Base):
    """Persisted, redacted context package passed into an agent run."""

    __tablename__ = "context_pack_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=True, index=True
    )
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("workflow_instances.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_profile_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    pack_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(120), nullable=False, default="agent_run")
    input_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assembled_context: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_refs: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    policy_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
