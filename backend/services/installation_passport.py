"""Deep module for stable, tenant-scoped installation carbon-data passports."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.ledger import content_hash, idempotency_hash
from backend.database import Base
from backend.models.activity_data import ActivityData
from backend.models.cbam_ledger import (
    CBAMProduct,
    Installation,
    ProductionOutput,
    ProductionProcess,
    SEEResult,
    SourceStreamAttribution,
)
from backend.models.document import DocumentStore
from backend.models.emission_result import EmissionResult
from backend.models.emission_source import EmissionSource
from backend.models.enterprise import Enterprise
from backend.models.installation_passport import (
    DataSharingGrant,
    DataSharingRevocation,
    InstallationAccount,
    InstallationAccountMember,
    InstallationProfileVersion,
    MethodologyReview,
    ProfileDistributionEvent,
)
from backend.models.rule_record import RuleRecord
from backend.models.site import Site
from backend.services.cbam_inputs import persist_production_output
from backend.services.cbam_see import calculate_and_persist_see, replay_see_result
from backend.services.rule_records import TRUSTED_CBAM_PUBLISHERS


class PassportConflict(RuntimeError):
    """The requested passport transition violates a deterministic gate."""


PASSPORT_SHARE_SCOPES = frozenset(
    {
        "identity",
        "processes",
        "products",
        "outputs",
        "emissions",
        "evidence_manifest",
        "methodology",
        "review",
    }
)


def create_sharing_grant(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    profile_version_id: uuid.UUID,
    recipient_name: str,
    recipient_type: str,
    recipient_tenant_id: uuid.UUID | None,
    purpose: str,
    scopes: list[str],
    expires_at: datetime,
    actor_id: uuid.UUID,
) -> DataSharingGrant:
    profile = _tenant_profile(db, tenant_id, profile_version_id)
    if profile.account_id != account_id or profile.status != "published":
        raise PassportConflict("只有当前租户的已发布护照版本可以授权共享")
    if not replay_profile_version(
        db,
        tenant_id=tenant_id,
        profile_version_id=profile.id,
    )["match"]:
        raise PassportConflict("已发布护照无法重放，禁止共享")
    normalized_scopes = sorted(set(scopes))
    if not normalized_scopes or not set(normalized_scopes) <= PASSPORT_SHARE_SCOPES:
        raise ValueError("sharing scopes are empty or contain unsupported fields")
    now = datetime.now(timezone.utc)
    if _aware(expires_at) <= now:
        raise ValueError("sharing grant expiration must be in the future")
    if recipient_tenant_id == tenant_id:
        raise ValueError("recipient tenant must differ from owner tenant")
    if recipient_tenant_id is not None:
        recipient_exists = db.execute(
            select(Base.metadata.tables["tenants"].c.id).where(
                Base.metadata.tables["tenants"].c.id == recipient_tenant_id
            )
        ).scalar_one_or_none()
        if recipient_exists is None:
            raise LookupError("recipient tenant does not exist")
    normalized_name = recipient_name.strip()
    normalized_purpose = purpose.strip()
    if not normalized_name or not normalized_purpose:
        raise ValueError("recipient and purpose cannot be blank")
    if recipient_type not in {
        "importer",
        "trader",
        "verifier",
        "software_partner",
        "customer",
        "other",
    }:
        raise ValueError("recipient type is not allowed")
    payload = {
        "record_type": "data_sharing_grant",
        "tenant_id": tenant_id,
        "account_id": account_id,
        "profile_version_id": profile.id,
        "recipient_tenant_id": recipient_tenant_id,
        "recipient_name": normalized_name,
        "recipient_type": recipient_type,
        "purpose": normalized_purpose,
        "scopes": normalized_scopes,
        "expires_at": _iso_utc(expires_at),
        "created_by": actor_id,
    }
    record = DataSharingGrant(
        tenant_id=tenant_id,
        account_id=account_id,
        profile_version_id=profile.id,
        recipient_tenant_id=recipient_tenant_id,
        recipient_name=normalized_name,
        recipient_type=recipient_type,
        purpose=normalized_purpose,
        scopes_json=normalized_scopes,
        expires_at=expires_at,
        created_by=str(actor_id),
        content_hash=content_hash(payload),
    )
    db.add(record)
    db.flush()
    return record


def revoke_sharing_grant(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    grant_id: uuid.UUID,
    actor_id: uuid.UUID,
    reason: str,
) -> DataSharingRevocation:
    grant = _owner_grant(db, tenant_id, account_id, grant_id)
    existing = (
        db.query(DataSharingRevocation)
        .filter(
            DataSharingRevocation.tenant_id == tenant_id,
            DataSharingRevocation.grant_id == grant.id,
        )
        .first()
    )
    if existing is not None:
        return existing
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ValueError("revocation reason cannot be blank")
    payload = {
        "record_type": "data_sharing_revocation",
        "tenant_id": tenant_id,
        "grant_id": grant.id,
        "revoked_by": actor_id,
        "reason": normalized_reason,
    }
    record = DataSharingRevocation(
        tenant_id=tenant_id,
        grant_id=grant.id,
        revoked_by=str(actor_id),
        reason=normalized_reason,
        content_hash=content_hash(payload),
    )
    try:
        with db.begin_nested():
            db.add(record)
            db.flush()
    except IntegrityError as exc:
        db.expire_all()
        winner = (
            db.query(DataSharingRevocation)
            .filter(
                DataSharingRevocation.tenant_id == tenant_id,
                DataSharingRevocation.grant_id == grant.id,
            )
            .first()
        )
        if winner is None:
            raise exc
        return winner
    return record


def list_received_grants(
    db: Session,
    *,
    recipient_tenant_id: uuid.UUID,
) -> list[DataSharingGrant]:
    grants = (
        db.query(DataSharingGrant)
        .filter(DataSharingGrant.recipient_tenant_id == recipient_tenant_id)
        .order_by(DataSharingGrant.created_at.desc())
        .all()
    )
    return [item for item in grants if _grant_is_active(db, item)]


def access_shared_package(
    db: Session,
    *,
    recipient_tenant_id: uuid.UUID,
    grant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> dict:
    grant = (
        db.query(DataSharingGrant)
        .filter(
            DataSharingGrant.id == grant_id,
            DataSharingGrant.recipient_tenant_id == recipient_tenant_id,
        )
        .first()
    )
    if grant is None:
        raise LookupError("sharing grant not found for recipient tenant")
    return _deliver_package(db, grant=grant, actor_id=actor_id, channel="api_view")


def export_shared_package(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    grant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> dict:
    grant = _owner_grant(db, tenant_id, account_id, grant_id)
    return _deliver_package(db, grant=grant, actor_id=actor_id, channel="json_export")


def add_production_output(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    process_id: uuid.UUID,
    product_id: uuid.UUID,
    period_start: datetime,
    period_end: datetime,
    quantity: str | int | Decimal,
    unit: str,
    actor_id: uuid.UUID,
) -> ProductionOutput:
    _account_process_product(
        db,
        tenant_id=tenant_id,
        account_id=account_id,
        process_id=process_id,
        product_id=product_id,
    )
    return persist_production_output(
        db,
        tenant_id=tenant_id,
        process_id=process_id,
        product_id=product_id,
        period_start=period_start,
        period_end=period_end,
        quantity=quantity,
        unit=unit,
        value_origin="human_confirmed",
        confirmed_by=str(actor_id),
    )


def add_source_attribution(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    process_id: uuid.UUID,
    emission_result_id: uuid.UUID,
    period_start: datetime,
    period_end: datetime,
    share: str | int | Decimal,
    method: str,
    actor_id: uuid.UUID,
) -> SourceStreamAttribution:
    account, _installation, processes, _products = _load_base_facts(
        db,
        tenant_id=tenant_id,
        account_id=account_id,
    )
    if process_id not in {item.id for item in processes}:
        raise LookupError("process does not belong to installation passport")
    result = (
        db.query(EmissionResult)
        .join(EmissionSource, EmissionSource.id == EmissionResult.emission_source_id)
        .join(Site, Site.id == EmissionSource.site_id)
        .filter(
            EmissionResult.id == emission_result_id,
            EmissionResult.tenant_id == tenant_id,
            Site.enterprise_id == account.enterprise_id,
        )
        .first()
    )
    if result is None:
        raise LookupError("emission result not found for passport enterprise and tenant")
    if not _same_instant(result.period_start, period_start) or not _same_instant(
        result.period_end,
        period_end,
    ):
        raise ValueError("emission result period must exactly match attribution period")
    value = _exact_decimal(share, "attribution share")
    if value != Decimal("1"):
        raise ValueError(
            "the current passport workbench supports a full 1.00 assignment; "
            "multi-process batches require the batch allocation interface"
        )
    normalized_method = method.strip()
    if not normalized_method:
        raise ValueError("attribution method cannot be blank")
    source_ref = f"emission_result:{result.id}"
    key = idempotency_hash(tenant_id, source_ref, period_start, period_end)
    payload = {
        "record_type": "source_stream_attribution",
        "tenant_id": tenant_id,
        "process_id": process_id,
        "source_ref": source_ref,
        "period_start": period_start,
        "period_end": period_end,
        "share": value,
        "method": normalized_method,
    }
    record_hash = content_hash(payload)
    previous = (
        db.query(SourceStreamAttribution)
        .filter(
            SourceStreamAttribution.tenant_id == tenant_id,
            SourceStreamAttribution.source_ref == source_ref,
            SourceStreamAttribution.period_start == period_start,
            SourceStreamAttribution.period_end == period_end,
            SourceStreamAttribution.superseded_by_id.is_(None),
        )
        .order_by(SourceStreamAttribution.version.desc())
        .first()
    )
    if previous is not None and previous.content_hash == record_hash:
        return previous
    record = SourceStreamAttribution(
        tenant_id=tenant_id,
        process_id=process_id,
        source_ref=source_ref,
        period_start=period_start,
        period_end=period_end,
        share=value,
        method=normalized_method,
        derived_from=[f"production_process:{process_id}", source_ref],
        content_hash=record_hash,
        idempotency_key=key,
        version=previous.version + 1 if previous else 1,
        supersedes_id=previous.id if previous else None,
        confirmed_by=str(actor_id),
        confirmed_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.flush()
    return record


def register_authoritative_rule(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    rule_kind: str,
    title: str,
    publisher: str,
    document_number: str,
    jurisdiction: str,
    vintage: int,
    valid_from: datetime,
    valid_to: datetime | None,
    source_url: str,
    source_content_hash: str,
) -> RuleRecord:
    if rule_kind not in {"cbam_methodology", "precursor_default"}:
        raise ValueError("unsupported rule kind")
    if publisher not in TRUSTED_CBAM_PUBLISHERS:
        raise ValueError("publisher is not trusted for the current CBAM boundary")
    if jurisdiction != "EU" or not document_number.startswith("EU-"):
        raise ValueError("rule jurisdiction or document number is invalid")
    if not source_url.startswith("https://"):
        raise ValueError("rule source must use HTTPS")
    if not re.fullmatch(r"[0-9a-f]{64}", source_content_hash):
        raise ValueError("rule source content hash must be lowercase SHA-256")
    if valid_to is not None and valid_from >= valid_to:
        raise ValueError("rule valid_from must precede valid_to")
    existing = (
        db.query(RuleRecord)
        .filter(
            RuleRecord.tenant_id == tenant_id,
            RuleRecord.rule_kind == rule_kind,
            RuleRecord.document_number == document_number,
            RuleRecord.vintage == vintage,
        )
        .first()
    )
    if existing is not None:
        same = (
            existing.title == title.strip()
            and existing.publisher == publisher
            and existing.jurisdiction == jurisdiction
            and existing.source_url == source_url
            and existing.content_hash == source_content_hash
        )
        if not same:
            raise PassportConflict("同一规则版本已存在但内容不同；请登记新的 vintage")
        return existing
    rule = RuleRecord(
        tenant_id=tenant_id,
        rule_kind=rule_kind,
        title=title.strip(),
        publisher=publisher,
        document_number=document_number,
        jurisdiction=jurisdiction,
        vintage=vintage,
        valid_from=valid_from,
        valid_to=valid_to,
        status="approved",
        source_url=source_url,
        content_hash=source_content_hash,
        approved_by=str(actor_id),
        approved_at=datetime.now(timezone.utc),
    )
    db.add(rule)
    db.flush()
    return rule


def list_authoritative_rules(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    rule_kind: str | None = None,
) -> list[RuleRecord]:
    query = db.query(RuleRecord).filter(
        RuleRecord.tenant_id == tenant_id,
        RuleRecord.status == "approved",
    )
    if rule_kind:
        query = query.filter(RuleRecord.rule_kind == rule_kind)
    return query.order_by(RuleRecord.vintage.desc(), RuleRecord.document_number).all()


def calculate_passport_see(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    process_id: uuid.UUID,
    product_id: uuid.UUID,
    production_output_id: uuid.UUID,
    methodology_ref: str,
    actor_id: uuid.UUID,
) -> SEEResult:
    _account_process_product(
        db,
        tenant_id=tenant_id,
        account_id=account_id,
        process_id=process_id,
        product_id=product_id,
    )
    output = (
        db.query(ProductionOutput)
        .filter(
            ProductionOutput.id == production_output_id,
            ProductionOutput.tenant_id == tenant_id,
            ProductionOutput.process_id == process_id,
            ProductionOutput.product_id == product_id,
        )
        .first()
    )
    if output is None:
        raise LookupError("production output does not belong to passport process/product")
    return calculate_and_persist_see(
        db,
        tenant_id=tenant_id,
        process_id=process_id,
        product_id=product_id,
        production_output_id=production_output_id,
        methodology_ref=methodology_ref,
        confirmed_by=str(actor_id),
    )


def create_passport_account(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    enterprise_id: uuid.UUID,
    actor_id: uuid.UUID,
    request_key: str,
    installation_name: str,
    operator_name: str,
    country_code: str,
    unlocode: str | None,
    process_name: str,
    aggregate_goods_category: str,
    production_route: str,
    product_name: str,
    cn_code: str,
) -> InstallationAccount:
    """Create the account and first immutable fact graph, idempotently."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", request_key):
        raise ValueError("request_key must contain 16-64 letters, digits, '_' or '-'")
    validate_passport_identity(
        installation_name=installation_name,
        operator_name=operator_name,
        country_code=country_code,
        unlocode=unlocode,
        process_name=process_name,
        aggregate_goods_category=aggregate_goods_category,
        production_route=production_route,
        product_name=product_name,
        cn_code=cn_code,
    )
    existing = (
        db.query(InstallationAccount)
        .filter(
            InstallationAccount.tenant_id == tenant_id,
            InstallationAccount.request_key == request_key,
        )
        .first()
    )
    if existing is not None:
        if not _account_request_matches(
            db,
            account=existing,
            enterprise_id=enterprise_id,
            installation_name=installation_name,
            operator_name=operator_name,
            country_code=country_code,
            unlocode=unlocode,
            process_name=process_name,
            aggregate_goods_category=aggregate_goods_category,
            production_route=production_route,
            product_name=product_name,
            cn_code=cn_code,
        ):
            raise PassportConflict("同一 request_key 已绑定不同的装置建档内容")
        return existing

    enterprise = (
        db.query(Enterprise)
        .filter(
            Enterprise.id == enterprise_id,
            Enterprise.tenant_id == tenant_id,
        )
        .first()
    )
    if enterprise is None:
        raise LookupError("enterprise not found for tenant")

    actor = str(actor_id)
    normalized_country = country_code.strip().upper()
    normalized_unlocode = unlocode.strip().upper() if unlocode else None
    initial_identity = {
        "installation_name": installation_name.strip(),
        "operator_name": operator_name.strip(),
        "country_code": normalized_country,
        "unlocode": normalized_unlocode,
        "process_name": process_name.strip(),
        "aggregate_goods_category": aggregate_goods_category.strip(),
        "production_route": production_route.strip(),
        "product_name": product_name.strip(),
        "cn_code": cn_code,
    }
    account_id = uuid.uuid4()
    account_code = f"ZCY-{normalized_country}-{account_id.hex[:8].upper()}"
    account_payload = {
        "record_type": "installation_account",
        "tenant_id": tenant_id,
        "enterprise_id": enterprise_id,
        "account_code": account_code,
        "request_key": request_key,
        "created_by": actor,
        "initial_identity": initial_identity,
    }
    account = InstallationAccount(
        id=account_id,
        tenant_id=tenant_id,
        enterprise_id=enterprise_id,
        account_code=account_code,
        request_key=request_key,
        created_by=actor,
        content_hash=content_hash(account_payload),
    )
    try:
        with db.begin_nested():
            db.add(account)
            db.flush()
    except IntegrityError as exc:
        db.expire_all()
        winner = (
            db.query(InstallationAccount)
            .filter(
                InstallationAccount.tenant_id == tenant_id,
                InstallationAccount.request_key == request_key,
            )
            .first()
        )
        if winner is None:
            raise exc
        if not _account_request_matches(
            db,
            account=winner,
            enterprise_id=enterprise_id,
            installation_name=installation_name,
            operator_name=operator_name,
            country_code=country_code,
            unlocode=unlocode,
            process_name=process_name,
            aggregate_goods_category=aggregate_goods_category,
            production_route=production_route,
            product_name=product_name,
            cn_code=cn_code,
        ):
            raise PassportConflict("并发 request_key 已绑定不同的装置建档内容")
        return winner

    installation_key = idempotency_hash(tenant_id, account.id, "identity")
    installation_payload = {
        "record_type": "cbam_installation",
        "tenant_id": tenant_id,
        "account_id": account.id,
        "enterprise_id": enterprise_id,
        "name": installation_name.strip(),
        "operator_name": operator_name.strip(),
        "country_code": normalized_country,
        "unlocode": normalized_unlocode,
    }
    installation = Installation(
        tenant_id=tenant_id,
        enterprise_id=enterprise_id,
        name=installation_payload["name"],
        operator_name=installation_payload["operator_name"],
        country_code=normalized_country,
        unlocode=normalized_unlocode,
        derived_from=[f"enterprise:{enterprise_id}"],
        content_hash=content_hash(installation_payload),
        idempotency_key=installation_key,
        version=1,
        confirmed_by=actor,
        confirmed_at=datetime.now(timezone.utc),
    )
    db.add(installation)
    db.flush()

    member_payload = {
        "record_type": "installation_account_member",
        "tenant_id": tenant_id,
        "account_id": account.id,
        "installation_id": installation.id,
        "added_by": actor,
    }
    db.add(
        InstallationAccountMember(
            tenant_id=tenant_id,
            account_id=account.id,
            installation_id=installation.id,
            added_by=actor,
            content_hash=content_hash(member_payload),
        )
    )

    process_payload = {
        "record_type": "cbam_production_process",
        "tenant_id": tenant_id,
        "installation_id": installation.id,
        "name": process_name.strip(),
        "aggregate_goods_category": aggregate_goods_category.strip(),
        "production_route": production_route.strip(),
    }
    process = ProductionProcess(
        tenant_id=tenant_id,
        installation_id=installation.id,
        name=process_payload["name"],
        aggregate_goods_category=process_payload["aggregate_goods_category"],
        production_route=process_payload["production_route"],
        derived_from=[f"installation:{installation.id}"],
        content_hash=content_hash(process_payload),
        idempotency_key=idempotency_hash(tenant_id, account.id, "process", process_name),
        version=1,
        confirmed_by=actor,
        confirmed_at=datetime.now(timezone.utc),
    )
    db.add(process)
    db.flush()

    product_payload = {
        "record_type": "cbam_product",
        "tenant_id": tenant_id,
        "process_id": process.id,
        "name": product_name.strip(),
        "cn_code": cn_code,
    }
    product = CBAMProduct(
        tenant_id=tenant_id,
        process_id=process.id,
        name=product_payload["name"],
        cn_code=cn_code,
        derived_from=[f"production_process:{process.id}"],
        content_hash=content_hash(product_payload),
        idempotency_key=idempotency_hash(tenant_id, account.id, "product", cn_code),
        version=1,
        confirmed_by=actor,
        confirmed_at=datetime.now(timezone.utc),
    )
    db.add(product)
    db.flush()
    return account


