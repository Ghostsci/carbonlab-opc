#!/usr/bin/env python3
"""Run a sanitized LLM conformance test against a verified synthetic dataset."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.validation.evaluator import run_conformance  # noqa: E402
from backend.validation.prompting import build_prompt  # noqa: E402
from backend.validation.providers import (  # noqa: E402
    OpenAICompatibleProvider,
    RecordingProvider,
)
from backend.validation.qualification import (  # noqa: E402
    load_and_verify_qualification_lock,
)
from backend.validation.reporting import (  # noqa: E402
    build_run_artifact,
    write_run_artifact,
)
from backend.validation.synthetic_factory import (  # noqa: E402
    load_dataset,
    verify_dataset,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run provider-independent factory extraction conformance tests."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "validation" / "datasets" / "synthetic_factory_v1",
    )
    parser.add_argument(
        "--splits",
        nargs="+",
        choices=("candidate", "holdout", "adversarial"),
        required=True,
    )
    parser.add_argument("--provider-id", default="deepseek")
    parser.add_argument("--model", default=os.environ.get("DEEPSEEK_MODEL"))
    parser.add_argument("--base-url", default=os.environ.get("DEEPSEEK_API_BASE"))
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--max-tokens", type=int, default=4_000)
    parser.add_argument("--report-prefix", type=Path)
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument(
        "--qualification-lock",
        type=Path,
        default=ROOT / "validation" / "QUALIFICATION_LOCK.json",
    )
    parser.add_argument(
        "--record-only",
        action="store_true",
        help="write a failed report but return exit code 0 during candidate tuning",
    )
    args = parser.parse_args()
    if not args.model:
        parser.error("--model or DEEPSEEK_MODEL is required")
    if not args.base_url:
        parser.error("--base-url or DEEPSEEK_API_BASE is required")

    manifest = verify_dataset(args.dataset)
    scenarios = load_dataset(
        args.dataset,
        splits=set(args.splits),
        verify_integrity=False,
    )
    if not scenarios:
        parser.error("the selected dataset splits contain no scenarios")
    selected_splits = set(args.splits)
    if selected_splits & {"holdout", "adversarial"}:
        packages = tuple(build_prompt(scenario) for scenario in scenarios)
        try:
            load_and_verify_qualification_lock(
                args.qualification_lock,
                manifest=manifest,
                packages=packages,
                splits=selected_splits,
            )
        except ValueError as exc:
            parser.error(str(exc))

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    raw_dir = args.raw_dir or (
        ROOT / "validation" / "runs" / f"{timestamp}_{args.provider_id}_{args.model}"
    )
    provider = OpenAICompatibleProvider(
        provider_id=args.provider_id,
        model=args.model,
        base_url=args.base_url,
        api_key_env=args.api_key_env,
        timeout_seconds=args.timeout_seconds,
        max_retries=args.max_retries,
        max_tokens=args.max_tokens,
    )
    recording_provider = RecordingProvider(provider, raw_dir)
    report = run_conformance(
        recording_provider,
        scenarios,
        dataset_version=manifest["dataset_version"],
        dataset_sha256=manifest["dataset_sha256"],
    )
    artifact = build_run_artifact(
        report,
        dataset_path=args.dataset,
        provider_configuration=recording_provider.public_configuration(),
    )
    prefix = args.report_prefix or (
        ROOT / "validation" / "reports" / artifact.run_id
    )
    json_path, markdown_path = write_run_artifact(
        artifact,
        json_path=prefix.with_suffix(".json"),
        markdown_path=prefix.with_suffix(".md"),
    )
    print(f"run_id={artifact.run_id}")
    print(f"json_report={json_path}")
    print(f"markdown_report={markdown_path}")
    print(f"case_pass_rate={report.case_pass_rate:.4f}")
    print(f"field_accuracy={report.field_accuracy:.4f}")
    print(f"eligible_for_shadow={artifact.gate_assessment.eligible_for_shadow}")
    if artifact.gate_assessment.eligible_for_shadow or args.record_only:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
