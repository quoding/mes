import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { Activity, AlertTriangle, BarChart2, Wrench, Bot, Hexagon } from "lucide-react";
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

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen text-[#e2e8f0] overflow-hidden">
        {/* Sidebar */}
        <aside className="w-56 shrink-0 bg-[#0d1322]/80 backdrop-blur-md border-r border-[#1c2740] flex flex-col">
          <div className="px-4 py-5 border-b border-[#1c2740]">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#38bdf8] to-[#6366f1] flex items-center justify-center shadow-[0_0_16px_rgba(56,189,248,0.35)]">
                <Hexagon size={18} className="text-white" strokeWidth={2.4} />
              </div>
              <div>
                <div className="text-[10px] font-bold text-[#38bdf8] tracking-[0.2em]">PNT</div>
                <div className="text-sm font-bold text-white leading-tight">Factory Monitor</div>
              </div>
            </div>
            <div className="text-[10px] text-[#64748b] mt-2">롤투롤 2차전지 전극 공정</div>
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
                      ? "bg-gradient-to-r from-[#38bdf8]/15 to-transparent text-white font-medium before:absolute before:left-0 before:top-1.5 before:bottom-1.5 before:w-0.5 before:rounded-full before:bg-[#38bdf8]"
                      : "text-[#7c8db5] hover:bg-[#1c2740]/60 hover:text-white"
                  }`
                }
              >
                <Icon size={16} />
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="p-4 border-t border-[#1c2740] text-[10px] text-[#64748b] space-y-0.5 leading-relaxed">
            <div className="text-[#7c8db5] font-medium">4-Layer Anomaly Detection</div>
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
