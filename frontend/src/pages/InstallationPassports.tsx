import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import {
  Archive,
  ArrowRight,
  BadgeCheck,
  BookOpenCheck,
  Building2,
  Check,
  ChevronRight,
  CircleAlert,
  Database,
  Download,
  Eye,
  FileCheck2,
  FilePlus2,
  Fingerprint,
  Gauge,
  KeyRound,
  Link2,
  LockKeyhole,
  Plus,
  RefreshCw,
  Scale,
  Send,
  ShieldCheck,
  Sparkles,
  Unplug,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import {
  addAttribution,
  addOutput,
  calculateSEE,
  createGrant,
  createPassport,
  exportGrant,
  fetchEmissionCandidates,
  fetchPassport,
  fetchPassports,
  fetchRules,
  freezeProfile,
  publishProfile,
  registerRule,
  reviewProfile,
  revokeGrant,
  type EmissionCandidate,
  type PassportDetail,
  type PassportProfile,
  type RuleRecord,
  type SharingGrant,
} from "../utils/passports";

const DEFAULT_PERIOD = { start: "2026-01-01", end: "2026-03-31" };
const DEFAULT_SHARE_EXPIRY = new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10);
const SHARE_SCOPES = [
  ["identity", "装置身份"],
  ["processes", "生产工序"],
  ["products", "产品信息"],
  ["outputs", "期间产量"],
  ["emissions", "排放与 SEE"],
  ["evidence_manifest", "证据清单"],
  ["methodology", "方法学规则"],
  ["review", "复核记录"],
] as const;

