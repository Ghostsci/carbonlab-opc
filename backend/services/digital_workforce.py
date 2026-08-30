"""Governed digital-workforce contracts and evidence-quality gate.

The role names in this module are not decorative personas.  Each contract
defines what a role may do, what it must not do, and where a human decision is
required.  The quality-review token is a short-lived capability: it proves that
the exact signed candidate passed an independent evidence check before a human
is allowed to write it to the formal activity ledger.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from jose import JWTError, jwt

from backend.auth.jwt import ALGORITHM, SECRET_KEY
from backend.services.built_in_skills import get_skill_for_role, load_built_in_skills
from backend.services.candidate_confirmation import canonical_sha256


WORKFORCE_CONTRACT_VERSION = "carbon-passport-workforce-v1.0"
QUALITY_REVIEW_AUDIENCE = "carbonlab-document-evidence-quality-review"
QUALITY_REVIEW_TOKEN_TTL_MINUTES = 10
ACCEPTED_QUALITY_STATUSES = {"pass", "pass_with_warnings"}


class QualityReviewError(ValueError):
    """Raised when a quality-review capability is invalid or cannot authorize a write."""


ROLE_CONTRACTS: tuple[dict[str, Any], ...] = (
    {
        "role_id": "H-00",
        "stage_key": "source_submission",
        "display_name": "企业数据提供人",
        "kind": "human",
        "mission": "提供原始业务资料并说明真实业务背景。",
        "allowed_actions": ["上传原始资料", "补充业务说明"],
        "forbidden_actions": ["要求系统隐藏缺失资料", "用口头说明替代原始证据"],
        "human_gate": True,
    },
    {
        "role_id": "A-01",
        "stage_key": "document_intake",
        "display_name": "碳数据收件员",
        "kind": "ai_agent",
        "mission": "接收文件，完成分类、去重和基础完整性检查。",
        "allowed_actions": ["识别文件类型", "计算文件哈希", "标记重复与缺失"],
        "forbidden_actions": ["修改原文件", "猜测缺失事实", "写入正式账本"],
        "human_gate": False,
    },
    {
        "role_id": "A-02",
        "stage_key": "evidence_extraction",
        "display_name": "碳证据提取员",
        "kind": "ai_agent",
        "mission": "从文件中提出结构化字段候选，并保留来源关联。",
        "allowed_actions": ["提取候选字段", "返回覆盖度", "关联源文件"],
        "forbidden_actions": ["把候选当成事实", "静默改精度", "编造字段或证据"],
        "human_gate": False,
    },
    {
        "role_id": "A-03",
        "stage_key": "evidence_quality_review",
        "display_name": "碳数据质检员",
        "kind": "ai_agent",
        "mission": "独立检查候选字段与证据、单位和数据约束是否一致。",
        "allowed_actions": ["字段—证据匹配", "单位与正值检查", "输出异常清单"],
        "forbidden_actions": ["自动修复事实", "代替人工确认", "批准正式发布"],
        "human_gate": False,
    },
    {
        "role_id": "H-01",
        "stage_key": "enterprise_confirmation",
        "display_name": "企业数据确认人",
        "kind": "human",
        "mission": "对照原始证据修改、拒绝或确认候选字段。",
        "allowed_actions": ["修改候选", "说明异常", "确认写入"],
        "forbidden_actions": ["绕过质检门禁", "替换不属于本企业的证据"],
        "human_gate": True,
    },
    {
        "role_id": "H-02",
        "stage_key": "methodology_review",
        "display_name": "方法与复核负责人",
        "kind": "human",
        "mission": "确定核算边界、方法学和适用排放因子版本。",
        "allowed_actions": ["选择方法学", "批准适用因子", "处理例外"],
        "forbidden_actions": ["使用无来源规则", "把内部复核冒充法定核查"],
        "human_gate": True,
    },
    {
        "role_id": "R-01",
        "stage_key": "deterministic_calculation",
        "display_name": "碳核算执行员",
        "kind": "deterministic_engine",
        "mission": "按获批输入和规则版本进行精确、可重放的确定性计算。",
        "allowed_actions": ["Decimal 精确计算", "单位换算", "结果重放"],
        "forbidden_actions": ["自行选择方法学", "推断缺失数值", "调用 LLM 生成结果"],
        "human_gate": False,
    },
    {
        "role_id": "A-04",
        "stage_key": "passport_compilation",
        "display_name": "碳护照编制员",
        "kind": "ai_agent",
        "mission": "把身份、证据、确认指纹、规则和计算结果装配成护照草稿。",
        "allowed_actions": ["汇总正式记录", "生成并冻结候选草稿", "标记缺失项"],
        "forbidden_actions": ["篡改正式记录", "批准方法学", "对外发布或共享"],
        "human_gate": False,
    },
    {
        "role_id": "H-03",
        "stage_key": "authorized_release",
        "display_name": "授权发布负责人",
        "kind": "human",
        "mission": "完成最终复核，冻结版本并决定发布与共享范围。",
        "allowed_actions": ["最终复核", "冻结与发布", "创建最小权限共享"],
        "forbidden_actions": ["发布未通过门禁的草稿", "删除既有审计记录"],
        "human_gate": True,
    },
)

WORKFLOW_SEQUENCE = tuple(role["stage_key"] for role in ROLE_CONTRACTS)

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "electricity_kwh": ("electricity_kwh", "用电量", "activity_quantity", "quantity"),
    "period": ("period", "账单月份", "billing_month", "date", "抄表日期"),
    "facility": ("facility", "所属工厂", "customer_name"),
}


def workforce_contract_payload() -> dict[str, Any]:
    roles = []
    for role in ROLE_CONTRACTS:
        skill = get_skill_for_role(role["role_id"])
        roles.append(
            {
                **dict(role),
                "skill": skill.to_dict() if skill else None,
            }
        )
    return {
        "contract_version": WORKFORCE_CONTRACT_VERSION,
        "workflow_name": "工厂碳数据护照受控工作流",
        "principle": "AI 提议，规则检查，人类确认，确定性计算，授权发布。",
        "sequence": list(WORKFLOW_SEQUENCE),
        "roles": roles,
        "built_in_skill_count": len(load_built_in_skills()),
    }


def _field(fields: dict[str, Any], aliases: tuple[str, ...]) -> tuple[str | None, Any]:
    for alias in aliases:
        if alias in fields and fields[alias] not in (None, ""):
            return alias, fields[alias]
    return None, None


def _normalized(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value).lower())


def _source_supports(
    value: Any,
    *,
    aliases: tuple[str, ...],
    source_fields: dict[str, Any],
    raw_text: str,
) -> bool | None:
    needle = _normalized(value)
    if not needle:
        return False
    normalized_aliases = {_normalized(alias) for alias in aliases}
    haystacks = [
        _normalized(item)
        for key, item in source_fields.items()
        if item not in (None, "")
        and any(
            alias == _normalized(key)
            or alias in _normalized(key)
            or _normalized(key) in alias
            for alias in normalized_aliases
        )
    ]
    normalized_raw = _normalized(raw_text)
    if not source_fields and not normalized_raw:
        return None
    # Raw-document occurrence alone cannot prove that a value supports this
    # specific field.  Only a value attached to the corresponding source-field
    # aliases can produce a positive field-to-evidence result.
    return any(needle == item or needle in item or item in needle for item in haystacks)


def _finding(
    check_key: str,
    label: str,
    result: str,
    message: str,
    *,
    evidence_ref: str | None = None,
    field_key: str | None = None,
    source_locator: dict[str, Any] | None = None,
    observed_value: Any = None,
    expected_value: Any = None,
) -> dict[str, Any]:
    human_action = (
        "confirm_source"
        if result == "warning"
        else "correct_and_rerun"
        if result == "fail"
        else "none"
    )
    return {
        "check_key": check_key,
        "label": label,
        "result": result,
        "message": message,
        "evidence_ref": evidence_ref,
        "field_key": field_key,
        "source_locator": _compact_locator(source_locator),
        "observed_value": None if observed_value is None else str(observed_value),
        "expected_value": None if expected_value is None else str(expected_value),
        "human_action": human_action,
        "requires_human_resolution": result == "warning",
    }


def _compact_locator(locator: Any) -> dict[str, Any] | None:
    if not isinstance(locator, dict):
        return None
    allowed = {
        "kind",
        "sheet",
        "row",
        "column",
        "column_label",
        "cell",
        "header_cell",
        "header",
        "raw_value",
        "unit",
        "unit_source",
        "text_line_start",
        "text_line_end",
        "excerpt",
    }
    compact = {key: value for key, value in locator.items() if key in allowed and value not in (None, "")}
    return compact or None


def _locator_label(locator: dict[str, Any] | None) -> str:
    if not locator:
        return "原文件（未能自动定位）"
    if locator.get("sheet") and locator.get("cell"):
        return f"工作表“{locator['sheet']}”单元格 {locator['cell']}"
    if locator.get("cell"):
        return f"单元格 {locator['cell']}"
    if locator.get("text_line_start"):
        return f"原文第 {locator['text_line_start']} 行"
    return "原文件（未能自动定位）"


def evaluate_document_quality(
    *,
    document_type: str,
    document_content_hash: str,
    fields: dict[str, Any],
    source_snapshot: dict[str, Any] | None,
    retrieval_evidence: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run deterministic checks without deciding whether the business fact is true."""
    findings: list[dict[str, Any]] = []
    source_snapshot = source_snapshot or {}
    source_fields = source_snapshot.get("fields")
    if not isinstance(source_fields, dict):
        source_fields = {}
    raw_text = source_snapshot.get("raw_text")
    if not isinstance(raw_text, str):
        raw_text = ""
    field_sources = source_snapshot.get("field_sources")
    if not isinstance(field_sources, dict):
        field_sources = {}
    retrieval_evidence = retrieval_evidence or {}

    if document_type == "electricity_bill":
        findings.append(_finding("document_type", "文档类型", "pass", "已限定为当前闭环支持的电费活动数据。"))
    else:
        findings.append(_finding("document_type", "文档类型", "fail", "当前正式活动账本仅接受电费活动数据。"))

    if re.fullmatch(r"[0-9a-f]{64}", document_content_hash or ""):
        findings.append(_finding("source_hash", "源文件哈希", "pass", "源文件具有服务器保存的 SHA-256 身份。"))
    else:
        findings.append(_finding("source_hash", "源文件哈希", "fail", "源文件缺少有效 SHA-256 身份。"))

    selected: dict[str, tuple[str | None, Any]] = {
        key: _field(fields, aliases) for key, aliases in FIELD_ALIASES.items()
    }
    labels = {"electricity_kwh": "用电量", "period": "报告期间", "facility": "所属设施"}
    for key, (field_key, value) in selected.items():
        locator = _compact_locator(field_sources.get(key) or field_sources.get(field_key or ""))
        location = _locator_label(locator)
        if value in (None, ""):
            findings.append(
                _finding(
                    f"required_{key}",
                    labels[key],
                    "fail",
                    f"缺少{labels[key]}，禁止进入人工确认。",
                    field_key=field_key or key,
                    expected_value=f"有效的{labels[key]}",
                )
            )
            continue
        findings.append(
            _finding(
                f"required_{key}",
                labels[key],
                "pass",
                f"候选中已包含{labels[key]}。",
                evidence_ref=f"field:{field_key}",
                field_key=field_key or key,
                source_locator=locator,
                observed_value=value,
            )
        )
        needle = _normalized(value)
        retrieval = retrieval_evidence.get(key) or {}
        hits = retrieval.get("hits") if isinstance(retrieval, dict) else None
        if not isinstance(hits, list) or not hits:
            findings.append(
                _finding(
                    f"retrieval_{key}",
                    f"{labels[key]}—RAG 字段证据",
                    "warning",
                    "受控检索没有找到该字段的专属证据片段，必须由人工对照原件。",
                    evidence_ref=(
                        f"retrieval:{retrieval.get('retrieval_run_id')}"
                        if isinstance(retrieval, dict) and retrieval.get("retrieval_run_id")
                        else None
                    ),
                    field_key=field_key or key,
                    source_locator=locator,
                    observed_value=value,
                )
            )
        else:
            supported = any(
                key in (hit.get("field_keys") or [])
                and needle in _normalized(hit.get("excerpt") or "")
                for hit in hits
                if isinstance(hit, dict)
            )
            findings.append(
                _finding(
                    f"retrieval_{key}",
                    f"{labels[key]}—RAG 字段证据",
                    "pass" if supported else "warning",
                    (
                        "受控检索已返回与当前字段和值绑定的证据片段。"
                        if supported
                        else "检索命中属于当前字段，但片段未直接支持当前编辑值，禁止把相似性当作事实。"
                    ),
                    evidence_ref=f"retrieval:{retrieval.get('retrieval_run_id')}",
                    field_key=field_key or key,
                    source_locator=locator,
                    observed_value=value,
                )
            )
        support = _source_supports(
            value,
            aliases=FIELD_ALIASES[key],
            source_fields=source_fields,
            raw_text=raw_text,
        )
        if support is True:
            result = "pass"
            message = f"{labels[key]}可在{location}定位。"
        elif support is None:
            result = "warning"
            message = f"源文件没有可搜索文本，{labels[key]}必须由人工打开原件确认。"
        else:
            result = "warning"
            message = f"{labels[key]}与识别快照不完全一致；请到{location}核对并说明。"
        findings.append(
            _finding(
                f"evidence_{key}",
                f"{labels[key]}—证据关联",
                result,
                message,
                evidence_ref=f"document:{document_content_hash[:16]}",
                field_key=field_key or key,
                source_locator=locator,
                observed_value=value,
            )
        )

    quantity_value = selected["electricity_kwh"][1]
    quantity_field_key = selected["electricity_kwh"][0] or "electricity_kwh"
    quantity_locator = _compact_locator(
        field_sources.get("electricity_kwh") or field_sources.get(quantity_field_key)
    )
    if isinstance(quantity_value, bool | float):
        findings.append(
            _finding(
                "quantity_exactness",
                "数值精度",
                "fail",
                "用电量不得使用二进制浮点数。",
                field_key=quantity_field_key,
                source_locator=quantity_locator,
                observed_value=quantity_value,
                expected_value="十进制定点数",
            )
        )
    elif quantity_value not in (None, ""):
        match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", str(quantity_value))
        try:
            number = Decimal(match.group(0).replace(",", "")) if match else None
        except InvalidOperation:
            number = None
        if number is None or number <= 0:
            findings.append(
                _finding(
                    "quantity_positive",
                    "用电量约束",
                    "fail",
                    "用电量必须是大于零的精确数值。",
                    field_key=quantity_field_key,
                    source_locator=quantity_locator,
                    observed_value=quantity_value,
                    expected_value="> 0",
                )
            )
        else:
            findings.append(
                _finding(
                    "quantity_positive",
                    "用电量约束",
                    "pass",
                    "用电量为正数，且可按十进制定点值解析。",
                    field_key=quantity_field_key,
                    source_locator=quantity_locator,
                    observed_value=quantity_value,
                    expected_value="> 0",
                )
            )

        unit_match = re.search(r"(?i)(kwh|mwh|wh|gj|mj|t|kg)\b", str(quantity_value))
        source_unit = str((quantity_locator or {}).get("unit") or "").strip()
        source_location = _locator_label(quantity_locator)
        if unit_match and unit_match.group(1).lower() != "kwh":
            findings.append(
                _finding(
                    "quantity_unit",
                    "用电量单位",
                    "fail",
                    f"当前字段单位为 {unit_match.group(1)}，不能静默按 kWh 写入。",
                    field_key=quantity_field_key,
                    source_locator=quantity_locator,
                    observed_value=unit_match.group(1),
                    expected_value="kWh",
                )
            )
        elif unit_match:
            findings.append(
                _finding(
                    "quantity_unit",
                    "用电量单位",
                    "pass",
                    "候选值明确标注为 kWh。",
                    field_key=quantity_field_key,
                    source_locator=quantity_locator,
                    observed_value="kWh",
                    expected_value="kWh",
                )
            )
        elif source_unit.lower() == "kwh":
            findings.append(
                _finding(
                    "quantity_unit",
                    "用电量单位",
                    "pass",
                    f"候选数字未重复携带单位，但{source_location}的表头/单位列明确标注为 kWh。",
                    field_key=quantity_field_key,
                    source_locator=quantity_locator,
                    observed_value=source_unit,
                    expected_value="kWh",
                )
            )
        elif source_unit:
            findings.append(
                _finding(
                    "quantity_unit",
                    "用电量单位",
                    "fail",
                    f"{source_location}标注的单位是 {source_unit}，不能静默按 kWh 写入。",
                    field_key=quantity_field_key,
                    source_locator=quantity_locator,
                    observed_value=source_unit,
                    expected_value="kWh",
                )
            )
        else:
            findings.append(
                _finding(
                    "quantity_unit",
                    "用电量单位",
                    "warning",
                    f"候选值和可定位的原文上下文都没有明确单位；请到{source_location}确认是否为 kWh。",
                    field_key=quantity_field_key,
                    source_locator=quantity_locator,
                    observed_value="未识别到单位",
                    expected_value="kWh",
                )
            )

    failed = sum(item["result"] == "fail" for item in findings)
    warned = sum(item["result"] == "warning" for item in findings)
    passed = sum(item["result"] == "pass" for item in findings)
    total = max(1, len(findings))
    score = max(0, min(100, round(((passed + warned * 0.5) / total) * 100)))
    quality_status = "fail" if failed else "pass_with_warnings" if warned else "pass"
    resolution_required_keys = [
        item["check_key"] for item in findings if item["requires_human_resolution"]
    ]
    return {
        "quality_status": quality_status,
        "score": score,
        "summary": (
            "发现阻断项，禁止写入正式账本。"
            if failed
            else "质检通过，但存在必须由人工确认的提示。"
            if warned
            else "字段、单位和源文件关联检查均通过。"
        ),
        "counts": {"passed": passed, "warnings": warned, "failed": failed},
        "findings": findings,
        "retrievals": retrieval_evidence,
        "human_confirmation_required": True,
        "human_resolution_required": bool(resolution_required_keys),
        "resolution_required_keys": resolution_required_keys,
        "warnings_resolved": not resolution_required_keys,
        "score_label": "自动质检覆盖得分（不等于事实准确率）",
    }


