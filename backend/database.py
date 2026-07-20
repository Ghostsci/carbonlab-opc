import json
import sqlite3
import uuid

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from backend.config import settings
from backend.core.ledger import content_hash


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def _sqlite_passport_profile_hash(
    tenant_id,
    account_id,
    installation_id,
    status,
    schema_version,
    snapshot_json,
    assessment_json,
    derived_from_json,
):
    """SQLite parity helper used by the database publication trigger."""

    def normalized_uuid(value):
        return str(uuid.UUID(str(value)))

    try:
        payload = {
            "record_type": "installation_profile_version",
            "tenant_id": normalized_uuid(tenant_id),
            "account_id": normalized_uuid(account_id),
            "installation_id": normalized_uuid(installation_id),
            "status": str(status),
            "schema_version": int(schema_version),
            "snapshot": json.loads(snapshot_json),
            "assessment": json.loads(assessment_json),
            "derived_from": json.loads(derived_from_json),
        }
        return content_hash(payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        return "__invalid_passport_profile_payload__"


def register_sqlite_integrity_functions(dbapi_connection):
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.create_function(
            "zcy_passport_profile_hash",
            8,
            _sqlite_passport_profile_hash,
            deterministic=True,
        )


@event.listens_for(Engine, "connect")
def _register_sqlite_integrity_functions(dbapi_connection, _connection_record):
    register_sqlite_integrity_functions(dbapi_connection)


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            echo=False,
            pool_size=20,
            max_overflow=30,
            pool_recycle=3600,
            pool_pre_ping=True,
        )
    return _engine


def get_sessionmaker():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


def get_db():
    db = get_sessionmaker()()
    try:
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            from backend.middleware.tenant import peek_current_tenant_id

            tenant_id = peek_current_tenant_id()
            if tenant_id:
                db.execute(
                    text("SET LOCAL app.current_tenant_id = :tenant_id"),
                    {"tenant_id": tenant_id},
                )
        yield db
    finally:
        db.close()
