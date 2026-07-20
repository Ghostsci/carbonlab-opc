"""Persist confirmed activity records into the formal emissions data model.

The Data Inbox first writes an auditable workflow checkpoint. This service
bridges that checkpoint into normalized operational tables:

Workflow checkpoint -> Site -> EmissionSource -> ActivityData -> EmissionResult
"""

from __future__ import annotations

import calendar
from decimal import Decimal, InvalidOperation
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.activity_data import ActivityData
from backend.models.document import DocumentStore
from backend.models.emission_factor import EmissionFactor
from backend.models.emission_result import EmissionResult
from backend.models.emission_source import EmissionSource
from backend.models.enterprise import Enterprise
from backend.models.ledger import LedgerIntegrityError
from backend.models.site import Site
from backend.models.user import User
from backend.core.ledger import (
    content_hash,
    idempotency_hash,
    ledger_decimal,
    require_confirmed_origin,
)
from backend.core.quantity import Quantity, QuantityError


DEFAULT_PROVINCE = "江苏"
DEFAULT_CITY = "苏州"
DEFAULT_GRID_REGION = "华东"
DEFAULT_ADDRESS = "江苏省苏州市张家港市"


def persist_confirmed_activity(
    db: Session,
    *,
    user: User,
    activity_record: dict[str, Any],
    trusted_factor_id: uuid.UUID | str | None = None,
) -> dict[str, Any]:
    """Persist an already-confirmed activity record into formal tables.

    This function is intentionally idempotent for repeated confirmation clicks:
    it reuses the same ActivityData row when the source file, source, and period
    match instead of appending duplicates.
    """
    if not user.enterprise_id:
        raise ValueError("当前用户未绑定企业，无法写入正式活动数据")
    if not user.tenant_id:
        raise ValueError("当前用户未绑定租户，无法写入正式活动数据")

    enterprise = (
        db.query(Enterprise)
        .filter(Enterprise.id == user.enterprise_id, Enterprise.tenant_id == user.tenant_id)
        .first()
    )
    if enterprise is None:
        raise ValueError("未找到当前租户下的企业，无法写入正式活动数据")

    quantity = _as_decimal(activity_record.get("quantity"))
    if quantity is None:
        raise ValueError("活动数据缺少有效数量，无法写入正式活动数据")

    period_start, period_end = _parse_period(activity_record.get("period"))
    unit = str(activity_record.get("unit") or "unknown")
    try:
        normalized_quantity = Quantity.of(quantity, unit)
    except QuantityError as exc:
        raise ValueError(f"活动数据单位或数值无效: {exc}") from exc
    origin = require_confirmed_origin(activity_record.get("value_origin"))
    quantity = ledger_decimal(normalized_quantity.value)
    category = _category_for_activity(activity_record)
    scope = "scope_2" if category in {"purchased_electricity", "purchased_heat"} else "scope_1"

    site = _get_or_create_site(db, user=user, enterprise=enterprise, activity_record=activity_record)
    source = _get_or_create_source(db, site=site, scope=scope, category=category)
    document_id = _optional_uuid(activity_record.get("file_id"))

    activity = _get_or_create_activity(
        db,
        source=source,
        activity_record=activity_record,
        period_start=period_start,
        period_end=period_end,
        quantity=quantity,
        unit=normalized_quantity.unit,
        document_id=document_id,
        tenant_id=user.tenant_id,
        enterprise_id=user.enterprise_id,
        confirmed_by=str(user.id),
        value_origin=origin,
    )
    db.flush()

    factor_uuid: uuid.UUID | None = None
    if trusted_factor_id is not None:
        try:
            factor_uuid = uuid.UUID(str(trusted_factor_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("trusted_factor_id 格式无效") from exc

    emission_result = _upsert_emission_result(
        db,
        source=source,
        activity=activity,
        activity_record=activity_record,
        period_start=period_start,
        period_end=period_end,
        quantity=quantity,
        unit=unit,
        tenant_id=user.tenant_id,
        confirmed_by=str(user.id),
        trusted_factor_id=factor_uuid,
    )
    db.flush()

    return {
        "site_id": str(site.id),
        "site_name": site.name,
        "emission_source_id": str(source.id),
        "emission_source_name": source.name,
        "activity_data_id": str(activity.id),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "calculation_status": "calculated" if emission_result else "pending_factor",
        "emission_result": _result_payload(emission_result) if emission_result else None,
    }


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool | float):
        return None
    if isinstance(value, Decimal | int):
        return Decimal(value)
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", str(value))
    if not match:
        return None
    try:
        return Decimal(match.group(0).replace(",", ""))
    except InvalidOperation:
        return None


def _optional_uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except Exception:
        return None


def _parse_period(value: Any) -> tuple[datetime, datetime]:
    text = str(value or "").strip()
    range_match = re.search(
        r"(\d{4})[./年-](\d{1,2})[./月-](\d{1,2})日?\s*(?:至|~|—|-)\s*(\d{4})[./年-](\d{1,2})[./月-](\d{1,2})日?",
        text,
    )
    if range_match:
        sy, sm, sd, ey, em, ed = map(int, range_match.groups())
        return (
            datetime(sy, sm, sd, tzinfo=timezone.utc),
            datetime(ey, em, ed, 23, 59, 59, tzinfo=timezone.utc),
        )

    quarter_match = re.search(
        r"(?i)(\d{4})\s*(?:[-/.]?\s*Q\s*([1-4])|年\s*第?\s*([一二三四1-4])\s*季度)",
        text,
    )
    if quarter_match:
        year = int(quarter_match.group(1))
        quarter_token = quarter_match.group(2) or quarter_match.group(3)
        quarter = (
            int(quarter_token)
            if quarter_token.isdigit()
            else {"一": 1, "二": 2, "三": 3, "四": 4}[quarter_token]
        )
        start_month = (quarter - 1) * 3 + 1
        end_month = quarter * 3
        last_day = calendar.monthrange(year, end_month)[1]
        return (
            datetime(year, start_month, 1, tzinfo=timezone.utc),
            datetime(year, end_month, last_day, 23, 59, 59, tzinfo=timezone.utc),
        )

    month_match = re.search(r"(\d{4})\s*(?:年|[-/.])\s*(\d{1,2})\s*(?:月)?", text)
    if month_match:
        year, month = map(int, month_match.groups())
        last_day = calendar.monthrange(year, month)[1]
        return (
            datetime(year, month, 1, tzinfo=timezone.utc),
            datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc),
        )

    raise ValueError(
        "reporting period is missing or unsupported; use YYYY-MM, YYYY-QN, "
        "or an explicit start/end date range"
    )


