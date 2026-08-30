"""Public behavior tests for governed employee runs and trace APIs."""

import json
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from passlib.context import CryptContext
import pytest
from sqlalchemy.exc import IntegrityError

from backend.database import Base, get_engine, get_sessionmaker
from backend.main import app
from backend.models.agent_ops import (
    AgentRunEvent,
    AgentRunEventImmutableError,
    AgentRunImmutableError,
    AgentRunLog,
)
from backend.models.enterprise import Enterprise
from backend.models.tenant import Tenant
from backend.models.user import User
from backend.services.agent_ops import (
    AgentOpsError,
    append_agent_run_event,
    complete_agent_run,
    get_agent_run,
    redact_trace_value,
    start_agent_run,
    verify_event_chain,
)


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def setup_module():
    Base.metadata.create_all(bind=get_engine())


def teardown_module():
    Base.metadata.drop_all(bind=get_engine())


def _identity(db, slug: str, email: str):
    tenant = Tenant(name=slug.upper(), slug=slug)
    db.add(tenant)
    db.flush()
    enterprise = Enterprise(
        name=f"{slug} factory",
        unified_social_credit_code=f"91110000{slug[:8].upper():0<8}",
        industry_code="C31",
        industry_name="制造业",
        tenant_id=tenant.id,
    )
    db.add(enterprise)
    db.flush()
    user = User(
        email=email,
        password_hash=pwd_context.hash("secret123"),
        role="admin",
        tenant_id=tenant.id,
        enterprise_id=enterprise.id,
    )
    db.add(user)
    db.commit()
    return tenant, enterprise, user


def _login(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "secret123"},
    )
    assert response.status_code == 200, response.json()
    return response.json()["access_token"]


def test_run_events_are_versioned_redacted_hash_linked_and_immutable():
    db = get_sessionmaker()()
    try:
        tenant, enterprise, _user = _identity(
            db,
            "agent-trace",
            "agent-trace@example.com",
        )
        run = start_agent_run(
            db,
            tenant_id=tenant.id,
            enterprise_id=enterprise.id,
            agent_id="A-02",
            trigger="api",
            input_snapshot={
                "filename": "bill.csv",
                "api_key": "sk-THISMUSTNOTLEAK123",
                "url": "https://example.test/run?access_token=canary-secret",
                "system_prompt": "hidden",
            },
        )
        append_agent_run_event(
            db,
            run=run,
            event_type="candidate_extracted",
            status="success",
            title="提出候选字段",
            summary="已提出 3 个字段，等待质检",
            payload={"authorization": "Bearer secret-bearer-value", "field_count": 3},
        )
        complete_agent_run(
            db,
            run=run,
            summary="候选字段已交给 A-03",
            output_snapshot={"candidate_token": "must-not-leak", "field_count": 3},
            waiting_human=False,
        )
        db.commit()

        loaded = get_agent_run(
            db,
            run_id=run.run_id,
            tenant_id=tenant.id,
            enterprise_id=enterprise.id,
        )
        assert loaded is not None
        assert loaded.skill_id == "carbon-evidence-extraction"
        assert loaded.skill_version == "1.0.0"
        assert len(loaded.skill_sha256 or "") == 64
        assert [event.sequence for event in loaded.events] == [1, 2, 3]
        assert verify_event_chain(loaded) is True

        serialized = json.dumps(
            {
                "input": loaded.input_snapshot,
                "output": loaded.output_snapshot,
                "events": [event.payload_json for event in loaded.events],
            },
            ensure_ascii=False,
        )
        for secret in (
            "THISMUSTNOTLEAK",
            "canary-secret",
            "secret-bearer-value",
            "must-not-leak",
            "hidden",
        ):
            assert secret not in serialized

        loaded.events[0].summary = "tampered"
        with pytest.raises(AgentRunEventImmutableError):
            db.commit()
        db.rollback()

        with pytest.raises(IntegrityError):
            db.execute(
                AgentRunEvent.__table__.delete().where(
                    AgentRunEvent.id == loaded.events[0].id
                )
            )
            db.commit()
        db.rollback()
    finally:
        db.close()


