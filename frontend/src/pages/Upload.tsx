import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  AlertCircle,
  AlertTriangle,
  Bot,
  CheckCircle2,
  ClipboardCheck,
  ChevronLeft,
  ChevronRight,
  Download,
  FileSpreadsheet,
  FileText,
  ImageIcon,
  Loader2,
  PencilLine,
  RefreshCw,
  ShieldCheck,
  UploadCloud,
} from "lucide-react";
import { Link } from "react-router-dom";
import { AgentRunDrawer } from "../components/AgentRunDetail";
import ProductJourney from "../components/ProductJourney";
import { useAuth } from "../contexts/AuthContext";
import {
  agentStatusLabel,
  agentStatusTone,
  fetchAgentRuns,
  type AgentRun,
} from "../utils/agentOps";
import { type WorkforceDocumentSnapshot } from "../utils/workforce";

type InboxStatus = "待确认" | "已完成" | "异常" | "识别中";
type FieldStatus = "已识别" | "待确认" | "人工修正" | "异常";
type InboxFilter = "all" | "pending" | "done" | "abnormal";
type ListState = "loading" | "ready" | "error";
type NoticeTone = "info" | "success" | "warning" | "error";

type RecognizedField = {
  key: string;
  label: string;
  value: string;
  status: FieldStatus;
  confidence: string;
};

type ApiUploadFile = {
  file_id: string;
  content_hash?: string | null;
  filename: string;
  mime_type?: string | null;
  size_bytes?: number | null;
  storage_url?: string | null;
  document_type?: string | null;
  fields?: Record<string, unknown> | null;
  confidence?: number | null;
  raw_text?: string | null;
  tables?: unknown[] | null;
  errors?: unknown[] | null;
  ocr_status?: string | null;
  workforce?: WorkforceDocumentSnapshot | null;
};

type InboxFile = {
  id: string;
  name: string;
  meta: string;
  status: InboxStatus;
  color: "blue" | "red" | "green" | "slate";
  documentType: string;
  confidence: number;
  fields: RecognizedField[];
  rawText: string;
  mimeType: string;
  sizeBytes: number;
  storageUrl?: string;
  contentHash?: string;
  tables: unknown[];
  errors: string[];
  ocrStatus: string;
  workforce: WorkforceDocumentSnapshot;
};

type UnderstandResponse = {
  document_type: string;
  fields: Record<string, unknown>;
  confidence: number;
  summary: string;
};

type FormalEmissionResult = {
  emission_result_id: string;
  co2_tonnes: number;
  co2_tonnes_exact?: string;
  unit: string;
  factor_id?: string | null;
  uncertainty_pct?: number | null;
  confidence_95_low?: number | null;
  confidence_95_high?: number | null;
};

type FormalWrite = {
  site_id?: string;
  site_name?: string;
  activity_data_id: string;
  document_id?: string | null;
  activity_quantity?: string;
  activity_unit?: string;
  period_start?: string;
  period_end?: string;
  emission_source_id: string;
  emission_source_name: string;
  calculation_status: "calculated" | "pending_factor";
  emission_result?: FormalEmissionResult | null;
  suggested_passport_account_id?: string | null;
};

type ConfirmResponse = {
  status: string;
  message: string;
  activity_record: {
    record_id: string;
    quantity?: number | null;
    unit?: string | null;
    period?: string;
    facility?: string;
  };
  workflow_id: string;
  step_key: string;
  confirmation: {
    candidate_id: string;
    fields_sha256: string;
    subject_sha256: string;
  };
  formal_write?: FormalWrite;
};

type FactorCandidate = {
  factor_id: string;
  factor_snapshot_sha256: string;
  name: string;
  code: string;
  region?: string | null;
  year: number;
  version_year?: number | null;
  published_date?: string | null;
  value: string;
  unit: string;
  source: string;
  source_url?: string | null;
  uncertainty_pct?: string | null;
  tenant_scope: "platform" | "tenant";
  region_match: "exact" | "national";
  preview_emissions: string;
  preview_unit: string;
};

type FactorCandidateResponse = {
  activity: {
    activity_data_id: string;
    quantity: string;
    unit: string;
    period_start: string;
    period_end: string;
    facility: string;
    grid_region: string;
  };
  calculation_status: "calculated" | "pending_factor";
  emission_result?: FormalEmissionResult | null;
  factor_candidates: FactorCandidate[];
  human_gate: string;
  calculation_engine: string;
};

type FactorConfirmationResponse = {
  status: "calculated";
  message: string;
  formal_write: FormalWrite;
};

type CandidateSnapshotResponse = {
  candidate_id: string;
  candidate_token: string;
  fields_sha256: string;
  subject_sha256: string;
  expires_at: string;
};

type QualityFinding = {
  check_key: string;
  label: string;
  result: "pass" | "warning" | "fail";
  message: string;
  evidence_ref?: string | null;
};

type QualityReviewResponse = {
  quality_review_id: string;
  quality_review_token: string;
  quality_result_sha256: string;
  quality_status: "pass" | "pass_with_warnings" | "fail";
  score: number;
  summary: string;
  counts: { passed: number; warnings: number; failed: number };
  findings: QualityFinding[];
  retrievals?: Record<string, {
    retrieval_run_id: string;
    ontology_version: string;
    embedding_model: string;
    hits: Array<{
      title: string;
      excerpt: string;
      field_keys: string[];
      content_hash: string;
      fused_score: string;
    }>;
  }>;
  expires_at: string;
  next_gate: string;
};

type ReviewBundle = {
  fileId: string;
  candidate: CandidateSnapshotResponse;
  review: QualityReviewResponse;
};

type Notice = { tone: NoticeTone; text: string };

const DEFAULT_FACTOR_SELECTION_NOTE = "已核对因子年份、区域、来源及单位，确认用于本期活动排放计算。";

const fieldLabels: Record<string, string> = {
  billing_month: "账单月份",
  period: "期间",
  electricity_kwh: "用电量",
  total_amount: "金额",
  amount: "金额",
  unit: "单位",
  unit_price: "单价",
  supplier_name: "供应商",
  customer_name: "用户名称",
  customer_number: "户号",
  meter_date: "抄表日期",
  meter_reading_start: "上期读数",
  meter_reading_end: "本期读数",
  facility: "所属设施",
  production: "产量",
  raw_text: "原始文本",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseUploadFile(value: unknown, index?: number): ApiUploadFile {
  if (!isRecord(value) || typeof value.file_id !== "string" || typeof value.filename !== "string") {
    const location = index === undefined ? "上传响应" : `文件列表第 ${index + 1} 项`;
    throw new Error(`${location}缺少 file_id 或 filename`);
  }

  return {
    file_id: value.file_id,
    content_hash: typeof value.content_hash === "string" ? value.content_hash : undefined,
    filename: value.filename,
    mime_type: typeof value.mime_type === "string" ? value.mime_type : undefined,
    size_bytes: typeof value.size_bytes === "number" ? value.size_bytes : undefined,
    storage_url: typeof value.storage_url === "string" ? value.storage_url : undefined,
    document_type: typeof value.document_type === "string" ? value.document_type : undefined,
    fields: isRecord(value.fields) ? value.fields : {},
    confidence: typeof value.confidence === "number" ? value.confidence : 0,
    raw_text: typeof value.raw_text === "string" ? value.raw_text : "",
    tables: Array.isArray(value.tables) ? value.tables : [],
    errors: Array.isArray(value.errors) ? value.errors : [],
    ocr_status: typeof value.ocr_status === "string" ? value.ocr_status : undefined,
    workforce: isRecord(value.workforce) ? value.workforce as WorkforceDocumentSnapshot : {},
  };
}

function parseUploadList(payload: unknown): ApiUploadFile[] {
  let items: unknown;

  if (Array.isArray(payload)) {
    items = payload;
  } else if (isRecord(payload)) {
    items = [payload.files, payload.items, payload.documents, payload.data].find(Array.isArray);
  }

  if (!Array.isArray(items)) {
    throw new Error("文件列表响应格式不正确");
  }

  return items.map((item, index) => parseUploadFile(item, index));
}

function formatFieldValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (value === null || value === undefined) return "";

  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function clampConfidence(value: number | null | undefined): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, value));
}

function understandConfidence(value: number | null | undefined): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return 0;
  return clampConfidence(value <= 1 ? value * 100 : value);
}

