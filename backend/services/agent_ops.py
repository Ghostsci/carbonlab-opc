"""Audit-safe task and execution trace service for the product workforce."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from backend.core.ledger import content_hash
from backend.models.agent_ops import (
    TERMINAL_AGENT_RUN_STATUSES,
    AgentRunEvent,
    AgentRunLog,
)
from backend.services.built_in_skills import BuiltInSkillError, get_skill_for_role
from backend.services.digital_workforce import ROLE_CONTRACTS


TRACE_REDACTION_VERSION = "trace-redaction-v1"
RUN_STATUSES = frozenset(
    {"queued", "running", "waiting_human", "completed", "failed", "cancelled"}
)
EVENT_STATUSES = frozenset({"info", "running", "success", "warning", "blocked", "error"})
_SENSITIVE_KEY = re.compile(
    r"(?:^|[_-])(api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|authorization|credential)(?:$|[_-])",
    re.IGNORECASE,
)
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)([?&](?:access_token|refresh_token|token|api_key|key)=)[^&#\s]+"),
)
_MAX_TRACE_TEXT = 2000


class AgentOpsError(ValueError):
    """Raised when a task or trace violates the governed execution contract."""


def _uuid(value: uuid.UUID | str | None) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def redact_trace_value(value: Any, *, key: str | None = None) -> Any:
    """Return a JSON-safe trace payload with credentials and raw prompts removed."""
    if key and _SENSITIVE_KEY.search(str(key)):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(child_key): redact_trace_value(child_value, key=str(child_key))
            for child_key, child_value in value.items()
            if str(child_key).lower() not in {"chain_of_thought", "hidden_reasoning", "system_prompt"}
        }
    if isinstance(value, (list, tuple, set)):
        return [redact_trace_value(item) for item in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized.astimezone(timezone.utc).isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        # Traces are descriptive, not formal ledgers. Preserve an explicit text
        # representation so logging never changes a business value silently.
        return repr(value)
    if isinstance(value, str):
        redacted = value
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub(
                lambda match: f"{match.group(1)}[REDACTED]" if match.lastindex else "[REDACTED]",
                redacted,
            )
        if len(redacted) > _MAX_TRACE_TEXT:
            return f"{redacted[:_MAX_TRACE_TEXT]}…[TRUNCATED]"
        return redacted
    if value is None or isinstance(value, (bool, int)):
        return value
    return str(value)


def _role_contract(role_id: str) -> dict[str, Any]:
    contract = next((role for role in ROLE_CONTRACTS if role["role_id"] == role_id), None)
    if contract is None:
        raise AgentOpsError(f"unknown governed role: {role_id}")
    return dict(contract)


def start_agent_run(
    db: Session,
    *,
    tenant_id: uuid.UUID | str,
    enterprise_id: uuid.UUID | str,
    agent_id: str,
    trigger: str,
    trigger_ref: str | None = None,
    source_file_id: uuid.UUID | str | None = None,
    workflow_id: uuid.UUID | str | None = None,
    workflow_step_id: uuid.UUID | str | None = None,
    input_snapshot: dict[str, Any] | None = None,
    parent_run_id: str | None = None,
    attempt_number: int = 1,
    summary: str | None = None,
) -> AgentRunLog:
    """Create one run and its immutable start event without committing."""
    tenant_uuid = _uuid(tenant_id)
    enterprise_uuid = _uuid(enterprise_id)
    if tenant_uuid is None or enterprise_uuid is None:
        raise AgentOpsError("agent runs require tenant and enterprise scope")
    if attempt_number < 1:
        raise AgentOpsError("attempt_number must be positive")
    contract = _role_contract(agent_id)
    skill = get_skill_for_role(agent_id)
    if contract["kind"] == "ai_agent" and skill is None:
        raise BuiltInSkillError(f"AI employee {agent_id} has no built-in skill")

    now = datetime.now(timezone.utc)
    run = AgentRunLog(
        agent_id=agent_id,
        run_id=f"run_{uuid.uuid4().hex}",
        tenant_id=tenant_uuid,
        enterprise_id=enterprise_uuid,
        workflow_id=_uuid(workflow_id),
        workflow_step_id=_uuid(workflow_step_id),
        source_file_id=_uuid(source_file_id),
        parent_run_id=parent_run_id,
        attempt_number=attempt_number,
        trigger=trigger[:20],
        trigger_ref=trigger_ref[:255] if trigger_ref else None,
        status="running",
        skill_id=skill.skill_id if skill else None,
        skill_version=skill.version if skill else None,
        skill_sha256=skill.package_sha256 if skill else None,
        redaction_version=TRACE_REDACTION_VERSION,
        node_path=[contract["stage_key"]],
        input_snapshot=redact_trace_value(input_snapshot or {}),
        summary=(summary or f"{contract['display_name']}开始处理任务")[:1000],
        started_at=now,
    )
    db.add(run)
    db.flush()
    append_agent_run_event(
        db,
        run=run,
        event_type="task_started",
        status="running",
        title=f"{contract['display_name']}开始工作",
        summary=run.summary,
        payload={
            "trigger": trigger,
            "trigger_ref": trigger_ref,
            "attempt_number": attempt_number,
            "skill": (
                {
                    "skill_id": skill.skill_id,
                    "version": skill.version,
                    "package_sha256": skill.package_sha256,
                }
                if skill
                else None
            ),
        },
        evidence_refs=[str(source_file_id)] if source_file_id else [],
        occurred_at=now,
    )
    return run


def append_agent_run_event(
    db: Session,
    *,
    run: AgentRunLog,
    event_type: str,
    status: str,
    title: str,
    summary: str,
    payload: dict[str, Any] | None = None,
    evidence_refs: list[Any] | None = None,
    occurred_at: datetime | None = None,
) -> AgentRunEvent:
    """Append one hash-linked, redacted event to a tenant-owned run."""
    if run.tenant_id is None or run.enterprise_id is None:
        raise AgentOpsError("legacy unscoped runs cannot receive governed events")
    if status not in EVENT_STATUSES:
        raise AgentOpsError(f"unsupported event status: {status}")
    # Locking the run serializes sequence allocation under PostgreSQL. SQLite
    # ignores FOR UPDATE, while the unique constraint still prevents ambiguity.
    locked = (
        db.query(AgentRunLog)
        .filter(AgentRunLog.run_id == run.run_id)
        .with_for_update()
        .one()
    )
    if locked.status in TERMINAL_AGENT_RUN_STATUSES:
        raise AgentOpsError(
            f"cannot append events after run reached terminal status {locked.status}"
        )
    last = (
        db.query(AgentRunEvent)
        .filter(AgentRunEvent.run_id == run.run_id)
        .order_by(AgentRunEvent.sequence.desc())
        .first()
    )
    sequence = (last.sequence + 1) if last else 1
    event_time = occurred_at or datetime.now(timezone.utc)
    redacted_payload = redact_trace_value(payload or {})
    redacted_evidence = redact_trace_value(evidence_refs or [])
    redacted_title = str(redact_trace_value(title))[:255]
    redacted_summary = str(redact_trace_value(summary))[:1000]
    hash_subject = {
        "tenant_id": str(locked.tenant_id),
        "enterprise_id": str(locked.enterprise_id),
        "run_id": locked.run_id,
        "sequence": sequence,
        "event_type": event_type,
        "status": status,
        "title": redacted_title,
        "summary": redacted_summary,
        "payload": redacted_payload,
        "evidence_refs": redacted_evidence,
        "prev_event_sha256": last.event_sha256 if last else None,
        "created_at": event_time,
    }
    event = AgentRunEvent(
        tenant_id=locked.tenant_id,
        enterprise_id=locked.enterprise_id,
        run_id=locked.run_id,
        sequence=sequence,
        event_type=event_type[:60],
        status=status,
        title=redacted_title,
        summary=redacted_summary,
        payload_json=redacted_payload,
        evidence_refs=redacted_evidence,
        prev_event_sha256=last.event_sha256 if last else None,
        event_sha256=content_hash(hash_subject),
        created_at=event_time,
    )
    db.add(event)
    db.flush()
    return event


def complete_agent_run(
    db: Session,
    *,
    run: AgentRunLog,
    summary: str,
    output_snapshot: dict[str, Any] | None = None,
    final_action: dict[str, Any] | None = None,
    evidence_refs: list[Any] | None = None,
    waiting_human: bool = False,
) -> AgentRunLog:
    status = "waiting_human" if waiting_human else "completed"
    event_status = "warning" if waiting_human else "success"
    now = datetime.now(timezone.utc)
    redacted_output = redact_trace_value(output_snapshot or {})
    append_agent_run_event(
        db,
        run=run,
        event_type="human_handoff" if waiting_human else "task_completed",
        status=event_status,
        title="等待人工责任门" if waiting_human else "任务完成",
        summary=summary,
        payload={"output": redacted_output, "final_action": final_action or {}},
        evidence_refs=evidence_refs,
        occurred_at=now,
    )
    run.status = status
    run.status_reason = "human_confirmation_required" if waiting_human else "completed_normally"
    run.summary = str(redact_trace_value(summary))[:1000]
    run.output_snapshot = redacted_output
    run.final_action = redact_trace_value(final_action or {})
    run.completed_at = now
    if run.started_at:
        started = run.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        run.execution_ms = max(0, int((now - started).total_seconds() * 1000))
    db.flush()
    return run


def fail_agent_run(
    db: Session,
    *,
    run: AgentRunLog,
    error_message: str,
    status_reason: str = "execution_failed",
    payload: dict[str, Any] | None = None,
) -> AgentRunLog:
    now = datetime.now(timezone.utc)
    safe_error = str(redact_trace_value(error_message))[:4000]
    append_agent_run_event(
        db,
        run=run,
        event_type="task_failed",
        status="error",
        title="任务失败",
        summary=safe_error[:1000],
        payload=payload,
        occurred_at=now,
    )
    run.status = "failed"
    run.status_reason = status_reason[:255]
    run.error_message = safe_error
    run.summary = safe_error[:1000]
    run.completed_at = now
    if run.started_at:
        started = run.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        run.execution_ms = max(0, int((now - started).total_seconds() * 1000))
    db.flush()
    return run


def list_agent_runs(
    db: Session,
    *,
    tenant_id: uuid.UUID | str,
    enterprise_id: uuid.UUID | str,
    source_file_id: uuid.UUID | str | None = None,
    agent_id: str | None = None,
    status_filter: str | None = None,
    limit: int = 100,
) -> list[AgentRunLog]:
    tenant_uuid = _uuid(tenant_id)
    enterprise_uuid = _uuid(enterprise_id)
    query = db.query(AgentRunLog).filter(
        AgentRunLog.tenant_id == tenant_uuid,
        AgentRunLog.enterprise_id == enterprise_uuid,
    )
    if source_file_id is not None:
        query = query.filter(AgentRunLog.source_file_id == _uuid(source_file_id))
    if agent_id:
        query = query.filter(AgentRunLog.agent_id == agent_id)
    if status_filter:
        if status_filter not in RUN_STATUSES:
            raise AgentOpsError(f"unsupported run status: {status_filter}")
        query = query.filter(AgentRunLog.status == status_filter)
    return (
        query.order_by(AgentRunLog.started_at.desc(), AgentRunLog.id.desc())
        .limit(min(max(limit, 1), 200))
        .all()
    )


def get_agent_run(
    db: Session,
    *,
    run_id: str,
    tenant_id: uuid.UUID | str,
    enterprise_id: uuid.UUID | str,
) -> AgentRunLog | None:
    return (
        db.query(AgentRunLog)
        .options(selectinload(AgentRunLog.events))
        .filter(
            AgentRunLog.run_id == run_id,
            AgentRunLog.tenant_id == _uuid(tenant_id),
            AgentRunLog.enterprise_id == _uuid(enterprise_id),
        )
        .first()
    )


def run_to_dict(run: AgentRunLog, *, include_events: bool = False) -> dict[str, Any]:
    contract = _role_contract(run.agent_id)
    payload = {
        "id": str(run.id),
        "run_id": run.run_id,
        "agent_id": run.agent_id,
        "agent_name": contract["display_name"],
        "agent_kind": contract["kind"],
        "tenant_id": str(run.tenant_id) if run.tenant_id else None,
        "enterprise_id": str(run.enterprise_id) if run.enterprise_id else None,
        "workflow_id": str(run.workflow_id) if run.workflow_id else None,
        "workflow_step_id": str(run.workflow_step_id) if run.workflow_step_id else None,
        "source_file_id": str(run.source_file_id) if run.source_file_id else None,
        "parent_run_id": run.parent_run_id,
        "attempt_number": run.attempt_number,
        "trigger": run.trigger,
        "trigger_ref": run.trigger_ref,
        "status": run.status,
        "status_reason": run.status_reason,
        "skill": (
            {
                "skill_id": run.skill_id,
                "version": run.skill_version,
                "package_sha256": run.skill_sha256,
            }
            if run.skill_id
            else None
        ),
        "redaction_version": run.redaction_version,
        "summary": run.summary,
        "input_snapshot": run.input_snapshot or {},
        "output_snapshot": run.output_snapshot or {},
        "final_action": run.final_action or {},
        "human_intervention": run.human_intervention or {},
        "execution_ms": run.execution_ms,
        "total_tokens": run.total_tokens,
        "total_cost_cny": format(run.total_cost_cny, "f") if run.total_cost_cny is not None else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "error_message": run.error_message,
    }
    payload["events"] = [event_to_dict(event) for event in run.events] if include_events else []
    return payload


def event_to_dict(event: AgentRunEvent) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "sequence": event.sequence,
        "event_type": event.event_type,
        "status": event.status,
        "title": event.title,
        "summary": event.summary,
        "payload": event.payload_json or {},
        "evidence_refs": event.evidence_refs or [],
        "prev_event_sha256": event.prev_event_sha256,
        "event_sha256": event.event_sha256,
        "created_at": event.created_at.isoformat(),
    }


def employee_overview(
    db: Session,
    *,
    tenant_id: uuid.UUID | str,
    enterprise_id: uuid.UUID | str,
) -> list[dict[str, Any]]:
    tenant_uuid = _uuid(tenant_id)
    enterprise_uuid = _uuid(enterprise_id)
    runs = (
        db.query(AgentRunLog)
        .filter(
            AgentRunLog.tenant_id == tenant_uuid,
            AgentRunLog.enterprise_id == enterprise_uuid,
        )
        .order_by(AgentRunLog.started_at.desc(), AgentRunLog.id.desc())
        .limit(500)
        .all()
    )
    by_agent: dict[str, list[AgentRunLog]] = {}
    for run in runs:
        by_agent.setdefault(run.agent_id, []).append(run)
    result = []
    for contract in ROLE_CONTRACTS:
        role_runs = by_agent.get(contract["role_id"], [])
        latest = role_runs[0] if role_runs else None
        active = next(
            (run for run in role_runs if run.status in {"queued", "running", "waiting_human"}),
            None,
        )
        skill = get_skill_for_role(contract["role_id"])
        result.append(
            {
                **dict(contract),
                "skill": skill.to_dict() if skill else None,
                "operating_status": active.status if active else "idle",
                "active_run": run_to_dict(active) if active else None,
                "latest_run": run_to_dict(latest) if latest else None,
                "metrics": {
                    "total_runs": len(role_runs),
                    "completed_runs": sum(run.status == "completed" for run in role_runs),
                    "waiting_human_runs": sum(run.status == "waiting_human" for run in role_runs),
                    "failed_runs": sum(run.status == "failed" for run in role_runs),
                },
            }
        )
    return result


def verify_event_chain(run: AgentRunLog) -> bool:
    previous: str | None = None
    for event in sorted(run.events, key=lambda item: item.sequence):
        if event.prev_event_sha256 != previous:
            return False
        subject = {
            "tenant_id": str(event.tenant_id),
            "enterprise_id": str(event.enterprise_id),
            "run_id": event.run_id,
            "sequence": event.sequence,
            "event_type": event.event_type,
            "status": event.status,
            "title": event.title,
            "summary": event.summary,
            "payload": event.payload_json or {},
            "evidence_refs": event.evidence_refs or [],
            "prev_event_sha256": event.prev_event_sha256,
            "created_at": event.created_at,
        }
        if content_hash(subject) != event.event_sha256:
            return False
        previous = event.event_sha256
    return True
