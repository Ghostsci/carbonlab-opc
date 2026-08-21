#!/usr/bin/env python3
"""Seed two explicitly synthetic passports for local product demonstrations.

The first passport intentionally remains incomplete for the "待用户完成" path.
The second is a complete reference workflow, but every user-visible boundary is
marked DEMO ONLY / non-regulatory. Neither passport represents a real customer,
an independently authenticated rule, statutory verification, or real delivery.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import os
import uuid

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from backend.database import get_sessionmaker
from backend.models.activity_data import ActivityData
from backend.models.document import DocumentStore
from backend.models.emission_factor import EmissionFactor
from backend.models.emission_result import EmissionResult
from backend.models.enterprise import Enterprise
from backend.models.installation_passport import (
    DataSharingGrant,
    DataSharingRevocation,
    InstallationAccount,
    InstallationProfileVersion,
    MethodologyReview,
    ProfileDistributionEvent,
)
from backend.models.site import Site
from backend.models.tenant import Tenant
from backend.models.user import User
from backend.services.activity_ingestion import (
    DEFAULT_ADDRESS,
    DEFAULT_CITY,
    DEFAULT_PROVINCE,
    persist_confirmed_activity,
)
from backend.services.installation_passport import (
    add_production_output,
    add_source_attribution,
    calculate_passport_see,
    create_methodology_review,
    create_passport_account,
    create_profile_snapshot,
    create_sharing_grant,
    export_shared_package,
    passport_detail,
    publish_profile_version,
    register_authoritative_rule,
    replay_profile_version,
)
from backend.services.storage import get_storage


EMAIL = "demo@huasheng-steel.com"
PASSWORD = os.environ.get("CARBONLAB_DEMO_PASSWORD")
TENANT_SLUG = "huasheng-passport-demo"
ENTERPRISE_CODE = "91130200DEMO000001"

INCOMPLETE_REQUEST_KEY = "passport-demo-2026-q1-v1"
REFERENCE_REQUEST_KEY = "passport-demo-reference-2026-q1-v1"
FACTOR_CODE = "DEMO-ELEC-2026-NOT-REGULATORY"
DEMO_FACTOR_REGION = "DEMO_ONLY"
LEGACY_DEMO_FACTOR_REGION = "华东"

PERIOD_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
PERIOD_END = datetime(2026, 3, 31, 23, 59, 59, tzinfo=timezone.utc)
RULE_VALID_FROM = datetime(2023, 5, 17, tzinfo=timezone.utc)
GRANT_EXPIRES_AT = datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

INCOMPLETE_FACILITY = "热轧卷板生产装置（演示）"
REFERENCE_FACILITY = "DEMO ONLY｜完整参考装置（非监管用途）"
REFERENCE_RECIPIENT = "DEMO ONLY｜虚构外部演示接收方（非真实客户）"
REFERENCE_GRANT_PURPOSE = (
    "DEMO ONLY｜仅演示最小字段导出；非真实客户交付、非监管申报"
)
REFERENCE_REVIEW_SUMMARY = (
    "DEMO ONLY：仅复核合成数据边界、100% 归集与确定性重放；"
    "不构成法定 CBAM 核查，也不构成规则真实性的独立认证。"
)
REFERENCE_REVIEW_FINDINGS = [
    {
        "severity": "notice",
        "code": "demo_only_non_regulatory",
        "message": "合成参考数据，仅用于产品演示；不得用于申报或真实交付。",
    }
]

INCOMPLETE_DOCUMENT_CONTENT = (
    "DEMO ONLY,NOT FOR REPORTING\n"
    "period,electricity_kwh,facility\n"
    "2026-Q1,2000000,热轧卷板生产装置（演示）\n"
).encode("utf-8")

REFERENCE_DOCUMENT_CONTENT = (
    "notice,DEMO ONLY / 非监管用途 / 合成数据 / 非真实客户交付\n"
    "period,electricity_kwh,facility\n"
    "2026-Q1,2000000,DEMO ONLY｜完整参考装置（非监管用途）\n"
).encode("utf-8")

REFERENCE_RULE_DESCRIPTOR = (
    "DEMO ONLY / NON-REGULATORY workflow metadata fixture. "
    "It points to the European Commission publication only to exercise the "
    "RuleRecord service boundary; it does not authenticate, certify, or mirror "
    "the official source document."
).encode("utf-8")


def _ensure_identity(db: Session) -> tuple[Tenant, Enterprise, User]:
    user = db.query(User).filter(User.email == EMAIL).first()
    if user is not None:
        tenant = db.get(Tenant, user.tenant_id)
        enterprise = db.get(Enterprise, user.enterprise_id)
        if tenant is None or enterprise is None:
            raise RuntimeError("existing demo user has a broken tenant/enterprise binding")
        if enterprise.tenant_id != tenant.id:
            raise RuntimeError("existing demo enterprise belongs to a different tenant")
        return tenant, enterprise, user

    tenant = db.query(Tenant).filter(Tenant.slug == TENANT_SLUG).first()
    if tenant is None:
        tenant = Tenant(
            name="华盛钢铁有限公司（演示租户）",
            slug=TENANT_SLUG,
            plan="enterprise",
            contact_email=EMAIL,
            branding={
                "company_name": "华盛钢铁有限公司（DEMO ONLY / 非真实客户）"
            },
            feature_overrides={"demo": True, "passport": True},
        )
        db.add(tenant)
        db.flush()

    enterprise = (
        db.query(Enterprise)
        .filter(
            Enterprise.tenant_id == tenant.id,
            Enterprise.unified_social_credit_code == ENTERPRISE_CODE,
        )
        .first()
    )
    if enterprise is None:
        conflicting_enterprise = (
            db.query(Enterprise)
            .filter(Enterprise.unified_social_credit_code == ENTERPRISE_CODE)
            .first()
        )
        if conflicting_enterprise is not None:
            raise RuntimeError("demo enterprise code is already bound to another tenant")
        enterprise = Enterprise(
            name="华盛钢铁有限公司（演示）",
            unified_social_credit_code=ENTERPRISE_CODE,
            industry_code="C3110",
            industry_name="黑色金属冶炼和压延加工业",
            tenant_id=tenant.id,
            contact_person="张路宁（演示）",
            contact_email=EMAIL,
        )
        db.add(enterprise)
        db.flush()

    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    user = User(
        email=EMAIL,
        password_hash=pwd.hash(PASSWORD),
        role="admin",
        tenant_id=tenant.id,
        enterprise_id=enterprise.id,
    )
    db.add(user)
    db.flush()
    return tenant, enterprise, user


def _ensure_demo_factor(db: Session) -> EmissionFactor:
    matches = db.query(EmissionFactor).filter(EmissionFactor.code == FACTOR_CODE).all()
    if len(matches) > 1:
        raise RuntimeError(f"multiple emission factors use demo code {FACTOR_CODE}")
    if matches:
        factor = matches[0]
        expected_content = (
            factor.name == "演示电力因子（非监管用途）"
            and factor.category == "electricity_grid"
            and factor.year == 2026
            and Decimal(str(factor.value)) == Decimal("0.5")
            and factor.unit == "kgCO2e/kWh"
            and factor.source == "DEMO ONLY — synthetic factor; not for reporting"
        )
        known_region_state = (factor.region, bool(factor.is_default)) in {
            (LEGACY_DEMO_FACTOR_REGION, True),
            (DEMO_FACTOR_REGION, False),
            (DEMO_FACTOR_REGION, True),
        }
        if not expected_content or not known_region_state:
            raise RuntimeError("existing demo factor code is bound to different content")
        factor.region = DEMO_FACTOR_REGION
        # Safe only because both the factor and seeded sites use the synthetic
        # DEMO_ONLY region.  This makes the interactive demo calculable without
        # allowing the fixture to match any real regional activity.
        factor.is_default = True
        db.flush()
        return factor

    factor = EmissionFactor(
        name="演示电力因子（非监管用途）",
        code=FACTOR_CODE,
        category="electricity_grid",
        region=DEMO_FACTOR_REGION,
        year=2026,
        version_year=2026,
        is_default=True,
        value=Decimal("0.5"),
        unit="kgCO2e/kWh",
        source="DEMO ONLY — synthetic factor; not for reporting",
        change_note="仅用于本地界面和工作流演示。",
    )
    db.add(factor)
    db.flush()
    return factor


def _ensure_demo_site(db: Session, *, user: User, facility: str) -> Site:
    if user.tenant_id is None or user.enterprise_id is None:
        raise RuntimeError("demo user is missing its tenant/enterprise binding")
    matches = (
        db.query(Site)
        .filter(
            Site.tenant_id == user.tenant_id,
            Site.enterprise_id == user.enterprise_id,
            Site.name == facility,
        )
        .all()
    )
    if len(matches) > 1:
        raise RuntimeError(f"multiple demo sites use facility name {facility}")
    if matches:
        site = matches[0]
        if site.grid_region not in {
            LEGACY_DEMO_FACTOR_REGION,
            DEMO_FACTOR_REGION,
        }:
            raise RuntimeError("existing demo site has an unexpected grid region")
        site.grid_region = DEMO_FACTOR_REGION
        db.flush()
        return site

    site = Site(
        enterprise_id=user.enterprise_id,
        tenant_id=user.tenant_id,
        name=facility,
        address=DEFAULT_ADDRESS,
        province=DEFAULT_PROVINCE,
        city=DEFAULT_CITY,
        grid_region=DEMO_FACTOR_REGION,
    )
    db.add(site)
    db.flush()
    return site


def _ensure_document(
    db: Session,
    *,
    tenant: Tenant,
    enterprise: Enterprise,
    content: bytes,
    object_name: str,
    filename: str,
    ocr_result: dict,
) -> DocumentStore:
    document_hash = hashlib.sha256(content).hexdigest()
    document = (
        db.query(DocumentStore)
        .filter(
            DocumentStore.tenant_id == tenant.id,
            DocumentStore.enterprise_id == enterprise.id,
            DocumentStore.content_hash == document_hash,
        )
        .first()
    )
    storage_path = document.storage_path if document is not None else object_name
    storage = get_storage()
    stored_content = storage.download(storage_path) if storage.exists(storage_path) else None
    if stored_content != content:
        storage.upload(storage_path, content, "text/csv")

    if document is not None:
        if document.enterprise_id != enterprise.id:
            raise RuntimeError("existing demo document belongs to a different enterprise")
        # Keep the synthetic inbox preview aligned with the current demo
        # contract without creating duplicate evidence records.
        document.ocr_result = ocr_result
        document.ocr_status = "completed"
        document.ocr_error = None
        db.flush()
        return document

    document = DocumentStore(
        tenant_id=tenant.id,
        enterprise_id=enterprise.id,
        filename=filename,
        mime_type="text/csv",
        size_bytes=len(content),
        storage_path=storage_path,
        content_hash=document_hash,
        doc_type="electricity_bill",
        ocr_status="completed",
        ocr_result=ocr_result,
    )
    db.add(document)
    db.flush()
    return document


def _ensure_confirmed_emission(
    db: Session,
    *,
    user: User,
    factor: EmissionFactor,
    document: DocumentStore,
    facility: str,
    notes: str,
) -> EmissionResult:
    _ensure_demo_site(db, user=user, facility=facility)
    existing = (
        db.query(EmissionResult)
        .join(ActivityData, ActivityData.id == EmissionResult.activity_data_id)
        .filter(
            EmissionResult.tenant_id == user.tenant_id,
            EmissionResult.period_start == PERIOD_START,
            EmissionResult.period_end == PERIOD_END,
            EmissionResult.superseded_by_id.is_(None),
            ActivityData.tenant_id == user.tenant_id,
            ActivityData.document_id == document.id,
            ActivityData.superseded_by_id.is_(None),
        )
        .order_by(EmissionResult.created_at.desc(), EmissionResult.id)
        .first()
    )
    if existing is not None:
        return existing

    formal = persist_confirmed_activity(
        db,
        user=user,
        trusted_factor_id=factor.id,
        activity_record={
            "file_id": str(document.id),
            "document_content_hash": document.content_hash,
            "filename": document.filename,
            "document_type": "electricity_bill",
            "activity_type": "purchased_electricity",
            "quantity": "2000000",
            "unit": "kWh",
            "period": "2026-01-01 至 2026-03-31",
            "facility": facility,
            "value_origin": "human_confirmed",
            "notes": notes,
        },
    )
    result_payload = formal.get("emission_result")
    if result_payload is None:
        raise RuntimeError("demo activity did not produce an EmissionResult")
    result = db.get(EmissionResult, uuid.UUID(result_payload["emission_result_id"]))
    if result is None:
        raise RuntimeError("demo EmissionResult disappeared after formal write")
    return result


def _ensure_account_nodes(
    db: Session,
    *,
    tenant: Tenant,
    enterprise: Enterprise,
    user: User,
    request_key: str,
    installation_name: str,
    operator_name: str,
    process_name: str,
    product_name: str,
) -> tuple[InstallationAccount, uuid.UUID, uuid.UUID]:
    account = create_passport_account(
        db,
        tenant_id=tenant.id,
        enterprise_id=enterprise.id,
        actor_id=user.id,
        request_key=request_key,
        installation_name=installation_name,
        operator_name=operator_name,
        country_code="CN",
        unlocode="CNTGS",
        process_name=process_name,
        aggregate_goods_category="iron_steel",
        production_route="bf_bof",
        product_name=product_name,
        cn_code="72085100",
    )
    detail = passport_detail(db, tenant_id=tenant.id, account_id=account.id)
    process = next(
        (item for item in detail["processes"] if item["name"] == process_name),
        None,
    )
    product = next(
        (
            item
            for item in detail["products"]
            if item["name"] == product_name and item["cn_code"] == "72085100"
        ),
        None,
    )
    if process is None or product is None:
        raise RuntimeError("demo passport is missing its deterministic process/product")
    return account, uuid.UUID(process["id"]), uuid.UUID(product["id"])


def _seed_incomplete_passport(
    db: Session,
    *,
    tenant: Tenant,
    enterprise: Enterprise,
    user: User,
    factor: EmissionFactor,
) -> InstallationAccount:
    document = _ensure_document(
        db,
        tenant=tenant,
        enterprise=enterprise,
        content=INCOMPLETE_DOCUMENT_CONTENT,
        object_name="demo/passport/electricity-q1-demo.csv",
        filename="DEMO_电费数据_2026Q1.csv",
        ocr_result={
            "demo_only": True,
            "incomplete_workflow": True,
            "confidence": 0.91,
            "raw_text": INCOMPLETE_DOCUMENT_CONTENT.decode("utf-8"),
            "errors": [],
            "fields": {
                "electricity_kwh": "2000000",
                "period": "2026-01-01 至 2026-03-31",
                "facility": INCOMPLETE_FACILITY,
            },
        },
    )
    emission = _ensure_confirmed_emission(
        db,
        user=user,
        factor=factor,
        document=document,
        facility=INCOMPLETE_FACILITY,
        notes="DEMO ONLY — incomplete workflow; not for regulatory reporting",
    )
    account, process_id, product_id = _ensure_account_nodes(
        db,
        tenant=tenant,
        enterprise=enterprise,
        user=user,
        request_key=INCOMPLETE_REQUEST_KEY,
        installation_name=INCOMPLETE_FACILITY,
        operator_name=enterprise.name,
        process_name="高炉—转炉—热轧主流程（演示）",
        product_name="热轧卷板（演示）",
    )
    add_production_output(
        db,
        tenant_id=tenant.id,
        account_id=account.id,
        process_id=process_id,
        product_id=product_id,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        quantity="1000",
        unit="t",
        actor_id=user.id,
    )
    add_source_attribution(
        db,
        tenant_id=tenant.id,
        account_id=account.id,
        process_id=process_id,
        emission_result_id=emission.id,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        share="1",
        method="metered_allocation",
        actor_id=user.id,
    )
    db.commit()

    published = (
        db.query(InstallationProfileVersion)
        .filter(
            InstallationProfileVersion.tenant_id == tenant.id,
            InstallationProfileVersion.account_id == account.id,
            InstallationProfileVersion.period_start == PERIOD_START,
            InstallationProfileVersion.period_end == PERIOD_END,
            InstallationProfileVersion.status == "published",
        )
        .first()
    )
    if published is None:
        create_profile_snapshot(
            db,
            tenant_id=tenant.id,
            account_id=account.id,
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            actor_id=user.id,
        )
        db.commit()
    return account


def _find_replayable_publication(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
) -> InstallationProfileVersion | None:
    published = (
        db.query(InstallationProfileVersion)
        .filter(
            InstallationProfileVersion.tenant_id == tenant_id,
            InstallationProfileVersion.account_id == account_id,
            InstallationProfileVersion.period_start == PERIOD_START,
            InstallationProfileVersion.period_end == PERIOD_END,
            InstallationProfileVersion.status == "published",
        )
        .order_by(InstallationProfileVersion.version.desc())
        .all()
    )
    for profile in published:
        if replay_profile_version(
            db,
            tenant_id=tenant_id,
            profile_version_id=profile.id,
        )["match"]:
            return profile
    if published:
        raise RuntimeError("existing complete demo publication cannot be replayed")
    return None


def _ensure_review(
    db: Session,
    *,
    tenant: Tenant,
    account: InstallationAccount,
    draft: InstallationProfileVersion,
    user: User,
) -> MethodologyReview:
    reviews = (
        db.query(MethodologyReview)
        .filter(
            MethodologyReview.tenant_id == tenant.id,
            MethodologyReview.account_id == account.id,
            MethodologyReview.profile_version_id == draft.id,
        )
        .order_by(MethodologyReview.created_at, MethodologyReview.id)
        .all()
    )
    for review in reviews:
        if (
            review.verdict in {"pass", "pass_with_actions"}
            and review.disclaimer == "方法学复核不等于法定 CBAM 核查"
        ):
            return review
    return create_methodology_review(
        db,
        tenant_id=tenant.id,
        account_id=account.id,
        profile_version_id=draft.id,
        reviewer_id=user.id,
        reviewer_role=user.role,
        verdict="pass",
        summary=REFERENCE_REVIEW_SUMMARY,
        findings=REFERENCE_REVIEW_FINDINGS,
    )


def _ensure_reference_grant(
    db: Session,
    *,
    tenant: Tenant,
    account: InstallationAccount,
    profile: InstallationProfileVersion,
    user: User,
) -> DataSharingGrant:
    revoked_grant_ids = {
        item.grant_id
        for item in db.query(DataSharingRevocation)
        .filter(DataSharingRevocation.tenant_id == tenant.id)
        .all()
    }
    grants = (
        db.query(DataSharingGrant)
        .filter(
            DataSharingGrant.tenant_id == tenant.id,
            DataSharingGrant.account_id == account.id,
            DataSharingGrant.profile_version_id == profile.id,
        )
        .order_by(DataSharingGrant.created_at, DataSharingGrant.id)
        .all()
    )
    now = datetime.now(timezone.utc)
    for grant in grants:
        expires_at = grant.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if (
            grant.id not in revoked_grant_ids
            and expires_at > now
            and grant.recipient_tenant_id is None
            and grant.recipient_name == REFERENCE_RECIPIENT
            and grant.recipient_type == "other"
            and grant.purpose == REFERENCE_GRANT_PURPOSE
            and grant.scopes_json == ["emissions"]
        ):
            return grant
    return create_sharing_grant(
        db,
        tenant_id=tenant.id,
        account_id=account.id,
        profile_version_id=profile.id,
        recipient_name=REFERENCE_RECIPIENT,
        recipient_type="other",
        recipient_tenant_id=None,
        purpose=REFERENCE_GRANT_PURPOSE,
        scopes=["emissions"],
        expires_at=GRANT_EXPIRES_AT,
        actor_id=user.id,
    )


def _ensure_single_export(
    db: Session,
    *,
    tenant: Tenant,
    account: InstallationAccount,
    profile: InstallationProfileVersion,
    grant: DataSharingGrant,
    user: User,
) -> ProfileDistributionEvent:
    event = (
        db.query(ProfileDistributionEvent)
        .filter(
            ProfileDistributionEvent.tenant_id == tenant.id,
            ProfileDistributionEvent.account_id == account.id,
            ProfileDistributionEvent.profile_version_id == profile.id,
            ProfileDistributionEvent.grant_id == grant.id,
            ProfileDistributionEvent.channel == "json_export",
        )
        .order_by(ProfileDistributionEvent.created_at, ProfileDistributionEvent.id)
        .first()
    )
    if event is not None:
        return event
    export_shared_package(
        db,
        tenant_id=tenant.id,
        account_id=account.id,
        grant_id=grant.id,
        actor_id=user.id,
    )
    event = (
        db.query(ProfileDistributionEvent)
        .filter(
            ProfileDistributionEvent.tenant_id == tenant.id,
            ProfileDistributionEvent.account_id == account.id,
            ProfileDistributionEvent.profile_version_id == profile.id,
            ProfileDistributionEvent.grant_id == grant.id,
            ProfileDistributionEvent.channel == "json_export",
        )
        .first()
    )
    if event is None:
        raise RuntimeError("demo export did not create a distribution event")
    return event


def _seed_complete_reference(
    db: Session,
    *,
    tenant: Tenant,
    enterprise: Enterprise,
    user: User,
    factor: EmissionFactor,
) -> tuple[
    InstallationAccount,
    InstallationProfileVersion,
    DataSharingGrant,
    ProfileDistributionEvent,
]:
    document = _ensure_document(
        db,
        tenant=tenant,
        enterprise=enterprise,
        content=REFERENCE_DOCUMENT_CONTENT,
        object_name="demo/passport/reference-complete-electricity-q1-demo-only.csv",
        filename="DEMO_ONLY_非监管用途_完整参考电费数据_2026Q1.csv",
        ocr_result={
            "demo_only": True,
            "non_regulatory": True,
            "synthetic": True,
            "not_a_real_customer_delivery": True,
            "confidence": 0.98,
            "raw_text": REFERENCE_DOCUMENT_CONTENT.decode("utf-8"),
            "errors": [],
            "fields": {
                "electricity_kwh": "2000000",
                "period": "2026-01-01 至 2026-03-31",
                "facility": REFERENCE_FACILITY,
                "boundary_notice": "DEMO ONLY / 非监管用途 / 合成数据",
            },
        },
    )
    emission = _ensure_confirmed_emission(
        db,
        user=user,
        factor=factor,
        document=document,
        facility=REFERENCE_FACILITY,
        notes="DEMO ONLY — synthetic human-confirmed value; not for reporting",
    )
    db.commit()

    account, process_id, product_id = _ensure_account_nodes(
        db,
        tenant=tenant,
        enterprise=enterprise,
        user=user,
        request_key=REFERENCE_REQUEST_KEY,
        installation_name=REFERENCE_FACILITY,
        operator_name=f"{enterprise.name}｜DEMO ONLY / 非真实客户",
        process_name="DEMO ONLY｜完整参考工序（非监管用途）",
        product_name="DEMO ONLY｜热轧卷板完整参考产品",
    )
    output = add_production_output(
        db,
        tenant_id=tenant.id,
        account_id=account.id,
        process_id=process_id,
        product_id=product_id,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        quantity="1000",
        unit="t",
        actor_id=user.id,
    )
    add_source_attribution(
        db,
        tenant_id=tenant.id,
        account_id=account.id,
        process_id=process_id,
        emission_result_id=emission.id,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        share="1",
        method="demo_only_metered_allocation_non_regulatory",
        actor_id=user.id,
    )
    db.commit()

    rule = register_authoritative_rule(
        db,
        tenant_id=tenant.id,
        actor_id=user.id,
        rule_kind="cbam_methodology",
        title=(
            "DEMO ONLY / 非监管用途 — EU 2023/1773 工作流元数据引用"
            "（未独立认证）"
        ),
        publisher="European Commission",
        document_number="EU-DEMO-ONLY-2023-1773-NOT-CERTIFIED",
        jurisdiction="EU",
        vintage=2023,
        valid_from=RULE_VALID_FROM,
        valid_to=None,
        source_url=(
            "https://eur-lex.europa.eu/eli/reg_impl/2023/1773/oj"
            "#DEMO-ONLY-NOT-INDEPENDENTLY-AUTHENTICATED"
        ),
        source_content_hash=hashlib.sha256(REFERENCE_RULE_DESCRIPTOR).hexdigest(),
    )
    calculate_passport_see(
        db,
        tenant_id=tenant.id,
        account_id=account.id,
        process_id=process_id,
        product_id=product_id,
        production_output_id=output.id,
        methodology_ref=f"rule_record:{rule.id}",
        actor_id=user.id,
    )
    db.commit()

    published = _find_replayable_publication(
        db,
        tenant_id=tenant.id,
        account_id=account.id,
    )
    if published is None:
        draft = create_profile_snapshot(
            db,
            tenant_id=tenant.id,
            account_id=account.id,
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            actor_id=user.id,
        )
        if draft.assessment_json["missing_keys"] != ["methodology_review"]:
            raise RuntimeError(
                "complete demo draft is not ready for methodology review: "
                f"{draft.assessment_json['missing_keys']}"
            )
        db.commit()

        review = _ensure_review(
            db,
            tenant=tenant,
            account=account,
            draft=draft,
            user=user,
        )
        db.commit()
        published = publish_profile_version(
            db,
            tenant_id=tenant.id,
            account_id=account.id,
            profile_version_id=draft.id,
            methodology_review_id=review.id,
            actor_id=user.id,
        )
        db.commit()

    grant = _ensure_reference_grant(
        db,
        tenant=tenant,
        account=account,
        profile=published,
        user=user,
    )
    db.commit()
    event = _ensure_single_export(
        db,
        tenant=tenant,
        account=account,
        profile=published,
        grant=grant,
        user=user,
    )
    db.commit()
    return account, published, grant, event


def main() -> None:
    if not PASSWORD:
        raise RuntimeError(
            "CARBONLAB_DEMO_PASSWORD must be set before creating the local demo user"
        )
    with get_sessionmaker()() as db:
        tenant, enterprise, user = _ensure_identity(db)
        factor = _ensure_demo_factor(db)
        db.commit()

        incomplete = _seed_incomplete_passport(
            db,
            tenant=tenant,
            enterprise=enterprise,
            user=user,
            factor=factor,
        )
        complete, published, grant, event = _seed_complete_reference(
            db,
            tenant=tenant,
            enterprise=enterprise,
            user=user,
            factor=factor,
        )

        print(f"Incomplete DEMO passport ready: {incomplete.account_code}")
        print("Still intentionally missing: RuleRecord, SEE, review, publication")
        print(f"Complete DEMO ONLY reference passport: {complete.account_code}")
        print(
            "Published immutable version "
            f"v{published.version}; statutory verification: false"
        )
        print(f"Least-privilege external demo grant: {grant.id} / scopes=emissions")
        print(f"Single JSON export distribution event: {event.id}")
        print("Boundary: synthetic data, non-regulatory, no real customer delivery")
        print(f"Demo login email: {EMAIL}")
        print("Demo password: supplied through CARBONLAB_DEMO_PASSWORD (not printed)")


if __name__ == "__main__":
    main()