def issue_quality_review(
    *,
    actor_user_id: str,
    tenant_id: str,
    enterprise_id: str,
    file_id: str,
    document_content_hash: str,
    candidate: dict[str, str],
    result: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    issued_at = now or datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=QUALITY_REVIEW_TOKEN_TTL_MINUTES)
    review_id = uuid.uuid4().hex
    result_hash = canonical_sha256(result)
    resolution_required_keys = [
        str(item) for item in result.get("resolution_required_keys", []) if str(item)
    ]
    claims = {
        "sub": actor_user_id,
        "aud": QUALITY_REVIEW_AUDIENCE,
        "type": "document_evidence_quality_review",
        "jti": review_id,
        "iat": issued_at,
        "exp": expires_at,
        "tenant_id": tenant_id,
        "enterprise_id": enterprise_id,
        "file_id": file_id,
        "document_content_hash": document_content_hash,
        "candidate_id": candidate["candidate_id"],
        "candidate_fields_sha256": candidate["fields_sha256"],
        "candidate_subject_sha256": candidate["subject_sha256"],
        "quality_status": result["quality_status"],
        "quality_score": result["score"],
        "quality_result_sha256": result_hash,
        "resolution_required_keys": resolution_required_keys,
        "warnings_resolved": not resolution_required_keys,
        "contract_version": WORKFORCE_CONTRACT_VERSION,
    }
    return {
        "quality_review_id": review_id,
        "quality_review_token": jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM),
        "quality_result_sha256": result_hash,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "resolution_required_keys": resolution_required_keys,
        "warnings_resolved": not resolution_required_keys,
    }