export default function InstallationPassports() {
  const { getHeaders } = useAuth();
  const navigate = useNavigate();
  const [passports, setPassports] = useState<PassportDetail[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PassportDetail | null>(null);
  const [candidates, setCandidates] = useState<EmissionCandidate[]>([]);
  const [rules, setRules] = useState<RuleRecord[]>([]);
  const [period, setPeriod] = useState(DEFAULT_PERIOD);
  const [createOpen, setCreateOpen] = useState(false);
  const [ruleOpen, setRuleOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [publishedOpen, setPublishedOpen] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    const items = await fetchPassports(getHeaders());
    setPassports(items);
    setSelectedId((current) => current || items[0]?.account.id || null);
  }, [getHeaders]);

  const loadDetail = useCallback(async () => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    const headers = getHeaders();
    const [passport, emissions, methodologyRules] = await Promise.all([
      fetchPassport(selectedId, period.start, period.end, headers),
      fetchEmissionCandidates(selectedId, period.start, period.end, headers),
      fetchRules(headers),
    ]);
    setDetail(passport);
    setCandidates(emissions);
    setRules(methodologyRules);
  }, [getHeaders, period.end, period.start, selectedId]);

  useEffect(() => {
    loadList().catch((err: Error) => setError(err.message));
  }, [loadList]);

  useEffect(() => {
    loadDetail().catch((err: Error) => setError(err.message));
  }, [loadDetail]);

  const refresh = useCallback(async () => {
    await Promise.all([loadList(), loadDetail()]);
  }, [loadDetail, loadList]);

  const run = async (label: string, action: () => Promise<unknown>, success: string) => {
    setBusy(label);
    setError(null);
    setNotice(null);
    try {
      await action();
      await refresh();
      setNotice(success);
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setBusy(null);
    }
  };

  const current = detail?.current_snapshot;
  const outputs = current?.production_outputs || [];
  const seeResults = current?.see_results || [];
  const evidence = current?.evidence_manifest || [];
  const published = [...(detail?.profiles || [])]
    .filter((item) => item.status === "published")
    .sort((a, b) => b.version - a.version)[0] || null;
  const latestDraft = [...(detail?.profiles || [])]
    .filter((item) => item.status === "draft" && item.version > (published?.version || 0))
    .sort((a, b) => b.version - a.version)[0] || null;
  const draftReview = latestDraft
    ? detail?.reviews.find((item) => item.profile_version_id === latestDraft.id) || null
    : null;

  return (
    <div className="mx-auto max-w-[1640px] space-y-6 pt-1">
      <header className="flex flex-col gap-5 pr-0 lg:pr-80 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <div className="mb-3 flex items-center gap-2 text-sm font-bold text-blue-600">
            <Fingerprint size={17} /> 生产装置可信数据账户
          </div>
          <h1 className="text-3xl font-black tracking-tight text-slate-950">工厂碳数据护照</h1>
          <p className="mt-3 max-w-3xl text-sm font-medium leading-6 text-slate-500">
            把装置身份、工序、产品、产量、活动排放、证据和方法学组织成可重放、可复核、可授权共享的版本；报告只是护照的一个输出。
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <button className="zc-button" onClick={() => refresh()} disabled={!!busy}>
            <RefreshCw size={17} /> 刷新事实
          </button>
          <button className="zc-button-primary" onClick={() => setCreateOpen(true)}>
            <Plus size={17} /> 新建装置护照
          </button>
        </div>
      </header>

      {(error || notice) && (
        <div className={`rounded-2xl border px-5 py-4 text-sm font-semibold ${error ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>
          {error || notice}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="zc-card-pad h-fit xl:sticky xl:top-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-black text-slate-950">装置账户</h2>
              <p className="mt-1 text-xs font-medium text-slate-500">稳定 ID，不随报告版本变化</p>
            </div>
            <span className="zc-pill zc-pill-blue">{passports.length}</span>
          </div>
          <div className="space-y-3">
            {passports.map((item) => (
              <button
                key={item.account.id}
                onClick={() => setSelectedId(item.account.id)}
                className={`w-full rounded-2xl border p-4 text-left transition ${selectedId === item.account.id ? "border-blue-300 bg-blue-50 shadow-sm" : "border-slate-100 bg-white hover:border-blue-200"}`}
              >
                <div className="flex items-start gap-3">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white text-blue-600 shadow-sm"><Building2 size={20} /></span>
                  <span className="min-w-0 flex-1">
                    <b className="block truncate text-sm text-slate-900">{item.installation.name}</b>
                    <small className="mt-1 block font-mono text-[10px] text-slate-500">{item.account.account_code}</small>
                  </span>
                  <ChevronRight size={17} className="mt-1 text-slate-400" />
                </div>
                <div className="mt-4 flex items-center gap-3">
                  <div className="zc-progress flex-1"><span style={{ width: `${item.assessment.score}%` }} /></div>
                  <span className="text-xs font-black text-slate-700">{item.assessment.score}%</span>
                </div>
              </button>
            ))}
            {!passports.length && (
              <button onClick={() => setCreateOpen(true)} className="w-full rounded-2xl border border-dashed border-blue-200 bg-blue-50/50 p-8 text-center text-sm font-bold text-blue-700">
                <Plus size={22} className="mx-auto mb-2" /> 建立第一份装置护照
              </button>
            )}
          </div>
        </aside>

        {!detail ? (
          <EmptyPassport onCreate={() => setCreateOpen(true)} />
        ) : (
          <main className="space-y-6">
            <PassportHero detail={detail} published={published} />

            {(detail.installation.name.includes("演示") || detail.installation.operator_name.includes("演示")) && (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm font-semibold leading-6 text-amber-900">
                <b>DEMO ONLY · 非监管用途。</b> 当前账户用于验证真实产品流程；其中规则、因子、复核、接收方和交付均为明确标注的合成演示数据，不能用于申报或法定核查。
              </div>
            )}

            <section className="grid grid-cols-1 gap-4 md:grid-cols-4">
              <Metric
                icon={Gauge}
                title={published ? "已发布版本完整度" : "当前档案完整度"}
                value={`${published?.completeness_score ?? detail.assessment.score}%`}
                note={published ? `v${published.version} 已固化，不受工作副本变化影响` : "由正式事实自动派生"}
                tone="blue"
              />
              <Metric icon={FileCheck2} title="证据文件" value={`${evidence.length}`} note="仅展示哈希与安全元数据" tone="green" />
              <Metric icon={Scale} title="单位产品 SEE" value={seeResults[0] ? `${compact(seeResults[0].specific_emissions)} ${seeResults[0].specific_unit}` : "待计算"} note={seeResults[0]?.replay_match ? "确定性重放通过" : "未形成正式结果"} tone="purple" />
              <Metric icon={LockKeyhole} title="当前版本" value={latestDraft ? `v${latestDraft.version} 草稿` : published ? `v${published.version} 已发布` : "未冻结"} note="已发布版本不可原地修改" tone="amber" />
            </section>

            {published && (
              <PublishedVersionPanel
                detail={detail}
                profile={published}
                open={publishedOpen}
                onToggle={() => setPublishedOpen((value) => !value)}
              />
            )}

            <section className="grid grid-cols-1 gap-6 2xl:grid-cols-[minmax(0,1fr)_380px]">
              <div className="space-y-6">
                <PeriodBar period={period} setPeriod={setPeriod} />

                <WorkflowCard number="01" title="装置、工序和产品已成为正式事实" icon={Building2} done>
                  <div className="grid gap-3 md:grid-cols-3">
                    <Fact label="装置经营者" value={detail.installation.operator_name} />
                    <Fact label="生产路线" value={detail.processes[0]?.production_route || "待补"} />
                    <Fact label="CN 编码" value={detail.products[0]?.cn_code || "待补"} />
                  </div>
                </WorkflowCard>

                <WorkflowCard number="02" title="接入已确认的活动排放与源文件" icon={Database} done={detail.assessment.checks.find((item) => item.key === "attributed_emissions")?.passed}>
                  {candidates.length ? (
                    <div className="space-y-3">
                      {candidates.map((candidate) => {
                        const assigned = (current?.attributions || []).some((item) => item.source_ref === `emission_result:${candidate.id}`);
                        return (
                          <div key={candidate.id} className="flex flex-col gap-3 rounded-2xl border border-slate-100 bg-slate-50 p-4 md:flex-row md:items-center">
                            <span className={`flex h-10 w-10 items-center justify-center rounded-xl ${candidate.evidence_ready ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}><FileCheck2 size={19} /></span>
                            <span className="min-w-0 flex-1">
                              <b className="block text-sm text-slate-900">{candidate.source_name}</b>
                              <small className="mt-1 block text-slate-500">{compact(candidate.emissions)} {candidate.unit} · {candidate.document_name || "没有源文件"}</small>
                            </span>
                            <button
                              disabled={assigned || !!busy || !detail.processes[0]}
                              onClick={() => run("归集排放", () => addAttribution(detail.account.id, {
                                process_id: detail.processes[0].id,
                                emission_result_id: candidate.id,
                                period_start: `${period.start}T00:00:00Z`,
                                period_end: `${period.end}T23:59:59Z`,
                                share: "1",
                                method: "metered_allocation",
                              }, getHeaders()), "活动排放已完整归集到当前工序。")}
                              className={assigned ? "zc-pill zc-pill-green" : "zc-button-soft"}
                            >
                              {assigned ? <><Check size={14} /> 已归集</> : "100% 归集到本工序"}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <Callout icon={FilePlus2} title="当前期间还没有可归集的正式排放" text="先在数据收件箱上传账单或生产记录，并完成人工字段确认。" action="去数据收集" onClick={() => navigate("/upload")} />
                  )}
                </WorkflowCard>

                <WorkflowCard number="03" title="登记报告期产量" icon={Archive} done={outputs.length > 0}>
                  <OutputForm
                    output={outputs[0]}
                    busy={!!busy}
                    onSubmit={(quantity) => run("登记产量", () => addOutput(detail.account.id, {
                      process_id: detail.processes[0].id,
                      product_id: detail.products[0].id,
                      period_start: `${period.start}T00:00:00Z`,
                      period_end: `${period.end}T23:59:59Z`,
                      quantity,
                      unit: "t",
                    }, getHeaders()), "报告期产量已写入追加式账本。")}
                  />
                </WorkflowCard>

                <WorkflowCard number="04" title="锁定权威方法学并生成确定性 SEE" icon={Scale} done={seeResults.length > 0}>
                  <div className="space-y-4">
                    <div className="flex flex-col gap-3 rounded-2xl border border-slate-100 p-4 md:flex-row md:items-center">
                      <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-50 text-violet-700"><BookOpenCheck size={19} /></span>
                      <span className="min-w-0 flex-1">
                        <b className="block text-sm text-slate-900">{rules[0]?.title || "尚未登记适用规则"}</b>
                        <small className="mt-1 block text-slate-500">{rules[0] ? `${rules[0].publisher} · ${rules[0].document_number} · vintage ${rules[0].vintage}` : "规则必须包含权威发布者、文号、适用期、来源 URL 与内容哈希。"}</small>
                      </span>
                      <button onClick={() => setRuleOpen((value) => !value)} className="zc-button">{ruleOpen ? "收起" : rules.length ? "登记新版本" : "登记规则"}</button>
                    </div>
                    {ruleOpen && <RuleForm busy={!!busy} onSubmit={(payload) => run("登记规则", () => registerRule(payload, getHeaders()), "权威规则版本已登记且不可原地修改。").then(() => setRuleOpen(false))} />}
                    {seeResults[0] ? (
                      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
                        <div className="flex items-center gap-3"><BadgeCheck className="text-emerald-600" /><b className="text-emerald-900">SEE 已生成并通过重放</b></div>
                        <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
                          <Fact label="直接排放" value={`${compact(seeResults[0].direct_emissions)} tCO₂e`} />
                          <Fact label="间接排放" value={`${compact(seeResults[0].indirect_emissions)} tCO₂e`} />
                          <Fact label="总排放" value={`${compact(seeResults[0].total_emissions)} tCO₂e`} />
                          <Fact label="单位产品" value={`${compact(seeResults[0].specific_emissions)} tCO₂e/t`} />
                        </div>
                      </div>
                    ) : (
                      <button
                        className="zc-button-primary w-full py-3"
                        disabled={!outputs[0] || !rules[0] || !(current?.attributions || []).length || !!busy}
                        onClick={() => run("计算 SEE", () => calculateSEE(detail.account.id, {
                          process_id: detail.processes[0].id,
                          product_id: detail.products[0].id,
                          production_output_id: outputs[0].id,
                          methodology_ref: `rule_record:${rules[0].id}`,
                        }, getHeaders()), "确定性 SEE 已生成并绑定精确输入版本。")}
                      >
                        <Sparkles size={17} /> 生成并重放 SEE
                      </button>
                    )}
                  </div>
                </WorkflowCard>

                <WorkflowCard number="05" title="冻结、方法学复核并发布" icon={ShieldCheck} done={!!published}>
                  <ReleasePanel
                    detail={detail}
                    latestDraft={latestDraft}
                    draftReview={draftReview}
                    published={published}
                    busy={!!busy}
                    onFreeze={() => run("冻结草稿", () => freezeProfile(detail.account.id, period.start, period.end, getHeaders()), "当前正式事实已冻结为可重放草稿。")}
                    onReview={(profile, review) => run("方法学复核", () => reviewProfile(detail.account.id, {
                      profile_version_id: profile.id,
                      ...review,
                    }, getHeaders()), "方法学复核已记录；该状态不等于法定 CBAM 核查。")}
                    onPublish={(profile, reviewId) => run("发布护照", () => publishProfile(detail.account.id, {
                      profile_version_id: profile.id,
                      methodology_review_id: reviewId,
                    }, getHeaders()), "不可变护照版本已发布。")}
                  />
                </WorkflowCard>

                <WorkflowCard number="06" title="按最小权限授权共享" icon={Link2} done={detail.sharing_grants.some((item) => item.active)}>
                  {!published ? (
                    <Callout icon={LockKeyhole} title="发布后才能授权" text="共享对象必须是完整、可重放且已经过方法学复核的不可变版本。" />
                  ) : (
                    <div className="space-y-4">
                      <button className="zc-button-primary" onClick={() => setShareOpen((value) => !value)}><KeyRound size={17} /> 创建共享授权</button>
                      {shareOpen && <ShareForm busy={!!busy} onSubmit={(payload) => run("创建授权", () => createGrant(detail.account.id, { ...payload, profile_version_id: published.id }, getHeaders()), "限范围共享授权已创建。" ).then(() => setShareOpen(false))} />}
                      <GrantList
                        grants={detail.sharing_grants}
                        busy={!!busy}
                        onExport={(grant) => run("导出共享包", async () => {
                          const result = await exportGrant(detail.account.id, grant.id, getHeaders());
                          downloadJson(result.package, `${detail.account.account_code}-v${published.version}-${grant.id.slice(0, 8)}.json`);
                        }, "共享包已导出，并记录了实际交付事件。")}
                        onRevoke={(grant) => run("撤销授权", () => revokeGrant(detail.account.id, grant.id, "授权由护照所有者主动撤销", getHeaders()), "授权已追加撤销事件，接收方访问立即失效。")}
                      />
                    </div>
                  )}
                </WorkflowCard>
              </div>

              <aside className="space-y-5 2xl:sticky 2xl:top-5 2xl:h-fit">
                <ReadinessPanel detail={detail} published={published} />
                <div className="zc-card-pad">
                  <div className="flex items-center gap-3"><ShieldCheck className="text-blue-600" /><h3 className="text-lg font-black text-slate-950">系统不会替你说谎</h3></div>
                  <div className="mt-4 space-y-3 text-sm leading-6 text-slate-600">
                    <Guardrail text="完整度来自正式记录，不接受客户端填写。" />
                    <Guardrail text="LLM 不能把裸数字写入正式护照。" />
                    <Guardrail text="方法学复核不冒充法定核查。" />
                    <Guardrail text="撤销授权不会改写旧记录，而是追加撤销事件。" />
                  </div>
                </div>
                <div className="zc-card-pad">
                  <h3 className="text-lg font-black text-slate-950">实际交付记录</h3>
                  <div className="mt-4 space-y-3">
                    {detail.distribution_events.slice(0, 5).map((event) => (
                      <div key={event.id} className="rounded-xl bg-slate-50 p-3 text-xs text-slate-600">
                        <b className="block text-slate-800">{event.delivered_to}</b>
                        <span>{event.channel === "json_export" ? "JSON 导出" : "平台访问"} · {event.package_hash.slice(0, 12)}…</span>
                      </div>
                    ))}
                    {!detail.distribution_events.length && <p className="text-sm text-slate-500">尚未发生真实交付，授权本身不算使用证据。</p>}
                  </div>
                </div>
              </aside>
            </section>
          </main>
        )}
      </div>

      {createOpen && <CreatePassportModal busy={!!busy} onClose={() => setCreateOpen(false)} onSubmit={(payload) => run("创建护照", async () => {
        const created = await createPassport(payload, getHeaders());
        setSelectedId(created.account.id);
      }, "装置护照账户和第一版正式事实已创建。").then(() => setCreateOpen(false))} />}
    </div>
  );
}

