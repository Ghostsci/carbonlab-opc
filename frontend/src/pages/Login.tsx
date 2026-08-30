import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Building2,
  Check,
  Eye,
  EyeOff,
  FileUp,
  Fingerprint,
  Leaf,
  LockKeyhole,
  Mail,
  ShieldCheck,
  UserCheck,
  type LucideIcon,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";

const DEMO_EMAIL = import.meta.env.VITE_DEMO_EMAIL || "";
const DEMO_PASSWORD = import.meta.env.VITE_DEMO_PASSWORD || "";

const WORKFLOW: Array<{
  number: string;
  title: string;
  note: string;
  icon: LucideIcon;
}> = [
  {
    number: "01",
    title: "上传原始文件",
    note: "保留文件身份与内容指纹",
    icon: FileUp,
  },
  {
    number: "02",
    title: "人工确认关键事实",
    note: "AI 不替企业做责任判断",
    icon: UserCheck,
  },
  {
    number: "03",
    title: "生成可追溯碳护照",
    note: "证据、因子、公式与操作留痕",
    icon: Fingerprint,
  },
];

export default function Login() {
  const { login, isLoading } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      await login(email.trim(), password);
      navigate("/");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "登录失败，请核对账号信息后重试");
    } finally {
      setSubmitting(false);
    }
  };

  const enterDemo = async () => {
    setEmail(DEMO_EMAIL);
    setPassword(DEMO_PASSWORD);
    setError("");
    setSubmitting(true);

    try {
      await login(DEMO_EMAIL, DEMO_PASSWORD);
      navigate("/");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "演示账号登录失败，请检查本地服务");
    } finally {
      setSubmitting(false);
    }
  };

  const pending = isLoading || submitting;
  const demoAvailable = Boolean(DEMO_EMAIL && DEMO_PASSWORD);

  return (
    <div className="min-h-[100dvh] bg-slate-50 lg:grid lg:grid-cols-[minmax(0,1.12fr)_minmax(430px,0.88fr)]">
      <section className="relative isolate overflow-hidden bg-[#071a36] px-6 py-8 text-white sm:px-10 lg:flex lg:min-h-[100dvh] lg:flex-col lg:px-12 lg:py-10 xl:px-16">
        <div
          aria-hidden="true"
          className="absolute inset-0 -z-20 bg-[radial-gradient(circle_at_15%_5%,rgba(34,211,238,0.18),transparent_26%),radial-gradient(circle_at_84%_42%,rgba(37,99,235,0.20),transparent_28%),linear-gradient(180deg,#0b2348_0%,#071a36_58%,#06152c_100%)]"
        />
        <div
          aria-hidden="true"
          className="absolute inset-y-0 right-0 -z-10 w-2/3 opacity-20 [background-image:linear-gradient(rgba(96,165,250,0.18)_1px,transparent_1px),linear-gradient(90deg,rgba(96,165,250,0.18)_1px,transparent_1px)] [background-size:42px_42px] [mask-image:linear-gradient(to_left,black,transparent)]"
        />

        <header className="flex items-center gap-3">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-cyan-300/30 bg-cyan-300/10 text-cyan-200 shadow-[0_12px_32px_rgba(8,47,73,0.35)]">
            <Leaf size={25} strokeWidth={2.2} />
          </span>
          <span>
            <b className="block text-2xl font-black tracking-tight">零碳云</b>
            <small className="mt-0.5 block text-xs font-medium tracking-wide text-blue-100/65">AI for Zero Carbon</small>
          </span>
        </header>

        <div className="my-auto py-12 lg:max-w-[820px] lg:py-14">
          <div className="inline-flex items-center gap-2 text-sm font-bold text-cyan-200">
            <ShieldCheck size={17} /> 面向制造企业的可信碳数据工作台
          </div>
          <h1 className="mt-5 max-w-[760px] text-4xl font-black leading-[1.18] tracking-[-0.04em] sm:text-5xl xl:text-[58px]">
            让每一笔碳数据，<br className="hidden sm:block" />都有证据可查
          </h1>
          <p className="mt-6 max-w-[720px] text-base font-medium leading-8 text-blue-100/75 sm:text-lg">
            AI 提取原始资料，人工确认关键事实，确定性规则完成计算，形成可追溯的工厂碳数据护照。
          </p>

          <div className="mt-10 grid gap-3 md:grid-cols-3 lg:mt-14">
            {WORKFLOW.map((step, index) => (
              <WorkflowStep key={step.number} step={step} last={index === WORKFLOW.length - 1} />
            ))}
          </div>
        </div>

        <footer className="flex items-start gap-3 border-t border-white/10 pt-6 text-sm font-semibold leading-6 text-blue-100/80">
          <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-emerald-400/15 text-emerald-300">
            <Check size={16} />
          </span>
          <span>AI 负责提议，人负责判断，系统负责留痕。</span>
        </footer>
      </section>

      <main className="flex items-center justify-center bg-[radial-gradient(circle_at_top_right,#ffffff_0%,#f7faff_48%,#f3f7fd_100%)] px-5 py-8 sm:px-10 lg:min-h-[100dvh] lg:px-12 lg:py-10 xl:px-16">
        <div className="w-full max-w-[560px]">
          <div className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-[0_28px_80px_rgba(30,64,175,0.10)] sm:p-9 xl:p-11">
            <div className="flex items-center gap-2 text-sm font-bold text-blue-600">
              <Building2 size={18} /> 企业工作台
            </div>
            <h2 className="mt-8 text-3xl font-black tracking-tight text-slate-950 sm:text-4xl">登录零碳云</h2>
            <p className="mt-3 text-sm font-medium text-slate-500 sm:text-base">进入您的碳数据工作空间</p>

            {error && (
              <div role="alert" className="mt-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold leading-6 text-red-700">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="mt-8 space-y-5">
              <label className="block">
                <span className="mb-2 block text-sm font-bold text-slate-800">邮箱</span>
                <span className="relative block">
                  <Mail aria-hidden="true" size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    className="h-[52px] w-full rounded-xl border border-slate-200 bg-white py-3 pl-11 pr-4 text-base text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-blue-400 focus:ring-4 focus:ring-blue-100"
                    placeholder="请输入企业邮箱"
                    autoComplete="email"
                    required
                    autoFocus
                  />
                </span>
              </label>

              <label className="block">
                <span className="mb-2 block text-sm font-bold text-slate-800">密码</span>
                <span className="relative block">
                  <LockKeyhole aria-hidden="true" size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    className="h-[52px] w-full rounded-xl border border-slate-200 bg-white py-3 pl-11 pr-12 text-base text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-blue-400 focus:ring-4 focus:ring-blue-100"
                    placeholder="请输入密码"
                    autoComplete="current-password"
                    required
                    minLength={6}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((current) => !current)}
                    className="absolute right-2 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
                    aria-label={showPassword ? "隐藏密码" : "显示密码"}
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </span>
              </label>

              <button
                type="submit"
                disabled={pending}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 py-3.5 text-base font-bold text-white shadow-[0_14px_30px_rgba(37,99,235,0.25)] transition hover:bg-blue-700 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-60"
              >
                {pending ? "正在安全登录..." : "登录"}
                {!pending && <ArrowRight size={18} />}
              </button>

              {demoAvailable && (
                <button
                  type="button"
                  onClick={enterDemo}
                  disabled={pending}
                  className="flex w-full items-center justify-center rounded-xl border border-blue-200 bg-white px-5 py-3.5 text-base font-bold text-blue-700 transition hover:border-blue-300 hover:bg-blue-50 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {submitting ? "正在进入演示..." : "一键进入演示"}
                </button>
              )}
            </form>

            <div className="mt-8 border-t border-slate-100 pt-6">
              <div className="flex items-start gap-3 text-xs font-medium leading-5 text-slate-500">
                <ShieldCheck size={18} className="mt-0.5 shrink-0 text-emerald-600" />
                <p>本系统生成的是可追溯数据档案，不替代政府证件或第三方核查结论。</p>
              </div>
              <p className="mt-5 text-center text-xs font-medium text-slate-400">企业账号由管理员统一开通</p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

function WorkflowStep({
  step,
  last,
}: {
  step: (typeof WORKFLOW)[number];
  last: boolean;
}) {
  const Icon = step.icon;
  return (
    <div className="relative rounded-2xl border border-white/10 bg-white/[0.055] p-4 backdrop-blur-sm sm:p-5">
      {!last && (
        <span aria-hidden="true" className="absolute -right-3 top-9 hidden h-px w-6 bg-blue-300/50 md:block" />
      )}
      <div className="flex items-center justify-between gap-3">
        <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-500/15 text-blue-100 ring-1 ring-inset ring-blue-300/20">
          <Icon size={21} />
        </span>
        <small className="font-mono text-xs font-bold tracking-wider text-blue-200/55">{step.number}</small>
      </div>
      <b className="mt-5 block text-sm text-white sm:text-base">{step.title}</b>
      <p className="mt-2 text-xs leading-5 text-blue-100/60">{step.note}</p>
    </div>
  );
}