def _validated_quality_review_claims(
    token: str,
    *,
    actor_user_id: str,
    tenant_id: str,
    enterprise_id: str,
    file_id: str,
    document_content_hash: str,
    candidate: dict[str, str],
) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=QUALITY_REVIEW_AUDIENCE,
            options={"require_exp": True, "require_sub": True, "require_aud": True},
        )
    except JWTError as exc:
        raise QualityReviewError("质检结果签名无效或已过期，请重新运行 A-03 质检") from exc
    if claims.get("type") != "document_evidence_quality_review":
        raise QualityReviewError("质检结果类型无效")
    expected = {
        "sub": actor_user_id,
        "tenant_id": tenant_id,
        "enterprise_id": enterprise_id,
        "file_id": file_id,
        "document_content_hash": document_content_hash,
        "candidate_id": candidate["candidate_id"],
        "candidate_fields_sha256": candidate["fields_sha256"],
        "candidate_subject_sha256": candidate["subject_sha256"],
        "contract_version": WORKFORCE_CONTRACT_VERSION,
    }
    if any(claims.get(key) != value for key, value in expected.items()):
        raise QualityReviewError("质检结果与当前候选、源文件或操作者不一致")
    quality_status = claims.get("quality_status")
    if quality_status not in ACCEPTED_QUALITY_STATUSES:
        raise QualityReviewError("A-03 质检存在阻断项，禁止写入正式账本")
    review_id = claims.get("jti")
    result_hash = claims.get("quality_result_sha256")
    score = claims.get("quality_score")
    if not isinstance(review_id, str) or not review_id:
        raise QualityReviewError("质检结果缺少唯一标识")
    if not isinstance(result_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", result_hash):
        raise QualityReviewError("质检结果缺少有效内容哈希")
    if not isinstance(score, int):
        raise QualityReviewError("质检结果分数格式无效")
    required_keys = claims.get("resolution_required_keys") or []
    if not isinstance(required_keys, list) or not all(isinstance(item, str) and item for item in required_keys):
        raise QualityReviewError("质检结果的人工处置清单格式无效")
    if claims.get("warnings_resolved") not in {True, False}:
        raise QualityReviewError("质检结果缺少人工处置状态")
    return claims


def verify_quality_review(
    token: str,
    *,
    actor_user_id: str,
    tenant_id: str,
    enterprise_id: str,
    file_id: str,
    document_content_hash: str,
    candidate: dict[str, str],
    require_warning_resolution: bool = True,
) -> dict[str, Any]:
    claims = _validated_quality_review_claims(
        token,
        actor_user_id=actor_user_id,
        tenant_id=tenant_id,
        enterprise_id=enterprise_id,
        file_id=file_id,
        document_content_hash=document_content_hash,
        candidate=candidate,
    )
    required_keys = list(claims.get("resolution_required_keys") or [])
    warnings_resolved = bool(claims.get("warnings_resolved"))
    if require_warning_resolution and required_keys and not warnings_resolved:
        raise QualityReviewError("A-03 仍有提示未由 H-01 逐项核对，请先定位原文并提交人工处置说明")
    return {
        "quality_review_id": str(claims["jti"]),
        "quality_status": str(claims["quality_status"]),
        "quality_score": int(claims["quality_score"]),
        "quality_result_sha256": str(claims["quality_result_sha256"]),
        "contract_version": WORKFORCE_CONTRACT_VERSION,
        "resolution_required_keys": required_keys,
        "warnings_resolved": warnings_resolved,
        "resolution_sha256": claims.get("resolution_sha256"),
        "resolved_at": claims.get("resolved_at"),
    }


def resolve_quality_review(
    token: str,
    *,
    actor_user_id: str,
    tenant_id: str,
    enterprise_id: str,
    file_id: str,
    document_content_hash: str,
    candidate: dict[str, str],
    resolutions: list[dict[str, str]],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Bind explicit H-01 dispositions to every non-blocking A-03 warning."""
    claims = _validated_quality_review_claims(
        token,
        actor_user_id=actor_user_id,
        tenant_id=tenant_id,
        enterprise_id=enterprise_id,
        file_id=file_id,
        document_content_hash=document_content_hash,
        candidate=candidate,
    )
    required = list(claims.get("resolution_required_keys") or [])
    if not required:
        raise QualityReviewError("当前质检没有需要单独处置的提示")

    by_key: dict[str, dict[str, str]] = {}
    for resolution in resolutions:
        check_key = str(resolution.get("check_key") or "").strip()
        decision = str(resolution.get("decision") or "").strip()
        reason = str(resolution.get("reason") or "").strip()
        if check_key in by_key:
            raise QualityReviewError(f"人工处置项重复：{check_key}")
        if decision != "confirmed_source":
            raise QualityReviewError(f"人工处置动作无效：{check_key}")
        if len(reason) < 8:
            raise QualityReviewError(f"人工处置说明过短：{check_key}")
        by_key[check_key] = {
            "check_key": check_key,
            "decision": decision,
            "reason": reason,
        }

    missing = [check_key for check_key in required if check_key not in by_key]
    unexpected = sorted(set(by_key) - set(required))
    if missing:
        raise QualityReviewError(f"仍有未处置的 A-03 提示：{', '.join(missing)}")
    if unexpected:
        raise QualityReviewError(f"提交了不属于本次质检的处置项：{', '.join(unexpected)}")

    ordered = [by_key[check_key] for check_key in required]
    resolved_at = now or datetime.now(timezone.utc)
    resolution_sha256 = canonical_sha256(
        {
            "quality_review_id": claims["jti"],
            "actor_user_id": actor_user_id,
            "resolutions": ordered,
        }
    )
    updated_claims = dict(claims)
    updated_claims.update(
        {
            "warnings_resolved": True,
            "resolution_sha256": resolution_sha256,
            "resolution_keys": required,
            "resolved_at": resolved_at.isoformat(),
        }
    )
    return {
        "quality_review_id": str(claims["jti"]),
        "quality_review_token": jwt.encode(updated_claims, SECRET_KEY, algorithm=ALGORITHM),
        "quality_status": str(claims["quality_status"]),
        "quality_score": int(claims["quality_score"]),
        "quality_result_sha256": str(claims["quality_result_sha256"]),
        "resolution_required_keys": required,
        "warnings_resolved": True,
        "resolution_sha256": resolution_sha256,
        "resolved_at": resolved_at.isoformat(),
        "resolutions": ordered,
        "expires_at": datetime.fromtimestamp(int(claims["exp"]), timezone.utc).isoformat(),
    }
