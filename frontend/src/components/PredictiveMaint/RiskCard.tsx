import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { MaintenanceReport } from "@/types/mes";
import { Wrench, TrendingUp } from "lucide-react";

function riskColor(score: number) {
  if (score >= 70) return "text-red-400";
  if (score >= 40) return "text-yellow-400";
  return "text-green-400";
}

function riskLabel(score: number) {
  if (score >= 70) return "🔴 고위험";
  if (score >= 40) return "🟠 중위험";
  return "✅ 정상";
}

function RiskGauge({ score }: { score: number }) {
  const pct = Math.min(100, score);
  const color = score >= 70 ? "#ef4444" : score >= 40 ? "#f59e0b" : "#10b981";
  return (
    <div className="relative w-16 h-16">
      <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
        <circle cx="18" cy="18" r="15.9" fill="none" stroke="#1f2937" strokeWidth="3" />
        <circle
          cx="18" cy="18" r="15.9" fill="none"
          stroke={color} strokeWidth="3"
          strokeDasharray={`${pct} 100`}
          strokeLinecap="round"
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className={`text-sm font-bold ${riskColor(score)}`}>{score.toFixed(0)}</span>
      </div>
    </div>
  );
}

export function RiskCard({ report }: { report: MaintenanceReport }) {
  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
      <div className="flex items-start gap-4">
        <RiskGauge score={report.risk_score} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Wrench size={14} className="text-[#9ca3af]" />
            <span className="text-sm font-semibold text-white">설비 #{report.equipment_id}</span>
            <span className={`text-xs ${riskColor(report.risk_score)}`}>
              {riskLabel(report.risk_score)}
            </span>
          </div>
          {report.similar_case_date && (
            <div className="text-xs text-[#6b7280] mb-2">
              <TrendingUp size={11} className="inline mr-1" />
              유사 사례: {new Date(report.similar_case_date).toLocaleDateString("ko-KR")}
            </div>
          )}
          {report.llm_summary && (
            <div className="text-xs text-[#9ca3af] leading-relaxed whitespace-pre-wrap line-clamp-4">
              {report.llm_summary}
            </div>
          )}
          <div className="text-xs text-[#4b5563] mt-2">
            {new Date(report.generated_at).toLocaleString("ko-KR")}
          </div>
        </div>
      </div>
    </div>
  );
}


export function PredictiveMaintPanel() {
  const { data: reports, isLoading } = useQuery<MaintenanceReport[]>({
    queryKey: ["maintenance-reports"],
    queryFn: () => api.get("/maintenance/reports").then((r) => r.data),
    refetchInterval: 120_000,
  });

  if (isLoading) return <div className="text-[#6b7280] text-sm p-4">예지보전 데이터 로딩 중…</div>;
  if (!reports?.length) return (
    <div className="text-[#6b7280] text-sm p-4">
      설비 리포트 없음. 씨드 후 /api/maintenance/reports/generate/&#123;id&#125; 호출하세요.
    </div>
  );

  return (
    <div className="space-y-3">
      {reports.map((r) => (
        <RiskCard key={r.id} report={r} />
      ))}
    </div>
  );
}
