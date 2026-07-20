"""AI candidate extraction endpoint for the OPC minimum workflow.

The model may propose fields, document type, entities, and a summary. It does
not confirm data, perform authoritative calculations, or publish a passport.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.ai.doc_understanding import understand_document

router = APIRouter(prefix="/ai", tags=["ai-candidate-extraction"])


class UnderstandRequest(BaseModel):
    text: str


class UnderstandResponse(BaseModel):
    document_type: str
    fields: dict[str, str]
    confidence: float
    entities: list[str]
    summary: str


@router.post("/understand", response_model=UnderstandResponse)
def understand(req: UnderstandRequest):
    """Return model-generated candidates; never write them to the formal ledger."""

    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text is required")

    result = understand_document(req.text[:4000])
    return UnderstandResponse(
        document_type=result.document_type,
        fields=result.fields,
        confidence=result.confidence,
        entities=result.entities,
        summary=result.summary,
    )
