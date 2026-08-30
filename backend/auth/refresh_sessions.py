"""Server-side refresh-token session lifecycle.

Refresh JWTs remain opaque to the browser, but every issued token has a
server-side session row keyed by a hash of its JTI. That gives us revocation,
rotation, and replay detection instead of relying on self-contained JWT expiry.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.auth.jwt import create_refresh_token, decode_token, refresh_token_expires_at
from backend.auth.user_lookup import auth_user_by_id
from backend.models.refresh_token_session import RefreshTokenSession
from backend.models.user import User

REFRESH_REUSE_GRACE_SECONDS = 10


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def hash_token_id(token_id: str) -> str:
    return hashlib.sha256(token_id.encode("utf-8")).hexdigest()


def _request_user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    value = request.headers.get("user-agent")
    return value[:512] if value else None


def _request_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host[:100]


def _unauthorized(detail: str = "无效或过期的刷新令牌") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def create_refresh_session(db: Session, user: User, request: Request | None = None) -> str:
    token_id = uuid.uuid4().hex
    token_hash = hash_token_id(token_id)
    expires_at = refresh_token_expires_at()
    refresh_token = create_refresh_token(
        str(user.id),
        user.email,
        token_id=token_id,
        expires_at=expires_at,
    )

    db.add(
        RefreshTokenSession(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=_request_user_agent(request),
            ip_address=_request_ip(request),
        )
    )
    db.commit()
    return refresh_token


def _decode_refresh_payload(refresh_token: str) -> tuple[uuid.UUID, str]:
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise _unauthorized("无效的刷新令牌类型")

    user_id = payload.get("sub")
    token_id = payload.get("jti")
    if not user_id or not token_id:
        raise _unauthorized("无效的刷新令牌")

    try:
        return uuid.UUID(str(user_id)), str(token_id)
    except ValueError:
        raise _unauthorized("无效的刷新令牌")


def _revoke_all_user_sessions(db: Session, user_id: uuid.UUID, now: datetime) -> None:
    db.query(RefreshTokenSession).filter(
        RefreshTokenSession.user_id == user_id,
        RefreshTokenSession.revoked_at.is_(None),
    ).update({"revoked_at": now}, synchronize_session=False)
    db.commit()


def rotate_refresh_session(
    db: Session,
    refresh_token: str,
    request: Request | None = None,
) -> tuple[User, str]:
    user_id, token_id = _decode_refresh_payload(refresh_token)
    token_hash = hash_token_id(token_id)
    now = _utc_now()

    session = (
        db.query(RefreshTokenSession)
        .filter(
            RefreshTokenSession.user_id == user_id,
            RefreshTokenSession.token_hash == token_hash,
        )
        .first()
    )
    if session is None:
        raise _unauthorized()

    if session.revoked_at is not None:
        revoked_at = _as_utc(session.revoked_at)
        grace_deadline = now - timedelta(seconds=REFRESH_REUSE_GRACE_SECONDS)
        if not session.replaced_by_token_hash or revoked_at < grace_deadline:
            _revoke_all_user_sessions(db, user_id, now)
        raise _unauthorized("刷新令牌已失效")

    if _as_utc(session.expires_at) <= now:
        session.revoked_at = now
        db.commit()
        raise _unauthorized()

    user = auth_user_by_id(db, user_id)
    if user is None:
        session.revoked_at = now
        db.commit()
        raise _unauthorized("用户不存在")

    new_token_id = uuid.uuid4().hex
    new_token_hash = hash_token_id(new_token_id)
    expires_at = refresh_token_expires_at(now)
    new_refresh_token = create_refresh_token(
        str(user.id),
        user.email,
        token_id=new_token_id,
        expires_at=expires_at,
    )

    session.revoked_at = now
    session.replaced_by_token_hash = new_token_hash
    db.add(
        RefreshTokenSession(
            user_id=user.id,
            token_hash=new_token_hash,
            expires_at=expires_at,
            user_agent=_request_user_agent(request),
            ip_address=_request_ip(request),
        )
    )
    db.commit()

    return user, new_refresh_token


def revoke_refresh_session(db: Session, refresh_token: str) -> None:
    try:
        user_id, token_id = _decode_refresh_payload(refresh_token)
    except HTTPException:
        return

    session = (
        db.query(RefreshTokenSession)
        .filter(
            RefreshTokenSession.user_id == user_id,
            RefreshTokenSession.token_hash == hash_token_id(token_id),
            RefreshTokenSession.revoked_at.is_(None),
        )
        .first()
    )
    if session is None:
        return
    session.revoked_at = _utc_now()
    db.commit()


def cleanup_expired_refresh_sessions(
    db: Session,
    revoked_retention_days: int = 30,
    now: datetime | None = None,
) -> int:
    """Delete refresh sessions that can no longer be used.

    Expired sessions are immediately removable. Revoked sessions are retained
    for a short audit/replay-detection window before deletion.
    """
    current_time = now or _utc_now()
    revoked_cutoff = current_time - timedelta(days=revoked_retention_days)
    deleted = (
        db.query(RefreshTokenSession)
        .filter(
            or_(
                RefreshTokenSession.expires_at <= current_time,
                RefreshTokenSession.revoked_at <= revoked_cutoff,
            )
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return int(deleted)