function normalizeFields(fields: Record<string, unknown> | null | undefined, confidence: number): RecognizedField[] {
  const status: FieldStatus = confidence < 90 ? "待确认" : "已识别";

  return Object.entries(fields || {})
    .map(([key, value]) => ({ key, value: formatFieldValue(value) }))
    .filter((field) => field.value.trim().length > 0)
    .map((field) => ({
      key: field.key,
      label: fieldLabels[field.key] || field.key,
      value: field.value,
      status,
      confidence: `${Math.round(confidence)}%`,
    }));
}

function normalizeErrors(errors: unknown[] | null | undefined): string[] {
  return (errors || [])
    .map((error) => formatFieldValue(error).trim())
    .filter(Boolean);
}

function fileExtension(filename: string): string {
  const extension = filename.split(".").pop();
  return extension && extension !== filename ? extension.toUpperCase() : "";
}

function formatBytes(sizeBytes: number): string {
  if (!Number.isFinite(sizeBytes) || sizeBytes <= 0) return "";
  if (sizeBytes >= 1024 * 1024) return `${(sizeBytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(sizeBytes / 1024))} KB`;
}

function formatMeta(filename: string, mimeType: string, sizeBytes: number): string {
  const type = fileExtension(filename) || mimeType.split("/").pop()?.toUpperCase() || "文件";
  return [type, formatBytes(sizeBytes)].filter(Boolean).join(" · ");
}

function fileColor(filename: string, mimeType: string): InboxFile["color"] {
  const lowerName = filename.toLowerCase();
  if (mimeType.includes("spreadsheet") || /\.(xlsx?|csv)$/.test(lowerName)) return "green";
  if (mimeType.startsWith("image/")) return "blue";
  if (mimeType === "application/pdf" || lowerName.endsWith(".pdf")) return "red";
  return "slate";
}

function statusFromOcr(ocrStatus: string, errors: string[]): InboxStatus {
  const status = ocrStatus.toLowerCase();
  if (["failed", "error", "quality_failed"].includes(status) || errors.length > 0) return "异常";
  if (["pending", "processing", "recognizing", "识别中"].includes(status)) return "识别中";
  if (["confirmed", "written", "completed_write"].includes(status)) return "已完成";
  return "待确认";
}

function toInboxFile(
  file: ApiUploadFile,
  fallback?: { mimeType?: string; sizeBytes?: number; ocrStatus?: string },
): InboxFile {
  const confidence = understandConfidence(file.confidence);
  const mimeType = file.mime_type || fallback?.mimeType || "application/octet-stream";
  const sizeBytes = file.size_bytes ?? fallback?.sizeBytes ?? 0;
  const errors = normalizeErrors(file.errors);
  const ocrStatus = file.ocr_status || fallback?.ocrStatus || "completed";

  return {
    id: file.file_id,
    name: file.filename,
    meta: formatMeta(file.filename, mimeType, sizeBytes),
    status: statusFromOcr(ocrStatus, errors),
    color: fileColor(file.filename, mimeType),
    documentType: file.document_type || "unknown",
    confidence,
    fields: normalizeFields(file.fields, confidence),
    rawText: file.raw_text || "",
    mimeType,
    sizeBytes,
    storageUrl: `/api/upload/${file.file_id}/download`,
    contentHash: file.content_hash || undefined,
    tables: file.tables || [],
    errors,
    ocrStatus,
    workforce: file.workforce || {},
  };
}

function fieldsToObject(fields: RecognizedField[]): Record<string, string> {
  return fields.reduce<Record<string, string>>((values, field) => {
    values[field.key] = field.value;
    return values;
  }, {});
}

function fieldValue(fields: RecognizedField[], keys: string[]): string {
  const normalizedKeys = new Set(keys.map((key) => key.toLowerCase()));
  return fields.find((field) => normalizedKeys.has(field.key.toLowerCase()))?.value.trim() || "";
}

function exactEmissionText(result: FormalEmissionResult): string {
  const raw = result.co2_tonnes_exact || String(result.co2_tonnes);
  const [integer, fraction] = raw.split(".");
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return fraction ? `${grouped}.${fraction}` : grouped;
}

function missingElectricityFields(file: InboxFile | undefined): string[] {
  if (!file || file.documentType !== "electricity_bill") return [];
  const missing: string[] = [];
  if (!fieldValue(file.fields, ["electricity_kwh", "用电量", "activity_quantity", "quantity"])) missing.push("用电量");
  if (!fieldValue(file.fields, ["period", "账单月份", "billing_month", "date", "抄表日期"])) missing.push("报告期间");
  if (!fieldValue(file.fields, ["facility", "所属工厂", "customer_name"])) missing.push("所属设施");
  return missing;
}

async function responseError(response: Response, fallback: string): Promise<string> {
  const payload = await response.json().catch(() => null);
  if (isRecord(payload)) {
    if (typeof payload.detail === "string") return payload.detail;
    if (typeof payload.message === "string") return payload.message;
  }
  return `${fallback}（${response.status}）`;
}

function matchesFilter(file: InboxFile, filter: InboxFilter): boolean {
  if (filter === "pending") return file.status === "待确认" || file.status === "识别中";
  if (filter === "done") return file.status === "已完成";
  if (filter === "abnormal") return file.status === "异常";
  return true;
}

function ocrStatusLabel(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized === "pending") return "等待识别";
  if (normalized === "processing") return "正在识别";
  if (normalized === "completed") return "识别完成，等待确认";
  if (normalized === "candidate_ready") return "A-02 候选已锁定，等待质检";
  if (normalized === "quality_reviewed") return "A-03 质检完成，等待人工确认";
  if (normalized === "quality_failed") return "A-03 质检发现阻断项";
  if (normalized === "confirmed") return "已人工确认并写入正式账本";
  if (normalized === "failed") return "识别失败";
  return status || "未知";
}

