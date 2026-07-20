import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from backend.models.enterprise import Enterprise
    from backend.models.emission_source import EmissionSource


class Site(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "sites"

    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("enterprises.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    province: Mapped[str] = mapped_column(String(50), nullable=False)
    city: Mapped[str] = mapped_column(String(50), nullable=False)
    grid_region: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="华北/东北/华东/华中/西北/南方"
    )
    longitude: Mapped[float | None] = mapped_column()
    latitude: Mapped[float | None] = mapped_column()
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True
    )

    enterprise: Mapped["Enterprise"] = relationship(back_populates="sites")
    emission_sources: Mapped[list["EmissionSource"]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )
