"""Tests for data inbox upload confirmation workflow."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
from unittest.mock import Mock

from fastapi.testclient import TestClient
from passlib.context import CryptContext
import pytest
from sqlalchemy.exc import IntegrityError

from backend.database import Base, get_engine, get_sessionmaker
from backend.main import app
from backend.models.activity_data import ActivityData
from backend.models.document import DocumentStore
from backend.models.emission_factor import EmissionFactor
from backend.models.emission_result import EmissionResult
from backend.models.emission_source import EmissionSource
from backend.models.enterprise import Enterprise
from backend.models.tenant import Tenant
from backend.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def setup_module():
    Base.metadata.create_all(bind=get_engine())


def teardown_module():
    Base.metadata.drop_all(bind=get_engine())


def _session():
    return get_sessionmaker()()


def _tenant(db, slug: str) -> Tenant:
    tenant = Tenant(name=slug.upper(), slug=slug)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def _enterprise(db, tenant: Tenant, suffix: str) -> Enterprise:
    enterprise = Enterprise(
        name=f"华盛钢铁 {suffix}",
        unified_social_credit_code=f"91110000123456{suffix:0>4}",
        industry_code="C31",
        industry_name="黑色金属冶炼和压延加工业",
        tenant_id=tenant.id,
    )
    db.add(enterprise)
    db.commit()
    db.refresh(enterprise)
    return enterprise


def _user(db, tenant: Tenant, enterprise: Enterprise, email: str) -> User:
    user = User(
        email=email,
        password_hash=pwd_context.hash("secret123"),
        role="admin",
        tenant_id=tenant.id,
        enterprise_id=enterprise.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login(client: TestClient, email: str) -> str:
    resp = client.post("/api/auth/login", json={"email": email, "password": "secret123"})
    assert resp.status_code == 200, resp.json()
    return resp.json()["access_token"]


def _document(
    db,
    tenant: Tenant,
    enterprise: Enterprise,
    *,
    filename: str = "source.csv",
    doc_type: str = "electricity_bill",
) -> DocumentStore:
    document = DocumentStore(
        tenant_id=tenant.id,
        enterprise_id=enterprise.id,
        filename=filename,
        mime_type="text/csv",
        size_bytes=32,
        storage_path=f"tests/{uuid.uuid4()}/{filename}",
        content_hash=uuid.uuid4().hex * 2,
        doc_type=doc_type,
        ocr_status="completed",
        ocr_result={"fields": {}, "confidence": 0},
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def _prepare_candidate(
    client: TestClient,
    token: str,
    document: DocumentStore,
    fields: dict,
) -> dict:
    response = client.post(
        f"/api/upload/{document.id}/candidate",
        headers={"Authorization": f"Bearer {token}"},
        json={"fields": fields},
    )
    assert response.status_code == 200, response.json()
    return response.json()


def _prepare_quality_review(
    client: TestClient,
    token: str,
    document: DocumentStore,
    fields: dict,
    candidate: dict,
) -> dict:
    response = client.post(
        f"/api/upload/{document.id}/quality-review",
        headers={"Authorization": f"Bearer {token}"},
        json={"candidate_token": candidate["candidate_token"], "fields": fields},
    )
    assert response.status_code == 200, response.json()
    return response.json()


def test_confirm_activity_requires_exact_server_signed_candidate_snapshot():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-candidate-lock")
        enterprise = _enterprise(db, tenant, "81")
        _user(db, tenant, enterprise, "upload-candidate-lock@example.com")
        document = _document(db, tenant, enterprise, filename="candidate-lock.csv")
        token = _login(client, "upload-candidate-lock@example.com")
        fields = {
            "electricity_kwh": "632600",
            "period": "2026-03",
            "facility": "炼钢厂",
        }
        candidate = _prepare_candidate(client, token, document, fields)
        quality = _prepare_quality_review(client, token, document, fields, candidate)

        tampered = client.post(
            "/api/upload/confirm-activity",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "candidate_token": candidate["candidate_token"],
                "quality_review_token": quality["quality_review_token"],
                "file_id": str(document.id),
                "document_content_hash": document.content_hash,
                "filename": document.filename,
                "document_type": "electricity_bill",
                "fields": {**fields, "electricity_kwh": "1"},
            },
        )
        assert tampered.status_code == 409, tampered.json()
        assert "候选快照" in tampered.json()["detail"]
        assert db.query(ActivityData).filter(ActivityData.tenant_id == tenant.id).count() == 0

        confirmed = client.post(
            "/api/upload/confirm-activity",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "candidate_token": candidate["candidate_token"],
                "quality_review_token": quality["quality_review_token"],
                "file_id": str(document.id),
                "document_content_hash": document.content_hash,
                "filename": document.filename,
                "document_type": "electricity_bill",
                "fields": fields,
            },
        )
        assert confirmed.status_code == 200, confirmed.json()
        assert confirmed.json()["confirmation"]["candidate_id"] == candidate["candidate_id"]
        assert confirmed.json()["confirmation"]["subject_sha256"] == candidate["subject_sha256"]

        activity_id = uuid.UUID(confirmed.json()["formal_write"]["activity_data_id"])
        with pytest.raises(IntegrityError):
            db.execute(
                ActivityData.__table__.update()
                .where(ActivityData.id == activity_id)
                .values(quantity=Decimal("-1"))
            )
            db.commit()
        db.rollback()
    finally:
        db.close()


def test_confirm_activity_requires_independent_a03_quality_gate():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-quality-gate")
        enterprise = _enterprise(db, tenant, "83")
        _user(db, tenant, enterprise, "upload-quality-gate@example.com")
        document = _document(db, tenant, enterprise, filename="quality-gate.csv")
        token = _login(client, "upload-quality-gate@example.com")
        fields = {
            "electricity_kwh": "632600 kWh",
            "period": "2026-03",
            "facility": "炼钢厂",
        }
        candidate = _prepare_candidate(client, token, document, fields)

        blocked = client.post(
            "/api/upload/confirm-activity",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "candidate_token": candidate["candidate_token"],
                "file_id": str(document.id),
                "document_content_hash": document.content_hash,
                "filename": document.filename,
                "document_type": "electricity_bill",
                "fields": fields,
            },
        )
        assert blocked.status_code == 409, blocked.json()
        assert "A-03" in blocked.json()["detail"]
        assert db.query(ActivityData).filter(ActivityData.tenant_id == tenant.id).count() == 0

        quality = _prepare_quality_review(client, token, document, fields, candidate)
        assert quality["quality_status"] in {"pass", "pass_with_warnings"}
        assert quality["formal_write_allowed"] is False
        assert quality["next_gate"].startswith("H-01")
    finally:
        db.close()


def test_a03_quality_token_is_bound_to_one_exact_candidate():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-quality-binding")
        enterprise = _enterprise(db, tenant, "84")
        _user(db, tenant, enterprise, "upload-quality-binding@example.com")
        document = _document(db, tenant, enterprise, filename="quality-binding.csv")
        token = _login(client, "upload-quality-binding@example.com")
        fields = {
            "electricity_kwh": "632600 kWh",
            "period": "2026-03",
            "facility": "炼钢厂",
        }
        first_candidate = _prepare_candidate(client, token, document, fields)
        first_quality = _prepare_quality_review(
            client,
            token,
            document,
            fields,
            first_candidate,
        )
        second_candidate = _prepare_candidate(client, token, document, fields)

        response = client.post(
            "/api/upload/confirm-activity",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "candidate_token": second_candidate["candidate_token"],
                "quality_review_token": first_quality["quality_review_token"],
                "file_id": str(document.id),
                "document_content_hash": document.content_hash,
                "filename": document.filename,
                "document_type": "electricity_bill",
                "fields": fields,
            },
        )

        assert response.status_code == 409, response.json()
        assert "当前候选" in response.json()["detail"]
        assert db.query(ActivityData).filter(ActivityData.tenant_id == tenant.id).count() == 0
    finally:
        db.close()


def test_workforce_contract_endpoint_exposes_permissions_and_human_gates():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-workforce-contract")
        enterprise = _enterprise(db, tenant, "85")
        _user(db, tenant, enterprise, "upload-workforce-contract@example.com")
        token = _login(client, "upload-workforce-contract@example.com")

        response = client.get(
            "/api/upload/workforce/roles",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200, response.json()
        payload = response.json()
        assert payload["contract_version"] == "carbon-passport-workforce-v1.0"
        roles = {item["role_id"]: item for item in payload["roles"]}
        assert set(roles) == {"H-00", "A-01", "A-02", "A-03", "H-01", "H-02", "R-01", "A-04", "H-03"}
        assert roles["A-03"]["human_gate"] is False
        assert "代替人工确认" in roles["A-03"]["forbidden_actions"]
        assert roles["H-01"]["human_gate"] is True
        assert "调用 LLM 生成结果" in roles["R-01"]["forbidden_actions"]
    finally:
        db.close()


def test_document_workflow_exposes_clickable_agent_run_history():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-agent-history")
        enterprise = _enterprise(db, tenant, "87")
        _user(db, tenant, enterprise, "upload-agent-history@example.com")
        document = _document(db, tenant, enterprise, filename="agent-history.csv")
        document.ocr_result = {
            "fields": {
                "electricity_kwh": "632600 kWh",
                "period": "2026-03",
                "facility": "炼钢厂",
            },
            "raw_text": "用电量 632600 kWh，账单月份 2026-03，所属工厂 炼钢厂",
            "confidence": 0.98,
        }
        db.commit()
        token = _login(client, "upload-agent-history@example.com")
        fields = dict(document.ocr_result["fields"])
        candidate = _prepare_candidate(client, token, document, fields)
        quality = _prepare_quality_review(client, token, document, fields, candidate)
        confirmed = client.post(
            "/api/upload/confirm-activity",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "candidate_token": candidate["candidate_token"],
                "quality_review_token": quality["quality_review_token"],
                "file_id": str(document.id),
                "document_content_hash": document.content_hash,
                "filename": document.filename,
                "document_type": "electricity_bill",
                "fields": fields,
            },
        )
        assert confirmed.status_code == 200, confirmed.json()

        history = client.get(
            f"/api/agent-ops/runs?source_file_id={document.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert history.status_code == 200, history.json()
        by_agent = {item["agent_id"]: item for item in history.json()["runs"]}
        assert {"A-02", "A-03", "H-01"}.issubset(by_agent)
        assert by_agent["A-03"]["skill"]["skill_id"] == "carbon-evidence-quality-review"

        detail = client.get(
            f"/api/agent-ops/runs/{by_agent['A-03']['run_id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert detail.status_code == 200, detail.json()
        assert detail.json()["event_chain_verified"] is True
        assert [event["event_type"] for event in detail.json()["events"]] == [
            "task_started",
            "candidate_binding_verified",
            "evidence_retrieved",
            "quality_gate_evaluated",
            "task_completed",
        ]
    finally:
        db.close()


def test_a03_does_not_treat_a_value_from_an_unrelated_source_field_as_evidence():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-quality-field-association")
        enterprise = _enterprise(db, tenant, "86")
        _user(db, tenant, enterprise, "upload-quality-field-association@example.com")
        document = _document(db, tenant, enterprise, filename="field-association.csv")
        document.ocr_result = {
            "fields": {
                "electricity_kwh": "632600 kWh",
                "period": "2026",
                "facility": "炼钢厂",
            },
            "raw_text": "炼钢厂 2026 632600 kWh",
            "confidence": 99,
        }
        db.commit()
        token = _login(client, "upload-quality-field-association@example.com")
        fields = {
            # 2026 exists in the document, but only as the reporting period. It
            # must not be accepted as evidence for electricity consumption.
            "electricity_kwh": "2026 kWh",
            "period": "2026",
            "facility": "炼钢厂",
        }
        candidate = _prepare_candidate(client, token, document, fields)

        quality = _prepare_quality_review(client, token, document, fields, candidate)

        electricity_evidence = next(
            item for item in quality["findings"]
            if item["check_key"] == "evidence_electricity_kwh"
        )
        assert electricity_evidence["result"] == "warning"
        assert quality["quality_status"] == "pass_with_warnings"
    finally:
        db.close()


def test_confirm_activity_writes_workflow_checkpoint():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-confirm")
        enterprise = _enterprise(db, tenant, "31")
        _user(db, tenant, enterprise, "upload-confirm@example.com")
        document = _document(
            db,
            tenant,
            enterprise,
            filename="电费单_2026-03.pdf",
        )
        token = _login(client, "upload-confirm@example.com")
        fields = {
            "electricity_kwh": "632600",
            "total_amount": "645805.08",
            "period": "2026-03-01 至 2026-03-31",
            "customer_name": "华盛钢铁有限公司（炼钢厂）",
            "facility": "炼钢厂",
        }
        candidate = _prepare_candidate(client, token, document, fields)
        quality = _prepare_quality_review(client, token, document, fields, candidate)

        resp = client.post(
            "/api/upload/confirm-activity",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "candidate_token": candidate["candidate_token"],
                "quality_review_token": quality["quality_review_token"],
                "file_id": str(document.id),
                "document_content_hash": document.content_hash,
                "filename": document.filename,
                "document_type": "electricity_bill",
                "confidence": 93.0,
                "fields": fields,
            },
        )
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["status"] == "written"
        assert body["step_key"] == "energy_data"
        assert body["activity_record"]["quantity"] == 632600.0
        assert body["activity_record"]["unit"] == "kWh"
        assert body["formal_write"]["activity_data_id"]
        assert body["formal_write"]["emission_source_id"]
        assert body["formal_write"]["calculation_status"] == "pending_factor"
        assert body["workflow"]["tenant_id"] == str(tenant.id)
        energy_step = next(step for step in body["workflow"]["steps"] if step["step_key"] == "energy_data")
        assert energy_step["checkpoints"][-1]["type"] == "data_inbox_activity_write"
        assert energy_step["checkpoints"][-1]["formal_write"]["activity_data_id"] == body["formal_write"]["activity_data_id"]
        assert energy_step["outputs"]["last_activity_data"]["file_id"] == str(document.id)
        assert energy_step["outputs"]["last_formal_activity_write"]["activity_data_id"] == body["formal_write"]["activity_data_id"]
    finally:
        db.close()


def test_confirm_activity_requires_authentication():
    client = TestClient(app)
    resp = client.post(
        "/api/upload/confirm-activity",
        json={"filename": "x.pdf", "fields": {}},
    )
    assert resp.status_code == 401


def test_upload_requires_authentication():
    client = TestClient(app)
    resp = client.post(
        "/api/upload",
        files={"file": ("electricity.csv", "账单月份,用电量\n2026年03月,632600 kWh\n".encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 401


def test_upload_inbox_list_and_download_require_authentication():
    client = TestClient(app)

    list_response = client.get("/api/upload")
    download_response = client.get(f"/api/upload/{uuid.uuid4()}/download")

    assert list_response.status_code == 401
    assert download_response.status_code == 401


def test_upload_inbox_lists_only_current_tenant_and_enterprise_in_stable_order(monkeypatch):
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-inbox-list")
        enterprise = _enterprise(db, tenant, "51")
        other_enterprise = _enterprise(db, tenant, "52")
        other_tenant = _tenant(db, "upload-inbox-list-other")
        other_tenant_enterprise = _enterprise(db, other_tenant, "53")
        _user(db, tenant, enterprise, "upload-inbox-list@example.com")

        created_at = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
        older = DocumentStore(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            tenant_id=tenant.id,
            enterprise_id=enterprise.id,
            filename="older.csv",
            mime_type="text/csv",
            size_bytes=120,
            storage_path="tenant/older.csv",
            content_hash="1" * 64,
            doc_type="electricity_bill",
            ocr_status="completed",
            ocr_result=None,
            ocr_error="OCR warning",
            created_at=created_at - timedelta(days=1),
        )
        lower_id = DocumentStore(
            id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            tenant_id=tenant.id,
            enterprise_id=enterprise.id,
            filename="lower-id.pdf",
            mime_type="application/pdf",
            size_bytes=240,
            storage_path="tenant/lower-id.pdf",
            content_hash="2" * 64,
            doc_type="invoice",
            ocr_status="completed",
            ocr_result={
                "fields": {"invoice_number": "INV-2"},
                "confidence": 91.5,
                "raw_text": "lower id text",
                "tables": [[{"invoice_number": "INV-2"}]],
                "errors": [],
            },
            created_at=created_at,
        )
        higher_id = DocumentStore(
            id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
            tenant_id=tenant.id,
            enterprise_id=enterprise.id,
            filename="higher-id.pdf",
            mime_type="application/pdf",
            size_bytes=360,
            storage_path="tenant/higher-id.pdf",
            content_hash="3" * 64,
            doc_type="invoice",
            ocr_status="failed",
            ocr_result={
                "fields": {},
                "confidence": 0,
                "raw_text": "",
                "tables": [],
                "errors": ["unreadable"],
            },
            created_at=created_at,
        )
        same_tenant_other_enterprise = DocumentStore(
            tenant_id=tenant.id,
            enterprise_id=other_enterprise.id,
            filename="other-enterprise.pdf",
            mime_type="application/pdf",
            size_bytes=480,
            storage_path="tenant/other-enterprise.pdf",
            content_hash="4" * 64,
            doc_type="invoice",
            ocr_status="completed",
            created_at=created_at + timedelta(days=1),
        )
        other_tenant_document = DocumentStore(
            tenant_id=other_tenant.id,
            enterprise_id=other_tenant_enterprise.id,
            filename="other-tenant.pdf",
            mime_type="application/pdf",
            size_bytes=600,
            storage_path="other-tenant/document.pdf",
            content_hash="5" * 64,
            doc_type="invoice",
            ocr_status="completed",
            created_at=created_at + timedelta(days=2),
        )
        db.add_all(
            [
                older,
                lower_id,
                higher_id,
                same_tenant_other_enterprise,
                other_tenant_document,
            ]
        )
        db.commit()

        storage = Mock()

        def presigned_url(storage_path: str, expires_hours: int = 1):
            if storage_path == older.storage_path:
                raise RuntimeError("storage unavailable")
            return f"https://files.example/{storage_path}?expires={expires_hours}"

        storage.presigned_url.side_effect = presigned_url
        monkeypatch.setattr("backend.api.upload.get_storage", lambda: storage)
        token = _login(client, "upload-inbox-list@example.com")

        response = client.get(
            "/api/upload",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200, response.json()
        body = response.json()
        assert [item["file_id"] for item in body] == [
            str(higher_id.id),
            str(lower_id.id),
            str(older.id),
        ]
        assert body[0] == {
            "file_id": str(higher_id.id),
            "content_hash": higher_id.content_hash,
            "filename": higher_id.filename,
            "mime_type": higher_id.mime_type,
            "size_bytes": higher_id.size_bytes,
            "storage_url": f"/api/upload/{higher_id.id}/download",
            "document_type": higher_id.doc_type,
            "fields": {},
            "confidence": 0,
            "raw_text": "",
            "tables": [],
                "errors": ["unreadable"],
                "ocr_status": "failed",
                "workforce": {},
                "created_at": higher_id.created_at.isoformat().replace("+00:00", "Z"),
            }
        assert body[2]["storage_url"] == f"/api/upload/{older.id}/download"
        assert body[2]["errors"] == ["OCR warning"]
        assert all("storage_path" not in item for item in body)
        assert str(same_tenant_other_enterprise.id) not in {item["file_id"] for item in body}
        assert str(other_tenant_document.id) not in {item["file_id"] for item in body}
    finally:
        db.close()


def test_upload_download_uses_owned_document_store_record(monkeypatch):
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-download-owner")
        enterprise = _enterprise(db, tenant, "54")
        other_tenant = _tenant(db, "upload-download-other")
        other_enterprise = _enterprise(db, other_tenant, "55")
        _user(db, tenant, enterprise, "upload-download-owner@example.com")
        owned = DocumentStore(
            tenant_id=tenant.id,
            enterprise_id=enterprise.id,
            filename="owned.pdf",
            mime_type="application/pdf",
            size_bytes=120,
            storage_path="owned/private-object.pdf",
            content_hash="6" * 64,
            doc_type="invoice",
            ocr_status="completed",
        )
        foreign = DocumentStore(
            tenant_id=other_tenant.id,
            enterprise_id=other_enterprise.id,
            filename="foreign.pdf",
            mime_type="application/pdf",
            size_bytes=120,
            storage_path="foreign/private-object.pdf",
            content_hash="7" * 64,
            doc_type="invoice",
            ocr_status="completed",
        )
        db.add_all([owned, foreign])
        db.commit()
        db.refresh(owned)
        db.refresh(foreign)

        storage = Mock()
        storage.download.return_value = b"%PDF-1.7 owned demo"
        monkeypatch.setattr("backend.api.upload.get_storage", lambda: storage)
        token = _login(client, "upload-download-owner@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        owned_response = client.get(f"/api/upload/{owned.id}/download", headers=headers)
        foreign_response = client.get(f"/api/upload/{foreign.id}/download", headers=headers)

        assert owned_response.status_code == 200
        assert owned_response.content == b"%PDF-1.7 owned demo"
        assert owned_response.headers["content-type"].startswith("application/pdf")
        assert owned_response.headers["content-disposition"].startswith("inline;")
        assert "owned.pdf" in owned_response.headers["content-disposition"]
        assert owned_response.headers["cache-control"] == "private, no-store"
        assert foreign_response.status_code == 404
        storage.download.assert_called_once_with(owned.storage_path)
        storage.list_objects.assert_not_called()
    finally:
        db.close()


def test_authenticated_csv_upload_extracts_table_fields():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-csv")
        enterprise = _enterprise(db, tenant, "32")
        _user(db, tenant, enterprise, "upload-csv@example.com")
        token = _login(client, "upload-csv@example.com")

        content = (
            "账单月份,用电量,金额,单位,供应商,抄表日期,所属工厂\n"
            "2026年03月,632600 kWh,645805.08 元,元,"
            "国网江苏省电力有限公司 张家港供电分公司,2026-03-31,炼钢厂\n"
        ).encode("utf-8")
        resp = client.post(
            "/api/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("electricity.csv", content, "text/csv")},
        )

        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert len(body["content_hash"]) == 64
        assert body["document_type"] == "electricity_bill"
        assert body["fields"]["electricity_kwh"] == "632600 kWh"
        assert body["fields"]["period"] == "2026年03月"
        assert body["fields"]["facility"] == "炼钢厂"
        assert body["confidence"] >= 50
    finally:
        db.close()


def test_same_uploaded_content_reuses_tenant_document_record():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-document-idempotent")
        enterprise = _enterprise(db, tenant, "35")
        _user(db, tenant, enterprise, "upload-document-idempotent@example.com")
        token = _login(client, "upload-document-idempotent@example.com")
        content = "账单月份,用电量\n2026年03月,632600 kWh\n".encode("utf-8")

        first = client.post(
            "/api/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("same.csv", content, "text/csv")},
        )
        second = client.post(
            "/api/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("same.csv", content, "text/csv")},
        )

        assert first.status_code == 200, first.json()
        assert second.status_code == 200, second.json()
        assert first.json()["file_id"] == second.json()["file_id"]
        assert first.json()["content_hash"] == second.json()["content_hash"]
        assert second.json()["reused"] is True
        from backend.models.document import DocumentStore

        assert (
            db.query(DocumentStore)
            .filter(DocumentStore.tenant_id == tenant.id)
            .count()
            == 1
        )
    finally:
        db.close()


def test_same_uploaded_content_is_isolated_between_enterprises():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-document-enterprise-dedupe")
        enterprise_a = _enterprise(db, tenant, "71")
        enterprise_b = _enterprise(db, tenant, "72")
        _user(db, tenant, enterprise_a, "upload-dedupe-a@example.com")
        _user(db, tenant, enterprise_b, "upload-dedupe-b@example.com")
        token_a = _login(client, "upload-dedupe-a@example.com")
        token_b = _login(client, "upload-dedupe-b@example.com")
        content = "账单月份,用电量\n2026年03月,632600 kWh\n".encode("utf-8")

        response_a = client.post(
            "/api/upload",
            headers={"Authorization": f"Bearer {token_a}"},
            files={"file": ("same.csv", content, "text/csv")},
        )
        response_b = client.post(
            "/api/upload",
            headers={"Authorization": f"Bearer {token_b}"},
            files={"file": ("same.csv", content, "text/csv")},
        )

        assert response_a.status_code == 200, response_a.json()
        assert response_b.status_code == 200, response_b.json()
        assert response_a.json()["content_hash"] == response_b.json()["content_hash"]
        assert response_a.json()["file_id"] != response_b.json()["file_id"]
        assert response_a.json()["reused"] is False
        assert response_b.json()["reused"] is False

        list_a = client.get(
            "/api/upload",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        list_b = client.get(
            "/api/upload",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert {item["file_id"] for item in list_a.json()} == {response_a.json()["file_id"]}
        assert {item["file_id"] for item in list_b.json()} == {response_b.json()["file_id"]}
    finally:
        db.close()


def test_confirm_activity_requires_owned_server_evidence():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-require-evidence")
        enterprise = _enterprise(db, tenant, "73")
        _user(db, tenant, enterprise, "upload-require-evidence@example.com")
        token = _login(client, "upload-require-evidence@example.com")

        response = client.post(
            "/api/upload/confirm-activity",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "filename": "untracked.csv",
                "document_type": "electricity_bill",
                "fields": {
                    "electricity_kwh": "632600",
                    "period": "2026-03",
                    "facility": "炼钢厂",
                },
            },
        )

        assert response.status_code == 400
        assert "源文件" in response.json()["detail"]
        assert db.query(ActivityData).filter(ActivityData.tenant_id == tenant.id).count() == 0
    finally:
        db.close()


def test_confirm_activity_requires_source_content_hash():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-require-content-hash")
        enterprise = _enterprise(db, tenant, "74")
        _user(db, tenant, enterprise, "upload-require-content-hash@example.com")
        document = _document(db, tenant, enterprise, filename="source-hash.csv")
        token = _login(client, "upload-require-content-hash@example.com")

        response = client.post(
            "/api/upload/confirm-activity",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "file_id": str(document.id),
                "filename": document.filename,
                "document_type": "electricity_bill",
                "fields": {
                    "electricity_kwh": "632600",
                    "period": "2026-03",
                    "facility": "炼钢厂",
                },
            },
        )

        assert response.status_code == 400
        assert "content_hash" in response.json()["detail"]
        assert db.query(ActivityData).filter(ActivityData.tenant_id == tenant.id).count() == 0
    finally:
        db.close()


def test_confirm_activity_rejects_document_owned_by_another_tenant():
    client = TestClient(app)
    db = _session()
    try:
        tenant_a = _tenant(db, "upload-document-owner-a")
        enterprise_a = _enterprise(db, tenant_a, "41")
        tenant_b = _tenant(db, "upload-document-owner-b")
        enterprise_b = _enterprise(db, tenant_b, "42")
        _user(db, tenant_b, enterprise_b, "upload-document-owner-b@example.com")
        document = DocumentStore(
            tenant_id=tenant_a.id,
            enterprise_id=enterprise_a.id,
            filename="tenant-a.csv",
            mime_type="text/csv",
            size_bytes=16,
            storage_path="tenant-a/source.csv",
            content_hash="a" * 64,
            doc_type="electricity_bill",
            ocr_status="completed",
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        token = _login(client, "upload-document-owner-b@example.com")

        response = client.post(
            "/api/upload/confirm-activity",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "file_id": str(document.id),
                "filename": document.filename,
                "document_type": "electricity_bill",
                "fields": {
                    "electricity_kwh": "632600",
                    "period": "2026-03",
                    "facility": "炼钢厂",
                },
            },
        )

        assert response.status_code == 404
        assert "无权访问" in response.json()["detail"]
        assert (
            db.query(ActivityData)
            .filter(ActivityData.tenant_id == tenant_b.id)
            .count()
            == 0
        )
    finally:
        db.close()


def test_confirm_activity_rejects_document_owned_by_another_enterprise():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-document-enterprise")
        enterprise_a = _enterprise(db, tenant, "61")
        enterprise_b = _enterprise(db, tenant, "62")
        _user(db, tenant, enterprise_b, "upload-document-enterprise-b@example.com")
        document = DocumentStore(
            tenant_id=tenant.id,
            enterprise_id=enterprise_a.id,
            filename="enterprise-a.csv",
            mime_type="text/csv",
            size_bytes=16,
            storage_path="enterprise-a/source.csv",
            content_hash="e" * 64,
            doc_type="electricity_bill",
            ocr_status="completed",
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        token = _login(client, "upload-document-enterprise-b@example.com")

        response = client.post(
            "/api/upload/confirm-activity",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "file_id": str(document.id),
                "filename": document.filename,
                "document_type": "electricity_bill",
                "fields": {
                    "electricity_kwh": "632600",
                    "period": "2026-03",
                    "facility": "炼钢厂",
                },
            },
        )

        assert response.status_code == 404
        assert "无权访问" in response.json()["detail"]
        assert db.query(ActivityData).filter(ActivityData.tenant_id == tenant.id).count() == 0
    finally:
        db.close()


def test_confirm_activity_rejects_nonexistent_document_reference():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-document-missing")
        enterprise = _enterprise(db, tenant, "45")
        _user(db, tenant, enterprise, "upload-document-missing@example.com")
        token = _login(client, "upload-document-missing@example.com")

        response = client.post(
            "/api/upload/confirm-activity",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "file_id": str(uuid.uuid4()),
                "filename": "missing.csv",
                "document_type": "electricity_bill",
                "fields": {
                    "electricity_kwh": "632600",
                    "period": "2026-03",
                    "facility": "炼钢厂",
                },
            },
        )

        assert response.status_code == 404
        assert "不存在" in response.json()["detail"]
        assert (
            db.query(ActivityData)
            .filter(ActivityData.tenant_id == tenant.id)
            .count()
            == 0
        )
    finally:
        db.close()


def test_confirm_activity_preserves_large_integer_quantity_exactly():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-exact-integer")
        enterprise = _enterprise(db, tenant, "43")
        _user(db, tenant, enterprise, "upload-exact-integer@example.com")
        document = _document(db, tenant, enterprise, filename="large-meter-reading.csv")
        token = _login(client, "upload-exact-integer@example.com")
        fields = {
            "electricity_kwh": 9007199254740993,
            "period": "2026-03",
            "facility": "炼钢厂",
        }
        candidate = _prepare_candidate(client, token, document, fields)
        quality = _prepare_quality_review(client, token, document, fields, candidate)

        response = client.post(
            "/api/upload/confirm-activity",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "candidate_token": candidate["candidate_token"],
                "quality_review_token": quality["quality_review_token"],
                "file_id": str(document.id),
                "document_content_hash": document.content_hash,
                "filename": document.filename,
                "document_type": "electricity_bill",
                "fields": fields,
            },
        )

        assert response.status_code == 200, response.json()
        activity_id = uuid.UUID(response.json()["formal_write"]["activity_data_id"])
        activity = db.get(ActivityData, activity_id)
        assert activity is not None
        assert activity.quantity == Decimal("9007199254740993.000000000000")
        assert response.json()["activity_record"]["quantity"] == 9007199254740993
    finally:
        db.close()


def test_confirm_activity_rejects_binary_float_quantity():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-reject-float")
        enterprise = _enterprise(db, tenant, "44")
        _user(db, tenant, enterprise, "upload-reject-float@example.com")
        document = _document(db, tenant, enterprise, filename="float-reading.csv")
        token = _login(client, "upload-reject-float@example.com")

        response = client.post(
            "/api/upload/confirm-activity",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "file_id": str(document.id),
                "document_content_hash": document.content_hash,
                "filename": document.filename,
                "document_type": "electricity_bill",
                "fields": {
                    "electricity_kwh": 0.1,
                    "period": "2026-03",
                    "facility": "炼钢厂",
                },
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "缺少可写入的用电量字段"
    finally:
        db.close()


def test_confirm_activity_rejects_negative_quantity_after_candidate_lock():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-reject-negative")
        enterprise = _enterprise(db, tenant, "82")
        _user(db, tenant, enterprise, "upload-reject-negative@example.com")
        document = _document(db, tenant, enterprise, filename="negative-reading.csv")
        token = _login(client, "upload-reject-negative@example.com")
        fields = {
            "electricity_kwh": "-632600",
            "period": "2026-03",
            "facility": "炼钢厂",
        }
        candidate = _prepare_candidate(client, token, document, fields)
        quality = _prepare_quality_review(client, token, document, fields, candidate)
        assert quality["quality_status"] == "fail"

        response = client.post(
            "/api/upload/confirm-activity",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "candidate_token": candidate["candidate_token"],
                "quality_review_token": quality["quality_review_token"],
                "file_id": str(document.id),
                "document_content_hash": document.content_hash,
                "filename": document.filename,
                "document_type": "electricity_bill",
                "fields": fields,
            },
        )

        assert response.status_code == 409, response.json()
        assert "质检存在阻断项" in response.json()["detail"]
        assert db.query(ActivityData).filter(ActivityData.tenant_id == tenant.id).count() == 0
    finally:
        db.close()


def test_confirm_activity_requires_visible_period_and_facility():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-required-context")
        enterprise = _enterprise(db, tenant, "63")
        _user(db, tenant, enterprise, "upload-required-context@example.com")
        document = _document(db, tenant, enterprise, filename="required-context.csv")
        token = _login(client, "upload-required-context@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        missing_period = client.post(
            "/api/upload/confirm-activity",
            headers=headers,
            json={
                "file_id": str(document.id),
                "document_content_hash": document.content_hash,
                "filename": document.filename,
                "document_type": "electricity_bill",
                "fields": {"electricity_kwh": "100", "facility": "炼钢厂"},
            },
        )
        missing_facility = client.post(
            "/api/upload/confirm-activity",
            headers=headers,
            json={
                "file_id": str(document.id),
                "document_content_hash": document.content_hash,
                "filename": document.filename,
                "document_type": "electricity_bill",
                "fields": {"electricity_kwh": "100", "period": "2026-03"},
            },
        )

        assert missing_period.status_code == 400
        assert "报告期间" in missing_period.json()["detail"]
        assert missing_facility.status_code == 400
        assert "所属设施" in missing_facility.json()["detail"]
        assert db.query(ActivityData).filter(ActivityData.tenant_id == tenant.id).count() == 0
    finally:
        db.close()


def test_confirm_activity_rejects_non_electricity_documents_from_activity_ledger():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-production-boundary")
        enterprise = _enterprise(db, tenant, "64")
        _user(db, tenant, enterprise, "upload-production-boundary@example.com")
        document = _document(
            db,
            tenant,
            enterprise,
            filename="production.xlsx",
            doc_type="production_report",
        )
        token = _login(client, "upload-production-boundary@example.com")

        response = client.post(
            "/api/upload/confirm-activity",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "file_id": str(document.id),
                "document_content_hash": document.content_hash,
                "filename": document.filename,
                "document_type": "production_report",
                "fields": {
                    "production_output": "1000",
                    "unit": "t",
                    "period_start": "2026-01-01",
                    "period_end": "2026-03-31",
                    "facility": "热轧装置",
                },
            },
        )

        assert response.status_code == 400
        assert "仅支持电费活动数据" in response.json()["detail"]
        assert db.query(ActivityData).filter(ActivityData.tenant_id == tenant.id).count() == 0
    finally:
        db.close()


def test_confirm_activity_requires_human_factor_gate_before_emission_result():
    client = TestClient(app)
    db = _session()
    try:
        tenant = _tenant(db, "upload-formal")
        enterprise = _enterprise(db, tenant, "33")
        _user(db, tenant, enterprise, "upload-formal@example.com")
        factor = EmissionFactor(
            tenant_id=tenant.id,
            name="华东电网测试因子",
            code="TEST-GRID-EAST-2026",
            category="electricity_grid",
            region="华东",
            year=2026,
            value=Decimal("0.6380"),
            unit="kgCO2/kWh",
            source="test",
            uncertainty=3.0,
            is_default=True,
        )
        document = DocumentStore(
            tenant_id=tenant.id,
            enterprise_id=enterprise.id,
            filename="电费单_2026-03.pdf",
            mime_type="application/pdf",
            size_bytes=120,
            storage_path="upload-formal/electricity.pdf",
            content_hash="8" * 64,
            doc_type="electricity_bill",
            ocr_status="completed",
            ocr_result={"fields": {"electricity_kwh": "632600"}, "confidence": 0.8},
        )
        db.add_all([factor, document])
        db.commit()
        db.refresh(document)
        token = _login(client, "upload-formal@example.com")

        payload = {
            "file_id": str(document.id),
            "document_content_hash": document.content_hash,
            "filename": "电费单_2026-03.pdf",
            "document_type": "electricity_bill",
            "confidence": 96.0,
            "fields": {
                "electricity_kwh": "632,600 kWh",
                "total_amount": "645,805.08 元",
                "period": "2026-03-01 至 2026-03-31",
                "supplier_name": "国网江苏省电力有限公司",
                "facility": "炼钢厂",
            },
        }
        candidate = _prepare_candidate(client, token, document, payload["fields"])
        quality = _prepare_quality_review(client, token, document, payload["fields"], candidate)
        payload["candidate_token"] = candidate["candidate_token"]
        payload["quality_review_token"] = quality["quality_review_token"]

        first = client.post(
            "/api/upload/confirm-activity",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        assert first.status_code == 200, first.json()
        second = client.post(
            "/api/upload/confirm-activity",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        assert second.status_code == 200, second.json()

        body = second.json()
        formal = body["formal_write"]
        assert formal["calculation_status"] == "pending_factor"
        assert formal["emission_result"] is None

        source_id = uuid.UUID(formal["emission_source_id"])
        activity_id = uuid.UUID(formal["activity_data_id"])
        assert db.query(EmissionSource).filter(EmissionSource.id == source_id).count() == 1
        source = db.get(EmissionSource, source_id)
        assert source.tenant_id == tenant.id
        assert db.query(ActivityData).filter(ActivityData.emission_source_id == source_id).count() == 1
        assert db.query(EmissionResult).filter(EmissionResult.activity_data_id == activity_id).count() == 0

        durable = client.get(
            f"/api/upload/{document.id}/formal-write",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert durable.status_code == 200, durable.json()
        assert durable.json()["formal_write"]["activity_data_id"] == str(activity_id)
        assert durable.json()["formal_write"]["calculation_status"] == "pending_factor"
        assert durable.json()["formal_write"]["activity_quantity"] == "632600"

        candidates = client.get(
            f"/api/upload/formal-activities/{activity_id}/factor-candidates",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert candidates.status_code == 200, candidates.json()
        factor_candidates = candidates.json()["factor_candidates"]
        assert [candidate["factor_id"] for candidate in factor_candidates] == [str(factor.id)]
        candidate = factor_candidates[0]
        assert candidate["tenant_scope"] == "tenant"
        assert candidate["region_match"] == "exact"
        assert candidate["preview_emissions"] == "403.5988"
        assert candidate["preview_unit"] == "tCO2"

        blank_reason = client.post(
            f"/api/upload/formal-activities/{activity_id}/confirm-factor",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "factor_id": str(factor.id),
                "factor_snapshot_sha256": candidate["factor_snapshot_sha256"],
                "selection_note": "            ",
            },
        )
        assert blank_reason.status_code == 400, blank_reason.json()
        assert "有效字符" in blank_reason.json()["detail"]

        stale = client.post(
            f"/api/upload/formal-activities/{activity_id}/confirm-factor",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "factor_id": str(factor.id),
                "factor_snapshot_sha256": "0" * 64,
                "selection_note": "人工已核对因子年份、区域、来源及适用单位。",
            },
        )
        assert stale.status_code == 409, stale.json()
        assert db.query(EmissionResult).filter(EmissionResult.activity_data_id == activity_id).count() == 0

        factor_confirmation = {
            "factor_id": str(factor.id),
            "factor_snapshot_sha256": candidate["factor_snapshot_sha256"],
            "selection_note": "人工已核对因子年份、区域、来源及适用单位。",
        }
        calculated = client.post(
            f"/api/upload/formal-activities/{activity_id}/confirm-factor",
            headers={"Authorization": f"Bearer {token}"},
            json=factor_confirmation,
        )
        assert calculated.status_code == 200, calculated.json()
        replayed = client.post(
            f"/api/upload/formal-activities/{activity_id}/confirm-factor",
            headers={"Authorization": f"Bearer {token}"},
            json=factor_confirmation,
        )
        assert replayed.status_code == 200, replayed.json()

        calculated_formal = calculated.json()["formal_write"]
        replayed_formal = replayed.json()["formal_write"]
        assert calculated_formal["calculation_status"] == "calculated"
        assert calculated_formal["emission_result"]["co2_tonnes"] == 403.5988
        assert calculated_formal["emission_result"]["co2_tonnes_exact"] == "403.5988"
        assert (
            replayed_formal["emission_result"]["emission_result_id"]
            == calculated_formal["emission_result"]["emission_result_id"]
        )
        result_id = uuid.UUID(calculated_formal["emission_result"]["emission_result_id"])
        assert db.query(EmissionResult).filter(EmissionResult.activity_data_id == activity_id).count() == 1

        activity = db.query(ActivityData).filter(ActivityData.id == activity_id).first()
        assert activity.quantity == 632600.0
        assert activity.unit == "kWh"
        assert "source_file_id=" in activity.notes

        result = db.query(EmissionResult).filter(EmissionResult.id == result_id).first()
        assert result.activity_data_id == activity.id
        assert result.factor_id == factor.id
        assert result.audit_trail["formula"] == (
            "Quantity(activity) × Quantity(factor) → target emission unit"
        )
        assert result.audit_trail["factor_confirmation"]["gate"] == "H-02"
        assert result.audit_trail["factor_confirmation"]["selection_note"] == (
            "人工已核对因子年份、区域、来源及适用单位。"
        )
        assert result.unit == "tCO2"

        # A later factor choice supersedes the first result.  Re-confirming the
        # original factor must create a fresh current version rather than hand
        # the UI the ID of the now-historical first result.
        alternate_factor = EmissionFactor(
            tenant_id=tenant.id,
            name="华东电网备选测试因子",
            code="TEST-GRID-EAST-ALT-2026",
            category="electricity_grid",
            region="华东",
            year=2026,
            value=Decimal("0.5000"),
            unit="kgCO2/kWh",
            source="test-alternate",
            uncertainty=2.0,
            is_default=False,
        )
        db.add(alternate_factor)
        db.commit()
        db.refresh(alternate_factor)

        refreshed_candidates = client.get(
            f"/api/upload/formal-activities/{activity_id}/factor-candidates",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert refreshed_candidates.status_code == 200, refreshed_candidates.json()
        alternate_candidate = next(
            item
            for item in refreshed_candidates.json()["factor_candidates"]
            if item["factor_id"] == str(alternate_factor.id)
        )
        alternate_confirmation = client.post(
            f"/api/upload/formal-activities/{activity_id}/confirm-factor",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "factor_id": str(alternate_factor.id),
                "factor_snapshot_sha256": alternate_candidate["factor_snapshot_sha256"],
                "selection_note": "人工改用备选因子并核对年份、区域、来源及适用单位。",
            },
        )
        assert alternate_confirmation.status_code == 200, alternate_confirmation.json()
        alternate_result_id = uuid.UUID(
            alternate_confirmation.json()["formal_write"]["emission_result"][
                "emission_result_id"
            ]
        )
        assert alternate_result_id != result_id

        original_candidate = next(
            item
            for item in refreshed_candidates.json()["factor_candidates"]
            if item["factor_id"] == str(factor.id)
        )
        restored_confirmation = client.post(
            f"/api/upload/formal-activities/{activity_id}/confirm-factor",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "factor_id": str(factor.id),
                "factor_snapshot_sha256": original_candidate["factor_snapshot_sha256"],
                "selection_note": "人工重新选择原因子并再次核对年份、区域、来源及适用单位。",
            },
        )
        assert restored_confirmation.status_code == 200, restored_confirmation.json()
        restored_result_id = uuid.UUID(
            restored_confirmation.json()["formal_write"]["emission_result"][
                "emission_result_id"
            ]
        )
        assert restored_result_id not in {result_id, alternate_result_id}

        db.expire_all()
        first_result = db.get(EmissionResult, result_id)
        second_result = db.get(EmissionResult, alternate_result_id)
        current_result = db.get(EmissionResult, restored_result_id)
        assert first_result.superseded_by_id == alternate_result_id
        assert second_result.superseded_by_id == restored_result_id
        assert current_result.superseded_by_id is None
        assert current_result.supersedes_id == alternate_result_id
        assert current_result.factor_id == factor.id
        assert current_result.version == 3

        db.expire_all()
        confirmed_document = db.get(DocumentStore, document.id)
        assert confirmed_document.ocr_status == "confirmed"
        assert confirmed_document.ocr_result["fields"] == payload["fields"]
        assert confirmed_document.ocr_result["human_confirmation"]["value_origin"] == "human_confirmed"
    finally:
        db.close()


def test_factor_gate_hides_cross_tenant_private_factor_and_rejects_wrong_year():
    client = TestClient(app)
    db = _session()
    try:
        owner_tenant = _tenant(db, "factor-private-owner")
        owner_enterprise = _enterprise(db, owner_tenant, "9412")
        _user(db, owner_tenant, owner_enterprise, "factor-private-owner@example.com")
        private_factor = EmissionFactor(
            tenant_id=owner_tenant.id,
            name="其他租户私有因子",
            code="PRIVATE-GRID-EAST-2026",
            category="electricity_grid",
            region="华东",
            year=2026,
            value=Decimal("0.6000"),
            unit="kgCO2e/kWh",
            source="private-test",
            is_default=True,
        )

        tenant = _tenant(db, "factor-gate-user")
        enterprise = _enterprise(db, tenant, "9413")
        _user(db, tenant, enterprise, "factor-gate-user@example.com")
        wrong_year_factor = EmissionFactor(
            tenant_id=None,
            name="平台因子但年份不匹配",
            code="GLOBAL-GRID-EAST-2025",
            category="electricity_grid",
            region="华东",
            year=2025,
            value=Decimal("0.5000"),
            unit="kgCO2e/kWh",
            source="platform-test",
            is_default=True,
        )
        document = _document(db, tenant, enterprise, filename="factor-gate.csv")
        db.add_all([private_factor, wrong_year_factor])
        db.commit()
        token = _login(client, "factor-gate-user@example.com")
        fields = {
            "electricity_kwh": "1000",
            "period": "2026-03",
            "facility": "炼钢厂",
        }
        candidate = _prepare_candidate(client, token, document, fields)
        quality = _prepare_quality_review(client, token, document, fields, candidate)
        confirmed = client.post(
            "/api/upload/confirm-activity",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "candidate_token": candidate["candidate_token"],
                "quality_review_token": quality["quality_review_token"],
                "file_id": str(document.id),
                "document_content_hash": document.content_hash,
                "filename": document.filename,
                "document_type": "electricity_bill",
                "fields": fields,
            },
        )
        assert confirmed.status_code == 200, confirmed.json()
        activity_id = confirmed.json()["formal_write"]["activity_data_id"]

        candidates = client.get(
            f"/api/upload/formal-activities/{activity_id}/factor-candidates",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert candidates.status_code == 200, candidates.json()
        assert candidates.json()["factor_candidates"] == []

        cross_tenant = client.post(
            f"/api/upload/formal-activities/{activity_id}/confirm-factor",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "factor_id": str(private_factor.id),
                "factor_snapshot_sha256": "0" * 64,
                "selection_note": "尝试引用其他租户的私有排放因子进行计算。",
            },
        )
        assert cross_tenant.status_code == 400
        assert "不可见" in cross_tenant.json()["detail"]

        wrong_year = client.post(
            f"/api/upload/formal-activities/{activity_id}/confirm-factor",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "factor_id": str(wrong_year_factor.id),
                "factor_snapshot_sha256": "0" * 64,
                "selection_note": "尝试引用适用年份不一致的排放因子进行计算。",
            },
        )
        assert wrong_year.status_code == 400
        assert "适用年份" in wrong_year.json()["detail"]
        assert db.query(EmissionResult).filter(EmissionResult.activity_data_id == uuid.UUID(activity_id)).count() == 0
    finally:
        db.close()
