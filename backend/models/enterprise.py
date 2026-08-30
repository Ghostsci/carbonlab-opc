import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from backend.models.site import Site
    from backend.models.cbam import CBAMReport
    from backend.models.document import DocumentStore
    from backend.models.user import User


class Enterprise(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "enterprises"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_enterprises_id_tenant"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unified_social_credit_code: Mapped[str] = mapped_column(
        String(18), unique=True, nullable=False, index=True
    )
    industry_code: Mapped[str] = mapped_column(String(10), nullable=False)
    industry_name: Mapped[str] = mapped_column(String(100), nullable=False)
    contact_person: Mapped[str | None] = mapped_column(String(100))
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True
    )

    sites: Mapped[list["Site"]] = relationship(back_populates="enterprise", cascade="all, delete-orphan")
    cbam_reports: Mapped[list["CBAMReport"]] = relationship(back_populates="enterprise", cascade="all, delete-orphan")
    documents: Mapped[list["DocumentStore"]] = relationship(back_populates="enterprise", cascade="all, delete-orphan")
    users: Mapped[list["User"]] = relationship(back_populates="enterprise")
