import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Code2,
  FileCheck2,
  Fingerprint,
  Loader2,
  ShieldCheck,
  UserCheck,
  X,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import {
  agentStatusLabel,
  agentStatusTone,
  fetchAgentRunDetail,
  formatRunDuration,
  shortHash,
  type AgentRun,
  type AgentRunEvent,
} from "../utils/agentOps";

type AgentRunDetailProps = {
  runId: string | null;
  onClose?: () => void;
  embedded?: boolean;
};

const HIDDEN_KEYS = new Set([
  "chain_of_thought",
  "hidden_reasoning",
  "system_prompt",
  "authorization",
  "api_key",
  "password",
  "credential",
]);

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function visibleEntries(value: Record<string, unknown>): Array<[string, unknown]> {
  return Object.entries(value).filter(([key]) => !HIDDEN_KEYS.has(key.toLowerCase()));
}

function eventIcon(event: AgentRunEvent): ReactNode {
  if (event.status === "error") return <AlertTriangle size={16} />;
  if (event.status === "warning") return <UserCheck size={16} />;
  if (event.status === "success") return <CheckCircle2 size={16} />;
  return <ChevronRight size={16} />;
}

function eventTone(event: AgentRunEvent): string {
  if (event.status === "error") return "border-red-200 bg-red-50 text-red-700";
  if (event.status === "warning") return "border-amber-200 bg-amber-50 text-amber-700";
  if (event.status === "success") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  return "border-blue-200 bg-blue-50 text-blue-700";
}

