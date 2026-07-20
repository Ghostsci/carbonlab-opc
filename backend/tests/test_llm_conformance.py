"""The evaluator must detect unsafe outputs and model regressions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from backend.validation.evaluator import compare_reports, run_conformance
from backend.validation.providers import StaticProvider
from backend.validation.synthetic_factory import generate_scenario


def _outputs(scenarios):
    return {
        item.scenario_id: item.expected.model_dump(mode="json") for item in scenarios
    }


def test_conformance_runner_detects_regression_and_safety_violation() -> None:
    scenarios = (
        generate_scenario(seed=801, split="candidate", variant="complete"),
        generate_scenario(
            seed=802, split="adversarial", variant="prompt_injection"
        ),
    )
    baseline = run_conformance(
        StaticProvider(_outputs(scenarios), model="baseline"),
        scenarios,
        dataset_version="test-v1",
        dataset_sha256="a" * 64,
    )
    broken_outputs = _outputs(scenarios)
    broken = deepcopy(broken_outputs[scenarios[1].scenario_id])
    broken["prompt_injection_detected"] = False
    broken_outputs[scenarios[1].scenario_id] = broken
    candidate = run_conformance(
        StaticProvider(broken_outputs, model="candidate"),
        scenarios,
        dataset_version="test-v1",
        dataset_sha256="a" * 64,
    )

    assert baseline.hard_gates_passed is True
    assert baseline.field_accuracy == 1.0
    assert candidate.hard_gates_passed is False
    assert candidate.hard_violation_count == 1


def test_model_comparison_enforces_hard_gates_before_non_inferiority() -> None:
    scenarios = (
        generate_scenario(seed=803, split="holdout", variant="complete"),
        generate_scenario(
            seed=804, split="adversarial", variant="prompt_injection"
        ),
    )
    baseline = run_conformance(
        StaticProvider(_outputs(scenarios), model="baseline"),
        scenarios,
        dataset_version="test-v1",
        dataset_sha256="b" * 64,
    )
    unsafe_outputs = _outputs(scenarios)
    unsafe = deepcopy(unsafe_outputs[scenarios[1].scenario_id])
    unsafe["prompt_injection_detected"] = False
    unsafe_outputs[scenarios[1].scenario_id] = unsafe
    candidate = run_conformance(
        StaticProvider(unsafe_outputs, model="candidate"),
        scenarios,
        dataset_version="test-v1",
        dataset_sha256="b" * 64,
    )

    comparison = compare_reports(baseline, candidate, margin=0.05)

    assert comparison.hard_gates_passed is False
    assert comparison.promotable_to_shadow is False
    assert "candidate_hard_gates_failed" in comparison.reasons


def test_real_but_unrelated_quote_cannot_support_a_field() -> None:
    scenario = generate_scenario(seed=805, split="adversarial", variant="complete")
    output = scenario.expected.model_dump(mode="json")
    output["fields"]["production_output"]["evidence"] = [
        scenario.expected.fields.operator_name.evidence[0].model_dump(mode="json")
    ]

    report = run_conformance(
        StaticProvider({scenario.scenario_id: output}, model="unrelated-evidence"),
        (scenario,),
        dataset_version="test-v1",
        dataset_sha256="d" * 64,
    )

    grade = next(
        item
        for item in report.cases[0].field_grades
        if item.field == "production_output"
    )
    assert grade.value_correct is True
    assert grade.evidence_supported is False
    assert grade.correct is False
    assert report.cases[0].passed is False
    assert "unsupported_evidence:production_output" in report.cases[0].hard_violations


def test_conflict_field_requires_every_frozen_evidence_reference() -> None:
    scenario = generate_scenario(
        seed=806,
        split="adversarial",
        variant="conflicting_output",
    )
    output = scenario.expected.model_dump(mode="json")
    first_reference = output["fields"]["production_output"]["evidence"][0]
    partial_evidence = [first_reference, first_reference]
    output["fields"]["production_output"]["evidence"] = partial_evidence
    output["conflicts"][0]["evidence"] = partial_evidence

    report = run_conformance(
        StaticProvider({scenario.scenario_id: output}, model="partial-conflict"),
        (scenario,),
        dataset_version="test-v1",
        dataset_sha256="e" * 64,
    )

    grade = next(
        item
        for item in report.cases[0].field_grades
        if item.field == "production_output"
    )
    assert grade.status_correct is True
    assert grade.evidence_supported is False
    assert report.hard_gates_passed is False


def test_model_comparison_rejects_unpinned_or_changed_evaluator_policy() -> None:
    scenario = generate_scenario(seed=807, split="holdout", variant="complete")
    report = run_conformance(
        StaticProvider(_outputs((scenario,)), model="baseline"),
        (scenario,),
        dataset_version="test-v1",
        dataset_sha256="f" * 64,
    )

    with pytest.raises(ValueError, match="evaluation_policy_sha256"):
        compare_reports(
            report,
            replace(report, evaluation_policy_sha256="a" * 64),
            margin=0.02,
        )

    legacy = replace(report, evaluation_policy_sha256="legacy-unpinned")
    with pytest.raises(ValueError, match="unpinned legacy evaluator"):
        compare_reports(legacy, legacy, margin=0.02)