function PassportHero({ detail, published }: { detail: PassportDetail; published: PassportProfile | null }) {
  return (
    <section className="overflow-hidden rounded-3xl border border-blue-100 bg-[radial-gradient(circle_at_85%_0%,rgba(59,130,246,0.17),transparent_28%),linear-gradient(135deg,#ffffff_0%,#f7fbff_100%)] p-6 shadow-sm md:p-8">
      <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
        <div className="flex items-start gap-4">
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-200"><Fingerprint size={28} /></span>
          <div>
            <div className="flex flex-wrap items-center gap-2"><h2 className="text-2xl font-black text-slate-950">{detail.installation.name}</h2><span className={`zc-pill ${published ? "zc-pill-green" : "zc-pill-amber"}`}>{published ? "已发布" : "建档中"}</span></div>
            <p className="mt-2 font-mono text-xs font-semibold text-blue-700">{detail.account.account_code}</p>
            <p className="mt-3 text-sm text-slate-500">{detail.installation.operator_name} · {detail.installation.country_code}{detail.installation.unlocode ? ` / ${detail.installation.unlocode}` : ""}</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 text-center">
          <div className="rounded-2xl border border-white bg-white/80 px-5 py-3 shadow-sm"><small className="text-slate-500">身份事实版本</small><b className="mt-1 block text-xl text-slate-950">v{detail.installation.version}</b></div>
          <div className="rounded-2xl border border-white bg-white/80 px-5 py-3 shadow-sm"><small className="text-slate-500">{published ? "已发布数据质量" : "数据质量"}</small><b className="mt-1 block text-xl text-emerald-600">{published?.data_quality_grade ?? detail.assessment.grade} 级</b></div>
        </div>
      </div>
    </section>
  );
}

