"""Multi-tenant model — Tenant, branding, and tenant-user relationship."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from backend.models.user import User


class Tenant(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True,
        comment="URL-safe tenant identifier for subdomain/dashboard routing"
    )
    domain: Mapped[str | None] = mapped_column(
        String(255), unique=True,
        comment="Custom domain for white-label (e.g. carbon.acme-corp.com)"
    )
    plan: Mapped[str] = mapped_column(
        String(20), nullable=False, default="free",
        comment="free / pro / enterprise"
    )
    contact_email: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(20))

    # White-label branding
    branding: Mapped[dict | None] = mapped_column(
        JSON, comment="logo_url / primary_color / secondary_color / company_name / favicon_url"
    )

    # Feature overrides (for custom enterprise plans)
    feature_overrides: Mapped[dict | None] = mapped_column(
        JSON, comment="manual overrides to plan-based feature flags"
    )

    users: Mapped[list["User"]] = relationship(back_populates="tenant")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "slug": self.slug,
            "domain": self.domain,
            "plan": self.plan,
            "contact_email": self.contact_email,
            "contact_phone": self.contact_phone,
            "branding": self.branding,
            "feature_overrides": self.feature_overrides,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
