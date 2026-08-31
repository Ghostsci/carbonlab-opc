#!/usr/bin/env python3
"""Verify the M4 evidence contract without modifying source or frozen inputs."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {
    "PASS",
    "FAIL_CODE",
    "FAIL_DEPENDENCY",
    "NOT_RUN_ENV",
    "BLOCKED_EXTERNAL",
    "PASS_WITH_LIMITATIONS",
}
EXPECTED_INPUT_HASHES = {
    "M3_MINIMUM_CLOSED_LOOP_V1.0.3_CORRECTED_CANONICAL.tar.gz": "60abf4fd50a1b1922f31958c4a50ec56330da5b251b1a761973295cd5b178d63",
    "CARB-16_M3_V1.0.3_CORRECTED_CANONICAL_DEVSECOPS.md": "f4210bf5cbd3d265f3004b8d1453e36165bc0d67a0e4a4f84fb19fd6dd792129",
    "CARB-16_M3_V1.0.3_CORRECTED_CANONICAL_INDEPENDENT_QA.md": "6db3f0cb9196d409ee8c5c23a27b88a57ae5f178409081502d05988df5416995",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def walk(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def main() -> int:
    summary = json.loads((ROOT / "results/replay-summary.json").read_text(encoding="utf-8"))
    results = json.loads((ROOT / "results/scenario-results.json").read_text(encoding="utf-8"))
    scenarios = results["scenarios"]
    checks: dict[str, bool] = {}
    checks["scenario_count_8"] = len(scenarios) == 8
    checks["allowed_classifications_only"] = all(
        item["classification"] in ALLOWED for item in scenarios
    )
    checks["all_scenarios_pass"] = all(
        item["classification"] == "PASS" for item in scenarios
    )
    checks["three_hashes_identical"] = len(summary["run_sha256"]) == 3 and len(
        set(summary["run_sha256"])
    ) == 1
    checks["semantic_consistency_100_percent"] = (
        summary["semantic_consistency"] is True
        and summary["semantic_consistency_rate"] == "100%"
    )
    checks["expected_semantic_hash"] = summary["run_sha256"] == [
        "a08a2451a7083933ff314a009e29a04266b7dcc9203c069700df623cb327a997"
    ] * 3
    by_id = {item["scenario_id"]: item for item in scenarios}
    checks["scenario_ids_exact"] = set(by_id) == {
        "S01_NORMAL_SINGLE",
        "S02_BATCH_ISOLATION",
        "S03_MISSING_EVIDENCE",
        "S04_UNIT_ANOMALY",
        "S05_PERIOD_CONFLICT",
        "S06_PROMPT_INJECTION",
        "S07_UNAUTHORIZED_CONFIRMATION",
        "S08_UNCONFIRMED_PUBLISH",
    }
    checks["deterministic_emissions"] = Decimal(
        by_id["S01_NORMAL_SINGLE"]["calculation_receipt"]["result"]["value"]
    ) == Decimal("1764.5905")
    checks["signed_confirmation"] = all(
        node.get("authentication") == "signed_confirmation_credential"
        for node in walk(results)
        if "authentication" in node
    )
    guarded_flags = [
        (key, node[key])
        for node in walk(results)
        for key in ("formal_write_allowed", "publish_allowed")
        if key in node
    ]
    checks["all_runtime_permission_flags_false"] = bool(guarded_flags) and all(
        value is False for _, value in guarded_flags
    )
    checks["no_credential_tokens_recorded"] = all(
        "token" not in node for node in walk(results)
    )
    checks["all_equivalent_evidence_exists"] = all(
        (ROOT / item["equivalent_text_evidence"]).is_file() for item in scenarios
    )
    checks["expected_rejections_retained"] = len(
        json.loads((ROOT / "results/failure-samples.json").read_text(encoding="utf-8"))
    ) == 7
    checks["input_hashes_match"] = all(
        digest(ROOT / "input-evidence" / name) == expected
        for name, expected in EXPECTED_INPUT_HASHES.items()
    )
    ledger = json.loads(
        (ROOT / "environment/execution-ledger.json").read_text(encoding="utf-8")
    )
    checks["all_recorded_execution_exit_codes_zero"] = all(
        item["exit_code"] == 0 for item in ledger["commands"]
    )
    checks["no_networked_model_or_remote_write"] = (
        ledger["networked_model_calls"] == 0 and ledger["remote_writes"] == 0
    )
    report = {
        "classification": "PASS" if all(checks.values()) else "FAIL_CODE",
        "checks": checks,
        "checked_count": len(checks),
        "passed_count": sum(checks.values()),
    }
    (ROOT / "results/artifact-verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
