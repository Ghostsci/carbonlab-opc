"""Add the factory carbon-data passport account, version, review, and sharing layer.

Revision ID: 029
Revises: 028
Create Date: 2026-07-10
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


IMMUTABLE_TABLES = {
    "installation_accounts": "passport_account",
    "installation_account_members": "passport_member",
    "methodology_reviews": "passport_review",
    "data_sharing_grants": "passport_grant",
    "data_sharing_revocations": "passport_revoke",
    "profile_distribution_events": "passport_delivery",
}


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    ]


def _create_tables() -> None:
    op.create_table(
        "installation_accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "enterprise_id",
            sa.Uuid(),
            sa.ForeignKey("enterprises.id"),
            nullable=False,
        ),
        sa.Column("account_code", sa.String(40), nullable=False),
        sa.Column("request_key", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            name="uq_installation_accounts_id_tenant",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "account_code",
            name="uq_installation_accounts_tenant_code",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "request_key",
            name="uq_installation_accounts_tenant_request",
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_installation_accounts_content_hash",
        ),
    )
    op.create_index("ix_installation_accounts_tenant", "installation_accounts", ["tenant_id"])
    op.create_index(
        "ix_installation_accounts_enterprise",
        "installation_accounts",
        ["enterprise_id"],
    )

    op.create_table(
        "installation_account_members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("added_by", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["account_id", "tenant_id"],
            ["installation_accounts.id", "installation_accounts.tenant_id"],
            name="fk_installation_account_member_account_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id", "tenant_id"],
            ["cbam_installations.id", "cbam_installations.tenant_id"],
            name="fk_installation_account_member_installation_tenant",
        ),
        sa.UniqueConstraint(
            "account_id",
            "installation_id",
            name="uq_installation_account_member_pair",
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_installation_account_members_content_hash",
        ),
    )
    op.create_index(
        "ix_installation_account_members_tenant",
        "installation_account_members",
        ["tenant_id"],
    )
    op.create_index(
        "ix_installation_account_members_account",
        "installation_account_members",
        ["account_id"],
    )

    op.create_table(
        "installation_profile_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("installation_accounts.id"),
            nullable=False,
        ),
        sa.Column(
            "installation_id",
            sa.Uuid(),
            sa.ForeignKey("cbam_installations.id"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("completeness_score", sa.Integer(), nullable=False),
        sa.Column("data_quality_grade", sa.String(2), nullable=False),
        sa.Column("assessment_json", sa.JSON(), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("derived_from", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("confirmed_by", sa.String(64), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supersedes_id", sa.Uuid(), nullable=True),
        sa.Column("superseded_by_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            name="uq_installation_profile_versions_id_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id", "tenant_id"],
            ["installation_profile_versions.id", "installation_profile_versions.tenant_id"],
            name="fk_installation_profile_versions_supersedes_tenant",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_id", "tenant_id"],
            ["installation_profile_versions.id", "installation_profile_versions.tenant_id"],
            name="fk_installation_profile_versions_superseded_by_tenant",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            "version",
            name="uq_installation_profile_versions_tenant_idempotency_version",
        ),
        sa.UniqueConstraint("supersedes_id", name="uq_installation_profile_versions_supersedes"),
        sa.UniqueConstraint(
            "superseded_by_id",
            name="uq_installation_profile_versions_superseded_by",
        ),
        sa.CheckConstraint("period_start < period_end", name="ck_passport_profile_period"),
        sa.CheckConstraint("status IN ('draft', 'published')", name="ck_passport_profile_status"),
        sa.CheckConstraint(
            "completeness_score BETWEEN 0 AND 100",
            name="ck_passport_profile_completeness",
        ),
        sa.CheckConstraint(
            "status <> 'published' OR completeness_score = 100",
            name="ck_passport_profile_published_complete",
        ),
        sa.CheckConstraint("version >= 1", name="ck_passport_profile_version"),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_passport_profile_hash"),
        sa.CheckConstraint(
            "supersedes_id IS NULL OR supersedes_id <> id",
            name="ck_passport_profile_not_self_supersedes",
        ),
        sa.CheckConstraint(
            "superseded_by_id IS NULL OR superseded_by_id <> id",
            name="ck_passport_profile_not_self_superseded",
        ),
    )
    for name, columns in (
        ("ix_passport_profile_tenant", ["tenant_id"]),
        ("ix_passport_profile_account", ["account_id"]),
        ("ix_passport_profile_installation", ["installation_id"]),
        ("ix_passport_profile_hash", ["content_hash"]),
    ):
        op.create_index(name, "installation_profile_versions", columns)

    op.create_table(
        "methodology_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("installation_accounts.id"), nullable=False),
        sa.Column(
            "profile_version_id",
            sa.Uuid(),
            sa.ForeignKey("installation_profile_versions.id"),
            nullable=False,
        ),
        sa.Column("reviewer_id", sa.String(64), nullable=False),
        sa.Column("reviewer_role", sa.String(32), nullable=False),
        sa.Column("verdict", sa.String(24), nullable=False),
        sa.Column("summary", sa.String(1000), nullable=False),
        sa.Column("findings_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("disclaimer", sa.String(255), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("id", "tenant_id", name="uq_methodology_reviews_id_tenant"),
        sa.CheckConstraint(
            "verdict IN ('pass', 'pass_with_actions', 'fail')",
            name="ck_methodology_reviews_verdict",
        ),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_methodology_reviews_hash"),
    )
    op.create_index("ix_methodology_reviews_tenant", "methodology_reviews", ["tenant_id"])
    op.create_index("ix_methodology_reviews_account", "methodology_reviews", ["account_id"])
    op.create_index(
        "ix_methodology_reviews_profile",
        "methodology_reviews",
        ["profile_version_id"],
    )

    op.create_table(
        "data_sharing_grants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("installation_accounts.id"), nullable=False),
        sa.Column(
            "profile_version_id",
            sa.Uuid(),
            sa.ForeignKey("installation_profile_versions.id"),
            nullable=False,
        ),
        sa.Column("recipient_tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("recipient_name", sa.String(255), nullable=False),
        sa.Column("recipient_type", sa.String(32), nullable=False),
        sa.Column("purpose", sa.String(500), nullable=False),
        sa.Column("scopes_json", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("id", "tenant_id", name="uq_data_sharing_grants_id_tenant"),
        sa.CheckConstraint(
            "recipient_type IN ('importer', 'trader', 'verifier', 'software_partner', 'customer', 'other')",
            name="ck_data_sharing_grants_recipient_type",
        ),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_data_sharing_grants_hash"),
    )
    for name, columns in (
        ("ix_data_sharing_grants_tenant", ["tenant_id"]),
        ("ix_data_sharing_grants_account", ["account_id"]),
        ("ix_data_sharing_grants_profile", ["profile_version_id"]),
        ("ix_data_sharing_grants_recipient", ["recipient_tenant_id"]),
    ):
        op.create_index(name, "data_sharing_grants", columns)

    op.create_table(
        "data_sharing_revocations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("grant_id", sa.Uuid(), sa.ForeignKey("data_sharing_grants.id"), nullable=False),
        sa.Column("revoked_by", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("grant_id", name="uq_data_sharing_revocations_grant"),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_data_sharing_revocations_hash"),
    )
    op.create_index("ix_data_sharing_revocations_tenant", "data_sharing_revocations", ["tenant_id"])
    op.create_index("ix_data_sharing_revocations_grant", "data_sharing_revocations", ["grant_id"])

    op.create_table(
        "profile_distribution_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("installation_accounts.id"), nullable=False),
        sa.Column(
            "profile_version_id",
            sa.Uuid(),
            sa.ForeignKey("installation_profile_versions.id"),
            nullable=False,
        ),
        sa.Column("grant_id", sa.Uuid(), sa.ForeignKey("data_sharing_grants.id"), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("delivered_to", sa.String(255), nullable=False),
        sa.Column("package_hash", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "channel IN ('api_view', 'json_export')",
            name="ck_profile_distribution_events_channel",
        ),
        sa.CheckConstraint(
            "length(package_hash) = 64 AND length(content_hash) = 64",
            name="ck_profile_distribution_events_hashes",
        ),
    )
    for name, columns in (
        ("ix_profile_distribution_events_tenant", ["tenant_id"]),
        ("ix_profile_distribution_events_account", ["account_id"]),
        ("ix_profile_distribution_events_profile", ["profile_version_id"]),
        ("ix_profile_distribution_events_grant", ["grant_id"]),
    ):
        op.create_index(name, "profile_distribution_events", columns)


def _create_immutable_guards() -> None:
    dialect = op.get_bind().dialect.name
    for table_name, prefix in IMMUTABLE_TABLES.items():
        if dialect == "postgresql":
            op.execute(
                sa.text(
                    f"""
                    CREATE FUNCTION zcy_{prefix}_immutable() RETURNS trigger AS $$
                    BEGIN
                        RAISE EXCEPTION 'passport audit records are immutable';
                    END;
                    $$ LANGUAGE plpgsql;
                    CREATE TRIGGER trg_{prefix}_guard_update
                    BEFORE UPDATE ON {table_name}
                    FOR EACH ROW EXECUTE FUNCTION zcy_{prefix}_immutable();
                    CREATE TRIGGER trg_{prefix}_guard_delete
                    BEFORE DELETE ON {table_name}
                    FOR EACH ROW EXECUTE FUNCTION zcy_{prefix}_immutable();
                    """
                )
            )
        elif dialect == "sqlite":
            for operation in ("UPDATE", "DELETE"):
                op.execute(
                    sa.text(
                        f"""
                        CREATE TRIGGER trg_{prefix}_guard_{operation.lower()}
                        BEFORE {operation} ON {table_name}
                        FOR EACH ROW BEGIN
                            SELECT RAISE(ABORT, 'passport audit records are immutable');
                        END;
                        """
                    )
                )


def _create_lineage_guards() -> None:
    dialect = op.get_bind().dialect.name
    postgres_checks = {
        "installation_accounts": """
            IF NOT EXISTS (SELECT 1 FROM enterprises e WHERE e.id = NEW.enterprise_id AND e.tenant_id = NEW.tenant_id)
            THEN RAISE EXCEPTION 'passport enterprise is missing or foreign'; END IF;
        """,
        "installation_account_members": """
            IF NOT EXISTS (SELECT 1 FROM installation_accounts a WHERE a.id = NEW.account_id AND a.tenant_id = NEW.tenant_id)
               OR NOT EXISTS (SELECT 1 FROM cbam_installations i WHERE i.id = NEW.installation_id AND i.tenant_id = NEW.tenant_id)
            THEN RAISE EXCEPTION 'passport member lineage violation'; END IF;
        """,
        "methodology_reviews": """
            IF NOT EXISTS (SELECT 1 FROM installation_accounts a WHERE a.id = NEW.account_id AND a.tenant_id = NEW.tenant_id)
               OR NOT EXISTS (
                   SELECT 1 FROM installation_profile_versions p
                   WHERE p.id = NEW.profile_version_id AND p.tenant_id = NEW.tenant_id
                     AND p.account_id = NEW.account_id AND p.status = 'draft'
                     AND p.completeness_score >= 88
               )
            THEN RAISE EXCEPTION 'methodology review lineage or readiness violation'; END IF;
        """,
        "data_sharing_grants": """
            IF NOT EXISTS (SELECT 1 FROM installation_accounts a WHERE a.id = NEW.account_id AND a.tenant_id = NEW.tenant_id)
               OR NOT EXISTS (
                   SELECT 1 FROM installation_profile_versions p
                   WHERE p.id = NEW.profile_version_id AND p.tenant_id = NEW.tenant_id
                     AND p.account_id = NEW.account_id AND p.status = 'published'
                     AND p.completeness_score = 100
               )
            THEN RAISE EXCEPTION 'sharing grant requires a published tenant-local profile'; END IF;
        """,
        "data_sharing_revocations": """
            IF NOT EXISTS (SELECT 1 FROM data_sharing_grants g WHERE g.id = NEW.grant_id AND g.tenant_id = NEW.tenant_id)
            THEN RAISE EXCEPTION 'sharing revocation grant is missing or foreign'; END IF;
        """,
    }
    sqlite_checks = {
        "installation_accounts": """
            WHEN NOT EXISTS (SELECT 1 FROM enterprises e WHERE e.id = NEW.enterprise_id AND e.tenant_id = NEW.tenant_id)
            THEN RAISE(ABORT, 'passport enterprise is missing or foreign')
        """,
        "installation_account_members": """
            WHEN NOT EXISTS (SELECT 1 FROM installation_accounts a WHERE a.id = NEW.account_id AND a.tenant_id = NEW.tenant_id)
              OR NOT EXISTS (SELECT 1 FROM cbam_installations i WHERE i.id = NEW.installation_id AND i.tenant_id = NEW.tenant_id)
            THEN RAISE(ABORT, 'passport member lineage violation')
        """,
        "methodology_reviews": """
            WHEN NOT EXISTS (SELECT 1 FROM installation_accounts a WHERE a.id = NEW.account_id AND a.tenant_id = NEW.tenant_id)
              OR NOT EXISTS (
                  SELECT 1 FROM installation_profile_versions p
                  WHERE p.id = NEW.profile_version_id AND p.tenant_id = NEW.tenant_id
                    AND p.account_id = NEW.account_id AND p.status = 'draft'
                    AND p.completeness_score >= 88
              )
            THEN RAISE(ABORT, 'methodology review lineage or readiness violation')
        """,
        "data_sharing_grants": """
            WHEN NOT EXISTS (SELECT 1 FROM installation_accounts a WHERE a.id = NEW.account_id AND a.tenant_id = NEW.tenant_id)
              OR NOT EXISTS (
                  SELECT 1 FROM installation_profile_versions p
                  WHERE p.id = NEW.profile_version_id AND p.tenant_id = NEW.tenant_id
                    AND p.account_id = NEW.account_id AND p.status = 'published'
                    AND p.completeness_score = 100
              )
            THEN RAISE(ABORT, 'sharing grant requires a published tenant-local profile')
        """,
        "data_sharing_revocations": """
            WHEN NOT EXISTS (SELECT 1 FROM data_sharing_grants g WHERE g.id = NEW.grant_id AND g.tenant_id = NEW.tenant_id)
            THEN RAISE(ABORT, 'sharing revocation grant is missing or foreign')
        """,
    }
    for table_name, check in (postgres_checks if dialect == "postgresql" else sqlite_checks).items():
        prefix = IMMUTABLE_TABLES[table_name]
        if dialect == "postgresql":
            op.execute(
                sa.text(
                    f"""
                    CREATE FUNCTION zcy_{prefix}_guard_insert() RETURNS trigger AS $$
                    BEGIN {check} RETURN NEW; END;
                    $$ LANGUAGE plpgsql;
                    CREATE TRIGGER trg_{prefix}_guard_insert
                    BEFORE INSERT ON {table_name}
                    FOR EACH ROW EXECUTE FUNCTION zcy_{prefix}_guard_insert();
                    """
                )
            )
        elif dialect == "sqlite":
            op.execute(
                sa.text(
                    f"""
                    CREATE TRIGGER trg_{prefix}_guard_insert
                    BEFORE INSERT ON {table_name}
                    FOR EACH ROW BEGIN SELECT CASE {check} END; END;
                    """
                )
            )


def _create_profile_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            sa.text(
                """
                CREATE FUNCTION zcy_passport_profile_guard_insert() RETURNS trigger AS $$
                DECLARE parent RECORD;
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM installation_accounts a
                        WHERE a.id = NEW.account_id AND a.tenant_id = NEW.tenant_id
                    ) OR NOT EXISTS (
                        SELECT 1 FROM installation_account_members m
                        WHERE m.account_id = NEW.account_id
                          AND m.installation_id = NEW.installation_id
                          AND m.tenant_id = NEW.tenant_id
                    ) THEN RAISE EXCEPTION 'passport tenant lineage violation'; END IF;
                    IF NEW.superseded_by_id IS NOT NULL THEN
                        RAISE EXCEPTION 'new profile versions cannot declare superseded_by_id';
                    END IF;
                    IF NEW.supersedes_id IS NULL THEN
                        IF NEW.version <> 1 THEN RAISE EXCEPTION 'root profile version must be 1'; END IF;
                    ELSE
                        SELECT tenant_id, account_id, version, superseded_by_id INTO parent
                        FROM installation_profile_versions WHERE id = NEW.supersedes_id;
                        IF NOT FOUND OR parent.tenant_id <> NEW.tenant_id
                           OR parent.account_id <> NEW.account_id
                           OR parent.superseded_by_id IS NOT NULL
                           OR NEW.version <> parent.version + 1 THEN
                            RAISE EXCEPTION 'invalid profile supersession';
                        END IF;
                    END IF;
                    IF NEW.status = 'published' THEN
                        IF NEW.supersedes_id IS NULL OR NOT EXISTS (
                            SELECT 1
                            FROM jsonb_array_elements_text(NEW.derived_from::jsonb) ref(value)
                            JOIN methodology_reviews review
                              ON review.id = split_part(ref.value, ':', 2)::uuid
                             AND review.tenant_id = NEW.tenant_id
                             AND review.account_id = NEW.account_id
                             AND review.profile_version_id = NEW.supersedes_id
                             AND review.verdict IN ('pass', 'pass_with_actions')
                            WHERE ref.value LIKE 'methodology_review:%'
                        ) THEN RAISE EXCEPTION 'published profile requires passing review'; END IF;
                        IF NOT EXISTS (
                            SELECT 1 FROM jsonb_array_elements_text(NEW.derived_from::jsonb) r
                            JOIN cbam_production_processes p
                              ON p.id = split_part(r.value, ':', 2)::uuid
                             AND p.tenant_id = NEW.tenant_id
                            JOIN installation_account_members m
                              ON m.installation_id = p.installation_id
                             AND m.account_id = NEW.account_id
                             AND m.tenant_id = NEW.tenant_id
                            WHERE r.value LIKE 'production_process:%'
                        ) OR NOT EXISTS (
                            SELECT 1 FROM jsonb_array_elements_text(NEW.derived_from::jsonb) r
                            JOIN cbam_products p ON p.id = split_part(r.value, ':', 2)::uuid
                              AND p.tenant_id = NEW.tenant_id
                            WHERE r.value LIKE 'cbam_product:%'
                        ) OR NOT EXISTS (
                            SELECT 1 FROM jsonb_array_elements_text(NEW.derived_from::jsonb) r
                            JOIN cbam_production_outputs o ON o.id = split_part(r.value, ':', 2)::uuid
                              AND o.tenant_id = NEW.tenant_id
                              AND o.period_start = NEW.period_start AND o.period_end = NEW.period_end
                            WHERE r.value LIKE 'production_output:%'
                        ) OR NOT EXISTS (
                            SELECT 1 FROM jsonb_array_elements_text(NEW.derived_from::jsonb) r
                            JOIN cbam_source_stream_attributions a ON a.id = split_part(r.value, ':', 2)::uuid
                              AND a.tenant_id = NEW.tenant_id
                              AND a.period_start = NEW.period_start AND a.period_end = NEW.period_end
                            WHERE r.value LIKE 'attribution:%'
                        ) OR NOT EXISTS (
                            SELECT 1 FROM jsonb_array_elements_text(NEW.derived_from::jsonb) r
                            JOIN emission_results e ON e.id = split_part(r.value, ':', 2)::uuid
                              AND e.tenant_id = NEW.tenant_id
                            WHERE r.value LIKE 'emission_result:%'
                        ) OR NOT EXISTS (
                            SELECT 1 FROM jsonb_array_elements_text(NEW.derived_from::jsonb) r
                            JOIN documents d ON d.id = split_part(r.value, ':', 2)::uuid
                              AND d.tenant_id = NEW.tenant_id
                            WHERE r.value LIKE 'document:%'
                        ) OR NOT EXISTS (
                            SELECT 1 FROM jsonb_array_elements_text(NEW.derived_from::jsonb) r
                            JOIN cbam_see_results s ON s.id = split_part(r.value, ':', 2)::uuid
                              AND s.tenant_id = NEW.tenant_id
                              AND s.period_start = NEW.period_start AND s.period_end = NEW.period_end
                            WHERE r.value LIKE 'see_result:%'
                        ) OR NOT EXISTS (
                            SELECT 1 FROM jsonb_array_elements_text(NEW.derived_from::jsonb) r
                            JOIN rule_records rr ON rr.id = split_part(r.value, ':', 2)::uuid
                              AND rr.tenant_id = NEW.tenant_id AND rr.status = 'approved'
                            WHERE r.value LIKE 'rule_record:%'
                        ) THEN RAISE EXCEPTION 'published profile lacks formal fact references'; END IF;
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER trg_passport_profile_guard_insert
                BEFORE INSERT ON installation_profile_versions
                FOR EACH ROW EXECUTE FUNCTION zcy_passport_profile_guard_insert();

                CREATE FUNCTION zcy_passport_profile_guard_update() RETURNS trigger AS $$
                BEGIN
                    IF (to_jsonb(NEW) - 'superseded_by_id' - 'updated_at') IS DISTINCT FROM
                       (to_jsonb(OLD) - 'superseded_by_id' - 'updated_at')
                       OR OLD.superseded_by_id IS NOT NULL OR NEW.superseded_by_id IS NULL
                       OR NOT EXISTS (
                           SELECT 1 FROM installation_profile_versions successor
                           WHERE successor.id = NEW.superseded_by_id
                             AND successor.tenant_id = OLD.tenant_id
                             AND successor.account_id = OLD.account_id
                             AND successor.supersedes_id = OLD.id
                             AND successor.version = OLD.version + 1
                       ) THEN RAISE EXCEPTION 'profile versions are append-only'; END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER trg_passport_profile_guard_update
                BEFORE UPDATE ON installation_profile_versions
                FOR EACH ROW EXECUTE FUNCTION zcy_passport_profile_guard_update();

                CREATE FUNCTION zcy_passport_profile_guard_delete() RETURNS trigger AS $$
                BEGIN RAISE EXCEPTION 'profile versions cannot be deleted'; END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER trg_passport_profile_guard_delete
                BEFORE DELETE ON installation_profile_versions
                FOR EACH ROW EXECUTE FUNCTION zcy_passport_profile_guard_delete();

                CREATE FUNCTION zcy_passport_profile_link_insert() RETURNS trigger AS $$
                BEGIN
                    IF NEW.supersedes_id IS NOT NULL THEN
                        UPDATE installation_profile_versions SET superseded_by_id = NEW.id
                        WHERE id = NEW.supersedes_id AND tenant_id = NEW.tenant_id
                          AND superseded_by_id IS NULL;
                        IF NOT FOUND THEN RAISE EXCEPTION 'failed to link profile supersession'; END IF;
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER trg_passport_profile_link_insert
                AFTER INSERT ON installation_profile_versions
                FOR EACH ROW EXECUTE FUNCTION zcy_passport_profile_link_insert();
                """
            )
        )
    elif dialect == "sqlite":
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_passport_profile_guard_insert
                BEFORE INSERT ON installation_profile_versions
                FOR EACH ROW BEGIN
                    SELECT CASE
                        WHEN NOT EXISTS (
                            SELECT 1 FROM installation_accounts a
                            WHERE a.id = NEW.account_id AND a.tenant_id = NEW.tenant_id
                        ) OR NOT EXISTS (
                            SELECT 1 FROM installation_account_members m
                            WHERE m.account_id = NEW.account_id
                              AND m.installation_id = NEW.installation_id
                              AND m.tenant_id = NEW.tenant_id
                        ) THEN RAISE(ABORT, 'passport tenant lineage violation')
                        WHEN NEW.superseded_by_id IS NOT NULL
                        THEN RAISE(ABORT, 'new profile versions cannot declare superseded_by_id')
                        WHEN NEW.supersedes_id IS NULL AND NEW.version <> 1
                        THEN RAISE(ABORT, 'root profile version must be 1')
                        WHEN NEW.supersedes_id IS NOT NULL AND NOT EXISTS (
                            SELECT 1 FROM installation_profile_versions parent
                            WHERE parent.id = NEW.supersedes_id
                              AND parent.tenant_id = NEW.tenant_id
                              AND parent.account_id = NEW.account_id
                              AND parent.superseded_by_id IS NULL
                              AND NEW.version = parent.version + 1
                        ) THEN RAISE(ABORT, 'invalid profile supersession')
                        WHEN NEW.status = 'published' AND (
                            NEW.supersedes_id IS NULL OR NOT EXISTS (
                                SELECT 1 FROM json_each(NEW.derived_from) ref
                                JOIN methodology_reviews review
                                  ON review.id = replace(substr(ref.value, 20), '-', '')
                                 AND review.tenant_id = NEW.tenant_id
                                 AND review.account_id = NEW.account_id
                                 AND review.profile_version_id = NEW.supersedes_id
                                 AND review.verdict IN ('pass', 'pass_with_actions')
                                WHERE ref.value LIKE 'methodology_review:%'
                            )
                        ) THEN RAISE(ABORT, 'published profile requires passing review')
                        WHEN NEW.status = 'published' AND (
                            NOT EXISTS (SELECT 1 FROM json_each(NEW.derived_from) WHERE value LIKE 'production_process:%')
                            OR NOT EXISTS (SELECT 1 FROM json_each(NEW.derived_from) WHERE value LIKE 'cbam_product:%')
                            OR NOT EXISTS (SELECT 1 FROM json_each(NEW.derived_from) WHERE value LIKE 'production_output:%')
                            OR NOT EXISTS (SELECT 1 FROM json_each(NEW.derived_from) WHERE value LIKE 'attribution:%')
                            OR NOT EXISTS (SELECT 1 FROM json_each(NEW.derived_from) WHERE value LIKE 'emission_result:%')
                            OR NOT EXISTS (SELECT 1 FROM json_each(NEW.derived_from) WHERE value LIKE 'document:%')
                            OR NOT EXISTS (SELECT 1 FROM json_each(NEW.derived_from) WHERE value LIKE 'see_result:%')
                            OR NOT EXISTS (SELECT 1 FROM json_each(NEW.derived_from) WHERE value LIKE 'rule_record:%')
                        ) THEN RAISE(ABORT, 'published profile lacks formal fact references')
                    END;
                END;
                """
            )
        )
        immutable_columns = [
            column["name"]
            for column in sa.inspect(op.get_bind()).get_columns("installation_profile_versions")
            if column["name"] not in {"superseded_by_id", "updated_at"}
        ]
        change = " OR ".join(f"NEW.{name} IS NOT OLD.{name}" for name in immutable_columns)
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_passport_profile_guard_update
                BEFORE UPDATE ON installation_profile_versions
                FOR EACH ROW WHEN {change}
                  OR OLD.superseded_by_id IS NOT NULL OR NEW.superseded_by_id IS NULL
                  OR NOT EXISTS (
                      SELECT 1 FROM installation_profile_versions successor
                      WHERE successor.id = NEW.superseded_by_id
                        AND successor.tenant_id = OLD.tenant_id
                        AND successor.account_id = OLD.account_id
                        AND successor.supersedes_id = OLD.id
                        AND successor.version = OLD.version + 1
                  )
                BEGIN SELECT RAISE(ABORT, 'profile versions are append-only'); END;
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_passport_profile_link_insert
                AFTER INSERT ON installation_profile_versions
                FOR EACH ROW WHEN NEW.supersedes_id IS NOT NULL
                BEGIN
                    UPDATE installation_profile_versions SET superseded_by_id = NEW.id
                    WHERE id = NEW.supersedes_id AND tenant_id = NEW.tenant_id
                      AND superseded_by_id IS NULL;
                END;
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_passport_profile_guard_delete
                BEFORE DELETE ON installation_profile_versions
                FOR EACH ROW BEGIN SELECT RAISE(ABORT, 'profile versions cannot be deleted'); END;
                """
            )
        )


def _create_distribution_guard() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            sa.text(
                """
                CREATE FUNCTION zcy_passport_delivery_guard_insert() RETURNS trigger AS $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM data_sharing_grants g
                        WHERE g.id = NEW.grant_id AND g.tenant_id = NEW.tenant_id
                          AND g.account_id = NEW.account_id
                          AND g.profile_version_id = NEW.profile_version_id
                          AND g.expires_at > CURRENT_TIMESTAMP
                    ) OR EXISTS (
                        SELECT 1 FROM data_sharing_revocations r
                        WHERE r.grant_id = NEW.grant_id AND r.tenant_id = NEW.tenant_id
                    ) THEN RAISE EXCEPTION 'distribution grant is missing, expired, or revoked'; END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER trg_passport_delivery_guard_insert
                BEFORE INSERT ON profile_distribution_events
                FOR EACH ROW EXECUTE FUNCTION zcy_passport_delivery_guard_insert();
                """
            )
        )
    elif dialect == "sqlite":
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_passport_delivery_guard_insert
                BEFORE INSERT ON profile_distribution_events
                FOR EACH ROW BEGIN
                    SELECT CASE WHEN NOT EXISTS (
                        SELECT 1 FROM data_sharing_grants g
                        WHERE g.id = NEW.grant_id AND g.tenant_id = NEW.tenant_id
                          AND g.account_id = NEW.account_id
                          AND g.profile_version_id = NEW.profile_version_id
                          AND g.expires_at > CURRENT_TIMESTAMP
                    ) OR EXISTS (
                        SELECT 1 FROM data_sharing_revocations r
                        WHERE r.grant_id = NEW.grant_id AND r.tenant_id = NEW.tenant_id
                    ) THEN RAISE(ABORT, 'distribution grant is missing, expired, or revoked') END;
                END;
                """
            )
        )


def upgrade() -> None:
    _create_tables()
    _create_lineage_guards()
    _create_immutable_guards()
    _create_profile_guards()
    _create_distribution_guard()


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(sa.text("DROP FUNCTION IF EXISTS zcy_passport_delivery_guard_insert() CASCADE"))
        for name in (
            "zcy_passport_profile_guard_insert",
            "zcy_passport_profile_guard_update",
            "zcy_passport_profile_guard_delete",
            "zcy_passport_profile_link_insert",
        ):
            op.execute(sa.text(f"DROP FUNCTION IF EXISTS {name}() CASCADE"))
        for prefix in IMMUTABLE_TABLES.values():
            op.execute(sa.text(f"DROP FUNCTION IF EXISTS zcy_{prefix}_immutable() CASCADE"))
            op.execute(sa.text(f"DROP FUNCTION IF EXISTS zcy_{prefix}_guard_insert() CASCADE"))
    for table in (
        "profile_distribution_events",
        "data_sharing_revocations",
        "data_sharing_grants",
        "methodology_reviews",
        "installation_profile_versions",
        "installation_account_members",
        "installation_accounts",
    ):
        op.drop_table(table)