function PublishedVersionPanel({ detail, profile, open, onToggle }: { detail: PassportDetail; profile: PassportProfile; open: boolean; onToggle: () => void }) {
  const outputs = profile.snapshot.production_outputs || [];
  const results = profile.snapshot.see_results || [];
  const evidence = profile.snapshot.evidence_manifest || [];
  const rules = profile.snapshot.rule_records || [];
  const review = profile.snapshot.methodology_review;
  return <section className="overflow-hidden rounded-3xl border border-emerald-200 bg-white shadow-sm shadow-emerald-100/60">
    <div className="flex flex-col gap-4 border-b border-emerald-100 bg-emerald-50/70 px-6 py-5 md:flex-row md:items-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-emerald-600 shadow-sm"><BadgeCheck size={24} /></span>
      <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h2 className="text-xl font-black text-emerald-950">已发布护照 v{profile.version}</h2><span className="zc-pill zc-pill-green">不可变</span><span className="zc-pill zc-pill-blue">重放 {profile.replay.match ? "通过" : "失败"}</span></div><p className="mt-1 text-sm font-medium text-emerald-800">{profile.period_start.slice(0, 10)} 至 {profile.period_end.slice(0, 10)} · 内容哈希 {profile.content_hash.slice(0, 20)}…</p></div>
      <div className="flex flex-wrap gap-2"><button className="zc-button" onClick={onToggle}><Eye size={16} /> {open ? "收起版本" : "查看版本"}</button><button className="zc-button-soft" onClick={() => downloadJson({ profile }, `${detail.account.account_code}-published-v${profile.version}.json`)}><Download size={16} /> 下载所有者副本</button></div>
    </div>
    {open && <div className="space-y-6 p-6">
      <div className="grid gap-3 md:grid-cols-4"><Fact label="装置" value={detail.installation.name} /><Fact label="生产路线" value={detail.processes[0]?.production_route || "—"} /><Fact label="产品 / CN" value={`${detail.products[0]?.name || "—"} / ${detail.products[0]?.cn_code || "—"}`} /><Fact label="完整度" value={`${profile.completeness_score}% · ${profile.data_quality_grade}`} /></div>
      <div className="grid gap-4 xl:grid-cols-3">
        <PublishedBlock title="期间产量" icon={Archive}>{outputs.length ? outputs.map((item) => <PublishedLine key={item.id} main={`${compact(item.quantity)} ${item.unit}`} sub={`记录 ${item.id.slice(0, 8)}… · v${item.version}`} />) : <EmptyLine />}</PublishedBlock>
        <PublishedBlock title="确定性 SEE" icon={Scale}>{results.length ? results.map((item) => <PublishedLine key={item.id} main={`${compact(item.specific_emissions)} ${item.specific_unit}`} sub={`总排放 ${compact(item.total_emissions)} ${item.emissions_unit} · ${item.data_quality}`} />) : <EmptyLine />}</PublishedBlock>
        <PublishedBlock title="证据与规则" icon={FileCheck2}><PublishedLine main={`${evidence.length} 份证据文件`} sub={evidence[0] ? `${evidence[0].filename} · ${evidence[0].content_hash.slice(0, 12)}…` : "无证据"} /><PublishedLine main={`${rules.length} 个规则版本`} sub={rules[0] ? `${rules[0].publisher} · ${rules[0].document_number}` : "无规则"} /></PublishedBlock>
      </div>
      <div className="rounded-2xl border border-blue-100 bg-blue-50/50 p-5"><div className="flex items-start gap-3"><ShieldCheck className="mt-0.5 shrink-0 text-blue-600" size={20} /><div><b className="text-sm text-slate-900">方法学复核记录</b><p className="mt-2 text-sm leading-6 text-slate-600">{review?.summary || "已发布版本未暴露复核摘要。"}</p><p className="mt-2 text-xs font-bold text-amber-700">方法学复核用于支持内部签字，不等于欧盟 CBAM 法定核查。</p></div></div></div>
    </div>}
  </section>;
}

