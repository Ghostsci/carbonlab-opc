"""Exact-key authentication lookups that do not weaken tenant RLS."""

from __future__ import annotations

import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.models.user import User


def _is_postgres(db: Session) -> bool:
    return db.bind is not None and db.bind.dialect.name == "postgresql"


def auth_user_by_email(db: Session, email: str) -> User | None:
    if not _is_postgres(db):
        user = db.query(User).filter(User.email == email).first()
    else:
        statement = select(User).from_statement(
            text("SELECT * FROM public.zcy_auth_user_by_email(:email)")
        )
        user = db.execute(statement, {"email": email}).scalar_one_or_none()
    if user is not None:
        db.expunge(user)
    return user


def auth_user_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    if not _is_postgres(db):
        user = db.query(User).filter(User.id == user_id).first()
    else:
        statement = select(User).from_statement(
            text("SELECT * FROM public.zcy_auth_user_by_id(:user_id)")
        )
        user = db.execute(statement, {"user_id": user_id}).scalar_one_or_none()
    if user is not None:
        db.expunge(user)
    return user
