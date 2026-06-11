import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { Activity, AlertTriangle, BarChart2, Wrench, Bot } from "lucide-react";
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
      <div className="flex h-screen bg-[#0a0e1a] text-[#e5e7eb] overflow-hidden">
        {/* Sidebar */}
        <aside className="w-56 shrink-0 bg-[#111827] border-r border-[#1f2937] flex flex-col">
          <div className="px-4 py-5 border-b border-[#1f2937]">
            <div className="text-xs font-bold text-[#6b7280] tracking-widest uppercase">PNT</div>
            <div className="text-lg font-bold text-white leading-tight">Factory Monitor</div>
            <div className="text-xs text-[#6b7280]">롤투롤 2차전지 공정</div>
          </div>
          <nav className="flex-1 p-3 space-y-1">
            {navItems.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                    isActive
                      ? "bg-blue-600 text-white"
                      : "text-[#9ca3af] hover:bg-[#1f2937] hover:text-white"
                  }`
                }
              >
                <Icon size={16} />
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="p-4 border-t border-[#1f2937] text-xs text-[#6b7280]">
            <div>gpt-5.4-mini / nano</div>
            <div className="flex items-center gap-1 mt-1">
              <span className="w-2 h-2 rounded-full bg-green-500 inline-block"></span>
              <span>시뮬레이터 가동 중</span>
            </div>
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
