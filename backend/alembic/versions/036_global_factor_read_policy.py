"""Allow tenant runtimes to read governed global emission factors.

Revision ID: 036
Revises: 035
Create Date: 2026-08-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "036"
down_revision: Union[str, None] = "035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_emission_factors "
        "ON emission_factors"
    )
    op.execute(
        "DROP POLICY IF EXISTS tenant_read_emission_factors "
        "ON emission_factors"
    )
    op.execute(
        "DROP POLICY IF EXISTS tenant_write_emission_factors "
        "ON emission_factors"
    )
    op.execute(
        "CREATE POLICY tenant_read_emission_factors ON emission_factors "
        "FOR SELECT TO tenant_user "
        "USING (tenant_id IS NULL OR "
        "tenant_id::text = current_setting('app.current_tenant_id', true))"
    )
    op.execute(
        "CREATE POLICY tenant_write_emission_factors ON emission_factors "
        "FOR ALL TO tenant_user "
        "USING (tenant_id::text = current_setting('app.current_tenant_id', true)) "
        "WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS tenant_read_emission_factors "
        "ON emission_factors"
    )
    op.execute(
        "DROP POLICY IF EXISTS tenant_write_emission_factors "
        "ON emission_factors"
    )
    op.execute(
        "CREATE POLICY tenant_isolation_emission_factors ON emission_factors "
        "FOR ALL TO tenant_user "
        "USING (tenant_id::text = current_setting('app.current_tenant_id', true)) "
        "WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))"
    )
