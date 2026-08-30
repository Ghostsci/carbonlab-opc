export type AgentRunStatus = "queued" | "running" | "waiting_human" | "completed" | "failed" | "cancelled";

export type AgentSkillSummary = {
  skill_id: string;
  role_id?: string;
  display_name?: string;
  version: string;
  category?: string;
  execution_mode?: string;
  allowed_tools?: string[];
  human_handoff?: string[];
  stores_raw_chain_of_thought?: boolean;
  package_sha256: string;
  instruction_sha256?: string;
  eval_case_count?: number;
  package_path?: string;
};

export type AgentRunEvent = {
  id: string;
  sequence: number;
  event_type: string;
  status: "info" | "success" | "warning" | "error" | string;
  title: string;
  summary?: string | null;
  payload: Record<string, unknown>;
  evidence_refs: unknown[];
  prev_event_sha256?: string | null;
  event_sha256: string;
  created_at: string;
};

export type AgentRun = {
  id: string;
  run_id: string;
  agent_id: string;
  agent_name: string;
  agent_kind: "ai_agent" | "human" | "deterministic_engine" | string;
  tenant_id?: string | null;
  enterprise_id?: string | null;
  workflow_id?: string | null;
  workflow_step_id?: string | null;
  source_file_id?: string | null;
  parent_run_id?: string | null;
  attempt_number: number;
  trigger: string;
  trigger_ref?: string | null;
  status: AgentRunStatus;
  status_reason?: string | null;
  skill?: Pick<AgentSkillSummary, "skill_id" | "version" | "package_sha256"> | null;
  redaction_version: string;
  summary?: string | null;
  input_snapshot: Record<string, unknown>;
  output_snapshot: Record<string, unknown>;
  final_action: Record<string, unknown>;
  human_intervention: Record<string, unknown>;
  execution_ms?: number | null;
  total_tokens?: number | null;
  total_cost_cny?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
  events: AgentRunEvent[];
  event_chain_verified?: boolean;
};

export type EmployeeOverview = {
  role_id: string;
  stage_key: string;
  display_name: string;
  kind: "ai_agent" | "human" | "deterministic_engine" | string;
  mission: string;
  allowed_actions: string[];
  forbidden_actions: string[];
  human_gate: boolean;
  skill?: AgentSkillSummary | null;
  operating_status: AgentRunStatus | "idle";
  active_run?: AgentRun | null;
  latest_run?: AgentRun | null;
  metrics: {
    total_runs: number;
    completed_runs: number;
    waiting_human_runs: number;
    failed_runs: number;
  };
};

type HeadersFactory = () => Record<string, string>;

async function apiError(response: Response, fallback: string): Promise<Error> {
  const payload = await response.json().catch(() => null) as { detail?: string; message?: string } | null;
  return new Error(payload?.detail || payload?.message || `${fallback}（${response.status}）`);
}

export async function fetchAgentEmployees(
  getHeaders: HeadersFactory,
  signal?: AbortSignal,
): Promise<EmployeeOverview[]> {
  const response = await fetch("/api/agent-ops/employees", {
    headers: getHeaders(),
    credentials: "include",
    signal,
  });
  if (!response.ok) throw await apiError(response, "读取数字员工状态失败");
  const payload = await response.json() as { employees?: EmployeeOverview[] };
  return payload.employees || [];
}

export async function fetchAgentRuns(
  getHeaders: HeadersFactory,
  params: {
    sourceFileId?: string;
    agentId?: string;
    status?: AgentRunStatus;
    limit?: number;
  } = {},
  signal?: AbortSignal,
): Promise<AgentRun[]> {
  const search = new URLSearchParams();
  if (params.sourceFileId) search.set("source_file_id", params.sourceFileId);
  if (params.agentId) search.set("agent_id", params.agentId);
  if (params.status) search.set("status", params.status);
  search.set("limit", String(params.limit ?? 100));
  const response = await fetch(`/api/agent-ops/runs?${search.toString()}`, {
    headers: getHeaders(),
    credentials: "include",
    signal,
  });
  if (!response.ok) throw await apiError(response, "读取任务运行记录失败");
  const payload = await response.json() as { runs?: AgentRun[] };
  return payload.runs || [];
}

export async function fetchAgentRunDetail(
  getHeaders: HeadersFactory,
  runId: string,
  signal?: AbortSignal,
): Promise<AgentRun> {
  const response = await fetch(`/api/agent-ops/runs/${encodeURIComponent(runId)}`, {
    headers: getHeaders(),
    credentials: "include",
    signal,
  });
  if (!response.ok) throw await apiError(response, "读取执行过程失败");
  return await response.json() as AgentRun;
}

export async function fetchAgentSkillDetail(
  getHeaders: HeadersFactory,
  skillId: string,
  signal?: AbortSignal,
): Promise<AgentSkillSummary & {
  skill_markdown: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  eval_cases: Record<string, unknown>[];
}> {
  const response = await fetch(`/api/agent-ops/skills/${encodeURIComponent(skillId)}`, {
    headers: getHeaders(),
    credentials: "include",
    signal,
  });
  if (!response.ok) throw await apiError(response, "读取 Skill 规范失败");
  return await response.json();
}

export function agentStatusLabel(status: AgentRunStatus | "idle" | string): string {
  if (status === "queued") return "排队中";
  if (status === "running") return "执行中";
  if (status === "waiting_human") return "等待人工";
  if (status === "completed") return "已完成";
  if (status === "failed") return "失败";
  if (status === "cancelled") return "已取消";
  return "空闲";
}

export function agentStatusTone(status: AgentRunStatus | "idle" | string): string {
  if (status === "completed") return "zc-pill-green";
  if (status === "failed") return "zc-pill-red";
  if (status === "waiting_human") return "zc-pill-amber";
  if (status === "running" || status === "queued") return "zc-pill-blue";
  return "zc-pill-slate";
}

export function shortHash(value?: string | null, length = 12): string {
  if (!value) return "-";
  return value.length > length ? `${value.slice(0, length)}…` : value;
}

export function formatRunDuration(milliseconds?: number | null): string {
  if (milliseconds === null || milliseconds === undefined) return "-";
  if (milliseconds < 1000) return `${milliseconds} ms`;
  return `${(milliseconds / 1000).toFixed(milliseconds < 10000 ? 1 : 0)} s`;
}