function PublishedBlock({ title, icon: Icon, children }: { title: string; icon: typeof Archive; children: ReactNode }) { return <div className="rounded-2xl border border-slate-100 bg-slate-50/70 p-5"><div className="mb-4 flex items-center gap-2 text-sm font-black text-slate-900"><Icon size={17} className="text-blue-600" />{title}</div><div className="space-y-3">{children}</div></div>; }
function PublishedLine({ main, sub }: { main: string; sub: string }) { return <div><b className="block text-sm text-slate-900">{main}</b><small className="mt-1 block leading-5 text-slate-500">{sub}</small></div>; }
function EmptyLine() { return <p className="text-sm text-slate-500">该版本没有可展示的记录。</p>; }

function Metric({ icon: Icon, title, value, note, tone }: { icon: typeof Gauge; title: string; value: string; note: string; tone: "blue" | "green" | "purple" | "amber" }) {
  const tones = { blue: "bg-blue-50 text-blue-600", green: "bg-emerald-50 text-emerald-600", purple: "bg-violet-50 text-violet-600", amber: "bg-amber-50 text-amber-600" };
  return <div className="zc-card-pad flex items-center gap-4"><span className={`flex h-12 w-12 items-center justify-center rounded-2xl ${tones[tone]}`}><Icon size={22} /></span><span className="min-w-0"><small className="font-semibold text-slate-500">{title}</small><b className="mt-1 block truncate text-xl text-slate-950">{value}</b><small className="mt-1 block truncate text-slate-400">{note}</small></span></div>;
}

function PeriodBar({ period, setPeriod }: { period: typeof DEFAULT_PERIOD; setPeriod: (period: typeof DEFAULT_PERIOD) => void }) {
  return <section className="zc-card-pad flex flex-col gap-4 md:flex-row md:items-center md:justify-between"><div><h2 className="text-lg font-black text-slate-950">当前核算期间</h2><p className="mt-1 text-sm text-slate-500">所有产量、排放、证据、规则和 SEE 必须落在同一期间。</p></div><div className="flex items-center gap-2"><input aria-label="期间开始" type="date" className="zc-input" value={period.start} onChange={(event) => setPeriod({ ...period, start: event.target.value })} /><ArrowRight size={16} className="text-slate-400" /><input aria-label="期间结束" type="date" className="zc-input" value={period.end} onChange={(event) => setPeriod({ ...period, end: event.target.value })} /></div></section>;
}

function WorkflowCard({ number, title, icon: Icon, done, children }: { number: string; title: string; icon: typeof Building2; done?: boolean; children: ReactNode }) {
  return <section className="zc-card-pad"><div className="mb-5 flex items-center gap-3"><span className={`flex h-11 w-11 items-center justify-center rounded-2xl ${done ? "bg-emerald-50 text-emerald-600" : "bg-blue-50 text-blue-600"}`}>{done ? <Check size={21} /> : <Icon size={21} />}</span><div className="min-w-0 flex-1"><small className="font-mono font-bold text-slate-400">STEP {number}</small><h2 className="truncate text-lg font-black text-slate-950">{title}</h2></div><span className={`zc-pill ${done ? "zc-pill-green" : "zc-pill-amber"}`}>{done ? "已满足" : "待完成"}</span></div>{children}</section>;
}

function Fact({ label, value }: { label: string; value: string }) { return <div className="rounded-xl bg-slate-50 p-3"><small className="font-semibold text-slate-500">{label}</small><b className="mt-1 block text-sm text-slate-900">{value}</b></div>; }

