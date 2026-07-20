"""Add source and notes columns to carbon assets.

Revision ID: 023
Revises: 022
Create Date: 2026-05-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("carbon_assets", sa.Column("source", sa.String(200), nullable=True))
    op.add_column("carbon_assets", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("carbon_assets", "notes")
    op.drop_column("carbon_assets", "source")
