import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, ForeignKeyConstraint, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from backend.models.site import Site
    from backend.models.activity_data import ActivityData


class EmissionSource(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "emission_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["site_id", "tenant_id"],
            ["sites.id", "sites.tenant_id"],
            name="fk_emission_sources_site_tenant",
        ),
    )

    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scope: Mapped[str] = mapped_column(String(10), nullable=False, comment="scope_1 / scope_2")
    category: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="stationary_combustion / mobile_combustion / purchased_electricity / purchased_heat"
    )
    fuel_type: Mapped[str | None] = mapped_column(
        String(50), comment="coal / natural_gas / diesel / gasoline"
    )
    source_code: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True,
        comment="e.g. SRC-001-STATIONARY, SRC-002-ELECTRICITY"
    )

    site: Mapped["Site"] = relationship(
        back_populates="emission_sources",
        foreign_keys=[site_id, tenant_id],
    )
    activity_data: Mapped[list["ActivityData"]] = relationship(
        back_populates="emission_source", cascade="all, delete-orphan"
    )
