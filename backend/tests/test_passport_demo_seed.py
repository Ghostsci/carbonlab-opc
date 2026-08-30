"""Regression coverage for the idempotent passport demo data factory."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.activity_data import ActivityData
from backend.models.cbam_ledger import (
    CBAMProduct,
    Installation,
    ProductionOutput,
    ProductionProcess,
    SEEResult,
    SourceStreamAttribution,
)
from backend.models.document import DocumentStore
from backend.models.emission_factor import EmissionFactor
from backend.models.emission_result import EmissionResult
from backend.models.emission_source import EmissionSource
from backend.models.enterprise import Enterprise
from backend.models.installation_passport import (
    DataSharingGrant,
    InstallationAccount,
    InstallationAccountMember,
    InstallationProfileVersion,
    MethodologyReview,
    ProfileDistributionEvent,
)
from backend.models.rule_record import RuleRecord
from backend.models.site import Site
from backend.models.tenant import Tenant
from backend.models.user import User
from backend.services.activity_ingestion import _find_electricity_factor
from backend.services.installation_passport import replay_profile_version
import scripts.seed_passport_demo as seed


class _MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def upload(self, object_name: str, data: bytes, _content_type: str) -> str:
        self.objects[object_name] = data
        return object_name

    def download(self, object_name: str) -> bytes | None:
        return self.objects.get(object_name)

    def exists(self, object_name: str) -> bool:
        return object_name in self.objects


_SEEDED_MODELS = (
    Tenant,
    Enterprise,
    User,
    EmissionFactor,
    DocumentStore,
    Site,
    EmissionSource,
    ActivityData,
    EmissionResult,
    InstallationAccount,
    InstallationAccountMember,
    Installation,
    ProductionProcess,
    CBAMProduct,
    ProductionOutput,
    SourceStreamAttribution,
    RuleRecord,
    SEEResult,
    InstallationProfileVersion,
    MethodologyReview,
    DataSharingGrant,
    ProfileDistributionEvent,
)


def _seeded_ids(db) -> dict[str, tuple[str, ...]]:
    return {
        model.__tablename__: tuple(
            sorted(str(item.id) for item in db.query(model).all())
        )
        for model in _SEEDED_MODELS
    }


def test_seed_builds_both_demo_paths_once_and_reuses_them(tmp_path, monkeypatch):
    monkeypatch.setattr(seed, "PASSWORD", "unit-test-only-password")
    engine = create_engine(f"sqlite:///{tmp_path / 'passport-demo-seed.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    storage = _MemoryStorage()
    monkeypatch.setattr(seed, "get_sessionmaker", lambda: SessionLocal)
    monkeypatch.setattr(seed, "get_storage", lambda: storage)

    try:
        seed.main()
        with SessionLocal() as db:
            first_ids = _seeded_ids(db)
            counts = {table: len(ids) for table, ids in first_ids.items()}
            assert counts == {
                "tenants": 1,
                "enterprises": 1,
                "users": 1,
                "emission_factors": 1,
                "documents": 2,
                "sites": 6,
                "emission_sources": 2,
                "activity_data": 2,
                "emission_results": 2,
                "installation_accounts": 2,
                "installation_account_members": 2,
                "cbam_installations": 2,
                "cbam_production_processes": 2,
                "cbam_products": 2,
                "cbam_production_outputs": 2,
                "cbam_source_stream_attributions": 2,
                "rule_records": 1,
                "cbam_see_results": 1,
                "installation_profile_versions": 3,
                "methodology_reviews": 1,
                "data_sharing_grants": 1,
                "profile_distribution_events": 1,
            }

            factor = db.query(EmissionFactor).filter_by(code=seed.FACTOR_CODE).one()
            assert factor.region == seed.DEMO_FACTOR_REGION
            assert factor.is_default is True
            demo_tenant = db.query(Tenant).filter(Tenant.slug == seed.TENANT_SLUG).one()
            demo_sites = db.query(Site).filter(Site.tenant_id == demo_tenant.id).all()
            assert {item.name for item in demo_sites} == {
                seed.INCOMPLETE_FACILITY,
                seed.REFERENCE_FACILITY,
                *seed.COMPETITION_DEMO_FACILITIES,
            }
            assert {item.grid_region for item in demo_sites} == {
                seed.DEMO_FACTOR_REGION
            }
            assert {item.factor_id for item in db.query(EmissionResult).all()} == {
                factor.id
            }

            incomplete = (
                db.query(InstallationAccount)
                .filter(InstallationAccount.request_key == seed.INCOMPLETE_REQUEST_KEY)
                .one()
            )
            incomplete_profiles = (
                db.query(InstallationProfileVersion)
                .filter(InstallationProfileVersion.account_id == incomplete.id)
                .all()
            )
            assert len(incomplete_profiles) == 1
            assert incomplete_profiles[0].status == "draft"
            assert incomplete_profiles[0].snapshot_json["see_results"] == []
            assert incomplete_profiles[0].snapshot_json["rule_records"] == []
            assert incomplete_profiles[0].snapshot_json["methodology_review"] is None

            complete = (
                db.query(InstallationAccount)
                .filter(InstallationAccount.request_key == seed.REFERENCE_REQUEST_KEY)
                .one()
            )
            complete_profiles = (
                db.query(InstallationProfileVersion)
                .filter(InstallationProfileVersion.account_id == complete.id)
                .order_by(InstallationProfileVersion.version)
                .all()
            )
            assert [item.status for item in complete_profiles] == ["draft", "published"]
            assert complete_profiles[0].assessment_json["missing_keys"] == [
                "methodology_review"
            ]
            published = complete_profiles[1]
            assert published.completeness_score == 100
            assert replay_profile_version(
                db,
                tenant_id=published.tenant_id,
                profile_version_id=published.id,
            )["match"] is True
            assert "DEMO ONLY" in published.snapshot_json["installation"]["name"]
            assert "未独立认证" in published.snapshot_json["rule_records"][0]["title"]
            assert published.snapshot_json["methodology_review"]["disclaimer"] == (
                "方法学复核不等于法定 CBAM 核查"
            )

            output = (
                db.query(ProductionOutput)
                .join(ProductionProcess, ProductionProcess.id == ProductionOutput.process_id)
                .filter(ProductionProcess.name.like("DEMO ONLY%"))
                .one()
            )
            attribution = (
                db.query(SourceStreamAttribution)
                .filter(SourceStreamAttribution.process_id == output.process_id)
                .one()
            )
            assert output.quantity == Decimal("1000")
            assert attribution.share == Decimal("1")

            grant = db.query(DataSharingGrant).one()
            assert grant.recipient_tenant_id is None
            assert grant.recipient_type == "other"
            assert grant.scopes_json == ["emissions"]
            assert "非真实客户交付" in grant.purpose
            event = db.query(ProfileDistributionEvent).one()
            assert event.grant_id == grant.id
            assert event.channel == "json_export"

            documents = db.query(DocumentStore).order_by(DocumentStore.filename).all()
            assert {item.ocr_result["confidence"] for item in documents} == {0.91, 0.98}
            assert all(item.ocr_result["raw_text"] for item in documents)

        assert storage.objects == {
            "demo/passport/electricity-q1-demo.csv": seed.INCOMPLETE_DOCUMENT_CONTENT,
            "demo/passport/reference-complete-electricity-q1-demo-only.csv": (
                seed.REFERENCE_DOCUMENT_CONTENT
            ),
        }

        seed.main()
        with SessionLocal() as db:
            assert _seeded_ids(db) == first_ids
            assert db.query(ProfileDistributionEvent).count() == 1
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_repeat_seed_migrates_only_known_demo_factor_and_sites(tmp_path, monkeypatch):
    monkeypatch.setattr(seed, "PASSWORD", "unit-test-only-password")
    engine = create_engine(f"sqlite:///{tmp_path / 'passport-demo-migration.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    storage = _MemoryStorage()
    monkeypatch.setattr(seed, "get_sessionmaker", lambda: SessionLocal)
    monkeypatch.setattr(seed, "get_storage", lambda: storage)

    try:
        seed.main()
        with SessionLocal.begin() as db:
            demo_tenant = db.query(Tenant).filter(Tenant.slug == seed.TENANT_SLUG).one()
            demo_factor = (
                db.query(EmissionFactor).filter(EmissionFactor.code == seed.FACTOR_CODE).one()
            )
            demo_factor.region = seed.LEGACY_DEMO_FACTOR_REGION
            demo_factor.is_default = True

            demo_sites = (
                db.query(Site)
                .filter(
                    Site.tenant_id == demo_tenant.id,
                    Site.name.in_([seed.INCOMPLETE_FACILITY, seed.REFERENCE_FACILITY]),
                )
                .all()
            )
            assert len(demo_sites) == 2
            for site in demo_sites:
                site.grid_region = seed.LEGACY_DEMO_FACTOR_REGION

            real_tenant = Tenant(
                name="真实租户",
                slug="real-factor-isolation",
                plan="enterprise",
            )
            db.add(real_tenant)
            db.flush()
            real_enterprise = Enterprise(
                name="真实企业",
                unified_social_credit_code="91130200REAL000001",
                industry_code="C3110",
                industry_name="黑色金属冶炼和压延加工业",
                tenant_id=real_tenant.id,
            )
            db.add(real_enterprise)
            db.flush()
            east_site = Site(
                enterprise_id=real_enterprise.id,
                tenant_id=real_tenant.id,
                name=seed.INCOMPLETE_FACILITY,
                address="真实华东地址",
                province="江苏",
                city="苏州",
                grid_region="华东",
            )
            national_site = Site(
                enterprise_id=real_enterprise.id,
                tenant_id=real_tenant.id,
                name=seed.REFERENCE_FACILITY,
                address="真实全国地址",
                province="北京",
                city="北京",
                grid_region="全国",
            )
            db.add_all([east_site, national_site])
            db.flush()
            east_source = EmissionSource(
                site_id=east_site.id,
                tenant_id=real_tenant.id,
                name="真实华东外购电力",
                scope="scope_2",
                category="purchased_electricity",
                source_code="REAL-EAST-ELEC",
            )
            national_source = EmissionSource(
                site_id=national_site.id,
                tenant_id=real_tenant.id,
                name="真实全国外购电力",
                scope="scope_2",
                category="purchased_electricity",
                source_code="REAL-NATIONAL-ELEC",
            )
            db.add_all([east_source, national_source])
            db.flush()
            east_site_id = east_site.id
            national_site_id = national_site.id
            east_source_id = east_source.id
            national_source_id = national_source.id
            real_tenant_id = real_tenant.id

        seed.main()
        with SessionLocal() as db:
            demo_factor = (
                db.query(EmissionFactor).filter(EmissionFactor.code == seed.FACTOR_CODE).one()
            )
            assert demo_factor.region == seed.DEMO_FACTOR_REGION
            assert demo_factor.is_default is True

            demo_tenant = db.query(Tenant).filter(Tenant.slug == seed.TENANT_SLUG).one()
            demo_sites = (
                db.query(Site)
                .filter(
                    Site.tenant_id == demo_tenant.id,
                    Site.name.in_([seed.INCOMPLETE_FACILITY, seed.REFERENCE_FACILITY]),
                )
                .all()
            )
            assert {item.grid_region for item in demo_sites} == {
                seed.DEMO_FACTOR_REGION
            }

            assert db.get(Site, east_site_id).grid_region == "华东"
            assert db.get(Site, national_site_id).grid_region == "全国"
            assert (
                _find_electricity_factor(
                    db,
                    source=db.get(EmissionSource, east_source_id),
                    period_start=seed.PERIOD_START,
                    tenant_id=real_tenant_id,
                )
                is None
            )
            assert (
                _find_electricity_factor(
                    db,
                    source=db.get(EmissionSource, national_source_id),
                    period_start=seed.PERIOD_START,
                    tenant_id=real_tenant_id,
                )
                is None
            )
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