def _account_request_matches(
    db: Session,
    *,
    account: InstallationAccount,
    enterprise_id: uuid.UUID,
    installation_name: str,
    operator_name: str,
    country_code: str,
    unlocode: str | None,
    process_name: str,
    aggregate_goods_category: str,
    production_route: str,
    product_name: str,
    cn_code: str,
) -> bool:
    """Prove that an idempotency replay describes the same immutable fact graph."""
    if account.enterprise_id != enterprise_id:
        return False
    normalized_identity = {
        "installation_name": installation_name.strip(),
        "operator_name": operator_name.strip(),
        "country_code": country_code.strip().upper(),
        "unlocode": unlocode.strip().upper() if unlocode else None,
        "process_name": process_name.strip(),
        "aggregate_goods_category": aggregate_goods_category.strip(),
        "production_route": production_route.strip(),
        "product_name": product_name.strip(),
        "cn_code": cn_code,
    }
    expected_hash = content_hash(
        {
            "record_type": "installation_account",
            "tenant_id": account.tenant_id,
            "enterprise_id": account.enterprise_id,
            "account_code": account.account_code,
            "request_key": account.request_key,
            "created_by": account.created_by,
            "initial_identity": normalized_identity,
        }
    )
    if account.content_hash == expected_hash:
        return True

    # Compatibility path for anchors created before the initial-request fingerprint
    # became part of the hash payload. This compares the immutable fact graph itself.
    try:
        _account, installation, processes, products = _load_base_facts(
            db,
            tenant_id=account.tenant_id,
            account_id=account.id,
        )
    except (LookupError, RuntimeError):
        return False
    if len(processes) != 1 or len(products) != 1:
        return False
    process = processes[0]
    product = products[0]
    return (
        installation.name == normalized_identity["installation_name"]
        and installation.operator_name == normalized_identity["operator_name"]
        and installation.country_code == normalized_identity["country_code"]
        and installation.unlocode == normalized_identity["unlocode"]
        and process.name == normalized_identity["process_name"]
        and process.aggregate_goods_category
        == normalized_identity["aggregate_goods_category"]
        and process.production_route == normalized_identity["production_route"]
        and product.name == normalized_identity["product_name"]
        and product.cn_code == normalized_identity["cn_code"]
    )


