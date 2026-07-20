import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Float, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from backend.models.enterprise import Enterprise


class CBAMReport(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "cbam_reports"

    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("enterprises.id"), nullable=False, index=True
    )
    report_period_start: Mapped[str] = mapped_column(String(7), nullable=False, comment="YYYY-MM")
    report_period_end: Mapped[str] = mapped_column(String(7), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft",
        comment="draft / calculated / reviewed / submitted"
    )
    total_embedded_emissions: Mapped[float | None] = mapped_column(Float, comment="tCO2 total")
    cbam_cost_eur: Mapped[float | None] = mapped_column(Float, comment="estimated CBAM cost in EUR")
    report_xml: Mapped[str | None] = mapped_column(comment="CBAM XML per EU schema")

    enterprise: Mapped["Enterprise"] = relationship(back_populates="cbam_reports")
    products: Mapped[list["Product"]] = relationship(back_populates="cbam_report", cascade="all, delete-orphan")


class Product(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "products"

    cbam_report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cbam_reports.id"), nullable=False, index=True
    )
    cn_code: Mapped[str] = mapped_column(String(10), nullable=False, comment="CN combined nomenclature code")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity_tonnes: Mapped[float] = mapped_column(Float, nullable=False)
    direct_emissions: Mapped[float | None] = mapped_column(Float, comment="tCO2, scope 1")
    indirect_emissions: Mapped[float | None] = mapped_column(Float, comment="tCO2, scope 2")
    precursor_emissions: Mapped[float | None] = mapped_column(Float, comment="tCO2 from precursors")
    default_value: Mapped[float | None] = mapped_column(Float, comment="EU default value for comparison")
    specific_embedded_emissions: Mapped[float | None] = mapped_column(Float, comment="tCO2/tonne product")

    cbam_report: Mapped["CBAMReport"] = relationship(back_populates="products")


class EmbeddedEmission(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "embedded_emissions"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="direct / indirect / precursor"
    )
    emission_factor_code: Mapped[str] = mapped_column(String(50), nullable=False)
    activity_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    activity_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    emission_tonnes: Mapped[float] = mapped_column(Float, nullable=False)
    is_actual: Mapped[bool] = mapped_column(Boolean, default=True, comment="actual vs default value")
