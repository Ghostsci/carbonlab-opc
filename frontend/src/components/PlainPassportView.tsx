import {
  ArrowRight,
  BadgeCheck,
  Building2,
  Calculator,
  Check,
  CircleAlert,
  Database,
  FileCheck2,
  Fingerprint,
  Gauge,
  ShieldCheck,
  UserCheck,
} from "lucide-react";
import type {
  PassportDetail,
  PassportProfile,
  PlainEmissionPassport,
} from "../utils/passports";

interface PlainPassportViewProps {
  detail: PassportDetail | null;
  context: PlainEmissionPassport | null;
  published: PassportProfile | null;
  includedInPublished: boolean;
  attributed: boolean;
  busy: boolean;
  onCreateAccount: () => void;
  onAttribute: () => void;
  onOpenProfessional: () => void;
}

export default function PlainPassportView({
  detail,
  context,
  published,
  includedInPublished,
  attributed,
  busy,
  onCreateAccount,
  onAttribute,
  onOpenProfessional,
}: PlainPassportViewProps) {
  if (!context && detail) {
    return (
      <AccountOverview
        detail={detail}
        published={published}
        onOpenProfessional={onOpenProfessional}
      />
    );
  }
  if (!context) return null;

  const matched = Boolean(context.matched_account_id && detail);
  const status = includedInPublished && published
    ? `已进入发布 v${published.version}`
    : attributed
      ? "已归入装置，待下一版发布"
      : matched
        ? "已匹配装置，待确认归集"
        : "活动排放护照草稿";
  const period = `${shortDate(context.period.start)} 至 ${shortDate(context.period.end)}`;
  const completedChecks = context.confirmations.filter((item) => item.status === "completed").length;

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-3xl border border-blue-100 bg-[radial-gradient(circle_at_90%_0%,rgba(37,99,235,0.18),transparent_30%),linear-gradient(135deg,#ffffff_0%,#f5f9ff_100%)] p-6 shadow-sm md:p-8">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
          <div className="max-w-4xl">
            <div className="flex flex-wrap items-center gap-2">
              <span className="zc-pill zc-pill-blue">一眼看懂版</span>
              <span className={`zc-pill ${includedInPublished ? "zc-pill-green" : "zc-pill-amber"}`}>{status}</span>
            </div>
            <h2 className="mt-4 text-2xl font-black text-slate-950 md:text-3xl">这份护照现在能证明什么？</h2>
            <p className="mt-4 text-base font-semibold leading-8 text-slate-700 md:text-lg">
              在 <b>{period}</b>，<b>{context.installation.name}</b> 使用了
              <b className="mx-1 text-blue-700">{humanNumber(context.activity.quantity)} {context.activity.unit}</b>，
              按人工确认的排放因子计算，本笔活动排放为
              <b className="mx-1 text-emerald-700">{humanNumber(context.calculation.result)} {context.calculation.unit}</b>。
            </p>
            <p className="mt-3 text-sm leading-6 text-slate-500">
              它不是政府证件，而是一份把“谁、哪份文件、多少用量、哪个因子、怎么算、谁确认”连在一起的可追溯档案。
            </p>
            {published && !includedInPublished && (
              <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold leading-6 text-amber-900">
                该装置已有历史发布版 v{published.version}，但本笔新记录尚未进入该版本，不能把历史发布状态套用到本笔数据上。
              </p>
            )}
          </div>
          <div className="grid min-w-[280px] grid-cols-2 gap-3">
            <SummaryMetric label="证据文件" value={context.document.id ? "1 份" : "待补"} />
            <SummaryMetric label="确认环节" value={`${completedChecks}/4`} />
            <SummaryMetric label="确定性复算" value={context.calculation.replay_match ? "通过" : "待检查"} good={context.calculation.replay_match} />
            <SummaryMetric
              label="本笔记录层级"
              value={includedInPublished && published ? `发布版 v${published.version}` : attributed ? "装置草稿" : "活动草稿"}
            />
          </div>
        </div>
      </section>

      <section className="zc-card-pad">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-bold text-blue-600"><Fingerprint size={17} /> 同一笔数据的完整来路</div>
            <h3 className="mt-2 text-xl font-black text-slate-950">顺着 1 → 6 看，就能知道结果为什么可信</h3>
          </div>
          <span className="text-xs font-semibold text-slate-400">所有数值均来自正式记录，不在浏览器中临时拼算</span>
        </div>

        <div className="mt-6 grid gap-4 lg:grid-cols-3">
          <EvidenceStep
            number="1"
            icon={Building2}
            title="这是哪家工厂"
            headline={context.installation.name}
            lines={[context.installation.operator_name, context.installation.address, `统计期间：${period}`]}
          />
          <EvidenceStep
            number="2"
            icon={FileCheck2}
            title="证据来自哪份文件"
            headline={context.document.filename || "尚未关联源文件"}
            lines={[
              context.document.content_hash ? `文件指纹：${context.document.content_hash.slice(0, 18)}…` : "文件指纹待补",
              "以后可以凭指纹回到同一份原始文件",
            ]}
          />
          <EvidenceStep
            number="3"
            icon={Gauge}
            title="原始活动数据是多少"
            headline={`${humanNumber(context.activity.quantity)} ${context.activity.unit}`}
            lines={[context.activity.source_name, scopeLabel(context.activity.scope), `活动记录：${context.activity.id.slice(0, 12)}…`]}
          />
          <EvidenceStep
            number="4"
            icon={Database}
            title="用了哪个排放因子"
            headline={`${humanNumber(context.factor.value)} ${context.factor.unit}`}
            lines={[
              context.factor.name,
              `${context.factor.year} 年 · ${context.factor.region || "区域未标注"}`,
              `来源：${context.factor.source}`,
            ]}
          />
          <EvidenceStep
            number="5"
            icon={Calculator}
            title="系统是怎么算的"
            headline={`${humanNumber(context.calculation.result)} ${context.calculation.unit}`}
            lines={[context.calculation.human_formula, context.calculation.replay_match ? "同样输入再次计算，结果一致" : "复算结果需要人工检查"]}
            tone={context.calculation.replay_match ? "green" : "amber"}
          />
          <EvidenceStep
            number="6"
            icon={UserCheck}
            title="谁对哪一步负责"
            headline={`${completedChecks} 个环节已留痕`}
            lines={context.confirmations.map((item) => `${item.gate} ${item.role}：${statusLabel(item.status)}`)}
          />
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_390px]">
        <div className="zc-card-pad">
          <div className="flex items-start gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700"><ShieldCheck size={21} /></span>
            <div>
              <h3 className="text-lg font-black text-slate-950">人工与 AI 的责任边界</h3>
              <p className="mt-1 text-sm leading-6 text-slate-500">AI 负责提取和整理，人确认事实与因子，确定性引擎负责算术。</p>
            </div>
          </div>
          <div className="mt-5 grid gap-3 md:grid-cols-2">
            {context.confirmations.map((item) => (
              <div key={item.gate} className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                <div className="flex items-center gap-2">
                  <span className={`flex h-7 w-7 items-center justify-center rounded-full ${item.status === "completed" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                    {item.status === "completed" ? <Check size={14} /> : <CircleAlert size={14} />}
                  </span>
                  <b className="text-sm text-slate-900">{item.gate} · {item.role}</b>
                </div>
                <p className="mt-2 text-xs leading-5 text-slate-500">{item.meaning}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-3xl border border-amber-200 bg-amber-50 p-6">
          <div className="flex items-center gap-2 text-amber-900"><CircleAlert size={20} /><h3 className="text-lg font-black">它目前还不能证明什么</h3></div>
          <div className="mt-4 space-y-3">
            {published && !includedInPublished && (
              <div className="flex gap-2 text-sm leading-6 text-amber-900"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />本笔记录尚未包含在现有 v{published.version} 发布版中。</div>
            )}
            {context.limitations.map((item) => (
              <div key={item} className="flex gap-2 text-sm leading-6 text-amber-900"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />{item}</div>
            ))}
          </div>
        </div>
      </section>

      <section className="flex flex-col gap-4 rounded-3xl border border-blue-100 bg-blue-50/60 p-6 md:flex-row md:items-center">
        <div className="min-w-0 flex-1">
          <h3 className="text-lg font-black text-slate-950">下一步只做一件事</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {!matched
              ? "补充工序、产品和 CN 编码，建立与本装置同名的稳定护照账户。系统不会把这笔数据误挂到别的装置。"
              : !attributed
                ? "确认这笔活动排放属于当前装置工序。完成后再登记产量，才能计算单位产品排放。"
                : "本笔排放已经归入装置；下一步创建新版草稿，登记报告期产量并进行方法学复核，再由 H-03 决定是否发布。"}
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          {!matched ? (
            <button type="button" className="zc-button-primary" onClick={onCreateAccount}><Building2 size={17} /> 补充资料并建立装置护照</button>
          ) : !attributed ? (
            <button type="button" className="zc-button-primary" disabled={busy} onClick={onAttribute}><BadgeCheck size={17} /> 确认归入当前装置</button>
          ) : (
            <span className="zc-pill zc-pill-green px-4 py-3"><Check size={15} /> 已归入当前装置</span>
          )}
          <button type="button" className="zc-button" onClick={onOpenProfessional}>进入专业操作视图 <ArrowRight size={16} /></button>
        </div>
      </section>
    </div>
  );
}

function AccountOverview({
  detail,
  published,
  onOpenProfessional,
}: {
  detail: PassportDetail;
  published: PassportProfile | null;
  onOpenProfessional: () => void;
}) {
  const snapshot = detail.current_snapshot;
  const output = snapshot.production_outputs?.[0];
  const see = snapshot.see_results?.[0];
  const evidence = snapshot.evidence_manifest || [];
  const missing = detail.assessment.checks.filter((item) => !item.passed);
  return (
    <div className="space-y-6">
      <section className="zc-card-pad">
        <div className="flex flex-col gap-5 md:flex-row md:items-center">
          <span className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-blue-600 text-white"><Fingerprint size={30} /></span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2"><span className="zc-pill zc-pill-blue">一眼看懂版</span><span className={`zc-pill ${published ? "zc-pill-green" : "zc-pill-amber"}`}>{published ? `已发布 v${published.version}` : "建档中"}</span></div>
            <h2 className="mt-3 text-2xl font-black text-slate-950">{detail.installation.name}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-500">这是一份装置级可追溯档案，不是政府证件。选择一笔活动排放后，页面会继续展示原文件、因子、公式与确认链。</p>
          </div>
          <button type="button" className="zc-button-primary" onClick={onOpenProfessional}>进入专业操作视图 <ArrowRight size={16} /></button>
        </div>
      </section>
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SimpleFact icon={Building2} label="工厂与产品" value={`${detail.installation.operator_name} · ${detail.products[0]?.name || "产品待补"}`} />
        <SimpleFact icon={Gauge} label="报告期产量" value={output ? `${humanNumber(output.quantity)} ${output.unit}` : "待登记"} />
        <SimpleFact icon={Calculator} label="单位产品排放" value={see ? `${humanNumber(see.specific_emissions)} ${see.specific_unit}` : "待计算"} />
        <SimpleFact icon={FileCheck2} label="证据文件" value={`${evidence.length} 份`} />
      </section>
      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="zc-card-pad">
          <h3 className="text-lg font-black text-slate-950">这份护照已经装进了什么</h3>
          <div className="mt-5 grid gap-3 md:grid-cols-2">
            {detail.assessment.checks.filter((item) => item.passed).map((item) => (
              <div key={item.key} className="flex items-center gap-3 rounded-xl bg-emerald-50 p-3 text-sm font-semibold text-emerald-900"><Check size={16} />{item.label}</div>
            ))}
          </div>
        </div>
        <div className="rounded-3xl border border-amber-200 bg-amber-50 p-6">
          <h3 className="text-lg font-black text-amber-950">接下来还缺什么</h3>
          <div className="mt-4 space-y-3">
            {missing.length ? missing.map((item) => <p key={item.key} className="text-sm leading-6 text-amber-900">• {item.label}</p>) : <p className="text-sm text-emerald-700">确定性门禁均已满足。</p>}
          </div>
        </div>
      </section>
    </div>
  );
}

function EvidenceStep({
  number,
  icon: Icon,
  title,
  headline,
  lines,
  tone = "blue",
}: {
  number: string;
  icon: typeof Building2;
  title: string;
  headline: string;
  lines: string[];
  tone?: "blue" | "green" | "amber";
}) {
  const tones = {
    blue: "bg-blue-50 text-blue-700",
    green: "bg-emerald-50 text-emerald-700",
    amber: "bg-amber-50 text-amber-700",
  };
  return (
    <div className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-3">
        <span className={`flex h-10 w-10 items-center justify-center rounded-xl ${tones[tone]}`}><Icon size={19} /></span>
        <div><small className="font-black text-blue-600">第 {number} 步</small><h4 className="text-sm font-black text-slate-900">{title}</h4></div>
      </div>
      <b className="mt-4 block break-words text-base text-slate-950">{headline}</b>
      <div className="mt-3 space-y-1.5">{lines.map((line, index) => <p key={`${line}-${index}`} className="break-words text-xs leading-5 text-slate-500">{line}</p>)}</div>
    </div>
  );
}

function SummaryMetric({ label, value, good = false }: { label: string; value: string; good?: boolean }) {
  return <div className="rounded-2xl border border-white bg-white/85 p-4 text-center shadow-sm"><small className="text-slate-500">{label}</small><b className={`mt-1 block text-lg ${good ? "text-emerald-600" : "text-slate-950"}`}>{value}</b></div>;
}

function SimpleFact({ icon: Icon, label, value }: { icon: typeof Building2; label: string; value: string }) {
  return <div className="zc-card-pad"><div className="flex items-center gap-2 text-xs font-bold text-slate-500"><Icon size={16} className="text-blue-600" />{label}</div><b className="mt-3 block text-base text-slate-950">{value}</b></div>;
}

function shortDate(value: string): string {
  return value.slice(0, 10);
}

function humanNumber(value: string): string {
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? parsed.toLocaleString("zh-CN", { maximumFractionDigits: 8 })
    : value;
}

function scopeLabel(value: string): string {
  if (value === "scope_1") return "范围一：企业直接排放";
  if (value === "scope_2") return "范围二：购入能源间接排放";
  return value;
}

function statusLabel(value: string): string {
  if (value === "completed") return "已完成";
  if (value === "needs_review") return "待检查";
  return "未留痕";
}