def _category_for_activity(activity_record: dict[str, Any]) -> str:
    activity_type = str(activity_record.get("activity_type") or "")
    document_type = str(activity_record.get("document_type") or "")
    if "electricity" in activity_type or document_type == "electricity_bill":
        return "purchased_electricity"
    return activity_type or "document_activity"


def _get_or_create_site(
    db: Session,
    *,
    user: User,
    enterprise: Enterprise,
    activity_record: dict[str, Any],
) -> Site:
    facility = str(activity_record.get("facility") or "").strip() or "默认工厂"
    site = (
        db.query(Site)
        .filter(
            Site.enterprise_id == enterprise.id,
            Site.name == facility,
            or_(Site.tenant_id == user.tenant_id, Site.tenant_id.is_(None)),
        )
        .first()
    )
    if site:
        if site.tenant_id is None:
            site.tenant_id = user.tenant_id
        return site

    site = Site(
        enterprise_id=enterprise.id,
        tenant_id=user.tenant_id,
        name=facility,
        address=DEFAULT_ADDRESS,
        province=DEFAULT_PROVINCE,
        city=DEFAULT_CITY,
        grid_region=DEFAULT_GRID_REGION,
    )
    db.add(site)
    db.flush()
    return site


def _get_or_create_source(db: Session, *, site: Site, scope: str, category: str) -> EmissionSource:
    source = (
        db.query(EmissionSource)
        .filter(EmissionSource.site_id == site.id, EmissionSource.scope == scope, EmissionSource.category == category)
        .first()
    )
    if source:
        return source

    source = EmissionSource(
        site_id=site.id,
        name=f"{site.name} 外购电力" if category == "purchased_electricity" else f"{site.name} {category}",
        scope=scope,
        category=category,
        fuel_type=None,
        source_code=f"DI-{str(site.id)[:8]}-{_source_code_suffix(category)}",
    )
    db.add(source)
    db.flush()
    return source