export default function Upload() {
  const { getHeaders, isAuthenticated, isLoading: authLoading } = useAuth();
  const inputRef = useRef<HTMLInputElement>(null);
  const [inboxFiles, setInboxFiles] = useState<InboxFile[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<InboxFilter>("all");
  const [listState, setListState] = useState<ListState>("loading");
  const [listError, setListError] = useState<string | null>(null);
  const [operation, setOperation] = useState<"upload" | "understand" | "quality" | "confirm" | "factor" | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [confirmResult, setConfirmResult] = useState<{ fileId: string; data: ConfirmResponse } | null>(null);
  const [reviewBundle, setReviewBundle] = useState<ReviewBundle | null>(null);
  const [durableFormalWrite, setDurableFormalWrite] = useState<{
    fileId: string;
    data: FormalWrite | null;
  } | null>(null);
  const [formalWriteLoading, setFormalWriteLoading] = useState(false);
  const [factorBundle, setFactorBundle] = useState<FactorCandidateResponse | null>(null);
  const [factorLoading, setFactorLoading] = useState(false);
  const [factorError, setFactorError] = useState<string | null>(null);
  const [selectedFactorId, setSelectedFactorId] = useState("");
  const [factorSelectionNote, setFactorSelectionNote] = useState(DEFAULT_FACTOR_SELECTION_NOTE);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [agentRuns, setAgentRuns] = useState<AgentRun[]>([]);
  const [agentRunsError, setAgentRunsError] = useState<string | null>(null);
  const [selectedAgentRunId, setSelectedAgentRunId] = useState<string | null>(null);

  const loadFiles = useCallback(async (signal?: AbortSignal) => {
    setListState("loading");
    setListError(null);

    try {
      const response = await fetch("/api/upload", {
        headers: getHeaders(),
        credentials: "include",
        signal,
      });
      if (!response.ok) throw new Error(await responseError(response, "读取当前租户文件失败"));

      const payload: unknown = await response.json();
      const files = parseUploadList(payload).map((file) => toInboxFile(file));
      setInboxFiles(files);
      setSelectedId((current) => (
        current && files.some((file) => file.id === current) ? current : files[0]?.id ?? null
      ));
      setListState("ready");
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      const message = error instanceof Error ? error.message : "读取当前租户文件失败";
      setListError(message);
      setListState("error");
    }
  }, [getHeaders]);

  useEffect(() => {
    if (authLoading || !isAuthenticated) return;
    const controller = new AbortController();
    void loadFiles(controller.signal);
    return () => controller.abort();
  }, [authLoading, isAuthenticated, loadFiles]);

  const visibleFiles = inboxFiles.filter((file) => matchesFilter(file, activeFilter));
  const selected = visibleFiles.find((file) => file.id === selectedId) || visibleFiles[0];
  const selectedIndex = selected ? visibleFiles.findIndex((file) => file.id === selected.id) : -1;
  const selectedConfirm = selected && confirmResult?.fileId === selected.id ? confirmResult.data : null;
  const selectedReview = selected && reviewBundle?.fileId === selected.id ? reviewBundle : null;
  const selectedFormalWrite = selectedConfirm?.formal_write || (
    selected && durableFormalWrite?.fileId === selected.id ? durableFormalWrite.data : null
  );
  const selectedFactor = factorBundle && factorBundle.activity.activity_data_id === selectedFormalWrite?.activity_data_id
    ? factorBundle.factor_candidates.find((factor) => factor.factor_id === selectedFactorId) || null
    : null;
  const selectedMissingFields = missingElectricityFields(selected);
  const writeSupported = selected?.documentType === "electricity_bill";
  const counts = {
    all: inboxFiles.length,
    pending: inboxFiles.filter((file) => matchesFilter(file, "pending")).length,
    done: inboxFiles.filter((file) => file.status === "已完成").length,
    abnormal: inboxFiles.filter((file) => file.status === "异常").length,
  };
  const latestAgentRun = (agentId: string) => agentRuns.find((run) => run.agent_id === agentId) || null;

  useEffect(() => {
    const fileId = selected?.id;
    if (!fileId || authLoading || !isAuthenticated) {
      setAgentRuns([]);
      setAgentRunsError(null);
      return;
    }
    const controller = new AbortController();
    const loadRuns = async () => {
      try {
        const nextRuns = await fetchAgentRuns(getHeaders, { sourceFileId: fileId, limit: 100 }, controller.signal);
        setAgentRuns(nextRuns);
        setAgentRunsError(null);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setAgentRunsError(error instanceof Error ? error.message : "读取岗位执行记录失败");
      }
    };
    void loadRuns();
    const timer = window.setInterval(() => void loadRuns(), 5000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [authLoading, getHeaders, isAuthenticated, selected?.id]);

  useEffect(() => {
    const fileId = selected?.id;
    if (!fileId || authLoading || !isAuthenticated) {
      setDurableFormalWrite(null);
      setFormalWriteLoading(false);
      return;
    }

    const controller = new AbortController();
    setFormalWriteLoading(true);
    setFactorBundle(null);
    setFactorError(null);
    setSelectedFactorId("");
    void fetch(`/api/upload/${fileId}/formal-write`, {
      headers: getHeaders(),
      credentials: "include",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(await responseError(response, "读取正式活动状态失败"));
        const payload = await response.json() as { formal_write: FormalWrite | null };
        setDurableFormalWrite({ fileId, data: payload.formal_write });
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setDurableFormalWrite({ fileId, data: null });
        setNotice({ tone: "error", text: error instanceof Error ? error.message : "读取正式活动状态失败" });
      })
      .finally(() => {
        if (!controller.signal.aborted) setFormalWriteLoading(false);
      });

    return () => controller.abort();
  }, [authLoading, getHeaders, isAuthenticated, selected?.id]);

  useEffect(() => {
    const activityId = selectedFormalWrite?.calculation_status === "pending_factor"
      ? selectedFormalWrite.activity_data_id
      : null;
    if (!activityId || authLoading || !isAuthenticated) {
      setFactorBundle(null);
      setFactorLoading(false);
      setFactorError(null);
      setSelectedFactorId("");
      return;
    }

    const controller = new AbortController();
    setFactorLoading(true);
    setFactorError(null);
    void fetch(`/api/upload/formal-activities/${activityId}/factor-candidates`, {
      headers: getHeaders(),
      credentials: "include",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(await responseError(response, "读取排放因子候选失败"));
        const payload = await response.json() as FactorCandidateResponse;
        setFactorBundle(payload);
        setSelectedFactorId((current) => (
          payload.factor_candidates.some((factor) => factor.factor_id === current)
            ? current
            : payload.factor_candidates[0]?.factor_id || ""
        ));
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setFactorBundle(null);
        setFactorError(error instanceof Error ? error.message : "读取排放因子候选失败");
      })
      .finally(() => {
        if (!controller.signal.aborted) setFactorLoading(false);
      });

    return () => controller.abort();
  }, [authLoading, getHeaders, isAuthenticated, selectedFormalWrite?.activity_data_id, selectedFormalWrite?.calculation_status]);

  useEffect(() => {
    const storageUrl = selected?.storageUrl;
    if (!storageUrl || authLoading || !isAuthenticated) {
      setPreviewUrl(null);
      setPreviewError(null);
      return;
    }

    const controller = new AbortController();
    let objectUrl: string | null = null;
    setPreviewUrl(null);
    setPreviewError(null);

    void fetch(storageUrl, {
      headers: getHeaders(),
      credentials: "include",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(await responseError(response, "读取原文件失败"));
        return response.blob();
      })
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setPreviewUrl(objectUrl);
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setPreviewError(error instanceof Error ? error.message : "读取原文件失败");
      });

    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [authLoading, getHeaders, isAuthenticated, selected?.id, selected?.storageUrl]);

  const updateFile = (fileId: string, patch: Partial<InboxFile>) => {
    setInboxFiles((current) => current.map((file) => (file.id === fileId ? { ...file, ...patch } : file)));
  };

  const selectFilter = (filter: InboxFilter) => {
    const nextFiles = inboxFiles.filter((file) => matchesFilter(file, filter));
    setActiveFilter(filter);
    setSelectedId((current) => (
      current && nextFiles.some((file) => file.id === current) ? current : nextFiles[0]?.id ?? null
    ));
    setConfirmResult(null);
    setReviewBundle(null);
  };

  const handleUpload = async (file: File) => {
    setOperation("upload");
    setNotice({ tone: "info", text: "正在上传文件并调用 OCR 识别..." });
    setConfirmResult(null);
    setReviewBundle(null);

    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/upload", {
        method: "POST",
        headers: getHeaders(),
        credentials: "include",
        body: form,
      });
      if (!response.ok) throw new Error(await responseError(response, "文件识别失败"));

      const payload: unknown = await response.json();
      const uploaded = toInboxFile(parseUploadFile(payload), {
        mimeType: file.type,
        sizeBytes: file.size,
        ocrStatus: "completed",
      });
      setInboxFiles((current) => [uploaded, ...current.filter((item) => item.id !== uploaded.id)]);
      setActiveFilter("all");
      setSelectedId(uploaded.id);
      setNotice({
        tone: uploaded.status === "异常" ? "warning" : "success",
        text: uploaded.status === "异常"
          ? `文件已上传，但识别服务返回异常：${uploaded.errors.join("；") || uploaded.name}`
          : `识别完成：${uploaded.name}，请核验并编辑字段后确认写入。`,
      });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "文件识别失败" });
    } finally {
      setOperation(null);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const handleFieldChange = (fileId: string, fieldKey: string, value: string) => {
    setInboxFiles((current) => current.map((file) => {
      if (file.id !== fileId) return file;
      return {
        ...file,
        status: "待确认",
        fields: file.fields.map((field) => (
          field.key === fieldKey ? { ...field, value, status: "人工修正" } : field
        )),
      };
    }));
    setConfirmResult((current) => (current?.fileId === fileId ? null : current));
    setReviewBundle((current) => (current?.fileId === fileId ? null : current));
  };

  const reUnderstand = async () => {
    if (!selected) return;
    if (!selected.rawText.trim()) {
      setNotice({ tone: "error", text: "该文件没有可供重新识别的原始文本。" });
      return;
    }

    const fileId = selected.id;
    setOperation("understand");
    setNotice({ tone: "info", text: "正在调用文档理解接口重新识别字段..." });

    try {
      const response = await fetch("/api/ai/understand", {
        method: "POST",
        headers: { ...getHeaders(), "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ text: selected.rawText }),
      });
      if (!response.ok) throw new Error(await responseError(response, "重新识别失败"));

      const data = await response.json() as UnderstandResponse;
      const confidence = understandConfidence(data.confidence);
      const recognizedFields = normalizeFields(data.fields, confidence);
      updateFile(fileId, {
        documentType: data.document_type || selected.documentType,
        confidence,
        fields: recognizedFields.length > 0 ? recognizedFields : selected.fields,
        status: "待确认",
        errors: [],
        ocrStatus: "completed",
      });
      setConfirmResult((current) => (current?.fileId === fileId ? null : current));
      setReviewBundle((current) => (current?.fileId === fileId ? null : current));
      setNotice({
        tone: "success",
        text: data.summary
          ? `重新识别完成：${data.summary}`
          : "重新识别完成，请人工核验当前字段。",
      });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "重新识别失败" });
    } finally {
      setOperation(null);
    }
  };

  const runQualityReview = async () => {
    if (!selected) return;
    const fileId = selected.id;
    const editedFields = fieldsToObject(selected.fields);
    setOperation("quality");
    setNotice({ tone: "info", text: "A-02 正在锁定候选，A-03 随后独立检查证据、单位与异常..." });
    setConfirmResult(null);
    setReviewBundle(null);

    try {
      const candidateResponse = await fetch(`/api/upload/${selected.id}/candidate`, {
        method: "POST",
        headers: { ...getHeaders(), "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ fields: editedFields }),
      });
      if (!candidateResponse.ok) {
        throw new Error(await responseError(candidateResponse, "锁定候选数据失败"));
      }
      const candidate = await candidateResponse.json() as CandidateSnapshotResponse;

      const qualityResponse = await fetch(`/api/upload/${selected.id}/quality-review`, {
        method: "POST",
        headers: { ...getHeaders(), "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          candidate_token: candidate.candidate_token,
          fields: editedFields,
        }),
      });
      if (!qualityResponse.ok) {
        throw new Error(await responseError(qualityResponse, "A-03 证据质检失败"));
      }
      const review = await qualityResponse.json() as QualityReviewResponse;
      setReviewBundle({ fileId, candidate, review });
      setNotice({
        tone: review.quality_status === "fail" ? "error" : review.quality_status === "pass_with_warnings" ? "warning" : "success",
        text: `A-03 质检${review.quality_status === "fail" ? "未通过" : "完成"}：${review.summary}`,
      });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "A-03 质检失败" });
    } finally {
      setOperation(null);
    }
  };

  const confirmWrite = async () => {
    if (!selected || !selectedReview) return;
    const fileId = selected.id;
    const editedFields = fieldsToObject(selected.fields);
    setOperation("confirm");
    setNotice({ tone: "info", text: "H-01 正在提交人工确认；系统会再次核对候选与 A-03 质检签名..." });
    setConfirmResult(null);

    try {

      const response = await fetch("/api/upload/confirm-activity", {
        method: "POST",
        headers: { ...getHeaders(), "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          candidate_token: selectedReview.candidate.candidate_token,
          quality_review_token: selectedReview.review.quality_review_token,
          file_id: selected.id,
          document_content_hash: selected.contentHash,
          filename: selected.name,
          document_type: selected.documentType,
          fields: editedFields,
          confidence: selected.confidence,
          target_dataset: "当前租户正式活动账本",
          target_boundary: "当前租户",
          note: "数据收件箱字段人工核验后写入",
        }),
      });
      if (!response.ok) throw new Error(await responseError(response, "写入失败"));

      const data = await response.json() as ConfirmResponse;
      setConfirmResult({ fileId, data });
      setDurableFormalWrite({ fileId, data: data.formal_write || null });
      setFactorSelectionNote(DEFAULT_FACTOR_SELECTION_NOTE);
      updateFile(fileId, {
        status: "已完成",
        ocrStatus: "confirmed",
        fields: selected.fields.map((field) => ({
          ...field,
          status: field.status === "异常" ? field.status : "已识别",
        })),
      });
      setActiveFilter("all");
      setSelectedId(fileId);
      setNotice({
        tone: "success",
        text: `${data.message} A-03 质检与 H-01 确认均已留痕，ActivityData ID：${data.formal_write?.activity_data_id || data.activity_record.record_id}`,
      });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "写入失败" });
    } finally {
      setOperation(null);
    }
  };

  const confirmFactor = async () => {
    if (!selected || !selectedFormalWrite || !selectedFactor) return;
    const fileId = selected.id;
    setOperation("factor");
    setNotice({
      tone: "info",
      text: "H-02 正在提交人工选择；R-01 将用确定性单位内核计算，不调用大模型做算术。",
    });

    try {
      const response = await fetch(
        `/api/upload/formal-activities/${selectedFormalWrite.activity_data_id}/confirm-factor`,
        {
          method: "POST",
          headers: { ...getHeaders(), "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            factor_id: selectedFactor.factor_id,
            factor_snapshot_sha256: selectedFactor.factor_snapshot_sha256,
            selection_note: factorSelectionNote.trim(),
          }),
        },
      );
      if (!response.ok) throw new Error(await responseError(response, "排放因子确认失败"));
      const data = await response.json() as FactorConfirmationResponse;
      setDurableFormalWrite({ fileId, data: data.formal_write });
      setConfirmResult((current) => (
        current?.fileId === fileId
          ? { fileId, data: { ...current.data, formal_write: data.formal_write } }
          : current
      ));
      setFactorBundle(null);
      setFactorError(null);
      setSelectedFactorId("");
      setNotice({
        tone: "success",
        text: `${data.message} 结果：${data.formal_write.emission_result ? exactEmissionText(data.formal_write.emission_result) : "-"} ${data.formal_write.emission_result?.unit || "tCO₂e"}。`,
      });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "排放因子确认失败" });
    } finally {
      setOperation(null);
    }
  };

  const moveSelection = (offset: number) => {
    if (selectedIndex < 0) return;
    const next = visibleFiles[selectedIndex + offset];
    if (next) {
      setSelectedId(next.id);
      setConfirmResult(null);
      setReviewBundle(null);
    }
  };

  const pendingFieldCount = selected?.fields.filter((field) => field.status === "待确认").length || 0;
  const manuallyEditedCount = selected?.fields.filter((field) => field.status === "人工修正").length || 0;
  const canRunQuality = Boolean(
    selected
    && writeSupported
    && selectedMissingFields.length === 0
    && selected.fields.length > 0
    && selected.status !== "已完成"
    && selected.status !== "识别中"
    && operation === null,
  );
  const qualityAccepted = Boolean(
    selectedReview
    && ["pass", "pass_with_warnings"].includes(selectedReview.review.quality_status),
  );
  const canConfirm = Boolean(
    selected
    && writeSupported
    && selectedMissingFields.length === 0
    && selected.fields.length > 0
    && selected.status !== "已完成"
    && selected.status !== "识别中"
    && operation === null
    && !selectedConfirm
    && qualityAccepted,
  );
  const canConfirmFactor = Boolean(
    selectedFormalWrite?.calculation_status === "pending_factor"
    && selectedFactor
    && factorSelectionNote.trim().length >= 12
    && operation === null,
  );
  const passportSearch = new URLSearchParams();
  if (selectedFormalWrite?.suggested_passport_account_id) {
    passportSearch.set("account_id", selectedFormalWrite.suggested_passport_account_id);
  }
  if (selectedFormalWrite?.emission_result?.emission_result_id) {
    passportSearch.set("emission_result_id", selectedFormalWrite.emission_result.emission_result_id);
  }
  if (selected?.id) passportSearch.set("source_file_id", selected.id);
  const passportTarget = passportSearch.size > 0 ? `/passports?${passportSearch.toString()}` : "/passports";
  return (
    <div className="mx-auto max-w-[1540px] space-y-6 pt-1">
      <header className="flex flex-col gap-5 pr-0 lg:pr-80 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <div className="mb-3 text-sm font-bold text-blue-600">受控数据收件与事实确认</div>
          <h1 className="text-3xl font-black text-slate-950">数字员工工作台</h1>
          <p className="mt-2 text-sm font-semibold text-slate-500">把原始文件变成带证据、经 A-03 质检、由 H-01 确认的正式活动数据。</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="zc-button-primary" onClick={() => inputRef.current?.click()} disabled={operation === "upload"}>
            <UploadCloud size={17} /> 上传文件
          </button>
          <Link to="/passports" className="zc-button"><ShieldCheck size={17} /> 查看工厂碳数据护照</Link>
        </div>
      </header>

      {notice && <NoticeBanner notice={notice} onClose={() => setNotice(null)} />}

      <ProductJourney
        active="data"
        states={{
          data: selectedFormalWrite || selectedConfirm || selected?.status === "已完成" ? "completed" : selectedReview?.review.quality_status === "fail" ? "warning" : "active",
          calculation: selectedFormalWrite?.calculation_status === "calculated"
            ? "completed"
            : selectedFormalWrite?.calculation_status === "pending_factor"
              ? "active"
              : "pending",
          passport: selectedFormalWrite?.emission_result ? "active" : "pending",
        }}
        note="AI 提议，H-01 确认企业事实，H-02 确认方法学因子，R-01 只做确定性计算。"
      />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[280px_1fr_340px_330px]">
        <aside className="zc-card-pad">
          <div className="mb-4 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-black">收到的文件</h2>
              <span className="text-blue-600">{counts.all}</span>
            </div>
            <button
              type="button"
              onClick={() => void loadFiles()}
              disabled={listState === "loading"}
              className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 disabled:opacity-50"
              aria-label="刷新文件列表"
              title="刷新文件列表"
            >
              <RefreshCw size={16} className={listState === "loading" ? "animate-spin" : ""} />
            </button>
          </div>

          <div className="mb-4 flex gap-4 border-b border-slate-100 text-sm font-semibold text-slate-500">
            <FilterButton active={activeFilter === "all"} onClick={() => selectFilter("all")}>全部</FilterButton>
            <FilterButton active={activeFilter === "pending"} onClick={() => selectFilter("pending")}>
              待确认 {counts.pending}
            </FilterButton>
            <FilterButton active={activeFilter === "done"} onClick={() => selectFilter("done")}>
              已完成 {counts.done}
            </FilterButton>
            <FilterButton active={activeFilter === "abnormal"} onClick={() => selectFilter("abnormal")}>
              异常 {counts.abnormal}
            </FilterButton>
          </div>

          {listState === "loading" && inboxFiles.length === 0 ? (
            <div className="flex min-h-40 flex-col items-center justify-center rounded-2xl bg-slate-50 px-4 text-center">
              <Loader2 className="animate-spin text-blue-500" size={24} />
              <p className="mt-3 text-sm font-bold text-slate-700">正在读取当前租户文件...</p>
            </div>
          ) : listState === "error" && inboxFiles.length === 0 ? (
            <ServiceError message={listError || "读取文件列表失败"} onRetry={() => void loadFiles()} />
          ) : (
            <>
              {listError && (
                <div className="mb-3 rounded-xl bg-red-50 px-3 py-2 text-xs font-bold leading-5 text-red-700">
                  {listError}
                </div>
              )}
              <div className="space-y-3">
                {visibleFiles.map((file) => (
                  <FileRow
                    key={file.id}
                    file={file}
                    active={file.id === selected?.id}
                    onClick={() => {
                      setSelectedId(file.id);
                      setConfirmResult(null);
                      setReviewBundle(null);
                    }}
                  />
                ))}
              </div>
              {visibleFiles.length === 0 && (
                <div className="flex min-h-40 flex-col items-center justify-center rounded-2xl bg-slate-50 px-4 text-center">
                  <FileText className="text-slate-300" size={28} />
                  <p className="mt-3 text-sm font-bold text-slate-700">
                    {inboxFiles.length === 0 ? "当前租户暂无文件" : "该分类暂无文件"}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    {inboxFiles.length === 0 ? "上传首个文件后会在这里显示真实识别结果。" : "可切换到其他分类查看。"}
                  </p>
                </div>
              )}
            </>
          )}

          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={operation === "upload"}
            className="mt-5 w-full rounded-2xl border border-dashed border-blue-300 bg-blue-50/40 p-5 text-center transition hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {operation === "upload" ? (
              <Loader2 className="mx-auto animate-spin text-blue-500" size={26} />
            ) : (
              <UploadCloud className="mx-auto text-blue-500" size={26} />
            )}
            <p className="mt-2 text-sm font-bold text-slate-700">点击上传文件并识别</p>
            <p className="mt-1 text-xs text-slate-500">支持带文本层 PDF、XLSX、CSV；扫描件暂不支持，单个文件不超过 10MB</p>
          </button>
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            accept=".pdf,.xlsx,.csv"
            onChange={(event) => {
              const file = event.currentTarget.files?.[0];
              if (file) void handleUpload(file);
            }}
          />
          <a
            href="/demo/electricity-q1.csv"
            download
            className="mt-3 flex w-full items-center justify-center gap-2 text-xs font-bold text-blue-600 hover:text-blue-800"
          >
            <Download size={14} /> 下载合成演示账单
          </a>
          <a
            href="/demo/carbonlab-competition-batch-v1.zip"
            download
            className="mt-2 flex w-full items-center justify-center gap-2 text-xs font-bold text-slate-600 hover:text-blue-800"
          >
            <Download size={14} /> 下载批量测试数据（12张账单）
          </a>
          <a
            href="/demo/carbonlab-competition-50-row-workbooks-v2.zip"
            download
            className="mt-2 flex w-full items-center justify-center gap-2 text-xs font-black text-emerald-700 hover:text-emerald-900"
          >
            <Download size={14} /> 下载50行明细版（12个Excel）
          </a>
        </aside>

        <main className="zc-card overflow-hidden">
          <div className="flex min-h-[69px] items-center justify-between border-b border-slate-100 px-5 py-4">
            <h2 className="min-w-0 truncate font-black text-slate-950">{selected?.name || "文件预览"}</h2>
            {selected && (
              <div className="ml-4 flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={() => moveSelection(-1)}
                  disabled={selectedIndex <= 0}
                  className="zc-button h-9 px-2 disabled:opacity-40"
                  aria-label="上一个文件"
                >
                  <ChevronLeft size={16} />
                </button>
                <span className="rounded-lg border border-slate-200 px-3 py-1 text-sm font-semibold">
                  {selectedIndex + 1} / {visibleFiles.length}
                </span>
                <button
                  type="button"
                  onClick={() => moveSelection(1)}
                  disabled={selectedIndex >= visibleFiles.length - 1}
                  className="zc-button h-9 px-2 disabled:opacity-40"
                  aria-label="下一个文件"
                >
                  <ChevronRight size={16} />
                </button>
                {previewUrl ? (
                  <a
                    href={previewUrl}
                    download={selected.name}
                    className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100"
                    aria-label="下载原文件"
                    title="下载原文件"
                  >
                    <Download size={18} />
                  </a>
                ) : (
                  <Download size={18} className="mx-2 text-slate-300" aria-label={previewError || "原文件加载中"} />
                )}
              </div>
            )}
          </div>
          <div className="flex min-h-[790px] items-start justify-center bg-slate-50 p-8">
            {selected ? (
              <DocumentPreview file={{ ...selected, storageUrl: previewUrl || undefined }} previewError={previewError} />
            ) : (
              <PanelEmpty
                loading={listState === "loading"}
                title={listState === "loading" ? "正在加载文件预览" : "请选择或上传文件"}
                body={listState === "error" ? "文件服务暂时不可用，请重试。" : "这里将显示当前租户文件的真实内容。"}
              />
            )}
          </div>
        </main>

        <section className="zc-card-pad">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-black">识别结果</h2>
            {selected && (
              <button
                type="button"
                onClick={() => setNotice({
                  tone: "info",
                  text: "当前百分比表示识别字段覆盖度，不代表事实正确率；所有候选字段都必须在写入前由人核对。",
                })}
                className="text-sm font-bold text-blue-600"
              >
                识别覆盖度说明
              </button>
            )}
          </div>

          {!selected ? (
            <PanelEmpty
              loading={listState === "loading"}
              title={listState === "loading" ? "正在加载识别结果" : "暂无识别结果"}
              body="选择文件后可在这里编辑并确认识别字段。"
            />
          ) : (
            <>
              {selected.errors.length > 0 && (
                <div className="mb-4 rounded-xl bg-red-50 px-3 py-2 text-xs font-bold leading-5 text-red-700">
                  {selected.errors.map((error) => <p key={error}>{error}</p>)}
                </div>
              )}

              {!writeSupported && (
                <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-bold leading-5 text-amber-800">
                  当前正式写入闭环仅支持电费活动数据。生产报表可先核验识别结果，再进入护照登记报告期产量；系统不会把它误写成 ActivityData。
                </div>
              )}

              {writeSupported && selectedMissingFields.length > 0 && (
                <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-bold leading-5 text-amber-800">
                  缺少必须由人工看到并确认的字段：{selectedMissingFields.join("、")}。补齐前禁止写入正式账本。
                </div>
              )}

              <div className="space-y-4">
                {selected.fields.map((field) => (
                  <Field
                    key={field.key}
                    data={field}
                    disabled={operation !== null || Boolean(selectedFormalWrite)}
                    onChange={(value) => handleFieldChange(selected.id, field.key, value)}
                  />
                ))}
              </div>

              {selected.fields.length === 0 && (
                <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-5 text-center">
                  <AlertCircle className="mx-auto text-slate-400" size={24} />
                  <p className="mt-2 text-sm font-bold text-slate-700">未识别到可编辑的结构化字段</p>
                  <p className="mt-1 text-xs leading-5 text-slate-500">如有原始文本，可尝试重新识别后再确认。</p>
                </div>
              )}

              {selectedReview && <QualityReviewCard review={selectedReview.review} />}

              <div className="mt-5 rounded-2xl bg-blue-50 p-4">
                <span className="font-bold text-slate-900">写入目标</span>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  当前租户正式活动账本，随后在护照中归集
                </p>
                {formalWriteLoading && !selectedFormalWrite && (
                  <div className="mt-3 flex items-center gap-2 text-xs font-bold text-blue-700">
                    <Loader2 size={14} className="animate-spin" /> 正在核对正式账本状态…
                  </div>
                )}
                {selectedFormalWrite && (
                  <div className="mt-3 space-y-1 text-xs font-bold text-emerald-700">
                    <p>
                      已入库 ActivityData
                      {selectedFormalWrite.activity_quantity
                        ? ` · ${selectedFormalWrite.activity_quantity} ${selectedFormalWrite.activity_unit || ""}`
                        : ""}
                    </p>
                    <p>排放源：{selectedFormalWrite.emission_source_name}</p>
                    {selectedConfirm?.confirmation.subject_sha256 && (
                      <p title={selectedConfirm.confirmation.subject_sha256}>
                        确认指纹：{selectedConfirm.confirmation.subject_sha256.slice(0, 16)}…
                      </p>
                    )}
                    {selectedFormalWrite.emission_result ? (
                      <p>
                        R-01 已计算 · {exactEmissionText(selectedFormalWrite.emission_result)} {selectedFormalWrite.emission_result.unit}
                      </p>
                    ) : (
                      <p className="text-amber-700">H-01 已完成 · 等待 H-02 人工确认排放因子</p>
                    )}
                  </div>
                )}
              </div>

              {selectedFormalWrite?.calculation_status === "pending_factor" && (
                <FactorConfirmationCard
                  bundle={factorBundle?.activity.activity_data_id === selectedFormalWrite.activity_data_id ? factorBundle : null}
                  loading={factorLoading}
                  error={factorError}
                  selectedFactorId={selectedFactorId}
                  selectionNote={factorSelectionNote}
                  disabled={operation !== null}
                  canConfirm={canConfirmFactor}
                  confirming={operation === "factor"}
                  onSelect={setSelectedFactorId}
                  onNoteChange={setFactorSelectionNote}
                  onConfirm={() => void confirmFactor()}
                />
              )}

              <button
                type="button"
                onClick={() => void runQualityReview()}
                disabled={!canRunQuality}
                className="mt-5 w-full zc-button-soft py-3 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <ClipboardCheck size={17} />
                {operation === "quality"
                  ? "A-03 正在独立质检..."
                  : !writeSupported
                    ? "该文档请在护照中登记"
                    : selectedMissingFields.length > 0
                      ? `请补齐：${selectedMissingFields.join("、")}`
                      : selectedReview
                        ? "重新运行 A-03 证据质检"
                        : "A-03 运行证据质检"}
              </button>

              <button
                type="button"
                onClick={() => void confirmWrite()}
                disabled={!canConfirm}
                className="mt-3 w-full zc-button-primary py-3 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <ShieldCheck size={17} />
                {operation === "confirm"
                  ? "H-01 正在确认并写入..."
                  : selectedFormalWrite || selectedConfirm || selected.status === "已完成"
                    ? "H-01 已确认并写入活动数据"
                    : !qualityAccepted
                      ? "须先通过 A-03 质检"
                      : "H-01 人工确认并写入正式账本"}
              </button>

              {(selectedFormalWrite?.emission_result || !writeSupported) && (
                <Link
                  to={passportTarget}
                  className="mt-3 flex w-full items-center justify-center gap-2 zc-button-soft py-3"
                >
                  {selectedFormalWrite?.emission_result ? "查看本笔碳护照草稿" : "进入装置护照登记"}
                  <ChevronRight size={16} />
                </Link>
              )}

              <button
                type="button"
                onClick={() => void reUnderstand()}
                disabled={operation !== null || !selected.rawText.trim()}
                className="mt-3 w-full zc-button disabled:opacity-60"
              >
                {operation === "understand" ? "识别中..." : "重新识别"}
              </button>
              <p className="mt-3 text-xs leading-5 text-slate-400">
                A-03 只检查证据与约束；H-01 对企业事实负责；H-02 对方法学因子负责；R-01 只执行可复算的确定性计算。这里生成的是可追溯档案草稿，不是政府证件或出口申报文书。
              </p>
            </>
          )}
        </section>

        <aside className="zc-card-pad">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-black">本单执行记录</h2>
              <p className="mt-1 text-xs text-slate-400">点击岗位查看真实 Run 与结构化执行过程</p>
            </div>
            <Link to="/agent-ops" className="text-xs font-bold text-blue-600 hover:text-blue-700">全部任务</Link>
          </div>
          {agentRunsError && <p className="mb-3 rounded-xl bg-red-50 px-3 py-2 text-xs text-red-600">{agentRunsError}</p>}
          {!selected ? (
            <PanelEmpty
              loading={listState === "loading"}
              title={listState === "loading" ? "正在读取文件状态" : "等待文件"}
              body="选择文件后会显示基于真实识别结果的核验建议。"
            />
          ) : (
            <>
              <Info
                icon={<Bot size={18} />}
                title="A-01 碳数据收件员"
                lines={[
                  "已登记文件身份、租户归属与内容哈希",
                  `文件类型：${selected.documentType}`,
                ]}
                run={latestAgentRun("A-01")}
                onOpenRun={setSelectedAgentRunId}
              />
              <Info
                icon={<Bot size={18} />}
                title="A-02 碳证据提取员"
                lines={[
                  `已返回 ${selected.fields.length} 个可编辑字段`,
                  `${pendingFieldCount} 个字段待人工确认`,
                  `${manuallyEditedCount} 个字段已人工修正`,
                ]}
                run={latestAgentRun("A-02")}
                onOpenRun={setSelectedAgentRunId}
              />
              {selected.errors.length > 0 ? (
                <Info
                  icon={<AlertTriangle size={18} />}
                  title="识别异常"
                  lines={selected.errors}
                />
              ) : (
                <Info
                  icon={<CheckCircle2 size={18} />}
                  title="A-03 碳数据质检员"
                  lines={[
                    selectedReview
                      ? `质检状态：${selectedReview.review.quality_status} · ${selectedReview.review.score} 分`
                      : "尚未运行独立证据质检",
                    selectedReview
                      ? `通过 ${selectedReview.review.counts.passed} / 提示 ${selectedReview.review.counts.warnings} / 阻断 ${selectedReview.review.counts.failed}`
                      : `OCR 状态：${ocrStatusLabel(selected.ocrStatus)}`,
                  ]}
                  run={latestAgentRun("A-03")}
                  onOpenRun={setSelectedAgentRunId}
                />
              )}
              <Info
                icon={<ShieldCheck size={18} />}
                title="H-01 企业数据确认人"
                lines={[
                  selectedFormalWrite
                    ? "企业事实已确认并写入不可静默覆盖的正式活动账本。"
                    : manuallyEditedCount > 0
                    ? "人工修正已保留；修改后必须重新质检。"
                    : "逐项对照原文件，必要时直接编辑。",
                  selectedFormalWrite
                    ? `ActivityData：${selectedFormalWrite.activity_data_id.slice(0, 12)}…`
                    : qualityAccepted
                      ? "质检门禁已打开，可以承担确认责任。"
                      : "质检未通过前，系统不会开放正式写入。",
                ]}
                run={latestAgentRun("H-01")}
                onOpenRun={setSelectedAgentRunId}
              />
              {selectedFormalWrite && (
                <Info
                  icon={<ShieldCheck size={18} />}
                  title="H-02 活动排放因子确认人"
                  lines={[
                    selectedFormalWrite.calculation_status === "calculated"
                      ? "已确认适用因子，因子快照与人工理由已写入审计链。"
                      : "待人工从兼容候选中确认因子；系统不会自动替人选择。",
                    factorBundle
                      ? `当前有 ${factorBundle.factor_candidates.length} 条合格候选。`
                      : selectedFormalWrite.calculation_status === "calculated"
                        ? `因子 ID：${selectedFormalWrite.emission_result?.factor_id?.slice(0, 12) || "已留痕"}…`
                        : "正在读取候选。",
                  ]}
                  run={latestAgentRun("H-02")}
                  onOpenRun={setSelectedAgentRunId}
                />
              )}
              {selectedFormalWrite && (
                <Info
                  icon={<CheckCircle2 size={18} />}
                  title="R-01 确定性计算引擎"
                  lines={[
                    selectedFormalWrite.emission_result
                      ? `已生成 ${exactEmissionText(selectedFormalWrite.emission_result)} ${selectedFormalWrite.emission_result.unit}。`
                      : "等待 H-02 放行后运行。",
                    "Decimal + Quantity 复算；大模型不参与算术。",
                  ]}
                  run={latestAgentRun("R-01")}
                  onOpenRun={setSelectedAgentRunId}
                />
              )}
              <p className="mt-3 text-xs text-slate-400">AI 提议不等于事实；人工确认与确定性规则共同构成正式结果</p>
            </>
          )}
        </aside>
      </div>
      <AgentRunDrawer runId={selectedAgentRunId} onClose={() => setSelectedAgentRunId(null)} />
    </div>
  );
}