function OutputForm({ output, busy, onSubmit }: { output?: { quantity: string; unit: string }; busy: boolean; onSubmit: (quantity: string) => void }) {
  const [quantity, setQuantity] = useState("1000");
  if (output) return <div className="flex items-center justify-between rounded-2xl border border-emerald-200 bg-emerald-50 p-5"><div><b className="text-emerald-900">已登记期间合格产量</b><p className="mt-1 text-sm text-emerald-700">{compact(output.quantity)} {output.unit} · 正式值使用 Decimal 保存</p></div><BadgeCheck className="text-emerald-600" /></div>;
  return <div className="flex flex-col gap-3 md:flex-row"><label className="flex-1"><span className="mb-2 block text-xs font-bold text-slate-500">合格产品产量（t）</span><input className="zc-input w-full" inputMode="decimal" value={quantity} onChange={(event) => setQuantity(event.target.value)} placeholder="例如 1000" /></label><button disabled={busy || !quantity} onClick={() => onSubmit(quantity)} className="zc-button-primary self-end"><Archive size={17} /> 写入正式产量</button></div>;
}

function RuleForm({ busy, onSubmit }: { busy: boolean; onSubmit: (payload: Record<string, unknown>) => void }) {
  const [form, setForm] = useState({ title: "CBAM embedded emissions methodology", document_number: "EU-2023-1773", vintage: "2023", valid_from: "2023-05-17", source_url: "https://eur-lex.europa.eu/eli/reg_impl/2023/1773/oj", source_content_hash: "" });
  return <div className="grid gap-3 rounded-2xl border border-blue-100 bg-blue-50/40 p-4 md:grid-cols-2"><Field label="规则标题" value={form.title} onChange={(value) => setForm({ ...form, title: value })} /><Field label="EU 文号" value={form.document_number} onChange={(value) => setForm({ ...form, document_number: value })} /><Field label="Vintage" value={form.vintage} onChange={(value) => setForm({ ...form, vintage: value })} /><Field label="生效日期" type="date" value={form.valid_from} onChange={(value) => setForm({ ...form, valid_from: value })} /><div className="md:col-span-2"><Field label="官方 HTTPS 来源" value={form.source_url} onChange={(value) => setForm({ ...form, source_url: value })} /></div><div className="md:col-span-2"><Field label="人工核对后的原文 SHA-256（64 位小写十六进制）" value={form.source_content_hash} onChange={(value) => setForm({ ...form, source_content_hash: value.toLowerCase() })} /><p className="mt-2 text-xs text-amber-700">P0 不会代下载法规原文；登记人必须确认 URL、文号与哈希对应同一版本。</p></div><div className="md:col-span-2 flex justify-end"><button disabled={busy || !/^[0-9a-f]{64}$/.test(form.source_content_hash)} onClick={() => onSubmit({ rule_kind: "cbam_methodology", title: form.title, publisher: "European Commission", document_number: form.document_number, jurisdiction: "EU", vintage: Number(form.vintage), valid_from: `${form.valid_from}T00:00:00Z`, valid_to: null, source_url: form.source_url, source_content_hash: form.source_content_hash })} className="zc-button-primary"><BookOpenCheck size={17} /> 登记不可变规则版本</button></div></div>;
}

function ReleasePanel({ detail, latestDraft, draftReview, published, busy, onFreeze, onReview, onPublish }: { detail: PassportDetail; latestDraft: PassportProfile | null; draftReview: { id: string } | null; published: PassportProfile | null; busy: boolean; onFreeze: () => void; onReview: (profile: PassportProfile, review: Record<string, unknown>) => void; onPublish: (profile: PassportProfile, reviewId: string) => void }) {
  const [reviewOpen, setReviewOpen] = useState(false);
  const [verdict, setVerdict] = useState("pass");
  const [summary, setSummary] = useState("");
  const [findings, setFindings] = useState("");
  if (published && !latestDraft) return <div className="space-y-4"><div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5"><div className="flex items-center gap-3"><BadgeCheck className="text-emerald-600" /><div><b className="text-emerald-900">护照 v{published.version} 已发布</b><p className="mt-1 text-sm text-emerald-700">完整度 {published.completeness_score}% · 内容哈希 {published.content_hash.slice(0, 16)}… · 确定性重放通过</p></div></div></div><button disabled={busy} onClick={onFreeze} className="zc-button-primary"><Archive size={17} /> 冻结当前事实，创建 v{published.version + 1} 草稿</button><p className="text-xs font-medium text-slate-500">旧版本保持不可变；下一版必须重新通过门禁与方法学复核。</p></div>;
  if (!latestDraft) return <button disabled={busy} onClick={onFreeze} className="zc-button-primary"><Archive size={17} /> 冻结当前事实为草稿</button>;
  const onlyReviewMissing = latestDraft.assessment.missing_keys.length === 1 && latestDraft.assessment.missing_keys[0] === "methodology_review";
  return <div className="space-y-4"><div className="rounded-2xl border border-slate-100 bg-slate-50 p-4"><div className="flex items-center justify-between"><div><b className="text-slate-900">草稿 v{latestDraft.version}</b><p className="mt-1 text-sm text-slate-500">完整度 {latestDraft.completeness_score}% · 重放 {latestDraft.replay.match ? "通过" : "失败"}</p></div><span className={`zc-pill ${latestDraft.replay.match ? "zc-pill-green" : "zc-pill-red"}`}>{latestDraft.replay.match ? "可重放" : "阻断"}</span></div></div>{!onlyReviewMissing ? <Callout icon={CircleAlert} title="仍有正式数据缺口" text={`缺少：${latestDraft.assessment.checks.filter((item) => !item.passed && item.key !== "methodology_review").map((item) => item.label).join("、") || "请重新冻结最新事实"}`} action="重新冻结" onClick={onFreeze} /> : !draftReview ? <div className="space-y-3"><button disabled={busy} onClick={() => setReviewOpen((value) => !value)} className="zc-button-primary"><ShieldCheck size={17} /> {reviewOpen ? "收起复核表" : "填写方法学复核"}</button>{reviewOpen && <div className="space-y-3 rounded-2xl border border-blue-100 bg-blue-50/40 p-4"><label><span className="mb-2 block text-xs font-bold text-slate-500">复核结论</span><select className="zc-input w-full" value={verdict} onChange={(event) => setVerdict(event.target.value)}><option value="pass">通过</option><option value="pass_with_actions">有条件通过</option><option value="fail">不通过</option></select></label><label><span className="mb-2 block text-xs font-bold text-slate-500">复核摘要（必须由复核人真实填写）</span><textarea className="zc-input min-h-24 w-full" value={summary} onChange={(event) => setSummary(event.target.value)} placeholder="说明边界、数据、证据、规则和重放检查结果。" /></label><label><span className="mb-2 block text-xs font-bold text-slate-500">发现项（每行一项，可选）</span><textarea className="zc-input min-h-20 w-full" value={findings} onChange={(event) => setFindings(event.target.value)} placeholder="例如：需要在正式核查前补充仪表校准记录" /></label><button disabled={busy || !summary.trim()} onClick={() => onReview(latestDraft, { verdict, summary: summary.trim(), findings: findings.split("\n").map((item) => item.trim()).filter(Boolean).map((message) => ({ severity: "note", message })) })} className="zc-button-primary"><ShieldCheck size={17} /> 提交复核记录</button></div>}</div> : draftReview && <button disabled={busy} onClick={() => onPublish(latestDraft, draftReview.id)} className="zc-button-primary"><Send size={17} /> 发布不可变护照版本</button>}<p className="text-xs font-medium text-slate-500">发布门禁来自 {detail.assessment.checks.length} 项确定性检查；方法学复核不等于法定核查。</p></div>;
}

