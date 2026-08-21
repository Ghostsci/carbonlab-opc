"""Behavior tests for the factory carbon-data passport public API."""

from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext
from sqlalchemy.exc import StatementError

from backend.database import Base, get_engine, get_sessionmaker
from backend.main import app
from backend.models.enterprise import Enterprise
from backend.models.emission_factor import EmissionFactor
from backend.models.document import DocumentStore
from backend.models.tenant import Tenant
from backend.models.user import User
from backend.models.installation_passport import (
    DataSharingGrant,
    InstallationAccountMember,
    MethodologyReview,
)
from backend.models.ledger import LedgerImmutableError, LedgerIntegrityError
from backend.services.activity_ingestion import persist_confirmed_activity
from backend.services.installation_passport import (
    add_production_output,
    add_source_attribution,
    calculate_passport_see,
    create_methodology_review,
    create_passport_account,
    create_profile_snapshot,
    passport_detail,
    publish_profile_version,
    register_authoritative_rule,
)


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def setup_module():
    Base.metadata.create_all(bind=get_engine())


def teardown_module():
    Base.metadata.drop_all(bind=get_engine())


def _session():
    return get_sessionmaker()()


def _identity(db, slug: str, *, role: str = "admin") -> tuple[Tenant, Enterprise, User]:
    suffix = uuid.uuid4().hex[:12].upper()
    tenant = Tenant(name=slug, slug=f"{slug}-{suffix.lower()}")
    db.add(tenant)
    db.flush()
    enterprise = Enterprise(
        name=f"{slug} 制造有限公司",
        unified_social_credit_code=f"91{suffix}0000",
        industry_code="C31",
        industry_name="黑色金属冶炼和压延加工业",
        tenant_id=tenant.id,
    )
    db.add(enterprise)
    db.flush()
    user = User(
        email=f"{slug}-{suffix.lower()}@example.com",
        password_hash=pwd_context.hash("secret123"),
        role=role,
        tenant_id=tenant.id,
        enterprise_id=enterprise.id,
    )
    db.add(user)
    db.commit()
    return tenant, enterprise, user


