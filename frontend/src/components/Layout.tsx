import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import {
  Building2,
  Bot,
  Calculator,
  ChevronDown,
  Fingerprint,
  HelpCircle,
  Inbox,
  LogOut,
  Menu,
  UserCircle,
  X,
} from "lucide-react";
import { useState } from "react";

const NAV_ITEMS = [
  { to: "/upload", zh: "数字员工工作台", en: "AI Workflow", icon: Inbox },
  { to: "/calculations", zh: "核算工作台", en: "Calculation", icon: Calculator },
  { to: "/passports", zh: "工厂碳数据护照", en: "Passport", icon: Fingerprint },
  { to: "/agent-ops", zh: "数字员工治理", en: "AgentOps", icon: Bot },
];

function roleLabel(role?: string) {
  if (role === "platform_admin") return "平台管理员";
  if (role === "admin") return "ESG 负责人";
  if (role === "manager") return "碳管理经理";
  if (role === "auditor") return "核查员";
  return "ESG 负责人";
}

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="zc-app">
      <button
        className="fixed left-4 top-4 z-50 rounded-xl bg-slate-900 p-2 text-white shadow-lg lg:hidden"
        onClick={() => setMobileOpen(true)}
        aria-label="打开导航"
      >
        <Menu size={20} />
      </button>

      <aside className={`fixed inset-y-0 left-0 z-50 w-[300px] bg-[#0d1b36] text-white shadow-2xl transition-transform duration-300 lg:translate-x-0 ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex h-full flex-col bg-[radial-gradient(circle_at_20%_0%,rgba(40,184,255,0.22),transparent_28%),linear-gradient(180deg,#102344_0%,#09172f_100%)] px-4 py-6">
          <div className="mb-9 flex items-center justify-between px-2">
            <div className="flex items-center gap-3">
              <div className="relative flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-400 to-blue-600 shadow-lg shadow-blue-950/40">
                <span className="text-2xl font-black">♧</span>
              </div>
              <div>
                <div className="text-2xl font-black tracking-tight">零碳云</div>
                <div className="text-xs text-blue-100/70">AI for Zero Carbon</div>
              </div>
            </div>
            <button className="rounded-lg p-1.5 text-blue-100 lg:hidden" onClick={() => setMobileOpen(false)}>
              <X size={18} />
            </button>
          </div>

          <nav className="space-y-2">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  onClick={() => setMobileOpen(false)}
                  className={({ isActive }) =>
                    `group flex items-center gap-3 rounded-xl px-4 py-3 text-[15px] font-semibold transition ${
                      isActive
                        ? "bg-blue-600 text-white shadow-lg shadow-blue-950/30"
                        : "text-blue-100/82 hover:bg-white/8 hover:text-white"
                    }`
                  }
                >
                  <Icon size={21} strokeWidth={2.2} />
                  <span className="min-w-0 flex-1 truncate">{item.zh}</span>
                  {item.en && <span className="text-xs font-medium text-blue-100/70">{item.en}</span>}
                </NavLink>
              );
            })}
          </nav>

          <div className="mt-auto space-y-4">
            <div className="rounded-xl border border-white/8 bg-white/8 p-3">
              <div className="flex items-center gap-3">
                <Building2 size={18} className="text-blue-100" />
                <div className="min-w-0 flex-1 truncate text-sm font-semibold">演示制造企业</div>
                <ChevronDown size={16} className="text-blue-100/70" />
              </div>
            </div>

            <div className="flex items-center gap-3 rounded-xl px-2 py-2">
              <div className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-blue-100 to-slate-300 text-slate-700">
                <UserCircle size={38} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-bold">{user?.email ?? "演示用户"}</div>
                <div className="truncate text-xs text-blue-100/65">{roleLabel(user?.role)}</div>
              </div>
              <button onClick={handleLogout} className="rounded-lg p-2 text-blue-100/70 hover:bg-white/10 hover:text-white" title="退出">
                <LogOut size={17} />
              </button>
            </div>
          </div>
        </div>
      </aside>

      <main className="zc-main">
        <Outlet />
      </main>

      <div className="fixed right-8 top-6 z-30 hidden gap-3 lg:flex">
        <button className="zc-button h-11 px-4">
          <Building2 size={17} className="text-blue-600" />
          演示制造企业
          <ChevronDown size={16} />
        </button>
        <button className="relative flex h-11 w-11 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 shadow-sm">
          <span className="absolute -right-1 -top-1 rounded-full bg-red-500 px-1.5 text-[10px] font-bold text-white">8</span>
          🔔
        </button>
        <button className="flex h-11 w-11 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 shadow-sm">
          <HelpCircle size={18} />
        </button>
        <button className="flex h-11 w-11 items-center justify-center overflow-hidden rounded-full border border-slate-200 bg-gradient-to-br from-blue-100 to-slate-300 text-slate-700 shadow-sm">
          <UserCircle size={32} />
        </button>
      </div>
    </div>
  );
}
