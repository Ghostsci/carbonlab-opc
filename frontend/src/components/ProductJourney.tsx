import { ArrowRight, Calculator, Check, Database, Fingerprint } from "lucide-react";

export type ProductJourneyStage = "data" | "calculation" | "passport";
export type ProductJourneyStatus = "completed" | "active" | "pending" | "warning";

type Props = {
  active: ProductJourneyStage;
  states?: Partial<Record<ProductJourneyStage, ProductJourneyStatus>>;
  note?: string;
};

const stages = [
  {
    key: "data" as const,
    title: "数据提取与确认",
    roles: "H-00、A-01、A-02、A-03、H-01",
    icon: Database,
  },
  {
    key: "calculation" as const,
    title: "方法与核算",
    roles: "H-02、R-01",
    icon: Calculator,
  },
  {
    key: "passport" as const,
    title: "护照编制发布",
    roles: "A-04、H-03",
    icon: Fingerprint,
  },
];

const labels: Record<ProductJourneyStatus, string> = {
  completed: "已完成",
  active: "进行中",
  pending: "等待中",
  warning: "需关注",
};

const styles: Record<ProductJourneyStatus, string> = {
  completed: "border-emerald-200 bg-emerald-50 text-emerald-900",
  active: "border-blue-400 bg-blue-50 text-blue-900 ring-2 ring-blue-100",
  pending: "border-slate-200 bg-white text-slate-500",
  warning: "border-amber-300 bg-amber-50 text-amber-900",
};

function defaultStatus(stage: ProductJourneyStage, active: ProductJourneyStage): ProductJourneyStatus {
  const order: ProductJourneyStage[] = ["data", "calculation", "passport"];
  const stageIndex = order.indexOf(stage);
  const activeIndex = order.indexOf(active);
  if (stageIndex < activeIndex) return "completed";
  if (stageIndex === activeIndex) return "active";
  return "pending";
}

export default function ProductJourney({ active, states = {}, note }: Props) {
  return (
    <section className="zc-card-pad">
      <div className="grid grid-cols-1 items-stretch gap-3 lg:grid-cols-[1fr_auto_1fr_auto_1fr]">
        {stages.map((stage, index) => {
          const status = states[stage.key] || defaultStatus(stage.key, active);
          const Icon = stage.icon;
          return (
            <div key={stage.key} className="contents">
              <article className={`rounded-2xl border px-4 py-3 ${styles[status]}`}>
                <div className="flex items-start gap-3">
                  <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${status === "active" ? "bg-blue-600 text-white" : status === "completed" ? "bg-emerald-600 text-white" : "bg-slate-100 text-slate-500"}`}>
                    {status === "completed" ? <Check size={19} /> : <Icon size={18} />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center justify-between gap-2">
                      <b className="text-sm font-black">{index + 1}. {stage.title}</b>
                      <small className="rounded-full bg-white/75 px-2 py-1 text-[10px] font-black">{labels[status]}</small>
                    </span>
                    <small className="mt-1 block font-semibold opacity-75">{stage.roles}</small>
                  </span>
                </div>
              </article>
              {index < stages.length - 1 && <ArrowRight className="mx-auto hidden self-center text-slate-300 lg:block" size={19} />}
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-xs font-semibold text-slate-500">
        {note || "AI 提议，规则检查，人类确认，确定性计算，授权发布。"}
      </p>
    </section>
  );
}
