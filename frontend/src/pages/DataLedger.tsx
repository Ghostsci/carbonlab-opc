import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  BookOpenCheck,
  Calculator,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Database,
  Download,
  FileCheck2,
  FileSpreadsheet,
  Fingerprint,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";

import ProductJourney from "../components/ProductJourney";
import { useAuth } from "../contexts/AuthContext";
import {
  downloadEvidence,
  exportDataLedger,
  fetchDataLedger,
  fetchDataLedgerDetail,
  type DataLedgerDetail,
  type DataLedgerFilters,
  type DataLedgerItem,
  type DataLedgerResponse,
} from "../utils/dataLedger";


type PageState = "loading" | "ready" | "error";
type StatusFilter = "all" | "pending_factor" | "calculated";

const EMPTY_RESPONSE: DataLedgerResponse = {
  summary: { total: 0, calculated: 0, pending_factor: 0, source_documents: 0 },
  items: [],
  pagination: { page: 1, page_size: 20, total: 0, pages: 0 },
};

const CATEGORY_LABELS: Record<string, string> = {
  purchased_electricity: "外购电力",
  purchased_heat: "外购热力",
  stationary_combustion: "固定燃烧",
  mobile_combustion: "移动燃烧",
};

const FIELD_LABELS: Record<string, string> = {
  electricity_kwh: "外购电量",
  period: "统计期间",
  facility: "所属工厂",
  methodology_ref: "方法学依据",
};

