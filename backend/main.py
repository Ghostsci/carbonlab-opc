from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.api.ai import router as ai_router
from backend.api.agent_ops import router as agent_ops_router
from backend.api.auth import router as auth_router
from backend.api.health import router as health_router
from backend.api.knowledge import router as knowledge_router
from backend.api.passports import router as passports_router
from backend.api.upload import router as upload_router
from backend.auth.jwt import decode_token
from backend.auth.public_paths import is_public_path
from backend.config import get_cors_allowed_origins, settings
from backend.middleware.tenant import tenant_middleware


app = FastAPI(
    title="CarbonLab OPC",
    description="AI 原生制造企业碳数据提取、核算与可信护照系统",
    version="1.0.0-migration",
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.security_hsts_enabled:
            response.headers["Strict-Transport-Security"] = (
                f"max-age={settings.security_hsts_max_age}; includeSubDomains"
            )
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The tenant context is derived from a verified access token. Route-level
# dependencies still enforce user, tenant, and role permissions.
app.middleware("http")(tenant_middleware)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or is_public_path(path):
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "缺少有效的认证令牌"})

    try:
        payload = decode_token(auth_header.removeprefix("Bearer "))
        if payload.get("type") != "access" or not payload.get("sub"):
            raise ValueError("invalid access token payload")
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "无效或过期的认证令牌"})

    return await call_next(request)


app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(ai_router, prefix="/api")
app.include_router(agent_ops_router, prefix="/api")
app.include_router(knowledge_router, prefix="/api")
app.include_router(passports_router, prefix="/api")
