import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { PredictiveMaintPanel } from "@/components/PredictiveMaint/RiskCard";
import type { Equipment } from "@/types/mes";
import { RefreshCw, Wrench } from "lucide-react";

export default function MaintenancePage() {
  const qc = useQueryClient();
  const [generating, setGenerating] = useState<number | null>(null);

  const { data: equipment = [] } = useQuery<Equipment[]>({
    queryKey: ["equipment"],
    queryFn: () => api.get("/maintenance/equipment").then((r) => r.data),
  });

  const generateReport = useMutation({
    mutationFn: (id: number) => api.post(`/maintenance/reports/generate/${id}`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["maintenance-reports"] });
      setGenerating(null);
    },
  });

  const daysUntil = (next: string | null) => {
    if (!next) return null;
    const diff = Math.ceil((new Date(next).getTime() - Date.now()) / 86_400_000);
    return diff;
  };

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold text-[var(--text-strong)]">예지보전</h1>
      <p className="text-sm text-[var(--muted)]">
        과거 이상 이력 기반 통계적 패턴 매칭 + AI 리포트 생성
      </p>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Equipment list */}
        <div>
          <h2 className="text-sm font-semibold text-[var(--muted2)] mb-3 uppercase tracking-wide">
            설비 목록
          </h2>
          <div className="space-y-2">
            {equipment.map((eq) => {
              const days = daysUntil(eq.next_maintenance);
              const urgent = days !== null && days < 7;
              return (
                <div
                  key={eq.id}
                  className={`bg-[var(--surface)] border rounded-xl p-4 flex items-center gap-4 ${
                    urgent ? "border-yellow-700" : "border-[var(--border)]"
                  }`}
                >
                  <Wrench size={16} className={urgent ? "text-yellow-400" : "text-[var(--muted)]"} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-[var(--text-strong)]">{eq.name}</div>
                    <div className="text-xs text-[var(--muted)]">
                      Line {eq.line_id} / {eq.station} · {eq.total_hours.toFixed(0)}h
                    </div>
                    {eq.next_maintenance && (
                      <div className={`text-xs mt-0.5 ${urgent ? "text-yellow-400" : "text-[var(--muted)]"}`}>
                        다음 정비: {new Date(eq.next_maintenance).toLocaleDateString("ko-KR")}
                        {days !== null && ` (${days}일 후)`}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => {
                      setGenerating(eq.id);
                      generateReport.mutate(eq.id);
                    }}
                    disabled={generating === eq.id}
                    className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white transition-colors"
                  >
                    <RefreshCw size={12} className={generating === eq.id ? "animate-spin" : ""} />
                    리포트
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        {/* Reports */}
        <div>
          <h2 className="text-sm font-semibold text-[var(--muted2)] mb-3 uppercase tracking-wide">
            예지보전 리포트
          </h2>
          <PredictiveMaintPanel />
        </div>
      </div>
    </div>
  );
}
