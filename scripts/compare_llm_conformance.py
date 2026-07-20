#!/usr/bin/env python3
"""Compare two conformance artifacts with a preregistered paired margin."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.validation.evaluator import compare_reports  # noqa: E402
from backend.validation.reporting import load_run_artifact  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument(
        "--margin",
        type=float,
        required=True,
        help="preregister this before inspecting candidate results",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--record-only", action="store_true")
    args = parser.parse_args()

    baseline = load_run_artifact(args.baseline)
    candidate = load_run_artifact(args.candidate)
    comparison = compare_reports(
        baseline.report,
        candidate.report,
        margin=args.margin,
    )
    payload = {
        "artifact_version": "1.0.0",
        "baseline_run_id": baseline.run_id,
        "candidate_run_id": candidate.run_id,
        "comparison": comparison.to_dict(),
        "production_eligible": False,
        "limitation": (
            "通过仅表示可进入影子运行；合成数据比较不能证明真实客户或法规表现。"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path = args.output.with_suffix(".md")
    markdown_path.write_text(
        _render_markdown(payload),
        encoding="utf-8",
    )
    print(f"comparison_report={args.output}")
    print(f"promotable_to_shadow={comparison.promotable_to_shadow}")
    if comparison.promotable_to_shadow or args.record_only:
        return 0
    return 2


def _render_markdown(payload: dict) -> str:
    comparison = payload["comparison"]
    reasons = comparison["reasons"] or ["无"]
    return "\n".join(
        (
            "# LLM 候选版本成对比较",
            "",
            f"- 基线：`{payload['baseline_run_id']}`",
            f"- 候选：`{payload['candidate_run_id']}`",
            f"- 预登记非劣效界值：{comparison['margin']:.2%}",
            f"- 成对场景数：{comparison['paired_observations']}",
            f"- 字段准确率差：{comparison['accuracy_difference']:.2%}",
            "- 95% bootstrap 区间："
            f"[{comparison['confidence_interval_95'][0]:.2%}, "
            f"{comparison['confidence_interval_95'][1]:.2%}]",
            f"- 硬门禁：{'通过' if comparison['hard_gates_passed'] else '失败'}",
            f"- 可进入影子：{'是' if comparison['promotable_to_shadow'] else '否'}",
            f"- 原因：{', '.join(reasons)}",
            "",
            f"> {payload['limitation']}",
            "",
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
