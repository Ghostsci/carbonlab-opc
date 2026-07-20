import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.core.db_types import ExactDecimal
from backend.models.base import TimestampMixin, UUIDMixin
from backend.models.ledger import LedgerRecordMixin

if TYPE_CHECKING:
    from backend.models.emission_source import EmissionSource


class ActivityData(Base, UUIDMixin, LedgerRecordMixin):
    __tablename__ = "activity_data"

    emission_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("emission_sources.id"), nullable=False, index=True
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(ExactDecimal(28, 12), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False, comment="Quantity unit")
    data_source: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="manual / ocr / erp / meter"
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), comment="source document reference"
    )
    notes: Mapped[str | None] = mapped_column(String(500))

    emission_source: Mapped["EmissionSource"] = relationship(back_populates="activity_data")
