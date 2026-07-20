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
        db.commit()
        return profile_payload(db, profile)
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
        db.commit()
        return review_payload(review)
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
        db.commit()
        return profile_payload(db, profile)
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
