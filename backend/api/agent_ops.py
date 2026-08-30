"""Read-only control plane for digital employees, skills and task traces."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.database import get_db
from backend.models.user import User
from backend.services.agent_ops import (
    AgentOpsError,
    employee_overview,
    get_agent_run,
    list_agent_runs,
    run_to_dict,
    verify_event_chain,
)
from backend.services.built_in_skills import get_skill, load_built_in_skills


router = APIRouter(prefix="/agent-ops", tags=["agent-ops"])


def _scope(user: User) -> tuple[uuid.UUID, uuid.UUID]:
    if user.tenant_id is None or user.enterprise_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前用户未绑定租户或企业",
        )
    return user.tenant_id, user.enterprise_id


@router.get("/skills")
def list_skills(user: User = Depends(get_current_user)):
    _scope(user)
    return {
        "skills": [skill.to_dict() for skill in load_built_in_skills()],
        "count": len(load_built_in_skills()),
    }


@router.get("/skills/{skill_id}")
def get_skill_detail(skill_id: str, user: User = Depends(get_current_user)):
    _scope(user)
    skill = get_skill(skill_id)
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill 不存在")
    return skill.to_dict(include_content=True)


@router.get("/employees")
def list_employees(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, enterprise_id = _scope(user)
    return {
        "employees": employee_overview(
            db,
            tenant_id=tenant_id,
            enterprise_id=enterprise_id,
        )
    }


@router.get("/runs")
def list_runs(
    source_file_id: uuid.UUID | None = None,
    agent_id: str | None = Query(default=None, max_length=100),
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, enterprise_id = _scope(user)
    try:
        runs = list_agent_runs(
            db,
            tenant_id=tenant_id,
            enterprise_id=enterprise_id,
            source_file_id=source_file_id,
            agent_id=agent_id,
            status_filter=status_filter,
            limit=limit,
        )
    except AgentOpsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"runs": [run_to_dict(run) for run in runs], "count": len(runs)}


@router.get("/runs/{run_id}")
def get_run_detail(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, enterprise_id = _scope(user)
    run = get_agent_run(
        db,
        run_id=run_id,
        tenant_id=tenant_id,
        enterprise_id=enterprise_id,
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务运行不存在")
    payload = run_to_dict(run, include_events=True)
    payload["event_chain_verified"] = verify_event_chain(run)
    return payload
