"""Reports must be reproducible, loadable, and unable to persist API secrets."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from backend.validation.evaluator import run_conformance
from backend.validation.providers import StaticProvider
from backend.validation.reporting import (
    build_run_artifact,
    load_run_artifact,
    write_run_artifact,
)
from backend.validation.synthetic_factory import generate_scenario


def _green_artifact(tmp_path: Path):
    scenario = generate_scenario(seed=901, split="holdout", variant="complete")
    provider = StaticProvider(
        {scenario.scenario_id: scenario.expected.model_dump(mode="json")}
    )
    report = run_conformance(
        provider,
        (scenario,),
        dataset_version="test-v1",
        dataset_sha256="c" * 64,
    )
    artifact = build_run_artifact(
        report,
        dataset_path=tmp_path / "synthetic",
        provider_configuration=provider.public_configuration(),
    )
    return artifact


def test_report_round_trip_preserves_slotted_dataclasses_without_raw_output(
    tmp_path: Path,
) -> None:
    artifact = _green_artifact(tmp_path)
    report_path = tmp_path / "report.json"

    write_run_artifact(artifact, json_path=report_path)
    loaded = load_run_artifact(report_path)
    serialized = report_path.read_text(encoding="utf-8")

    assert loaded.report.to_dict() == artifact.report.to_dict()
    assert loaded.gate_assessment.eligible_for_shadow is True
    assert "output_text" not in serialized
    assert "formal_write_allowed" not in serialized


def test_report_writer_rejects_credential_like_values(tmp_path: Path) -> None:
    artifact = _green_artifact(tmp_path)
    unsafe = replace(
        artifact,
        provider_configuration={"credential": "sk-this-is-a-fake-test-secret"},
    )

    with pytest.raises(ValueError, match="credential-like secret"):
        write_run_artifact(unsafe, json_path=tmp_path / "unsafe.json")


@pytest.mark.parametrize(
    "provider_configuration",
    (
        {
            "base_url": (
                "https://models.example.com/v1"
                "?access_token=synthetic-canary-value"
            )
        },
        {"base_url": "https://synthetic-user:synthetic-pass@models.example.com/v1"},
        {"access_token": "synthetic-canary-value"},
        {"authorization": "Bearer synthetic-canary-value"},
        {"bearer": "synthetic-canary-value"},
        {"token": "synthetic-canary-value"},
    ),
)
def test_report_writer_rejects_non_sk_credentials(
    tmp_path: Path,
    provider_configuration: dict[str, str],
) -> None:
    artifact = replace(
        _green_artifact(tmp_path),
        provider_configuration=provider_configuration,
    )
    json_path = tmp_path / "unsafe.json"
    markdown_path = tmp_path / "unsafe.md"

    with pytest.raises(ValueError, match="credential-like secret"):
        write_run_artifact(
            artifact,
            json_path=json_path,
            markdown_path=markdown_path,
        )

    assert not json_path.exists()
    assert not markdown_path.exists()


def test_report_writer_scans_rendered_markdown_before_writing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    artifact = _green_artifact(tmp_path)
    json_path = tmp_path / "unsafe-markdown.json"
    markdown_path = tmp_path / "unsafe-markdown.md"
    monkeypatch.setattr(
        "backend.validation.reporting.render_markdown",
        lambda _artifact: "Authorization: Bearer synthetic-canary-value",
    )

    with pytest.raises(ValueError, match="credential-like secret"):
        write_run_artifact(
            artifact,
            json_path=json_path,
            markdown_path=markdown_path,
        )

    assert not json_path.exists()
    assert not markdown_path.exists()


def test_report_loader_rejects_tampered_gate_assessment(tmp_path: Path) -> None:
    artifact = _green_artifact(tmp_path)
    report_path = tmp_path / "report.json"
    write_run_artifact(artifact, json_path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["gate_assessment"]["eligible_for_shadow"] = False
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="gate assessment mismatch"):
        load_run_artifact(report_path)
