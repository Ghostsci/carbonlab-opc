"""Adversarial tests for the ontology and tenant-scoped hybrid retriever."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from backend.ai.ontology import ontology_contract, ontology_version
from backend.ai.rag import RAGBoundaryError, get_rag_service
from backend.api.passports import MethodologySearchRequest, search_methodology_candidates
from backend.models.document import DocumentStore
from backend.models.enterprise import Enterprise
from backend.models.knowledge import KnowledgeChunk, RetrievalRun
from backend.models.tenant import Tenant
from backend.models.user import User
from backend.services.digital_workforce import evaluate_document_quality
from backend.services.installation_passport import (
    create_passport_account,
    register_authoritative_rule,
)


def _identity(db, slug: str) -> tuple[Tenant, Enterprise, User]:
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
        password_hash="not-used-in-service-tests",
        role="admin",
        tenant_id=tenant.id,
        enterprise_id=enterprise.id,
    )
    db.add(user)
    db.flush()
    return tenant, enterprise, user


def _document(db, tenant, enterprise, *, marker: str, fields: dict) -> DocumentStore:
    document = DocumentStore(
        tenant_id=tenant.id,
        enterprise_id=enterprise.id,
        filename=f"{marker}.csv",
        mime_type="text/csv",
        size_bytes=128,
        storage_path=f"tests/{marker}.csv",
        content_hash=uuid.uuid4().hex * 2,
        doc_type="electricity_bill",
        ocr_status="completed",
        ocr_result={
            "fields": fields,
            "confidence": 97,
            "raw_text": "；".join(f"{key}={value}" for key, value in fields.items()),
        },
    )
    db.add(document)
    db.flush()
    return document


def test_ontology_contract_is_small_versioned_and_keeps_r01_out_of_rag():
    contract = ontology_contract()
    assert ontology_version() == "carbon-passport-ontology-v0.1.0"
    assert "supportsField" in {relation["name"] for relation in contract["relations"]}
    assert all(
        "R-01" not in policy["allowed_roles"]
        for policy in contract["corpora"].values()
    )


def test_document_indexing_is_idempotent(db_session):
    tenant, enterprise, _user = _identity(db_session, "rag-index-idempotency")
    document = _document(
        db_session,
        tenant,
        enterprise,
        marker="same-document",
        fields={"electricity_kwh": "4096 kWh", "period": "2026-03"},
    )
    rag = get_rag_service()

    first = rag.index_document(db_session, document)
    first_chunk_count = (
        db_session.query(KnowledgeChunk)
        .filter(KnowledgeChunk.document_id == first.id)
        .count()
    )
    second = rag.index_document(db_session, document)
    second_chunk_count = (
        db_session.query(KnowledgeChunk)
        .filter(KnowledgeChunk.document_id == second.id)
        .count()
    )

    assert second.id == first.id
    assert second_chunk_count == first_chunk_count


def test_a03_retrieval_is_field_specific_not_document_occurrence(db_session):
    tenant, enterprise, user = _identity(db_session, "rag-field-specific")
    document = _document(
        db_session,
        tenant,
        enterprise,
        marker="unrelated-value",
        fields={
            "electricity_kwh": "125000 kWh",
            "total_amount": "632600 元",
            "period": "2026-03",
            "facility": "炼钢厂",
        },
    )
    rag = get_rag_service()
    rag.index_document(db_session, document)
    retrieval = rag.search(
        db_session,
        tenant_id=tenant.id,
        enterprise_id=enterprise.id,
        actor_id=user.id,
        role_id="A-03",
        purpose="field_evidence_review",
        query_text="字段 electricity_kwh 候选值 632600",
        corpus_types={"tenant_evidence"},
        source_ref=str(document.id),
        field_key="electricity_kwh",
    )
    assert retrieval.hits
    assert all(hit.field_keys == ["electricity_kwh"] for hit in retrieval.hits)
    result = evaluate_document_quality(
        document_type="electricity_bill",
        document_content_hash=document.content_hash,
        fields={
            "electricity_kwh": "632600",
            "period": "2026-03",
            "facility": "炼钢厂",
        },
        source_snapshot=document.ocr_result,
        retrieval_evidence={"electricity_kwh": retrieval.model_dump()},
    )
    finding = next(item for item in result["findings"] if item["check_key"] == "retrieval_electricity_kwh")
    assert finding["result"] == "warning"
    assert "相似性" in finding["message"]


def test_tenant_and_enterprise_are_filtered_before_ranking(db_session):
    tenant_a, enterprise_a, user_a = _identity(db_session, "rag-tenant-a")
    tenant_b, enterprise_b, _user_b = _identity(db_session, "rag-tenant-b")
    document_a = _document(
        db_session,
        tenant_a,
        enterprise_a,
        marker="tenant-a-safe",
        fields={"electricity_kwh": "1000 kWh"},
    )
    document_b = _document(
        db_session,
        tenant_b,
        enterprise_b,
        marker="tenant-b-secret-canary",
        fields={"electricity_kwh": "TENANT_B_SECRET_998877 kWh"},
    )
    rag = get_rag_service()
    rag.index_document(db_session, document_a)
    rag.index_document(db_session, document_b)
    result = rag.search(
        db_session,
        tenant_id=tenant_a.id,
        enterprise_id=enterprise_a.id,
        actor_id=user_a.id,
        role_id="A-03",
        purpose="cross_tenant_attack",
        query_text="TENANT_B_SECRET_998877",
        corpus_types={"tenant_evidence"},
    )
    assert all(hit.source_ref != str(document_b.id) for hit in result.hits)
    run = db_session.get(RetrievalRun, uuid.UUID(result.retrieval_run_id))
    assert run is not None
    assert run.tenant_id == tenant_a.id
    assert run.filters_payload["tenant_scope_before_ranking"] is True


def test_role_cannot_request_an_unapproved_corpus(db_session):
    tenant, enterprise, user = _identity(db_session, "rag-role-boundary")
    with pytest.raises(RAGBoundaryError, match="cannot access"):
        get_rag_service().search(
            db_session,
            tenant_id=tenant.id,
            enterprise_id=enterprise.id,
            actor_id=user.id,
            role_id="R-01",
            purpose="forbidden_calculation_retrieval",
            query_text="calculate emissions from text",
            corpus_types={"tenant_evidence"},
        )


def test_h02_rejects_expired_rules_and_returns_current_approved_rule(db_session):
    tenant, enterprise, user = _identity(db_session, "rag-rule-validity")
    expired = register_authoritative_rule(
        db_session,
        tenant_id=tenant.id,
        actor_id=user.id,
        rule_kind="cbam_methodology",
        title="Expired methodology",
        publisher="European Commission",
        document_number=f"EU-2022-{uuid.uuid4().hex[:8].upper()}",
        jurisdiction="EU",
        vintage=2022,
        valid_from=datetime(2022, 1, 1, tzinfo=timezone.utc),
        valid_to=datetime(2025, 1, 1, tzinfo=timezone.utc),
        source_url="https://eur-lex.europa.eu/expired-test",
        source_content_hash="a" * 64,
    )
    current = register_authoritative_rule(
        db_session,
        tenant_id=tenant.id,
        actor_id=user.id,
        rule_kind="cbam_methodology",
        title="Current CBAM methodology",
        publisher="European Commission",
        document_number=f"EU-2023-{uuid.uuid4().hex[:8].upper()}",
        jurisdiction="EU",
        vintage=2023,
        valid_from=datetime(2023, 5, 17, tzinfo=timezone.utc),
        valid_to=None,
        source_url="https://eur-lex.europa.eu/current-test",
        source_content_hash="b" * 64,
    )
    rag = get_rag_service()
    rag.index_rule(db_session, expired)
    rag.index_rule(db_session, current)
    result = rag.search(
        db_session,
        tenant_id=tenant.id,
        enterprise_id=enterprise.id,
        actor_id=user.id,
        role_id="H-02",
        purpose="methodology_rule_review",
        query_text="current CBAM methodology",
        corpus_types={"public_methodology"},
        valid_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        jurisdiction="EU",
        field_key="methodology_ref",
    )
    assert {hit.source_ref for hit in result.hits} == {str(current.id)}


def test_retrieval_trace_redacts_credentials_and_is_replayable(db_session):
    tenant, enterprise, user = _identity(db_session, "rag-trace")
    document = _document(
        db_session,
        tenant,
        enterprise,
        marker="trace-document",
        fields={"electricity_kwh": "2048 kWh"},
    )
    rag = get_rag_service()
    rag.index_document(db_session, document)
    query = "2048 https://example.test/path?access_token=CANARY_SECRET_TOKEN_123456"
    first = rag.search(
        db_session,
        tenant_id=tenant.id,
        enterprise_id=enterprise.id,
        actor_id=user.id,
        role_id="A-03",
        purpose="trace_replay",
        query_text=query,
        corpus_types={"tenant_evidence"},
        source_ref=str(document.id),
        field_key="electricity_kwh",
    )
    second = rag.search(
        db_session,
        tenant_id=tenant.id,
        enterprise_id=enterprise.id,
        actor_id=user.id,
        role_id="A-03",
        purpose="trace_replay",
        query_text=query,
        corpus_types={"tenant_evidence"},
        source_ref=str(document.id),
        field_key="electricity_kwh",
    )
    first_run = db_session.get(RetrievalRun, uuid.UUID(first.retrieval_run_id))
    second_run = db_session.get(RetrievalRun, uuid.UUID(second.retrieval_run_id))
    assert first_run is not None and second_run is not None
    assert "CANARY_SECRET_TOKEN" not in first_run.query_text
    assert "[REDACTED]" in first_run.query_text
    assert first_run.result_hash == second_run.result_hash


def test_h02_passport_endpoint_returns_candidates_without_formal_write(db_session):
    tenant, enterprise, user = _identity(db_session, "rag-methodology-api")
    account = create_passport_account(
        db_session,
        tenant_id=tenant.id,
        enterprise_id=enterprise.id,
        actor_id=user.id,
        request_key=uuid.uuid4().hex,
        installation_name="热轧卷板生产装置",
        operator_name=enterprise.name,
        country_code="CN",
        unlocode="CNTGS",
        process_name="热轧主工序",
        aggregate_goods_category="iron_steel",
        production_route="bf_bof",
        product_name="热轧卷板",
        cn_code="72085100",
    )
    rule = register_authoritative_rule(
        db_session,
        tenant_id=tenant.id,
        actor_id=user.id,
        rule_kind="cbam_methodology",
        title="CBAM hot rolled coil methodology",
        publisher="European Commission",
        document_number=f"EU-2023-{uuid.uuid4().hex[:8].upper()}",
        jurisdiction="EU",
        vintage=2023,
        valid_from=datetime(2023, 5, 17, tzinfo=timezone.utc),
        valid_to=None,
        source_url="https://eur-lex.europa.eu/hot-rolled-coil-test",
        source_content_hash="c" * 64,
    )
    response = search_methodology_candidates(
        account.id,
        MethodologySearchRequest(
            period_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            period_end=datetime(2026, 3, 31, tzinfo=timezone.utc),
        ),
        db_session,
        user,
    )
    assert response["candidates"]
    assert response["candidates"][0]["rule"]["id"] == str(rule.id)
    assert response["candidates"][0]["formal_write_allowed"] is False
    assert response["human_gate"].startswith("H-02")
