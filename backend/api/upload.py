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
from backend.auth.dependencies import get_current_user
from backend.database import get_db
from backend.models.ai_os import WorkflowStep
from backend.models.document import DocumentStore
from backend.models.user import User
from backend.services.activity_ingestion import persist_confirmed_activity
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
        "created_at": document.created_at,
    }


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
        snapshot = existing.ocr_result or {}
        return {
            "file_id": str(existing.id),
            "content_hash": existing.content_hash,
            "filename": existing.filename,
            "object_name": existing.storage_path,
            "storage_url": f"/api/upload/{existing.id}/download",
            "document_type": existing.doc_type,
            "fields": snapshot.get("fields", {}),
            "confidence": snapshot.get("confidence", 0),
            "raw_text": snapshot.get("raw_text", ""),
            "tables": snapshot.get("tables", []),
            "errors": snapshot.get("errors", []),
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
            "raw_text": result.raw_text[:1000],
            "tables": result.tables,
            "errors": result.errors,
        }
        db.add(
            DocumentStore(
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
        )
        db.commit()

        return {
            "file_id": file_id,
            "content_hash": document_content_hash,
            "filename": file.filename,
            "object_name": object_name,
            "storage_url": f"/api/upload/{file_id}/download",
            "document_type": result.document_type.value,
            **snapshot,
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

    workflow = (
        get_workflow_for_tenant(
            db,
            req.workflow_id,
            tenant_id,
            enterprise_id,
        )
        if req.workflow_id
        else ensure_demo_cbam_workflow(db, tenant_id=tenant_id, enterprise_id=user.enterprise_id, owner_user_id=user.id)
    )
    step = _find_step(workflow, "energy_data") or _find_step(workflow, workflow.current_step_key or "")
    if step is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到可写入的数据收集步骤")

    activity_record = _activity_from_fields(req)
    # Evidence identity is server-authoritative.  The client may edit extracted
    # fields, but cannot substitute a filename or hash for the owned document.
    activity_record.update(
        {
            "file_id": str(document.id),
            "document_content_hash": document.content_hash,
            "filename": document.filename,
        }
    )
    try:
        formal_write = persist_confirmed_activity(db, user=user, activity_record=activity_record)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

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
            },
        }
    )
    document.ocr_result = snapshot
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
    }