def list_passport_accounts(db: Session, tenant_id: uuid.UUID) -> list[dict]:
    accounts = (
        db.query(InstallationAccount)
        .filter(InstallationAccount.tenant_id == tenant_id)
        .order_by(InstallationAccount.created_at.desc(), InstallationAccount.id)
        .all()
    )
    return [passport_detail(db, tenant_id=tenant_id, account_id=item.id) for item in accounts]


def passport_detail(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> dict:
    if (period_start is None) != (period_end is None):
        raise ValueError("period_start and period_end must be supplied together")
    if period_start is not None and period_start >= period_end:
        raise ValueError("period_start must precede period_end")
    account = (
        db.query(InstallationAccount)
        .filter(
            InstallationAccount.id == account_id,
            InstallationAccount.tenant_id == tenant_id,
        )
        .first()
    )
    if account is None:
        raise LookupError("installation passport not found for tenant")
    member = (
        db.query(InstallationAccountMember)
        .filter(
            InstallationAccountMember.account_id == account.id,
            InstallationAccountMember.tenant_id == tenant_id,
        )
        .order_by(InstallationAccountMember.created_at.desc())
        .first()
    )
    if member is None:
        raise RuntimeError("installation passport has no formal identity version")
    installation = (
        db.query(Installation)
        .filter(
            Installation.id == member.installation_id,
            Installation.tenant_id == tenant_id,
        )
        .one()
    )
    installation_ids = [
        row.installation_id
        for row in db.query(InstallationAccountMember)
        .filter(
            InstallationAccountMember.account_id == account.id,
            InstallationAccountMember.tenant_id == tenant_id,
        )
        .all()
    ]
    processes = (
        db.query(ProductionProcess)
        .filter(
            ProductionProcess.tenant_id == tenant_id,
            ProductionProcess.installation_id.in_(installation_ids),
            ProductionProcess.superseded_by_id.is_(None),
        )
        .order_by(ProductionProcess.created_at, ProductionProcess.id)
        .all()
    )
    process_ids = [item.id for item in processes]
    products = (
        db.query(CBAMProduct)
        .filter(
            CBAMProduct.tenant_id == tenant_id,
            CBAMProduct.process_id.in_(process_ids),
            CBAMProduct.superseded_by_id.is_(None),
        )
        .order_by(CBAMProduct.created_at, CBAMProduct.id)
        .all()
        if process_ids
        else []
    )
    snapshot = _base_snapshot(
        account=account,
        installation=installation,
        processes=processes,
        products=products,
        period_start=period_start,
        period_end=period_end,
    )
    if period_start is not None and period_end is not None:
        snapshot = _enrich_snapshot(
            db,
            tenant_id=tenant_id,
            account=account,
            snapshot=snapshot,
            process_ids=process_ids,
            product_ids=[item.id for item in products],
            period_start=period_start,
            period_end=period_end,
        )
    assessment = _assessment(snapshot)
    profiles = (
        db.query(InstallationProfileVersion)
        .filter(
            InstallationProfileVersion.tenant_id == tenant_id,
            InstallationProfileVersion.account_id == account.id,
        )
        .order_by(InstallationProfileVersion.version.desc())
        .all()
    )
    reviews = (
        db.query(MethodologyReview)
        .filter(
            MethodologyReview.tenant_id == tenant_id,
            MethodologyReview.account_id == account.id,
        )
        .order_by(MethodologyReview.created_at.desc())
        .all()
    )
    grants = (
        db.query(DataSharingGrant)
        .filter(
            DataSharingGrant.tenant_id == tenant_id,
            DataSharingGrant.account_id == account.id,
        )
        .order_by(DataSharingGrant.created_at.desc())
        .all()
    )
    events = (
        db.query(ProfileDistributionEvent)
        .filter(
            ProfileDistributionEvent.tenant_id == tenant_id,
            ProfileDistributionEvent.account_id == account.id,
        )
        .order_by(ProfileDistributionEvent.created_at.desc())
        .all()
    )
    if period_start is None and profiles:
        assessment = profiles[0].assessment_json
    return {
        "account": {
            "id": str(account.id),
            "tenant_id": str(account.tenant_id),
            "enterprise_id": str(account.enterprise_id),
            "account_code": account.account_code,
            "created_at": account.created_at.isoformat() if account.created_at else None,
        },
        "installation": {
            "id": str(installation.id),
            "name": installation.name,
            "operator_name": installation.operator_name,
            "country_code": installation.country_code,
            "unlocode": installation.unlocode,
            "version": installation.version,
            "content_hash": installation.content_hash,
        },
        "processes": [
            {
                "id": str(item.id),
                "name": item.name,
                "aggregate_goods_category": item.aggregate_goods_category,
                "production_route": item.production_route,
                "version": item.version,
            }
            for item in processes
        ],
        "products": [
            {
                "id": str(item.id),
                "process_id": str(item.process_id),
                "name": item.name,
                "cn_code": item.cn_code,
                "version": item.version,
            }
            for item in products
        ],
        "assessment": assessment,
        "current_snapshot": snapshot,
        "profiles": [_profile_payload(db, item) for item in profiles],
        "reviews": [_review_payload(item) for item in reviews],
        "sharing_grants": [_grant_payload(db, item) for item in grants],
        "distribution_events": [_distribution_payload(item) for item in events],
    }


def list_emission_candidates(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> list[dict]:
    account, _installation, _processes, _products = _load_base_facts(
        db,
        tenant_id=tenant_id,
        account_id=account_id,
    )
    query = (
        db.query(EmissionResult, EmissionSource, ActivityData, DocumentStore)
        .join(EmissionSource, EmissionSource.id == EmissionResult.emission_source_id)
        .join(Site, Site.id == EmissionSource.site_id)
        .outerjoin(ActivityData, ActivityData.id == EmissionResult.activity_data_id)
        .outerjoin(DocumentStore, DocumentStore.id == ActivityData.document_id)
        .filter(
            EmissionResult.tenant_id == tenant_id,
            EmissionResult.superseded_by_id.is_(None),
            Site.enterprise_id == account.enterprise_id,
        )
    )
    if period_start is not None and period_end is not None:
        query = query.filter(
            EmissionResult.period_start == period_start,
            EmissionResult.period_end == period_end,
        )
    rows = query.order_by(EmissionResult.period_start.desc()).all()
    return [
        {
            "id": str(result.id),
            "source_name": source.name,
            "scope": result.scope,
            "category": source.category,
            "period_start": _iso_utc(result.period_start),
            "period_end": _iso_utc(result.period_end),
            "emissions": _decimal_text(result.co2_tonnes),
            "unit": result.unit,
            "document_id": str(document.id) if document else None,
            "document_name": document.filename if document else None,
            "evidence_ready": document is not None,
        }
        for result, source, _activity, document in rows
    ]


def create_profile_snapshot(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    period_start: datetime,
    period_end: datetime,
    actor_id: uuid.UUID,
) -> InstallationProfileVersion:
    if period_start >= period_end:
        raise ValueError("period_start must precede period_end")
    account, installation, processes, products = _load_base_facts(
        db,
        tenant_id=tenant_id,
        account_id=account_id,
    )
    snapshot = _base_snapshot(
        account=account,
        installation=installation,
        processes=processes,
        products=products,
        period_start=period_start,
        period_end=period_end,
    )
    snapshot = _enrich_snapshot(
        db,
        tenant_id=tenant_id,
        account=account,
        snapshot=snapshot,
        process_ids=[item.id for item in processes],
        product_ids=[item.id for item in products],
        period_start=period_start,
        period_end=period_end,
    )
    assessment = _assessment(snapshot)
    references = _snapshot_references(snapshot)
    key = idempotency_hash(tenant_id, account.id, period_start, period_end)
    payload = _profile_hash_payload(
        account=account,
        installation=installation,
        status="draft",
        snapshot=snapshot,
        assessment=assessment,
        references=references,
    )
    record_hash = content_hash(payload)
    previous = (
        db.query(InstallationProfileVersion)
        .filter(
            InstallationProfileVersion.tenant_id == tenant_id,
            InstallationProfileVersion.account_id == account.id,
            InstallationProfileVersion.period_start == period_start,
            InstallationProfileVersion.period_end == period_end,
            InstallationProfileVersion.superseded_by_id.is_(None),
        )
        .order_by(InstallationProfileVersion.version.desc())
        .first()
    )
    if previous is not None and previous.content_hash == record_hash:
        return previous
    profile = InstallationProfileVersion(
        tenant_id=tenant_id,
        account_id=account.id,
        installation_id=installation.id,
        period_start=period_start,
        period_end=period_end,
        status="draft",
        schema_version=1,
        completeness_score=assessment["score"],
        data_quality_grade=assessment["grade"],
        assessment_json=assessment,
        snapshot_json=snapshot,
        derived_from=references,
        content_hash=record_hash,
        idempotency_key=key,
        version=previous.version + 1 if previous else 1,
        supersedes_id=previous.id if previous else None,
        confirmed_by=str(actor_id),
        confirmed_at=datetime.now(timezone.utc),
    )
    db.add(profile)
    db.flush()
    return profile


def replay_profile_version(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    profile_version_id: uuid.UUID,
) -> dict:
    profile = _tenant_profile(db, tenant_id, profile_version_id)
    account, installation, processes, products = _load_base_facts(
        db,
        tenant_id=tenant_id,
        account_id=profile.account_id,
        installation_id=profile.installation_id,
        exact_process_ids=_ref_ids(profile.derived_from, "production_process"),
        exact_product_ids=_ref_ids(profile.derived_from, "cbam_product"),
    )
    snapshot = _base_snapshot(
        account=account,
        installation=installation,
        processes=processes,
        products=products,
        period_start=profile.period_start,
        period_end=profile.period_end,
    )
    snapshot = _enrich_snapshot(
        db,
        tenant_id=tenant_id,
        account=account,
        snapshot=snapshot,
        process_ids=[item.id for item in processes],
        product_ids=[item.id for item in products],
        period_start=profile.period_start,
        period_end=profile.period_end,
        exact_references=profile.derived_from,
    )
    assessment = _assessment(snapshot)
    references = _snapshot_references(snapshot)
    expected = content_hash(
        _profile_hash_payload(
            account=account,
            installation=installation,
            status=profile.status,
            snapshot=snapshot,
            assessment=assessment,
            references=references,
        )
    )
    matches = (
        snapshot == profile.snapshot_json
        and assessment == profile.assessment_json
        and references == profile.derived_from
        and expected == profile.content_hash
    )
    return {
        "match": matches,
        "content_hash_match": expected == profile.content_hash,
        "snapshot_match": snapshot == profile.snapshot_json,
        "assessment_match": assessment == profile.assessment_json,
    }


def create_methodology_review(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    profile_version_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    reviewer_role: str,
    verdict: str,
    summary: str,
    findings: list[dict],
) -> MethodologyReview:
    if reviewer_role not in {"platform_admin", "admin", "manager", "auditor"}:
        raise ValueError("reviewer role is not allowed")
    if verdict not in {"pass", "pass_with_actions", "fail"}:
        raise ValueError("methodology review verdict is not allowed")
    normalized_summary = summary.strip()
    if not normalized_summary:
        raise ValueError("methodology review summary cannot be blank")
    profile = _tenant_profile(db, tenant_id, profile_version_id)
    if profile.account_id != account_id:
        raise LookupError("profile does not belong to installation account")
    replay = replay_profile_version(
        db,
        tenant_id=tenant_id,
        profile_version_id=profile.id,
    )
    if not replay["match"]:
        raise PassportConflict("档案无法确定性重放，禁止复核")
    missing = [
        item["label"]
        for item in profile.assessment_json["checks"]
        if not item["passed"] and item["key"] != "methodology_review"
    ]
    if missing:
        raise PassportConflict(f"档案仍缺少：{'、'.join(missing)}")
    payload = {
        "record_type": "methodology_review",
        "tenant_id": tenant_id,
        "account_id": account_id,
        "profile_version_id": profile.id,
        "reviewer_id": reviewer_id,
        "reviewer_role": reviewer_role,
        "verdict": verdict,
        "summary": normalized_summary,
        "findings": findings,
        "disclaimer": "方法学复核不等于法定 CBAM 核查",
    }
    review = MethodologyReview(
        tenant_id=tenant_id,
        account_id=account_id,
        profile_version_id=profile.id,
        reviewer_id=str(reviewer_id),
        reviewer_role=reviewer_role,
        verdict=verdict,
        summary=normalized_summary,
        findings_json=findings,
        disclaimer=payload["disclaimer"],
        content_hash=content_hash(payload),
    )
    db.add(review)
    db.flush()
    return review


def publish_profile_version(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    profile_version_id: uuid.UUID,
    methodology_review_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> InstallationProfileVersion:
    profile = _tenant_profile(db, tenant_id, profile_version_id)
    if profile.account_id != account_id:
        raise LookupError("profile does not belong to installation account")
    missing = [
        item["label"]
        for item in profile.assessment_json["checks"]
        if not item["passed"] and item["key"] != "methodology_review"
    ]
    if missing:
        raise PassportConflict(f"档案仍缺少：{'、'.join(missing)}")
    review = (
        db.query(MethodologyReview)
        .filter(
            MethodologyReview.id == methodology_review_id,
            MethodologyReview.tenant_id == tenant_id,
            MethodologyReview.account_id == account_id,
            MethodologyReview.profile_version_id == profile.id,
        )
        .first()
    )
    if review is None or review.verdict not in {"pass", "pass_with_actions"}:
        raise PassportConflict("缺少针对当前冻结草稿的通过方法学复核")
    replay = replay_profile_version(
        db,
        tenant_id=tenant_id,
        profile_version_id=profile.id,
    )
    if not replay["match"]:
        raise PassportConflict("档案无法确定性重放，禁止发布")
    current_account, current_installation, current_processes, current_products = (
        _load_base_facts(
            db,
            tenant_id=tenant_id,
            account_id=account_id,
        )
    )
    current_snapshot = _base_snapshot(
        account=current_account,
        installation=current_installation,
        processes=current_processes,
        products=current_products,
        period_start=profile.period_start,
        period_end=profile.period_end,
    )
    current_snapshot = _enrich_snapshot(
        db,
        tenant_id=tenant_id,
        account=current_account,
        snapshot=current_snapshot,
        process_ids=[item.id for item in current_processes],
        product_ids=[item.id for item in current_products],
        period_start=profile.period_start,
        period_end=profile.period_end,
    )
    if _snapshot_references(current_snapshot) != profile.derived_from:
        raise PassportConflict("正式事实已变化，请重新冻结档案并完成方法学复核")
    account, installation, processes, products = _load_base_facts(
        db,
        tenant_id=tenant_id,
        account_id=account_id,
        installation_id=profile.installation_id,
        exact_process_ids=_ref_ids(profile.derived_from, "production_process"),
        exact_product_ids=_ref_ids(profile.derived_from, "cbam_product"),
    )
    snapshot = _base_snapshot(
        account=account,
        installation=installation,
        processes=processes,
        products=products,
        period_start=profile.period_start,
        period_end=profile.period_end,
    )
    snapshot = _enrich_snapshot(
        db,
        tenant_id=tenant_id,
        account=account,
        snapshot=snapshot,
        process_ids=[item.id for item in processes],
        product_ids=[item.id for item in products],
        period_start=profile.period_start,
        period_end=profile.period_end,
        exact_references=[
            *profile.derived_from,
            f"methodology_review:{review.id}",
        ],
    )
    assessment = _assessment(snapshot)
    if assessment["score"] != 100:
        raise PassportConflict("加入复核后档案仍未满足全部发布谓词")
    references = _snapshot_references(snapshot)
    payload = _profile_hash_payload(
        account=account,
        installation=installation,
        status="published",
        snapshot=snapshot,
        assessment=assessment,
        references=references,
    )
    published = InstallationProfileVersion(
        tenant_id=tenant_id,
        account_id=account_id,
        installation_id=installation.id,
        period_start=profile.period_start,
        period_end=profile.period_end,
        status="published",
        schema_version=1,
        completeness_score=100,
        data_quality_grade=assessment["grade"],
        assessment_json=assessment,
        snapshot_json=snapshot,
        derived_from=references,
        content_hash=content_hash(payload),
        idempotency_key=profile.idempotency_key,
        version=profile.version + 1,
        supersedes_id=profile.id,
        confirmed_by=str(actor_id),
        confirmed_at=datetime.now(timezone.utc),
    )
    existing = (
        db.query(InstallationProfileVersion)
        .filter(
            InstallationProfileVersion.tenant_id == tenant_id,
            InstallationProfileVersion.supersedes_id == profile.id,
        )
        .first()
    )
    if existing is not None:
        if existing.content_hash != published.content_hash:
            raise PassportConflict("草稿已经发布为不同内容的后继版本")
        return existing
    try:
        with db.begin_nested():
            db.add(published)
            db.flush()
    except IntegrityError as exc:
        db.expire_all()
        winner = (
            db.query(InstallationProfileVersion)
            .filter(
                InstallationProfileVersion.tenant_id == tenant_id,
                InstallationProfileVersion.supersedes_id == profile.id,
            )
            .first()
        )
        if winner is not None and winner.content_hash == published.content_hash:
            return winner
        raise exc
    return published


def _load_base_facts(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    installation_id: uuid.UUID | None = None,
    exact_process_ids: list[uuid.UUID] | None = None,
    exact_product_ids: list[uuid.UUID] | None = None,
):
    account = (
        db.query(InstallationAccount)
        .filter(
            InstallationAccount.id == account_id,
            InstallationAccount.tenant_id == tenant_id,
        )
        .first()
    )
    if account is None:
        raise LookupError("installation passport not found for tenant")
    members = (
        db.query(InstallationAccountMember)
        .filter(
            InstallationAccountMember.account_id == account.id,
            InstallationAccountMember.tenant_id == tenant_id,
        )
        .order_by(InstallationAccountMember.created_at.desc())
        .all()
    )
    member_ids = [item.installation_id for item in members]
    selected_installation_id = installation_id or (member_ids[0] if member_ids else None)
    if selected_installation_id not in member_ids:
        raise LookupError("installation version is not a member of this passport")
    installation = (
        db.query(Installation)
        .filter(
            Installation.id == selected_installation_id,
            Installation.tenant_id == tenant_id,
        )
        .one()
    )
    process_query = db.query(ProductionProcess).filter(
        ProductionProcess.tenant_id == tenant_id,
        ProductionProcess.installation_id.in_(member_ids),
    )
    if exact_process_ids is None:
        process_query = process_query.filter(ProductionProcess.superseded_by_id.is_(None))
    else:
        process_query = process_query.filter(ProductionProcess.id.in_(exact_process_ids))
    processes = process_query.order_by(ProductionProcess.id).all()
    process_ids = [item.id for item in processes]
    product_query = db.query(CBAMProduct).filter(
        CBAMProduct.tenant_id == tenant_id,
        CBAMProduct.process_id.in_(process_ids),
    )
    if exact_product_ids is None:
        product_query = product_query.filter(CBAMProduct.superseded_by_id.is_(None))
    else:
        product_query = product_query.filter(CBAMProduct.id.in_(exact_product_ids))
    products = product_query.order_by(CBAMProduct.id).all() if process_ids else []
    return account, installation, processes, products


def _base_snapshot(
    *,
    account,
    installation,
    processes,
    products,
    period_start,
    period_end,
) -> dict:
    return {
        "schema_version": 1,
        "account": {
            "id": str(account.id),
            "account_code": account.account_code,
            "enterprise_id": str(account.enterprise_id),
        },
        "installation": {
            "id": str(installation.id),
            "name": installation.name,
            "operator_name": installation.operator_name,
            "country_code": installation.country_code,
            "unlocode": installation.unlocode,
            "version": installation.version,
            "content_hash": installation.content_hash,
        },
        "period": {
            "start": _iso_utc(period_start),
            "end": _iso_utc(period_end),
        },
        "processes": [
            {
                "id": str(item.id),
                "name": item.name,
                "aggregate_goods_category": item.aggregate_goods_category,
                "production_route": item.production_route,
                "version": item.version,
                "content_hash": item.content_hash,
            }
            for item in sorted(processes, key=lambda row: str(row.id))
        ],
        "products": [
            {
                "id": str(item.id),
                "process_id": str(item.process_id),
                "name": item.name,
                "cn_code": item.cn_code,
                "version": item.version,
                "content_hash": item.content_hash,
            }
            for item in sorted(products, key=lambda row: str(row.id))
        ],
        "production_outputs": [],
        "attributions": [],
        "emission_results": [],
        "evidence_manifest": [],
        "see_results": [],
        "rule_records": [],
        "methodology_review": None,
    }


def _enrich_snapshot(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    account: InstallationAccount,
    snapshot: dict,
    process_ids: list[uuid.UUID],
    product_ids: list[uuid.UUID],
    period_start: datetime,
    period_end: datetime,
    exact_references: list[str] | None = None,
) -> dict:
    """Project current or exact immutable facts into a safe passport snapshot."""
    output_query = db.query(ProductionOutput).filter(
        ProductionOutput.tenant_id == tenant_id,
        ProductionOutput.process_id.in_(process_ids),
        ProductionOutput.product_id.in_(product_ids),
        ProductionOutput.period_start == period_start,
        ProductionOutput.period_end == period_end,
    )
    attribution_query = db.query(SourceStreamAttribution).filter(
        SourceStreamAttribution.tenant_id == tenant_id,
        SourceStreamAttribution.process_id.in_(process_ids),
        SourceStreamAttribution.period_start == period_start,
        SourceStreamAttribution.period_end == period_end,
    )
    see_query = db.query(SEEResult).filter(
        SEEResult.tenant_id == tenant_id,
        SEEResult.process_id.in_(process_ids),
        SEEResult.product_id.in_(product_ids),
        SEEResult.period_start == period_start,
        SEEResult.period_end == period_end,
    )
    if exact_references is None:
        outputs = output_query.filter(ProductionOutput.superseded_by_id.is_(None)).all()
        attributions = attribution_query.filter(
            SourceStreamAttribution.superseded_by_id.is_(None)
        ).all()
        see_results = see_query.filter(SEEResult.superseded_by_id.is_(None)).all()
        review = None
    else:
        output_ids = _ref_ids(exact_references, "production_output")
        attribution_ids = _ref_ids(exact_references, "attribution")
        see_ids = _ref_ids(exact_references, "see_result")
        outputs = output_query.filter(ProductionOutput.id.in_(output_ids)).all()
        attributions = attribution_query.filter(
            SourceStreamAttribution.id.in_(attribution_ids)
        ).all()
        see_results = see_query.filter(SEEResult.id.in_(see_ids)).all()
        review_ids = _ref_ids(exact_references, "methodology_review")
        review = (
            db.query(MethodologyReview)
            .filter(
                MethodologyReview.id == review_ids[0],
                MethodologyReview.tenant_id == tenant_id,
                MethodologyReview.account_id == account.id,
            )
            .first()
            if len(review_ids) == 1
            else None
        )

    source_ids = []
    for item in attributions:
        prefix, separator, identifier = item.source_ref.partition(":")
        if prefix == "emission_result" and separator == ":":
            try:
                source_ids.append(uuid.UUID(identifier))
            except ValueError:
                continue
    result_query = (
        db.query(EmissionResult)
        .join(EmissionSource, EmissionSource.id == EmissionResult.emission_source_id)
        .join(Site, Site.id == EmissionSource.site_id)
        .filter(
            EmissionResult.tenant_id == tenant_id,
            EmissionResult.id.in_(source_ids),
            EmissionResult.period_start == period_start,
            EmissionResult.period_end == period_end,
            EmissionResult.scope.in_(("scope_1", "scope_2")),
            EmissionResult.unit == "tCO2e",
            Site.enterprise_id == account.enterprise_id,
        )
    )
    if exact_references is None:
        result_query = result_query.filter(EmissionResult.superseded_by_id.is_(None))
    else:
        result_query = result_query.filter(
            EmissionResult.id.in_(_ref_ids(exact_references, "emission_result"))
        )
    emission_results = result_query.all() if source_ids else []
    activity_ids = [item.activity_data_id for item in emission_results if item.activity_data_id]
    activities = (
        db.query(ActivityData)
        .filter(
            ActivityData.tenant_id == tenant_id,
            ActivityData.id.in_(activity_ids),
        )
        .all()
        if activity_ids
        else []
    )
    activity_by_id = {item.id: item for item in activities}
    document_ids = [item.document_id for item in activities if item.document_id]
    document_query = db.query(DocumentStore).filter(
        DocumentStore.tenant_id == tenant_id,
        DocumentStore.enterprise_id == account.enterprise_id,
        DocumentStore.id.in_(document_ids),
    )
    if exact_references is not None:
        document_query = document_query.filter(
            DocumentStore.id.in_(_ref_ids(exact_references, "document"))
        )
    documents = document_query.all() if document_ids else []

    rule_ids = []
    for item in see_results:
        prefix, separator, identifier = item.methodology_ref.partition(":")
        if prefix == "rule_record" and separator == ":":
            try:
                rule_ids.append(uuid.UUID(identifier))
            except ValueError:
                continue
    rule_query = db.query(RuleRecord).filter(
        RuleRecord.tenant_id == tenant_id,
        RuleRecord.id.in_(rule_ids),
        RuleRecord.status == "approved",
    )
    if exact_references is not None:
        rule_query = rule_query.filter(
            RuleRecord.id.in_(_ref_ids(exact_references, "rule_record"))
        )
    rules = rule_query.all() if rule_ids else []

    snapshot["production_outputs"] = [
        {
            "id": str(item.id),
            "process_id": str(item.process_id),
            "product_id": str(item.product_id),
            "period_start": _iso_utc(item.period_start),
            "period_end": _iso_utc(item.period_end),
            "quantity": _decimal_text(item.quantity),
            "unit": item.unit,
            "version": item.version,
            "content_hash": item.content_hash,
        }
        for item in sorted(outputs, key=lambda row: str(row.id))
    ]
    snapshot["attributions"] = [
        {
            "id": str(item.id),
            "process_id": str(item.process_id),
            "source_ref": item.source_ref,
            "period_start": _iso_utc(item.period_start),
            "period_end": _iso_utc(item.period_end),
            "share": _decimal_text(item.share),
            "method": item.method,
            "version": item.version,
            "content_hash": item.content_hash,
        }
        for item in sorted(attributions, key=lambda row: str(row.id))
    ]
    snapshot["emission_results"] = [
        {
            "id": str(item.id),
            "emission_source_id": str(item.emission_source_id),
            "activity_data_id": str(item.activity_data_id) if item.activity_data_id else None,
            "document_id": (
                str(activity_by_id[item.activity_data_id].document_id)
                if item.activity_data_id in activity_by_id
                and activity_by_id[item.activity_data_id].document_id
                else None
            ),
            "scope": item.scope,
            "period_start": _iso_utc(item.period_start),
            "period_end": _iso_utc(item.period_end),
            "emissions": _decimal_text(item.co2_tonnes),
            "unit": item.unit,
            "factor_id": str(item.factor_id) if item.factor_id else None,
            "version": item.version,
            "content_hash": item.content_hash,
        }
        for item in sorted(emission_results, key=lambda row: str(row.id))
    ]
    snapshot["evidence_manifest"] = [
        {
            "id": str(item.id),
            "filename": item.filename,
            "mime_type": item.mime_type,
            "size_bytes": item.size_bytes,
            "doc_type": item.doc_type,
            "content_hash": item.content_hash,
        }
        for item in sorted(documents, key=lambda row: str(row.id))
    ]
    snapshot["see_results"] = [
        {
            "id": str(item.id),
            "process_id": str(item.process_id),
            "product_id": str(item.product_id),
            "production_output_id": str(item.production_output_id),
            "direct_emissions": _decimal_text(item.direct_emissions),
            "indirect_emissions": _decimal_text(item.indirect_emissions),
            "precursor_emissions": _decimal_text(item.precursor_emissions),
            "total_emissions": _decimal_text(item.total_emissions),
            "emissions_unit": item.emissions_unit,
            "specific_emissions": _decimal_text(item.specific_emissions),
            "specific_unit": item.specific_unit,
            "data_quality": item.data_quality,
            "methodology_ref": item.methodology_ref,
            "derived_from": item.derived_from,
            "version": item.version,
            "content_hash": item.content_hash,
            "replay_match": replay_see_result(
                db,
                tenant_id=tenant_id,
                see_result_id=item.id,
            )["match"],
        }
        for item in sorted(see_results, key=lambda row: str(row.id))
    ]
    snapshot["rule_records"] = [
        {
            "id": str(item.id),
            "rule_kind": item.rule_kind,
            "title": item.title,
            "publisher": item.publisher,
            "document_number": item.document_number,
            "jurisdiction": item.jurisdiction,
            "vintage": item.vintage,
            "valid_from": _iso_utc(item.valid_from),
            "valid_to": _iso_utc(item.valid_to),
            "source_url": item.source_url,
            "content_hash": item.content_hash,
        }
        for item in sorted(rules, key=lambda row: str(row.id))
    ]
    snapshot["methodology_review"] = _review_payload(review) if review else None
    return snapshot


def _assessment(snapshot: dict) -> dict:
    installation = snapshot["installation"]
    attribution_totals: dict[str, Decimal] = {}
    for item in snapshot["attributions"]:
        attribution_totals[item["source_ref"]] = (
            attribution_totals.get(item["source_ref"], Decimal("0"))
            + Decimal(item["share"])
        )
    attribution_complete = bool(attribution_totals) and all(
        value == Decimal("1") for value in attribution_totals.values()
    )
    result_documents = {
        item["document_id"]
        for item in snapshot["emission_results"]
        if item["document_id"] is not None
    }
    manifest_ids = {item["id"] for item in snapshot["evidence_manifest"]}
    evidence_complete = bool(result_documents) and result_documents <= manifest_ids
    output_refs = {
        f"production_output:{item['id']}" for item in snapshot["production_outputs"]
    }
    attribution_refs = {
        f"attribution:{item['id']}" for item in snapshot["attributions"]
    }
    see_input_refs = {
        reference
        for item in snapshot["see_results"]
        for reference in item["derived_from"]
    }
    see_replay_complete = (
        bool(snapshot["see_results"])
        and all(item["replay_match"] for item in snapshot["see_results"])
        and output_refs <= see_input_refs
        and attribution_refs <= see_input_refs
    )
    methodology_refs = {
        item["methodology_ref"] for item in snapshot["see_results"]
    }
    rule_refs = {f"rule_record:{item['id']}" for item in snapshot["rule_records"]}
    rules_complete = bool(methodology_refs) and methodology_refs <= rule_refs
    review = snapshot["methodology_review"]
    review_passed = bool(review) and review["verdict"] in {
        "pass",
        "pass_with_actions",
    }
    checks = [
        _check("installation_identity", bool(installation["name"] and installation["operator_name"] and installation["country_code"]), "装置身份"),
        _check("production_process", bool(snapshot["processes"]), "生产工序"),
        _check("product", bool(snapshot["products"]), "产品与 CN 编码"),
        _check("production_output", bool(snapshot["production_outputs"]), "报告期产量"),
        _check("attributed_emissions", attribution_complete, "活动排放归集"),
        _check("evidence_documents", evidence_complete, "源文件证据"),
        _check("deterministic_see", see_replay_complete, "确定性 SEE"),
        _check("authoritative_rule", rules_complete, "权威方法学规则"),
        _check("methodology_review", review_passed, "方法学复核"),
    ]
    passed = sum(1 for item in checks if item["passed"])
    return {
        "score": passed * 100 // len(checks),
        "grade": "A" if passed == len(checks) else "B" if passed >= 7 else "C",
        "checks": checks,
        "missing_keys": [item["key"] for item in checks if not item["passed"]],
        "ready_to_publish": passed == len(checks),
    }


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _decimal_text(value) -> str:
    return format(Decimal(str(value)), "f")


def _exact_decimal(value, label: str) -> Decimal:
    if isinstance(value, bool | float):
        raise TypeError(f"{label} rejects binary float values")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be an exact decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be finite")
    return result


def _same_instant(left: datetime, right: datetime) -> bool:
    def normalize(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

    return normalize(left).astimezone(timezone.utc) == normalize(right).astimezone(
        timezone.utc
    )


def _account_process_product(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    process_id: uuid.UUID,
    product_id: uuid.UUID,
) -> tuple[InstallationAccount, ProductionProcess, CBAMProduct]:
    account, _installation, processes, products = _load_base_facts(
        db,
        tenant_id=tenant_id,
        account_id=account_id,
    )
    process = next((item for item in processes if item.id == process_id), None)
    product = next((item for item in products if item.id == product_id), None)
    if process is None or product is None or product.process_id != process.id:
        raise LookupError("process or product does not belong to installation passport")
    return account, process, product


def _snapshot_references(snapshot: dict) -> list[str]:
    references = [
        f"installation:{snapshot['installation']['id']}",
        *[f"production_process:{item['id']}" for item in snapshot["processes"]],
        *[f"cbam_product:{item['id']}" for item in snapshot["products"]],
        *[f"production_output:{item['id']}" for item in snapshot["production_outputs"]],
        *[f"attribution:{item['id']}" for item in snapshot["attributions"]],
        *[f"emission_result:{item['id']}" for item in snapshot["emission_results"]],
        *[f"document:{item['id']}" for item in snapshot["evidence_manifest"]],
        *[f"see_result:{item['id']}" for item in snapshot["see_results"]],
        *[f"rule_record:{item['id']}" for item in snapshot["rule_records"]],
    ]
    if snapshot["methodology_review"]:
        references.append(
            f"methodology_review:{snapshot['methodology_review']['id']}"
        )
    return references


def _profile_hash_payload(*, account, installation, status, snapshot, assessment, references):
    return {
        "record_type": "installation_profile_version",
        "tenant_id": account.tenant_id,
        "account_id": account.id,
        "installation_id": installation.id,
        "status": status,
        "schema_version": 1,
        "snapshot": snapshot,
        "assessment": assessment,
        "derived_from": references,
    }


def _tenant_profile(db, tenant_id, profile_id) -> InstallationProfileVersion:
    profile = (
        db.query(InstallationProfileVersion)
        .filter(
            InstallationProfileVersion.id == profile_id,
            InstallationProfileVersion.tenant_id == tenant_id,
        )
        .first()
    )
    if profile is None:
        raise LookupError("profile version not found for tenant")
    return profile


def _ref_ids(references: list[str], prefix: str) -> list[uuid.UUID]:
    result = []
    marker = f"{prefix}:"
    for reference in references:
        if reference.startswith(marker):
            result.append(uuid.UUID(reference.removeprefix(marker)))
    return result


def _profile_payload(db: Session, profile: InstallationProfileVersion) -> dict:
    return {
        "id": str(profile.id),
        "account_id": str(profile.account_id),
        "installation_id": str(profile.installation_id),
        "period_start": profile.period_start.isoformat(),
        "period_end": profile.period_end.isoformat(),
        "status": profile.status,
        "schema_version": profile.schema_version,
        "version": profile.version,
        "completeness_score": profile.completeness_score,
        "data_quality_grade": profile.data_quality_grade,
        "content_hash": profile.content_hash,
        "assessment": profile.assessment_json,
        "snapshot": profile.snapshot_json,
        "replay": replay_profile_version(
            db,
            tenant_id=profile.tenant_id,
            profile_version_id=profile.id,
        ),
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
    }


def profile_payload(db: Session, profile: InstallationProfileVersion) -> dict:
    return _profile_payload(db, profile)


def _review_payload(review: MethodologyReview) -> dict:
    return {
        "id": str(review.id),
        "profile_version_id": str(review.profile_version_id),
        "reviewer_id": review.reviewer_id,
        "reviewer_role": review.reviewer_role,
        "verdict": review.verdict,
        "summary": review.summary,
        "findings": review.findings_json,
        "disclaimer": review.disclaimer,
        "content_hash": review.content_hash,
        "created_at": _iso_utc(review.created_at),
    }


def review_payload(review: MethodologyReview) -> dict:
    return _review_payload(review)


def grant_payload(db: Session, grant: DataSharingGrant) -> dict:
    return _grant_payload(db, grant)


def revocation_payload(record: DataSharingRevocation) -> dict:
    return {
        "id": str(record.id),
        "grant_id": str(record.grant_id),
        "revoked_by": record.revoked_by,
        "reason": record.reason,
        "content_hash": record.content_hash,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def _grant_payload(db: Session, grant: DataSharingGrant) -> dict:
    revocation = (
        db.query(DataSharingRevocation)
        .filter(
            DataSharingRevocation.tenant_id == grant.tenant_id,
            DataSharingRevocation.grant_id == grant.id,
        )
        .first()
    )
    return {
        "id": str(grant.id),
        "account_id": str(grant.account_id),
        "profile_version_id": str(grant.profile_version_id),
        "recipient_tenant_id": (
            str(grant.recipient_tenant_id) if grant.recipient_tenant_id else None
        ),
        "recipient_name": grant.recipient_name,
        "recipient_type": grant.recipient_type,
        "purpose": grant.purpose,
        "scopes": grant.scopes_json,
        "expires_at": _iso_utc(grant.expires_at),
        "active": _grant_is_active(db, grant),
        "revocation": revocation_payload(revocation) if revocation else None,
        "content_hash": grant.content_hash,
        "created_at": grant.created_at.isoformat() if grant.created_at else None,
    }


def _distribution_payload(record: ProfileDistributionEvent) -> dict:
    return {
        "id": str(record.id),
        "profile_version_id": str(record.profile_version_id),
        "grant_id": str(record.grant_id),
        "channel": record.channel,
        "delivered_to": record.delivered_to,
        "package_hash": record.package_hash,
        "actor_id": record.actor_id,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _grant_is_active(db: Session, grant: DataSharingGrant) -> bool:
    revoked = (
        db.query(DataSharingRevocation.id)
        .filter(
            DataSharingRevocation.tenant_id == grant.tenant_id,
            DataSharingRevocation.grant_id == grant.id,
        )
        .first()
        is not None
    )
    return not revoked and _aware(grant.expires_at) > datetime.now(timezone.utc)


def _owner_grant(
    db: Session,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    grant_id: uuid.UUID,
) -> DataSharingGrant:
    grant = (
        db.query(DataSharingGrant)
        .filter(
            DataSharingGrant.id == grant_id,
            DataSharingGrant.tenant_id == tenant_id,
            DataSharingGrant.account_id == account_id,
        )
        .first()
    )
    if grant is None:
        raise LookupError("sharing grant not found for owner tenant")
    return grant


def _deliver_package(
    db: Session,
    *,
    grant: DataSharingGrant,
    actor_id: uuid.UUID,
    channel: str,
) -> dict:
    if not _grant_is_active(db, grant):
        raise PassportConflict("共享授权已撤销或过期")
    profile = _tenant_profile(db, grant.tenant_id, grant.profile_version_id)
    if profile.status != "published" or not replay_profile_version(
        db,
        tenant_id=grant.tenant_id,
        profile_version_id=profile.id,
    )["match"]:
        raise PassportConflict("共享版本未发布或无法确定性重放")
    snapshot = profile.snapshot_json
    scopes = set(grant.scopes_json)
    package = {
        "schema": "zcy.installation-passport.package.v1",
        "profile_version_id": str(profile.id),
        "profile_version": profile.version,
        "period": snapshot["period"],
        "grant": {
            "id": str(grant.id),
            "recipient_name": grant.recipient_name,
            "recipient_type": grant.recipient_type,
            "purpose": grant.purpose,
            "scopes": grant.scopes_json,
            "expires_at": _iso_utc(grant.expires_at),
        },
        "verification_status": {
            "profile_status": profile.status,
            "completeness_score": profile.completeness_score,
            "data_quality_grade": profile.data_quality_grade,
            "statutory_verification": False,
            "notice": "方法学复核不等于法定 CBAM 核查",
        },
    }
    if "identity" in scopes:
        package["account"] = snapshot["account"]
        package["installation"] = snapshot["installation"]
    if "processes" in scopes:
        package["processes"] = snapshot["processes"]
    if "products" in scopes:
        package["products"] = snapshot["products"]
    if "outputs" in scopes:
        package["production_outputs"] = snapshot["production_outputs"]
    if "emissions" in scopes:
        package["attributions"] = snapshot["attributions"]
        package["emission_results"] = snapshot["emission_results"]
        package["see_results"] = snapshot["see_results"]
    if "evidence_manifest" in scopes:
        package["evidence_manifest"] = snapshot["evidence_manifest"]
    if "methodology" in scopes:
        package["rule_records"] = snapshot["rule_records"]
    if "review" in scopes:
        package["methodology_review"] = snapshot["methodology_review"]
    package_hash = content_hash(package)
    event_payload = {
        "record_type": "profile_distribution_event",
        "tenant_id": grant.tenant_id,
        "account_id": grant.account_id,
        "profile_version_id": profile.id,
        "grant_id": grant.id,
        "channel": channel,
        "delivered_to": grant.recipient_name,
        "package_hash": package_hash,
        "actor_id": actor_id,
    }
    db.add(
        ProfileDistributionEvent(
            tenant_id=grant.tenant_id,
            account_id=grant.account_id,
            profile_version_id=profile.id,
            grant_id=grant.id,
            channel=channel,
            delivered_to=grant.recipient_name,
            package_hash=package_hash,
            actor_id=str(actor_id),
            content_hash=content_hash(event_payload),
        )
    )
    db.flush()
    return {"package_hash": package_hash, "package": package}


def _check(key: str, passed: bool, label: str) -> dict:
    return {
        "key": key,
        "label": label,
        "passed": passed,
        "reason": "已满足" if passed else f"尚未满足：{label}",
    }


def validate_passport_identity(
    *,
    installation_name: str,
    operator_name: str,
    country_code: str,
    unlocode: str | None,
    process_name: str,
    aggregate_goods_category: str,
    production_route: str,
    product_name: str,
    cn_code: str,
) -> None:
    values = {
        "installation_name": installation_name,
        "operator_name": operator_name,
        "process_name": process_name,
        "aggregate_goods_category": aggregate_goods_category,
        "production_route": production_route,
        "product_name": product_name,
    }
    if any(not value.strip() for value in values.values()):
        raise ValueError("installation, process, and product fields cannot be blank")
    if not re.fullmatch(r"[A-Z]{2}", country_code.strip().upper()):
        raise ValueError("country_code must be two uppercase letters")
    if unlocode and not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}", unlocode.strip().upper()):
        raise ValueError("unlocode must be a five-character UN/LOCODE")
    if not re.fullmatch(r"\d{8}", cn_code):
        raise ValueError("cn_code must contain exactly eight digits")