def _source_code_suffix(category: str) -> str:
    return {
        "purchased_electricity": "ELEC",
        "purchased_heat": "HEAT",
        "stationary_combustion": "STAT",
        "mobile_combustion": "MOB",
    }.get(category, "DOC")


def _get_or_create_activity(
    db: Session,
    *,
    source: EmissionSource,
    activity_record: dict[str, Any],
    period_start: datetime,
    period_end: datetime,
    quantity: Decimal,
    unit: str,
    document_id: uuid.UUID | None,
    tenant_id: uuid.UUID,
    enterprise_id: uuid.UUID,
    confirmed_by: str,
    value_origin: str,
) -> ActivityData:
    raw_file_id = activity_record.get("file_id")
    if raw_file_id not in (None, "") and document_id is None:
        raise ValueError("源文件 file_id 格式无效，禁止写入正式活动数据")
    document = db.get(DocumentStore, document_id) if document_id else None
    if document_id is not None and document is None:
        raise ValueError("源文件 file_id 不存在，禁止写入正式活动数据")
    if document is not None and document.tenant_id != tenant_id:
        raise ValueError("源文件不属于当前租户，禁止写入正式活动数据")
    if document is not None and document.enterprise_id != enterprise_id:
        raise ValueError("源文件不属于当前企业，禁止写入正式活动数据")
    file_id = str(document.id) if document is not None else ""
    claimed_document_hash = activity_record.get("document_content_hash")
    if claimed_document_hash and document is None:
        raise ValueError("未找到当前租户下与 content_hash 对应的源文件")
    if (
        document is not None
        and claimed_document_hash
        and claimed_document_hash != document.content_hash
    ):
        raise ValueError("源文件 content_hash 与服务器记录不一致")
    document_hash = str(
        document.content_hash
        if document is not None
        else claimed_document_hash
        or content_hash(
            {
                "file_id": file_id,
                "filename": activity_record.get("filename"),
            }
        )
    )
    idempotency_key = idempotency_hash(
        tenant_id,
        source.id,
        period_start,
        period_end,
        document_hash,
    )
    payload = {
        "record_type": "activity_data",
        "tenant_id": tenant_id,
        "emission_source_id": source.id,
        "period_start": period_start,
        "period_end": period_end,
        "quantity": quantity,
        "unit": unit,
        "data_source": "ocr",
        "document_id": document_id,
        "source_file_id": file_id,
        "value_origin": value_origin,
    }
    record_hash = content_hash(payload)
    for _attempt in range(5):
        latest = (
            db.query(ActivityData)
            .filter(
                ActivityData.tenant_id == tenant_id,
                ActivityData.idempotency_key == idempotency_key,
            )
            .order_by(ActivityData.version.desc())
            .first()
        )
        if latest and latest.content_hash == record_hash:
            return latest

        activity = ActivityData(
            tenant_id=tenant_id,
            emission_source_id=source.id,
            period_start=period_start,
            period_end=period_end,
            quantity=quantity,
            unit=unit,
            data_source="ocr",
            document_id=document_id,
            notes=_activity_notes(activity_record),
            derived_from=[f"document:{file_id}"] if file_id else [],
            content_hash=record_hash,
            idempotency_key=idempotency_key,
            version=(latest.version + 1) if latest else 1,
            supersedes_id=latest.id if latest else None,
            superseded_by_id=None,
            confirmed_by=confirmed_by,
            confirmed_at=datetime.now(timezone.utc),
        )
        try:
            with db.begin_nested():
                db.add(activity)
                db.flush()
        except (IntegrityError, LedgerIntegrityError) as exc:
            db.expire_all()
            winner = (
                db.query(ActivityData)
                .filter(
                    ActivityData.tenant_id == tenant_id,
                    ActivityData.idempotency_key == idempotency_key,
                )
                .order_by(ActivityData.version.desc())
                .first()
            )
            if winner is None:
                raise exc
            if winner.content_hash == record_hash:
                return winner
            continue
        if latest:
            db.expire(latest, ["superseded_by_id"])
        return activity
    raise RuntimeError("activity ledger write did not converge after concurrent retries")


