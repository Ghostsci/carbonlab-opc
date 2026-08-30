"""File upload and OCR processing endpoint — MinIO S3 storage."""

import hashlib
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.ai.ocr import OCRService, DocumentType
from backend.ai.rag import get_rag_service
from backend.auth.dependencies import get_current_user
from backend.config import settings
from backend.database import get_db
from backend.models.ai_os import WorkflowStep
from backend.models.document import DocumentStore
from backend.models.user import User
from backend.services.activity_ingestion import (
    confirm_activity_factor,
    get_document_formal_write,
    list_activity_factor_candidates,
    persist_confirmed_activity,
)
from backend.services.agent_ops import (
    append_agent_run_event,
    complete_agent_run,
    start_agent_run,
)
from backend.services.candidate_confirmation import (
    CandidateSnapshotError,
    issue_candidate_snapshot,
    verify_candidate_snapshot,
)
from backend.services.digital_workforce import (
    QualityReviewError,
    evaluate_document_quality,
    issue_quality_review,
    verify_quality_review,
    workforce_contract_payload,
)
from backend.services.workflow_engine import ensure_demo_cbam_workflow, get_workflow_for_tenant, workflow_to_dict
from backend.services.storage import (
    get_storage,
    generate_object_name,
    detect_content_type,
)

router = APIRouter(prefix="/upload", tags=["upload"])

ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".csv"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

ocr_service = OCRService()


class ConfirmActivityRequest(BaseModel):
    candidate_token: str | None = None
    quality_review_token: str | None = None
    workflow_id: str | None = None
    file_id: str | None = None
    document_content_hash: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    filename: str = Field(min_length=1, max_length=255)
    document_type: str = "unknown"
    fields: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    target_dataset: str = "能源消耗 - 外购电力"
    target_boundary: str = "华盛钢铁 - 炼钢厂（2026）"
    note: str | None = None


class PrepareCandidateRequest(BaseModel):
    fields: dict[str, Any] = Field(min_length=1)


class QualityReviewRequest(BaseModel):
    candidate_token: str = Field(min_length=1)
    fields: dict[str, Any] = Field(min_length=1)


class ConfirmActivityFactorRequest(BaseModel):
    factor_id: uuid.UUID
    factor_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection_note: str = Field(min_length=12, max_length=1000)


def _require_document_context(user: User) -> tuple[uuid.UUID, uuid.UUID]:
    if not user.tenant_id or not user.enterprise_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前用户未绑定租户或企业",
        )
    return user.tenant_id, user.enterprise_id


def _document_response(document: DocumentStore) -> dict[str, Any]:
    snapshot = document.ocr_result or {}
    errors = snapshot.get("errors")
    if errors is None:
        errors = [document.ocr_error] if document.ocr_error else []
    return {
        "file_id": str(document.id),
        "content_hash": document.content_hash,
        "filename": document.filename,
        "mime_type": document.mime_type,
        "size_bytes": document.size_bytes,
        "storage_url": f"/api/upload/{document.id}/download",
        "document_type": document.doc_type,
        "fields": snapshot.get("fields") or {},
        "confidence": snapshot.get("confidence") or 0,
        "raw_text": snapshot.get("raw_text") or "",
        "tables": snapshot.get("tables") or [],
        "errors": errors,
        "ocr_status": document.ocr_status,
        "workforce": snapshot.get("workforce") or {},
        "created_at": document.created_at,
    }


def _record_workforce_stage(
    document: DocumentStore,
    stage_key: str,
    *,
    status_value: str,
    payload: dict[str, Any] | None = None,
) -> None:
    snapshot = dict(document.ocr_result or {})
    workforce = dict(snapshot.get("workforce") or {})
    stages = dict(workforce.get("stages") or {})
    stages[stage_key] = {
        "status": status_value,
        "at": datetime.now(timezone.utc).isoformat(),
        **(payload or {}),
    }
    workforce.update(
        {
            "contract_version": workforce_contract_payload()["contract_version"],
            "current_stage": stage_key,
            "stages": stages,
        }
    )
    snapshot["workforce"] = workforce
    document.ocr_result = snapshot


def _number(value: Any) -> int | str | None:
    if value is None:
        return None
    if isinstance(value, bool | float):
        return None
    if isinstance(value, int):
        return value
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", str(value))
    if not match:
        return None
    token = match.group(0).replace(",", "")
    return token if "." in token else int(token)


