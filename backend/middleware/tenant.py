"""Tenant middleware — extracts tenant_id from JWT and injects into request scope.

Usage:
    from backend.middleware.tenant import get_current_tenant_id

    @router.get("/data")
    def get_data(tenant_id: str = Depends(get_current_tenant_id)):
        # tenant_id is guaranteed to be present
        ...
"""

import contextvars
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status

from backend.auth.jwt import decode_token
from backend.auth.public_paths import is_public_path

# FastAPI doesn't have a built-in request-scoped DI container,
# so we use contextvars for the tenant scope.
_current_tenant_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_tenant_id", default=None
)


def set_current_tenant_id(tenant_id: str | None) -> None:
    _current_tenant_id.set(tenant_id)


def get_current_tenant_id() -> str:
    tid = _current_tenant_id.get()
    if tid is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="未找到租户信息 — 请确认已登录有效的租户账号",
        )
    return tid


def peek_current_tenant_id() -> str | None:
    """Return tenant context when present without raising for public requests."""
    return _current_tenant_id.get()


async def tenant_middleware(request: Request, call_next):
    """Extract tenant from JWT and set contextvar for downstream dependencies."""
    path = request.url.path

    # Clear on every request
    _current_tenant_id.set(None)

    if request.method == "OPTIONS" or is_public_path(path):
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            payload = decode_token(auth_header.removeprefix("Bearer "))
            tenant_id = payload.get("tenant_id")
            if not tenant_id and payload.get("sub"):
                from backend.auth.user_lookup import auth_user_by_id
                from backend.database import get_sessionmaker

                with get_sessionmaker()() as db:
                    user = auth_user_by_id(db, UUID(payload["sub"]))
                    tenant_id = str(user.tenant_id) if user and user.tenant_id else None
            if tenant_id:
                _current_tenant_id.set(tenant_id)
        except Exception:
            pass  # Let auth middleware handle 401

    return await call_next(request)
