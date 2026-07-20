export interface PassportCheck {
  key: string;
  label: string;
  passed: boolean;
  reason: string;
}

export interface PassportAssessment {
  score: number;
  grade: "A" | "B" | "C";
  checks: PassportCheck[];
  missing_keys: string[];
  ready_to_publish: boolean;
}

export interface PassportProfile {
  id: string;
  account_id: string;
  installation_id: string;
  period_start: string;
  period_end: string;
  status: "draft" | "published";
  schema_version: number;
  version: number;
  completeness_score: number;
  data_quality_grade: string;
  content_hash: string;
  assessment: PassportAssessment;
  snapshot: Record<string, unknown> & {
    production_outputs?: ProductionOutput[];
    attributions?: Attribution[];
    see_results?: SEEOutput[];
    evidence_manifest?: EvidenceManifestItem[];
    rule_records?: RuleRecord[];
    methodology_review?: MethodologyReview | null;
  };
  replay: {
    match: boolean;
    content_hash_match: boolean;
    snapshot_match: boolean;
    assessment_match: boolean;
  };
  created_at?: string | null;
}

export interface MethodologyReview {
  id: string;
  profile_version_id: string;
  reviewer_id: string;
  reviewer_role: string;
  verdict: "pass" | "pass_with_actions" | "fail";
  summary: string;
  findings: Array<Record<string, unknown>>;
  disclaimer: string;
  content_hash: string;
  created_at?: string | null;
}

export interface SharingGrant {
  id: string;
  account_id: string;
  profile_version_id: string;
  recipient_tenant_id?: string | null;
  recipient_name: string;
  recipient_type: string;
  purpose: string;
  scopes: string[];
  expires_at: string;
  active: boolean;
  content_hash: string;
  created_at?: string | null;
}

export interface ProductionOutput {
  id: string;
  process_id: string;
  product_id: string;
  period_start: string;
  period_end: string;
  quantity: string;
  unit: string;
  version: number;
  content_hash: string;
}

export interface Attribution {
  id: string;
  process_id: string;
  source_ref: string;
  period_start: string;
  period_end: string;
  share: string;
  method: string;
  version: number;
  content_hash: string;
}

export interface SEEOutput {
  id: string;
  process_id: string;
  product_id: string;
  production_output_id: string;
  direct_emissions: string;
  indirect_emissions: string;
  precursor_emissions: string;
  total_emissions: string;
  emissions_unit: string;
  specific_emissions: string;
  specific_unit: string;
  data_quality: string;
  methodology_ref: string;
  replay_match?: boolean;
  content_hash: string;
}

export interface EvidenceManifestItem {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  doc_type: string;
  content_hash: string;
}

export interface RuleRecord {
  id: string;
  rule_kind: string;
  title: string;
  publisher: string;
  document_number: string;
  jurisdiction: string;
  vintage: number;
  valid_from: string;
  valid_to?: string | null;
  status?: string;
  source_url: string;
  content_hash: string;
}

export interface EmissionCandidate {
  id: string;
  source_name: string;
  scope: string;
  category: string;
  period_start: string;
  period_end: string;
  emissions: string;
  unit: string;
  document_id?: string | null;
  document_name?: string | null;
  evidence_ready: boolean;
}

export interface PassportDetail {
  account: {
    id: string;
    tenant_id: string;
    enterprise_id: string;
    account_code: string;
    created_at?: string | null;
  };
  installation: {
    id: string;
    name: string;
    operator_name: string;
    country_code: string;
    unlocode?: string | null;
    version: number;
    content_hash: string;
  };
  processes: Array<{
    id: string;
    name: string;
    aggregate_goods_category: string;
    production_route: string;
    version: number;
  }>;
  products: Array<{
    id: string;
    process_id: string;
    name: string;
    cn_code: string;
    version: number;
  }>;
  assessment: PassportAssessment;
  current_snapshot: PassportProfile["snapshot"];
  profiles: PassportProfile[];
  reviews: MethodologyReview[];
  sharing_grants: SharingGrant[];
  distribution_events: Array<{
    id: string;
    profile_version_id: string;
    grant_id: string;
    channel: string;
    delivered_to: string;
    package_hash: string;
    actor_id: string;
    created_at?: string | null;
  }>;
}

type Headers = Record<string, string>;

