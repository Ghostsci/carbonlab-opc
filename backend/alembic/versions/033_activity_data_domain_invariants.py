"""Enforce positive activity quantities and valid reporting periods.

Revision ID: 033
Revises: 032
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "033"
down_revision: Union[str, None] = "032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _preflight() -> None:
    invalid = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM activity_data "
            "WHERE CAST(quantity AS NUMERIC) <= 0 OR period_start >= period_end"
        )
    ).scalar_one()
    if invalid:
        raise RuntimeError(
            f"033 found {invalid} invalid activity_data rows; audit and correct them before migration"
        )


def upgrade() -> None:
    _preflight()
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            sa.text(
                """
                CREATE TRIGGER IF NOT EXISTS trg_activity_data_domain_insert
                BEFORE INSERT ON activity_data
                WHEN CAST(NEW.quantity AS NUMERIC) <= 0 OR NEW.period_start >= NEW.period_end
                BEGIN
                    SELECT RAISE(ABORT, 'activity_data domain invariant violated');
                END
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER IF NOT EXISTS trg_activity_data_domain_update
                BEFORE UPDATE OF quantity, period_start, period_end ON activity_data
                WHEN CAST(NEW.quantity AS NUMERIC) <= 0 OR NEW.period_start >= NEW.period_end
                BEGIN
                    SELECT RAISE(ABORT, 'activity_data domain invariant violated');
                END
                """
            )
        )
        return

    op.create_check_constraint(
        "ck_activity_data_positive_quantity",
        "activity_data",
        "CAST(quantity AS NUMERIC) > 0",
    )
    op.create_check_constraint(
        "ck_activity_data_valid_period",
        "activity_data",
        "period_start < period_end",
    )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_activity_data_domain_update"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_activity_data_domain_insert"))
        return
    op.drop_constraint(
        "ck_activity_data_valid_period",
        "activity_data",
        type_="check",
    )
    op.drop_constraint(
        "ck_activity_data_positive_quantity",
        "activity_data",
        type_="check",
    )
