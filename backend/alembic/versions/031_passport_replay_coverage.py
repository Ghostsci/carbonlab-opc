"""Require published passport SEE results to cover every current formal input.

Revision ID: 031
Revises: 030
Create Date: 2026-07-10
"""

from importlib import import_module
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ensure_no_published_profiles() -> None:
    published_count = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM installation_profile_versions "
            "WHERE status = 'published'"
        )
    ).scalar_one()
    if published_count:
        raise RuntimeError(
            "031 requires audit and republication of pre-existing published passports"
        )


def upgrade() -> None:
    _ensure_no_published_profiles()
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS trg_passport_profile_replay_guard_insert "
                "ON installation_profile_versions"
            )
        )
    elif dialect == "sqlite":
        op.execute(
            sa.text("DROP TRIGGER IF EXISTS trg_passport_profile_replay_guard_insert")
        )
    else:
        return

    replay_guard = import_module(
        "backend.alembic.versions.030_passport_replay_guard"
    )
    if dialect == "postgresql":
        replay_guard._postgres_upgrade()
    else:
        replay_guard._sqlite_upgrade()


def downgrade() -> None:
    raise RuntimeError(
        "031 is an irreversible integrity migration; restore from a pre-031 backup "
        "instead of weakening published-passport replay checks"
    )
