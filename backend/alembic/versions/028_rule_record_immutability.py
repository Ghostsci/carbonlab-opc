"""Protect RuleRecord from database-level update and delete.

Revision ID: 028
Revises: 027
Create Date: 2026-07-04
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            sa.text(
                """
                CREATE FUNCTION zcy_rule_record_immutable() RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION
                        'rule records are immutable; create a new vintage';
                END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER trg_rule_records_guard_update
                BEFORE UPDATE ON rule_records
                FOR EACH ROW EXECUTE FUNCTION zcy_rule_record_immutable();
                CREATE TRIGGER trg_rule_records_guard_delete
                BEFORE DELETE ON rule_records
                FOR EACH ROW EXECUTE FUNCTION zcy_rule_record_immutable();
                """
            )
        )
    elif dialect == "sqlite":
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_rule_records_guard_update
                BEFORE UPDATE ON rule_records
                FOR EACH ROW
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'rule records are immutable; create a new vintage'
                    );
                END;
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_rule_records_guard_delete
                BEFORE DELETE ON rule_records
                FOR EACH ROW
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'rule records are immutable; create a new vintage'
                    );
                END;
                """
            )
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS trg_rule_records_guard_update "
                "ON rule_records"
            )
        )
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS trg_rule_records_guard_delete "
                "ON rule_records"
            )
        )
        op.execute(sa.text("DROP FUNCTION IF EXISTS zcy_rule_record_immutable()"))
    elif dialect == "sqlite":
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_rule_records_guard_update"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_rule_records_guard_delete"))