function ShareForm({ busy, onSubmit }: { busy: boolean; onSubmit: (payload: Record<string, unknown>) => void }) {
  const [form, setForm] = useState({ recipient_name: "", recipient_type: "importer", recipient_tenant_id: "", purpose: "CBAM 数据复核", expires: DEFAULT_SHARE_EXPIRY });
  const [scopes, setScopes] = useState<string[]>(["identity", "processes", "products", "outputs", "emissions", "evidence_manifest", "methodology", "review"]);
  return <div className="rounded-2xl border border-blue-100 bg-blue-50/40 p-4"><div className="grid gap-3 md:grid-cols-2"><Field label="接收方名称" value={form.recipient_name} onChange={(value) => setForm({ ...form, recipient_name: value })} /><label><span className="mb-2 block text-xs font-bold text-slate-500">接收方类型</span><select className="zc-input w-full" value={form.recipient_type} onChange={(event) => setForm({ ...form, recipient_type: event.target.value })}><option value="importer">进口商</option><option value="trader">贸易商</option><option value="verifier">核查机构</option><option value="software_partner">软件合作方</option><option value="customer">客户</option><option value="other">其他</option></select></label><Field label="接收方租户 ID（平台内共享时填写）" value={form.recipient_tenant_id} onChange={(value) => setForm({ ...form, recipient_tenant_id: value })} /><Field label="到期日" type="date" value={form.expires} onChange={(value) => setForm({ ...form, expires: value })} /><div className="md:col-span-2"><Field label="共享目的" value={form.purpose} onChange={(value) => setForm({ ...form, purpose: value })} /></div></div><div className="mt-4"><span className="text-xs font-bold text-slate-500">授权字段范围</span><div className="mt-2 flex flex-wrap gap-2">{SHARE_SCOPES.map(([key, label]) => <button key={key} onClick={() => setScopes((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key])} className={`rounded-lg border px-3 py-2 text-xs font-bold ${scopes.includes(key) ? "border-blue-300 bg-blue-100 text-blue-700" : "border-slate-200 bg-white text-slate-500"}`}>{scopes.includes(key) && <Check size={12} className="mr-1 inline" />}{label}</button>)}</div></div><div className="mt-4 flex justify-end"><button disabled={busy || !form.recipient_name || !scopes.length} onClick={() => onSubmit({ recipient_name: form.recipient_name, recipient_type: form.recipient_type, recipient_tenant_id: form.recipient_tenant_id || null, purpose: form.purpose, scopes, expires_at: `${form.expires}T23:59:59Z` })} className="zc-button-primary"><KeyRound size={17} /> 创建最小权限授权</button></div></div>;
}

function GrantList({ grants, busy, onExport, onRevoke }: { grants: SharingGrant[]; busy: boolean; onExport: (grant: SharingGrant) => void; onRevoke: (grant: SharingGrant) => void }) {
  return <div className="space-y-3">{grants.map((grant) => <div key={grant.id} className="flex flex-col gap-3 rounded-2xl border border-slate-100 p-4 md:flex-row md:items-center"><span className={`flex h-10 w-10 items-center justify-center rounded-xl ${grant.active ? "bg-emerald-50 text-emerald-600" : "bg-slate-100 text-slate-500"}`}>{grant.active ? <Link2 size={19} /> : <Unplug size={19} />}</span><span className="min-w-0 flex-1"><b className="block text-sm text-slate-900">{grant.recipient_name}</b><small className="mt-1 block text-slate-500">{grant.scopes.length} 个字段域 · 到期 {new Date(grant.expires_at).toLocaleDateString("zh-CN")}</small></span>{grant.active && <div className="flex gap-2"><button disabled={busy} className="zc-button-soft" onClick={() => onExport(grant)}><Download size={15} /> 导出</button><button disabled={busy} className="zc-button-danger" onClick={() => onRevoke(grant)}><Unplug size={15} /> 撤销</button></div>}</div>)}{!grants.length && <p className="text-sm text-slate-500">尚未创建共享授权。</p>}</div>;
}

