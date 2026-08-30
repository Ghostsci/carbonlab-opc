export type WorkforceRoleKind = "ai_agent" | "human" | "deterministic_engine";
export type WorkforceStageStatus = "pending" | "active" | "completed" | "warning" | "blocked";

export interface WorkforceRoleContract {
  role_id: string;
  stage_key: string;
  display_name: string;
  kind: WorkforceRoleKind;
  mission: string;
  allowed_actions: string[];
  forbidden_actions: string[];
  human_gate: boolean;
}

export interface WorkforceContractPayload {
  contract_version: string;
  workflow_name: string;
  principle: string;
  sequence: string[];
  roles: WorkforceRoleContract[];
}

export interface WorkforceDocumentSnapshot {
  contract_version?: string;
  current_stage?: string;
  stages?: Record<string, {
    status?: string;
    at?: string;
    role_id?: string;
    [key: string]: unknown;
  }>;
}

export const FALLBACK_WORKFORCE: WorkforceContractPayload = {
  contract_version: "carbon-passport-workforce-v1.0",
  workflow_name: "工厂碳数据护照受控工作流",
  principle: "AI 提议，规则检查，人类确认，确定性计算，授权发布。",
  sequence: [
    "source_submission",
    "document_intake",
    "evidence_extraction",
    "evidence_quality_review",
    "enterprise_confirmation",
    "methodology_review",
    "deterministic_calculation",
    "passport_compilation",
    "authorized_release",
  ],
  roles: [
    ["H-00", "source_submission", "企业数据提供人", "human", "上传原始资料并说明业务事实", true],
    ["A-01", "document_intake", "碳数据收件员", "ai_agent", "分类、去重和完整性检查", false],
    ["A-02", "evidence_extraction", "碳证据提取员", "ai_agent", "提出带来源的字段候选", false],
    ["A-03", "evidence_quality_review", "碳数据质检员", "ai_agent", "独立检查证据、单位和异常", false],
    ["H-01", "enterprise_confirmation", "企业数据确认人", "human", "修改、拒绝或确认业务事实", true],
    ["H-02", "methodology_review", "方法与复核负责人", "human", "批准边界、方法和排放因子", true],
    ["R-01", "deterministic_calculation", "碳核算执行员", "deterministic_engine", "执行精确、可重放的规则计算", false],
    ["A-04", "passport_compilation", "碳护照编制员", "ai_agent", "装配正式记录与护照草稿", false],
    ["H-03", "authorized_release", "授权发布负责人", "human", "最终复核、冻结和授权分享", true],
  ].map(([role_id, stage_key, display_name, kind, mission, human_gate]) => ({
    role_id: String(role_id),
    stage_key: String(stage_key),
    display_name: String(display_name),
    kind: kind as WorkforceRoleKind,
    mission: String(mission),
    allowed_actions: [],
    forbidden_actions: [],
    human_gate: Boolean(human_gate),
  })),
};

export async function fetchWorkforceContracts(
  headers: Record<string, string>,
): Promise<WorkforceContractPayload> {
  const response = await fetch("/api/upload/workforce/roles", {
    headers,
    credentials: "include",
  });
  if (!response.ok) throw new Error(`读取数字员工契约失败（${response.status}）`);
  return response.json() as Promise<WorkforceContractPayload>;
}
