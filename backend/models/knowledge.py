"""Tenant-scoped knowledge, ontology tags, and auditable retrieval traces."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.config import RAG_SCHEMA_EMBEDDING_DIMENSIONS
from backend.database import Base
from backend.models.base import UUIDMixin


class KnowledgeDocument(Base, UUIDMixin):
    __tablename__ = "knowledge_documents"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("tenants.id"),
        nullable=True,
        index=True,
    )
    enterprise_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("enterprises.id"),
        nullable=True,
        index=True,
    )
    visibility: Mapped[str] = mapped_column(String(20), nullable=False)
    corpus_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_payload: Mapped[dict | None] = mapped_column("metadata_json", JSON)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    ontology_version: Mapped[str] = mapped_column(String(64), nullable=False)
    jurisdiction: Mapped[str | None] = mapped_column(String(32))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_status: Mapped[str] = mapped_column(String(20), nullable=False)
    security_label: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default=func.now(),
    )

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "corpus_type IN ('tenant_evidence', 'public_methodology', 'internal_sop')",
            name="ck_knowledge_documents_corpus",
        ),
        CheckConstraint(
            "visibility IN ('tenant', 'public', 'platform')",
            name="ck_knowledge_documents_visibility",
        ),
        CheckConstraint(
            "approval_status IN ('source', 'candidate', 'approved', 'withdrawn', 'superseded')",
            name="ck_knowledge_documents_approval",
        ),
        CheckConstraint(
            "length(content_hash) = 64 AND length(idempotency_key) = 64",
            name="ck_knowledge_documents_hashes",
        ),
    )


class KnowledgeChunk(Base, UUIDMixin):
    __tablename__ = "knowledge_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("tenants.id"),
        nullable=True,
        index=True,
    )
    enterprise_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("enterprises.id"),
        nullable=True,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_payload: Mapped[dict | None] = mapped_column("metadata_json", JSON)
    field_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    ontology_concepts: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    ontology_version: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(
        JSON().with_variant(Vector(RAG_SCHEMA_EMBEDDING_DIMENSIONS), "postgresql")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default=func.now(),
    )

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            "content_hash",
            name="uq_knowledge_chunk_document_index_hash",
        ),
        CheckConstraint("chunk_index >= 0", name="ck_knowledge_chunks_index"),
        CheckConstraint("length(content_hash) = 64", name="ck_knowledge_chunks_hash"),
    )


class RetrievalRun(Base, UUIDMixin):
    __tablename__ = "knowledge_retrieval_runs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("enterprises.id"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    role_id: Mapped[str] = mapped_column(String(16), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    filters_payload: Mapped[dict] = mapped_column("filters_json", JSON, nullable=False)
    corpus_types: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    ontology_version: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    result_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=func.now(),
    )

    hits: Mapped[list["RetrievalHit"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("top_k BETWEEN 1 AND 20", name="ck_knowledge_retrieval_top_k"),
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_knowledge_retrieval_status",
        ),
        CheckConstraint("length(query_hash) = 64", name="ck_knowledge_retrieval_query_hash"),
    )


class RetrievalHit(Base, UUIDMixin):
    __tablename__ = "knowledge_retrieval_hits"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("enterprises.id"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("knowledge_retrieval_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("knowledge_chunks.id"),
        nullable=False,
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    lexical_score: Mapped[float] = mapped_column(Float, nullable=False)
    vector_score: Mapped[float] = mapped_column(Float, nullable=False)
    fused_score: Mapped[float] = mapped_column(Float, nullable=False)
    selected: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=func.now(),
    )

    run: Mapped[RetrievalRun] = relationship(back_populates="hits")
    chunk: Mapped[KnowledgeChunk] = relationship()

    __table_args__ = (
        UniqueConstraint("run_id", "rank", name="uq_knowledge_retrieval_hit_rank"),
        UniqueConstraint("run_id", "chunk_id", name="uq_knowledge_retrieval_hit_chunk"),
        CheckConstraint("rank >= 1", name="ck_knowledge_retrieval_hit_rank"),
    )