function dateTime(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

export function AgentRunDetailPanel({ runId, onClose, embedded = false }: AgentRunDetailProps) {
  const { getHeaders } = useAuth();
  const [run, setRun] = useState<AgentRun | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) {
      setRun(null);
      setState("idle");
      return;
    }
    const controller = new AbortController();
    setState("loading");
    setError(null);
    void fetchAgentRunDetail(getHeaders, runId, controller.signal)
      .then((data) => {
        setRun(data);
        setState("ready");
      })
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "读取执行过程失败");
        setState("error");
      });
    return () => controller.abort();
  }, [getHeaders, runId]);

  const snapshotSections = useMemo(() => {
    if (!run) return [];
    return [
      { title: "输入摘要", value: run.input_snapshot, icon: <FileCheck2 size={16} /> },
      { title: "输出摘要", value: run.output_snapshot, icon: <Code2 size={16} /> },
      { title: "最终动作", value: run.final_action, icon: <ShieldCheck size={16} /> },
    ].filter((section) => visibleEntries(section.value).length > 0);
  }, [run]);

  if (!runId) {
    return (
      <div className="flex min-h-[360px] flex-col items-center justify-center px-8 text-center">
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-blue-600">
          <Fingerprint size={23} />
        </div>
        <p className="font-bold text-slate-800">选择一条任务运行</p>
        <p className="mt-2 max-w-xs text-sm leading-6 text-slate-500">这里展示可审计事件、证据引用和 Skill 版本，不展示模型隐藏推理。</p>
      </div>
    );
  }

  if (state === "loading") {
    return (
      <div className="flex min-h-[360px] items-center justify-center text-sm text-slate-500">
        <Loader2 className="mr-2 animate-spin" size={18} /> 正在读取执行过程...
      </div>
    );
  }

  if (state === "error" || !run) {
    return (
      <div className="flex min-h-[360px] flex-col items-center justify-center px-8 text-center">
        <AlertTriangle className="mb-3 text-red-500" size={26} />
        <p className="font-bold text-slate-800">执行过程读取失败</p>
        <p className="mt-2 text-sm text-slate-500">{error || "任务运行不存在"}</p>
      </div>
    );
  }

  return (
    <div className={embedded ? "h-full" : "min-h-full"}>
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 px-5 py-4 backdrop-blur">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-blue-50 text-blue-600">
            {run.agent_kind === "human" ? <UserCheck size={21} /> : run.agent_kind === "deterministic_engine" ? <Code2 size={21} /> : <Bot size={21} />}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-black text-slate-950">{run.agent_id} {run.agent_name}</h2>
              <span className={`zc-pill ${agentStatusTone(run.status)}`}>{agentStatusLabel(run.status)}</span>
            </div>
            <p className="mt-1 truncate text-xs text-slate-500">Run {run.run_id}</p>
          </div>
          {onClose && (
            <button type="button" onClick={onClose} className="rounded-xl p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700" aria-label="关闭执行详情">
              <X size={19} />
            </button>
          )}
        </div>
      </header>

      <div className="space-y-5 p-5">
        <section className="rounded-2xl border border-blue-100 bg-blue-50/60 p-4">
          <div className="flex items-start gap-3">
            <ShieldCheck className="mt-0.5 shrink-0 text-blue-600" size={18} />
            <div>
              <p className="font-bold text-slate-900">{run.summary || "该岗位已记录结构化执行结果。"}</p>
              <p className="mt-2 text-xs leading-5 text-slate-500">本页仅显示可复核的决策摘要、输入输出和证据，不保存或展示模型隐藏思维过程。</p>
            </div>
          </div>
        </section>

        <section className="grid grid-cols-2 gap-3 text-sm">
          <Meta label="开始时间" value={dateTime(run.started_at)} icon={<Clock3 size={15} />} />
          <Meta label="执行耗时" value={formatRunDuration(run.execution_ms)} icon={<Clock3 size={15} />} />
          <Meta label="触发方式" value={run.trigger || "-"} icon={<ChevronRight size={15} />} />
          <Meta label="尝试次数" value={`第 ${run.attempt_number} 次`} icon={<ChevronRight size={15} />} />
        </section>

        <section>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-black text-slate-900">执行事件</h3>
            <span className={`zc-pill ${run.event_chain_verified ? "zc-pill-green" : "zc-pill-red"}`}>
              {run.event_chain_verified ? "哈希链通过" : "哈希链异常"}
            </span>
          </div>
          <div className="space-y-0">
            {run.events.map((event, index) => (
              <div key={event.id} className="relative flex gap-3 pb-5 last:pb-0">
                {index < run.events.length - 1 && <span className="absolute left-[15px] top-8 h-[calc(100%-24px)] w-px bg-slate-200" />}
                <span className={`relative z-[1] flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border ${eventTone(event)}`}>
                  {eventIcon(event)}
                </span>
                <div className="min-w-0 flex-1 pt-0.5">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-bold text-slate-900">{event.sequence}. {event.title}</p>
                      {event.summary && <p className="mt-1 text-sm leading-6 text-slate-600">{event.summary}</p>}
                    </div>
                    <span className="text-[11px] text-slate-400">{dateTime(event.created_at)}</span>
                  </div>
                  {event.evidence_refs.length > 0 && (
                    <div className="mt-2 rounded-xl bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-500">
                      证据引用：{event.evidence_refs.map(displayValue).join("；")}
                    </div>
                  )}
                  <p className="mt-2 font-mono text-[10px] text-slate-400">event {shortHash(event.event_sha256, 16)}</p>
                </div>
              </div>
            ))}
            {run.events.length === 0 && <p className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-500">该运行尚未产生事件。</p>}
          </div>
        </section>

        {run.skill && (
          <section className="rounded-2xl border border-slate-200 p-4">
            <div className="mb-3 flex items-center gap-2">
              <Fingerprint className="text-blue-600" size={17} />
              <h3 className="font-black text-slate-900">固定 Skill</h3>
            </div>
            <div className="grid gap-2 text-sm sm:grid-cols-2">
              <KeyValue label="Skill ID" value={run.skill.skill_id} />
              <KeyValue label="版本" value={run.skill.version} />
              <KeyValue label="包哈希" value={shortHash(run.skill.package_sha256, 18)} mono />
              <KeyValue label="脱敏规则" value={run.redaction_version} />
            </div>
          </section>
        )}

        {snapshotSections.map((section) => (
          <section key={section.title} className="rounded-2xl border border-slate-200 p-4">
            <div className="mb-3 flex items-center gap-2 text-blue-600">
              {section.icon}
              <h3 className="font-black text-slate-900">{section.title}</h3>
            </div>
            <div className="space-y-2">
              {visibleEntries(section.value).map(([key, value]) => (
                <div key={key} className="grid gap-1 rounded-xl bg-slate-50 px-3 py-2.5 text-sm sm:grid-cols-[128px_minmax(0,1fr)]">
                  <span className="break-words text-slate-500">{key}</span>
                  <pre className="whitespace-pre-wrap break-all font-sans font-semibold leading-5 text-slate-700">{displayValue(value)}</pre>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

export function AgentRunDrawer({ runId, onClose }: { runId: string | null; onClose: () => void }) {
  if (!runId) return null;
  return (
    <div className="fixed inset-0 z-[80] flex justify-end bg-slate-950/28" role="dialog" aria-modal="true" aria-label="数字员工执行详情">
      <button type="button" className="absolute inset-0 cursor-default" onClick={onClose} aria-label="关闭详情" />
      <aside className="relative h-full w-full overflow-y-auto bg-white shadow-2xl sm:max-w-xl">
        <AgentRunDetailPanel runId={runId} onClose={onClose} />
      </aside>
    </div>
  );
}

function Meta({ label, value, icon }: { label: string; value: string; icon: ReactNode }) {
  return (
    <div className="rounded-2xl bg-slate-50 p-3">
      <div className="flex items-center gap-1.5 text-xs text-slate-400">{icon}{label}</div>
      <p className="mt-1 break-words font-bold text-slate-800">{value}</p>
    </div>
  );
}

function KeyValue({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-xl bg-slate-50 px-3 py-2.5">
      <p className="text-xs text-slate-400">{label}</p>
      <p className={`mt-1 break-all font-semibold text-slate-700 ${mono ? "font-mono text-xs" : ""}`}>{value}</p>
    </div>
  );
}
