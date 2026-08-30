"""Behavioral tests for checked-in digital employee skills."""

from fastapi.testclient import TestClient
from passlib.context import CryptContext

from backend.database import Base, get_engine, get_sessionmaker
from backend.main import app
from backend.models.enterprise import Enterprise
from backend.models.tenant import Tenant
from backend.models.user import User
from backend.services.built_in_skills import REQUIRED_AI_ROLES, load_built_in_skills


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def setup_module():
    Base.metadata.create_all(bind=get_engine())


def teardown_module():
    Base.metadata.drop_all(bind=get_engine())


def test_each_ai_employee_has_one_versioned_non_reasoning_skill():
    skills = load_built_in_skills()

    assert {skill.role_id for skill in skills} == REQUIRED_AI_ROLES
    assert len({skill.skill_id for skill in skills}) == len(skills)
    assert all(skill.version == "1.0.0" for skill in skills)
    assert all(len(skill.package_sha256) == 64 for skill in skills)
    assert all(len(skill.instruction_sha256) == 64 for skill in skills)
    assert all(skill.stores_raw_chain_of_thought is False for skill in skills)
    assert all(skill.eval_cases for skill in skills)


def test_workforce_endpoint_exposes_skill_version_and_hash_per_ai_employee():
    db = get_sessionmaker()()
    try:
        tenant = Tenant(name="SKILL TENANT", slug="skill-tenant")
        db.add(tenant)
        db.flush()
        enterprise = Enterprise(
            name="Skill Factory",
            unified_social_credit_code="91110000SKILL00001",
            industry_code="C31",
            industry_name="制造业",
            tenant_id=tenant.id,
        )
        db.add(enterprise)
        db.flush()
        user = User(
            email="skills@example.com",
            password_hash=pwd_context.hash("secret123"),
            role="admin",
            tenant_id=tenant.id,
            enterprise_id=enterprise.id,
        )
        db.add(user)
        db.commit()

        client = TestClient(app)
        login = client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "secret123"},
        )
        assert login.status_code == 200, login.json()
        response = client.get(
            "/api/upload/workforce/roles",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )

        assert response.status_code == 200, response.json()
        payload = response.json()
        assert payload["built_in_skill_count"] == 4
        by_role = {role["role_id"]: role for role in payload["roles"]}
        for role_id in REQUIRED_AI_ROLES:
            skill = by_role[role_id]["skill"]
            assert skill["role_id"] == role_id
            assert skill["version"] == "1.0.0"
            assert len(skill["package_sha256"]) == 64
        assert by_role["H-01"]["skill"] is None
        assert by_role["R-01"]["skill"] is None
    finally:
        db.close()