def _activity_notes(activity_record: dict[str, Any]) -> str:
    parts = [
        "source=data_inbox",
        f"source_file_id={activity_record.get('file_id') or ''}",
        f"filename={activity_record.get('filename') or ''}",
        f"confidence={activity_record.get('confidence') if activity_record.get('confidence') is not None else ''}",
    ]
    return "; ".join(parts)[:500]


def _upsert_emission_result(
    db: Session,
    *,
    source: EmissionSource,
    activity: ActivityData,
    activity_record: dict[str, Any],
    period_start: datetime,
    period_end: datetime,
    quantity: Decimal,
    unit: str,
    tenant_id: uuid.UUID,
    confirmed_by: str,
    trusted_factor_id: uuid.UUID | None,
) -> EmissionResult | None:
    if source.category != "purchased_electricity":
        return None

    factor = _find_electricity_factor(
        db,
        source=source,
        period_start=period_start,
        trusted_factor_id=trusted_factor_id,
    )
    if factor is None:
        return None

    try:
        activity_quantity = Quantity.of(quantity, unit)
        factor_quantity = Quantity.of(factor.value, factor.unit)
    except QuantityError as exc:
        raise ValueError(f"活动数据与排放因子量纲不兼容: {exc}") from exc
    target_unit = "tCO2e" if "CO2e" in factor.unit else "tCO2"
    try:
        emission_quantity = (activity_quantity * factor_quantity).convert_to(target_unit)
    except QuantityError as exc:
        raise ValueError(f"活动数据与排放因子量纲不兼容: {exc}") from exc
    if emission_quantity.unit not in {"tCO2", "tCO2e"}:
        return None

    result_value = ledger_decimal(emission_quantity.value)
    uncertainty = factor.uncertainty
    uncertainty_decimal = Decimal(str(uncertainty)) if uncertainty is not None else None
    low = (
        result_value * (Decimal("1") - uncertainty_decimal / Decimal("100"))
        if uncertainty_decimal is not None
        else None
    )
    high = (
        result_value * (Decimal("1") + uncertainty_decimal / Decimal("100"))
        if uncertainty_decimal is not None
        else None
    )
    audit_trail = {
        "source": "data_inbox_confirm_activity",
        "activity_data_id": str(activity.id),
        "formula": "Quantity(activity) × Quantity(factor) → target emission unit",
        "quantity": str(quantity),
        "unit": unit,
        "factor": {
            "id": str(factor.id),
            "code": factor.code,
            "name": factor.name,
            "value": str(factor.value),
            "unit": factor.unit,
            "source": factor.source,
            "year": factor.year,
            "region": factor.region,
        },
        "source_file_id": activity_record.get("file_id"),
        "filename": activity_record.get("filename"),
        "confidence": (
            str(activity_record.get("confidence"))
            if activity_record.get("confidence") is not None
            else None
        ),
    }
    idempotency_key = idempotency_hash(
        tenant_id,
        activity.id,
        factor.id,
        "quantity-kernel-v1",
    )
    payload = {
        "record_type": "emission_result",
        "tenant_id": tenant_id,
        "emission_source_id": source.id,
        "period_start": period_start,
        "period_end": period_end,
        "scope": source.scope,
        "value": result_value,
        "unit": emission_quantity.unit,
        "factor_id": factor.id,
        "activity_data_id": activity.id,
        "audit_trail": audit_trail,
    }
    record_hash = content_hash(payload)
    for _attempt in range(5):
        existing = (
            db.query(EmissionResult)
            .filter(
                EmissionResult.tenant_id == tenant_id,
                EmissionResult.idempotency_key == idempotency_key,
            )
            .order_by(EmissionResult.version.desc())
            .first()
        )
        if existing and existing.content_hash == record_hash:
            return existing

        previous = (
            db.query(EmissionResult)
            .filter(
                EmissionResult.tenant_id == tenant_id,
                EmissionResult.emission_source_id == source.id,
                EmissionResult.period_start == period_start,
                EmissionResult.period_end == period_end,
                EmissionResult.scope == source.scope,
                EmissionResult.superseded_by_id.is_(None),
            )
            .order_by(EmissionResult.version.desc())
            .first()
        )
        result = EmissionResult(
            tenant_id=tenant_id,
            emission_source_id=source.id,
            period_start=period_start,
            period_end=period_end,
            scope=source.scope,
            co2_tonnes=result_value,
            unit=emission_quantity.unit,
            factor_id=factor.id,
            activity_data_id=activity.id,
            uncertainty_pct=uncertainty,
            confidence_95_low=low,
            confidence_95_high=high,
            audit_trail=audit_trail,
            derived_from=[
                f"activity_data:{activity.id}",
                f"emission_factor:{factor.id}",
            ],
            content_hash=record_hash,
            idempotency_key=idempotency_key,
            version=(previous.version + 1) if previous else 1,
            supersedes_id=previous.id if previous else None,
            superseded_by_id=None,
            confirmed_by=confirmed_by,
            confirmed_at=datetime.now(timezone.utc),
        )
        try:
            with db.begin_nested():
                db.add(result)
                db.flush()
        except (IntegrityError, LedgerIntegrityError) as exc:
            db.expire_all()
            winner = (
                db.query(EmissionResult)
                .filter(
                    EmissionResult.tenant_id == tenant_id,
                    EmissionResult.idempotency_key == idempotency_key,
                )
                .order_by(EmissionResult.version.desc())
                .first()
            )
            if winner is None:
                raise exc
            if winner.content_hash == record_hash:
                return winner
            continue
        if previous:
            db.expire(previous, ["superseded_by_id"])
        return result
    raise RuntimeError("emission result write did not converge after concurrent retries")


