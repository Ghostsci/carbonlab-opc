"""Add anomaly alerts table (P4-9). Revises: 010"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table("anomaly_alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("enterprise_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("enterprises.id", ondelete="CASCADE"), nullable=False),
        sa.Column("emission_source_name", sa.String(200), nullable=False),
        sa.Column("scope", sa.String(10), nullable=False),
        sa.Column("period", sa.String(10), nullable=False),
        sa.Column("co2_tonnes", sa.Float, nullable=False),
        sa.Column("anomaly_type", sa.String(30), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("z_score", sa.Float, nullable=True),
        sa.Column("mom_change_pct", sa.Float, nullable=True),
        sa.Column("rule_triggered", sa.String(50), nullable=False, server_default="none"),
        sa.Column("explanation", sa.Text, nullable=False),
        sa.Column("recommendations", sa.Text, nullable=True),
        sa.Column("is_resolved", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("resolved_by", sa.String(100), nullable=True),
        sa.Column("resolved_at", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

def downgrade() -> None:
    op.drop_table("anomaly_alerts")
