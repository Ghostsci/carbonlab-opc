import uuid
from decimal import Decimal
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.core.db_types import ExactDecimal
from backend.models.base import TimestampMixin, UUIDMixin
from backend.models.ledger import LedgerRecordMixin

if TYPE_CHECKING:
    from backend.models.emission_source import EmissionSource


class EmissionResult(Base, UUIDMixin, TimestampMixin, LedgerRecordMixin):
    __tablename__ = "emission_results"

    emission_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("emission_sources.id"), nullable=False, index=True
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scope: Mapped[str] = mapped_column(String(10), nullable=False)
    co2_tonnes: Mapped[Decimal] = mapped_column(ExactDecimal(28, 12), nullable=False)
    unit: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="tCO2 or tCO2e; never implicitly interchangeable",
    )
    uncertainty_pct: Mapped[float | None] = mapped_column(Float)
    confidence_95_low: Mapped[float | None] = mapped_column(Float)
    confidence_95_high: Mapped[float | None] = mapped_column(Float)

    factor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("emission_factors.id")
    )
    activity_data_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity_data.id")
    )
    audit_trail: Mapped[dict | None] = mapped_column(JSON, comment="step-by-step calculation trace")

    emission_source: Mapped["EmissionSource"] = relationship()
