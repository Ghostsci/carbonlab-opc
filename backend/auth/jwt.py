"""JWT token creation, verification, and decoding."""

from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

from fastapi import HTTPException, status
from jose import JWTError, jwt

from backend.config import settings

SECRET_KEY = settings.jwt_secret
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes
REFRESH_TOKEN_EXPIRE_DAYS = settings.refresh_token_expire_days


def create_access_token(user_id: str, email: str, tenant_id: str | None = None) -> str:
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if tenant_id:
        payload["tenant_id"] = tenant_id
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def refresh_token_expires_at(now: datetime | None = None) -> datetime:
    base = now or datetime.now(timezone.utc)
    return base + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)


def create_refresh_token(
    user_id: str,
    email: str,
    token_id: str | None = None,
    expires_at: datetime | None = None,
) -> str:
    token_id = token_id or uuid.uuid4().hex
    payload = {
        "sub": user_id,
        "email": email,
        "type": "refresh",
        "jti": token_id,
        "exp": expires_at or refresh_token_expires_at(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的认证令牌",
        )
