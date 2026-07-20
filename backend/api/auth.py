import hmac
import secrets
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.auth.jwt import create_access_token
from backend.auth.refresh_sessions import (
    create_refresh_session,
    revoke_refresh_session,
    rotate_refresh_session,
)
from backend.database import get_db
from backend.models.user import User
from backend.config import get_cors_allowed_origins, settings

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    tenant_id: str | None
    enterprise_id: str | None


def _set_auth_cookies(response: Response, refresh_token: str) -> None:
    csrf_token = secrets.token_urlsafe(32)
    max_age = settings.refresh_token_expire_days * 24 * 60 * 60
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        max_age=max_age,
        path="/api/auth",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        max_age=max_age,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        key="refresh_token",
        path="/api/auth",
    )
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path="/",
    )


def _require_csrf(request: Request) -> None:
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get(CSRF_HEADER_NAME)
    if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF 校验失败",
        )


def _origin_from_url(value: str) -> str | None:
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}".rstrip("/")


def _request_origin(request: Request) -> str:
    return f"{request.url.scheme.lower()}://{request.url.netloc.lower()}".rstrip("/")


def _require_allowed_browser_origin(request: Request) -> None:
    """Reject browser credential-setting requests from unexpected origins.

    CLI/mobile clients may omit Origin/Referer. Browser requests that include
    either header must match the API origin or configured frontend origins.
    """
    origin_header = request.headers.get("origin")
    referer_header = request.headers.get("referer")
    supplied_origin = _origin_from_url(origin_header or referer_header or "")
    if supplied_origin is None:
        return

    allowed_origins = set(get_cors_allowed_origins())
    allowed_origins.add(_request_origin(request))
    if supplied_origin not in allowed_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="请求来源不被允许",
        )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=TokenResponse,
    response_model_exclude_none=True,
)
def register(req: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    _require_allowed_browser_origin(request)
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱已注册",
        )
    if len(req.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码长度不能少于6位",
        )

    user = User(
        email=req.email,
        password_hash=pwd_context.hash(req.password),
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    access_token = create_access_token(
        str(user.id),
        user.email,
        str(user.tenant_id) if user.tenant_id else None,
    )
    refresh_token = create_refresh_session(db, user)
    _set_auth_cookies(response, refresh_token)

    return TokenResponse(
        access_token=access_token,
        user=user.to_dict(),
    )


@router.post("/login", response_model=TokenResponse, response_model_exclude_none=True)
def login(req: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    _require_allowed_browser_origin(request)
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not pwd_context.verify(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )

    access_token = create_access_token(
        str(user.id),
        user.email,
        str(user.tenant_id) if user.tenant_id else None,
    )
    refresh_token = create_refresh_session(db, user)
    _set_auth_cookies(response, refresh_token)

    return TokenResponse(
        access_token=access_token,
        user=user.to_dict(),
    )


@router.post("/refresh")
def refresh(
    request: Request,
    response: Response,
    req: RefreshRequest | None = None,
    db: Session = Depends(get_db),
):
    body_refresh_token = req.refresh_token if req and req.refresh_token else None
    refresh_token = body_refresh_token or request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少刷新令牌",
        )

    if body_refresh_token is None:
        _require_allowed_browser_origin(request)
        _require_csrf(request)

    user, new_refresh_token = rotate_refresh_session(db, refresh_token, request)

    access_token = create_access_token(
        str(user.id),
        user.email,
        str(user.tenant_id) if user.tenant_id else None,
    )
    _set_auth_cookies(response, new_refresh_token)
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        _require_allowed_browser_origin(request)
        _require_csrf(request)
        revoke_refresh_session(db, refresh_token)
    _clear_auth_cookies(response)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user.to_dict()
