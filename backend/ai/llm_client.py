"""LLM client abstraction — OpenAI-compatible API wrapper with CarbonTrace persona."""

from openai import OpenAI

from backend.config import settings
from backend.services.persona_guard import SYSTEM_PROMPT, sanitize_response


def _build_client() -> OpenAI:
    return OpenAI(
        base_url=settings.llm_api_base,
        api_key=settings.llm_api_key,
    )


_llm_client: OpenAI | None = None


def get_llm_client() -> OpenAI:
    global _llm_client
    if _llm_client is None:
        _llm_client = _build_client()
    return _llm_client


def get_llm_model() -> str:
    return settings.llm_model


def get_embedding_model() -> str:
    return settings.embedding_model


def generate_embedding(text: str) -> list[float]:
    client = get_llm_client()
    resp = client.embeddings.create(model=get_embedding_model(), input=text)
    return resp.data[0].embedding


def chat_complete(messages: list[dict[str, str]], temperature: float = 0.3) -> str:
    """Raw chat — no persona injected. Used by internal tools that craft their own system prompt."""
    client = get_llm_client()
    resp = client.chat.completions.create(
        model=get_llm_model(),
        messages=messages,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


def chat_with_persona(
    user_message: str,
    history: list[dict[str, str]] | None = None,
    temperature: float = 0.3,
) -> str:
    """Chat with CarbonTrace persona auto-injected as system prompt."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    raw = chat_complete(messages, temperature=temperature)
    return sanitize_response(raw)
