"""Factory carbon-data passport API."""

from __future__ import annotations

from datetime import datetime
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.database import get_db
from backend.models.user import User
from backend.ai.rag import get_rag_service
from backend.services.agent_ops import (
    append_agent_run_event,
    complete_agent_run,
    start_agent_run,
)
from backend.services.rule_records import resolve_rule_record
from backend.services.installation_passport import (
    PassportConflict,
    add_production_output,
    add_source_attribution,
    access_shared_package,
    calculate_passport_see,
    create_methodology_review,
    create_passport_account,
    create_profile_snapshot,
    create_sharing_grant,
    emission_result_plain_view,
    export_shared_package,
    grant_payload,
    list_passport_accounts,
    list_authoritative_rules,
    list_emission_candidates,
    list_received_grants,
    passport_detail,
    profile_payload,
    publish_profile_version,
    register_authoritative_rule,
    revoke_sharing_grant,
    revocation_payload,
    review_payload,
    validate_passport_identity,
)


router = APIRouter(prefix="/passports", tags=["installation-passports"])


class CreatePassportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_key: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    installation_name: str = Field(min_length=1, max_length=255)
    operator_name: str = Field(min_length=1, max_length=255)
    country_code: str = Field(default="CN", min_length=2, max_length=2)
    unlocode: str | None = Field(default=None, min_length=5, max_length=5)
    process_name: str = Field(min_length=1, max_length=255)
    aggregate_goods_category: str = Field(min_length=1, max_length=64)
    production_route: str = Field(min_length=1, max_length=32)
    product_name: str = Field(min_length=1, max_length=255)
    cn_code: str = Field(pattern=r"^\d{8}$")

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        normalized = value.upper()
        if not re.fullmatch(r"[A-Z]{2}", normalized):
            raise ValueError("country_code must be two uppercase letters")
        return normalized

    @field_validator("unlocode")
    @classmethod
    def normalize_unlocode(cls, value: str | None) -> str | None:
        return value.upper() if value else None


class CreateProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_start: datetime
    period_end: datetime


class CreateMethodologyReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    profile_version_id: uuid.UUID
    verdict: str = Field(pattern=r"^(pass|pass_with_actions|fail)$")
    summary: str = Field(min_length=1, max_length=1000)
    findings: list[dict] = Field(default_factory=list, max_length=100)


class PublishProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_version_id: uuid.UUID
    methodology_review_id: uuid.UUID


class AddProductionOutputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    process_id: uuid.UUID
    product_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    quantity: str | int
    unit: str = Field(min_length=1, max_length=64)

    @field_validator("quantity", mode="before")
    @classmethod
    def reject_float_quantity(cls, value):
        if isinstance(value, bool | float):
            raise ValueError("formal quantity rejects binary float values")
        return value


class AddAttributionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    process_id: uuid.UUID
    emission_result_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    share: str | int
    method: str = Field(min_length=1, max_length=64)

    @field_validator("share", mode="before")
    @classmethod
    def reject_float_share(cls, value):
        if isinstance(value, bool | float):
            raise ValueError("formal attribution rejects binary float values")
        return value


class RegisterRuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    rule_kind: str = Field(pattern=r"^(cbam_methodology|precursor_default)$")
    title: str = Field(min_length=1, max_length=255)
    publisher: str = Field(min_length=1, max_length=255)
    document_number: str = Field(min_length=1, max_length=128)
    jurisdiction: str = Field(min_length=1, max_length=32)
    vintage: int = Field(ge=1900, le=9999)
    valid_from: datetime
    valid_to: datetime | None = None
    source_url: str = Field(min_length=8, max_length=2000)
    source_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class CalculateSEERequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    process_id: uuid.UUID
    product_id: uuid.UUID
    production_output_id: uuid.UUID
    methodology_ref: str = Field(pattern=r"^rule_record:[0-9a-fA-F-]{36}$")


class MethodologySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    period_start: datetime
    period_end: datetime
    query: str | None = Field(default=None, max_length=500)
    jurisdiction: str = Field(default="EU", pattern=r"^[A-Z]{2,8}$")
    top_k: int = Field(default=5, ge=1, le=10)


class CreateSharingGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    profile_version_id: uuid.UUID
    recipient_name: str = Field(min_length=1, max_length=255)
    recipient_type: str = Field(
        pattern=r"^(importer|trader|verifier|software_partner|customer|other)$"
    )
    recipient_tenant_id: uuid.UUID | None = None
    purpose: str = Field(min_length=1, max_length=500)
    scopes: list[str] = Field(min_length=1, max_length=8)
    expires_at: datetime


class RevokeSharingGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(min_length=1, max_length=500)


def _context(user: User) -> tuple[uuid.UUID, uuid.UUID]:
    if not user.tenant_id or not user.enterprise_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前用户未绑定租户或企业",
        )
    return user.tenant_id, user.enterprise_id


@router.get("")
def list_passports(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, _enterprise_id = _context(user)
    return list_passport_accounts(db, tenant_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_passport(
    req: CreatePassportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, enterprise_id = _context(user)
    try:
        validate_passport_identity(**req.model_dump(exclude={"request_key"}))
        account = create_passport_account(
            db,
            tenant_id=tenant_id,
            enterprise_id=enterprise_id,
            actor_id=user.id,
            **req.model_dump(),
        )
        db.commit()
        return passport_detail(db, tenant_id=tenant_id, account_id=account.id)
    except (LookupError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PassportConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/rules")
def get_rules(
    rule_kind: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, _enterprise_id = _context(user)
    return [_rule_payload(item) for item in list_authoritative_rules(db, tenant_id=tenant_id, rule_kind=rule_kind)]


@router.post("/rules", status_code=status.HTTP_201_CREATED)
def create_rule(
    req: RegisterRuleRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, _enterprise_id = _context(user)
    if user.role not in {"platform_admin", "admin", "manager", "auditor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无规则登记权限")
    try:
        rule = register_authoritative_rule(
            db,
            tenant_id=tenant_id,
            actor_id=user.id,
            **req.model_dump(),
        )
        get_rag_service().index_rule(db, rule)
        db.commit()
        return _rule_payload(rule)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PassportConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/shared")
def list_shared_with_me(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, _enterprise_id = _context(user)
    grants = list_received_grants(db, recipient_tenant_id=tenant_id)
    return [grant_payload(db, item) for item in grants]


@router.get("/shared/{grant_id}")
def get_shared_package(
    grant_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, _enterprise_id = _context(user)
    try:
        result = access_shared_package(
            db,
            recipient_tenant_id=tenant_id,
            grant_id=grant_id,
            actor_id=user.id,
        )
        db.commit()
        return result
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PassportConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/emission-results/{emission_result_id}/plain-view")
def get_emission_result_plain_view(
    emission_result_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Explain one formal activity-emission result without audit jargon."""
    tenant_id, enterprise_id = _context(user)
    try:
        return emission_result_plain_view(
            db,
            tenant_id=tenant_id,
            enterprise_id=enterprise_id,
            emission_result_id=emission_result_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/{account_id}")
def get_passport(
    account_id: uuid.UUID,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, _enterprise_id = _context(user)
    try:
        return passport_detail(
            db,
            tenant_id=tenant_id,
            account_id=account_id,
            period_start=period_start,
            period_end=period_end,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{account_id}/methodology-candidates")
def search_methodology_candidates(
    account_id: uuid.UUID,
    req: MethodologySearchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return applicable rule candidates; H-02 must still choose one explicitly."""
    tenant_id, enterprise_id = _context(user)
    if user.role not in {"platform_admin", "admin", "manager", "auditor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无方法学检索权限")
    if req.period_start >= req.period_end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="报告期间无效")
    try:
        detail = passport_detail(
            db,
            tenant_id=tenant_id,
            account_id=account_id,
            period_start=req.period_start,
            period_end=req.period_end,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    process = detail["processes"][0] if detail["processes"] else {}
    product = detail["products"][0] if detail["products"] else {}
    query = req.query or (
        f"CBAM 方法规则 产品 {product.get('name', '')} CN {product.get('cn_code', '')} "
        f"生产路线 {process.get('production_route', '')} 报告期 "
        f"{req.period_start.date().isoformat()} 至 {req.period_end.date().isoformat()}"
    )
    retrieval = get_rag_service().search(
        db,
        tenant_id=tenant_id,
        enterprise_id=enterprise_id,
        actor_id=user.id,
        role_id="H-02",
        purpose="methodology_rule_review",
        query_text=query,
        corpus_types={"public_methodology"},
        top_k=req.top_k,
        valid_at=req.period_start,
        jurisdiction=req.jurisdiction,
        field_key="methodology_ref",
    )
    candidates: list[dict] = []
    for hit in retrieval.hits:
        if hit.source_type != "rule_record" or not hit.source_ref:
            continue
        try:
            rule = resolve_rule_record(
                db,
                tenant_id=tenant_id,
                reference=f"rule_record:{hit.source_ref}",
                expected_kind="cbam_methodology",
                period_start=req.period_start,
                period_end=req.period_end,
            )
        except ValueError:
            continue
        candidates.append(
            {
                "rule": _rule_payload(rule),
                "retrieval": hit.model_dump(),
                "methodology_ref": f"rule_record:{rule.id}",
                "human_confirmation_required": True,
                "formal_write_allowed": False,
            }
        )
    db.commit()
    return {
        "retrieval_run_id": retrieval.retrieval_run_id,
        "ontology_version": retrieval.ontology_version,
        "embedding_model": retrieval.embedding_model,
        "candidates": candidates,
        "human_gate": "H-02 方法与复核负责人",
        "next_engine": "R-01 确定性核算执行员",
        "warning": retrieval.warning,
    }


@router.get("/{account_id}/emission-candidates")
def get_emission_candidates(
    account_id: uuid.UUID,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, _enterprise_id = _context(user)
    try:
        return list_emission_candidates(
            db,
            tenant_id=tenant_id,
            account_id=account_id,
            period_start=period_start,
            period_end=period_end,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{account_id}/outputs", status_code=status.HTTP_201_CREATED)
def create_output(
    account_id: uuid.UUID,
    req: AddProductionOutputRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, _enterprise_id = _context(user)
    try:
        record = add_production_output(
            db,
            tenant_id=tenant_id,
            account_id=account_id,
            actor_id=user.id,
            **req.model_dump(),
        )
        db.commit()
        return _output_payload(record)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{account_id}/attributions", status_code=status.HTTP_201_CREATED)
def create_attribution(
    account_id: uuid.UUID,
    req: AddAttributionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, _enterprise_id = _context(user)
    try:
        record = add_source_attribution(
            db,
            tenant_id=tenant_id,
            account_id=account_id,
            actor_id=user.id,
            **req.model_dump(),
        )
        db.commit()
        return _attribution_payload(record)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{account_id}/see-results", status_code=status.HTTP_201_CREATED)
def create_see_result(
    account_id: uuid.UUID,
    req: CalculateSEERequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, _enterprise_id = _context(user)
    try:
        record = calculate_passport_see(
            db,
            tenant_id=tenant_id,
            account_id=account_id,
            actor_id=user.id,
            **req.model_dump(),
        )
        db.commit()
        return _see_payload(record)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{account_id}/sharing-grants", status_code=status.HTTP_201_CREATED)
def create_grant(
    account_id: uuid.UUID,
    req: CreateSharingGrantRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, _enterprise_id = _context(user)
    if user.role not in {"platform_admin", "admin", "manager"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无共享授权权限")
    try:
        grant = create_sharing_grant(
            db,
            tenant_id=tenant_id,
            account_id=account_id,
            actor_id=user.id,
            **req.model_dump(),
        )
        db.commit()
        return grant_payload(db, grant)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PassportConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{account_id}/sharing-grants/{grant_id}/export")
def export_grant_package(
    account_id: uuid.UUID,
    grant_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, _enterprise_id = _context(user)
    try:
        result = export_shared_package(
            db,
            tenant_id=tenant_id,
            account_id=account_id,
            grant_id=grant_id,
            actor_id=user.id,
        )
        db.commit()
        return result
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PassportConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{account_id}/sharing-grants/{grant_id}/revoke", status_code=status.HTTP_201_CREATED)
def revoke_grant(
    account_id: uuid.UUID,
    grant_id: uuid.UUID,
    req: RevokeSharingGrantRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, _enterprise_id = _context(user)
    if user.role not in {"platform_admin", "admin", "manager"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无撤销授权权限")
    try:
        record = revoke_sharing_grant(
            db,
            tenant_id=tenant_id,
            account_id=account_id,
            grant_id=grant_id,
            actor_id=user.id,
            reason=req.reason,
        )
        db.commit()
        return revocation_payload(record)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{account_id}/profiles", status_code=status.HTTP_201_CREATED)
def create_profile(
    account_id: uuid.UUID,
    req: CreateProfileRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, _enterprise_id = _context(user)
    try:
        profile = create_profile_snapshot(
            db,
            tenant_id=tenant_id,
            account_id=account_id,
            period_start=req.period_start,
            period_end=req.period_end,
            actor_id=user.id,
        )
        compilation_run = start_agent_run(
            db,
            tenant_id=tenant_id,
            enterprise_id=user.enterprise_id,
            agent_id="A-04",
            trigger="profile_freeze",
            trigger_ref=str(account_id),
            input_snapshot={
                "account_id": str(account_id),
                "installation_id": str(profile.installation_id),
                "period_start": req.period_start,
                "period_end": req.period_end,
                "formal_record_refs": list(profile.derived_from),
            },
            summary="A-04 从正式记录装配可重放的护照草稿",
        )
        append_agent_run_event(
            db,
            run=compilation_run,
            event_type="passport_draft_compiled",
            status="warning" if profile.completeness_score < 100 else "success",
            title="护照草稿已冻结",
            summary=(
                f"完整度 {profile.completeness_score}%，数据质量 {profile.data_quality_grade}；"
                "草稿仍需 H-03 授权发布"
            ),
            payload={
                "profile_version_id": str(profile.id),
                "status": profile.status,
                "completeness_score": profile.completeness_score,
                "data_quality_grade": profile.data_quality_grade,
                "derived_from": list(profile.derived_from),
                "content_hash": profile.content_hash,
            },
            evidence_refs=list(profile.derived_from),
        )
        complete_agent_run(
            db,
            run=compilation_run,
            summary="A-04 已冻结护照草稿并先交给 H-02 方法复核，复核后再进入 H-03 发布门",
            output_snapshot={
                "profile_version_id": str(profile.id),
                "status": "ready_for_review" if profile.completeness_score == 100 else "draft",
                "completeness_score": profile.completeness_score,
                "data_quality_grade": profile.data_quality_grade,
                "derived_from": list(profile.derived_from),
                "next_gate": "H-02",
            },
            final_action={"handoff_to": "H-02", "auto_publish": False},
            evidence_refs=list(profile.derived_from),
        )
        db.commit()
        payload = profile_payload(db, profile)
        payload["agent_run_id"] = compilation_run.run_id
        return payload
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{account_id}/reviews", status_code=status.HTTP_201_CREATED)
def review_profile(
    account_id: uuid.UUID,
    req: CreateMethodologyReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, _enterprise_id = _context(user)
    if user.role not in {"platform_admin", "admin", "manager", "auditor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无方法学复核权限")
    try:
        review = create_methodology_review(
            db,
            tenant_id=tenant_id,
            account_id=account_id,
            profile_version_id=req.profile_version_id,
            reviewer_id=user.id,
            reviewer_role=user.role,
            verdict=req.verdict,
            summary=req.summary,
            findings=req.findings,
        )
        review_run = start_agent_run(
            db,
            tenant_id=tenant_id,
            enterprise_id=user.enterprise_id,
            agent_id="H-02",
            trigger="profile_review",
            trigger_ref=str(req.profile_version_id),
            input_snapshot={
                "account_id": str(account_id),
                "profile_version_id": str(req.profile_version_id),
                "verdict": req.verdict,
                "finding_count": len(req.findings),
            },
            summary="H-02 对冻结护照草稿执行方法学复核",
        )
        append_agent_run_event(
            db,
            run=review_run,
            event_type="methodology_review_recorded",
            status="blocked" if req.verdict == "fail" else (
                "warning" if req.verdict == "pass_with_actions" else "success"
            ),
            title="方法学复核已记录",
            summary=f"复核结论 {req.verdict}；该结论不等于法定 CBAM 核查",
            payload={
                "review_id": str(review.id),
                "profile_version_id": str(req.profile_version_id),
                "verdict": req.verdict,
                "finding_count": len(req.findings),
                "disclaimer": review.disclaimer,
            },
            evidence_refs=[str(req.profile_version_id), str(review.id)],
        )
        complete_agent_run(
            db,
            run=review_run,
            summary="H-02 已完成护照草稿方法学复核",
            output_snapshot={
                "review_id": str(review.id),
                "verdict": req.verdict,
                "next_gate": "H-03" if req.verdict != "fail" else "H-02",
            },
            final_action={
                "handoff_to": "H-03" if req.verdict != "fail" else "H-02",
                "publication_blocked": req.verdict == "fail",
            },
            evidence_refs=[str(req.profile_version_id), str(review.id)],
        )
        db.commit()
        payload = review_payload(review)
        payload["agent_run_id"] = review_run.run_id
        return payload
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PassportConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{account_id}/publish", status_code=status.HTTP_201_CREATED)
def publish_profile(
    account_id: uuid.UUID,
    req: PublishProfileRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tenant_id, _enterprise_id = _context(user)
    if user.role not in {"platform_admin", "admin", "manager"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无发布权限")
    try:
        profile = publish_profile_version(
            db,
            tenant_id=tenant_id,
            account_id=account_id,
            profile_version_id=req.profile_version_id,
            methodology_review_id=req.methodology_review_id,
            actor_id=user.id,
        )
        release_run = start_agent_run(
            db,
            tenant_id=tenant_id,
            enterprise_id=user.enterprise_id,
            agent_id="H-03",
            trigger="profile_publish",
            trigger_ref=str(profile.id),
            input_snapshot={
                "account_id": str(account_id),
                "profile_version_id": str(req.profile_version_id),
                "methodology_review_id": str(req.methodology_review_id),
            },
            summary="H-03 执行最终复核、版本冻结和授权发布",
        )
        append_agent_run_event(
            db,
            run=release_run,
            event_type="passport_published",
            status="success",
            title="护照版本已授权发布",
            summary="发布版本已通过重放、正式事实和方法学复核门禁",
            payload={
                "published_profile_version_id": str(profile.id),
                "supersedes_id": str(profile.supersedes_id),
                "content_hash": profile.content_hash,
                "completeness_score": profile.completeness_score,
                "data_quality_grade": profile.data_quality_grade,
            },
            evidence_refs=[
                str(req.profile_version_id),
                str(req.methodology_review_id),
                str(profile.id),
            ],
        )
        complete_agent_run(
            db,
            run=release_run,
            summary="H-03 已发布可验证、可重放的护照版本",
            output_snapshot={
                "profile_version_id": str(profile.id),
                "status": profile.status,
                "content_hash": profile.content_hash,
            },
            final_action={"published": True},
            evidence_refs=[str(profile.id)],
        )
        db.commit()
        payload = profile_payload(db, profile)
        payload["agent_run_id"] = release_run.run_id
        return payload
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PassportConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _decimal_text(value) -> str:
    return format(value, "f")


def _output_payload(record) -> dict:
    return {
        "id": str(record.id),
        "process_id": str(record.process_id),
        "product_id": str(record.product_id),
        "period_start": record.period_start.isoformat(),
        "period_end": record.period_end.isoformat(),
        "quantity": _decimal_text(record.quantity),
        "unit": record.unit,
        "version": record.version,
        "content_hash": record.content_hash,
    }


def _attribution_payload(record) -> dict:
    return {
        "id": str(record.id),
        "process_id": str(record.process_id),
        "source_ref": record.source_ref,
        "period_start": record.period_start.isoformat(),
        "period_end": record.period_end.isoformat(),
        "share": _decimal_text(record.share),
        "method": record.method,
        "version": record.version,
        "content_hash": record.content_hash,
    }


def _rule_payload(record) -> dict:
    return {
        "id": str(record.id),
        "rule_kind": record.rule_kind,
        "title": record.title,
        "publisher": record.publisher,
        "document_number": record.document_number,
        "jurisdiction": record.jurisdiction,
        "vintage": record.vintage,
        "valid_from": record.valid_from.isoformat(),
        "valid_to": record.valid_to.isoformat() if record.valid_to else None,
        "status": record.status,
        "source_url": record.source_url,
        "content_hash": record.content_hash,
        "approved_by": record.approved_by,
        "approved_at": record.approved_at.isoformat(),
    }


def _see_payload(record) -> dict:
    return {
        "id": str(record.id),
        "process_id": str(record.process_id),
        "product_id": str(record.product_id),
        "production_output_id": str(record.production_output_id),
        "period_start": record.period_start.isoformat(),
        "period_end": record.period_end.isoformat(),
        "direct_emissions": _decimal_text(record.direct_emissions),
        "indirect_emissions": _decimal_text(record.indirect_emissions),
        "precursor_emissions": _decimal_text(record.precursor_emissions),
        "total_emissions": _decimal_text(record.total_emissions),
        "emissions_unit": record.emissions_unit,
        "specific_emissions": _decimal_text(record.specific_emissions),
        "specific_unit": record.specific_unit,
        "data_quality": record.data_quality,
        "methodology_ref": record.methodology_ref,
        "version": record.version,
        "content_hash": record.content_hash,
    }
