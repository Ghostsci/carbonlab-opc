"""Read-only customer view over the append-only formal activity ledger.

The database ledger remains the source of truth.  This module only projects
tenant-owned formal records into a customer-readable list, detail view and
export.  It never mutates ledger rows.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from math import ceil
from typing import Any
import uuid

from sqlalchemy import and_, distinct, exists, func, or_
from sqlalchemy.orm import Query, Session

from backend.ai.ontology import ontology_contract, ontology_version
from backend.models.activity_data import ActivityData
from backend.models.document import DocumentStore
from backend.models.emission_result import EmissionResult
from backend.models.emission_source import EmissionSource
from backend.models.site import Site


STATUS_VALUES = {"calculated", "pending_factor"}
FORMAL_DESTINATIONS = {
    "electricity_kwh": "ActivityData.quantity",
    "period": "ActivityData.period_start / period_end",
    "facility": "Site.name",
    "methodology_ref": "EmissionResult.factor_id / RuleRecord",
}


def list_formal_activities(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    enterprise_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
    query_text: str | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
    facility: str | None = None,
    category: str | None = None,
    document_type: str | None = None,
    calculation_status: str | None = None,
) -> dict[str, Any]:
    """Return a paginated, tenant- and enterprise-scoped ledger projection."""
    base = _scoped_query(
        db,
        tenant_id=tenant_id,
        enterprise_id=enterprise_id,
        query_text=query_text,
        period_start=period_start,
        period_end=period_end,
        facility=facility,
        category=category,
        document_type=document_type,
        calculation_status=calculation_status,
    )
    total = base.count()
    calculated = base.filter(_has_current_result(tenant_id)).count()
    source_documents = (
        base.with_entities(func.count(distinct(ActivityData.document_id)))
        .filter(ActivityData.document_id.is_not(None))
        .scalar()
        or 0
    )
    rows = (
        base.order_by(ActivityData.confirmed_at.desc(), ActivityData.version.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        _list_item(
            db,
            tenant_id=tenant_id,
            activity=activity,
            source=source,
            site=site,
            document=document,
        )
        for activity, source, site, document in rows
    ]
    return {
        "summary": {
            "total": total,
            "calculated": calculated,
            "pending_factor": total - calculated,
            "source_documents": int(source_documents),
        },
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": ceil(total / page_size) if total else 0,
        },
        "filters": {
            "query": query_text,
            "period_start": period_start.isoformat() if period_start else None,
            "period_end": period_end.isoformat() if period_end else None,
            "facility": facility,
            "category": category,
            "document_type": document_type,
            "calculation_status": calculation_status,
        },
    }


def get_formal_activity_detail(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    enterprise_id: uuid.UUID,
    activity_id: uuid.UUID,
) -> dict[str, Any] | None:
    row = (
        _scoped_query(db, tenant_id=tenant_id, enterprise_id=enterprise_id)
        .filter(ActivityData.id == activity_id)
        .first()
    )
    if row is None:
        return None
    activity, source, site, document = row
    item = _list_item(
        db,
        tenant_id=tenant_id,
        activity=activity,
        source=source,
        site=site,
        document=document,
    )
    snapshot = document.ocr_result if document and isinstance(document.ocr_result, dict) else {}
    confirmation = snapshot.get("human_confirmation") or {}
    quality_review = confirmation.get("quality_review") or {}
    versions = (
        db.query(ActivityData)
        .join(EmissionSource, EmissionSource.id == ActivityData.emission_source_id)
        .join(Site, Site.id == EmissionSource.site_id)
        .filter(
            ActivityData.tenant_id == tenant_id,
            ActivityData.idempotency_key == activity.idempotency_key,
            EmissionSource.tenant_id == tenant_id,
            Site.tenant_id == tenant_id,
            Site.enterprise_id == enterprise_id,
        )
        .order_by(ActivityData.version.desc())
        .all()
    )
    return {
        **item,
        "ontology": {
            "version": ontology_version(),
            "role": "统一不同来源字段的语义，不替代正式账本约束",
        },
        "standardized_fields": _standardized_fields(
            activity=activity,
            site=site,
            document=document,
        ),
        "quality_review": _safe_quality_detail(quality_review),
        "human_confirmation": {
            "actor_user_id": confirmation.get("actor_user_id") or activity.confirmed_by,
            "candidate_id": confirmation.get("candidate_id"),
            "confirmed_at": confirmation.get("at") or _iso(activity.confirmed_at),
            "value_origin": confirmation.get("value_origin") or "human_confirmed",
        },
        "formal_record": {
            "record_type": "ActivityData",
            "content_hash": activity.content_hash,
            "idempotency_key": activity.idempotency_key,
            "version": activity.version,
            "confirmed_by": activity.confirmed_by,
            "confirmed_at": _iso(activity.confirmed_at),
            "append_only": True,
            "supersedes_id": str(activity.supersedes_id) if activity.supersedes_id else None,
            "superseded_by_id": str(activity.superseded_by_id) if activity.superseded_by_id else None,
        },
        "lineage": list(activity.derived_from or []),
        "version_history": [
            {
                "activity_data_id": str(version.id),
                "version": version.version,
                "quantity": _decimal_text(version.quantity),
                "unit": version.unit,
                "content_hash": version.content_hash,
                "confirmed_by": version.confirmed_by,
                "confirmed_at": _iso(version.confirmed_at),
                "is_current": version.superseded_by_id is None,
                "supersedes_id": str(version.supersedes_id) if version.supersedes_id else None,
            }
            for version in versions
        ],
    }


def export_formal_activity_rows(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    enterprise_id: uuid.UUID,
    query_text: str | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
    facility: str | None = None,
    category: str | None = None,
    document_type: str | None = None,
    calculation_status: str | None = None,
) -> list[dict[str, Any]]:
    rows = (
        _scoped_query(
            db,
            tenant_id=tenant_id,
            enterprise_id=enterprise_id,
            query_text=query_text,
            period_start=period_start,
            period_end=period_end,
            facility=facility,
            category=category,
            document_type=document_type,
            calculation_status=calculation_status,
        )
        .order_by(ActivityData.period_start.desc(), ActivityData.confirmed_at.desc())
        .all()
    )
    return [
        _list_item(
            db,
            tenant_id=tenant_id,
            activity=activity,
            source=source,
            site=site,
            document=document,
        )
        for activity, source, site, document in rows
    ]


def _scoped_query(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    enterprise_id: uuid.UUID,
    query_text: str | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
    facility: str | None = None,
    category: str | None = None,
    document_type: str | None = None,
    calculation_status: str | None = None,
) -> Query:
    query = (
        db.query(ActivityData, EmissionSource, Site, DocumentStore)
        .join(EmissionSource, EmissionSource.id == ActivityData.emission_source_id)
        .join(Site, Site.id == EmissionSource.site_id)
        .outerjoin(
            DocumentStore,
            and_(
                DocumentStore.id == ActivityData.document_id,
                DocumentStore.tenant_id == tenant_id,
                DocumentStore.enterprise_id == enterprise_id,
            ),
        )
        .filter(
            ActivityData.tenant_id == tenant_id,
            ActivityData.superseded_by_id.is_(None),
            EmissionSource.tenant_id == tenant_id,
            Site.tenant_id == tenant_id,
            Site.enterprise_id == enterprise_id,
        )
    )
    if query_text and query_text.strip():
        pattern = f"%{query_text.strip()}%"
        query = query.filter(
            or_(
                Site.name.ilike(pattern),
                EmissionSource.name.ilike(pattern),
                DocumentStore.filename.ilike(pattern),
                ActivityData.unit.ilike(pattern),
            )
        )
    if period_start:
        start = datetime.combine(period_start, time.min, tzinfo=timezone.utc)
        query = query.filter(ActivityData.period_end >= start)
    if period_end:
        end = datetime.combine(period_end, time.max, tzinfo=timezone.utc)
        query = query.filter(ActivityData.period_start <= end)
    if facility and facility.strip():
        query = query.filter(Site.name.ilike(f"%{facility.strip()}%"))
    if category:
        query = query.filter(EmissionSource.category == category)
    if document_type:
        query = query.filter(DocumentStore.doc_type == document_type)
    if calculation_status:
        if calculation_status not in STATUS_VALUES:
            raise ValueError("calculation_status 仅支持 calculated 或 pending_factor")
        result_exists = _has_current_result(tenant_id)
        query = query.filter(result_exists if calculation_status == "calculated" else ~result_exists)
    return query


def _has_current_result(tenant_id: uuid.UUID):
    return exists().where(
        and_(
            EmissionResult.tenant_id == tenant_id,
            EmissionResult.activity_data_id == ActivityData.id,
            EmissionResult.superseded_by_id.is_(None),
        )
    )


def _current_result(db: Session, tenant_id: uuid.UUID, activity_id: uuid.UUID) -> EmissionResult | None:
    return (
        db.query(EmissionResult)
        .filter(
            EmissionResult.tenant_id == tenant_id,
            EmissionResult.activity_data_id == activity_id,
            EmissionResult.superseded_by_id.is_(None),
        )
        .order_by(EmissionResult.version.desc(), EmissionResult.confirmed_at.desc())
        .first()
    )


def _list_item(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    activity: ActivityData,
    source: EmissionSource,
    site: Site,
    document: DocumentStore | None,
) -> dict[str, Any]:
    result = _current_result(db, tenant_id, activity.id)
    snapshot = document.ocr_result if document and isinstance(document.ocr_result, dict) else {}
    confirmation = snapshot.get("human_confirmation") or {}
    quality_review = confirmation.get("quality_review") or {}
    return {
        "activity_data_id": str(activity.id),
        "period": {
            "start": _iso(activity.period_start),
            "end": _iso(activity.period_end),
            "label": _period_label(activity.period_start, activity.period_end),
        },
        "facility": {
            "site_id": str(site.id),
            "name": site.name,
            "grid_region": site.grid_region,
        },
        "emission_source": {
            "emission_source_id": str(source.id),
            "name": source.name,
            "scope": source.scope,
            "category": source.category,
        },
        "activity": {
            "quantity": _decimal_text(activity.quantity),
            "unit": activity.unit,
            "data_source": activity.data_source,
        },
        "source_document": _document_payload(document),
        "quality": _quality_summary(quality_review),
        "confirmation": {
            "confirmed_by": activity.confirmed_by,
            "confirmed_at": _iso(activity.confirmed_at),
            "version": activity.version,
        },
        "calculation_status": "calculated" if result else "pending_factor",
        "emission_result": _emission_result_payload(result),
        "content_hash": activity.content_hash,
    }


def _document_payload(document: DocumentStore | None) -> dict[str, Any] | None:
    if document is None:
        return None
    return {
        "document_id": str(document.id),
        "filename": document.filename,
        "document_type": document.doc_type,
        "mime_type": document.mime_type,
        "size_bytes": document.size_bytes,
        "content_hash": document.content_hash,
        "download_url": f"/api/upload/{document.id}/download",
        "uploaded_at": _iso(document.created_at),
    }


def _quality_summary(quality_review: dict[str, Any]) -> dict[str, Any]:
    return {
        "quality_review_id": quality_review.get("quality_review_id"),
        "status": quality_review.get("quality_status") or "not_available",
        "score": quality_review.get("score"),
        "score_label": quality_review.get("score_label") or "自动检查覆盖得分",
        "warnings_resolved": quality_review.get("warnings_resolved"),
    }


def _safe_quality_detail(quality_review: dict[str, Any]) -> dict[str, Any]:
    summary = _quality_summary(quality_review)
    return {
        **summary,
        "summary": quality_review.get("summary"),
        "counts": quality_review.get("counts") or {},
        "findings": quality_review.get("findings") or [],
        "resolutions": quality_review.get("resolutions") or [],
        "quality_result_sha256": quality_review.get("quality_result_sha256"),
        "resolution_sha256": quality_review.get("resolution_sha256"),
    }


def _standardized_fields(
    *,
    activity: ActivityData,
    site: Site,
    document: DocumentStore | None,
) -> list[dict[str, Any]]:
    snapshot = document.ocr_result if document and isinstance(document.ocr_result, dict) else {}
    fields = snapshot.get("fields") or {}
    field_sources = snapshot.get("field_sources") or {}
    definitions = ontology_contract()["field_mappings"]
    values = {
        "electricity_kwh": _decimal_text(activity.quantity),
        "period": _period_label(activity.period_start, activity.period_end),
        "facility": site.name,
        "methodology_ref": None,
    }
    rows: list[dict[str, Any]] = []
    for canonical_key, definition in definitions.items():
        aliases = [str(alias) for alias in definition.get("aliases", [])]
        raw_field = next(
            (
                key
                for key in fields
                if str(key).strip().lower()
                in {canonical_key.lower(), *(alias.strip().lower() for alias in aliases)}
            ),
            None,
        )
        rows.append(
            {
                "canonical_key": canonical_key,
                "canonical_value": values.get(canonical_key),
                "expected_unit": definition.get("expected_unit"),
                "concepts": definition.get("concepts") or [],
                "raw_field": raw_field,
                "raw_value": fields.get(raw_field) if raw_field else None,
                "source_locator": field_sources.get(raw_field) if raw_field else None,
                "formal_destination": FORMAL_DESTINATIONS.get(canonical_key),
                "status": "formal" if raw_field and values.get(canonical_key) is not None else "not_captured",
            }
        )
    return rows


def _emission_result_payload(result: EmissionResult | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        "emission_result_id": str(result.id),
        "co2_tonnes": _decimal_text(result.co2_tonnes),
        "unit": result.unit,
        "factor_id": str(result.factor_id) if result.factor_id else None,
        "confirmed_at": _iso(result.confirmed_at),
    }


def _period_label(start: datetime, end: datetime) -> str:
    if start.year == end.year and start.month == 1 and end.month == 3:
        return f"{start.year} Q1"
    if start.year == end.year and start.month == 4 and end.month == 6:
        return f"{start.year} Q2"
    if start.year == end.year and start.month == 7 and end.month == 9:
        return f"{start.year} Q3"
    if start.year == end.year and start.month == 10 and end.month == 12:
        return f"{start.year} Q4"
    if start.year == end.year and start.month == end.month:
        return f"{start.year}-{start.month:02d}"
    return f"{start.date().isoformat()} 至 {end.date().isoformat()}"


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
