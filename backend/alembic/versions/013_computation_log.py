"""computation log tables"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "computation_receipts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_data_hash", sa.String(64), nullable=False, index=True),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("step_count", sa.Integer(), nullable=False),
        sa.Column("decimal_precision", sa.Integer(), server_default="28"),
        sa.Column("total_co2_tonnes", sa.Numeric(28, 8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "computation_steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("receipt_id", sa.Uuid(), sa.ForeignKey("computation_receipts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("output_raw", sa.Numeric(28, 8), nullable=False),
        sa.Column("output_rounded", sa.Numeric(28, 8), nullable=False),
        sa.Column("rounding_rule", sa.String(50), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("computation_steps")
    op.drop_table("computation_receipts")
