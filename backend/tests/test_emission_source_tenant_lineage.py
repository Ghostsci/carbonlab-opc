"""Database-contract tests for tenant-owned emission sources."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import Base
from backend.models.emission_source import EmissionSource
from backend.models.enterprise import Enterprise
from backend.models.site import Site
from backend.models.tenant import Tenant


def test_database_rejects_emission_source_linked_to_site_in_another_tenant():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        tenant_a = Tenant(name="租户 A", slug=f"tenant-a-{uuid.uuid4().hex[:8]}")
        tenant_b = Tenant(name="租户 B", slug=f"tenant-b-{uuid.uuid4().hex[:8]}")
        db.add_all([tenant_a, tenant_b])
        db.flush()
        enterprise_a = Enterprise(
            name="租户 A 企业",
            unified_social_credit_code=f"91{uuid.uuid4().hex[:16].upper()}",
            industry_code="C31",
            industry_name="黑色金属冶炼和压延加工业",
            tenant_id=tenant_a.id,
        )
        db.add(enterprise_a)
        db.flush()
        site_a = Site(
            enterprise_id=enterprise_a.id,
            tenant_id=tenant_a.id,
            name="租户 A 工厂",
            address="测试地址",
            province="江苏",
            city="苏州",
            grid_region="华东",
        )
        db.add(site_a)
        db.flush()
        db.add(
            EmissionSource(
                site_id=site_a.id,
                tenant_id=tenant_b.id,
                name="伪造跨租户排放源",
                scope="scope_2",
                category="purchased_electricity",
                source_code=f"CROSS-{uuid.uuid4().hex[:12]}",
            )
        )

        with pytest.raises(IntegrityError):
            db.commit()
