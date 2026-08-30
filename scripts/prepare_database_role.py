"""Create and grant the non-superuser PostgreSQL runtime role.

Alembic needs a database owner for DDL, while the web application must not run
as that owner or as a superuser because either identity can bypass RLS. This
startup helper keeps those responsibilities separate and is idempotent.
"""

from __future__ import annotations

import argparse
import os

from psycopg2 import sql
from sqlalchemy import create_engine


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def prepare(*, grant: bool) -> None:
    migration_url = _required("DATABASE_MIGRATION_URL")
    app_user = _required("POSTGRES_APP_USER")
    app_password = _required("POSTGRES_APP_PASSWORD")
    engine = create_engine(migration_url, isolation_level="AUTOCOMMIT")
    owner_user = engine.url.username
    database_name = engine.url.database
    if not owner_user or not database_name:
        raise RuntimeError("DATABASE_MIGRATION_URL must include owner and database")

    raw = engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (app_user,))
            exists = cursor.fetchone() is not None
            role_statement = "ALTER ROLE" if exists else "CREATE ROLE"
            cursor.execute(
                sql.SQL(
                    f"{role_statement} {{}} WITH LOGIN PASSWORD {{}} NOSUPERUSER "
                    "NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
                ).format(sql.Identifier(app_user), sql.Literal(app_password))
            )
            cursor.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(database_name), sql.Identifier(app_user)
                )
            )
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = 'tenant_user'")
            if cursor.fetchone() is not None:
                cursor.execute(
                    sql.SQL("GRANT tenant_user TO {}").format(sql.Identifier(app_user))
                )
            if grant:
                cursor.execute(
                    sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(app_user))
                )
                cursor.execute(
                    sql.SQL(
                        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}"
                    ).format(sql.Identifier(app_user))
                )
                cursor.execute(
                    sql.SQL(
                        "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {}"
                    ).format(sql.Identifier(app_user))
                )
                cursor.execute(
                    sql.SQL(
                        "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
                    ).format(sql.Identifier(owner_user), sql.Identifier(app_user))
                )
                cursor.execute(
                    sql.SQL(
                        "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                        "GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {}"
                    ).format(sql.Identifier(owner_user), sql.Identifier(app_user))
                )
                for signature in (
                    "public.zcy_auth_user_by_email(text)",
                    "public.zcy_auth_user_by_id(uuid)",
                ):
                    cursor.execute("SELECT to_regprocedure(%s)", (signature,))
                    if cursor.fetchone()[0] is not None:
                        cursor.execute(
                            sql.SQL("GRANT EXECUTE ON FUNCTION {} TO {}").format(
                                sql.SQL(signature), sql.Identifier(app_user)
                            )
                        )
        raw.commit()
    finally:
        raw.close()
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grant", action="store_true", help="grant runtime access after migrations")
    args = parser.parse_args()
    prepare(grant=args.grant)


if __name__ == "__main__":
    main()
