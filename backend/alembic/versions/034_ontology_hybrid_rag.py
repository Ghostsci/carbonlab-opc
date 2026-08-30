"""Upgrade the dormant knowledge tables into a governed ontology/RAG layer.

Revision ID: 034
Revises: 033
Create Date: 2026-08-27
"""

from __future__ import annotations

import hashlib
from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa


revision: str = "034"
down_revision: Union[str, None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ONTOLOGY_VERSION = "carbon-passport-ontology-v0.1.0"
EMBEDDING_DIMENSIONS = 1536


def _json_empty_list_default(dialect: str):
    return sa.text("'[]'::json") if dialect == "postgresql" else sa.text("'[]'")


def _backfill_document_keys() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, source_type, source_ref, content_hash, tenant_id "
            "FROM knowledge_documents"
        )
    ).mappings()
    for row in rows:
        raw = "|".join(
            str(row.get(key) or "")
            for key in ("id", "source_type", "source_ref", "content_hash", "tenant_id")
        )
        key = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        source_type = str(row.get("source_type") or "")
        if source_type == "rule_record":
            corpus_type = "public_methodology"
            approval_status = "approved"
            security_label = "public"
        elif row.get("tenant_id") is not None:
            corpus_type = "tenant_evidence"
            approval_status = "source"
            security_label = "tenant_confidential"
        else:
            corpus_type = "internal_sop"
            approval_status = "candidate"
            security_label = "platform_internal"
        bind.execute(
            sa.text(
                "UPDATE knowledge_documents SET idempotency_key=:key, "
                "corpus_type=:corpus_type, approval_status=:approval_status, "
                "security_label=:security_label, ontology_version=:ontology_version "
                "WHERE id=:id"
            ),
            {
                "id": row["id"],
                "key": key,
                "corpus_type": corpus_type,
                "approval_status": approval_status,
                "security_label": security_label,
                "ontology_version": ONTOLOGY_VERSION,
            },
        )


