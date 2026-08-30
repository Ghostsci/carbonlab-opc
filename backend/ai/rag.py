"""Auditable hybrid retrieval for evidence and methodology candidates.

This module deliberately does not generate formal facts, select a methodology,
or calculate emissions.  It returns traceable candidate evidence to A-03 or
H-02 and records the exact retrieval inputs and hits.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
import re
from typing import Any, Iterable
import uuid

from pydantic import BaseModel, Field
from pgvector.sqlalchemy import Vector
from sqlalchemy import and_, cast, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session

from backend.ai.embeddings import (
    embed_text,
    embedding_model_name,
    lexical_document,
    lexical_tokens,
)
from backend.ai.ontology import (
    canonical_field,
    concepts_for_field,
    ontology_version,
    role_allowed_corpora,
)
from backend.config import RAG_SCHEMA_EMBEDDING_DIMENSIONS, settings
from backend.models.document import DocumentStore
from backend.models.knowledge import (
    KnowledgeChunk,
    KnowledgeDocument,
    RetrievalHit,
    RetrievalRun,
)
from backend.models.rule_record import RuleRecord
from backend.services.candidate_confirmation import canonical_sha256


class RAGBoundaryError(ValueError):
    """Raised when a caller tries to cross a corpus or role boundary."""


class RAGHit(BaseModel):
    rank: int
    chunk_id: str
    knowledge_document_id: str
    corpus_type: str
    source_type: str
    source_ref: str | None
    title: str
    excerpt: str
    content_hash: str
    field_keys: list[str]
    ontology_concepts: list[str]
    jurisdiction: str | None
    valid_from: str | None
    valid_to: str | None
    lexical_score: str
    vector_score: str
    fused_score: str


class RAGResponse(BaseModel):
    retrieval_run_id: str
    role_id: str
    purpose: str
    ontology_version: str
    embedding_model: str
    corpora: list[str]
    hits: list[RAGHit]
    formal_write_allowed: bool = False
    human_gate_required: bool = True
    warning: str = "检索结果仅为候选证据，不是正式事实、方法批准或核算结果。"


SOP_DOCUMENTS: tuple[dict[str, str], ...] = (
    {
        "source_ref": "sop:a03-field-evidence-v1",
        "title": "A-03 字段级证据审核 SOP",
        "body": (
            "A-03 必须验证证据片段是否支持当前字段。文件中出现相同数字，"
            "但没有绑定到该字段名称时，不得判定为字段证据通过。"
        ),
    },
    {
        "source_ref": "sop:h02-methodology-v1",
        "title": "H-02 方法学审核 SOP",
        "body": (
            "H-02 只能从已批准、在报告期内有效、发布者和文号完整的规则记录中选择方法。"
            "RAG 只能排序候选，不能自动批准或替代人工决定。"
        ),
    },
)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _idempotency_key(*parts: object) -> str:
    return _sha256_text("|".join(str(part or "") for part in parts))


def _safe_json_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {str(key): _safe_json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_safe_json_value(item) for item in value]
    return str(value)


def _redact_query(text: str) -> str:
    redacted = re.sub(r"(?i)\b(sk|ds|mm)-[a-z0-9_-]{8,}\b", "[REDACTED_CREDENTIAL]", text)
    redacted = re.sub(
        r"(?i)(access_token|api_key|apikey|authorization|bearer|token|password)=([^&\s]+)",
        r"\1=[REDACTED]",
        redacted,
    )
    redacted = re.sub(r"(?i)\bbearer\s+[a-z0-9._~+/-]{8,}", "Bearer [REDACTED]", redacted)
    return redacted[:1000]


def _chunks(text: str, *, size: int = 700, overlap: int = 100) -> Iterable[str]:
    cleaned = re.sub(r"\r\n?", "\n", text).strip()
    if not cleaned:
        return []
    if len(cleaned) <= size:
        return [cleaned]
    result: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + size)
        result.append(cleaned[start:end].strip())
        if end == len(cleaned):
            break
        start = max(start + 1, end - overlap)
    return result


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
    right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


def _lexical_score(query: str, content: str) -> float:
    query_tokens = set(lexical_tokens(query))
    content_tokens = set(lexical_tokens(content))
    if not query_tokens or not content_tokens:
        return 0.0
    overlap = len(query_tokens & content_tokens)
    return overlap / math.sqrt(len(query_tokens) * len(content_tokens))


def _excerpt(text: str, *, limit: int = 280) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact if len(compact) <= limit else f"{compact[:limit].rstrip()}…"


class RAGService:
    def _create_document(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        enterprise_id: uuid.UUID | None,
        corpus_type: str,
        visibility: str,
        source_type: str,
        source_ref: str,
        title: str,
        body_text: str,
        content_hash: str,
        approval_status: str,
        security_label: str,
        metadata: dict[str, Any],
        jurisdiction: str | None = None,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        field_chunks: list[tuple[str, str]] | None = None,
    ) -> KnowledgeDocument:
        key = _idempotency_key(
            tenant_id,
            enterprise_id,
            corpus_type,
            source_type,
            source_ref,
            content_hash,
            ontology_version(),
        )
        existing = db.query(KnowledgeDocument).filter(KnowledgeDocument.idempotency_key == key).first()
        if existing is not None:
            return existing
        try:
            # A savepoint makes concurrent indexing idempotent. If another
            # worker wins the unique-key race, only this savepoint is rolled
            # back and the caller can reuse the committed document.
            with db.begin_nested():
                document = KnowledgeDocument(
                    tenant_id=tenant_id,
                    enterprise_id=enterprise_id,
                    visibility=visibility,
                    corpus_type=corpus_type,
                    source_type=source_type,
                    source_ref=source_ref,
                    title=title,
                    content_hash=content_hash,
                    idempotency_key=key,
                    version=1,
                    body_text=body_text,
                    metadata_payload=_safe_json_value(metadata),
                    status="active",
                    ontology_version=ontology_version(),
                    jurisdiction=jurisdiction,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    approval_status=approval_status,
                    security_label=security_label,
                )
                db.add(document)
                db.flush()

                prepared: list[tuple[str, list[str], list[str]]] = []
                for field_key, field_text in field_chunks or []:
                    canonical = canonical_field(field_key) or field_key
                    prepared.append((field_text, [canonical], concepts_for_field(canonical)))
                prepared.extend(
                    (chunk, [], ["EvidenceChunk"])
                    for chunk in _chunks(body_text)
                    if chunk
                )
                seen: set[str] = set()
                for index, (content, field_keys, concepts) in enumerate(prepared):
                    chunk_hash = _sha256_text(content)
                    if chunk_hash in seen:
                        continue
                    seen.add(chunk_hash)
                    vector = embed_text(content)
                    db.add(
                        KnowledgeChunk(
                            document_id=document.id,
                            tenant_id=tenant_id,
                            enterprise_id=enterprise_id,
                            chunk_index=index,
                            content=content,
                            search_text=lexical_document(content),
                            content_hash=chunk_hash,
                            token_estimate=max(1, len(content) // 4),
                            metadata_payload={"source_ref": source_ref, "title": title},
                            field_keys=field_keys,
                            ontology_concepts=concepts,
                            ontology_version=ontology_version(),
                            embedding_model=embedding_model_name(),
                            embedding_dimensions=len(vector),
                            embedding=vector,
                        )
                    )
                db.flush()
        except IntegrityError:
            existing = (
                db.query(KnowledgeDocument)
                .filter(KnowledgeDocument.idempotency_key == key)
                .first()
            )
            if existing is None:
                raise
            return existing
        return document

    def index_document(self, db: Session, document: DocumentStore) -> KnowledgeDocument:
        snapshot = document.ocr_result or {}
        fields = snapshot.get("fields") if isinstance(snapshot.get("fields"), dict) else {}
        raw_text = snapshot.get("raw_text") if isinstance(snapshot.get("raw_text"), str) else ""
        field_lines: list[tuple[str, str]] = []
        for key, value in fields.items():
            if value in (None, ""):
                continue
            canonical = canonical_field(str(key)) or str(key)
            field_lines.append(
                (
                    canonical,
                    f"源文件：{document.filename}\n文档类型：{document.doc_type}\n"
                    f"字段：{canonical}\n识别值：{value}",
                )
            )
        body = "\n".join(text for _key, text in field_lines)
        if raw_text:
            body = f"{body}\n\n原文识别快照：\n{raw_text[:settings.rag_max_source_chars]}".strip()
        if not body:
            body = f"源文件：{document.filename}\n文档类型：{document.doc_type}\n当前没有可检索文本。"
        return self._create_document(
            db,
            tenant_id=document.tenant_id,
            enterprise_id=document.enterprise_id,
            corpus_type="tenant_evidence",
            visibility="tenant",
            source_type="document_store",
            source_ref=str(document.id),
            title=document.filename,
            body_text=body,
            content_hash=document.content_hash,
            approval_status="source",
            security_label="tenant_confidential",
            metadata={
                "document_id": str(document.id),
                "doc_type": document.doc_type,
                "mime_type": document.mime_type,
                "ocr_status": document.ocr_status,
            },
            field_chunks=field_lines,
        )

    def index_rule(self, db: Session, rule: RuleRecord) -> KnowledgeDocument:
        body = "\n".join(
            (
                f"规则标题：{rule.title}",
                f"发布者：{rule.publisher}",
                f"文号：{rule.document_number}",
                f"法域：{rule.jurisdiction}",
                f"版本年份：{rule.vintage}",
                f"有效期：{rule.valid_from.isoformat()} 至 {rule.valid_to.isoformat() if rule.valid_to else '持续有效'}",
                f"权威来源：{rule.source_url}",
                f"来源内容哈希：{rule.content_hash}",
                "用途：供 H-02 作为方法规则候选；必须人工确认后才能交给 R-01。",
            )
        )
        return self._create_document(
            db,
            tenant_id=rule.tenant_id,
            enterprise_id=None,
            corpus_type="public_methodology",
            visibility="tenant",
            source_type="rule_record",
            source_ref=str(rule.id),
            title=rule.title,
            body_text=body,
            content_hash=rule.content_hash,
            approval_status=rule.status,
            security_label="public",
            metadata={
                "rule_kind": rule.rule_kind,
                "publisher": rule.publisher,
                "document_number": rule.document_number,
                "vintage": rule.vintage,
                "source_url": rule.source_url,
            },
            jurisdiction=rule.jurisdiction,
            valid_from=rule.valid_from,
            valid_to=rule.valid_to,
            field_chunks=[("methodology_ref", body)],
        )

    def ensure_internal_sop(self, db: Session, tenant_id: uuid.UUID) -> None:
        for item in SOP_DOCUMENTS:
            body = item["body"]
            self._create_document(
                db,
                tenant_id=tenant_id,
                enterprise_id=None,
                corpus_type="internal_sop",
                visibility="platform",
                source_type="workforce_sop",
                source_ref=item["source_ref"],
                title=item["title"],
                body_text=body,
                content_hash=_sha256_text(body),
                approval_status="approved",
                security_label="platform_internal",
                metadata={"contract": "carbon-passport-workforce-v1.0"},
            )

    def ensure_rules_indexed(self, db: Session, tenant_id: uuid.UUID) -> None:
        rules = (
            db.query(RuleRecord)
            .filter(RuleRecord.tenant_id == tenant_id, RuleRecord.status == "approved")
            .all()
        )
        for rule in rules:
            self.index_rule(db, rule)

    def _base_query(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        enterprise_id: uuid.UUID,
        corpora: set[str],
        valid_at: datetime | None,
        jurisdiction: str | None,
        source_ref: str | None,
    ) -> Query:
        query = (
            db.query(KnowledgeChunk)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .filter(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeChunk.tenant_id == tenant_id,
                KnowledgeDocument.status == "active",
                KnowledgeDocument.corpus_type.in_(corpora),
                KnowledgeDocument.approval_status.in_(("source", "approved")),
                or_(
                    and_(
                        KnowledgeDocument.corpus_type == "tenant_evidence",
                        KnowledgeDocument.enterprise_id == enterprise_id,
                        KnowledgeChunk.enterprise_id == enterprise_id,
                    ),
                    and_(
                        KnowledgeDocument.corpus_type.in_(("public_methodology", "internal_sop")),
                        KnowledgeDocument.enterprise_id.is_(None),
                        KnowledgeChunk.enterprise_id.is_(None),
                    ),
                ),
            )
        )
        if valid_at is not None:
            query = query.filter(
                or_(KnowledgeDocument.valid_from.is_(None), KnowledgeDocument.valid_from <= valid_at),
                or_(KnowledgeDocument.valid_to.is_(None), KnowledgeDocument.valid_to >= valid_at),
            )
        if jurisdiction:
            query = query.filter(
                or_(KnowledgeDocument.jurisdiction.is_(None), KnowledgeDocument.jurisdiction == jurisdiction)
            )
        if source_ref:
            query = query.filter(KnowledgeDocument.source_ref == source_ref)
        if "public_methodology" in corpora:
            query = query.filter(
                or_(
                    KnowledgeDocument.corpus_type != "public_methodology",
                    KnowledgeDocument.approval_status == "approved",
                )
            )
        return query

    def search(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        enterprise_id: uuid.UUID,
        actor_id: uuid.UUID | str,
        role_id: str,
        purpose: str,
        query_text: str,
        corpus_types: Iterable[str],
        top_k: int = 5,
        valid_at: datetime | None = None,
        jurisdiction: str | None = None,
        source_ref: str | None = None,
        field_key: str | None = None,
    ) -> RAGResponse:
        query_text = query_text.strip()
        if not query_text:
            raise RAGBoundaryError("RAG query cannot be empty")
        if not 1 <= top_k <= 20:
            raise RAGBoundaryError("RAG top_k must be between 1 and 20")
        corpora = set(corpus_types)
        allowed = role_allowed_corpora(role_id)
        if not corpora or not corpora <= allowed:
            raise RAGBoundaryError(
                f"role {role_id} cannot access requested corpora: {sorted(corpora - allowed)}"
            )
        if "internal_sop" in corpora:
            self.ensure_internal_sop(db, tenant_id)
        if "public_methodology" in corpora:
            self.ensure_rules_indexed(db, tenant_id)

        raw_query_hash = _sha256_text(query_text)
        vector = embed_text(query_text)
        run = RetrievalRun(
            tenant_id=tenant_id,
            enterprise_id=enterprise_id,
            actor_id=str(actor_id),
            role_id=role_id,
            purpose=purpose,
            query_text=_redact_query(query_text),
            query_hash=raw_query_hash,
            filters_payload={
                "valid_at": valid_at.isoformat() if valid_at else None,
                "jurisdiction": jurisdiction,
                "source_ref": source_ref,
                "field_key": field_key,
                "tenant_scope_before_ranking": True,
            },
            corpus_types=sorted(corpora),
            ontology_version=ontology_version(),
            embedding_model=embedding_model_name(),
            top_k=top_k,
            status="running",
        )
        db.add(run)
        db.flush()

        base = self._base_query(
            db,
            tenant_id=tenant_id,
            enterprise_id=enterprise_id,
            corpora=corpora,
            valid_at=valid_at,
            jurisdiction=jurisdiction,
            source_ref=source_ref,
        )
        limit = max(
            top_k,
            min(settings.rag_candidate_limit, max(top_k * 8, 50)),
        )
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            vector_rows = (
                base.filter(KnowledgeChunk.embedding.is_not(None))
                .order_by(
                    KnowledgeChunk.embedding.op("<=>")(
                        cast(vector, Vector(RAG_SCHEMA_EMBEDDING_DIMENSIONS))
                    )
                )
                .limit(limit)
                .all()
            )
            tokens = lexical_tokens(query_text)[:32]
            if tokens:
                tsquery = " ".join(tokens)
                lexical_rows = (
                    base.order_by(
                        func.ts_rank_cd(
                            func.to_tsvector("simple", KnowledgeChunk.search_text),
                            func.plainto_tsquery("simple", tsquery),
                        ).desc()
                    )
                    .limit(limit)
                    .all()
                )
            else:
                lexical_rows = []
            rows = list({row.id: row for row in [*vector_rows, *lexical_rows]}.values())
        else:
            rows = base.limit(limit).all()

        canonical_requested = canonical_field(field_key) if field_key else None
        ranked: list[tuple[KnowledgeChunk, float, float, float]] = []
        for chunk in rows:
            if canonical_requested and canonical_requested not in (chunk.field_keys or []):
                continue
            lexical_score = _lexical_score(query_text, chunk.content)
            stored_embedding = [] if chunk.embedding is None else list(chunk.embedding)
            vector_score = max(0.0, _cosine(vector, stored_embedding))
            field_bonus = 0.12 if canonical_requested and canonical_requested in (chunk.field_keys or []) else 0.0
            fused = min(1.0, lexical_score * 0.58 + vector_score * 0.42 + field_bonus)
            ranked.append((chunk, lexical_score, vector_score, fused))
        ranked.sort(key=lambda item: (-item[3], -item[1], str(item[0].id)))
        selected = ranked[:top_k]

        hits: list[RAGHit] = []
        result_identity: list[dict[str, Any]] = []
        for rank, (chunk, lexical_score, vector_score, fused_score) in enumerate(selected, start=1):
            document = chunk.document
            hit = RAGHit(
                rank=rank,
                chunk_id=str(chunk.id),
                knowledge_document_id=str(document.id),
                corpus_type=document.corpus_type,
                source_type=document.source_type,
                source_ref=document.source_ref,
                title=document.title,
                excerpt=_excerpt(chunk.content),
                content_hash=chunk.content_hash,
                field_keys=list(chunk.field_keys or []),
                ontology_concepts=list(chunk.ontology_concepts or []),
                jurisdiction=document.jurisdiction,
                valid_from=document.valid_from.isoformat() if document.valid_from else None,
                valid_to=document.valid_to.isoformat() if document.valid_to else None,
                lexical_score=f"{lexical_score:.8f}",
                vector_score=f"{vector_score:.8f}",
                fused_score=f"{fused_score:.8f}",
            )
            hits.append(hit)
            result_identity.append(
                {
                    "rank": rank,
                    "chunk_id": str(chunk.id),
                    "content_hash": chunk.content_hash,
                    "fused_score": hit.fused_score,
                }
            )
            db.add(
                RetrievalHit(
                    tenant_id=tenant_id,
                    enterprise_id=enterprise_id,
                    run_id=run.id,
                    chunk_id=chunk.id,
                    rank=rank,
                    lexical_score=lexical_score,
                    vector_score=vector_score,
                    fused_score=fused_score,
                    selected=True,
                )
            )
        run.result_hash = canonical_sha256(result_identity)
        run.status = "completed"
        db.flush()
        return RAGResponse(
            retrieval_run_id=str(run.id),
            role_id=role_id,
            purpose=purpose,
            ontology_version=ontology_version(),
            embedding_model=embedding_model_name(),
            corpora=sorted(corpora),
            hits=hits,
        )


_rag_service: RAGService | None = None


def get_rag_service() -> RAGService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service
