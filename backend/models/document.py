import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from backend.models.enterprise import Enterprise


class DocumentStore(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "enterprise_id",
            "content_hash",
            name="uq_documents_tenant_enterprise_content_hash",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("enterprises.id"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    doc_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="invoice / electricity_bill / production_report / verification_report"
    )
    ocr_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending",
        comment="pending / processing / completed / failed"
    )
    ocr_result: Mapped[dict | None] = mapped_column(JSON, comment="extracted fields")
    ocr_error: Mapped[str | None] = mapped_column()

    enterprise: Mapped["Enterprise"] = relationship(back_populates="documents")