function ReadinessPanel({ detail, published }: { detail: PassportDetail; published: PassportProfile | null }) {
  return <div className="zc-card-pad"><div className="flex items-center justify-between"><div><h3 className="text-lg font-black text-slate-950">{published ? "下一版发布门禁" : "发布门禁"}</h3><p className="mt-1 text-xs text-slate-500">{published ? `已发布 v${published.version} 保持 ${published.completeness_score}%；新版本须重新复核` : "客户端不能覆盖"}</p></div><div className="flex h-14 w-14 items-center justify-center rounded-full border-[6px] border-blue-500 text-sm font-black text-slate-950">{detail.assessment.score}%</div></div><div className="mt-5 space-y-3">{detail.assessment.checks.map((check) => <div key={check.key} className="flex items-center gap-3"><span className={`flex h-7 w-7 items-center justify-center rounded-full ${check.passed ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-400"}`}>{check.passed ? <Check size={14} /> : <span className="h-2 w-2 rounded-full bg-current" />}</span><span className={`text-sm font-semibold ${check.passed ? "text-slate-800" : "text-slate-500"}`}>{check.label}</span></div>)}</div></div>;
}

function Guardrail({ text }: { text: string }) { return <div className="flex gap-3"><ShieldCheck size={17} className="mt-1 shrink-0 text-blue-600" /><span>{text}</span></div>; }

function Callout({ icon: Icon, title, text, action, onClick }: { icon: typeof FilePlus2; title: string; text: string; action?: string; onClick?: () => void }) { return <div className="flex flex-col gap-4 rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-5 md:flex-row md:items-center"><span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white text-blue-600 shadow-sm"><Icon size={20} /></span><span className="min-w-0 flex-1"><b className="block text-sm text-slate-900">{title}</b><small className="mt-1 block leading-5 text-slate-500">{text}</small></span>{action && <button onClick={onClick} className="zc-button-soft">{action}<ChevronRight size={15} /></button>}</div>; }

function CreatePassportModal({ busy, onClose, onSubmit }: { busy: boolean; onClose: () => void; onSubmit: (payload: Record<string, unknown>) => void }) {
  const [form, setForm] = useState({ installation_name: "热轧卷板生产装置", operator_name: "华盛钢铁有限公司", country_code: "CN", unlocode: "CNTGS", process_name: "高炉—转炉—热轧主流程", aggregate_goods_category: "iron_steel", production_route: "bf_bof", product_name: "热轧卷板", cn_code: "72085100" });
  return <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/35 p-4 backdrop-blur-sm"><div className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl md:p-8"><div className="flex items-start justify-between"><div><div className="mb-2 flex items-center gap-2 text-sm font-bold text-blue-600"><Fingerprint size={17} /> 创建稳定装置账户</div><h2 className="text-2xl font-black text-slate-950">先建立最小可信身份</h2><p className="mt-2 text-sm text-slate-500">后续数据更新会新增事实版本，不会覆盖这份历史。</p></div><button onClick={onClose} className="zc-button">关闭</button></div><div className="mt-6 grid gap-4 md:grid-cols-2"><Field label="装置名称" value={form.installation_name} onChange={(value) => setForm({ ...form, installation_name: value })} /><Field label="经营者名称" value={form.operator_name} onChange={(value) => setForm({ ...form, operator_name: value })} /><Field label="国家代码" value={form.country_code} onChange={(value) => setForm({ ...form, country_code: value.toUpperCase() })} /><Field label="UN/LOCODE（可选）" value={form.unlocode} onChange={(value) => setForm({ ...form, unlocode: value.toUpperCase() })} /><Field label="生产工序" value={form.process_name} onChange={(value) => setForm({ ...form, process_name: value })} /><Field label="生产路线" value={form.production_route} onChange={(value) => setForm({ ...form, production_route: value })} /><Field label="产品名称" value={form.product_name} onChange={(value) => setForm({ ...form, product_name: value })} /><Field label="八位 CN 编码" value={form.cn_code} onChange={(value) => setForm({ ...form, cn_code: value.replace(/\D/g, "").slice(0, 8) })} /></div><div className="mt-6 flex justify-end"><button disabled={busy || form.cn_code.length !== 8} onClick={() => onSubmit({ ...form, unlocode: form.unlocode || null, request_key: crypto.randomUUID().replaceAll("-", "") })} className="zc-button-primary px-6 py-3"><Plus size={17} /> 创建护照账户</button></div></div></div>;
}

function EmptyPassport({ onCreate }: { onCreate: () => void }) { return <div className="zc-card-pad flex min-h-[520px] flex-col items-center justify-center text-center"><span className="flex h-20 w-20 items-center justify-center rounded-3xl bg-blue-50 text-blue-600"><Fingerprint size={36} /></span><h2 className="mt-5 text-2xl font-black text-slate-950">这里还没有装置护照</h2><p className="mt-3 max-w-lg text-sm leading-6 text-slate-500">先建立一个稳定的生产装置账户，再把现有的数据收集、排放计算、证据和方法学能力挂到同一条可重放主线上。</p><button onClick={onCreate} className="zc-button-primary mt-6"><Plus size={17} /> 建立第一份护照</button></div>; }

function Field({ label, value, onChange, type = "text" }: { label: string; value: string; onChange: (value: string) => void; type?: string }) { return <label><span className="mb-2 block text-xs font-bold text-slate-500">{label}</span><input type={type} className="zc-input w-full" value={value} onChange={(event) => onChange(event.target.value)} /></label>; }

function compact(value: string): string { const number = Number(value); return Number.isFinite(number) ? number.toLocaleString("zh-CN", { maximumFractionDigits: 6 }) : value; }

function downloadJson(value: Record<string, unknown>, filename: string) { const blob = new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.rel = "noopener"; anchor.click(); URL.revokeObjectURL(url); }
