"""Scope uploaded-document deduplication to one enterprise.

Revision ID: 032
Revises: 031
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    constraints = {
        item.get("name")
        for item in inspector.get_unique_constraints("documents")
    }
    indexes = {item.get("name") for item in inspector.get_indexes("documents")}
    old_name = "uq_documents_tenant_content_hash"
    new_name = "uq_documents_tenant_enterprise_content_hash"

    # Some legacy SQLite fixtures were stamped at 025 without the historical
    # document constraint. Avoid a table rebuild there: unrelated triggers may
    # reference omitted legacy tables, while a unique index provides the same
    # enforcement for this migration's purpose.
    if bind.dialect.name == "sqlite" and old_name not in constraints:
        if new_name not in constraints | indexes:
            op.create_index(
                new_name,
                "documents",
                ["tenant_id", "enterprise_id", "content_hash"],
                unique=True,
            )
        return

    with op.batch_alter_table("documents") as batch:
        if old_name in constraints:
            batch.drop_constraint(
                old_name,
                type_="unique",
            )
        if new_name not in constraints | indexes:
            batch.create_unique_constraint(
                new_name,
                ["tenant_id", "enterprise_id", "content_hash"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    constraints = {
        item.get("name")
        for item in inspector.get_unique_constraints("documents")
    }
    indexes = {item.get("name") for item in inspector.get_indexes("documents")}
    old_name = "uq_documents_tenant_content_hash"
    new_name = "uq_documents_tenant_enterprise_content_hash"

    if bind.dialect.name == "sqlite" and new_name in indexes:
        op.drop_index(new_name, table_name="documents")
        if old_name not in constraints | indexes:
            op.create_index(
                old_name,
                "documents",
                ["tenant_id", "content_hash"],
                unique=True,
            )
        return

    with op.batch_alter_table("documents") as batch:
        if new_name in constraints:
            batch.drop_constraint(
                new_name,
                type_="unique",
            )
        if old_name not in constraints | indexes:
            batch.create_unique_constraint(
                old_name,
                ["tenant_id", "content_hash"],
            )
