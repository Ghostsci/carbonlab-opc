import { ArrowRight, Bot, Calculator, Check, CircleAlert, ShieldCheck, UserRound } from "lucide-react";
import {
  FALLBACK_WORKFORCE,
  type WorkforceContractPayload,
  type WorkforceRoleContract,
  type WorkforceStageStatus,
} from "../utils/workforce";

type StageState = {
  status: WorkforceStageStatus;
  note?: string;
};

type Props = {
  contracts?: WorkforceContractPayload | null;
  stages: Record<string, StageState>;
  focus?: "intake" | "passport";
};

const statusStyle: Record<WorkforceStageStatus, string> = {
  pending: "border-slate-200 bg-white text-slate-500",
  active: "border-blue-300 bg-blue-50 text-blue-800 ring-2 ring-blue-100",
  completed: "border-emerald-200 bg-emerald-50 text-emerald-800",
  warning: "border-amber-300 bg-amber-50 text-amber-800",
  blocked: "border-red-300 bg-red-50 text-red-800",
};

const statusLabel: Record<WorkforceStageStatus, string> = {
  pending: "等待",
  active: "当前",
  completed: "完成",
  warning: "需关注",
  blocked: "阻断",
};

function RoleIcon({ role }: { role: WorkforceRoleContract }) {
  if (role.kind === "human") return <UserRound size={17} />;
  if (role.kind === "deterministic_engine") return <Calculator size={17} />;
  return <Bot size={17} />;
}

export default function CarbonWorkforceRail({ contracts, stages, focus = "intake" }: Props) {
  const payload = contracts || FALLBACK_WORKFORCE;
  const roles = payload.sequence
    .map((key) => payload.roles.find((role) => role.stage_key === key))
    .filter((role): role is WorkforceRoleContract => Boolean(role));

  return (
    <section className="zc-card-pad overflow-hidden">
      <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-black text-blue-700">
            <ShieldCheck size={17} /> 受控数字员工协作链
          </div>
          <p className="mt-1 text-xs font-semibold text-slate-500">{payload.principle}</p>
        </div>
        <span className="zc-pill zc-pill-slate">契约 {payload.contract_version}</span>
      </div>

      <div className="overflow-x-auto pb-2">
        <div className="flex min-w-max items-stretch gap-2">
          {roles.map((role, index) => {
            const state = stages[role.stage_key] || { status: "pending" as const };
            const dimmed = focus === "intake"
              ? index > 4
              : index < 4;
            return (
              <div key={role.role_id} className="flex items-center gap-2">
                <article
                  className={`w-[178px] rounded-2xl border p-3 transition ${statusStyle[state.status]} ${dimmed && state.status === "pending" ? "opacity-65" : ""}`}
                  title={`可做：${role.allowed_actions.join("、") || role.mission}\n禁止：${role.forbidden_actions.join("、") || "不得越权"}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2 text-xs font-black">
                      <RoleIcon role={role} /> {role.role_id}
                    </span>
                    <span className="flex items-center gap-1 rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-black">
                      {state.status === "completed" && <Check size={10} />}
                      {state.status === "blocked" && <CircleAlert size={10} />}
                      {statusLabel[state.status]}
                    </span>
                  </div>
                  <h3 className="mt-2 text-sm font-black">{role.display_name}</h3>
                  <p className="mt-1 line-clamp-2 min-h-8 text-[11px] font-medium leading-4 opacity-80">
                    {state.note || role.mission}
                  </p>
                  {role.human_gate && <span className="mt-2 inline-flex text-[10px] font-black">人工责任门</span>}
                </article>
                {index < roles.length - 1 && <ArrowRight size={15} className="shrink-0 text-slate-300" />}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
