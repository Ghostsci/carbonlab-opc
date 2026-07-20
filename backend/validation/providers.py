"""Replaceable LLM provider interface with a secure OpenAI-compatible adapter."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from openai import OpenAI


@dataclass(frozen=True, slots=True)
class ProviderInvocation:
    provider_id: str
    model: str
    output_text: str
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    system_fingerprint: str | None = None


class LLMProvider(Protocol):
    provider_id: str
    model: str

    def complete_json(self, messages: list[dict[str, str]]) -> ProviderInvocation:
        """Return one JSON response. Implementations must never log credentials."""

    def public_configuration(self) -> dict[str, object]:
        """Return non-secret parameters required to reproduce the invocation."""


class OpenAICompatibleProvider:
    """Provider adapter for DeepSeek and other OpenAI-compatible APIs."""

    def __init__(
        self,
        *,
        provider_id: str,
        model: str,
        base_url: str,
        api_key_env: str,
        timeout_seconds: float = 90.0,
        max_retries: int = 2,
        temperature: float = 0.0,
        max_tokens: int = 4_000,
    ) -> None:
        _validate_base_url(base_url)
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(f"required provider credential is missing: {api_key_env}")
        self.provider_id = provider_id
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._api_key_env = api_key_env
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    def complete_json(self, messages: list[dict[str, str]]) -> ProviderInvocation:
        started = time.monotonic()
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            response_format={"type": "json_object"},
            stream=False,
        )
        latency_ms = round((time.monotonic() - started) * 1000)
        output = response.choices[0].message.content or ""
        if not output.strip():
            raise RuntimeError("provider returned an empty JSON response")
        usage = response.usage
        return ProviderInvocation(
            provider_id=self.provider_id,
            model=self.model,
            output_text=output,
            latency_ms=latency_ms,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            system_fingerprint=getattr(response, "system_fingerprint", None),
        )

    def public_configuration(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "model": self.model,
            "base_url": self._base_url,
            "api_key_env": self._api_key_env,
            "timeout_seconds": self._timeout_seconds,
            "max_retries": self._max_retries,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "response_format": "json_object",
        }


class StaticProvider:
    """Deterministic provider used to test the conformance harness itself."""

    def __init__(
        self,
        outputs: dict[str, dict | str],
        *,
        provider_id: str = "static",
        model: str = "static-v1",
    ) -> None:
        self.provider_id = provider_id
        self.model = model
        self._outputs = outputs

    def complete_json(self, messages: list[dict[str, str]]) -> ProviderInvocation:
        scenario_id = _scenario_id_from_messages(messages)
        value = self._outputs[scenario_id]
        output = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return ProviderInvocation(
            provider_id=self.provider_id,
            model=self.model,
            output_text=output,
            latency_ms=1,
        )

    def public_configuration(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "model": self.model,
            "adapter": "static",
        }


class RecordingProvider:
    """Write raw synthetic responses to a Git-ignored directory for debugging."""

    def __init__(self, delegate: LLMProvider, destination: Path) -> None:
        self.provider_id = delegate.provider_id
        self.model = delegate.model
        self._delegate = delegate
        self._destination = destination
        self._destination.mkdir(parents=True, exist_ok=True, mode=0o700)

    def complete_json(self, messages: list[dict[str, str]]) -> ProviderInvocation:
        scenario_id = _scenario_id_from_messages(messages)
        invocation = self._delegate.complete_json(messages)
        payload = {
            "provider_id": invocation.provider_id,
            "model": invocation.model,
            "scenario_id": scenario_id,
            "latency_ms": invocation.latency_ms,
            "prompt_tokens": invocation.prompt_tokens,
            "completion_tokens": invocation.completion_tokens,
            "system_fingerprint": invocation.system_fingerprint,
            "output_text": invocation.output_text,
        }
        path = self._destination / f"{scenario_id}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)
        return invocation

    def public_configuration(self) -> dict[str, object]:
        return self._delegate.public_configuration()


def _scenario_id_from_messages(messages: list[dict[str, str]]) -> str:
    prefix = "SCENARIO_ID="
    for message in messages:
        for line in message["content"].splitlines():
            if line.startswith(prefix):
                return line.removeprefix(prefix).strip()
    raise KeyError("prompt package does not expose a scenario ID")


def _validate_base_url(base_url: str) -> None:
    if not base_url or base_url != base_url.strip():
        raise ValueError("provider base URL must not contain surrounding whitespace")
    parsed = urlparse(base_url)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(
            "provider base URL must not include userinfo, query, or fragment"
        )
    if parsed.query or parsed.fragment:
        raise ValueError(
            "provider base URL must not include userinfo, query, or fragment"
        )
    if parsed.scheme == "https" and parsed.hostname:
        return
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return
    raise ValueError("provider base URL must be HTTPS or an explicit localhost URL")
