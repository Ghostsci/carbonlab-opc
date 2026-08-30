"""Single source of truth for unauthenticated HTTP paths.

Authentication endpoints are not uniformly public: login/refresh/logout are
bootstrap operations, while ``/api/auth/me`` must run inside the authenticated
tenant context.  Keeping exact routes here prevents a broad ``/api/auth``
prefix from accidentally bypassing tenant initialization.
"""

from __future__ import annotations


PUBLIC_EXACT_PATHS = frozenset(
    {
        "/api/health",
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/refresh",
        "/api/auth/logout",
        "/openapi.json",
        "/redoc",
    }
)
PUBLIC_PATH_PREFIXES = ("/docs",)


def is_public_path(path: str) -> bool:
    """Return whether ``path`` may be reached without an access token."""
    normalized = path.rstrip("/") or "/"
    if normalized in PUBLIC_EXACT_PATHS:
        return True
    return any(
        normalized == prefix or normalized.startswith(f"{prefix}/")
        for prefix in PUBLIC_PATH_PREFIXES
    )