function FactorConfirmationCard({
  bundle,
  loading,
  error,
  selectedFactorId,
  selectionNote,
  disabled,
  canConfirm,
  confirming,
  onSelect,
  onNoteChange,
  onConfirm,
}: {
  bundle: FactorCandidateResponse | null;
  loading: boolean;
  error: string | null;
  selectedFactorId: string;
  selectionNote: string;
  disabled: boolean;
  canConfirm: boolean;
  confirming: boolean;
  onSelect: (factorId: string) => void;
  onNoteChange: (note: string) => void;
  onConfirm: () => void;
}) {
  return (
    <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50/70 p-4">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white text-amber-600">
          <ShieldCheck size={18} />
        </span>
        <div>
          <h3 className="text-sm font-black text-slate-900">H-02 活动排放因子确认</h3>
          <p className="mt-1 text-xs font-semibold leading-5 text-slate-600">
            系统只列出年份、区域和单位兼容的候选；由人确认采用哪一条方法学依据。
          </p>
        </div>
      </div>

      {bundle && (
        <div className="mt-3 rounded-xl bg-white/80 px-3 py-2 text-xs leading-5 text-slate-600">
          {bundle.activity.facility} · {bundle.activity.quantity} {bundle.activity.unit}<br />
          {bundle.activity.period_start.slice(0, 10)}—{bundle.activity.period_end.slice(0, 10)} · {bundle.activity.grid_region}电网
        </div>
      )}

      {loading ? (
        <div className="mt-3 flex items-center gap-2 rounded-xl bg-white/80 px-3 py-4 text-xs font-bold text-blue-700">
          <Loader2 size={15} className="animate-spin" /> 正在筛选可用因子…
        </div>
      ) : error ? (
        <div className="mt-3 rounded-xl border border-red-200 bg-red-50 px-3 py-3 text-xs font-bold leading-5 text-red-700">
          {error}
        </div>
      ) : bundle && bundle.factor_candidates.length === 0 ? (
        <div className="mt-3 rounded-xl border border-amber-200 bg-white px-3 py-3 text-xs font-bold leading-5 text-amber-800">
          未找到同年份、同区域且量纲兼容的正式因子。系统不会用旧年份或错误单位代算，请先维护因子库。
        </div>
      ) : (
        <div className="mt-3 space-y-2" role="radiogroup" aria-label="选择活动排放因子">
          {bundle?.factor_candidates.map((factor) => {
            const active = factor.factor_id === selectedFactorId;
            return (
              <button
                key={factor.factor_id}
                type="button"
                role="radio"
                aria-checked={active}
                disabled={disabled}
                onClick={() => onSelect(factor.factor_id)}
                className={`w-full rounded-xl border p-3 text-left transition disabled:cursor-not-allowed disabled:opacity-60 ${active ? "border-blue-400 bg-blue-50" : "border-slate-200 bg-white hover:border-blue-200"}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-black text-slate-900">{factor.name}</p>
                    <p className="mt-1 text-[11px] leading-5 text-slate-500">
                      {factor.year} · {factor.region || "未标区域"} · {factor.value} {factor.unit}
                    </p>
                  </div>
                  <span className={`zc-pill ${factor.tenant_scope === "platform" ? "zc-pill-blue" : "zc-pill-green"}`}>
                    {factor.tenant_scope === "platform" ? "平台因子" : "企业因子"}
                  </span>
                </div>
                <div className="mt-2 flex items-center justify-between gap-2 border-t border-slate-100 pt-2 text-[11px]">
                  <span className="truncate text-slate-500">来源：{factor.source}</span>
                  <b className="shrink-0 text-blue-700">预览 {factor.preview_emissions} {factor.preview_unit}</b>
                </div>
              </button>
            );
          })}
        </div>
      )}

      {bundle && bundle.factor_candidates.length > 0 && (
        <>
          <label className="mt-3 block text-xs font-black text-slate-700" htmlFor="factor-selection-note">
            人工选择理由
          </label>
          <textarea
            id="factor-selection-note"
            value={selectionNote}
            onChange={(event) => onNoteChange(event.currentTarget.value)}
            disabled={disabled}
            rows={3}
            maxLength={1000}
            className="mt-2 w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold leading-5 text-slate-700 outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100 disabled:cursor-not-allowed disabled:opacity-60"
          />
          <div className="mt-1 flex justify-between text-[10px] font-semibold text-slate-400">
            <span>至少 12 字，随结果永久留痕</span>
            <span>{selectionNote.trim().length} / 1000</span>
          </div>
          <button
            type="button"
            onClick={onConfirm}
            disabled={!canConfirm}
            className="mt-3 w-full zc-button-primary py-3 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {confirming ? <Loader2 size={17} className="animate-spin" /> : <CheckCircle2 size={17} />}
            {confirming ? "H-02 正在确认并计算…" : "H-02 确认因子并运行 R-01"}
          </button>
        </>
      )}
      <p className="mt-3 text-[11px] font-semibold leading-5 text-slate-500">
        R-01 使用 Decimal + Quantity 单位内核，模型不参与数值运算。
      </p>
    </div>
  );
}

function NoticeBanner({ notice, onClose }: { notice: Notice; onClose: () => void }) {
  const toneClass = {
    info: "border-blue-100 bg-blue-50 text-blue-700",
    success: "border-emerald-100 bg-emerald-50 text-emerald-700",
    warning: "border-amber-100 bg-amber-50 text-amber-700",
    error: "border-red-100 bg-red-50 text-red-700",
  }[notice.tone];

  return (
    <div className={`flex items-start justify-between gap-4 rounded-2xl border px-4 py-3 text-sm font-bold ${toneClass}`}>
      <span className="leading-6">{notice.text}</span>
      <button type="button" onClick={onClose} className="shrink-0 opacity-70 hover:opacity-100" aria-label="关闭提示">
        ×
      </button>
    </div>
  );
}

function QualityReviewCard({ review }: { review: QualityReviewResponse }) {
  const blocked = review.quality_status === "fail";
  const warned = review.quality_status === "pass_with_warnings";
  return (
    <div className={`mt-5 rounded-2xl border p-4 ${blocked ? "border-red-200 bg-red-50" : warned ? "border-amber-200 bg-amber-50" : "border-emerald-200 bg-emerald-50"}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white ${blocked ? "text-red-600" : warned ? "text-amber-600" : "text-emerald-600"}`}>
            {blocked ? <AlertCircle size={18} /> : <ClipboardCheck size={18} />}
          </span>
          <div>
            <h3 className="text-sm font-black text-slate-900">A-03 独立证据质检</h3>
            <p className="mt-1 text-xs font-semibold leading-5 text-slate-600">{review.summary}</p>
          </div>
        </div>
        <span className={`zc-pill ${blocked ? "zc-pill-red" : warned ? "zc-pill-amber" : "zc-pill-green"}`}>{review.score} 分</span>
      </div>
      <div className="mt-3 max-h-48 space-y-2 overflow-y-auto pr-1">
        {review.findings.map((finding) => (
          <div key={finding.check_key} className="flex gap-2 rounded-xl bg-white/75 px-3 py-2 text-xs leading-5">
            <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${finding.result === "fail" ? "bg-red-500" : finding.result === "warning" ? "bg-amber-500" : "bg-emerald-500"}`} />
            <span><b className="text-slate-800">{finding.label}：</b><span className="text-slate-600">{finding.message}</span></span>
          </div>
        ))}
      </div>
      {review.retrievals && Object.keys(review.retrievals).length > 0 && (
        <div className="mt-3 rounded-xl border border-blue-100 bg-white/80 p-3">
          <div className="flex items-center gap-2 text-xs font-black text-blue-800">
            <Bot size={14} /> 本体约束下的字段证据检索
          </div>
          <div className="mt-2 space-y-2">
            {Object.entries(review.retrievals).map(([fieldKey, retrieval]) => (
              <div key={fieldKey} className="rounded-lg bg-slate-50 px-3 py-2 text-[11px] leading-5 text-slate-600">
                <div className="flex items-center justify-between gap-3">
                  <b className="text-slate-800">{fieldLabels[fieldKey] || fieldKey}</b>
                  <span className="font-mono text-[10px] text-slate-400">Trace {retrieval.retrieval_run_id.slice(0, 8)}</span>
                </div>
                <p className="mt-1">{retrieval.hits[0]?.excerpt || "未找到字段专属证据，转人工核对。"}</p>
              </div>
            ))}
          </div>
        </div>
      )}
      <p className="mt-3 text-[11px] font-semibold text-slate-500">质检只给出风险清单；通过后仍须 H-01 对事实负责。</p>
    </div>
  );
}

function FilterButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`whitespace-nowrap pb-3 ${active ? "border-b-2 border-blue-600 text-blue-600" : ""}`}
    >
      {children}
    </button>
  );
}

