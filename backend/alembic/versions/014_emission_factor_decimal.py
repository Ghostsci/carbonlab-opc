"""change emission_factors.value from Float to Numeric(18,8)"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("emission_factors") as batch_op:
        batch_op.alter_column(
            "value",
            existing_type=sa.Float(),
            type_=sa.Numeric(18, 8),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("emission_factors") as batch_op:
        batch_op.alter_column(
            "value",
            existing_type=sa.Numeric(18, 8),
            type_=sa.Float(),
            existing_nullable=False,
        )
