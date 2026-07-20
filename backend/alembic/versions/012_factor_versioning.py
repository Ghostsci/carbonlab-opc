"""factor versioning: add version_year, is_default, superseded_by, source_url, change_note"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("emission_factors", sa.Column("version_year", sa.Integer(), nullable=True))
    op.add_column("emission_factors", sa.Column("published_date", sa.Date(), nullable=True))
    op.add_column("emission_factors", sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("emission_factors", sa.Column("superseded_by", sa.Uuid(), nullable=True))
    op.add_column("emission_factors", sa.Column("source_url", sa.Text(), nullable=True))
    op.add_column("emission_factors", sa.Column("change_note", sa.Text(), nullable=True))
    op.create_index("ix_emission_factors_version_year", "emission_factors", ["version_year"])
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_factor_code_year_default "
        "ON emission_factors(code, version_year) WHERE is_default = true"
    )


def downgrade() -> None:
    op.drop_index("idx_factor_code_year_default", table_name="emission_factors")
    op.drop_index("ix_emission_factors_version_year", table_name="emission_factors")
    op.drop_column("emission_factors", "change_note")
    op.drop_column("emission_factors", "source_url")
    op.drop_column("emission_factors", "superseded_by")
    op.drop_column("emission_factors", "is_default")
    op.drop_column("emission_factors", "published_date")
    op.drop_column("emission_factors", "version_year")
