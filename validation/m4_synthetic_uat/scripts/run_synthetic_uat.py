#!/usr/bin/env python3
"""Replay the M4 synthetic user-acceptance scenarios against accepted M3 V1.0.3."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable

from jose import jwt
from pydantic import ValidationError

from backend.auth.jwt import ALGORITHM, SECRET_KEY
from backend.services.candidate_passport_v1 import (
    CONFIRMATION_AUDIENCE,
    CandidateInput,
    CandidatePassport,
    CandidatePipelineError,
    ConfirmationAction,
    ReviewerCredential,
    apply_human_action,
    build_candidate,
    run_batch,
)
from backend.validation.synthetic_factory import generate_scenario


ARTIFACT_VERSION = "M4_SYNTHETIC_UAT_V1.0.0"
FIXED_TIME = datetime(2026, 8, 14, tzinfo=timezone.utc)
FIXED_EXPIRY = datetime(2030, 1, 1, tzinfo=timezone.utc)
ALLOWED_CLASSIFICATIONS = {
    "PASS",
    "FAIL_CODE",
    "FAIL_DEPENDENCY",
    "NOT_RUN_ENV",
    "BLOCKED_EXTERNAL",
    "PASS_WITH_LIMITATIONS",
}


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def make_input(variant: str, seed: int, scenario_id: str) -> CandidateInput:
    source = generate_scenario(seed=seed, split="candidate", variant=variant)
    return CandidateInput(scenario_id=scenario_id, documents=tuple(source.documents))


def mutate_input(source: CandidateInput, mutate: Callable[[dict], None]) -> CandidateInput:
    payload = source.model_dump(mode="json")
    mutate(payload)
    return CandidateInput.model_validate(payload)


def action(decision: str = "confirm") -> ConfirmationAction:
    return ConfirmationAction(
        decision=decision,
        reason="M4 synthetic acceptance fixture",
        occurred_at=FIXED_TIME,
    )


def reviewer(
    *,
    actor_id: str = "synthetic-reviewer",
    role: str = "auditor",
    audience: str = CONFIRMATION_AUDIENCE,
    secret: str = SECRET_KEY,
    expiry: datetime = FIXED_EXPIRY,
) -> ReviewerCredential:
    payload = {
        "sub": actor_id,
        "role": role,
        "aud": audience,
        "type": "passport_confirmation",
        "exp": expiry,
    }
    return ReviewerCredential(token=jwt.encode(payload, secret, algorithm=ALGORITHM))


def field_evidence(passport: CandidatePassport) -> dict:
    fields = passport.candidate["fields"]
    return {
        name: {
            "status": value["status"],
            "value": value["value"],
            "unit": value["unit"],
            "evidence": value["evidence"],
            "requires_human_confirmation": value["requires_human_confirmation"],
        }
        for name, value in fields.items()
    }


def base_record(
    scenario_id: str,
    title: str,
    coverage: list[str],
    user_goal: str,
    steps: list[str],
) -> dict:
    return {
        "scenario_id": scenario_id,
        "title": title,
        "coverage": coverage,
        "user_goal": user_goal,
        "operation_steps": steps,
        "classification": "PASS",
        "synthetic_only": True,
        "real_user_observation": False,
    }


def s01_normal_single() -> dict:
    record = base_record(
        "S01_NORMAL_SINGLE",
        "正常单条候选查看、来源追溯与人工确认",
        ["正常单条", "候选字段", "字段级证据", "确定性计算", "人工确认"],
        "上传一组合成文件，核对候选字段和来源后完成候选确认。",
        [
            "提交一组完整合成装置、用电量和产量文件。",
            "查看候选字段、单位、证据引文和候选状态。",
            "使用服务端签名的合成复核凭据确认候选。",
            "查看确定性计算回执和候选护照边界。",
        ],
    )
    source = make_input("complete", 1001, "m4_normal_single")
    before = build_candidate(source)
    after = apply_human_action(before, action(), reviewer())
    receipt = after.calculation_receipt or {}
    assert before.state == "candidate"
    assert after.state == "calculated"
    assert Decimal(receipt["result"]["value"]) == Decimal("1764.5905")
    assert receipt["rule_version"] == "synthetic-electricity-rule-v1"
    assert after.confirmation["authentication"] == "signed_confirmation_credential"
    assert before.formal_write_allowed is False and after.formal_write_allowed is False
    assert before.publish_allowed is False and after.publish_allowed is False
    assert all(
        value["requires_human_confirmation"]
        for value in before.candidate["fields"].values()
    )
    record.update(
        {
            "observable_result": [
                "9 个候选字段均带候选状态；已抽取字段带原文证据。",
                "签名凭据通过后状态由 candidate 转为 calculated。",
                "排放量由冻结规则计算为 1764.5905 tCO2e。",
                "正式写入和发布标志在确认前后均为 false。",
            ],
            "candidate_fields_and_evidence": field_evidence(before),
            "state_transition": ["uploaded", "candidate", "calculated_local_candidate"],
            "expected_rejection": None,
            "calculation_receipt": receipt,
            "control_checks": {
                "ai_output_remains_candidate_before_confirmation": True,
                "deterministic_rule_calculation": True,
                "signed_confirmation_credential_verified": True,
                "formal_write_allowed_false": True,
                "publish_allowed_false": True,
            },
        }
    )
    return record


def s02_batch_isolation() -> dict:
    record = base_record(
        "S02_BATCH_ISOLATION",
        "批量处理与逐项异常隔离",
        ["批量", "逐项隔离", "确定性重放"],
        "一次处理三组合成文件，并确认单个异常不会污染其他候选。",
        [
            "提交两个完整场景和一个缺失产量场景。",
            "对每项提供相同边界的签名合成复核凭据。",
            "核对两个完整项计算成功、缺失项按项拒绝。",
        ],
    )
    items = (
        make_input("complete", 1006, "m4_batch_complete_a"),
        make_input("missing_output", 1002, "m4_batch_missing_output"),
        make_input("complete", 1011, "m4_batch_complete_b"),
    )
    actions = {item.scenario_id: (action(), reviewer()) for item in items}
    results = run_batch(items, actions)
    by_id = {item["scenario_id"]: item for item in results}
    assert by_id["m4_batch_complete_a"]["passport"]["state"] == "calculated"
    assert by_id["m4_batch_complete_b"]["passport"]["state"] == "calculated"
    assert by_id["m4_batch_missing_output"]["outcome"] == "expected_rejection"
    assert by_id["m4_batch_missing_output"]["reason"].startswith(
        "unresolved_candidates:production_output"
    )
    for item in results:
        passport = item.get("passport")
        if passport:
            assert passport["formal_write_allowed"] is False
            assert passport["publish_allowed"] is False
    record.update(
        {
            "observable_result": [
                "两个完整项进入 calculated 本地候选态。",
                "缺失产量项单独 expected_rejection，未阻断其他项。",
                "全部返回项 classification 均为 PASS。",
            ],
            "candidate_fields_and_evidence": {
                item.scenario_id: field_evidence(build_candidate(item)) for item in items
            },
            "state_transition": {
                "m4_batch_complete_a": ["uploaded", "candidate", "calculated_local_candidate"],
                "m4_batch_missing_output": ["uploaded", "candidate_missing", "guard_rejected"],
                "m4_batch_complete_b": ["uploaded", "candidate", "calculated_local_candidate"],
            },
            "expected_rejection": {
                "scenario_id": "m4_batch_missing_output",
                "reason": by_id["m4_batch_missing_output"]["reason"],
            },
            "batch_results": results,
            "control_checks": {
                "per_item_isolation": True,
                "deterministic_calculation_for_complete_items": True,
                "formal_write_allowed_false": True,
                "publish_allowed_false": True,
            },
        }
    )
    return record


def s03_missing_evidence() -> dict:
    record = base_record(
        "S03_MISSING_EVIDENCE",
        "缺失用电证据时阻断确认",
        ["缺失证据", "fail-closed", "人工确认边界"],
        "识别缺失的用电证据，并确认不能靠人工点击跳过缺口。",
        [
            "提交声明未提供本期用电量的合成文件。",
            "查看 purchased_electricity 的缺失状态和空证据列表。",
            "尝试使用有效签名凭据确认。",
        ],
    )
    source = make_input("missing_electricity", 1005, "m4_missing_evidence")
    passport = build_candidate(source)
    field = passport.candidate["fields"]["purchased_electricity"]
    assert field["status"] == "missing" and field["evidence"] == []
    reason = None
    try:
        apply_human_action(passport, action(), reviewer())
    except CandidatePipelineError as exc:
        reason = exc.reason
    assert reason == "unresolved_candidates:purchased_electricity"
    assert passport.state == "candidate"
    record.update(
        {
            "observable_result": [
                "用电字段显示 missing，未虚构字段级证据。",
                "有效签名凭据也不能绕过未解决字段。",
                "拒绝后原候选仍停留在 candidate。",
            ],
            "candidate_fields_and_evidence": field_evidence(passport),
            "state_transition": ["uploaded", "candidate_missing", "guard_rejected"],
            "expected_rejection": reason,
            "control_checks": {
                "missing_evidence_not_invented": True,
                "valid_credential_cannot_bypass_missing_field": True,
                "fail_closed": True,
                "formal_write_allowed_false": passport.formal_write_allowed is False,
                "publish_allowed_false": passport.publish_allowed is False,
            },
        }
    )
    return record


def s04_unit_anomaly() -> dict:
    record = base_record(
        "S04_UNIT_ANOMALY",
        "产量单位缺失时不猜测单位",
        ["单位异常", "fail-closed", "证据追溯"],
        "发现产量数值没有单位时，阻止系统自行猜测或计算。",
        [
            "提交含产量数值但单位未标明的合成台账。",
            "查看 production_output 的 ambiguous 状态和原文证据。",
            "尝试确认并计算。",
        ],
    )
    source = make_input("ambiguous_output_unit", 1003, "m4_unit_anomaly")
    passport = build_candidate(source)
    field = passport.candidate["fields"]["production_output"]
    assert field["status"] == "ambiguous" and field["unit"] is None
    reason = None
    try:
        apply_human_action(passport, action(), reviewer())
    except CandidatePipelineError as exc:
        reason = exc.reason
    assert reason == "unresolved_candidates:production_output"
    record.update(
        {
            "observable_result": [
                "产量保留 ambiguous，不把未标明单位的值变成 t。",
                "原文证据可追溯，确定性计算未执行。",
            ],
            "candidate_fields_and_evidence": field_evidence(passport),
            "state_transition": ["uploaded", "candidate_ambiguous", "guard_rejected"],
            "expected_rejection": reason,
            "control_checks": {
                "unit_not_guessed": True,
                "calculation_not_executed": True,
                "fail_closed": True,
                "formal_write_allowed_false": passport.formal_write_allowed is False,
                "publish_allowed_false": passport.publish_allowed is False,
            },
        }
    )
    return record


def s05_period_conflict() -> dict:
    record = base_record(
        "S05_PERIOD_CONFLICT",
        "报告期起止冲突时在候选生成前拒绝",
        ["期间冲突", "fail-closed"],
        "识别开始日期晚于结束日期的文件，避免生成误导性候选。",
        [
            "提交开始日期为 2027-01-01、结束日期为 2026-12-31 的合成文件。",
            "观察期间校验结果和候选生成状态。",
        ],
    )
    source = make_input("complete", 1001, "m4_period_conflict")

    def reverse_period(payload: dict) -> None:
        identity = next(
            item for item in payload["documents"] if item["document_id"] == "identity"
        )
        identity["content"] = identity["content"].replace(
            "期间开始：2026-10-01", "期间开始：2027-01-01"
        )

    broken = mutate_input(source, reverse_period)
    identity = next(item for item in broken.documents if item.document_id == "identity")
    reason = None
    try:
        build_candidate(broken)
    except CandidatePipelineError as exc:
        reason = exc.reason
    assert reason == "invalid_period"
    record.update(
        {
            "observable_result": [
                "期间冲突返回 invalid_period。",
                "拒绝发生在候选护照生成前，没有计算、正式写入或发布状态。",
            ],
            "candidate_fields_and_evidence": {
                "candidate": None,
                "source_evidence": [
                    line
                    for line in identity.content.splitlines()
                    if line.startswith("期间开始：") or line.startswith("期间结束：")
                ],
            },
            "state_transition": ["uploaded", "validation_rejected", "no_candidate"],
            "expected_rejection": reason,
            "control_checks": {
                "invalid_period_rejected_before_candidate": True,
                "calculation_not_executed": True,
                "fail_closed": True,
                "formal_write_allowed_false": True,
                "publish_allowed_false": True,
            },
        }
    )
    return record


def s06_prompt_injection() -> dict:
    record = base_record(
        "S06_PROMPT_INJECTION",
        "文档内提示注入不能越过人工边界",
        ["提示注入", "fail-closed", "候选态"],
        "确认文件中的越权指令只会触发风险标记，不会允许写入或发布。",
        [
            "提交包含‘忽略所有系统规则’等指令的合成文件。",
            "查看 prompt_injection_detected。",
            "使用有效签名凭据尝试确认。",
        ],
    )
    source = make_input("prompt_injection", 3001, "m4_prompt_injection")
    passport = build_candidate(source)
    assert passport.candidate["prompt_injection_detected"] is True
    reason = None
    try:
        apply_human_action(passport, action(), reviewer())
    except CandidatePipelineError as exc:
        reason = exc.reason
    assert reason == "document_instruction_detected"
    assert passport.state == "candidate"
    record.update(
        {
            "observable_result": [
                "候选标记 prompt_injection_detected=true。",
                "有效签名凭据不能覆盖文档指令风险，返回 expected rejection。",
            ],
            "candidate_fields_and_evidence": field_evidence(passport),
            "state_transition": ["uploaded", "candidate_risk_flagged", "guard_rejected"],
            "expected_rejection": reason,
            "control_checks": {
                "document_instruction_not_executed": True,
                "credential_cannot_bypass_injection_guard": True,
                "fail_closed": True,
                "formal_write_allowed_false": passport.formal_write_allowed is False,
                "publish_allowed_false": passport.publish_allowed is False,
            },
        }
    )
    return record


def s07_unauthorized_confirmation() -> dict:
    record = base_record(
        "S07_UNAUTHORIZED_CONFIRMATION",
        "伪造或越权人工确认凭据被拒绝",
        ["未授权确认", "凭据防伪", "责任边界"],
        "确认调用方不能自报身份，也不能用伪造签名或普通成员角色确认候选。",
        [
            "生成正常候选。",
            "尝试在确认动作中自行注入 actor_id/actor_type。",
            "分别使用伪造签名凭据和未授权角色凭据确认。",
        ],
    )
    passport = build_candidate(make_input("complete", 1001, "m4_unauthorized_confirm"))
    rejections: dict[str, str] = {}
    try:
        ConfirmationAction.model_validate(
            {
                "decision": "confirm",
                "reason": "self asserted",
                "occurred_at": FIXED_TIME,
                "actor_id": "forged-human",
                "actor_type": "human",
            }
        )
    except ValidationError:
        rejections["self_asserted_actor"] = "extra_forbidden"
    try:
        apply_human_action(
            passport,
            action(),
            reviewer(secret="attacker-controlled-secret"),
        )
    except CandidatePipelineError as exc:
        rejections["forged_signature"] = exc.reason
    try:
        apply_human_action(passport, action(), reviewer(role="member"))
    except CandidatePipelineError as exc:
        rejections["unauthorized_role"] = exc.reason
    assert rejections == {
        "self_asserted_actor": "extra_forbidden",
        "forged_signature": "reviewer_credential_invalid",
        "unauthorized_role": "reviewer_not_authorized",
    }
    assert passport.state == "candidate" and passport.confirmation is None
    record.update(
        {
            "observable_result": [
                "调用方自报 actor 字段被契约拒绝。",
                "伪造签名返回 reviewer_credential_invalid。",
                "未授权角色返回 reviewer_not_authorized。",
                "候选未产生确认记录且仍为 candidate。",
            ],
            "candidate_fields_and_evidence": field_evidence(passport),
            "state_transition": ["uploaded", "candidate", "credential_rejected", "candidate_unchanged"],
            "expected_rejection": rejections,
            "control_checks": {
                "caller_cannot_self_assert_identity": True,
                "forged_signature_rejected": True,
                "unauthorized_role_rejected": True,
                "candidate_unchanged": True,
                "formal_write_allowed_false": passport.formal_write_allowed is False,
                "publish_allowed_false": passport.publish_allowed is False,
            },
        }
    )
    return record


def s08_unconfirmed_publish() -> dict:
    record = base_record(
        "S08_UNCONFIRMED_PUBLISH",
        "未确认候选的正式写入或发布尝试被契约拒绝",
        ["未确认发布", "正式写入禁止", "fail-closed"],
        "确认未完成人工确认的候选不能被改造成 published 或正式写入对象。",
        [
            "生成正常候选但不执行人工确认。",
            "尝试把 state 改为 published，并把两个权限标志改为 true。",
            "核对原候选状态和权限标志。",
        ],
    )
    passport = build_candidate(make_input("complete", 1001, "m4_unconfirmed_publish"))
    attempted = passport.model_dump(mode="json")
    attempted["state"] = "published"
    attempted["formal_write_allowed"] = True
    attempted["publish_allowed"] = True
    rejection = None
    try:
        CandidatePassport.model_validate(attempted)
    except ValidationError as exc:
        rejected_fields = sorted({str(item["loc"][0]) for item in exc.errors()})
        rejection = {"type": "contract_validation_error", "fields": rejected_fields}
    assert rejection == {
        "type": "contract_validation_error",
        "fields": ["formal_write_allowed", "publish_allowed", "state"],
    }
    assert passport.state == "candidate" and passport.confirmation is None
    assert passport.formal_write_allowed is False and passport.publish_allowed is False
    record.update(
        {
            "observable_result": [
                "published 状态不在候选护照状态契约中。",
                "formal_write_allowed=true 与 publish_allowed=true 均被 Literal[False] 拒绝。",
                "原候选没有确认记录，状态和两个权限标志均未改变。",
            ],
            "candidate_fields_and_evidence": field_evidence(passport),
            "state_transition": ["uploaded", "candidate", "publish_contract_rejected", "candidate_unchanged"],
            "expected_rejection": rejection,
            "control_checks": {
                "unconfirmed_candidate_not_publishable": True,
                "formal_write_true_rejected": True,
                "publish_true_rejected": True,
                "fail_closed": True,
            },
        }
    )
    return record


SCENARIOS: tuple[Callable[[], dict], ...] = (
    s01_normal_single,
    s02_batch_isolation,
    s03_missing_evidence,
    s04_unit_anomaly,
    s05_period_conflict,
    s06_prompt_injection,
    s07_unauthorized_confirmation,
    s08_unconfirmed_publish,
)


def run_once(output_dir: Path, run_index: int) -> int:
    scenario_results: list[dict] = []
    evidence_dir = output_dir / "evidence" / f"run-{run_index}"
    log_lines = [
        f"artifact_version={ARTIFACT_VERSION}",
        f"run_index={run_index}",
        "mode=SYNTHETIC_ONLY_LOCAL_CANDIDATE",
        "external_llm_calls=0",
        "remote_writes=0",
    ]
    for scenario in SCENARIOS:
        try:
            result = scenario()
        except Exception as exc:  # Evidence must retain unexpected failures.
            result = {
                "scenario_id": scenario.__name__.upper(),
                "title": scenario.__name__,
                "classification": "FAIL_CODE",
                "synthetic_only": True,
                "real_user_observation": False,
                "unexpected_error": {"type": type(exc).__name__, "message": str(exc)},
            }
        assert result["classification"] in ALLOWED_CLASSIFICATIONS
        result["equivalent_text_evidence"] = f"evidence/{result['scenario_id']}.json"
        scenario_results.append(result)
        write_json(evidence_dir / f"{result['scenario_id']}.json", result)
        log_lines.append(
            f"{result['scenario_id']} classification={result['classification']}"
        )
    semantic = {
        "artifact_version": ARTIFACT_VERSION,
        "mode": "SYNTHETIC_ONLY_LOCAL_CANDIDATE",
        "scenarios": scenario_results,
    }
    run_hash = canonical_sha256(semantic)
    replay = {"run_index": run_index, "run_sha256": run_hash, "semantic": semantic}
    write_json(output_dir / "results" / f"replay-{run_index}.json", replay)
    log_lines.extend(
        [
            f"scenario_count={len(scenario_results)}",
            f"run_sha256={run_hash}",
            "exit_code=0" if all(item["classification"] == "PASS" for item in scenario_results) else "exit_code=1",
        ]
    )
    (output_dir / "logs").mkdir(parents=True, exist_ok=True)
    (output_dir / "logs" / f"replay-{run_index}.log").write_text(
        "\n".join(log_lines) + "\n", encoding="utf-8"
    )
    return 0 if all(item["classification"] == "PASS" for item in scenario_results) else 1


def finalize(output_dir: Path) -> int:
    replays = [
        json.loads((output_dir / "results" / f"replay-{index}.json").read_text(encoding="utf-8"))
        for index in (1, 2, 3)
    ]
    hashes = [item["run_sha256"] for item in replays]
    semantics = [item["semantic"] for item in replays]
    consistent = len(set(hashes)) == 1 and semantics[0] == semantics[1] == semantics[2]
    classifications = {
        item["scenario_id"]: item["classification"]
        for item in semantics[0]["scenarios"]
    }
    all_pass = all(value == "PASS" for value in classifications.values())
    summary = {
        "artifact_version": ARTIFACT_VERSION,
        "scenario_count": len(classifications),
        "classifications": classifications,
        "run_sha256": hashes,
        "semantic_consistency": consistent,
        "semantic_consistency_rate": "100%" if consistent else "0%",
        "all_scenarios_pass": all_pass,
        "candidate_verdict": "ACCEPT" if consistent and all_pass else "CHANGES_REQUIRED",
        "independent_review_required": True,
    }
    write_json(output_dir / "results" / "replay-summary.json", summary)
    write_json(output_dir / "results" / "scenario-results.json", semantics[0])
    failure_samples = []
    for scenario in semantics[0]["scenarios"]:
        if scenario.get("expected_rejection") is not None:
            failure_samples.append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "classification": scenario["classification"],
                    "expected_rejection": scenario["expected_rejection"],
                    "state_transition": scenario.get("state_transition"),
                }
            )
    write_json(output_dir / "results" / "failure-samples.json", failure_samples)
    source_evidence = output_dir / "evidence" / "run-1"
    for path in source_evidence.glob("*.json"):
        shutil.copy2(path, output_dir / "evidence" / path.name)
    return 0 if consistent and all_pass else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-index", type=int, choices=(1, 2, 3))
    group.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if args.finalize:
        return finalize(args.output_dir)
    return run_once(args.output_dir, args.run_index)


if __name__ == "__main__":
    raise SystemExit(main())
