import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  Clock3,
  Code2,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
  UserCheck,
} from "lucide-react";
import { AgentRunDetailPanel } from "../components/AgentRunDetail";
import { useAuth } from "../contexts/AuthContext";
import {
  agentStatusLabel,
  agentStatusTone,
  fetchAgentEmployees,
  fetchAgentRuns,
  formatRunDuration,
  shortHash,
  type AgentRun,
  type EmployeeOverview,
} from "../utils/agentOps";

type PageState = "loading" | "ready" | "error";
type RunFilter = "all" | "active" | "completed" | "failed";

const KIND_LABELS: Record<string, string> = {
  ai_agent: "AI 数字员工",
  human: "人工责任岗",
  deterministic_engine: "确定性执行器",
};

function dateTime(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function roleIcon(kind: string) {
  if (kind === "human") return <UserCheck size={19} />;
  if (kind === "deterministic_engine") return <Code2 size={19} />;
  return <Bot size={19} />;
}

export default function AgentOps() {
  const { getHeaders, isAuthenticated, isLoading: authLoading } = useAuth();
  const [employees, setEmployees] = useState<EmployeeOverview[]>([]);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState<string>("all");
  const [runFilter, setRunFilter] = useState<RunFilter>("all");
  const [search, setSearch] = useState("");
  const [state, setState] = useState<PageState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const load = useCallback(async (signal?: AbortSignal, quiet = false) => {
    if (!quiet) setState("loading");
    else setRefreshing(true);
    setError(null);
    try {
      const [nextEmployees, nextRuns] = await Promise.all([
        fetchAgentEmployees(getHeaders, signal),
        fetchAgentRuns(getHeaders, { limit: 200 }, signal),
      ]);
      setEmployees(nextEmployees);
      setRuns(nextRuns);
      setSelectedRunId((current) => (
        current && nextRuns.some((run) => run.run_id === current) ? current : nextRuns[0]?.run_id ?? null
      ));
      setLastUpdated(new Date());
      setState("ready");
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setError(reason instanceof Error ? reason.message : "读取数字员工运行状态失败");
      setState("error");
    } finally {
      setRefreshing(false);
    }
  }, [getHeaders]);

  useEffect(() => {
    if (authLoading || !isAuthenticated) return;
    const controller = new AbortController();
    void load(controller.signal);
    const timer = window.setInterval(() => void load(undefined, true), 10000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [authLoading, isAuthenticated, load]);

  const filteredRuns = useMemo(() => {
    const query = search.trim().toLowerCase();
    return runs.filter((run) => {
      if (selectedAgentId !== "all" && run.agent_id !== selectedAgentId) return false;
      if (runFilter === "active" && !["queued", "running", "waiting_human"].includes(run.status)) return false;
      if (runFilter === "completed" && run.status !== "completed") return false;
      if (runFilter === "failed" && run.status !== "failed") return false;
      if (!query) return true;
      return [run.agent_id, run.agent_name, run.summary, run.run_id, run.trigger_ref]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query));
    });
  }, [runFilter, runs, search, selectedAgentId]);

  const summary = useMemo(() => ({
    active: runs.filter((run) => ["queued", "running"].includes(run.status)).length,
    waiting: runs.filter((run) => run.status === "waiting_human").length,
    completed: runs.filter((run) => run.status === "completed").length,
    failed: runs.filter((run) => run.status === "failed").length,
  }), [runs]);

  return (
    <div className="mx-auto max-w-[1800px] pt-12 lg:pt-0">
      <header className="mb-6 pr-0 lg:pr-[360px]">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-blue-600">
              <Activity size={17} /> AgentOps 控制平面
            </div>
            <h1 className="text-3xl font-black tracking-tight text-slate-950">数字员工运行与治理</h1>
            <p className="mt-2 text-sm leading-6 text-slate-500">查看谁在做什么、依据哪个 Skill、产生了哪些可复核事件，以及任务停在哪个人工责任门。</p>
          </div>
          <button type="button" onClick={() => void load(undefined, true)} disabled={refreshing} className="zc-button disabled:opacity-60">
            <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
            {refreshing ? "刷新中" : "刷新"}
          </button>
        </div>
      </header>

      <section className="mb-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard icon={<Activity size={21} />} label="正在运行" value={summary.active} tone="blue" description="排队或执行中的自动任务" />
        <SummaryCard icon={<Clock3 size={21} />} label="等待人工" value={summary.waiting} tone="amber" description="必须由责任人明确放行" />
        <SummaryCard icon={<CheckCircle2 size={21} />} label="已完成" value={summary.completed} tone="green" description="事件链完整的历史运行" />
        <SummaryCard icon={<AlertTriangle size={21} />} label="失败" value={summary.failed} tone="red" description="保留错误与重试证据" />
      </section>

      {state === "loading" && (
        <div className="zc-card-pad flex min-h-[420px] items-center justify-center text-sm text-slate-500">
          <Loader2 className="mr-2 animate-spin" size={19} /> 正在读取数字员工运行状态...
        </div>
      )}

      {state === "error" && (
        <div className="zc-card-pad flex min-h-[320px] flex-col items-center justify-center text-center">
          <AlertTriangle className="mb-3 text-red-500" size={28} />
          <p className="font-black text-slate-900">AgentOps 暂时不可用</p>
          <p className="mt-2 text-sm text-slate-500">{error}</p>
          <button type="button" className="zc-button mt-5" onClick={() => void load()}>重新加载</button>
        </div>
      )}

      {state === "ready" && (
        <>
          <section className="mb-5 zc-card-pad">
            <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-lg font-black text-slate-950">岗位与边界</h2>
                <p className="mt-1 text-sm text-slate-500">AI、人工责任岗和确定性引擎在同一条工作流中分工，但权限不能互相替代。</p>
              </div>
              <p className="text-xs text-slate-400">{lastUpdated ? `更新于 ${lastUpdated.toLocaleTimeString("zh-CN", { hour12: false })}` : ""}</p>
            </div>
            <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
              {employees.map((employee) => (
                <button
                  type="button"
                  key={employee.role_id}
                  onClick={() => {
                    setSelectedAgentId(employee.role_id);
                    if (employee.latest_run) setSelectedRunId(employee.latest_run.run_id);
                  }}
                  className={`rounded-2xl border p-4 text-left transition active:scale-[0.99] ${selectedAgentId === employee.role_id ? "border-blue-300 bg-blue-50/65 shadow-sm" : "border-slate-200 bg-white hover:border-blue-200 hover:bg-blue-50/30"}`}
                >
                  <div className="flex items-start gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-blue-600">{roleIcon(employee.kind)}</div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-black text-slate-900">{employee.role_id} {employee.display_name}</p>
                        <span className={`zc-pill ${agentStatusTone(employee.operating_status)}`}>{agentStatusLabel(employee.operating_status)}</span>
                      </div>
                      <p className="mt-1 text-xs text-slate-400">{KIND_LABELS[employee.kind] || employee.kind}</p>
                    </div>
                  </div>
                  <p className="mt-3 line-clamp-2 min-h-10 text-sm leading-5 text-slate-600">{employee.mission}</p>
                  <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-3 text-xs">
                    <span className="font-semibold text-slate-500">运行 {employee.metrics.total_runs} 次</span>
                    {employee.skill ? (
                      <span className="font-mono text-blue-600">Skill {employee.skill.version}</span>
                    ) : (
                      <span className="text-slate-400">责任边界</span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </section>

          <section className="grid min-h-[720px] gap-5 2xl:grid-cols-[minmax(0,1.4fr)_minmax(420px,0.8fr)]">
            <div className="zc-card overflow-hidden">
              <div className="border-b border-slate-200 p-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-black text-slate-950">任务运行</h2>
                    <p className="mt-1 text-sm text-slate-500">每条记录都绑定租户、业务对象、岗位与版本化 Skill。</p>
                  </div>
                  {selectedAgentId !== "all" && (
                    <button type="button" className="text-sm font-semibold text-blue-600" onClick={() => setSelectedAgentId("all")}>清除岗位筛选</button>
                  )}
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <label className="relative min-w-[240px] flex-1">
                    <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                    <input value={search} onChange={(event) => setSearch(event.currentTarget.value)} className="zc-input w-full pl-9" placeholder="搜索岗位、Run ID 或摘要" />
                  </label>
                  <select value={runFilter} onChange={(event) => setRunFilter(event.currentTarget.value as RunFilter)} className="zc-input min-w-36">
                    <option value="all">全部状态</option>
                    <option value="active">进行中</option>
                    <option value="completed">已完成</option>
                    <option value="failed">失败</option>
                  </select>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="zc-table min-w-[820px]">
                  <thead>
                    <tr>
                      <th>岗位与任务</th>
                      <th>状态</th>
                      <th>Skill</th>
                      <th>耗时</th>
                      <th>开始时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRuns.map((run) => (
                      <tr key={run.run_id} onClick={() => setSelectedRunId(run.run_id)} className={`cursor-pointer ${selectedRunId === run.run_id ? "bg-blue-50/80" : ""}`}>
                        <td>
                          <div className="flex items-start gap-3">
                            <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-blue-600">{roleIcon(run.agent_kind)}</span>
                            <div className="min-w-0">
                              <p className="font-bold text-slate-900">{run.agent_id} {run.agent_name}</p>
                              <p className="mt-1 max-w-[420px] truncate text-xs text-slate-500">{run.summary || run.run_id}</p>
                            </div>
                          </div>
                        </td>
                        <td><span className={`zc-pill ${agentStatusTone(run.status)}`}>{agentStatusLabel(run.status)}</span></td>
                        <td>
                          {run.skill ? (
                            <div>
                              <p className="font-mono text-xs font-semibold text-blue-700">{run.skill.version}</p>
                              <p className="mt-1 font-mono text-[10px] text-slate-400">{shortHash(run.skill.package_sha256)}</p>
                            </div>
                          ) : <span className="text-xs text-slate-400">责任岗 / 内核</span>}
                        </td>
                        <td>{formatRunDuration(run.execution_ms)}</td>
                        <td className="whitespace-nowrap text-xs text-slate-500">{dateTime(run.started_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {filteredRuns.length === 0 && (
                  <div className="flex min-h-[300px] flex-col items-center justify-center px-6 text-center">
                    <Activity className="mb-3 text-slate-300" size={28} />
                    <p className="font-bold text-slate-700">当前筛选下没有任务</p>
                    <p className="mt-2 text-sm text-slate-400">上传或处理一份文件后，真实运行记录会自动出现在这里。</p>
                  </div>
                )}
              </div>
            </div>

            <aside className="zc-card overflow-hidden">
              <AgentRunDetailPanel runId={selectedRunId} embedded />
            </aside>
          </section>

          <section className="mt-5 rounded-2xl border border-blue-100 bg-blue-50/55 p-4">
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 shrink-0 text-blue-600" size={19} />
              <div>
                <p className="font-black text-slate-900">治理原则：数字员工可以提议和检查，但不能越过人工责任门，也不能替代确定性计算。</p>
                <p className="mt-1 text-sm leading-6 text-slate-500">系统保留的是可复核事件、证据、结果和 Skill 指纹，而不是不可验证的模型隐藏推理。</p>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function SummaryCard({
  icon,
  label,
  value,
  tone,
  description,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  tone: "blue" | "amber" | "green" | "red";
  description: string;
}) {
  const tones = {
    blue: "bg-blue-50 text-blue-600",
    amber: "bg-amber-50 text-amber-600",
    green: "bg-emerald-50 text-emerald-600",
    red: "bg-red-50 text-red-600",
  };
  return (
    <div className="zc-card-pad flex items-center gap-4">
      <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl ${tones[tone]}`}>{icon}</div>
      <div>
        <p className="text-sm font-semibold text-slate-500">{label}</p>
        <p className="mt-0.5 text-2xl font-black text-slate-950">{value}</p>
        <p className="mt-1 text-xs text-slate-400">{description}</p>
      </div>
    </div>
  );
}