def _field(fields: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in fields and fields[name] not in (None, ""):
            return fields[name]
    return None


def _activity_from_fields(req: ConfirmActivityRequest) -> dict[str, Any]:
    if req.document_type != "electricity_bill":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前正式写入闭环仅支持电费活动数据；其他文档请在护照对应步骤登记",
        )
    fields = req.fields or {}
    quantity = _number(_field(fields, "electricity_kwh", "用电量", "activity_quantity", "quantity"))
    amount = _number(_field(fields, "total_amount", "金额", "amount"))
    period_value = _field(fields, "period", "账单月份", "billing_month", "date", "抄表日期")
    supplier = str(_field(fields, "supplier_name", "供应商", "provider") or "")
    facility_value = _field(fields, "facility", "所属工厂", "customer_name")

    if quantity is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少可写入的用电量字段")
    if period_value in (None, ""):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少经人工核验的报告期间")
    if facility_value in (None, ""):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少经人工核验的所属设施")
    period = str(period_value)
    facility = str(facility_value)

    return {
        "record_id": str(uuid.uuid4()),
        "file_id": req.file_id,
        "document_content_hash": req.document_content_hash,
        "filename": req.filename,
        "document_type": req.document_type,
        "activity_type": "purchased_electricity" if req.document_type == "electricity_bill" else "document_activity",
        "quantity": quantity,
        "unit": "kWh" if req.document_type == "electricity_bill" else str(_field(fields, "unit", "单位") or "unknown"),
        "amount": amount,
        "amount_unit": "CNY" if amount is not None else None,
        "period": period,
        "supplier": supplier,
        "facility": facility,
        "confidence": req.confidence,
        "target_dataset": req.target_dataset,
        "target_boundary": req.target_boundary,
        "source": "data_inbox_ocr_confirmed",
        "value_origin": "human_confirmed",
    }


def _find_step(workflow, step_key: str) -> WorkflowStep | None:
    return next((step for step in workflow.steps or [] if step.step_key == step_key), None)


@router.get("/workforce/roles")
def get_workforce_roles(user: User = Depends(get_current_user)):
    """Return the governed role contracts used by the current product workflow."""
    _require_document_context(user)
    return workforce_contract_payload()


