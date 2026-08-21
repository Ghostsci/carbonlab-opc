import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  AlertCircle,
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  FileSpreadsheet,
  FileText,
  ImageIcon,
  Loader2,
  PencilLine,
  RefreshCw,
  UploadCloud,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

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
};

type UnderstandResponse = {
  document_type: string;
  fields: Record<string, unknown>;
  confidence: number;
  summary: string;
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
  formal_write?: {
    activity_data_id: string;
    emission_source_id: string;
    emission_source_name: string;
    calculation_status: "calculated" | "pending_factor";
    emission_result?: {
      emission_result_id: string;
      co2_tonnes: number;
      factor_id?: string | null;
    } | null;
  };
};

type CandidateSnapshotResponse = {
  candidate_id: string;
  candidate_token: string;
  fields_sha256: string;
  subject_sha256: string;
  expires_at: string;
};

type Notice = { tone: NoticeTone; text: string };

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
  if (status === "failed" || status === "error" || errors.length > 0) return "异常";
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
  const [operation, setOperation] = useState<"upload" | "understand" | "confirm" | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [confirmResult, setConfirmResult] = useState<{ fileId: string; data: ConfirmResponse } | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

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
  const selectedMissingFields = missingElectricityFields(selected);
  const writeSupported = selected?.documentType === "electricity_bill";
  const counts = {
    all: inboxFiles.length,
    pending: inboxFiles.filter((file) => matchesFilter(file, "pending")).length,
    done: inboxFiles.filter((file) => file.status === "已完成").length,
    abnormal: inboxFiles.filter((file) => file.status === "异常").length,
  };

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
  };

  const handleUpload = async (file: File) => {
    setOperation("upload");
    setNotice({ tone: "info", text: "正在上传文件并调用 OCR 识别..." });
    setConfirmResult(null);

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

  const confirmWrite = async () => {
    if (!selected) return;
    const fileId = selected.id;
    const editedFields = fieldsToObject(selected.fields);
    setOperation("confirm");
    setNotice({ tone: "info", text: "正在锁定本次人工确认内容，然后写入正式活动账本..." });
    setConfirmResult(null);

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

      const response = await fetch("/api/upload/confirm-activity", {
        method: "POST",
        headers: { ...getHeaders(), "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          candidate_token: candidate.candidate_token,
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
        text: `${data.message} 已锁定本次确认内容，记录 ID：${data.activity_record.record_id}`,
      });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "写入失败" });
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
    }
  };

  const pendingFieldCount = selected?.fields.filter((field) => field.status === "待确认").length || 0;
  const manuallyEditedCount = selected?.fields.filter((field) => field.status === "人工修正").length || 0;
  const canConfirm = Boolean(
    selected
    && writeSupported
    && selectedMissingFields.length === 0
    && selected.fields.length > 0
    && selected.status !== "已完成"
    && selected.status !== "识别中"
    && operation === null
    && !selectedConfirm,
  );

  return (
    <div className="mx-auto max-w-[1540px] space-y-6 pt-1">
      <header className="pr-0 lg:pr-80">
        <h1 className="text-3xl font-black text-slate-950">数据收件箱 / 文件识别与字段确认</h1>
        <p className="mt-2 text-sm font-semibold text-slate-500">
          读取当前登录租户的文件，核验关键信息并写入正式活动数据
        </p>
      </header>

      {notice && <NoticeBanner notice={notice} onClose={() => setNotice(null)} />}

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
                    disabled={operation !== null}
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

              <div className="mt-5 rounded-2xl bg-blue-50 p-4">
                <span className="font-bold text-slate-900">写入目标</span>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  当前租户正式活动账本，随后在护照中归集
                </p>
                {selectedConfirm && (
                  <div className="mt-3 space-y-1 text-xs font-bold text-emerald-700">
                    <p>
                      已入库 ActivityData
                      {selectedConfirm.activity_record.quantity !== null
                        && selectedConfirm.activity_record.quantity !== undefined
                        ? ` · ${selectedConfirm.activity_record.quantity.toLocaleString()} ${selectedConfirm.activity_record.unit || ""}`
                        : ""}
                    </p>
                    <p>排放源：{selectedConfirm.formal_write?.emission_source_name || selectedConfirm.step_key}</p>
                    <p title={selectedConfirm.confirmation.subject_sha256}>
                      确认指纹：{selectedConfirm.confirmation.subject_sha256.slice(0, 16)}…
                    </p>
                    {selectedConfirm.formal_write?.emission_result ? (
                      <p>
                        已计算 · {selectedConfirm.formal_write.emission_result.co2_tonnes.toLocaleString()} tCO₂e
                      </p>
                    ) : (
                      <p className="text-amber-700">待匹配排放因子后计算结果</p>
                    )}
                  </div>
                )}
              </div>

              <button
                type="button"
                onClick={() => void confirmWrite()}
                disabled={!canConfirm}
                className="mt-5 w-full zc-button-primary py-3 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {operation === "confirm"
                  ? "写入中..."
                  : !writeSupported
                    ? "该文档请在护照中登记"
                    : selectedMissingFields.length > 0
                      ? `请补齐：${selectedMissingFields.join("、")}`
                  : selectedConfirm || selected.status === "已完成"
                    ? "已确认并写入活动数据"
                    : "锁定候选并确认写入"}
              </button>

              {(selectedConfirm || selected.status === "已完成" || !writeSupported) && (
                <Link
                  to={selectedConfirm?.formal_write?.emission_result?.emission_result_id
                    ? `/passports?emission_result_id=${encodeURIComponent(selectedConfirm.formal_write.emission_result.emission_result_id)}&source_file_id=${encodeURIComponent(selected.id)}`
                    : "/passports"}
                  className="mt-3 flex w-full items-center justify-center gap-2 zc-button-soft py-3"
                >
                  进入护照归集
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
                确认时会提交当前编辑值；活动数据写入租户账本后，再由护照完成装置与产品归集。
              </p>
            </>
          )}
        </section>

        <aside className="zc-card-pad">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-black">AI 助理</h2>
          </div>
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
                title="识别说明"
                lines={[
                  `已返回 ${selected.fields.length} 个可编辑字段`,
                  `${pendingFieldCount} 个字段待人工确认`,
                  `${manuallyEditedCount} 个字段已人工修正`,
                  `文档类型：${selected.documentType}`,
                ]}
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
                  title="处理状态"
                  lines={[
                    `OCR 状态：${ocrStatusLabel(selected.ocrStatus)}`,
                    `识别字段覆盖度：${Math.round(selected.confidence)}%`,
                  ]}
                />
              )}
              <Info
                icon={<FileText size={18} />}
                title="操作建议"
                lines={[
                  manuallyEditedCount > 0
                    ? "人工修正已保留，确认时将提交当前编辑值。"
                    : "请逐项核对识别字段，必要时直接编辑。",
                  "确认写入后，可进入护照完成装置、工序与产品归集。",
                ]}
              />
              <p className="mt-3 text-xs text-slate-400">AI 识别内容仅供核验，请以原始文件为准</p>
            </>
          )}
        </aside>
      </div>
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

function Info({ icon, title, lines }: { icon: ReactNode; title: string; lines: string[] }) {
  return (
    <div className="mb-4 rounded-2xl bg-slate-50 p-4">
      <div className="mb-2 flex items-center gap-2 font-black text-slate-900">
        <span className="text-blue-600">{icon}</span>
        {title}
      </div>
      {lines.map((line, index) => (
        <p key={`${index}-${line}`} className="mb-1 break-words text-sm leading-6 text-slate-600">{line}</p>
      ))}
    </div>
  );
}
