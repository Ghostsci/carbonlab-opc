import uuid
from decimal import Decimal
from datetime import date

from sqlalchemy import String, Numeric, Float, Integer, Boolean, Text, Date, Uuid, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.base import TimestampMixin, UUIDMixin


class EmissionFactor(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "emission_factors"

    # ``NULL`` means a platform-governed reference factor that every tenant may
    # read but no tenant runtime role may mutate.  A non-null value represents
    # a tenant-private factor.  PostgreSQL RLS enforces that distinction; the
    # explicit mapping keeps SQLite tests and service-level checks equivalent.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("tenants.id"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    category: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="fuel / electricity_grid / heat / process / transport"
    )
    fuel_type: Mapped[str | None] = mapped_column(String(50))
    region: Mapped[str | None] = mapped_column(
        String(50), comment="华北/东北/华东/华中/西北/南方/全国"
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    version_year: Mapped[int | None] = mapped_column(Integer, index=True)
    published_date: Mapped[date | None] = mapped_column(Date)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("emission_factors.id"), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    change_note: Mapped[str | None] = mapped_column(Text)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False, comment="kgCO2/kWh / kgCO2/kg / tCO2/TJ")
    source: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="IPCC EFDB / NDRC / EEA"
    )
    gwp: Mapped[str | None] = mapped_column(String(10), comment="AR5 / AR6")
    uncertainty: Mapped[float | None] = mapped_column(Float, comment="± percentage")