def _find_electricity_factor(
    db: Session,
    *,
    source: EmissionSource,
    period_start: datetime,
    trusted_factor_id: uuid.UUID | None = None,
) -> EmissionFactor | None:
    region = source.site.grid_region if source.site else DEFAULT_GRID_REGION
    if trusted_factor_id is not None:
        factor = db.get(EmissionFactor, trusted_factor_id)
        if factor is None:
            raise ValueError("指定的排放因子不存在")
        if factor.category != "electricity_grid":
            raise ValueError("指定的排放因子不是电网排放因子")
        if factor.year != period_start.year:
            raise ValueError("指定排放因子的适用年份与活动期间不一致")
        if factor.region not in {region, "全国"}:
            raise ValueError("指定排放因子的区域与活动设施不一致")
        return factor

    preferred = (
        db.query(EmissionFactor)
        .filter(
            EmissionFactor.category == "electricity_grid",
            EmissionFactor.region == region,
            EmissionFactor.year == period_start.year,
            EmissionFactor.is_default.is_(True),
        )
        .order_by(EmissionFactor.created_at.desc())
        .first()
    )
    if preferred:
        return preferred

    return (
        db.query(EmissionFactor)
        .filter(
            EmissionFactor.category == "electricity_grid",
            EmissionFactor.is_default.is_(True),
            or_(EmissionFactor.region == region, EmissionFactor.region == "全国"),
        )
        .order_by(
            (EmissionFactor.year == period_start.year).desc(),
            EmissionFactor.year.desc(),
            EmissionFactor.created_at.desc(),
        )
        .first()
    )


def _result_payload(result: EmissionResult) -> dict[str, Any]:
    return {
        "emission_result_id": str(result.id),
        "co2_tonnes": float(result.co2_tonnes),
        "unit": result.unit,
        "factor_id": str(result.factor_id) if result.factor_id else None,
        "uncertainty_pct": result.uncertainty_pct,
        "confidence_95_low": (
            float(result.confidence_95_low)
            if result.confidence_95_low is not None
            else None
        ),
        "confidence_95_high": (
            float(result.confidence_95_high)
            if result.confidence_95_high is not None
            else None
        ),
    }