def _enable_postgres_tenant_policies() -> None:
    for table in (
        "knowledge_documents",
        "knowledge_chunks",
        "knowledge_retrieval_runs",
        "knowledge_retrieval_hits",
    ):
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}"))
        op.execute(
            sa.text(
                f"CREATE POLICY tenant_isolation_{table} ON {table} "
                "USING (tenant_id::text = current_setting('app.current_tenant_id', true)) "
                "WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))"
            )
        )


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    document_enterprise_column = (
        sa.Column("enterprise_id", sa.Uuid(), sa.ForeignKey("enterprises.id"), nullable=True)
        if dialect == "postgresql"
        else sa.Column("enterprise_id", sa.Uuid(), nullable=True)
    )
    op.add_column("knowledge_documents", document_enterprise_column)
    op.add_column("knowledge_documents", sa.Column("corpus_type", sa.String(32), nullable=True))
    op.add_column("knowledge_documents", sa.Column("idempotency_key", sa.String(64), nullable=True))
    op.add_column("knowledge_documents", sa.Column("ontology_version", sa.String(64), nullable=True))
    op.add_column("knowledge_documents", sa.Column("jurisdiction", sa.String(32), nullable=True))
    op.add_column("knowledge_documents", sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("knowledge_documents", sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True))
    op.add_column("knowledge_documents", sa.Column("approval_status", sa.String(20), nullable=True))
    op.add_column("knowledge_documents", sa.Column("security_label", sa.String(32), nullable=True))
    _backfill_document_keys()

    with op.batch_alter_table("knowledge_documents") as batch:
        batch.alter_column("corpus_type", existing_type=sa.String(32), nullable=False)
        batch.alter_column("idempotency_key", existing_type=sa.String(64), nullable=False)
        batch.alter_column("ontology_version", existing_type=sa.String(64), nullable=False)
        batch.alter_column("approval_status", existing_type=sa.String(20), nullable=False)
        batch.alter_column("security_label", existing_type=sa.String(32), nullable=False)
        batch.create_unique_constraint(
            "uq_knowledge_documents_idempotency_key",
            ["idempotency_key"],
        )
        batch.create_check_constraint(
            "ck_knowledge_documents_corpus",
            "corpus_type IN ('tenant_evidence', 'public_methodology', 'internal_sop')",
        )
        batch.create_check_constraint(
            "ck_knowledge_documents_visibility",
            "visibility IN ('tenant', 'public', 'platform')",
        )
        batch.create_check_constraint(
            "ck_knowledge_documents_approval",
            "approval_status IN ('source', 'candidate', 'approved', 'withdrawn', 'superseded')",
        )
        batch.create_check_constraint(
            "ck_knowledge_documents_hashes",
            "length(content_hash) = 64 AND length(idempotency_key) = 64",
        )
    op.create_index("ix_knowledge_documents_enterprise_id", "knowledge_documents", ["enterprise_id"])
    op.create_index("ix_knowledge_documents_corpus_type", "knowledge_documents", ["corpus_type"])

    empty_list = _json_empty_list_default(dialect)
    chunk_enterprise_column = (
        sa.Column("enterprise_id", sa.Uuid(), sa.ForeignKey("enterprises.id"), nullable=True)
        if dialect == "postgresql"
        else sa.Column("enterprise_id", sa.Uuid(), nullable=True)
    )
    op.add_column("knowledge_chunks", chunk_enterprise_column)
    op.add_column(
        "knowledge_chunks",
        sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("field_keys", sa.JSON(), nullable=False, server_default=empty_list),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("ontology_concepts", sa.JSON(), nullable=False, server_default=empty_list),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column(
            "ontology_version",
            sa.String(64),
            nullable=False,
            server_default=ONTOLOGY_VERSION,
        ),
    )
    op.add_column("knowledge_chunks", sa.Column("embedding_model", sa.String(128), nullable=True))
    op.add_column("knowledge_chunks", sa.Column("embedding_dimensions", sa.Integer(), nullable=True))
    embedding_type = Vector(EMBEDDING_DIMENSIONS) if dialect == "postgresql" else sa.JSON()
    op.add_column("knowledge_chunks", sa.Column("embedding", embedding_type, nullable=True))
    op.execute(sa.text("UPDATE knowledge_chunks SET search_text=content WHERE search_text=''"))
    with op.batch_alter_table("knowledge_chunks") as batch:
        batch.create_unique_constraint(
            "uq_knowledge_chunk_document_index_hash",
            ["document_id", "chunk_index", "content_hash"],
        )
        batch.create_check_constraint("ck_knowledge_chunks_index", "chunk_index >= 0")
        batch.create_check_constraint("ck_knowledge_chunks_hash", "length(content_hash) = 64")
    op.create_index("ix_knowledge_chunks_enterprise_id", "knowledge_chunks", ["enterprise_id"])

    op.create_table(
        "knowledge_retrieval_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("enterprise_id", sa.Uuid(), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("role_id", sa.String(16), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("filters_json", sa.JSON(), nullable=False),
        sa.Column("corpus_types", sa.JSON(), nullable=False),
        sa.Column("ontology_version", sa.String(64), nullable=False),
        sa.Column("embedding_model", sa.String(128), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("top_k BETWEEN 1 AND 20", name="ck_knowledge_retrieval_top_k"),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_knowledge_retrieval_status"),
        sa.CheckConstraint("length(query_hash) = 64", name="ck_knowledge_retrieval_query_hash"),
    )
    op.create_index("ix_knowledge_retrieval_runs_tenant_id", "knowledge_retrieval_runs", ["tenant_id"])
    op.create_index("ix_knowledge_retrieval_runs_enterprise_id", "knowledge_retrieval_runs", ["enterprise_id"])

    op.create_table(
        "knowledge_retrieval_hits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("enterprise_id", sa.Uuid(), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("knowledge_retrieval_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), sa.ForeignKey("knowledge_chunks.id"), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("lexical_score", sa.Float(), nullable=False),
        sa.Column("vector_score", sa.Float(), nullable=False),
        sa.Column("fused_score", sa.Float(), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "rank", name="uq_knowledge_retrieval_hit_rank"),
        sa.UniqueConstraint("run_id", "chunk_id", name="uq_knowledge_retrieval_hit_chunk"),
        sa.CheckConstraint("rank >= 1", name="ck_knowledge_retrieval_hit_rank"),
    )
    op.create_index("ix_knowledge_retrieval_hits_tenant_id", "knowledge_retrieval_hits", ["tenant_id"])
    op.create_index("ix_knowledge_retrieval_hits_enterprise_id", "knowledge_retrieval_hits", ["enterprise_id"])
    op.create_index("ix_knowledge_retrieval_hits_run_id", "knowledge_retrieval_hits", ["run_id"])
    op.create_index("ix_knowledge_retrieval_hits_chunk_id", "knowledge_retrieval_hits", ["chunk_id"])

    if dialect == "postgresql":
        op.execute(
            sa.text(
                "CREATE INDEX ix_knowledge_chunks_search_tsv ON knowledge_chunks "
                "USING gin (to_tsvector('simple', search_text))"
            )
        )
        # Login and refresh happen before a request has a tenant context. Keep
        # the web role behind RLS and expose only exact-key auth lookups through
        # tightly scoped SECURITY DEFINER functions.
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION public.zcy_auth_user_by_email(login_email text)
                RETURNS SETOF public.users
                LANGUAGE sql STABLE SECURITY DEFINER
                SET search_path = pg_catalog, public
                AS $$
                    SELECT users.* FROM public.users
                    WHERE lower(users.email) = lower(login_email)
                    LIMIT 1
                $$
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION public.zcy_auth_user_by_id(login_user_id uuid)
                RETURNS SETOF public.users
                LANGUAGE sql STABLE SECURITY DEFINER
                SET search_path = pg_catalog, public
                AS $$
                    SELECT users.* FROM public.users
                    WHERE users.id = login_user_id
                    LIMIT 1
                $$
                """
            )
        )
        op.execute(sa.text("REVOKE ALL ON FUNCTION public.zcy_auth_user_by_email(text) FROM PUBLIC"))
        op.execute(sa.text("REVOKE ALL ON FUNCTION public.zcy_auth_user_by_id(uuid) FROM PUBLIC"))
        _enable_postgres_tenant_policies()


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(sa.text("DROP FUNCTION IF EXISTS public.zcy_auth_user_by_id(uuid)"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS public.zcy_auth_user_by_email(text)"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_knowledge_chunks_search_tsv"))
    op.drop_table("knowledge_retrieval_hits")
    op.drop_table("knowledge_retrieval_runs")
    op.drop_index("ix_knowledge_chunks_enterprise_id", table_name="knowledge_chunks")
    with op.batch_alter_table("knowledge_chunks") as batch:
        for column in (
            "embedding",
            "embedding_dimensions",
            "embedding_model",
            "ontology_version",
            "ontology_concepts",
            "field_keys",
            "search_text",
            "enterprise_id",
        ):
            batch.drop_column(column)
    op.drop_index("ix_knowledge_documents_corpus_type", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_enterprise_id", table_name="knowledge_documents")
    with op.batch_alter_table("knowledge_documents") as batch:
        for column in (
            "security_label",
            "approval_status",
            "valid_to",
            "valid_from",
            "jurisdiction",
            "ontology_version",
            "idempotency_key",
            "corpus_type",
            "enterprise_id",
        ):
            batch.drop_column(column)