function dateTime(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function shortHash(value?: string | null, length = 12): string {
  if (!value) return "-";
  return value.length > length ? `${value.slice(0, length)}…` : value;
}

function sourceLocatorLabel(locator?: Record<string, unknown> | null): string {
  if (!locator) return "原件中未记录定位坐标";
  const sheet = typeof locator.sheet === "string" ? locator.sheet : null;
  const cell = typeof locator.cell === "string" ? locator.cell : null;
  if (sheet || cell) return `${sheet ? `工作表「${sheet}」` : ""}${sheet && cell ? " · " : ""}${cell || ""}`;
  const lineStart = typeof locator.text_line_start === "number" ? locator.text_line_start : null;
  const lineEnd = typeof locator.text_line_end === "number" ? locator.text_line_end : lineStart;
  if (lineStart) return `文本第 ${lineStart}${lineEnd && lineEnd !== lineStart ? `–${lineEnd}` : ""} 行`;
  return "原件定位信息已保留";
}

export default function DataLedger() {
  const { getHeaders, isAuthenticated, isLoading: authLoading } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [response, setResponse] = useState<DataLedgerResponse>(EMPTY_RESPONSE);
  const [state, setState] = useState<PageState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [searchInput, setSearchInput] = useState(searchParams.get("q") || "");
  const [appliedSearch, setAppliedSearch] = useState(searchParams.get("q") || "");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>((searchParams.get("status") as StatusFilter) || "all");
  const [category, setCategory] = useState(searchParams.get("category") || "");
  const [page, setPage] = useState(Number(searchParams.get("page") || "1"));
  const [selectedId, setSelectedId] = useState<string | null>(searchParams.get("activity_id"));
  const [detail, setDetail] = useState<DataLedgerDetail | null>(null);
  const [detailState, setDetailState] = useState<PageState>(selectedId ? "loading" : "ready");
  const [detailError, setDetailError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const filters = useMemo<DataLedgerFilters>(() => ({
    q: appliedSearch,
    status: statusFilter,
    category,
    page,
    pageSize: 20,
  }), [appliedSearch, category, page, statusFilter]);

  const load = useCallback(async (quiet = false, signal?: AbortSignal) => {
    if (quiet) setRefreshing(true);
    else setState("loading");
    setError(null);
    try {
      const payload = await fetchDataLedger(getHeaders, filters, signal);
      setResponse(payload);
      setState("ready");
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setError(reason instanceof Error ? reason.message : "标准化数据台账读取失败");
      setState("error");
    } finally {
      setRefreshing(false);
    }
  }, [filters, getHeaders]);

  useEffect(() => {
    if (authLoading || !isAuthenticated) return;
    const controller = new AbortController();
    void load(false, controller.signal);
    return () => controller.abort();
  }, [authLoading, isAuthenticated, load]);

  useEffect(() => {
    if (!selectedId || authLoading || !isAuthenticated) {
      setDetail(null);
      return;
    }
    const controller = new AbortController();
    setDetailState("loading");
    setDetailError(null);
    void fetchDataLedgerDetail(getHeaders, selectedId, controller.signal)
      .then((payload) => {
        setDetail(payload);
        setDetailState("ready");
      })
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setDetailError(reason instanceof Error ? reason.message : "标准化记录详情读取失败");
        setDetailState("error");
      });
    return () => controller.abort();
  }, [authLoading, getHeaders, isAuthenticated, selectedId]);

  const updateUrl = (next: { activityId?: string | null; currentPage?: number } = {}) => {
    const params = new URLSearchParams();
    if (appliedSearch) params.set("q", appliedSearch);
    if (statusFilter !== "all") params.set("status", statusFilter);
    if (category) params.set("category", category);
    const nextPage = next.currentPage ?? page;
    if (nextPage > 1) params.set("page", String(nextPage));
    const activityId = next.activityId === undefined ? selectedId : next.activityId;
    if (activityId) params.set("activity_id", activityId);
    setSearchParams(params, { replace: true });
  };

  const selectRecord = (item: DataLedgerItem) => {
    setSelectedId(item.activity_data_id);
    updateUrl({ activityId: item.activity_data_id });
  };

  const closeDetail = () => {
    setSelectedId(null);
    setDetail(null);
    updateUrl({ activityId: null });
  };

  const applySearch = () => {
    setPage(1);
    setAppliedSearch(searchInput.trim());
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      await exportDataLedger(getHeaders, filters);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "导出标准化数据台账失败");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="mx-auto max-w-[1680px] space-y-5 pt-12 lg:pt-0">
      <header className="flex flex-col gap-4 pr-0 lg:pr-80 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm font-bold text-blue-600">
            <BookOpenCheck size={17} /> 人工确认后的企业数据资产
          </div>
          <h1 className="text-3xl font-black tracking-tight text-slate-950">标准化数据台账</h1>
          <p className="mt-2 max-w-3xl text-sm font-semibold leading-6 text-slate-500">
            这里不是原始文件夹，而是把不同票据统一成同一种碳数据语言后，已经由 H-01 确认并可重复用于核算的正式记录。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to="/upload" className="zc-button"><FileCheck2 size={17} /> 上传并标准化</Link>
          <button type="button" className="zc-button-primary" onClick={() => void handleExport()} disabled={exporting || response.summary.total === 0}>
            {exporting ? <Loader2 size={17} className="animate-spin" /> : <Download size={17} />}
            {exporting ? "正在导出" : "导出 Excel 台账"}
          </button>
        </div>
      </header>

      <ProductJourney
        active="data"
        states={{
          data: response.summary.total > 0 ? "completed" : "active",
          calculation:
            response.summary.total === 0
              ? "pending"
              : response.summary.pending_factor > 0
                ? "active"
                : "completed",
          passport: response.summary.calculated > 0 ? "active" : "pending",
        }}
        note="标准化台账是数据收集与正式核算之间的交接层：原件保留、字段统一、人工确认、版本可追溯。"
      />

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard icon={<Database size={21} />} label="正式活动数据" value={response.summary.total} description="已通过 H-01 确认并写入账本" tone="blue" />
        <SummaryCard icon={<FileSpreadsheet size={21} />} label="关联原始文件" value={response.summary.source_documents} description="每条记录可回到原始证据" tone="purple" />
        <SummaryCard icon={<Calculator size={21} />} label="等待方法确认" value={response.summary.pending_factor} description="下一步由 H-02 选择适用因子" tone="amber" />
        <SummaryCard icon={<CheckCircle2 size={21} />} label="已完成核算" value={response.summary.calculated} description="已生成确定性排放结果" tone="green" />
      </section>

      <section className="zc-card overflow-hidden">
        <div className="border-b border-slate-200 p-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-lg font-black text-slate-950">可复用的标准记录</h2>
              <p className="mt-1 text-sm text-slate-500">点开任意一条，可查看“原文件 → 标准字段 → 人工确认 → 正式账本”的完整来路。</p>
            </div>
            <button type="button" className="zc-button" onClick={() => void load(true)} disabled={refreshing}>
              <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} /> {refreshing ? "刷新中" : "刷新"}
            </button>
          </div>
          <div className="mt-4 grid gap-2 lg:grid-cols-[minmax(260px,1fr)_190px_190px_auto]">
            <label className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
              <input
                value={searchInput}
                onChange={(event) => setSearchInput(event.currentTarget.value)}
                onKeyDown={(event) => { if (event.key === "Enter") applySearch(); }}
                className="zc-input w-full pl-9"
                placeholder="搜索工厂、文件名或活动来源"
              />
            </label>
            <select value={statusFilter} onChange={(event) => { setStatusFilter(event.currentTarget.value as StatusFilter); setPage(1); }} className="zc-input">
              <option value="all">全部核算状态</option>
              <option value="pending_factor">等待方法确认</option>
              <option value="calculated">已完成核算</option>
            </select>
            <select value={category} onChange={(event) => { setCategory(event.currentTarget.value); setPage(1); }} className="zc-input">
              <option value="">全部活动类型</option>
              <option value="purchased_electricity">外购电力</option>
              <option value="purchased_heat">外购热力</option>
              <option value="stationary_combustion">固定燃烧</option>
              <option value="mobile_combustion">移动燃烧</option>
            </select>
            <button type="button" className="zc-button-primary" onClick={applySearch}><Search size={16} /> 查询</button>
          </div>
        </div>

        {state === "loading" && (
          <div className="flex min-h-[420px] items-center justify-center text-sm font-semibold text-slate-500">
            <Loader2 className="mr-2 animate-spin text-blue-600" size={20} /> 正在读取正式账本...
          </div>
        )}

        {state === "error" && (
          <div className="flex min-h-[360px] flex-col items-center justify-center p-8 text-center">
            <AlertTriangle size={30} className="text-red-500" />
            <h3 className="mt-3 font-black text-slate-950">标准化数据暂时无法读取</h3>
            <p className="mt-2 text-sm text-slate-500">{error}</p>
            <button type="button" className="zc-button mt-5" onClick={() => void load()}>重新加载</button>
          </div>
        )}

        {state === "ready" && response.items.length === 0 && (
          <div className="flex min-h-[420px] flex-col items-center justify-center p-8 text-center">
            <Database size={38} className="text-blue-500" />
            <h3 className="mt-4 text-xl font-black text-slate-950">还没有符合条件的正式记录</h3>
            <p className="mt-2 max-w-xl text-sm leading-6 text-slate-500">先上传电费账单等原始资料，完成 A-03 证据质检和 H-01 人工确认，数据才会出现在这里。</p>
            <Link to="/upload" className="zc-button-primary mt-5"><ArrowRight size={17} /> 去上传并确认</Link>
          </div>
        )}

        {state === "ready" && response.items.length > 0 && (
          <>
            <div className="overflow-x-auto">
              <table className="zc-table min-w-[1120px]">
                <thead>
                  <tr>
                    <th>期间与工厂</th>
                    <th>标准活动数据</th>
                    <th>原始证据</th>
                    <th>A-03 质检</th>
                    <th>核算状态</th>
                    <th>确认与版本</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {response.items.map((item) => (
                    <tr key={item.activity_data_id} onClick={() => selectRecord(item)} className="cursor-pointer">
                      <td>
                        <p className="font-black text-slate-900">{item.period.label}</p>
                        <p className="mt-1 text-xs text-slate-500">{item.facility.name} · {item.facility.grid_region}</p>
                      </td>
                      <td>
                        <p className="font-black text-slate-900">{Number(item.activity.quantity).toLocaleString("zh-CN")} {item.activity.unit}</p>
                        <p className="mt-1 text-xs text-slate-500">{CATEGORY_LABELS[item.emission_source.category] || item.emission_source.category}</p>
                      </td>
                      <td>
                        <p className="max-w-[220px] truncate font-semibold text-slate-700">{item.source_document?.filename || "无关联文件"}</p>
                        <p className="mt-1 font-mono text-[10px] text-slate-400">{shortHash(item.source_document?.content_hash)}</p>
                      </td>
                      <td>
                        <span className={`zc-pill ${item.quality.status === "pass" ? "zc-pill-green" : item.quality.status === "pass_with_warnings" ? "zc-pill-amber" : "zc-pill-slate"}`}>
                          {item.quality.score == null ? "历史记录未关联评分" : `${item.quality.score} 分 · 已处置`}
                        </span>
                        <p className="mt-1 text-[10px] text-slate-400">自动检查覆盖得分</p>
                      </td>
                      <td>
                        {item.calculation_status === "calculated" ? (
                          <div>
                            <span className="zc-pill zc-pill-green"><CheckCircle2 size={12} /> 已核算</span>
                            <p className="mt-1 text-xs font-bold text-emerald-700">{item.emission_result?.co2_tonnes} {item.emission_result?.unit}</p>
                          </div>
                        ) : (
                          <span className="zc-pill zc-pill-amber">等待 H-02 选因子</span>
                        )}
                      </td>
                      <td>
                        <p className="text-xs font-bold text-slate-700">v{item.confirmation.version} · H-01 已确认</p>
                        <p className="mt-1 text-[10px] text-slate-400">{dateTime(item.confirmation.confirmed_at)}</p>
                      </td>
                      <td><button type="button" className="text-sm font-black text-blue-600">查看来路 →</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-5 py-4 text-sm text-slate-500">
              <span>共 {response.pagination.total} 条正式记录 · 第 {response.pagination.page} / {Math.max(1, response.pagination.pages)} 页</span>
              <div className="flex gap-2">
                <button type="button" className="zc-button h-9 px-3" disabled={page <= 1} onClick={() => { const next = page - 1; setPage(next); updateUrl({ currentPage: next }); }}><ChevronLeft size={16} /> 上一页</button>
                <button type="button" className="zc-button h-9 px-3" disabled={page >= response.pagination.pages} onClick={() => { const next = page + 1; setPage(next); updateUrl({ currentPage: next }); }}>下一页 <ChevronRight size={16} /></button>
              </div>
            </div>
          </>
        )}
      </section>

      {selectedId && (
        <DetailDrawer
          detail={detail}
          state={detailState}
          error={detailError}
          onClose={closeDetail}
          onDownload={async () => {
            if (!detail?.source_document) return;
            await downloadEvidence(getHeaders, detail.source_document.download_url, detail.source_document.filename);
          }}
        />
      )}
    </div>
  );
}

function SummaryCard({ icon, label, value, description, tone }: { icon: React.ReactNode; label: string; value: number; description: string; tone: "blue" | "purple" | "amber" | "green" }) {
  const colors = {
    blue: "bg-blue-50 text-blue-600",
    purple: "bg-violet-50 text-violet-600",
    amber: "bg-amber-50 text-amber-600",
    green: "bg-emerald-50 text-emerald-600",
  }[tone];
  return (
    <article className="zc-card-pad flex items-start gap-4">
      <span className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl ${colors}`}>{icon}</span>
      <div>
        <p className="text-xs font-bold text-slate-500">{label}</p>
        <p className="mt-1 text-2xl font-black text-slate-950">{value}</p>
        <p className="mt-1 text-xs leading-5 text-slate-400">{description}</p>
      </div>
    </article>
  );
}

function DetailDrawer({
  detail,
  state,
  error,
  onClose,
  onDownload,
}: {
  detail: DataLedgerDetail | null;
  state: PageState;
  error: string | null;
  onClose: () => void;
  onDownload: () => Promise<void>;
}) {
  return (
    <div className="fixed inset-0 z-[80] flex justify-end bg-slate-950/28 backdrop-blur-[2px]" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}>
      <aside className="h-full w-full max-w-[760px] overflow-y-auto bg-[#f8faff] shadow-2xl">
        <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-slate-200 bg-white/95 px-6 py-5 backdrop-blur">
          <div>
            <p className="text-xs font-black text-blue-600">标准化记录详情</p>
            <h2 className="mt-1 text-xl font-black text-slate-950">一条数据从哪里来、经过谁、去了哪里</h2>
          </div>
          <button type="button" onClick={onClose} className="rounded-xl p-2 text-slate-500 hover:bg-slate-100" aria-label="关闭详情"><X size={20} /></button>
        </div>

        {state === "loading" && <div className="flex min-h-[560px] items-center justify-center text-sm font-semibold text-slate-500"><Loader2 className="mr-2 animate-spin text-blue-600" size={20} /> 正在还原数据来路...</div>}
        {state === "error" && <div className="p-8 text-center"><AlertTriangle className="mx-auto text-red-500" size={30} /><p className="mt-3 font-black text-slate-900">详情读取失败</p><p className="mt-2 text-sm text-slate-500">{error}</p></div>}

        {state === "ready" && detail && (
          <div className="space-y-5 p-6">
            <section className="rounded-2xl border border-blue-200 bg-gradient-to-br from-blue-50 to-white p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="zc-pill zc-pill-green"><ShieldCheck size={13} /> 正式账本记录</span>
                    <span className="zc-pill zc-pill-blue">v{detail.formal_record.version}</span>
                  </div>
                  <h3 className="mt-3 text-2xl font-black text-slate-950">{Number(detail.activity.quantity).toLocaleString("zh-CN")} {detail.activity.unit}</h3>
                  <p className="mt-1 text-sm font-semibold text-slate-500">{detail.period.label} · {detail.facility.name} · {CATEGORY_LABELS[detail.emission_source.category] || detail.emission_source.category}</p>
                </div>
                <span className={`zc-pill ${detail.calculation_status === "calculated" ? "zc-pill-green" : "zc-pill-amber"}`}>
                  {detail.calculation_status === "calculated" ? "已完成核算" : "等待 H-02 方法确认"}
                </span>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <TraceStep number="1" title="原始证据" text={detail.source_document?.filename || "无关联文件"} tone="slate" />
                <TraceStep number="2" title="AI 标准化" text={`${detail.standardized_fields.filter((field) => field.status === "formal").length} 个字段映射到统一语义`} tone="blue" />
                <TraceStep number="3" title="人工确认" text={`H-01 于 ${dateTime(detail.human_confirmation.confirmed_at)} 确认`} tone="amber" />
                <TraceStep number="4" title="正式入库" text={`ActivityData v${detail.formal_record.version}，不可原地修改`} tone="green" />
              </div>
            </section>

            <section className="zc-card-pad">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="font-black text-slate-950">标准字段与原件位置</h3>
                  <p className="mt-1 text-xs text-slate-500">客户看到的是统一字段；核查时仍可定位到原文件中的具体单元格或文本行。</p>
                </div>
                {detail.source_document && <button type="button" className="zc-button h-9 px-3" onClick={() => void onDownload()}><Download size={15} /> 下载原件</button>}
              </div>
              <div className="mt-4 space-y-3">
                {detail.standardized_fields.filter((field) => field.status === "formal").map((field) => (
                  <article key={field.canonical_key} className="rounded-xl border border-slate-200 bg-white p-4">
                    <div className="grid items-center gap-3 sm:grid-cols-[1fr_auto_1fr]">
                      <div>
                        <p className="text-[10px] font-black text-slate-400">原始字段</p>
                        <p className="mt-1 text-sm font-black text-slate-900">{field.raw_field || "-"}</p>
                        <p className="mt-1 truncate text-xs text-slate-500">{String(field.raw_value ?? "-")}</p>
                      </div>
                      <ArrowRight className="hidden text-blue-400 sm:block" size={18} />
                      <div className="rounded-xl bg-blue-50 px-3 py-2.5">
                        <p className="text-[10px] font-black text-blue-500">统一标准字段</p>
                        <p className="mt-1 text-sm font-black text-blue-950">{FIELD_LABELS[field.canonical_key] || field.canonical_key}</p>
                        <p className="mt-1 font-mono text-[10px] text-blue-600">{field.formal_destination}</p>
                      </div>
                    </div>
                    <p className="mt-3 border-t border-slate-100 pt-3 text-xs font-semibold text-slate-500">原件位置：{sourceLocatorLabel(field.source_locator)}</p>
                  </article>
                ))}
              </div>
            </section>

            <section className="grid gap-4 sm:grid-cols-2">
              <article className="zc-card-pad">
                <h3 className="font-black text-slate-950">A-03 证据质检</h3>
                <div className="mt-3 flex items-end gap-2"><span className="text-3xl font-black text-slate-950">{detail.quality_review.score ?? "-"}</span><span className="mb-1 text-xs font-bold text-slate-400">/ 100</span></div>
                <p className="mt-1 text-xs font-semibold text-slate-500">{detail.quality_review.score_label}，不等于事实准确率</p>
                {detail.quality_review.score == null && detail.quality_review.status === "pass" ? (
                  <span className="zc-pill zc-pill-slate mt-3">历史质检门禁已通过，未保存数值评分</span>
                ) : detail.quality_review.warnings_resolved === true ? (
                  <span className="zc-pill zc-pill-green mt-3"><CheckCircle2 size={12} /> 提示已人工处置</span>
                ) : detail.quality_review.warnings_resolved === false ? (
                  <span className="zc-pill zc-pill-amber mt-3"><AlertTriangle size={12} /> 仍待人工处置</span>
                ) : (
                  <span className="zc-pill zc-pill-slate mt-3">历史记录未关联质检快照</span>
                )}
              </article>
              <article className="zc-card-pad">
                <h3 className="font-black text-slate-950">核算交接状态</h3>
                {detail.emission_result ? (
                  <><p className="mt-3 text-2xl font-black text-emerald-700">{detail.emission_result.co2_tonnes} {detail.emission_result.unit}</p><p className="mt-2 text-xs text-slate-500">已绑定人工确认的因子并由 R-01 确定性计算</p></>
                ) : (
                  <><p className="mt-3 text-lg font-black text-amber-700">等待 H-02 选择适用因子</p><p className="mt-2 text-xs leading-5 text-slate-500">企业事实已经入库，但方法学输入尚未由责任人签字。</p></>
                )}
                <Link to="/calculations" className="zc-button-soft mt-4 w-full"><Calculator size={15} /> 进入核算工作台</Link>
              </article>
            </section>

            <section className="zc-card-pad">
              <h3 className="font-black text-slate-950">版本与防篡改信息</h3>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <Meta label="本体版本" value={detail.ontology.version} />
                <Meta label="正式记录 ID" value={detail.activity_data_id} />
                <Meta label="正式记录哈希" value={detail.formal_record.content_hash} />
                <Meta label="原文件哈希" value={detail.source_document?.content_hash || "-"} />
              </div>
              <details className="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                <summary className="cursor-pointer text-sm font-black text-slate-700">查看版本历史（{detail.version_history.length}）</summary>
                <div className="mt-3 space-y-2 border-t border-slate-200 pt-3">
                  {detail.version_history.map((version) => (
                    <div key={version.activity_data_id} className="flex items-start justify-between gap-3 rounded-lg bg-white px-3 py-2 text-xs">
                      <div><b className="text-slate-800">v{version.version} · {version.quantity} {version.unit}</b><p className="mt-1 font-mono text-[10px] text-slate-400">{shortHash(version.content_hash, 18)}</p></div>
                      <span className={`zc-pill ${version.is_current ? "zc-pill-green" : "zc-pill-slate"}`}>{version.is_current ? "当前版本" : "历史版本"}</span>
                    </div>
                  ))}
                </div>
              </details>
            </section>

            <div className="grid gap-3 sm:grid-cols-2">
              <Link to="/upload" className="zc-button"><FileCheck2 size={16} /> 返回原始资料工作台</Link>
              <Link to="/passports" className="zc-button-primary"><Fingerprint size={16} /> 查看工厂碳数据护照</Link>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

function TraceStep({ number, title, text, tone }: { number: string; title: string; text: string; tone: "slate" | "blue" | "amber" | "green" }) {
  const color = {
    slate: "bg-slate-100 text-slate-600",
    blue: "bg-blue-100 text-blue-700",
    amber: "bg-amber-100 text-amber-700",
    green: "bg-emerald-100 text-emerald-700",
  }[tone];
  return <div className="rounded-xl border border-white/80 bg-white/80 p-3"><div className="flex items-start gap-3"><span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-black ${color}`}>{number}</span><div><p className="text-xs font-black text-slate-800">{title}</p><p className="mt-1 text-[11px] leading-4 text-slate-500">{text}</p></div></div></div>;
}

function Meta({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl bg-slate-50 px-3 py-2.5"><p className="text-[10px] font-black text-slate-400">{label}</p><p className="mt-1 break-all font-mono text-[11px] font-semibold text-slate-700">{value}</p></div>;
}