def test_agent_ops_api_never_returns_another_enterprise_run():
    db = get_sessionmaker()()
    try:
        tenant_a, enterprise_a, _ = _identity(db, "ops-a", "ops-a@example.com")
        tenant_b, enterprise_b, _ = _identity(db, "ops-b", "ops-b@example.com")
        run_a = start_agent_run(
            db,
            tenant_id=tenant_a.id,
            enterprise_id=enterprise_a.id,
            agent_id="A-01",
            trigger="api",
            summary="A owned run",
        )
        complete_agent_run(db, run=run_a, summary="A complete")
        run_b = start_agent_run(
            db,
            tenant_id=tenant_b.id,
            enterprise_id=enterprise_b.id,
            agent_id="A-03",
            trigger="api",
            summary="B private run",
        )
        complete_agent_run(db, run=run_b, summary="B complete")
        db.commit()

        client = TestClient(app)
        token_a = _login(client, "ops-a@example.com")
        headers_a = {"Authorization": f"Bearer {token_a}"}

        listed = client.get("/api/agent-ops/runs", headers=headers_a)
        assert listed.status_code == 200, listed.json()
        assert [item["run_id"] for item in listed.json()["runs"]] == [run_a.run_id]

        detail_a = client.get(f"/api/agent-ops/runs/{run_a.run_id}", headers=headers_a)
        assert detail_a.status_code == 200, detail_a.json()
        assert detail_a.json()["event_chain_verified"] is True
        assert len(detail_a.json()["events"]) == 2

        detail_b = client.get(f"/api/agent-ops/runs/{run_b.run_id}", headers=headers_a)
        assert detail_b.status_code == 404

        employees = client.get("/api/agent-ops/employees", headers=headers_a)
        assert employees.status_code == 200, employees.json()
        by_role = {item["role_id"]: item for item in employees.json()["employees"]}
        assert by_role["A-01"]["metrics"]["total_runs"] == 1
        assert by_role["A-03"]["metrics"]["total_runs"] == 0
    finally:
        db.close()


def test_trace_redaction_covers_query_tokens_and_hidden_reasoning_keys():
    value = redact_trace_value(
        {
            "endpoint": "https://api.test/v1?token=abc123&mode=fast",
            "nested": {"credential": "top-secret"},
            "chain_of_thought": "do not retain",
        }
    )
    encoded = json.dumps(value)
    assert "abc123" not in encoded
    assert "top-secret" not in encoded
    assert "do not retain" not in encoded


def test_terminal_runs_reject_late_events_updates_and_deletes():
    db = get_sessionmaker()()
    try:
        tenant, enterprise, _user = _identity(
            db,
            "terminal-run",
            "terminal-run@example.com",
        )
        run = start_agent_run(
            db,
            tenant_id=tenant.id,
            enterprise_id=enterprise.id,
            agent_id="A-04",
            trigger="api",
        )
        complete_agent_run(db, run=run, summary="passport compiled")
        db.commit()

        run.summary = "tampered through ORM"
        with pytest.raises(AgentRunImmutableError):
            db.commit()
        db.rollback()

        with pytest.raises(AgentOpsError):
            append_agent_run_event(
                db,
                run=run,
                event_type="late_event",
                status="success",
                title="late",
                summary="must not be appended",
            )
        db.rollback()

        with pytest.raises(IntegrityError):
            db.execute(
                AgentRunLog.__table__.update()
                .where(AgentRunLog.run_id == run.run_id)
                .values(summary="tampered through SQL")
            )
            db.commit()
        db.rollback()

        with pytest.raises(IntegrityError):
            db.execute(
                AgentRunEvent.__table__.insert().values(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    enterprise_id=enterprise.id,
                    run_id=run.run_id,
                    sequence=3,
                    event_type="late_event",
                    status="success",
                    title="late",
                    summary="must not be appended",
                    payload_json={},
                    evidence_refs=[],
                    prev_event_sha256="a" * 64,
                    event_sha256="b" * 64,
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.commit()
        db.rollback()

        with pytest.raises(IntegrityError):
            db.execute(
                AgentRunLog.__table__.delete().where(
                    AgentRunLog.run_id == run.run_id
                )
            )
            db.commit()
        db.rollback()
    finally:
        db.close()


def test_database_rejects_cross_tenant_run_and_event_lineage():
    db = get_sessionmaker()()
    try:
        tenant_a, enterprise_a, _ = _identity(
            db,
            "lin-a",
            "lineage-a@example.com",
        )
        tenant_b, enterprise_b, _ = _identity(
            db,
            "lin-b",
            "lineage-b@example.com",
        )
        run_a = start_agent_run(
            db,
            tenant_id=tenant_a.id,
            enterprise_id=enterprise_a.id,
            agent_id="A-01",
            trigger="api",
        )
        db.commit()

        with pytest.raises(IntegrityError):
            db.execute(
                AgentRunLog.__table__.insert().values(
                    id=uuid.uuid4(),
                    agent_id="A-03",
                    run_id=f"run_{uuid.uuid4().hex}",
                    tenant_id=tenant_a.id,
                    enterprise_id=enterprise_b.id,
                    attempt_number=1,
                    trigger="api",
                    status="running",
                    redaction_version="trace-redaction-v1",
                )
            )
            db.commit()
        db.rollback()

        with pytest.raises(IntegrityError):
            db.execute(
                AgentRunEvent.__table__.insert().values(
                    id=uuid.uuid4(),
                    tenant_id=tenant_b.id,
                    enterprise_id=enterprise_b.id,
                    run_id=run_a.run_id,
                    sequence=2,
                    event_type="cross_scope_event",
                    status="success",
                    title="foreign",
                    summary="must not attach to tenant A",
                    payload_json={},
                    evidence_refs=[],
                    prev_event_sha256="a" * 64,
                    event_sha256="b" * 64,
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.commit()
        db.rollback()
    finally:
        db.close()
