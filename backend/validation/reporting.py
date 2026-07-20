"""Sanitized, reproducible validation artifacts and preregistered gate assessment."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.validation.evaluator import (
    CaseGrade,
    ConformanceReport,
    FieldGrade,
)


ARTIFACT_VERSION = "1.1.0"
ROOT = Path(__file__).resolve().parents[2]
RELEASE_GATES_PATH = ROOT / "validation" / "RELEASE_GATES.json"
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)https?://[^/\s@]+@"),
    re.compile(
        r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"
    ),
    re.compile(
        r"(?i)[?&#](?:api[_-]?key|access[_-]?token|refresh[_-]?token|"
        r"id[_-]?token|auth[_-]?token|token|authorization|bearer|"
        r"client[_-]?secret|password|secret|credential)="
        r"[^&#\s\"']{8,}"
    ),
    re.compile(
        r"(?i)['\"](?:api[_-]?key|access[_-]?token|refresh[_-]?token|"
        r"id[_-]?token|auth[_-]?token|token|authorization|bearer|"
        r"client[_-]?secret|password|secret|credential)['\"]\s*:\s*"
        r"['\"][^'\"]+['\"]"
    ),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|"
        r"id[_-]?token|auth[_-]?token|token|authorization|bearer|"
        r"client[_-]?secret|password|secret|credential)\b\s*[=:]\s*"
        r"['\"]?[^\s,'\"}]{8,}"
    ),
)
SENSITIVE_KEY_NAMES = frozenset(
    {
        "apikey",
        "accesstoken",
        "refreshtoken",
        "idtoken",
        "authtoken",
        "token",
        "authorization",
        "bearer",
        "clientsecret",
        "password",
        "secret",
        "credential",
    }
)


@dataclass(frozen=True, slots=True)
class GateAssessment:
    gate_version: str
    eligible_for_shadow: bool
    eligible_for_production: bool
    checks: dict[str, bool]
    failed_checks: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ValidationRunArtifact:
    artifact_version: str
    run_id: str
    created_at_utc: str
    git_commit: str
    git_worktree_dirty: bool
    dataset_path: str
    selected_splits: tuple[str, ...]
    provider_configuration: dict[str, object]
    report: ConformanceReport
    gate_assessment: GateAssessment

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_report(
    report: ConformanceReport,
    *,
    release_gates_path: Path = RELEASE_GATES_PATH,
) -> GateAssessment:
    config = json.loads(release_gates_path.read_text(encoding="utf-8"))
    thresholds = config["shadow_eligibility"]
    checks = {
        "hard_gates_passed": report.hard_gates_passed,
        "schema_valid_rate": report.schema_valid_rate == 1.0,
        "case_pass_rate": report.case_pass_rate
        >= thresholds["minimum_case_pass_rate"],
        "field_accuracy": report.field_accuracy
        >= thresholds["minimum_field_accuracy"],
        "numeric_field_accuracy": report.numeric_field_accuracy
        >= thresholds["minimum_numeric_field_accuracy"],
        "evidence_supported_rate": report.evidence_supported_rate
        >= thresholds["minimum_evidence_supported_rate"],
        "prompt_injection_classification_rate": (
            report.prompt_injection_classification_rate
            >= thresholds["minimum_prompt_injection_classification_rate"]
        ),
        "provider_failure_count": report.provider_failure_count
        <= thresholds["maximum_provider_failures"],
        "hard_violation_count": report.hard_violation_count
        <= thresholds["maximum_hard_violations"],
    }
    failed = tuple(name for name, passed in checks.items() if not passed)
    return GateAssessment(
        gate_version=str(config["version"]),
        eligible_for_shadow=not failed,
        eligible_for_production=False,
        checks=checks,
        failed_checks=failed,
        limitations=(
            "仅验证受约束的合成文本场景，不代表真实票据、OCR或客户数据表现。",
            "不证明法规适用性、法定核查接受、客户付费或绝对零错误。",
            "即使门禁绿色，也只允许进入人工平行处理的影子试验。",
        ),
    )


def build_run_artifact(
    report: ConformanceReport,
    *,
    dataset_path: Path,
    provider_configuration: dict[str, object],
) -> ValidationRunArtifact:
    created_at = datetime.now(UTC).replace(microsecond=0)
    commit, dirty = _git_state()
    model_slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", report.model).strip("-")
    run_id = (
        created_at.strftime("%Y%m%dT%H%M%SZ")
        + "_"
        + model_slug
        + "_"
        + report.prompt_set_sha256[:10]
    )
    try:
        dataset_label = str(dataset_path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        dataset_label = dataset_path.name
    return ValidationRunArtifact(
        artifact_version=ARTIFACT_VERSION,
        run_id=run_id,
        created_at_utc=created_at.isoformat().replace("+00:00", "Z"),
        git_commit=commit,
        git_worktree_dirty=dirty,
        dataset_path=dataset_label,
        selected_splits=report.splits,
        provider_configuration=provider_configuration,
        report=report,
        gate_assessment=assess_report(report),
    )


def write_run_artifact(
    artifact: ValidationRunArtifact,
    *,
    json_path: Path,
    markdown_path: Path | None = None,
) -> tuple[Path, Path]:
    markdown_path = markdown_path or json_path.with_suffix(".md")
    artifact_payload = artifact.to_dict()
    _assert_no_sensitive_fields(artifact_payload)
    payload = json.dumps(
        artifact_payload, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    markdown = render_markdown(artifact)
    _assert_secret_free(payload)
    _assert_secret_free(markdown)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(payload, encoding="utf-8")
    markdown_path.write_text(markdown, encoding="utf-8")
    return json_path, markdown_path


def load_run_artifact(path: Path) -> ValidationRunArtifact:
    serialized = path.read_text(encoding="utf-8")
    _assert_secret_free(serialized)
    payload = json.loads(serialized)
    _assert_no_sensitive_fields(payload)
    report_payload = dict(payload["report"])
    report_payload.setdefault("evaluation_policy_sha256", "legacy-unpinned")
    raw_cases = report_payload.pop("cases")
    splits = tuple(report_payload.pop("splits"))
    cases = tuple(
        CaseGrade(
            **{
                **{
                    key: value
                    for key, value in case.items()
                    if key not in {"field_grades", "hard_violations"}
                },
                "field_grades": tuple(
                    FieldGrade(**field) for field in case["field_grades"]
                ),
                "hard_violations": tuple(case["hard_violations"]),
            }
        )
        for case in raw_cases
    )
    report = ConformanceReport(
        **report_payload,
        splits=splits,
        cases=cases,
    )
    gate_payload = dict(payload["gate_assessment"])
    failed_checks = tuple(gate_payload.pop("failed_checks"))
    limitations = tuple(gate_payload.pop("limitations"))
    gates = GateAssessment(
        **gate_payload,
        failed_checks=failed_checks,
        limitations=limitations,
    )
    expected_gates = assess_report(report)
    if gates != expected_gates:
        raise ValueError("validation artifact gate assessment mismatch")
    return ValidationRunArtifact(
        **{
            key: value
            for key, value in payload.items()
            if key not in {"report", "gate_assessment", "selected_splits"}
        },
        selected_splits=tuple(payload["selected_splits"]),
        report=report,
        gate_assessment=gates,
    )


def render_markdown(artifact: ValidationRunArtifact) -> str:
    report = artifact.report
    gates = artifact.gate_assessment
    status = "可进入人工影子试验" if gates.eligible_for_shadow else "未达到影子试验门槛"
    rows = [
        ("场景通过率", report.case_pass_rate),
        ("Schema 有效率", report.schema_valid_rate),
        ("字段准确率", report.field_accuracy),
        ("关键数值字段准确率", report.numeric_field_accuracy),
        ("证据可定位率", report.evidence_supported_rate),
        ("提示词注入分类准确率", report.prompt_injection_classification_rate),
    ]
    failed_cases = [case for case in report.cases if not case.passed]
    failure_lines = []
    for case in failed_cases:
        failed_fields = ", ".join(
            field.field for field in case.field_grades if not field.correct
        ) or "无字段评分"
        violations = ", ".join(case.hard_violations) or "无硬违规"
        failure_lines.append(
            f"| `{case.scenario_id}` | {case.variant} | {failed_fields} | {violations} |"
        )
    if not failure_lines:
        failure_lines.append("| — | — | — | — |")
    check_lines = [
        f"- [{'x' if passed else ' '}] `{name}`"
        for name, passed in gates.checks.items()
    ]
    metric_lines = [
        f"| {name} | {value:.2%} |" for name, value in rows
    ]
    limitation_lines = [f"- {item}" for item in gates.limitations]
    return "\n".join(
        (
            "# 零碳云 LLM 合成验证报告",
            "",
            f"> 裁决：**{status}**。这是候选提取能力测试，不是商业、法规或正式核查结论。",
            "",
            "## 运行身份",
            "",
            f"- Run ID：`{artifact.run_id}`",
            f"- 时间（UTC）：`{artifact.created_at_utc}`",
            f"- Provider / 模型：`{report.provider_id}` / `{report.model}`",
            f"- 数据分层：`{', '.join(report.splits)}`，共 {report.scenario_count} 个场景",
            f"- Git：`{artifact.git_commit}`；工作区{'有未提交变更' if artifact.git_worktree_dirty else '干净'}",
            "",
            "## 预登记门禁",
            "",
            *check_lines,
            "",
            "## 核心指标",
            "",
            "| 指标 | 结果 |",
            "|---|---:|",
            *metric_lines,
            f"| Provider 失败 | {report.provider_failure_count} |",
            f"| 硬违规 | {report.hard_violation_count} |",
            f"| 总延迟 | {report.total_latency_ms / 1000:.1f} 秒 |",
            f"| Token | 输入 {report.prompt_tokens} / 输出 {report.completion_tokens} |",
            "",
            "## 失败场景",
            "",
            "| 场景 | 类型 | 未通过字段 | 硬违规 |",
            "|---|---|---|---|",
            *failure_lines,
            "",
            "## 可重放指纹",
            "",
            f"- Dataset：`{report.dataset_sha256}`",
            f"- Contract：`{report.contract_sha256}`",
            f"- Task：`{report.task_sha256}`",
            f"- Schema：`{report.schema_sha256}`",
            f"- Prompt set：`{report.prompt_set_sha256}`",
            f"- Evaluation policy：`{report.evaluation_policy_sha256}`",
            "",
            "## 结论边界",
            "",
            *limitation_lines,
            "",
        )
    )


def _assert_secret_free(value: str) -> None:
    if any(pattern.search(value) for pattern in SECRET_PATTERNS):
        raise ValueError("validation artifact contains a credential-like secret")


def _assert_no_sensitive_fields(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).casefold())
            if (
                normalized in SENSITIVE_KEY_NAMES
                and item is not None
                and item != ""
            ):
                raise ValueError(
                    "validation artifact contains a credential-like secret"
                )
            _assert_no_sensitive_fields(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_no_sensitive_fields(item)


def _git_state() -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return commit, bool(status.strip())
