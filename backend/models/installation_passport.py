"""Stable installation-account objects for the carbon-data passport product."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    Uuid,
    event,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.models.base import TimestampMixin, UUIDMixin
from backend.models.ledger import LedgerImmutableError, LedgerIntegrityError
from backend.models.ledger import LedgerRecordMixin


class InstallationAccount(Base, UUIDMixin, TimestampMixin):
    """Stable passport anchor; changing installation facts never changes this ID."""

    __tablename__ = "installation_accounts"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "tenant_id",
            name="uq_installation_accounts_id_tenant",
        ),
        UniqueConstraint(
            "tenant_id",
            "account_code",
            name="uq_installation_accounts_tenant_code",
        ),
        UniqueConstraint(
            "tenant_id",
            "request_key",
            name="uq_installation_accounts_tenant_request",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    enterprise_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("enterprises.id"),
        nullable=False,
        index=True,
    )
    account_code: Mapped[str] = mapped_column(String(40), nullable=False)
    request_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class InstallationAccountMember(Base, UUIDMixin, TimestampMixin):
    """Immutable membership linking an account to an installation fact version."""

    __tablename__ = "installation_account_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "tenant_id"],
            ["installation_accounts.id", "installation_accounts.tenant_id"],
            name="fk_installation_account_member_account_tenant",
        ),
        ForeignKeyConstraint(
            ["installation_id", "tenant_id"],
            ["cbam_installations.id", "cbam_installations.tenant_id"],
            name="fk_installation_account_member_installation_tenant",
        ),
        UniqueConstraint(
            "account_id",
            "installation_id",
            name="uq_installation_account_member_pair",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    installation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        index=True,
    )
    added_by: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class InstallationProfileVersion(
    Base,
    UUIDMixin,
    TimestampMixin,
    LedgerRecordMixin,
):
    """Immutable, replayable projection of one installation reporting period."""

    __tablename__ = "installation_profile_versions"

    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("installation_accounts.id"),
        nullable=False,
        index=True,
    )
    installation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("cbam_installations.id"),
        nullable=False,
        index=True,
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    completeness_score: Mapped[int] = mapped_column(Integer, nullable=False)
    data_quality_grade: Mapped[str] = mapped_column(String(2), nullable=False)
    assessment_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)


class MethodologyReview(Base, UUIDMixin, TimestampMixin):
    """Immutable human review; explicitly not a statutory CBAM verification."""

    __tablename__ = "methodology_reviews"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "tenant_id",
            name="uq_methodology_reviews_id_tenant",
        ),
        CheckConstraint(
            "verdict IN ('pass', 'pass_with_actions', 'fail')",
            name="ck_methodology_reviews_verdict",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("installation_accounts.id"),
        nullable=False,
        index=True,
    )
    profile_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("installation_profile_versions.id"),
        nullable=False,
        index=True,
    )
    reviewer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewer_role: Mapped[str] = mapped_column(String(32), nullable=False)
    verdict: Mapped[str] = mapped_column(String(24), nullable=False)
    summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    findings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    disclaimer: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class DataSharingGrant(Base, UUIDMixin, TimestampMixin):
    """Immutable least-privilege grant for one published profile version."""

    __tablename__ = "data_sharing_grants"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "tenant_id",
            name="uq_data_sharing_grants_id_tenant",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("installation_accounts.id"),
        nullable=False,
        index=True,
    )
    profile_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("installation_profile_versions.id"),
        nullable=False,
        index=True,
    )
    recipient_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("tenants.id"),
        nullable=True,
        index=True,
    )
    recipient_name: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient_type: Mapped[str] = mapped_column(String(32), nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    scopes_json: Mapped[list] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class DataSharingRevocation(Base, UUIDMixin, TimestampMixin):
    """Append-only revocation event; grants are never updated in place."""

    __tablename__ = "data_sharing_revocations"
    __table_args__ = (
        UniqueConstraint("grant_id", name="uq_data_sharing_revocations_grant"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    grant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("data_sharing_grants.id"),
        nullable=False,
        index=True,
    )
    revoked_by: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class ProfileDistributionEvent(Base, UUIDMixin, TimestampMixin):
    """Immutable proof that a scoped package was actually produced or accessed."""

    __tablename__ = "profile_distribution_events"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("installation_accounts.id"),
        nullable=False,
        index=True,
    )
    profile_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("installation_profile_versions.id"),
        nullable=False,
        index=True,
    )
    grant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("data_sharing_grants.id"),
        nullable=False,
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    delivered_to: Mapped[str] = mapped_column(String(255), nullable=False)
    package_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


def _tenant_owner(connection, table_name: str, record_id) -> uuid.UUID | None:
    table = Base.metadata.tables[table_name]
    return connection.execute(
        select(table.c.tenant_id).where(table.c.id == record_id)
    ).scalar_one_or_none()


def _reference_ids(references: list[str] | None, prefix: str) -> list[uuid.UUID]:
    marker = f"{prefix}:"
    result: list[uuid.UUID] = []
    for reference in references or []:
        if not isinstance(reference, str) or not reference.startswith(marker):
            continue
        try:
            result.append(uuid.UUID(reference.removeprefix(marker)))
        except ValueError as exc:
            raise LedgerIntegrityError(
                f"published profile contains malformed {prefix} reference"
            ) from exc
    return result


def _assert_owned_references(
    connection,
    *,
    table_name: str,
    record_ids: list[uuid.UUID],
    tenant_id: uuid.UUID,
    label: str,
    conditions=(),
) -> None:
    if not record_ids:
        raise LedgerIntegrityError(f"published profile requires {label} reference")
    table = Base.metadata.tables[table_name]
    found = connection.execute(
        select(table.c.id).where(
            table.c.id.in_(record_ids),
            table.c.tenant_id == tenant_id,
            *conditions,
        )
    ).scalars().all()
    if {str(item) for item in found} != {str(item) for item in record_ids}:
        raise LedgerIntegrityError(
            f"published profile {label} reference is missing, foreign, or inapplicable"
        )


def _validate_published_references(connection, target: InstallationProfileVersion) -> None:
    if target.supersedes_id is None:
        raise LedgerIntegrityError("published profile must supersede its reviewed draft")
    references = target.derived_from or []
    installation_ids = _reference_ids(references, "installation")
    if installation_ids != [target.installation_id]:
        raise LedgerIntegrityError("published profile must reference its exact installation")

    review_ids = _reference_ids(references, "methodology_review")
    if len(review_ids) != 1:
        raise LedgerIntegrityError("published profile requires exactly one methodology review")
    review_table = Base.metadata.tables["methodology_reviews"]
    review = connection.execute(
        select(review_table.c.id).where(
            review_table.c.id == review_ids[0],
            review_table.c.tenant_id == target.tenant_id,
            review_table.c.account_id == target.account_id,
            review_table.c.profile_version_id == target.supersedes_id,
            review_table.c.verdict.in_(("pass", "pass_with_actions")),
        )
    ).scalar_one_or_none()
    if review is None:
        raise LedgerIntegrityError("published profile requires a passing review of its parent draft")

    process_ids = _reference_ids(references, "production_process")
    if not process_ids:
        raise LedgerIntegrityError("published profile requires production process reference")
    process_table = Base.metadata.tables["cbam_production_processes"]
    member_table = Base.metadata.tables["installation_account_members"]
    valid_processes = connection.execute(
        select(process_table.c.id)
        .join(
            member_table,
            member_table.c.installation_id == process_table.c.installation_id,
        )
        .where(
            process_table.c.id.in_(process_ids),
            process_table.c.tenant_id == target.tenant_id,
            member_table.c.tenant_id == target.tenant_id,
            member_table.c.account_id == target.account_id,
        )
    ).scalars().all()
    if {str(item) for item in valid_processes} != {str(item) for item in process_ids}:
        raise LedgerIntegrityError("published profile process is outside the passport account")

    product_ids = _reference_ids(references, "cbam_product")
    product_table = Base.metadata.tables["cbam_products"]
    _assert_owned_references(
        connection,
        table_name="cbam_products",
        record_ids=product_ids,
        tenant_id=target.tenant_id,
        label="product",
        conditions=(product_table.c.process_id.in_(process_ids),),
    )

    output_table = Base.metadata.tables["cbam_production_outputs"]
    _assert_owned_references(
        connection,
        table_name="cbam_production_outputs",
        record_ids=_reference_ids(references, "production_output"),
        tenant_id=target.tenant_id,
        label="production output",
        conditions=(
            output_table.c.process_id.in_(process_ids),
            output_table.c.product_id.in_(product_ids),
            output_table.c.period_start == target.period_start,
            output_table.c.period_end == target.period_end,
        ),
    )
    attribution_table = Base.metadata.tables["cbam_source_stream_attributions"]
    _assert_owned_references(
        connection,
        table_name="cbam_source_stream_attributions",
        record_ids=_reference_ids(references, "attribution"),
        tenant_id=target.tenant_id,
        label="attribution",
        conditions=(
            attribution_table.c.process_id.in_(process_ids),
            attribution_table.c.period_start == target.period_start,
            attribution_table.c.period_end == target.period_end,
        ),
    )
    _assert_owned_references(
        connection,
        table_name="emission_results",
        record_ids=_reference_ids(references, "emission_result"),
        tenant_id=target.tenant_id,
        label="emission result",
    )
    _assert_owned_references(
        connection,
        table_name="documents",
        record_ids=_reference_ids(references, "document"),
        tenant_id=target.tenant_id,
        label="document",
    )
    see_table = Base.metadata.tables["cbam_see_results"]
    _assert_owned_references(
        connection,
        table_name="cbam_see_results",
        record_ids=_reference_ids(references, "see_result"),
        tenant_id=target.tenant_id,
        label="SEE result",
        conditions=(
            see_table.c.process_id.in_(process_ids),
            see_table.c.product_id.in_(product_ids),
            see_table.c.period_start == target.period_start,
            see_table.c.period_end == target.period_end,
        ),
    )
    rule_table = Base.metadata.tables["rule_records"]
    _assert_owned_references(
        connection,
        table_name="rule_records",
        record_ids=_reference_ids(references, "rule_record"),
        tenant_id=target.tenant_id,
        label="approved rule",
        conditions=(rule_table.c.status == "approved",),
    )


@event.listens_for(InstallationAccount, "before_insert")
def _validate_account(_mapper, connection, target: InstallationAccount) -> None:
    if _tenant_owner(connection, "enterprises", target.enterprise_id) != target.tenant_id:
        raise LedgerIntegrityError("installation account enterprise is missing or foreign")
    if len(target.content_hash) != 64:
        raise LedgerIntegrityError("installation account content hash must be SHA-256")


@event.listens_for(InstallationAccountMember, "before_insert")
def _validate_member(_mapper, connection, target: InstallationAccountMember) -> None:
    if _tenant_owner(connection, "installation_accounts", target.account_id) != target.tenant_id:
        raise LedgerIntegrityError("installation account member account is missing or foreign")
    if _tenant_owner(connection, "cbam_installations", target.installation_id) != target.tenant_id:
        raise LedgerIntegrityError("installation account member installation is missing or foreign")
    if len(target.content_hash) != 64:
        raise LedgerIntegrityError("installation account member content hash must be SHA-256")


@event.listens_for(InstallationProfileVersion, "before_insert")
def _validate_profile_version(_mapper, connection, target: InstallationProfileVersion) -> None:
    if _tenant_owner(connection, "installation_accounts", target.account_id) != target.tenant_id:
        raise LedgerIntegrityError("profile account is missing or foreign")
    if _tenant_owner(connection, "cbam_installations", target.installation_id) != target.tenant_id:
        raise LedgerIntegrityError("profile installation is missing or foreign")
    member_table = Base.metadata.tables["installation_account_members"]
    member = connection.execute(
        select(member_table.c.id).where(
            member_table.c.tenant_id == target.tenant_id,
            member_table.c.account_id == target.account_id,
            member_table.c.installation_id == target.installation_id,
        )
    ).scalar_one_or_none()
    if member is None:
        raise LedgerIntegrityError("profile installation is not a member of its passport account")
    if target.period_start >= target.period_end:
        raise LedgerIntegrityError("profile period_start must precede period_end")
    if target.status not in {"draft", "published"}:
        raise LedgerIntegrityError("profile status is not allowed")
    if not 0 <= target.completeness_score <= 100:
        raise LedgerIntegrityError("profile completeness must be between 0 and 100")
    if target.status == "published" and target.completeness_score != 100:
        raise LedgerIntegrityError("published profile must be 100% complete")
    if target.status == "published":
        _validate_published_references(connection, target)


@event.listens_for(MethodologyReview, "before_insert")
def _validate_methodology_review(_mapper, connection, target: MethodologyReview) -> None:
    if _tenant_owner(connection, "installation_accounts", target.account_id) != target.tenant_id:
        raise LedgerIntegrityError("methodology review account is missing or foreign")
    profile_table = Base.metadata.tables["installation_profile_versions"]
    profile = connection.execute(
        select(profile_table.c.id).where(
            profile_table.c.id == target.profile_version_id,
            profile_table.c.tenant_id == target.tenant_id,
            profile_table.c.account_id == target.account_id,
            profile_table.c.status == "draft",
            profile_table.c.completeness_score >= 88,
        )
    ).scalar_one_or_none()
    if profile is None:
        raise LedgerIntegrityError("methodology review profile is missing, foreign, or not ready")
    if target.verdict not in {"pass", "pass_with_actions", "fail"}:
        raise LedgerIntegrityError("methodology review verdict is not allowed")
    if len(target.content_hash) != 64:
        raise LedgerIntegrityError("methodology review content hash must be SHA-256")


@event.listens_for(DataSharingGrant, "before_insert")
def _validate_sharing_grant(_mapper, connection, target: DataSharingGrant) -> None:
    if _tenant_owner(connection, "installation_accounts", target.account_id) != target.tenant_id:
        raise LedgerIntegrityError("sharing grant account is missing or foreign")
    profile_table = Base.metadata.tables["installation_profile_versions"]
    profile = connection.execute(
        select(profile_table.c.id).where(
            profile_table.c.id == target.profile_version_id,
            profile_table.c.tenant_id == target.tenant_id,
            profile_table.c.account_id == target.account_id,
            profile_table.c.status == "published",
            profile_table.c.completeness_score == 100,
        )
    ).scalar_one_or_none()
    if profile is None:
        raise LedgerIntegrityError("sharing grant requires a published tenant-local profile")
    expires_at = target.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise LedgerIntegrityError("sharing grant expiration must be in the future")
    if len(target.content_hash) != 64:
        raise LedgerIntegrityError("sharing grant content hash must be SHA-256")


@event.listens_for(DataSharingRevocation, "before_insert")
def _validate_sharing_revocation(_mapper, connection, target: DataSharingRevocation) -> None:
    if _tenant_owner(connection, "data_sharing_grants", target.grant_id) != target.tenant_id:
        raise LedgerIntegrityError("sharing revocation grant is missing or foreign")
    if len(target.content_hash) != 64:
        raise LedgerIntegrityError("sharing revocation content hash must be SHA-256")


@event.listens_for(ProfileDistributionEvent, "before_insert")
def _validate_distribution_event(_mapper, connection, target: ProfileDistributionEvent) -> None:
    if _tenant_owner(connection, "installation_accounts", target.account_id) != target.tenant_id:
        raise LedgerIntegrityError("distribution account is missing or foreign")
    if _tenant_owner(connection, "installation_profile_versions", target.profile_version_id) != target.tenant_id:
        raise LedgerIntegrityError("distribution profile is missing or foreign")
    grant_table = Base.metadata.tables["data_sharing_grants"]
    grant = connection.execute(
        select(grant_table.c.id).where(
            grant_table.c.id == target.grant_id,
            grant_table.c.tenant_id == target.tenant_id,
            grant_table.c.account_id == target.account_id,
            grant_table.c.profile_version_id == target.profile_version_id,
            grant_table.c.expires_at > datetime.now(timezone.utc),
        )
    ).scalar_one_or_none()
    revocation_table = Base.metadata.tables["data_sharing_revocations"]
    revoked = connection.execute(
        select(revocation_table.c.id).where(
            revocation_table.c.tenant_id == target.tenant_id,
            revocation_table.c.grant_id == target.grant_id,
        )
    ).scalar_one_or_none()
    if grant is None or revoked is not None:
        raise LedgerIntegrityError("distribution grant is missing, expired, or revoked")
    if len(target.package_hash) != 64 or len(target.content_hash) != 64:
        raise LedgerIntegrityError("distribution hashes must be SHA-256")


@event.listens_for(InstallationAccount, "before_update")
@event.listens_for(InstallationAccount, "before_delete")
@event.listens_for(InstallationAccountMember, "before_update")
@event.listens_for(InstallationAccountMember, "before_delete")
@event.listens_for(MethodologyReview, "before_update")
@event.listens_for(MethodologyReview, "before_delete")
@event.listens_for(DataSharingGrant, "before_update")
@event.listens_for(DataSharingGrant, "before_delete")
@event.listens_for(DataSharingRevocation, "before_update")
@event.listens_for(DataSharingRevocation, "before_delete")
@event.listens_for(ProfileDistributionEvent, "before_update")
@event.listens_for(ProfileDistributionEvent, "before_delete")
def _guard_passport_anchor_immutability(_mapper, _connection, _target) -> None:
    raise LedgerImmutableError(
        "installation passport anchors are immutable; append a new formal fact version"
    )