@router.post("")
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {ext}。支持: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件大小超过限制 ({MAX_FILE_SIZE // 1024 // 1024}MB)",
        )

    if not user.tenant_id or not user.enterprise_id:
        raise HTTPException(status_code=400, detail="当前用户未绑定租户或企业")
    document_content_hash = hashlib.sha256(content).hexdigest()
    existing = (
        db.query(DocumentStore)
        .filter(
            DocumentStore.tenant_id == user.tenant_id,
            DocumentStore.enterprise_id == user.enterprise_id,
            DocumentStore.content_hash == document_content_hash,
        )
        .first()
    )
    if existing is not None:
        intake_run = start_agent_run(
            db,
            tenant_id=user.tenant_id,
            enterprise_id=user.enterprise_id,
            agent_id="A-01",
            trigger="file_upload",
            trigger_ref=existing.filename,
            source_file_id=existing.id,
            input_snapshot={
                "filename": existing.filename,
                "content_hash": document_content_hash,
                "size_bytes": len(content),
            },
            summary="发现同企业同内容文件，复用既有受控文档",
        )
        append_agent_run_event(
            db,
            run=intake_run,
            event_type="duplicate_reused",
            status="success",
            title="复用既有文件",
            summary="内容哈希已存在，没有创建重复文档",
            payload={"content_hash": document_content_hash, "reused": True},
            evidence_refs=[str(existing.id)],
        )
        complete_agent_run(
            db,
            run=intake_run,
            summary="A-01 已完成文件去重并复用既有文档",
            output_snapshot={
                "file_id": str(existing.id),
                "document_type": existing.doc_type,
                "reused": True,
                "next_role_id": "A-02",
            },
            evidence_refs=[str(existing.id)],
        )
        _record_workforce_stage(
            existing,
            "document_intake",
            status_value="completed",
            payload={
                "role_id": "A-01",
                "run_id": intake_run.run_id,
                "content_hash": document_content_hash,
                "reused": True,
            },
        )
        get_rag_service().index_document(db, existing)
        db.commit()
        return {
            **_document_response(existing),
            "object_name": existing.storage_path,
            "reused": True,
        }

    file_id = str(uuid.uuid4())
    object_name = generate_object_name(file.filename, file_id)
    content_type = detect_content_type(file.filename)

    # Upload to storage (MinIO or local)
    storage = get_storage()
    storage.upload(object_name, content, content_type)

    # OCR processing — write to temp file for OCR engine
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        result = ocr_service.process(tmp_path)
        tmp_path.unlink(missing_ok=True)
        snapshot = {
            "fields": result.fields,
            "confidence": result.confidence,
            "raw_text": result.raw_text[: settings.rag_max_source_chars],
            "tables": result.tables,
            "errors": result.errors,
            "workforce": {
                "contract_version": workforce_contract_payload()["contract_version"],
                "current_stage": "evidence_extraction",
                "stages": {
                    "document_intake": {
                        "status": "completed",
                        "at": datetime.now(timezone.utc).isoformat(),
                        "role_id": "A-01",
                        "content_hash": document_content_hash,
                        "reused": False,
                    },
                    "evidence_extraction": {
                        "status": "completed" if not result.errors else "attention",
                        "at": datetime.now(timezone.utc).isoformat(),
                        "role_id": "A-02",
                        "field_count": len(result.fields),
                        "coverage": result.confidence,
                    },
                },
            },
        }
        document = DocumentStore(
            id=uuid.UUID(file_id),
            tenant_id=user.tenant_id,
            enterprise_id=user.enterprise_id,
            filename=file.filename,
            mime_type=content_type,
            size_bytes=len(content),
            storage_path=object_name,
            content_hash=document_content_hash,
            doc_type=result.document_type.value,
            ocr_status="completed",
            ocr_result=snapshot,
        )
        db.add(document)
        db.flush()
        intake_run = start_agent_run(
            db,
            tenant_id=user.tenant_id,
            enterprise_id=user.enterprise_id,
            agent_id="A-01",
            trigger="file_upload",
            trigger_ref=file.filename,
            source_file_id=document.id,
            input_snapshot={
                "file_id": file_id,
                "filename": file.filename,
                "mime_type": content_type,
                "size_bytes": len(content),
                "content_hash": document_content_hash,
            },
        )
        append_agent_run_event(
            db,
            run=intake_run,
            event_type="file_registered",
            status="success",
            title="文件身份登记完成",
            summary="已登记租户、企业、文件 ID 与服务器内容哈希",
            payload={
                "document_type": result.document_type.value,
                "reused": False,
                "content_hash": document_content_hash,
            },
            evidence_refs=[file_id],
        )
        complete_agent_run(
            db,
            run=intake_run,
            summary="A-01 已完成文件登记与基础完整性检查",
            output_snapshot={
                "file_id": file_id,
                "content_hash": document_content_hash,
                "document_type": result.document_type.value,
                "status": "completed",
                "reused": False,
                "next_role_id": "A-02",
            },
            evidence_refs=[file_id],
        )
        extraction_run = start_agent_run(
            db,
            tenant_id=user.tenant_id,
            enterprise_id=user.enterprise_id,
            agent_id="A-02",
            trigger="file_upload",
            trigger_ref=file.filename,
            source_file_id=document.id,
            parent_run_id=intake_run.run_id,
            input_snapshot={
                "file_id": file_id,
                "content_hash": document_content_hash,
                "document_type": result.document_type.value,
                "raw_text_available": bool(result.raw_text),
                "table_count": len(result.tables),
            },
        )
        append_agent_run_event(
            db,
            run=extraction_run,
            event_type="candidate_fields_extracted",
            status="warning" if result.errors else "success",
            title="候选字段提取完成",
            summary=f"提出 {len(result.fields)} 个字段候选，覆盖度 {result.confidence:.0%}",
            payload={
                "field_keys": sorted(str(key) for key in result.fields),
                "field_count": len(result.fields),
                "coverage": result.confidence,
                "warning_count": len(result.errors),
            },
            evidence_refs=[file_id],
        )
        complete_agent_run(
            db,
            run=extraction_run,
            summary="A-02 已提出字段候选并交给 A-03 独立质检",
            output_snapshot={
                "field_count": len(result.fields),
                "field_keys": sorted(str(key) for key in result.fields),
                "coverage": result.confidence,
                "warnings": list(result.errors),
                "next_role_id": "A-03",
            },
            final_action={"handoff_to": "A-03"},
            evidence_refs=[file_id],
        )
        workforce = dict(snapshot["workforce"])
        workforce_stages = dict(workforce["stages"])
        workforce_stages["document_intake"] = {
            **workforce_stages["document_intake"],
            "run_id": intake_run.run_id,
        }
        workforce_stages["evidence_extraction"] = {
            **workforce_stages["evidence_extraction"],
            "run_id": extraction_run.run_id,
        }
        workforce["stages"] = workforce_stages
        snapshot["workforce"] = workforce
        document.ocr_result = snapshot
        get_rag_service().index_document(db, document)
        db.commit()

        return {
            "file_id": file_id,
            "content_hash": document_content_hash,
            "filename": file.filename,
            "mime_type": content_type,
            "size_bytes": len(content),
            "object_name": object_name,
            "storage_url": f"/api/upload/{file_id}/download",
            "document_type": result.document_type.value,
            **snapshot,
            "ocr_status": "completed",
            "reused": False,
        }
    except Exception as e:
        raise HTTPException(status_code=422, detail='文档处理失败，请检查文件格式') from e


@router.get("")
def list_uploaded_files(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List documents owned by the authenticated tenant and enterprise."""
    tenant_id, enterprise_id = _require_document_context(user)
    documents = (
        db.query(DocumentStore)
        .filter(
            DocumentStore.tenant_id == tenant_id,
            DocumentStore.enterprise_id == enterprise_id,
        )
        .order_by(DocumentStore.created_at.desc(), DocumentStore.id.desc())
        .all()
    )
    return [_document_response(document) for document in documents]


@router.get("/{file_id}/download")
def download_file(
    file_id: uuid.UUID,
    download: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the owned document through the authenticated application boundary."""
    tenant_id, enterprise_id = _require_document_context(user)
    document = (
        db.query(DocumentStore)
        .filter(
            DocumentStore.id == file_id,
            DocumentStore.tenant_id == tenant_id,
            DocumentStore.enterprise_id == enterprise_id,
        )
        .first()
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在",
        )
    content = get_storage().download(document.storage_path)
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件内容不存在",
        )
    content_type = document.mime_type or detect_content_type(document.filename)
    encoded_filename = quote(document.filename, safe="")
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                f"{'attachment' if download else 'inline'}; "
                f"filename*=UTF-8''{encoded_filename}"
            ),
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/{file_id}/candidate")
def prepare_document_candidate(
    file_id: uuid.UUID,
    req: PrepareCandidateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Sign the exact candidate fields that the authenticated user will confirm."""
    tenant_id, enterprise_id = _require_document_context(user)
    document = (
        db.query(DocumentStore)
        .filter(
            DocumentStore.id == file_id,
            DocumentStore.tenant_id == tenant_id,
            DocumentStore.enterprise_id == enterprise_id,
        )
        .first()
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在或无权访问")
    try:
        signed = issue_candidate_snapshot(
            actor_user_id=str(user.id),
            tenant_id=str(tenant_id),
            enterprise_id=str(enterprise_id),
            file_id=str(document.id),
            document_content_hash=document.content_hash,
            document_type=document.doc_type,
            fields=req.fields,
        )
    except CandidateSnapshotError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    extraction_run = start_agent_run(
        db,
        tenant_id=tenant_id,
        enterprise_id=enterprise_id,
        agent_id="A-02",
        trigger="candidate_prepare",
        trigger_ref=str(document.id),
        source_file_id=document.id,
        input_snapshot={
            "file_id": str(document.id),
            "content_hash": document.content_hash,
            "document_type": document.doc_type,
            "field_keys": sorted(str(key) for key in req.fields),
        },
        summary="将当前可编辑字段冻结为服务端签名候选",
    )
    append_agent_run_event(
        db,
        run=extraction_run,
        event_type="candidate_snapshot_signed",
        status="success",
        title="候选快照已冻结",
        summary=f"冻结 {len(req.fields)} 个候选字段，等待 A-03 质检",
        payload={
            "candidate_id": signed["candidate_id"],
            "fields_sha256": signed["fields_sha256"],
            "field_keys": sorted(str(key) for key in req.fields),
        },
        evidence_refs=[str(document.id)],
    )
    complete_agent_run(
        db,
        run=extraction_run,
        summary="A-02 已冻结候选快照并交给 A-03",
        output_snapshot={
            "candidate_id": signed["candidate_id"],
            "fields_sha256": signed["fields_sha256"],
            "field_count": len(req.fields),
            "next_role_id": "A-03",
        },
        final_action={"handoff_to": "A-03"},
        evidence_refs=[str(document.id)],
    )
    _record_workforce_stage(
        document,
        "evidence_extraction",
        status_value="completed",
        payload={
            "role_id": "A-02",
            "run_id": extraction_run.run_id,
            "candidate_id": signed["candidate_id"],
            "fields_sha256": signed["fields_sha256"],
            "field_count": len(req.fields),
        },
    )
    document.ocr_status = "candidate_ready"
    db.commit()
    return {
        **signed,
        "state": "candidate",
        "confirmation_required": True,
        "formal_write_allowed": False,
        "source": {
            "file_id": str(document.id),
            "filename": document.filename,
            "content_hash": document.content_hash,
            "document_type": document.doc_type,
        },
        "fields": req.fields,
    }


@router.post("/{file_id}/quality-review")
def review_document_candidate(
    file_id: uuid.UUID,
    req: QualityReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Run A-03 checks and issue a candidate-bound quality capability."""
    tenant_id, enterprise_id = _require_document_context(user)
    document = (
        db.query(DocumentStore)
        .filter(
            DocumentStore.id == file_id,
            DocumentStore.tenant_id == tenant_id,
            DocumentStore.enterprise_id == enterprise_id,
        )
        .first()
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在或无权访问")
    try:
        candidate = verify_candidate_snapshot(
            req.candidate_token,
            actor_user_id=str(user.id),
            tenant_id=str(tenant_id),
            enterprise_id=str(enterprise_id),
            file_id=str(document.id),
            document_content_hash=document.content_hash,
            document_type=document.doc_type,
            fields=req.fields,
        )
    except CandidateSnapshotError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    quality_run = start_agent_run(
        db,
        tenant_id=tenant_id,
        enterprise_id=enterprise_id,
        agent_id="A-03",
        trigger="quality_review",
        trigger_ref=candidate["candidate_id"],
        source_file_id=document.id,
        input_snapshot={
            "file_id": str(document.id),
            "content_hash": document.content_hash,
            "candidate_id": candidate["candidate_id"],
            "fields_sha256": candidate["fields_sha256"],
            "field_keys": sorted(str(key) for key in req.fields),
        },
    )
    append_agent_run_event(
        db,
        run=quality_run,
        event_type="candidate_binding_verified",
        status="success",
        title="候选身份校验通过",
        summary="候选、文件、租户、企业和字段哈希绑定一致",
        payload={
            "candidate_id": candidate["candidate_id"],
            "fields_sha256": candidate["fields_sha256"],
        },
        evidence_refs=[str(document.id)],
    )

    rag = get_rag_service()
    rag.index_document(db, document)
    retrieval_evidence: dict[str, dict[str, Any]] = {}
    retrieval_run_ids: list[str] = []
    field_queries = {
        "electricity_kwh": ("electricity_kwh", "用电量", "activity_quantity", "quantity"),
        "period": ("period", "账单月份", "billing_month", "date", "抄表日期"),
        "facility": ("facility", "所属工厂", "customer_name"),
    }
    for canonical_key, aliases in field_queries.items():
        value = _field(req.fields, *aliases)
        if value in (None, ""):
            continue
        retrieval = rag.search(
            db,
            tenant_id=tenant_id,
            enterprise_id=enterprise_id,
            actor_id=user.id,
            role_id="A-03",
            purpose="field_evidence_review",
            query_text=f"字段 {canonical_key} 候选值 {value} 源文件 {document.filename}",
            corpus_types={"tenant_evidence"},
            top_k=3,
            source_ref=str(document.id),
            field_key=canonical_key,
        )
        retrieval_evidence[canonical_key] = retrieval.model_dump()
        retrieval_run_ids.append(retrieval.retrieval_run_id)

    append_agent_run_event(
        db,
        run=quality_run,
        event_type="evidence_retrieved",
        status="success",
        title="字段级证据检索完成",
        summary=f"完成 {len(retrieval_run_ids)} 次受租户约束的证据检索",
        payload={
            "retrieval_run_ids": retrieval_run_ids,
            "reviewed_fields": sorted(retrieval_evidence),
        },
        evidence_refs=[str(document.id), *retrieval_run_ids],
    )

    result = evaluate_document_quality(
        document_type=document.doc_type,
        document_content_hash=document.content_hash,
        fields=req.fields,
        source_snapshot=document.ocr_result or {},
        retrieval_evidence=retrieval_evidence,
    )
    signed = issue_quality_review(
        actor_user_id=str(user.id),
        tenant_id=str(tenant_id),
        enterprise_id=str(enterprise_id),
        file_id=str(document.id),
        document_content_hash=document.content_hash,
        candidate=candidate,
        result=result,
    )
    append_agent_run_event(
        db,
        run=quality_run,
        event_type="quality_gate_evaluated",
        status="blocked" if result["quality_status"] == "fail" else (
            "warning" if result["quality_status"] == "pass_with_warnings" else "success"
        ),
        title="独立质检完成",
        summary=(
            f"状态 {result['quality_status']}，得分 {result['score']}；"
            f"通过 {result['counts']['passed']}、提示 {result['counts']['warnings']}、"
            f"阻断 {result['counts']['failed']}"
        ),
        payload={
            "quality_review_id": signed["quality_review_id"],
            "quality_status": result["quality_status"],
            "score": result["score"],
            "counts": result["counts"],
            "findings": result["findings"],
            "quality_result_sha256": signed["quality_result_sha256"],
        },
        evidence_refs=[str(document.id), *retrieval_run_ids],
    )
    complete_agent_run(
        db,
        run=quality_run,
        summary=(
            "A-03 已完成质检；等待 H-01 承担企业事实确认责任"
            if result["quality_status"] != "fail"
            else "A-03 已完成质检并阻断正式写入；等待人工处理异常"
        ),
        output_snapshot={
            "quality_review_id": signed["quality_review_id"],
            "quality_status": result["quality_status"],
            "score": result["score"],
            "counts": result["counts"],
            "next_gate": "H-01",
        },
        final_action={
            "handoff_to": "H-01",
            "formal_write_blocked": result["quality_status"] == "fail",
        },
        evidence_refs=[str(document.id), *retrieval_run_ids],
    )
    _record_workforce_stage(
        document,
        "evidence_quality_review",
        status_value="blocked" if result["quality_status"] == "fail" else "completed",
        payload={
            "role_id": "A-03",
            "run_id": quality_run.run_id,
            "quality_review_id": signed["quality_review_id"],
            "quality_status": result["quality_status"],
            "score": result["score"],
            "quality_result_sha256": signed["quality_result_sha256"],
            "counts": result["counts"],
        },
    )
    document.ocr_status = "quality_failed" if result["quality_status"] == "fail" else "quality_reviewed"
    db.commit()
    return {
        **signed,
        **result,
        "candidate_id": candidate["candidate_id"],
        "candidate_fields_sha256": candidate["fields_sha256"],
        "state": "quality_reviewed",
        "agent": {"role_id": "A-03", "display_name": "碳数据质检员"},
        "formal_write_allowed": False,
        "next_gate": "H-01 企业数据确认人",
    }


@router.post("/confirm-activity")
def confirm_activity_data(
    req: ConfirmActivityRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Confirm OCR fields and persist them as an auditable workflow checkpoint.

    This deliberately writes to the AI-native Workflow State first instead of
    creating an incomplete emission source row. The persisted checkpoint is the
    handoff record for the later factor-mapping/calculation step.
    """
    tenant_id, enterprise_id = _require_document_context(user)
    if not req.file_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="正式活动数据必须关联已上传的源文件",
        )
    try:
        document_id = uuid.UUID(req.file_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="源文件 file_id 格式无效",
        ) from exc
    document = (
        db.query(DocumentStore)
        .filter(
            DocumentStore.id == document_id,
            DocumentStore.tenant_id == tenant_id,
            DocumentStore.enterprise_id == enterprise_id,
        )
        .first()
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="源文件不存在或无权访问",
        )
    if not req.document_content_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="确认正式活动数据时必须提交源文件 content_hash",
        )
    if req.document_content_hash != document.content_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="源文件 content_hash 与服务器记录不一致",
        )

    activity_record = _activity_from_fields(req)
    if not req.candidate_token:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先生成并核对服务端签名的候选快照",
        )
    try:
        confirmation = verify_candidate_snapshot(
            req.candidate_token,
            actor_user_id=str(user.id),
            tenant_id=str(tenant_id),
            enterprise_id=str(enterprise_id),
            file_id=str(document.id),
            document_content_hash=document.content_hash,
            document_type=req.document_type,
            fields=req.fields,
        )
    except CandidateSnapshotError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not req.quality_review_token:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先由 A-03 碳数据质检员完成独立证据质检",
        )
    try:
        quality_review = verify_quality_review(
            req.quality_review_token,
            actor_user_id=str(user.id),
            tenant_id=str(tenant_id),
            enterprise_id=str(enterprise_id),
            file_id=str(document.id),
            document_content_hash=document.content_hash,
            candidate=confirmation,
        )
    except QualityReviewError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    activity_record.update(
        {
            "candidate_id": confirmation["candidate_id"],
            "candidate_fields_sha256": confirmation["fields_sha256"],
            "candidate_subject_sha256": confirmation["subject_sha256"],
            "quality_review_id": quality_review["quality_review_id"],
            "quality_result_sha256": quality_review["quality_result_sha256"],
        }
    )
    # Evidence identity is server-authoritative.  The client may edit extracted
    # fields, but cannot substitute a filename or hash for the owned document.
    activity_record.update(
        {
            "file_id": str(document.id),
            "document_content_hash": document.content_hash,
            "filename": document.filename,
        }
    )
    # Invalid or tampered candidates must not create workflow state as a side
    # effect. Resolve the destination only after all confirmation bindings pass.
    workflow = (
        get_workflow_for_tenant(
            db,
            req.workflow_id,
            tenant_id,
            enterprise_id,
        )
        if req.workflow_id
        else ensure_demo_cbam_workflow(
            db,
            tenant_id=tenant_id,
            enterprise_id=user.enterprise_id,
            owner_user_id=user.id,
        )
    )
    step = _find_step(workflow, "energy_data") or _find_step(
        workflow,
        workflow.current_step_key or "",
    )
    if step is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到可写入的数据收集步骤")
    confirmation_run = start_agent_run(
        db,
        tenant_id=tenant_id,
        enterprise_id=enterprise_id,
        agent_id="H-01",
        trigger="human_confirm",
        trigger_ref=confirmation["candidate_id"],
        source_file_id=document.id,
        workflow_id=workflow.id,
        workflow_step_id=step.id,
        input_snapshot={
            "file_id": str(document.id),
            "candidate_id": confirmation["candidate_id"],
            "fields_sha256": confirmation["fields_sha256"],
            "quality_review_id": quality_review["quality_review_id"],
            "quality_result_sha256": quality_review["quality_result_sha256"],
        },
        summary="H-01 对照原始证据承担企业事实确认责任",
    )
    try:
        formal_write = persist_confirmed_activity(db, user=user, activity_record=activity_record)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    append_agent_run_event(
        db,
        run=confirmation_run,
        event_type="human_fact_confirmed",
        status="success",
        title="企业事实已确认",
        summary="经 A-03 门禁后，H-01 确认候选并写入正式活动账本",
        payload={
            "actor_user_id": str(user.id),
            "candidate_id": confirmation["candidate_id"],
            "quality_review_id": quality_review["quality_review_id"],
            "activity_data_id": formal_write["activity_data_id"],
        },
        evidence_refs=[str(document.id), formal_write["activity_data_id"]],
    )
    complete_agent_run(
        db,
        run=confirmation_run,
        summary="H-01 已确认企业事实并交给 H-02 选择适用因子",
        output_snapshot={
            "activity_data_id": formal_write["activity_data_id"],
            "calculation_status": formal_write["calculation_status"],
            "next_gate": "H-02",
        },
        final_action={"handoff_to": "H-02"},
        evidence_refs=[str(document.id), formal_write["activity_data_id"]],
    )

    confirmed_at = datetime.now(timezone.utc)
    snapshot = dict(document.ocr_result or {})
    snapshot.update(
        {
            "fields": req.fields,
            "confidence": req.confidence if req.confidence is not None else snapshot.get("confidence", 0),
            "human_confirmation": {
                "at": confirmed_at.isoformat(),
                "actor_user_id": str(user.id),
                "value_origin": "human_confirmed",
                **confirmation,
                "quality_review": quality_review,
            },
        }
    )
    document.ocr_result = snapshot
    _record_workforce_stage(
        document,
        "enterprise_confirmation",
        status_value="completed",
        payload={
            "role_id": "H-01",
            "run_id": confirmation_run.run_id,
            "actor_user_id": str(user.id),
            "candidate_id": confirmation["candidate_id"],
            "quality_review_id": quality_review["quality_review_id"],
        },
    )
    document.ocr_status = "confirmed"
    document.ocr_error = None

    checkpoint = {
        "at": confirmed_at.isoformat(),
        "type": "data_inbox_activity_write",
        "status": "confirmed",
        "actor_user_id": str(user.id),
        "activity_record": activity_record,
        "formal_write": formal_write,
        "field_count": len(req.fields),
        "note": req.note or "OCR 字段已人工确认并写入工作流活动数据检查点。",
        "quality_review": quality_review,
    }
    step.checkpoints_json = [*(step.checkpoints_json or []), checkpoint]
    outputs = dict(step.outputs_json or {})
    outputs["last_activity_data"] = activity_record
    outputs["last_formal_activity_write"] = formal_write
    outputs["field_completeness"] = max(float(outputs.get("field_completeness") or 0), 0.98 if req.document_type == "electricity_bill" else 0.85)
    step.outputs_json = outputs
    step.status = "completed" if step.step_key == "energy_data" else step.status
    step.updated_at = datetime.now(timezone.utc)
    workflow.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(workflow)
    return {
        "status": "written",
        "message": "已确认字段并写入当前工作流活动数据检查点。",
        "workflow_id": str(workflow.id),
        "step_key": step.step_key,
        "activity_record": activity_record,
        "formal_write": formal_write,
        "checkpoint": checkpoint,
        "workflow": workflow_to_dict(workflow, include_steps=True),
        "confirmation": confirmation,
        "quality_review": quality_review,
    }


@router.get("/{file_id}/formal-write")
def get_formal_activity_write(
    file_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the durable H-01/H-02 state for one owned source document."""
    try:
        formal_write = get_document_formal_write(
            db,
            user=user,
            document_id=file_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return {"formal_write": formal_write}


@router.get("/formal-activities/{activity_id}/factor-candidates")
def get_activity_factor_candidates(
    activity_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List exact-period, region-compatible factors for H-02 confirmation."""
    try:
        return list_activity_factor_candidates(
            db,
            user=user,
            activity_id=activity_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/formal-activities/{activity_id}/confirm-factor")
def confirm_formal_activity_factor(
    activity_id: uuid.UUID,
    req: ConfirmActivityFactorRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Apply the H-02 gate and run R-01 without any LLM arithmetic."""
    try:
        formal_write = confirm_activity_factor(
            db,
            user=user,
            activity_id=activity_id,
            factor_id=req.factor_id,
            factor_snapshot_sha256=req.factor_snapshot_sha256,
            selection_note=req.selection_note,
        )
        document_id = formal_write.get("document_id")
        document = db.get(DocumentStore, uuid.UUID(document_id)) if document_id else None
        result = formal_write.get("emission_result") or {}
        h02_run = start_agent_run(
            db,
            tenant_id=user.tenant_id,
            enterprise_id=user.enterprise_id,
            agent_id="H-02",
            trigger="factor_confirm",
            trigger_ref=str(activity_id),
            source_file_id=document_id,
            input_snapshot={
                "activity_data_id": str(activity_id),
                "factor_id": str(req.factor_id),
                "factor_snapshot_sha256": req.factor_snapshot_sha256,
                "selection_note": req.selection_note,
            },
            summary="H-02 确认适用因子与选择理由",
        )
        append_agent_run_event(
            db,
            run=h02_run,
            event_type="factor_confirmed",
            status="success",
            title="活动排放因子已确认",
            summary="因子快照与人工选择理由已写入审计链",
            payload={
                "actor_user_id": str(user.id),
                "factor_id": str(req.factor_id),
                "factor_snapshot_sha256": req.factor_snapshot_sha256,
                "selection_note": req.selection_note,
            },
            evidence_refs=[str(activity_id), str(req.factor_id)],
        )
        complete_agent_run(
            db,
            run=h02_run,
            summary="H-02 已放行获批因子，交给 R-01 确定性计算",
            output_snapshot={
                "activity_data_id": str(activity_id),
                "factor_id": str(req.factor_id),
                "next_engine": "R-01",
            },
            final_action={"handoff_to": "R-01"},
            evidence_refs=[str(activity_id), str(req.factor_id)],
        )
        calculation_run = start_agent_run(
            db,
            tenant_id=user.tenant_id,
            enterprise_id=user.enterprise_id,
            agent_id="R-01",
            trigger="factor_confirm",
            trigger_ref=str(activity_id),
            source_file_id=document_id,
            parent_run_id=h02_run.run_id,
            input_snapshot={
                "activity_data_id": str(activity_id),
                "factor_id": str(req.factor_id),
                "calculation_engine": "Decimal + Quantity",
            },
            summary="R-01 使用获批输入执行确定性计算",
        )
        append_agent_run_event(
            db,
            run=calculation_run,
            event_type="deterministic_calculation_completed",
            status="success",
            title="确定性计算完成",
            summary="Decimal + Quantity 已生成可复算排放结果，大模型未参与算术",
            payload={
                "emission_result_id": result.get("emission_result_id"),
                "co2_tonnes_exact": result.get("co2_tonnes_exact"),
                "unit": result.get("unit"),
                "factor_id": result.get("factor_id"),
            },
            evidence_refs=[
                str(activity_id),
                str(req.factor_id),
                result.get("emission_result_id"),
            ],
        )
        complete_agent_run(
            db,
            run=calculation_run,
            summary="R-01 已生成正式排放结果，可进入护照归集",
            output_snapshot={
                "emission_result_id": result.get("emission_result_id"),
                "co2_tonnes_exact": result.get("co2_tonnes_exact"),
                "unit": result.get("unit"),
                "next_role_id": "A-04",
            },
            final_action={"handoff_to": "A-04"},
            evidence_refs=[result.get("emission_result_id")],
        )
        if document is not None:
            _record_workforce_stage(
                document,
                "activity_factor_confirmation",
                status_value="completed",
                payload={
                    "role_id": "H-02",
                    "run_id": h02_run.run_id,
                    "actor_user_id": str(user.id),
                    "factor_id": str(req.factor_id),
                    "factor_snapshot_sha256": req.factor_snapshot_sha256,
                    "selection_note": req.selection_note,
                },
            )
            _record_workforce_stage(
                document,
                "activity_emission_calculation",
                status_value="completed",
                payload={
                    "role_id": "R-01",
                    "run_id": calculation_run.run_id,
                    "emission_result_id": result.get("emission_result_id"),
                    "unit": result.get("unit"),
                },
            )
        db.commit()
        return {
            "status": "calculated",
            "message": "H-02 已确认活动排放因子，R-01 已生成正式排放结果。",
            "formal_write": formal_write,
        }
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        code = status.HTTP_409_CONFLICT if "已变化" in str(exc) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(exc)) from exc
