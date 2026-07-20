"""Workflow state service for AI-native carbon compliance flows."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from backend.models.ai_os import WorkflowInstance, WorkflowStep


CBAM_HRC_WORKFLOW_KEY = "cbam-2026q1-hrc-001"

CBAM_HRC_DEMO_STEPS: list[dict[str, Any]] = [
    {
        "step_key": "product_info",
        "title": "产品信息",
        "status": "completed",
        "sort_order": 1,
        "agent_profile_key": "cbam-agent-v1",
        "risk_level": "low",
        "outputs_json": {"product": "热轧卷板", "hs_code": "7208.51"},
    },
    {
        "step_key": "enterprise_data",
        "title": "企业数据",
        "status": "completed",
        "sort_order": 2,
        "agent_profile_key": "cbam-agent-v1",
        "risk_level": "low",
        "outputs_json": {"enterprise": "华盛钢铁有限公司", "facility": "炼钢厂"},
    },
    {
        "step_key": "energy_data",
        "title": "能源数据",
        "status": "completed",
        "sort_order": 3,
        "agent_profile_key": "factor-agent-v1",
        "risk_level": "medium",
        "outputs_json": {"field_completeness": 0.98, "missing_fields": []},
    },
    {
        "step_key": "supplier_data",
        "title": "供应商数据",
        "status": "in_progress",
        "sort_order": 4,
        "agent_profile_key": "supplier-agent-v1",
        "risk_level": "high",
        "outputs_json": {
            "submitted": 16,
            "total": 21,
            "blocked_by": ["供应商 A 未提交原材料数据", "3 家供应商关键字段缺失"],
        },
    },
    {
        "step_key": "factor_confirmation",
        "title": "因子确认",
        "status": "pending",
        "sort_order": 5,
        "agent_profile_key": "factor-agent-v1",
        "risk_level": "medium",
    },
    {
        "step_key": "calculation",
        "title": "计算结果",
        "status": "pending",
        "sort_order": 6,
        "agent_profile_key": "factor-agent-v1",
        "risk_level": "medium",
    },
    {
        "step_key": "report_generation",
        "title": "报告生成",
        "status": "pending",
        "sort_order": 7,
        "agent_profile_key": "cbam-agent-v1",
        "risk_level": "medium",
    },
    {
        "step_key": "approval_submission",
        "title": "审批与提交",
        "status": "pending",
        "sort_order": 8,
        "agent_profile_key": "cbam-agent-v1",
        "risk_level": "high",
    },
]


def _uuid(value: uuid.UUID | str | None) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _progress_from_steps(steps: list[WorkflowStep]) -> int:
    if not steps:
        return 0
    completed = sum(1 for step in steps if step.status in {"completed", "skipped"})
    in_progress_bonus = 0.5 if any(step.status == "in_progress" for step in steps) else 0
    return min(100, int(((completed + in_progress_bonus) / len(steps)) * 100))


def ensure_demo_cbam_workflow(
    db: Session,
    tenant_id: uuid.UUID | str,
    enterprise_id: uuid.UUID | str | None = None,
    owner_user_id: uuid.UUID | str | None = None,
) -> WorkflowInstance:
    """Ensure one HRC CBAM demo workflow exists for the current enterprise."""
    tenant_uuid = _uuid(tenant_id)
    enterprise_uuid = _uuid(enterprise_id)
    if tenant_uuid is None:
        raise ValueError("tenant_id is required for workflow state")
    if enterprise_uuid is None:
        raise ValueError("enterprise_id is required for workflow state")

    workflow = (
        db.query(WorkflowInstance)
        .options(selectinload(WorkflowInstance.steps))
        .filter(
            WorkflowInstance.tenant_id == tenant_uuid,
            WorkflowInstance.enterprise_id == enterprise_uuid,
            WorkflowInstance.workflow_key == CBAM_HRC_WORKFLOW_KEY,
        )
        .first()
    )
    if workflow is not None:
        return workflow

    now = datetime.now(timezone.utc)
    workflow = WorkflowInstance(
        tenant_id=tenant_uuid,
        enterprise_id=enterprise_uuid,
        owner_user_id=_uuid(owner_user_id),
        workflow_key=CBAM_HRC_WORKFLOW_KEY,
        workflow_type="cbam_report",
        title="2026 Q1 热轧卷板 CBAM 数据包",
        status="active",
        priority="high",
        phase="supplier_data_collection",
        progress_percent=65,
        current_step_key="supplier_data",
        due_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
        started_at=now,
        metadata_json={
            "product": "热轧卷板",
            "reporting_period": "2026 Q1",
            "period_start": "2026-01-01",
            "period_end": "2026-03-31",
            "scenario": "steel_hrc_cbam_demo",
            "business_goal": "形成可审计、可审批、可导出的 CBAM 报告草稿",
        },
    )
    db.add(workflow)
    db.flush()

    for step_payload in CBAM_HRC_DEMO_STEPS:
        db.add(
            WorkflowStep(
                workflow_id=workflow.id,
                tenant_id=tenant_uuid,
                inputs_json={},
                checkpoints_json=[],
                **step_payload,
            )
        )
    db.flush()
    db.refresh(workflow)
    return workflow


def list_workflows(
    db: Session,
    tenant_id: uuid.UUID | str,
    enterprise_id: uuid.UUID | str | None = None,
    *,
    workflow_type: str | None = None,
    status_filter: str | None = None,
) -> list[WorkflowInstance]:
    tenant_uuid = _uuid(tenant_id)
    enterprise_uuid = _uuid(enterprise_id)
    query = (
        db.query(WorkflowInstance)
        .options(selectinload(WorkflowInstance.steps))
        .filter(
            WorkflowInstance.tenant_id == tenant_uuid,
            WorkflowInstance.enterprise_id == enterprise_uuid,
        )
    )
    if workflow_type:
        query = query.filter(WorkflowInstance.workflow_type == workflow_type)
    if status_filter:
        query = query.filter(WorkflowInstance.status == status_filter)
    return query.order_by(WorkflowInstance.updated_at.desc()).all()


def get_workflow_for_tenant(
    db: Session,
    workflow_id: uuid.UUID | str,
    tenant_id: uuid.UUID | str,
    enterprise_id: uuid.UUID | str | None = None,
) -> WorkflowInstance:
    """Return a workflow only when both tenant and enterprise boundaries match.

    ``enterprise_id=None`` deliberately scopes the lookup to unassigned
    workflows instead of falling back to tenant-wide access. User-facing
    callers must pass the authenticated user's enterprise id.
    """
    workflow_uuid = _uuid(workflow_id)
    tenant_uuid = _uuid(tenant_id)
    enterprise_uuid = _uuid(enterprise_id)
    workflow = (
        db.query(WorkflowInstance)
        .options(selectinload(WorkflowInstance.steps))
        .filter(
            WorkflowInstance.id == workflow_uuid,
            WorkflowInstance.tenant_id == tenant_uuid,
            WorkflowInstance.enterprise_id == enterprise_uuid,
        )
        .first()
    )
    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="工作流不存在或不属于当前租户与企业",
        )
    return workflow


def workflow_to_dict(workflow: WorkflowInstance, *, include_steps: bool = True) -> dict[str, Any]:
    steps = sorted(workflow.steps or [], key=lambda step: step.sort_order)
    return {
        "id": str(workflow.id),
        "tenant_id": str(workflow.tenant_id),
        "enterprise_id": str(workflow.enterprise_id) if workflow.enterprise_id else None,
        "workflow_key": workflow.workflow_key,
        "workflow_type": workflow.workflow_type,
        "title": workflow.title,
        "status": workflow.status,
        "priority": workflow.priority,
        "phase": workflow.phase,
        "progress_percent": workflow.progress_percent,
        "current_step_key": workflow.current_step_key,
        "due_at": workflow.due_at.isoformat() if workflow.due_at else None,
        "started_at": workflow.started_at.isoformat() if workflow.started_at else None,
        "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None,
        "metadata": workflow.metadata_json or {},
        "steps": [
            {
                "id": str(step.id),
                "step_key": step.step_key,
                "title": step.title,
                "status": step.status,
                "sort_order": step.sort_order,
                "agent_profile_key": step.agent_profile_key,
                "risk_level": step.risk_level,
                "inputs": step.inputs_json or {},
                "outputs": step.outputs_json or {},
                "checkpoints": step.checkpoints_json or [],
                "started_at": step.started_at.isoformat() if step.started_at else None,
                "completed_at": step.completed_at.isoformat() if step.completed_at else None,
            }
            for step in steps
        ]
        if include_steps
        else [],
        "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
        "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
    }


def advance_workflow_step(
    db: Session,
    workflow: WorkflowInstance,
    *,
    actor_user_id: uuid.UUID | str | None = None,
    note: str | None = None,
) -> WorkflowInstance:
    """Complete the current step and move the workflow to the next pending step."""
    now = datetime.now(timezone.utc)
    previous_progress = workflow.progress_percent or 0
    steps = sorted(workflow.steps or [], key=lambda step: step.sort_order)
    current = next((step for step in steps if step.step_key == workflow.current_step_key), None)
    if current is None:
        current = next((step for step in steps if step.status == "in_progress"), None)

    if current and current.status not in {"completed", "skipped"}:
        current.status = "completed"
        current.completed_at = now
        audit_note = {
            "actor_user_id": str(actor_user_id) if actor_user_id else None,
            "note": note or "advanced_by_user",
            "at": now.isoformat(),
        }
        current.checkpoints_json = [*(current.checkpoints_json or []), audit_note]

    next_step = next((step for step in steps if step.status == "pending"), None)
    if next_step:
        next_step.status = "in_progress"
        next_step.started_at = now
        workflow.current_step_key = next_step.step_key
        workflow.phase = next_step.step_key
        workflow.status = "active"
    else:
        workflow.current_step_key = None
        workflow.phase = "completed"
        workflow.status = "completed"
        workflow.completed_at = now

    calculated_progress = _progress_from_steps(steps)
    if workflow.status == "completed":
        workflow.progress_percent = 100
    else:
        # Keep business progress monotonic. The initial CBAM demo progress
        # includes supplier-response completeness, so a pure step-count
        # calculation can otherwise make the UI move backwards.
        workflow.progress_percent = min(99, max(previous_progress + 5, calculated_progress))
    db.flush()
    db.refresh(workflow)
    return workflow
