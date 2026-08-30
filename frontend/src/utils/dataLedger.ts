export type DataLedgerSummary = {
  total: number;
  calculated: number;
  pending_factor: number;
  source_documents: number;
};

export type DataLedgerItem = {
  activity_data_id: string;
  period: { start: string; end: string; label: string };
  facility: { site_id: string; name: string; grid_region: string };
  emission_source: {
    emission_source_id: string;
    name: string;
    scope: string;
    category: string;
  };
  activity: { quantity: string; unit: string; data_source: string };
  source_document: {
    document_id: string;
    filename: string;
    document_type: string;
    mime_type: string;
    size_bytes: number;
    content_hash: string;
    download_url: string;
    uploaded_at?: string | null;
  } | null;
  quality: {
    quality_review_id?: string | null;
    status: string;
    score?: number | null;
    score_label: string;
    warnings_resolved?: boolean | null;
  };
  confirmation: { confirmed_by: string; confirmed_at: string; version: number };
  calculation_status: "calculated" | "pending_factor";
  emission_result: {
    emission_result_id: string;
    co2_tonnes: string;
    unit: string;
    factor_id?: string | null;
    confirmed_at?: string | null;
  } | null;
  content_hash: string;
};

export type StandardizedField = {
  canonical_key: string;
  canonical_value?: string | null;
  expected_unit?: string | null;
  concepts: string[];
  raw_field?: string | null;
  raw_value?: unknown;
  source_locator?: Record<string, unknown> | null;
  formal_destination?: string | null;
  status: "formal" | "not_captured";
};

export type DataLedgerDetail = DataLedgerItem & {
  ontology: { version: string; role: string };
  standardized_fields: StandardizedField[];
  quality_review: DataLedgerItem["quality"] & {
    summary?: string | null;
    counts?: Record<string, number>;
    findings: Array<Record<string, unknown>>;
    resolutions: Array<Record<string, unknown>>;
    quality_result_sha256?: string | null;
    resolution_sha256?: string | null;
  };
  human_confirmation: {
    actor_user_id: string;
    candidate_id?: string | null;
    confirmed_at: string;
    value_origin: string;
  };
  formal_record: {
    record_type: string;
    content_hash: string;
    idempotency_key: string;
    version: number;
    confirmed_by: string;
    confirmed_at: string;
    append_only: boolean;
    supersedes_id?: string | null;
    superseded_by_id?: string | null;
  };
  lineage: string[];
  version_history: Array<{
    activity_data_id: string;
    version: number;
    quantity: string;
    unit: string;
    content_hash: string;
    confirmed_by: string;
    confirmed_at: string;
    is_current: boolean;
    supersedes_id?: string | null;
  }>;
};

export type DataLedgerResponse = {
  summary: DataLedgerSummary;
  items: DataLedgerItem[];
  pagination: { page: number; page_size: number; total: number; pages: number };
};

export type DataLedgerFilters = {
  q?: string;
  status?: "all" | "calculated" | "pending_factor";
  category?: string;
  periodStart?: string;
  periodEnd?: string;
  page?: number;
  pageSize?: number;
};

type HeadersFactory = () => Record<string, string>;

function searchParams(filters: DataLedgerFilters, includePagination = true): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.q?.trim()) params.set("q", filters.q.trim());
  if (filters.status && filters.status !== "all") params.set("status", filters.status);
  if (filters.category) params.set("category", filters.category);
  if (filters.periodStart) params.set("period_start", filters.periodStart);
  if (filters.periodEnd) params.set("period_end", filters.periodEnd);
  if (includePagination) {
    params.set("page", String(filters.page || 1));
    params.set("page_size", String(filters.pageSize || 20));
  }
  return params;
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `请求失败（${response.status}）`;
    try {
      const payload = await response.json() as { detail?: string };
      if (payload.detail) detail = payload.detail;
    } catch {
      // Keep the status-based fallback when the response is not JSON.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export async function fetchDataLedger(
  getHeaders: HeadersFactory,
  filters: DataLedgerFilters,
  signal?: AbortSignal,
): Promise<DataLedgerResponse> {
  const params = searchParams(filters);
  return parse<DataLedgerResponse>(await fetch(`/api/formal-activities?${params}`, {
    headers: getHeaders(),
    credentials: "include",
    signal,
  }));
}

export async function fetchDataLedgerDetail(
  getHeaders: HeadersFactory,
  activityId: string,
  signal?: AbortSignal,
): Promise<DataLedgerDetail> {
  return parse<DataLedgerDetail>(await fetch(`/api/formal-activities/${encodeURIComponent(activityId)}`, {
    headers: getHeaders(),
    credentials: "include",
    signal,
  }));
}

export async function exportDataLedger(
  getHeaders: HeadersFactory,
  filters: DataLedgerFilters,
): Promise<void> {
  const params = searchParams(filters, false);
  const response = await fetch(`/api/formal-activities/export?${params}`, {
    headers: getHeaders(),
    credentials: "include",
  });
  if (!response.ok) {
    await parse<never>(response);
    return;
  }
  const blob = await response.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `CarbonLab_标准化数据台账_${new Date().toISOString().slice(0, 10)}.xlsx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}

export async function downloadEvidence(
  getHeaders: HeadersFactory,
  url: string,
  filename: string,
): Promise<void> {
  const response = await fetch(url, {
    headers: getHeaders(),
    credentials: "include",
  });
  if (!response.ok) {
    await parse<never>(response);
    return;
  }
  const blob = await response.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}
