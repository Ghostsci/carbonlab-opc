"""Public AI package exports without eager service or database imports."""

from __future__ import annotations

from importlib import import_module


_EXPORTS = {
    "OCRService": ("backend.ai.ocr", "OCRService"),
    "OCRResult": ("backend.ai.ocr", "OCRResult"),
    "DocumentType": ("backend.ai.ocr", "DocumentType"),
    "DocumentReadError": ("backend.ai.ocr", "DocumentReadError"),
    "DocumentReaderUnavailable": (
        "backend.ai.ocr",
        "DocumentReaderUnavailable",
    ),
    "extract_fields": ("backend.ai.ocr", "extract_fields"),
    "InvoiceExtractor": ("backend.ai.extractors", "InvoiceExtractor"),
    "ElectricityBillExtractor": (
        "backend.ai.extractors",
        "ElectricityBillExtractor",
    ),
    "ProductionReportExtractor": (
        "backend.ai.extractors",
        "ProductionReportExtractor",
    ),
    "RAGService": ("backend.ai.rag", "RAGService"),
    "RAGResponse": ("backend.ai.rag", "RAGResponse"),
    "get_rag_service": ("backend.ai.rag", "get_rag_service"),
    "understand_document": (
        "backend.ai.doc_understanding",
        "understand_document",
    ),
    "DocumentUnderstanding": (
        "backend.ai.doc_understanding",
        "DocumentUnderstanding",
    ),
    "get_llm_client": ("backend.ai.llm_client", "get_llm_client"),
    "chat_complete": ("backend.ai.llm_client", "chat_complete"),
    "generate_embedding": ("backend.ai.llm_client", "generate_embedding"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
