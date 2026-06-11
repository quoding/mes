import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { Activity, AlertTriangle, BarChart2, Wrench, Bot, Hexagon, Sun, Moon } from "lucide-react";
import { useThemeStore } from "@/stores/themeStore";
import DashboardPage from "@/pages/DashboardPage";
import ProcessPage from "@/pages/ProcessPage";
import AnomalyPage from "@/pages/AnomalyPage";
import MaintenancePage from "@/pages/MaintenancePage";
import AgentPage from "@/pages/AgentPage";

const navItems = [
  { to: "/", icon: Activity, label: "대시보드" },
  { to: "/process", icon: BarChart2, label: "공정 모니터" },
  { to: "/anomaly", icon: AlertTriangle, label: "이상 탐지" },
  { to: "/maintenance", icon: Wrench, label: "예지보전" },
  { to: "/agent", icon: Bot, label: "AI 에이전트" },
];

function ThemeToggle() {
  const theme = useThemeStore((s) => s.theme);
  const toggle = useThemeStore((s) => s.toggle);
  return (
    <button
      onClick={toggle}
      className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-xs text-[var(--muted2)] hover:bg-[var(--border)]/60 hover:text-[var(--text-strong)] transition-colors"
      title={theme === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환"}
    >
      {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
      {theme === "dark" ? "라이트 모드" : "다크 모드"}
    </button>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen text-[var(--text)] overflow-hidden">
        {/* Sidebar */}
        <aside className="w-56 shrink-0 bg-[var(--surface)]/80 backdrop-blur-md border-r border-[var(--border)] flex flex-col">
          <div className="px-4 py-5 border-b border-[var(--border)]">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[var(--accent)] to-[#6366f1] flex items-center justify-center shadow-[0_0_16px_rgba(56,189,248,0.35)]">
                <Hexagon size={18} className="text-white" strokeWidth={2.4} />
              </div>
              <div>
                <div className="text-[10px] font-bold text-[var(--accent)] tracking-[0.2em]">PNT</div>
                <div className="text-sm font-bold text-[var(--text-strong)] leading-tight">Factory Monitor</div>
              </div>
            </div>
            <div className="text-[10px] text-[var(--muted)] mt-2">롤투롤 2차전지 전극 공정</div>
          </div>
          <nav className="flex-1 p-3 space-y-1">
            {navItems.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  `relative flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all ${
                    isActive
                      ? "bg-gradient-to-r from-[var(--accent)]/15 to-transparent text-[var(--text-strong)] font-medium before:absolute before:left-0 before:top-1.5 before:bottom-1.5 before:w-0.5 before:rounded-full before:bg-[var(--accent)]"
                      : "text-[var(--muted2)] hover:bg-[var(--border)]/60 hover:text-[var(--text-strong)]"
                  }`
                }
              >
                <Icon size={16} />
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="px-3 pb-1">
            <ThemeToggle />
          </div>
          <div className="p-4 border-t border-[var(--border)] text-[10px] text-[var(--muted)] space-y-0.5 leading-relaxed">
            <div className="text-[var(--muted2)] font-medium">4-Layer Anomaly Detection</div>
            <div>Z-score · EWMA · iForest · 상관 시그니처</div>
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 overflow-auto">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/process" element={<ProcessPage />} />
            <Route path="/anomaly" element={<AnomalyPage />} />
            <Route path="/maintenance" element={<MaintenancePage />} />
            <Route path="/agent" element={<AgentPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
