"""Replaceable embedding boundary with an offline deterministic default."""

from __future__ import annotations

import hashlib
import math
import re

from backend.ai.llm_client import generate_embedding
from backend.config import RAG_SCHEMA_EMBEDDING_DIMENSIONS, settings


LOCAL_HASH_MODEL = "local-feature-hash-v1"


def lexical_tokens(text: str) -> list[str]:
    normalized = text.lower()
    tokens = re.findall(r"[a-z0-9]+(?:[._/-][a-z0-9]+)*", normalized)
    for sequence in re.findall(r"[\u4e00-\u9fff]+", normalized):
        tokens.extend(sequence)
        tokens.extend(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return [token for token in tokens if token]


def lexical_document(text: str) -> str:
    return " ".join(lexical_tokens(text))


def _local_feature_hash(text: str, dimensions: int) -> list[float]:
    if dimensions < 64:
        raise ValueError("RAG embedding dimensions must be at least 64")
    vector = [0.0] * dimensions
    tokens = lexical_tokens(text)
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:8], "big") % dimensions
        sign = -1.0 if digest[8] & 1 else 1.0
        vector[index] += sign
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude:
        vector = [value / magnitude for value in vector]
    return vector


def embedding_model_name() -> str:
    if settings.rag_embedding_provider == "local_hash":
        return f"{LOCAL_HASH_MODEL}:{settings.rag_embedding_dimensions}"
    if settings.rag_embedding_provider == "llm":
        return settings.embedding_model
    raise ValueError("RAG_EMBEDDING_PROVIDER must be 'local_hash' or 'llm'")


def embed_text(text: str) -> list[float]:
    dimensions = settings.rag_embedding_dimensions
    if dimensions != RAG_SCHEMA_EMBEDDING_DIMENSIONS:
        raise ValueError(
            "RAG embedding dimensions are part of the database schema; "
            f"configured {dimensions}, expected {RAG_SCHEMA_EMBEDDING_DIMENSIONS}"
        )
    if settings.rag_embedding_provider == "local_hash":
        return _local_feature_hash(text, dimensions)
    if settings.rag_embedding_provider != "llm":
        raise ValueError("RAG_EMBEDDING_PROVIDER must be 'local_hash' or 'llm'")
    vector = generate_embedding(text)
    if len(vector) != dimensions:
        raise ValueError(
            f"embedding dimension mismatch: provider returned {len(vector)}, expected {dimensions}"
        )
    if any(not math.isfinite(float(value)) for value in vector):
        raise ValueError("embedding provider returned non-finite values")
    magnitude = math.sqrt(sum(float(value) * float(value) for value in vector))
    return [float(value) / magnitude for value in vector] if magnitude else [0.0] * dimensions