function ServiceError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-2xl border border-red-100 bg-red-50 p-4 text-center">
      <AlertCircle className="mx-auto text-red-500" size={26} />
      <p className="mt-2 text-sm font-black text-red-800">文件服务暂时不可用</p>
      <p className="mt-1 text-xs leading-5 text-red-700">{message}</p>
      <button type="button" onClick={onRetry} className="mt-3 zc-button-danger px-4 py-2">
        重新加载
      </button>
    </div>
  );
}

function PanelEmpty({ loading, title, body }: { loading?: boolean; title: string; body: string }) {
  return (
    <div className="flex min-h-48 w-full flex-col items-center justify-center px-6 text-center">
      {loading ? (
        <Loader2 className="animate-spin text-blue-500" size={28} />
      ) : (
        <FileText className="text-slate-300" size={32} />
      )}
      <p className="mt-3 text-sm font-black text-slate-700">{title}</p>
      <p className="mt-1 max-w-xs text-xs leading-5 text-slate-500">{body}</p>
    </div>
  );
}

function DocumentPreview({ file, previewError }: { file: InboxFile; previewError?: string | null }) {
  if (file.storageUrl && file.mimeType.startsWith("image/")) {
    return (
      <img
        src={file.storageUrl}
        alt={file.name}
        className="max-h-[730px] max-w-full rounded-sm bg-white object-contain shadow-xl shadow-slate-200/70"
      />
    );
  }

  if (file.storageUrl && (file.mimeType === "application/pdf" || file.name.toLowerCase().endsWith(".pdf"))) {
    return (
      <iframe
        src={file.storageUrl}
        title={file.name}
        className="h-[730px] w-full max-w-[720px] rounded-sm bg-white shadow-xl shadow-slate-200/70"
      />
    );
  }

  if (file.rawText.trim()) {
    return (
      <div className="w-full max-w-[620px] rounded-sm bg-white p-10 shadow-xl shadow-slate-200/70">
        <h3 className="mb-4 break-words text-xl font-black">{file.name}</h3>
        <pre className="whitespace-pre-wrap break-words text-sm leading-7 text-slate-700">{file.rawText}</pre>
      </div>
    );
  }

  return (
    <PanelEmpty
      title={previewError ? "原文件读取失败" : "暂无可预览内容"}
      body={previewError || (file.storageUrl ? "可通过右上角下载原文件进行核验。" : "文件服务未返回原文或可访问的存储地址。")}
    />
  );
}