async function api<T>(url: string, headers: Headers, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      ...headers,
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers || {}),
    },
  });
  if (!response.ok) {
    let message = `请求失败：${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string | Array<{ msg?: string }> };
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((item) => item.msg).filter(Boolean).join("；") || message;
    } catch {
      // Keep the status-based message when the backend did not return JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

function periodQuery(periodStart: string, periodEnd: string): string {
  const params = new URLSearchParams({
    period_start: new Date(`${periodStart}T00:00:00Z`).toISOString(),
    period_end: new Date(`${periodEnd}T23:59:59Z`).toISOString(),
  });
  return params.toString();
}

export function fetchPassports(headers: Headers): Promise<PassportDetail[]> {
  return api("/api/passports", headers);
}

export function fetchPassport(
  accountId: string,
  periodStart: string,
  periodEnd: string,
  headers: Headers,
): Promise<PassportDetail> {
  return api(`/api/passports/${accountId}?${periodQuery(periodStart, periodEnd)}`, headers);
}

export function createPassport(payload: Record<string, unknown>, headers: Headers): Promise<PassportDetail> {
  return api("/api/passports", headers, { method: "POST", body: JSON.stringify(payload) });
}

export function fetchEmissionCandidates(
  accountId: string,
  periodStart: string,
  periodEnd: string,
  headers: Headers,
): Promise<EmissionCandidate[]> {
  return api(`/api/passports/${accountId}/emission-candidates?${periodQuery(periodStart, periodEnd)}`, headers);
}

export function addOutput(
  accountId: string,
  payload: Record<string, unknown>,
  headers: Headers,
): Promise<ProductionOutput> {
  return api(`/api/passports/${accountId}/outputs`, headers, { method: "POST", body: JSON.stringify(payload) });
}

export function addAttribution(
  accountId: string,
  payload: Record<string, unknown>,
  headers: Headers,
): Promise<Attribution> {
  return api(`/api/passports/${accountId}/attributions`, headers, { method: "POST", body: JSON.stringify(payload) });
}

export function fetchRules(headers: Headers): Promise<RuleRecord[]> {
  return api("/api/passports/rules?rule_kind=cbam_methodology", headers);
}

export function registerRule(payload: Record<string, unknown>, headers: Headers): Promise<RuleRecord> {
  return api("/api/passports/rules", headers, { method: "POST", body: JSON.stringify(payload) });
}

export function calculateSEE(
  accountId: string,
  payload: Record<string, unknown>,
  headers: Headers,
): Promise<SEEOutput> {
  return api(`/api/passports/${accountId}/see-results`, headers, { method: "POST", body: JSON.stringify(payload) });
}

export function freezeProfile(
  accountId: string,
  periodStart: string,
  periodEnd: string,
  headers: Headers,
): Promise<PassportProfile> {
  return api(`/api/passports/${accountId}/profiles`, headers, {
    method: "POST",
    body: JSON.stringify({
      period_start: new Date(`${periodStart}T00:00:00Z`).toISOString(),
      period_end: new Date(`${periodEnd}T23:59:59Z`).toISOString(),
    }),
  });
}

export function reviewProfile(
  accountId: string,
  payload: Record<string, unknown>,
  headers: Headers,
): Promise<MethodologyReview> {
  return api(`/api/passports/${accountId}/reviews`, headers, { method: "POST", body: JSON.stringify(payload) });
}

export function publishProfile(
  accountId: string,
  payload: Record<string, unknown>,
  headers: Headers,
): Promise<PassportProfile> {
  return api(`/api/passports/${accountId}/publish`, headers, { method: "POST", body: JSON.stringify(payload) });
}

export function createGrant(
  accountId: string,
  payload: Record<string, unknown>,
  headers: Headers,
): Promise<SharingGrant> {
  return api(`/api/passports/${accountId}/sharing-grants`, headers, { method: "POST", body: JSON.stringify(payload) });
}

export function exportGrant(accountId: string, grantId: string, headers: Headers): Promise<{ package_hash: string; package: Record<string, unknown> }> {
  return api(`/api/passports/${accountId}/sharing-grants/${grantId}/export`, headers, { method: "POST" });
}

export function revokeGrant(accountId: string, grantId: string, reason: string, headers: Headers): Promise<unknown> {
  return api(`/api/passports/${accountId}/sharing-grants/${grantId}/revoke`, headers, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}
