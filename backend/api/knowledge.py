"""Read-only ontology contract and tenant-scoped retrieval audit endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.ai.ontology import public_ontology_payload
from backend.auth.dependencies import get_current_user
from backend.database import get_db
from backend.models.knowledge import RetrievalRun
from backend.models.user import User


router = APIRouter(prefix="/knowledge", tags=["governed-knowledge"])


def _context(user: User) -> tuple[uuid.UUID, uuid.UUID]:
    if not user.tenant_id or not user.enterprise_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前用户未绑定租户或企业")
    return user.tenant_id, user.enterprise_id


@router.get("/ontology")
def get_ontology(user: User = Depends(get_current_user)):
    _context(user)
    return public_ontology_payload()


@router.get("/retrievals/{run_id}")
def get_retrieval_trace(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, enterprise_id = _context(user)
    run = (
        db.query(RetrievalRun)
        .filter(
            RetrievalRun.id == run_id,
            RetrievalRun.tenant_id == tenant_id,
            RetrievalRun.enterprise_id == enterprise_id,
        )
        .first()
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="检索记录不存在")
    return {
        "retrieval_run_id": str(run.id),
        "role_id": run.role_id,
        "purpose": run.purpose,
        "query_text": run.query_text,
        "query_hash": run.query_hash,
        "filters": run.filters_payload,
        "corpora": run.corpus_types,
        "ontology_version": run.ontology_version,
        "embedding_model": run.embedding_model,
        "result_hash": run.result_hash,
        "status": run.status,
        "hits": [
            {
                "rank": hit.rank,
                "chunk_id": str(hit.chunk_id),
                "content_hash": hit.chunk.content_hash,
                "title": hit.chunk.document.title,
                "source_ref": hit.chunk.document.source_ref,
                "field_keys": hit.chunk.field_keys,
                "ontology_concepts": hit.chunk.ontology_concepts,
                "lexical_score": hit.lexical_score,
                "vector_score": hit.vector_score,
                "fused_score": hit.fused_score,
            }
            for hit in sorted(run.hits, key=lambda item: item.rank)
        ],
        "formal_write_allowed": False,
    }
