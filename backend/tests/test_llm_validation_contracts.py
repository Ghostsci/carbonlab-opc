"""Behavior tests for strict, provider-independent LLM output contracts."""

from __future__ import annotations

import json
import stat

import pytest
from pydantic import ValidationError

from backend.validation.contracts import FactoryDocumentExtraction
from backend.validation.providers import (
    OpenAICompatibleProvider,
    RecordingProvider,
    StaticProvider,
)
from backend.validation.synthetic_factory import generate_scenario


def _candidate(value: str, quote: str, *, unit: str | None = None) -> dict:
    return {
        "status": "extracted",
        "value": value,
        "unit": unit,
        "evidence": [{"document_id": "identity", "quote": quote}],
        "requires_human_confirmation": True,
        "uncertainty_reason": None,
    }


def _valid_payload() -> dict:
    return {
        "schema_version": "1.1.0",
        "task_id": "factory_document_extraction_v1",
        "scenario_id": "case_contract_001",
        "fields": {
            "installation_name": _candidate("合成热轧装置", "装置：合成热轧装置"),
            "operator_name": _candidate("合成钢铁有限公司", "经营者：合成钢铁有限公司"),
            "product_name": _candidate("热轧卷板", "产品：热轧卷板"),
            "cn_code": _candidate("72085100", "CN编码：72085100"),
            "production_route": _candidate("bf_bof", "生产路线：bf_bof"),
            "period_start": _candidate("2026-01-01", "期间开始：2026-01-01"),
            "period_end": _candidate("2026-03-31", "期间结束：2026-03-31"),
            "production_output": _candidate("1000", "合格产量：1000 t", unit="t"),
            "purchased_electricity": _candidate(
                "2000000", "本期用电量：2000000 kWh", unit="kWh"
            ),
        },
        "prompt_injection_detected": False,
        "conflicts": [],
        "missing_fields": [],
        "formal_write_allowed": False,
    }


def test_provider_output_schema_rejects_unknown_fields() -> None:
    payload = _valid_payload()
    payload["approval"] = "自动通过"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        FactoryDocumentExtraction.model_validate(payload)


def test_contract_rejects_formal_write_and_unsupported_extraction() -> None:
    payload = _valid_payload()
    payload["formal_write_allowed"] = True
    payload["fields"]["production_output"]["evidence"] = []

    with pytest.raises(ValidationError):
        FactoryDocumentExtraction.model_validate(payload)


def test_conflict_summary_must_repeat_the_field_evidence() -> None:
    scenario = generate_scenario(
        seed=799,
        split="adversarial",
        variant="conflicting_output",
    )
    payload = scenario.expected.model_dump(mode="json")
    payload["conflicts"][0]["evidence"] = [
        scenario.expected.fields.operator_name.evidence[0].model_dump(mode="json"),
        scenario.expected.fields.product_name.evidence[0].model_dump(mode="json"),
    ]

    with pytest.raises(ValidationError, match="conflict evidence must match"):
        FactoryDocumentExtraction.model_validate(payload)


def test_provider_adapter_rejects_insecure_remote_endpoint() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        OpenAICompatibleProvider(
            provider_id="unsafe",
            model="unsafe-v1",
            base_url="http://models.example.com",
            api_key_env="MISSING_TEST_KEY",
        )


def test_provider_adapter_requires_environment_credential(monkeypatch) -> None:
    monkeypatch.delenv("MISSING_TEST_KEY", raising=False)

    with pytest.raises(RuntimeError, match="MISSING_TEST_KEY"):
        OpenAICompatibleProvider(
            provider_id="missing",
            model="missing-v1",
            base_url="https://models.example.com",
            api_key_env="MISSING_TEST_KEY",
        )


@pytest.mark.parametrize(
    "base_url",
    (
        "https://synthetic-user:synthetic-password@models.example.com/v1",
        "https://models.example.com/v1?access_token=synthetic-canary-value",
        "https://models.example.com/v1#authorization=synthetic-canary-value",
    ),
)
def test_provider_adapter_rejects_credentials_in_url_components(base_url: str) -> None:
    with pytest.raises(ValueError, match="userinfo, query, or fragment"):
        OpenAICompatibleProvider(
            provider_id="unsafe-url",
            model="unsafe-v1",
            base_url=base_url,
            api_key_env="MISSING_TEST_KEY",
        )


def test_recording_provider_never_persists_prompt_or_credential(tmp_path) -> None:
    output = _valid_payload()
    provider = RecordingProvider(
        StaticProvider({"case_contract_001": output}),
        tmp_path / "raw",
    )
    messages = [
        {"role": "system", "content": "credential-like prompt must not persist"},
        {"role": "user", "content": "SCENARIO_ID=case_contract_001"},
    ]

    provider.complete_json(messages)

    path = tmp_path / "raw" / "case_contract_001.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600
    assert "messages" not in payload
    assert "prompt" not in payload
    assert payload["output_text"]