def _login(client: TestClient, user: User) -> str:
    response = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": "secret123"},
    )
    assert response.status_code == 200, response.json()
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _published_passport_fixture(db, tenant, enterprise, user):
    period_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    period_end = datetime(2026, 3, 31, 23, 59, 59, tzinfo=timezone.utc)
    factor = EmissionFactor(
        name="华东电网共享测试因子",
        code=f"SHARE-ELEC-{uuid.uuid4().hex[:8]}",
        category="electricity_grid",
        region="华东",
        year=2026,
        version_year=2026,
        is_default=True,
        value=Decimal("0.5"),
        unit="kgCO2e/kWh",
        source="test-authoritative-fixture",
    )
    document = DocumentStore(
        tenant_id=tenant.id,
        enterprise_id=enterprise.id,
        filename="owner-electricity-q1.csv",
        mime_type="text/csv",
        size_bytes=32,
        storage_path="private/owner-electricity-q1.csv",
        content_hash=uuid.uuid4().hex * 2,
        doc_type="electricity_bill",
        ocr_status="completed",
        ocr_result={"fields": {"electricity_kwh": "2000000"}},
    )
    db.add_all([factor, document])
    db.flush()
    formal = persist_confirmed_activity(
        db,
        user=user,
        activity_record={
            "file_id": str(document.id),
            "document_content_hash": document.content_hash,
            "filename": document.filename,
            "document_type": "electricity_bill",
            "activity_type": "purchased_electricity",
            "quantity": "2000000",
            "unit": "kWh",
            "period": "2026-01-01 至 2026-03-31",
            "facility": "共享测试装置",
            "value_origin": "human_confirmed",
        },
    )
    account = create_passport_account(
        db,
        tenant_id=tenant.id,
        enterprise_id=enterprise.id,
        actor_id=user.id,
        request_key=uuid.uuid4().hex,
        installation_name="共享测试装置",
        operator_name=enterprise.name,
        country_code="CN",
        unlocode="CNTGS",
        process_name="共享测试主工序",
        aggregate_goods_category="iron_steel",
        production_route="bf_bof",
        product_name="热轧卷板",
        cn_code="72085100",
    )
    detail = passport_detail(db, tenant_id=tenant.id, account_id=account.id)
    process_id = uuid.UUID(detail["processes"][0]["id"])
    product_id = uuid.UUID(detail["products"][0]["id"])
    output = add_production_output(
        db,
        tenant_id=tenant.id,
        account_id=account.id,
        process_id=process_id,
        product_id=product_id,
        period_start=period_start,
        period_end=period_end,
        quantity="1000",
        unit="t",
        actor_id=user.id,
    )
    add_source_attribution(
        db,
        tenant_id=tenant.id,
        account_id=account.id,
        process_id=process_id,
        emission_result_id=uuid.UUID(formal["emission_result"]["emission_result_id"]),
        period_start=period_start,
        period_end=period_end,
        share="1",
        method="metered_allocation",
        actor_id=user.id,
    )
    db.commit()
    rule = register_authoritative_rule(
        db,
        tenant_id=tenant.id,
        actor_id=user.id,
        rule_kind="cbam_methodology",
        title="CBAM shared profile methodology",
        publisher="European Commission",
        document_number=f"EU-2023-1773-{uuid.uuid4().hex[:6].upper()}",
        jurisdiction="EU",
        vintage=2023,
        valid_from=datetime(2023, 5, 17, tzinfo=timezone.utc),
        valid_to=None,
        source_url="https://eur-lex.europa.eu/eli/reg_impl/2023/1773/oj",
        source_content_hash="b" * 64,
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
    draft = create_profile_snapshot(
        db,
        tenant_id=tenant.id,
        account_id=account.id,
        period_start=period_start,
        period_end=period_end,
        actor_id=user.id,
    )
    review = create_methodology_review(
        db,
        tenant_id=tenant.id,
        account_id=account.id,
        profile_version_id=draft.id,
        reviewer_id=user.id,
        reviewer_role=user.role,
        verdict="pass",
        summary="共享前方法学复核通过。",
        findings=[],
    )
    published = publish_profile_version(
        db,
        tenant_id=tenant.id,
        account_id=account.id,
        profile_version_id=draft.id,
        methodology_review_id=review.id,
        actor_id=user.id,
    )
    db.commit()
    return account, published


def test_passport_api_creates_stable_account_and_tenant_scoped_profile():
    client = TestClient(app)
    db = _session()
    try:
        tenant, enterprise, user = _identity(db, "passport-create")
        token = _login(client, user)
        request_key = uuid.uuid4().hex
        payload = {
            "request_key": request_key,
            "installation_name": "唐山热轧生产装置",
            "operator_name": enterprise.name,
            "country_code": "CN",
            "unlocode": "CNTGS",
            "process_name": "高炉—转炉—热轧流程",
            "aggregate_goods_category": "iron_steel",
            "production_route": "bf_bof",
            "product_name": "热轧卷板",
            "cn_code": "72085100",
        }

        created = client.post("/api/passports", headers=_headers(token), json=payload)
        assert created.status_code == 201, created.json()
        body = created.json()
        assert body["account"]["tenant_id"] == str(tenant.id)
        assert body["account"]["enterprise_id"] == str(enterprise.id)
        assert body["installation"]["name"] == "唐山热轧生产装置"
        assert body["processes"][0]["production_route"] == "bf_bof"
        assert body["products"][0]["cn_code"] == "72085100"
        assert body["assessment"]["score"] < 100
        assert "production_output" in body["assessment"]["missing_keys"]

        replayed = client.post("/api/passports", headers=_headers(token), json=payload)
        assert replayed.status_code == 201, replayed.json()
        assert replayed.json()["account"]["id"] == body["account"]["id"]

        conflicting_replay = client.post(
            "/api/passports",
            headers=_headers(token),
            json={**payload, "product_name": "伪造的不同产品"},
        )
        assert conflicting_replay.status_code == 409, conflicting_replay.json()
        assert "request_key" in conflicting_replay.json()["detail"]

        listed = client.get("/api/passports", headers=_headers(token))
        assert listed.status_code == 200, listed.json()
        assert [item["account"]["id"] for item in listed.json()] == [
            body["account"]["id"]
        ]
    finally:
        db.close()


def test_incomplete_passport_cannot_be_reviewed_or_published():
    client = TestClient(app)
    db = _session()
    try:
        _tenant, enterprise, user = _identity(db, "passport-incomplete")
        token = _login(client, user)
        created = client.post(
            "/api/passports",
            headers=_headers(token),
            json={
                "request_key": uuid.uuid4().hex,
                "installation_name": "不完整装置",
                "operator_name": enterprise.name,
                "country_code": "CN",
                "process_name": "热轧流程",
                "aggregate_goods_category": "iron_steel",
                "production_route": "bf_bof",
                "product_name": "热轧卷板",
                "cn_code": "72085100",
            },
        )
        account_id = created.json()["account"]["id"]

        snapshot = client.post(
            f"/api/passports/{account_id}/profiles",
            headers=_headers(token),
            json={
                "period_start": "2026-01-01T00:00:00Z",
                "period_end": "2026-03-31T23:59:59Z",
            },
        )
        assert snapshot.status_code == 201, snapshot.json()
        profile = snapshot.json()
        assert profile["status"] == "draft"
        assert profile["completeness_score"] < 100
        assert profile["replay"]["match"] is True, profile["replay"]

        review = client.post(
            f"/api/passports/{account_id}/reviews",
            headers=_headers(token),
            json={
                "profile_version_id": profile["id"],
                "verdict": "pass",
                "summary": "方法学边界已复核。",
                "findings": [],
            },
        )
        assert review.status_code == 409
        assert "缺少" in review.json()["detail"]

        publish = client.post(
            f"/api/passports/{account_id}/publish",
            headers=_headers(token),
            json={
                "profile_version_id": profile["id"],
                "methodology_review_id": str(uuid.uuid4()),
            },
        )
        assert publish.status_code == 409
    finally:
        db.close()


def test_complete_passport_can_be_replayed_reviewed_and_published():
    client = TestClient(app)
    db = _session()
    try:
        _tenant, enterprise, user = _identity(db, "passport-complete")
        factor = EmissionFactor(
            name="华东电网测试因子",
            code=f"TEST-ELEC-{uuid.uuid4().hex[:8]}",
            category="electricity_grid",
            region="华东",
            year=2026,
            version_year=2026,
            is_default=True,
            value=Decimal("0.5"),
            unit="kgCO2e/kWh",
            source="test-authoritative-fixture",
        )
        db.add(factor)
        db.commit()
        token = _login(client, user)
        headers = _headers(token)

        created = client.post(
            "/api/passports",
            headers=headers,
            json={
                "request_key": uuid.uuid4().hex,
                "installation_name": "热轧卷板生产装置",
                "operator_name": enterprise.name,
                "country_code": "CN",
                "unlocode": "CNTGS",
                "process_name": "热轧主工序",
                "aggregate_goods_category": "iron_steel",
                "production_route": "bf_bof",
                "product_name": "热轧卷板",
                "cn_code": "72085100",
            },
        )
        assert created.status_code == 201, created.json()
        detail = created.json()
        account_id = detail["account"]["id"]
        process_id = detail["processes"][0]["id"]
        product_id = detail["products"][0]["id"]

        csv_content = (
            "账单月份,用电量,所属工厂\n"
            "2026年第一季度,2000000 kWh,热轧卷板生产装置\n"
        ).encode("utf-8")
        uploaded = client.post(
            "/api/upload",
            headers=headers,
            files={"file": ("electricity-q1.csv", csv_content, "text/csv")},
        )
        assert uploaded.status_code == 200, uploaded.json()
        document = uploaded.json()
        fields = {
            "electricity_kwh": "2000000",
            "period": "2026-01-01 至 2026-03-31",
            "facility": "热轧卷板生产装置",
        }
        candidate = client.post(
            f"/api/upload/{document['file_id']}/candidate",
            headers=headers,
            json={"fields": fields},
        )
        assert candidate.status_code == 200, candidate.json()
        confirmed = client.post(
            "/api/upload/confirm-activity",
            headers=headers,
            json={
                "candidate_token": candidate.json()["candidate_token"],
                "file_id": document["file_id"],
                "document_content_hash": document["content_hash"],
                "filename": document["filename"],
                "document_type": "electricity_bill",
                "fields": fields,
            },
        )
        assert confirmed.status_code == 200, confirmed.json()
        emission_result_id = confirmed.json()["formal_write"]["emission_result"][
            "emission_result_id"
        ]

        output = client.post(
            f"/api/passports/{account_id}/outputs",
            headers=headers,
            json={
                "process_id": process_id,
                "product_id": product_id,
                "period_start": "2026-01-01T00:00:00Z",
                "period_end": "2026-03-31T23:59:59Z",
                "quantity": "1000",
                "unit": "t",
            },
        )
        assert output.status_code == 201, output.json()

        attribution = client.post(
            f"/api/passports/{account_id}/attributions",
            headers=headers,
            json={
                "process_id": process_id,
                "emission_result_id": emission_result_id,
                "period_start": "2026-01-01T00:00:00Z",
                "period_end": "2026-03-31T23:59:59Z",
                "share": "1",
                "method": "metered_allocation",
            },
        )
        assert attribution.status_code == 201, attribution.json()

        rule = client.post(
            "/api/passports/rules",
            headers=headers,
            json={
                "rule_kind": "cbam_methodology",
                "title": "CBAM embedded emissions methodology",
                "publisher": "European Commission",
                "document_number": "EU-2023-1773-TEST",
                "jurisdiction": "EU",
                "vintage": 2023,
                "valid_from": "2023-05-17T00:00:00Z",
                "valid_to": None,
                "source_url": "https://eur-lex.europa.eu/eli/reg_impl/2023/1773/oj",
                "source_content_hash": "a" * 64,
            },
        )
        assert rule.status_code == 201, rule.json()
        methodology_ref = f"rule_record:{rule.json()['id']}"

        see = client.post(
            f"/api/passports/{account_id}/see-results",
            headers=headers,
            json={
                "process_id": process_id,
                "product_id": product_id,
                "production_output_id": output.json()["id"],
                "methodology_ref": methodology_ref,
            },
        )
        assert see.status_code == 201, see.json()
        assert see.json()["total_emissions"] == "1000.000000000000"
        assert see.json()["specific_emissions"] == "1.000000000000"

        snapshot = client.post(
            f"/api/passports/{account_id}/profiles",
            headers=headers,
            json={
                "period_start": "2026-01-01T00:00:00Z",
                "period_end": "2026-03-31T23:59:59Z",
            },
        )
        assert snapshot.status_code == 201, snapshot.json()
        draft = snapshot.json()
        assert draft["completeness_score"] == 88
        assert draft["assessment"]["missing_keys"] == ["methodology_review"]
        assert draft["replay"]["match"] is True, draft["replay"]

        review = client.post(
            f"/api/passports/{account_id}/reviews",
            headers=headers,
            json={
                "profile_version_id": draft["id"],
                "verdict": "pass",
                "summary": "边界、归集引用、证据与规则版本均已完成方法学复核。",
                "findings": [],
            },
        )
        assert review.status_code == 201, review.json()
        assert review.json()["disclaimer"] == "方法学复核不等于法定 CBAM 核查"

        corrected_output = client.post(
            f"/api/passports/{account_id}/outputs",
            headers=headers,
            json={
                "process_id": process_id,
                "product_id": product_id,
                "period_start": "2026-01-01T00:00:00Z",
                "period_end": "2026-03-31T23:59:59Z",
                "quantity": "1100",
                "unit": "t",
            },
        )
        assert corrected_output.status_code == 201, corrected_output.json()
        assert corrected_output.json()["id"] != output.json()["id"]

        stale_publish = client.post(
            f"/api/passports/{account_id}/publish",
            headers=headers,
            json={
                "profile_version_id": draft["id"],
                "methodology_review_id": review.json()["id"],
            },
        )
        assert stale_publish.status_code == 409, stale_publish.json()
        assert "正式事实已变化" in stale_publish.json()["detail"]

        stale_see_draft = client.post(
            f"/api/passports/{account_id}/profiles",
            headers=headers,
            json={
                "period_start": "2026-01-01T00:00:00Z",
                "period_end": "2026-03-31T23:59:59Z",
            },
        )
        assert stale_see_draft.status_code == 201, stale_see_draft.json()
        assert "deterministic_see" in stale_see_draft.json()["assessment"][
            "missing_keys"
        ]
        assert stale_see_draft.json()["assessment"]["ready_to_publish"] is False

        refreshed_see = client.post(
            f"/api/passports/{account_id}/see-results",
            headers=headers,
            json={
                "process_id": process_id,
                "product_id": product_id,
                "production_output_id": corrected_output.json()["id"],
                "methodology_ref": methodology_ref,
            },
        )
        assert refreshed_see.status_code == 201, refreshed_see.json()

        refreshed_snapshot = client.post(
            f"/api/passports/{account_id}/profiles",
            headers=headers,
            json={
                "period_start": "2026-01-01T00:00:00Z",
                "period_end": "2026-03-31T23:59:59Z",
            },
        )
        assert refreshed_snapshot.status_code == 201, refreshed_snapshot.json()
        refreshed_draft = refreshed_snapshot.json()
        assert refreshed_draft["assessment"]["missing_keys"] == [
            "methodology_review"
        ]
        refreshed_review = client.post(
            f"/api/passports/{account_id}/reviews",
            headers=headers,
            json={
                "profile_version_id": refreshed_draft["id"],
                "verdict": "pass",
                "summary": "产量修订后已重新完成方法学复核。",
                "findings": [],
            },
        )
        assert refreshed_review.status_code == 201, refreshed_review.json()
        published = client.post(
            f"/api/passports/{account_id}/publish",
            headers=headers,
            json={
                "profile_version_id": refreshed_draft["id"],
                "methodology_review_id": refreshed_review.json()["id"],
            },
        )
        assert published.status_code == 201, published.json()
        final = published.json()
        assert final["status"] == "published"
        assert final["version"] == refreshed_draft["version"] + 1
        assert final["completeness_score"] == 100
        assert final["replay"]["match"] is True, final["replay"]
        assert final["snapshot"]["methodology_review"]["verdict"] == "pass"
        repeated_publish = client.post(
            f"/api/passports/{account_id}/publish",
            headers=headers,
            json={
                "profile_version_id": refreshed_draft["id"],
                "methodology_review_id": refreshed_review.json()["id"],
            },
        )
        assert repeated_publish.status_code == 201, repeated_publish.json()
        assert repeated_publish.json()["id"] == final["id"]

        revised_attribution = client.post(
            f"/api/passports/{account_id}/attributions",
            headers=headers,
            json={
                "process_id": process_id,
                "emission_result_id": emission_result_id,
                "period_start": "2026-01-01T00:00:00Z",
                "period_end": "2026-03-31T23:59:59Z",
                "share": "1",
                "method": "reconciled_metered_allocation",
            },
        )
        assert revised_attribution.status_code == 201, revised_attribution.json()
        assert revised_attribution.json()["id"] != attribution.json()["id"]

        stale_attribution_draft = client.post(
            f"/api/passports/{account_id}/profiles",
            headers=headers,
            json={
                "period_start": "2026-01-01T00:00:00Z",
                "period_end": "2026-03-31T23:59:59Z",
            },
        )
        assert stale_attribution_draft.status_code == 201, (
            stale_attribution_draft.json()
        )
        assert "deterministic_see" in stale_attribution_draft.json()["assessment"][
            "missing_keys"
        ]
    finally:
        db.close()


def test_cross_tenant_passport_access_is_denied_without_grant():
    client = TestClient(app)
    db = _session()
    try:
        _tenant_a, enterprise_a, user_a = _identity(db, "passport-owner")
        _tenant_b, _enterprise_b, user_b = _identity(db, "passport-outsider")
        token_a = _login(client, user_a)
        token_b = _login(client, user_b)
        created = client.post(
            "/api/passports",
            headers=_headers(token_a),
            json={
                "request_key": uuid.uuid4().hex,
                "installation_name": "租户 A 装置",
                "operator_name": enterprise_a.name,
                "country_code": "CN",
                "process_name": "主工序",
                "aggregate_goods_category": "iron_steel",
                "production_route": "bf_bof",
                "product_name": "热轧卷板",
                "cn_code": "72085100",
            },
        )
        account_id = created.json()["account"]["id"]

        response = client.get(
            f"/api/passports/{account_id}",
            headers=_headers(token_b),
        )
        assert response.status_code == 404
        assert "tenant" in response.json()["detail"]
    finally:
        db.close()


def test_scoped_share_hides_ungranted_sections_and_revocation_stops_access():
    client = TestClient(app)
    db = _session()
    try:
        tenant_owner, enterprise_owner, owner = _identity(db, "passport-share-owner")
        tenant_recipient, _enterprise_recipient, recipient = _identity(
            db,
            "passport-share-recipient",
        )
        account, published = _published_passport_fixture(
            db,
            tenant_owner,
            enterprise_owner,
            owner,
        )
        owner_token = _login(client, owner)
        recipient_token = _login(client, recipient)

        grant = client.post(
            f"/api/passports/{account.id}/sharing-grants",
            headers=_headers(owner_token),
            json={
                "profile_version_id": str(published.id),
                "recipient_name": "欧洲进口商测试租户",
                "recipient_type": "importer",
                "recipient_tenant_id": str(tenant_recipient.id),
                "purpose": "CBAM 数据复核",
                "scopes": ["identity", "emissions"],
                "expires_at": (
                    datetime.now(timezone.utc) + timedelta(days=7)
                ).isoformat(),
            },
        )
        assert grant.status_code == 201, grant.json()
        grant_id = grant.json()["id"]
        assert grant.json()["active"] is True

        shared = client.get(
            f"/api/passports/shared/{grant_id}",
            headers=_headers(recipient_token),
        )
        assert shared.status_code == 200, shared.json()
        package = shared.json()["package"]
        assert package["installation"]["name"] == "共享测试装置"
        assert package["see_results"][0]["specific_emissions"] == "1.000000000000"
        assert "evidence_manifest" not in package
        assert "rule_records" not in package
        assert "methodology_review" not in package
        assert "storage_path" not in str(package)
        assert package["verification_status"]["statutory_verification"] is False

        revoked = client.post(
            f"/api/passports/{account.id}/sharing-grants/{grant_id}/revoke",
            headers=_headers(owner_token),
            json={"reason": "接收方任务已结束"},
        )
        assert revoked.status_code == 201, revoked.json()

        after_revoke = client.get(
            f"/api/passports/shared/{grant_id}",
            headers=_headers(recipient_token),
        )
        assert after_revoke.status_code == 409
        assert "撤销" in after_revoke.json()["detail"]
        inbox = client.get("/api/passports/shared", headers=_headers(recipient_token))
        assert inbox.status_code == 200
        assert inbox.json() == []
    finally:
        db.close()


def test_passport_formal_records_reject_update_delete_and_cross_tenant_lineage():
    db = _session()
    try:
        tenant_a, enterprise_a, user_a = _identity(db, "passport-guard-a")
        tenant_b, enterprise_b, user_b = _identity(db, "passport-guard-b")
        account_a = create_passport_account(
            db,
            tenant_id=tenant_a.id,
            enterprise_id=enterprise_a.id,
            actor_id=user_a.id,
            request_key=uuid.uuid4().hex,
            installation_name="A 装置",
            operator_name=enterprise_a.name,
            country_code="CN",
            unlocode=None,
            process_name="A 工序",
            aggregate_goods_category="iron_steel",
            production_route="bf_bof",
            product_name="A 产品",
            cn_code="72085100",
        )
        account_b = create_passport_account(
            db,
            tenant_id=tenant_b.id,
            enterprise_id=enterprise_b.id,
            actor_id=user_b.id,
            request_key=uuid.uuid4().hex,
            installation_name="B 装置",
            operator_name=enterprise_b.name,
            country_code="CN",
            unlocode=None,
            process_name="B 工序",
            aggregate_goods_category="iron_steel",
            production_route="bf_bof",
            product_name="B 产品",
            cn_code="72085100",
        )
        db.commit()

        account_a.account_code = "FORGED-CODE"
        with pytest.raises(LedgerImmutableError):
            db.flush()
        db.rollback()

        detail_b = passport_detail(db, tenant_id=tenant_b.id, account_id=account_b.id)
        db.add(
            InstallationAccountMember(
                tenant_id=tenant_b.id,
                account_id=account_a.id,
                installation_id=uuid.UUID(detail_b["installation"]["id"]),
                added_by=str(user_b.id),
                content_hash="c" * 64,
            )
        )
        with pytest.raises((LedgerIntegrityError, StatementError)):
            db.flush()
        db.rollback()

        draft = create_profile_snapshot(
            db,
            tenant_id=tenant_a.id,
            account_id=account_a.id,
            period_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            period_end=datetime(2026, 3, 31, 23, 59, 59, tzinfo=timezone.utc),
            actor_id=user_a.id,
        )
        db.commit()
        db.add(
            MethodologyReview(
                tenant_id=tenant_a.id,
                account_id=account_a.id,
                profile_version_id=draft.id,
                reviewer_id=str(user_a.id),
                reviewer_role="admin",
                verdict="pass",
                summary="试图绕过完整度门禁。",
                findings_json=[],
                disclaimer="方法学复核不等于法定 CBAM 核查",
                content_hash="d" * 64,
            )
        )
        with pytest.raises(LedgerIntegrityError):
            db.flush()
        db.rollback()

        db.add(
            DataSharingGrant(
                tenant_id=tenant_a.id,
                account_id=account_a.id,
                profile_version_id=draft.id,
                recipient_tenant_id=tenant_b.id,
                recipient_name="伪造接收方",
                recipient_type="importer",
                purpose="绕过发布门禁",
                scopes_json=["identity"],
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                created_by=str(user_a.id),
                content_hash="e" * 64,
            )
        )
        with pytest.raises(LedgerIntegrityError):
            db.flush()
        db.rollback()
    finally:
        db.close()


def test_passport_api_rejects_binary_float_and_unknown_write_fields():
    client = TestClient(app)
    db = _session()
    try:
        _tenant, enterprise, user = _identity(db, "passport-input-guard")
        token = _login(client, user)
        payload = {
            "request_key": uuid.uuid4().hex,
            "installation_name": "输入防线装置",
            "operator_name": enterprise.name,
            "country_code": "CN",
            "process_name": "主工序",
            "aggregate_goods_category": "iron_steel",
            "production_route": "bf_bof",
            "product_name": "热轧卷板",
            "cn_code": "72085100",
        }
        forged = client.post(
            "/api/passports",
            headers=_headers(token),
            json={**payload, "completeness_score": 100},
        )
        assert forged.status_code == 422

        created = client.post("/api/passports", headers=_headers(token), json=payload)
        detail = created.json()
        output = client.post(
            f"/api/passports/{detail['account']['id']}/outputs",
            headers=_headers(token),
            json={
                "process_id": detail["processes"][0]["id"],
                "product_id": detail["products"][0]["id"],
                "period_start": "2026-01-01T00:00:00Z",
                "period_end": "2026-03-31T23:59:59Z",
                "quantity": 0.1,
                "unit": "t",
            },
        )
        assert output.status_code == 422
        assert "binary float" in str(output.json())
    finally:
        db.close()
