"""Make the database recompute published passport snapshots and hashes.

Revision ID: 030
Revises: 029
Create Date: 2026-07-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ensure_no_published_profiles() -> None:
    published_count = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM installation_profile_versions "
            "WHERE status = 'published'"
        )
    ).scalar_one()
    if published_count:
        raise RuntimeError(
            "030 requires audit and republication of pre-existing published passports"
        )


def _postgres_upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    op.execute(
        sa.text(
            r"""
            CREATE OR REPLACE FUNCTION zcy_canonical_jsonb(value jsonb) RETURNS text AS $$
                SELECT CASE jsonb_typeof(value)
                    WHEN 'object' THEN COALESCE(
                        (
                            SELECT '{' || string_agg(
                                to_jsonb(key)::text || ':' || zcy_canonical_jsonb(value -> key),
                                ',' ORDER BY key
                            ) || '}'
                            FROM jsonb_object_keys(value) AS keys(key)
                        ),
                        '{}'
                    )
                    WHEN 'array' THEN COALESCE(
                        (
                            SELECT '[' || string_agg(
                                zcy_canonical_jsonb(element), ',' ORDER BY ordinal
                            ) || ']'
                            FROM jsonb_array_elements(value)
                            WITH ORDINALITY AS items(element, ordinal)
                        ),
                        '[]'
                    )
                    ELSE value::text
                END
            $$ LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE;

            CREATE OR REPLACE FUNCTION zcy_iso_utc(value timestamptz) RETURNS text AS $$
                SELECT CASE WHEN value IS NULL THEN NULL ELSE
                    to_char(value AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS') ||
                    CASE
                        WHEN (extract(microseconds FROM value)::bigint % 1000000) = 0 THEN ''
                        ELSE '.' || to_char(value AT TIME ZONE 'UTC', 'US')
                    END || 'Z'
                END
            $$ LANGUAGE sql IMMUTABLE PARALLEL SAFE;

            CREATE OR REPLACE FUNCTION zcy_iso_offset_utc(value timestamptz) RETURNS text AS $$
                SELECT CASE WHEN value IS NULL THEN NULL ELSE
                    to_char(value AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS') ||
                    CASE
                        WHEN (extract(microseconds FROM value)::bigint % 1000000) = 0 THEN ''
                        ELSE '.' || to_char(value AT TIME ZONE 'UTC', 'US')
                    END || '+00:00'
                END
            $$ LANGUAGE sql IMMUTABLE PARALLEL SAFE;

            CREATE OR REPLACE FUNCTION zcy_passport_expected_see_hash(
                row_value cbam_see_results
            ) RETURNS text AS $$
                SELECT encode(
                    digest(
                        convert_to(
                            zcy_canonical_jsonb(
                                jsonb_build_object(
                                    'record_type', 'cbam_see_result',
                                    'tenant_id', row_value.tenant_id::text,
                                    'process_id', row_value.process_id::text,
                                    'product_id', row_value.product_id::text,
                                    'production_output_id', row_value.production_output_id::text,
                                    'period_start', zcy_iso_offset_utc(row_value.period_start),
                                    'period_end', zcy_iso_offset_utc(row_value.period_end),
                                    'direct', row_value.direct_emissions::text,
                                    'indirect', row_value.indirect_emissions::text,
                                    'precursor', row_value.precursor_emissions::text,
                                    'total', row_value.total_emissions::text,
                                    'specific', row_value.specific_emissions::text,
                                    'emissions_unit', row_value.emissions_unit,
                                    'specific_unit', row_value.specific_unit,
                                    'data_quality', row_value.data_quality,
                                    'methodology_ref', row_value.methodology_ref,
                                    'derived_from', row_value.derived_from::jsonb
                                )
                            ),
                            'UTF8'
                        ),
                        'sha256'
                    ),
                    'hex'
                )
            $$ LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE;
            """
        )
    )
    op.execute(
        sa.text(
            r"""
            CREATE OR REPLACE FUNCTION zcy_passport_profile_replay_guard_insert()
            RETURNS trigger AS $$
            DECLARE
                account_json jsonb;
                installation_json jsonb;
                processes_json jsonb;
                products_json jsonb;
                outputs_json jsonb;
                attributions_json jsonb;
                emissions_json jsonb;
                documents_json jsonb;
                see_json jsonb;
                rules_json jsonb;
                review_json jsonb;
                expected_snapshot jsonb;
                expected_assessment jsonb;
                expected_references jsonb;
                expected_hash text;
            BEGIN
                IF NEW.status <> 'published' THEN
                    RETURN NEW;
                END IF;

                SELECT jsonb_build_object(
                    'id', a.id::text,
                    'account_code', a.account_code,
                    'enterprise_id', a.enterprise_id::text
                ) INTO account_json
                FROM installation_accounts a
                WHERE a.id = NEW.account_id AND a.tenant_id = NEW.tenant_id;

                SELECT jsonb_build_object(
                    'id', i.id::text,
                    'name', i.name,
                    'operator_name', i.operator_name,
                    'country_code', i.country_code,
                    'unlocode', i.unlocode,
                    'version', i.version,
                    'content_hash', i.content_hash
                ) INTO installation_json
                FROM cbam_installations i
                JOIN installation_account_members m
                  ON m.installation_id = i.id
                 AND m.tenant_id = i.tenant_id
                 AND m.account_id = NEW.account_id
                WHERE i.id = NEW.installation_id AND i.tenant_id = NEW.tenant_id;

                SELECT COALESCE(jsonb_agg(jsonb_build_object(
                    'id', p.id::text,
                    'name', p.name,
                    'aggregate_goods_category', p.aggregate_goods_category,
                    'production_route', p.production_route,
                    'version', p.version,
                    'content_hash', p.content_hash
                ) ORDER BY p.id::text), '[]'::jsonb)
                INTO processes_json
                FROM jsonb_array_elements_text(NEW.derived_from::jsonb) ref
                JOIN cbam_production_processes p
                  ON ref.value = 'production_process:' || p.id::text
                 AND p.tenant_id = NEW.tenant_id
                 AND p.superseded_by_id IS NULL
                JOIN installation_account_members m
                  ON m.installation_id = p.installation_id
                 AND m.tenant_id = NEW.tenant_id
                 AND m.account_id = NEW.account_id
                WHERE ref.value LIKE 'production_process:%';

                SELECT COALESCE(jsonb_agg(jsonb_build_object(
                    'id', p.id::text,
                    'process_id', p.process_id::text,
                    'name', p.name,
                    'cn_code', p.cn_code,
                    'version', p.version,
                    'content_hash', p.content_hash
                ) ORDER BY p.id::text), '[]'::jsonb)
                INTO products_json
                FROM jsonb_array_elements_text(NEW.derived_from::jsonb) ref
                JOIN cbam_products p
                  ON ref.value = 'cbam_product:' || p.id::text
                 AND p.tenant_id = NEW.tenant_id
                 AND p.superseded_by_id IS NULL
                WHERE ref.value LIKE 'cbam_product:%'
                  AND EXISTS (
                      SELECT 1 FROM jsonb_array_elements(processes_json) process_item
                      WHERE process_item ->> 'id' = p.process_id::text
                  );

                SELECT COALESCE(jsonb_agg(jsonb_build_object(
                    'id', o.id::text,
                    'process_id', o.process_id::text,
                    'product_id', o.product_id::text,
                    'period_start', zcy_iso_utc(o.period_start),
                    'period_end', zcy_iso_utc(o.period_end),
                    'quantity', o.quantity::text,
                    'unit', o.unit,
                    'version', o.version,
                    'content_hash', o.content_hash
                ) ORDER BY o.id::text), '[]'::jsonb)
                INTO outputs_json
                FROM jsonb_array_elements_text(NEW.derived_from::jsonb) ref
                JOIN cbam_production_outputs o
                  ON ref.value = 'production_output:' || o.id::text
                 AND o.tenant_id = NEW.tenant_id
                 AND o.period_start = NEW.period_start
                 AND o.period_end = NEW.period_end
                 AND o.superseded_by_id IS NULL
                WHERE ref.value LIKE 'production_output:%'
                  AND EXISTS (
                      SELECT 1 FROM jsonb_array_elements(processes_json) process_item
                      WHERE process_item ->> 'id' = o.process_id::text
                  )
                  AND EXISTS (
                      SELECT 1 FROM jsonb_array_elements(products_json) product_item
                      WHERE product_item ->> 'id' = o.product_id::text
                        AND product_item ->> 'process_id' = o.process_id::text
                  );

                SELECT COALESCE(jsonb_agg(jsonb_build_object(
                    'id', a.id::text,
                    'process_id', a.process_id::text,
                    'source_ref', a.source_ref,
                    'period_start', zcy_iso_utc(a.period_start),
                    'period_end', zcy_iso_utc(a.period_end),
                    'share', a.share::text,
                    'method', a.method,
                    'version', a.version,
                    'content_hash', a.content_hash
                ) ORDER BY a.id::text), '[]'::jsonb)
                INTO attributions_json
                FROM jsonb_array_elements_text(NEW.derived_from::jsonb) ref
                JOIN cbam_source_stream_attributions a
                  ON ref.value = 'attribution:' || a.id::text
                 AND a.tenant_id = NEW.tenant_id
                 AND a.period_start = NEW.period_start
                 AND a.period_end = NEW.period_end
                 AND a.superseded_by_id IS NULL
                WHERE ref.value LIKE 'attribution:%'
                  AND EXISTS (
                      SELECT 1 FROM jsonb_array_elements(processes_json) process_item
                      WHERE process_item ->> 'id' = a.process_id::text
                  );

                SELECT COALESCE(jsonb_agg(jsonb_build_object(
                    'id', e.id::text,
                    'emission_source_id', e.emission_source_id::text,
                    'activity_data_id', CASE WHEN e.activity_data_id IS NULL THEN NULL ELSE e.activity_data_id::text END,
                    'document_id', CASE WHEN activity.document_id IS NULL THEN NULL ELSE activity.document_id::text END,
                    'scope', e.scope,
                    'period_start', zcy_iso_utc(e.period_start),
                    'period_end', zcy_iso_utc(e.period_end),
                    'emissions', e.co2_tonnes::text,
                    'unit', e.unit,
                    'factor_id', CASE WHEN e.factor_id IS NULL THEN NULL ELSE e.factor_id::text END,
                    'version', e.version,
                    'content_hash', e.content_hash
                ) ORDER BY e.id::text), '[]'::jsonb)
                INTO emissions_json
                FROM jsonb_array_elements_text(NEW.derived_from::jsonb) ref
                JOIN emission_results e
                  ON ref.value = 'emission_result:' || e.id::text
                 AND e.tenant_id = NEW.tenant_id
                 AND e.period_start = NEW.period_start
                 AND e.period_end = NEW.period_end
                 AND e.scope IN ('scope_1', 'scope_2')
                 AND e.unit = 'tCO2e'
                 AND e.superseded_by_id IS NULL
                JOIN emission_sources source ON source.id = e.emission_source_id
                JOIN sites site
                  ON site.id = source.site_id
                 AND site.enterprise_id = (account_json ->> 'enterprise_id')::uuid
                LEFT JOIN activity_data activity
                  ON activity.id = e.activity_data_id
                 AND activity.tenant_id = NEW.tenant_id
                WHERE ref.value LIKE 'emission_result:%'
                  AND EXISTS (
                      SELECT 1 FROM jsonb_array_elements(attributions_json) attribution_item
                      WHERE attribution_item ->> 'source_ref' = 'emission_result:' || e.id::text
                  );

                SELECT COALESCE(jsonb_agg(jsonb_build_object(
                    'id', d.id::text,
                    'filename', d.filename,
                    'mime_type', d.mime_type,
                    'size_bytes', d.size_bytes,
                    'doc_type', d.doc_type,
                    'content_hash', d.content_hash
                ) ORDER BY d.id::text), '[]'::jsonb)
                INTO documents_json
                FROM jsonb_array_elements_text(NEW.derived_from::jsonb) ref
                JOIN documents d
                  ON ref.value = 'document:' || d.id::text
                 AND d.tenant_id = NEW.tenant_id
                 AND d.enterprise_id = (account_json ->> 'enterprise_id')::uuid
                WHERE ref.value LIKE 'document:%'
                  AND EXISTS (
                      SELECT 1 FROM jsonb_array_elements(emissions_json) emission_item
                      WHERE emission_item ->> 'document_id' = d.id::text
                  );

                SELECT COALESCE(jsonb_agg(jsonb_build_object(
                    'id', s.id::text,
                    'process_id', s.process_id::text,
                    'product_id', s.product_id::text,
                    'production_output_id', s.production_output_id::text,
                    'direct_emissions', s.direct_emissions::text,
                    'indirect_emissions', s.indirect_emissions::text,
                    'precursor_emissions', s.precursor_emissions::text,
                    'total_emissions', s.total_emissions::text,
                    'emissions_unit', s.emissions_unit,
                    'specific_emissions', s.specific_emissions::text,
                    'specific_unit', s.specific_unit,
                    'data_quality', s.data_quality,
                    'methodology_ref', s.methodology_ref,
                    'derived_from', s.derived_from::jsonb,
                    'version', s.version,
                    'content_hash', s.content_hash,
                    'replay_match', true
                ) ORDER BY s.id::text), '[]'::jsonb)
                INTO see_json
                FROM jsonb_array_elements_text(NEW.derived_from::jsonb) ref
                JOIN cbam_see_results s
                  ON ref.value = 'see_result:' || s.id::text
                 AND s.tenant_id = NEW.tenant_id
                 AND s.period_start = NEW.period_start
                 AND s.period_end = NEW.period_end
                 AND s.superseded_by_id IS NULL
                WHERE ref.value LIKE 'see_result:%'
                  AND EXISTS (
                      SELECT 1 FROM jsonb_array_elements(processes_json) process_item
                      WHERE process_item ->> 'id' = s.process_id::text
                  )
                  AND EXISTS (
                      SELECT 1 FROM jsonb_array_elements(products_json) product_item
                      WHERE product_item ->> 'id' = s.product_id::text
                        AND product_item ->> 'process_id' = s.process_id::text
                  )
                  AND EXISTS (
                      SELECT 1 FROM jsonb_array_elements(outputs_json) output_item
                      WHERE output_item ->> 'id' = s.production_output_id::text
                        AND output_item ->> 'process_id' = s.process_id::text
                        AND output_item ->> 'product_id' = s.product_id::text
                  );

                SELECT COALESCE(jsonb_agg(jsonb_build_object(
                    'id', r.id::text,
                    'rule_kind', r.rule_kind,
                    'title', r.title,
                    'publisher', r.publisher,
                    'document_number', r.document_number,
                    'jurisdiction', r.jurisdiction,
                    'vintage', r.vintage,
                    'valid_from', zcy_iso_utc(r.valid_from),
                    'valid_to', zcy_iso_utc(r.valid_to),
                    'source_url', r.source_url,
                    'content_hash', r.content_hash
                ) ORDER BY r.id::text), '[]'::jsonb)
                INTO rules_json
                FROM jsonb_array_elements_text(NEW.derived_from::jsonb) ref
                JOIN rule_records r
                  ON ref.value = 'rule_record:' || r.id::text
                 AND r.tenant_id = NEW.tenant_id
                 AND r.status = 'approved'
                 AND r.valid_from <= NEW.period_start
                 AND (r.valid_to IS NULL OR r.valid_to >= NEW.period_end)
                WHERE ref.value LIKE 'rule_record:%'
                  AND EXISTS (
                      SELECT 1 FROM jsonb_array_elements(see_json) see_item
                      WHERE see_item ->> 'methodology_ref' = 'rule_record:' || r.id::text
                  );

                SELECT jsonb_build_object(
                    'id', r.id::text,
                    'profile_version_id', r.profile_version_id::text,
                    'reviewer_id', r.reviewer_id,
                    'reviewer_role', r.reviewer_role,
                    'verdict', r.verdict,
                    'summary', r.summary,
                    'findings', r.findings_json::jsonb,
                    'disclaimer', r.disclaimer,
                    'content_hash', r.content_hash,
                    'created_at', zcy_iso_utc(r.created_at)
                ) INTO review_json
                FROM jsonb_array_elements_text(NEW.derived_from::jsonb) ref
                JOIN methodology_reviews r
                  ON ref.value = 'methodology_review:' || r.id::text
                 AND r.tenant_id = NEW.tenant_id
                 AND r.account_id = NEW.account_id
                 AND r.profile_version_id = NEW.supersedes_id
                 AND r.verdict IN ('pass', 'pass_with_actions')
                WHERE ref.value LIKE 'methodology_review:%';

                IF account_json IS NULL OR installation_json IS NULL
                   OR jsonb_array_length(processes_json) = 0
                   OR jsonb_array_length(products_json) = 0
                   OR jsonb_array_length(outputs_json) = 0
                   OR jsonb_array_length(attributions_json) = 0
                   OR jsonb_array_length(emissions_json) = 0
                   OR jsonb_array_length(documents_json) = 0
                   OR jsonb_array_length(see_json) = 0
                   OR jsonb_array_length(rules_json) = 0
                   OR review_json IS NULL THEN
                    RAISE EXCEPTION 'published passport replay is missing formal facts';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM installation_account_members member
                    JOIN cbam_production_processes process
                      ON process.installation_id = member.installation_id
                     AND process.tenant_id = NEW.tenant_id
                     AND process.superseded_by_id IS NULL
                    WHERE member.account_id = NEW.account_id
                      AND member.tenant_id = NEW.tenant_id
                      AND NOT (
                          NEW.derived_from::jsonb ?
                          ('production_process:' || process.id::text)
                      )
                ) OR EXISTS (
                    SELECT 1
                    FROM installation_account_members member
                    JOIN cbam_production_processes process
                      ON process.installation_id = member.installation_id
                     AND process.tenant_id = NEW.tenant_id
                     AND process.superseded_by_id IS NULL
                    JOIN cbam_products product
                      ON product.process_id = process.id
                     AND product.tenant_id = NEW.tenant_id
                     AND product.superseded_by_id IS NULL
                    WHERE member.account_id = NEW.account_id
                      AND member.tenant_id = NEW.tenant_id
                      AND NOT (
                          NEW.derived_from::jsonb ?
                          ('cbam_product:' || product.id::text)
                      )
                ) OR EXISTS (
                    SELECT 1
                    FROM installation_account_members member
                    JOIN cbam_production_processes process
                      ON process.installation_id = member.installation_id
                     AND process.tenant_id = NEW.tenant_id
                     AND process.superseded_by_id IS NULL
                    JOIN cbam_production_outputs output
                      ON output.process_id = process.id
                     AND output.tenant_id = NEW.tenant_id
                     AND output.period_start = NEW.period_start
                     AND output.period_end = NEW.period_end
                     AND output.superseded_by_id IS NULL
                    WHERE member.account_id = NEW.account_id
                      AND member.tenant_id = NEW.tenant_id
                      AND NOT (
                          NEW.derived_from::jsonb ?
                          ('production_output:' || output.id::text)
                      )
                ) OR EXISTS (
                    SELECT 1
                    FROM installation_account_members member
                    JOIN cbam_production_processes process
                      ON process.installation_id = member.installation_id
                     AND process.tenant_id = NEW.tenant_id
                     AND process.superseded_by_id IS NULL
                    JOIN cbam_source_stream_attributions attribution
                      ON attribution.process_id = process.id
                     AND attribution.tenant_id = NEW.tenant_id
                     AND attribution.period_start = NEW.period_start
                     AND attribution.period_end = NEW.period_end
                     AND attribution.superseded_by_id IS NULL
                    WHERE member.account_id = NEW.account_id
                      AND member.tenant_id = NEW.tenant_id
                      AND NOT (
                          NEW.derived_from::jsonb ?
                          ('attribution:' || attribution.id::text)
                      )
                ) THEN
                    RAISE EXCEPTION 'published passport omits current formal facts';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements_text(NEW.derived_from::jsonb) ref
                    JOIN cbam_source_stream_attributions a
                      ON ref.value = 'attribution:' || a.id::text
                     AND a.tenant_id = NEW.tenant_id
                    WHERE ref.value LIKE 'attribution:%'
                    GROUP BY a.source_ref
                    HAVING sum(a.share) <> 1
                ) THEN
                    RAISE EXCEPTION 'published passport attribution replay is incomplete';
                END IF;

                IF EXISTS (
                    SELECT 1 FROM jsonb_array_elements(attributions_json) attribution_item
                    WHERE NOT EXISTS (
                        SELECT 1 FROM jsonb_array_elements(emissions_json) emission_item
                        WHERE attribution_item ->> 'source_ref' =
                              'emission_result:' || (emission_item ->> 'id')
                    )
                ) THEN
                    RAISE EXCEPTION 'published passport attribution source is not replayable';
                END IF;

                IF EXISTS (
                    SELECT 1 FROM jsonb_array_elements(emissions_json) item
                    WHERE item ->> 'document_id' IS NULL
                       OR NOT EXISTS (
                           SELECT 1 FROM jsonb_array_elements(documents_json) document_item
                           WHERE document_item ->> 'id' = item ->> 'document_id'
                       )
                ) THEN
                    RAISE EXCEPTION 'published passport evidence replay is incomplete';
                END IF;

                IF EXISTS (
                    SELECT 1 FROM jsonb_array_elements(outputs_json) output_item
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM jsonb_array_elements(see_json) see_item
                        CROSS JOIN LATERAL jsonb_array_elements_text(
                            see_item -> 'derived_from'
                        ) see_ref
                        WHERE see_ref.value =
                              'production_output:' || (output_item ->> 'id')
                    )
                ) OR EXISTS (
                    SELECT 1 FROM jsonb_array_elements(attributions_json) attribution_item
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM jsonb_array_elements(see_json) see_item
                        CROSS JOIN LATERAL jsonb_array_elements_text(
                            see_item -> 'derived_from'
                        ) see_ref
                        WHERE see_ref.value =
                              'attribution:' || (attribution_item ->> 'id')
                    )
                ) THEN
                    RAISE EXCEPTION 'published passport SEE does not cover current formal inputs';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements_text(NEW.derived_from::jsonb) ref
                    JOIN cbam_see_results s
                      ON ref.value = 'see_result:' || s.id::text
                     AND s.tenant_id = NEW.tenant_id
                    JOIN cbam_production_outputs output ON output.id = s.production_output_id
                    CROSS JOIN LATERAL (
                        SELECT
                            COALESCE(sum(e.co2_tonnes * a.share) FILTER (WHERE e.scope = 'scope_1'), 0) AS direct,
                            COALESCE(sum(e.co2_tonnes * a.share) FILTER (WHERE e.scope = 'scope_2'), 0) AS indirect,
                            bool_and(e.scope IN ('scope_1', 'scope_2') AND e.unit = 'tCO2e') AS valid_inputs
                        FROM jsonb_array_elements_text(s.derived_from::jsonb) see_ref
                        JOIN cbam_source_stream_attributions a
                          ON see_ref.value = 'attribution:' || a.id::text
                         AND a.tenant_id = s.tenant_id
                        JOIN emission_results e
                          ON a.source_ref = 'emission_result:' || e.id::text
                         AND e.tenant_id = s.tenant_id
                        WHERE see_ref.value LIKE 'attribution:%'
                    ) emission_totals
                    CROSS JOIN LATERAL (
                        SELECT
                            COALESCE(sum(p.quantity * p.specific_emissions), 0) AS precursor,
                            CASE
                                WHEN count(p.id) = 0 THEN 'not_applicable'
                                WHEN bool_or(p.data_quality = 'rule_default') THEN 'rule_default'
                                WHEN bool_or(p.data_quality = 'supplier_declared') THEN 'supplier_declared'
                                ELSE 'supplier_verified'
                            END AS expected_quality
                        FROM jsonb_array_elements_text(s.derived_from::jsonb) see_ref
                        JOIN cbam_precursor_consumptions p
                          ON see_ref.value = 'precursor:' || p.id::text
                         AND p.tenant_id = s.tenant_id
                        WHERE see_ref.value LIKE 'precursor:%'
                    ) precursor_totals
                    WHERE ref.value LIKE 'see_result:%'
                      AND (
                          emission_totals.valid_inputs IS DISTINCT FROM true
                          OR s.direct_emissions <> emission_totals.direct
                          OR s.indirect_emissions <> emission_totals.indirect
                          OR s.precursor_emissions <> precursor_totals.precursor
                          OR s.total_emissions <> emission_totals.direct + emission_totals.indirect + precursor_totals.precursor
                          OR s.specific_emissions <> round(
                              (emission_totals.direct + emission_totals.indirect + precursor_totals.precursor)
                              / output.quantity,
                              12
                          )
                          OR s.data_quality <> precursor_totals.expected_quality
                          OR s.content_hash <> zcy_passport_expected_see_hash(s)
                          OR EXISTS (
                              SELECT 1 FROM jsonb_array_elements_text(s.derived_from::jsonb) see_ref
                              WHERE see_ref.value LIKE 'attribution:%'
                                AND NOT (NEW.derived_from::jsonb ? see_ref.value)
                          )
                      )
                ) THEN
                    RAISE EXCEPTION 'published passport SEE cannot be deterministically replayed';
                END IF;

                expected_snapshot := jsonb_build_object(
                    'schema_version', 1,
                    'account', account_json,
                    'installation', installation_json,
                    'period', jsonb_build_object(
                        'start', zcy_iso_utc(NEW.period_start),
                        'end', zcy_iso_utc(NEW.period_end)
                    ),
                    'processes', processes_json,
                    'products', products_json,
                    'production_outputs', outputs_json,
                    'attributions', attributions_json,
                    'emission_results', emissions_json,
                    'evidence_manifest', documents_json,
                    'see_results', see_json,
                    'rule_records', rules_json,
                    'methodology_review', review_json
                );

                expected_assessment := jsonb_build_object(
                    'score', 100,
                    'grade', 'A',
                    'checks', jsonb_build_array(
                        jsonb_build_object('key', 'installation_identity', 'label', '装置身份', 'passed', true, 'reason', '已满足'),
                        jsonb_build_object('key', 'production_process', 'label', '生产工序', 'passed', true, 'reason', '已满足'),
                        jsonb_build_object('key', 'product', 'label', '产品与 CN 编码', 'passed', true, 'reason', '已满足'),
                        jsonb_build_object('key', 'production_output', 'label', '报告期产量', 'passed', true, 'reason', '已满足'),
                        jsonb_build_object('key', 'attributed_emissions', 'label', '活动排放归集', 'passed', true, 'reason', '已满足'),
                        jsonb_build_object('key', 'evidence_documents', 'label', '源文件证据', 'passed', true, 'reason', '已满足'),
                        jsonb_build_object('key', 'deterministic_see', 'label', '确定性 SEE', 'passed', true, 'reason', '已满足'),
                        jsonb_build_object('key', 'authoritative_rule', 'label', '权威方法学规则', 'passed', true, 'reason', '已满足'),
                        jsonb_build_object('key', 'methodology_review', 'label', '方法学复核', 'passed', true, 'reason', '已满足')
                    ),
                    'missing_keys', jsonb_build_array(),
                    'ready_to_publish', true
                );

                SELECT jsonb_build_array('installation:' || NEW.installation_id::text)
                    || COALESCE((SELECT jsonb_agg(to_jsonb('production_process:' || (item ->> 'id')) ORDER BY item ->> 'id') FROM jsonb_array_elements(processes_json) item), '[]'::jsonb)
                    || COALESCE((SELECT jsonb_agg(to_jsonb('cbam_product:' || (item ->> 'id')) ORDER BY item ->> 'id') FROM jsonb_array_elements(products_json) item), '[]'::jsonb)
                    || COALESCE((SELECT jsonb_agg(to_jsonb('production_output:' || (item ->> 'id')) ORDER BY item ->> 'id') FROM jsonb_array_elements(outputs_json) item), '[]'::jsonb)
                    || COALESCE((SELECT jsonb_agg(to_jsonb('attribution:' || (item ->> 'id')) ORDER BY item ->> 'id') FROM jsonb_array_elements(attributions_json) item), '[]'::jsonb)
                    || COALESCE((SELECT jsonb_agg(to_jsonb('emission_result:' || (item ->> 'id')) ORDER BY item ->> 'id') FROM jsonb_array_elements(emissions_json) item), '[]'::jsonb)
                    || COALESCE((SELECT jsonb_agg(to_jsonb('document:' || (item ->> 'id')) ORDER BY item ->> 'id') FROM jsonb_array_elements(documents_json) item), '[]'::jsonb)
                    || COALESCE((SELECT jsonb_agg(to_jsonb('see_result:' || (item ->> 'id')) ORDER BY item ->> 'id') FROM jsonb_array_elements(see_json) item), '[]'::jsonb)
                    || COALESCE((SELECT jsonb_agg(to_jsonb('rule_record:' || (item ->> 'id')) ORDER BY item ->> 'id') FROM jsonb_array_elements(rules_json) item), '[]'::jsonb)
                    || jsonb_build_array('methodology_review:' || (review_json ->> 'id'))
                INTO expected_references;

                IF NEW.snapshot_json::jsonb IS DISTINCT FROM expected_snapshot THEN
                    RAISE EXCEPTION 'published passport snapshot does not replay from formal facts';
                END IF;
                IF NEW.assessment_json::jsonb IS DISTINCT FROM expected_assessment
                   OR NEW.completeness_score <> 100
                   OR NEW.data_quality_grade <> 'A' THEN
                    RAISE EXCEPTION 'published passport assessment is not database-derived';
                END IF;
                IF NEW.derived_from::jsonb IS DISTINCT FROM expected_references THEN
                    RAISE EXCEPTION 'published passport references do not match its snapshot';
                END IF;

                expected_hash := encode(
                    digest(
                        convert_to(
                            zcy_canonical_jsonb(jsonb_build_object(
                                'record_type', 'installation_profile_version',
                                'tenant_id', NEW.tenant_id::text,
                                'account_id', NEW.account_id::text,
                                'installation_id', NEW.installation_id::text,
                                'status', NEW.status,
                                'schema_version', NEW.schema_version,
                                'snapshot', expected_snapshot,
                                'assessment', expected_assessment,
                                'derived_from', expected_references
                            )),
                            'UTF8'
                        ),
                        'sha256'
                    ),
                    'hex'
                );
                IF NEW.content_hash <> expected_hash THEN
                    RAISE EXCEPTION 'published passport content hash does not match replayed body';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_passport_profile_replay_guard_insert
            BEFORE INSERT ON installation_profile_versions
            FOR EACH ROW EXECUTE FUNCTION zcy_passport_profile_replay_guard_insert();
            """
        )
    )


def _sqlite_upgrade() -> None:
    op.execute(
        sa.text(
            r"""
            CREATE TRIGGER trg_passport_profile_replay_guard_insert
            BEFORE INSERT ON installation_profile_versions
            FOR EACH ROW WHEN NEW.status = 'published'
            BEGIN
                SELECT CASE
                    WHEN NEW.content_hash <> zcy_passport_profile_hash(
                        NEW.tenant_id,
                        NEW.account_id,
                        NEW.installation_id,
                        NEW.status,
                        NEW.schema_version,
                        NEW.snapshot_json,
                        NEW.assessment_json,
                        NEW.derived_from
                    )
                    THEN RAISE(ABORT, 'published passport content hash does not match body')
                    WHEN replace(json_extract(NEW.snapshot_json, '$.account.id'), '-', '') <> replace(NEW.account_id, '-', '')
                      OR replace(json_extract(NEW.snapshot_json, '$.installation.id'), '-', '') <> replace(NEW.installation_id, '-', '')
                      OR datetime(json_extract(NEW.snapshot_json, '$.period.start')) <> datetime(NEW.period_start)
                      OR datetime(json_extract(NEW.snapshot_json, '$.period.end')) <> datetime(NEW.period_end)
                    THEN RAISE(ABORT, 'published passport snapshot identity or period mismatch')
                    WHEN json_extract(NEW.assessment_json, '$.score') <> 100
                      OR json_extract(NEW.assessment_json, '$.grade') <> 'A'
                      OR json_extract(NEW.assessment_json, '$.ready_to_publish') <> 1
                      OR json_array_length(json_extract(NEW.assessment_json, '$.checks')) <> 9
                      OR json_array_length(json_extract(NEW.assessment_json, '$.missing_keys')) <> 0
                      OR EXISTS (
                          SELECT 1 FROM json_each(NEW.assessment_json, '$.checks') item
                          WHERE json_extract(item.value, '$.passed') <> 1
                      )
                    THEN RAISE(ABORT, 'published passport assessment is not derived')
                    WHEN json_array_length(json_extract(NEW.snapshot_json, '$.processes')) = 0
                      OR json_array_length(json_extract(NEW.snapshot_json, '$.products')) = 0
                      OR json_array_length(json_extract(NEW.snapshot_json, '$.production_outputs')) = 0
                      OR json_array_length(json_extract(NEW.snapshot_json, '$.attributions')) = 0
                      OR json_array_length(json_extract(NEW.snapshot_json, '$.emission_results')) = 0
                      OR json_array_length(json_extract(NEW.snapshot_json, '$.evidence_manifest')) = 0
                      OR json_array_length(json_extract(NEW.snapshot_json, '$.see_results')) = 0
                      OR json_array_length(json_extract(NEW.snapshot_json, '$.rule_records')) = 0
                      OR json_type(NEW.snapshot_json, '$.methodology_review') <> 'object'
                    THEN RAISE(ABORT, 'published passport snapshot is incomplete')
                END;
            END;
            """
        )
    )


def upgrade() -> None:
    _ensure_no_published_profiles()
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        _postgres_upgrade()
    elif dialect == "sqlite":
        _sqlite_upgrade()


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_passport_profile_replay_guard_insert"))
    if dialect == "postgresql":
        for signature in (
            "zcy_passport_profile_replay_guard_insert()",
            "zcy_passport_expected_see_hash(cbam_see_results)",
            "zcy_iso_offset_utc(timestamptz)",
            "zcy_iso_utc(timestamptz)",
            "zcy_canonical_jsonb(jsonb)",
        ):
            op.execute(sa.text(f"DROP FUNCTION IF EXISTS {signature} CASCADE"))