function FileRow({ file, active, onClick }: { file: InboxFile; active?: boolean; onClick: () => void }) {
  const lowerName = file.name.toLowerCase();
  const Icon = file.mimeType.includes("spreadsheet") || /\.(xlsx?|csv)$/.test(lowerName)
    ? FileSpreadsheet
    : file.mimeType.startsWith("image/") || /\.(png|jpe?g)$/.test(lowerName)
      ? ImageIcon
      : FileText;
  const statusClass = file.status === "待确认" || file.status === "识别中"
    ? "zc-pill-amber"
    : file.status === "已完成"
      ? "zc-pill-green"
      : "zc-pill-red";
  const iconClass = file.color === "red"
    ? "text-red-500"
    : file.color === "green"
      ? "text-emerald-500"
      : file.color === "slate"
        ? "text-slate-400"
        : "text-blue-600";

  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-2xl border p-4 text-left ${active ? "border-blue-300 bg-blue-50" : "border-slate-100 bg-white"}`}
    >
      <div className="flex items-center gap-3">
        <Icon className={iconClass} size={25} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-black text-slate-900">{file.name}</div>
          <div className="mt-1 text-xs text-slate-500">{file.meta}</div>
        </div>
        <span className={`zc-pill ${statusClass}`}>{file.status}</span>
      </div>
    </button>
  );
}

function Field({
  data,
  disabled,
  onChange,
}: {
  data: RecognizedField;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const pending = data.status === "待确认" || data.status === "人工修正";
  const statusLabel = data.status === "人工修正" ? "待确认 / 人工修正" : data.status;

  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2 text-xs font-semibold text-slate-500">
        <span>{data.label}</span>
        <div className="flex items-center gap-2">
          <span>{data.confidence}</span>
          <span className={`zc-pill ${pending ? "zc-pill-amber" : data.status === "异常" ? "zc-pill-red" : "zc-pill-green"}`}>
            {statusLabel}
          </span>
        </div>
      </div>
      <div className="flex items-start gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5 transition focus-within:border-blue-300 focus-within:ring-2 focus-within:ring-blue-50">
        <textarea
          value={data.value}
          onChange={(event) => onChange(event.currentTarget.value)}
          disabled={disabled}
          rows={data.value.includes("\n") || data.value.length > 60 ? 3 : 1}
          className="min-h-6 min-w-0 flex-1 resize-y border-0 bg-transparent text-sm font-semibold leading-6 text-slate-800 outline-none disabled:cursor-not-allowed disabled:opacity-60"
          aria-label={`编辑${data.label}`}
        />
        <PencilLine size={15} className="mt-1 shrink-0 text-slate-400" />
      </div>
    </div>
  );
}

function Info({
  icon,
  title,
  lines,
  run,
  onOpenRun,
}: {
  icon: ReactNode;
  title: string;
  lines: string[];
  run?: AgentRun | null;
  onOpenRun?: (runId: string) => void;
}) {
  const className = `mb-4 w-full rounded-2xl bg-slate-50 p-4 text-left ${run ? "cursor-pointer border border-transparent transition hover:border-blue-200 hover:bg-blue-50/55 active:scale-[0.99]" : ""}`;
  const content = (
    <>
      <div className="mb-2 flex items-center gap-2 font-black text-slate-900">
        <span className="text-blue-600">{icon}</span>
        <span className="min-w-0 flex-1">{title}</span>
        {run && <span className={`zc-pill ${agentStatusTone(run.status)}`}>{agentStatusLabel(run.status)}</span>}
      </div>
      {lines.map((line, index) => (
        <p key={`${index}-${line}`} className="mb-1 break-words text-sm leading-6 text-slate-600">{line}</p>
      ))}
      {run && <p className="mt-2 text-xs font-bold text-blue-600">查看执行过程与 Skill 版本</p>}
    </>
  );
  if (run && onOpenRun) {
    return <button type="button" className={className} onClick={() => onOpenRun(run.run_id)}>{content}</button>;
  }
  return <div className={className}>{content}</div>;
}
