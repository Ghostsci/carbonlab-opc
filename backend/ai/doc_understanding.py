"""LLM document understanding — fallback when OCR extraction fails.

When PaddleOCR can't parse a document or confidence is below threshold,
the LLM directly reads the raw text and extracts structured fields.
"""

import json
from dataclasses import dataclass, field

from backend.ai.llm_client import chat_complete


EXTRACTION_PROMPT = """你是一个碳核算文档处理专家。请从以下文档内容中提取碳核算相关的结构化字段。

文档内容:
---
{document_text}
---

请提取以下信息并以JSON格式返回:
1. document_type: 文档类型 (invoice/electricity_bill/production_report/verification_report/unknown)
2. fields: 提取到的字段键值对
3. confidence: 你对提取结果的置信度 (0.0-1.0)
4. entities: 识别到的组织、地点、能源类型等实体列表
5. summary: 文档内容的简短摘要 (50字以内)

只返回JSON，不要其他内容。"""


@dataclass
class DocumentUnderstanding:
    document_type: str
    fields: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0
    entities: list[str] = field(default_factory=list)
    summary: str = ""
    raw_response: str = ""


def understand_document(text: str) -> DocumentUnderstanding:
    """Use LLM to understand document content when OCR fails or is low confidence."""
    if not text.strip():
        return DocumentUnderstanding(
            document_type="unknown",
            summary="空文档，无法解析",
        )

    prompt = EXTRACTION_PROMPT.format(document_text=text[:4000])

    try:
        raw = chat_complete([
            {"role": "system", "content": "你是 CarbonTrace 碳迹云平台的文档解析引擎。你精准地从文档中提取碳核算数据，只返回JSON，不要解释。"},
            {"role": "user", "content": prompt},
        ], temperature=0.1)

        result = _parse_json_response(raw)

        return DocumentUnderstanding(
            document_type=result.get("document_type", "unknown"),
            fields=result.get("fields", {}),
            confidence=result.get("confidence", 0.0),
            entities=result.get("entities", []),
            summary=result.get("summary", ""),
            raw_response=raw,
        )
    except Exception:
        return DocumentUnderstanding(
            document_type="unknown",
            confidence=0.0,
            summary="LLM 解析失败",
        )


def _parse_json_response(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:]) if lines[0].startswith("```") else raw
        if raw.endswith("```"):
            raw = raw[:-3].strip()
    return json.loads(raw)
