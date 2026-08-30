import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth.jwt import create_access_token
from backend.main import app
from backend.middleware.tenant import peek_current_tenant_id, tenant_middleware


def test_public_registration_is_disabled_for_tenant_scoped_accounts():
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/register",
            json={"email": "public-signup@example.com", "password": "not-used-123"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "企业账号由管理员按租户开通；当前不开放公开注册"


def test_authenticated_me_route_receives_tenant_context_from_access_token():
    """`/api/auth/me` is authenticated and must not inherit public auth routing."""
    probe = FastAPI()
    probe.middleware("http")(tenant_middleware)

    @probe.get("/api/auth/me")
    def tenant_probe():
        return {"tenant_id": peek_current_tenant_id()}

    tenant_id = uuid.uuid4()
    token = create_access_token(
        str(uuid.uuid4()),
        "tenant-probe@example.com",
        str(tenant_id),
    )

    with TestClient(probe) as client:
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json() == {"tenant_id": str(tenant_id)}
