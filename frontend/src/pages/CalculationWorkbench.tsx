import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  BadgeCheck,
  BookOpenCheck,
  Calculator,
  Check,
  ChevronDown,
  CircleAlert,
  Database,
  Eye,
  FileCheck2,
  Fingerprint,
  Loader2,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";
import ProductJourney from "../components/ProductJourney";
import { useAuth } from "../contexts/AuthContext";
import {
  calculateSEE,
  fetchEmissionCandidates,
  fetchPassport,
  fetchPassports,
  fetchRules,
  registerRule,
  searchMethodologyCandidates,
  type EmissionCandidate,
  type MethodologySearchResponse,
  type PassportDetail,
  type RuleRecord,
} from "../utils/passports";

const DEFAULT_PERIOD = { start: "2026-01-01", end: "2026-03-31" };

export default function CalculationWorkbench() {
  const { getHeaders } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedAccountId = searchParams.get("account_id");
  const [passports, setPassports] = useState<PassportDetail[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(requestedAccountId);
  const [detail, setDetail] = useState<PassportDetail | null>(null);
  const [candidates, setCandidates] = useState<EmissionCandidate[]>([]);
  const [rules, setRules] = useState<RuleRecord[]>([]);
  const [period, setPeriod] = useState(DEFAULT_PERIOD);
  const [methodologySearch, setMethodologySearch] = useState<MethodologySearchResponse | null>(null);
  const [selectedMethodologyRef, setSelectedMethodologyRef] = useState<string | null>(null);
  const [approvedMethodologyRef, setApprovedMethodologyRef] = useState<string | null>(null);
  const [approvalNote, setApprovalNote] = useState("");
  const [ruleOpen, setRuleOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [listLoaded, setListLoaded] = useState(false);

  const loadList = useCallback(async () => {
    const items = await fetchPassports(getHeaders());
    setPassports(items);
    setSelectedId((current) => {
      const preferred = requestedAccountId && items.some((item) => item.account.id === requestedAccountId)
        ? requestedAccountId
        : current && items.some((item) => item.account.id === current)
          ? current
          : items[0]?.account.id || null;
      return preferred;
    });
  }, [getHeaders, requestedAccountId]);

  const loadContext = useCallback(async () => {
    if (!selectedId) {
      setDetail(null);
      setCandidates([]);
      return;
    }
    const headers = getHeaders();
    const [passport, emissionCandidates, availableRules] = await Promise.all([
      fetchPassport(selectedId, period.start, period.end, headers),
      fetchEmissionCandidates(selectedId, period.start, period.end, headers),
      fetchRules(headers),
    ]);
    setDetail(passport);
    setCandidates(emissionCandidates);
    setRules(availableRules);
  }, [getHeaders, period.end, period.start, selectedId]);

  useEffect(() => {
    void loadList()
      .catch((err: Error) => setError(err.message))
      .finally(() => setListLoaded(true));
  }, [loadList]);

  useEffect(() => {
    void loadContext().catch((err: Error) => setError(err.message));
  }, [loadContext]);

  useEffect(() => {
    setMethodologySearch(null);
    setSelectedMethodologyRef(null);
    setApprovedMethodologyRef(null);
    setApprovalNote("");
  }, [selectedId, period.start, period.end]);

  useEffect(() => {
    if (!selectedId || selectedId === requestedAccountId) return;
    const next = new URLSearchParams(searchParams);
    next.set("account_id", selectedId);
    setSearchParams(next, { replace: true });
  }, [requestedAccountId, searchParams, selectedId, setSearchParams]);

  const refresh = useCallback(async () => {
    await Promise.all([loadList(), loadContext()]);
  }, [loadContext, loadList]);

  const runMethodologySearch = async () => {
    if (!detail) return;
    setBusy("search");
    setError(null);
    setNotice(null);
    try {
      const result = await searchMethodologyCandidates(detail.account.id, period.start, period.end, getHeaders());
      setMethodologySearch(result);
      setSelectedMethodologyRef(null);
      setApprovedMethodologyRef(null);
      setNotice(result.candidates.length
        ? `已返回 ${result.candidates.length} 条报告期内有效候选；仍须由 H-02 明确选择。`
        : "当前范围没有可用候选；系统不会用失效规则凑数。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "方法规则检索失败");
    } finally {
      setBusy(null);
    }
  };

  const approveMethodology = () => {
    if (!selectedMethodologyRef) return;
    setApprovedMethodologyRef(selectedMethodologyRef);
    setNotice("H-02 已明确选择该规则；R-01 仍需单独执行确定性计算，当前步骤尚未生成正式 SEE。");
  };

  const runCalculation = async () => {
    if (!detail || !output || !effectiveMethodologyRef || !attributed) return;
    setBusy("calculate");
    setError(null);
    setNotice(null);
    try {
      await calculateSEE(detail.account.id, {
        process_id: detail.processes[0].id,
        product_id: detail.products[0].id,
        production_output_id: output.id,
        methodology_ref: effectiveMethodologyRef,
      }, getHeaders());
      await refresh();
      setNotice("R-01 已使用锁定的输入版本和 RuleRecord ID 生成 SEE，确定性重放结果已写入正式账本。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "确定性 SEE 计算失败");
    } finally {
      setBusy(null);
    }
  };

  const current = detail?.current_snapshot;
  const output = current?.production_outputs?.[0];
  const see = current?.see_results?.[0];
  const attributionCount = current?.attributions?.length || 0;
  const attributed = attributionCount > 0;
  const attributedCandidateIds = useMemo(
    () => new Set((current?.attributions ?? []).map((item) => item.source_ref.replace("emission_result:", ""))),
    [current?.attributions],
  );
  const attributedCandidates = candidates.filter((item) => attributedCandidateIds.has(item.id));
  const existingMethodologyRef = see?.methodology_ref || null;
  const effectiveMethodologyRef = existingMethodologyRef || approvedMethodologyRef;
  const activeRule = rules.find((rule) => `rule_record:${rule.id}` === effectiveMethodologyRef) || null;
  const inputsReady = Boolean(detail && output && attributed);
  const isDemo = Boolean(detail && (detail.installation.name.includes("演示") || detail.installation.operator_name.includes("演示")));

  if (!listLoaded) {
    return (
      <div className="mx-auto max-w-[1500px] space-y-6 pt-1">
        <PageHeader />
        <ProductJourney active="calculation" note="正在读取稳定装置账户与报告期上下文。" />
        <div className="zc-card-pad flex min-h-[360px] items-center justify-center text-sm font-semibold text-slate-500">
          <Loader2 className="mr-3 animate-spin" size={19} /> 正在加载核算工作台...
        </div>
      </div>
    );
  }

  if (!passports.length) {
    return (
      <div className="mx-auto max-w-[1500px] space-y-6 pt-1">
        <PageHeader />
        <ProductJourney active="calculation" note="核算必须绑定稳定装置账户；请先在护照页建立装置、工序和产品身份。" />
        {error && <Banner tone="error" text={error} onClose={() => setError(null)} />}
        <EmptyCalculation />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1580px] space-y-6 pt-1">
      <PageHeader accountId={selectedId} />

      <ProductJourney
        active="calculation"
        states={{ data: inputsReady ? "completed" : "warning", calculation: "active", passport: "pending" }}
        note="AI 查找候选，H-02 批准规则，R-01 只执行确定性计算。"
      />

      {error && <Banner tone="error" text={error} onClose={() => setError(null)} />}
      {notice && <Banner tone="info" text={notice} onClose={() => setNotice(null)} />}

      {!detail ? (
        <div className="zc-card-pad flex min-h-[420px] items-center justify-center text-slate-500">
          <Loader2 className="mr-3 animate-spin" /> 正在读取核算上下文...
        </div>
      ) : (
        <>
          <section className="zc-card-pad">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div className="flex items-start gap-4">
                <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-200">
                  <Database size={27} />
                </span>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-xl font-black text-slate-950">{detail.installation.name}</h2>
                    {isDemo && <span className="zc-pill zc-pill-amber">DEMO ONLY · 非监管用途</span>}
                  </div>
                  <p className="mt-1 font-mono text-xs font-bold text-blue-600">{detail.account.account_code}</p>
                  <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-xs font-semibold text-slate-500">
                    <span>产品 <b className="ml-1 text-slate-800">{detail.products[0]?.name || "待补"}</b></span>
                    <span>CN 编码 <b className="ml-1 text-slate-800">{detail.products[0]?.cn_code || "待补"}</b></span>
                    <span>报告期 <b className="ml-1 text-slate-800">{period.start} 至 {period.end}</b></span>
                  </div>
                </div>
              </div>
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
                <label className="text-xs font-bold text-slate-500">
                  当前装置
                  <span className="relative mt-1 block">
                    <select
                      className="zc-input min-w-72 appearance-none pr-10"
                      value={selectedId || ""}
                      onChange={(event) => setSelectedId(event.target.value)}
                    >
                      {passports.map((item) => <option key={item.account.id} value={item.account.id}>{item.installation.name}</option>)}
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-3 top-3 text-slate-400" size={16} />
                  </span>
                </label>
                <label className="text-xs font-bold text-slate-500">
                  报告期开始
                  <input className="zc-input mt-1" type="date" value={period.start} onChange={(event) => setPeriod({ ...period, start: event.target.value })} />
                </label>
                <label className="text-xs font-bold text-slate-500">
                  报告期结束
                  <input className="zc-input mt-1" type="date" value={period.end} onChange={(event) => setPeriod({ ...period, end: event.target.value })} />
                </label>
                <button className="zc-button mt-5 h-11" onClick={() => void refresh()} disabled={!!busy}>
                  <RefreshCw size={16} className={busy ? "animate-spin" : ""} /> 刷新
                </button>
              </div>
            </div>

            <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatusMetric label="输入事实" value={inputsReady ? "已确认" : "待补齐"} tone={inputsReady ? "green" : "amber"} />
              <StatusMetric label="证据文件" value={`${current?.evidence_manifest?.length || 0}`} />
              <StatusMetric label="适用规则" value={activeRule ? activeRule.document_number : approvedMethodologyRef ? "已选择" : "待批准"} tone={activeRule || approvedMethodologyRef ? "green" : "amber"} />
              <StatusMetric label="正式 SEE" value={see ? `${compact(see.specific_emissions)} ${see.specific_unit}` : "未生成"} tone={see ? "green" : "slate"} />
            </div>
          </section>

          <section className="grid grid-cols-1 gap-6 2xl:grid-cols-[300px_minmax(0,1fr)_370px]">
            <ConfirmedInputs
              candidates={attributedCandidates}
              output={output}
              attributed={attributed}
              attributionCount={attributionCount}
              see={see}
              processName={detail.processes[0]?.name || "待补"}
              evidenceCount={current?.evidence_manifest?.length || 0}
            />

            <section className="zc-card-pad">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="flex items-center gap-2 text-sm font-black text-blue-700"><ShieldCheck size={17} /> H-02 选择方法规则</div>
                  <p className="mt-1 text-xs font-semibold text-slate-500">本体先限定适用范围，RAG 只在有效规则中检索候选。</p>
                </div>
                <span className="zc-pill zc-pill-slate">本体版本 {methodologySearch?.ontology_version || "v0.1"}</span>
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-2 rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3 text-xs font-black text-slate-600">
                {[
                  "EU",
                  "CBAM",
                  detail.processes[0]?.aggregate_goods_category || "钢铁",
                  detail.products[0]?.name || "产品待补",
                  `${period.start.slice(0, 4)} Q${Math.ceil(Number(period.start.slice(5, 7)) / 3)}`,
                ].map((item, index, items) => (
                  <span key={`${item}-${index}`} className="contents">
                    <span className="rounded-lg border border-slate-200 bg-white px-3 py-2">{item}</span>
                    {index < items.length - 1 && <span className="text-slate-300">→</span>}
                  </span>
                ))}
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                <button className="zc-button-primary" onClick={() => void runMethodologySearch()} disabled={!!busy || !rules.length}>
                  {busy === "search" ? <Loader2 className="animate-spin" size={16} /> : <Search size={16} />} H-02 检索有效候选
                </button>
                <button className="zc-button" onClick={() => setRuleOpen((value) => !value)}>
                  <BookOpenCheck size={16} /> {ruleOpen ? "收起规则登记" : rules.length ? "登记新规则版本" : "登记权威规则"}
                </button>
              </div>

              {ruleOpen && <RuleRegistrationForm busy={!!busy} onSubmit={async (payload) => {
                setBusy("register");
                setError(null);
                try {
                  await registerRule(payload, getHeaders());
                  await refresh();
                  setRuleOpen(false);
                  setNotice("权威规则版本已登记；仍须由 H-02 重新检索并选择。 ");
                } catch (err) {
                  setError(err instanceof Error ? err.message : "规则登记失败");
                } finally {
                  setBusy(null);
                }
              }} />}

              <div className="mt-5">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-black text-slate-900">RAG 检索候选</h3>
                  {methodologySearch && <span className="zc-pill zc-pill-blue">候选 {methodologySearch.candidates.length}</span>}
                </div>
                {!methodologySearch ? (
                  <div className="mt-3 rounded-2xl border border-dashed border-blue-200 bg-blue-50/40 p-6 text-center">
                    <Search className="mx-auto text-blue-500" size={24} />
                    <p className="mt-2 text-sm font-bold text-slate-700">尚未执行报告期规则检索</p>
                    <p className="mt-1 text-xs leading-5 text-slate-500">检索会记录查询范围、命中片段和 Trace；不会自动批准规则。</p>
                  </div>
                ) : (
                  <div className="mt-3 space-y-3">
                    {methodologySearch.candidates.map((candidate) => {
                      const selected = selectedMethodologyRef === candidate.methodology_ref;
                      const approved = approvedMethodologyRef === candidate.methodology_ref || existingMethodologyRef === candidate.methodology_ref;
                      return (
                        <button
                          key={candidate.rule.id}
                          type="button"
                          onClick={() => {
                            if (existingMethodologyRef) return;
                            setSelectedMethodologyRef(candidate.methodology_ref);
                            setApprovedMethodologyRef(null);
                          }}
                          className={`w-full rounded-2xl border p-4 text-left transition ${selected || approved ? "border-blue-400 bg-blue-50 ring-2 ring-blue-100" : "border-slate-200 bg-white hover:border-blue-300"}`}
                        >
                          <div className="flex items-start gap-3">
                            <span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${selected || approved ? "border-blue-600 bg-blue-600 text-white" : "border-slate-300"}`}>
                              {(selected || approved) && <Check size={12} />}
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="flex flex-wrap items-center justify-between gap-2">
                                <b className="text-sm text-slate-900">{candidate.rule.title}</b>
                                <span className="zc-pill zc-pill-green">报告期内有效</span>
                              </span>
                              <small className="mt-1 block text-slate-500">{candidate.rule.publisher} · {candidate.rule.document_number} · Vintage {candidate.rule.vintage}</small>
                              <span className="mt-3 flex items-center gap-2 text-xs font-bold text-blue-600"><Eye size={14} /> 来源片段：{candidate.retrieval.excerpt.slice(0, 90)}{candidate.retrieval.excerpt.length > 90 ? "…" : ""}</span>
                            </span>
                          </div>
                        </button>
                      );
                    })}
                    {!methodologySearch.candidates.length && (
                      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm font-semibold text-amber-800">当前范围没有可用候选；系统不会用失效规则凑数。</div>
                    )}
                  </div>
                )}
              </div>

              <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-xs font-semibold leading-5 text-amber-800">
                RAG 只负责检索和排序；H-02 的明确选择才会被交给 R-01。尚未执行计算前，不产生正式方法学结果。
              </div>

              {!existingMethodologyRef && (
                <div className="mt-4 space-y-3">
                  <label className="block text-xs font-bold text-slate-500">
                    人工选择说明
                    <textarea
                      className="zc-input mt-2 min-h-20 w-full"
                      value={approvalNote}
                      onChange={(event) => setApprovalNote(event.target.value)}
                      placeholder="说明选择该规则的业务依据；当前原型仅用于本页人工确认，不写入正式账本。"
                    />
                  </label>
                  <button className="zc-button-primary w-full py-3" disabled={!selectedMethodologyRef || !approvalNote.trim()} onClick={approveMethodology}>
                    <ShieldCheck size={17} /> {approvedMethodologyRef ? "H-02 已明确选择" : "H-02 确认所选规则"}
                  </button>
                </div>
              )}
            </section>

            <CalculationPanel
              see={see}
              outputQuantity={output?.quantity}
              inputsReady={inputsReady}
              methodologyReady={Boolean(effectiveMethodologyRef)}
              activeRule={activeRule}
              busy={busy === "calculate"}
              onCalculate={() => void runCalculation()}
            />
          </section>

          <section className="zc-card-pad flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-3">
              <Fingerprint className="text-blue-600" size={22} />
              <div>
                <b className="text-sm text-slate-900">核算完成后进入护照编制与发布</b>
                <p className="mt-1 text-xs text-slate-500">护照页只消费正式 SEE，不再重复执行 RAG 检索和计算。</p>
              </div>
            </div>
            <Link to={`/passports?account_id=${encodeURIComponent(detail.account.id)}`} className={`zc-button-primary ${!see ? "pointer-events-none opacity-50" : ""}`}>
              查看工厂碳数据护照 <Fingerprint size={16} />
            </Link>
          </section>

          <details className="zc-card-pad group">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-black text-slate-800">
              <span>查看规则来源、RAG Trace 与计算版本</span>
              <span className="flex flex-wrap gap-2">
                <span className="zc-pill zc-pill-slate">证据 {current?.evidence_manifest?.length || 0}</span>
                <span className="zc-pill zc-pill-slate">RAG 候选 {methodologySearch?.candidates.length || 0}</span>
                <span className="zc-pill zc-pill-slate">本体 {methodologySearch?.ontology_version || "v0.1"}</span>
                <span className="zc-pill zc-pill-slate">Trace {methodologySearch?.retrieval_run_id.slice(0, 8) || "未生成"}</span>
              </span>
            </summary>
            <div className="mt-4 grid gap-3 border-t border-slate-100 pt-4 text-xs text-slate-600 md:grid-cols-3">
              <AuditFact label="H-02 选择" value={effectiveMethodologyRef || "未形成"} />
              <AuditFact label="RAG Trace" value={methodologySearch?.retrieval_run_id || "未生成"} />
              <AuditFact label="SEE 内容哈希" value={see?.content_hash || "未生成"} />
            </div>
          </details>
        </>
      )}
    </div>
  );
}

function PageHeader({ accountId }: { accountId?: string | null }) {
  return (
    <header className="flex flex-col gap-5 pr-0 lg:pr-80 xl:flex-row xl:items-end xl:justify-between">
      <div>
        <div className="mb-3 flex items-center gap-2 text-sm font-bold text-blue-600"><Calculator size={17} /> 方法与确定性计算</div>
        <h1 className="text-3xl font-black tracking-tight text-slate-950">核算工作台</h1>
        <p className="mt-3 max-w-3xl text-sm font-medium leading-6 text-slate-500">把企业确认的事实与人工选择的方法，转成精确、可解释、可重放的核算结果。</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Link to="/upload" className="zc-button"><Database size={17} /> 返回数据工作台</Link>
        <Link to={accountId ? `/passports?account_id=${encodeURIComponent(accountId)}` : "/passports"} className="zc-button-primary"><Fingerprint size={17} /> 查看碳数据护照</Link>
      </div>
    </header>
  );
}

function ConfirmedInputs({ candidates, output, attributed, attributionCount, see, processName, evidenceCount }: {
  candidates: EmissionCandidate[];
  output?: { quantity: string; unit: string };
  attributed: boolean;
  attributionCount: number;
  see?: { total_emissions: string; emissions_unit: string };
  processName: string;
  evidenceCount: number;
}) {
  const emissionsValue = candidates.length
    ? candidates.map((item) => `${compact(item.emissions)} ${item.unit}`).join(" + ")
    : see
      ? `${compact(see.total_emissions)} ${see.emissions_unit}`
      : attributed
        ? `已锁定 ${attributionCount} 条归集引用`
        : "尚未归集";
  const emissionsNote = candidates[0]?.document_name
    || (attributed ? "以正式归集账本为准；候选接口不作为完成状态判据" : "请先在护照页归集已确认排放");
  return (
    <aside className="zc-card-pad h-fit 2xl:sticky 2xl:top-5">
      <div className="flex items-center gap-2 text-sm font-black text-slate-900"><Database size={17} className="text-blue-600" /> 已确认输入</div>
      <p className="mt-1 text-xs font-semibold text-slate-500">来自正式账本，只读展示</p>
      <div className="mt-4 space-y-3">
        <InputFact
          title="活动排放"
          value={emissionsValue}
          note={emissionsNote}
          ready={attributed}
        />
        <InputFact title="合格产品产量" value={output ? `${compact(output.quantity)} ${output.unit}` : "尚未登记"} note="报告期产量账本" ready={Boolean(output)} />
        <InputFact title="归集目标" value={attributed ? "100%" : "待归集"} note={processName} ready={attributed} />
        <InputFact title="证据文件" value={`${evidenceCount} 份`} note="仅展示安全元数据与哈希" ready={evidenceCount > 0} />
      </div>
      <Link to="/upload" className="zc-button-soft mt-4 flex w-full justify-center"><FileCheck2 size={16} /> 查看原始证据</Link>
      <p className="mt-3 text-xs leading-5 text-slate-400">这里不能修改企业事实；如需修改，请回到数字员工工作台重新质检并确认。</p>
    </aside>
  );
}

function CalculationPanel({ see, outputQuantity, inputsReady, methodologyReady, activeRule, busy, onCalculate }: {
  see?: { direct_emissions: string; indirect_emissions: string; total_emissions: string; emissions_unit: string; specific_emissions: string; specific_unit: string; replay_match?: boolean };
  outputQuantity?: string;
  inputsReady: boolean;
  methodologyReady: boolean;
  activeRule: RuleRecord | null;
  busy: boolean;
  onCalculate: () => void;
}) {
  return (
    <aside className="zc-card-pad h-fit 2xl:sticky 2xl:top-5">
      <div className="flex items-center gap-2 text-sm font-black text-slate-900"><Calculator size={17} className="text-blue-600" /> R-01 确定性计算</div>
      <p className="mt-1 text-xs font-semibold text-slate-500">只接收正式输入和 H-02 明确选择的 RuleRecord。</p>

      <div className="mt-4 space-y-2 rounded-2xl border border-slate-100 bg-slate-50 p-4 text-xs font-semibold text-slate-600">
        <CheckLine ready={inputsReady} label="活动排放与产量已准备" />
        <CheckLine ready={methodologyReady} label={methodologyReady ? `方法规则已选择${activeRule ? ` · ${activeRule.document_number}` : ""}` : "等待 H-02 选择方法规则"} />
        <CheckLine ready={Boolean(see?.replay_match)} label={see ? (see.replay_match ? "确定性重放通过" : "确定性重放未通过") : "尚未生成正式 SEE"} />
      </div>

      <div className="mt-4 rounded-2xl border border-blue-100 bg-blue-50/40 p-4">
        <b className="text-xs text-slate-900">计算公式</b>
        <div className="mt-3 rounded-xl bg-white px-3 py-4 text-center text-sm font-black text-slate-700">总排放 ÷ 合格产品产量 = 单位产品 SEE</div>
        <p className="mt-3 text-center text-xs font-semibold text-slate-500">{see ? `${compact(see.total_emissions)} ${see.emissions_unit} ÷ ${compact(outputQuantity || "0")} t` : outputQuantity ? `正式排放 ÷ ${compact(outputQuantity)} t` : "等待正式输入"}</p>
      </div>

      {see ? (
        <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
          <div className="flex items-center gap-2 text-sm font-black text-emerald-900"><BadgeCheck size={18} /> 正式 SEE 已生成</div>
          <div className="mt-4 text-center">
            <b className="text-3xl font-black text-emerald-700">{compact(see.specific_emissions)}</b>
            <span className="ml-2 text-sm font-bold text-emerald-800">{see.specific_unit}</span>
          </div>
          <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs text-emerald-800">
            <span><small className="block opacity-70">直接</small><b>{compact(see.direct_emissions)}</b></span>
            <span><small className="block opacity-70">间接</small><b>{compact(see.indirect_emissions)}</b></span>
            <span><small className="block opacity-70">总排放</small><b>{compact(see.total_emissions)}</b></span>
          </div>
        </div>
      ) : (
        <button className="zc-button-primary mt-4 w-full py-3" disabled={!inputsReady || !methodologyReady || busy} onClick={onCalculate}>
          {busy ? <Loader2 className="animate-spin" size={17} /> : <Play size={17} />} 运行确定性 SEE
        </button>
      )}

      <p className="mt-3 text-xs leading-5 text-slate-400">R-01 使用 Decimal 精确计算，不调用大模型生成结果，也不会自行选择方法学。</p>
      <div className="mt-4 flex flex-wrap gap-2">
        <span className="zc-pill zc-pill-blue">单位检查</span>
        <span className="zc-pill zc-pill-blue">期间一致性</span>
        <span className="zc-pill zc-pill-blue">确定性重放</span>
      </div>
    </aside>
  );
}

function RuleRegistrationForm({ busy, onSubmit }: { busy: boolean; onSubmit: (payload: Record<string, unknown>) => Promise<void> }) {
  const [form, setForm] = useState({
    title: "EU CBAM 方法学规则",
    document_number: "",
    vintage: "2026",
    valid_from: "2026-01-01",
    source_url: "https://",
    source_content_hash: "",
  });
  const validHash = /^[0-9a-f]{64}$/.test(form.source_content_hash);
  return (
    <div className="mt-4 grid gap-3 rounded-2xl border border-blue-100 bg-blue-50/40 p-4 md:grid-cols-2">
      <MiniField label="规则标题" value={form.title} onChange={(value) => setForm({ ...form, title: value })} />
      <MiniField label="文号" value={form.document_number} onChange={(value) => setForm({ ...form, document_number: value })} />
      <MiniField label="Vintage" value={form.vintage} onChange={(value) => setForm({ ...form, vintage: value })} />
      <MiniField label="生效日期" value={form.valid_from} type="date" onChange={(value) => setForm({ ...form, valid_from: value })} />
      <div className="md:col-span-2"><MiniField label="官方 HTTPS 来源" value={form.source_url} onChange={(value) => setForm({ ...form, source_url: value })} /></div>
      <div className="md:col-span-2"><MiniField label="人工核对后的原文 SHA-256" value={form.source_content_hash} onChange={(value) => setForm({ ...form, source_content_hash: value.toLowerCase() })} /></div>
      <div className="md:col-span-2 flex items-center justify-between gap-3">
        <p className="text-xs font-semibold text-amber-700">登记人必须确认 URL、文号与哈希对应同一版本。</p>
        <button className="zc-button-primary" disabled={busy || !form.document_number || !validHash} onClick={() => void onSubmit({
          rule_kind: "cbam_methodology",
          title: form.title,
          publisher: "European Commission",
          document_number: form.document_number,
          jurisdiction: "EU",
          vintage: Number(form.vintage),
          valid_from: `${form.valid_from}T00:00:00Z`,
          valid_to: null,
          source_url: form.source_url,
          source_content_hash: form.source_content_hash,
        })}><BookOpenCheck size={16} /> 登记不可变版本</button>
      </div>
    </div>
  );
}

function StatusMetric({ label, value, tone = "blue" }: { label: string; value: string; tone?: "blue" | "green" | "amber" | "slate" }) {
  const colors = { blue: "text-blue-700", green: "text-emerald-700", amber: "text-amber-700", slate: "text-slate-700" };
  return <div className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3"><small className="font-semibold text-slate-500">{label}</small><b className={`mt-1 block truncate text-lg ${colors[tone]}`}>{value}</b></div>;
}

function InputFact({ title, value, note, ready }: { title: string; value: string; note: string; ready: boolean }) {
  return <div className={`rounded-2xl border p-4 ${ready ? "border-emerald-100 bg-emerald-50/50" : "border-amber-200 bg-amber-50"}`}><div className="flex items-start justify-between gap-2"><span><small className="font-bold text-slate-500">{title}</small><b className="mt-1 block text-lg text-slate-900">{value}</b></span>{ready ? <Check className="text-emerald-600" size={17} /> : <CircleAlert className="text-amber-600" size={17} />}</div><p className="mt-2 break-words text-xs text-slate-500">{note}</p></div>;
}

function CheckLine({ ready, label }: { ready: boolean; label: string }) {
  return <div className="flex items-start gap-2"><span className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full ${ready ? "bg-emerald-600 text-white" : "bg-amber-100 text-amber-700"}`}>{ready ? <Check size={10} /> : <CircleAlert size={10} />}</span><span>{label}</span></div>;
}

function MiniField({ label, value, type = "text", onChange }: { label: string; value: string; type?: string; onChange: (value: string) => void }) {
  return <label className="block text-xs font-bold text-slate-500">{label}<input className="zc-input mt-2 w-full" type={type} value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function AuditFact({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl bg-slate-50 p-3"><b className="block text-slate-800">{label}</b><span className="mt-1 block break-all font-mono text-[10px] text-slate-500">{value}</span></div>;
}

function Banner({ tone, text, onClose }: { tone: "info" | "error"; text: string; onClose: () => void }) {
  return <div className={`flex items-start gap-3 rounded-2xl border px-4 py-3 text-sm font-semibold ${tone === "error" ? "border-red-200 bg-red-50 text-red-800" : "border-blue-200 bg-blue-50 text-blue-800"}`}>{tone === "error" ? <AlertTriangle className="mt-0.5 shrink-0" size={17} /> : <ShieldCheck className="mt-0.5 shrink-0" size={17} />}<span className="flex-1">{text}</span><button onClick={onClose} className="text-xs font-black">关闭</button></div>;
}

function EmptyCalculation() {
  return <div className="zc-card-pad flex min-h-[480px] flex-col items-center justify-center text-center"><span className="flex h-20 w-20 items-center justify-center rounded-3xl bg-blue-50 text-blue-600"><Calculator size={36} /></span><h2 className="mt-5 text-2xl font-black text-slate-950">还没有可核算的装置账户</h2><p className="mt-3 max-w-lg text-sm leading-6 text-slate-500">先建立稳定的装置、工序和产品身份，再把企业确认的数据归集到报告期。</p><Link to="/passports" className="zc-button-primary mt-6"><Fingerprint size={17} /> 去建立装置护照</Link></div>;
}

function compact(value: string | number): string {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return number.toLocaleString("zh-CN", { maximumFractionDigits: 6 });
}
